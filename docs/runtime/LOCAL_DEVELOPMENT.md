# Local development and isolation boundary

Potato Harness is local-first. Editing the Harness itself, validating schemas,
unit testing its deterministic modules, and running the offline demo **do not
require Bubblewrap** or an API key.

From the Harness checkout:

```sh
python3 -m harness.readiness --mode development
python3 -m unittest discover -s tests -v
python3 tools/validate_pack.py
python3 tools/verify_manifest.py
python3 tools/run_demo.py
```

The readiness command checks Python 3.12+ and Git presence. It deliberately does
not call the isolation probe, run an agent, execute a project's code, or authorize
untrusted tool effects. `ready: true` in development mode means only that these
host prerequisites are present, **not** that the runtime is safe to activate.

Before **protected execution** of project tests or AI-generated code, run:

```sh
python3 -m harness.readiness --mode execution
python3 -m harness.isolation --probe
```

Execution readiness requires the actual Bubblewrap profile to launch. The
existing `python3 -m harness.runtime run --state ...` continues to probe the
profile before any model call, and it never falls back to running tests directly
on the host. A passing readiness probe is necessary but not a full production
sandbox certification; the live containment tests must also pass.

`harness.isolation.backend.IsolationBackend` is a small host-owned adapter
protocol (`probe` and `run`); `BubblewrapBackend` delegates to the original
fail-closed `probe`/`run_private` functions. The runtime selects this trusted
implementation. Neither task config nor model output can choose an alternative.
Other operating systems need their own reviewed adapter and verification before
they can run untrusted code. Do **not** add an unsandboxed backend or map
`development` readiness to execution authorization.

Local Git is required for exact revision pinning; GitHub/cloud credentials are not
needed for the local deterministic workflow. OpenCode/OMO/Jev/model live testing
is explicitly outside this change.
