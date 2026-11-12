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
import time
import uuid

from harness.controller import Controller,Event,initialize,ROOT,_json
from harness.budget import Budget
from harness.state import Outbox
from harness.context import DOMAIN_PROFILES,_redact,compile_context
from harness.scheduler import Scheduler
from harness.isolation.backend import BubblewrapBackend
from harness.jev import Jev
from harness.leases import LeaseManager
from harness.publisher import Publisher
from harness.policy import authorize,_parts
from harness.verifier import TrustedEvidence,digest_bytes,verify_bundle

MAX_BYTES=1024*1024


def _write(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        stream.write(_json(value));stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


def _git(repo,*args):
    result=subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-C',str(repo),*args],capture_output=True,check=True,env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'})
    return result.stdout.decode().strip()


def _config(config):
    required={'repo','base_sha','model','scope','test_argv','objective','budget','output'}
    if set(config)-required-{'completion_jev','worker_command','jev_provider','jev_model','domain_profile'} or not required<=set(config):raise ValueError('Unknown or missing config fields')
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
    return deepcopy(config)


def init(config,state):
    config=_config(config);state=Path(state).absolute()
    repo=Path(config['repo']).resolve(strict=True)
    if _git(repo,'status','--porcelain') or _git(repo,'rev-parse','HEAD')!=config['base_sha']:raise ValueError('Trusted repository must be clean at pinned base SHA')
    output=Path(config['output']).absolute()
    if output.exists() or output.is_relative_to(repo) or any(p.is_symlink() for p in (output,*output.parents)):raise ValueError('Output must be a new nonsymlink directory outside source repository')
    if state.exists():raise ValueError('State directory already exists')
    if state.is_relative_to(repo):raise ValueError('State must be outside repository')
    state.mkdir(mode=0o700,parents=True)
    workspace=state/'workspace';workspace.mkdir(mode=0o700)
    # Raw blobs avoid .gitattributes export-ignore/export-subst transformations.
    entries=subprocess.check_output(['/usr/bin/git','-C',str(repo),'ls-tree','-rz','--full-tree',config['base_sha']]).split(b'\0')
    total_bytes=0
    for entry in entries:
        if not entry:continue
        header,encoded_name=entry.split(b'\t',1);mode,kind,blob=header.decode().split()
        name=encoded_name.decode('utf-8');parts=_parts(name)
        if kind!='blob' or mode not in ('100644','100755'):raise ValueError('Only regular tracked source files allowed')
        size=int(_git(repo,'cat-file','-s',blob));total_bytes+=size
        if size>MAX_BYTES or total_bytes>32*MAX_BYTES:raise ValueError('Source exceeds trial byte bounds')
        content=subprocess.check_output(['/usr/bin/git','-C',str(repo),'cat-file','blob',blob])
        target=workspace.joinpath(*parts);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as output:output.write(content)
        target.chmod(0o755 if mode=='100755' else 0o644)
    for name in config['scope']:
        if not (workspace/name).is_file():raise ValueError('Trial scope must name existing tracked files')
    # Host-only Git object database; workers only see the archive workspace.
    _git(repo,'bundle','create',str(state/'base.bundle'),'HEAD')
    integration=state/'integration-repo';integration.mkdir(mode=0o700)
    _git(integration,'init')
    _git(integration,'fetch',str(state/'base.bundle'),'HEAD')
    _git(integration,'checkout','--detach','FETCH_HEAD')
    initialize(state/'state.db')
    task=json.loads((ROOT/'fixtures/valid/task.json').read_text())
    task.update(task_id='trial-'+uuid.uuid4().hex,workflow_id='persistent-trial',user_turn_id=uuid.uuid4().hex,repository_id=digest_bytes(str(repo).encode()),revision=0,row_version=0,owner='backend',task_class='BOUNDED',risk='LOW',objective=config['objective'],scope=config['scope'],depends_on=[],acceptance=[{'id':'configured-tests','expected':config['objective'],'requires':['relevant_checks','basic_review','acceptance_coverage']}],base_commit={'hash_algorithm':'sha1' if len(config['base_sha'])==40 else 'sha256','value':config['base_sha']},target_commit={'hash_algorithm':'sha1' if len(config['base_sha'])==40 else 'sha256','value':config['base_sha']},required_checks=['relevant_checks','basic_review','acceptance_coverage'],policy_version='bounded-trial-3.0',budget_id='trial-budget')
    Controller(state/'state.db').create_task(task,event_id='intake',idempotency_key='intake')
    b=config['budget'];record=json.loads((ROOT/'fixtures/valid/budget.json').read_text())
    record.update(task_id=task['task_id'],revision=0,budget_id=task['budget_id'],token_soft=b['tokens'],token_hard=b['tokens'],cost_usd_soft=b['cost_usd'],cost_usd_hard=b['cost_usd'],wall_time_s_soft=math.ceil(b['wall_time_s']),wall_time_s_hard=math.ceil(b['wall_time_s']),max_parallel_workers=1)
    Budget(state/'state.db').configure(task['task_id'],record)
    _write(state/'config.json',config)
    _write(state/'run.json',{'task_id':task['task_id'],'state':'INITIALIZED','reason':'Ready for sandbox probe','trace':[],'lease_id':None,'grant':None})
    return status(state)


def status(state):
    state=Path(state).absolute();run=json.loads((state/'run.json').read_text());task=Controller(state/'state.db').get_task(run['task_id'])
    return {**run,'task_status':task['status'],'revision':task['revision'],'unresolved_effects':Outbox(state/'state.db').unresolved(task['task_id'])}


@contextmanager
def _lock(state):
    with (state/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


class _Guard:
    """Trusted trial guard. EXECUTING checks the *persisted* lease and budget.

    The in-memory grant binding is host-issued and checked against the database
    fencing token. This is not yet a general durable grant issuer.
    """
    ready=False;artifact=False;verified=False;audit=False;clean=False

    def __init__(self,database):
        self.database=Path(database).resolve()
        self.execution=None

    def _can_execute(self,context):
        binding=self.execution
        before=context.before
        if (not self.ready or before['status']!='ASSIGNED' or
                context.after['revision']!=before['revision'] or
                not isinstance(binding,dict)):
            return False
        grant=binding.get('grant')
        if not isinstance(grant,dict):
            return False
        now=datetime.now(timezone.utc)
        try:
            if (grant.get('status')!='ACTIVE' or
                    grant.get('task_id')!=before['task_id'] or
                    grant.get('task_revision')!=before['revision'] or
                    grant.get('agent_id')!=before['owner'] or
                    grant.get('worker_session_id')!=binding['session'] or
                    grant.get('workspace_id')!='trial-workspace' or
                    set(grant.get('actions',[]))!={'read','edit','test'} or
                    grant.get('paths')!=before['scope'] or
                    grant.get('policy_digest')!=digest_bytes((ROOT/'policy/checks.json').read_bytes()) or
                    datetime.fromisoformat(grant['expires_at'])<=now):
                return False
            db=sqlite3.connect(self.database.as_uri()+'?mode=ro',uri=True)
            db.row_factory=sqlite3.Row
            try:
                db.execute('BEGIN')
                lease=db.execute('SELECT * FROM leases WHERE lease_id=?',
                                 (binding['lease_id'],)).fetchone()
                budget=db.execute('SELECT r.*,b.task_id,b.revision,b.budget_json '
                                  'FROM budget_reservations r JOIN budgets b USING(budget_id) '
                                  'WHERE r.attempt_id=?',(binding['attempt_id'],)).fetchone()
                claims=db.execute('SELECT kind,resource_key FROM lease_claims WHERE lease_id=? '
                                  'ORDER BY kind,resource_key',(binding['lease_id'],)).fetchall()
                if not lease or not budget:
                    return False
                if (lease['status']!='ACTIVE' or
                        lease['task_id']!=before['task_id'] or
                        lease['task_revision']!=before['revision'] or
                        lease['repository_id']!=before['repository_id'] or
                        lease['worker_session_id']!=binding['session'] or
                        lease['workspace_id']!='trial-workspace' or
                        datetime.fromisoformat(lease['expires_at'])<=now or
                        grant['fencing_token']!=lease['fencing_token']):
                    return False
                if sorted((r['kind'],r['resource_key']) for r in claims)!=sorted(
                        ('path',p) for p in before['scope']):
                    return False
                if (budget['task_id']!=before['task_id'] or
                        budget['revision']!=before['revision'] or
                        budget['settlement'] is not None or
                        budget['tokens']!=binding['tokens'] or
                        budget['cost']!=binding['cost'] or
                        json.loads(budget['budget_json'])['status']!='ACTIVE'):
                    return False
                if db.execute("SELECT 1 FROM outbox WHERE task_id=? AND state='UNKNOWN' LIMIT 1",
                              (before['task_id'],)).fetchone():
                    return False
                return True
            finally:
                db.close()
        except (KeyError,TypeError,ValueError,sqlite3.Error,OSError):
            return False

    def __call__(self,c):
        target=c.after['status']
        if target=='BLOCKED':return True
        if c.event.kind=='pin_target':return self.artifact
        if target=='EXECUTING':return self._can_execute(c)
        if target in ('CLASSIFIED','PLANNED','ASSIGNED'):return self.ready
        if target in ('REVIEWING','VERIFYING'):return self.artifact
        if target=='COMPLETION_AUDITING':return self.verified
        if target=='ACCEPTED':return self.verified and self.audit
        if target=='DONE':return self.verified and self.audit and self.clean
        return False


def _worker(request,command,timeout):
    # No shell. Provider bridge is host-trusted; the model only returns edit data.
    with __import__('tempfile').TemporaryFile() as out,__import__('tempfile').TemporaryFile() as err:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True)
        try:process.communicate(_json(request).encode(),timeout=timeout)
        except BaseException as error:
            import signal
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
            if isinstance(error,subprocess.TimeoutExpired):raise RuntimeError('Provider bridge timed out; outcome uncertain') from None
            raise
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
    with _lock(state):
        return _run(state,worker or _worker,
                    sandbox_probe if sandbox_probe is not None else backend.probe,
                    sandbox_run if sandbox_run is not None else backend.run)


def _run(state,worker,sandbox_probe,sandbox_run):
    config=_config(json.loads((state/'config.json').read_text()));run=json.loads((state/'run.json').read_text())
    if run['state']!='INITIALIZED':raise ValueError('Run already started; inspect status/recover, never auto-replay')
    guard=_Guard(state/'state.db');controller=Controller(state/'state.db',guard=guard);task=controller.get_task(run['task_id'])
    outbox=Outbox(state/'state.db');budget=Budget(state/'state.db');leases=LeaseManager(state/'state.db')
    workspace=state/'workspace';grant=None;effect=None;claimed=False;provider_returned=False
    deadline=time.monotonic()+config['budget']['wall_time_s']
    def remaining():
        value=min(80,deadline-time.monotonic())
        if value<=0:raise ValueError('Hard wall time exhausted')
        return value
    def save():_write(state/'run.json',run)
    def move(target,reference=None):
        nonlocal task
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
        isolation=sandbox_probe();run['sandbox']=isolation;save()
        if isolation.get('available') is not True:raise RuntimeError('Sandbox unavailable: '+str(isolation.get('reason')))
        jev=Jev(state/'state.db',provider=_jev_provider(config));run['jev_preflight']=jev.preflight(task['task_id']);save()
        guard.ready=True
        for target in ('CLASSIFIED','PLANNED'):move(target)
        dag={'nodes':[{'id':'trial','task_id':task['task_id'],'needs':[]}]}
        if Scheduler(state/'state.db').ready(dag)!=[task['task_id']]:raise ValueError('Task not in bounded ready queue')
        move('ASSIGNED')
        before=_snapshot(workspace)
        # Reserve finite provider budget BEFORE execution state or lease issuance.
        attempt='provider-'+task['task_id']
        budget.reserve(task['task_id'],config['budget']['tokens'],config['budget']['estimate_cost_usd'],attempt)
        session=uuid.uuid4().hex
        # ASSIGNED leases are prospective: LeaseManager.validate still denies
        # worker effects until the trusted controller enters EXECUTING.
        lease=leases.acquire(task['task_id'],task['row_version'],session,'trial-workspace',[{'kind':'path','key':p} for p in config['scope']])
        run['lease_id']=lease['lease_id']
        grant=json.loads((ROOT/'fixtures/valid/capability-grant.json').read_text())
        grant.update(grant_id='trial-edit',task_id=task['task_id'],task_revision=task['revision'],agent_id='backend',worker_session_id=session,workspace_id='trial-workspace',actions=['read','edit','test'],paths=config['scope'],policy_digest=digest_bytes((ROOT/'policy/checks.json').read_bytes()),fencing_token=lease['fencing_token'],expires_at=(datetime.now(timezone.utc)+timedelta(seconds=90)).isoformat())
        run['grant']=grant;run['attempt_id']=attempt;save()
        guard.execution={'lease_id':lease['lease_id'],'session':session,
                         'attempt_id':attempt,'grant':deepcopy(grant),
                         'tokens':config['budget']['tokens'],
                         'cost':config['budget']['estimate_cost_usd']}
        move('EXECUTING')
        context={k:grant[k] for k in ('task_id','task_revision','agent_id','worker_session_id','workspace_id','policy_digest','fencing_token')};context['workspace_root']=str(workspace)
        def allowed(action,path):
            leases.validate(lease['lease_id'],task['task_id'],task['revision'],session,'trial-workspace')
            authorize(grant['grant_id'],{'action':action,'path':path},context,lambda _:deepcopy(grant),lambda:datetime.now(timezone.utc))
        segments=[{'name':'task-contract','text':_json({'objective':config['objective'],'scope':config['scope'],'required_output':{'edits':[{'path':'exact scoped path','content':'replacement UTF-8 text'}],'summary':'brief explanation'}}),'mandatory':True,'trust':'untrusted'}]
        for name in config['scope']:
            allowed('read',name)
            segments.append({'name':name,'text':(workspace/name).read_text(),'mandatory':True,'trust':'untrusted'})
        pack=compile_context(task,{'role':'backend','session_id':session},segments,config['budget']['tokens']-1,lambda text:len(text.encode('utf-8')),domain_profile=config.get('domain_profile'))
        # This host counter is a conservative byte ceiling, never an exact tokenizer.
        prompt=pack['text']
        input_ceiling=len(prompt.encode('utf-8'))
        if input_ceiling>=config['budget']['tokens']:raise ValueError('Mandatory prompt byte ceiling exceeds finite token reservation; increase budget')
        run['context']={'digest':pack['content_hash'],'role_prompt_hash':pack['role_prompt_hash'],'policy_digest':pack['policy_digest'],'input_utf8_bytes':input_ceiling,'count_method':'conservative UTF-8 byte ceiling; not exact model tokens','output_token_allowance':min(4096,config['budget']['tokens']-input_ceiling)};save()
        provider_project=state/'provider-project';provider_project.mkdir(mode=0o700)
        command=config.get('worker_command',[str(ROOT/'integrations/opencode/node_modules/.bin/bun'),str(ROOT/'integrations/opencode/src/worker.mjs')])
        if type(command) is not list or not command or any(type(v) is not str for v in command):raise ValueError('Host worker command must be argv')
        request={'role':'backend','prompt':prompt,'model':config['model'],'projectDir':str(provider_project),'coordination':{'objective':_redact(config['objective']),'scope':config['scope']},'output_token_allowance':run['context']['output_token_allowance']}
        effect=outbox.reserve(task['task_id'],task['revision'],{'kind':'provider-proposal','model':config['model'],'context_digest':run['context']['digest']},'provider:'+task['task_id'])
        run['effect_id']=effect;run['attempt_id']=attempt;save()
        claimed=outbox.claim(effect)
        if not claimed:raise RuntimeError('Effect already claimed; reconcile external outcome')
        response=worker(request,command,remaining())
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
        publisher=Publisher(state/'state.db',state/'objects');publications=[]
        for path in changed:
            allowed('read',path);artifact=(workspace/path).read_bytes()
            publications.append(publisher.publish(lease_id=lease['lease_id'],worker_session_id=session,workspace_id='trial-workspace',fencing_token=lease['fencing_token'],path=path,artifact=artifact,expected_digest=digest_bytes(artifact)))
        run['publications']=publications
        # Commit in the separate host-only checkout; no .git reaches worker.
        integration=state/'integration-repo'
        # Bypass attribute clean filters: the committed blobs are exactly tested bytes.
        for path in sorted(after):
            _safe_edit(integration,path,(workspace/path).read_bytes())
            blob=_git(integration,'hash-object','-w','--no-filters','--',path)
            mode='100755' if (workspace/path).stat().st_mode & 0o111 else '100644'
            _git(integration,'update-index','--add','--cacheinfo',mode,blob,path)
        tree=_git(integration,'write-tree')
        target=_git(integration,'-c','user.name=Potato Trial Host','-c','user.email=trial@localhost.invalid','commit-tree',tree,'-p',config['base_sha'],'-m','Bounded trial candidate')
        _git(integration,'update-ref','HEAD',target)
        cleanup();guard.artifact=True
        task=controller.pin_target(task['task_id'],task['row_version'],{'hash_algorithm':'sha1' if len(target)==40 else 'sha256','value':target},event_id='pin',idempotency_key='pin')
        lease=leases.acquire(task['task_id'],task['row_version'],session,'trial-workspace',[{'kind':'path','key':p} for p in config['scope']]);run['lease_id']=lease['lease_id'];save()
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
            record={'schema_version':'3.0.1','evidence_id':check,'task_id':task['task_id'],'task_revision':task['revision'],'repository_id':task['repository_id'],'acceptance_ids':['configured-tests'],'commit':task['target_commit'],'kind':'test' if check=='relevant_checks' else 'basic_review' if check=='basic_review' else 'contract_check','check_id':check,'source':'persistent-trial-host','issuer_id':'trial-host','attestation_ref':'host:'+check,'run_id':uuid.uuid4().hex,'result':'PASS' if check!='relevant_checks' or test.get('returncode')==0 and test.get('timed_out') is False else 'FAIL','artifact_digest':digest_bytes(artifact),'created_at':datetime.now(timezone.utc).isoformat(),'policy_version':task['policy_version']}
            records.append(record);attestations[record['attestation_ref']]=TrustedEvidence(deepcopy(record),artifact)
            (state/(check+'.artifact')).write_bytes(artifact)
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
        result={'target_commit':task['target_commit'],'publications':publications,'checks':[r['check_id'] for r in records]}
        _write(state/'result.json',result)
        output=Path(config['output']).absolute();output.mkdir(parents=True,exist_ok=False,mode=0o700)
        _write(output/'result.json',result)
        artifacts_output=output/'artifacts';artifacts_output.mkdir(mode=0o700)
        for receipt in publications:
            (artifacts_output/receipt['digest'].split(':')[1]).write_bytes(Path(receipt['object_path']).read_bytes())
        for check in artifacts:(output/(check+'.artifact')).write_bytes(artifacts[check])
        _write(output/'evidence.json',records)
        move('DONE');run.update(state='DONE')
    except Exception as error:
        if effect and claimed and not provider_returned:
            try:outbox.mark_unknown(effect)
            except ValueError:pass
        cleanup()
        if task['status'] not in ('DONE','CANCELLED','BLOCKED'):move('BLOCKED','runtime-hold')
        run.update(state='HOLD',reason=_redact(str(error)))
    save();return status(state)


def recover(state):
    state=Path(state).absolute()
    with _lock(state):
        run=json.loads((state/'run.json').read_text());outbox=Outbox(state/'state.db')
        task=Controller(state/'state.db').get_task(run['task_id'])
        if task['status']=='DONE' and run['state']=='DONE':
            return status(state)
        with outbox.controller._connection() as db:
            effects=[row[0] for row in db.execute("SELECT effect_id FROM outbox WHERE task_id=? AND state='DISPATCHING'",(run['task_id'],))]
            active_leases=[row[0] for row in db.execute(
                "SELECT lease_id FROM leases WHERE task_id=? AND status IN ('ACTIVE','SUSPECT')",
                (run['task_id'],))]
        for effect in effects:outbox.mark_unknown(effect)
        leases=LeaseManager(state/'state.db')
        # The run.json pointer may lag SQLite after a host crash. Inspect all
        # persisted leases, not just the latest optional pointer.
        for lease_id in active_leases:leases.suspect(lease_id)
        run.update(state='HOLD',reason='Recovery never retransmits effects; reconcile UNKNOWN outcomes and fence suspect leases before a new task')
        _write(state/'run.json',run)
        return status(state)


def halo(state,*,train=None,evaluation=None,holdout=None):
    run=status(state)
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
