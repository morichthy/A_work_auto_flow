import json,collections
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'.run-captures/budget-trace';E=json.loads((P/'events.json').read_text(encoding='utf-8'));D=json.loads((P/'decomposition.json').read_text(encoding='utf-8'));A=json.loads((P/'analysis.json').read_text(encoding='utf-8'));C=json.loads((P/'calls.json').read_text(encoding='utf-8'))
parts=[x for x in E if x['kind']=='part'];uniq={};skips=collections.Counter();missing={}
for p in parts:
 k=(json.dumps(p['ref'],sort_keys=True),p['selector'],p['text']['sha256']);uniq[k]=p['text']['chars']
 if p['parts_added']:continue
 previous=E[p['seq']-2]
 if previous['kind']=='gap' and previous.get('details',{}).get('code')=='BUDGET':skips['budget']+=1;missing[k]=p['text']['chars']
 else:skips['deduplicated']+=1
roleunique={};roles=collections.Counter();bylane=collections.Counter();byrolehash={}
for x in E:
 if x['kind']=='charge' and x['key']=='output_chars' and x['success'] and x['stack'][0]['function']=='_run_search':
  outer=next(r for r in x['stack'] if r['function']=='recall');bylane[outer['lane']]+=x['requested']
  for c in x['stack'][0]['visible']:
   ref=json.dumps(c['refs'][0],sort_keys=True)
   for role,h in [('excerpt',c['excerpt'])]+[('matched_text',h['matched_text']) for h in c['hits']]:
    roles[role]+=h['chars'];roleunique[(ref,role,h['sha256'])]=h['chars']
result={'calls':C,'by_charge_site':A['by_charge_site'],'output_consumed':C[-1]['consumed']['output_chars'],'sum_successful_debits':sum(v['success_chars'] for v in A['by_charge_site'].values()),'search_chars_by_lane':dict(bylane),'search_chars_by_role':dict(roles),'search_unique_chars_by_ref_role_hash':sum(roleunique.values()),'search_unique_chars_by_ref_hash':D['search_fragment_chars_unique_by_fixed_ref_and_text_hash'],'search_repeated_chars_by_ref_hash':D['search_fragment_repeated_chars'],'candidate_diagnostic_chars':D['fused_hit_diagnostics_chars'],'candidate_diagnostic_matched_text_chars':D['fused_hit_matched_text_chars'],'candidate_diagnostic_metadata_and_json_chars':D['fused_hit_diagnostics_chars']-D['fused_hit_matched_text_chars'],'part_attempts':len(parts),'part_added_count':sum(x['parts_added'] for x in parts),'part_skip_counts':dict(skips),'attempted_part_unique_text_chars':sum(uniq.values()),'successful_part_text_chars':sum(x['text']['chars'] for x in parts if x['parts_added']),'omitted_unique_part_text_chars':sum(missing.values()),'image_data_url_chars':D['images_data_url_chars'],'image_caption_charged_chars':97,'failure':A['failed_output_charges'][-1], 'limitations':['instrumented replay, elapsed_s includes Coordinator construction/close and observer overhead','100000 is current server maximum, not a no-budget run','8634 counts unique attempted text blocks, not hypothetical complete final response or all undiscovered material','dedup metrics are byte-equivalent Unicode text by fixedref/text hash, not semantic dedup','image data_url is not charged to output_chars','no note/AI semantic reading was performed; objective is recall budget diagnosis']}
assert result['sum_successful_debits']==result['output_consumed']==99986
assert result['attempted_part_unique_text_chars']==result['successful_part_text_chars']+result['omitted_unique_part_text_chars']
(P/'final-metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ['failure','calls','by_charge_site','limitations']},ensure_ascii=False))
