// A real CLI server preflight. No session is prompted; no external inference.
import os from 'node:os';
import {withTimeout} from './bridge_limits.mjs';
import {launchPrivateServer,awaitServerPolicy} from './server-process.mjs';
let server,ok=false;
try{
 if(process.argv.length!==3)throw Error('MODEL_ARGUMENT_REQUIRED');
 const binary=Bun.which('opencode');
 if(!binary)throw Error('CLI_NOT_FOUND');
 const {OpenCode}=await import('@opencode/client');
 server=await launchPrivateServer({binary,operatorHome:os.homedir(),model:process.argv[2],clientFactory:OpenCode.make});
 await withTimeout(()=>awaitServerPolicy(server),20000);
 console.log(JSON.stringify({status:'PASS',layer:'native-cli-server-preflight',version:'2.4.1',model:process.argv[2],policy:'active',external_inference:false,console_api:false}));
 ok=true;
}catch(e){
 // Only locally authored fixed error codes; never echo server/provider text.
 const known=new Set(['MODEL_ARGUMENT_REQUIRED','CLI_NOT_FOUND','CLI_VERSION_FAILED','CLI_VERSION_MISMATCH','CLI_VERSION_TIMEOUT','FREE_MODEL_REQUIRED','UNSAFE_SERVER_STATE_DIRECTORY','UNSAFE_SERVER_ENDPOINT','SERVER_VERSION_MISMATCH','SERVER_START_FAILED','SERVER_POLICY_OR_FREE_MODEL_NOT_READY']);
 console.error(JSON.stringify({status:'HOLD',reason:known.has(e?.message)?e.message:'SERVER_PREFLIGHT_FAILED',external_inference:false}));
}finally{
 try{await server?.close();}catch{ok=false;console.error('SERVER_CLEANUP_FAILED');}
}
process.exitCode=ok?0:2;
