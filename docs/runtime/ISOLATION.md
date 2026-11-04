# Private Linux runner

`harness.isolation` implements a fail-closed Bubblewrap launcher with no host
execution fallback. The embedding host must own the workspace and argv. A model
cannot activate isolation by claiming the profile is available.

## Interface

`probe()` returns a dictionary with `available`, `reason` and `version`. It checks
Linux, executable availability and the actual Bubblewrap version, then launches
`/usr/bin/true` using the complete profile in a temporary private workspace.
Installed software alone is not a successful probe. Each probe is fresh.

`run_private(workspace: Path, argv: list[str], timeout=10)` validates its inputs,
probes again, and raises `SandboxUnavailable` if the platform cannot establish
the profile. Invalid workspace/argv/timeout inputs raise `ValueError`. A launch
failure raises `SandboxUnavailable`; a launched command returns a dictionary:
`returncode`, UTF-8 replacement-decoded `stdout` and `stderr`, and `timed_out`.
Nonzero command status is preserved. There is no shell wrapper or shell string
conversion: argv is passed directly with `shell=False`. The executable must be
an absolute canonical path inside the sandbox. This does not prohibit a trusted
caller from explicitly selecting an interpreter.

`python -m harness.isolation --probe` prints the actual JSON status and exits
zero only when available, otherwise one.

## Profile

The fixed profile requests all Bubblewrap namespaces, explicitly enables the
user namespace, disables further user namespaces, drops all capabilities,
starts a new session, dies with its parent and clears the environment. PATH is
set to `/usr/bin:/bin`. Network namespaces are not shared with the host.

Only host `/usr` is mounted read-only. `/bin`, `/lib` and `/lib64` are symlinks
to their `/usr` counterparts. A private tmpfs `/tmp`, proc filesystem `/proc`
and minimal `/dev` are provided. The sole explicit writable host bind is the
validated workspace at `/work`, also used as the working directory. Host root,
`/etc`, homes, Docker sockets and host runtime directories are not mounted.
Programs requiring host configuration or extra mounts fail rather than gaining
additional access.

Workspace roots must be existing absolute directories outside system trees.
`/`, `/tmp` itself, traversal components, symlink roots and symlink ancestors are
rejected. The workspace tree is inspected and must contain only regular files
and directories; symlinks, sockets, FIFOs and device entries are rejected. The
host must supply a dedicated private workspace, without credentials or sensitive
files and without untrusted concurrent mutation. Inspection is not atomic and
does not make filesystem IO safe against a racing host process. Hardlink
provenance is also a host responsibility.

## Resource and lifecycle bounds

Output is captured into temporary regular files, not unbounded pipes. Each
process inherits a 1 MiB `RLIMIT_FSIZE`, 1 GiB address-space limit, 64-descriptor
limit, no core dumps and a CPU-time bound derived from the requested timeout.
The file-size limit also constrains worker-created regular files. Captured
streams are read at most 1 MiB each; replacement decoding can expand encoded
text size. Timeout must be a finite number in `(0, 120]` seconds. On timeout the
launcher kills the process group and waits for the direct child, reporting
`timed_out=true`. This is not a cgroup-based memory/process-count controller.

Lease revocation, stale publisher fencing, immutable publication, policy
authorization, approvals and outbox effects remain separate host integrations.
This profile and tests do not certify a full production kernel sandbox. They do
not bypass kernel restrictions or prove an unavailable platform is contained.

## Current activation evidence

The actual probe in this environment finds `bubblewrap 0.9.0` but fails to create
the requested namespace profile:

```
bwrap: open /proc/<pid>/ns/ns failed: No such file or directory
```

Consequently availability is false, the CLI exits one, and `run_private` refuses
execution. No host fallback is attempted. Actual containment is **not verified**
on this host.

Run `.venv-demo/bin/python -m unittest tests.runtime.test_isolation -v`.
The initial regression run failed on the missing API. The implemented suite has
17 tests: 11 pass and 6 explicitly skip here. Five live tests cover private
writes/absent host paths, read-only `/usr`, network isolation, timeout and output
bounds only when the real probe succeeds. The remaining skip records this host's
inability to create even a test Unix-domain socket. Passing deterministic tests
cover fail-closed decisions, fresh probes, unsafe inputs, special-file rejection,
command profile construction and timeout kill/wait orchestration; they are not
claimed as successful live escape tests.
