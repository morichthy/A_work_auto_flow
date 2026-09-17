"""Run-only observer. No budget/policy changes; only SERVER_LIMITS request override."""
import sys,json,time,uuid,hashlib,csv
from pathlib import Path
from dataclasses import asdict,is_dataclass
RUN=Path(__file__).resolve().parents[1]; ROOT=RUN.parents[3]
OUT=RUN/'.run-captures'/'budget-trace'
OLD=ROOT/'projects/architecture-evolution/runs/run-20260916t085438z-3e40d5ed8471/.run-captures/latency'
sys.path.insert(0,str(ROOT/'automation/scripts'))
from material_query.api import dispatch
from material_query.coordinator import Coordinator
from material_query.budget import Ledger,SERVER_LIMITS
from material_query.assembly import Assembler
from material_query.reading import Reading
from material_query import query_plan
EVENTS=[]
def write(name,value): (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def hashed(text): return {'chars':len(text),'sha256':hashlib.sha256(text.encode()).hexdigest()}
def basic(value): return asdict(value) if is_dataclass(value) else value
def cand(value):
    return {'title':value.get('title'),'refs':value.get('refs'),'excerpt':hashed(value.get('excerpt','')),'hits':[{'matched_text':hashed(h.get('matched_text') or ''),'representation_refs':h.get('representation_refs'),'query_source':h.get('query_source')} for h in value.get('hits',[])]}
def stack():
    output=[]; f=sys._getframe(2)
    while f and len(output)<12:
        if 'material_query' in f.f_code.co_filename:
            d=f.f_locals; r={'file':Path(f.f_code.co_filename).name,'function':f.f_code.co_name,'line':f.f_lineno}
            for k in ('lane','route','group','title','selector','definition','ref','child_def'):
                if k in d:r[k]=basic(d[k])
            if isinstance(d.get('candidate'),dict):r['candidate']=cand(d['candidate'])
            if 'visible' in d:r['visible']=[cand(c) for c in d['visible']]
            if isinstance(d.get('text'),str):r['text']=hashed(d['text'])
            output.append(r)
        f=f.f_back
    return output
def event(kind,**v): EVENTS.append({'seq':len(EVENTS)+1,'kind':kind,'time_ns':time.time_ns(),**v})
orig_charge=Ledger.charge
def charge(self,key,amount,**kwargs):
    r={'key':key,'requested':amount,'used_before':self.used[key],'held_before':self.held[key],'limit':self.limits[key],'remaining_before':self.remaining(key),'stack':stack()}
    try:
        result=orig_charge(self,key,amount,**kwargs);r['success']=True;return result
    except Exception as e:r.update(success=False,error=str(e),code=getattr(e,'code',None));raise
    finally:r.update(used_after=self.used[key],held_after=self.held[key]);event('charge',**r)
Ledger.charge=charge
orig_add=Assembler.add
def add(self,group,title,text,selector,ref,**kwargs):
    before=len(self.parts);used=self.ledger.used['output_chars']
    try:return orig_add(self,group,title,text,selector,ref,**kwargs)
    finally:event('part',group=group,title=title,text=hashed(text),selector=selector,ref=basic(ref),parts_added=len(self.parts)-before,charged=self.ledger.used['output_chars']-used,stack=stack())
Assembler.add=add
orig_gap=Assembler.gap
def gap(self,message,**kwargs):
    event('gap',message=message,details={k:basic(v) for k,v in kwargs.items()},remaining=self.ledger.remaining('output_chars'),stack=stack());return orig_gap(self,message,**kwargs)
Assembler.gap=gap
orig_diag=query_plan.charge_diagnostics
def diagnostics(ledger,value):
    event('diagnostics',json_chars=len(json.dumps(value,ensure_ascii=False)),keys=list(value) if isinstance(value,dict) else None,hits=len(value.get('hits',[])) if isinstance(value,dict) else 0,matched_text_chars=sum(len(h.get('matched_text') or '') for h in value.get('hits',[])) if isinstance(value,dict) else 0,stack=stack());return orig_diag(ledger,value)
query_plan.charge_diagnostics=diagnostics
orig_packet=Reading.candidate_packet
def packet(self,c,l,s):
    before=self.ledger.used['output_chars'];t=time.perf_counter()
    try:
        v=orig_packet(self,c,l,s)
        event('candidate_packet',lane=l,candidate=cand(c),definition=basic(v['definition']),charged=self.ledger.used['output_chars']-before,elapsed_s=time.perf_counter()-t,complete=v['complete'],model_text=hashed(v['text']),image_chars=sum(len(f.get('data_url','')) for p in v['packet']['parts'] for f in p.get('figures',[])))
        return v
    except Exception as e:event('candidate_packet_error',lane=l,candidate=cand(c),error=str(e));raise
Reading.candidate_packet=packet

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    source={}
    for p in (ROOT/'automation/scripts').rglob('*.py'):
        data=p.read_bytes();source[p.relative_to(ROOT).as_posix()]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    write('source-manifest.json',source)
    start=json.loads((OLD/'1789549676960911300-main-reading-start-request.json').read_text(encoding='utf-8'))
    recall=json.loads((OLD/'1789549992460223400-reader-reading-recall-request.json').read_text(encoding='utf-8'))
    start['session_id']='RS-'+str(uuid.uuid4());start['query']['budget']=asdict(SERVER_LIMITS)
    start['query']['result_limit']=10;start['reranking']={'mode':'auto','candidate_limit':30,'conditions':[]}
    recall.update(session_id=start['session_id'],expected_revision=1,request_id=str(uuid.uuid4()))
    access=start['query']['scope_ceiling']['owner_ids'];results=[]
    for action,request in [('reading-template',{}),('reading-start',start),('reading-recall',recall)]:
        write(action+'-request.json',request);print(action+' begin',flush=True);t=time.perf_counter();app=Coordinator(ROOT,access_owner_ids=access)
        try:response=dispatch(app,action,request)
        finally:app.close()
        write(action+'-response.json',response)
        row={'action':action,'elapsed_s':time.perf_counter()-t,'status':response.get('status'),'code':response.get('code'),'consumed':response.get('consumed'),'session_id':start['session_id']}
        results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True);write('events.json',EVENTS);write('calls.json',results)
        if response.get('status') not in ('ok','partial'):break
    charges=[e for e in EVENTS if e['kind']=='charge']
    with (OUT/'charges.csv').open('w',encoding='utf-8-sig',newline='') as f:
        keys=['seq','key','requested','used_before','used_after','held_before','remaining_before','limit','success','site'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for e in charges:w.writerow({**{k:e.get(k) for k in keys[:-1]},'site':' > '.join(r['file']+':'+str(r['line'])+':'+r['function'] for r in e['stack'])})
    write('summary.json',{'calls':results,'event_count':len(EVENTS),'failed_charges':[e for e in charges if not e['success']],'successful_output_chars':sum(e['requested'] for e in charges if e['success'] and e['key']=='output_chars')})
if __name__=='__main__':main()
