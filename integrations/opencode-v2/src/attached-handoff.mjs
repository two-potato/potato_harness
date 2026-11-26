import fs from 'node:fs';
import path from 'node:path';
import {ROOT} from './profile.mjs';

export function consumeAttachedHandoff(envelope,mode){
 if(!['attached-free','attached-free-fixture'].includes(mode))throw Error('ATTACHED_HANDOFF_MODE');
 const python=['.venv-demo/bin/python','.venv/bin/python'].map(p=>path.join(ROOT,p)).find(p=>fs.existsSync(p));
 if(!python)throw Error('ATTACHED_HOST_PYTHON_MISSING');
 const helper=Bun.spawnSync([python,'-I','-c',
  'import sys;sys.path.insert(0,sys.argv[1]);from harness.runtime.attached_handoff import main;sys.exit(main(sys.argv[2]))',
  ROOT,'opencode-v2-'+mode],
  {stdin:Buffer.from(JSON.stringify(envelope)),stdout:'pipe',stderr:'pipe',timeout:15000});
 if(helper.exitCode!==0||helper.stdout.byteLength>262144)throw Error('ATTACHED_HOST_HANDOFF_HOLD');
 return JSON.parse(helper.stdout.toString());
}
