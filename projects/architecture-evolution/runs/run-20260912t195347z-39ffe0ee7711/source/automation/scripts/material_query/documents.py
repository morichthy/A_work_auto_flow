"""将召回命中连接到其 Owner 已编排文稿；同一固定文稿只交付一次。

这是读取已有发布内容，不是把零散命中临时综合成报告。Owner 归属是明确
组织关系，不用同关键词猜测科学关联。全部读取沿原权限、版本与预算。
"""
from dataclasses import asdict
from memory import index
from memory.errors import MemoryError
from .assembly import Assembler
from .contracts import DefinitionRef, FixedRef, FullDocumentsRequest
from .legacy_adapter import fixed_record, memory_error
from .validation import QueryError, parse


def full_documents(coordinator, raw):
    from .coordinator import current_scope_allows, required_scope_allows, envelope, failure
    state, locked, packet, aggregate = None, False, None, None
    matches = []
    try:
        request = parse(raw, FullDocumentsRequest)
        state = coordinator.store.get(request.query_id)
        locked = state.lock.acquire(blocking=False)
        if not locked:
            raise QueryError("CONFLICT", "同一查询已有活动操作")
        if request.expected_request_digest != state.request_digest or any(cid not in state.candidates for cid in request.candidate_ids):
            raise QueryError("CONFLICT", "候选选择不属于本次查询条件")
        if state.request.purpose == "formal":
            raise QueryError("UNSUPPORTED", "完整文稿包含尚未逐结论核验的正文；请在探索/审计查询读取，正式用途继续使用结论组包")
        with state.ledger.active():
            reader = coordinator.reader(state)
            selected = [state.candidates[cid] for cid in request.candidate_ids]
            coordinator._reauthorize(state, selected, reader=reader)
            by_owner, explicit = {}, {}
            for item in selected:
                for raw_ref in item["refs"]:
                    ref = parse(raw_ref, FixedRef)
                    if ref.kind == "owner":
                        by_owner.setdefault(ref.id, set()).add(item["candidate_id"])
                        continue
                    if ref.kind not in {"record", "representation"}:
                        continue
                    record = reader.record(ref)
                    by_owner.setdefault(record["owner_id"], set()).add(item["candidate_id"])
                    if record["kind"] == "document" and record["payload"]["document_type"] == request.document_type:
                        # 一个逻辑文稿最多返回一次；显式所选固定版本优先于目录最新版。
                        prior = explicit.get(ref.id)
                        cids = {item["candidate_id"]} | (prior[1] if prior else set())
                        explicit[ref.id] = (prior[0] if prior else record, cids)
            documents, gaps, issues = dict(explicit), [], []
            db = index.connect(coordinator.root, create=False)
            if db is None:
                raise QueryError("SOURCE_MISSING", "文稿目录索引尚未建立")
            try:
                for oid, cids in by_owner.items():
                    chosen = [key for key, (doc, _) in documents.items() if doc["owner_id"] == oid]
                    if chosen:
                        for key in chosen:
                            documents[key][1].update(cids)
                        continue
                    # 索引只定位文稿 ID。按当前规范日期选择同类型的最新文稿，
                    # 不信任索引 payload 的正文、版本或权限。
                    limit = state.ledger.remaining("candidates")
                    rows = db.execute("SELECT record_id FROM memory_records WHERE owner_id=? AND entity_kind='record' AND kind='document' ORDER BY record_id LIMIT ?", (oid, limit + 1)).fetchall()
                    choices = []
                    if len(rows) > limit:
                        gaps.append("文稿目录达到候选预算，未覆盖所有登记文稿")
                    for row in rows[:limit]:
                        state.ledger.charge("candidates", 1)
                        try:
                            doc = reader.current_record(row[0])
                            if doc["kind"] != "document" or doc["payload"]["document_type"] != request.document_type:
                                continue
                            # 已由命中确定 Owner，全文读取不再套用命中条目的
                            # L1/L3 等内容筛选，否则 level=null 的文稿永远不可达。
                            if not required_scope_allows(reader, doc, state.request):
                                continue
                            choices.append(doc)
                        except (QueryError, MemoryError) as exc:
                            error = memory_error(exc) if isinstance(exc, MemoryError) else exc
                            if error.code in {"BUDGET", "CANCELLED"}:
                                raise error
                            gaps.append("部分文稿因范围、来源或版本不满足而省略")
                    if choices:
                        doc = max(choices, key=lambda r: (r["updated_at"], r["revision"], r["record_id"]))
                        ref = fixed_record(doc)
                        key = ref.id
                        old = documents.get(key)
                        documents[key] = (doc, set(cids) | (old[1] if old else set()))
                    elif not any(doc["owner_id"] == oid for doc, _ in documents.values()):
                        gaps.append("部分命中的归属对象没有可读取的对应文稿；未临时生成")
            finally:
                db.close()
            aggregate = Assembler(reader, state.ledger, lambda record: current_scope_allows(reader, record, state.request))
            for doc, cids in documents.values():
                ref = fixed_record(doc)
                assembler = Assembler(reader, state.ledger, lambda record: required_scope_allows(reader, record, state.request),
                                      required_allowed=lambda record: required_scope_allows(reader, record, state.request))
                try:
                    assembler.add_record(ref, DefinitionRef("full", "1"), state.request.question)
                    # 保持每段正文与自己的固定图示绑定，不拼平后让两篇单元的
                    # figure:0 相互覆盖。文稿只保存有序段索引，正文不重复输出。
                    state.ledger.charge("output_chars", len(doc["title"]) + sum(len(p["heading"]) for p in assembler.parts))
                    indices = list(range(len(aggregate.parts), len(aggregate.parts) + len(assembler.parts)))
                    aggregate.parts.extend(assembler.parts)
                    aggregate.contributors.update(assembler.contributors)
                    aggregate.contributors[(ref.id, ref.revision, ref.sha256)] = ref
                    matches.append({"ref": asdict(ref), "title": doc["title"], "candidate_ids": sorted(cids),
                                    "complete": not assembler.gaps, "part_indices": indices})
                except QueryError as exc:
                    if exc.code in {"BUDGET", "CANCELLED"}:
                        raise
                    assembler.gap(exc.message, code=exc.code, ref=ref)
                gaps.extend(assembler.gaps)
                issues.extend(assembler.issues)
            aggregate.gaps = list(dict.fromkeys(gaps))
            aggregate.issues = issues
            if not matches and not gaps:
                aggregate.gaps.append("所选条目没有可读取的完整文稿")
            packet = coordinator._packet(state, aggregate)
            packet["documents"] = matches
            result = envelope(packet, state=state, status="partial" if aggregate.gaps else "ok", warnings=aggregate.gaps,
                              issues=issues, basis=reader.basis(), stop="exhausted")
        result["consumed"] = state.ledger.snapshot()
        return result
    except Exception as exc:
        # 后续文稿预算耗尽时交付已完整组装的前文稿，不把先前结果清空。
        if aggregate is not None and aggregate.parts:
            packet = coordinator._packet(state, aggregate)
            packet["documents"] = matches
        if packet:
            packet["complete"] = False
        return failure(exc, state, value=packet)
    finally:
        if locked:
            state.lock.release()
