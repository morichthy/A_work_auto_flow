"""登记本轮实际新增/改名测试；不移除其他范围的测试或放宽验收等级。"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'automation/testing'))
import catalog

allowed = {
    'automation/tests/test_recent_notes_evidence.py',
    'automation/frontend/src/CurrentReading.test.tsx',
    'automation/frontend/src/Evidence.test.tsx',
    'automation/frontend/src/ResearchDocument.test.tsx',
    'automation/frontend/src/ReadingEvidence.test.tsx',
    'automation/frontend/e2e/workbench.spec.ts',
}
data = catalog.load(ROOT)
found = catalog.discover(ROOT)
before = catalog.audit(ROOT, data)
# Removing a renamed test only changes its catalog locator, not a historical result.
removed = [row['id'] for row in data['tests'] if row['id'] in before['missing'] and row['path'] in allowed]
data['tests'] = [row for row in data['tests'] if row['id'] not in removed]
added = []
for identity in before['unclassified']:
    row = found[identity]
    if row['path'] not in allowed:
        continue
    data['tests'].append({**row, 'capability': 'workbench', 'quick': False, 'full': True,
                          'requires': ['frontend-dev'] if row['kind'] != 'python' else [], 'authorization': []})
    added.append(identity)
if added or removed:
    data['revision'] += 1
    (ROOT / catalog.CATALOG).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
result = {'added': added, 'removed': removed, 'audit': catalog.audit(ROOT, data)}
print(json.dumps(result, ensure_ascii=False, indent=2))
if result['audit']['status'] != 'passed':
    raise SystemExit(1)
