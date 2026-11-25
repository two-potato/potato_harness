// Trusted local audit: fixed event labels only; no prompts, IDs, URLs or credentials.
import fs from 'node:fs';
export function auditSequence(worker){
 return ['ready','model:valera-ceo','http:valera-ceo','model:'+worker,'http:'+worker];
}
// Only known local labels can reach the report. Unknown input is never echoed.
export function auditViolation(event){
 if(event==='violation')return 'unspecified';
 const codes=['permission','retry','resolve_kind','resolve_model','resolve_session','resolve_role','resolve_duplicate','model_scope','model_duplicate','http_scope','http_duplicate','websocket','sequence','offline_stop','offline_http'];
 return codes.find(code=>event==='violation:'+code)??null;
}
export function readAudit(file){
 const stat=fs.lstatSync(file);
 if(!stat.isFile()||stat.size>1024||(stat.mode&0o077)!==0)throw Error('AUDIT_INVALID');
 const s=fs.readFileSync(file,'utf8');
 if(!s)return [];
 if(!s.endsWith('\n'))throw Error('AUDIT_INVALID');
 return s.slice(0,-1).split('\n');
}
export function recordAudit(file,worker,event){
 const previous=readAudit(file),expected=auditSequence(worker);
 const valid=previous.every((v,i)=>v===expected[i]);
 const violation=auditViolation(event);
 if(violation||!valid||event!==expected[previous.length]){
  if(!previous.some(x=>auditViolation(x)))fs.appendFileSync(file,violation?event+'\n':'violation:sequence\n');
  if(!violation)throw Error('AUDIT_SEQUENCE_DENIED');
  return;
 }
 fs.appendFileSync(file,event+'\n');
}
export function assertAudit(actual,worker,count){
 const expected=auditSequence(worker).slice(0,count);
 if(!Array.isArray(actual)||actual.length!==expected.length||!expected.every((v,i)=>actual[i]===v))throw Error('AUDIT_MISMATCH');
}
