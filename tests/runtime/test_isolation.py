import json
import os
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from harness.isolation import SandboxUnavailable, probe, run_private


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)

    def test_missing_binary_fails_probe(self):
        with patch('harness.isolation.BWRAP', '/missing/bwrap'):
            result = probe()
        self.assertFalse(result['available'])
        self.assertTrue(result['reason'])
        self.assertIn('version', result)

    def test_nonlinux_fails_closed(self):
        with patch('harness.isolation.sys.platform', 'darwin'):
            self.assertFalse(probe()['available'])
            with self.assertRaises(SandboxUnavailable):
                run_private(self.workspace, ['/usr/bin/true'])

    def test_probe_failure_never_runs_payload(self):
        payload = self.workspace / 'host-marker'
        with patch('harness.isolation.probe', return_value={
                'available': False, 'reason': 'namespace denied', 'version': 'test'}):
            with self.assertRaises(SandboxUnavailable):
                run_private(self.workspace, ['/usr/bin/touch', str(payload)])
        self.assertFalse(payload.exists())

    def test_unsafe_workspace_roots(self):
        for path in [Path('/'), Path('/usr'), Path('/usr/bin'), Path('/etc'), Path('/proc'),
                     Path('/tmp'), Path('relative'), self.workspace / 'missing']:
            with self.subTest(path=path), self.assertRaises((ValueError, SandboxUnavailable)):
                run_private(path, ['/usr/bin/true'])

    def test_symlink_workspace_and_ancestor(self):
        link = self.workspace / 'link'
        link.symlink_to(self.workspace, target_is_directory=True)
        (self.workspace / 'child').mkdir()
        for path in [link, link / 'child']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                run_private(path, ['/usr/bin/true'])

    def test_argv_is_strict_no_shell_coercion(self):
        for argv in ['echo hello', (), [], [''], ['true', None], ['true\x00'], ['--help']]:
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                run_private(self.workspace, argv)

    def test_timeout_bounds(self):
        for timeout in [0, -1, True, float('nan'), float('inf'), 121, '10']:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                run_private(self.workspace, ['/usr/bin/true'], timeout=timeout)

    def test_cli_probe_reports_actual_availability(self):
        result = subprocess.run([sys.executable, '-m', 'harness.isolation', '--probe'],
                                capture_output=True, text=True, timeout=15)
        record = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0 if record['available'] else 1)
        self.assertIn('reason', record)

    def test_workspace_socket_denied_when_host_can_create_socket(self):
        try:
            endpoint = socket.socket(socket.AF_UNIX)
        except PermissionError as exc:
            self.skipTest('Host socket creation unavailable: ' + str(exc))
        self.addCleanup(endpoint.close)
        endpoint.bind(str(self.workspace / 'host.sock'))
        with self.assertRaises(ValueError):
            run_private(self.workspace, ['/usr/bin/true'])

    def test_workspace_fifo_denied(self):
        os.mkfifo(self.workspace / 'pipe')
        with self.assertRaises(ValueError):
            run_private(self.workspace, ['/usr/bin/true'])

    def test_profile_and_fresh_probe_used_for_each_run(self):
        from harness.isolation import _command
        command = _command(self.workspace, ['/usr/bin/true'])
        for option in ['--unshare-all', '--unshare-user', '--disable-userns', '--cap-drop',
                       '--new-session', '--die-with-parent', '--clearenv']:
            self.assertIn(option, command)
        self.assertNotIn('--share-net', command)
        self.assertEqual(command[command.index('--ro-bind') + 1:command.index('--ro-bind') + 3],
                         ['/usr', '/usr'])
        self.assertEqual(command.count('--bind'), 1)
        self.assertEqual(command[command.index('--bind') + 1:command.index('--bind') + 3],
                         [str(self.workspace), '/work'])
        denied = {'available': False, 'reason': 'revoked platform support', 'version': 'test'}
        with patch('harness.isolation.probe', side_effect=[dict(denied, available=True), denied]) as check:
            with patch('harness.isolation._execute', return_value={'returncode': 0}) as execute:
                run_private(self.workspace, ['/usr/bin/true'])
                with self.assertRaises(SandboxUnavailable):
                    run_private(self.workspace, ['/usr/bin/true'])
                self.assertEqual(execute.call_count, 1)
            self.assertEqual(check.call_count, 2)

    def test_timeout_kills_process_group_then_waits(self):
        from harness.isolation import _execute
        process = Mock(pid=12345, returncode=-9)
        process.wait.side_effect = [subprocess.TimeoutExpired('bwrap', .1), -9]
        with patch('harness.isolation.subprocess.Popen', return_value=process) as popen:
            with patch('harness.isolation.os.killpg') as kill:
                result = _execute(['/usr/bin/bwrap', '--version'], .1)
        kill.assert_called_once_with(12345, 9)
        self.assertEqual(process.wait.call_count, 2)
        self.assertTrue(result['timed_out'])
        self.assertFalse(popen.call_args.kwargs['shell'])
        self.assertTrue(popen.call_args.kwargs['start_new_session'])

    def live(self):
        status = probe()
        if not status['available']:
            self.skipTest('Live isolation unavailable: ' + status['reason'])

    def test_live_private_workspace_and_absent_host_paths(self):
        self.live()
        code = "from pathlib import Path; Path('/work/result').write_text('private'); assert not Path('/etc/passwd').exists(); assert not Path('/root').exists(); assert not Path('/var/run/docker.sock').exists()"
        result = run_private(self.workspace, ['/usr/bin/python3', '-c', code])
        self.assertEqual(result['returncode'], 0, result)
        self.assertEqual((self.workspace / 'result').read_text(), 'private')

    def test_live_network_denied(self):
        self.live()
        code = "import socket; s=socket.socket(); s.settimeout(1);\ntry: s.connect(('1.1.1.1',443))\nexcept OSError: pass\nelse: raise AssertionError('network connected')"
        result = run_private(self.workspace, ['/usr/bin/python3', '-c', code])
        self.assertEqual(result['returncode'], 0, result)

    def test_live_usr_read_only(self):
        self.live()
        result = run_private(self.workspace, ['/usr/bin/touch', '/usr/isolation-escape-test'])
        self.assertNotEqual(result['returncode'], 0)

    def test_live_timeout_kills_and_waits(self):
        self.live()
        result = run_private(self.workspace, ['/usr/bin/python3', '-c', 'import time; time.sleep(10)'], timeout=.2)
        self.assertTrue(result['timed_out'])
        self.assertNotEqual(result['returncode'], 0)

    def test_live_output_bounded(self):
        self.live()
        result = run_private(self.workspace, ['/usr/bin/python3', '-c', "import os; os.write(1,b'x'*2000000)"])
        self.assertLessEqual(len(result['stdout'].encode()), 1048576)
