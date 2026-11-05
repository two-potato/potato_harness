process.env.DO_NOT_TRACK='1';process.env.OMO_DISABLE_TELEMETRY='1';process.env.OMO_DISABLE_POSTHOG='1';process.env.OMO_SEND_ANONYMOUS_TELEMETRY='0';
// Explicit local dependency setup only; no global OpenCode config writes.
import {spawnSync} from 'node:child_process';import path from 'node:path';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
for(const file of ['opencode-ai/postinstall.mjs','bun/install.js']){
 const r=spawnSync(process.execPath,[path.join(root,'node_modules',file)],{cwd:root,stdio:'inherit'});
 if(r.status!==0)process.exit(r.status||1);
}
