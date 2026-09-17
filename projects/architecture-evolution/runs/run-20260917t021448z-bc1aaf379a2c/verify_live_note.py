"""回读真实旧 RS 的派生展示；不修改阅读历史或科学正文。"""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'automation/scripts'))
from workbench_app.web import post

sid = 'RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3b'
head = ROOT / '.local/reading-sessions' / sid / 'HEAD.json'
before = hashlib.sha256(head.read_bytes()).hexdigest()
service = SimpleNamespace(root=ROOT, materials=SimpleNamespace(access_owner_ids=None))
value = post(service, 'reading-notes/snapshot', {'session_id': sid})
body = value['context_markdown']
checks = {
    'head_unchanged': before == hashlib.sha256(head.read_bytes()).hexdigest(),
    'no_orchestration': all(text not in body for text in ('# 当前问题', '由主任务读取 handoff', '结果/缺口：', '### 问题')),
    'material_suggestions': '### 可选的下一步建议' in body,
    'formula_preserved': '$' in body,
    'fixed_links_preserved': '#/evidence?' in body,
}
print(json.dumps({'session_id':sid, 'revision':value['revision'], 'checks':checks,
                  'body_chars':len(body), 'references':len(value['references']),
                  'verification':value['verification'], 'gaps':value['gaps']}, ensure_ascii=False, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
