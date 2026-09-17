"""本轮只读现场定位：不读全库正文、不改索引或规范材料。"""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'automation/scripts'))
from material_query.evidence_navigation import Catalog,read_json
from memory import owners
c=Catalog(ROOT)
try:
    for row in c.db.execute('SELECT owner_id,owner_type,native_ref FROM memory_owners'):
        if row['owner_id'] in c.owners: continue
        ref=json.loads(row['native_ref'])
        try:
            path=owners.safe_path(ROOT,ref['path'])
            if not path.is_file(): raise ValueError('登记原对象不存在')
            raw=read_json(path) if path.suffix=='.json' else {'title':path.stem}
            if path.suffix=='.json' and ref.get('id_field') and raw.get(ref['id_field']) != ref.get('id_value'):
                raise ValueError('Owner登记身份与原卡不一致: '+repr((ref.get('id_field'),ref.get('id_value'),raw.get(ref['id_field']))))
            c.add_owner(row['owner_id'],row['owner_type'],ref['path'],raw)
        except Exception as exc:
            print(json.dumps({'owner_id':row['owner_id'],'native_ref':ref,'error':str(exc)},ensure_ascii=False))
    registry=read_json(ROOT/'retrieval/sources.json')
    for source in registry['sources']:
        if Path(source['path']).suffix.lower() in {'.png','.jpg','.jpeg','.webp'}:
            print(json.dumps({'image_registration':source},ensure_ascii=False))
finally:c.close()
