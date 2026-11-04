"""End-to-end local demo with real Git, tests, SQLite and evidence rejection."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import html
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid

from harness.controller import Controller, Event, initialize
from harness.jev import Jev
from harness.verifier import TrustedEvidence, VerificationError, digest_bytes, verify_bundle
from .worker import SOURCE, prepare, apply_proposal, test_candidate, git

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ('success', 'failed-tests', 'stale-evidence', 'unauthorized')


class DemoGuard:
    """Host-only toy policy. Does not authorize arbitrary repositories or agents."""
    def __init__(self):
        self.ready = False
        self.artifact = False
        self.verified = False
        self.audit = False
        self.finished = False

    def __call__(self, context):
        state = context.after['status']
        if context.event.kind == 'pin_target':
            return self.artifact
        if state == 'BLOCKED':
            return True
        if state in ('CLASSIFIED', 'PLANNED', 'ASSIGNED', 'EXECUTING'):
            return self.ready
        if state in ('REVIEWING', 'VERIFYING'):
            return self.artifact
        if state in ('COMPLETION_AUDITING', 'REREVIEW'):
            return self.verified
        if state == 'ACCEPTED':
            return self.verified and self.audit
        if state == 'DONE':
            return self.verified and self.audit and self.finished
        return False


def run_scenario(scenario, *, proposal=None, adapter='offline', jev_provider=None, jev_completion=False):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown demo scenario')
    start = time.perf_counter()
    report = {'scenario': scenario, 'adapter': adapter, 'status': None, 'verified': False,
              'reason': '', 'operator': None, 'baseline_returncode': None,
              'candidate_returncode': None, 'revision': 0, 'timeline': [], 'evidence': [],
              'model_requests': 0, 'api_cost': None}
    with tempfile.TemporaryDirectory(prefix='potato-demo-') as temp:
        root = Path(temp)
        repo = root / 'repo'
        repo.mkdir()
        base = prepare(repo)
        report.update(base_commit=base, target_commit=base)
        baseline_code, baseline_log = test_candidate(repo)
        report.update(baseline_returncode=baseline_code, baseline_log=baseline_log.decode())
        if baseline_code == 0:
            raise RuntimeError('Demo baseline unexpectedly passed')
        db = root / 'state.db'
        initialize(db)
        guard = DemoGuard()
        controller = Controller(db, guard=guard)
        task = json.loads((ROOT / 'fixtures/valid/task.json').read_text())
        task.update(task_id='demo-' + scenario, workflow_id='portfolio', user_turn_id='local-demo-' + str(uuid.uuid4()),
                    repository_id='disposable-demo-repository', revision=0, row_version=0,
                    owner='backend', task_class='BOUNDED', risk='LOW', objective='Correct integer-cent subtotal',
                    scope=['calculation.py'], non_goals=['arbitrary code', 'deployment'],
                    acceptance=[{'id':'subtotal', 'expected':'subtotal equals unit cents times quantity',
                                 'requires':['relevant_checks', 'basic_review']}],
                    base_commit={'hash_algorithm':'sha1', 'value':base},
                    target_commit={'hash_algorithm':'sha1', 'value':base},
                    required_checks=['acceptance_coverage', 'relevant_checks', 'basic_review'],
                    policy_version='portfolio-demo-v1', budget_id='one-local-attempt')
        controller.create_task(task, event_id='intake', idempotency_key='intake')
        report['timeline'].append({'state':'NEW', 'row_version':0, 'revision':0})

        def move(state, reference=None):
            nonlocal task
            task = controller.transition(task['task_id'], task['row_version'],
                                         Event('event-' + str(task['row_version']),
                                               'key-' + str(task['row_version']), state, reference=reference))
            report['timeline'].append({'state':state, 'row_version':task['row_version'], 'revision':task['revision']})

        jev = Jev(db, provider=jev_provider)
        report['jev_preflight'] = jev.preflight(task['task_id'])
        guard.ready = True
        for state in ('CLASSIFIED', 'PLANNED', 'ASSIGNED', 'EXECUTING'):
            move(state)
        try:
            candidate = proposal if scenario == 'success' and proposal is not None else {
                'operator':'add' if scenario == 'failed-tests' else 'multiply'}
            report['operator'] = candidate.get('operator') if isinstance(candidate, dict) else None
            from harness.policy import authorize
            from harness.leases import LeaseManager
            from harness.publisher import Publisher
            manager=LeaseManager(db)
            lease=manager.acquire(task['task_id'],task['row_version'],'demo-worker','demo-workspace',[{'kind':'path','key':'calculation.py'}])
            grant = json.loads((ROOT / 'fixtures/valid/capability-grant.json').read_text())
            policy_digest = digest_bytes((ROOT / 'policy/checks.json').read_bytes())
            grant.update(grant_id='demo-edit', task_id=task['task_id'], task_revision=task['revision'], agent_id='backend', worker_session_id='demo-worker', workspace_id='demo-workspace', actions=['edit'], paths=['calculation.py'], policy_digest=policy_digest, fencing_token=lease['fencing_token'], expires_at=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
            context = {key:grant[key] for key in ('task_id','task_revision','agent_id','worker_session_id','workspace_id','policy_digest','fencing_token')}
            context['workspace_root'] = str(repo)
            def authorize_write():
                authorize('demo-edit', {'action':'edit','path':'calculation.py'}, context, lambda identity:deepcopy(grant), lambda:datetime.now(timezone.utc))
            commit = apply_proposal(repo, candidate, actor='valera' if scenario == 'unauthorized' else 'backend', permitted=True, authorize_write=authorize_write)
            content=(repo/'calculation.py').read_bytes()
            report['publication']=Publisher(db,root/'objects').publish(lease_id=lease['lease_id'],worker_session_id='demo-worker',workspace_id='demo-workspace',fencing_token=lease['fencing_token'],path='calculation.py',artifact=content,expected_digest=digest_bytes(content))
            manager.release(lease['lease_id'],reconcile=True)
            grant['status'] = 'REVOKED'
            report['grant_status_after_edit'] = grant['status']
            guard.artifact = True
            task = controller.pin_target(task['task_id'], task['row_version'],
                                         {'hash_algorithm':'sha1', 'value':commit},
                                         event_id='pin', idempotency_key='pin')
            report['timeline'].append({'state':'TARGET_PINNED', 'row_version':task['row_version'], 'revision':task['revision']})
            report['target_commit'] = commit
            move('REVIEWING')
            code, log = test_candidate(repo)
            report.update(candidate_returncode=code, candidate_log=log.decode())
            # Deterministic basic review is deliberately not called independent QA.
            changed = git(repo, 'diff', '--name-only', base, commit).splitlines()
            review_pass = changed == ['calculation.py'] and (repo / 'calculation.py').read_text() == SOURCE.format(operator='*')
            review_bytes = json.dumps({'changed':changed, 'expected_template':review_pass}).encode()
            artifacts = {'relevant_checks':log, 'basic_review':review_bytes,
                         'acceptance_coverage':json.dumps({'subtotal':['test_three_items','test_empty_basket','test_single_item']}).encode()}
            records, attestations = [], {}
            for check, artifact in artifacts.items():
                record = {'schema_version':'3.0.1', 'evidence_id':check, 'task_id':task['task_id'],
                          'task_revision':task['revision'], 'repository_id':task['repository_id'],
                          'acceptance_ids':['subtotal'], 'commit':deepcopy(task['target_commit']),
                          'kind':'test' if check == 'relevant_checks' else 'basic_review' if check == 'basic_review' else 'contract_check',
                          'check_id':check, 'source':'trusted-local-demo-collector', 'issuer_id':'local-demo-host',
                          'attestation_ref':'local:' + check, 'run_id':scenario + ':' + check,
                          'result':'PASS' if (code == 0 if check == 'relevant_checks' else review_pass if check == 'basic_review' else True) else 'FAIL',
                          'artifact_digest':digest_bytes(artifact), 'created_at':datetime.now(timezone.utc).isoformat(),
                          'policy_version':task['policy_version']}
                if scenario == 'stale-evidence':
                    record['commit']['value'] = base
                records.append(record)
                attestations[record['attestation_ref']] = TrustedEvidence(deepcopy(record), artifact)
            report['evidence'] = records
            report['artifacts'] = {ref: item.artifact.decode('utf-8') for ref, item in attestations.items()}
            move('VERIFYING')
            verify_bundle(records, task, attestations.__getitem__, trusted_issuers=frozenset({'local-demo-host'}))
            guard.verified = True
            report['verified'] = True
            move('COMPLETION_AUDITING')
            advice = jev.completion(task['task_id'], records, attestations.__getitem__, trusted_issuers=frozenset({'local-demo-host'}), enabled=jev_completion)
            report['jev_completion'] = advice
            if jev_completion and advice['verdict'] != 'CLEAR':
                if advice['verdict'] in ('REVIEW_RECOMMENDED', 'INCOMPLETE'):
                    move('REREVIEW')
                raise ValueError('Jev completion requires review: ' + advice['verdict'])
            guard.audit = True
            move('ACCEPTED')
            # All subprocesses are joined; the demo issues no enduring grants/leases.
            guard.finished = True
            move('DONE')
            report['reason'] = 'Fresh attested tests and review cover the pinned candidate'
        except (VerificationError, PermissionError, ValueError) as error:
            report['reason'] = str(error)
            move('BLOCKED', reference='demo-rejection')
        report.update(status=task['status'], revision=task['revision'])
        with sqlite3.connect(db) as connection:
            report['provider_attempts'] = [dict(key=r[0], state=r[1], record=json.loads(r[2])) for r in connection.execute('SELECT idempotency_key,state,result_json FROM provider_attempts')]
        with sqlite3.connect(db) as connection:
            report['events'] = [dict(zip(('type','revision','row_version','payload'), row)) for row in connection.execute(
                'SELECT event_type,revision,row_version,payload_json FROM events ORDER BY event_seq')]
    report['elapsed_seconds'] = round(time.perf_counter() - start, 4)
    report['expected_outcome'] = report['status'] == ('DONE' if scenario == 'success' else 'BLOCKED')
    return report


def terminal_lines(summary):
    lines = ['POTATO HARNESS | supervised automation demo',
             ('Ollama proposal + real Git/tests/SQLite.' if summary['model']['live_call'] else
              'Offline baseline: deterministic proposals, real Git/tests/SQLite.'), '']
    for item in summary['scenarios']:
        lines.append(f"[{item['status']}] {item['scenario']}  {item['elapsed_seconds']:.3f}s")
        lines.append('  ' + ' > '.join(event['state'] for event in item['timeline']))
        lines.append('  ' + item['reason'])
        lines.append('')
    lines.append('EXPECTED OUTCOMES: ' + ('4/4 PASS' if summary['all_expected'] else 'FAILED'))
    lines.append('Not a production sandbox. Model requests: ' + str(summary['model']['requests']))
    return lines


def run_all(output, *, proposal=None, adapter='offline', model_info=None, jev_provider=None, jev_completion=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    results = [run_scenario(name, proposal=proposal, adapter=adapter if name == 'success' else 'offline', jev_provider=jev_provider if name == 'success' else None, jev_completion=jev_completion if name == 'success' else False) for name in SCENARIOS]
    summary = {'version':'0.1.0-demo', 'generated_at':datetime.now(timezone.utc).isoformat(),
               'all_expected':all(item['expected_outcome'] for item in results), 'scenarios':results,
               'model':model_info or {'live_call':False, 'model':None, 'requests':0, 'elapsed_seconds':None},
               'limits':'Constrained demo; not OS sandboxing or production authentication. No cost/savings benchmark.'}
    results[0]['model_requests'] = summary['model']['requests']
    (output / 'report.json').write_text(json.dumps(summary, indent=2) + '\n')
    lines = terminal_lines(summary)
    (output / 'terminal.txt').write_text('\n'.join(lines) + '\n')
    cards = ''.join('<section><h2>' + html.escape(item['scenario']) + ' <b class="' + item['status'].lower() + '">' + item['status'] + '</b></h2><p>' + html.escape(item['reason']) + '</p><p class="time">' + str(item['elapsed_seconds']) + ' seconds · revision ' + str(item['revision']) + '</p><div class="flow">' + ''.join('<span>' + html.escape(event['state']) + '</span>' for event in item['timeline']) + '</div><details><summary>Raw evidence and audit events</summary><pre>' + html.escape(json.dumps(item, indent=2)) + '</pre></details></section>' for item in results)
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Potato Harness demo</title><style>
body{font:16px system-ui,sans-serif;margin:0;background:#101820;color:#ecf1f4}main{max-width:1080px;margin:auto;padding:48px 24px}h1{font-size:42px;letter-spacing:-1.4px;margin:8px 0}h2{font-size:21px}p{line-height:1.6;color:#bac9d2}.eyebrow{color:#f5b841;letter-spacing:3px;font-size:12px}section{background:#192630;border:1px solid #344653;border-radius:12px;padding:24px;margin:20px 0}b{float:right;font-size:13px;padding:7px 12px;border-radius:6px}.done{background:#174d3e;color:#9df3c2}.blocked{background:#513f1d;color:#ffd88d}.flow{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.flow span{background:#263a48;border-radius:5px;padding:6px 9px;font:11px monospace}.time{font-family:monospace}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;color:#b7d1df}summary{cursor:pointer;color:#f5b841}a{color:#f5b841}</style><main><div class="eyebrow">PORTFOLIO / EXECUTABLE EVIDENCE</div><h1>Potato Harness</h1><p>One accepted repair. Three deliberate failures. Every decision leaves a trace.</p><p>''' + html.escape(summary['limits']) + '</p>' + cards + '<p><a href="report.json">Download machine-readable evidence</a> · <a href="terminal.txt">Terminal transcript</a></p></main></html>'
    (output / 'index.html').write_text(document)
    cast = [json.dumps({'version':2, 'width':120, 'height':32, 'title':'Potato Harness — recorded demo output'})]
    for index, line in enumerate(lines):
        cast.append(json.dumps([round(index * 0.8, 2), 'o', line + '\r\n']))
    (output / 'session.cast').write_text('\n'.join(cast) + '\n')
    return summary
