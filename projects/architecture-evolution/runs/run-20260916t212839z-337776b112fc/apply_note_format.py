"""经公开材料API应用已审查的纯排版请求；不改核验、权限或底层存储。"""
import json
from pathlib import Path
import sys
RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[3]
sys.path.insert(0, str(ROOT/'automation/scripts'))
from material_query.coordinator import Coordinator
from material_query.api import dispatch

request = json.loads((RUN/'note-format-request.json').read_text(encoding='utf-8'))
app = Coordinator(ROOT)
try:
    result = dispatch(app, 'reading-note', request)
    (RUN/'note-format-api-receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
finally:
    app.close()
