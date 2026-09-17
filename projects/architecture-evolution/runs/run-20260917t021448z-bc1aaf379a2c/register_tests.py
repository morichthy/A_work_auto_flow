"""只登记本轮明确拥有路径的新测试；未知或退出测试须另外审查。"""
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'automation'))
from testing.catalog import audit, discover, load

data = load(ROOT)
before = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
found = discover(ROOT)
known = {row['id'] for row in data['tests']}
paths = {
    'automation/tests/test_evidence_content.py', 'automation/tests/test_note_knowledge_body.py',
    'automation/frontend/src/Evidence.test.tsx', 'automation/frontend/src/MemoryNavigation.test.tsx',
    'automation/frontend/src/ReadingEvidence.test.tsx', 'automation/frontend/src/CurrentReading.test.tsx',
    'automation/frontend/e2e/workbench.spec.ts',
}
added = []
for key, row in found.items():
    if key in known or row['path'] not in paths:
        continue
    baseline = any(name in key for name in (
        'test_registered_raster_requires_hash_and_current_permission',
        'test_registered_tool_identity_uses_registry_member',
        'test_owner_body_excludes_planning_but_keeps_knowledge_and_gaps'))
    item = dict(row, capability='workbench', quick=baseline, full=True,
                requires=[] if row['kind']=='python' else ['frontend-dev'], authorization=[])
    if baseline:
        item['baseline'] = dict(risk='图片访问或身份解析越界、知识正文混入任务编排',
            reason='保护本轮真实故障及固定来源权限边界',
            review_triggers=['证据适配器或阅读正文契约变化'],
            reviewed_at='2026-09-17', reviewed_by='Codex',
            review_basis='RUN-20260917T021448Z-BC1AAF379A2C')
    data['tests'].append(item)
    added.append(key)
if added:
    old_revision = data['revision']
    data['revision'] += 1
    data['history'].append(dict(at=datetime.now(timezone.utc).isoformat(), actor='Codex',
        before_revision=old_revision, after_revision=data['revision'],
        reason='知识笔记与分类型证据详情回归；权限、合法工具身份、正文边界加入基线，其余按影响执行',
        added=added))
    backup = Path(__file__).with_name('catalog-before.json')
    if not backup.exists(): backup.write_text(before, encoding='utf-8')
    (ROOT/'automation/testing/catalog.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(audit(ROOT,data),ensure_ascii=False,indent=2))
