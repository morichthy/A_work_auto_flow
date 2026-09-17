"""通过公开只读API固定上一报告及当前Owner基线，供本轮结果整合。"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent.parent / 'verification'
sys.path.insert(0, str(ROOT / 'automation/scripts'))
from memory import api
from memory.service import MemoryService

service = MemoryService(ROOT)
owner = 'PRJ-ARCHITECTURE-EVOLUTION'
requests = {
    'owner-before': ('inspect', {'owner_id': owner}),
    'previous-overview': ('inspect', {'owner_id': owner, 'record_id': 'MEM-3227e150-36dd-5d01-825d-38c7362989b2', 'revision': 1}),
    'previous-document': ('document', {'owner_id': owner, 'document_id': 'MEM-5c827f1d-99ff-5a60-a150-ac28ad89c877', 'revision': 1}),
    'previous-impact': ('document-impact', {'owner_id': owner, 'document_id': 'MEM-5c827f1d-99ff-5a60-a150-ac28ad89c877', 'revision': 1}),
}
for label, (action, request) in requests.items():
    value = api.dispatch(service, action, request)
    with (HERE / (label + '.json')).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    if 'error' in value:
        raise RuntimeError(value)
    print(label, 'saved')
