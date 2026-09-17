"""有界既有导航与人工决策；规范写入只调用 memory 的公开动作。

索引提供候选身份，规范记录和当前授权决定边是否可读。导航接受不创建
claim/review，也不把结构相似解释为科学支持。模型不可用时提供真实技能入口。
"""
from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace
import uuid

from memory import api, index
from memory.contracts import canonical_hash
from memory.errors import MemoryError

from .contracts import AssociationRequest, FixedRef
from .legacy_adapter import fixed_record, memory_error, to_legacy
from .validation import QueryError, object_fields, parse


MANUAL_ENTRY = ("未配置可执行且可计量的结构联想提供器；请使用关联探索技能入口 "
                "automation/workflows/association-exploration/SKILL.md，提交固定引用、共同机制、差异、迁移条件与反证检查。")
RELATIONS = {"input": "input", "references": "references", "same_entity": "same_entity", "mentions": "mentions",
             "prerequisite": "depends_on", "depends_on": "depends_on", "similar_structure": "similar_structure",
             "analogous_to": "similar_structure", "same_problem": "similar_structure",
             "same_failure_mode": "similar_structure", "supports": "supports",
             "contradicts": "contradicts", "supersedes": "supersedes", "contains": "contains",
             "precedes": "precedes", "member_of": "member_of"}


def private_state(state):
    """短期状态仅存在查询实例，不与公开搜索 resume 的响应字典混用。"""
    if not hasattr(state, "_material_graph"):
        state._material_graph = {"nodes": {}, "edges": set(), "jobs": {}, "cursors": {}, "decisions": {}}
    return state._material_graph


def identity(ref):
    return (ref.kind, ref.id, ref.revision, ref.sha256, ref.locator)


def charge_node(state, ref, depth):
    """图深度是从最初查询根累计的最大层数，后续选中已发现节点不能重置。"""
    graph = private_state(state)
    key = identity(ref)
    if key not in graph["nodes"]:
        state.ledger.charge("graph_nodes", 1)
        graph["nodes"][key] = depth
    else:
        depth = graph["nodes"][key]
    used = state.ledger.used["graph_hops"]
    if depth > used:
        state.ledger.charge("graph_hops", depth - used)
    return depth


def charge_edge(state, edge):
    known = private_state(state)["edges"]
    if edge["edge_id"] not in known:
        state.ledger.charge("graph_edges", 1)
        known.add(edge["edge_id"])


def fixed_legacy(reader, value):
    """旧引用允许缺 SHA；仅从其指定规范修订补全，绝不改为最新内容。"""
    kind, target = value["target_kind"], value["target_id"]
    if kind == "record":
        record = reader.store.read_record(reader.locate(target), target, value.get("revision"))
        if value.get("sha256") and value["sha256"] != record["record_hash"]:
            raise QueryError("STALE", "关联端点固定指纹不匹配")
        locator = value.get("locator")
        ref = fixed_record(record, None if locator in {None, "", "record"} else locator)
        reader.record(ref)
        return ref
    if kind == "file":
        # 仅授权与登记检查；真正原件字节读取在组包阶段计费。
        if target in reader.excluded_ids:
            raise QueryError("DENIED", "来源已排除")
        reader.service._file(value)
        return parse({"kind": "file", "id": target, "revision": value.get("revision"),
                    "sha256": value.get("sha256"), "locator": value.get("locator") or None}, FixedRef)
    raise QueryError("UNSUPPORTED", "此图端点尚无有界固定读取适配器")


def scope_state(state, *, supplement=False):
    scope = state.request.association.supplement_scope if supplement else None
    return SimpleNamespace(request=replace(state.request, scope=scope), query_id=state.query_id) if scope is not None else state


def allowed(state, record, *, reader, supplement=False):
    from .coordinator import current_scope_allows
    request = scope_state(state, supplement=supplement).request
    return current_scope_allows(reader, record, request)


def endpoint_owner_allowed(state, reader, target_id, *, supplement=False):
    """先用身份目录排除越界 owner，不为已知越界端点打开规范正文。"""
    owner = reader.locate(target_id)
    request = scope_state(state, supplement=supplement).request
    return all(scope.owner_ids is None or owner["owner_id"] in scope.owner_ids
               for scope in (request.scope, request.scope_ceiling))


def scoped_basis(state, reader, refs):
    """只有真正输出的固定依据进入回执，不把被筛掉的试读材料带入 basis。"""
    basis = reader.basis()
    permitted = {(ref["id"], ref["revision"], ref["sha256"]) for ref in refs}
    basis["refs"] = [ref for ref in basis["refs"] if (ref["id"], ref["revision"], ref["sha256"]) in permitted]
    ceiling = state.request.scope_ceiling.owner_ids
    basis["owner_heads"] = [pair for pair in basis["owner_heads"] if ceiling is None or pair[0] in ceiling]
    return basis


def candidate(coordinator, state, reader, ref, *, group="required_context", supplement=False):
    """深化材料复用正常表示/用途准入，并按完整固定引用区分单元内的块。"""
    if ref.kind == "file":
        reader.service._file(to_legacy(ref))
        scopes = (scope_state(state, supplement=supplement).request.scope, state.request.scope_ceiling)
        if ref.id in reader.excluded_ids or any(
                scope.source_ids is not None and ref.id not in scope.source_ids for scope in scopes):
            return None
        # 原件不伪造科学复核，也不在只请求知识记录时混进结果。
        if state.request.purpose == "formal" or any(scope.kinds is not None or scope.levels is not None for scope in scopes):
            return None
        value = {"candidate_id": "", "refs": [asdict(ref)], "title": "已登记原始材料", "excerpt": "",
                 "channels": ["graph"], "score": 0.0, "realization": {
                     "definition": {"key": "original", "version": "1"}, "refs": [asdict(ref)],
                     "state": "direct", "missing_selectors": [], "generator_version": None},
                 "evidence_status": "not-reviewed", "group": group, "hits": [],
                 "evaluated_claim_refs": [], "unresolved_claim_refs": []}
    else:
        if not endpoint_owner_allowed(state, reader, ref.id, supplement=supplement):
            return None
        # Supplement exclusions are additive and temporary for this read. The
        # initial request exclusions always remain in reader.excluded_ids.
        old_exclusions = set(reader.excluded_ids)
        scope = scope_state(state, supplement=supplement).request.scope
        reader.excluded_ids.update((*scope.exclude_ids, *scope.excluded_owner_ids, *(r.id for r in scope.excluded_refs)))
        try:
            record = reader.record(ref)
        finally:
            reader.excluded_ids = old_exclusions
        value = coordinator.make_candidate(scope_state(state, supplement=supplement), reader, record,
            {"rank_channels": {"graph": 1}, "score": 0.0}, {}, state.request.question, group=group)
        if value is None:
            return None
        value["refs"] = [asdict(ref)]
        value["realization"]["refs"] = [asdict(ref)]
        for hit in value["hits"]:
            hit["score_meaning"] = "既有固定关系导航；不是知识置信度"
            hit["representation_refs"] = [asdict(ref)]
        if ref.locator and ref.locator.startswith("block:"):
            value["realization"]["definition"] = {"key": "section", "version": "1"}
    value["candidate_id"] = "C-" + canonical_hash({"query": state.query_id, "ref": asdict(ref), "group": group})[:24]
    return value


def make_edge(source, target, kind, evidence, *, legacy_relation, state="accepted_navigation", conditions=(), differences=()):
    # These refs identify the canonical record that authored this edge. They are
    # provenance references, not a claim that the target is scientifically true.
    # Keep the original field/relation in the identity so parallel authored links
    # with the same endpoints do not disappear during page or graph deduplication.
    evidence_relations = ["references"] * len(evidence)
    return {"edge_id": "GE-" + canonical_hash({"source": asdict(source), "target": asdict(target),
                "kind": kind, "evidence": [asdict(ref) for ref in evidence],
                "evidence_relations": evidence_relations, "legacy_relation": legacy_relation})[:24],
            "source": asdict(source), "target": asdict(target), "kind": kind,
            "evidence": [asdict(ref) for ref in evidence], "state": state,
            "conditions": list(conditions), "differences": list(differences),
            "proposer": "canonical:" + legacy_relation, "generator_version": "existing-relations/1",
            "evidence_relations": evidence_relations, "legacy_relation": legacy_relation}


def navigation_edges(state, reader, seed, direction="both", relation_kinds=(), *, include_diagnostics=False):
    """SQL 只取有限边身份；正文读取、端点版本和状态全部重新核验。"""
    db = index.connect(reader.root, create=False)
    if db is None:
        raise QueryError("SOURCE_MISSING", "关系索引尚未建立")
    try:
        where, args = ("from_id=?", [seed.id]) if direction == "forward" else (
            ("to_id=?", [seed.id]) if direction == "reverse" else ("(from_id=? OR to_id=?)", [seed.id, seed.id]))
        limit = state.ledger.remaining("graph_edges") + 1
        rows = list(db.execute("SELECT association_id,owner_id,from_id,to_id FROM memory_edges WHERE " + where + " ORDER BY association_id LIMIT ?", [*args, limit]))
    finally:
        db.close()
    for row in rows:
        state.ledger.checkpoint()
        if state.request.scope_ceiling.owner_ids is not None and row[1] not in state.request.scope_ceiling.owner_ids:
            continue
        if any(not endpoint_owner_allowed(state, reader, target, supplement=target != seed.id) for target in (row[2], row[3])):
            continue
        record = reader.current_record(row[0])
        p = record["payload"]
        relation = p.get("relation")
        kind = RELATIONS.get(relation)
        if kind is None or relation in {"supports", "input"}:
            continue
        edge_state = {"accepted": "accepted_navigation", "candidate": "proposed",
                      "rejected": "retracted", "withdrawn": "retracted"}.get(p.get("status"))
        if edge_state is None or edge_state != "accepted_navigation" and not include_diagnostics:
            continue
        if relation_kinds and kind not in relation_kinds:
            continue
        source, target = fixed_legacy(reader, p["from"]), fixed_legacy(reader, p["to"])
        # Association reuse is about current navigation: an edge fixed to r1 is
        # explicitly stale after r2, even while the historical r1 remains readable.
        if any(ref.kind == "record" and reader.current_record(ref.id)["record_hash"] != ref.sha256 for ref in (source, target)):
            if not include_diagnostics:
                raise QueryError("STALE", "已有关系引用旧修订，须重新判断后才可导航")
            edge_state = "stale"
        if not any(ref.id == seed.id and (edge_state == "stale" or
                   ref.revision == seed.revision and ref.sha256 == seed.sha256) for ref in (source, target)):
            continue
        yield make_edge(source, target, kind, [fixed_record(record)], legacy_relation=relation,
                        state=edge_state, conditions=p.get("transfer_limits", []), differences=p.get("differences", [])), record


def add_existing(coordinator, state, reader, found):
    """搜索的独立联想组；补充范围可不同，但仍受 ceiling、原排除与授权约束。"""
    options = state.request.association
    if options.max_items == 0 or options.output_share == 0:
        return [], []
    results, gaps, seen = [], [], {identity(parse(ref, FixedRef)) for item in found for ref in item["refs"]}
    excerpt_limit = int(state.ledger.remaining("output_chars") * options.output_share)
    excerpt_used = 0
    for item in found:
        for raw in item["refs"]:
            seed = parse(raw, FixedRef)
            if seed.kind != "record":
                continue
            try:
                depth = charge_node(state, seed, 0)
                # 一条旧关系不能阻断同一来源后面的有效补充。诊断边只用于
                # 说明缺口，仍仅把当前 accepted_navigation 的端点交付正文。
                for edge, _ in navigation_edges(state, reader, seed, include_diagnostics=True):
                    if edge["state"] != "accepted_navigation":
                        if edge["state"] == "stale":
                            gaps.append("已有关系引用旧修订，须重新判断后才可导航")
                        continue
                    target = parse(edge["target"] if edge["source"]["id"] == seed.id else edge["source"], FixedRef)
                    if identity(target) in seen:
                        continue
                    value = candidate(coordinator, state, reader, target, group="association", supplement=True)
                    if value is None:
                        continue
                    length = len(value["excerpt"])
                    if excerpt_used + length > excerpt_limit:
                        gaps.append("联想篇幅达到预留比例，剩余关系未展开")
                        return results, gaps
                    charge_node(state, target, depth + 1)
                    charge_edge(state, edge)
                    state.ledger.charge("candidates", 1)
                    state.ledger.charge("output_chars", length)
                    excerpt_used += length
                    seen.add(identity(target))
                    results.append(value)
                    if len(results) >= options.max_items:
                        return results, gaps
            except (QueryError, MemoryError) as exc:
                error = memory_error(exc) if isinstance(exc, MemoryError) else exc
                gaps.append(error.message if error.code in {"BUDGET", "CANCELLED", "STALE"} else "部分关系因范围或来源不满足而省略")
                if error.code in {"BUDGET", "CANCELLED"}:
                    return results, gaps
    return results, list(dict.fromkeys(gaps))


def _selected(state, ids):
    if not ids or len(set(ids)) != len(ids):
        raise QueryError("VALIDATION", "请选择不重复的实际候选")
    if any(cid not in state.candidates for cid in ids):
        raise QueryError("DENIED", "候选不属于本次查询")
    return [state.candidates[cid] for cid in ids]


def discover(coordinator, raw):
    from .coordinator import envelope, failure
    state, locked = None, False
    try:
        request = parse(raw, AssociationRequest)
        state = coordinator.store.get(request.query_id)
        locked = state.lock.acquire(blocking=False)
        if not locked:
            raise QueryError("CONFLICT", "同一查询已有活动操作")
        with state.ledger.active():
            reader = coordinator.reader(state)
            selected = _selected(state, request.seed_candidate_ids)
            if request.profile is not None or state.request.association.mode == "explore_structural":
                raise QueryError("UNSUPPORTED", MANUAL_ENTRY)
            if state.request.association.mode == "off":
                raise QueryError("VALIDATION", "本次查询未开启联想，不能在续接时绕过原开关")
            output, gaps = [], []
            maximum = state.request.association.max_items
            if maximum == 0:
                return envelope([], state=state, stop="exhausted")
            for item in selected:
                for raw_ref in item["refs"]:
                    seed = parse(raw_ref, FixedRef)
                    if seed.kind != "record":
                        continue
                    record = reader.record(seed)
                    if not allowed(state, record, reader=reader):
                        raise QueryError("DENIED", "选定材料已不满足查询范围")
                    try:
                        for edge, record in navigation_edges(state, reader, seed):
                            refs = [parse(edge[key], FixedRef) for key in ("source", "target")]
                            if any(not allowed(state, reader.record(ref), reader=reader, supplement=ref.id != seed.id) for ref in refs):
                                continue
                            charge_node(state, seed, 0)
                            for ref in refs:
                                charge_node(state, ref, private_state(state)["nodes"][identity(seed)] + (ref.id != seed.id))
                            charge_edge(state, edge)
                            pid = "AP-" + canonical_hash({"query": state.query_id, "edge": edge["edge_id"]})[:24]
                            proposal = {"proposal_id": pid, "source": [edge["source"]], "target": [edge["target"]],
                                "common_structure": record["payload"].get("shared_structure", ""), "differences": list(edge["differences"]),
                                "transfer_conditions": record["payload"].get("transfer_limits", []),
                                "verification_hint": "仅作导航；在目标条件下独立验证，不能据此接受科学主张。",
                                "method": "existing-relations/1:" + record["payload"]["relation"], "state": "accepted_navigation"}
                            text_size = sum(len(value) for value in [proposal["common_structure"], proposal["verification_hint"],
                                            *proposal["differences"], *proposal["transfer_conditions"]])
                            state.ledger.charge("output_chars", text_size)
                            state.proposals[pid] = {"public": proposal, "association_ref": asdict(fixed_record(record))}
                            if pid not in {p["proposal_id"] for p in output}:
                                output.append(proposal)
                            if len(output) >= maximum:
                                break
                    except QueryError as exc:
                        if exc.code != "STALE":
                            raise
                        gaps.append(exc.message)
                    if len(output) >= maximum:
                        break
                if len(output) >= maximum:
                    break
            refs = [ref for p in output for ref in [*p["source"], *p["target"], state.proposals[p["proposal_id"]]["association_ref"]]]
            result = envelope(output, state=state, status="partial" if gaps else "ok", warnings=gaps,
                              basis=scoped_basis(state, reader, refs), stop="exhausted")
        result["consumed"] = state.ledger.snapshot()
        return result
    except Exception as exc:
        return failure(exc, state)
    finally:
        if locked:
            state.lock.release()


def decide(coordinator, raw):
    """幂等、绑定固定提议的接受/拒绝；复核状态完全交给原规范服务。"""
    from .coordinator import envelope, failure
    state, locked, committed = None, False, None
    try:
        object_fields(raw, {"query_id", "proposal_id", "decision", "reason", "request_id"})
        if raw["decision"] not in {"accept_navigation", "reject"} or not isinstance(raw["reason"], str) or not raw["reason"].strip():
            raise QueryError("VALIDATION", "需要明确的导航决策和理由")
        try:
            uuid.UUID(raw["request_id"])
        except (ValueError, TypeError, AttributeError):
            raise QueryError("VALIDATION", "决策 request_id 必须是 UUID")
        state = coordinator.store.get(raw["query_id"])
        locked = state.lock.acquire(blocking=False)
        if not locked:
            raise QueryError("CONFLICT", "同一查询已有活动操作")
        with state.ledger.active():
            saved = state.proposals.get(raw["proposal_id"])
            if saved is None:
                raise QueryError("DENIED", "提议不属于本次查询")
            reader = coordinator.reader(state)
            for endpoint in saved["public"]["source"] + saved["public"]["target"]:
                ref = parse(endpoint, FixedRef)
                record = reader.record(ref)
                if not (allowed(state, record, reader=reader) or allowed(state, record, reader=reader, supplement=True)):
                    raise QueryError("DENIED", "关系端点已不满足查询范围")
                if reader.current_record(ref.id)["record_hash"] != ref.sha256:
                    saved["public"]["state"] = "stale"
                    raise QueryError("STALE", "提议端点已变更，请重新发现")
            decisions = private_state(state)["decisions"]
            fingerprint = canonical_hash(raw)
            old = decisions.get(raw["request_id"])
            if old is not None:
                if old["digest"] != fingerprint:
                    raise QueryError("CONFLICT", "同一 request_id 不能改写决策")
                pending = old["receipt"].get("index_status") != "indexed"
                return envelope(deepcopy(old["proposal"]), state=state, status="partial" if pending else "ok",
                    warnings=["导航决策已保存；关系索引待显式更新"] if pending else [], basis=reader.basis(), stop="completed")
            fixed = parse(saved["association_ref"], FixedRef)
            record = reader.record(fixed)
            if reader.current_record(fixed.id)["record_hash"] != fixed.sha256:
                raise QueryError("STALE", "规范关系已变更，请重新发现")
            payload = deepcopy(record["payload"])
            payload["status"] = "accepted" if raw["decision"] == "accept_navigation" else "rejected"
            # Preserve every original condition and evidence ref. The application
            # never invents support or promotes an event claim on accept_navigation.
            owner = reader.owner(record["owner_id"])
            head, _ = reader.store.head_manifest(owner)
            draft = {"owner_id": record["owner_id"], "kind": "association", "title": record["title"],
                "body_markdown": record["body_markdown"], "keywords": record["keywords"], "payload": payload,
                "sources": deepcopy(payload["basis_refs"]), "provenance_gap": record["provenance_gap"],
                "record_reason": raw["reason"], "change_reason": raw["reason"],
                "sensitivity": record["sensitivity"], "discovery": record["discovery"]}
            request = {"schema_version": 1, "request_id": raw["request_id"], "actor": {"kind": "workflow", "id": "material-query"},
                       "owner_id": record["owner_id"], "expected_head": head["commit_id"] if head else None,
                       "operations": [{"op": "decide_association", "record_id": record["record_id"],
                                       "expected_revision": record["revision"], "draft": draft}]}
            # The proposal is bound to an EXISTING association whose endpoints
            # and relation cannot change here. Use the public dedicated operation
            # so the legacy discovery helper need not scan unrelated owners.
            from .writer import Writer
            main, supplement, ceiling = state.request.scope, state.request.association.supplement_scope or state.request.scope, state.request.scope_ceiling
            def union_then_ceiling(field):
                first, second, cap = getattr(main, field), getattr(supplement, field), getattr(ceiling, field)
                requested = None if first is None or second is None else set(first) | set(second)
                if cap is not None:
                    requested = set(cap) if requested is None else requested & set(cap)
                return requested
            owner_ids = union_then_ceiling("owner_ids")
            if coordinator.access_owner_ids is not None:
                owner_ids = set(coordinator.access_owner_ids) if owner_ids is None else owner_ids & set(coordinator.access_owner_ids)
            writer = Writer(reader.root, state.ledger, access_owner_ids=owner_ids,
                            excluded_ids=reader.excluded_ids, source_ids=union_then_ceiling("source_ids"))
            receipt = api.dispatch(writer, "commit", request)
            proposal = deepcopy(saved["public"])
            proposal["state"] = "accepted_navigation" if raw["decision"] == "accept_navigation" else "rejected"
            saved["public"] = proposal
            committed = proposal
            decisions[raw["request_id"]] = {"digest": fingerprint, "proposal": deepcopy(proposal), "receipt": receipt}
            pending = receipt.get("index_status") != "indexed"
            result = envelope(proposal, state=state, status="partial" if pending else "ok",
                warnings=["导航决策已保存；关系索引待显式更新"] if pending else [], basis=reader.basis(), stop="completed")
        result["consumed"] = state.ledger.snapshot()
        return result
    except Exception as exc:
        return failure(exc, state, value=committed)
    finally:
        if locked:
            state.lock.release()
