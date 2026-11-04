"""Run with python -m harness.demo; see tools/run_demo.py for bootstrap."""
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from .runner import run_all, terminal_lines


def main(argv=None):
    parser = argparse.ArgumentParser(description='Potato Harness: four disposable demo scenarios')
    parser.add_argument('--output', type=Path, default=Path('.runtime') / ('demo-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')))
    parser.add_argument('--adapter', choices=['offline', 'ollama'], default='offline')
    parser.add_argument('--model', help='An already installed Ollama model; required for --adapter ollama')
    parser.add_argument('--endpoint', default='http://127.0.0.1:11434')
    parser.add_argument('--jev-provider', choices=['opencode','typesafe'])
    parser.add_argument('--jev-model')
    parser.add_argument('--jev-completion', action='store_true')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Output path already exists; choose a new directory')
    if args.adapter == 'ollama' and not args.model:
        parser.error('--model is required for Ollama')
    jev_provider = None
    if args.jev_provider:
        from harness.jev.transport import SystemOne
        key = os.environ.get('OPENCODE_API_KEY' if args.jev_provider == 'opencode' else 'TYPESAFE_API_KEY')
        if not key or not args.jev_model:
            parser.error('Configure provider API key in environment and --jev-model')
        jev_provider = SystemOne(provider=args.jev_provider, model=args.jev_model, api_key=key)
    elif args.jev_completion:
        parser.error('--jev-completion requires --jev-provider')
    proposal = None
    model_info = {'live_call':False, 'model':None, 'requests':0, 'elapsed_seconds':None}
    try:
        if args.adapter == 'ollama':
            from harness.adapters.ollama import propose
            started = time.perf_counter()
            proposal = propose(args.model, endpoint=args.endpoint)
            model_info.update(live_call=True, model=args.model, requests=1,
                              elapsed_seconds=round(time.perf_counter() - started, 4))
        summary = run_all(args.output, proposal=proposal, adapter=args.adapter, model_info=model_info, jev_provider=jev_provider, jev_completion=args.jev_completion)
        print('\n'.join(terminal_lines(summary)))
        print('\nReport: ' + str((args.output / 'index.html').resolve()))
        return 0 if summary['all_expected'] else 1
    except (ValueError, RuntimeError, OSError) as error:
        print('Demo stopped: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
