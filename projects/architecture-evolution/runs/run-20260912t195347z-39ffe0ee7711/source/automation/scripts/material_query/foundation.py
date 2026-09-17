"""材料查询的底层兼容入口：实际固定读取、事务、变化页与索引计划。

旧 v0.1 的 43 个协议不是新的存储格式。本模块把其中尚无应用入口的部分
接回 memory-v3；每次操作仍使用 query_id 的可信权限、活动锁与累计预算。
规范修订只通过 memory.api.dispatch，索引只写既有派生表，不能冒充复核。

使用：Foundation(coordinator).dispatch("describe", {"query_id": ..., "refs": [...]})。
动作清单由 capabilities 返回；未知动作/硬语义拒绝，不返回成功占位对象。
"""
from collections import deque
from copy import deepcopy
from dataclasses import asdict
import math
import sqlite3
import uuid

from memory import api, contracts as legacy_contracts, index
from memory.contracts import canonical_hash
from memory.errors import MemoryError

from . import definitions, representations
from .associations import endpoint_owner_allowed, fixed_legacy, identity, scoped_basis
from .contracts import DefinitionRef, FixedRef
from .coordinator import current_scope_allows, envelope, failure, record_allowed
from .legacy_adapter import fixed_record, memory_error, to_legacy
from .validation import QueryError, object_fields, parse
from .wire import digest


# This map distinguishes ownership from implementation. 'delegated' means that
# the listed runtime API owns the behavior, not that every v0.1 field is supported.
METHOD_MAP = {
    "ContentReader.describe": "describe", "ContentReader.read": "read", "ContentReader.list_page": "list-page",
    "ReferenceResolver.resolve": "resolve", "ContentCommands.validate": "validate", "ContentCommands.commit": "commit",
    "ContentCommands.restore": "restore", "RevisionStore.apply": "apply", "RevisionStore.history": "history",
    "RepresentationCatalog.list": "representation-list", "RepresentationCatalog.read": "read",
    "RepresentationBuilder.plan": "representation-plan", "RepresentationBuilder.build": "representation-build",
    "ChangeReader.read": "changes", "IndexLifecycle.status": "index-status", "IndexLifecycle.plan": "index-plan",
    "IndexLifecycle.execute": "index-execute", "RecallProvider.capabilities": "delegated:Coordinator.capabilities",
    "RecallProvider.recall": "delegated:Coordinator.search", "CandidateDeduplicator.deduplicate": "deduplicate",
    "FusionStrategy.fuse": "delegated:Coordinator.ranking_strategies", "Reranker.rerank": "rerank",
    "DiversitySelector.select": "select", "RankingPipeline.rank": "delegated:Coordinator._recall",
    "RelationNavigator.neighbors": "delegated:deepening.deepen", "RelationNavigator.paths": "paths",
    "RelationNavigator.suggest_links": "delegated:associations.discover/decide",
    "ExpansionPolicy.next_step": "next-step", "SearchCoordinator.search": "delegated:Coordinator.search",
    "SearchCoordinator.resume": "delegated:Coordinator.resume", "ContextBuilder.build": "delegated:Coordinator.assemble",
    "ReadViewService.list": "list-page", "ReadViewService.render": "read",
    "MaintenancePlanner.plan": "delegated:maintenance.plan", "MaintenanceExecutor.execute": "delegated:maintenance.apply",
    "MaintenanceExecutor.status": "delegated:maintenance.status",
    "EvidencePolicy.authorize": "delegated:Reader.owner/record", "EvidencePolicy.assess": "delegated:Evidence",
    "ReviewService.append_review": "review",
    "ImpactAnalyzer.affected": "delegated:maintenance.plan", "ExecutionControl.reserve": "reserve",
    "ExecutionControl.settle": "settle", "ExecutionControl.check_cancelled": "check-cancelled"}


def _state(state):
    if not hasattr(state, "_material_foundation"):
        state._material_foundation = {"cursors": {}, "jobs": {}, "pages": {}, "plans": {},
                                      "validations": {}, "restores": {}, "slices": {}}
    return state._material_foundation


def _limit(raw, default=25):
    limit = raw.get("limit", default)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise QueryError("VALIDATION", "分页数量必须为 1..100")
    return limit


def _uuid(value):
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise QueryError("VALIDATION", "请求身份必须是 UUID") from exc
    return value


def _fields(raw, required=(), optional=()):
    return object_fields(raw, {"query_id", *required}, optional)


def _metadata(record, ref=None):
    return {"ref": asdict(ref or fixed_record(record)), "owner_id": record["owner_id"], "kind": record["kind"],
            "layer": record.get("level"), "title": record["title"],
            "facets": deepcopy(record["payload"].get("knowledge_facets", {}))}


class _ProjectionAccess:
    """索引只检查可读来源闭包；不把复核状态或检索分数混入访问决策。"""
    def __init__(self, catalog):
        self.catalog = catalog

    def access_errors(self, target, *, revision=None):
        catalog, reader = self.catalog, self.catalog.reader
        target_id = target["target_id"] if isinstance(target, dict) else target
        try:
            if target_id in catalog.claims:
                record = catalog.claims[target_id][1]
            else:
                record = reader.current_record(target_id)
            reader.record(fixed_record(record))
            return []
        except (QueryError, MemoryError) as exc:
            error = memory_error(exc) if isinstance(exc, MemoryError) else exc
            if error.code in {"BUDGET", "CANCELLED", "UNSUPPORTED"}:
                raise
            # The old projector understands the original error family. No raw
            # service messages, paths or forbidden titles leave this adapter.
            return [{"code": "ACCESS_DENIED", "target_id": target_id, "message": "规范来源当前不可读"}]


class _ProjectionCatalog(index.Catalog):
    """复用原项目投影器，替换会全库扫描的旧证据目录为逐项受控读取。"""
    def __init__(self, reader):
        self.reader, self.root, self.store = reader, reader.root, reader.store
        self.owners = {}
        for oid in reader.views:
            try:
                self.owners[oid] = reader.owner(oid)
            except QueryError:
                continue
        self.snapshots, self.locations, self.claims = {}, {}, {}
        self._adapter, self._evidence = None, None
        self.access = _ProjectionAccess(self)

    def evidence_adapter(self):
        return self.access

    def graph(self):
        raise QueryError("UNSUPPORTED", "此索引计划不支持未计量的旧 Run/原生证据图；请使用既有索引维护入口")


class Foundation:
    def __init__(self, coordinator, *, index_fault=None, rerankers=None):
        self.coordinator = coordinator
        # Trusted Python-only hook for a real transaction failure test. It is
        # never supplied by HTTP JSON and cannot select code or a shell command.
        self.index_fault = index_fault
        # These are actual deterministic text scorers, not a claim that a
        # neural reranker is installed. A trusted application can replace this
        # narrow callable without changing request/candidate/evidence contracts.
        self.rerankers = {("term-overlap", "1"): self._term_overlap, ("exact-phrase", "1"): self._exact_phrase}
        if rerankers:
            self.rerankers.update(rerankers)

    def capabilities(self):
        return {"methods": dict(METHOD_MAP), "actions": sorted({value for value in METHOD_MAP.values() if ":" not in value} | {"maintenance-status", "definition-resolve"}),
            "version": "foundation-v1", "canonical_schema": "memory-v3",
            "definition_aliases": {"source_contract_version": "0.1", "mapping_version": definitions.LEGACY_ALIAS_VERSION,
                "target_definition_version": definitions.VERSION, "keys": dict(definitions.LEGACY_ALIASES),
                "action": "foundation/definition-resolve"},
            "model_providers": [], "tokenizers": [],
            "model_metering": "无已注册模型/分词计量策略；仅保留独立硬预算，不声明已执行模型",
            "rerank_strategies": [{"name": name, "version": version, "model": None} for name, version in self.rerankers],
            "index_channels": ["lexical", "graph"], "index_atomicity": "per-owner-fts-transaction",
            "limitations": ["新字段不能当旧 v0.1 DTO 原样提交；本适配动作有独立严格输入。",
                "索引计划仅支持规范 memory-v3 owner；旧 Run/原生表示图、向量与跨 owner 原子切换须用专门提供器。",
                "索引输入页必须完整且连续；未完成页不能推进覆盖水位。",
                "导航路径返回有序最短固定路径；不会把导航路径提升为科学支持。",
                "临时计划绑定查询 TTL；规范提交幂等回执持久保留。"]}

    @staticmethod
    def _term_overlap(question, text):
        """查询词覆盖率；分数只衡量已提供正文的词面相关性。"""
        import retrieval
        terms, content = set(retrieval.tokens(question)), set(retrieval.tokens(text))
        return len(terms & content) / len(terms) if terms else 0.0

    @staticmethod
    def _exact_phrase(question, text):
        """精确短语得分，与词覆盖策略共享输入/输出边界。"""
        return 1.0 if question.strip() and question.casefold() in text.casefold() else 0.0

    def dispatch(self, action, raw):
        if action == "definition-resolve":
            try:
                return envelope(definitions.resolve_legacy(raw))
            except Exception as exc:
                return failure(exc)
        if action == "capabilities":
            try:
                object_fields(raw, ())
                return envelope(self.capabilities())
            except Exception as exc:
                return failure(exc)
        if action == "paths":
            return self._paths(raw)
        if action == "maintenance-status":
            # The maintenance service owns persisted plan versions and receipt
            # verification. Keep its lock/ledger lifecycle instead of wrapping
            # it in a second active operation here.
            from .maintenance import status
            return status(self.coordinator, raw)
        handlers = {"describe": self._describe, "read": self._read, "list-page": self._list_page,
                    "resolve": self._resolve, "history": self._history, "changes": self._changes,
                    "validate": self._validate, "commit": self._commit, "apply": self._apply, "restore": self._restore,
                    "index-status": self._index_status, "index-plan": self._index_plan, "index-execute": self._index_execute,
                    "representation-list": self._representation_list, "representation-plan": self._representation_plan,
                    "representation-build": self._representation_build, "deduplicate": self._deduplicate,
                    "select": self._select, "rerank": self._rerank, "next-step": self._next_step, "reserve": self._reserve,
                    "settle": self._settle, "check-cancelled": self._check_cancelled, "review": self._review}
        state, reader, locked, value = None, None, False, None
        try:
            if action not in handlers:
                raise QueryError("UNSUPPORTED", "底层动作未登记；不将未实现契约伪装为成功")
            if not isinstance(raw, dict) or not isinstance(raw.get("query_id"), str):
                raise QueryError("VALIDATION", "底层操作须绑定实际查询身份")
            state = self.coordinator.store.get(raw["query_id"])
            locked = state.lock.acquire(blocking=False)
            if not locked:
                raise QueryError("CONFLICT", "同一查询已有活动操作")
            # Settlement only confirms already spent cost and releases holds;
            # it must remain possible after cancellation or budget exhaustion.
            with state.ledger.active(cleanup=action == "settle"):
                reader = self.coordinator.reader(state)
                # Explicit foundation reads can recover a lost derived locator
                # from the canonical manifests. Normal search keeps its narrow
                # default and does not silently acquire a whole-corpus fallback.
                reader.claim_locator = lambda claim_id: self._locate_claim(state, reader, claim_id)
                value = handlers[action](state, reader, raw)
                gaps = value.get("gaps", []) if isinstance(value, dict) else []
                partial = bool(gaps or isinstance(value, dict) and value.get("index_status") == "pending")
                # Handlers only register authorized refs. Owner heads are still
                # filtered by the original ceiling before crossing the boundary.
                refs = list(_extract_fixed(value))
                result = envelope(value, state=state, status="partial" if partial else "ok", warnings=gaps,
                                  basis=scoped_basis(state, reader, refs), code="BUDGET" if isinstance(value, dict) and value.get("overrun") else None,
                                  stop="page" if isinstance(value, dict) and value.get("next_cursor") else "completed")
            result["consumed"] = state.ledger.snapshot()
            return result
        except Exception as exc:
            error = memory_error(exc) if isinstance(exc, MemoryError) else exc
            # A committed receipt must survive a later budget/index failure;
            # reporting value=None would incorrectly imply that no write occurred.
            saved = value if isinstance(value, dict) and (value.get("save_status") in {"committed", "no_change"}
                or value.get("plan_id") and value.get("owners")
                or value.get("reservation_id") and ("scores" in value or "actual" in value)) else None
            return failure(error, state, value=saved)
        finally:
            if locked:
                state.lock.release()

    def _owner(self, state, reader, owner_id):
        owner = reader.owner(owner_id)
        if any(scope.owner_ids is not None and owner_id not in scope.owner_ids for scope in (state.request.scope, state.request.scope_ceiling)):
            raise QueryError("DENIED", "对象超出原查询范围")
        return owner

    def _owners(self, state, reader, requested=None):
        if requested is not None and (not isinstance(requested, list) or any(not isinstance(oid, str) for oid in requested)):
            raise QueryError("VALIDATION", "owner_ids 必须为数组或 null")
        output = []
        for oid in requested if requested is not None else reader.views:
            try:
                self._owner(state, reader, oid)
                output.append(oid)
            except QueryError:
                if requested is not None:
                    raise
        return list(dict.fromkeys(output))

    def _record(self, state, reader, ref):
        if not endpoint_owner_allowed(state, reader, ref.id):
            raise QueryError("DENIED", "材料超出原查询范围")
        record = reader.record(ref)
        if not current_scope_allows(reader, record, state.request):
            raise QueryError("DENIED", "材料不满足原查询筛选")
        return record

    def _file(self, state, reader, ref):
        """原件身份也受硬范围约束；已登记不等于属于此次查询的来源。"""
        if ref.id in reader.excluded_ids or any(scope.source_ids is not None and ref.id not in scope.source_ids
                for scope in (state.request.scope, state.request.scope_ceiling)):
            raise QueryError("DENIED", "原件不属于原查询允许的来源")
        return reader.service._file(to_legacy(ref))

    def _locate_claim(self, state, reader, claim_id):
        """索引缺失时只扫描可读规范清单；完整扫描后才断言 claim 身份唯一。"""
        if not hasattr(reader, "_foundation_claims"):
            claims = {}
            # Dependency authorization uses the trusted ceiling, while the
            # primary scope filters returned material. A selected B review may
            # legitimately depend on an A claim when A is inside that ceiling.
            for oid in reader.views:
                if state.request.scope_ceiling.owner_ids is not None and oid not in state.request.scope_ceiling.owner_ids:
                    continue
                try:
                    owner = reader.owner(oid)
                except QueryError as exc:
                    if exc.code != "DENIED":
                        raise
                    continue
                _head, manifest = reader.store.head_manifest(owner)
                for rid, entry in (manifest or {}).get("record_heads", {}).items():
                    if rid in reader.excluded_ids:
                        continue
                    state.ledger.charge("candidates", 1)
                    record = reader.store.read_record(owner, rid, entry["revision"])
                    if record["sensitivity"] == "restricted":
                        continue
                    for claim in record["payload"].get("claims", []):
                        cid = claim["claim_id"]
                        if cid in claims and claims[cid]["record_id"] != rid:
                            raise QueryError("INTERNAL", "规范 claim 身份存在歧义")
                        claims[cid] = record
            reader._foundation_claims = claims
        record = reader._foundation_claims.get(claim_id)
        if record is None:
            raise QueryError("SOURCE_MISSING", "获准规范清单中没有可定位的 claim 容器")
        return record

    def _refs(self, raw):
        refs = raw.get("refs")
        if not isinstance(refs, list) or not refs or len(refs) > 100:
            raise QueryError("VALIDATION", "固定引用批次必须为 1..100 项")
        return [parse(ref, FixedRef) for ref in refs]

    def _describe(self, state, reader, raw):
        _fields(raw, {"refs"})
        items, gaps = [], []
        for ref in self._refs(raw):
            try:
                state.ledger.charge("candidates", 1)
                if ref.kind not in {"record", "representation"}:
                    raise QueryError("UNSUPPORTED", "该描述入口只描述规范记录；原件通过 resolve/read 定位")
                record = self._record(state, reader, ref)
                state.ledger.charge("output_chars", len(record["title"]))
                items.append(_metadata(record, ref))
            except (QueryError, MemoryError) as exc:
                error = memory_error(exc) if isinstance(exc, MemoryError) else exc
                if error.code in {"BUDGET", "CANCELLED"}:
                    raise
                gaps.append({"code": error.code, "message": "部分固定材料不可描述"})
        return {"items": items, "gaps": _gap_text(gaps), "missing": gaps}

    def _read(self, state, reader, raw):
        _fields(raw, {"refs"}, {"definition"})
        definition = parse(raw.get("definition", asdict(state.request.definition)), DefinitionRef)
        definitions.get(definition)
        from .assembly import Assembler
        refs = self._refs(raw)
        formal_texts = {}
        if state.request.purpose == "formal":
            from .evidence import Evidence
            for ref in refs:
                if ref.kind not in {"record", "representation"}:
                    continue
                record = self._record(state, reader, ref)
                assessment = Evidence(reader).assess(record, state.request.applicability)
                accepted = {row["claim_id"] for row in assessment if row["effective_validity"]}
                formal_texts[ref.id] = "\n".join(claim["statement"] for claim in record["payload"].get("claims", []) if claim["claim_id"] in accepted)
        assembler = Assembler(reader, state.ledger,
            lambda record: current_scope_allows(reader, record, state.request),
            purpose=state.request.purpose, formal_texts=formal_texts)
        for ref in refs:
            state.ledger.charge("candidates", 1)
            if ref.kind in {"record", "representation"}:
                record = self._record(state, reader, ref)
                realization = representations.availability(record, ref, definition)
                if realization["state"] not in {"direct", "assemblable"}:
                    assembler.gaps.append("固定材料不能提供指定类型；未静默回退")
                    continue
                if definition.key == "original":
                    for legacy in record["sources"]:
                        if legacy["target_kind"] == "file":
                            self._file(state, reader, fixed_legacy(reader, legacy))
            elif ref.kind == "file":
                # All content still flows through the ordinary atomic assembly
                # and byte ledger after this scope/purpose gate.
                self._file(state, reader, ref)
                if state.request.purpose == "formal":
                    raise QueryError("UNSUPPORTED", "原件正文没有独立结论复核，不能作为正式证据投影")
            elif ref.kind != "file":
                raise QueryError("UNSUPPORTED", "该固定身份没有可直接阅读的正文")
            assembler.add_record(ref, definition, state.request.question)
        items = [{"ref": part["refs"][0], "markdown": part["markdown"], "required_refs": part["refs"],
                  "selectors": part["selectors"], "complete": not assembler.gaps} for part in assembler.parts]
        for item in items:
            # Only a server-issued, fixed slice may enter an HTTP rerank call.
            # A client cannot forge source text by pairing arbitrary prose with
            # a genuine record reference. Repeated reads share the same handle.
            slice_id = "FS-" + digest(item)
            item["slice_id"] = slice_id
            _state(state)["slices"][slice_id] = deepcopy(item)
        return {"items": items, "missing": assembler.gaps, "gaps": list(dict.fromkeys(assembler.gaps)), "canonical_writes": 0}

    def _resolve(self, state, reader, raw):
        _fields(raw, {"refs"})
        refs = raw["refs"]
        if not isinstance(refs, list) or not 1 <= len(refs) <= 100:
            raise QueryError("VALIDATION", "旧引用批次须为 1..100 项")
        output = []
        for legacy in refs:
            object_fields(legacy, {"target_kind", "target_id", "revision", "sha256", "locator", "relation"})
            state.ledger.charge("candidates", 1)
            if legacy["target_kind"] == "owner":
                owner = self._owner(state, reader, legacy["target_id"])
                sha = owner["fingerprint"]
                if legacy["sha256"] not in {None, sha}:
                    raise QueryError("STALE", "对象固定指纹已变化")
                ref = FixedRef("owner", owner["owner_id"], None, sha, legacy["locator"] or None)
            elif legacy["target_kind"] == "claim":
                db = index.connect(reader.root, create=False)
                row = None
                if db is not None:
                    try:
                        row = db.execute("SELECT record_id FROM memory_records WHERE canonical_id=? AND entity_kind='claim'", (legacy["target_id"],)).fetchone()
                    finally:
                        db.close()
                # The index locates a container only. A missing derived row
                # does not make a canonical claim disappear from fixed reads.
                record = reader.current_record(row[0]) if row else self._locate_claim(state, reader, legacy["target_id"])
                self._record(state, reader, fixed_record(record))
                matches = [claim for claim in record["payload"].get("claims", []) if claim["claim_id"] == legacy["target_id"]]
                if len(matches) != 1:
                    raise QueryError("STALE", "结论目录和规范容器不一致")
                sha = canonical_hash(matches[0])
                if legacy["sha256"] not in {None, sha}:
                    raise QueryError("STALE", "结论固定指纹不匹配")
                ref = FixedRef("claim", legacy["target_id"], None, sha, legacy["locator"] or None)
            else:
                if legacy["target_kind"] == "record" and not endpoint_owner_allowed(state, reader, legacy["target_id"]):
                    raise QueryError("DENIED", "引用超出原查询范围")
                ref = fixed_legacy(reader, legacy)
                if ref.kind == "record":
                    self._record(state, reader, ref)
                elif ref.kind == "file":
                    self._file(state, reader, ref)
            output.append({"target": asdict(ref), "relation": legacy["relation"]})
        return {"links": output, "gaps": []}

    def _page_job(self, state, reader, action, raw):
        data = _state(state)
        signature = digest({"action": action, **{key: value for key, value in raw.items() if key != "cursor"}})
        cursor = raw.get("cursor")
        if cursor is not None:
            if not isinstance(cursor, str) or data["cursors"].get(cursor, (None,))[0] != signature:
                raise QueryError("EXPIRED", "底层游标不属于当前动作和固定范围")
        job = data["jobs"].get(signature)
        if job is None:
            owner_ids = self._owners(state, reader, [raw["owner_id"]] if action == "history" else raw.get("owner_ids"))
            pins = []
            for oid in owner_ids:
                owner = self._owner(state, reader, oid)
                head, manifest = reader.store.head_manifest(owner)
                pins.append((oid, deepcopy(head), deepcopy(manifest)))
            job = {"pins": pins, "responses": {}, "action": action, "signature": signature}
            data["jobs"][signature] = job
        position = data["cursors"][cursor][1] if cursor else (0, 0)
        return data, job, position, cursor

    def _save_page(self, state, data, job, position, cursor, items, more, gaps, refs=()):
        next_cursor = None
        if more:
            next_cursor = str(uuid.uuid4())
            data["cursors"][next_cursor] = (job["signature"], position)
        page_id = "FP-" + str(uuid.uuid4())
        page = {"page_id": page_id, "items": items, "next_cursor": next_cursor, "gaps": list(dict.fromkeys(gaps)),
                "basis_heads": [[oid, head["commit_id"] if head else None] for oid, head, _ in job["pins"]]}
        data["pages"][page_id] = {"public": deepcopy(page), "action": job["action"], "from_cursor": cursor,
                                   "signature": job["signature"], "pins": job["pins"]}
        job["responses"][cursor or "first"] = deepcopy(page)
        return page

    def _cached_page(self, state, reader, job, cursor):
        page = job["responses"].get(cursor or "first")
        if page is None:
            return None
        for raw_ref in _extract_fixed(page):
            ref = parse(raw_ref, FixedRef)
            if ref.kind in {"record", "representation"}:
                self._record(state, reader, ref)
        for oid, _head, _manifest in job["pins"]:
            self._owner(state, reader, oid)
        return deepcopy(page)

    def _list_page(self, state, reader, raw):
        _fields(raw, (), {"owner_ids", "limit", "cursor"})
        limit = _limit(raw)
        data, job, (owner_pos, entry_pos), cursor = self._page_job(state, reader, "list-page", raw)
        cached = self._cached_page(state, reader, job, cursor)
        if cached is not None:
            return cached
        items, gaps = [], []
        while owner_pos < len(job["pins"]) and len(items) < limit:
            oid, _head, manifest = job["pins"][owner_pos]
            self._owner(state, reader, oid)
            entries = sorted((manifest or {}).get("record_heads", {}).items())
            while entry_pos < len(entries) and len(items) < limit:
                state.ledger.charge("candidates", 1)
                rid, entry = entries[entry_pos]
                entry_pos += 1
                ref = FixedRef("record", rid, entry["revision"], entry["record_hash"], None)
                try:
                    record = self._record(state, reader, ref)
                    state.ledger.charge("output_chars", len(record["title"]))
                    items.append(_metadata(record, ref))
                except QueryError as exc:
                    if exc.code in {"BUDGET", "CANCELLED"}:
                        raise
                    gaps.append("部分固定目录项不可读或不满足筛选")
            if entry_pos >= len(entries):
                owner_pos, entry_pos = owner_pos + 1, 0
        return self._save_page(state, data, job, (owner_pos, entry_pos), cursor, items, owner_pos < len(job["pins"]), gaps)

    def _history(self, state, reader, raw):
        _fields(raw, {"owner_id"}, {"limit", "cursor"})
        return self._change_page(state, reader, raw, "history")

    def _changes(self, state, reader, raw):
        _fields(raw, (), {"owner_ids", "limit", "cursor"})
        return self._change_page(state, reader, raw, "changes")

    def _change_page(self, state, reader, raw, action):
        limit = _limit(raw)
        data, job, (owner_pos, distance), cursor = self._page_job(state, reader, action, raw)
        cached = self._cached_page(state, reader, job, cursor)
        if cached is not None:
            return cached
        items, gaps = [], []
        while owner_pos < len(job["pins"]) and len(items) < limit:
            oid, _head, manifest = job["pins"][owner_pos]
            owner = self._owner(state, reader, oid)
            # Page positions refer to the originally pinned chain; a concurrent
            # new HEAD never inserts or shifts history under a saved cursor.
            skipped = 0
            while manifest and skipped < distance:
                parent = manifest["parent_commit_id"]
                manifest = reader.store._manifest(owner, parent, manifest["parent_manifest_hash"]) if parent else None
                skipped += 1
            while manifest and len(items) < limit:
                state.ledger.charge("candidates", 1)
                parent_id = manifest["parent_commit_id"]
                previous = reader.store._manifest(owner, parent_id, manifest["parent_manifest_hash"]) if parent_id else None
                old_heads = (previous or {}).get("record_heads", {})
                changed = manifest.get("changed_ids")
                if changed is None:
                    changed = [rid for rid, entry in manifest["record_heads"].items() if old_heads.get(rid) != entry]
                current_refs, previous_refs = [], []
                for rid in changed:
                    entry = manifest["record_heads"][rid]
                    ref = FixedRef("record", rid, entry["revision"], entry["record_hash"], None)
                    try:
                        self._record(state, reader, ref)
                        current_refs.append(asdict(ref))
                        if rid in old_heads:
                            old = old_heads[rid]
                            pinned = FixedRef("record", rid, old["revision"], old["record_hash"], None)
                            self._record(state, reader, pinned)
                            previous_refs.append(asdict(pinned))
                    except QueryError as exc:
                        if exc.code in {"BUDGET", "CANCELLED"}:
                            raise
                        gaps.append("部分历史变化因当前授权或筛选而省略")
                if current_refs:
                    event = {"event_id": manifest["commit_id"], "owner_id": oid, "commit_id": manifest["commit_id"],
                             "generation": manifest["generation"], "previous_refs": previous_refs, "current_refs": current_refs}
                    if action == "history":
                        matches = [(request_id, entry) for request_id, entry in manifest["request_ledger"].items() if entry["commit_id"] == manifest["commit_id"]]
                        if len(matches) != 1:
                            raise QueryError("INTERNAL", "历史提交缺少唯一幂等回执")
                        request_id, entry = matches[0]
                        receipt = reader.store.read_json(reader.store.path(owner, "commits/" + manifest["commit_id"] + "/receipt.json"))
                        if canonical_hash(receipt) != entry["receipt_hash"]:
                            raise QueryError("INTERNAL", "历史回执指纹不匹配")
                        event.update(request_id=request_id, save_status=receipt["save_status"], follow_up_required=["index"])
                    items.append(event)
                distance += 1
                manifest = previous
            if manifest is None:
                owner_pos, distance = owner_pos + 1, 0
        return self._save_page(state, data, job, (owner_pos, distance), cursor, items, owner_pos < len(job["pins"]), gaps)

    def _writer(self, state, reader):
        from .writer import Writer
        source_sets = [set(scope.source_ids) for scope in (state.request.scope, state.request.scope_ceiling) if scope.source_ids is not None]
        sources = set.intersection(*source_sets) if source_sets else None
        return Writer(reader.root, state.ledger, access_owner_ids=self._owners(state, reader),
                      excluded_ids=reader.excluded_ids, source_ids=sources)

    def _guard_batch(self, state, reader, batch, basis_refs=()):
        if not legacy_contracts.validate_request(batch)["valid"]:
            raise QueryError("VALIDATION", "内容批次不符合 memory-v3 公共提交契约")
        self._owner(state, reader, batch["owner_id"])
        if len(batch["operations"]) > 100:
            raise QueryError("VALIDATION", "单批最多 100 项修改")
        for raw_ref in basis_refs:
            ref = parse(raw_ref, FixedRef)
            if ref.kind == "file":
                self._file(state, reader, ref)
                reader.file_bytes(ref)
            else:
                self._record(state, reader, ref)
        for operation in batch["operations"]:
            state.ledger.charge("candidates", 1)
            draft = operation["draft"]
            if draft["owner_id"] != batch["owner_id"]:
                raise QueryError("VALIDATION", "一个规范事务只能有一个 owner")
            # Scope predicates apply to both the current target and the proposed
            # shape. The public service still performs all actual schema, source
            # version and state-transition checks before its atomic publication.
            shaped = {**draft, "record_id": operation.get("record_id", "new"),
                      "level": legacy_contracts.project_memory_level(draft)}
            if not all(record_allowed(shaped, scope) for scope in (state.request.scope, state.request.scope_ceiling)):
                raise QueryError("DENIED", "修改后的材料不满足原查询范围")
            if operation.get("record_id"):
                current = reader.current_record(operation["record_id"])
                self._record(state, reader, fixed_record(current))

    def _validate(self, state, reader, raw):
        _fields(raw, {"batch"}, {"basis_refs"})
        self._guard_batch(state, reader, raw["batch"], raw.get("basis_refs", []))
        result = api.dispatch(self._writer(state, reader), "validate-draft", raw["batch"])
        handle = "FV-" + str(uuid.uuid4())
        fingerprint = digest({"batch": raw["batch"], "basis_refs": raw.get("basis_refs", [])})
        _state(state)["validations"][handle] = {"batch": deepcopy(raw["batch"]), "basis_refs": deepcopy(raw.get("basis_refs", [])), "digest": fingerprint}
        return {"validation_handle": handle, "batch_sha256": fingerprint, "validator": "memory-v3",
                "validated_basis": deepcopy(raw.get("basis_refs", [])), "receipt": result, "gaps": []}

    def _commit(self, state, reader, raw):
        _fields(raw, {"batch"}, {"basis_refs"})
        self._guard_batch(state, reader, raw["batch"], raw.get("basis_refs", []))
        return api.dispatch(self._writer(state, reader), "commit", raw["batch"])

    def _apply(self, state, reader, raw):
        _fields(raw, {"validation_handle", "expected_batch_sha256"})
        saved = _state(state)["validations"].get(raw["validation_handle"])
        if saved is None:
            raise QueryError("EXPIRED", "验证凭据不属于本查询或已到期")
        if saved["digest"] != raw["expected_batch_sha256"]:
            raise QueryError("CONFLICT", "批次指纹不匹配已验证内容")
        return self._commit(state, reader, {"query_id": state.query_id, "batch": saved["batch"], "basis_refs": saved["basis_refs"]})

    def _restore(self, state, reader, raw):
        _fields(raw, {"owner_id", "expected_head", "restore_refs", "current_refs", "reason", "request_id"})
        if not isinstance(raw["reason"], str) or not raw["reason"].strip():
            raise QueryError("VALIDATION", "恢复必须记录理由")
        _uuid(raw["request_id"])
        self._owner(state, reader, raw["owner_id"])
        retry = _state(state)["restores"].get(raw["request_id"])
        if retry is not None:
            if retry["digest"] != digest(raw):
                raise QueryError("CONFLICT", "同一恢复 request_id 不能更改原恢复请求")
            return self._commit(state, reader, {"query_id": state.query_id, "batch": retry["batch"], "basis_refs": raw["restore_refs"]})
        restore = self._refs({"refs": raw["restore_refs"]})
        currents = self._refs({"refs": raw["current_refs"]})
        by_id = {ref.id: ref for ref in currents}
        if len(by_id) != len(currents) or {ref.id for ref in restore} != set(by_id):
            raise QueryError("VALIDATION", "每个恢复目标都要绑定唯一当前修订")
        operations = []
        fields = {"schema_version", "owner_id", "kind", "title", "body_markdown", "keywords", "payload", "sources",
                  "provenance_gap", "record_reason", "change_reason", "sensitivity", "discovery"}
        for target in restore:
            current_ref = by_id[target.id]
            old = self._record(state, reader, target)
            current = self._record(state, reader, current_ref)
            if reader.current_record(target.id)["record_hash"] != current_ref.sha256:
                raise QueryError("CONFLICT", "恢复将覆盖后续修改，已拒绝")
            if old["owner_id"] != raw["owner_id"] or target.revision >= current_ref.revision or old["kind"] == "review":
                raise QueryError("VALIDATION", "只能恢复同 owner 的历史内容修订；科学复核须走专门动作")
            draft = {key: deepcopy(value) for key, value in old.items() if key in fields}
            draft["change_reason"] = raw["reason"]
            op = {"policy": "set_policy", "question": "transition_question", "association": "decide_association", "checkpoint": "save_checkpoint"}.get(old["kind"], "put_record")
            operations.append({"op": op, "record_id": target.id, "expected_revision": current["revision"], "draft": draft})
        batch = {"schema_version": 1, "request_id": raw["request_id"], "actor": {"kind": "workflow", "id": "material-foundation"},
                 "owner_id": raw["owner_id"], "expected_head": raw["expected_head"], "operations": operations}
        _state(state)["restores"][raw["request_id"]] = {"digest": digest(raw), "batch": deepcopy(batch)}
        return self._commit(state, reader, {"query_id": state.query_id, "batch": batch, "basis_refs": raw["restore_refs"]})

    def _review(self, state, reader, raw):
        _fields(raw, {"command"})
        command = raw["command"]
        if not isinstance(command, dict) or not isinstance(command.get("owner_id"), str):
            raise QueryError("VALIDATION", "复核命令必须声明规范 owner")
        self._owner(state, reader, command["owner_id"])
        return api.dispatch(self._writer(state, reader), "review", command)

    def _index_key(self, value=None):
        expected = {"channel": "lexical", "representation": "existing", "encoder": None,
                    "analyzer": {"name": "memory-fts", "version": index.PROJECTION_VERSION}, "dimension": None}
        if value is None:
            return expected
        if not isinstance(value, dict) or set(value) != set(expected):
            raise QueryError("VALIDATION", "索引键必须包含 channel/representation/encoder/analyzer/dimension")
        comparison = {**value, "channel": "lexical"}
        if value["channel"] not in {"lexical", "graph"} or comparison != expected:
            raise QueryError("UNSUPPORTED", "此索引键/编码版本不属于既有 FTS 与关联投影")
        return deepcopy(value)

    def _watermarks(self, state, reader, owner_ids, key):
        db = index.connect(reader.root, create=False)
        items = []
        try:
            for oid in owner_ids:
                owner = self._owner(state, reader, oid)
                head, _ = reader.store.head_manifest(owner)
                generation = head["generation"] if head else 0
                row = db.execute("SELECT * FROM memory_index_state WHERE owner_id=?", (oid,)).fetchone() if db is not None else None
                current = dict(row) if row else {}
                ready = (current.get("fts_status") == "indexed" and current.get("indexed_generation") == generation
                    and current.get("target_generation") == generation and current.get("native_fingerprint") == owner["fingerprint"]
                    and current.get("projection_version") == index.PROJECTION_VERSION)
                items.append({"owner_id": oid, "index": key, "head": deepcopy(head), "indexed_generation": current.get("indexed_generation"),
                    "target_generation": generation, "coverage": "complete" if ready and key["channel"] == "lexical" else "partial" if row else "unknown",
                    "state": "indexed" if ready else "pending", "scope": "existing_associations_only" if key["channel"] == "graph" else "existing_searchable_representations"})
        finally:
            if db is not None:
                db.close()
        return items

    def _index_status(self, state, reader, raw):
        _fields(raw, (), {"owner_ids", "index"})
        key = self._index_key(raw.get("index"))
        items = self._watermarks(state, reader, self._owners(state, reader, raw.get("owner_ids")), key)
        return {"watermarks": items, "writes": 0, "gaps": []}

    def _index_plan(self, state, reader, raw):
        _fields(raw, {"mode", "page_ids"}, {"index"})
        if raw["mode"] not in {"incremental", "repair", "rebuild"}:
            raise QueryError("UNSUPPORTED", "索引维护模式未登记")
        key = self._index_key(raw.get("index"))
        ids = raw["page_ids"]
        if not isinstance(ids, list) or not ids or len(ids) > 1000 or len(set(ids)) != len(ids):
            raise QueryError("VALIDATION", "索引计划需要不重复的实际输入页")
        pages = [_state(state)["pages"].get(page_id) for page_id in ids]
        if any(page is None for page in pages):
            raise QueryError("EXPIRED", "输入页不属于本查询")
        kind = pages[0]["action"]
        if kind not in {"list-page", "changes"} or any(page["action"] != kind or page["signature"] != pages[0]["signature"] for page in pages):
            raise QueryError("VALIDATION", "全量内容页与增量变化页不可混合")
        if raw["mode"] == "rebuild" and kind != "list-page" or raw["mode"] == "incremental" and kind != "changes":
            raise QueryError("VALIDATION", "重建需要内容页，增量需要变化页")
        previous = None
        for page in pages:
            if page["from_cursor"] != previous or page["public"]["gaps"]:
                raise QueryError("VALIDATION", "索引输入页有缺口或顺序不连续")
            previous = page["public"]["next_cursor"]
        if previous is not None:
            raise QueryError("VALIDATION", "索引输入分页尚未完整，不能发布完整覆盖水位")
        # Whole-owner projections must not silently discard a user's hard
        # kind/role/exclusion filters. Such selective indexes need another key.
        for scope in (state.request.scope, state.request.scope_ceiling):
            if any(getattr(scope, name) is not None for name in ("levels", "kinds", "roles", "outcomes", "review_states", "validities", "source_ids", "confidence_levels", "time_window", "recorded_from", "recorded_before")) or any(
                    getattr(scope, name) for name in ("excluded_refs", "excluded_owner_ids", "exclude_ids", "applicability_conditions", "applicability_exclusions")):
                raise QueryError("UNSUPPORTED", "既有索引按完整 owner 维护；此筛选需要专用选择性索引")
        pins = pages[0]["pins"]
        for oid, head, _manifest in pins:
            owner = self._owner(state, reader, oid)
            current, _ = reader.store.head_manifest(owner)
            if current != head:
                raise QueryError("STALE", "索引输入页的规范 HEAD 已变化")
            if owner["owner_type"] == "run":
                raise QueryError("UNSUPPORTED", "旧 Run 图的完整索引仍由既有专门维护入口负责")
        public = {"plan_id": "FI-" + str(uuid.uuid4()), "mode": raw["mode"], "index": key, "page_ids": ids,
                  "owner_ids": [oid for oid, _head, _manifest in pins], "basis_heads": [[oid, head["commit_id"] if head else None] for oid, head, _manifest in pins],
                  "input_kind": kind, "from_cursor": None, "next_scan_cursor": None,
                  "event_ids": [item["event_id"] for page in pages for item in page["public"]["items"]] if kind == "changes" else [],
                  "atomicity": "per-owner-fts-transaction", "gaps": []}
        fingerprint = digest(public)
        public["plan_digest"] = fingerprint
        _state(state)["plans"][public["plan_id"]] = {"kind": "index", "public": deepcopy(public), "digest": fingerprint,
            "pins": pins, "completed": {}, "receipt": None}
        return public

    def _index_execute(self, state, reader, raw):
        _fields(raw, {"plan_id", "expected_digest"})
        saved = _state(state)["plans"].get(raw["plan_id"])
        if saved is None or saved["kind"] != "index":
            raise QueryError("EXPIRED", "索引计划不属于当前查询")
        if saved["digest"] != raw["expected_digest"]:
            raise QueryError("CONFLICT", "索引计划指纹不匹配")
        plan = saved["public"]
        for oid, pinned, _manifest in saved["pins"]:
            owner = self._owner(state, reader, oid)
            head, _ = reader.store.head_manifest(owner)
            if head != pinned:
                raise QueryError("STALE", "索引计划固定 HEAD 已变化；不能用新内容冒充原计划")
        if saved["receipt"] is not None:
            result = deepcopy(saved["receipt"])
            result["watermarks"] = self._watermarks(state, reader, plan["owner_ids"], plan["index"])
            if all(item["state"] == "indexed" for item in result["watermarks"]):
                return result
            saved["completed"] = {}
        catalog = _ProjectionCatalog(reader)
        gaps = []
        for oid, pinned, _manifest in saved["pins"]:
            if oid in saved["completed"]:
                continue
            state.ledger.checkpoint()
            # sync_owner projects the complete canonical snapshot first, then
            # publishes FTS rows/relationships/watermark in one SQLite transaction.
            # Unlike legacy rebuild, this never commits a preliminary deletion.
            projected = index.project_owner(catalog, oid)
            if projected["snapshot"]["head"] != pinned:
                raise QueryError("STALE", "索引投影读取到不同固定代次")
            def boundary(point):
                state.ledger.checkpoint()
                if point == "fts_before_commit":
                    current, _ = reader.store.head_manifest(self._owner(state, reader, oid))
                    if current != pinned:
                        raise QueryError("STALE", "索引提交前规范 HEAD 已变化")
                if self.index_fault is not None:
                    self.index_fault(point)
            db = index.connect(reader.root)
            try:
                # The existing transaction primitive is used directly because
                # sync_owner(vector='off') would also disable an existing vector
                # watermark. A lexical/graph plan must leave that backend alone.
                details = index._sync_fts(db, projected, fault=boundary, force=plan["mode"] in {"repair", "rebuild"})
                state.ledger.checkpoint()
                saved["completed"][oid] = {"owner_id": oid, "generation": projected["generation"], "fts": "indexed", "details": details}
            except (OSError, MemoryError, sqlite3.Error):
                gaps.append("部分索引事务未完成；保留原计划重试，规范记录不重复提交")
            finally:
                db.close()
        pending = [oid for oid in plan["owner_ids"] if oid not in saved["completed"]]
        completed_events = [event for event in plan["event_ids"] if any(
            event == manifest["commit_id"] and oid in saved["completed"] for oid, _head, manifest in saved["pins"] if manifest)]
        # A full owner projection covers all fixed events for that owner, not
        # just its newest manifest; map ownership using the preserved input pages.
        if plan["input_kind"] == "changes":
            completed_events = [item["event_id"] for page_id in plan["page_ids"] for item in _state(state)["pages"][page_id]["public"]["items"] if item["owner_id"] in saved["completed"]]
        result = {"plan_id": plan["plan_id"], "index_status": "pending" if pending else "indexed", "owners": list(saved["completed"].values()),
                  "pending_owners": pending, "completed_events": completed_events,
                  "pending_events": [event for event in plan["event_ids"] if event not in completed_events],
                  "watermarks": self._watermarks(state, reader, plan["owner_ids"], plan["index"]),
                  "resume_cursor": plan["plan_id"] if pending else None, "canonical_writes": 0, "gaps": gaps}
        saved["receipt"] = deepcopy(result)
        return result

    def _representation_list(self, state, reader, raw):
        _fields(raw, {"refs"}, {"definition"})
        definition = parse(raw.get("definition", asdict(state.request.definition)), DefinitionRef)
        definitions.get(definition)
        items = []
        for ref in self._refs(raw):
            state.ledger.charge("candidates", 1)
            record = self._record(state, reader, ref)
            items.append(representations.availability(record, ref, definition))
        return {"items": items, "gaps": []}

    def _representation_plan(self, state, reader, raw):
        _fields(raw, {"refs"}, {"definition"})
        listed = self._representation_list(state, reader, raw)
        if any(item["state"] not in {"direct", "assemblable"} for item in listed["items"]):
            raise QueryError("UNSUPPORTED", "新语义表示需要真实审查草案；请使用 semantic-maintenance 技能入口")
        plan = {"plan_id": "FR-" + str(uuid.uuid4()), "refs": deepcopy(raw["refs"]),
                "definition": deepcopy(raw.get("definition", asdict(state.request.definition))),
                "builder": {"name": "existing-field-assembly", "version": "1"},
                "generation": "never", "canonical": False, "gaps": []}
        fingerprint = digest(plan)
        plan["plan_digest"] = fingerprint
        _state(state)["plans"][plan["plan_id"]] = {"kind": "representation", "public": deepcopy(plan), "digest": fingerprint}
        return plan

    def _representation_build(self, state, reader, raw):
        _fields(raw, {"plan_id", "expected_digest"})
        saved = _state(state)["plans"].get(raw["plan_id"])
        if saved is None or saved["kind"] != "representation":
            raise QueryError("EXPIRED", "表示计划不属于此查询")
        if saved["digest"] != raw["expected_digest"]:
            raise QueryError("CONFLICT", "表示计划指纹不匹配")
        plan = saved["public"]
        result = self._read(state, reader, {"query_id": state.query_id, "refs": plan["refs"], "definition": plan["definition"]})
        return {"plan_id": plan["plan_id"], "derived": result["items"], "content_proposals": [],
                "canonical": False, "canonical_writes": 0, "gaps": result["gaps"]}

    def _candidates(self, state, raw):
        ids = raw.get("candidate_ids")
        if not isinstance(ids, list) or not ids or len(ids) > 1000 or any(not isinstance(cid, str) or cid not in state.candidates for cid in ids):
            raise QueryError("DENIED", "输入只能选择当前查询已有候选")
        return [deepcopy(state.candidates[cid]) for cid in ids]

    def _authorize_candidates(self, state, reader, values):
        """候选身份可以缓存，当前权限和正式复核结论不能从旧页继承。"""
        if state.request.purpose == "formal":
            from .evidence import Evidence
            policy = Evidence(reader)
        for value in values:
            state.ledger.checkpoint()
            for raw_ref in value["refs"]:
                ref = parse(raw_ref, FixedRef)
                if ref.kind == "file":
                    self._file(state, reader, ref)
                else:
                    self._record(state, reader, ref)
            if state.request.purpose == "formal":
                assessed = policy.project([parse(ref, FixedRef) for ref in (value.get("evaluated_claim_refs") or value["refs"])],
                                          state.request.applicability)
                if assessed["rejected"] or not assessed["claims"]:
                    raise QueryError("STALE", "候选的当前复核状态已变化，请重新查询")

    def _deduplicate(self, state, reader, raw):
        _fields(raw, {"candidate_ids"})
        values, output = self._candidates(state, raw), {}
        self._authorize_candidates(state, reader, values)
        for value in values:
            state.ledger.checkpoint()
            key = tuple(sorted((ref["kind"], ref["id"], ref["revision"] or 0, ref["sha256"], ref["locator"] or "") for ref in value["refs"]))
            if key not in output:
                output[key] = value
                continue
            merged = output[key]
            merged["channels"] = list(dict.fromkeys([*merged["channels"], *value["channels"]]))
            hits = {digest(hit): hit for hit in [*merged["hits"], *value["hits"]]}
            merged["hits"] = list(hits.values())
        return {"candidates": list(output.values()), "gaps": [], "identity_policy": "fixed-ref-with-version-and-locator"}

    def _select(self, state, reader, raw):
        _fields(raw, {"candidate_ids", "limit"}, {"strategy", "strategy_version"})
        limit = _limit(raw)
        if raw.get("strategy", "owner-round-robin") != "owner-round-robin" or raw.get("strategy_version", "1") != "1":
            raise QueryError("UNSUPPORTED", "多样性策略或版本未登记")
        values = self._candidates(state, raw)
        self._authorize_candidates(state, reader, values)
        buckets = {}
        for value in values:
            ref = parse(value["refs"][0], FixedRef)
            if ref.kind == "file":
                owner_id = "registered-file"
            else:
                owner_id = self._record(state, reader, ref)["owner_id"]
            buckets.setdefault(owner_id, deque()).append(value)
        selected, seen = [], set()
        while any(buckets.values()) and len(selected) < limit:
            for queue in buckets.values():
                if queue and len(selected) < limit:
                    value = queue.popleft()
                    if value["candidate_id"] not in seen:
                        seen.add(value["candidate_id"])
                        selected.append(value)
        return {"candidates": selected, "omitted": [{"candidate_id": item["candidate_id"], "reason": "owner-round-robin limit"}
            for item in values if item["candidate_id"] not in seen], "strategy": {"name": "owner-round-robin", "version": "1"}, "gaps": []}

    def _rerank(self, state, reader, raw):
        """仅重排显式候选和已提供正文；不启动召回或补读缺失的正文。"""
        _fields(raw, {"candidate_ids", "text_slice_ids", "strategy", "strategy_version"})
        key = (raw["strategy"], raw["strategy_version"])
        if any(not isinstance(part, str) for part in key) or key not in self.rerankers:
            raise QueryError("UNSUPPORTED", "所需重排策略/模型没有已登记的可计量提供器")
        ids = raw["text_slice_ids"]
        if not isinstance(ids, list) or len(ids) > 100 or any(not isinstance(sid, str) for sid in ids) or len(set(ids)) != len(ids):
            raise QueryError("VALIDATION", "重排正文必须是至多 100 个不重复的已读文本片段身份")
        values = list({value["candidate_id"]: value for value in self._candidates(state, raw)}.values())
        self._authorize_candidates(state, reader, values)
        slices = []
        for sid in ids:
            item = _state(state)["slices"].get(sid)
            if item is None:
                raise QueryError("EXPIRED", "正文片段不属于当前查询的实际读取结果")
            slices.append(item)
        def matches(raw_ref, candidate_ref):
            left, right = parse(raw_ref, FixedRef), parse(candidate_ref, FixedRef)
            return (left.kind, left.id, left.revision, left.sha256) == (right.kind, right.id, right.revision, right.sha256) and (
                right.locator is None or right.locator == left.locator)
        if any(not any(matches(item["ref"], ref) for value in values for ref in value["refs"]) for item in slices):
            raise QueryError("DENIED", "显式正文片段不属于输入候选的固定身份或块范围")
        texts, missing, gaps = {}, [], []
        for value in values:
            chosen = [item for item in slices if any(matches(item["ref"], ref) for ref in value["refs"])]
            if not chosen:
                missing.append(value["candidate_id"])
                continue
            for item in chosen:
                if not item["complete"]:
                    gaps.append("部分显式正文片段不完整，重排分数只反映已提供文本")
                for raw_ref in item["required_refs"]:
                    ref = parse(raw_ref, FixedRef)
                    self._file(state, reader, ref) if ref.kind == "file" else self._record(state, reader, ref)
            texts[value["candidate_id"]] = "\n\n".join(item["markdown"] for item in chosen)
        if missing:
            gaps.append("部分输入候选缺少显式正文，保留原候选并列在已评分候选之后；没有隐式补读")
        reservation = state.ledger.reserve({"rerank_items": len(texts)})
        completed, scores, failures = 0, {}, []
        stopped = None
        try:
            with state.ledger.provider(reservation):
                for value in values:
                    cid = value["candidate_id"]
                    if cid not in texts:
                        continue
                    # Debit before invoking the provider. Even a failing scorer
                    # consumed a real attempted item and must not be free on retry.
                    state.ledger.charge("rerank_items", 1)
                    completed += 1
                    try:
                        score = self.rerankers[key](" ".join([state.request.question, *state.request.keywords]).strip(), texts[cid])
                        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
                            raise ValueError("rerank provider returned an invalid score")
                        scores[cid] = float(score)
                    except QueryError:
                        raise
                    except Exception:
                        failures.append(cid)
                        gaps.append("部分重排提供器执行失败，保留原候选与失败诊断")
        except QueryError as exc:
            stopped = exc.code
            gaps.append(exc.message)
        finally:
            state.ledger.settle(reservation, {"rerank_items": completed})
        order = {value["candidate_id"]: position for position, value in enumerate(values)}
        values.sort(key=lambda value: (value["candidate_id"] not in scores, -scores.get(value["candidate_id"], 0.0), order[value["candidate_id"]]))
        return {"candidates": values, "scores": [{"candidate_id": value["candidate_id"], "score": scores[value["candidate_id"]],
                    "score_meaning": "显式正文的确定性词面相关性；不是证据置信度"} for value in values if value["candidate_id"] in scores],
                "strategy": {"name": key[0], "version": key[1], "model": None}, "missing_text": missing, "failed_items": failures,
                "text_slice_ids": ids, "reservation_id": reservation["reservation_id"], "stopped": stopped, "gaps": list(dict.fromkeys(gaps))}

    def _next_step(self, state, reader, raw):
        _fields(raw)
        if state.ledger.remaining("candidates") == 0 or state.ledger.remaining("read_bytes") == 0:
            return {"action": "stop", "reason": "原查询候选或读取预算已耗尽", "gaps": []}
        cursors = [cursor for cursor in state.cursor_ids if cursor not in state.responses]
        if cursors:
            return {"action": "resume", "cursor": cursors[0], "reason": "存在绑定原查询的未读候选页", "gaps": []}
        if state.candidates and state.ledger.remaining("graph_nodes") and state.ledger.remaining("graph_hops"):
            return {"action": "deepen", "reason": "可按固定候选执行受原预算限制的显式深化", "gaps": []}
        return {"action": "stop", "reason": "当前提供器没有获准的后续操作；新查询需独立创建", "gaps": []}

    def _reserve(self, state, reader, raw):
        _fields(raw, {"ceiling"})
        return {"reservation": state.ledger.reserve(raw["ceiling"]), "gaps": []}

    def _settle(self, state, reader, raw):
        _fields(raw, {"reservation", "actual"})
        receipt = state.ledger.settle(raw["reservation"], raw["actual"])
        receipt["gaps"] = ["实际提供器费用超过预约；已如实结算并停止新的查询工作"] if receipt["overrun"] else []
        return receipt

    def _check_cancelled(self, state, reader, raw):
        _fields(raw)
        state.ledger.checkpoint()
        return {"cancelled": False, "gaps": []}

    def _paths(self, raw):
        """将同一深化任务已返回的边组成有序路径，保持方向及目标固定版本。"""
        state, locked = None, False
        try:
            _fields(raw, {"candidate_ids", "target_refs"}, {"direction", "relation_kinds", "cursor", "limit"})
            limit = _limit(raw)
            targets = [parse(ref, FixedRef) for ref in raw["target_refs"]] if isinstance(raw["target_refs"], list) else []
            if not targets or len(targets) > 100:
                raise QueryError("VALIDATION", "路径需要 1..100 个固定目标")
            direction = raw.get("direction", "forward")
            state = self.coordinator.store.get(raw["query_id"])
            # The public deepener owns traversal and charges its own active
            # interval. Path assembly is another interval in the same ledger.
            from .deepening import deepen, _reauthorize
            from .associations import private_state
            request = {"query_id": state.query_id, "candidate_ids": raw["candidate_ids"], "mode": "bounded_graph",
                "direction": direction, "relation_kinds": raw.get("relation_kinds", []), "strategy": "bounded-bfs", "strategy_version": "1", "cursor": raw.get("cursor")}
            result = deepen(self.coordinator, request)
            if result["value"] is None:
                return result
            locked = state.lock.acquire(blocking=False)
            if not locked:
                raise QueryError("CONFLICT", "路径组合时同一查询已有活动操作")
            with state.ledger.active():
                reader = self.coordinator.reader(state)
                for ref in targets:
                    if ref.kind == "file":
                        self._file(state, reader, ref)
                    else:
                        self._record(state, reader, ref)
                signature = digest({**request, "cursor": None})
                job = private_state(state)["jobs"][signature]
                edges = {edge["edge_id"]: edge for page in [*job["responses"].values(), result["value"]] for edge in page["edges"]}
                receipt = {"candidates": [], "edges": list(edges.values())}
                _reauthorize(state, reader, receipt)
                adjacency = {}
                for edge in edges.values():
                    # Diagnostics expose rejected/stale fixed links for review;
                    # they must never reconnect an otherwise disconnected path.
                    if edge["state"] not in {"accepted_navigation", "verified_claim"}:
                        continue
                    left, right = parse(edge["source"], FixedRef), parse(edge["target"], FixedRef)
                    if direction in {"forward", "both"}:
                        adjacency.setdefault(identity(left), []).append((right, edge))
                    if direction in {"reverse", "both"}:
                        adjacency.setdefault(identity(right), []).append((left, edge))
                wanted = {identity(ref) for ref in targets}
                paths = []
                selected = self._candidates(state, raw)
                self._authorize_candidates(state, reader, selected)
                for value in selected:
                    for raw_ref in value["refs"]:
                        seed = parse(raw_ref, FixedRef)
                        queue, seen = deque([(seed, [seed], [])]), {identity(seed)}
                        while queue and len(paths) < limit:
                            state.ledger.checkpoint()
                            ref, refs, edge_ids = queue.popleft()
                            if identity(ref) in wanted:
                                path_edges = [edges[eid] for eid in edge_ids]
                                paths.append({"source": asdict(seed), "target": asdict(ref), "refs": [asdict(r) for r in refs],
                                    "edge_ids": edge_ids, "conditions": list(dict.fromkeys(c for edge in path_edges for c in edge["conditions"])),
                                    "differences": list(dict.fromkeys(c for edge in path_edges for c in edge["differences"]))})
                                continue
                            for target, edge in adjacency.get(identity(ref), []):
                                if identity(target) not in seen and len(edge_ids) < state.ledger.limits["graph_hops"]:
                                    seen.add(identity(target))
                                    queue.append((target, [*refs, target], [*edge_ids, edge["edge_id"]]))
                gaps = list(result["value"]["gaps"])
                reached = {identity(parse(path["target"], FixedRef)) for path in paths}
                if wanted - reached:
                    gaps.append("当前有界关系页未连通全部指定目标；不能据此推断现实中不存在关系")
                payload = {"paths": paths, "edges": list(edges.values()), "next_cursor": result["value"]["next_cursor"],
                           "gaps": list(dict.fromkeys(gaps)), "strategy": "shortest-fixed-bfs/1"}
                output = envelope(payload, state=state, status="partial" if gaps else "ok", warnings=gaps,
                                  basis=scoped_basis(state, reader, list(_extract_fixed(payload))), stop=result["stop_reason"])
            output["consumed"] = state.ledger.snapshot()
            return output
        except Exception as exc:
            return failure(exc, state)
        finally:
            if locked:
                state.lock.release()


def _extract_fixed(value):
    """只识别完整固定引用对象，不把客户端任意字符串当可读路径。"""
    if isinstance(value, dict):
        if set(value) == {"kind", "id", "revision", "sha256", "locator"}:
            yield value
        else:
            for item in value.values():
                yield from _extract_fixed(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _extract_fixed(item)


def _gap_text(gaps):
    return list(dict.fromkeys(item["message"] for item in gaps))
