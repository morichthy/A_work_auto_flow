"""Execute fixed unittest IDs with a flushed JSONL event for each terminal state."""

from __future__ import annotations

import json
import sys
import time
import traceback
import unittest
from pathlib import Path


ROOT = Path.cwd()
ARTIFACTS = ROOT / ".local" / "release-20260916"


class TracedResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity, events):
        super().__init__(stream, descriptions, verbosity)
        self.events = events

    def event(self, test, status, detail=None):
        row = {"time": time.time(), "id": test.id(), "status": status}
        if detail:
            row["detail"] = detail
        self.events.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.events.flush()

    def startTest(self, test):
        self.event(test, "started")
        super().startTest(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self.event(test, "passed")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.event(test, "failed", "".join(traceback.format_exception(*err)))

    def addError(self, test, err):
        super().addError(test, err)
        self.event(test, "error", "".join(traceback.format_exception(*err)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.event(test, "skipped", reason)


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: run_traced_ids.py EVENT_FILE TEST_ID [TEST_ID ...]")
    event_path = ARTIFACTS / sys.argv[1]
    test_ids = sys.argv[2:]
    sys.path.insert(0, str(ROOT / "automation" / "tests"))
    suite = unittest.defaultTestLoader.loadTestsFromNames(test_ids)
    with event_path.open("w", encoding="utf-8") as events:
        runner = unittest.TextTestRunner(
            verbosity=2,
            resultclass=lambda stream, descriptions, verbosity: TracedResult(
                stream, descriptions, verbosity, events
            ),
        )
        result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
