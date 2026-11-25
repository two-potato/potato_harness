import {test} from 'node:test';
import assert from 'node:assert/strict';
import {BridgeDeadlineError} from '../src/bridge_limits.mjs';
import {valeraFailure} from '../src/valera_diagnostics.mjs';
test('fixed deadline and SDK status categories never include raw text',()=>{
 const secret='PRIVATE_TOKEN';
 assert.deepEqual(valeraFailure('prompt',new BridgeDeadlineError(secret)),{step:'prompt',reason_code:'DEADLINE'});
 assert.deepEqual(valeraFailure('prompt',{name:'AbortError',message:secret}),{step:'prompt',reason_code:'ABORTED'});
 assert.deepEqual(valeraFailure('response',{data:{statusCode:401,message:secret}}),{step:'response',reason_code:'AUTH'});
 assert.deepEqual(valeraFailure('response',{data:{statusCode:429,message:secret}}),{step:'response',reason_code:'RATE_LIMIT'});
 assert.deepEqual(valeraFailure('prompt',Error(secret)),{step:'prompt',reason_code:'STEP_FAILED'});
 assert.deepEqual(valeraFailure('json',SyntaxError(secret)),{step:'json',reason_code:'INVALID_JSON'});
 assert.deepEqual(valeraFailure('assignment',Error(secret)),{step:'assignment',reason_code:'INVALID_ASSIGNMENT'});
 assert.deepEqual(valeraFailure('close',Error(secret)),{step:'close',reason_code:'STEP_FAILED'});
 assert.deepEqual(valeraFailure(secret,Error(secret)),{step:'unknown',reason_code:'STEP_FAILED'});
});
