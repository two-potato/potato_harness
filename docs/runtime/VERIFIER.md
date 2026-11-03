# Runtime verifier

`harness.verifier` supplies fail-closed primitives. A rejected input raises
`VerificationError` (`ValueError`); successful verification returns `None`.
It does not issue approvals, execute actions, persist gate decisions, or protect
worker processes.

## Trusted host integration

The host supplies `trusted_issuers: frozenset[str]` and resolver functions from
its protected configuration. A worker's chosen callback or issuer allowlist is
not a trust root. `collector(attestation_ref)` must freshly return
`TrustedEvidence(record, artifact, revoked=False)` from an authenticated provider;
`artifact` is the actual `bytes`. The frozen dataclass prevents field reassignment,
not mutation of its nested dictionary. Providers must own their snapshots and
prevent concurrent mutation during verification.

`verify_evidence(record, task, collector, *, trusted_issuers)` validates the
canonical schemas (including strict RFC3339 timestamps checked independently
of optional format-checker dependencies), exact provider record, issuer,
revocation and artifact digest. It binds task ID, revision, repository, exact
commit object and policy version. Known checks are the union of the supplied
task's required checks and acceptance requirements; known acceptance IDs come
from that task. The controller must compute applicability/risk before calling
this module. Evidence verification alone does not require a PASS result.

`verify_bundle(records, task, collector, *, trusted_issuers, author_actor=None,
author_session=None)` additionally requires PASS coverage for every check and
every acceptance/check pair. Any non-PASS required record rejects the bundle,
even alongside a later PASS. Evidence IDs and `(issuer_id, run_id)` identities
must be unique. Independent review records (kind `independent_review` or check
`independent_qa`) require both author identifiers and both attested reviewer
identifiers, with different actors and sessions. This checks explicit identity
conflicts; organizational conflict-of-interest policy remains host-owned.

## Human approvals

`verify_approval(record, task, action, issuer, clock, *, trusted_issuers)` resolves
the approval again on every invocation. `issuer(attestation_ref)` must return the
current authenticated approval record, including current revocation status.
A missing/changed/revoked record fails. The record must be APPROVED, bind the task
revision, exact action digest, target and ordered scope array, contain a nonblank
nonce and satisfy `issued_at <= clock() < expires_at`. The clock must return an
aware `datetime`. The action must contain `target` and `scope` matching the
approval. Additional action parameters remain bound through its digest.

`action_digest(action)` serializes JSON with `sort_keys=True`,
`separators=(',', ':')`, `ensure_ascii=False`, and `allow_nan=False`, then encodes
UTF-8. `digest_bytes(bytes)` returns `sha256:` followed by lowercase hexadecimal.
Only exact native JSON types are accepted recursively: string-keyed dictionaries,
lists, strings, integers, finite floats, booleans and null. Tuples, nonstring keys
and subclasses are rejected before encoding. Arrays retain their order. This is the project encoding, not a claim of RFC 8785
canonicalization across arbitrary language runtimes.

Validation authenticates an already issued record only through the trusted
resolver boundary. It does not authenticate a human itself, consume a nonce,
prevent replay across calls, or guarantee global trust. The effect controller
must atomically track nonce use and reconcile retries, recheck freshness at the
effect boundary, and persist its own CAS-bound gate decision. No claim of live
runtime protection follows from these library tests.

## Verification

Run `python -m unittest discover -s tests/runtime -p test_verifier.py`. Tests cover successful
verification, canonical Unicode hashing, malformed/schema-invalid input,
substituted/stale bindings, false issuers, missing/wrong/revoked artifacts,
coverage gaps, conflicting results, duplicate identities, review independence,
approval changes/revocation, expiry/future issuance and resolver failures.
