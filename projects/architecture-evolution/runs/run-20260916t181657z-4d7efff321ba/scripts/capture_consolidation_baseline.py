"""Freeze a read-only consolidation baseline for the Owner-document reading Run.

Only public ``memory.api.dispatch`` read actions are used.  The document MEM
record and assembled document receive distinct receipt names.  Existing
receipts are immutable: a rerun rejects different bytes rather than replacing
the prior baseline.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parents[1]
OUT = RUN / ".run-captures" / "consolidation-baseline"
OWNER_ID = "PRJ-ARCHITECTURE-EVOLUTION"
TARGETS = {
    "reader-unit": "MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b",
    "workbench-section": "MEM-50f66b7c-7953-5715-8b70-5ae7705176ab",
    "overview": "MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155",
    "document-record": "MEM-bd121869-a0b9-59e3-af23-8e8675374a63",
}


def archive(name: str, value: object) -> None:
    """Write one immutable JSON receipt, rejecting a differing rerun."""
    path = OUT / name
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"frozen receipt differs: {path}")
        return
    pending = path.with_name(f".pending-{uuid.uuid4().hex}")
    pending.write_text(content, encoding="utf-8")
    pending.replace(path)


def dispatch(service, action: str, request: dict) -> dict:
    """Call one public read action and refuse a response reporting writes."""
    from memory import api
    response = api.dispatch(service, action, request)
    if response.get("error"):
        raise RuntimeError(response["error"])
    if response.get("writes") not in (None, 0):
        raise RuntimeError(f"read-only action unexpectedly reported writes: {action}")
    return response


def main() -> None:
    sys.path.insert(0, str(ROOT / "automation" / "scripts"))
    from memory.service import MemoryService

    OUT.mkdir(parents=True, exist_ok=True)
    service = MemoryService(ROOT)
    start = dispatch(service, "inspect", {"owner_id": OWNER_ID})
    archive("owner-start.json", start)
    records = {}
    for name, record_id in TARGETS.items():
        receipt = dispatch(service, "inspect", {"owner_id": OWNER_ID, "record_id": record_id})
        archive(f"{name}.json", receipt)
        records[name] = {"record_id": record_id, "revision": receipt["record"]["revision"], "record_hash": receipt["record"]["record_hash"]}

    document_request = {"owner_id": OWNER_ID, "document_id": TARGETS["document-record"], "revision": records["document-record"]["revision"]}
    archive("document-request.json", document_request)
    archive("outline.json", dispatch(service, "outline", document_request))
    archive("document-assembled.json", dispatch(service, "document", document_request))
    archive("document-impact.json", dispatch(service, "document-impact", document_request))
    end = dispatch(service, "inspect", {"owner_id": OWNER_ID})
    archive("owner-end.json", end)
    if start["head"] != end["head"]:
        raise RuntimeError("Owner HEAD changed while reading; baseline is not stable")

    files = ["owner-start.json", "reader-unit.json", "workbench-section.json", "overview.json", "document-record.json", "document-request.json", "outline.json", "document-assembled.json", "document-impact.json", "owner-end.json"]
    manifest = {"owner_id": OWNER_ID, "head": start["head"], "records": records, "files": {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in files}, "status": "read-only baseline; no Run or memory commit submitted"}
    archive("manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
