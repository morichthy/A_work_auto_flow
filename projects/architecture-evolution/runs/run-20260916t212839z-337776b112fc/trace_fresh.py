import sys,json
from pathlib import Path
sys.path.insert(0,'automation/scripts')
from material_query.coordinator import Coordinator
from material_query.api import dispatch
def trace(frame,event,arg):
    if event == 'exception' and type(arg[1]).__name__ == 'MemoryError':
        print(frame.f_code.co_filename, frame.f_lineno, repr(arg[1]), getattr(arg[1],'details',{}), file=sys.stderr)
    return trace
sys.settrace(trace)
a=Coordinator(Path.cwd())
r=dispatch(a,'reading-handoff',{'session_id':'RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3b'})
print(json.dumps({k:v for k,v in r.items() if k!='value'},ensure_ascii=False))
a.close()
