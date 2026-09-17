from pathlib import Path
import sys,json
b=Path(__file__).resolve().parent;sys.path.insert(0,str(b.parents[1]/'automation/scripts'))
from memory.service import MemoryService
from memory import api
s=json.loads((b/'state.json').read_text(encoding='utf-8'));svc=MemoryService(s['root'])
snapshot=svc.inspect('RES-R');d=s['final_document'];live=svc.inspect('RES-R',record_id=d['record_id'])['record']
view=api.dispatch(svc,'document',{'owner_id':'RES-R','document_id':d['record_id'],'revision':d['revision']})
old=json.loads((b/'after-document.json').read_text(encoding='utf-8'))
assert snapshot['head']==s['final_head'] and live==d and view['report']==old['report']
r={'head':snapshot['head'],'document':{'record_id':live['record_id'],'revision':live['revision'],'record_hash':live['record_hash']},'complete':view['report']['complete'],'report_coverage':view['report_coverage'],'report_version_hints':view['report_version_hints'],'index_status':snapshot['index_status'],'full_report_unchanged':True}
(b/'final-readonly-recheck.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=False))
