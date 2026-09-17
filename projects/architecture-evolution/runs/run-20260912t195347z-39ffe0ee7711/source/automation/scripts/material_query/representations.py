"""判定真实内容能否按类型呈现；类型注册与材料可用性不混用。"""
from dataclasses import asdict

from . import definitions


def inspect(coordinator, raw):
    """Inspect fixed inputs without performing recall or generating text."""
    from types import SimpleNamespace
    from memory.errors import MemoryError
    from .budget import DEFAULT_BUDGET, Ledger
    from .contracts import DefinitionRef, FixedRef
    from .coordinator import envelope, failure
    from .reader import Reader
    from .validation import QueryError, object_fields, parse
    state = SimpleNamespace(ledger=Ledger(DEFAULT_BUDGET))
    try:
        object_fields(raw, {"refs", "definition"})
        refs = parse(raw["refs"], tuple[FixedRef, ...])
        if not 1 <= len(refs) <= 32:
            raise QueryError("VALIDATION", "每批检查1–32个固定材料")
        definition = parse(raw["definition"], DefinitionRef)
        definitions.get(definition)
        reader = Reader(coordinator.root, state.ledger, access_owner_ids=coordinator.access_owner_ids)
        result = []
        with state.ledger.active():
            for ref in refs:
                if ref.kind == "file":
                    reader.file_bytes(ref)
                    result.append({"definition": asdict(definition), "refs": [asdict(ref)],
                                   "state": "direct" if definition.key == "original" else "unsupported",
                                   "missing_selectors": [] if definition.key == "original" else ["canonical content"], "generator_version": None})
                    continue
                record = reader.record(ref)
                item = availability(record, ref, definition)
                # Explicit inspection checks freshness of declared contributors.
                # It is intentionally separate from cheap candidate field checks
                # so a summary search does not hash every original implicitly.
                from memory.evidence_adapter import iter_refs
                from .legacy_adapter import from_legacy
                for legacy in iter_refs({"sources": record["sources"], "payload": record["payload"]}):
                    try:
                        if legacy["target_kind"] == "file":
                            reader.file_bytes(from_legacy(legacy)[0])
                        elif legacy["target_kind"] == "record":
                            current = reader.current_record(legacy["target_id"])
                            if current["revision"] != legacy["revision"] or legacy.get("sha256") and current["record_hash"] != legacy["sha256"]:
                                raise QueryError("STALE", "贡献材料已有新版")
                    except QueryError as exc:
                        if exc.code != "STALE":
                            raise
                        item.update(state="stale", missing_selectors=["current contributor version"])
                result.append(item)
            basis = reader.basis()
        return envelope(result, state=state, basis=basis)
    except (QueryError, MemoryError) as exc:
        return failure(exc, state)


def availability(record, ref, definition):
    definitions.get(definition)
    key, kind = definition.key, record.get("kind")
    payload = record.get("payload", {})
    state, missing = "unsupported", []
    if key == "original":
        files = [item for item in record.get("sources", []) if item.get("target_kind") == "file"]
        state = "assemblable" if files else "needs_generation"
        if not files:
            missing = ["source.content"]
    elif key == "unit_digest":
        if kind == "detail" and payload.get("retrieval_description"):
            state = "assemblable"
        elif kind == "experience" and payload:
            state = "assemblable"
        else:
            missing = ["detail.retrieval_description or experience fields"]
            state = "needs_generation"
    elif key in {"full", "section"}:
        if kind == "detail" and (payload.get("blocks") or record.get("body_markdown")):
            state = "direct"
        elif kind == "document_section" and payload.get("blocks"):
            state = "direct"
        elif kind == "document" and payload.get("section_refs"):
            state = "assemblable"
        elif record.get("body_markdown"):
            state = "direct"
        elif kind not in {"detail", "document", "document_section"} and payload:
            # Historical events, experiences and maps store their complete
            # authored content in structured fields. legacy_full renders those
            # fields, so an empty optional body does not mean missing content.
            state = "direct"
        else:
            state, missing = "needs_generation", ["complete content"]
    elif key in {"topic", "domain"}:
        if kind in {"map", "document", "document_section"}:
            state = "assemblable"
        else:
            state, missing = "needs_generation", ["map or authored document"]
    return {"definition": asdict(definition), "refs": [asdict(ref)], "state": state,
            "missing_selectors": missing, "generator_version": "field-template-1" if state == "assemblable" else None}
