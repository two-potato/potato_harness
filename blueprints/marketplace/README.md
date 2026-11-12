# Potato Marketplace Blueprint — R1 contract seed

**Status: R1 CONTRACTS / NOT RUNTIME READY.** No Django, Next.js, OpenSearch,
Kong, Swarm or payment service is deployed by this repository. This is a
logically isolated subtree of the single potato_harness repository. It must not
become an import dependency of the generic Potato Harness core.

## Verify locally

From `blueprints/marketplace/` (or use the root trusted `tools/marketplace.py` CLI):

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m factory_contracts examples/marketplace.factory.example.yaml
```

Expected: machine-readable `marketplace.factory/v1`, one valid fixture, negative
cases, five OpenAPI definitions, one AsyncAPI description, JSON Schema event
envelope, owner/security matrix and the 12 pre-agreed architecture decisions.

`examples/marketplace.factory.example.yaml` is a **sandbox-only** placeholder:
zero blueprint SHA and zero country pack digest are *intentionally invalid for
release*. Validators currently require their shape only; trusted generator
(R2) will bind real SHA and digest to actual signed/approved resources. Country
pack is `UNVERIFIED_DEV_ONLY`; production payment provider is rejected.

The PSP supports only `fake_psp` in R1; no live CIS split/payouts are claimed.
CIS country list is a product targeting list, **not** a compliance certification.

## R1 acceptance scope

- Generated project has independent repository, database and deploy identity.
- Five mandatory services cannot be disabled, changed to arbitrary engines or
  omitted; Kong is separate from Nginx and Admin API is private.
- Docker image references use immutable SHA256 digests; no `latest`.
- Country, payment, security and OpenAPI/AsyncAPI configuration rejects unsafe
  omissions and unsupported provider settings.
- Event envelope is versioned, carries idempotency/correlation and aggregate
  version, and contains no arbitrarily nested customer/financial PII.
- Generated code, integrations, deployment and model inference are R2–R5 work.

See `docs/ARCHITECTURE_BASELINE_v1.md` and `docs/IMPLEMENTATION_PLAN_v1.md`.
