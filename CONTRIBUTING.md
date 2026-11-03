# Contributing

Use Python 3.12+, Git and an isolated virtual environment. Read AGENTS.md and
rules/SECURITY.md. Keep changes small and include an observable failure case.

```bash
python -m pip install -r requirements-validation.txt
python -m unittest discover -s tests -v
python tools/validate_pack.py
python tools/verify_manifest.py
python -m harness.demo
```

Update MANIFEST.sha256.json after reviewing intentional changes. It covers
source files and the recorded demo assets, not local databases or environments.
Do not commit credentials, real approval records, customer code or model output
containing private data. Offline scenarios must remain deterministic and require
no model server or API credentials. Live Ollama calls are opt-in and must be
reported separately from local HTTP protocol tests.

PRs state the concrete behavior, test commands/results and what remains outside
scope. Do not claim a successful demo establishes production isolation, approval
issuer authentication or all H/M/C evaluation coverage. Human review is required
before production activation; merging code does not activate adapters.
