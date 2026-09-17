"""Register this bounded change and retain a byte-for-byte pre-review snapshot."""
from pathlib import Path
from datetime import datetime, timezone
import json

root = Path(__file__).resolve().parents[2]
catalog = root / 'automation/testing/catalog.json'
raw = catalog.read_bytes()
(Path(__file__).parent / 'catalog-before.json').write_bytes(raw)
data = json.loads(raw)
at = datetime.now(timezone.utc).isoformat()
new = [
    ('test_workspace_settings', 'WorkspaceSettingsTests', 'test_legacy_disk_adds_only_new_default_without_changing_bytes_or_revision', 'workbench', True),
    ('test_workspace_settings', 'WorkspaceSettingsTests', 'test_requirements_text_bounds_preservation_and_incomplete_write_rejection', 'workbench', True),
    ('test_reading_delegation', 'ReadingDelegationTests', 'test_custom_model_requirements_reach_host_and_worker_without_overriding_route_or_scope', 'retrieval', False),
]
added = []
for module, cls, method, capability, quick in new:
    selector = f'{module}.{cls}.{method}'
    entry = dict(id='python:' + selector, kind='python', selector=selector,
                 path=f'automation/tests/{module}.py', capability=capability,
                 quick=quick, full=True, requires=[], authorization=[])
    if quick:
        entry['baseline'] = dict(
            risk='旧配置被读取时改写，或旧客户端漏字段写入导致用户模型偏好丢失。',
            reason='原CAS基线不覆盖schema-1补字段与偏好遗漏；两项空目录测试共同保护无损升级及完整写入，成本低且无模型依赖。',
            review_triggers=['设置schema兼容', '完整快照写入', '能力文本校验'],
            reviewed_at=at, reviewed_by='Codex',
            review_basis='.local/capability-settings-tests/backend-settings.log：15项通过；覆盖原字节/hash保持、未知及额外缺字段拒绝、已保存偏好不被漏字段覆盖。')
    added.append(entry)
selector = 'validates requirements and preserves exact text while collaboration is off'
added.append(dict(id='component:src/WorkspaceSettings.test.tsx::' + selector,
    kind='component', selector=selector, path='automation/frontend/src/WorkspaceSettings.test.tsx',
    capability='workbench', quick=False, full=True, requires=['frontend-dev'], authorization=[]))
existing = {item['id'] for item in data['tests']}
assert not any(item['id'] in existing for item in added)
data['tests'].extend(added)
before_revision = data['revision']
data['revision'] += 1
data['history'].append(dict(at=at, actor='Codex',
    reason='登记能力偏好4项新增测试；旧配置无损读取与完整写入防丢偏好加入固定基线。组件与委派文本贯通按影响执行，既有RS权限/预算、CAS及真实setup防线继续保留。',
    added=[item['id'] for item in added],
    changes=[dict(id=item['id'], before_quick=None, after_quick=item['quick']) for item in added],
    before_revision=before_revision, after_revision=data['revision'],
    baseline_review=dict(retained='既有设置CAS、旧RS预算及委派撤权/预算/固定引用基线仍保护原风险，无退出或替代。',
        impact_only='UI文本交互及委派模型选择偏好属应用合同；相关组件10项和委派10项已执行，不增加固定防线的fixture成本；权限与预算由既有独立基线覆盖。'),
    evidence=['.local/capability-settings-tests/backend-settings.log',
              '.local/capability-settings-tests/backend-delegation.log',
              '.local/capability-settings-tests/component.log'],
    previous_catalog='.local/capability-settings-tests/catalog-before.json'))
catalog.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(revision=data['revision'], added=[item['id'] for item in added]), ensure_ascii=False))
