"""按内容职责召回，并沿作者保存的固定引用展开已有正文。

来源选择只控制直接召回；用户的范围、排除项、可信权限和查询账本始终
控制后续展开。旧 event/map 不冒充叙述经过或研究概览，不推断同归属关系。
"""
from dataclasses import asdict

from .contracts import ContentExpandRequest, FixedRef
from .validation import QueryError, parse

SOURCE_KINDS = {
    "overview_experience": ("overview", "experience"),
    "process": ("narrative",),
    "technical": ("detail",),
}


def references(record, target):
    """新字段优先；旧经验只复用确实保存的固定技术依据，不猜测关联。"""
    payload = record.get("payload", {})
    yield from payload.get("process_refs" if target == "process" else "technical_refs", ())
    if target == "technical" and not payload.get("technical_refs"):
        yield from record.get("sources", ())
        yield from payload.get("evidence_refs", ())


def _expand_candidates(coordinator, raw):
    from memory.errors import MemoryError
    from .coordinator import envelope, failure, current_scope_allows
    from .associations import (candidate, charge_node, charge_edge, endpoint_owner_allowed,
                               identity, make_edge, scoped_basis)
    from .legacy_adapter import from_legacy, memory_error
    state, locked, value = None, False, None
    try:
        request = parse(raw, ContentExpandRequest)
        state = coordinator.store.get(request.query_id)
        locked = state.lock.acquire(blocking=False)
        if not locked:
            raise QueryError("CONFLICT", "同一查询已有活动操作")
        if request.expected_request_digest != state.request_digest or any(
                cid not in state.candidates for cid in request.candidate_ids):
            raise QueryError("CONFLICT", "候选选择不属于本次查询条件")
        if state.request.content_source is None:
            raise QueryError("UNSUPPORTED", "内容展开需使用content_source查询；旧表示查询仍使用deepen")
        with state.ledger.active():
            reader = coordinator.reader(state)
            selected = [state.candidates[cid] for cid in request.candidate_ids]
            coordinator._reauthorize(state, selected, reader=reader)
            value = {"candidates": [], "edges": [], "proposals": [], "next_cursor": None, "gaps": []}
            issues = []
            emitted = set()
            for item in selected:
                for raw_ref in item["refs"]:
                    source = parse(raw_ref, FixedRef)
                    if source.kind not in {"record", "representation"}:
                        value["gaps"].append("原始登记没有规范经过或技术正文的固定展开入口")
                        continue
                    record = reader.record(source)
                    depth = charge_node(state, source, 0)
                    for legacy in references(record, request.target):
                        state.ledger.checkpoint()
                        # Mutable or file references are not an implicit request
                        # to find a current record or to open an original file.
                        if legacy.get("target_kind") != "record" or not legacy.get("sha256") or type(legacy.get("revision")) is not int:
                            continue
                        try:
                            ref = from_legacy(legacy)[0]
                            if not endpoint_owner_allowed(state, reader, ref.id):
                                raise QueryError("DENIED", "关联超出查询范围")
                            target = reader.record(ref)
                            if target["kind"] not in SOURCE_KINDS[request.target]:
                                continue
                            if ref.locator and ref.locator.startswith("block:") and not any(
                                    b.get("block_id") == ref.locator[6:] for b in target["payload"].get("blocks", [])):
                                raise QueryError("SOURCE_MISSING", "固定技术块不存在")
                            if not current_scope_allows(reader, target, state.request):
                                raise QueryError("DENIED", "关联不满足查询范围")
                            if state.request.freshness == "current" and reader.current_record(ref.id)["record_hash"] != ref.sha256:
                                raise QueryError("STALE", "固定关联已有新版，未替换为当前正文")
                            if identity(ref) in emitted:
                                continue
                            charge_node(state, ref, depth + 1)
                            edge = make_edge(source, ref, "references", [source], legacy_relation="content:" + request.target)
                            charge_edge(state, edge)
                            result = candidate(coordinator, state, reader, ref)
                            if result is None:
                                continue
                            state.ledger.charge("candidates", 1)
                            state.ledger.charge("output_chars", coordinator._candidate_chars(result))
                            state.candidates[result["candidate_id"]] = result
                            value["candidates"].append(result)
                            value["edges"].append(edge)
                            emitted.add(identity(ref))
                        except (QueryError, MemoryError) as exc:
                            error = memory_error(exc) if isinstance(exc, MemoryError) else exc
                            if error.code in {"BUDGET", "CANCELLED"}:
                                raise error
                            message = {"DENIED": "部分固定关联超出当前范围或权限，未展开",
                                       "STALE": "部分固定关联版本已变化，未替换为新正文",
                                       "SOURCE_MISSING": "部分固定关联的来源不可用"}.get(error.code, "部分固定关联未通过内容核验")
                            value["gaps"].append(message)
                            issues.append({"code": error.code, "message": message, "affected_refs": [],
                                           "retry": "replan" if error.code == "STALE" else "after_external_change"})
            if not value["candidates"] and not value["gaps"]:
                value["gaps"].append("所选内容未保存通向该类正文的可用固定关联")
            if request.include_packet and value["candidates"] and state.request.association.mode == "existing_only":
                from .associations import add_existing
                supplements, supplement_gaps = add_existing(coordinator, state, reader, value["candidates"])
                for supplement in supplements:
                    state.candidates[supplement["candidate_id"]] = supplement
                value["candidates"].extend(supplements)
                value["gaps"].extend(supplement_gaps)
            value["gaps"] = list(dict.fromkeys(value["gaps"]))
            refs = [r for c in value["candidates"] for r in c["refs"]]
            refs += [asdict(parse(r, FixedRef)) for c in selected for r in c["refs"]]
            result = envelope(value, state=state, status="partial" if value["gaps"] else "ok",
                            warnings=value["gaps"], issues=issues, basis=scoped_basis(state, reader, refs), stop="exhausted")
        result["consumed"] = state.ledger.snapshot()
        return result
    except Exception as exc:
        return failure(exc, state, value=value if value and value["candidates"] else None)
    finally:
        if locked:
            state.lock.release()


def expand(coordinator, raw):
    """候选读取与正文组装依次复用同一个查询；不新建搜索或清空预算。

两步分别持锁并重新授权，避免重入同一个锁；中间即使来源变化，组装也会
拒绝过期材料。候选成功但正文失败时保留部分结果和实际失败，不伪装完成。
"""
    result = _expand_candidates(coordinator, raw)
    value = result.get("value")
    if not isinstance(raw, dict) or not raw.get("include_packet") or not value or not value["candidates"]:
        return result
    assembly = coordinator.assemble({"query_id": raw["query_id"], "candidate_ids": [c["candidate_id"] for c in value["candidates"]],
                                     "expected_request_digest": raw["expected_request_digest"]})
    value["packet"] = assembly.get("value")
    warnings = list(dict.fromkeys([*result["warnings"], *assembly["warnings"]]))
    value["gaps"] = list(dict.fromkeys([*value["gaps"], *assembly["warnings"]]))
    return {**result, "value": value, "status": "ok" if result["status"] == assembly["status"] == "ok" else "partial",
            "code": assembly.get("code") or result.get("code"), "consumed": assembly["consumed"],
            "warnings": warnings, "issues": [*result.get("issues", []), *assembly.get("issues", [])],
            "basis": assembly.get("basis") or result.get("basis")}
