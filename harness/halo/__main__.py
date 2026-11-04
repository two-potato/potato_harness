import argparse
import json
from pathlib import Path
from . import run_demo

parser = argparse.ArgumentParser(description='Offline synthetic HALO proposal demo (no network)')
parser.add_argument('--output',type=Path,required=True)
args = parser.parse_args()
result = run_demo(args.output)
print(json.dumps({'status':result['status'],'output':str(args.output),'synthetic':True}))
raise SystemExit(0 if result['status']=='PROPOSED' else 1)
