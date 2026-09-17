"""Independent compressed Owner discovery projection.

The canonical memory store remains authoritative.  This module deterministically
projects Owner metadata plus L4/L3, compact L2 and L1 retrieval descriptions into
its own SQLite FTS table and Qdrant namespace.  It never copies L1 blocks, L0
evidence or composed documents into the default discovery surface.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .contracts import canonical_hash, project_memory_level
from .errors import MemoryError
from . import index, owners
from .store import MemoryStore, utc_now
from .technical_units import description_text, is_unit


PROJECTION_VERSION = "owner-discovery-v1"
ENCODER_VERSION = "owner-discovery-minilm-v1"
COLLECTION_PREFIX = "memory_discovery_v1"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _head_generation(head):
    return head["generation"] if head else 0


def _state(db, owner_id):
    row = db.execute("SELECT * FROM memory_discovery_index_state WHERE owner_id=?", (owner_id,)).fetchone()
    return dict(row) if row else None


def _save_state(db, owner_id, head, **changes):
    """Update one derived watermark without claiming another channel succeeded."""
    current = _state(db, owner_id) or {
        "owner_id": owner_id,
        "expected_head": _json(head),
        "indexed_generation": None,
        "vector_generation": None,
        "target_generation": _head_generation(head),
        "lexical_status": "pending",
        "vector_status": "pending",
        "projection_version": PROJECTION_VERSION,
        "encoder_version": None,
        "vector_collection": None,
        "native_fingerprint": None,
        "lexical_signature": None,
        "vector_signature": None,
        "lexical_error": None,
        "vector_error": None,
        "updated_at": utc_now(),
    }
    current.update(expected_head=_json(head), target_generation=_head_generation(head),
                   updated_at=utc_now())
    current.update(changes)
    index._upsert(db, "memory_discovery_index_state", current)
    return current


def _strings(value):
    """Flatten only explicitly selected authored fields, preserving list order."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_strings(child))
        return result
    return []


def _owner_text(owner):
    native = owner.get("native_data", {})
    values = [owner.get("owner_id", ""), owner.get("owner_type", ""), *owner.get("aliases", [])]
    for key in ("keywords", "tags", "description", "summary"):
        values.extend(_strings(native.get(key)))
    return "\n".join(value for value in values if isinstance(value, str) and value.strip())


def _record_text(record, level):
    """Return the contracted compressed surface; None means intentionally absent."""
    payload = record.get("payload", {})
    if level == "L1":
        return description_text(record) if is_unit(record) else None
    if level == "L2":
        if record.get("schema_version") == 4 and record.get("kind") == "narrative":
            parts = [payload.get("question", "")]
            for stage in payload.get("stages", []):
                # `action` is intentionally excluded: discovery needs the
                # situation/reason/outcome spine, while complete process prose
                # remains available only after Owner selection.
                for key in ("situation", "reason", "outcome"):
                    parts.extend(_strings(stage.get(key)))
            parts.extend(_strings(payload.get("limitations")))
            return "\n".join(part for part in parts if part.strip())
        # Compatibility for old L2 shapes which did not author the compact
        # narrative fields.  The row remains one record, never its raw L0 refs.
        return record.get("body_markdown", "")
    if level == "L3":
        parts = [record.get("body_markdown", "")]
        for key in ("problem_structure", "recommendation", "applicable", "prohibited",
                    "failure_modes", "retry_conditions"):
            parts.extend(_strings(payload.get(key)))
        return "\n".join(part for part in parts if part.strip())
    if level == "L4":
        parts = [record.get("body_markdown", "")]
        for key in ("question", "methods", "results", "current_stage", "limitations", "open_questions",
                    "topic", "next_steps"):
            parts.extend(_strings(payload.get(key)))
        return "\n".join(part for part in parts if part.strip())
    return None


def _projection_id(owner_id, source_kind, source_id):
    return "DSP-" + canonical_hash({"owner_id": owner_id, "source_kind": source_kind,
                                     "source_id": source_id})[:32]


def _entry(owner, *, source_id, source_kind, source_level, source_revision,
           source_hash, title, text, fixed_ref, discovery="workspace_summary",
           sensitivity="internal"):
    value = {
        "projection_id": _projection_id(owner["owner_id"], source_kind, source_id),
        "owner_id": owner["owner_id"],
        "source_id": source_id,
        "source_kind": source_kind,
        "source_level": source_level,
        "source_revision": source_revision,
        "source_hash": source_hash,
        "title": title,
        "text": text,
        "fixed_ref": fixed_ref,
        "discovery": discovery,
        "sensitivity": sensitivity,
    }
    value["signature"] = canonical_hash({"projection_version": PROJECTION_VERSION, "entry": value})
    return value


def project_owner(catalog, owner_id):
    """Project one already-fixed Catalog snapshot without generating summaries."""
    owner = catalog.owners.get(owner_id)
    if owner is None:
        raise MemoryError("NOT_FOUND", "发现投影对象不存在", {"owner_id": owner_id})
    snapshot = catalog.snapshot(owner_id)
    generation = _head_generation(snapshot["head"])
    missing = []
    if owner.get("native_data", {}).get("sensitivity") == "restricted":
        return {"owner": owner, "snapshot": snapshot, "generation": generation,
                "entries": [], "missing": [{"owner_id": owner_id, "reason": "access_denied"}],
                "signature": canonical_hash({"projection_version": PROJECTION_VERSION, "entries": []})}

    native_sensitivity = owner.get("native_data", {}).get("sensitivity", "internal")
    _revision, owner_digest, _target_owner = catalog.target_version(
        {"target_kind": "owner", "target_id": owner_id})
    owner_ref = {"target_kind": "owner", "target_id": owner_id, "revision": None,
                 "sha256": owner_digest, "locator": owner["native_ref"]["path"],
                 "relation": "references"}
    entries = [_entry(owner, source_id=owner_id, source_kind="owner", source_level=None,
        source_revision=None, source_hash=owner_digest, title=owner["title"],
        text=_owner_text(owner), fixed_ref=owner_ref, sensitivity=native_sensitivity)]
    adapter = catalog.evidence_adapter()
    for record in snapshot["records"].values():
        try:
            level = project_memory_level(record)
        except ValueError:
            missing.append({"record_id": record.get("record_id"), "reason": "unsupported_level"})
            continue
        text = _record_text(record, level)
        # Documents, representations, L0 and legacy/non-unit L1 never enter the
        # compressed projection even if their full text is searchable elsewhere.
        if text is None:
            continue
        failures = adapter.access_errors(record["record_id"])
        if record.get("sensitivity") == "restricted" or failures:
            missing.append({"record_id": record["record_id"],
                "reason": "access_denied" if record.get("sensitivity") == "restricted" or
                    any(error["code"] in {"ACCESS_DENIED", "UNSAFE_PATH"} for error in failures) else "unavailable",
                "errors": failures})
            continue
        fixed = {"target_kind": "record", "target_id": record["record_id"],
                 # A public fixed record identity always uses record_hash.  The
                 # projection's source_hash below intentionally remains the
                 # semantic content hash for change detection.
                 "revision": record["revision"], "sha256": record["record_hash"],
                 "locator": "retrieval_description" if level == "L1" else "record",
                 "relation": "references"}
        sensitivity = max((native_sensitivity, record.get("sensitivity", "internal")),
                          key=lambda value: index.SENSITIVITY.get(value, 3))
        entries.append(_entry(owner, source_id=record["record_id"], source_kind=record["kind"],
            source_level=level, source_revision=record["revision"], source_hash=record["content_hash"],
            title=record["title"], text=text, fixed_ref=fixed, discovery=record["discovery"],
            sensitivity=sensitivity))
    signature = canonical_hash({"projection_version": PROJECTION_VERSION,
        "owner_fingerprint": owner["fingerprint"],
        "head": snapshot["head"], "entries": [[row["projection_id"], row["signature"]] for row in entries]})
    return {"owner": owner, "snapshot": snapshot, "generation": generation,
            "entries": entries, "missing": missing, "signature": signature}


def _vector_entries(entries):
    """Adapt discovery identities to the reusable local vector transport."""
    return [{"entry_id": row["projection_id"], "canonical_id": row["projection_id"],
             "owner_id": row["owner_id"], "record_id": row["source_id"],
             "representation_id": None, "title": row["title"], "text": row["text"],
             "revision": row["source_revision"], "content_hash": row["source_hash"],
             "discovery": row["discovery"], "sensitivity": row["sensitivity"],
             "signature": row["signature"]} for row in entries]


class DiscoveryVectorBackend(index.MemoryVectorBackend):
    """Same verified encoder, with a physically separate discovery collection."""
    def __init__(self, root, cfg=None):
        super().__init__(root, cfg, collection_prefix=COLLECTION_PREFIX, encoder_version=ENCODER_VERSION)


def _sync_lexical(db, projected, *, fault=lambda _point: None):
    owner_id = projected["owner"]["owner_id"]
    old = _state(db, owner_id)
    counts = {row[0]: row[1] for row in db.execute("""SELECT f.projection_id,COUNT(*)
        FROM memory_discovery_fts f JOIN memory_discovery_entries e
        ON e.projection_id=f.projection_id WHERE e.owner_id=? GROUP BY f.projection_id""", (owner_id,))}
    expected = {row["projection_id"] for row in projected["entries"]}
    physical_ready = set(counts) == expected and all(count == 1 for count in counts.values())
    if (old and old["lexical_status"] == "indexed" and old["indexed_generation"] == projected["generation"]
            and old["expected_head"] == _json(projected["snapshot"]["head"])
            and old["projection_version"] == PROJECTION_VERSION
            and old["native_fingerprint"] == projected["owner"]["fingerprint"]
            and old["lexical_signature"] == projected["signature"] and physical_ready):
        return {"status": "indexed", "changed_entries": 0, "removed_entries": 0, "unchanged": True}
    try:
        db.execute("BEGIN IMMEDIATE")
        fault("discovery_fts_begin")
        previous = {row["projection_id"]: dict(row) for row in db.execute(
            "SELECT * FROM memory_discovery_entries WHERE owner_id=?", (owner_id,))}
        current = {row["projection_id"]: row for row in projected["entries"]}
        removed = set(previous) - set(current)
        changed = [row for key, row in current.items() if key not in previous or
                   previous[key]["signature"] != row["signature"] or counts.get(key) != 1]
        for key in removed | {row["projection_id"] for row in changed}:
            db.execute("DELETE FROM memory_discovery_fts WHERE projection_id=?", (key,))
            db.execute("DELETE FROM memory_discovery_entries WHERE projection_id=?", (key,))
        import retrieval
        for row in changed:
            saved = dict(row, fixed_ref=_json(row["fixed_ref"]))
            index._upsert(db, "memory_discovery_entries", saved)
            db.execute("INSERT INTO memory_discovery_fts(projection_id,owner_id,title,text) VALUES(?,?,?,?)", (
                row["projection_id"], owner_id, " ".join(retrieval.tokens(row["title"])),
                " ".join(retrieval.tokens(row["text"]))))
            fault("discovery_fts_entry")
        _save_state(db, owner_id, projected["snapshot"]["head"],
            indexed_generation=projected["generation"], lexical_status="indexed",
            projection_version=PROJECTION_VERSION, native_fingerprint=projected["owner"]["fingerprint"],
            lexical_signature=projected["signature"], lexical_error=None)
        fault("discovery_fts_before_commit")
        db.commit()
        return {"status": "indexed", "changed_entries": len(changed),
                "removed_entries": len(removed), "unchanged": False}
    except Exception:
        db.rollback()
        raise


def _same_basis(root, owner_id, projected):
    current_owner = owners.resolve_owner(root, owner_id)
    current_head = MemoryStore(root).read_snapshot(current_owner)["head"]
    return current_head == projected["snapshot"]["head"] and current_owner["fingerprint"] == projected["owner"]["fingerprint"]


def mark_pending(root, owner_id, expected_head):
    """Invalidate both discovery lanes after a canonical commit.

    Existing rows are retained for repair diagnostics but become unreadable
    immediately because search requires an indexed watermark on the new HEAD.
    This write is derived state only and never retries the canonical commit.
    """
    root = Path(root).resolve()
    owner = owners.resolve_owner(root, owner_id)
    actual = MemoryStore(root).read_snapshot(owner)["head"]
    if actual != expected_head:
        raise MemoryError("STALE_BASIS", "不能把 discovery 待办绑定到不同 HEAD",
                          {"expected_head": expected_head, "current_head": actual})
    with closing(index.connect(root)) as db:
        value = _save_state(db, owner_id, expected_head, lexical_status="pending", vector_status="pending",
            projection_version=PROJECTION_VERSION, native_fingerprint=owner["fingerprint"],
            lexical_error=None, vector_error=None)
        db.commit()
    return value


def rebuild_owner(root, owner_id, expected_head, *, projection_version, vector="auto",
                  dry_run=False, fault=None, backend_factory=None):
    """Idempotently rebuild one fixed Owner basis; never follows a changed HEAD."""
    if projection_version != PROJECTION_VERSION:
        raise MemoryError("INVALID_ARGUMENT", "发现投影版本与当前实现不匹配",
                          {"requested": projection_version, "current": PROJECTION_VERSION})
    index._validate_vector_mode(vector)
    root = Path(root).resolve()
    fault = fault or (lambda _point: None)
    catalog = index.Catalog(root)
    if owner_id not in catalog.owners:
        raise MemoryError("NOT_FOUND", "发现投影对象不存在", {"owner_id": owner_id})
    owners.require_readable_owner(catalog.owners[owner_id])
    actual_head = catalog.snapshot(owner_id)["head"]
    if expected_head != actual_head:
        if dry_run:
            return {"owner_id": owner_id, "expected_head": expected_head, "current_head": actual_head,
                    "index_status": "stale", "dry_run": True, "writes": 0, "canonical_writes": 0}
        with closing(index.connect(root)) as db:
            state = _save_state(db, owner_id, expected_head, target_generation=_head_generation(actual_head),
                lexical_status="stale", vector_status="stale", projection_version=PROJECTION_VERSION,
                native_fingerprint=catalog.owners[owner_id]["fingerprint"],
                lexical_error=_json({"code": "STALE_BASIS", "current_head": actual_head}),
                vector_error=_json({"code": "STALE_BASIS", "current_head": actual_head}))
            db.commit()
        return {"owner_id": owner_id, "expected_head": expected_head, "current_head": actual_head,
                "index_status": "stale", "lexical": {"status": "stale"},
                "vector": {"status": "stale"}, "state": state, "missing": []}

    projected = project_owner(catalog, owner_id)
    if dry_run:
        return {"owner_id": owner_id, "expected_head": expected_head, "index_status": "preview",
                "dry_run": True, "projection_entries": len(projected["entries"]),
                "missing": projected["missing"], "writes": 0, "canonical_writes": 0}
    lexical, vector_result, error = {}, {}, None
    backend = None
    with closing(index.connect(root)) as db:
        try:
            lexical = _sync_lexical(db, projected, fault=fault)
        except Exception as exc:
            error = exc if isinstance(exc, MemoryError) else index._database_error(exc) if isinstance(exc, sqlite3.Error) else MemoryError(
                "STORAGE_ERROR", "发现词法投影同步失败", {"reason": str(exc)})
            _save_state(db, owner_id, expected_head, lexical_status="failed",
                        lexical_error=_json(error.as_dict()))
            db.commit()
        if error is None and not _same_basis(root, owner_id, projected):
            error = MemoryError("STALE_BASIS", "发现投影期间 Owner HEAD 或原生登记已变化")
            _save_state(db, owner_id, expected_head, lexical_status="stale", vector_status="stale",
                        lexical_error=_json(error.as_dict()), vector_error=_json(error.as_dict()))
            db.commit()
        elif error is None and vector == "off":
            _save_state(db, owner_id, expected_head, vector_status="disabled", vector_error=None)
            db.commit()
            vector_result = {"status": "disabled", "reason": "调用方显式关闭向量"}
        elif error is None:
            try:
                backend = (backend_factory or DiscoveryVectorBackend)(root)
                fault("discovery_vector_begin")
                vector_result = backend.sync_owner(owner_id, _vector_entries(projected["entries"]), fault=fault)
                if not _same_basis(root, owner_id, projected):
                    raise MemoryError("STALE_BASIS", "发现向量同步期间 Owner HEAD 或原生登记已变化")
                signature = canonical_hash([[row["projection_id"], row["signature"]] for row in projected["entries"]])
                _save_state(db, owner_id, expected_head, vector_generation=projected["generation"],
                    vector_status="indexed", encoder_version=ENCODER_VERSION,
                    vector_collection=backend.collection, vector_signature=signature, vector_error=None)
                db.commit()
                vector_result["status"] = "indexed"
            except Exception as exc:
                error = index.vector_error(exc)
                status_value = "unavailable" if error.code == "CAPABILITY_UNAVAILABLE" else (
                    "stale" if error.code == "STALE_BASIS" else "failed")
                _save_state(db, owner_id, expected_head, vector_status=status_value,
                            vector_error=_json(error.as_dict()))
                db.commit()
                vector_result = {"status": status_value, "error": error.as_dict()}
        state = _state(db, owner_id)
    if backend is not None:
        backend.close()
    indexed = state["lexical_status"] == "indexed" and state["vector_status"] in {"indexed", "disabled"}
    stale = "stale" in {state["lexical_status"], state["vector_status"]}
    return {"owner_id": owner_id, "expected_head": expected_head,
            "index_status": "indexed" if indexed else "stale" if stale else "pending",
            "lexical": {"status": state["lexical_status"],
                        "indexed_generation": state["indexed_generation"], **lexical},
            "vector": {"status": state["vector_status"],
                       "indexed_generation": state["vector_generation"], **vector_result},
            "state": state, "missing": projected["missing"],
            "error": error.as_dict() if error else None}


def status(root, owner_id):
    """Read current discovery readiness without creating tables or rebuilding."""
    root = Path(root).resolve()
    owner = owners.resolve_owner(root, owner_id)
    head = MemoryStore(root).read_snapshot(owner)["head"]
    db = index.connect(root, create=False)
    if db is None:
        return {"owner_id": owner_id, "index_status": "pending",
                "lexical": "not_created", "vector": "not_created", "expected_head": head}
    try:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
        if "memory_discovery_index_state" not in names:
            return {"owner_id": owner_id, "index_status": "pending",
                    "lexical": "not_created", "vector": "not_created", "expected_head": head}
        state = _state(db, owner_id)
        if state is None:
            return {"owner_id": owner_id, "index_status": "pending",
                    "lexical": "not_created", "vector": "not_created", "expected_head": head}
        basis = (state["expected_head"] == _json(head) and state["projection_version"] == PROJECTION_VERSION
                 and state["native_fingerprint"] == owner["fingerprint"])
        entry_count = db.execute("SELECT COUNT(*) FROM memory_discovery_entries WHERE owner_id=?", (owner_id,)).fetchone()[0]
        fts_count = db.execute("""SELECT COUNT(*) FROM memory_discovery_fts f
            JOIN memory_discovery_entries e ON e.projection_id=f.projection_id WHERE e.owner_id=?""", (owner_id,)).fetchone()[0]
        physical = entry_count == fts_count and entry_count > 0
        lexical = state["lexical_status"] if basis else "stale"
        if lexical == "indexed" and not physical:
            lexical = "unavailable"
        vector = state["vector_status"] if basis else "stale"
        indexed = lexical == "indexed" and vector in {"indexed", "disabled"}
        stale = "stale" in {lexical, vector}
        return {"owner_id": owner_id, "index_status": "indexed" if indexed else "stale" if stale else "pending",
                "lexical": lexical, "vector": vector, "expected_head": head,
                "projection_version": state["projection_version"], "state": state}
    finally:
        db.close()


def _eligible_states(root, owner_ids, channel):
    catalog = index.Catalog(root)
    selected = list(catalog.owners) if owner_ids is None else list(dict.fromkeys(owner_ids))
    if any(owner_id not in catalog.owners for owner_id in selected):
        raise MemoryError("NOT_FOUND", "发现查询范围含未知 Owner")
    states, ready = [], []
    for owner_id in selected:
        owner = catalog.owners[owner_id]
        if owner.get("native_data", {}).get("sensitivity") == "restricted":
            states.append({"owner_id": owner_id, "status": "unavailable", "reason": "access_denied"})
            continue
        current = status(root, owner_id)
        lane = current["lexical" if channel == "lexical" else "vector"]
        if lane == "indexed":
            ready.append(owner_id)
            states.append({"owner_id": owner_id, "status": "ready"})
        else:
            states.append({"owner_id": owner_id, "status": lane})
    return catalog, selected, ready, states


def _decode_entry(row):
    value = dict(row)
    value["fixed_ref"] = json.loads(value["fixed_ref"])
    return value


def _entry_live(catalog, row):
    """Recheck current identity and source permission before exposing cached text.

    External source permission can change without a memory HEAD commit, so a
    matching projection watermark alone is insufficient authorization.
    """
    try:
        ref = row["fixed_ref"]
        if ref["target_kind"] == "owner":
            owner = catalog.owners.get(row["owner_id"])
            if not owner or owner.get("native_data", {}).get("sensitivity") == "restricted":
                return False
            _revision, digest, _owner_id = catalog.target_version(ref)
            return digest == ref.get("sha256")
        record = catalog.record(ref["target_id"])
        if (record["revision"] != ref.get("revision") or record["record_hash"] != ref.get("sha256")
                or record.get("sensitivity") == "restricted"):
            return False
        return not catalog.evidence_adapter().access_errors(record["record_id"])
    except (MemoryError, KeyError, TypeError):
        return False


def _description_absent(description):
    """Detect only a wholly missing/blank description, never semantic coverage."""
    if not isinstance(description, dict) or not description:
        return True
    return not any(text.strip() for value in description.values() for text in _strings(value))


def search(root, query, *, owner_ids=None, channel="lexical", limit=100, backend_factory=None):
    """Search only the discovery projection; never falls back to full text."""
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise MemoryError("INVALID_ARGUMENT", "发现查询必须为 1–2000 个字符")
    if channel not in {"lexical", "dense"}:
        raise MemoryError("INVALID_ARGUMENT", "发现通道必须为 lexical 或 dense")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise MemoryError("INVALID_ARGUMENT", "发现查询 limit 必须为 1–1000")
    if owner_ids is not None and (not isinstance(owner_ids, list) or
            any(not isinstance(owner_id, str) or not owner_id for owner_id in owner_ids)):
        raise MemoryError("INVALID_ARGUMENT", "owner_ids 必须是 Owner 身份数组")
    root = Path(root).resolve()
    db = index.connect(root, create=False)
    if db is None:
        return {"status": "unavailable", "hits": [], "states": [],
                "degradation": [{"reason": "discovery_index_not_created"}]}
    try:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
        if not {"memory_discovery_entries", "memory_discovery_fts", "memory_discovery_index_state"} <= names:
            return {"status": "unavailable", "hits": [], "states": [],
                    "degradation": [{"reason": "discovery_index_not_created"}]}
        catalog, selected, ready, states = _eligible_states(root, owner_ids, channel)
        if not ready:
            return {"status": "unavailable", "hits": [], "states": states,
                    "degradation": [{"reason": "no_ready_discovery_owner"}]}
        explicit_owners = owner_ids is not None
        placeholders = ",".join("?" for _ in ready)
        by_id = {}
        for raw in db.execute("SELECT * FROM memory_discovery_entries WHERE owner_id IN (" + placeholders + ")", ready):
            row = _decode_entry(raw)
            if (row["sensitivity"] != "restricted" and (row["discovery"] != "owner_only" or explicit_owners)
                    and _entry_live(catalog, row)):
                by_id[row["projection_id"]] = row
        hits = []
        if channel == "lexical":
            import retrieval
            terms = list(dict.fromkeys(retrieval.tokens(query)))[:128]
            if not terms:
                raise MemoryError("INVALID_ARGUMENT", "发现查询没有可检索词")
            expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
            rows = db.execute("""SELECT e.projection_id,bm25(memory_discovery_fts,0.0,0.0,4.0,1.0) AS score
                FROM memory_discovery_fts JOIN memory_discovery_entries e
                ON e.projection_id=memory_discovery_fts.projection_id
                WHERE memory_discovery_fts MATCH ? ORDER BY score,e.owner_id,e.projection_id""", (expression,))
            ranked = [(by_id[row["projection_id"]], float(row["score"])) for row in rows if row["projection_id"] in by_id]
        else:
            backend = None
            try:
                backend = (backend_factory or DiscoveryVectorBackend)(root)
                raw = backend.search(query, set(by_id))
                ranked = [(by_id[row["entry_id"]], float(row.get("vector_score", 0.0)))
                          for row in raw if row.get("entry_id") in by_id]
                ranked.sort(key=lambda item: (-item[1], item[0]["owner_id"], item[0]["projection_id"]))
            finally:
                if backend is not None:
                    backend.close()
        for rank, (row, score) in enumerate(ranked[:limit], 1):
            hits.append({"owner_id": row["owner_id"], "projection_id": row["projection_id"],
                "fixed_ref": row["fixed_ref"], "source_level": row["source_level"],
                "source_kind": row["source_kind"], "title": row["title"], "text": row["text"],
                "locator": row["fixed_ref"].get("locator"), "signature": row["signature"],
                "rank": rank, "score": score, "channel": channel})
        overall = "ready" if len(ready) == len(selected) else "partial"
        degradation = [{"owner_id": state["owner_id"], "reason": state["status"]}
                       for state in states if state["status"] != "ready"]
        return {"status": overall, "hits": hits, "states": states, "degradation": degradation}
    finally:
        db.close()


def gaps(root, owner_id=None, *, offset=0, limit=50):
    """Report deterministic repair inputs; never judge semantic completeness."""
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
        raise MemoryError("INVALID_ARGUMENT", "gap 分页参数无效")
    catalog = index.Catalog(root)
    ids = [owner_id] if owner_id is not None else list(catalog.owners)
    if any(value not in catalog.owners for value in ids):
        raise MemoryError("NOT_FOUND", "gap 范围含未知 Owner")
    page = ids[offset:offset + limit]
    result = []
    for oid in page:
        owner = catalog.owners[oid]
        row_gaps = []
        if owner.get("native_data", {}).get("sensitivity") == "restricted":
            row_gaps.append({"code": "OWNER_ACCESS_DENIED"})
            result.append({"owner_id": oid, "expected_head": None, "gaps": row_gaps})
            continue
        snapshot = catalog.snapshot(oid)
        records = list(snapshot["records"].values())
        levels = []
        for record in records:
            try:
                level = project_memory_level(record)
            except ValueError:
                continue
            levels.append(level)
            if level == "L1" and record.get("kind") == "detail":
                description = record.get("payload", {}).get("retrieval_description")
                if _description_absent(description):
                    row_gaps.append({"code": "L1_RETRIEVAL_DESCRIPTION_MISSING",
                                     "record_id": record["record_id"]})
            failures = catalog.evidence_adapter().access_errors(record["record_id"])
            if failures:
                row_gaps.append({"code": "SOURCE_OR_PERMISSION_UNAVAILABLE",
                                 "record_id": record["record_id"], "errors": failures})
        if "L4" not in levels:
            row_gaps.append({"code": "MISSING_L4"})
        readiness = status(root, oid)
        if readiness["index_status"] != "indexed":
            row_gaps.append({"code": "DISCOVERY_INDEX_NOT_READY",
                             "lexical": readiness["lexical"], "vector": readiness["vector"]})
        result.append({"owner_id": oid, "expected_head": snapshot["head"], "gaps": row_gaps})
    next_offset = offset + len(page)
    return {"owners": result, "next_offset": next_offset if next_offset < len(ids) else None}
