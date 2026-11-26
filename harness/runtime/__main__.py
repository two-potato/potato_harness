import argparse
import json
from pathlib import Path
from harness.runtime import init,run,status,recover,halo


def main():
    parser=argparse.ArgumentParser(description='Persistent fail-closed bounded trial runtime')
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('init','run','status','recover','halo'):
        item=sub.add_parser(command);item.add_argument('--state',required=True)
        if command=='init':item.add_argument('--config',required=True)
        if command=='run':
            item.add_argument('--confirm-attached-trial',action='store_true')
            item.add_argument('--trust-attached-opencode',action='store_true',help='Accept the reviewed existing OpenCode as trusted transport for this synthetic trial only')
        if command=='halo':
            item.add_argument('--train');item.add_argument('--eval',dest='evaluation');item.add_argument('--holdout')
    args=parser.parse_args()
    try:
        if args.command=='init':result=init(json.loads(Path(args.config).read_text()),args.state)
        elif args.command=='halo':result=halo(args.state,train=args.train,evaluation=args.evaluation,holdout=args.holdout)
        elif args.command=='run':result=run(args.state,confirm_attached_trial=args.confirm_attached_trial,trust_attached_opencode=args.trust_attached_opencode)
        else:result=globals()[args.command](args.state)
        print(json.dumps(result,indent=2));return 0 if result.get('state')!='HOLD' and result.get('status')!='HOLD' else 2
    except Exception as error:
        print(json.dumps({'status':'HOLD','reason':str(error)}));return 2

if __name__=='__main__':raise SystemExit(main())
