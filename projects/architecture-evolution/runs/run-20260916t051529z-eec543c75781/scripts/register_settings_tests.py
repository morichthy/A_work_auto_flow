"""显式登记本次新增测试，并保留前后catalog；不执行测试或伪造通过。"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'automation/testing'))
import runner
import catalog

receipts = []
for module, capability, requirements in [
    ('test_workspace_settings', 'workbench', []),
    ('test_workspace_settings_integration', 'workbench', []),
    ('src/WorkspaceSettings.test.tsx', 'workbench', ['frontend-dev']),
    ('src/MaterialQuery.test.tsx', 'retrieval', ['frontend-dev']),
    ('e2e/settings.spec.ts', 'workbench', ['frontend-dev', 'windows']),
]:
    # 允许脚本在中断后恢复：只有仍未登记的方法才再次执行公开register。
    current = catalog.load(ROOT)
    known = {row['id'] for row in current['tests']}
    pending = [row for row in catalog.discover(ROOT).values() if row['id'] not in known and
               (row['selector'].startswith(module + '.') or row['path'].removeprefix('automation/frontend/') == module)]
    if not pending:
        continue
    args = ['register', '--module', module, '--capability', capability, '--reason',
            '工作区设置：默认值、CAS、缓存失效、旧RS和UI草稿/保存行为']
    for value in requirements:
        args.extend(['--requires', value])
    value, code = runner.execute(ROOT, args)
    receipts.append(value)
    if code:
        raise RuntimeError(value)

current = catalog.load(ROOT)
selected = {
    'python:test_workspace_settings.WorkspaceSettingsTests.test_update_is_complete_cas_and_persists_only_authoritative_shape',
    'python:test_workspace_settings_integration.SettingsIntegrationTests.test_capabilities_and_new_template_consume_settings_but_saved_rs_is_fixed',
}
changes = []
for row in current['tests']:
    if row['id'] in selected and not row.get('quick'):
        changes.append({'id': row['id'], 'before_quick': False, 'after_quick': True})
        row.update(quick=True, baseline={
            'risk': '设置覆盖并发修改或放宽旧会话已经固定的费用上限。',
            'reason': '新权威状态及跨入口默认值需要独立防线，两项空工作区测试成本低且不重复模型回归。',
            'review_triggers': ['设置契约/保存', '默认值消费', 'RS预算恢复'],
            'reviewed_at': datetime.now(timezone.utc).isoformat(), 'reviewed_by': 'Codex',
            'review_basis': '本Run核心与集成测试通过；其余缓存/UI边界按影响执行，升级沿已有真实setup基线。'})
if changes:
    backup = ROOT / '.local/testing/catalog-history' / f"revision-{current['revision']}-{uuid.uuid4().hex}.json"
    backup.write_text(json.dumps(catalog.load(ROOT), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    current['revision'] += 1
    current.setdefault('history', []).append({'at': datetime.now(timezone.utc).isoformat(),
        'actor': 'Codex', 'reason': '新增设置CAS及旧RS预算基线，其他新用例按影响执行', 'changes': changes})
    (ROOT / catalog.CATALOG).write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
result = {'registrations': receipts, 'baseline_changes': changes, 'audit': catalog.audit(ROOT)}
(RUN / 'verification/test-catalog.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result['audit'], ensure_ascii=False, indent=2))
