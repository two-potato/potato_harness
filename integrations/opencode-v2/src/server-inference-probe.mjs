// Explicit opt-in only. Never called by installation, CI or the runtime.
import os from 'node:os';
import {launchPrivateServer,awaitServerPolicy} from './server-process.mjs';
import {probeArgs,runNativeProbe} from './server-inference.mjs';
let report;
try{
 const model=probeArgs(process.argv.slice(2));
 const binary=Bun.which('opencode');
 if(!binary)throw Error('CLI_NOT_FOUND');
 const {OpenCode}=await import('@opencode/client');
 report=await runNativeProbe({model,awaitPolicy:awaitServerPolicy,launch:options=>launchPrivateServer({...options,binary,operatorHome:os.homedir(),clientFactory:OpenCode.make})});
}catch{
 report={status:'HOLD',layer:'native-cli-server-inference-probe',reason:'ARGUMENT_OR_SETUP_HOLD',external_inference:false,attempted_prompts:0,runtime_admission:false};
}
console.log(JSON.stringify(report));
process.exitCode=report.status==='PASS'?0:2;
