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
seller-owned revision-bound endpoints, Next.js TypeScript storefront sources, an
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
- `frontend/`: Next.js TypeScript read-only SSR catalog UI.
- `marketplace.factory.yaml`, `blueprint.lock`, `.env.example`, `README.md`,
  `NEXT_STEPS.md`.

The generated backend requires an operator-controlled PostgreSQL instance and
secret env configuration. The GitHub `marketplace-contracts` workflow performs
a bounded Django/PostgreSQL smoke test plus Next.js build; no live models or
Swarm are involved. Direct dependency versions are pinned but the transitive
`pip` and `npm` lock files are not yet release-ready.

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
full seller portal and transactional moderation, R3 Nginx/Kong and Docker Swarm,
R4 five mandatory running microservices, R5 end-to-end validation. No live PSP,
network calls, production deployment or real-model inference is performed.
