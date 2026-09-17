"""Read-only local source integrity check; no search, index, RS, or source writes."""
from pathlib import Path
import json,sys,traceback
root=Path.cwd();sys.path.insert(0,str(root/'automation/scripts'))
from memory.store import MemoryStore
from memory.owners import resolve_owner
store=MemoryStore(root)
try:
 owner=resolve_owner(root,'RES-FLOATING-POINT-SUMMATION')
 snapshot=store.read_snapshot(owner)
 print(json.dumps({'direct_owner_integrity':'ok','record_count':len(snapshot['records'])},ensure_ascii=False))
 from material_query.coordinator import Coordinator
 from material_query.contracts import QueryRequest
 from material_query.validation import parse
 from material_query.legacy_adapter import fixed_record
 q=json.loads((root/'projects/architecture-evolution/runs/run-20260916t201935z-6c6692a35c2a/example/01-start-request.json').read_text(encoding='utf-8'))['query']
 app=Coordinator(root)
 try:
  state=app._new(parse(q,QueryRequest)); reader=app.reader(state)
  for rid,record in snapshot['records'].items():
   try:
    reader.record(fixed_record(record))
   except Exception as exc:
    print(json.dumps({'failed_root':rid,'type':type(exc).__name__,'message':str(exc),'cause':str(exc.__cause__),'cause_details':getattr(exc.__cause__,'details',None)},ensure_ascii=False),flush=True)
    traceback.print_exc();break
  else: print('all 27 direct record source closures passed',flush=True)
  from material_query.reading_owner import ReferenceAssembler
  from material_query.contracts import DefinitionRef
  for rid,record in snapshot['records'].items():
   try:
    assembler=ReferenceAssembler(reader,state.ledger,lambda _:True,required_allowed=lambda _:True)
    assembler.add_record(fixed_record(record),DefinitionRef('full','1'),q['question'])
   except Exception as exc:
    print(json.dumps({'assembly_failed_root':rid,'kind':record['kind'],'type':type(exc).__name__,'message':str(exc),'cause':str(exc.__cause__),'cause_details':getattr(exc.__cause__,'details',None)},ensure_ascii=False),flush=True)
    traceback.print_exc();break
  else: print('all 27 direct full assemblies passed',flush=True)
 finally: app.close()
except Exception as exc:
 print(json.dumps({'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc),'details':getattr(exc,'details',None)},ensure_ascii=False))
 traceback.print_exc()
