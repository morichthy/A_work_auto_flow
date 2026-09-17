"""Write one public material-query API receipt verbatim for the Owner smoke test."""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / "automation" / "scripts"))
from material_query.api import dispatch
from material_query.coordinator import Coordinator

action, request_file, receipt_file, timing_file = sys.argv[1:]
# Preserve the exact request bytes beside each receipt before parsing.  A later
# retry may need a corrected request, but must never make this capture ambiguous.
request_bytes = Path(request_file).read_bytes()
snapshot_file = Path(receipt_file + ".request-snapshot.json")
snapshot_file.write_bytes(request_bytes)
request_sha256 = hashlib.sha256(request_bytes).hexdigest()
request = json.loads(request_bytes.decode("utf-8"))
started = time.perf_counter()
app = Coordinator(ROOT)
try:
    receipt = dispatch(app, action, request)
finally:
    app.close()
elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
Path(receipt_file).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
Path(timing_file).write_text(json.dumps({"action": action, "wall_ms": elapsed_ms, "measurement": "API dispatch wall time; no host-model internal timing", "request_snapshot": str(snapshot_file), "request_sha256": request_sha256}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"receipt": receipt_file, "status": receipt.get("status"), "code": receipt.get("code"), "revision": (receipt.get("value") or {}).get("revision")}, ensure_ascii=False))
