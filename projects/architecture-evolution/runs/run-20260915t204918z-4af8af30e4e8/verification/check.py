"""Reproducible synthetic public-API scenario; never accesses business owners."""
from pathlib import Path
import sys,json,uuid,copy
BASE=Path(__file__).resolve().parent
REPO=BASE.parents[1]
sys.path[:0]=[str(REPO/'automation/tests'),str(REPO/'automation/scripts')]
from memory import api,contracts,documents
from memory.service import MemoryService
from test_memory_documents_v3 import unit_payload,section_payload,document_payload
phase=sys.argv[1]
state_path=BASE/'state.json'
def dump(name,obj):
 (BASE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
if phase=='seed':
 root=BASE/('synthetic-'+uuid.uuid4().hex[:8]); (root/'research/topic').mkdir(parents=True)
 (root/'research/topic/research.json').write_text(json.dumps({'research_id':'RES-R','title':'SYNTHETIC ONLY','status':'active','claims':[],'dependencies':[]}),encoding='utf-8')
 state={'root':str(root)}
else: state=json.loads(state_path.read_text(encoding='utf-8'));root=Path(state['root'])
service=MemoryService(root)
def save(kind,payload,old=None,**extra):
 # Fresh HEAD and full draft keep the public compare-and-swap contract explicit.
 draft={k:copy.deepcopy(old[k]) for k in (*contracts.CONTENT_FIELDS,'schema_version','record_reason')} if old else dict(schema_version=3,owner_id='RES-R',kind=kind,title='合成 '+kind,body_markdown='',keywords=[],sources=[],provenance_gap='合成接口验证，无现实实验',record_reason='合成完整成果同步验证',discovery='owner_only',sensitivity='internal')
 draft.update(payload=payload,**extra)
 op={'op':'put_record','draft':draft}
 if old: op.update(record_id=old['record_id'],expected_revision=old['revision'])
 else: op['client_key']=uuid.uuid4().hex
 head=service.inspect('RES-R')['head']
 request=dict(schema_version=1,request_id=str(uuid.uuid4()),actor={'kind':'ai','id':'consolidate-results-synthetic-check'},owner_id='RES-R',expected_head=head['commit_id'] if head else None,operations=[op])
 validation=service.validate_draft(request);receipt=service.commit(request)
 log=BASE/'requests.jsonl'
 with log.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(request=request,validation=validation,receipt=receipt),ensure_ascii=False)+'\n')
 result=receipt['record_results'][0]
 return service.inspect('RES-R',record_id=result['record_id'],revision=result['revision'])['record']
def view(name,doc):
 obj=api.dispatch(service,'document',dict(owner_id='RES-R',document_id=doc['record_id'],revision=doc['revision']));dump(name,obj);return obj
if phase=='seed':
 u=save('detail',unit_payload())
 s=save('document_section',section_payload(documents.fixed_ref(u)))
 d=save('document',document_payload([documents.fixed_ref(s)]))
 ov=dict(question='摄氏温度如何转为开尔文',claims=[],methods=['线性平移'],results=['T=t+273.15'],current_stage='只定义合成换算',limitations=['未验证传感器误差'],open_questions=['输入边界待整理'],process_refs=[],technical_refs=[documents.fixed_ref(u)],experience_refs=[])
 o=save('overview',ov,schema_version=4,body_markdown='合成摄氏转开尔文换算。输入边界待整理。')
 state.update(unit=u,section=s,document=d,overview=o,baseline_head=service.inspect('RES-R')['head'])
 view('before-document.json',d);dump('before-overview.json',o)
 p=copy.deepcopy(u['payload']);p['blocks'][0]['markdown']='定义：t 为摄氏温度（°C），T 为热力学温度（K）；合成输入限定 t >= -273.15 °C。'
 newer=save('detail',p,u,change_reason='补齐变量单位和绝对零度边界')
 p=unit_payload();p['retrieval_description']['question']='换算后负开尔文的反例';p['blocks']=[dict(block_id='counterexample',role='results',markdown='边界反例：t=-300 °C 代入得到 T=-26.85 K。该输入超出既定适用域，必须拒绝；这不代表现实传感器已验证。',requires_block_ids=[])]
 new=save('detail',p,title='合成边界反例')
 state.update(newer=newer,new=new)
 dump('before-impact.json',api.dispatch(service,'document-impact',dict(owner_id='RES-R',document_id=d['record_id'])))
 dump('current-inventory.json',service.inspect('RES-R'))
 dump('outline.json',api.dispatch(service,'outline',dict(owner_id='RES-R',document_id=d['record_id'])))
 dump('state.json',state)
 print(str(BASE))
else:
 u,s,d,o,newer,new=[state[k] for k in ('unit','section','document','overview','newer','new')]
 p=section_payload(documents.fixed_ref(newer));p['blocks'][0]['markdown']='本章将摄氏温度转换为开尔文，仅在 t >= -273.15 °C 的合成适用域内使用；后附反例说明拒绝域外输入的原因。'
 p['blocks'].append({'type':'unit','ref':documents.fixed_ref(new)})
 ns=save('document_section',p,s,change_reason='更新定义并纳入之前未编排的边界反例')
 p=copy.deepcopy(o['payload']);p.update(current_stage='合成定义与反例已编排，现实测量待验证',limitations=['只验证合成软件流程','未验证传感器误差','t < -273.15 °C 必须拒绝'],open_questions=['现实传感器误差尚未验证'],technical_refs=[documents.fixed_ref(newer),documents.fixed_ref(new)])
 no=save('overview',p,o,body_markdown='摄氏转开尔文公式 T=t+273.15；仅适用于 t >= -273.15 °C。域外反例已纳入全文，现实传感器误差仍待验证。',change_reason='同步适用域、反例和未决问题')
 p=copy.deepcopy(d['payload']);p['section_refs']=[documents.fixed_ref(ns)]
 nd=save('document',p,d,change_reason='固定已同步章节')
 final=view('after-document.json',nd);old=view('old-document-reread.json',d)
 assert old['report']['sections']==json.loads((BASE/'before-document.json').read_text(encoding='utf-8'))['report']['sections']
 assert service.inspect('RES-R',record_id=u['record_id'],revision=1)['record']==u
 before=service.inspect('RES-R')['head'];unchanged=save('detail',copy.deepcopy(newer['payload']),newer)
 assert unchanged['revision']==newer['revision'] and service.inspect('RES-R')['head']==before
 impact=api.dispatch(service,'document-impact',dict(owner_id='RES-R',document_id=nd['record_id']))
 dump('after-impact.json',impact);dump('after-overview.json',no);dump('final-inventory.json',service.inspect('RES-R'))
 state.update(final_document=nd,final_section=ns,final_overview=no,final_head=service.inspect('RES-R')['head'],old_document_preserved=True,unchanged_revision_preserved=True)
 dump('state.json',state)
 print(json.dumps({'report_complete':final['report']['complete'],'impact':impact},ensure_ascii=False))
