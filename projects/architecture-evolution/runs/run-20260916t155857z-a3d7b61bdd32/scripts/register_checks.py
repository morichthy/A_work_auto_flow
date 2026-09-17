"""登记本次新增回归并保存目录前后快照；静态登记不代替实际执行。

输入为当前测试源码/catalog，输出为更新目录及Run回执；并发变化时拒绝覆盖。
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'automation/testing'))
import catalog

OUT = Path(__file__).resolve().parents[1] / '.run-captures/catalog'
OUT.mkdir(parents=True, exist_ok=True)
target = ROOT / catalog.CATALOG
original = target.read_bytes()
data = json.loads(original)
known = {row['id'] for row in data['tests']}
owned_paths = {
    'automation/frontend/src/CurrentReading.test.tsx',
    'automation/frontend/src/ReadingSessions.test.tsx',
    'automation/frontend/src/MaterialNavigation.test.tsx',
    'automation/frontend/src/MemoryNavigation.test.tsx',
    'automation/frontend/src/ReadingEvidence.test.tsx',
    'automation/tests/test_reading_workflow.py',
    'automation/tests/test_reading_handoff_view.py',
}
extra_ids = {
    'python:test_deployment_workbench.DeploymentWorkbenchTests.test_source_archive_excludes_private_reading_markdown',
    'browser:e2e/workbench.spec.ts::首页自动阅读笔记、定向证据与主题导航真实接口',
}
added = []
for identity, row in catalog.discover(ROOT).items():
    if identity in known or (row['path'] not in owned_paths and identity not in extra_ids):
        continue
    capability = 'upgrade' if 'deployment' in row['path'] else 'retrieval' if row['kind'] == 'python' else 'workbench'
    # 数据权限是长期防线；其他局部 UI 检查按影响运行，避免增加每次quick成本。
    critical = identity.endswith('test_superset_access_keeps_original_ceiling_and_rejects_narrower_host')
    entry = dict(row, capability=capability, quick=critical, full=True,
                 requires=[] if row['kind'] == 'python' else ['frontend-dev'] + (['windows'] if row['kind'] == 'browser' else []),
                 authorization=[])
    if critical:
        entry['baseline'] = {
            'risk': '更广宿主读取时扩大原范围，或较窄宿主读取越权笔记',
            'reason': '修复不可读时同时保护原授权域和范围上限',
            'review_triggers': ['reading授权、scope_ceiling或持久会话变化'],
            'reviewed_at': datetime.now(timezone.utc).isoformat(), 'reviewed_by': 'Codex',
            'review_basis': 'RUN-20260916T155857Z-A3D7B61BDD32 workflow18项回归通过；保留撤权与预算防线',
        }
    data['tests'].append(entry)
    added.append(identity)
if added:
    before = data['revision']
    data['revision'] += 1
    data.setdefault('history', []).append({
        'at': datetime.now(timezone.utc).isoformat(), 'actor': 'Codex',
        'reason': '阅读上下文、首页和主题深链接、固定来源展示与私人副本分发',
        'before_revision': before, 'after_revision': data['revision'], 'added': added,
        'baseline_review': '新增授权超集/原范围防线；现有撤权/预算/升级成员保留；UI与归档按影响执行。',
        'evidence': ['RUN-20260916T155857Z-A3D7B61BDD32'],
    })
    if target.read_bytes() != original:
        raise RuntimeError('catalog已被并发修改，重新运行合并，不覆盖他人结果')
    (OUT / f'before-r{before}.json').write_bytes(original)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / f'after-r{data["revision"]}.json').write_bytes(target.read_bytes())
report = catalog.audit(ROOT, data)
(OUT / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'added': added, 'audit': report}, ensure_ascii=False, indent=2))
sys.exit(0 if report['status'] == 'passed' else 1)
