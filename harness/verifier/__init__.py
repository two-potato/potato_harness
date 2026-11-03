"""Fail-closed verification against host-configured, freshly resolved attestations.

Resolvers and trust roots are injected by trusted host code, never by workers.
This module provides verification, not authentication, issuance or nonce storage.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]


class VerificationError(ValueError):
    """An input, attestation, or required gate could not be verified."""


@dataclass(frozen=True)
class TrustedEvidence:
    record: dict
    artifact: bytes
    revoked: bool = False


def digest_bytes(value: bytes) -> str:
    if not isinstance(value, bytes):
        raise VerificationError('Artifact must be bytes')
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def _json_native(value):
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise VerificationError('JSON object keys must be strings')
            _json_native(item)
    elif type(value) is list:
        for item in value:
            _json_native(item)
    elif type(value) is float:
        if not math.isfinite(value):
            raise VerificationError('JSON numbers must be finite')
    elif value is not None and type(value) not in (str, int, bool):
        raise VerificationError('Expected native JSON value types')


def action_digest(action: dict) -> str:
    """SHA-256 over sorted compact JSON, literal Unicode, encoded as UTF-8."""
    if type(action) is not dict:
        raise VerificationError('Action must be an object')
    try:
        _json_native(action)
        encoded = json.dumps(action, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise VerificationError('Action is not canonical JSON') from exc
    return digest_bytes(encoded)


def _validate(record, schema):
    try:
        validator = Draft202012Validator(json.loads(
            (ROOT / 'schemas' / (schema + '.schema.json')).read_text()),
            format_checker=FormatChecker())
        validator.validate(record)
    except Exception as exc:
        raise VerificationError(f'Invalid {schema}') from exc


def _date(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(
                r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})', value):
            raise ValueError('RFC3339 timestamp required')
        parsed = datetime.fromisoformat(value.upper().replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('Timezone required')
        return parsed
    except (AttributeError, TypeError, ValueError) as exc:
        raise VerificationError('Invalid aware timestamp') from exc


def _task(task):
    _validate(task, 'task')
    ids = [item['id'] for item in task['acceptance']]
    if len(ids) != len(set(ids)):
        raise VerificationError('Duplicate acceptance IDs')
    checks = set(task['required_checks'])
    for item in task['acceptance']:
        checks.update(item['requires'])
    return set(ids), checks


def _resolve(resolver, reference):
    try:
        return resolver(reference)
    except Exception as exc:
        raise VerificationError('Attestation resolver failed') from exc


def _binding(record, task):
    if record['task_id'] != task['task_id'] or record['task_revision'] != task['revision']:
        raise VerificationError('Task binding mismatch')


def verify_evidence(record, task, collector, *, trusted_issuers: frozenset[str]) -> None:
    acceptance_ids, checks = _task(task)
    _validate(record, 'evidence-record')
    _date(record['created_at'])
    fetched = _resolve(collector, record['attestation_ref'])
    if not isinstance(fetched, TrustedEvidence) or fetched.revoked is not False:
        raise VerificationError('Missing or revoked evidence')
    # Compare canonical JSON as well: Python equality alone equates True with 1.
    _validate(fetched.record, 'evidence-record')
    if action_digest(fetched.record) != action_digest(record):
        raise VerificationError('Attestation record mismatch')
    if record['issuer_id'] not in trusted_issuers:
        raise VerificationError('Untrusted evidence issuer')
    if digest_bytes(fetched.artifact) != record['artifact_digest']:
        raise VerificationError('Artifact digest mismatch')
    _binding(record, task)
    for key, expected in [('repository_id', task['repository_id']),
                          ('commit', task['target_commit']), ('policy_version', task['policy_version'])]:
        if record[key] != expected:
            raise VerificationError(f'Evidence {key} binding mismatch')
    if record['check_id'] not in checks or not set(record['acceptance_ids']) <= acceptance_ids:
        raise VerificationError('Unknown check or acceptance ID')


def verify_bundle(records, task, collector, *, trusted_issuers: frozenset[str],
                  author_actor=None, author_session=None) -> None:
    _, required = _task(task)
    seen_ids, seen_runs, covered, acceptance = set(), set(), set(), set()
    for record in records:
        verify_evidence(record, task, collector, trusted_issuers=trusted_issuers)
        run = (record['issuer_id'], record['run_id'])
        if record['evidence_id'] in seen_ids or run in seen_runs:
            raise VerificationError('Duplicate evidence or issuer/run identity')
        seen_ids.add(record['evidence_id'])
        seen_runs.add(run)
        if record['check_id'] in required and record['result'] != 'PASS':
            raise VerificationError('Required evidence is not PASS; reconciliation required')
        if record['kind'] == 'independent_review' or record['check_id'] == 'independent_qa':
            reviewer_actor = record.get('reviewer_actor')
            reviewer_session = record.get('reviewer_session')
            if not all(isinstance(value, str) and value.strip() for value in
                       [author_actor, author_session, reviewer_actor, reviewer_session]):
                raise VerificationError('Author and attested reviewer identities required')
            if author_actor == reviewer_actor or author_session == reviewer_session:
                raise VerificationError('Review is not independent')
        if record['result'] == 'PASS':
            covered.add(record['check_id'])
            acceptance.update((aid, record['check_id']) for aid in record['acceptance_ids'])
    if not required <= covered:
        raise VerificationError('Required checks missing')
    for item in task['acceptance']:
        if any((item['id'], check) not in acceptance for check in item['requires']):
            raise VerificationError('Acceptance requirement coverage missing')


def verify_approval(record, task, action, issuer, clock, *, trusted_issuers: frozenset[str]) -> None:
    _task(task)
    _validate(record, 'human-approval')
    fetched = _resolve(issuer, record['attestation_ref'])
    _validate(fetched, 'human-approval')
    if action_digest(fetched) != action_digest(record):
        raise VerificationError('Approval attestation mismatch or revoked')
    if record['issuer_id'] not in trusted_issuers or record['status'] != 'APPROVED':
        raise VerificationError('Approval is not trusted and approved')
    _binding(record, task)
    if action_digest(action) != record['action_digest']:
        raise VerificationError('Action digest mismatch')
    if action.get('target') != record['target'] or action.get('scope') != record['scope']:
        raise VerificationError('Approval target/scope mismatch')
    if not record['nonce'].strip():
        raise VerificationError('Approval nonce required')
    issued, expires = _date(record['issued_at']), _date(record['expires_at'])
    try:
        now = clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('Aware clock required')
        if not issued <= now < expires:
            raise ValueError('Approval expired or issued in future')
    except Exception as exc:
        raise VerificationError('Approval time window invalid') from exc
