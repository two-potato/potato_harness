# One clone: Potato Harness and Marketplace Factory

One Git repository and one policy hierarchy: root `AGENTS.md` and `rules/*`.
The marketplace domain lives in `blueprints/marketplace/`; it does not grant
permissions or introduce Django/Next.js dependencies into the generic Harness.

## Offline generation (deterministic, trusted-host operation)

```sh
git clone https://github.com/two-potato/potato_harness.git
cd potato_harness
python3 -m venv .venv
.venv/bin/python -m pip install -r blueprints/marketplace/requirements-dev.txt
.venv/bin/python tools/marketplace.py status
.venv/bin/python tools/marketplace.py validate blueprints/marketplace/examples/marketplace.factory.example.yaml
.venv/bin/python tools/marketplace.py generate demo-market-kz
```

The `generate` command creates `../demo-market-kz/` as an independent Git
repository, containing actual Django/DRF backend source, a catalog migration and
seller-group RBAC and owner-scoped revision-bound endpoints, Next.js TypeScript storefront sources, an
unverified sandbox manifest and a deterministic `blueprint.lock`. All templates
are copied from reviewed source; **no template code, model, Git hook, npm, pip,
Docker, shell script or external payment provider is executed** except trusted
local Git commands for initial source commit. Generating source is not permission
to execute that source. Verify runtime admission and isolation first.

`init demo-market-kz` remains a backwards-compatible, *contract-only* seed,
which creates no Django or frontend source. `generate` refuses an existing
output, symlinked parent, `..` segment, source-repository destination, invalid
manifest, or a real payment provider. R2 preview supports the verified KZ/KZT
**development fixture only** and `fake_psp` sandbox. Example digests and
country packs are placeholders and never permit production or payouts.

For a different operator-supplied manifest:

```sh
.venv/bin/python tools/marketplace.py generate demo-market-kz \
    --manifest /absolute/path/to/marketplace.factory.yaml \
    --output /absolute/new-directory
```

The slug in the manifest must exactly match the requested slug.

## Inspect generated source

The generated project contains:

- `backend/`: Django/DRF, PostgreSQL connection, `catalog.Listing` revision
  and publication status model, migration, scoped seller API and access tests.
- `frontend/`: Next.js TypeScript public SSR catalog, seller login/portal,
  and staff/moderator review queue with Django session+CSRF.
- `marketplace.factory.yaml`, `blueprint.lock`, `.env.example`, `README.md`,
  `NEXT_STEPS.md`.

The generated backend requires an operator-controlled PostgreSQL instance and
secret env configuration. The GitHub `marketplace-contracts` workflow performs
a bounded Django/PostgreSQL smoke test plus Next.js build; no live models or
Swarm are involved. Direct dependency versions are pinned but the transitive
`pip` and `npm` lock files are not yet release-ready.

## Local browser MVP: seller -> moderation -> buyer

**Host-controlled development only.** The generator writes reviewed source; it
does not execute Python/Node, expose a port or authorize deployment. A local
operator must inspect the generated project before installing dependencies.

Use a private PostgreSQL instance and set `PGDATABASE`, `PGUSER`, `PGPASSWORD`,
`PGHOST`, `PGPORT`. Also set `DJANGO_SECRET_KEY` to a fresh random value of
at least 32 characters. On a loopback-only development machine, set
`DJANGO_DEBUG=1`; do not use that setting on an externally accessible host.

```sh
cd ../demo-market-kz/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver 127.0.0.1:8000

# Another terminal in ../demo-market-kz/frontend:
# MARKETPLACE_API_URL must be http://127.0.0.1:8000
npm install --ignore-scripts
npm run typecheck
npm run dev -- --hostname 127.0.0.1
```

The Django admin, `http://127.0.0.1:8000/admin/`, is only available when
`DJANGO_DEBUG=1`. The migration creates empty `seller` and `moderator`
groups, **not accounts or passwords**. The administrator creates users and
assigns the `seller` group. A human reviewer must be both `staff` and a
member of `moderator`. These roles cannot be assigned through the public API.

Use `http://127.0.0.1:3000/seller` to sign in, create, edit and submit a draft
with an expected revision; then `/moderation` to approve/reject that exact
revision; then `/` to view the published listing anonymously. Rejected or
unreviewed revisions are invisible in the storefront. Django checks CSRF on
session requests and on state-changing API requests. Decision UUIDs are
idempotent, and replay with conflicting content is rejected.

**Not production authentication:** no self-service registration, rate limiting,
account recovery, external identity provider, browser E2E automation or network
security audit is included. Do not expose this demo to a public interface. The
moderation workflow is local and human-only; separate R4 moderation events and
five running services still need implementation.

## OpenCode workflow and remaining work

```sh
opencode
# in the OpenCode TUI: /marketplace demo-market-kz
```

The OpenCode command is a **planning entrypoint only**, with native tools denied.
It must not silently run `generate`, enable shell/Docker access, or claim that
a functioning marketplace was deployed. The operator may explicitly run the
trusted CLI. The full autonomous agent workflow requires independently approved
capability grants and a tested protected runner in R0.

Still incomplete: R1 typed OpenAPI response schemas and generated TypeScript
clients (#16), production-grade country packs and payment reconciliation, R2
production authentication and moderation-service integration, R3 Nginx/Kong and Docker Swarm,
R4 five mandatory running microservices, R5 end-to-end validation. No live PSP,
network calls, production deployment or real-model inference is performed.
