"""Offline, bounded context optimization; never authorizes runtime changes."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Mapping


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Candidate:
    max_optional_detail_chars: int

    def __post_init__(self):
        if type(self.max_optional_detail_chars) is not int or self.max_optional_detail_chars not in (0, 64, 128, 256):
            raise ValueError('candidate outside finite trusted domain')

    @classmethod
    def from_dict(cls, value):
        if set(value) != {'max_optional_detail_chars'}:
            raise ValueError('unknown candidate key / invariant weakening')
        return cls(**value)

    def as_dict(self):
        return {'max_optional_detail_chars': self.max_optional_detail_chars}

    def apply(self, row):
        if set(row) != {'trace_id', 'status', 'checks', 'bindings', 'optional_detail'}:
            raise ValueError('expected redacted structured trace')
        if not isinstance(row['trace_id'], str) or not row['trace_id'] or not isinstance(row['status'], str):
            raise ValueError('invalid mandatory trace identity/status')
        if not isinstance(row['checks'], list) or not all(isinstance(v,str) for v in row['checks']) or not isinstance(row['bindings'], dict) or not isinstance(row['optional_detail'], str):
            raise ValueError('invalid trace fields')
        # Copy through canonical JSON: no caller mutation of mandatory fields.
        result = json.loads(json.dumps(row, allow_nan=False))
        result['optional_detail'] = row['optional_detail'][:self.max_optional_detail_chars]
        return result


@dataclass(frozen=True)
class Host:
    baseline_commit: Mapping
    policy_version: str
    split_ids: tuple
    split_digests: tuple
    evaluator_digest: str
    optimizer_identity: str
    evaluator_identity: str

    def __post_init__(self):
        # Frozen object plus immutable baseline; host owns this provenance.
        from types import MappingProxyType
        object.__setattr__(self, 'baseline_commit', MappingProxyType(dict(self.baseline_commit)))
        object.__setattr__(self, 'split_ids', tuple(self.split_ids))
        object.__setattr__(self, 'split_digests', tuple(self.split_digests))

    def validate(self):
        import re
        baseline = self.baseline_commit
        algorithm = baseline.get('hash_algorithm')
        if set(baseline) != {'hash_algorithm','value'} or algorithm not in ('sha1','sha256') or not re.fullmatch('[0-9a-f]{'+str(40 if algorithm=='sha1' else 64)+'}',baseline['value']):
            raise ValueError('invalid baseline')
        if len(self.split_ids)!=3 or len(set(self.split_ids))!=3 or not all(isinstance(x,str) and x for x in self.split_ids):
            raise ValueError('split IDs overlap')
        if len(self.split_digests)!=3 or len(set(self.split_digests))!=3:
            raise ValueError('split digests overlap')
        if not all(re.fullmatch('sha256:[0-9a-f]{64}', x) for x in (*self.split_digests,self.evaluator_digest)):
            raise ValueError('invalid provenance digest')
        if not self.policy_version or not self.optimizer_identity or not self.evaluator_identity or self.optimizer_identity==self.evaluator_identity:
            raise ValueError('independent evaluator identity required')


class HoldoutExhausted(ValueError):
    pass


class Ledger:
    """Separate durable attempt ledger; reservations are never retried automatically."""
    def __init__(self, path):
        self.path = Path(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts (version TEXT, attempt TEXT, status TEXT, detail TEXT, holdout_digest TEXT, PRIMARY KEY(version,attempt))')
            if 'holdout_digest' not in {row[1] for row in db.execute('PRAGMA table_info(attempts)')}:
                db.execute('ALTER TABLE attempts ADD COLUMN holdout_digest TEXT')
            db.execute('CREATE TABLE IF NOT EXISTS holdout_versions (version TEXT PRIMARY KEY, digest TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def reserve(self, version, attempt, holdout_digest):
        import re
        if not isinstance(attempt, str) or not attempt.strip():
            raise ValueError('nonblank attempt ID required')
        if not isinstance(version, str) or not version.strip() or not isinstance(holdout_digest, str) or not re.fullmatch('sha256:[0-9a-f]{64}', holdout_digest):
            raise ValueError('valid holdout version and digest required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM attempts WHERE holdout_digest IS NULL LIMIT 1').fetchone():
                raise ValueError('legacy unbound ledger requires trusted migration; refusing budget reset')
            binding = db.execute('SELECT digest FROM holdout_versions WHERE version=?',(version,)).fetchone()
            if binding and binding[0] != holdout_digest:
                raise ValueError('holdout version already bound to different content')
            db.execute('INSERT OR IGNORE INTO holdout_versions VALUES (?,?)',(version,holdout_digest))
            if db.execute('SELECT 1 FROM attempts WHERE holdout_digest=? AND attempt=?',(holdout_digest,attempt)).fetchone():
                return False
            if db.execute('SELECT count(*) FROM attempts WHERE holdout_digest=?',(holdout_digest,)).fetchone()[0]>=10:
                raise HoldoutExhausted('holdout content exhausted; rotate/quarantine')
            db.execute('INSERT INTO attempts VALUES (?,?,?,?,?)',(version,attempt,'UNKNOWN','reserved before evaluation',holdout_digest))
        return True

    def finish(self, version, attempt, result):
        with self.connect() as db:
            db.execute('UPDATE attempts SET status=?,detail=? WHERE version=? AND attempt=?',(result['status'],json.dumps(result,sort_keys=True),version,attempt))

    def attempts(self):
        with self.connect() as db:
            return db.execute('SELECT version,attempt,status,detail FROM attempts ORDER BY rowid').fetchall()


def benchmark(rows, candidate):
    before = after = regressions = 0
    for row in rows:
        transformed = candidate.apply(row)
        before += len(row['optional_detail'])
        after += len(transformed['optional_detail'])
        regressions += any(transformed[key] != row[key] for key in ('trace_id','status','checks','bindings'))
    return dict(sample_size=len(rows), before=before, after=after, safety_regressions=regressions)


class TrustedEvaluator:
    """Trusted in-process reference implementation; optimizer interface exposes aggregates only."""
    def __init__(self, identity, holdout):
        self.identity = identity
        self.__holdout = json.loads(json.dumps(holdout))
        self.split_digest = digest(self.__holdout)
        self.code_digest = 'sha256:' + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def evaluate(self, candidate, expected_digest, evaluator_digest, excluded_trace_ids=()):
        if expected_digest != self.split_digest or evaluator_digest != self.code_digest:
            raise ValueError('evaluator/holdout provenance mismatch')
        ids = [row['trace_id'] for row in self.__holdout]
        if len(ids)!=len(set(ids)) or set(ids)&set(excluded_trace_ids):
            raise ValueError('holdout trace IDs overlap')
        return dict(benchmark(self.__holdout,candidate),split_digest=self.split_digest,evaluator_digest=self.code_digest)


def optimize(host, current_baseline, train, evaluation, evaluator, ledger, attempt_id, candidate_spec=None):
    # The caller supplies host-authenticated immutable bindings, never model claims.
    if not isinstance(attempt_id,str) or not attempt_id.strip():
        return {'status':'REJECTED','reason':'nonblank attempt ID required'}
    version = host.split_ids[2]
    try:
        if not ledger.reserve(version,attempt_id,host.split_digests[2]):
            return {'status':'UNKNOWN','reason':'attempt already reserved; no resend'}
    except ValueError as exc:
        return {'status':'HOLD' if isinstance(exc,HoldoutExhausted) else 'REJECTED','reason':str(exc)}
    try:
        host.validate()
        if dict(current_baseline)!=dict(host.baseline_commit):
            raise ValueError('stale baseline')
        if evaluator.identity!=host.evaluator_identity or evaluator.code_digest!=host.evaluator_digest:
            raise ValueError('evaluator identity/digest mismatch')
        if digest(train)!=host.split_digests[0] or digest(evaluation)!=host.split_digests[1]:
            raise ValueError('tampered optimizer splits')
        if not train or not evaluation:
            raise ValueError('empty optimizer splits')
        # Trusted host ensures holdout membership is disjoint; evaluator verifies it below.
        if len({row['trace_id'] for row in train})!=len(train) or len({row['trace_id'] for row in evaluation})!=len(evaluation) or {r['trace_id'] for r in train}&{r['trace_id'] for r in evaluation}:
            raise ValueError('overlapping trace IDs')
        candidates = [Candidate.from_dict(candidate_spec)] if candidate_spec is not None else [Candidate(n) for n in (0,64,128,256)]
        selected = min(candidates,key=lambda c: benchmark(train,c)['after'])
        local = benchmark(evaluation,selected)
        holdout = evaluator.evaluate(selected,host.split_digests[2],host.evaluator_digest,tuple(r['trace_id'] for r in (*train,*evaluation)))
        if holdout['split_digest']!=host.split_digests[2] or holdout['evaluator_digest']!=host.evaluator_digest:
            raise ValueError('tampered evaluation aggregate provenance')
        metrics = [local, holdout]
        if any(type(m[k]) is not int or m[k]<0 for m in metrics for k in ('sample_size','before','after','safety_regressions')):
            raise ValueError('invalid aggregate')
        if any(m['sample_size']==0 for m in metrics):
            result = {'status':'HOLD','reason':'empty benchmark; no fabricated metrics'}
        else:
            regressions=sum(m['safety_regressions'] for m in metrics)
            improved=all(m['before']-m['after']>=max(32,m['before']*.05) for m in metrics)
            status='REJECTED' if regressions else ('PROPOSED' if improved else 'HOLD')
            metric = lambda key: [dict(name=name+'_optional_detail_chars',value=m[key],sample_size=m['sample_size']) for name,m in zip(('eval','holdout'),metrics)]
            proposal=dict(schema_version='3.0.1',proposal_id=attempt_id,source_trace_set_digest=digest(train),baseline_commit=dict(host.baseline_commit),policy_version=host.policy_version,target_component='context.optional_detail',hypothesis='Bound optional detail while preserving mandatory trace fields.',candidate_diff_digest=digest(selected.as_dict()),evaluator_digest=host.evaluator_digest,train_split_digest=host.split_digests[0],eval_split_digest=host.split_digests[1],holdout_split_digest=host.split_digests[2],train_eval_run_id=attempt_id+':eval',holdout_eval_run_id=attempt_id+':holdout',metrics_before=metric('before'),metrics_after=metric('after'),safety_regressions=regressions,status=status,rollback_ref='restore:'+host.baseline_commit['value'])
            from jsonschema import Draft202012Validator
            schema_path = Path(__file__).resolve().parents[2]/'schemas/halo-proposal.schema.json'
            Draft202012Validator(json.loads(schema_path.read_text())).validate(proposal)
            result=dict(status=status,proposal=proposal,candidate=selected.as_dict(),evaluation=dict(local=local,holdout=holdout,benchmark='deterministic optional text character count; not tokens/cost',uncertainty='synthetic deterministic smoke evidence; no statistical safety guarantee'))
    except ValueError as exc:
        result={'status':'REJECTED','reason':str(exc)}
    except Exception as exc:
        result={'status':'HOLD','reason':'evaluator/workflow failure: '+type(exc).__name__}
    ledger.finish(version,attempt_id,result)
    return result


def run_demo(output: Path):
    output.mkdir(parents=True,exist_ok=False)
    rows=lambda prefix: tuple(dict(trace_id=f'{prefix}{i}',status='PASS',checks=['required_gate'],bindings={'policy':'synthetic-v1'},optional_detail='Synthetic optional detail. '*40) for i in range(5))
    train,evaluation,holdout=rows('train'),rows('eval'),rows('holdout')
    evaluator=TrustedEvaluator('trusted-independent-evaluator',holdout)
    import subprocess
    repository = Path(__file__).resolve().parents[2]
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=repository,text=True).strip()
    host=Host({'hash_algorithm':'sha1' if len(head)==40 else 'sha256','value':head},'synthetic-v1',('synthetic-train-v1','synthetic-eval-v1','synthetic-holdout-v1'),(digest(train),digest(evaluation),digest(holdout)),evaluator.code_digest,'optimizer',evaluator.identity)
    result=optimize(host,host.baseline_commit,train,evaluation,evaluator,Ledger(output/'ledger.sqlite'),'synthetic-demo-1')
    (output/'proposal.json').write_text(json.dumps(result.get('proposal',{'status':result['status']}),indent=2)+'\n')
    (output/'evaluation.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
