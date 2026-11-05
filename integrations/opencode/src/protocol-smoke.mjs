// Real OpenCode+OMO with local provider fixture. No external model/key.
import {createServer} from 'node:http';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import assert from 'node:assert/strict';
import {createOpencodeServer,createOpencodeClient} from '@opencode-ai/sdk';import {prepareProject} from './profile.mjs';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'potato-provider-smoke-'));let server;let count=0;
const fixture=createServer(async(req,res)=>{
 let input='';for await(const chunk of req)input+=chunk;
 if(req.url?.endsWith('/chat/completions')){
  count++;const body=JSON.parse(input);assert.ok(body.messages.some(m=>m.role==='user'));assert.ok((body.max_tokens??body.max_completion_tokens)<=64);
  const lastUser=JSON.stringify(body.messages.filter(m=>m.role==='user').at(-1)?.content);
  const isPlan=lastUser.includes('fixture JSON coordination')||lastUser.includes('approved_owner');
  const content=JSON.stringify(isPlan?{owner:'backend',reason:'fixture routing'}:{edits:[{path:'example.py',content:'result = 42\n'}],summary:'fixture proposal'});
  if(body.stream){res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:1,model:'fixture',choices:[{index:0,delta:{role:'assistant',content},finish_reason:null}]})+'\n\n');res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:1,model:'fixture',choices:[{index:0,delta:{},finish_reason:'stop'}],usage:{prompt_tokens:10,completion_tokens:10,total_tokens:20}})+'\n\n');res.end('data: [DONE]\n\n');}
  else{res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({id:'fixture',object:'chat.completion',created:1,model:'fixture',choices:[{index:0,message:{role:'assistant',content},finish_reason:'stop'}],usage:{prompt_tokens:10,completion_tokens:10,total_tokens:20}}));}
 }else{res.writeHead(404);res.end();}
});
try{
 await new Promise(r=>fixture.listen(0,'127.0.0.1',r));
 process.env.HOME=temp;process.env.XDG_CONFIG_HOME=path.join(temp,'config');process.env.XDG_DATA_HOME=path.join(temp,'data');process.env.XDG_CACHE_HOME=path.join(temp,'cache');process.env.OPENCODE_DISABLE_DEFAULT_PLUGINS='true';
 process.env.OPENCODE_SERVER_USERNAME='potato';process.env.OPENCODE_SERVER_PASSWORD='test-fixture-password';
 const config=prepareProject(temp,'fixture/test');
 config.provider={fixture:{npm:'@ai-sdk/openai-compatible',name:'Fixture',options:{baseURL:`http://127.0.0.1:${fixture.address().port}/v1`,apiKey:'test-only'},models:{test:{name:'fixture-test',limit:{context:64000,output:64},cost:{input:0,output:0}}}}};
 process.chdir(temp);server=await createOpencodeServer({hostname:'127.0.0.1',port:0,timeout:30000,config});
 const client=createOpencodeClient({baseUrl:server.url,directory:temp,throwOnError:true,headers:{Authorization:'Basic '+Buffer.from('potato:test-fixture-password').toString('base64')}});
 const agents=await client.app.agents();assert.ok(agents.data.find(a=>a.name==='valera-ceo').description.includes('[OMO 5.1.60 + Potato Harness]'));
 const session=await client.session.create({body:{title:'Fixture integration'}});
 const planning=await client.session.prompt({path:{id:session.data.id},body:{agent:'valera-ceo',parts:[{type:'text',text:'Return the fixture JSON coordination.'}],tools:{}}});
 const plan=JSON.parse(planning.data.parts.filter(p=>p.type==='text').map(p=>p.text).join(''));assert.equal(plan.owner,'backend');
 const response=await client.session.prompt({path:{id:session.data.id},body:{agent:'backend',parts:[{type:'text',text:'Return the fixture JSON proposal.'}],tools:{}}});
 if(response.data.info.error)throw Error(JSON.stringify(response.data.info.error));
 const text=response.data.parts.filter(x=>x.type==='text').map(x=>x.text).join('');
 const proposal=JSON.parse(text);assert.equal(proposal.edits[0].path,'example.py');assert.equal(count,2);
 await client.session.delete({path:{id:session.data.id}});
 const {fileURLToPath}=await import('node:url');
 const workerPath=path.join(path.dirname(fileURLToPath(import.meta.url)),'worker.mjs');
 const child=Bun.spawn([process.execPath,workerPath],{env:{PATH:process.env.PATH,POTATO_PROVIDER_FIXTURE_URL:`http://127.0.0.1:${fixture.address().port}/v1`},stdin:'pipe',stdout:'pipe',stderr:'pipe'});
 child.stdin.write(JSON.stringify({role:'backend',model:'fixture/test',prompt:'Return fixture JSON proposal.',output_token_allowance:128,coordination:{objective:'Fixture repair',scope:['example.py']}}));child.stdin.end();
 const workerOutput=await new Response(child.stdout).text(),workerError=await new Response(child.stderr).text();
 assert.equal(await child.exited,0,workerError);const workerResult=JSON.parse(workerOutput);assert.equal(workerResult.edits[0].path,'example.py');assert.equal(workerResult.usage.input_tokens,20);assert.equal(count,4);
 console.log(JSON.stringify({status:'PASS',layer:'real-opencode-omo-local-provider-fixture',provider_requests:count,proposal,live_inference:false}));
}finally{server?.close();await new Promise(r=>fixture.close(r));fs.rmSync(temp,{recursive:true,force:true});}
