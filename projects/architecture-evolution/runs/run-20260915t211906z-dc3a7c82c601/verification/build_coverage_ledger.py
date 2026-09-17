"""Merge terminal unittest log records into a fixed-ID release coverage ledger."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path.cwd()
ARTIFACTS = ROOT / ".local" / "release-20260916"
LOGS = [
    "backend-unittest.log",
    "backend-unittest-synthetic-tier.log",
    "backend-unittest-workspace-cli.log",
    "backend-unittest-remaining-synthetic.log",
    "backend-unittest-remaining-model.log",
    "backend-unittest-b01-recheck.log",
    "backend-unittest-workbench-relations-elevated.log",
]
EVENTS = [
    "b01-recheck-events.jsonl",
    "workbench-relations-elevated-events.jsonl",
]
START = re.compile(r"^(test_[^(]+) \(([^)]+)\)(.*)$")
TERMINAL = re.compile(r"^(?:.*\.\.\. )?(ok|FAIL|ERROR|skipped|expected failure|unexpected success)$")


def normalized(token: str) -> str:
    return {
        "ok": "passed",
        "FAIL": "failed",
        "ERROR": "error",
        "skipped": "skipped",
        "expected failure": "expected_failure",
        "unexpected success": "unexpected_success",
    }[token]


def main() -> None:
    records: dict[str, dict[str, str]] = {}
    for name in LOGS:
        active = None
        for line in (ARTIFACTS / name).read_text(encoding="utf-8", errors="replace").splitlines():
            match = START.match(line)
            if match:
                active = match.group(2)
                trailing = match.group(3)
                terminal = re.search(r"\.\.\. (ok|FAIL|ERROR|skipped|expected failure|unexpected success)$", trailing)
                if terminal:
                    records[active] = {"status": normalized(terminal.group(1)), "source": name}
                    active = None
                continue
            if active:
                terminal = TERMINAL.match(line)
                if terminal:
                    records[active] = {"status": normalized(terminal.group(1)), "source": name}
                    active = None
    # JSONL events are flushed per test and prevail over buffered console output.
    for name in EVENTS:
        path = ARTIFACTS / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if value["status"] in {"passed", "failed", "error", "skipped"}:
                records[value["id"]] = {"status": value["status"], "source": name}
    discovered = json.loads((ARTIFACTS / "discovered-test-ids.json").read_text(encoding="utf-8-sig"))
    tests = [{"id": test_id, **records.get(test_id, {"status": "not_executed", "source": None})} for test_id in discovered]
    counts: dict[str, int] = {}
    for test in tests:
        counts[test["status"]] = counts.get(test["status"], 0) + 1
    ledger = {
        "discovery_count": len(discovered),
        "terminal_count": sum(counts.get(status, 0) for status in ("passed", "failed", "error", "skipped", "expected_failure", "unexpected_success")),
        "counts": counts,
        "source_logs": LOGS + EVENTS,
        "tests": tests,
    }
    (ARTIFACTS / "backend-unittest-coverage-ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: ledger[key] for key in ("discovery_count", "terminal_count", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
