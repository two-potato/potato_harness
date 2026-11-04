"""Report actual availability without any host execution fallback."""
import argparse
import json

from . import probe

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--probe', action='store_true', required=True)
parser.parse_args()
status = probe()
print(json.dumps(status, sort_keys=True))
raise SystemExit(0 if status['available'] else 1)
