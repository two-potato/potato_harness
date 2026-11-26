// Local trust enrollment: an independently authenticated reviewer's public key,
// not a self-asserted JSON review or an environment flag.
import fs from 'node:fs';
import path from 'node:path';
import {createHash,createPublicKey,verify} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {ROOT} from './profile.mjs';
import {assertPrivateDirectory,ATTACHED_TRIAL_MODEL} from './attached-stage-ledger.mjs';
export const REVIEW_SCOPE='attached-zero-price-subtotal-v1';
const hash=b=>createHash('sha256').update(b).digest('hex');
const fail=()=>{throw Error('ATTACHED_REVIEW_NOT_VERIFIED');};
function readPrivate(file,max){
 const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
 try{
  const s=fs.fstatSync(fd);
  if(!s.isFile()||s.nlink!==1||s.uid!==process.getuid()||(s.mode&0o077)!==0||s.size>max)fail();
  return fs.readFileSync(fd);
 }finally{fs.closeSync(fd);}
}
export function verifyReviewRecord(raw,signature,pem,now=Date.now()){
 const key=createPublicKey(pem);
 if(key.asymmetricKeyType!=='ed25519'||signature.length!==64||!verify(null,raw,key,signature))fail();
 const r=JSON.parse(raw.toString('utf8'));
 if(!r||Object.keys(r).sort().join(',')!=='expires_at,manifest_sha256,revision,scope,version'||
    r.version!==1||r.scope!==REVIEW_SCOPE||typeof r.revision!=='string'||!/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(r.revision)||
    typeof r.manifest_sha256!=='string'||!/^[a-f0-9]{64}$/.test(r.manifest_sha256)||typeof r.expires_at!=='string'||
    !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(r.expires_at)||
    !Number.isFinite(Date.parse(r.expires_at))||Date.parse(r.expires_at)<=now||
    Date.parse(r.expires_at)>now+7*86400000)fail();
 return Object.freeze(r);
}
export function verifyAttachedReview(home,root=ROOT){
 try{
  if(!process.getuid||process.getuid()===0||!path.isAbsolute(home)||fs.realpathSync(home)!==home)fail();
  const dir=path.join(home,'.config/potato-harness/attached-review');
  assertPrivateDirectory(dir);
  const r=verifyReviewRecord(readPrivate(path.join(dir,'review.json'),4096),
   readPrivate(path.join(dir,'review.sig'),64),readPrivate(path.join(dir,'reviewer.pem'),4096));
  const git=(...args)=>execFileSync('/usr/bin/git',['-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
   '-C',root,...args],{encoding:'utf8',timeout:3000,stdio:['ignore','pipe','ignore'],
   env:{PATH:'/usr/bin:/bin',HOME:'/nonexistent',GIT_CONFIG_NOSYSTEM:'1',
    GIT_CONFIG_GLOBAL:'/dev/null',GIT_NO_REPLACE_OBJECTS:'1'}}).trim();
  if(fs.realpathSync(root)!==root||git('rev-parse','--show-toplevel')!==root||
     git('status','--porcelain','--untracked-files=all')!==''||
     git('rev-parse','HEAD^{tree}')!==git('rev-parse',r.revision+'^{tree}'))fail();
  git('merge-base','--is-ancestor',r.revision,'HEAD');
  const mf=fs.readFileSync(path.join(root,'MANIFEST.sha256.json'));
  if(hash(mf)!==r.manifest_sha256)fail();
  const files=JSON.parse(mf.toString('utf8'));
  if(!files||typeof files!=='object'||Array.isArray(files))fail();
  for(const [rel,digest] of Object.entries(files)){
   const f=path.join(root,rel);
   if(path.isAbsolute(rel)||!f.startsWith(root+path.sep)||fs.realpathSync(f)!==f||
      !fs.lstatSync(f).isFile()||!/^[a-f0-9]{64}$/.test(digest)||hash(fs.readFileSync(f))!==digest)fail();
  }
  return r;
 }catch{fail();}
}
export function admitReviewedScope(scope,request,home){
 const r=verifyAttachedReview(home);
 return scope?.model===ATTACHED_TRIAL_MODEL&&scope.request_sha256===hash(JSON.stringify(request))&&
  JSON.stringify(scope.roles)==='["valera-ceo","backend"]'&&scope.output_limit===1024&&
  scope.token_limit===request.token_allowance&&scope.token_limit<=100000&&
  scope.bridge_timeout_ms===request.bridge_timeout_ms&&scope.bridge_timeout_ms<=120000&&
  Date.parse(r.expires_at)>Date.now();
}
