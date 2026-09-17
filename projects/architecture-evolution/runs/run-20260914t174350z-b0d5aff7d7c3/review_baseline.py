"""复审受影响的既有基线，保存前版清单；不改变quick成员或伪造测试结果。"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path


run_dir = Path(__file__).resolve().parent
root = run_dir.parents[3]
path = root / 'automation/testing/catalog.json'
before = path.read_bytes()
catalog = json.loads(before)
snapshot = run_dir / ('catalog-before-review-r' + str(catalog['revision']) + '.json')
# 只运行一次；已有快照不能被覆盖，保留可追踪的清单历史。
with snapshot.open('xb') as stream:
    stream.write(before)
changes = []
for item in catalog['tests']:
    affected = item['path'] in {'automation/tests/test_reading_workflow.py',
                               'automation/tests/test_deployment_workbench.py'}
    if not (affected and item.get('quick') and 'baseline' in item):
        continue
    old = deepcopy(item)
    item['baseline'].update(reviewed_at='2026-09-15', reviewed_by='Codex',
        review_basis='RUN-20260914T174350Z-B0D5AFF7D7C3：23项阅读与18项升级检查通过；'
                     '保留原权限/预算/固定阅读断言，升级扩展用户词库保护；新增双语检查按影响执行。')
    changes.append({'before': old, 'after': deepcopy(item)})
catalog['revision'] += 1
catalog['history'].append({'at': datetime.now(timezone.utc).isoformat(), 'actor': 'Codex',
    'reason': '双语查询计划及词库补种影响审查；原基线成员保持，新增8项仅按影响执行',
    'changes': changes, 'evidence': 'RUN-20260914T174350Z-B0D5AFF7D7C3'})
path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'revision': catalog['revision'], 'reviewed': len(changes), 'snapshot': str(snapshot)}, ensure_ascii=False))
