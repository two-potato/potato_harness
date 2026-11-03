# Portfolio case: supervised repair, with evidence

## Problem

An agent can say “done” while its tests fail, its report describes another commit,
or it did not have permission to write. Potato Harness makes those claims inputs
to deterministic checks rather than a completion decision.

## Runnable example

The disposable sample calculates an order subtotal in integer cents. Its initial
implementation adds price and quantity. The proposal changes one allowlisted
operator to multiplication. Three real tests cover multiple items, zero quantity
and one item. This small example isolates orchestration; it does not claim that
choosing an arithmetic operator is difficult AI work.

`python3 tools/run_demo.py` installs pinned validation dependencies in a local
virtual environment on first use and produces an HTML report. Python 3.12+ and Git
must already be installed. The first setup needs package-network access; subsequent
offline runs do not need a model, credentials, cloud services or network access.

The default proposer is deterministic. `--adapter ollama --model YOUR_MODEL`
uses a real local model via a constrained JSON proposal, if you have an installed
model and running Ollama. Neither adapter can submit arbitrary Python or shell.
The host renders the allowlisted operation into a fixed source template.

## What to inspect

1. Baseline tests fail before any candidate is accepted.
2. The host writes the candidate in a disposable Git repository, pins its actual
   commit and increments the semantic task revision atomically.
3. A host-owned collector captures actual test output and a deterministic basic
   review of changed paths/template. This is not independent human QA.
4. The verifier checks fresh attested records, SHA-256 artifact bytes and exact
   task/repository/revision/commit/policy identities. Coverage is per acceptance
   requirement, not just a count of PASS reports.
5. The controller records completion only after the demo guard accepts the
   evidence. Three negative scenarios finish BLOCKED and explain why.

The recorded run is in [demo/report.json](demo/report.json). Timings are one local
run, include subprocess startup, and are not throughput benchmarks or savings
estimates. There is no baseline comparison against autonomous agents. No paid API
was called in the offline sample; local compute cost is not measured.

## Engineering decisions

- SQLite transactions and compare-and-swap prevent stale state writes.
- Task revision binds meaning; row version binds concurrent storage updates.
- Model output is a tiny typed proposal; credentials and policy remain host-owned.
- Attestation resolvers are injected trusted interfaces; JSON alone is not trust.
- Failed, missing or contradictory required evidence cannot be replaced by a later
  unqualified PASS. Reviewer identity checks prevent self-review where required.
- A sample report and paced playback make decisions inspectable without a server.

## Honest limitations

This local demonstration is not a general coding-agent sandbox. It issues no live
worker grants, long-lived leases or production effects. It does not implement the
full policy compiler, general broker, outbox reconciliation, scheduler, OpenCode or
Jev integration, authenticated human-approval service, or nonce consumption store.
The approval verifier is tested with synthetic issuer records; the demo never
fabricates a real person's approval. The core controller still denies transitions
by default; only the deliberately constrained demo configures DemoGuard.

The optional Ollama adapter was tested against a local HTTP fixture server.
A live model run is NOT_RUN unless your generated report says otherwise. The
H/M/C integration registry remains NOT_RUN. Target pinning invalidates revision
bindings but is not OS-level revocation; production adapters must reconcile grants.

## Authorship and interview framing

This is an individual, AI-assisted project. Explain the problem, architecture,
implementation choices and tests you can reproduce; distinguish your decisions
from generated code. Do not present synthetic evidence as customer outcomes,
invent team ownership, or claim unmeasured productivity gains.

Suggested interview sequence: show the report, run the command, explain a rejected
stale commit, inspect one test, then describe the next isolation milestone.

## License and sources

Project code is MIT licensed; third-party dependencies retain their own licenses.
Original role snapshots came from the project owner's Notion exports; their hashes
and source links remain in sources.json / NOTION_LINKS.json. Ollama is an optional
external dependency, not bundled or affiliated with this project.

## Walkthrough assets

`demo/walkthrough.mp4` is a two-minute, silent illustrated explanation generated
from the recorded report; it is not a real-time screen recording. `session.cast`
replays captured terminal text at a readable synthetic pace. Its timestamps must
not be used as runtime measurements. Actual timings are in report.json.

Rebuild the video with Pillow, ffmpeg and DejaVu fonts installed:
`python tools/render_demo_video.py docs/demo/report.json docs/demo`.
The renderer replaces only preview.png/walkthrough.mp4 in the chosen directory.
