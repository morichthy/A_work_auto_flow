"""多通道记忆检索：先过滤/回源，再按规范身份折叠与 RRF 融合。

检索身份不是证据复核。探索可以返回未复核局部经验及其边界；formal 只
采用证据服务逐次回源批准的 CLM 文本。历史必须显式请求，不污染当前 FTS。
"""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid
import unicodedata

from . import index, owners
from .contracts import SCHEMA, canonical_hash, validate_schema
from .errors import MemoryError
from .store import utc_now

STAGES = {"focus": {"limit": 6, "cross_owners": 2}, "investigate": {"limit": 14, "cross_owners": 4},
          "wide": {"limit": 24, "cross_owners": 8}}
RANKING_POLICY_VERSION = "topic-evidence-tiers-v2"
REQUEST_KEYS = {"query", "purpose", "scope", "owner_id", "owner_types", "include_ids", "full_ids", "exclude_ids",
                "stage", "budget", "history", "vector", "limit", "kinds", "levels", "retrieval_mode"}


def collapse_channel(rows):
    """同通道取每个规范 ID 的最优原名次，再连续编号，不叠加重复表示。

    输入已经按通道自己的排序排列；raw score 仅作为解释保留，不能参与
    后续跨通道数学求和。字符串列表也可用于精确数值测试。
    """
    output, seen = [], {}
    for original_rank, raw in enumerate(rows, 1):
        row = {"canonical_id": raw} if isinstance(raw, str) else dict(raw)
        cid = row.get("canonical_id")
        if not isinstance(cid, str) or not cid:
            raise MemoryError("INVALID_ARGUMENT", "通道候选缺少规范身份")
        if cid not in seen:
            current = {**row, "rank": len(output) + 1, "original_rank": original_rank, "matches": []}
            seen[cid] = current
            output.append(current)
        # 保留命中的表示/窗口身份，解释“为什么找到”，不增加排名贡献。
        evidence = {key: row[key] for key in ("entry_id", "representation_id", "vector_id", "revision", "source_id") if key in row}
        if evidence and evidence not in seen[cid]["matches"]:
            seen[cid]["matches"].append(evidence)
    return output


def rrf(channels):
    """固定 k=60 的等权 Reciprocal Rank Fusion；并列按规范 ID 升序。

    score(d)=Σ_c 1/(60+rank_c(d))，rank 从 1 开始。缺失通道没有贡献。
    每个通道在求和前再次规范折叠，防止调用者重复摘要导致名次偏置。
    """
    result = {}
    for channel, rows in channels.items():
        for row in collapse_channel(rows):
            cid = row["canonical_id"]
            item = result.setdefault(cid, {"canonical_id": cid, "score": 0.0, "rank_channels": {}, "channel_matches": {}})
            item["score"] += 1.0 / (60 + row["rank"])
            item["rank_channels"][channel] = row["rank"]
            item["channel_matches"][channel] = row.get("matches", [])
    return sorted(result.values(), key=lambda item: (-item["score"], item["canonical_id"]))


def topic_evidence_ranking(channels, records, query):
    """Prefer explicit topic evidence, retaining all other hits as fallbacks.

    ``records`` must contain only current, access-checked candidate rows. Declared
    keywords identify a topic explicitly named by the query; they are not labels
    learned from evaluation examples and never grant read access. A literal
    English identifier must match a whole token (``cat`` is not ``concatenate``).

    Within each tier the original equal-weight, k=60 RRF and canonical-ID tie
    rule remain unchanged. A matching claim precedes its broad native Run, but
    both keep their distinct identities and the Run remains selectable/readable.
    No keyword match means exactly the original ranking, including vector-only
    discovery. Missing keywords never exclude a result: those hits form tier 1.
    """
    original = rrf(channels)
    normalize = lambda value: unicodedata.normalize("NFKC", value).casefold().strip()
    query_text = normalize(query)
    keywords = {cid: {normalize(k) for k in row.get("keywords", []) if len(normalize(k)) >= 2}
                for cid, row in records.items() if row is not None}
    vocabulary = set().union(*keywords.values()) if keywords else set()
    matched = {term for term in vocabulary if (
        bool(re.search(r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])", query_text))
        if re.fullmatch(r"[a-z0-9_ -]+", term) else term in query_text)}
    # Prefer a complete declared phrase over its contained shorter keyword.
    # This is deterministic textual specificity, not a tuned score threshold.
    matched = {term for term in matched if not any(term != other and term in other for other in matched)}
    if not matched:
        return original, []
    present = {item["canonical_id"] for item in original}
    topic_ids = {cid for cid in present if keywords.get(cid, set()) & matched}
    parents = {records[cid]["owner_id"] for cid in topic_ids
               if records[cid].get("entity_kind") == "legacy-claim"}
    containers = {cid for cid in topic_ids if cid in parents and records[cid].get("entity_kind") == "legacy-run"}
    primary_ids = topic_ids - containers
    if not primary_ids:
        return original, []
    # Filter a copied channel only for the primary tier, then renumber canonical
    # ranks normally. No record, source, review state or persisted index changes.
    primary = rrf({name: [row for row in rows if
                         (row if isinstance(row, str) else row["canonical_id"]) in primary_ids]
                   for name, rows in channels.items()})
    ranked = [{**item, "priority_tier": 0} for item in primary]
    ranked.extend({**item, "priority_tier": 2 if item["canonical_id"] in containers else 1}
                  for item in original if item["canonical_id"] not in primary_ids)
    ranked.sort(key=lambda item: (item["priority_tier"], -item["score"], item["canonical_id"]))
    return ranked, sorted(matched)


def _request(request):
    errors = validate_schema(request, SCHEMA["$defs"]["SearchRequest"], SCHEMA["$defs"])
    if errors:
        raise MemoryError("INVALID_SCHEMA", "查询不符合公共契约", errors=errors)
    value = deepcopy(request)
    if not isinstance(value.get("query"), str) or not value["query"].strip() or len(value["query"]) > 2000:
        raise MemoryError("INVALID_ARGUMENT", "query 必须为 1–2000 个字符")
    if value.get("purpose") not in {"exploration", "formal"}:
        raise MemoryError("INVALID_ARGUMENT", "purpose 必须为 exploration 或 formal")
    if value["purpose"] == "formal" and (not isinstance(value.get("scope"), str) or not value["scope"].strip()):
        raise MemoryError("INVALID_ARGUMENT", "formal 查询必须指定 scope")
    value.setdefault("stage", "focus")
    value.setdefault("vector", "auto")
    value.setdefault("history", False)
    value.setdefault("retrieval_mode", "knowledge")
    if value['retrieval_mode'] == 'documents':
        if value['vector'] == 'required':
            raise MemoryError('INVALID_ARGUMENT', '文档导航检索使用固定全文通道，不包含知识向量')
        value['vector'] = 'off'
    if (not isinstance(value["stage"], str) or value["stage"] not in STAGES or not isinstance(value["vector"], str)
            or value["vector"] not in {"off", "auto", "required"} or type(value["history"]) is not bool):
        raise MemoryError("INVALID_ARGUMENT", "stage、vector 或 history 无效")
    value.setdefault("limit", STAGES[value["stage"]]["limit"])
    if type(value["limit"]) is not int or not 1 <= value["limit"] <= 100:
        raise MemoryError("INVALID_ARGUMENT", "limit 必须为 1–100 的整数")
    if "budget" in value and (type(value["budget"]) is not int or value["budget"] < 1):
        raise MemoryError("INVALID_ARGUMENT", "budget 必须为正整数 Unicode 码点预算")
    if value.get("scope") is not None and not isinstance(value["scope"], str):
        raise MemoryError("INVALID_ARGUMENT", "scope 必须为字符串或 null")
    for key in ("include_ids", "full_ids", "exclude_ids", "owner_types", "kinds", "levels"):
        value.setdefault(key, [])
        if not isinstance(value[key], list) or not all(isinstance(x, str) and x for x in value[key]):
            raise MemoryError("INVALID_ARGUMENT", key + " 必须为非空字符串数组")
        value[key] = list(dict.fromkeys(value[key]))
    if "owner_id" in value and value["owner_id"] is not None and (not isinstance(value["owner_id"], str) or not value["owner_id"]):
        raise MemoryError("INVALID_ARGUMENT", "owner_id 必须为有效对象身份或 null")
    if value["levels"] and any(level not in {"L0", "L1", "L2", "L3", "L4", "auxiliary"} for level in value["levels"]):
        raise MemoryError("INVALID_ARGUMENT", "levels 只允许 L0–L4 或 auxiliary")
    return value


def _row(row):
    value = dict(row)
    for key in ("keywords", "payload", "source_ref"):
        if isinstance(value.get(key), str):
            try:
                value[key] = json.loads(value[key])
            except ValueError as exc:
                raise MemoryError("INTEGRITY_ERROR", "派生记忆行损坏；需要重建索引") from exc
    return value


def _metadata_allowed(row, request, catalog):
    cid, oid = row["canonical_id"], row["owner_id"]
    if cid in request["exclude_ids"] or row["record_id"] in request["exclude_ids"] or oid in request["exclude_ids"]:
        return False, "explicit_exclude"
    owner = catalog.owners.get(oid)
    if owner is None:
        return False, "owner_unavailable"
    if request["owner_types"] and owner["owner_type"] not in request["owner_types"]:
        return False, "owner_type_filter"
    if request["kinds"] and row["kind"] not in request["kinds"]:
        return False, "kind_filter"
    if request["levels"] and (row["level"] or "auxiliary") not in request["levels"]:
        return False, "level_filter"
    document_kind = row['kind'] in {'document', 'document_section'}
    if request.get('retrieval_mode') == 'documents' and not document_kind:
        return False, 'document_filter'
    if document_kind and request.get('retrieval_mode') != 'documents' and cid not in set(request['include_ids'] + request['full_ids']):
        return False, 'document_navigation_only'
    if row["level"] == "L0":
        # Trace is an explicit identity lookup, not a second unrestricted raw
        # log search. Authorization, exclusions and source validity still apply.
        chosen = set(request["include_ids"] + request["full_ids"] + [request["query"].strip()])
        if request.get("retrieval_mode", "knowledge") != "trace" or cid not in chosen:
            return False, "source_trace_only"
    if row["discovery"] == "owner_only" and request.get("owner_id") != oid:
        return False, "owner_only"
    sensitivity = owner.get("native_data", {}).get("sensitivity", "internal")
    if index.SENSITIVITY.get(sensitivity, 3) >= 3 or index.SENSITIVITY.get(row["sensitivity"], 3) >= 3:
        return False, "access_denied"
    return True, None


def _boundaries(row):
    payload = row.get("payload", {})
    failure = payload.get("failure") or {}
    values = {key: deepcopy(payload.get(key, [])) for key in ("applicable", "prohibited", "failure_modes", "retry_conditions", "constraints")}
    if 'retrieval_description' in payload:
        description = payload['retrieval_description']
        values.update(applicable=deepcopy(description['applicable']), prohibited=deepcopy(description['not_applicable']),
                      not_applicable=deepcopy(description['not_applicable']), limitations=deepcopy(description['limitations']))
    if failure:
        values["tested_scope"] = failure.get("tested_scope")
        values["cannot_infer"] = failure.get("cannot_infer")
        values["retry_conditions"] = list(dict.fromkeys([*values["retry_conditions"], *failure.get("retry_conditions", [])]))
    return values


def _live(row, request, catalog, *, service):
    """候选在返回任何正文前回源，旧缓存不能扩大授权或伪装当前修订。"""
    cid, oid = row["canonical_id"], row["owner_id"]
    allowed, reason = _metadata_allowed(row, request, catalog)
    if not allowed:
        return None, {"canonical_id": cid, "reason": reason}
    owner = catalog.owners[oid]
    risks = []
    try:
        failures = (catalog.evidence_adapter().access_errors(row["record_id"], revision=row["revision"])
                    if request["history"] and row.get("revision") is not None
                    else catalog.evidence_adapter().access_errors(cid))
        if failures:
            return None, {"canonical_id": cid, "reason": "access_denied" if any(
                e["code"] in {"ACCESS_DENIED", "UNSAFE_PATH"} for e in failures) else "unavailable", "errors": failures}
        if row["entity_kind"] in {"legacy-run", "legacy-claim"}:
            current_rows = {r["canonical_id"]: r for r in index._legacy_rows(catalog, owner)}
            current = current_rows.get(cid)
            if current is None:
                return None, {"canonical_id": cid, "reason": "unavailable"}
            if current["content_hash"] != row["content_hash"]:
                # An old full-text match cannot be displayed as though the new
                # object still contained that term. A normal sync restores recall.
                return None, {"canonical_id": cid, "reason": "index_stale"}
            row = current
            record = None
            refs = owner["native_data"].get("dependencies", [])
            # The old EvidenceGraph owns native path refs; it checks enabled paths,
            # missing bytes and fingerprints without changing old review state.
            node = catalog.graph().nodes.get(cid)
            if node:
                risks.extend({"code": "STALE_BASIS", "message": text} for text in sorted(node.get("blockers", set())))
        else:
            current = catalog.record(row["record_id"])
            current_row = index._row(current, owner)
            allowed, reason = _metadata_allowed({**current_row, "canonical_id": cid}, request, catalog)
            if not allowed:
                return None, {"canonical_id": cid, "reason": reason}
            revision = row["revision"] if request["history"] else current["revision"]
            if not request["history"] and (row["revision"] != current["revision"] or
                    row["entity_kind"] == "record" and row["content_hash"] != current["content_hash"]):
                return None, {"canonical_id": cid, "reason": "index_stale"}
            record = catalog.record(row["record_id"], revision)
            claim = next((c for c in record.get("payload", {}).get("claims", []) if c["claim_id"] == cid), None) if row["entity_kind"] == "claim" else None
            if row["entity_kind"] == "claim" and claim is None:
                return None, {"canonical_id": cid, "reason": "unavailable"}
            row = index._row(record, owner, canonical_id=cid, entity_kind=row["entity_kind"], claim=claim,
                             trace=request.get("retrieval_mode") == "trace")
            row["stored_level"] = record["level"]
            if record['kind'] == 'association':
                # A successful historical Ref lookup is not proof that the
                # relation still binds the current endpoint revisions. Keep
                # history readable while explicitly marking navigation stale.
                from .associations import view as association_view
                relation_state = association_view(service, record)
                if relation_state['stale']:
                    risks.append({'code': 'STALE_ASSOCIATION', 'changed_endpoints': relation_state['changed_endpoints']})
            if revision != current["revision"]:
                risks.append({"code": "HISTORICAL_REVISION", "message": "显式历史修订；不代表当前记录", "current_revision": current["revision"]})
            refs = list(index.references(record))
            seen = set()
            for ref in refs:
                key = canonical_hash(ref)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    # Access was checked for the entire provenance closure above.
                    # Reuse the same adapter's verified record/claim versions and
                    # original-file hashes instead of rescanning every owner for
                    # each individual reference through the write-side resolver.
                    catalog.evidence_adapter()._reference(ref)
                except MemoryError as exc:
                    if exc.code in {"ACCESS_DENIED", "UNSAFE_PATH"}:
                        return None, {"canonical_id": cid, "reason": "access_denied", "target_id": ref["target_id"]}
                    if ref["target_kind"] == "file" and exc.code in {"UNRESOLVED_REFERENCE", "NOT_FOUND"}:
                        # Registry deletion or a missing original never reuses
                        # yesterday's extracted body as if it had been reloaded.
                        return None, {"canonical_id": cid, "reason": "unavailable", "target_id": ref["target_id"]}
                    risks.append({"code": exc.code, "target_id": ref["target_id"], "message": str(exc)})
        # Non-claim navigation/experience records have no independent formal
        # evidence validity. Use a real Boolean, never truthy 'unreviewed' text.
        review_state, validity = "not-reviewed", False
        if row["entity_kind"] in {"claim", "legacy-claim"}:
            try:
                state = catalog.evidence_adapter().claim_state(cid, request.get("scope"))
                review_state, validity = state["review_state"], state["effective_validity"]
                risks.extend(state.get("errors", []))
            except ImportError:
                risks.append({"code": "EVIDENCE_INELIGIBLE", "message": "证据服务尚未可用"})
        elif row["entity_kind"] == "legacy-run":
            review_state = owner["native_data"].get("review", {}).get("status", "not-reviewed")
        if any(risk.get("code") == "HISTORICAL_REVISION" for risk in risks):
            # A current review cannot validate different historical content.
            # The fixed historical Ref remains available for explicit inspection.
            validity = False
        row.update(review_state=review_state, effective_validity=validity, risks=risks)
        return row, None
    except MemoryError as exc:
        if exc.code in {"INTEGRITY_ERROR", "UNSAFE_PATH"}:
            # Corruption is not an empty search result; preserve the error contract.
            raise
        return None, {"canonical_id": cid, "reason": "unavailable", "code": exc.code}


def _history_rows(catalog, request):
    rows, seen = [], set()
    for oid, owner in catalog.owners.items():
        if request["owner_types"] and owner["owner_type"] not in request["owner_types"]:
            continue
        if oid in request["exclude_ids"] or index.SENSITIVITY.get(owner["native_data"].get("sensitivity", "internal"), 3) >= 3:
            continue
        snapshot = catalog.snapshot(oid)
        manifest = snapshot["manifest"]
        visited = set()
        while manifest:
            cid = manifest["commit_id"]
            if cid in visited:
                raise MemoryError("INTEGRITY_ERROR", "历史索引遇到提交循环")
            visited.add(cid)
            for rid, entry in manifest["record_heads"].items():
                identity = (rid, entry["revision"])
                if identity in seen:
                    continue
                seen.add(identity)
                record = catalog.store._record(owner, rid, entry)
                if record["kind"] == "representation":
                    continue
                row = index._row(record, owner)
                from .technical_units import is_unit, render_full
                # Only the ephemeral historical search text is enlarged. The
                # candidate's authored description and all canonical bytes stay
                # unchanged, and _live still checks current source permissions.
                if is_unit(record):
                    row['_history_search_text'] = row['body'] + '\n' + render_full(record)
                rows.append(row)
                for claim in record.get("payload", {}).get("claims", []):
                    rows.append(index._row(record, owner, canonical_id=claim["claim_id"], entity_kind="claim", claim=claim))
            parent = manifest["parent_commit_id"]
            manifest = catalog.store._manifest(owner, parent, manifest["parent_manifest_hash"]) if parent else None
        rows.extend(index._legacy_rows(catalog, owner))
    return rows


def _history_channel(rows, expression):
    """临时内存 FTS 与当前表同分词，历史文本从不写回当前搜索集合。"""
    import retrieval
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE VIRTUAL TABLE h USING fts5(idx UNINDEXED,title,text)")
        for number, row in enumerate(rows):
            db.execute("INSERT INTO h VALUES(?,?,?)", (number, " ".join(retrieval.tokens(row["title"])), " ".join(retrieval.tokens(row.get('_history_search_text', row["body"])))))
        results = db.execute("SELECT idx,bm25(h,0.0,4.0,1.0) AS score FROM h WHERE h MATCH ? ORDER BY score,idx", (expression,)).fetchall()
        return [{**rows[number], "fts_score": score} for number, score in results]


def _legacy_channel(db, expression, metadata, catalog):
    """已有全文通道只映射到已登记规范身份；不制造第二个 Run 或 CLM。

    旧库中未适配的自由文件仍由原全文入口提供。这里不把未知路径临时
    扩成新的访问授权，也不根据相似标题把两份不同证据合并。
    """
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    if not {"docs", "chunks", "terms"} <= tables:
        return []
    native = {}
    for cid, row in metadata.items():
        owner = catalog.owners.get(row["owner_id"])
        if row["entity_kind"] == "legacy-run" and owner:
            path = owners.safe_path(catalog.root, owner["native_ref"]["path"])
            native[str(path)] = cid
            native[str(path.parent / "README.md")] = cid
    result = []
    columns = {r[1] for r in db.execute("PRAGMA table_info(docs)")}
    if not {"id", "path", "digest", "state"} <= columns:
        return []
    rows = db.execute("""SELECT docs.id AS source_id,docs.path,docs.digest,bm25(terms,4.0,1.0) AS score
        FROM terms JOIN chunks ON chunks.id=terms.rowid JOIN docs ON docs.id=chunks.source_id
        WHERE terms MATCH ? AND docs.state='ready' ORDER BY score,docs.id,chunks.id""", (expression,))
    for row in rows:
        path = Path(row["path"])
        path = path if path.is_absolute() else catalog.root / path
        cid = native.get(str(path))
        if cid not in metadata:
            continue
        if not path.is_relative_to(catalog.root):
            continue
        checked = owners.safe_path(catalog.root, path.relative_to(catalog.root).as_posix())
        if checked.is_file() and hashlib.sha256(checked.read_bytes()).hexdigest() == row["digest"]:
            result.append({"canonical_id": cid, "source_id": row["source_id"], "fts_score": row["score"]})
    return result


def _save_query(root, value):
    folder = owners.safe_path(root, "retrieval/queries")
    folder.mkdir(parents=True, exist_ok=True)
    path = owners.safe_path(root, "retrieval/queries/" + value["query_id"] + ".json")
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.write("\n")
    except OSError as exc:
        raise MemoryError("STORAGE_ERROR", "无法保存查询回执", {"reason": str(exc)}) from exc
    return path


def search(root, request, *, refresh=False, record=True, backend_factory=None, ranking_profile="hybrid"):
    """查询规范记忆，返回排名、完整边界和真实回源风险。

    owner_id 表示当前工作的对象，不是硬性 owner 过滤：它允许看本对象
    owner_only 内容，同时从其他对象发现 workspace_summary 经验。显式
    exclude 永远优先于 include/full；这些选择被原样保存供后续展开继承。
    """
    from .service import MemoryService
    import retrieval
    started = time.perf_counter()
    root = Path(root).resolve()
    request = _request(request)
    # Internal ablation entry used by the fixed evaluation runner. Profiles only
    # remove ranking channels/representations; all access and formal evidence
    # checks still execute. Public request JSON cannot select a hidden profile.
    if ranking_profile not in {"hybrid", "legacy", "memory_single", "memory_multi"}:
        raise MemoryError("INVALID_ARGUMENT", "未知检索评价方案")
    cfg = index.configuration(root)
    terms = retrieval.expanded_terms(request["query"], cfg)
    if not terms:
        raise MemoryError("INVALID_ARGUMENT", "查询没有可检索词项")
    expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in dict.fromkeys(terms))
    db = index.connect(root, create=False)
    has_schema = bool(db and db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_records'").fetchone())
    projection_stale = False
    if has_schema:
        columns = {row[1] for row in db.execute("PRAGMA table_info(memory_index_state)")}
        projection_stale = "projection_version" not in columns
        if not projection_stale:
            projection_stale = bool(db.execute("SELECT 1 FROM memory_index_state WHERE projection_version IS NULL OR projection_version!=? LIMIT 1",
                                              (index.PROJECTION_VERSION,)).fetchone())
    if db:
        db.close()
    sync_result = None
    if refresh or not has_schema or projection_stale:
        # Initial keyword reconstruction is always available in a core install;
        # vector capability is inspected separately, without downloading a model.
        sync_result = index.reconcile(root, vector=request["vector"] if refresh else "off", backend_factory=backend_factory)
    catalog, service = index.Catalog(root), MemoryService(root)
    if request.get("owner_id") is not None and request["owner_id"] not in catalog.owners:
        raise MemoryError("NOT_FOUND", "当前查询对象不存在")
    missing = [{"canonical_id": cid, "reason": "explicit_exclude"} for cid in request["exclude_ids"]]
    degradation, channels, live, history_match = [], {}, {}, {}
    backend, vector_collection = None, None
    with closing(index.connect(root)) as db:
        metadata = {}
        for raw in db.execute("SELECT * FROM memory_records"):
            row = _row(raw)
            allowed, reason = _metadata_allowed(row, request, catalog)
            if allowed:
                metadata[row["canonical_id"]] = row
            elif row["canonical_id"] in request["include_ids"] + request["full_ids"]:
                missing.append({"canonical_id": row["canonical_id"], "reason": reason})
        def live_for(cid, candidate=None):
            key = (cid, candidate.get("revision")) if request["history"] and candidate else cid
            if key not in live:
                source = candidate if candidate is not None else metadata.get(cid)
                if source is None:
                    live[key] = None
                    return None
                current, omitted = _live(source, request, catalog, service=service)
                live[key] = current
                if omitted and omitted not in missing:
                    missing.append(omitted)
            return live[key]
        if ranking_profile == "legacy":
            channels["memory_fts"] = []
        elif request["history"] or request.get('retrieval_mode') == 'documents':
            candidates = _history_channel(_history_rows(catalog, request) if request['history'] else list(metadata.values()), expression)
            eligible = []
            for row in candidates:
                current = live_for(row["canonical_id"], row)
                if current:
                    eligible.append({"canonical_id": row["canonical_id"], "revision": row["revision"], "fts_score": row["fts_score"]})
                    history_match.setdefault(row["canonical_id"], current)
            channels["memory_fts"] = eligible
        else:
            candidates = db.execute("""SELECT e.*,bm25(memory_fts,0.0,0.0,4.0,1.0) AS score
                FROM memory_fts JOIN memory_entries e ON e.entry_id=memory_fts.entry_id
                WHERE memory_fts MATCH ? ORDER BY score,e.canonical_id,e.entry_id""", (expression,))
            eligible = []
            for candidate in candidates:
                if ranking_profile == "memory_single" and candidate["representation_id"]:
                    continue
                cid = candidate["canonical_id"]
                if cid not in metadata or candidate["sensitivity"] == "restricted":
                    continue
                if candidate["discovery"] == "owner_only" and candidate["owner_id"] != request.get("owner_id"):
                    continue
                if candidate["representation_id"] in request["exclude_ids"] or candidate["owner_id"] in request["exclude_ids"]:
                    continue
                current = live_for(cid)
                if not current:
                    continue
                if candidate["representation_id"]:
                    try:
                        rep = catalog.record(candidate["representation_id"])
                        ref = rep["payload"]["target"]
                        if ref["target_id"] != cid:
                            continue
                        revision, digest, _ = catalog.target_version(ref)
                        if (ref["target_kind"] == "record" and revision != ref["revision"]) or (ref["target_kind"] != "record" and digest != ref["sha256"]):
                            missing.append({"canonical_id": cid, "representation_id": rep["record_id"], "reason": "stale_representation"})
                            continue
                        if (rep["sensitivity"] == "restricted" or catalog.owners[rep["owner_id"]]["native_data"].get("sensitivity") == "restricted"
                                or rep["discovery"] == "owner_only" and rep["owner_id"] != request.get("owner_id")):
                            continue
                        if rep["payload"]["text"] != candidate["text"] or catalog.evidence_adapter().access_errors(rep["record_id"]):
                            missing.append({"canonical_id": cid, "representation_id": rep["record_id"], "reason": "stale_representation"})
                            continue
                    except MemoryError as exc:
                        missing.append({"canonical_id": cid, "representation_id": candidate["representation_id"], "reason": exc.code})
                        continue
                eligible.append({"canonical_id": cid, "entry_id": candidate["entry_id"], "representation_id": candidate["representation_id"],
                                 "revision": candidate["revision"], "fts_score": candidate["score"]})
            channels["memory_fts"] = eligible
        channels["legacy_fts"] = [row for row in _legacy_channel(db, expression, metadata, catalog) if live_for(row["canonical_id"])]
        legacy_native = {row["canonical_id"] for row in channels["legacy_fts"]
                         if metadata[row["canonical_id"]]["entity_kind"] == "legacy-run"}
        # A native Run's base memory text is a fallback mirror of the same
        # original already served by legacy FTS, not another independent signal.
        # Keep actual authored representations, and keep the base fallback when
        # no valid legacy hit exists. Different sources are never merged here.
        channels["memory_fts"] = [row for row in channels["memory_fts"]
            if row["canonical_id"] not in legacy_native or row.get("representation_id")]
        exact = request["query"].strip()
        if exact in metadata and live_for(exact):
            channels["identity"] = [exact]
        if request["vector"] != "off" and not request["history"]:
            try:
                backend = (backend_factory or index.MemoryVectorBackend)(root)
                vector_collection = backend.collection
                hits = backend.search(request["query"], set(metadata))
                candidates = []
                for hit in hits:
                    cid = hit["canonical_id"]
                    if cid not in metadata or not live_for(cid):
                        continue
                    entry = db.execute("SELECT * FROM memory_entries WHERE entry_id=?", (hit.get("entry_id"),)).fetchone()
                    if not entry or entry["signature"] != hit.get("signature"):
                        continue
                    if entry["sensitivity"] == "restricted" or entry["discovery"] == "owner_only" and entry["owner_id"] != request.get("owner_id"):
                        continue
                    if entry["owner_id"] in request["exclude_ids"] or entry["representation_id"] in request["exclude_ids"]:
                        continue
                    if entry["representation_id"]:
                        try:
                            rep = catalog.record(entry["representation_id"])
                            ref = rep["payload"]["target"]
                            revision, digest, _ = catalog.target_version(ref)
                            if (ref["target_id"] != cid or rep["payload"]["text"] != entry["text"] or
                                    rep["sensitivity"] == "restricted" or
                                    catalog.owners[rep["owner_id"]]["native_data"].get("sensitivity") == "restricted" or
                                    rep["discovery"] == "owner_only" and rep["owner_id"] != request.get("owner_id") or
                                    ref["target_kind"] == "record" and revision != ref["revision"] or
                                    ref["target_kind"] != "record" and digest != ref["sha256"] or
                                    catalog.evidence_adapter().access_errors(rep["record_id"])):
                                continue
                        except MemoryError:
                            continue
                    if hit.get("vector_score", 0.0) < cfg.get("vector_min_score", 0.2):
                        continue
                    candidates.append(hit)
                channels["vector"] = candidates
            except Exception as exc:
                error = index.vector_error(exc)
                if request["vector"] == "required":
                    raise error
                degradation.append({"channel": "vector", "code": error.code, "reason": str(error), "details": error.details})
            finally:
                if backend is not None:
                    backend.close()
        elif request["history"] and request["vector"] != "off":
            if request["vector"] == "required":
                raise MemoryError("CAPABILITY_UNAVAILABLE", "历史修订不写当前向量集合；请用 vector=off 显式历史全文查询")
            degradation.append({"channel": "vector", "reason": "历史模式使用独立临时 FTS，避免污染当前向量集合"})
        if ranking_profile == "legacy":
            channels = {"legacy_fts": channels["legacy_fts"]}
        elif ranking_profile in {"memory_single", "memory_multi"}:
            channels = {key: value for key, value in channels.items() if key != "vector"}
            if ranking_profile == "memory_single":
                channels["memory_fts"] = [row for row in channels["memory_fts"] if not row.get("representation_id")]
        topic_terms = []
        # Exact identities, explicit historical reads and formal projection keep
        # their existing semantics. The v2 policy addresses exploratory discovery
        # without weakening access checks or changing accepted-evidence gates.
        if (ranking_profile != "legacy" and request["purpose"] == "exploration"
                and not request["history"] and request["query"].strip() not in metadata):
            candidate_ids = {item["canonical_id"] for item in rrf(channels)}
            ranked, topic_terms = topic_evidence_ranking(
                channels, {cid: live_for(cid) for cid in candidate_ids}, request["query"])
        else:
            ranked = rrf(channels)
        explicit = [cid for cid in dict.fromkeys(request["full_ids"] + request["include_ids"]) if cid not in request["exclude_ids"]]
        if request["retrieval_mode"] == "trace" and request["query"].strip() in metadata:
            explicit = list(dict.fromkeys([*explicit, request["query"].strip()]))
        ranked_ids = {item["canonical_id"] for item in ranked}
        for cid in explicit:
            if cid not in metadata:
                if not any(x.get("canonical_id") == cid for x in missing):
                    missing.append({"canonical_id": cid, "reason": "unavailable_or_filtered"})
                continue
            if cid not in ranked_ids and live_for(cid):
                ranked.append({"canonical_id": cid, "score": 0.0, "rank_channels": {}, "channel_matches": {}, "explicit": True})
        # Explicit selection affects inclusion, not the mathematical RRF score.
        ranked.sort(key=lambda item: (0 if item["canonical_id"] in explicit else 1,
                                     item.get("priority_tier", 0), -item["score"], item["canonical_id"]))
        result_rows, other_owners = [], set()
        for rank in ranked:
            cid = rank["canonical_id"]
            current = history_match.get(cid) if request["history"] and cid in history_match else live_for(cid)
            if not current:
                continue
            oid = current["owner_id"]
            if oid != request.get("owner_id") and oid not in other_owners:
                if len(other_owners) >= STAGES[request["stage"]]["cross_owners"]:
                    missing.append({"canonical_id": cid, "reason": "cross_owner_limit"})
                    continue
                other_owners.add(oid)
            result_rows.append({**rank, "revision": current["revision"], "owner_id": oid, "record_id": current["record_id"],
                "kind": current["kind"], "level": current["level"], "effective_level": current["level"],
                "stored_level": current.get("stored_level", "L1" if current["entity_kind"].startswith("legacy-") else current["level"]),
                "taxonomy_version": 2, "title": current["title"],
                "roles": ["claim" if current["entity_kind"] in {"claim", "legacy-claim"} else current["kind"]],
                "match_reason": {"channels": list(rank["rank_channels"]), "terms": terms,
                                 "ranking_policy": RANKING_POLICY_VERSION, "topic_terms": topic_terms,
                                 "priority_tier": rank.get("priority_tier", 0),
                                 "representations": rank["channel_matches"], "explicit_selection": cid in explicit},
                "snippet": current["body"][:400], "boundaries": _boundaries(current), "source_ref": current["source_ref"],
                "content_hash": current["content_hash"], "review_state": current["review_state"],
                "effective_validity": current["effective_validity"], "risks": current["risks"],
                "historical": any(r.get("code") == "HISTORICAL_REVISION" for r in current["risks"]),
                "expansion_paths": [{"owner_id": oid, "record_id": current["record_id"], "revision": current["revision"]}]})
            if len(result_rows) >= request["limit"]:
                break
        source_heads = {oid: snapshot["head"] for oid, snapshot in catalog.snapshots.items()}
        if catalog._adapter is not None:
            source_heads.update(catalog._adapter.source_heads)
        index_states = [dict(row) for row in db.execute("SELECT * FROM memory_index_state")]
    rejected = []
    if request["purpose"] == "formal":
        from .evidence_adapter import formal_projection
        projection = formal_projection(root, [item["source_ref"] for item in result_rows], request["scope"], service=service)
        approved = {item["canonical_id"]: item for item in projection["claims"]}
        rejected = projection["rejected"]
        formal_rows = []
        for cid, claim in approved.items():
            row = next((item for item in result_rows if item["canonical_id"] == cid), None)
            if row is None:
                row = next((item for item in result_rows if item["record_id"] == claim.get("record_id") or
                            item["canonical_id"] == claim.get("owner_id")), None)
            if row is None:
                # An accepted claim reached through a navigation record still has
                # its own identity and fixed Ref; it never inherits map prose.
                row = {"score": 0.0, "rank_channels": {}, "channel_matches": {}, "boundaries": {},
                       "match_reason": {"channels": ["formal_projection"]}, "risks": [], "historical": False}
            ref = {"target_kind": "claim", "target_id": cid, "revision": None, "sha256": claim["sha256"],
                   "locator": "statement", "relation": "references"}
            formal_rows.append({**row, **claim, "source_ref": ref, "roles": ["claim"], "snippet": claim["text"]})
        result_rows = sorted(formal_rows, key=lambda item: (-item["score"], item["canonical_id"]))[:request["limit"]]
        source_heads.update(projection.get("source_heads", {}))
    result = {"query_id": "QMEM-" + str(uuid.uuid4()), "created_at": utc_now(), "query": request["query"],
        "query_fingerprint": canonical_hash({"request": request, "source_heads": source_heads, "encoder_version": index.ENCODER_VERSION,
                                             "vector_collection": vector_collection, "config": cfg, "ranking_profile": ranking_profile,
                                             "ranking_policy": RANKING_POLICY_VERSION}),
        "scope": request.get("scope"), "purpose": request["purpose"], "retrieval_mode": request["retrieval_mode"],
        "selection": {**{key: request[key] for key in ("include_ids", "full_ids", "exclude_ids", "stage")},
                      "budget": request.get("budget", min(16000, cfg.get("context_chars", 16000)))},
        "source_heads": source_heads, "candidates": result_rows, "missing": missing, "rejected": rejected,
        "degradation": degradation, "index_state": index_states, "sync_result": sync_result,
        "vector_collection": vector_collection, "timings": {"total_seconds": time.perf_counter() - started}}
    result["ranking_profile"] = ranking_profile
    if record:
        _save_query(root, result)
    return result
