"""只校验本次固定产物及时间和；物理脚本入口避免PowerShell管道丢失stdin。"""
import csv
import hashlib
import json
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[5]
slugs=['run-20260916t085438z-3e40d5ed8471','run-20260916t091635z-effbef761124','run-20260916t092432z-6976e1302de8']
results=[]
for slug in slugs:
    run=root/'projects/architecture-evolution/runs'/slug
    inventory=json.loads((run/'verification/freeze-evidence-manifest.json').read_text(encoding='utf-8'))
    entries={**inventory['inputs'],**inventory['artifacts']}
    bad=[name for name,sha in entries.items() if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha]
    assert not bad,bad
    meta=json.loads((run/'run.json').read_text(encoding='utf-8'))
    results.append({'run_id':meta['run_id'],'status':meta['status'],'checked_files':len(entries),'run_sha256':hashlib.sha256((run/'run.json').read_bytes()).hexdigest()})
first=root/'projects/architecture-evolution/runs'/slugs[0]/'verification'
manifest=json.loads((first/'source-manifest.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(first/'framework-source-snapshot.zip') as archive:
    assert set(archive.namelist())==set(manifest['files'])
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==sha for name,sha in manifest['files'].items())
last=root/'projects/architecture-evolution/runs'/slugs[-1]
with (last/'verification/stage-timeline.csv').open(encoding='utf-8',newline='') as stream:
    rows=list(csv.DictReader(stream))
assert abs(sum(float(r['wall_seconds']) for r in rows[:-1])-float(rows[-1]['wall_seconds']))<1e-6
out={'status':'passed','runs':results,'source_files':len(manifest['files']),'stage_total_s':float(rows[-1]['wall_seconds']),'scope':'固定产物与源码ZIP哈希、连续时间分解合计；不代表业务科学复核。'}
(last/'.run-captures/freeze-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False))
