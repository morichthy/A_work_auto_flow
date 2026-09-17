"""Apply via the collision-free public-API baseline recapture."""
from __future__ import annotations
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
RUN = HERE.parent
sys.path.insert(0, str(HERE))
import apply_budget_trace_results as apply
apply.BASELINE = RUN / ".run-captures" / "memory-closure" / "baseline-recapture-v2"
apply.main()
