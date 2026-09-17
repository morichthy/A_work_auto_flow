"""Summarize exact successful ledger debits; no product or frozen evidence edits."""
import json,collections,hashlib,zipfile,difflib
from pathlib import Path
RUN=Path(__file__).resolve().parents[1];ROOT=RUN.parents[3];OUT=RUN/'.run-captures/budget-trace'
e=json.loads((OUT/'events.json').read_text(encoding='utf-8'))
c=[x for x in e if x['kind']=='charge' and x['key']=='output_chars']
by=collections.defaultdict(lambda:{'success_chars':0,'success_calls':0,'failed_calls':0,'failed_requested':0})
for x in c:
 s=x['stack'][0]; k=s['file']+':'+str(s['line'])+':'+s['function'];r=by[k]
 if x['success']:r['success_chars']+=x['requested'];r['success_calls']+=1
 else:r['failed_calls']+=1;r['failed_requested']+=x['requested']
parts=[x for x in e if x['kind']=='part']; dup=collections.defaultdict(list)
for x in parts:
 if x['parts_added']:dup[(json.dumps(x['ref'],sort_keys=True),x['selector'],x['text']['sha256'])].append(x)
duplicates=[{'ref':v[0]['ref'],'selector':v[0]['selector'],'chars':v[0]['text']['chars'],'occurrences':len(v),'charged':sum(x['charged'] for x in v),'seqs':[x['seq'] for x in v]} for v in dup.values() if len(v)>1]
result={'by_charge_site':dict(by),'part_attempts':len(parts),'parts_added':sum(x['parts_added'] for x in parts),'part_charged':sum(x['charged'] for x in parts),'largest_parts':sorted(parts,key=lambda x:x['text']['chars'],reverse=True)[:15],'duplicate_parts':duplicates,'candidate_packets':[x for x in e if x['kind'].startswith('candidate_packet')],'diagnostics':[x for x in e if x['kind']=='diagnostics'],'gaps':[x for x in e if x['kind']=='gap'],'failed_output_charges':[x for x in c if not x['success']]}
(OUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
# Preserve currently executed Python source files beside their manifest.
manifest=json.loads((OUT/'source-manifest.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(OUT/'source-snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
 for rel,meta in manifest.items():
  p=ROOT/rel;b=p.read_bytes()
  if hashlib.sha256(b).hexdigest()!=meta['sha256']:raise RuntimeError('Source changed during measurement: '+rel)
  z.writestr(rel,b)
print(json.dumps({'by_charge_site':dict(by),'part_attempts':len(parts),'parts_added':result['parts_added'],'part_charged':result['part_charged'],'duplicates':duplicates,'candidate_packet_count':len(result['candidate_packets']),'gap_count':len(result['gaps']),'failures':[{'seq':x['seq'],'requested':x['requested'],'used_before':x['used_before'],'remaining':x['remaining_before'],'site':x['stack'][0]} for x in result['failed_output_charges']]},ensure_ascii=False))
