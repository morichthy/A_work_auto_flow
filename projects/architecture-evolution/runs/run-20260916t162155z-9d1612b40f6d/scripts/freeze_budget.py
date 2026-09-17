"""Freeze this Run once, then register explicit inputs/artifacts through public API."""
import json,hashlib,sys,zipfile,uuid
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[1];ROOT=R.parents[3];P=R/'.run-captures/budget-trace'
sys.path.insert(0,str(ROOT/'automation/scripts'))
import run_capture

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return p.relative_to(ROOT).as_posix()
def write(p,v):
 b=json.dumps(v,ensure_ascii=False,indent=2)+'\n';temp=p.with_name('.pending-'+uuid.uuid4().hex);temp.write_text(b,encoding='utf-8');temp.replace(p)
def files(p):return sorted(x for x in p.rglob('*') if x.is_file() and '__pycache__' not in x.parts and not x.name.startswith('.pending-'))

def main():
 meta=read(R/'run.json')
 if meta['inputs'] or meta['artifacts']:raise RuntimeError('Already registered; refusing overwrite')
 m=read(P/'final-metrics.json');events=read(P/'events.json');source=read(P/'source-manifest.json')
 with zipfile.ZipFile(P/'source-snapshot.zip') as z:
  for name,row in source.items():
   assert hashlib.sha256(z.read(name)).hexdigest()==row['sha256']
   assert sha(ROOT/name)==row['sha256'],name
 charges=[e for e in events if e['kind']=='charge' and e['success'] and e['key']=='output_chars']
 assert sum(e['requested'] for e in charges)==m['output_consumed']==99986
 assert m['part_attempts']==m['part_added_count']+sum(m['part_skip_counts'].values())==33
 assert m['attempted_part_unique_text_chars']==m['successful_part_text_chars']+m['omitted_unique_part_text_chars']==8634
 # Validate every diagnostic matched-text fingerprint was already present in
 # a search result of the same fixed record. This supports the repeated-text claim.
 search=set()
 for e in charges:
  if e['stack'][0]['function']=='_run_search':
   for c in e['stack'][0]['visible']:
    ref=json.dumps(c['refs'][0],sort_keys=True)
    for h in c['hits']:search.add((ref,h['matched_text']['sha256']))
 diag=read(P/'decomposition.json')['diagnostics'];checked=0
 for d in diag:
  c=d.get('candidate')
  if not c or not d['hits']:continue
  ref=json.dumps(c['refs'][0],sort_keys=True)
  for h in c['hits']:
   assert (ref,h['matched_text']['sha256']) in search;checked+=1
 start=read(P/'reading-start-request.json');recall=read(P/'reading-recall-request.json')
 first=min(e['time_ns'] for e in events);last=max(e['time_ns'] for e in events)
 dt=lambda t:datetime.fromtimestamp(t/1e9,timezone.utc).isoformat().replace('+00:00','Z')
 meta.update(status='failed',started_at=dt(first),ended_at=dt(last),question=recall['question'],
  keywords=['recall','budget-accounting','instrumented-replay','floating-point'],
  parameters={'session_id':start['session_id'],'result_limit':10,'reranking':start['reranking'],'budget':start['query']['budget'],'query_variants':recall['query_variants'],'scope':start['query']['scope'],'scope_ceiling':start['query']['scope_ceiling'],'instrumentation':'Run-only wrappers, original accounting/policy executed; no AI reading/note/handoff'},
  metrics={k:v for k,v in m.items() if k not in ['failure','calls','limitations']},
  quality_results=[{'name':'actual_reading_recall','status':'failed','scope':'Actual public API rejected BUDGET; not a successful full reading workflow.'},{'name':'accounting_trace_consistency','status':'passed','scope':'99986 charge sum; 33 part outcomes; 8634 unique text sum; source snapshot fingerprints; '+str(checked)+' fused-hit text fingerprints previously seen in search.'}],
  conclusion='召回10/重排30、100000字符上限仍失败；内部搜索46872与诊断46443主导消耗，正文6555。完整结论见RESULTS.md。',limitations=m['limitations'],parent_run_ids=['RUN-20260916T085438Z-3E40D5ED8471'])
 write(R/'run.json',meta)
 inputs=[p for p in files(R/'scripts')]+[P/'source-manifest.json',P/'source-snapshot.zip']
 artifacts=[p for p in files(P) if p not in inputs]+files(R/'.run-captures/memory-baseline')+[R/'RESULTS.md']
 manifest={'run_id':meta['run_id'],'inputs':{rel(p):sha(p) for p in inputs},'artifacts':{rel(p):sha(p) for p in artifacts},'assertions':{'successful_output_chars':99986,'unique_part_text_chars':8634,'part_outcomes':33,'diagnostic_hit_texts_verified_against_search':checked,'source_files_verified':len(source)},'note':'manifest excludes own hash, registration receipt, mutable run.json and future closure'}
 write(R/'.run-captures/freeze-manifest.json',manifest);artifacts.append(R/'.run-captures/freeze-manifest.json')
 receipt=run_capture.register(ROOT,meta['run_id'],inputs=[rel(p) for p in inputs],artifacts=[rel(p) for p in artifacts])
 write(R/'registration-summary.json',receipt)
 entries=read(R/'run.json');registered=entries['inputs']+entries['artifacts']
 for row in registered:assert sha(ROOT/row['path'])==row['sha256']
 verify={'status':'passed','inputs':len(entries['inputs']),'artifacts':len(entries['artifacts']),'verified_entries':len(registered),'run_json_sha256':sha(R/'run.json'),'assertions':manifest['assertions'],'registration':receipt}
 write(R/'.run-captures/freeze-verification.json',verify);print(json.dumps(verify,ensure_ascii=False))
if __name__=='__main__':main()
