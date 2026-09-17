"""查询、选择与组包的应用编排；不更换既有规范存储或生成业务结论。

仅对已有FTS索引做有界候选读取，随后逐项固定来源核验；结果数量限制不能
变成全库正文读取。结构筛选和正式证据准入在最终K之前执行，预算不足明示。
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
import threading
import uuid

from memory import index
from memory.contracts import canonical_hash
from memory.errors import MemoryError
from memory.search import rrf

from . import definitions, representations
from .assembly import Assembler
from .budget import DEFAULT_BUDGET, SERVER_LIMITS
from .contracts import AssembleRequest, FixedRef, QueryRequest
from .legacy_adapter import fixed_record, memory_error, to_legacy
from .reader import Reader
from .state import StateStore
from .validation import QueryError, parse
from .wire import digest, json_value, observe_basis


def envelope(value=None, *, state=None, status="ok", code=None, warnings=(), basis=None, stop=None, issues=()):
    warnings = list(dict.fromkeys(warnings))
    issues = json_value(issues)
    # Existing human-readable warnings remain compatible; never guess which
    # fixed reference a provider-wide warning affects from its free text.
    described = {item["message"] for item in issues}
    issues += [{"code": code or "PARTIAL", "message": message, "affected_refs": [],
                "retry": retry_hint(code or "PARTIAL")} for message in warnings if message not in described]
    return {"status": status, "value": value, "code": code, "warnings": warnings, "issues": issues,
            "consumed": state.ledger.snapshot() if state else {key: 0 for key in asdict(DEFAULT_BUDGET)},
            "stop_reason": stop, "basis": observe_basis(basis)}


def retry_hint(code):
    """重试描述恢复条件；预算/CAS/TTL 变化需要新计划，不能盲目重放。"""
    if code in {"BUDGET", "CONFLICT", "EXPIRED", "STALE", "CANCELLED"}:
        return "replan"
    if code in {"DENIED", "SOURCE_MISSING", "UNSUPPORTED", "PARTIAL", "INDEX_PENDING"}:
        return "after_external_change"
    return "same_request" if code == "RUNNING" else "never"


def failure(exc, state=None, *, value=None, basis=None):
    if isinstance(exc, MemoryError):
        exc = memory_error(exc)
    if not isinstance(exc, QueryError):
        exc = QueryError("INTERNAL", "材料查询执行失败")
    status = "cancelled" if exc.code == "CANCELLED" else "partial" if value is not None else "rejected" if exc.code in {
        "VALIDATION", "DENIED", "CONFLICT", "EXPIRED", "UNSUPPORTED", "STALE", "BUDGET", "SOURCE_MISSING"} else "failed"
    # Only already observed references may enter a public issue. In particular,
    # denied requests must not disclose caller-supplied identities or locators.
    observed = (json_value(basis) or {}).get("refs", [])
    affected = [] if exc.code == "DENIED" else [json_value(ref) for ref in exc.affected_refs if json_value(ref) in observed]
    issue = {"code": exc.code, "message": exc.message, "affected_refs": affected,
             "retry": exc.retry or retry_hint(exc.code)}
    return envelope(value, state=state, status=status, code=exc.code, warnings=(exc.message,), basis=basis, stop=exc.code.lower(), issues=[issue])


def excluded(request):
    return {item for scope in (request.scope, request.scope_ceiling) for item in (
        *scope.excluded_owner_ids, *scope.exclude_ids, *(ref.id for ref in scope.excluded_refs))}


def _date_match(raw, start, before):
    if not raw:
        return False
    try:
        date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return (start is None or date >= datetime.fromisoformat(start.replace("Z", "+00:00"))) and (
            before is None or date < datetime.fromisoformat(before.replace("Z", "+00:00")))
    except (ValueError, TypeError):
        return False


def record_allowed(record, scope, *, evidence=None):
    """不同维度AND，单维度OR；Unknown只在显式允许时匹配未知，而非所有值。"""
    oid, rid, payload = record["owner_id"], record["record_id"], record.get("payload", {})
    if oid in scope.excluded_owner_ids or rid in scope.exclude_ids or oid in scope.exclude_ids or any(r.id == rid for r in scope.excluded_refs):
        return False
    if scope.owner_ids is not None and oid not in scope.owner_ids:
        return False
    if scope.kinds is not None and record["kind"] not in scope.kinds:
        return False
    if scope.levels is not None and (record.get("level") or "unlayered") not in scope.levels:
        return False
    if scope.source_ids is not None and not {r["target_id"] for r in record.get("sources", [])} & set(scope.source_ids):
        return False
    if scope.recorded_from is not None or scope.recorded_before is not None:
        if not _date_match(record.get("created_at") or record.get("recorded_at"), scope.recorded_from, scope.recorded_before):
            return False
    if scope.time_window:
        window = scope.time_window
        raw = record.get("created_at") if window.field == "recorded_at" else payload.get(window.field)
        if not _date_match(raw, window.start_inclusive, window.end_exclusive):
            return False
    from .facets import matches, record_matches
    if not record_matches(record, scope, evidence):
        return False
    review = (evidence or {}).get("state", "not-reviewed")
    validity = (evidence or {}).get("validity", "unknown")
    values = ((scope.review_states, review if isinstance(review, list) else [review]),
              (scope.validities, validity if isinstance(validity, list) else [validity]))
    for expected, actual in values:
        if not matches(expected, actual, scope.include_unknown):
            return False
    return True


def filtered_claim_states(reader, record, request, claim_ids=None):
    """Intersect review and validity filters on each same current claim."""
    from .evidence import Evidence
    from .facets import confidence_levels, matches
    states = Evidence(reader).assess(record, request.applicability or None)
    if claim_ids is not None:
        states = [item for item in states if item["claim_id"] in claim_ids]
    for item in states:
        item["validity"] = "valid" if item["effective_validity"] else "unknown" if item["review_state"] == "not-reviewed" else "invalid"
    return [item for item in states if all(
        matches(scope.review_states, [item["review_state"]], scope.include_unknown) and
        matches(scope.validities, [item["validity"]], scope.include_unknown) and
        matches(scope.confidence_levels, confidence_levels(record, scope, [(item["claim_id"], item["sha256"])]), scope.include_unknown)
        for scope in (request.scope, request.scope_ceiling))]


def evidence_summary(states):
    # Keep the assessed targets internally so confidence filtering cannot borrow
    # a different claim's level after per-claim review/validity intersection.
    return {"state": sorted({item["review_state"] for item in states}), "validity": sorted({item["validity"] for item in states}),
            "assessed_claims": [(item["claim_id"], item["sha256"]) for item in states]}


def current_scope_allows(reader, record, request):
    owner = reader.owner(record["owner_id"])
    if not owner_allowed(owner, request):
        return False
    # 当前策略在搜索、展开、组装和缓存重取时都核对，不能仅在初次召回执行。
    if getattr(request, "freshness", "fixed") == "current":
        _, manifest = reader.store.head_manifest(owner)
        latest = (manifest or {}).get("record_heads", {}).get(record["record_id"])
        if latest is None or latest["record_hash"] != record["record_hash"]:
            raise QueryError("STALE", "固定材料已有新修订，请重新查询；没有自动替换正文")
    evidence = None
    if any(scope.review_states is not None or scope.validities is not None or scope.confidence_levels is not None for scope in (request.scope, request.scope_ceiling)):
        states = filtered_claim_states(reader, record, request)
        if not states and any(scope.review_states is not None or scope.validities is not None for scope in (request.scope, request.scope_ceiling)):
            return False
        evidence = evidence_summary(states)
    return all(record_allowed(record, scope, evidence=evidence) for scope in (request.scope, request.scope_ceiling))


def owner_allowed(owner, request):
    """标准对象类型与具体身份相交，不依赖标题前缀或存储路径猜测类别。"""
    return all((scope.owner_ids is None or owner["owner_id"] in scope.owner_ids)
               and (scope.owner_types is None or owner["owner_type"] in scope.owner_types)
               for scope in (request.scope, request.scope_ceiling))


def required_scope_allows(reader, record, request):
    """显式依赖按读取上限核验，主输出的分类不剥离必需定义。

    Reader 仍持有两个范围的排除合集与可信 ACL。只有已经声明为必需的
    固定引用使用此路径；它不能把未命中材料插入直接召回或放宽版本策略。
    """
    return current_scope_allows(reader, record, replace(request, scope=request.scope_ceiling))


class Coordinator:
    def __init__(self, root, *, access_owner_ids=None, state_store=None, ranking_strategies=None):
        self.root = Path(root).resolve()
        # Trusted Python construction only; HTTP body cannot grant this access.
        self.access_owner_ids = None if access_owner_ids is None else tuple(access_owner_ids)
        self.store = state_store or StateStore()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="material-query")
        self.ranking_strategies = {"rrf": self._rrf, "topic-evidence-v2": self._topic_rank}
        if ranking_strategies:
            self.ranking_strategies.update(ranking_strategies)

    def capabilities(self):
        return {"enabled": True, "api_version": "0.2", "definitions_version": definitions.VERSION,
                "content_sources": ["overview_experience", "process", "technical", "all"],
                "content_expansion": ["process", "technical"],
                "full_documents": True,
                "owner_types": ["research", "project", "knowledge", "run", "core-algorithm", "report", "data", "tool"],
                "default_freshness": "current",
                "association": {"modes": ["off", "existing_only"], "strategy": "existing-relations", "version": "1", "structural_requires_review": True},
                "deepening": {"modes": ["source_mapping", "bounded_graph"], "strategy": "bounded-bfs", "version": "1"},
                "maintenance": {"strategy": "dependency-review", "version": "1", "automatic_agent": False, "task_package": True},
                "limits": asdict(SERVER_LIMITS), "default_budget": asdict(DEFAULT_BUDGET), "query_ttl_seconds": self.store.ttl,
                "channels": ["identity", "lexical"], "ranking_strategies": sorted(self.ranking_strategies),
                "model_providers": [], "tokenizers": [],
                "model_metering": "无已注册模型/分词计量策略；模型预算字段不是已配置模型的证明",
                "definition_alias_resolution": "foundation/definition-resolve"}

    def reader(self, state):
        # A prerequisite may lie outside the selected output scope, but it must
        # never cause body IO beyond the immutable owner ceiling or trusted ACL.
        allowed = self.access_owner_ids
        ceiling = state.request.scope_ceiling.owner_ids
        if ceiling is not None:
            allowed = tuple(ceiling) if allowed is None else tuple(set(allowed) & set(ceiling))
        return Reader(self.root, state.ledger, access_owner_ids=allowed, excluded_ids=excluded(state.request))

    def _new(self, request):
        request = parse(json_value(request), QueryRequest)
        definitions.get(request.definition)
        for fallback in request.fallback_definitions:
            definitions.get(fallback)
        if request.dialect != "plain":
            raise QueryError("UNSUPPORTED", "首期词法提供器只支持plain查询；不静默改变布尔/短语语义")
        if request.allow_index_repair or request.max_staleness_seconds is not None:
            raise QueryError("UNSUPPORTED", "查询内索引修复与按秒过期容忍尚未注册；请使用显式索引维护入口")
        if request.ranking_strategy not in self.ranking_strategies or request.ranking_version != "1":
            raise QueryError("UNSUPPORTED", "排序策略或版本未注册")
        if request.association.mode not in {"off", "existing_only"}:
            raise QueryError("UNSUPPORTED", "结构探索需要真实语义审查，当前可导出任务包使用Skill")
        if request.association.strategy != "existing-relations" or request.association.strategy_version != "1":
            raise QueryError("UNSUPPORTED", "联想策略或版本未注册")
        return self.store.create(request)

    def start(self, request):
        state = None
        try:
            state = self._new(request)
            self.executor.submit(self._run_search, state)
            return envelope({"query_id": state.query_id, "state": "running"}, state=state)
        except (QueryError, MemoryError) as exc:
            return failure(exc, state)

    def search(self, request):
        state = None
        try:
            state = self._new(request)
            self._run_search(state)
            return deepcopy(state.result)
        except (QueryError, MemoryError) as exc:
            return failure(exc, state)

    def poll(self, query_id):
        state = None
        acquired = False
        try:
            state = self.store.get(query_id)
            if state.result is None:
                return envelope(None, state=state, status="partial", code="RUNNING")
            if not state.lock.acquire(blocking=False):
                raise QueryError("CONFLICT", "查询已有活动操作")
            acquired = True
            # A completed cached response must not outlive source revocation.
            # Rechecks only the returned candidate set, never reruns recall.
            if state.result.get("value") and state.result["value"].get("candidates"):
                self.reauthorize(state, state.result["value"]["candidates"])
            result = deepcopy(state.result)
            result["consumed"] = state.ledger.snapshot()
            return result
        except (QueryError, MemoryError) as exc:
            return failure(exc, state)
        finally:
            if acquired:
                state.lock.release()

    def cancel(self, query_id):
        state = None
        try:
            state = self.store.get(query_id)
            state.ledger.cancelled.set()
            state.status = "cancelled"
            return envelope(None, state=state, status="cancelled", code="CANCELLED", stop="cancelled")
        except QueryError as exc:
            return failure(exc, state)

    def reauthorize(self, state, candidates):
        # This is authorization work, not a second candidate/output charge. The
        # actual source reads remain metered; cancelled results cannot leak refs.
        with state.ledger.active():
            self._reauthorize(state, candidates)

    def _reauthorize(self, state, candidates, *, reader=None):
        reader = reader or self.reader(state)
        from .evidence import Evidence
        evidence = Evidence(reader)
        for candidate in candidates:
            from .associations import scope_state
            request = scope_state(state, supplement=candidate.get("group") == "association").request
            for raw in candidate["refs"]:
                ref = parse(raw, FixedRef)
                if ref.kind in {"record", "representation"}:
                    old_exclusions = set(reader.excluded_ids)
                    reader.excluded_ids.update(excluded(request))
                    try:
                        record = reader.record(ref)
                    finally:
                        reader.excluded_ids = old_exclusions
                    allowed = required_scope_allows if candidate.get("group") == "required_context" else current_scope_allows
                    if not allowed(reader, record, request):
                        raise QueryError("STALE", "材料当前不再满足原筛选，请重新查询")
                elif ref.kind == "file":
                    reader.file_bytes(ref)
                elif ref.kind == "owner":
                    from .catalog_search import native_candidate
                    if native_candidate(self, state, reader, ref) is None:
                        raise QueryError("DENIED", "原始登记不满足当前范围")
            # Diagnostics expose fixed representation identities too. A cached
            # candidate cannot retain those identities after their own source
            # closure/ACL is revoked while the canonical target stays readable.
            for hit in candidate.get("hits", ()):
                for raw in hit.get("representation_refs", ()):
                    source = parse(raw, FixedRef)
                    if source.kind == "representation":
                        reader.record(source)
            if state.request.purpose == "formal":
                approved = candidate.get("evaluated_claim_refs") or candidate["refs"]
                current = evidence.project([parse(r, FixedRef) for r in approved], state.request.applicability)
                if current["rejected"] or not current["claims"]:
                    raise QueryError("STALE", "选定结论的当前复核状态已变化，请重新查询")

    @staticmethod
    def _rrf(channels, records, query):
        return rrf(channels)

    @staticmethod
    def _topic_rank(channels, records, query):
        from memory.search import topic_evidence_ranking
        return topic_evidence_ranking(channels, records, query)[0]

    def _receipt(self, state, candidates, gaps, cursor=None):
        return {"query_id": state.query_id, "request_digest": state.request_digest, "candidates": candidates,
                "next_cursor": cursor, "expires_at": state.expires_at, "gaps": list(dict.fromkeys(gaps))}

    def _run_search(self, state):
        found, gaps, basis, delivered = [], [], None, []
        with state.lock:
            try:
                with state.ledger.active():
                    reader = self.reader(state)
                    found, gaps, basis = self._recall(state, reader)
                    if state.request.association.mode == "existing_only" and found:
                        from .associations import add_existing
                        supplements, supplement_gaps = add_existing(self, state, reader, found)
                        gaps.extend(supplement_gaps)
                        # Direct ranked candidates retain priority on later pages.
                        # Supplements are already authorized but join the visible
                        # queue only after the frozen direct window is exhausted.
                        state.recall["supplements"].extend(supplements)
                        self._append_supplements(state)
                        basis = self._search_basis(state, reader)
                    visible = state.ordered[:state.request.result_limit]
                    state.ledger.charge("output_chars", sum(self._candidate_chars(c) for c in visible if c["group"] != "association"))
                    delivered = visible
                    cursor = self._search_cursor(state, len(visible))
                    state.result = envelope(self._receipt(state, visible, gaps, cursor), state=state,
                        status="partial" if gaps else "ok", warnings=gaps, basis=basis,
                        stop="budget" if state.recall.get("terminal") else "page" if cursor else "exhausted")
                state.status = "completed"
            except Exception as exc:
                value = self._receipt(state, delivered, gaps) if delivered and isinstance(exc, QueryError) and exc.code in {"BUDGET", "CANCELLED"} else None
                state.result = failure(exc, state, value=value, basis=basis)
                state.status = "cancelled" if isinstance(exc, QueryError) and exc.code == "CANCELLED" else "failed"
            state.result["consumed"] = state.ledger.snapshot()

    def _search_cursor(self, state, offset):
        job = state.recall
        more = offset < len(state.ordered) or job.get("position", 0) < len(job.get("groups", ()))
        if not more or job.get("terminal"):
            return None
        cursor = str(uuid.uuid4())
        state.cursor_ids[cursor] = offset
        return cursor

    @staticmethod
    def _candidate_chars(candidate):
        # Matched fragments are user-visible source text, so they share the
        # same output ceiling as the canonical candidate excerpt.
        return len(candidate["excerpt"]) + sum(len(hit.get("matched_text") or "") for hit in candidate.get("hits", ()))

    @staticmethod
    def _append_supplements(state):
        job = state.recall
        if job.get("position", 0) >= len(job.get("groups", ())):
            for candidate in job.get("supplements", ()):
                if candidate["candidate_id"] not in state.candidates:
                    state.ordered.append(candidate)
                    state.candidates[candidate["candidate_id"]] = candidate
            job["supplements"] = []

    def _recall(self, state, reader):
        """Freeze bounded index metadata, then authorize only enough final results.

        Keyword metadata participates only in ranking. It grants no body access
        and never substitutes for the canonical checks performed by _read_search.
        A cursor retains this window and its manifest-pinned revisions; a later
        index refresh cannot inject different candidates into the same query.
        """
        request = state.request
        db = index.connect(self.root, create=False)
        if db is None:
            raise QueryError("SOURCE_MISSING", "已有索引尚未建立，请先使用索引维护入口")
        job = state.recall = {"groups": [], "position": 0, "gaps": [], "watermarks": [],
                              "pins": {}, "supplements": [], "terminal": False}
        gaps, channels = job["gaps"], {}
        try:
            allowed_owners = []
            for oid in reader.views:
                try:
                    owner = reader.owner(oid)
                except QueryError:
                    continue
                if owner_allowed(owner, request):
                    allowed_owners.append(oid)
            if not allowed_owners:
                return [], gaps, reader.basis()
            remaining = state.ledger.remaining("candidates")
            if not remaining:
                raise QueryError("BUDGET", "候选预算为零")
            placeholders = ",".join("?" for _ in allowed_owners)
            text = " ".join([request.question, *request.keywords]).strip()
            job["text"] = text
            columns = "r.canonical_id,r.record_id,r.owner_id,r.entity_kind,r.revision,r.content_hash,r.keywords"
            # Filter before the bounded recall window: technical records must
            # not consume the slots reserved for the user's chosen source.
            from .content import SOURCE_KINDS
            source_kinds = SOURCE_KINDS.get(request.content_source, ())
            source_sql = " AND r.kind IN (" + ",".join("?" for _ in source_kinds) + ")" if source_kinds else ""
            # Independent providers must not share one exception boundary. Exact
            # identity is evaluated first and survives a broken FTS table/reader.
            if "identity" in request.channels:
                identity = channels["identity"] = []
                ids = list(dict.fromkeys([text, *(ref.id for s in (request.scope, request.scope_ceiling) for ref in s.include_refs)]))
                try:
                    for target in ids[:remaining]:
                        state.ledger.checkpoint()
                        row = db.execute(f"SELECT {columns} FROM memory_records r WHERE r.canonical_id=? AND r.owner_id IN ({placeholders}) AND r.sensitivity!='restricted' AND r.entity_kind IN ('record','claim')" + source_sql,
                                         [target, *allowed_owners, *source_kinds]).fetchone()
                        if row:
                            identity.append(dict(row))
                    if len(ids) > remaining:
                        gaps.append("identity 候选窗口已达预算上限")
                except (sqlite3.Error, OSError, MemoryError):
                    gaps.append("召回通道 identity 执行失败；保留其他已完成通道")
            if "lexical" in request.channels:
                lexical = channels["lexical"] = []
                try:
                    import retrieval
                    terms = retrieval.expanded_terms(text, index.configuration(self.root))
                    terms = list(dict.fromkeys(term for term in terms if term))[:64]
                    job["terms"] = terms
                    expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
                    if expression:
                        sql = f"""SELECT {columns},e.entry_id,e.representation_id,
                            bm25(memory_fts) AS raw_score
                            FROM memory_fts JOIN memory_entries e ON e.entry_id=memory_fts.entry_id
                            JOIN memory_records r ON r.canonical_id=e.canonical_id
                            WHERE memory_fts MATCH ? AND r.owner_id IN ({placeholders})
                            AND e.owner_id IN ({placeholders}) AND r.sensitivity!='restricted'
                            AND e.sensitivity!='restricted' AND r.entity_kind IN ('record','claim')
                            {source_sql} ORDER BY raw_score,r.canonical_id,e.entry_id LIMIT ?"""
                        # Append each completed row so a provider's iterator
                        # failure cannot erase the already returned prefix.
                        for row in db.execute(sql, [expression, *allowed_owners, *allowed_owners, *source_kinds, remaining]):
                            state.ledger.checkpoint()
                            lexical.append(dict(row))
                    if len(lexical) >= remaining:
                        gaps.append("候选窗口已达预算上限，不能保证全量覆盖")
                except (sqlite3.Error, OSError, MemoryError):
                    gaps.append("召回通道 lexical 执行失败；保留其他已完成通道")
            missing = set(request.channels) - {"identity", "lexical"}
            if missing:
                gaps.append("未执行通道：" + ", ".join(sorted(missing)) + "；首期有界提供器不调用无硬预算的全窗口查询")
                if not set(request.channels) & {"identity", "lexical"}:
                    raise QueryError("UNSUPPORTED", "当前选定召回通道不支持有界执行")

            # Missing rows are checked against the complete authorized owner set,
            # not merely by iterating rows that happen to remain in SQLite.
            states = {}
            try:
                states = {row["owner_id"]: dict(row) for row in db.execute(
                    f"SELECT owner_id,indexed_generation,target_generation,fts_status FROM memory_index_state WHERE owner_id IN ({placeholders})",
                    allowed_owners)}
            except (sqlite3.Error, OSError, MemoryError):
                gaps.append("索引水位不可读，不能确认当前覆盖")
            manifests = {}
            for oid in allowed_owners:
                state.ledger.checkpoint()
                head, manifest = reader.store.head_manifest(reader.owner(oid))
                manifests[oid] = (head, manifest)
                watermark = states.get(oid)
                generation = head["generation"] if head else 0
                if watermark is None:
                    job["watermarks"].append((oid, "missing"))
                    gaps.append("索引水位缺少 owner 记录，不能确认当前覆盖")
                else:
                    job["watermarks"].append((oid, str(watermark["indexed_generation"])))
                    if watermark["fts_status"] != "indexed" or watermark["indexed_generation"] != watermark["target_generation"] or watermark["indexed_generation"] != generation:
                        gaps.append("索引水位未完整覆盖当前内容")

            rows_by_id, metadata = {}, {}
            for channel, values in channels.items():
                for entry_rank, raw in enumerate(values, 1):
                    cid = raw["canonical_id"]
                    # Keep every representation and its own native score. RRF
                    # still collapses canonical IDs once per channel for ranking.
                    rows_by_id.setdefault(cid, {}).setdefault(channel, []).append({**raw, "_entry_rank": entry_rank})
                    try:
                        keywords = json.loads(raw["keywords"])
                    except (TypeError, ValueError):
                        keywords = []
                        gaps.append("部分索引排序元数据不可解析")
                    metadata[cid] = {"keywords": keywords, "owner_id": raw["owner_id"], "entity_kind": raw["entity_kind"]}
                    for rid in (raw["record_id"], raw.get("representation_id")):
                        if not rid or rid in job["pins"]:
                            continue
                        for owner_id, (_head, manifest) in manifests.items():
                            entry = (manifest or {}).get("record_heads", {}).get(rid)
                            if entry:
                                job["pins"][rid] = FixedRef("record", rid, entry["revision"], entry["record_hash"], None)
                                break
            ranked = self.ranking_strategies[request.ranking_strategy](channels, metadata, text)
            groups = {}
            for hit in ranked:
                matching = rows_by_id[hit["canonical_id"]]
                row = next(iter(matching.values()))[0]
                # All matched canonical claims/representations of one record are
                # admitted together, before final K. This avoids reading that
                # container again merely to discover a duplicate on a later page.
                key = row["record_id"]
                group = groups.setdefault(key, {"record_id": key, "matches": []})
                group["matches"].append(({**hit, "channel_rows": matching}, row))
            job["groups"] = list(groups.values())
            from .catalog_search import append_catalog
            append_catalog(state, reader, db, manifests)
            from .history_search import append_history
            append_history(state, reader, manifests)
        finally:
            db.close()
        self._read_search(state, reader, request.result_limit)
        return state.ordered[:request.result_limit], gaps, self._search_basis(state, reader)

    def _read_search(self, state, reader, target_count):
        """Append authorized final candidates until K; rejection triggers refill."""
        job, request = state.recall, state.request
        while len(state.ordered) < target_count and job["position"] < len(job["groups"]) and not job["terminal"]:
            group = job["groups"][job["position"]]
            candidate = None
            try:
                state.ledger.checkpoint()
                if group.get("native_ref"):
                    from .catalog_search import native_candidate
                    state.ledger.charge("candidates", 1)
                    candidate = native_candidate(self, state, reader, group["native_ref"])
                    job["position"] += 1
                    if candidate:
                        state.ordered.append(candidate)
                        state.candidates[candidate["candidate_id"]] = candidate
                    continue
                ref = group.get("ref") or job["pins"].get(group["record_id"])
                requested = [r for s in (request.scope, request.scope_ceiling) for r in s.include_refs if r.id == group["record_id"]]
                if requested and request.freshness == "fixed":
                    ref = requested[0]
                if ref is None:
                    raise QueryError("SOURCE_MISSING", "索引候选缺少固定规范修订")
                # Charge unique canonical candidates, not duplicate representations.
                if not group.get("charged"):
                    state.ledger.charge("candidates", len(group["matches"]))
                record = reader.record(ref)
                if record.get("discovery") == "owner_only" and not any(
                        s.owner_ids is not None and record["owner_id"] in s.owner_ids for s in (request.scope, request.scope_ceiling)):
                    job["position"] += 1
                    continue
                current_head, current_manifest = reader.store.head_manifest(reader.owner(record["owner_id"]))
                latest = (current_manifest or {}).get("record_heads", {}).get(record["record_id"])
                if request.freshness == "current" and (latest is None or latest["revision"] != ref.revision):
                    job["gaps"].append("固定候选在继续读取前已更新，未替换为新修订")
                    job["position"] += 1
                    continue
                for hit, row in group["matches"]:
                    if not (requested and request.freshness == "fixed") and row["revision"] != record["revision"]:
                        job["gaps"].append("存在过期索引命中，未当作当前内容返回")
                        if request.freshness == "current":
                            continue
                    value = self.make_candidate(state, reader, record, hit, row, job["text"])
                    if value is None:
                        continue
                    if candidate is None:
                        candidate = value
                    else:
                        for field in ("hits", "evaluated_claim_refs", "unresolved_claim_refs"):
                            known = {digest(item) for item in candidate[field]}
                            for item in value[field]:
                                if digest(item) not in known:
                                    candidate[field].append(item)
                                    known.add(digest(item))
                        candidate["channels"] = list(dict.fromkeys([*candidate["channels"], *value["channels"]]))
                        # A merged formal result may add eligible claims, but no
                        # unreviewed statement can enter its displayed excerpt.
                        if request.purpose == "formal":
                            approved = {r["id"] for r in candidate["evaluated_claim_refs"]}
                            candidate["excerpt"] = "\n".join(c["statement"] for c in record["payload"].get("claims", []) if c["claim_id"] in approved)[:400]
                job["position"] += 1
                if candidate is not None:
                    if candidate["realization"]["state"] not in {"direct", "assemblable"}:
                        job["gaps"].append("部分材料缺少请求表示；仅返回可用性说明，不能组装为所请求正文")
                    state.ordered.append(candidate)
                    state.candidates[candidate["candidate_id"]] = candidate
            except (QueryError, MemoryError) as exc:
                err = memory_error(exc) if isinstance(exc, MemoryError) else exc
                if err.code in {"BUDGET", "CANCELLED"}:
                    job["gaps"].append(err.message)
                    job["terminal"] = True
                    break
                job["position"] += 1
                job["gaps"].append("部分候选因范围、来源或版本不满足而省略")
        self._append_supplements(state)

    def _search_basis(self, state, reader):
        try:
            return reader.basis(state.recall.get("watermarks", ()))
        except QueryError as exc:
            if exc.code not in {"BUDGET", "CANCELLED"}:
                raise
            state.recall["gaps"].append("预算不足以完成最终HEAD复查，输出仅绑定固定引用")
            return {"refs": [asdict(ref) for ref in reader.fixed.values()], "owner_heads": list(reader.heads.items()),
                    "index_watermarks": state.recall.get("watermarks", []), "consistency": "cross_owner_optimistic"}

    def make_candidate(self, state, reader, record, hit, row, text, *, group="direct"):
        evidence = None
        request = state.request
        from .content import SOURCE_KINDS
        if group == "direct" and request.content_source not in {None, "all"} and record["kind"] not in SOURCE_KINDS[request.content_source]:
            return None
        if request.purpose == "formal" or any(s.review_states is not None or s.validities is not None or s.confidence_levels is not None for s in (request.scope, request.scope_ceiling)):
            # An exact claim hit must not borrow a different accepted claim in
            # its container. This keeps final K evidence eligibility meaningful.
            ids = {row["canonical_id"]} if row.get("entity_kind") == "claim" else None
            # Review history and current applicability are independent. A
            # withdrawn claim stays withdrawn, and an accepted-but-stale review
            # does not turn into "not reviewed". Apply both filters per claim.
            states = filtered_claim_states(reader, record, request, ids)
            good = [item for item in states if item.get("effective_validity")]
            evidence = evidence_summary(states)
            if request.purpose == "formal" and not good:
                return None
        if not owner_allowed(reader.owner(record["owner_id"]), request) or not all(record_allowed(record, scope, evidence=evidence) for scope in (request.scope, request.scope_ceiling)):
            return None
        requested = [item for scope in (request.scope, request.scope_ceiling) for item in scope.include_refs
                     if item.id == record["record_id"] and item.revision == record["revision"] and item.sha256 == record["record_hash"]]
        # Preserve an explicit block locator through candidate selection. Losing
        # it here would silently replace a requested section with a text guess.
        ref = fixed_record(record, requested[0].locator if requested else None)
        definition = request.definition
        realization = representations.availability(record, ref, definition)
        if realization["state"] not in {"direct", "assemblable"}:
            if request.missing_policy == "fallback":
                for fallback in request.fallback_definitions:
                    possible = representations.availability(record, ref, fallback)
                    if possible["state"] in {"direct", "assemblable"}:
                        realization = possible
                        break
            if realization["state"] not in {"direct", "assemblable"} and request.missing_policy in {"skip", "fallback"}:
                return None
        from memory.technical_units import description_text, is_unit
        excerpt = description_text(record) if is_unit(record) else record.get("body_markdown", "")
        if not excerpt:
            from .assembly import readable_payload
            excerpt = readable_payload(record["payload"])
        approved_ids = {item["claim_id"] for item in good} if request.purpose == "formal" else None
        hits = self._channel_hits(state, reader, record, ref, hit, row, approved_ids=approved_ids)
        if hit.get("channel_rows") and not hits:
            # An inaccessible/stale representation cannot remain the sole reason
            # to disclose a target, even when the target itself is readable.
            return None
        if request.purpose == "formal":
            excerpt = "\n".join(claim["statement"] for claim in record["payload"].get("claims", []) if claim["claim_id"] in approved_ids)
        from .facets import unknown_facets
        claim_refs = [(c["claim_id"], canonical_hash(c)) for c in record["payload"].get("claims", ())
                      if c["claim_id"] == row.get("canonical_id")] if row.get("entity_kind") == "claim" else None
        _, manifest = reader.store.head_manifest(reader.owner(record["owner_id"]))
        latest = (manifest or {}).get("record_heads", {}).get(record["record_id"])
        if request.freshness == "current" and (not latest or latest["record_hash"] != ref.sha256):
            raise QueryError("STALE", "固定材料已有新修订，未替换正文")
        return {"candidate_id": "C-" + canonical_hash({"query": state.query_id, "ref": asdict(ref), "group": group})[:24],
                "refs": [asdict(ref)], "title": record["title"], "excerpt": excerpt[:400],
                "content_kind": record["kind"], "knowledge_type": record["payload"].get("knowledge_type"),
                "is_latest": bool(latest and latest["record_hash"] == ref.sha256),
                "owner_type": reader.owner(record["owner_id"])["owner_type"],
                "channels": list(dict.fromkeys(item["channel"] for item in hits)), "score": hit.get("score", 0.0), "realization": realization,
                "evidence_status": (evidence["state"][0] if len(evidence["state"]) == 1 else "mixed") if evidence else "not-assessed", "group": group, "hits": hits,
                "evaluated_claim_refs": [asdict(FixedRef("claim", item["claim_id"], None, item["sha256"], None)) for item in states if item["effective_validity"]] if evidence else [],
                "unresolved_claim_refs": [asdict(FixedRef("claim", item["claim_id"], None, item["sha256"], None)) for item in states if not item["effective_validity"]] if evidence else [],
                "unknown_facets": list(unknown_facets(record, (request.scope, request.scope_ceiling), claim_refs))}

    def _channel_hits(self, state, reader, record, ref, hit, row, *, approved_ids=None):
        """Keep each provider score attached to its actual fixed hit source.

        Multiple indexed representations share one RRF vote per canonical ID,
        but remain separate diagnostics. Their bodies are read only when this
        target reaches final-result admission, under the same query budget.
        """
        matched = hit.get("channel_rows")
        if matched is None:
            # Existing relation navigation has no lexical representation window.
            matched = {channel: [{**row, "_entry_rank": rank}] for channel, rank in hit.get("rank_channels", {}).items()}
        output = []
        for channel, entries in matched.items():
            for entry in entries:
                source = ref
                source_text = None
                rep_id = entry.get("representation_id")
                if rep_id:
                    try:
                        pinned = state.recall["pins"].get(rep_id)
                        if pinned is None:
                            raise QueryError("SOURCE_MISSING", "命中表示没有固定规范修订")
                        source = FixedRef("representation", pinned.id, pinned.revision, pinned.sha256, pinned.locator)
                        representation = reader.record(source)
                        target = representation.get("payload", {}).get("target", {})
                        if representation["kind"] != "representation" or target.get("target_id") != entry["canonical_id"]:
                            raise QueryError("STALE", "命中表示与规范目标不匹配")
                        if target.get("target_kind") == "record" and (target.get("revision") != ref.revision or target.get("sha256") not in {None, ref.sha256}):
                            raise QueryError("STALE", "命中表示对应不同固定修订")
                        if target.get("target_kind") == "claim":
                            claims = [c for c in record["payload"].get("claims", ()) if c["claim_id"] == entry["canonical_id"]]
                            if len(claims) != 1 or target.get("sha256") != canonical_hash(claims[0]):
                                raise QueryError("STALE", "命中表示对应不同固定结论")
                        # A representation is authored source text of its own.
                        # An accepted target claim does not approve every phrase
                        # in that representation for formal disclosure.
                        if approved_ids is None:
                            source_text = representation["payload"]["text"]
                    except (QueryError, MemoryError) as exc:
                        err = memory_error(exc) if isinstance(exc, MemoryError) else exc
                        if err.code in {"BUDGET", "CANCELLED"}:
                            raise err
                        state.recall["gaps"].append("部分命中表示因来源、权限或固定版本不满足而省略")
                        continue
                elif entry.get("entity_kind") == "claim":
                    claims = [c for c in record["payload"].get("claims", ()) if c["claim_id"] == entry["canonical_id"]]
                    if len(claims) != 1:
                        continue
                    source = FixedRef("claim", claims[0]["claim_id"], None, canonical_hash(claims[0]), "statement")
                    if approved_ids is None or claims[0]["claim_id"] in approved_ids:
                        source_text = claims[0]["statement"]
                elif approved_ids is None and channel == "lexical":
                    # Recreate the existing deterministic entry from the exact
                    # authorized canonical revision, rather than trusting cached
                    # SQLite prose or substituting the candidate's display text.
                    projected = index._row(record, reader.owner(record["owner_id"]))
                    source_text = projected["title"] + "\n" + index._entry(projected)["text"]
                matched_text = None
                if channel == "identity":
                    # This provider matched the persisted identity field itself.
                    matched_text = entry.get("canonical_id", ref.id)
                elif channel == "lexical":
                    if source_text is not None:
                        positions = [match.start() for term in state.recall.get("terms", ())
                                     if (match := re.search(re.escape(term), source_text, re.IGNORECASE))]
                        if positions:
                            start = max(0, min(positions) - 60)
                            matched_text = source_text[start:start + 240]
                    if matched_text is None:
                        state.recall["gaps"].append("部分词法命中没有可按当前用途展示的固定原文片段；matched_text 为 null")
                output.append({"channel": channel, "provider": "canonical-history" if row.get("_history") else "memory-fts" if channel == "lexical" else channel,
                    "provider_version": index.PROJECTION_VERSION if channel == "lexical" else "1", "rank": entry.get("_entry_rank", 1),
                    "raw_score": entry.get("raw_score") if channel == "lexical" else None,
                    "score_meaning": "获准登记目录匹配；非FTS排名" if channel == "catalog" else "固定历史版本的词项匹配；非FTS排名" if row.get("_history") else "FTS bm25（越低越相关）" if channel == "lexical" else "精确身份匹配" if channel == "identity" else "既有固定关系导航",
                    "representation_refs": [asdict(source)], "matched_text": matched_text})
        return output

    def resume(self, query_id, cursor):
        state = None
        acquired = False
        try:
            state = self.store.get(query_id)
            if not state.lock.acquire(blocking=False):
                raise QueryError("CONFLICT", "查询已有活动操作")
            acquired = True
            if cursor in state.responses:
                result = deepcopy(state.responses[cursor])
                self.reauthorize(state, result["value"]["candidates"])
                result["consumed"] = state.ledger.snapshot()
                return result
            if cursor not in state.cursor_ids:
                raise QueryError("EXPIRED", "游标不属于本查询或已到期")
            offset = state.cursor_ids[cursor]
            with state.ledger.active():
                reader = self.reader(state)
                target = offset + state.request.result_limit
                # A previous page may have admitted supplements or a batch that
                # did not fit output budget. Revalidate only that cached prefix;
                # new direct candidates are authorized by the incremental reader.
                cached = state.ordered[offset:min(target, len(state.ordered))]
                if cached:
                    self._reauthorize(state, cached, reader=reader)
                if state.recall:
                    self._read_search(state, reader, target)
                values = state.ordered[offset:target]
                # Reserve the complete page atomically. Failed output charging
                # leaves admitted items and the input cursor in place for retry.
                state.ledger.charge("output_chars", sum(self._candidate_chars(c) for c in values if c["group"] != "association"))
                next_cursor = self._search_cursor(state, offset + len(values))
                gaps = state.recall.get("gaps", state.result["warnings"])
                basis = self._search_basis(state, reader) if state.recall else state.result["basis"]
                result = envelope(self._receipt(state, values, gaps, next_cursor), state=state,
                                  status="partial" if gaps else "ok", warnings=gaps, basis=basis,
                                  stop="budget" if state.recall.get("terminal") else "page" if next_cursor else "exhausted")
            state.responses[cursor] = deepcopy(result)
            if state.recall and gaps != state.result["warnings"]:
                # A later page can discover staleness or a provider gap. Keep
                # that query-wide incompleteness visible to subsequent assembly,
                # while preserving the first page and its original fixed basis.
                state.result = envelope(state.result["value"], state=state,
                    status="partial" if gaps else "ok", warnings=gaps, basis=state.result["basis"],
                    stop=result["stop_reason"])
            result["consumed"] = state.ledger.snapshot()
            return result
        except (QueryError, MemoryError) as exc:
            return failure(exc, state)
        finally:
            if acquired:
                state.lock.release()

    def assemble(self, request):
        state, assembler, reader = None, None, None
        acquired = False
        try:
            request = parse(json_value(request), AssembleRequest)
            state = self.store.get(request.query_id)
            if not state.lock.acquire(blocking=False):
                raise QueryError("CONFLICT", "查询已有活动操作")
            acquired = True
            if request.expected_request_digest != state.request_digest or any(cid not in state.candidates for cid in request.candidate_ids):
                raise QueryError("CONFLICT", "候选选择不属于本次查询条件")
            cache_key = "assemble:" + digest(request)
            if cache_key in state.responses:
                self.reauthorize(state, [state.candidates[cid] for cid in request.candidate_ids])
                result = deepcopy(state.responses[cache_key])
                # 缓存材料包还含必要依赖。重取必须核验全部已输出贡献者，
                # 否则根候选未变、依赖更新时仍会返回过期正文。
                contributors = result.get("value", {}).get("contributors", [])
                self.reauthorize(state, [{"refs": contributors, "group": "required_context"}])
                result["consumed"] = state.ledger.snapshot()
                return result
            with state.ledger.active():
                reader = self.reader(state)
                selected = [state.candidates[cid] for cid in request.candidate_ids]
                self._reauthorize(state, selected, reader=reader)
                formal_texts = {}
                if state.request.purpose == "formal":
                    from .evidence import Evidence
                    refs = [parse(ref, FixedRef) for row in selected for ref in (row.get("evaluated_claim_refs") or row["refs"])]
                    result = Evidence(reader).project(refs, state.request.applicability)
                    if result["rejected"]:
                        raise QueryError("STALE", "选定结论不再满足正式用途，请重新查询")
                    for claim in result["claims"]:
                        rid = claim.get("record_id")
                        formal_texts[rid] = formal_texts.get(rid, "") + "\n" + claim.get("text", "")
                from .associations import scope_state
                supplement_request = scope_state(state, supplement=True).request
                assembler = Assembler(reader, state.ledger, lambda record: current_scope_allows(reader, record, state.request),
                                      required_allowed=lambda record: required_scope_allows(reader, record, state.request),
                                      association_allowed=lambda record: current_scope_allows(reader, record, supplement_request),
                                      purpose=state.request.purpose, formal_texts=formal_texts, association_share=state.request.association.output_share)
                for candidate in sorted(selected, key=lambda row: row["group"] == "association"):
                    for raw in candidate["refs"]:
                        from .contracts import DefinitionRef
                        definition = parse(candidate["realization"]["definition"], DefinitionRef)
                        previous_exclusions = set(reader.excluded_ids)
                        if candidate["group"] == "association":
                            reader.excluded_ids.update(excluded(supplement_request))
                        try:
                            assembler.add_record(parse(raw, FixedRef), definition, state.request.question,
                                                 group="association" if candidate["group"] == "association" else None)
                        finally:
                            reader.excluded_ids = previous_exclusions
                packet = self._packet(state, assembler)
                basis = reader.basis()
            result = envelope(packet, state=state, status="partial" if assembler.gaps or state.result["warnings"] else "ok",
                              warnings=[*state.result["warnings"], *assembler.gaps], basis=basis,
                              issues=[*state.result.get("issues", []), *assembler.issues])
            state.responses[cache_key] = deepcopy(result)
            return result
        except (QueryError, MemoryError) as exc:
            packet = self._packet(state, assembler) if assembler and assembler.parts and isinstance(exc, QueryError) and exc.code in {"BUDGET", "CANCELLED"} else None
            if packet:
                packet["complete"] = False
            return failure(exc, state, value=packet)
        finally:
            if acquired:
                state.lock.release()

    @staticmethod
    def _packet(state, assembler):
        parts = list(assembler.parts)
        if assembler.gaps:
            # Diagnostic warnings remain available in the envelope. A rendered
            # prose block must share the same output budget as source material.
            markdown = "\n".join(assembler.gaps)
            if len(markdown) <= state.ledger.remaining("output_chars") and not state.ledger.cancelled.is_set():
                try:
                    state.ledger.charge("output_chars", len(markdown))
                    parts.append({"group": "gaps", "heading": "缺口", "markdown": markdown, "refs": [], "selectors": [], "omitted": assembler.gaps})
                except QueryError:
                    pass
        return {"packet_id": "PKT-" + str(uuid.uuid4()), "query_id": state.query_id, "definition": asdict(state.request.definition),
                "parts": parts, "contributors": [asdict(ref) for ref in assembler.contributors.values()],
                "complete": not assembler.gaps and not state.result.get("warnings"), "canonical": False}

    def close(self):
        for state in self.store.states.values():
            state.ledger.cancelled.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
