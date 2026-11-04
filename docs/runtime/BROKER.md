# Initial capability decision broker

`harness.policy.authorize(grant_id, request, context, resolve_grant, clock)`
returns `None` when the requested decision passes and raises
`AuthorizationError` (a `ValueError`) for rejection, malformed input or dependency
failure. It performs no filesystem write, shell command or external effect.

## Host contract

The trusted host owns the resolver, clock and context. Model-provided context or
callbacks cannot establish authorization. `resolve_grant(grant_id)` is called on
every invocation and must fetch the current authenticated grant, including its
revocation state, from protected host storage. There is no positive cache.

Requests must be exact dictionaries with only `action` and `path`. Actions are
initially restricted to `read`, `edit` and `test`, and must also appear in the
grant. `publish` and `external_effect` are denied until lease, publisher and
outbox integration exists. Any additional request field, including any network
field regardless of value, is denied. Grant network destinations do not enable
network requests through this API.

Context must be an exact dictionary with these keys:

| Key | Meaning |
| --- | --- |
| `task_id` | Current task identity |
| `task_revision` | Current semantic revision; exact integer, at least zero |
| `agent_id` | Current specialist role |
| `worker_session_id` | Unique current worker session |
| `workspace_id` | Host-assigned workspace identity |
| `workspace_root` | Existing absolute workspace directory, string path |
| `policy_digest` | Current policy digest |
| `fencing_token` | Current fencing token; exact integer, at least one |

Every binding except `workspace_root` must exactly match the freshly fetched
grant; that field is resolved by the host's workspace registry because the grant
schema carries `workspace_id`, not a root path. No aliases or extra keys are
accepted. Booleans and floating-point representations of revision/fence are
rejected in grants and context. The complete capability-grant schema is checked.
The grant ID must match the requested ID and status must be `ACTIVE`.

Expiration uses strict RFC3339 syntax plus datetime parsing independently of
optional format-checker packages. The clock must return an aware `datetime`;
`clock() >= expires_at` rejects the decision. Valera has no engineering access;
its role is outside the capability schema and fails closed. Explore may only
read, even when a grant lists edit/test actions.

## Path boundary

Both request paths and every grant prefix must be canonical relative POSIX
paths: no empty path, empty component, dot, traversal, absolute path, backslash,
glob metacharacters or NUL. Root-wide grants are not supported in this initial
API. Prefix matching uses path components, so `src` does not authorize `src2`.
`.git`, `.env` and `.env.*` components are denied anywhere in the path.

The workspace root must exist and be a directory. Symlink workspace roots,
symlink ancestors, and symlink components in request or grant paths are denied,
including dangling leaf links and links whose targets remain inside the
workspace. Resolved paths must remain inside the resolved workspace. A missing
nonsymlink leaf is permitted so that an authorized edit can create a new file.

## Integration limits

This is a decision API, not an OS sandbox and not race-free IO. A symlink or
filesystem entry can change after inspection. The actual effect implementation
must use an appropriate protected filesystem boundary and race-resistant IO;
callers must not wrap arbitrary shell execution in this check and claim
isolation. Current fence equality checks do not themselves supply an exclusive
lease or fence a long-running writer. Authentication, protected grant issuance,
lease ownership, process isolation, effect mediation and atomic publication
remain host integration responsibilities. No live sandbox activation is claimed.

## Tests

Run `.venv-demo/bin/python -m unittest tests.runtime.test_broker` after installing
the repository requirements in that environment. The 22 tests exercise allowed
decisions and adversarial revocation/substitution, every context binding, strict
integers, expiry and timestamps, roles, unknown request shapes/actions, network
denial, missing grants/provider errors, path prefix boundaries, secret paths,
symlink escapes and dangling symlinks. Initial regression execution failed
because the module did not exist; implementation then passed the focused suite.

Existing regular files with multiple hard links are denied to prevent aliases of
secret or out-of-scope files. This is still a point-in-time decision, not race-free IO.
