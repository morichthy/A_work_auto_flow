"""Detailed, hash-based accounting decomposition; lengths are characters, not tokens."""
import json,collections
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'.run-captures/budget-trace';E=json.loads((P/'events.json').read_text(encoding='utf-8'))
fragments=collections.defaultdict(list);routes=[];diagnostics=[]
for i,e in enumerate(E):
 if e['kind']=='charge' and e['key']=='output_chars' and e['success'] and e['stack'][0]['function']=='_run_search':
  s=e['stack'][0];outer=next(r for r in e['stack'] if r['function']=='recall');routes.append({'seq':e['seq'],'lane':outer.get('lane'),'route':outer.get('route'),'chars':e['requested'],'candidates':len(s['visible'])})
  for c in s['visible']:
   ref=json.dumps(c['refs'][0],sort_keys=True)
   for role,h in [('excerpt',c['excerpt'])]+[('matched_text',h['matched_text']) for h in c['hits']]:
    if h['chars']:fragments[(ref,h['sha256'])].append({'role':role,'chars':h['chars'],'seq':e['seq'],'lane':outer.get('lane'),'route':outer.get('route',{}).get('id')})
 if e['kind']=='diagnostics':
  c=next(x for x in E[i+1:] if x['kind']=='charge');s=e['stack'][0]
  diagnostics.append({'seq':e['seq'],'lane':s.get('lane'),'line':s['line'],'chars':c['requested'],'success':c['success'],'hits':e['hits'],'matched_text_chars':e['matched_text_chars'],'keys':e['keys'],'candidate':s.get('candidate')})
parts=[e for e in E if e['kind']=='part'];part_groups=collections.defaultdict(lambda:{'attempted_chars':0,'added_chars':0,'charged':0,'parts':0})
for e in parts:
 g=part_groups[e['group']];g['attempted_chars']+=e['text']['chars'];g['added_chars']+=e['text']['chars'] if e['parts_added'] else 0;g['charged']+=e['charged'];g['parts']+=e['parts_added']
unique=sum(v[0]['chars'] for v in fragments.values());total=sum(x['chars'] for v in fragments.values() for x in v)
result={'routes':routes,'diagnostics':diagnostics,'search_fragment_chars_total':total,'search_fragment_chars_unique_by_fixed_ref_and_text_hash':unique,'search_fragment_repeated_chars':total-unique,'search_unique_fragments':len(fragments),'search_fragment_occurrences':sum(len(v) for v in fragments.values()),'search_duplicate_fragments':[{'ref':json.loads(k[0]),'text_sha256':k[1],'chars':v[0]['chars'],'occurrences':v} for k,v in fragments.items() if len(v)>1],'part_groups':dict(part_groups),'required_context_parts':[e for e in parts if e['group']=='required_context'],'images_data_url_chars':sum(e['image_chars'] for e in E if e['kind']=='candidate_packet'),'fused_hit_diagnostics_chars':sum(d['chars'] for d in diagnostics if d['hits'] and d['success']),'fused_hit_matched_text_chars':sum(d['matched_text_chars'] for d in diagnostics if d['hits'] and d['success'])}
(P/'decomposition.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ['routes','diagnostics','search_duplicate_fragments','required_context_parts']},ensure_ascii=False))
print('required_context_attempts',len(result['required_context_parts']))
