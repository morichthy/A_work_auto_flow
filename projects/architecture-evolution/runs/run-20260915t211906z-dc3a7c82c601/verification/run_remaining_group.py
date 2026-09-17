"""Run one fixed, non-overlapping subset of the release unittest inventory.

The input plan is derived from unittest discovery and completed terminal log
records.  It deliberately treats an interrupted test as remaining work.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path.cwd()
ARTIFACTS = ROOT / ".local" / "release-20260916"
PLAN = ARTIFACTS / "remaining-test-plan.json"
MODEL_MODULES = {
    "test_local_retrieval",
    "test_material_recall",
    "test_memory_associations_real",
    "test_retrieval",
    "test_retrieval_layers",
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"synthetic", "model"}:
        raise SystemExit("usage: run_remaining_group.py {synthetic|model}")
    group = sys.argv[1]
    plan = json.loads(PLAN.read_text(encoding="utf-8-sig"))
    test_ids = []
    for test_id in plan["remaining_ids"]:
        is_model = test_id.split(".", 1)[0] in MODEL_MODULES
        if is_model == (group == "model"):
            test_ids.append(test_id)
    # Discovery normally adds this path; explicit loading from fixed IDs does not.
    sys.path.insert(0, str(ROOT / "automation" / "tests"))
    suite = unittest.defaultTestLoader.loadTestsFromNames(test_ids)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {
        "group": group,
        "planned_ids": test_ids,
        "planned_count": len(test_ids),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "successful": result.wasSuccessful(),
    }
    (ARTIFACTS / f"remaining-{group}-result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
