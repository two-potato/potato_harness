import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,sign} from 'node:crypto';
import {verifyReviewRecord,REVIEW_SCOPE} from '../src/attached-admission.mjs';
const {privateKey,publicKey}=generateKeyPairSync('ed25519');
const pem=publicKey.export({type:'spki',format:'pem'});
const now=Date.parse('2026-11-26T00:00:00Z');
const base={version:1,revision:'a'.repeat(40),manifest_sha256:'b'.repeat(64),
 scope:REVIEW_SCOPE,expires_at:'2026-11-27T00:00:00Z'};
const encode=o=>Buffer.from(JSON.stringify(o));
const signature=b=>sign(null,b,privateKey);
test('review receipt needs the separately enrolled Ed25519 public key',()=>{
 const raw=encode(base),sig=signature(raw);
 assert.deepEqual(verifyReviewRecord(raw,sig,pem,now),base);
 const other=generateKeyPairSync('ed25519').publicKey.export({type:'spki',format:'pem'});
 assert.throws(()=>verifyReviewRecord(raw,sig,other,now));
 assert.throws(()=>verifyReviewRecord(encode({...base,revision:'c'.repeat(40)}),sig,pem,now));
});
test('signed but expired, broad, long-lived or malformed receipts fail closed',()=>{
 for(const patch of [{expires_at:'2026-11-25T00:00:00Z'},{expires_at:'2026-12-26T00:00:00Z'},
  {scope:'production'},{scope:'attached-zero-price-subtotal-v1'},{revision:'main'},{version:2},{manifest_sha256:'x'},{approved:true}]){
  const raw=encode({...base,...patch});assert.throws(()=>verifyReviewRecord(raw,signature(raw),pem,now));
 }
});
