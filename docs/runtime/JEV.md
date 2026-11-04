# Jev advisory runtime

`Jev(database, provider=None)` uses the controller's provider_attempts table.
`preflight(task_id)` reserves a single send per parent user_turn_id, shared by
children. `completion(task_id, records, collector, trusted_issuers=..., enabled=...)`
first verifies base evidence against the current task in COMPLETION_AUDITING.
Its identity binds task, revision, exact commit, evidence digest and policy.

Reservation/send authorization commits before provider invocation. Duplicate and
restarted calls never resend. SENT/RESERVED observations return UNKNOWN; this may
also mean another process is still working. Provider errors persist UNKNOWN.
A completed result is advisory and cannot change privileges or bypass a gate.
Missing configuration is UNAVAILABLE; disabled completion is SKIPPED_BY_POLICY.
An unavailable reservation is not automatically retried after configuration changes:
start a new user turn for a new preflight, never delete audit rows to force retry.
The trusted host owns provider callbacks and stable user-turn identity.

The demo calls preflight automatically. With completion enabled, REVIEW_RECOMMENDED
or INCOMPLETE routes to REREVIEW then BLOCKED for bounded human/specialist followup.
An unavailable/unknown completion also blocks. Base test failures prevent the
completion provider call entirely. Production OpenCode/Valera session hooks still
need the target runtime integration; this is the Python harness's hook API.

## Configure

Install validation requirements or use the one-command demo bootstrap. Configure
OPENCODE_API_KEY or TYPESAFE_API_KEY through your shell/secret manager; do not put
keys in commands, commits, reports or chat. Then run:

```bash
python3 tools/run_demo.py --jev-provider opencode --jev-model jev-1.13-free --jev-completion
# Or: --jev-provider typesafe --jev-model YOUR_AVAILABLE_MODEL
```

Model availability and billing are account/provider dependent; no free access is
assumed. No model inference was executed in the development environment because
no keys were configured. Real local HTTP protocol tests and durable DB tests pass.

Verified documentation: [OpenCode models / Jev](https://opencode.ai/v2/docs/console/models/)
and [TypeSafe OpenAPI](https://api.typesafe.ai/openapi.json). Current endpoints are
https://opencode.ai/inference/systemone/v1/systemone and
https://api.typesafe.ai/v1/systemone. The old Zen URL is not hard-coded.
SystemOne sends typed `noul` questions, not chat messages. Structural risk/class/
counts/base-gate metadata are the only outbound task data; no code, objective,
paths, credentials or holdout examples are sent. This limits semantic advice.

Response probabilities map to fixed advisory labels: >=0.5 recommends review,
0.2–0.5 is incomplete, otherwise clear. Thresholds are a local conservative policy,
not a calibrated safety guarantee. HTTPS destinations are allowlisted; proxies and
redirects disabled; response <=64KiB; socket timeout <=120s and no retries. The
socket timeout is not a total wall-clock deadline. Test HTTP requires loopback and
the literal synthetic key test-only. Logs omit raw provider errors and responses.

Each demo scenario is a separate disposable task/turn with a fresh UUID. The
configured external provider is used only by the success scenario; negative
scenarios remain offline. Provider-attempt records are copied into report JSON
before the demo database is removed. For a persistent worker host, supply a durable
controller database to Jev; the disposable demo is not a restartable job service.
