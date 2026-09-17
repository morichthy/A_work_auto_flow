"""固定引用的来源映射与有界图深化，不扩大查询权限或重新创建预算。

游标保存服务端 BFS 队列，不接受客户端 frontier。节点身份包括修订、SHA
和块定位；循环/菱形只计费一次，而请求活动读取仍在每次调用重新授权。
"""
from collections import deque
from copy import deepcopy
from dataclasses import asdict, replace
import uuid

from memory import index
from memory.errors import MemoryError
from memory.evidence_adapter import iter_refs

from .associations import (MANUAL_ENTRY, RELATIONS, _selected, allowed, candidate, charge_edge,
    charge_node, endpoint_owner_allowed, fixed_legacy, identity, make_edge, navigation_edges, private_state, scoped_basis)
from .contracts import DeepenRequest, FixedRef
from .legacy_adapter import fixed_record, memory_error
from .validation import QueryError, parse
from .wire import digest


def _references(record, mode):
    """保留关系的原字段语义；文稿 block_ids 变为精确 block: 定位。"""
    payload = record["payload"]
    if record["kind"] == "document":
        for position, ref in enumerate(payload.get("section_refs", [])):
            yield ref, "contains", "document.section_refs:" + str(position)
    elif record["kind"] == "document_section":
        for position, block in enumerate(payload.get("blocks", [])):
            if block["type"] == "unit":
                for bid in block.get("block_ids", []) or [None]:
                    ref = dict(block["ref"])
                    if bid:
                        ref["locator"] = "block:" + bid
                    yield ref, "contains", "document_section.blocks:" + str(position)
    if mode == "source_mapping":
        # A section's generic sources often name the entire same unit. Returning
        # that in parallel would silently undo the exact authored block selection.
        if record["kind"] not in {"document", "document_section"}:
            for ref in iter_refs({"sources": record.get("sources", []), "evidence_refs": payload.get("evidence_refs", [])}):
                if ref["target_kind"] == "file":
                    yield ref, RELATIONS.get(ref["relation"]), "source_mapping:" + ref["relation"]
        return
    for ref in record.get("sources", []):
        kind = RELATIONS.get(ref["relation"])
        yield ref, kind, "sources:" + ref["relation"]
    # The authored relation is authoritative even inside an evidence/result
    # collection. A containing field does not turn 'references' into 'supports'.
    for key in ("result_refs", "conflict_refs", "evidence_refs", "claim_refs"):
        for ref in payload.get(key, []):
            yield ref, RELATIONS.get(ref["relation"]), key + ":" + ref["relation"]


def _forward(state, reader, ref, mode, kinds, gaps):
    if ref.kind not in {"record", "representation"}:
        return
    record = reader.record(ref)
    if not allowed(state, record, reader=reader):
        raise QueryError("DENIED", "深化节点不满足查询范围")
    seen = set()
    for legacy, kind, relation in _references(record, mode):
        if kind is None:
            # Unknown canonical vocabulary may be readable as content, but it
            # cannot silently become another graph relation or disappear.
            gaps.append("部分规范关系尚无登记的图关系映射；没有改写为其他关系")
            continue
        if kinds and kind not in kinds:
            continue
        if legacy["target_kind"] == "record" and not endpoint_owner_allowed(state, reader, legacy["target_id"]):
            continue
        target = fixed_legacy(reader, legacy)
        edge_identity = (identity(target), kind, relation)
        if edge_identity in seen:
            continue
        seen.add(edge_identity)
        yield make_edge(ref, target, kind, [fixed_record(record)], legacy_relation=relation), target
    if ref.locator and ref.locator.startswith("block:"):
        # Required definitions are graph dependencies with fixed block identity.
        blocks = {b["block_id"]: b for b in record["payload"].get("blocks", [])}
        block = blocks.get(ref.locator[6:])
        if block is None:
            raise QueryError("SOURCE_MISSING", "固定技术块不存在")
        if not kinds or "depends_on" in kinds:
            for bid in block.get("requires_block_ids", []):
                target = fixed_record(record, "block:" + bid)
                yield make_edge(ref, target, "depends_on", [fixed_record(record)],
                                legacy_relation="requires_block_ids"), target


def _neighbors(state, reader, ref, request, gaps):
    """倒查先有界取目录身份，再核验规范引用，绝不信任索引缓存关系。"""
    if request.direction in {"forward", "both"}:
        yield from _forward(state, reader, ref, request.mode, request.relation_kinds, gaps)
    if request.mode == "bounded_graph" and ref.kind == "record":
        for edge, _ in navigation_edges(state, reader, ref, request.direction, request.relation_kinds, include_diagnostics=True):
            target = parse(edge["target"] if edge["source"]["id"] == ref.id else edge["source"], FixedRef)
            yield edge, target
    if request.direction not in {"reverse", "both"}:
        return
    db = index.connect(reader.root, create=False)
    if db is None:
        raise QueryError("SOURCE_MISSING", "反向引用目录不可用")
    limit = state.ledger.remaining("candidates")
    if not limit:
        raise QueryError("BUDGET", "反向引用扫描候选预算不足")
    try:
        # memory_records does not project record.sources. LIKE(payload) alone
        # would miss prerequisite/input edges, so bounded canonical verification
        # is necessary until a complete versioned inverse projection exists.
        rows = list(db.execute("SELECT record_id,owner_id FROM memory_records WHERE entity_kind='record' "
                               "AND kind!='association' AND sensitivity!='restricted' ORDER BY record_id LIMIT ?", (limit + 1,)))
    finally:
        db.close()
    if len(rows) > limit:
        gaps.append("反向引用仅核验有界目录窗口，尚不能保证全量覆盖")
    for row in rows[:limit]:
        state.ledger.checkpoint()
        try:
            reader.owner(row[1])
            if any(scope.owner_ids is not None and row[1] not in scope.owner_ids for scope in (state.request.scope, state.request.scope_ceiling)):
                continue
            state.ledger.charge("candidates", 1)
            source = reader.current_record(row[0])
            if not allowed(state, source, reader=reader):
                continue
            for edge, target in _forward(state, reader, fixed_record(source), request.mode, request.relation_kinds, gaps):
                # A whole-record selection may find an authored block reference;
                # a selected block, however, never matches another block.
                if (target.kind, target.id, target.revision, target.sha256) == (ref.kind, ref.id, ref.revision, ref.sha256) and (
                        not ref.locator or ref.locator == "record" or target.locator == ref.locator):
                    yield edge, fixed_record(source)
        except (QueryError, MemoryError) as exc:
            error = memory_error(exc) if isinstance(exc, MemoryError) else exc
            if error.code in {"BUDGET", "CANCELLED"}:
                raise
            gaps.append("部分反向关系因范围、来源或版本不满足而省略")


def _reauthorize(state, reader, receipt):
    """缓存只保存结果，不保存权限；页重放也读取当前授权/关系状态。"""
    if state.request.purpose == "formal":
        from .evidence import Evidence
        evidence = Evidence(reader)
        for item in receipt["candidates"]:
            refs = item.get("evaluated_claim_refs") or item["refs"]
            current = evidence.project([parse(ref, FixedRef) for ref in refs], state.request.applicability)
            if current["rejected"] or not current["claims"]:
                raise QueryError("STALE", "深化候选的当前复核状态已变化，请重新查询")
    refs = [raw for item in receipt["candidates"] for raw in item["refs"]]
    refs += [raw for edge in receipt["edges"] for raw in [edge["source"], edge["target"], *edge["evidence"]]]
    edge_states = {ref["id"]: edge["state"] for edge in receipt["edges"] for ref in edge["evidence"]}
    for raw in refs:
        ref = parse(raw, FixedRef)
        if ref.kind == "file":
            from .legacy_adapter import to_legacy
            if ref.id in reader.excluded_ids:
                raise QueryError("DENIED", "来源已排除")
            reader.service._file(to_legacy(ref))
        else:
            record = reader.record(ref)
            if record["kind"] == "association":
                expected = {"accepted_navigation": {"accepted"}, "proposed": {"candidate"},
                            "retracted": {"rejected", "withdrawn"},
                            "stale": {"accepted", "candidate", "rejected", "withdrawn"}}.get(edge_states.get(ref.id), {"accepted"})
                if reader.current_record(ref.id)["record_hash"] != ref.sha256 or record["payload"]["status"] not in expected:
                    raise QueryError("STALE", "缓存关系状态已变化")
            elif not allowed(state, record, reader=reader):
                raise QueryError("DENIED", "缓存深化材料已不满足查询范围")


def _basis(state, reader, receipt):
    refs = [ref for item in receipt["candidates"] for ref in item["refs"]]
    refs += [ref for edge in receipt["edges"] for ref in [edge["source"], edge["target"], *edge["evidence"]]]
    return scoped_basis(state, reader, refs)


def deepen(coordinator, raw):
    from .coordinator import envelope, failure
    state, locked, value, reader, job = None, False, None, None, None
    try:
        request = parse(raw, DeepenRequest)
        if request.strategy != "bounded-bfs" or request.strategy_version != "1":
            raise QueryError("UNSUPPORTED", "未登记的深化策略或版本")
        state = coordinator.store.get(request.query_id)
        locked = state.lock.acquire(blocking=False)
        if not locked:
            raise QueryError("CONFLICT", "同一查询已有活动操作")
        with state.ledger.active():
            reader = coordinator.reader(state)
            selected = _selected(state, request.candidate_ids)
            if request.mode == "structural_discovery":
                raise QueryError("UNSUPPORTED", MANUAL_ENTRY)
            graph = private_state(state)
            signature = digest(replace(request, cursor=None))
            key = request.cursor or "first"
            if request.cursor and graph["cursors"].get(request.cursor) != signature:
                raise QueryError("EXPIRED", "深化游标不属于此查询、种子或策略")
            job = graph["jobs"].get(signature)
            if job is None:
                job = {"frontier": deque(), "pending": deque(), "expanded": set(), "emitted": set(), "responses": {}}
                for item in selected:
                    for raw_ref in item["refs"]:
                        ref = parse(raw_ref, FixedRef)
                        if ref.kind == "file":
                            fixed_legacy(reader, {"target_kind": "file", "target_id": ref.id, "revision": ref.revision,
                                "sha256": ref.sha256, "locator": ref.locator or "", "relation": "references"})
                        elif not allowed(state, reader.record(ref), reader=reader):
                            raise QueryError("DENIED", "选定材料已不满足查询范围")
                        depth = charge_node(state, ref, 0)
                        job["frontier"].append((ref, depth))
                        job["emitted"].add(identity(ref))
                graph["jobs"][signature] = job
            if key in job["responses"]:
                receipt = deepcopy(job["responses"][key])
                _reauthorize(state, reader, receipt)
                result = envelope(receipt, state=state, status="partial" if receipt["gaps"] else "ok",
                    warnings=receipt["gaps"], basis=_basis(state, reader, receipt), stop="page" if receipt["next_cursor"] else "exhausted")
            else:
                if job.get("terminal"):
                    raise QueryError(*job["terminal"])
                value = {"candidates": [], "edges": [], "proposals": [], "next_cursor": None, "gaps": []}
                page_edges = set()
                page_limit = state.request.result_limit
                while (job["pending"] or job["frontier"]) and len(value["candidates"]) < page_limit and len(value["edges"]) < page_limit:
                    state.ledger.checkpoint()
                    if not job["pending"]:
                        ref, depth = job["frontier"].popleft()
                        if identity(ref) in job["expanded"]:
                            continue
                        job["expanded"].add(identity(ref))
                        if depth >= state.ledger.limits["graph_hops"]:
                            value["gaps"].append("已到本查询累计图深度边界，更深引用未展开")
                            continue
                        try:
                            for edge, target in _neighbors(state, reader, ref, request, value["gaps"]):
                                job["pending"].append((edge, target, depth + 1))
                        except (QueryError, MemoryError) as exc:
                            error = memory_error(exc) if isinstance(exc, MemoryError) else exc
                            if error.code in {"BUDGET", "CANCELLED"}:
                                raise
                            value["gaps"].append(error.message if error.code == "STALE" else "部分深化关系因范围或来源不满足而省略")
                        if not job["pending"]:
                            continue
                    edge, target, depth = job["pending"][0]
                    # Pending edges can cross HTTP requests: authorize their full
                    # fixed chain again before exposing identities or prose.
                    try:
                        _reauthorize(state, reader, {"candidates": [], "edges": [edge]})
                        if edge["state"] not in {"accepted_navigation", "verified_claim"}:
                            # Rejected/stale edges remain visible as authorized
                            # diagnostic evidence, but never introduce a node,
                            # candidate, frontier, or a navigable path.
                            if edge["edge_id"] not in page_edges:
                                charge_edge(state, edge)
                                state.ledger.charge("output_chars", sum(map(len, (*edge["conditions"], *edge["differences"]))))
                                page_edges.add(edge["edge_id"])
                                value["edges"].append(edge)
                            value["gaps"].append("已有关系引用旧修订，未用于导航" if edge["state"] == "stale" else "关系尚未采纳或已被拒绝/撤回，保留诊断但不用于导航")
                            job["pending"].popleft()
                            continue
                        item = candidate(coordinator, state, reader, target)
                        if item is None:
                            value["gaps"].append("部分深化内容不满足所选类型或范围")
                            job["pending"].popleft()
                            continue
                        new_node = identity(target) not in job["emitted"]
                        node_depth = charge_node(state, target, depth)
                        charge_edge(state, edge)
                        if new_node:
                            state.ledger.charge("candidates", 1)
                            state.ledger.charge("output_chars", len(item["excerpt"]))
                            state.candidates[item["candidate_id"]] = item
                            value["candidates"].append(item)
                            job["emitted"].add(identity(target))
                            job["frontier"].append((target, node_depth))
                        if edge["edge_id"] not in page_edges:
                            state.ledger.charge("output_chars", sum(map(len, (*edge["conditions"], *edge["differences"]))))
                            page_edges.add(edge["edge_id"])
                            value["edges"].append(edge)
                        job["pending"].popleft()
                    except (QueryError, MemoryError) as exc:
                        error = memory_error(exc) if isinstance(exc, MemoryError) else exc
                        if error.code in {"BUDGET", "CANCELLED"}:
                            raise
                        value["gaps"].append(error.message if error.code == "STALE" else "部分深化关系因范围或来源不满足而省略")
                        job["pending"].popleft()
                if job["pending"] or job["frontier"]:
                    cursor = str(uuid.uuid4())
                    graph["cursors"][cursor] = signature
                    value["next_cursor"] = cursor
                value["gaps"] = list(dict.fromkeys(value["gaps"]))
                job["responses"][key] = deepcopy(value)
                result = envelope(value, state=state, status="partial" if value["gaps"] else "ok", warnings=value["gaps"],
                    basis=_basis(state, reader, value), stop="page" if value["next_cursor"] else "exhausted")
        result["consumed"] = state.ledger.snapshot()
        return result
    except Exception as exc:
        error = memory_error(exc) if isinstance(exc, MemoryError) else exc
        if job is not None and isinstance(error, QueryError) and error.code in {"BUDGET", "CANCELLED"}:
            job["terminal"] = (error.code, error.message)
        partial = value if value and (value["candidates"] or value["edges"]) and isinstance(error, QueryError) and error.code in {"BUDGET", "CANCELLED"} else None
        return failure(error, state, value=partial)
    finally:
        if locked:
            state.lock.release()
