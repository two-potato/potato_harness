import test from 'node:test';
import assert from 'node:assert/strict';
import {offlineNetworkValid} from '../src/offline-network.mjs';
test('offline diagnostic requires distinct Linux net namespace with loopback only',()=>{
 const header='Inter-| Receive | Transmit\n face |bytes packets |bytes packets\n';
 const lo=header+' lo: 0 0 0 0\n';
 assert.equal(offlineNetworkValid('net:[1]','net:[2]',lo),true);
 for(const [a,b,d] of [['net:[1]','net:[1]',lo],[undefined,'net:[2]',lo],['bad','net:[2]',lo],['net:[1]','net:[2]',lo+' eth0: 0 0 0 0\n'],['net:[1]','net:[2]',header]])assert.equal(offlineNetworkValid(a,b,d),false);
});
