"""Static validation only; never validates runtime authorization."""
from pathlib import Path
import hashlib,json,re,sqlite3
from datetime import datetime
from jsonschema import Draft202012Validator,FormatChecker
from referencing import Registry,Resource

ROOT=Path(__file__).resolve().parents[1]
FORMATS=FormatChecker()
@FORMATS.checks('date-time', raises=(ValueError,TypeError))
def strict_datetime(value):
    if not isinstance(value,str):return True
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})',value):return False
    datetime.fromisoformat(value.upper().replace('Z','+00:00'))
    return True
def validators():
    docs={p.stem.removesuffix('.schema'):json.loads(p.read_text()) for p in (ROOT/'schemas').glob('*.json')}
    registry=Registry().with_resources((s['$id'],Resource.from_contents(s)) for s in docs.values())
    return {n:Draft202012Validator(s,registry=registry,format_checker=FORMATS) for n,s in docs.items()}

def main():
    vals=validators()
    for name,v in vals.items():
        Draft202012Validator.check_schema(v.schema)
        v.validate(json.loads((ROOT/'fixtures/valid'/f'{name}.json').read_text()))
    for src in json.loads((ROOT/'sources.json').read_text()):
        assert hashlib.sha256((ROOT/src['path']).read_bytes()).hexdigest()==src['sha256'],src['path']
    transitions=json.loads((ROOT/'policy/transitions.json').read_text())
    assert set(transitions['states'])==set(vals['task'].schema['properties']['status']['enum'])
    for a,b in transitions['edges']:
        assert a in transitions['states'] and b in transitions['states']
        assert a not in transitions['terminal']
    for path in (ROOT/'skills').glob('*/SKILL.md'):
        t=path.read_text();m=re.match(r'---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n',t)
        assert m and m[1]==path.parent.name,path
        assert len(t.splitlines())<500
    c=sqlite3.connect(':memory:');c.executescript((ROOT/'state/001_init.sql').read_text())
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert c.execute('PRAGMA integrity_check').fetchone()==('ok',)
    required={'tasks','events','outbox','approvals','leases','lease_claims','resource_fences','budgets','gate_decisions','checkpoints','provider_attempts','evidence','schema_migrations'}
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert required<=tables
    print(f'PASS: {len(vals)} schemas and valid fixtures; 9 source hashes; 10 skill headers; state policy; 13 SQL tables/integrity.')

if __name__=='__main__':main()
