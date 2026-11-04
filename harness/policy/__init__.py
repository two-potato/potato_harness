"""Host-owned capability decisions; this is not an OS sandbox or IO wrapper."""
from datetime import datetime
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CONTEXT_KEYS = frozenset({'task_id', 'task_revision', 'agent_id', 'worker_session_id',
                         'workspace_id', 'workspace_root', 'policy_digest', 'fencing_token'})
BINDINGS = CONTEXT_KEYS - {'workspace_root'}
SCHEMA = json.loads((ROOT / 'schemas/capability-grant.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


class AuthorizationError(ValueError):
    """The requested operation has no currently verified authorization."""


def _text(value):
    return type(value) is str and bool(value.strip())


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})', value):
        raise AuthorizationError('Strict RFC3339 expiration required')
    return datetime.fromisoformat(value.upper().replace('Z', '+00:00'))


def _parts(value):
    if type(value) is not str or not value or any(c in value for c in '\\*?[]\x00'):
        raise AuthorizationError('Canonical relative POSIX path required')
    parts = value.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise AuthorizationError('Path contains empty or traversal component')
    if any(part == '.git' or part == '.env' or part.startswith('.env.') for part in parts):
        raise AuthorizationError('Secret and Git paths are denied')
    return parts


def _path(root, value):
    parts = _parts(value)
    candidate = root
    for part in parts:
        candidate = candidate / part
        if candidate.is_file() and candidate.stat().st_nlink > 1:
            raise AuthorizationError('Hard-linked file aliases are denied')
        if candidate.is_symlink():
            raise AuthorizationError('Symlink path components are denied')
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise AuthorizationError('Path escapes workspace')
    return parts


def authorize(grant_id, request, context, resolve_grant, clock) -> None:
    """Freshly resolve and verify one read/edit/test decision; perform no effect.

    The embedding host, not the model, must own context, resolver and clock.
    Callers must not treat the result as race-free filesystem authorization.
    """
    try:
        _authorize(grant_id, request, context, resolve_grant, clock)
    except AuthorizationError:
        raise
    except Exception as exc:
        raise AuthorizationError('Authorization input or trusted dependency failed') from exc


def _authorize(grant_id, request, context, resolve_grant, clock):
    if not _text(grant_id):
        raise AuthorizationError('Grant identity required')
    # Resolve on every invocation; no positive decision or grant cache.
    grant = resolve_grant(grant_id)
    if type(grant) is not dict:
        raise AuthorizationError('Grant must be a schema-valid object')
    VALIDATOR.validate(grant)
    if type(context) is not dict or set(context) != CONTEXT_KEYS:
        raise AuthorizationError('Exact host context required')
    for key in BINDINGS:
        if key in ('task_revision', 'fencing_token'):
            minimum = 0 if key == 'task_revision' else 1
            if any(type(obj[key]) is not int or obj[key] < minimum for obj in (grant, context)):
                raise AuthorizationError('Strict integer revision/fence required')
        elif not _text(context[key]) or type(grant[key]) is not str:
            raise AuthorizationError('Nonempty identity required')
        if grant[key] != context[key]:
            raise AuthorizationError('Grant binding mismatch: ' + key)
    if grant['grant_id'] != grant_id or grant['status'] != 'ACTIVE':
        raise AuthorizationError('Grant substituted or inactive')
    expires, now = _date(grant['expires_at']), clock()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None or now >= expires:
        raise AuthorizationError('Grant expired or invalid clock')
    if type(request) is not dict or set(request) != {'action', 'path'}:
        raise AuthorizationError('Only action/path requests supported; network denied')
    action = request['action']
    if type(action) is not str or action not in ('read', 'edit', 'test'):
        raise AuthorizationError('Action unsupported until effect integration')
    if action not in grant['actions']:
        raise AuthorizationError('Action not granted')
    if context['agent_id'] == 'valera' or (context['agent_id'] == 'explore' and action != 'read'):
        raise AuthorizationError('Role cannot perform this engineering action')
    root_value = context['workspace_root']
    if type(root_value) is not str or not root_value:
        raise AuthorizationError('Absolute workspace root required')
    root = Path(root_value)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise AuthorizationError('Existing nonsymlink workspace root required')
    # Include ancestors of the workspace itself in symlink rejection.
    if any(parent.is_symlink() for parent in root.parents):
        raise AuthorizationError('Workspace ancestor is a symlink')
    root = root.resolve(strict=True)
    prefixes = [_path(root, prefix) for prefix in grant['paths']]
    parts = _path(root, request['path'])
    if not any(parts[:len(prefix)] == prefix for prefix in prefixes):
        raise AuthorizationError('Path outside granted prefixes')
