"""Apply the reviewed per-charge budget-trace conclusion through public memory APIs.

The script is intentionally inert until the completed Run, a non-empty RESULTS
file, and a reviewer-authored conclusion file are supplied.  It updates the
existing reader unit, section, overview, and process document in dependency
order, with CAS revisions from the frozen baseline.  It never rewrites the
historical latency Run or its fixed receipts.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parents[1]
BASELINE = RUN / ".run-captures" / "memory-baseline"
OUT = RUN / ".run-captures" / "memory-closure"
OWNER_ID = "PRJ-ARCHITECTURE-EVOLUTION"
TARGETS = {
    "unit": "MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b",
    "section": "MEM-50f66b7c-7953-5715-8b70-5ae7705176ab",
    "document": "MEM-bd121869-a0b9-59e3-af23-8e8675374a63",
    "overview": "MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155",
}
BOUNDARY = (
    "本轮是每路10/重排30、服务器允许100,000字符预算下的单次失败诊断；"
    "逐笔扣费仅解释这次输入、候选和实现路径，不能推断其他主题、规模或宿主的费用和延迟。"
    "未修改产品检索、预算或重排实现；历史Run及其固定结果不改写。"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def archive(name: str, value: object) -> None:
    """Keep every preflight, commit, and readback receipt immutable."""
    path = OUT / name
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != data:
            raise RuntimeError(f"frozen closure receipt differs: {path}")
        return
    pending = path.with_name(f".pending-{uuid.uuid4().hex}")
    pending.write_text(data, encoding="utf-8")
    pending.replace(path)


def refs(*groups: list[dict]) -> list[dict]:
    """Append fixed references without changing the version of existing evidence."""
    result: list[dict] = []
    for group in groups:
        for ref in group:
            if ref not in result:
                result.append(deepcopy(ref))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--conclusion-file", type=Path, required=True)
    args = parser.parse_args()

    manifest = load(BASELINE / "manifest.json")
    for name, digest in manifest["files"].items():
        actual = hashlib.sha256((BASELINE / name).read_bytes()).hexdigest()
        if actual != digest:
            raise RuntimeError(f"baseline receipt changed: {name}")
    run = load(args.run_json)
    if run.get("run_id") != load(RUN / "run.json")["run_id"]:
        raise RuntimeError("only this diagnosis Run may be recorded")
    if run.get("status") not in {"succeeded", "failed"} or not run.get("artifacts"):
        raise RuntimeError("Run must be completed and have registered artifacts")
    results = args.results.read_text(encoding="utf-8")
    conclusion = args.conclusion_file.read_text(encoding="utf-8").strip()
    if not results.strip() or not conclusion:
        raise RuntimeError("RESULTS and reviewed conclusion must both be non-empty")

    sys.path.insert(0, str(ROOT / "automation" / "scripts"))
    from evidence import fingerprint
    from memory import api, contracts, documents
    from memory.service import MemoryService

    OUT.mkdir(parents=True, exist_ok=True)
    service = MemoryService(ROOT)

    def invoke(action: str, request: dict, label: str) -> dict:
        response = api.dispatch(service, action, request)
        if response.get("error"):
            archive(label + "-error.json", response)
            raise RuntimeError(response["error"])
        return response

    expected_head = manifest["head"]["commit_id"]
    current = invoke("inspect", {"owner_id": OWNER_ID}, "head-before")
    archive("head-before.json", current)
    if current["head"]["commit_id"] != expected_head:
        raise RuntimeError("Owner changed after baseline; re-read and re-review before applying")
    old = {key: load(BASELINE / f"{key}.json")["record"] for key in TARGETS}
    run_ref = {
        "target_kind": "owner", "target_id": run["run_id"], "revision": None,
        "sha256": fingerprint(run), "locator": "逐笔预算trace、RESULTS与固定产物",
        "relation": "input",
    }

    def draft(record: dict) -> dict:
        value = {key: deepcopy(record[key]) for key in (*contracts.CONTENT_FIELDS, "schema_version", "record_reason")}
        value["change_reason"] = "追加每路10/重排30的逐笔预算trace，校正旧总账推断并保留历史Run。"
        value["keywords"] = list(dict.fromkeys([*value["keywords"], "budget-trace", "每路10", "重排30"]))
        return value

    def commit(label: str, changes: dict, head: str, revisions: dict) -> tuple[dict, str]:
        request = {
            "schema_version": 3, "request_id": str(uuid.uuid4()),
            "actor": {"kind": "ai", "id": "codex-budget-trace"},
            "owner_id": OWNER_ID, "expected_head": head,
            "operations": [{"op": "put_record", "record_id": TARGETS[key],
                            "expected_revision": revisions[key], "draft": value}
                           for key, value in changes.items()],
        }
        structural = contracts.validate_request(request)
        archive(label + "-structural.json", structural)
        if not structural["valid"]:
            raise RuntimeError(structural)
        archive(label + "-request.json", request)
        preflight = invoke("validate-draft", request, label + "-preflight")
        archive(label + "-preflight.json", preflight)
        if not preflight.get("valid"):
            raise RuntimeError(preflight)
        receipt = invoke("commit", request, label + "-commit")
        archive(label + "-commit.json", receipt)
        saved = {}
        for key in changes:
            saved[key] = invoke("inspect", {"owner_id": OWNER_ID, "record_id": TARGETS[key],
                                               "revision": revisions[key] + 1}, label + "-" + key)["record"]
            archive(label + "-" + key + "-readback.json", saved[key])
        return saved, receipt["commit_id"]

    unit = draft(old["unit"])
    if any(block["block_id"] == "budget-trace-results" for block in unit["payload"]["blocks"]):
        raise RuntimeError("budget-trace result already exists; inspect prior closure")
    unit["sources"] = refs(unit["sources"], [run_ref])
    unit["payload"]["evidence_refs"] = refs(unit["payload"]["evidence_refs"], [run_ref])
    unit["payload"]["blocks"].append({"block_id": "budget-trace-results", "role": "results",
                                         "markdown": results, "requires_block_ids": []})
    unit["payload"]["retrieval_description"]["method"] += "；本轮以每笔实际charge分解100k预算失败。"
    unit["payload"]["retrieval_description"]["key_findings"].append(conclusion)
    unit["payload"]["retrieval_description"]["limitations"] = list(dict.fromkeys(
        [*unit["payload"]["retrieval_description"]["limitations"], BOUNDARY]))
    saved, head = commit("01-unit", {"unit": unit}, expected_head, {key: manifest["records"][key]["revision"] for key in TARGETS})

    unit_ref = documents.fixed_ref(saved["unit"])
    section = draft(old["section"])
    for block in section["payload"]["blocks"]:
        if block.get("type") == "unit" and block.get("ref", {}).get("target_id") == TARGETS["unit"]:
            block["ref"] = unit_ref
            block["block_ids"] = list(dict.fromkeys([*block.get("block_ids", []), "budget-trace-results"]))
            break
    else:
        raise RuntimeError("reader unit is absent from baseline section")
    section["payload"]["blocks"].insert(0, {"type": "prose", "markdown": conclusion + "\n\n" + BOUNDARY,
                                               "evidence_refs": [unit_ref]})
    section["sources"] = refs([ref for ref in section["sources"] if ref["target_id"] != TARGETS["unit"]], [unit_ref])
    overview = draft(old["overview"])
    overview["body_markdown"] += "\n\n本轮逐笔预算trace：\n\n" + conclusion + "\n\n" + BOUNDARY
    overview["payload"]["results"].append(conclusion)
    overview["payload"]["limitations"] = list(dict.fromkeys([*overview["payload"]["limitations"], BOUNDARY]))
    overview["payload"]["current_stage"] = "每路10/重排30的逐笔预算诊断已完成；已校正旧总账推断，未实施产品修复。"
    overview["payload"]["technical_refs"] = refs(overview["payload"]["technical_refs"], [unit_ref])
    overview["sources"] = refs(overview["sources"], [unit_ref])
    middle, head = commit("02-section-overview", {"section": section, "overview": overview}, head,
                          {"section": manifest["records"]["section"]["revision"],
                           "overview": manifest["records"]["overview"]["revision"]})

    document = draft(old["document"])
    section_ref = documents.fixed_ref(middle["section"])
    document["payload"]["section_refs"] = [section_ref if ref["target_id"] == TARGETS["section"] else ref
                                               for ref in document["payload"]["section_refs"]]
    document["payload"]["common_refs"] = refs([ref for ref in document["payload"]["common_refs"]
                                                  if ref["target_id"] != TARGETS["unit"]], [unit_ref])
    document["payload"]["scope"] += "；追加每路10/重排30逐笔预算trace及旧总账推断校正，不含产品修复。"
    document["sources"] = refs(document["payload"]["common_refs"], document["payload"]["section_refs"])
    final, _ = commit("03-document", {"document": document}, head,
                      {"document": manifest["records"]["document"]["revision"]})

    request = {"owner_id": OWNER_ID, "document_id": TARGETS["document"], "revision": final["document"]["revision"]}
    report = invoke("document", request, "final-document")
    archive("final-document.json", report)
    archive("final-impact.json", invoke("document-impact", request, "final-impact"))
    if not report["report"]["complete"]:
        raise RuntimeError("committed document did not assemble completely")
    archive("identities.json", {key: documents.fixed_ref(value) for key, value in {**saved, **middle, **final}.items()})
    print("Committed and read back. A human/AI full-text consistency review remains required before a sync claim.")


if __name__ == "__main__":
    main()
