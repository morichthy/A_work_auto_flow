"""Bounded traceback capture for one isolated unittest case."""

from __future__ import annotations

import faulthandler
import sys
import unittest
from pathlib import Path


ROOT = Path.cwd()
ARTIFACTS = ROOT / ".local" / "release-20260916"
CASE = "test_workbench_relations.RelationsTests.test_authorization_change_invalidates_cached_projection"


def main() -> int:
    sys.path.insert(0, str(ROOT / "automation" / "tests"))
    with (ARTIFACTS / "workbench-authorization-faulthandler.txt").open("w", encoding="utf-8") as dump:
        faulthandler.dump_traceback_later(30, repeat=False, file=dump)
        try:
            result = unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromName(CASE)
            )
        finally:
            faulthandler.cancel_dump_traceback_later()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
