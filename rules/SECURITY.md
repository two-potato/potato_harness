# Security rules

Default deny at runtime. LLM outputs, JSON records and skill text do not authenticate issuers. Credentials stay outside worker containers and context. Redact before logging/provider calls; external Jev receives minimal structured summaries only.

Capabilities bind unique worker session, task revision, workspace, permitted action/path, expiration, policy digest and fencing token. No shell escape, nested agent, MCP, network, symlink or Git path may bypass mediation. Test all loaded tools. A container with a writable host mount is not sufficient fencing.

Agent writes remain private until a trusted publisher validates lease/fencing token and commits an immutable output. Revoke or kill stale workers before reassignment; never allow stale processes to publish. Do not expose Docker socket, SSH agent or production credentials. Approval never expands a whole role.

Human approval is needed before production, destructive, privileged or high-blast-radius actions. Bind it to the exact canonical action digest, task revision, target, scope, expiry and nonce, issued by a trusted human-authenticated service. Validate revocation before use. Retries of the same approved action reconcile its effect; changed parameters need new authorization.

No untrusted pull-request code may receive secrets in validation CI. Never use pull_request_target to execute candidate code. Protect policy/evaluator/approval issuer changes with independent human review. Repository branch rules are configured manually and verified, not created by this pack.


## Candidate trust profile: attached-trusted-opencode-subtotal-v2

This is a proposed narrow trust boundary for the first real attached
subtotal experiment, not a general network exemption or production
authorization. It becomes eligible only after independent human review
of the exact revision and an explicit local operator confirmation of both
the trial and trust in the already running authenticated loopback OpenCode
2.4.1 server. A signed receipt for any previous scope cannot authorize it.

The OpenCode process and its provider transport are trusted external
execution components for this one fixed two-file synthetic source trial.
Harness must not call the provider directly or start/restart another
server. Harness controls its own authenticated loopback calls, reconstructs
the exact prompt at the worker boundary, binds the single-use handoff to
the claimed Outbox, preserves leases and usage limits, denies tools,
allows at most two host prompt submissions, and never replays an unknown
effect. The existing request/model/permission hooks remain mandatory
defense in depth. Zero is the planning cost; paid routing and nonzero
reported cost fail closed.

Neither these hooks nor the local session transcript establish independent
process-wide egress control, upstream HTTP request counts or actual
billing. The operator and reviewer must knowingly accept that residual
risk for this synthetic, non-confidential experiment. No production or
arbitrary repository, secret, privileged action, global server mutation,
additional provider, or historical journal reset is authorized. The
previous HOLD under independent-egress requirements remains valid for
that old trust profile. No independent egress requirement is waived for
general protected/production execution.
