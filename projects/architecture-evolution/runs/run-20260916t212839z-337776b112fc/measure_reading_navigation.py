"""只读接口性能对照；快照写入仅为派生展示，绝不修改规范业务材料。"""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'automation/scripts'))
from material_query.coordinator import Coordinator
from material_query.api import dispatch
from material_query.reading_notes import recent, snapshot
from material_query.evidence_navigation import search, detail

SID = 'RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3b'
app = Coordinator(ROOT)
service = SimpleNamespace(root=ROOT, materials=app)
rows = []


def measure(label, operation):
    start = time.perf_counter()
    try:
        result = operation()
        value = result.get('value') if 'status' in result else result
        summary = {'status': result.get('status', 'ok'), 'code': result.get('code')}
        if isinstance(value, dict):
            summary.update({key:value[key] for key in ('revision','notes_count','omitted_note_count','total','verification') if key in value})
            summary['markdown_chars'] = len(value.get('context_markdown', value.get('content_markdown','')))
            summary['item_count'] = len(value.get('items', []))
    except Exception as exc:
        summary = {'status':'exception', 'type':type(exc).__name__, 'message':str(exc)}
    rows.append({'operation':label, 'elapsed_seconds':round(time.perf_counter()-start, 6), **summary})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)


try:
    measure('old_reading_list', lambda:dispatch(app, 'reading-list', {'limit':20}))
    measure('old_reading_view_selected', lambda:dispatch(app, 'reading-view', {'session_id':SID,'notes_only':True}))
    measure('new_recent_first_call', lambda:recent(service, {'limit':20}))
    measure('new_snapshot_selected', lambda:snapshot(service, {'session_id':SID}))
    measure('new_recent_warm', lambda:recent(service, {'limit':20}))
    measure('new_snapshot_warm', lambda:snapshot(service, {'session_id':SID}))
    measure('evidence_native_run_search', lambda:search(service, {'query':'RUN-20260916T212839Z-337776B112FC'}))
    measure('evidence_native_run_detail', lambda:detail(service, {'id':'RUN-20260916T212839Z-337776B112FC'}))
finally:
    app.close()
