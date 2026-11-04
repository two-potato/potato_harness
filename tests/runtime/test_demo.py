import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class DemoTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('harness.demo.runner'), 'Demo runner missing')
        from harness.demo.runner import run_scenario, run_all
        return run_scenario, run_all

    def test_happy_path_fixes_real_bug_and_reaches_done(self):
        run, _ = self.api()
        report = run('success')
        self.assertEqual(report['status'], 'DONE')
        self.assertNotEqual(report['baseline_returncode'], 0)
        self.assertEqual(report['candidate_returncode'], 0)
        self.assertEqual(report['operator'], 'multiply')
        self.assertEqual(report['revision'], 1)
        self.assertEqual(report['timeline'][-1]['state'], 'DONE')
        self.assertTrue(report['verified'])
        self.assertEqual(len(report['target_commit']), 40)

    def test_failing_tests_never_reach_done(self):
        run, _ = self.api()
        report = run('failed-tests')
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertNotEqual(report['candidate_returncode'], 0)
        self.assertFalse(report['verified'])

    def test_stale_commit_evidence_is_rejected(self):
        run, _ = self.api()
        report = run('stale-evidence')
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(report['candidate_returncode'], 0)
        self.assertIn('commit', report['reason'].lower())

    def test_forbidden_role_cannot_change_artifact(self):
        run, _ = self.api()
        report = run('unauthorized')
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(report['base_commit'], report['target_commit'])
        self.assertIsNone(report['candidate_returncode'])
        self.assertIn('permission', report['reason'].lower())

    def test_report_artifacts_and_expected_outcomes(self):
        _, run_all = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'report'
            summary = run_all(output)
            self.assertTrue(summary['all_expected'])
            self.assertEqual(len(summary['scenarios']), 4)
            self.assertEqual(json.loads((output / 'report.json').read_text()), summary)
            self.assertIn('Potato Harness', (output / 'index.html').read_text())
            self.assertTrue((output / 'session.cast').is_file())
            with self.assertRaises(FileExistsError):
                run_all(output)

    def test_proposal_cannot_inject_code_or_change_other_paths(self):
        self.assertIsNotNone(importlib.util.find_spec('harness.demo.worker'), 'Constrained worker missing')
        from harness.demo.worker import validate_proposal
        for proposal in [{'operator': '__import__("os")'}, {'operator':'multiply', 'path':'../x'},
                         {'operator':'multiply', 'code':'print(1)'}, {}, ['multiply']]:
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                validate_proposal(proposal)

    def test_recorded_artifact_bytes_match_evidence_digests(self):
        run, _ = self.api()
        from harness.verifier import digest_bytes
        report = run('success')
        self.assertIn('artifacts', report)
        for record in report['evidence']:
            artifact = report['artifacts'][record['attestation_ref']].encode('utf-8')
            self.assertEqual(digest_bytes(artifact), record['artifact_digest'])

    def test_jev_hooks_run_before_dispatch_and_after_base_pass(self):
        run, _ = self.api()
        calls=[]
        def advice(request):
            calls.append(request['phase'])
            return {'verdict':'CLEAR','gaps':[]}
        report=run('success',jev_provider=advice,jev_completion=True)
        self.assertEqual(calls,['PREFLIGHT','COMPLETION'])
        self.assertEqual(report['status'],'DONE')
        calls.clear()
        report=run('failed-tests',jev_provider=advice,jev_completion=True)
        self.assertEqual(calls,['PREFLIGHT'])
        self.assertEqual(report['status'],'BLOCKED')

    def test_jev_completion_gap_routes_to_review_then_blocks(self):
        run, _ = self.api()
        def advice(request):
            return {'verdict':'REVIEW_RECOMMENDED','gaps':['extra_review']}
        report=run('success',jev_provider=advice,jev_completion=True)
        self.assertEqual(report['status'],'BLOCKED')
        self.assertIn('REREVIEW',[x['state'] for x in report['timeline']])
