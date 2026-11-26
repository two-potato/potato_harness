"""Persistent single-host trial runner; credentials and execution stay on host."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import tempfile
import time
import uuid

from harness.controller import Controller,Event,initialize,ROOT,_json
from harness.budget import Budget
from harness.runtime.offline_network import require_offline_network
from harness.runtime.dispatch import reserve_provider_dispatch
from harness.runtime.workspace import MAX_BYTES,_git,prepare_workspace,repository_identity
from harness.state import Outbox
from harness.context import DOMAIN_PROFILES,_redact,compile_context
from harness.scheduler import Scheduler, SPECIALISTS
from harness.isolation.backend import BubblewrapBackend
from harness.jev import Jev
from harness.leases import LeaseManager
from harness.publisher import Publisher
from harness.policy import authorize,_parts
from harness.verifier import TrustedEvidence,digest_bytes,verify_bundle

def _write_private_bytes(path,data):
    """Write host-owned state atomically, independent of the caller's umask."""
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),0o600)
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write(path,value):
    _write_private_bytes(path,_json(value).encode('utf-8'))


def _config(config):
    required={'repo','base_sha','model','scope','test_argv','objective','budget','output'}
    if set(config)-required-{'completion_jev','worker_command','jev_provider','jev_model','domain_profile','adapter','provider_budget_confirmed'} or not required<=set(config):raise ValueError('Unknown or missing config fields')
    if not all(isinstance(config[k],str) and config[k] for k in ('repo','base_sha','model','objective','output')):raise ValueError('Nonempty config text required')
    if not re.fullmatch('[a-f0-9]{40}|[a-f0-9]{64}',config['base_sha']):raise ValueError('Pinned base SHA required')
    if not isinstance(config['scope'],list) or not config['scope'] or len(set(config['scope']))!=len(config['scope']):raise ValueError('Unique exact-file scope required')
    for name in config['scope']:
        _parts(name)
        if re.search(r'(?i)(^|/)(\.github|policy|rules|agents|auth|security|deploy|infra|secrets?|credentials?)(/|\.|$)|(?i:password|payment|migration|dockerfile)',name):raise ValueError('Scope requires human risk classification; bounded trial rejects it')
    argv=config['test_argv']
    if type(argv) is not list or not argv or any(type(x) is not str or '\0' in x for x in argv) or not argv[0].startswith('/'):raise ValueError('Trusted absolute test argv required')
    b=config['budget']
    if set(b)!={'tokens','cost_usd','estimate_cost_usd','wall_time_s'}:raise ValueError('Exact finite budget configuration required')
    if type(b['tokens']) is not int or b['tokens']<1:raise ValueError('Positive token budget required')
    for name in ('cost_usd','estimate_cost_usd','wall_time_s'):
        if type(b[name]) not in (int,float) or not math.isfinite(b[name]) or b[name]<=0:raise ValueError('Finite positive budget required')
    if b['estimate_cost_usd']>b['cost_usd'] or b['wall_time_s']>120:raise ValueError('Estimate exceeds budget or wall time exceeds trial 120s')
    if type(config.get('completion_jev',False)) is not bool:raise ValueError('completion_jev must be boolean')
    if 'domain_profile' in config:
        profile = config['domain_profile']
        if not isinstance(profile, str) or profile not in DOMAIN_PROFILES:
            raise ValueError('Unknown domain profile')
    config=deepcopy(config)
    if 'worker_command' in config:
        if 'adapter' in config:
            raise ValueError('Explicit adapter cannot be combined with worker_command')
        command=config['worker_command']
        if type(command) is not list or not command or any(type(v) is not str or not v for v in command) or not command[0].startswith('/'):
            raise ValueError('Custom host worker requires absolute argv')
        if 'provider_budget_confirmed' in config:
            raise ValueError('Provider budget confirmation is only valid for Console profile')
        return config
    adapter=config.setdefault('adapter','opencode-v2-console')
    if adapter=='opencode-v2-native-free':
        raise ValueError('Native free live activation HOLD: candidate is not admitted; independent review and live evidence required')
    if adapter not in ('opencode-v2-fixture','opencode-v2-console','opencode-v2-native-free-fixture','opencode-v2-native-free-offline'):
        raise ValueError('Unknown provider adapter; create a new v2 trial')
    if adapter.startswith('opencode-v2'):
        if config.get('jev_provider') or config.get('completion_jev'):
            raise ValueError('V2 bounded profile does not admit separate Jev calls')
        if adapter=='opencode-v2-fixture' and (config['model']!='fixture/test' or config['scope']!=['calculation.py'] or config['objective']!='Fix subtotal so it multiplies integer unit price by quantity. Preserve function signature.'):
            raise ValueError('V2 fixture is restricted to the generated subtotal trial')
        if adapter=='opencode-v2-native-free-fixture' and (config['model']!='opencode/potato-runtime-fixture-free' or config['scope']!=['calculation.py'] or config['objective']!='Fix subtotal so it multiplies integer unit price by quantity. Preserve function signature.'):
            raise ValueError('Native free fixture is restricted to the synthetic subtotal trial')
        if adapter=='opencode-v2-native-free-offline' and (not re.fullmatch(r'opencode/[a-z0-9][a-z0-9.-]{0,126}-free',config['model']) or config['model']=='opencode/potato-runtime-fixture-free' or config['scope']!=['calculation.py'] or config['objective']!='Fix subtotal so it multiplies integer unit price by quantity. Preserve function signature.'):
            raise ValueError('Native offline profile requires an explicit free model and generated subtotal trial')
        if adapter=='opencode-v2-console' and (config['model']!='opencode/minimax-m3' or config.get('provider_budget_confirmed') is not True):
            raise ValueError('V2 Console requires the explicit paid model and operator-confirmed provider budget')
    if 'provider_budget_confirmed' in config and (adapter!='opencode-v2-console' or config['provider_budget_confirmed'] is not True):
        raise ValueError('Provider budget confirmation is only valid for Console profile')
    return deepcopy(config)


def _worker_command(config):
    if 'worker_command' in config:return config['worker_command']
    bun=str(ROOT/'integrations/opencode-v2/node_modules/.bin/bun')
    adapter=config['adapter']
    mode={'opencode-v2-fixture':'fixture','opencode-v2-console':'console','opencode-v2-native-free-fixture':'native-free-fixture','opencode-v2-native-free-offline':'native-free-offline'}[adapter]
    return [bun,str(ROOT/'integrations/opencode-v2/src/worker.mjs'),mode]


def init(config,state):
    config=_config(config);state=Path(state).absolute()
    repo=Path(config['repo']).resolve(strict=True)
    if _git(repo,'status','--porcelain') or _git(repo,'rev-parse','HEAD')!=config['base_sha']:raise ValueError('Trusted repository must be clean at pinned base SHA')
    output=Path(config['output']).absolute()
    if output.exists() or output.is_relative_to(repo) or any(p.is_symlink() for p in (output,*output.parents)):raise ValueError('Output must be a new nonsymlink directory outside source repository')
    if state.exists():raise ValueError('State directory already exists')
    if state.is_relative_to(repo):raise ValueError('State must be outside repository')
    state.mkdir(mode=0o700,parents=True)
    prepare_workspace(repo,config['base_sha'],config['scope'],state)
    initialize(state/'state.db')
    task=json.loads((ROOT/'fixtures/valid/task.json').read_text())
    task.update(task_id='trial-'+uuid.uuid4().hex,workflow_id='persistent-trial',user_turn_id=uuid.uuid4().hex,repository_id=repository_identity(repo),revision=0,row_version=0,owner='backend',task_class='BOUNDED',risk='LOW',objective=config['objective'],scope=config['scope'],depends_on=[],acceptance=[{'id':'configured-tests','expected':config['objective'],'requires':['relevant_checks','basic_review','acceptance_coverage']}],base_commit={'hash_algorithm':'sha1' if len(config['base_sha'])==40 else 'sha256','value':config['base_sha']},target_commit={'hash_algorithm':'sha1' if len(config['base_sha'])==40 else 'sha256','value':config['base_sha']},required_checks=['relevant_checks','basic_review','acceptance_coverage'],policy_version='bounded-trial-3.0',budget_id='trial-budget')
    Controller(state/'state.db').create_task(task,event_id='intake',idempotency_key='intake')
    b=config['budget'];record=json.loads((ROOT/'fixtures/valid/budget.json').read_text())
    record.update(task_id=task['task_id'],revision=0,budget_id=task['budget_id'],token_soft=b['tokens'],token_hard=b['tokens'],cost_usd_soft=b['cost_usd'],cost_usd_hard=b['cost_usd'],wall_time_s_soft=math.ceil(b['wall_time_s']),wall_time_s_hard=math.ceil(b['wall_time_s']),max_parallel_workers=1)
    Budget(state/'state.db').configure(task['task_id'],record)
    _write(state/'config.json',config)
    _write(state/'run.json',{'task_id':task['task_id'],'state':'INITIALIZED','reason':'Ready for sandbox probe','trace':[],'lease_id':None,'grant':None,**({'adapter':config['adapter'],'provider_mode':'offline' if config['adapter']=='opencode-v2-native-free-offline' else 'synthetic' if config['adapter'] in ('opencode-v2-fixture','opencode-v2-native-free-fixture') else 'external'} if 'adapter' in config else {})})
    return status(state)


def status(state):
    state=Path(state).absolute()
    return _status(state,state/'state.db')


def _status(state,database):
    run=json.loads((state/'run.json').read_text());task=Controller(database).get_task(run['task_id'])
    return {**run,'task_status':task['status'],'revision':task['revision'],'unresolved_effects':Outbox(database).unresolved(task['task_id'])}


@contextmanager
def _lock(state):
    with (state/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


class _Guard:
    ready=False;artifact=False;verified=False;audit=False;clean=False
    def __call__(self,c):
        target=c.after['status']
        if target=='BLOCKED':return True
        if c.event.kind=='pin_target':return self.artifact
        if target in ('CLASSIFIED','PLANNED','ASSIGNED','EXECUTING'):return self.ready
        if target in ('REVIEWING','VERIFYING'):return self.artifact
        if target=='COMPLETION_AUDITING':return self.verified
        if target=='ACCEPTED':return self.verified and self.audit
        if target=='DONE':return self.verified and self.audit and self.clean
        return False


def _worker(request,command,timeout,*,diagnostics_path=None):
    # No shell. Provider bridge is host-trusted; the model only returns edit data.
    # Keep raw provider stderr in an unnamed temporary file; never publish it.
    from harness.runtime.gateway_diagnostics import parse_gateway_events
    with __import__('tempfile').TemporaryFile() as out,__import__('tempfile').TemporaryFile() as err:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True)
        outcome='ERROR'
        try:
            # Shared model deadline leaves time for bounded cleanup before host expiry.
            payload={**request,'bridge_timeout_ms':min(120000,max(4001,math.floor(timeout*1000)-1000))}
            process.communicate(_json(payload).encode(),timeout=timeout)
            if process.returncode==0:outcome='OK'
        except BaseException as error:
            if isinstance(error,subprocess.TimeoutExpired):outcome='TIMEOUT'
            import signal
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
            if isinstance(error,subprocess.TimeoutExpired):raise RuntimeError('Provider bridge timed out; outcome uncertain') from None
            raise
        finally:
            if diagnostics_path is not None:
                try:
                    _write(Path(diagnostics_path),{'schema_version':1,'outcome':outcome,
                                                   'events':parse_gateway_events(err)})
                except OSError:
                    # Advisory logging failure must never authorize a retry.
                    pass
        if process.returncode:raise RuntimeError('Provider bridge failed; inspect host bridge logs')
        if out.tell()>MAX_BYTES:raise ValueError('Provider response exceeds bound')
        out.seek(0);return json.loads(out.read(MAX_BYTES))


def _snapshot(workspace):
    result={}
    for directory,dirs,files in os.walk(workspace,followlinks=False):
        for name in dirs+files:
            path=Path(directory)/name;info=path.lstat()
            if not(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) or (stat.S_ISREG(info.st_mode) and info.st_nlink!=1):raise ValueError('Unsafe workspace alias or special file')
        for name in files:
            path=Path(directory)/name
            if path.stat().st_size>MAX_BYTES:raise ValueError('Workspace file exceeds bound')
            result[str(path.relative_to(workspace))]={'digest':digest_bytes(path.read_bytes()),'executable':bool(path.stat().st_mode & 0o111)}
    return result


def _safe_edit(workspace,path,content):
    parts=_parts(path);directory=os.open(workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory);os.close(directory);directory=child
        fd=os.open(parts[-1],os.O_WRONLY|os.O_NOFOLLOW,dir_fd=directory)
        with os.fdopen(fd,'wb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('Unsafe edit target')
            stream.truncate(0);stream.write(content);stream.flush();os.fsync(stream.fileno())
    finally:os.close(directory)


def _jev_provider(config):
    if not config.get('jev_provider'):return None
    from harness.jev.transport import SystemOne
    provider=config['jev_provider']
    if provider not in ('opencode','typesafe') or not isinstance(config.get('jev_model'),str):raise ValueError('Explicit valid Jev provider/model required')
    def request(value):
        key=os.environ.get('OPENCODE_API_KEY' if provider=='opencode' else 'TYPESAFE_API_KEY','')
        return SystemOne(provider=provider,model=config['jev_model'],api_key=key)(value)
    return request


def run(state,*,worker=None,sandbox_probe=None,sandbox_run=None):
    """Injected callbacks are host test seams; CLI always uses actual sandbox."""
    backend=BubblewrapBackend()
    state=Path(state).absolute()
    if worker is None:
        def worker(request,command,timeout):
            return _worker(request,command,timeout,diagnostics_path=state/'gateway-phases.json')
    with _lock(state):
        return _run(state,worker,
                    sandbox_probe if sandbox_probe is not None else backend.probe,
                    sandbox_run if sandbox_run is not None else backend.run)


def _run(state,worker,sandbox_probe,sandbox_run,*,workflow_binding=None):
    # Private trusted-host entry point; no workflow binding is accepted by CLI.
    database=state/'state.db' if workflow_binding is None else workflow_binding['database']
    workspace_id='trial-workspace' if workflow_binding is None else workflow_binding['layout']['workspace_id']
    object_store=state/'objects' if workflow_binding is None else workflow_binding['object_store']
    saved=json.loads((state/'config.json').read_text());run=json.loads((state/'run.json').read_text())
    if run['state']!='INITIALIZED':raise ValueError('Run already started; inspect status/recover, never auto-replay')
    if 'adapter' not in saved and 'worker_command' not in saved:raise ValueError('Old initialized state cannot migrate in place; create a new v2 trial')
    config=_config(saved)
    if config.get('adapter')!=run.get('adapter'):raise ValueError('Saved adapter does not match initialized run; create a new trial')
    guard=_Guard();controller=Controller(database,guard=guard);task=controller.get_task(run['task_id'])
    role=task['owner']
    if workflow_binding is not None:
        if (task!=workflow_binding['task'] or task['status']!='PLANNED' or role not in SPECIALISTS or
                config['model']!='fixture/workflow' or config.get('worker_command')!=['/usr/bin/false'] or
                'adapter' in config or config.get('jev_provider') or config.get('completion_jev') or
                run.get('provider_mode')!='synthetic'):
            raise ValueError('Invalid synthetic workflow execution binding')
    elif role!='backend':
        raise ValueError('Single-task trial requires Backend')
    outbox=Outbox(database);budget=Budget(database);leases=LeaseManager(database)
    workspace=state/'workspace';grant=None;effect=None;claimed=False;provider_returned=False
    deadline=time.monotonic()+config['budget']['wall_time_s']
    workflow_deadline=None if workflow_binding is None else workflow_binding.get('deadline')
    def remaining():
        value=min(80,deadline-time.monotonic())
        if workflow_deadline is not None:
            value=min(value,workflow_deadline.remaining())
        if value<=0:raise ValueError('Hard wall time exhausted')
        return value
    def save():_write(state/'run.json',run)
    def move(target,reference=None):
        nonlocal task
        if workflow_deadline is not None and target!='BLOCKED':
            remaining()
        task=controller.transition(task['task_id'],task['row_version'],Event(uuid.uuid4().hex,uuid.uuid4().hex,target,reference=reference))
        run['trace'].append({'state':target,'revision':task['revision'],'row_version':task['row_version']});save()
    def cleanup():
        if grant:
            grant['status']='REVOKED';run['grant']=grant
        if run['lease_id']:
            leases.release(run['lease_id'],reconcile=True);run['lease_id']=None
        save()
    try:
        run['state']='RUNNING';save()
        if workflow_deadline is not None:remaining()
        if config.get('adapter')=='opencode-v2-native-free-offline':require_offline_network()
        isolation=sandbox_probe();run['sandbox']=isolation;save()
        if isolation.get('available') is not True:raise RuntimeError('Sandbox unavailable: '+str(isolation.get('reason')))
        if config.get('adapter')=='opencode-v2-console' and not os.environ.get('OPENCODE_API_KEY'):
            raise ValueError('Console API key missing before dispatch')
        if workflow_deadline is not None:remaining()
        jev=Jev(database,provider=_jev_provider(config));run['jev_preflight']=jev.preflight(task['task_id']);save()
        guard.ready=True
        if workflow_binding is None:
            for target in ('CLASSIFIED','PLANNED'):move(target)
            dag={'schema_version':'3.0.1','workflow_id':task['workflow_id'],'nodes':[{'id':'trial','task_id':task['task_id'],'needs':[]}]}
            if Scheduler(database).ready_workflow(dag,workflow_id=task['workflow_id'],
                    user_turn_id=task['user_turn_id'],repository_id=task['repository_id'],
                    approved_revisions={task['task_id']:task['revision']},available_owners=('backend',))!=[task['task_id']]:
                raise ValueError('Task not in bounded ready queue')
        for target in ('ASSIGNED','EXECUTING'):move(target)
        before=_snapshot(workspace)
        session=uuid.uuid4().hex
        lease=leases.acquire(task['task_id'],task['row_version'],session,workspace_id,[{'kind':'path','key':p} for p in config['scope']])
        run['lease_id']=lease['lease_id']
        grant=json.loads((ROOT/'fixtures/valid/capability-grant.json').read_text())
        grant.update(grant_id='trial-edit' if workflow_binding is None else task['task_id']+':edit',task_id=task['task_id'],task_revision=task['revision'],agent_id=role,worker_session_id=session,workspace_id=workspace_id,actions=['read','edit','test'],paths=config['scope'],policy_digest=digest_bytes((ROOT/'policy/checks.json').read_bytes()),fencing_token=lease['fencing_token'],expires_at=(datetime.now(timezone.utc)+timedelta(seconds=90)).isoformat())
        run['grant']=grant;save()
        context={k:grant[k] for k in ('task_id','task_revision','agent_id','worker_session_id','workspace_id','policy_digest','fencing_token')};context['workspace_root']=str(workspace)
        def allowed(action,path):
            if workflow_deadline is not None:remaining()
            leases.validate(lease['lease_id'],task['task_id'],task['revision'],session,workspace_id)
            authorize(grant['grant_id'],{'action':action,'path':path},context,lambda _:deepcopy(grant),lambda:datetime.now(timezone.utc))
        segments=[{'name':'task-contract','text':_json({'objective':config['objective'],'scope':config['scope'],'required_output':{'edits':[{'path':'exact scoped path','content':'replacement UTF-8 text'}],'summary':'brief explanation'}}),'mandatory':True,'trust':'untrusted'}]
        for name in config['scope']:
            allowed('read',name)
            segments.append({'name':name,'text':(workspace/name).read_text(),'mandatory':True,'trust':'untrusted'})
        if workflow_binding is not None:
            segments.extend(deepcopy(workflow_binding['segments']))
        pack=compile_context(task,{'role':role,'session_id':session},segments,config['budget']['tokens']-1,lambda text:len(text.encode('utf-8')),domain_profile=config.get('domain_profile'))
        # This host counter is a conservative byte ceiling, never an exact tokenizer.
        prompt=pack['text']
        input_ceiling=len(prompt.encode('utf-8'))
        if input_ceiling>=config['budget']['tokens']:raise ValueError('Mandatory prompt byte ceiling exceeds finite token reservation; increase budget')
        run['context']={'digest':pack['content_hash'],'role_prompt_hash':pack['role_prompt_hash'],'policy_digest':pack['policy_digest'],'input_utf8_bytes':input_ceiling,'count_method':'conservative UTF-8 byte ceiling; not exact model tokens','output_token_allowance':min(4096,config['budget']['tokens']-input_ceiling)};save()
        provider_project=state/'provider-project';provider_project.mkdir(mode=0o700)
        command=_worker_command(config)
        if type(command) is not list or not command or any(type(v) is not str for v in command):raise ValueError('Host worker command must be argv')
        request={'role':role,'prompt':prompt,'model':config['model'],'projectDir':str(provider_project),'coordination':{'objective':_redact(config['objective']),'scope':config['scope']},'output_token_allowance':run['context']['output_token_allowance']}
        if config.get('adapter') in ('opencode-v2-native-free-fixture','opencode-v2-native-free-offline'):
            request['token_allowance']=config['budget']['tokens']
        if config.get('adapter')=='opencode-v2-console':
            request['provider_budget']={'tokens':config['budget']['tokens'],'cost_usd':config['budget']['estimate_cost_usd']}
        if workflow_deadline is not None:remaining()
        dispatch=reserve_provider_dispatch(database,task_id=task['task_id'],
            revision=task['revision'],row_version=task['row_version'],owner=task['owner'],
            lease_id=lease['lease_id'],session=session,workspace=workspace_id,
            model=config['model'],context_digest=run['context']['digest'],
            tokens=config['budget']['tokens'],cost=config['budget']['estimate_cost_usd'],adapter=config.get('adapter'))
        effect=dispatch['effect_id'];attempt=dispatch['attempt_id'];claimed=True
        run['effect_id']=effect;run['attempt_id']=attempt;save()
        response=worker(request,command,remaining())
        if config.get('adapter')=='opencode-v2-native-free-offline':raise RuntimeError('Offline diagnostic cannot return a proposal')
        provider_returned=True
        outbox.finish(effect,{'response_digest':digest_bytes(_json(response).encode())},True)
        usage=response.get('usage',{});tokens=usage.get('input_tokens');output=usage.get('output_tokens');cost=usage.get('cost_usd')
        if type(tokens) is not int or tokens<0 or type(output) is not int or output<0:raise ValueError('Provider actual token usage unknown; reservation retained')
        if type(cost) not in (int,float) or not math.isfinite(cost) or cost<0:raise ValueError('Provider actual cost unknown; HOLD reservation retained for reconciliation')
        budget.settle(attempt,tokens+output,cost);run['usage']=usage;save()
        if tokens+output>config['budget']['tokens'] or cost>config['budget']['estimate_cost_usd']:raise ValueError('Provider usage exceeded reserved hard dispatch allowance; reconciled HOLD')
        remaining()
        edits=response.get('edits')
        if type(edits) is not list or not edits or len(edits)>len(config['scope']):raise ValueError('Bounded nonempty edit proposal required')
        seen=set();total=0
        for edit in edits:
            if type(edit) is not dict or set(edit)!={'path','content'} or edit['path'] in seen or edit['path'] not in config['scope'] or type(edit['content']) is not str:raise ValueError('Invalid or unscoped edit')
            seen.add(edit['path']);content=edit['content'].encode();total+=len(content)
            if total>MAX_BYTES:raise ValueError('Edit byte limit exceeded')
            allowed('edit',edit['path']);_safe_edit(workspace,edit['path'],content)
        after=_snapshot(workspace);changed=sorted(p for p in set(before)|set(after) if before.get(p)!=after.get(p))
        if not changed or any(p not in config['scope'] for p in changed):raise ValueError('Review: no change or change outside scope')
        publisher=Publisher(database,object_store);publications=[]
        for path in changed:
            allowed('read',path);artifact=(workspace/path).read_bytes()
            publications.append(publisher.publish(lease_id=lease['lease_id'],worker_session_id=session,workspace_id=workspace_id,fencing_token=lease['fencing_token'],path=path,artifact=artifact,expected_digest=digest_bytes(artifact)))
        run['publications']=publications
        # Commit in the separate host-only checkout; no .git reaches worker.
        integration=state/'integration-repo'
        # Bypass attribute clean filters: the committed blobs are exactly tested bytes.
        for path in sorted(after):
            if workflow_deadline is not None:remaining()
            _safe_edit(integration,path,(workspace/path).read_bytes())
            blob=_git(integration,'hash-object','-w','--no-filters','--',path)
            mode='100755' if (workspace/path).stat().st_mode & 0o111 else '100644'
            _git(integration,'update-index','--add','--cacheinfo',mode,blob,path)
        tree=_git(integration,'write-tree')
        target=_git(integration,'-c','user.name=Potato Trial Host','-c','user.email=trial@localhost.invalid','commit-tree',tree,'-p',config['base_sha'],'-m','Bounded trial candidate')
        if workflow_deadline is not None:remaining()
        _git(integration,'update-ref','HEAD',target)
        cleanup();guard.artifact=True
        if workflow_deadline is not None:remaining()
        task=controller.pin_target(task['task_id'],task['row_version'],{'hash_algorithm':'sha1' if len(target)==40 else 'sha256','value':target},event_id='pin' if workflow_binding is None else task['task_id']+':pin',idempotency_key='pin' if workflow_binding is None else task['task_id']+':pin')
        lease=leases.acquire(task['task_id'],task['row_version'],session,workspace_id,[{'kind':'path','key':p} for p in config['scope']]);run['lease_id']=lease['lease_id'];save()
        # Validation capability is fresh for the pinned revision and cannot edit.
        grant.update(task_revision=task['revision'],actions=['read','test'],status='ACTIVE',fencing_token=lease['fencing_token'],expires_at=(datetime.now(timezone.utc)+timedelta(seconds=90)).isoformat())
        context.update(task_revision=task['revision'],fencing_token=lease['fencing_token']);run['grant']=grant;save()
        allowed('test',config['scope'][0])
        test=sandbox_run(workspace,config['test_argv'],timeout=remaining())
        move('REVIEWING')
        test_bytes=_json(test).encode()
        # Tests may create caches, but must not modify any pinned input.
        tested=_snapshot(workspace)
        if any(tested.get(path)!=digest for path,digest in after.items()):raise ValueError('Tests modified pinned source; evidence invalid')
        artifacts={'relevant_checks':test_bytes,'basic_review':_json({'changed':changed,'scope_verified':True,'reviewer':'deterministic-host-review'}).encode(),'acceptance_coverage':_json({'configured-tests':config['test_argv'],'contract':'User-supplied test command is acceptance for this bounded trial'}).encode()}
        records=[];attestations={}
        for check,artifact in artifacts.items():
            record={'schema_version':'3.0.1','evidence_id':check if workflow_binding is None else task['task_id']+':'+check,'task_id':task['task_id'],'task_revision':task['revision'],'repository_id':task['repository_id'],'acceptance_ids':['configured-tests'],'commit':task['target_commit'],'kind':'test' if check=='relevant_checks' else 'basic_review' if check=='basic_review' else 'contract_check','check_id':check,'source':'persistent-trial-host','issuer_id':'trial-host','attestation_ref':'host:'+check if workflow_binding is None else 'host:'+task['task_id']+':'+check,'run_id':uuid.uuid4().hex,'result':'PASS' if check!='relevant_checks' or test.get('returncode')==0 and test.get('timed_out') is False else 'FAIL','artifact_digest':digest_bytes(artifact),'created_at':datetime.now(timezone.utc).isoformat(),'policy_version':task['policy_version']}
            records.append(record);attestations[record['attestation_ref']]=TrustedEvidence(deepcopy(record),artifact)
            _write_private_bytes(state/(check+'.artifact'),artifact)
        _write(state/'evidence.json',records)
        move('VERIFYING');verify_bundle(records,task,attestations.__getitem__,trusted_issuers=frozenset({'trial-host'}))
        with controller._connection(write=True) as db:
            for r in records:db.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?)',(r['evidence_id'],task['task_id'],task['revision'],task['target_commit']['value'],r['artifact_digest'],r['attestation_ref'],_json(r)))
        guard.verified=True;move('COMPLETION_AUDITING')
        run['jev_completion']=jev.completion(task['task_id'],records,attestations.__getitem__,trusted_issuers=frozenset({'trial-host'}),enabled=config.get('completion_jev',False));save()
        if config.get('completion_jev',False) and run['jev_completion']['verdict']!='CLEAR':raise ValueError('Completion advisor did not clear; requires review')
        guard.audit=True;move('ACCEPTED');cleanup();guard.clean=True
        if outbox.unresolved(task['task_id']):raise ValueError('Unresolved effects prevent completion')
        run.update(reason='Pinned source passed configured tests and deterministic bounded review')
        result={'target_commit':task['target_commit'],'publications':publications,'checks':[r['check_id'] for r in records],**({k:run[k] for k in ('adapter','provider_mode') if k in run})}
        _write(state/'result.json',result)
        output=Path(config['output']).absolute();output.mkdir(parents=True,exist_ok=False,mode=0o700)
        _write(output/'result.json',result)
        artifacts_output=output/'artifacts';artifacts_output.mkdir(mode=0o700)
        for receipt in publications:
            (artifacts_output/receipt['digest'].split(':')[1]).write_bytes(Path(receipt['object_path']).read_bytes())
        for check in artifacts:_write_private_bytes(output/(check+'.artifact'),artifacts[check])
        _write(output/'evidence.json',records)
        move('DONE');run.update(state='DONE')
    except Exception as error:
        if effect and claimed and not provider_returned:
            try:outbox.mark_unknown(effect)
            except ValueError:pass
        cleanup()
        if task['status'] not in ('DONE','CANCELLED','BLOCKED'):move('BLOCKED','runtime-hold')
        run.update(state='HOLD',reason=_redact(str(error)))
    save();return _status(state,database)


def recover(state):
    state=Path(state).absolute()
    with _lock(state):
        run=json.loads((state/'run.json').read_text());outbox=Outbox(state/'state.db')
        with outbox.controller._connection() as db:
            effects=[row[0] for row in db.execute("SELECT effect_id FROM outbox WHERE task_id=? AND state='DISPATCHING'",(run['task_id'],))]
        for effect in effects:outbox.mark_unknown(effect)
        leases=LeaseManager(state/'state.db')
        if run['lease_id']:leases.suspect(run['lease_id'])
        run.update(state='HOLD',reason='Recovery never retransmits effects; reconcile UNKNOWN outcomes and fence suspect leases before a new task')
        _write(state/'run.json',run)
        return status(state)


def halo(state,*,train=None,evaluation=None,holdout=None):
    run=status(state)
    if run.get('provider_mode') in ('synthetic','offline'):return {'status':'HOLD','reason':'Synthetic or offline v2 trial is not actual HALO inference evidence'}
    trace={'trace_id':run['task_id'],'status':run['task_status'],'checks':[],'bindings':{'revision':run['revision']},'optional_detail':_redact(run['reason'])}
    path=Path(state)/'halo-trace.json';_write(path,trace)
    if not any((train,evaluation,holdout)):
        return {'status':'HOLD','reason':'One actual trace is not separate train/validation/holdout datasets; no optimization performed','trace':str(path)}
    if not all((train,evaluation,holdout)):raise ValueError('All three explicit datasets required')
    from harness.halo import Host,TrustedEvaluator,Ledger,optimize,digest
    datasets=[]
    for filename in (train,evaluation,holdout):
        source=Path(filename)
        if source.stat().st_size>MAX_BYTES:raise ValueError('Dataset exceeds byte limit')
        rows=json.loads(source.read_text())
        if type(rows) is not list or not rows:raise ValueError('Nonempty actual trace arrays required')
        # Supplied data is host-authorized evidence; redact free text before use.
        for row in rows:
            if type(row) is not dict or set(row)!={'trace_id','status','checks','bindings','optional_detail'}:raise ValueError('Invalid redacted trace dataset')
            row['optional_detail']=_redact(row['optional_detail'])
        datasets.append(rows)
    task=Controller(Path(state)/'state.db').get_task(run['task_id'])
    evaluator=TrustedEvaluator('runtime-independent-evaluator',datasets[2])
    hashes=tuple(digest(rows) for rows in datasets)
    host=Host(task['target_commit'],task['policy_version'],tuple('actual:'+h for h in hashes),hashes,evaluator.code_digest,'runtime-offline-optimizer',evaluator.identity)
    result=optimize(host,task['target_commit'],datasets[0],datasets[1],evaluator,Ledger(Path(state)/'halo-ledger.db'),uuid.uuid4().hex)
    if 'evaluation' in result:result['evaluation']['uncertainty']='Operator-supplied actual trace datasets; deterministic text-size comparison, no statistical safety guarantee'
    _write(Path(state)/'halo-result.json',result)
    return result
