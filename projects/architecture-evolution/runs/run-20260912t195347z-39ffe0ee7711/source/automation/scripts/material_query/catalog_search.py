"""所有来源补齐不进入普通知识 FTS 的已登记原件、章节、文稿与表示。

只用获准目录/索引定位，随后走固定读取；不会把临时缓存或任意工作区文件
当作材料，也不修改现有知识检索的索引职责。窗口不足时明确覆盖缺口。
"""
from dataclasses import asdict
import json
from memory.contracts import canonical_hash
from .contracts import FixedRef
from .validation import QueryError


def native_view(owner, native):
    """内部筛选视图，输出仍为 owner 固定引用，绝不伪造规范记录/修订。"""
    return {"owner_id": owner["owner_id"], "record_id": owner["owner_id"], "kind": "source", "level": "L0",
            "payload": native if isinstance(native, dict) else {}, "sources": [],
            "created_at": native.get("created_at") if isinstance(native, dict) else None}


def native_candidate(coordinator, state, reader, ref):
    from .coordinator import owner_allowed, record_allowed
    owner = reader.owner(ref.id)
    if state.request.purpose == "formal" or not owner_allowed(owner, state.request):
        return None
    text, native = reader.native(ref)
    if not all(record_allowed(native_view(owner, native), scope) for scope in (state.request.scope, state.request.scope_ceiling)):
        return None
    title = owner.get("title") or ref.id
    return {"candidate_id": "C-" + canonical_hash({"query": state.query_id, "ref": asdict(ref), "group": "direct"})[:24],
            "refs": [asdict(ref)], "title": title + "：原始登记", "excerpt": text[:400],
            "channels": ["catalog"], "score": 0.0, "realization": {"definition": {"key": "full", "version": "1"},
                "refs": [asdict(ref)], "state": "direct", "missing_selectors": [], "generator_version": None},
            "evidence_status": "not-assessed", "group": "direct", "hits": [], "evaluated_claim_refs": [],
            "unresolved_claim_refs": [], "unknown_facets": [], "content_kind": "source", "knowledge_type": None,
            "owner_type": owner["owner_type"], "is_latest": True}


def append_catalog(state, reader, db, manifests):
    if state.request.content_source != "all":
        return
    from .coordinator import record_allowed
    job, request = state.recall, state.request
    terms = job.get("terms", ())
    identifiers = {job["text"], *(ref.id for scope in (request.scope, request.scope_ceiling) for ref in scope.include_refs)}
    def matched(identity, text):
        return ("identity" in request.channels and identity in identifiers) or (
            "lexical" in request.channels and any(term.casefold() in text.casefold() for term in terms))
    remaining = max(0, state.ledger.remaining("candidates") - len(job["groups"]))
    existing = {g["record_id"] for g in job["groups"]}
    additions = []
    for oid, (_head, manifest) in manifests.items():
        owner = reader.owner(oid)
        # Native catalog metadata is already supplied by the authorized Owner
        # inventory. Open and fingerprint the actual card only after a match.
        native = owner["native_data"]
        if isinstance(native, dict):
            native_text = " ".join(str(native.get(key, "")) for key in ("title", "question", "keywords", "conclusion", "summary"))
        else:
            native_text = str(owner.get("title", ""))
        if all(record_allowed(native_view(owner, native), scope) for scope in (request.scope, request.scope_ceiling)) and matched(oid, native_text):
            additions.append({"record_id": oid, "native_ref": FixedRef("owner", oid, None, owner["fingerprint"], None), "matches": []})
        # This path complements only classes intentionally absent from FTS.
        # Ordinary indexed records keep their existing BM25/RRF path unchanged.
        rows = db.execute("SELECT record_id,title,body,payload FROM memory_records WHERE owner_id=? AND entity_kind='record' AND (level='L0' OR kind IN ('document','document_section')) AND sensitivity!='restricted' ORDER BY record_id LIMIT ?", (oid, remaining + 1)).fetchall()
        representations = db.execute("SELECT representation_id AS record_id,'' AS title,text AS body,'{}' AS payload FROM memory_representations WHERE owner_id=? ORDER BY representation_id LIMIT ?", (oid, remaining + 1)).fetchall()
        if len(rows) > remaining or len(representations) > remaining:
            job["gaps"].append("所有来源的目录补充达到窗口上限，尚未覆盖全部登记项")
        for row in [*rows[:remaining], *representations[:remaining]]:
            state.ledger.checkpoint()
            rid = row["record_id"]
            entry = (manifest or {}).get("record_heads", {}).get(rid)
            if rid in existing or not entry or not matched(rid, row["title"] + "\n" + row["body"] + "\n" + row["payload"]):
                continue
            existing.add(rid)
            ref = FixedRef("record", rid, entry["revision"], entry["record_hash"], None)
            job["pins"][rid] = ref
            metadata = {"canonical_id": rid, "record_id": rid, "owner_id": oid, "entity_kind": "record", "revision": ref.revision}
            additions.append({"record_id": rid, "matches": [({"rank_channels": {"catalog": 1}, "score": 0.0}, metadata)]})
    if len(additions) > remaining:
        job["gaps"].append("所有来源的补充候选达到窗口上限，尚未覆盖全部登记项")
    job["groups"].extend(additions[:remaining])
