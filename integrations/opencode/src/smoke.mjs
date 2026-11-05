import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
import {prepareProject} from './profile.mjs';
import {createOpencodeClient,createOpencodeServer} from '@opencode-ai/sdk';
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'potato-omo-smoke-'));
process.env.HOME=dir;process.env.XDG_CONFIG_HOME=path.join(dir,'config');process.env.XDG_CACHE_HOME=path.join(dir,'cache');process.env.XDG_DATA_HOME=path.join(dir,'data');
process.env.OPENCODE_DISABLE_DEFAULT_PLUGINS='true';
const config=prepareProject(dir,'opencode/gpt-6.1-sol');
let server;
try{
 process.chdir(dir);
 server=await createOpencodeServer({hostname:'127.0.0.1',port:0,timeout:30000,config});
 const client=createOpencodeClient({baseUrl:server.url,directory:dir,throwOnError:true});
 const agents=await client.app.agents();
 if(!agents.data?.find(a=>a.name==='valera-ceo')?.description?.includes('[OMO 5.1.60 + Potato Harness]'))throw Error('Composed OMO/Harness plugin did not execute config hook');
 console.log(JSON.stringify({server:server.url,agents:agents.data?.map(a=>a.name),omoLoaded:true}));
}finally{server?.close();fs.rmSync(dir,{recursive:true,force:true});}
