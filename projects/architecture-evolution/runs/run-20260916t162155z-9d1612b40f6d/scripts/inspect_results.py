import json,collections
from pathlib import Path
p=Path('projects/architecture-evolution/runs/run-20260916t162155z-9d1612b40f6d/.run-captures/budget-trace');e=json.loads((p/'events.json').read_text(encoding='utf-8'))
for n,x in enumerate(e):
 if x['kind']=='diagnostics':
  c=next(v for v in e[n+1:] if v['kind']=='charge')
  s=x['stack'][0]
  print(json.dumps({'kind':'diag','seq':x['seq'],'chars':c['requested'],'success':c['success'],'reading_line':s['line'],'lane':s.get('lane'),'keys':x['keys'],'hits':x['hits'],'matched':x['matched_text_chars']},ensure_ascii=False))
for x in e:
 if x['kind']=='candidate_packet':print(json.dumps({k:v for k,v in x.items() if k not in ['candidate','time_ns']},ensure_ascii=False),x['candidate']['title'])
