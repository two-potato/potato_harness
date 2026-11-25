// A separate, Linux-network-isolated diagnostic. Never admit provider inference.
import os from 'node:os';
import {requireOfflineNetwork} from './offline-network.mjs';
import {modelRef} from './server-policy.mjs';
import {launchPrivateServer,awaitServerPolicy} from './server-process.mjs';
import {runNativeProbe} from './server-inference.mjs';
let report,isolated=false;
try{
 requireOfflineNetwork();isolated=true;
 if(process.argv.length!==3)throw Error('MODEL_ARGUMENT_REQUIRED');
 const model=process.argv[2];modelRef(model);
 const binary=Bun.which('opencode');
 if(!binary)throw Error('CLI_NOT_FOUND');
 const {OpenCode}=await import('@opencode/client');
 report=await runNativeProbe({model,offline:true,awaitPolicy:awaitServerPolicy,launch:options=>launchPrivateServer({...options,binary,operatorHome:os.homedir(),clientFactory:OpenCode.make})});
}catch{
 report={status:'HOLD',layer:'native-cli-offline-diagnostic',reason:isolated?'ARGUMENT_OR_SETUP_HOLD':'OFFLINE_NETWORK_REQUIRED',external_inference:false,attempted_prompts:0,runtime_admission:false};
}
console.log(JSON.stringify({...report,offline_network:isolated}));
process.exitCode=2;
