"""只读诊断：保留原校验和返回，仅记录首个完整性异常的位置。"""
import json
from pathlib import Path
import sys
import traceback
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'automation/scripts'))
from memory.store import MemoryStore as Store
from material_query.coordinator import Coordinator
from material_query.api import dispatch

original = Store._record
def inspected(self, *args, **kwargs):
    try:
        return original(self, *args, **kwargs)
    except Exception as exc:
        print(json.dumps({'root':str(ROOT), 'python':sys.executable, 'record':args[1] if len(args)>1 else None,
                          'exception':repr(exc), 'details':getattr(exc, 'details', None)}, ensure_ascii=False))
        traceback.print_exc()
        raise
Store._record = inspected
app = Coordinator(ROOT)
try:
    result = dispatch(app, 'reading-handoff', {'session_id':'RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3b'})
    print(json.dumps({key:value for key,value in result.items() if key!='value'}, ensure_ascii=False))
finally:
    app.close()
