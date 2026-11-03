import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from harness.verifier import (TrustedEvidence, VerificationError, action_digest,
                              digest_bytes, verify_approval, verify_bundle, verify_evidence)

ROOT = Path(__file__).resolve().parents[2]


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / 'fixtures/valid/task.json').read_text())
        self.record = json.loads((ROOT / 'fixtures/valid/evidence-record.json').read_text())
        self.record['artifact_digest'] = digest_bytes(b'artifact')
        self.trusted = frozenset({'fixture'})
        self.collector = lambda ref: TrustedEvidence(copy.deepcopy(self.record), b'artifact')
        self.action = {'target': 'production', 'scope': ['deploy'], 'label': 'ёж'}
        self.approval = json.loads((ROOT / 'fixtures/valid/human-approval.json').read_text())
        self.approval.update(action_digest=action_digest(self.action), target='production', scope=['deploy'],
                             issued_at='2026-11-03T05:00:00Z', expires_at='2026-11-03T07:00:00Z')
        self.now = lambda: datetime(2026, 11, 3, 6, tzinfo=timezone.utc)

    def evidence(self, record=None, collector=None):
        verify_evidence(record or self.record, self.task, collector or self.collector, trusted_issuers=self.trusted)

    def bundle(self, records=None, **kwargs):
        verify_bundle(records or [self.record], self.task, self.collector, trusted_issuers=self.trusted, **kwargs)

    def approval_check(self, **kwargs):
        verify_approval(self.approval, self.task, self.action,
                        kwargs.pop('issuer', lambda ref: copy.deepcopy(self.approval)), self.now,
                        trusted_issuers=self.trusted, **kwargs)

    def test_valid_evidence_bundle_and_approval(self):
        self.evidence()
        self.bundle()
        self.approval_check()

    def test_digest_utf8_canonical(self):
        self.assertEqual(action_digest(self.action), digest_bytes(
            '{"label":"ёж","scope":["deploy"],"target":"production"}'.encode('utf-8')))
        with self.assertRaises(VerificationError):
            action_digest({'x': float('nan')})

    def test_evidence_binding_and_schema_rejections(self):
        for key, value in [('issuer_id', 'false'), ('task_id', 'other'), ('task_revision', 0),
                           ('repository_id', 'other'), ('policy_version', 'old'),
                           ('check_id', 'unknown'), ('acceptance_ids', ['unknown']),
                           ('created_at', 'yesterday'), ('extra', True), ('task_revision', True)]:
            with self.subTest(key=key, value=value):
                record = copy.deepcopy(self.record)
                record[key] = value
                with self.assertRaises(VerificationError):
                    self.evidence(record)
        self.record['commit']['value'] = 'b' * 40
        with self.assertRaises(VerificationError):
            self.evidence()

    def test_collector_mismatch_revocation_and_artifact(self):
        altered = dict(self.record, run_id='substituted')
        for result in [TrustedEvidence(altered, b'artifact'),
                       TrustedEvidence(self.record, b'artifact', True),
                       TrustedEvidence(self.record, b'wrong'),
                       TrustedEvidence(self.record, None), None]:
            with self.subTest(result=result):
                with self.assertRaises(VerificationError):
                    self.evidence(collector=lambda ref: result)

    def test_missing_and_wrong_acceptance_coverage(self):
        self.task['acceptance'].append({'id': 'second', 'expected': 'second', 'requires': ['fixture']})
        with self.assertRaises(VerificationError):
            self.bundle()
        self.task['acceptance'][0]['requires'] = ['additional']
        with self.assertRaises(VerificationError):
            self.bundle()

    def test_required_nonpass_cannot_be_erased(self):
        for status in ['FAIL', 'UNKNOWN', 'SKIPPED', 'ERROR']:
            failed = dict(self.record, evidence_id='failed', run_id='failed', result=status)
            records = [failed, self.record]
            collector = lambda ref: TrustedEvidence(next(r for r in records if r['attestation_ref'] == ref), b'artifact')
            failed['attestation_ref'] = 'failed'
            with self.subTest(status=status), self.assertRaises(VerificationError):
                verify_bundle(records, self.task, collector, trusted_issuers=self.trusted)

    def test_duplicate_evidence_and_run(self):
        for field in ['evidence_id', 'run_id']:
            other = dict(self.record, evidence_id='other', run_id='other', attestation_ref='other')
            other[field] = self.record[field]
            with self.subTest(field=field), self.assertRaises(VerificationError):
                verify_bundle([self.record, other], self.task,
                    lambda ref: TrustedEvidence(other if ref == 'other' else self.record, b'artifact'),
                    trusted_issuers=self.trusted)

    def test_independence_requires_attested_distinct_ids(self):
        self.record['kind'] = 'independent_review'
        for author_actor, author_session, reviewer_actor, reviewer_session in [
            (None, None, 'qa', 'qa-session'), ('author', 'session', 'author', 'qa-session'),
            ('author', 'session', 'qa', 'session'), ('author', 'session', None, None)]:
            self.record.pop('reviewer_actor', None)
            self.record.pop('reviewer_session', None)
            if reviewer_actor:
                self.record.update(reviewer_actor=reviewer_actor, reviewer_session=reviewer_session)
            with self.subTest(author_actor=author_actor, reviewer_actor=reviewer_actor), self.assertRaises(VerificationError):
                self.bundle(author_actor=author_actor, author_session=author_session)
        self.record.update(reviewer_actor='qa', reviewer_session='qa-session')
        self.bundle(author_actor='author', author_session='session')

    def test_approval_rejections(self):
        original = copy.deepcopy(self.approval)
        for key, value in [('issuer_id', 'false'), ('status', 'REVOKED'), ('status', 'DENIED'),
                           ('nonce', ''), ('task_revision', 0), ('task_id', 'wrong'),
                           ('target', 'other'), ('scope', ['other']), ('action_digest', digest_bytes(b'wrong')),
                           ('issued_at', '2026-11-03T06:01:00Z'),
                           ('expires_at', '2026-11-03T06:00:00Z'), ('issued_at', '2026-11-03T05:00:00')]:
            self.approval = dict(original, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(VerificationError):
                self.approval_check()
        self.approval = original
        with self.assertRaises(VerificationError):
            self.approval_check(issuer=lambda ref: dict(original, status='REVOKED'))
        self.now = lambda: datetime(2026, 11, 3, 6)
        with self.assertRaises(VerificationError):
            self.approval_check()

    def test_attested_untrusted_issuer_is_rejected(self):
        self.record['issuer_id'] = 'forged-provider'
        with self.assertRaises(VerificationError):
            self.evidence()
        self.approval['issuer_id'] = 'forged-provider'
        with self.assertRaises(VerificationError):
            self.approval_check()

    def test_required_check_missing_and_duplicate_acceptance(self):
        self.task['required_checks'].append('missing')
        with self.assertRaises(VerificationError):
            self.bundle()
        self.task['required_checks'].pop()
        self.task['acceptance'].append(copy.deepcopy(self.task['acceptance'][0]))
        with self.assertRaises(VerificationError):
            self.bundle()

    def test_fresh_resolver_is_called_on_each_approval(self):
        calls = []
        def issuer(ref):
            calls.append(ref)
            return dict(self.approval, status='APPROVED' if len(calls) == 1 else 'REVOKED')
        self.approval_check(issuer=issuer)
        with self.assertRaises(VerificationError):
            self.approval_check(issuer=issuer)
        self.assertEqual(len(calls), 2)

    def test_non_rfc3339_timestamps_rejected(self):
        for value in ['20261103T050000+0000', '2026-11-03 05:00:00+00:00',
                      '2026-11-03T05:00:00+0000']:
            self.record['created_at'] = value
            with self.subTest(field='created_at', value=value), self.assertRaises(VerificationError):
                self.evidence()
            for field in ['issued_at', 'expires_at']:
                original = self.approval[field]
                self.approval[field] = value.replace('05', '07') if field == 'expires_at' else value
                with self.subTest(field=field, value=value), self.assertRaises(VerificationError):
                    self.approval_check()
                self.approval[field] = original

    def test_action_rejects_non_json_python_types_recursively(self):
        class IntSubclass(int):
            pass
        for action in [{1: 'value'}, {'nested': {1: 'value'}},
                       {'nested': [(1, 2)]}, {'nested': IntSubclass(1)},
                       {'nested': {'set'}}, {'nested': float('inf')}]:
            with self.subTest(action=action), self.assertRaises(VerificationError):
                action_digest(action)
        action_digest({'nested': [None, True, False, 1, 1.5, 'text', {}]})

    def test_resolver_errors_fail_closed(self):
        def broken(ref):
            raise OSError('provider unavailable')
        with self.assertRaises(VerificationError):
            self.evidence(collector=broken)
        with self.assertRaises(VerificationError):
            self.approval_check(issuer=broken)
