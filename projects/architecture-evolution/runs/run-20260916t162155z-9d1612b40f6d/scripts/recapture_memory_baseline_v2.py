"""Repair the historical receipt-name collision in a fresh, isolated baseline."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RUN = HERE.parent
sys.path.insert(0, str(HERE))
import capture_memory_baseline as base

# The registered first capture script stays unchanged.  Its two document
# responses share a filename; distinguish the assembled document by response
# shape while retaining document.json as the record required by the updater.
base.OUT = RUN / ".run-captures" / "memory-closure" / "baseline-recapture-v2"
original_archive = base.archive

def archive(name, value):
    if name == "document.json" and isinstance(value, dict) and "report" in value:
        name = "document-assembled.json"
    original_archive(name, value)

base.archive = archive
base.main()

# Include the actual full-document receipt in the newly created manifest.
manifest_path = base.OUT / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assembled = base.OUT / "document-assembled.json"
manifest["files"]["document-assembled.json"] = hashlib.sha256(assembled.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
