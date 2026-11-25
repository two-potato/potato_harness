"""Private Linux exec helper; only invoked by the trusted isolation host.

Run with an isolated Python interpreter. Apply limits in this fresh process,
then replace it with the fixed Bubblewrap executable. No generic host command
or fallback is accepted. This is not an independent sandbox boundary.
"""
import os
import resource
import sys

BWRAP = '/usr/bin/bwrap'
OUTPUT_LIMIT = 1024 * 1024
MEMORY_LIMIT = 1024 * 1024 * 1024


def _cap(value, ceiling):
    return ceiling if value == resource.RLIM_INFINITY else min(value, ceiling)


def _apply_limits(cpu):
    if type(cpu) is not int or not 1 <= cpu <= 120:
        raise ValueError('Invalid CPU limit')
    for kind, soft, hard in (
        (resource.RLIMIT_FSIZE, OUTPUT_LIMIT, OUTPUT_LIMIT),
        (resource.RLIMIT_CPU, cpu, cpu + 1),
        (resource.RLIMIT_AS, MEMORY_LIMIT, MEMORY_LIMIT),
        (resource.RLIMIT_NOFILE, 64, 64),
        (resource.RLIMIT_CORE, 0, 0),
    ):
        old_soft, old_hard = resource.getrlimit(kind)
        new_hard = _cap(old_hard, hard)
        new_soft = min(_cap(old_soft, soft), new_hard)
        resource.setrlimit(kind, (new_soft, new_hard))


def main(args):
    try:
        if (sys.platform != 'linux' or len(args) < 3 or args[1] != '--' or
                not args[0].isascii() or not args[0].isdigit()):
            raise ValueError('Invalid launcher arguments')
        cpu = int(args[0])
        _apply_limits(cpu)
        # The host owns the complete Bubblewrap profile. Never execute argv[0]
        # as a host executable and never inherit a caller's environment.
        os.execve(BWRAP, [BWRAP, *args[2:]], {})
    except (OSError, ValueError, OverflowError):
        print('Sandbox launcher failed to apply limits or exec Bubblewrap',
              file=sys.stderr)
        return 125
    return 125


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
