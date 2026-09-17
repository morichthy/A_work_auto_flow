import zipfile,json,hashlib,difflib
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[3];O=R/'.run-captures/budget-trace';old=ROOT/'projects/architecture-evolution/runs/run-20260916t085438z-3e40d5ed8471/verification/framework-source-snapshot.zip'
items=['automation/scripts/material_query/'+n+'.py' for n in ['assembly','query_plan','coordinator','budget','reading']]+['automation/scripts/workspace_settings.py'];rows=[]
with zipfile.ZipFile(old) as z:
 for item in items:
  before=z.read(item);after=(ROOT/item).read_bytes();rows.append({'path':item,'old_sha256':hashlib.sha256(before).hexdigest(),'current_sha256':hashlib.sha256(after).hexdigest(),'identical':before==after})
  if before!=after:(O/(Path(item).stem+'-vs-baseline.diff')).write_text(''.join(difflib.unified_diff(before.decode('utf-8-sig').splitlines(True),after.decode('utf-8-sig').splitlines(True),fromfile='baseline/'+item,tofile='current/'+item)),encoding='utf-8')
(O/'baseline-code-comparison.json').write_text(json.dumps({'baseline_snapshot':old.relative_to(ROOT).as_posix(),'baseline_snapshot_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'files':rows},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(rows))
