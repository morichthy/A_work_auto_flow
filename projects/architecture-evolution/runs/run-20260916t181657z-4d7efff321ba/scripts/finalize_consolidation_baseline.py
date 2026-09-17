"""Finalize a previously captured read-only consolidation baseline.

This intentionally performs just the final Owner HEAD read and manifest write,
so the public-memory reads remain within the command runner time limit.
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
FILES = ["owner-start.json", "reader-unit.json", "workbench-section.json", "overview.json", "document-record.json", "document-request.json", "outline.json", "document-assembled.json", "document-impact.json", "owner-end.json"]


def archive(name: str, value: object) -> None:
    """Preserve immutable receipt bytes across retried finalization."""
    path = OUT / name
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"frozen receipt differs: {path}")
        return
    pending = path.with_name(f".pending-{uuid.uuid4().hex}")
    pending.write_text(content, encoding="utf-8")
    pending.replace(path)


def main() -> None:
    sys.path.insert(0, str(ROOT / "automation" / "scripts"))
    from memory import api
    from memory.service import MemoryService

    start = json.loads((OUT / "owner-start.json").read_text(encoding="utf-8"))
    service = MemoryService(ROOT)
    end = api.dispatch(service, "inspect", {"owner_id": OWNER_ID})
    if end.get("error") or end.get("writes") not in (None, 0):
        raise RuntimeError(end.get("error") or "unexpected memory write")
    archive("owner-end.json", end)
    if start["head"] != end["head"]:
        raise RuntimeError("Owner HEAD changed while reading; baseline is not stable")
    records = {}
    for key, filename in {"reader-unit": "reader-unit.json", "workbench-section": "workbench-section.json", "overview": "overview.json", "document-record": "document-record.json"}.items():
        record = json.loads((OUT / filename).read_text(encoding="utf-8"))["record"]
        records[key] = {"record_id": record["record_id"], "revision": record["revision"], "record_hash": record["record_hash"]}
    manifest = {"owner_id": OWNER_ID, "head": start["head"], "records": records, "files": {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in FILES}, "status": "read-only baseline; no Run or memory commit submitted"}
    archive("manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
