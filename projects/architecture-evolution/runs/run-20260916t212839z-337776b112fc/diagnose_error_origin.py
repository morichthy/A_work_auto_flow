"""只读强交接诊断；不抑制错误、不改变校验或保存逻辑。"""
import json
from pathlib import Path
import sys
import traceback

ROOT = Path.cwd().resolve()
sys.path.insert(0, str(ROOT / 'automation/scripts'))
from memory.errors import MemoryError
from material_query.coordinator import Coordinator
from material_query.api import dispatch
import memory.store

original = MemoryError.__init__
def traced(self, *args, **kwargs):
    original(self, *args, **kwargs)
    print(json.dumps({'memory_error': self.as_dict()}, ensure_ascii=False), file=sys.stderr)
    traceback.print_stack(file=sys.stderr)
MemoryError.__init__ = traced

print(json.dumps({'root':str(ROOT), 'python':sys.executable,
                  'store_module':memory.store.__file__, 'sys_path':sys.path}, ensure_ascii=False))
app = Coordinator(ROOT)
try:
    result = dispatch(app, 'reading-handoff', {'session_id':'RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3b'})
    print(json.dumps({key:value for key,value in result.items() if key != 'value'}, ensure_ascii=False))
finally:
    app.close()
