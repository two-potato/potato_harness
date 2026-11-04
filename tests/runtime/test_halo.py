import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path

from harness.halo import Candidate, Host, Ledger, TrustedEvaluator, digest, optimize, run_demo


def fixture(root):
    rows = lambda prefix: tuple(dict(trace_id=f'{prefix}{i}', status='PASS', checks=['required'], bindings={'policy': 'v1'}, optional_detail='x' * 500) for i in range(3))
    train, evaluation, holdout = rows('t'), rows('e'), rows('h')
    evaluator = TrustedEvaluator('reviewer', holdout)
    host = Host({'hash_algorithm': 'sha1', 'value': 'a'*40}, 'v1', ('train-v1', 'eval-v1', 'holdout-v1'), (digest(train), digest(evaluation), digest(holdout)), evaluator.code_digest, 'optimizer', 'reviewer')
    return host, train, evaluation, evaluator, Ledger(root / 'ledger.sqlite')


class HaloTests(unittest.TestCase):
    def test_demo_schema_and_no_approval(self):
        import jsonschema
        with tempfile.TemporaryDirectory() as tmp:
            result = run_demo(Path(tmp)/'new')
            schema = json.loads((Path(__file__).parents[2]/'schemas/halo-proposal.schema.json').read_text())
            jsonschema.validate(result['proposal'], schema)
            self.assertEqual(result['proposal']['status'], 'PROPOSED')
            self.assertGreater(result['proposal']['metrics_before'][0]['value'], result['proposal']['metrics_after'][0]['value'])
            with self.assertRaises(FileExistsError): run_demo(Path(tmp)/'new')

    def test_negative_contracts_and_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            host, train, evaluation, evaluator, ledger = fixture(Path(tmp))
            bad = [dict(max_optional_detail_chars=0, required_checks=[]), dict(max_optional_detail_chars=-1), dict(policy='weak'), dict(max_optional_detail_chars=7)]
            for i, candidate in enumerate(bad):
                result = optimize(host, host.baseline_commit, train, evaluation, evaluator, ledger, str(i), candidate)
                self.assertEqual(result['status'], 'REJECTED')
            result = optimize(host, {'hash_algorithm':'sha1','value':'b'*40}, train, evaluation, evaluator, ledger, 'stale')
            self.assertEqual(result['status'], 'REJECTED')
            self.assertEqual(len(ledger.attempts()), 5)
            result = optimize(host, host.baseline_commit, train, evaluation, evaluator, ledger, '0')
            self.assertEqual(result['status'], 'UNKNOWN')

    def test_provenance_overlap_identity(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as tmp:
            host, train, evaluation, evaluator, ledger = fixture(Path(tmp))
            hosts = [replace(host, evaluator_identity='optimizer'), replace(host, split_ids=('x','x','z')), replace(host, split_digests=(digest(train),)*3), replace(host,evaluator_digest=digest('tampered'))]
            for i, bad_host in enumerate(hosts):
                self.assertEqual(optimize(bad_host, host.baseline_commit, train, evaluation, evaluator, ledger, str(i))['status'], 'REJECTED')
            changed = tuple(dict(row, optional_detail='tampered') for row in train)
            self.assertEqual(optimize(host,host.baseline_commit,changed,evaluation,evaluator,ledger,'changed')['status'],'REJECTED')

    def test_failure_consumed_no_resend_and_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            host, train, evaluation, evaluator, ledger = fixture(Path(tmp))
            def fail(*args): raise RuntimeError('evaluator offline')
            evaluator.evaluate = fail
            self.assertEqual(optimize(host,host.baseline_commit,train,evaluation,evaluator,ledger,'failure')['status'],'HOLD')
            self.assertEqual(optimize(host,host.baseline_commit,train,evaluation,evaluator,Ledger(ledger.path),'failure')['status'],'UNKNOWN')
            for i in range(9): ledger.reserve(host.split_ids[2], str(i),host.split_digests[2])
            with self.assertRaises(ValueError): ledger.reserve(host.split_ids[2], 'eleventh',host.split_digests[2])

    def test_atomic_concurrent_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp)/'ledger.sqlite')
            def reserve(i):
                try: return ledger.reserve('holdout', str(i),digest('holdout'))
                except ValueError: return False
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                results = list(pool.map(reserve, range(25)))
            self.assertEqual(sum(results),10)
            self.assertEqual(len(ledger.attempts()),10)

    def test_empty_and_noisy_data_no_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            host, train, evaluation, evaluator, ledger = fixture(Path(tmp))
            self.assertEqual(optimize(host,host.baseline_commit,(),evaluation,evaluator,ledger,'empty')['status'],'REJECTED')
            with self.assertRaises(ValueError): Candidate.from_dict({'max_optional_detail_chars': True})
            with self.assertRaises(ValueError): Candidate(0).apply({'trace_id':'x','status':'PASS','checks':[], 'bindings':{},'optional_detail':42})

    def test_holdout_membership_and_aggregate_tampering(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as tmp:
            host, train, evaluation, evaluator, ledger = fixture(Path(tmp))
            overlapping = TrustedEvaluator('reviewer', tuple(dict(r, trace_id=train[0]['trace_id'] if i==0 else r['trace_id']) for i,r in enumerate(evaluation)))
            overlap_host = replace(host,split_digests=(digest(train),digest(evaluation),overlapping.split_digest))
            self.assertEqual(optimize(overlap_host,host.baseline_commit,train,evaluation,overlapping,ledger,'overlap')['status'],'REJECTED')
            evaluator.evaluate=lambda *args: dict(sample_size=3,before=100,after=0,safety_regressions=0,split_digest=digest('forged'),evaluator_digest=host.evaluator_digest)
            self.assertEqual(optimize(host,host.baseline_commit,train,evaluation,evaluator,ledger,'forged')['status'],'REJECTED')

    def test_no_improvement_and_regression_never_proposed(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as tmp:
            host, train, evaluation, evaluator, ledger = fixture(Path(tmp))
            short = lambda rows: tuple(dict(r,optional_detail='tiny') for r in rows)
            train,evaluation=short(train),short(evaluation)
            evaluator=TrustedEvaluator('reviewer',tuple(dict(r,trace_id='h'+r['trace_id']) for r in evaluation))
            host=replace(host,split_digests=(digest(train),digest(evaluation),evaluator.split_digest))
            self.assertEqual(optimize(host,host.baseline_commit,train,evaluation,evaluator,ledger,'noise')['status'],'HOLD')
            evaluator.evaluate=lambda *args: dict(sample_size=3,before=100,after=0,safety_regressions=1,split_digest=host.split_digests[2],evaluator_digest=host.evaluator_digest)
            self.assertEqual(optimize(host,host.baseline_commit,train,evaluation,evaluator,ledger,'regression')['status'],'REJECTED')

    def test_abandoned_reservation_not_resent(self):
        with tempfile.TemporaryDirectory() as tmp:
            host, train, evaluation, evaluator, ledger = fixture(Path(tmp))
            ledger.reserve(host.split_ids[2],'crashed',host.split_digests[2])
            evaluator.evaluate=lambda *args: self.fail('must not resend')
            self.assertEqual(optimize(host,host.baseline_commit,train,evaluation,evaluator,Ledger(ledger.path),'crashed')['status'],'UNKNOWN')

    def test_holdout_alias_cannot_reset_cap_or_resend(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as tmp:
            host,train,evaluation,evaluator,ledger=fixture(Path(tmp))
            for i in range(10):
                ledger.reserve('original',str(i),host.split_digests[2])
            alias=replace(host,split_ids=('t','e','relabeled'))
            self.assertEqual(optimize(alias,host.baseline_commit,train,evaluation,evaluator,ledger,'new')['status'],'HOLD')
            self.assertEqual(optimize(alias,host.baseline_commit,train,evaluation,evaluator,ledger,'0')['status'],'UNKNOWN')
            with self.assertRaisesRegex(ValueError,'different content'):
                ledger.reserve('original','changed',digest('different content'))
            self.assertEqual(len(ledger.attempts()),10)

    def test_blank_attempt_ids_and_invalid_output_never_proposed(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            host,train,evaluation,evaluator,ledger=fixture(Path(tmp))
            for attempt in ('','   ',None):
                self.assertEqual(optimize(host,host.baseline_commit,train,evaluation,evaluator,ledger,attempt)['status'],'REJECTED')
            self.assertEqual(len(ledger.attempts()),0)
            with patch('jsonschema.Draft202012Validator.validate',side_effect=ValueError('schema rejected')):
                self.assertEqual(optimize(host,host.baseline_commit,train,evaluation,evaluator,ledger,'schema')['status'],'REJECTED')
            self.assertEqual(len(ledger.attempts()),1)
