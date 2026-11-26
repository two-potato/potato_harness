"""Host-owned at-most-once handoff for the exact attached subtotal trial.

The operator and host UID are trusted. This is not a boundary against an
operator who can modify the host interpreter, process or database. A live
handoff additionally binds explicit trust in the shared OpenCode transport;
its worker must verify a signed review of that specific trust policy.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from datetime import datetime, timezone

from harness.controller import Controller, _json
from harness.context import compile_context
from harness.leases import LeaseManager
from harness.policy import authorize
from harness.verifier import action_digest
from harness.runtime import attached_trial as trial

def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()

TRUST_PROFILE='attached-trusted-opencode-subtotal-v2'
FIXTURE_PROFILE='attached-controlled-fixture-v1'

def issue(request, *, adapter, trust_attached_opencode, max_bridge_timeout_ms):
    if (adapter not in trial.ADAPTERS or
            type(trust_attached_opencode) is not bool or
            trust_attached_opencode!=(adapter==trial.ADAPTER) or
            type(max_bridge_timeout_ms) is not int or not 4000<max_bridge_timeout_ms<=80000):
        raise ValueError('Attached handoff requires exact trust and deadline scope')
    nonce=secrets.token_hex(32)
    return nonce, {'nonce_sha256':_hash(nonce),'request_sha256':_hash(_json(request)),
                   'operator_confirmed':True,
                   'trust_profile':TRUST_PROFILE if adapter==trial.ADAPTER else FIXTURE_PROFILE,
                   'max_bridge_timeout_ms':max_bridge_timeout_ms}

def _private(path, directory=False, private_mode=True):
    s=path.lstat()
    if (path.resolve(strict=True)!=path or s.st_uid!=os.getuid() or
            (private_mode and s.st_mode & 0o077) or
            (not stat.S_ISDIR(s.st_mode) if directory else
             not stat.S_ISREG(s.st_mode) or s.st_nlink!=1)):
        raise ValueError('Unsafe attached handoff state')

def consume(envelope, *, expected_adapter=trial.FIXTURE_ADAPTER):
    from harness.runtime import _config
    if expected_adapter not in trial.ADAPTERS:raise ValueError('Invalid attached worker mode')
    live=expected_adapter==trial.ADAPTER
    if (type(envelope) is not dict or set(envelope)!={'state','nonce','bridge_timeout_ms'} or
            type(envelope['state']) is not str or type(envelope['nonce']) is not str or
            not re.fullmatch('[a-f0-9]{64}',envelope['nonce']) or
            type(envelope['bridge_timeout_ms']) is not int or not 4000<envelope['bridge_timeout_ms']<=80000):
        raise ValueError('Attached handoff envelope invalid')
    state=Path(envelope['state'])
    if not state.is_absolute():raise ValueError('Absolute attached state required')
    _private(state,True)
    for name in ('config.json','run.json','state.db'):_private(state/name)
    _private(state/'run.lock',private_mode=False)
    # A running trusted parent must hold the existing runtime lock.
    with (state/'run.lock').open('rb') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:pass
        else:raise ValueError('Attached runtime lock is not held')
    cfg=_config(json.loads((state/'config.json').read_text()))
    run=json.loads((state/'run.json').read_text())
    profile=TRUST_PROFILE if live else FIXTURE_PROFILE
    if (cfg.get('adapter')!=expected_adapter or run.get('adapter')!=expected_adapter or
            run.get('provider_mode')!=('external' if live else 'synthetic') or run.get('state')!='RUNNING' or
            run.get('transport_trust')!=profile):
        raise ValueError('Attached handoff does not match running adapter and trust profile')
    trial.verify_source(Path(cfg['repo']).resolve(strict=True),cfg['base_sha'])
    workspace=state/'workspace';trial.verify_workspace(workspace)
    project=state/'provider-project';_private(project,True)
    if any(project.iterdir()):raise ValueError('Attached provider project must be empty')
    controller=Controller(state/'state.db')
    with controller._connection(write=True) as db:
        task=controller._read(db,run['task_id'])
        effect=db.execute('SELECT * FROM outbox WHERE effect_id=?',(run['effect_id'],)).fetchone()
        if (not effect or effect['state']!='DISPATCHING' or effect['task_id']!=task['task_id'] or
                effect['task_revision']!=task['revision'] or task['status']!='EXECUTING' or
                task['owner']!='backend' or task['objective']!=trial.OBJECTIVE or task['scope']!=['calculation.py'] or
                task['base_commit']['value']!=cfg['base_sha']):
            raise ValueError('Attached handoff requires current claimed Outbox')
        action=json.loads(effect['payload_json'])
        if (action_digest(action)!=effect['action_digest'] or action.get('kind')!='provider-proposal' or
                action.get('adapter')!=expected_adapter or action.get('model')!=trial.MODEL or
                action.get('owner')!='backend' or action.get('cost_allowance_usd')!=0 or
                action.get('token_allowance')!=cfg['budget']['tokens'] or action.get('attempt_id')!=run['attempt_id'] or
                action.get('lease_id')!=run['lease_id']):
            raise ValueError('Attached handoff action mismatch')
        binding=action.get('attached_handoff')
        if (type(binding) is not dict or binding.get('operator_confirmed') is not True or
                binding.get('nonce_sha256')!=_hash(envelope['nonce']) or binding.get('trust_profile')!=profile or
                type(binding.get('max_bridge_timeout_ms')) is not int or
                not envelope['bridge_timeout_ms']<=binding['max_bridge_timeout_ms']<=80000):
            raise ValueError('Attached handoff nonce mismatch')
        reservation=db.execute('SELECT * FROM budget_reservations WHERE attempt_id=?',(run['attempt_id'],)).fetchone()
        if (not reservation or reservation['budget_id']!=task['budget_id'] or
                reservation['settlement'] is not None or reservation['tokens']!=cfg['budget']['tokens'] or
                reservation['cost']!=0):
            raise ValueError('Attached handoff reservation mismatch')
        lease=LeaseManager(state/'state.db')._validate(db,action['lease_id'],task['task_id'],task['revision'],
                                                     action['session'],action['workspace'])
        if lease['fencing_token']!=action['fencing_token'] or lease['resources']!=[{'kind':'path','key':'calculation.py'}]:
            raise ValueError('Attached handoff lease mismatch')
        grant=run['grant']
        context={k:grant[k] for k in ('task_id','task_revision','agent_id','worker_session_id','workspace_id','policy_digest','fencing_token')}
        context['workspace_root']=str(workspace)
        if (context['task_id'],context['task_revision'],context['agent_id'],context['worker_session_id'],
                context['workspace_id'],context['fencing_token'])!=(task['task_id'],task['revision'],'backend',
                    action['session'],action['workspace'],action['fencing_token']):
            raise ValueError('Attached handoff grant mismatch')
        authorize(grant['grant_id'],{'action':'read','path':'calculation.py'},context,lambda _:grant,lambda:datetime.now(timezone.utc))
        segments=[{'name':'task-contract','text':_json({'objective':trial.OBJECTIVE,'scope':['calculation.py'],
                   'required_output':{'edits':[{'path':'exact scoped path','content':'replacement UTF-8 text'}],'summary':'brief explanation'}}),
                   'mandatory':True,'trust':'untrusted'},
                  {'name':'calculation.py','text':trial.FILES['calculation.py'].decode(),'mandatory':True,'trust':'untrusted'}]
        pack=compile_context(task,{'role':'backend','session_id':action['session']},segments,
                             cfg['budget']['tokens']-1,lambda text:len(text.encode()))
        if pack['content_hash']!=action['context_digest'] or pack['content_hash']!=run['context']['digest']:
            raise ValueError('Attached handoff context mismatch')
        request={'role':'backend','prompt':pack['text'],'model':trial.MODEL,'projectDir':str(project),
                 'coordination':{'objective':trial.OBJECTIVE,'scope':['calculation.py']},
                 'output_token_allowance':2048,'token_allowance':cfg['budget']['tokens']}
        if binding.get('request_sha256')!=_hash(_json(request)):
            raise ValueError('Attached handoff exact request mismatch')
        if db.execute("UPDATE attached_worker_handoffs SET state='CONSUMED' WHERE effect_id=? AND nonce_sha256=? AND state='ISSUED'",
                      (run['effect_id'],_hash(envelope['nonce']))).rowcount!=1:
            raise ValueError('Attached handoff already consumed or absent')
    return {**request,'bridge_timeout_ms':envelope['bridge_timeout_ms']}

def main(expected_adapter=trial.FIXTURE_ADAPTER):
    try:
        raw=sys.stdin.buffer.read(8193)
        if len(raw)>8192:raise ValueError('Oversized handoff')
        sys.stdout.write(_json(consume(json.loads(raw),expected_adapter=expected_adapter))+'\n')
        return 0
    except Exception:
        sys.stderr.write('Attached host handoff rejected.\n')
        return 2
