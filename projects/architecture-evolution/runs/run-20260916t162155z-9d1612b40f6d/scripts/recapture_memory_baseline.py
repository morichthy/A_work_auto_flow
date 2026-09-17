"""Create a second immutable public-API baseline without touching registered files."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parents[1]
OUT = RUN / ".run-captures" / "memory-closure" / "baseline-recapture"
OWNER = "PRJ-ARCHITECTURE-EVOLUTION"
TARGETS = {"unit": "MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b", "section": "MEM-50f66b7c-7953-5715-8b70-5ae7705176ab", "document": "MEM-bd121869-a0b9-59e3-af23-8e8675374a63", "overview": "MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155"}

def save(name, value):
    path = OUT / name
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != data: raise RuntimeError("immutable receipt differs: " + name)
        return
    pending = path.with_name(".pending-" + uuid.uuid4().hex)
    pending.write_text(data, encoding="utf-8"); pending.replace(path)

def main():
    sys.path.insert(0, str(ROOT / "automation" / "scripts"))
    from memory import api
    from memory.service import MemoryService
    OUT.mkdir(parents=True, exist_ok=True)
    service = MemoryService(ROOT)
    def read(action, request):
        value = api.dispatch(service, action, request)
        if value.get("error") or value.get("writes") not in (None, 0): raise RuntimeError(value)
        return value
    start = read("inspect", {"owner_id": OWNER}); save("owner-start.json", start)
    records = {}
    for key, record_id in TARGETS.items():
        value = read("inspect", {"owner_id": OWNER, "record_id": record_id}); save(key + ".json", value)
        records[key] = {"record_id": record_id, "revision": value["record"]["revision"], "record_hash": value["record"]["record_hash"]}
    request = {"owner_id": OWNER, "document_id": TARGETS["document"], "revision": records["document"]["revision"]}
    save("document-request.json", request)
    for action, name in (("outline", "outline.json"), ("document", "document.json"), ("document-impact", "document-impact.json")):
        save(name, read(action, request))
    end = read("inspect", {"owner_id": OWNER}); save("owner-end.json", end)
    if start["head"] != end["head"]: raise RuntimeError("Owner changed during re-capture")
    names = ["owner-start.json", "unit.json", "section.json", "document.json", "overview.json", "document-request.json", "outline.json", "document-impact.json", "owner-end.json"]
    save("manifest.json", {"owner_id": OWNER, "head": start["head"], "records": records, "files": {n: hashlib.sha256((OUT / n).read_bytes()).hexdigest() for n in names}, "status": "read-only recapture; no commit submitted"})

if __name__ == "__main__": main()
