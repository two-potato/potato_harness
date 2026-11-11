"""Check local development or protected execution prerequisites."""

import argparse
import json

from . import check_readiness, MODES


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=MODES, default='development')
    args = parser.parse_args(argv)
    report = check_readiness(args.mode)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
