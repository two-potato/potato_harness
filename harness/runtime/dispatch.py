"""Atomic trusted-host provider dispatch reservation; no provider execution.

The caller has already obtained the task grant, private workspace and lease.
This is not a replacement for scheduler, capability authorization, process
isolation or the provider's usage/billing evidence.
"""
import re

from harness.budget import Budget
from harness.controller import Controller, ControllerError
from harness.leases import LeaseManager
from harness.scheduler import SPECIALISTS
from harness.state import Outbox
from harness.runtime.attached_trial import ADAPTERS,ADAPTER


def reserve_provider_dispatch(database, *, task_id, revision, row_version, owner,
                              lease_id, session, workspace, model, context_digest,
                              tokens, cost, adapter=None, attached_handoff=None):
    if (type(revision) is not int or type(row_version) is not int or
            type(owner) is not str or owner not in SPECIALISTS or
            type(model) is not str or not model.strip() or
            type(context_digest) is not str or not re.fullmatch(r'sha256:[a-f0-9]{64}',context_digest) or
            (adapter is not None and (type(adapter) is not str or not adapter.strip()))):
        raise ControllerError('Invalid trusted dispatch bindings')
    if adapter in ADAPTERS:
        from harness.runtime.attached_handoff import TRUST_PROFILE,FIXTURE_PROFILE
        if (type(attached_handoff) is not dict or set(attached_handoff)!={'nonce_sha256','request_sha256','operator_confirmed','trust_profile','max_bridge_timeout_ms'} or
                attached_handoff['trust_profile']!=(TRUST_PROFILE if adapter==ADAPTER else FIXTURE_PROFILE) or
                type(attached_handoff['max_bridge_timeout_ms']) is not int or not 4000<attached_handoff['max_bridge_timeout_ms']<=80000 or
                attached_handoff['operator_confirmed'] is not True or cost!=0 or
                any(type(attached_handoff[k]) is not str or not re.fullmatch('[a-f0-9]{64}',attached_handoff[k])
                    for k in ('nonce_sha256','request_sha256'))):
            raise ControllerError('Attached dispatch requires exact confirmed handoff')
    elif attached_handoff is not None:
        raise ControllerError('Attached handoff cannot authorize another adapter')
    controller=Controller(database)
    budget=Budget(database)
    outbox=Outbox(database)
    leases=LeaseManager(database)
    attempt='provider-'+task_id
    key='provider:'+task_id
    with controller._connection(write=True) as db:
        task=controller._read(db,task_id)
        if (task['revision'],task['row_version'],task['owner'],task['status'])!=(revision,row_version,owner,'EXECUTING'):
            raise ControllerError('Stale or unauthorized dispatch task')
        lease=leases._validate(db,lease_id,task_id,revision,session,workspace)
        if {(r['kind'],r['key']) for r in lease['resources']}!={('path',p) for p in task['scope']}:
            raise ControllerError('Lease must bind exact task scope')
        # The bounded proposal is at most once per task. Unknown outcomes are
        # never re-claimed; repair/reassignment is a separate future protocol.
        if db.execute("SELECT 1 FROM outbox WHERE task_id=? AND (idempotency_key=? OR state IN ('PENDING','DISPATCHING','UNKNOWN'))",(task_id,key)).fetchone():
            raise ControllerError('Prior dispatch or unresolved effect; reconcile before new task')
        if db.execute('SELECT 1 FROM budget_reservations WHERE attempt_id=?',(attempt,)).fetchone():
            raise ControllerError('Prior reservation; reconcile before new task')
        budget._reserve(db,task_id,tokens,cost,attempt)
        action={'kind':'provider-proposal','model':model,'context_digest':context_digest,
                'owner':owner,'lease_id':lease_id,'fencing_token':lease['fencing_token'],
                'session':session,'workspace':workspace,'attempt_id':attempt,
                'token_allowance':tokens,'cost_allowance_usd':cost}
        if adapter is not None:action['adapter']=adapter
        if attached_handoff is not None:
            action['attached_handoff']=dict(attached_handoff)
        effect=outbox._reserve(db,task_id,revision,action,key)
        if not outbox._claim(db,effect):
            raise ControllerError('Dispatch claim denied')
        if attached_handoff is not None:
            db.execute("CREATE TABLE IF NOT EXISTS attached_worker_handoffs(effect_id TEXT PRIMARY KEY REFERENCES outbox(effect_id), nonce_sha256 TEXT UNIQUE NOT NULL, state TEXT NOT NULL CHECK(state IN ('ISSUED','CONSUMED')))")
            db.execute("INSERT INTO attached_worker_handoffs VALUES(?,?,'ISSUED')",(effect,attached_handoff['nonce_sha256']))
        return {'effect_id':effect,'attempt_id':attempt}
