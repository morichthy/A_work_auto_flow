"""记忆派生索引：独立 SQLite 表、原子 FTS 水位和可补偿向量水位。

规范记录仍由 HEAD/不可变提交负责。本模块只写 retrieval/generated 与本地
Qdrant 集合，任何索引错误都不能撤销业务提交或伪造第二条记录。当前修订
进入排名，历史修订只由显式历史读取展开；旧 docs/chunks/terms 表完全保留。
"""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

from .contracts import canonical_hash, project_memory_level
from .errors import MemoryError
from . import owners
from .store import MemoryStore, utc_now

SCHEMA_VERSION = 1
PROJECTION_VERSION = "memory-v3-technical-description-documents"
ENCODER_VERSION = "memory-record-representation-v3-technical-description"
SENSITIVITY = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def database_path(root):
    """复用旧检索库文件，避免创建第二套正式存储或修改旧 schema 版本号。"""
    return owners.safe_path(Path(root).resolve(), "retrieval/generated/search.sqlite3")


def connect(root, *, create=True):
    """只登记 memory_* 表；不修改 PRAGMA user_version 或旧全文表。

    读路径可以 create=False；不存在时返回 None，不把一次空查询伪装成已建
    索引。短超时把另一个写者映射为 LOCKED，调用方可以稍后 reconcile。
    """
    path = database_path(root)
    if not path.exists() and not create:
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        db = sqlite3.connect(path, timeout=2.0)
        db.row_factory = sqlite3.Row
        if create:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memory_schema (version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS memory_owners (
                    owner_id TEXT PRIMARY KEY, owner_type TEXT NOT NULL, native_ref TEXT NOT NULL,
                    native_fingerprint TEXT NOT NULL, head TEXT, generation INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS memory_records (
                    canonical_id TEXT PRIMARY KEY, record_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                    entity_kind TEXT NOT NULL, kind TEXT NOT NULL, level TEXT,
                    revision INTEGER, content_hash TEXT NOT NULL, title TEXT NOT NULL,
                    body TEXT NOT NULL, keywords TEXT NOT NULL, payload TEXT NOT NULL,
                    discovery TEXT NOT NULL, sensitivity TEXT NOT NULL, source_ref TEXT NOT NULL,
                    signature TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS memory_record_owner ON memory_records(owner_id);
                CREATE TABLE IF NOT EXISTS memory_representations (
                    target_id TEXT NOT NULL, slot TEXT NOT NULL, representation_id TEXT NOT NULL UNIQUE,
                    owner_id TEXT NOT NULL, target_revision INTEGER, source_hash TEXT,
                    text TEXT NOT NULL, active INTEGER NOT NULL, reason TEXT,
                    signature TEXT NOT NULL, PRIMARY KEY(target_id,slot));
                CREATE TABLE IF NOT EXISTS memory_entries (
                    entry_id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                    record_id TEXT NOT NULL, representation_id TEXT, signature TEXT NOT NULL,
                    title TEXT NOT NULL, text TEXT NOT NULL, revision INTEGER,
                    content_hash TEXT NOT NULL, discovery TEXT NOT NULL, sensitivity TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS memory_entry_owner ON memory_entries(owner_id);
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    entry_id UNINDEXED, canonical_id UNINDEXED, title, text);
                CREATE TABLE IF NOT EXISTS memory_edges (
                    association_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL, relation TEXT NOT NULL, status TEXT NOT NULL,
                    source_versions TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS memory_index_state (
                    owner_id TEXT PRIMARY KEY, indexed_generation INTEGER,
                    vector_generation INTEGER, target_generation INTEGER NOT NULL,
                    fts_status TEXT NOT NULL, vector_status TEXT NOT NULL,
                    encoder_version TEXT, vector_collection TEXT, native_fingerprint TEXT,
                    dependency_signature TEXT, vector_signature TEXT, error TEXT,
                    updated_at TEXT NOT NULL);
            """)
            versions = [row[0] for row in db.execute("SELECT version FROM memory_schema")]
            if not versions:
                db.execute("INSERT INTO memory_schema VALUES(?)", (SCHEMA_VERSION,))
            elif versions != [SCHEMA_VERSION]:
                raise MemoryError("INTEGRITY_ERROR", "记忆索引 schema 不受支持；保留现场后使用匹配版本迁移")
            # This is a disposable index watermark, not a canonical migration.
            # Old records/HEADs and the older retrieval tables stay untouched.
            # NULL on an old row forces a real projection refresh before reuse.
            columns = {row[1] for row in db.execute("PRAGMA table_info(memory_index_state)")}
            if "projection_version" not in columns:
                db.execute("ALTER TABLE memory_index_state ADD COLUMN projection_version TEXT")
            db.commit()
        return db
    except sqlite3.Error as exc:
        if 'db' in locals():
            db.close()
        raise _database_error(exc) from exc
    except Exception:
        if 'db' in locals():
            db.close()
        raise


def _database_error(exc):
    code = "LOCKED" if "locked" in str(exc).lower() or "busy" in str(exc).lower() else "STORAGE_ERROR"
    return MemoryError(code, "记忆派生数据库不可用", {"reason": str(exc)})


def configuration(root):
    """仅读本机配置；缺文件表示没有向量能力，绝不联网补齐。"""
    path = owners.safe_path(Path(root).resolve(), "retrieval/config.json")
    if not path.exists():
        return {"vector_store": {"provider": None}, "aliases": {}, "candidate_limit": 100}
    return owners._read(path)


def references(value):
    """遍历正式固定引用；missing_refs 是声明缺口，不能伪装成有效来源。"""
    if isinstance(value, dict):
        if "target_kind" in value and "target_id" in value:
            yield value
        else:
            for key, child in value.items():
                if key != "missing_refs":
                    yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


class Catalog:
    """一次操作内复用只读快照；下一次查询必须重新取得，不把缓存当权限。

    每个 record/claim 沿用原身份。旧 Run 提供 RUN-ID 的 L2 事件视图；其 CLM
    原地索引，不创建重复 MEM-event 或第二个结论身份。
    """
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.store = MemoryStore(self.root)
        self.owners = {view["owner_id"]: view for view in owners.list_owners(self.root)}
        self.snapshots = {}
        self.locations = {}
        self.claims = {}
        self._evidence = None
        self._adapter = None

    def snapshot(self, owner_id):
        if owner_id not in self.owners:
            raise MemoryError("NOT_FOUND", "索引目标对象不存在", {"owner_id": owner_id})
        if owner_id not in self.snapshots:
            value = self.store.read_snapshot(self.owners[owner_id])
            for rid, record in value["records"].items():
                if rid in self.locations and self.locations[rid] != owner_id:
                    raise MemoryError("INTEGRITY_ERROR", "规范记录身份重复", {"record_id": rid})
                self.locations[rid] = owner_id
                for claim in record.get("payload", {}).get("claims", []):
                    cid = claim["claim_id"]
                    if cid in self.claims and self.claims[cid][1]["record_id"] != rid:
                        raise MemoryError("INTEGRITY_ERROR", "结论身份重复", {"claim_id": cid})
                    self.claims[cid] = (claim, record)
            self.snapshots[owner_id] = value
        return self.snapshots[owner_id]

    def record(self, record_id, revision=None):
        if self._adapter is not None and record_id in self._adapter.records:
            # EvidenceAdapter already verified every immutable record and HEAD
            # in this request. Re-reading all files of the same owner here would
            # double the scan without obtaining a newer coherent snapshot.
            current = self._adapter.records[record_id]
            oid = current["owner_id"]
            self.locations[record_id] = oid
            if revision is None or revision == current["revision"]:
                return current
            return self.store.read_record(self.owners[oid], record_id, revision)
        if record_id not in self.locations:
            for owner_id in self.owners:
                self.snapshot(owner_id)
                if record_id in self.locations:
                    break
        oid = self.locations.get(record_id)
        if oid is None:
            raise MemoryError("NOT_FOUND", "规范记录不存在", {"record_id": record_id})
        current = self.snapshot(oid)["records"][record_id]
        if revision is None or current["revision"] == revision:
            return current
        return self.store.read_record(self.owners[oid], record_id, revision)

    def graph(self):
        if self._evidence is None:
            import evidence
            self._evidence = evidence.EvidenceGraph(self.root)
            if self._evidence.errors:
                raise MemoryError("INTEGRITY_ERROR", "旧证据元数据损坏", {"errors": self._evidence.errors})
        return self._evidence

    def evidence_adapter(self):
        """一次操作复用 W04 只读检查器；每次查询重新建立来源权限快照。"""
        if self._adapter is None:
            from .service import MemoryService
            from .evidence_adapter import EvidenceAdapter
            self._adapter = EvidenceAdapter(MemoryService(self.root), _owner_views=self.owners.values())
            for oid, snapshot in self.snapshots.items():
                if snapshot["head"] != self._adapter.source_heads.get(oid):
                    raise MemoryError("STALE_BASIS", "规范 HEAD 在一次检索快照读取期间变化", {"owner_id": oid})
            self.claims.update(self._adapter.claims)
        return self._adapter

    def target_version(self, ref):
        """表示只能绑定当前目标版本；原表示修订保留，但过期文本不参与排名。"""
        tid, kind = ref["target_id"], ref["target_kind"]
        if kind == "record":
            record = self.record(tid)
            return record["revision"], record["content_hash"], record["owner_id"]
        if kind == "owner":
            owner = self.owners.get(tid)
            if not owner:
                raise MemoryError("NOT_FOUND", "表示目标对象不存在")
            node = self.graph().nodes.get(tid)
            return None, node["fingerprint"] if node else owner["fingerprint"], tid
        if kind == "claim":
            node = self.graph().nodes.get(tid)
            if node:
                return None, node["fingerprint"], node["owner"]
            for oid in self.owners:
                self.snapshot(oid)
            if tid in self.claims:
                claim, record = self.claims[tid]
                return None, canonical_hash(claim), record["owner_id"]
            raise MemoryError("NOT_FOUND", "表示目标结论不存在")
        # 文件表示也只能来自登记，不能把自由路径引入全文读取。
        from .service import MemoryService
        resolved = MemoryService(self.root)._resolve_ref(ref, {}, [])
        return None, resolved["sha256"], None


def _row(record, owner, *, canonical_id=None, entity_kind="record", claim=None, trace=False):
    payload = record.get("payload", {})
    title = claim["statement"] if claim else record["title"]
    body = claim["statement"] if claim else record["body_markdown"]
    # 将结构字段作为可检索文本，同时保留完整 payload 供有边界的展开。
    # 不加入审计时间/作者/哈希，避免纯技术词成为虚假的内容匹配依据。
    searchable = _searchable_payload(payload)
    if record['kind'] == 'detail' and record.get('schema_version') == 3:
        from .technical_units import description_text
        body, searchable = description_text(record), ''
        # The derived row needs applicability and reference metadata, not a
        # second copy of the complete technical blocks/figures in SQLite.
        payload = {key: value for key, value in payload.items() if key not in {'blocks', 'figures'}}
    level = project_memory_level(record)
    if level == "L0" and not trace:
        # Keep only identity/locator metadata in the derived catalogue. Raw
        # evidence text must not enter normal FTS, vector text or summaries.
        body, searchable = "", ""
    native_level = owner.get("native_data", {}).get("sensitivity", "internal")
    sensitivity = max((record.get("sensitivity", "internal"), native_level), key=lambda x: SENSITIVITY.get(x, 3))
    cid = canonical_id or record["record_id"]
    ref = {"target_kind": "claim" if claim else "record", "target_id": cid,
           "revision": None if claim else record["revision"],
           "sha256": canonical_hash(claim) if claim else None, "locator": "statement" if claim else "record",
           "relation": "references"}
    row = dict(canonical_id=cid, record_id=record["record_id"], owner_id=owner["owner_id"],
        entity_kind=entity_kind, kind=record["kind"], level=level, revision=record["revision"],
        content_hash=canonical_hash(claim) if claim else record["content_hash"], title=title,
        body=body + ("\n" + searchable if searchable else ""), keywords=record.get("keywords", []),
        payload=payload, discovery=record["discovery"], sensitivity=sensitivity, source_ref=ref)
    row["signature"] = canonical_hash({"projection_version": PROJECTION_VERSION, "row": row})
    return row


def _searchable_payload(payload):
    fields = {"question", "objective", "hypothesis", "action", "observation", "decision", "topic",
              "problem_structure", "recommendation", "applicable", "prohibited", "failure_modes",
              "retry_conditions", "next_steps", "constraints", "success_criteria", "missing_evidence",
              "next_step", "stop_reason", "blocker", "reopen_condition", "method", "steps", "results",
              'purpose', 'audience', 'scope'}
    values = []
    for key in sorted(fields):
        value = payload.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(v for v in value if isinstance(v, str))
    # Only authored scientific fields are indexed. Ref hashes, file paths and
    # server-owned audit metadata remain out of keyword and vector matching.
    for parameter in payload.get("parameters", []):
        if isinstance(parameter, dict):
            values.extend(str(parameter[key]) for key in ("name", "value", "unit", "description") if parameter.get(key) is not None)
    for formula in payload.get("formulas", []):
        if isinstance(formula, dict):
            values.append(formula.get("latex", ""))
    for figure in payload.get("figures", []):
        if isinstance(figure, dict):
            values.append(figure.get("caption", ""))
    # Index authored report prose only; referenced detail and raw evidence
    # retain their own access-checked rows rather than being copied here.
    report = payload.get('report', {})
    if report:
        values.append(report.get('title', ''))
        for section in report.get('sections', []):
            values.append(section.get('title', ''))
            values.extend(block['markdown'] for block in section.get('blocks', []) if block.get('type') == 'prose')
    values.extend(block['markdown'] for block in payload.get('blocks', []) if block.get('type') == 'prose')
    return "\n".join(values)


def _legacy_rows(catalog, owner):
    """适配只读取旧原生事实；不从展示 Markdown 创造额外身份。"""
    native, oid = owner["native_data"], owner["owner_id"]
    if owner["owner_type"] != "run":
        return []
    graph = catalog.graph()
    node = graph.nodes.get(oid)
    fingerprint = node["fingerprint"] if node else owner["fingerprint"]
    payload = {"question": native.get("question", ""), "action": native.get("run_type", ""),
               "observation": native.get("conclusion", ""), "failure_modes": native.get("limitations", []),
               "claims": native.get("claims", [])}
    base = dict(canonical_id=oid, record_id=oid, owner_id=oid, entity_kind="legacy-run", kind="event", level="L2",
        revision=None, content_hash=fingerprint, title=owner["title"], body=_searchable_payload(payload),
        keywords=native.get("keywords", []), payload=payload, discovery=native.get("discovery", "workspace_summary"),
        sensitivity=native.get("sensitivity", "internal"), source_ref={"target_kind": "owner", "target_id": oid,
            "revision": None, "sha256": fingerprint, "locator": "run.json", "relation": "references"})
    base["signature"] = canonical_hash(base)
    result = [base]
    for claim in native.get("claims", []):
        node = graph.nodes.get(claim["claim_id"])
        digest = node["fingerprint"] if node else canonical_hash(claim)
        row = {**base, "canonical_id": claim["claim_id"], "entity_kind": "legacy-claim",
               "title": claim["statement"], "body": claim["statement"], "content_hash": digest,
               "source_ref": {"target_kind": "claim", "target_id": claim["claim_id"], "revision": None,
                              "sha256": digest, "locator": "statement", "relation": "references"}}
        row["signature"] = canonical_hash({k: v for k, v in row.items() if k != "signature"})
        result.append(row)
    return result


def _entry(row, *, representation=None):
    entry = dict(entry_id=("REPRESENTATION:" + representation["representation_id"]) if representation else row["canonical_id"],
        canonical_id=row["canonical_id"], owner_id=representation["owner_id"] if representation else row["owner_id"],
        record_id=row["record_id"], representation_id=representation["representation_id"] if representation else None,
        title=row["title"], text=representation["text"] if representation else row["body"] + "\n" + " ".join(row["keywords"]),
        revision=row["revision"], content_hash=row["content_hash"], discovery=row["discovery"], sensitivity=row["sensitivity"])
    entry["signature"] = canonical_hash({"projection_version": PROJECTION_VERSION, "entry": entry})
    return entry


def project_owner(catalog, owner_id):
    """当前规范快照→派生行；丢失/过期表示只保存风险元数据、不保存可检索正文。"""
    owner = catalog.owners[owner_id]
    snapshot = catalog.snapshot(owner_id)
    rows = _legacy_rows(catalog, owner)
    representations, edges, entries, missing = [], [], [], []
    for record in snapshot["records"].values():
        if record["kind"] == "representation":
            continue
        row = _row(record, owner)
        rows.append(row)
        for claim in record.get("payload", {}).get("claims", []):
            rows.append(_row(record, owner, canonical_id=claim["claim_id"], entity_kind="claim", claim=claim))
        if record["kind"] == "association":
            payload = record["payload"]
            edges.append(dict(association_id=record["record_id"], owner_id=owner_id,
                from_id=payload["from"]["target_id"], to_id=payload["to"]["target_id"], relation=payload["relation"],
                status=payload["status"], source_versions=[payload["from"], payload["to"]]))
    # A restricted owner is not indexed into FTS/vector text at all. Its canonical
    # files remain unchanged; later permission expansion requires a fresh sync.
    visible_rows = []
    for row in rows:
        failures = catalog.evidence_adapter().access_errors(row["canonical_id"])
        if row["sensitivity"] == "restricted" or failures:
            missing.append({"canonical_id": row["canonical_id"], "reason": "access_denied" if row["sensitivity"] == "restricted" or
                any(e["code"] in {"ACCESS_DENIED", "UNSAFE_PATH"} for e in failures) else "unavailable",
                "errors": failures})
        else:
            visible_rows.append(row)
    rows = visible_rows
    by_id = {row["canonical_id"]: row for row in rows}
    entries.extend(_entry(row) for row in rows if row["level"] != "L0" and row['kind'] not in {'document', 'document_section'})
    for record in snapshot["records"].values():
        if record["kind"] != "representation":
            continue
        payload = record["payload"]
        target = payload["target"]
        rep = dict(target_id=target["target_id"], slot=payload["slot"], representation_id=record["record_id"],
                   owner_id=owner_id, target_revision=target["revision"], source_hash=target["sha256"],
                   text=payload["text"], active=1, reason=None)
        try:
            revision, digest, target_owner = catalog.target_version(target)
            failures = catalog.evidence_adapter().access_errors(record["record_id"])
            if failures:
                rep.update(active=0, reason="access_denied" if any(e["code"] in {"ACCESS_DENIED", "UNSAFE_PATH"} for e in failures) else "unavailable")
            if (target["target_kind"] == "record" and revision != target["revision"]) or (
                    target["target_kind"] != "record" and digest != target["sha256"]):
                rep.update(active=0, reason="stale_target")
            row = by_id.get(target["target_id"])
            if not row and target["target_kind"] == "record":
                target_record = catalog.record(target["target_id"])
                row = _row(target_record, catalog.owners[target_owner])
            elif not row and target["target_kind"] in {"claim", "owner"} and target_owner:
                # Cross-owner representations retain the target's canonical ID.
                # Resolve only its native rows, avoiding recursive representation
                # expansion when two owners refer to one another.
                row = next((value for value in _legacy_rows(catalog, catalog.owners[target_owner])
                            if value["canonical_id"] == target["target_id"]), None)
                if row is None and target["target_id"] in catalog.claims:
                    claim, target_record = catalog.claims[target["target_id"]]
                    row = _row(target_record, catalog.owners[target_owner],
                               canonical_id=target["target_id"], entity_kind="claim", claim=claim)
            if row and row["sensitivity"] == "restricted":
                rep.update(active=0, reason="access_denied")
            if row and row["level"] == "L0":
                # A translation or paraphrase cannot turn evidence-only source
                # text into a knowledge candidate, including cross-owner reps.
                rep.update(active=0, reason="source_trace_only")
            if row and row['kind'] in {'document', 'document_section'}:
                rep.update(active=0, reason='document_navigation_only')
            if record["sensitivity"] == "restricted" or owner["native_data"].get("sensitivity") == "restricted":
                rep.update(active=0, reason="access_denied")
            if row and rep["active"]:
                entry = _entry(row, representation=rep)
                # Neither the representation's own discovery nor sensitivity can
                # widen the target record's boundary. An owner_only representation
                # stays local even when its target is discoverable workspace-wide.
                if record["discovery"] == "owner_only":
                    entry["discovery"] = "owner_only"
                entry["sensitivity"] = max((entry["sensitivity"], record["sensitivity"]), key=lambda x: SENSITIVITY.get(x, 3))
                entry["signature"] = canonical_hash({k: v for k, v in entry.items() if k != "signature"})
                entries.append(entry)
            elif not row and rep["active"]:
                rep.update(active=0, reason="target_not_indexable")
        except MemoryError as exc:
            rep.update(active=0, reason=exc.code)
        if not rep["active"]:
            missing.append({"canonical_id": rep["target_id"], "representation_id": rep["representation_id"], "reason": rep["reason"]})
            rep["text"] = ""  # Never retain forbidden/stale prose in a live FTS row.
        rep["signature"] = canonical_hash(rep)
        representations.append(rep)
    generation = snapshot["head"]["generation"] if snapshot["head"] else 0
    return dict(owner=owner, snapshot=snapshot, generation=generation, rows=rows, entries=entries,
                representations=representations, edges=edges, missing=missing,
                dependency_signature=canonical_hash({"projection_version": PROJECTION_VERSION, "representations": representations,
                    "native_fingerprint": owner["fingerprint"], "records": [[r["canonical_id"], r["signature"]] for r in rows]}))


def _upsert(db, table, value, *, json_fields=()):
    fields = list(value)
    data = [_json(value[key]) if key in json_fields else value[key] for key in fields]
    sql = "INSERT OR REPLACE INTO " + table + " (" + ",".join(fields) + ") VALUES(" + ",".join("?" for _ in fields) + ")"
    db.execute(sql, data)


def _state(db, owner_id):
    row = db.execute("SELECT * FROM memory_index_state WHERE owner_id=?", (owner_id,)).fetchone()
    return dict(row) if row else None


def _save_state(db, owner_id, generation, **changes):
    value = _state(db, owner_id) or dict(owner_id=owner_id, indexed_generation=None, vector_generation=None,
        target_generation=generation, fts_status="pending", vector_status="pending", encoder_version=None,
        vector_collection=None, native_fingerprint=None, dependency_signature=None, vector_signature=None, error=None, updated_at=utc_now())
    value.update(target_generation=generation, updated_at=utc_now(), **changes)
    _upsert(db, "memory_index_state", value)
    return value


def _sync_fts(db, projected, *, fault=lambda _point: None, force=False):
    """一笔 SQLite 事务同时更新内容与 FTS 水位，异常不会留下假成功水位。"""
    import retrieval
    oid = projected["owner"]["owner_id"]
    owner = projected["owner"]
    old = _state(db, oid)
    fts_counts = {row[0]: row[1] for row in db.execute("""SELECT f.entry_id,COUNT(*) FROM memory_fts f
        JOIN memory_entries e ON e.entry_id=f.entry_id WHERE e.owner_id=? GROUP BY f.entry_id""", (oid,))}
    expected_entries = {row["entry_id"] for row in projected["entries"]}
    physical_ready = set(fts_counts) == expected_entries and all(count == 1 for count in fts_counts.values())
    if (not force and old and old["indexed_generation"] == projected["generation"] and old["dependency_signature"] == projected["dependency_signature"]
            and old.get("projection_version") == PROJECTION_VERSION
            and old["fts_status"] == "indexed" and physical_ready):
        return {"changed_entries": 0, "removed_entries": 0, "unchanged": True}
    try:
        db.execute("BEGIN IMMEDIATE")
        fault("fts_begin")
        # Every table is owned independently. Only this object's rows are touched;
        # vector IDs and watermarks for all other owners remain unchanged.
        previous = {row["entry_id"]: dict(row) for row in db.execute("SELECT * FROM memory_entries WHERE owner_id=?", (oid,))}
        current = {row["entry_id"]: row for row in projected["entries"]}
        removed = set(previous) - set(current)
        # Explicit repair restores text even if IDs/generation look current,
        # inside this transaction so no half-built generation becomes visible.
        changed = [row for key, row in current.items() if force or key not in previous or previous[key]["signature"] != row["signature"] or fts_counts.get(key) != 1]
        for key in removed | {row["entry_id"] for row in changed}:
            db.execute("DELETE FROM memory_fts WHERE entry_id=?", (key,))
            db.execute("DELETE FROM memory_entries WHERE entry_id=?", (key,))
        for row in changed:
            _upsert(db, "memory_entries", row)
            db.execute("INSERT INTO memory_fts(entry_id,canonical_id,title,text) VALUES(?,?,?,?)", (
                row["entry_id"], row["canonical_id"], " ".join(retrieval.tokens(row["title"])), " ".join(retrieval.tokens(row["text"]))))
            fault("fts_entry")
        for table in ("memory_records", "memory_representations", "memory_edges"):
            db.execute("DELETE FROM " + table + " WHERE owner_id=?", (oid,))
        for row in projected["rows"]:
            collision = db.execute("SELECT owner_id FROM memory_records WHERE canonical_id=?", (row["canonical_id"],)).fetchone()
            if collision and collision[0] != oid:
                raise MemoryError("INTEGRITY_ERROR", "不同对象声明重复规范身份", {"canonical_id": row["canonical_id"]})
            _upsert(db, "memory_records", row, json_fields=("keywords", "payload", "source_ref"))
        for row in projected["representations"]:
            collision = db.execute("SELECT representation_id FROM memory_representations WHERE target_id=? AND slot=?", (row["target_id"], row["slot"])).fetchone()
            if collision and collision[0] != row["representation_id"]:
                raise MemoryError("INVALID_SCHEMA", "target+slot 存在两个规范表示", {"target_id": row["target_id"], "slot": row["slot"]})
            _upsert(db, "memory_representations", row)
        for row in projected["edges"]:
            _upsert(db, "memory_edges", row, json_fields=("source_versions",))
        _upsert(db, "memory_owners", dict(owner_id=oid, owner_type=owner["owner_type"], native_ref=_json(owner["native_ref"]),
            native_fingerprint=owner["fingerprint"], head=_json(projected["snapshot"]["head"]), generation=projected["generation"]))
        _save_state(db, oid, projected["generation"], indexed_generation=projected["generation"], fts_status="indexed",
                    native_fingerprint=owner["fingerprint"], dependency_signature=projected["dependency_signature"],
                    projection_version=PROJECTION_VERSION, error=None)
        fault("fts_before_commit")
        db.commit()
        return {"changed_entries": len(changed), "removed_entries": len(removed), "unchanged": False}
    except Exception:
        db.rollback()
        raise


class MemoryVectorBackend:
    """既有本地 384 维编码器的记忆集合适配，不下载、不替换模型。

    向量窗口携带 entry/canonical/owner/版本，窗口和多个表示在查询通道内
    折叠。集合身份包含模型实际清单、FastEmbed 版本及记忆编码版本。
    """
    def __init__(self, root, cfg=None):
        import qdrant_backend
        self.root = Path(root).resolve()
        cfg = configuration(root) if cfg is None else cfg
        if not qdrant_backend.enabled(cfg):
            raise MemoryError("CAPABILITY_UNAVAILABLE", "未配置本地向量后端")
        setting = cfg.get("embedding", {})
        # 首版迁移契约只接受已验证的标准模型与相对路径；其他模型必须先
        # 同步配置迁移/维度契约，不能依赖后端接受任意名称而暗示可迁移。
        if (setting.get("model") != DEFAULT_MODEL or setting.get("path") != "services/qdrant/models/multilingual-minilm"
                or setting.get("manifest", "services/qdrant/model-manifest.json") != "services/qdrant/model-manifest.json"):
            raise MemoryError("CAPABILITY_UNAVAILABLE", "记忆向量只支持当前已验证标准模型名称与路径")
        owners.safe_path(self.root, setting["path"])
        owners.safe_path(self.root, setting.get("manifest", "services/qdrant/model-manifest.json"))
        owners.safe_path(self.root, cfg["vector_store"].get("path", "services/qdrant/storage"))
        try:
            self.backend = qdrant_backend.LocalBackend(self.root, cfg, collection_prefix="memory_v1",
                encoding_version=ENCODER_VERSION, expected_dimensions=384)
        except Exception as exc:
            raise vector_error(exc) from exc
        self.collection = self.backend.collection

    def close(self):
        self.backend.close()

    def _filter(self, **conditions):
        models = self.backend.models
        filters = []
        for key, value in conditions.items():
            match = models.MatchAny(any=value) if isinstance(value, list) else models.MatchValue(value=value)
            filters.append(models.FieldCondition(key=key, match=match))
        return models.Filter(must=filters)

    def sync_owner(self, owner_id, entries, *, previous_entries=None, fault=lambda _point: None):
        """只重建变化 entry 的窗口，保持其他对象及未变化向量 ID 不变。

        删除/插入可能部分完成，但水位只在全部成功后推进；query 会核对
        SQLite 版本与当前源，失败条目不可冒充新版本。reconcile 可幂等补偿。
        """
        from qdrant_client.models import PointStruct, FilterSelector
        client, backend = self.backend.client, self.backend
        active = {entry["entry_id"]: entry for entry in entries}
        points, offset = [], None
        existing = {}
        while True:
            batch, offset = client.scroll(self.collection, scroll_filter=self._filter(owner_id=owner_id),
                limit=256, offset=offset, with_payload=True, with_vectors=False)
            for point in batch:
                payload = point.payload or {}
                existing.setdefault(payload.get("entry_id"), []).append((str(point.id), payload.get("signature"), payload.get("window_count")))
            if offset is None:
                break
        removed = set(existing) - set(active)
        changed = [entry for eid, entry in active.items() if eid not in existing or
                   any(sig != entry["signature"] or window_count != len(existing[eid]) for _, sig, window_count in existing[eid])]
        # Count/digest checks above also repair a vector collection removed outside
        # SQLite; a watermark alone never proves the physical points still exist.
        for eid in sorted(removed | {entry["entry_id"] for entry in changed}):
            fault("vector_delete")
            client.delete(self.collection, points_selector=FilterSelector(filter=self._filter(owner_id=owner_id, entry_id=eid)), wait=True)
        for entry in changed:
            encoding = backend.tokenizer.encode(entry["text"], add_special_tokens=False)
            offsets = encoding.offsets
            title_tokens = backend.tokenizer.encode(entry["title"], add_special_tokens=False)
            prefix = backend.tokenizer.decode(title_tokens.ids[:40])
            texts, payloads, identities = [], [], []
            for start_token in range(0, len(offsets), 300):
                window = offsets[start_token:start_token + 360]
                if not window:
                    continue
                start, end = window[0][0], window[-1][1]
                payload = {key: entry[key] for key in ("entry_id", "canonical_id", "owner_id", "record_id",
                    "representation_id", "revision", "content_hash", "discovery", "sensitivity", "signature")}
                payload.update(start=start, end=end, encoder_version=ENCODER_VERSION)
                identity = f"{self.collection}:{entry['entry_id']}:{entry['signature']}:{start}:{end}"
                identities.append(str(uuid.uuid5(uuid.NAMESPACE_URL, identity)))
                payloads.append(payload)
                texts.append(prefix + "\n" + entry["text"][start:end])
            # Empty structured records still have titles; retain one explicit title
            # window so auxiliary entities do not disappear silently from vectors.
            if not texts:
                payload = {key: entry[key] for key in ("entry_id", "canonical_id", "owner_id", "record_id",
                    "representation_id", "revision", "content_hash", "discovery", "sensitivity", "signature")}
                payload.update(start=0, end=0, encoder_version=ENCODER_VERSION)
                identities = [str(uuid.uuid5(uuid.NAMESPACE_URL, self.collection + ":" + entry["entry_id"] + ":" + entry["signature"] + ":title"))]
                payloads, texts = [payload], [prefix]
            fault("vector_encode")
            vectors = list(backend.model.passage_embed(texts, batch_size=16))
            if len(vectors) != len(texts) or any(len(vector) != 384 for vector in vectors):
                raise MemoryError("CAPABILITY_UNAVAILABLE", "编码器返回数量或维度不符合 384 维契约")
            for payload in payloads:
                payload["window_count"] = len(texts)
            points = [PointStruct(id=pid, vector=vector.tolist(), payload=payload)
                      for pid, vector, payload in zip(identities, vectors, payloads)]
            for at in range(0, len(points), 64):
                fault("vector_upsert")
                client.upsert(self.collection, points[at:at + 64], wait=True)
        return {"collection": self.collection, "updated_entries": len(changed), "removed_entries": len(removed),
                "points": client.count(self.collection, count_filter=self._filter(owner_id=owner_id), exact=True).count}

    def search(self, query, allowed_ids):
        """先限当前获准规范 ID，再取窗口排名；不以窗口数量决定记录名次。

        查询全部获准窗口再折叠，避免十个同义表示挤掉第二条规范记录。
        不返回向量本身，资源成本由点数量/10k记录基准单独测量。
        """
        if not allowed_ids:
            return []
        query_filter = self._filter(canonical_id=sorted(allowed_ids))
        count = self.backend.client.count(self.collection, count_filter=query_filter, exact=True).count
        if count == 0:
            return []
        vector = next(self.backend.model.query_embed(query)).tolist()
        if len(vector) != 384:
            raise MemoryError("CAPABILITY_UNAVAILABLE", "查询向量维度不是 384")
        result = self.backend.client.query_points(self.collection, query=vector, limit=count,
            query_filter=query_filter, with_payload=True, with_vectors=False)
        return [{**(point.payload or {}), "vector_score": float(point.score), "vector_id": str(point.id)} for point in result.points]


def vector_error(exc):
    if isinstance(exc, MemoryError):
        return exc
    reason = str(exc)
    code = "LOCKED" if "locked" in reason.lower() or "already accessed" in reason.lower() else (
        "STORAGE_ERROR" if isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError) else "CAPABILITY_UNAVAILABLE")
    return MemoryError(code, "本地记忆向量不可用；未联网或更换模型", {"reason": reason})


def _validate_vector_mode(value):
    if value not in {"off", "auto", "required"}:
        raise MemoryError("INVALID_ARGUMENT", "vector 必须为 off、auto 或 required")


def status(root, owner_id):
    """只读对比真实 HEAD 与两个索引水位；不会建库或再次运行模型。

    供 inspect/幂等重试展示当前状态。旧提交回执仍保持原样，派生状态
    可以改善；不能为了让回执变绿重做业务提交。
    """
    root = Path(root).resolve()
    owner = owners.resolve_owner(root, owner_id)
    snapshot = MemoryStore(root).read_snapshot(owner)
    generation = snapshot["head"]["generation"] if snapshot["head"] else 0
    db = connect(root, create=False)
    state = None
    if db is not None:
        try:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_index_state'").fetchone():
                state = _state(db, owner_id)
        finally:
            db.close()
    if state is None:
        return {"owner_id": owner_id, "generation": generation, "index_status": "pending",
                "index_details": {"fts": "not_created", "vector": "not_created", "indexed_generation": None,
                    "vector_generation": None, "reason": "派生索引尚未建立；规范记录仍从 HEAD 可读"}}
    native_matches = state["native_fingerprint"] == owner["fingerprint"]
    # A matching HEAD alone does not make an index built with the old layer
    # taxonomy current. Read-only status reports pending until reprojection.
    projection_matches = state.get("projection_version") == PROJECTION_VERSION
    fts_ready = state["fts_status"] == "indexed" and state["indexed_generation"] == generation and native_matches and projection_matches
    vector_ready = state["vector_status"] == "disabled" or (state["vector_status"] == "indexed" and state["vector_generation"] == generation and native_matches and projection_matches and state["encoder_version"] == ENCODER_VERSION)
    return {"owner_id": owner_id, "generation": generation, "index_status": "indexed" if fts_ready and vector_ready else "pending",
        "index_details": {"fts": state["fts_status"] if fts_ready else "pending" if state["fts_status"] == "indexed" else state["fts_status"],
            "vector": state["vector_status"] if vector_ready else "pending" if state["vector_status"] == "indexed" else state["vector_status"],
            "indexed_generation": state["indexed_generation"], "vector_generation": state["vector_generation"],
            "target_generation": generation, "encoder_version": state["encoder_version"],
            "collection": state["vector_collection"], "error": json.loads(state["error"]) if state.get("error") else None}}


def sync_owner(root, owner_id, generation=None, *, vector="auto", fault=None, backend_factory=None, catalog=None):
    """同步一份当前 HEAD；返回 FTS/向量独立结果，失败保留规范待办。

    backend_factory/fault 仅供可信 Python 集成测试注入，CLI 不接受这些字段。
    传 generation 时必须与实际 HEAD 一致，不能把旧代次写成当前成功水位。
    """
    _validate_vector_mode(vector)
    root = Path(root).resolve()
    fault = fault or (lambda _point: None)
    catalog = catalog or Catalog(root)
    if owner_id not in catalog.owners:
        raise MemoryError("NOT_FOUND", "索引对象不存在", {"owner_id": owner_id})
    projected = project_owner(catalog, owner_id)
    current = projected["generation"]
    if generation is not None and (type(generation) is not int or generation != current):
        raise MemoryError("STALE_BASIS", "索引目标代次已变化", {"requested_generation": generation, "current_generation": current})
    started = time.perf_counter()
    error, fts_details, vector_details = None, {}, {}
    backend = None
    try:
        with closing(connect(root)) as db:
            try:
                fts_details = _sync_fts(db, projected, fault=fault)
            except (sqlite3.Error, OSError, MemoryError) as exc:
                error = exc if isinstance(exc, MemoryError) else _database_error(exc) if isinstance(exc, sqlite3.Error) else MemoryError("STORAGE_ERROR", "FTS 同步失败", {"reason": str(exc)})
                _save_state(db, owner_id, current, fts_status="failed", error=_json(error.as_dict()))
                db.commit()
            if error is None:
                if vector == "off":
                    _save_state(db, owner_id, current, vector_status="disabled")
                    vector_details = {"status": "disabled", "reason": "调用方显式关闭向量"}
                    db.commit()
                else:
                    try:
                        backend = (backend_factory or MemoryVectorBackend)(root)
                        fault("vector_begin")
                        vector_details = backend.sync_owner(owner_id, projected["entries"], fault=fault)
                        # A concurrent business commit cannot retroactively change
                        # this snapshot. Keep its actual watermark and pending state
                        # rather than claiming the newer HEAD has already been read.
                        observed = MemoryStore(root).read_snapshot(owners.resolve_owner(root, owner_id))["head"]
                        if observed != projected["snapshot"]["head"]:
                            raise MemoryError("STALE_BASIS", "向量同步期间 HEAD 已变化")
                        signature = canonical_hash([[entry["entry_id"], entry["signature"]] for entry in projected["entries"]])
                        _save_state(db, owner_id, current, vector_generation=current, vector_status="indexed", encoder_version=ENCODER_VERSION,
                            vector_collection=backend.collection, vector_signature=signature, error=None)
                        vector_details["status"] = "indexed"
                    except Exception as exc:
                        error = vector_error(exc)
                        _save_state(db, owner_id, current, vector_status="pending" if error.code == "CAPABILITY_UNAVAILABLE" else "failed", error=_json(error.as_dict()))
                        vector_details = {"status": "pending" if error.code == "CAPABILITY_UNAVAILABLE" else "failed", "error": error.as_dict()}
                    db.commit()
            state = _state(db, owner_id)
    except (MemoryError, sqlite3.Error, OSError) as exc:
        # Even when the derived database itself is unavailable, each immutable
        # commit already contains index_pending. Reconcile starts from HEAD after
        # the storage issue is removed, so no business retry is required.
        error = exc if isinstance(exc, MemoryError) else _database_error(exc) if isinstance(exc, sqlite3.Error) else MemoryError("STORAGE_ERROR", "索引存储不可用", {"reason": str(exc)})
        state = {"indexed_generation": None, "vector_generation": None, "target_generation": current,
                 "fts_status": "failed", "vector_status": "pending"}
    finally:
        if backend is not None:
            backend.close()
    success = state["fts_status"] == "indexed" and state["vector_status"] in {"indexed", "disabled"}
    return {"owner_id": owner_id, "generation": current, "index_status": "indexed" if success else "pending",
            "fts": {"status": state["fts_status"], "indexed_generation": state["indexed_generation"], **fts_details},
            "vector": {"status": state["vector_status"], "indexed_generation": state["vector_generation"], **vector_details},
            "state": state, "missing": projected["missing"], "error": error.as_dict() if error else None,
            "elapsed_seconds": time.perf_counter() - started}


def _prune_missing_owners(root, active_ids, *, vector="auto", backend_factory=None):
    """删除登记后的派生可见性也需要补偿；不删除任何规范文件。"""
    with closing(connect(root)) as db:
        removed = [row[0] for row in db.execute("SELECT owner_id FROM memory_owners") if row[0] not in active_ids]
        for oid in removed:
            keys = [row[0] for row in db.execute("SELECT entry_id FROM memory_entries WHERE owner_id=?", (oid,))]
            for key in keys:
                db.execute("DELETE FROM memory_fts WHERE entry_id=?", (key,))
            for table in ("memory_records", "memory_entries", "memory_edges", "memory_representations", "memory_owners"):
                db.execute("DELETE FROM " + table + " WHERE owner_id=?", (oid,))
            # Keep a durable tombstone until the vector backend confirms removal.
            _save_state(db, oid, 0, fts_status="removed", indexed_generation=0, vector_status="pending")
        db.commit()
        pending = [row[0] for row in db.execute("SELECT owner_id FROM memory_index_state WHERE fts_status='removed' AND vector_status!='removed'")]
        if vector != "off" and pending:
            backend = None
            try:
                backend = (backend_factory or MemoryVectorBackend)(root)
                for oid in pending:
                    backend.sync_owner(oid, [])
                    _save_state(db, oid, 0, vector_status="removed", vector_generation=0, error=None)
                db.commit()
            except Exception as exc:
                db.rollback()
                for oid in pending:
                    _save_state(db, oid, 0, error=_json(vector_error(exc).as_dict()))
                db.commit()
            finally:
                if backend is not None:
                    backend.close()
        unresolved = [row[0] for row in db.execute(
            "SELECT owner_id FROM memory_index_state WHERE fts_status='removed' AND vector_status!='removed'")]
        return removed, unresolved if vector != "off" else []


def reconcile(root, owner_id=None, *, vector="auto", fault=None, backend_factory=None):
    """从规范 HEAD 重放持久待办；不会再次 commit 或修改历史回执。"""
    _validate_vector_mode(vector)
    catalog = Catalog(root)
    ids = [owner_id] if owner_id is not None else list(catalog.owners)
    results = [sync_owner(root, oid, vector=vector, fault=fault, backend_factory=backend_factory, catalog=catalog) for oid in ids]
    removed, pending = _prune_missing_owners(root, set(catalog.owners), vector=vector, backend_factory=backend_factory) if owner_id is None else ([], [])
    return {"index_status": "indexed" if not pending and all(r["index_status"] == "indexed" for r in results) else "pending",
            "owners": results, "removed_owners": removed, "pending_removals": pending, "canonical_writes": 0}


def rebuild(root, scope=None, dry_run=False, *, vector="auto", fault=None, backend_factory=None):
    """按受控对象重建；预览零写入，保留旧全文表和所有规范版本。

    不先删除整个数据库；逐 owner 的原子 FTS 事务允许中断后从现有水位
    继续。物理索引被删除时同一入口直接重新生成，因此无需重放业务提交。
    """
    _validate_vector_mode(vector)
    catalog = Catalog(root)
    ids = list(catalog.owners) if scope is None else ([scope] if isinstance(scope, str) else list(scope))
    if any(oid not in catalog.owners for oid in ids):
        raise MemoryError("NOT_FOUND", "重建范围含未知对象")
    if dry_run:
        return {"dry_run": True, "owner_ids": ids, "database": str(database_path(root)), "canonical_writes": 0, "writes": 0}
    # Force physical FTS reconstruction even if the watermark survived while a
    # user deleted its virtual table contents. Only selected owner states change.
    with closing(connect(root)) as db:
        for oid in ids:
            db.execute("UPDATE memory_index_state SET fts_status='pending',dependency_signature=NULL WHERE owner_id=?", (oid,))
            # Drop derived entries for this owner so each current entry is inserted
            # again. This transaction cannot affect the old docs/chunks/terms.
            for row in db.execute("SELECT entry_id FROM memory_entries WHERE owner_id=?", (oid,)).fetchall():
                db.execute("DELETE FROM memory_fts WHERE entry_id=?", (row[0],))
            db.execute("DELETE FROM memory_entries WHERE owner_id=?", (oid,))
        db.commit()
    results = [sync_owner(root, oid, vector=vector, fault=fault, backend_factory=backend_factory, catalog=catalog) for oid in ids]
    removed, pending = _prune_missing_owners(root, set(catalog.owners), vector=vector, backend_factory=backend_factory) if scope is None else ([], [])
    return {"dry_run": False, "index_status": "indexed" if not pending and all(r["index_status"] == "indexed" for r in results) else "pending",
            "owners": results, "removed_owners": removed, "pending_removals": pending, "canonical_writes": 0}
