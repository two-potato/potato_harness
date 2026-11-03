# Security rules

Default deny at runtime. LLM outputs, JSON records and skill text do not authenticate issuers. Credentials stay outside worker containers and context. Redact before logging/provider calls; external Jev receives minimal structured summaries only.

Capabilities bind unique worker session, task revision, workspace, permitted action/path, expiration, policy digest and fencing token. No shell escape, nested agent, MCP, network, symlink or Git path may bypass mediation. Test all loaded tools. A container with a writable host mount is not sufficient fencing.

Agent writes remain private until a trusted publisher validates lease/fencing token and commits an immutable output. Revoke or kill stale workers before reassignment; never allow stale processes to publish. Do not expose Docker socket, SSH agent or production credentials. Approval never expands a whole role.

Human approval is needed before production, destructive, privileged or high-blast-radius actions. Bind it to the exact canonical action digest, task revision, target, scope, expiry and nonce, issued by a trusted human-authenticated service. Validate revocation before use. Retries of the same approved action reconcile its effect; changed parameters need new authorization.

No untrusted pull-request code may receive secrets in validation CI. Never use pull_request_target to execute candidate code. Protect policy/evaluator/approval issuer changes with independent human review. Repository branch rules are configured manually and verified, not created by this pack.
