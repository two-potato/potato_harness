# Persistent bounded trial runtime

Run from the harness checkout with its Python requirements installed. The production command requires a working Bubblewrap namespace profile; it probes that profile before any model call. API credentials belong in the host bridge environment, never the copied source or model prompt.

```sh
python -m harness.runtime init --config /absolute/config.json --state /absolute/new-state
python -m harness.runtime run --state /absolute/new-state
python -m harness.runtime status --state /absolute/new-state
python -m harness.runtime recover --state /absolute/new-state
python -m harness.runtime halo --state /absolute/new-state
```

Config is trusted operator input. No dynamic command comes from model output.

```json
{
  "repo": "/absolute/clean-source-repository",
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "model": "provider/model",
  "scope": ["src/calculation.py"],
  "test_argv": ["/usr/bin/python3", "-m", "unittest", "discover"],
  "objective": "The configured acceptance tests pass after the scoped repair",
  "budget": {
    "tokens": 70000,
    "cost_usd": 1,
    "estimate_cost_usd": 0.75,
    "wall_time_s": 120
  },
  "output": "/absolute/new-result-directory",
  "completion_jev": false
}
```

Optional `worker_command` is a trusted argv override. Default is the repository-pinned Bun executable plus `integrations/opencode/src/worker.mjs`. Its JSON stdin is `{role,prompt,model,projectDir,output_token_allowance,coordination}`; JSON stdout is `{edits:[{path,content}],summary,usage:{input_tokens,output_tokens,cost_usd}}`. The bridge runs outside the sandbox because it needs provider credentials; model tools must be disabled by that bridge. Provider projectDir is a new empty directory separate from copied source, preventing source `.opencode` configuration from becoming host plugin authority.

`init` requires a clean source repository matching the exact SHA. It copies committed regular files from raw `git ls-tree`/`git cat-file` blobs, excluding Git metadata and rejecting special files, secret paths, files over 1 MiB and repositories over 32 MiB. Committed `.gitattributes` export/clean transforms cannot hide tests or alter these raw inputs. Target commits use the exact raw tested blobs and executable bits. The source repository is never modified. State is a new private directory outside it. Trial scope is a nonempty list of exact existing tracked file paths. A conservative filename rule rejects obvious authentication, payment, policy, deployment and other high-risk changes. This is a bounded LOW-risk trial policy, not a general risk classifier: operators must not submit changes whose actual risk exceeds LOW. Tests are supplied by the operator as the acceptance contract; the runtime does not infer business correctness from arbitrary passing tests.

`run` holds an exclusive host lock and executes one attempt. Jev preflight is durable and advisory before planning; missing Jev transport is recorded as unavailable. The host reserves the explicit finite dispatch token/cost reservation (not a proven provider-wide spend bound), claims one outbox effect, obtains scoped grants and leases, and requests inert edit proposals. The actual context compiler loads and hashes mandatory role/policy instructions; the actual scheduler checks the singleton task is ready before assignment. Mandatory instructions and scoped source are JSON delimited; common secrets are redacted. The compiler receives an explicit host UTF-8 byte counter for this trial, providing a conservative input ceiling rather than an exact tokenizer count. Its token-named counters must therefore be interpreted as byte ceilings in this profile. The output allowance is capped at 4096 and sent to the pinned bridge for provider output enforcement. Actual usage is reconciled; any usage above the reserved dispatch allowance returns HOLD before edits, with the actual overrun retained in the budget ledger.

Provider actual input/output tokens and finite actual cost are required before edits. Unknown actual cost places the run on HOLD with reservation retained. No unknown cost is substituted with zero. System One advice does not expose actual token/cost usage through this transport: configured live Jev calls are not reconciled into the worker budget. A provider-wide hard spend cap and an agreed Jev price/accounting mechanism remain a prerequisite for cost-constrained live trials; no total-cost enforcement is claimed. An absent Jev provider makes no network call and incurs no asserted charge. Failed/crashed/ambiguous provider calls become UNKNOWN and are never retransmitted by run or recover. One run does not retry or resume; a reconciled new task requires explicit host action.

The host applies at most 1 MiB of scoped edits through directory file descriptors with no-follow checks and denies symlinks, hardlinks, scope escapes and duplicate edit paths. It publishes immutable bytes while the original lease is valid, revokes the edit grant and releases that lease, and creates a real Git commit in a separate host-only checkout initialized from the pinned base, and pins that actual commit SHA. Git metadata never enters the worker mount. A fresh revision-bound lease and read/test grant precede the test subprocess. The configured test argv executes only through `run_private`; no host fallback exists. Source mutations by tests invalidate evidence. All subprocesses are synchronously joined before cleanup.

Exact-target host attestations cover `relevant_checks`, deterministic `basic_review` of the changed-file scope, and the configured acceptance-test mapping. `verify_bundle` validates these receipts before completion audit. LOW-risk deterministic review is not independent specialist QA. Completion Jev is explicitly disabled in the default 3.0 trial profile and recorded as policy-skipped. Configure `jev_provider` (`opencode` or `typesafe`) and `jev_model` to activate System One using host `OPENCODE_API_KEY` or `TYPESAFE_API_KEY`. Missing credentials yield durable unavailable advice; required completion then yields HOLD. Grants are revoked, leases released and unresolved effects checked before DONE. The new output directory contains `result.json`, immutable artifact bytes, evidence and test outputs; state retains immutable publications, actual test logs, evidence records, SQLite events and a redacted run trace. The output uses publication references rather than silently editing the original repository.

`recover` marks interrupted DISPATCHING effects UNKNOWN and surviving leases SUSPECT, reports HOLD, and never executes provider/shell/Git effects. A trusted operator must confirm external outcomes and fence workers before reissuing any work. `halo` exports one redacted actual trace and returns HOLD because that trace cannot constitute distinct training, validation and holdout datasets. It creates no synthetic optimization data. To evaluate existing actual datasets, supply all three `--train FILE --eval FILE --holdout FILE` JSON arrays of redacted trace records. The trusted evaluator verifies disjoint memberships and binds the durable attempt ledger, actual target commit and policy. Results are offline proposals only and never change runtime policy.

Verification: `python -m unittest discover -s tests/runtime -v`. Runtime tests inject a fixture worker and sandbox callbacks explicitly; they prove lifecycle wiring, not live model execution or Linux isolation. Production CLI never exposes those callback seams. Real provider smoke and actual sandbox activation evidence must be collected separately on the trial host.
