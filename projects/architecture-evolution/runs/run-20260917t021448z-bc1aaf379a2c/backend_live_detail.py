"""只读实际浮点证据详情；日志仅结果/尺寸，不复制图片原字节。"""
import sys,json,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'automation/scripts'))
from material_query.evidence_navigation import detail,Catalog
service=SimpleNamespace(root=ROOT,materials=SimpleNamespace(access_owner_ids=None))
for identity in ['MEM-ab9db095-2545-594c-9e94-f72bab43c464']:
    start=time.perf_counter()
    try:
        value=detail(service,{'id':identity})
        print(json.dumps({'id':identity,'seconds':time.perf_counter()-start,'kind':value['kind'],'body_chars':len(value['content_markdown']),
            'image_count':len(value['images']),'media_bytes':len((value.get('media') or {}).get('data_url','')),'warnings':value['warnings'],
            'references':len(value['references'])},ensure_ascii=False),flush=True)
    except Exception as exc:print(json.dumps({'id':identity,'error':str(exc),'type':type(exc).__name__},ensure_ascii=False),flush=True)
c=Catalog(ROOT)
print(json.dumps({'tool_title':c.owner('TOOL-WORKSPACE-001')['title'],'catalog_warnings':c.warnings},ensure_ascii=False));c.close()
