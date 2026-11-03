from pathlib import Path
import json,hashlib
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'MANIFEST.sha256.json').read_text())
for rel,expected in manifest.items():
    p=root/rel
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
        raise SystemExit('FAIL: '+rel)
print(f'PASS: {len(manifest)} exported files match manifest. Added files are not covered.')
