from copy import deepcopy
import importlib.util
import json
import multiprocessing
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def clear(request):
    return {'verdict':'CLEAR', 'gaps':[]}


def race_jev(db, queue):
    from harness.jev import Jev
    def provider(request):
        queue.put('sent')
        return clear(request)
    Jev(db, provider=provider).preflight('fixture')


class JevTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('harness.jev.service'), 'Jev coordinator missing')
        from harness.jev import Jev, JevError
        from harness.controller import Controller, initialize
        self.Jev, self.Error = Jev, JevError
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name)/'state.db'
        initialize(self.db)
        self.task=json.loads((ROOT/'fixtures/valid/task.json').read_text())
        self.task.update(revision=0,row_version=0)
        self.controller=Controller(self.db,guard=lambda c:True)
        self.controller.create_task(self.task,event_id='create',idempotency_key='create')

    def test_preflight_duplicate_and_child_share_original_advice(self):
        calls=[]
        def provider(request):
            calls.append(request)
            return clear(request)
        j=self.Jev(self.db,provider=provider)
        first=j.preflight('fixture')
        second=j.preflight('fixture')
        child=dict(self.task,task_id='child')
        self.controller.create_task(child,event_id='child',idempotency_key='child')
        result=j.preflight('child')
        self.assertEqual(first,second)
        self.assertEqual(result,first)
        self.assertEqual(result['task_id'],'fixture')
        self.assertEqual(len(calls),1)
        self.assertFalse(first['authoritative'])

    def test_missing_provider_explicit_unavailable_and_no_later_retry(self):
        first=self.Jev(self.db).preflight('fixture')
        self.assertEqual(first['attempt_state'],'UNAVAILABLE')
        def forbidden(request):
            self.fail('Unavailable attempt must not retry')
        self.assertEqual(self.Jev(self.db,provider=forbidden).preflight('fixture'),first)

    def test_provider_error_unknown_no_error_body_no_retry(self):
        def failing(request):
            raise TimeoutError('SECRET TOKEN')
        result=self.Jev(self.db,provider=failing).preflight('fixture')
        self.assertEqual(result['attempt_state'],'UNKNOWN')
        self.assertNotIn('SECRET',json.dumps(result))
        self.assertEqual(self.Jev(self.db,provider=clear).preflight('fixture'),result)

    def test_authoritative_or_invalid_provider_result_never_clear(self):
        j=self.Jev(self.db,provider=lambda r:{'verdict':'CLEAR','gaps':[], 'authoritative':True})
        self.assertEqual(j.preflight('fixture')['attempt_state'],'UNKNOWN')

    def test_sent_after_crash_never_resends(self):
        j=self.Jev(self.db,provider=clear)
        result=j.preflight('fixture')
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE provider_attempts SET state='SENT' WHERE idempotency_key=?",(result['idempotency_key'],))
        recovered=self.Jev(self.db,provider=lambda r:self.fail('must not resend')).preflight('fixture')
        self.assertEqual(recovered['attempt_state'],'UNKNOWN')

    def advance(self):
        from harness.controller import Event
        for index,state in enumerate(['CLASSIFIED','PLANNED','ASSIGNED','EXECUTING','REVIEWING','VERIFYING','COMPLETION_AUDITING']):
            self.controller.transition('fixture',index,Event(str(index),str(index),state))

    def test_completion_runs_only_after_trusted_base_gate(self):
        from harness.verifier import VerificationError
        j=self.Jev(self.db,provider=lambda r:self.fail('Failed gate must not send'))
        self.advance()
        with self.assertRaises(VerificationError):
            j.completion('fixture',[],lambda ref:None,trusted_issuers=frozenset({'host'}),enabled=True)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM provider_attempts').fetchone()[0],0)

    def evidence(self):
        from harness.verifier import TrustedEvidence,digest_bytes
        task=self.controller.get_task('fixture')
        record=json.loads((ROOT/'fixtures/valid/evidence-record.json').read_text())
        record.update(task_revision=task['revision'],artifact_digest=digest_bytes(b'test'),issuer_id='host')
        return [record],lambda ref:TrustedEvidence(deepcopy(record),b'test')

    def test_completion_cached_and_disabled_policy_recorded(self):
        self.advance()
        records,collector=self.evidence()
        j=self.Jev(self.db,provider=clear)
        first=j.completion('fixture',records,collector,trusted_issuers=frozenset({'host'}),enabled=True)
        self.assertEqual(first['verdict'],'CLEAR')
        self.assertEqual(j.completion('fixture',records,collector,trusted_issuers=frozenset({'host'}),enabled=True),first)

    def test_disabled_completion_never_calls(self):
        self.advance()
        records,collector=self.evidence()
        result=self.Jev(self.db,provider=lambda r:self.fail()).completion('fixture',records,collector,trusted_issuers=frozenset({'host'}),enabled=False)
        self.assertIn('SKIPPED_BY_POLICY',result['gaps'])

    def test_cached_completion_rejects_task_changed_during_verification(self):
        from harness.controller import Event
        self.advance()
        records,collector=self.evidence()
        calls=[]
        def provider(request):
            calls.append(request)
            return clear(request)
        j=self.Jev(self.db,provider=provider)
        first=j.completion('fixture',records,collector,trusted_issuers=frozenset({'host'}),enabled=True)
        self.assertEqual(first['verdict'],'CLEAR')
        def changing_collector(reference):
            task=self.controller.get_task('fixture')
            self.controller.transition('fixture',task['row_version'],Event('rereview','rereview','REREVIEW'))
            return collector(reference)
        with self.assertRaises(self.Error):
            j.completion('fixture',records,changing_collector,trusted_issuers=frozenset({'host'}),enabled=True)
        self.assertEqual(self.controller.get_task('fixture')['status'],'REREVIEW')
        self.assertEqual(len(calls),1)

    def test_real_process_race_authorizes_one_send(self):
        ctx=multiprocessing.get_context('spawn');q=ctx.Queue()
        processes=[ctx.Process(target=race_jev,args=(str(self.db),q)) for _ in range(2)]
        for p in processes:p.start()
        for p in processes:
            p.join(15)
            if p.is_alive():p.terminate();p.join()
            self.assertEqual(p.exitcode,0)
        self.assertEqual(q.get(timeout=2),'sent')
        import queue
        with self.assertRaises(queue.Empty):q.get(timeout=.2)
        q.close()
