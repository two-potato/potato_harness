import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from harness.policy import AuthorizationError, authorize

ROOT = Path(__file__).resolve().parents[2]


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'src').mkdir()
        self.grant = json.loads((ROOT / 'fixtures/valid/capability-grant.json').read_text())
        self.grant.update(grant_id='grant', agent_id='backend', actions=['read', 'edit', 'test'],
                          paths=['src'], status='ACTIVE', expires_at='2026-11-04T07:00:00Z')
        self.context = {key: self.grant[key] for key in ['task_id', 'task_revision', 'agent_id',
            'worker_session_id', 'workspace_id', 'policy_digest', 'fencing_token']}
        self.context['workspace_root'] = str(self.root)
        self.clock = lambda: datetime(2026, 11, 4, 6, tzinfo=timezone.utc)
        self.request = {'action': 'read', 'path': 'src/new.py'}
        self.resolve = lambda ref: copy.deepcopy(self.grant)

    def check(self):
        return authorize('grant', self.request, self.context, self.resolve, self.clock)

    def test_allowed_actions(self):
        for action in ['read', 'edit', 'test']:
            self.request['action'] = action
            self.assertIsNone(self.check())

    def test_fresh_revocation(self):
        self.check()
        self.grant['status'] = 'REVOKED'
        with self.assertRaises(AuthorizationError):
            self.check()

    def test_changed_grant_identity(self):
        self.grant['grant_id'] = 'substitution'
        with self.assertRaises(AuthorizationError):
            self.check()

    def test_all_context_bindings(self):
        for key in ['task_id', 'task_revision', 'agent_id', 'worker_session_id',
                    'workspace_id', 'policy_digest', 'fencing_token']:
            old = self.context[key]
            self.context[key] = old + 1 if type(old) is int else old + '-changed'
            with self.subTest(key=key), self.assertRaises(AuthorizationError):
                self.check()
            self.context[key] = old

    def test_strict_context_keys(self):
        for change in ['missing', 'extra']:
            context = self.context.copy()
            if change == 'missing':
                del context['worker_session_id']
            else:
                context['trusted'] = True
            with self.subTest(change=change), self.assertRaises(AuthorizationError):
                authorize('grant', self.request, context, self.resolve, self.clock)

    def test_strict_integer_types(self):
        for target in [self.context, self.grant]:
            for key in ['task_revision', 'fencing_token']:
                old = target[key]
                for value in [True, float(old)]:
                    target[key] = value
                    with self.subTest(key=key, value=value), self.assertRaises(AuthorizationError):
                        self.check()
                target[key] = old

    def test_expired_and_expired_status(self):
        self.grant['expires_at'] = '2026-11-04T06:00:00Z'
        with self.assertRaises(AuthorizationError):
            self.check()
        self.grant.update(expires_at='2026-11-04T07:00:00Z', status='EXPIRED')
        with self.assertRaises(AuthorizationError):
            self.check()

    def test_strict_dates_and_clock(self):
        for value in ['20261104T070000+0000', '2026-11-04 07:00:00+00:00',
                      '2026-11-04T07:00:00', '2026-99-04T07:00:00Z']:
            self.grant['expires_at'] = value
            with self.subTest(value=value), self.assertRaises(AuthorizationError):
                self.check()
        self.grant['expires_at'] = '2026-11-04T07:00:00Z'
        self.clock = lambda: datetime(2026, 11, 4, 6)
        with self.assertRaises(AuthorizationError):
            self.check()

    def test_unknown_and_unintegrated_actions(self):
        self.grant['actions'] += ['publish', 'external_effect']
        for action in ['shell', 'publish', 'external_effect', '', None]:
            self.request['action'] = action
            with self.subTest(action=action), self.assertRaises(AuthorizationError):
                self.check()

    def test_request_exact_shape(self):
        for request in [None, [], {'action': 'read'}, dict(self.request, unknown=True),
                        dict(self.request, network=None), dict(self.request, network_destinations=[])]:
            self.request = request
            with self.subTest(request=request), self.assertRaises(AuthorizationError):
                self.check()

    def test_denies_ungranted_action(self):
        self.grant['actions'] = ['read']
        self.request['action'] = 'edit'
        with self.assertRaises(AuthorizationError):
            self.check()

    def test_valera_engineering_denied(self):
        self.grant['agent_id'] = self.context['agent_id'] = 'valera'
        with self.assertRaises(AuthorizationError):
            self.check()

    def test_explore_read_only(self):
        self.grant['agent_id'] = self.context['agent_id'] = 'explore'
        self.check()
        for action in ['edit', 'test']:
            self.request['action'] = action
            with self.subTest(action=action), self.assertRaises(AuthorizationError):
                self.check()

    def test_noncanonical_request_paths(self):
        for path in ['', '.', '/', '/src/new.py', 'src/../new.py', 'src/./new.py',
                     'src//new.py', 'src/', 'src\\new.py', 'src/*', 'src/?', 'src/[ab]',
                     'src/\x00bad', '../src', 1]:
            self.request['path'] = path
            with self.subTest(path=path), self.assertRaises(AuthorizationError):
                self.check()

    def test_noncanonical_grant_paths(self):
        for path in ['.', 'src/', 'src//x', 'src/../x', '/src', 'src\\x', 'src/*']:
            self.grant['paths'] = [path, 'src']
            with self.subTest(path=path), self.assertRaises(AuthorizationError):
                self.check()

    def test_component_prefix(self):
        self.request['path'] = 'src2/other.py'
        with self.assertRaises(AuthorizationError):
            self.check()
        self.request['path'] = 'src'
        self.check()

    def test_secret_paths(self):
        for path in ['src/.env', 'src/.env.local', 'src/.git/config', 'src/nested/.env.production']:
            self.request['path'] = path
            with self.subTest(path=path), self.assertRaises(AuthorizationError):
                self.check()

    def test_symlink_directory_escape(self):
        (self.root / 'src' / 'link').symlink_to(self.root.parent, target_is_directory=True)
        self.request['path'] = 'src/link/new.py'
        with self.assertRaises(AuthorizationError):
            self.check()

    def test_symlink_inside_workspace_and_dangling_leaf(self):
        for name, target in [('inside', self.root / 'src'), ('dangling', self.root / 'absent')]:
            (self.root / 'src' / name).symlink_to(target)
            self.request['path'] = 'src/' + name
            with self.subTest(name=name), self.assertRaises(AuthorizationError):
                self.check()

    def test_symlink_grant_path(self):
        (self.root / 'alias').symlink_to(self.root / 'src', target_is_directory=True)
        self.grant['paths'] = ['alias', 'src']
        with self.assertRaises(AuthorizationError):
            self.check()

    def test_invalid_workspace(self):
        for root in ['relative', str(self.root / 'absent')]:
            self.context['workspace_root'] = root
            with self.subTest(root=root), self.assertRaises(AuthorizationError):
                self.check()

    def test_resolver_failure_and_schema(self):
        for result in [None, {}, dict(self.grant, extra=True)]:
            self.resolve = lambda ref: result
            with self.subTest(result=result), self.assertRaises(AuthorizationError):
                self.check()
        def failure(ref):
            raise OSError('unavailable')
        self.resolve = failure
        with self.assertRaises(AuthorizationError):
            self.check()

    def test_hardlink_cannot_alias_protected_secret(self):
        import os
        secret=self.root/'.env'
        secret.write_text('private')
        alias=self.root/'src'/'alias.py'
        os.link(secret,alias)
        self.request={'action':'edit','path':'src/alias.py'}
        with self.assertRaises(AuthorizationError):
            self.check()
        self.assertEqual(secret.read_text(),'private')
