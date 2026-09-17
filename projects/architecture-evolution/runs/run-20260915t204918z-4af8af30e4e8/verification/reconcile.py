"""Public reconciliation attempt; no backend mocks or changes to settings."""
from pathlib import Path
import sys,json
base=Path(__file__).resolve().parent
sys.path.insert(0,str(base.parents[1]/'automation/scripts'))
from memory.service import MemoryService
from memory import api
state=json.loads((base/'state.json').read_text(encoding='utf-8'))
result=api.dispatch(MemoryService(state['root']),'reconcile',{'owner_id':'RES-R'})
(base/'reconcile.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
