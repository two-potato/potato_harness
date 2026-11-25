"""Fail-closed Linux Bubblewrap profile for explicitly private workspaces.

The host must own the workspace and all inputs. This is not a production kernel
sandbox certification or an atomic filesystem/lease boundary.
"""
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
from time import monotonic

BWRAP = '/usr/bin/bwrap'
OUTPUT_LIMIT = 1024 * 1024
MEMORY_LIMIT = 1024 * 1024 * 1024
SYSTEM_ROOTS = ('/usr', '/etc', '/home', '/root', '/proc', '/sys', '/dev', '/run', '/var',
                '/bin', '/lib', '/lib64', '/boot', '/opt')


class SandboxUnavailable(RuntimeError):
    """The required isolation profile cannot be established; no fallback allowed."""


def _execute(argv, timeout):
    # Only trusted host code constructs the Bubblewrap command. Resource
    # limits are installed in a fresh isolated interpreter, not preexec_fn:
    # fork-time Python callbacks can deadlock in a multithreaded host.
    if (type(argv) is not list or len(argv)<2 or argv[0]!=BWRAP or
            BWRAP!='/usr/bin/bwrap' or any(type(arg) is not str or '\0' in arg for arg in argv)):
        raise ValueError('Only the fixed Bubblewrap executable is admitted')
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=120:
        raise ValueError('Invalid sandbox timeout')
    helper=Path(__file__).resolve().with_name('_launcher.py')
    command=[sys.executable,'-I','-S',str(helper),str(max(1,math.ceil(timeout))),'--',*argv[1:]]
    # Regular files avoid unbounded PIPE capture and blocked pipe readers.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   shell=False, close_fds=True, start_new_session=True,
                                   env={}, cwd='/')
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except BaseException as error:
            timed_out=isinstance(error,subprocess.TimeoutExpired)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if not timed_out:
                raise
        stdout.seek(0)
        stderr.seek(0)
        return {'returncode': process.returncode,
                'stdout': stdout.read(OUTPUT_LIMIT).decode('utf-8', errors='replace'),
                'stderr': stderr.read(OUTPUT_LIMIT).decode('utf-8', errors='replace'),
                'timed_out': timed_out}


def _command(workspace, argv):
    return [BWRAP, '--unshare-all', '--unshare-user', '--disable-userns', '--cap-drop', 'ALL',
            '--new-session', '--die-with-parent', '--clearenv',
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
            '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
            '--tmpfs', '/tmp', '--proc', '/proc', '--dev', '/dev',
            '--bind', str(workspace), '/work', '--chdir', '/work',
            '--setenv', 'PATH', '/usr/bin:/bin', '--', *argv]


def probe() -> dict:
    """Actually launch the profile; binary presence alone does not mean available."""
    result = {'available': False, 'reason': '', 'version': None}
    if sys.platform != 'linux':
        result['reason'] = 'Linux namespaces are required'
        return result
    try:
        if not Path(BWRAP).is_file() or not os.access(BWRAP, os.X_OK):
            raise OSError('Bubblewrap executable is missing: ' + BWRAP)
        version = _execute([BWRAP, '--version'], 3)
        result['version'] = version['stdout'].strip() or None
        if version['returncode'] != 0 or version['timed_out']:
            raise OSError('Bubblewrap version check failed: ' + version['stderr'].strip())
        with tempfile.TemporaryDirectory(prefix='harness-probe-') as workspace:
            smoke = _execute(_command(Path(workspace), ['/usr/bin/true']), 3)
        if smoke['returncode'] != 0 or smoke['timed_out']:
            result['reason'] = 'Bubblewrap profile failed: ' + (smoke['stderr'].strip() or
                                ('timeout' if smoke['timed_out'] else str(smoke['returncode'])))
            return result
        result.update(available=True, reason='Bubblewrap profile launched successfully')
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result['reason'] = str(exc)
    return result


def _workspace(workspace):
    if not isinstance(workspace, Path) or not workspace.is_absolute():
        raise ValueError('An absolute private workspace Path is required')
    if '..' in workspace.parts or workspace == Path('/') or workspace == Path('/tmp'):
        raise ValueError('Unsafe workspace root')
    for root in SYSTEM_ROOTS:
        if workspace.is_relative_to(Path(root)):
            raise ValueError('System paths cannot be writable workspaces')
    if any(path.is_symlink() for path in [workspace, *workspace.parents]):
        raise ValueError('Workspace and ancestors must not be symlinks')
    if not workspace.is_dir():
        raise ValueError('Workspace must be an existing private directory')
    # Exclude inherited host sockets, devices and symlink aliases. This inspection
    # assumes the host prevents concurrent mutation; it is not race-resistant IO.
    def scan_error(error):
        raise ValueError('Cannot inspect private workspace') from error
    for directory, directories, files in os.walk(workspace, followlinks=False, onerror=scan_error):
        for name in directories + files:
            mode = (Path(directory) / name).lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError('Workspace contains symlink or special file')
    return workspace.resolve(strict=True)


def _arguments(argv, timeout):
    if type(argv) is not list or not argv or any(type(arg) is not str or '\x00' in arg for arg in argv):
        raise ValueError('argv must be a nonempty list of NUL-free strings')
    if not argv[0] or not argv[0].startswith('/') or any(part in ('.', '..', '') for part in argv[0].split('/')[1:]):
        raise ValueError('Executable must be a canonical absolute sandbox path')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError('timeout must be finite and in (0, 120] seconds')


def run_private(workspace: Path, argv: list[str], timeout=10) -> dict:
    """Run direct argv inside the verified profile or raise; never execute on host."""
    _arguments(argv, timeout)
    deadline = monotonic() + timeout
    workspace = _workspace(workspace)
    status = probe()
    if not status['available']:
        raise SandboxUnavailable(status['reason'])
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise SandboxUnavailable('Sandbox deadline exhausted before payload launch')
    try:
        return _execute(_command(workspace, argv), remaining)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SandboxUnavailable('Bubblewrap launch failed: ' + str(exc)) from exc
