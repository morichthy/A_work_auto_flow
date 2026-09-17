"""Capture public memory read receipts; never edit authoritative store files."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / 'automation' / 'scripts'))
from memory.api import dispatch
from memory.service import MemoryService
service = MemoryService(ROOT)
output = Path(__file__).parent
owner = 'PRJ-ARCHITECTURE-EVOLUTION'
document_id = 'MEM-bd121869-a0b9-59e3-af23-8e8675374a63'
for action, name, request in [
    ('inspect', 'baseline-owner', {'owner_id': owner}),
    ('outline', 'baseline-outline', {'owner_id': owner, 'document_id': document_id}),
    ('document', 'baseline-document', {'owner_id': owner, 'document_id': document_id}),
    ('document-impact', 'baseline-impact', {'owner_id': owner, 'document_id': document_id}),
]:
    value = dispatch(service, action, request)
    (output / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(name, 'saved', flush=True)
