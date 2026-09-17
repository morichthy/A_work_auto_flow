"""Use the isolated re-captured baseline for the already-reviewed memory update."""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent
sys.path.insert(0, str(HERE))
import apply_budget_trace_results as apply

# The original script and registered inputs remain byte-for-byte unchanged.
apply.BASELINE = RUN / ".run-captures" / "memory-closure" / "baseline-recapture"
apply.main()
