"""Trusted host guard for the Linux offline diagnostic profile."""
import os
from pathlib import Path
import re
import sys


def offline_network_valid(outer, inner, devices):
    return (all(type(v) is str and re.fullmatch(r'net:\[\d+\]', v) for v in (outer, inner))
            and outer != inner and type(devices) is str and
            [line.split(':', 1)[0].strip() for line in devices.strip().splitlines()[2:]] == ['lo'])


def require_offline_network():
    try:
        valid = sys.platform.startswith('linux') and offline_network_valid(
            os.environ.get('POTATO_OUTER_NETNS'), os.readlink('/proc/self/ns/net'),
            Path('/proc/net/dev').read_text())
    except (OSError, UnicodeError):
        valid = False
    if not valid:
        raise ValueError('Offline network namespace required before dispatch')
