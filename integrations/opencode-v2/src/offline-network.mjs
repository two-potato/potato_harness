// Linux-only offline diagnostic guard. Never silently fall back to live networking.
import fs from 'node:fs';
export function offlineNetworkValid(outer,inner,devices){
 if(typeof outer!=='string'||typeof inner!=='string'||!/^net:\[\d+\]$/.test(outer)||!/^net:\[\d+\]$/.test(inner)||outer===inner||typeof devices!=='string')return false;
 const names=devices.trim().split('\n').slice(2).map(line=>line.split(':')[0].trim());
 return names.length===1&&names[0]==='lo';
}
export function requireOfflineNetwork(){
 if(process.platform!=='linux'||!offlineNetworkValid(process.env.POTATO_OUTER_NETNS,fs.readlinkSync('/proc/self/ns/net'),fs.readFileSync('/proc/net/dev','utf8')))throw Error('OFFLINE_NETWORK_REQUIRED');
}
