#!/usr/bin/env python3
"""One-command bootstrap; no API keys or model downloads in default mode."""
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info < (3, 12):
        raise SystemExit('Python 3.12 or newer is required')
    directory = ROOT / '.venv-demo'
    python = directory / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.exists():
        print('Creating isolated demo environment...', flush=True)
        venv.EnvBuilder(with_pip=True).create(directory)
    requirements = ROOT / 'requirements-validation.txt'
    marker = directory / 'potato-requirements.txt'
    if not marker.exists() or marker.read_bytes() != requirements.read_bytes():
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
        marker.write_bytes(requirements.read_bytes())
    return subprocess.run([str(python), '-m', 'harness.demo', *sys.argv[1:]], cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
