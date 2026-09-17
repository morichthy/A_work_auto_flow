"""有界语义维护任务包与显式应用；不自动猜测修订、不伪造语义审查。

plan 只产生 defer 候选和完整内容交付回执。review 记录人工/AI 明确提交的
逐项判断并预检草案，保存新的不可覆盖版本。apply 绑定该版本及稳定请求 ID，
经现有 memory 公共动作逐 owner 提交，持久记录每一步，支持失败后安全续查。
"""
from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
import re
import sqlite3
from types import SimpleNamespace
import uuid

from memory import api, contracts as memory_contracts, index, owners
from memory.evidence_adapter import iter_refs
from memory.errors import MemoryError
from memory.technical_units import is_unit, render_full

from .budget import DEFAULT_BUDGET, Ledger
from .contracts import FixedRef, MaintenancePlan, MaintenanceRequest, MaintenanceStatusReceipt, MaintenanceStatusRequest, Scope
from .legacy_adapter import fixed_record, from_legacy, memory_error
from .reader import Reader
from .validation import QueryError, object_fields, parse
from .wire import digest, json_value
from .writer import Writer


BASE = ".local/material-query/plans"
PLAN_ID = re.compile(r"MP-[0-9a-f-]{36}")
HASH = re.compile(r"[0-9a-f]{64}")
WRITE_ACTIONS = {"revise", "resynthesize", "retract"}
EDITABLE_KINDS = {"detail", "event", "narrative", "experience", "map", "overview", "document", "document_section", "representation"}


def _result(value=None, *, state=None, warnings=(), basis=None, status=None):
    from .coordinator import envelope
    return envelope(json_value(value), state=state, status=status or ("partial" if warnings else "ok"), warnings=warnings, basis=json_value(basis))


def _error(exc, state=None, value=None, basis=None):
    from .coordinator import failure
    return failure(exc, state, value=json_value(value), basis=json_value(basis))


def _key(ref):
    value = asdict(ref) if isinstance(ref, FixedRef) else ref
    # 一份完整记录交付覆盖它的所有块定位；仍固定类型、修订和指纹。
    return (value["kind"], value["id"], value["revision"], value["sha256"])


def _path(root, relative):
    return owners.safe_path(root, relative)


def _read(path, reader=None):
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise QueryError("INTERNAL", "维护计划超过受控存储上限")
        # 状态查询沿既有 query 的账本读取持久计划；其完整上下文 JSON 也
        # 是真实读取，不能因为属于 .local 就绕过 read_bytes 硬上限。
        return reader.store.read_json(path) if reader is not None else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QueryError("SOURCE_MISSING", "维护计划或执行回执不可用") from exc


def _write_once(path, value):
    """创建不可覆盖 JSON；同一路径只允许字节完全相同的幂等重试。"""
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise QueryError("CONFLICT", "不可覆盖已有维护版本或请求身份")
        return
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _locked(root, plan_id):
    path = _path(root, f"{BASE}/{plan_id}/operation.lock")
    lock = {"pid": os.getpid(), "token": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise QueryError("CONFLICT", "维护计划已有活动操作；遗留锁需检查后恢复") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(lock, stream)
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        # 不删除不属于本次操作的锁；不扫描或递归清理计划目录。
        if path.exists() and _read(path) == lock:
            path.unlink()


def _plan_digest(value):
    return digest({key: item for key, item in value.items() if key != "plan_digest"})


def _save(root, value, metadata):
    value["plan_digest"] = _plan_digest(value)
    path = _path(root, f"{BASE}/{value['plan_id']}/{value['plan_digest']}.json")
    stored = {"schema_version": 1, "plan": value, **metadata}
    stored["storage_digest"] = digest(stored)
    if path.exists():
        prior = _load(root, value["plan_id"], value["plan_digest"])
        if prior["plan"] == value and all(prior.get(key) == metadata.get(key) for key in ("request", "parent_digest", "reviewed")):
            return  # 同一明确审查重试回读原版本，不用新的计时数覆盖原审计。
    _write_once(path, stored)


def _load(root, plan_id, expected_digest, reader=None):
    if not isinstance(plan_id, str) or not PLAN_ID.fullmatch(plan_id) or not isinstance(expected_digest, str) or not HASH.fullmatch(expected_digest):
        raise QueryError("VALIDATION", "维护计划身份或指纹不合法")
    stored = _read(_path(root, f"{BASE}/{plan_id}/{expected_digest}.json"), reader)
    if not isinstance(stored, dict) or not isinstance(stored.get("plan"), dict):
        raise QueryError("INTERNAL", "维护计划存储结构损坏")
    if (stored.get("schema_version") != 1 or stored.get("storage_digest") != digest({k: v for k, v in stored.items() if k != "storage_digest"})
            or stored.get("plan", {}).get("plan_id") != plan_id or stored["plan"].get("plan_digest") != expected_digest
            or _plan_digest(stored["plan"]) != expected_digest):
        raise QueryError("INTERNAL", "维护计划存储指纹不匹配")
    parse(stored["plan"], MaintenancePlan)
    return stored


def _operation(coordinator, scope):
    state = SimpleNamespace(ledger=Ledger(DEFAULT_BUDGET))
    access = None if coordinator.access_owner_ids is None else set(coordinator.access_owner_ids)
    if scope.owner_ids is not None:
        access = set(scope.owner_ids) if access is None else access & set(scope.owner_ids)
    excluded = {*scope.excluded_owner_ids, *scope.exclude_ids, *(ref.id for ref in scope.excluded_refs)}
    reader = Reader(coordinator.root, state.ledger, access_owner_ids=access, excluded_ids=excluded)
    return state, reader


def _writer(coordinator, state, reader, scope):
    return Writer(coordinator.root, state.ledger, access_owner_ids=reader.access_owner_ids,
                  excluded_ids=reader.excluded_ids, source_ids=scope.source_ids)


def _allowed(record, scope):
    from .coordinator import record_allowed
    return record_allowed(record, scope)


def _read_fixed(reader, ref, scope):
    if ref.kind in {"record", "representation"}:
        record = reader.record(ref)
        if not _allowed(record, scope):
            raise QueryError("DENIED", "维护对象不在保存的范围内")
        return record
    if ref.kind == "file":
        if scope.source_ids is not None and ref.id not in scope.source_ids:
            raise QueryError("DENIED", "维护原件不在保存的来源范围内")
        return reader.file_bytes(ref)
    raise QueryError("UNSUPPORTED", "维护任务包首期仅接收规范记录和已登记原件")


def _body(record):
    """交付完整规范语义字段，不能用检索摘要冒充完整技术单元。"""
    body = render_full(record) if is_unit(record) else record.get("body_markdown", "")
    # payload JSON 保留 claim、范围、反证、文稿固定引用等全部字段；正文仍
    # 独立显示 Markdown/LaTeX，便于审查者阅读公式与技术块。
    return "\n\n".join(text for text in (body, "```json\n" + json.dumps({key: record[key] for key in memory_contracts.CONTENT_FIELDS if key != "body_markdown"}, ensure_ascii=False, indent=2) + "\n```") if text)


def _contexts(reader, targets, scope):
    parts, delivered, dependencies, gaps = [], {}, {}, []
    queued = deque((ref, None) for ref in targets)
    seen = set()
    while queued:
        ref, parent = queued.popleft()
        key = _key(ref)
        if parent is not None:
            dependencies.setdefault(parent, set()).add(key)
        if key in seen:
            continue
        seen.add(key)
        try:
            value = _read_fixed(reader, ref, scope)
            if ref.kind == "file":
                try:
                    body = value.decode("utf-8-sig")
                except UnicodeError:
                    gaps.append("二进制原件已核验但尚未交付可审查预览；涉及它的判断须延后")
                    continue
                title, selector = "已登记原始材料", "source.content"
            else:
                title, selector, body = value["title"], "canonical.complete", _body(value)
                for legacy in iter_refs({"sources": value["sources"], "payload": value["payload"]}):
                    try:
                        child, _ = from_legacy(legacy)
                    except QueryError:
                        gaps.append("部分声明来源缺少完整固定引用，尚未交付")
                        dependencies.setdefault(key, set()).add(("unresolved", legacy["target_id"], None, None))
                        continue
                    dependencies.setdefault(key, set()).add(_key(child))
                    queued.append((child, key))
            if len(body) > reader.ledger.remaining("output_chars"):
                gaps.append("输出预算不足以交付完整内容；未交付对象只能保持延后")
                continue
            reader.ledger.charge("output_chars", len(body))
            parts.append({"group": "direct" if parent is None else "required_context", "heading": title,
                          "markdown": body, "refs": [asdict(ref)], "selectors": [selector], "omitted": []})
            delivered[key] = asdict(ref)
        except (QueryError, MemoryError) as exc:
            error = memory_error(exc) if isinstance(exc, MemoryError) else exc
            if error.code in {"BUDGET", "CANCELLED"}:
                gaps.append("预算不足，未完成全部维护上下文交付")
                break
            if error.code == "DENIED":
                raise
            gaps.append(error.message)
    # 每项语义判断需覆盖其全部声明来源；有限闭包中的循环按 visited 去重。
    requirements = {}
    for ref in targets:
        start, pending, reached = _key(ref), [_key(ref)], set()
        while pending:
            key = pending.pop()
            if key in reached:
                continue
            reached.add(key)
            pending.extend(dependencies.get(key, ()))
        requirements[ref.id] = [list(key) for key in sorted(reached, key=str)]
    return parts, delivered, requirements, gaps


def plan(coordinator, raw):
    """产生可审查任务包；共享词项只是影响候选，不是语义一致性的判断。"""
    state = None
    try:
        request = parse(json_value(raw), MaintenanceRequest)
        if request.strategy != "dependency-review" or request.strategy_version != "1":
            raise QueryError("UNSUPPORTED", "维护策略或版本未注册")
        if not request.changed_refs:
            raise QueryError("VALIDATION", "维护计划需要至少一个固定变化来源")
        state, reader = _operation(coordinator, request.scope)
        targets, keywords, reasons, unchecked = {}, set(), {}, ["尚未执行语义判断；初始动作全部为defer", "未调用语义向量、模型或未登记旧Run来源；不能据此声称覆盖全部影响"]
        with state.ledger.active():
            for ref in request.changed_refs:
                state.ledger.charge("candidates", 1)
                value = _read_fixed(reader, ref, request.scope)
                if ref.kind in {"record", "representation"}:
                    targets[ref.id] = ref
                    keywords.update(value.get("keywords", []))
                    reasons[ref.id] = ["本次显式变化来源，等待逐项审查"]
            db = index.connect(coordinator.root, create=False)
            if db is None:
                unchecked.append("索引不可用，仅形成显式变化对象的任务包")
            else:
                try:
                    visible = []
                    for oid in reader.views:
                        try:
                            reader.owner(oid)
                        except QueryError:
                            continue
                        visible.append(oid)
                    if visible:
                        slots = ",".join("?" for _ in visible)
                        clauses, parameters = [], [*visible]
                        for column, values in (("kind", request.scope.kinds), ("COALESCE(level,'unlayered')", request.scope.levels)):
                            if values is not None:
                                clauses.append(" AND " + column + " IN (" + ",".join("?" for _ in values) + ")" if values else " AND 0")
                                parameters.extend(values)
                        parameters.append(state.ledger.remaining("candidates"))
                        rows = db.execute(f"""SELECT record_id,keywords FROM memory_records
                            WHERE owner_id IN ({slots}) AND entity_kind='record'
                            AND kind IN ('detail','event','narrative','experience','map','overview','document','document_section','feedback')
                            {''.join(clauses)} ORDER BY record_id LIMIT ?""", parameters).fetchall()
                        changed_ids = {ref.id for ref in request.changed_refs}
                        for row in rows:
                            if row["record_id"] in targets:
                                continue
                            state.ledger.charge("candidates", 1)
                            try:
                                record = reader.current_record(row["record_id"])
                            except (QueryError, MemoryError) as exc:
                                error = memory_error(exc) if isinstance(exc, MemoryError) else exc
                                if error.code in {"BUDGET", "CANCELLED"}:
                                    raise
                                unchecked.append("部分维护候选未满足范围、来源或版本条件，已省略")
                                continue
                            if not _allowed(record, request.scope):
                                continue
                            references = {ref["target_id"] for ref in iter_refs({"sources": record["sources"], "payload": record["payload"]})}
                            direct = bool(references & changed_ids)
                            topical = bool(keywords & set(record.get("keywords", [])))
                            if direct or topical:
                                ref = fixed_record(record)
                                targets[ref.id] = ref
                                reasons[ref.id] = ["声明引用指向变化来源，需审查" if direct else "共享主题词的候选，尚未判断语义影响"]
                        if len(rows) >= state.ledger.remaining("candidates"):
                            unchecked.append("候选扫描有数量上限，未保证穷尽反向依赖与无边新反证")
                finally:
                    db.close()
            parts, delivered, requirements, gaps = _contexts(reader, [*targets.values(), *[ref for ref in request.changed_refs if ref.kind == "file"]], request.scope)
            unchecked.extend(gaps)
            basis = reader.basis()
            # 只保留用户选择/实际任务项及其明确来源，避免试读但未入选候选
            # 的身份进入对外依据。当前 owner HEAD 仍用于保守 CAS 核对。
            public_refs = {_key(ref) for ref in targets.values()} | set(delivered)
            basis["refs"] = [ref for ref in basis["refs"] if _key(ref) in public_refs]
            value = {"plan_id": "MP-" + str(uuid.uuid4()), "plan_digest": "", "basis": basis,
                "items": [{"ref": asdict(ref), "action": "defer", "reasons": reasons[ref.id],
                           "affected_refs": [asdict(changed) for changed in request.changed_refs], "draft_json": None} for ref in targets.values()],
                "reviewed_refs": [], "unchecked_regions": list(dict.fromkeys(unchecked)), "semantic_reviewer": None,
                "context_items": parts, "read_receipt": "READ-" + str(uuid.uuid4()), "review_note": "", "reviewer_kind": None}
            _save(coordinator.root, value, {"request": json_value(request), "reviewed": False, "parent_digest": None,
                "delivered_refs": list(delivered.values()), "requirements": requirements,
                "delivery_note": "此回执仅证明完整内容已交付，不证明审查者理解或科学结论有效",
                "consumed": state.ledger.snapshot()})
        return _result(value, state=state, warnings=value["unchecked_regions"], basis=basis)
    except (QueryError, MemoryError, OSError, ValueError) as exc:
        return _error(exc, state)


def _verify_basis(reader, saved, *, completed=None):
    scope = parse(saved["request"]["scope"], Scope)
    for raw in saved["plan"]["basis"]["refs"]:
        _read_fixed(reader, parse(raw, FixedRef), scope)
    for oid, expected in saved["plan"]["basis"]["owner_heads"]:
        owner = reader.owner(oid)
        head, _ = reader.store.head_manifest(owner)
        current = head["commit_id"] if head else None
        if current != (completed or {}).get(oid, expected):
            raise QueryError("CONFLICT", "维护依据HEAD已变化，请重新形成计划")


def _draft(item, original, delivered):
    if item["action"] in {"retain", "defer"}:
        if item["draft_json"] is not None:
            raise QueryError("VALIDATION", "保留/延后动作不能夹带写入草案")
        return None
    if not item["draft_json"]:
        raise QueryError("VALIDATION", "修订或撤回必须提供具体可预检草案")
    try:
        draft = json.loads(item["draft_json"])
    except (ValueError, TypeError) as exc:
        raise QueryError("VALIDATION", "维护草案不是合法JSON") from exc
    if not isinstance(draft, dict):
        raise QueryError("VALIDATION", "维护草案必须为JSON对象")
    if item["action"] == "retract":
        object_fields(draft, {"claim_id", "reason"})
        if not isinstance(draft["claim_id"], str) or not isinstance(draft["reason"], str) or not draft["reason"].strip() or draft["claim_id"] not in {
                claim["claim_id"] for claim in original["payload"].get("claims", [])}:
            raise QueryError("VALIDATION", "撤回必须明确该记录内的claim与原因")
        return draft
    # 仅放行统一层级的两条迁移路径；完整正文和前版固定引用由统一写入门检查。
    migration = (original["kind"], draft.get("kind")) in {("event", "narrative"), ("map", "overview")}
    if original["kind"] not in EDITABLE_KINDS or draft.get("owner_id") != original["owner_id"] or (draft.get("kind") != original["kind"] and not migration):
        raise QueryError("DENIED", "维护草案不能改变归属/类型或写入复核与控制记录")
    expected_version = 4 if draft.get("kind") in {"narrative", "overview"} or (draft.get("kind") == "experience" and draft.get("schema_version") == 4) else 3
    if draft.get("schema_version") != expected_version:
        raise QueryError("VALIDATION", "维护修订必须符合该类型的当前草案版本")
    for legacy in iter_refs({"sources": draft.get("sources", []), "payload": draft.get("payload", {})}):
        ref, _ = from_legacy(legacy)
        if _key(ref) not in delivered:
            raise QueryError("DENIED", "草案引用尚未交付审查的来源，请先重建维护任务包")
    return draft


def _requests(value, originals, request_id):
    """按 owner 形成稳定公共请求；普通修订合批，撤回复用 review 动作。"""
    groups = {}
    actor = {"kind": value["reviewer_kind"], "id": value["semantic_reviewer"]}
    heads = dict(value["basis"]["owner_heads"])
    for item in value["items"]:
        if item["action"] not in WRITE_ACTIONS:
            continue
        record = originals[item["ref"]["id"]]
        oid = record["owner_id"]
        groups.setdefault(oid, []).append((item, record))
    results = []
    for oid, entries in sorted(groups.items()):
        rid = str(uuid.uuid5(uuid.UUID(request_id), "owner:" + oid))
        retractions = [item for item, _ in entries if item["action"] == "retract"]
        if retractions:
            if len(entries) != 1:
                raise QueryError("UNSUPPORTED", "首期同一owner的撤回须使用独立维护计划")
            item, record = entries[0]
            draft = json.loads(item["draft_json"])
            request = {"schema_version": 1, "request_id": rid, "actor": actor, "owner_id": oid,
                       "expected_head": heads[oid], "target_claim_id": draft["claim_id"],
                       "expected_content_hash": record["content_hash"], "state": "retracted",
                       "reason": draft["reason"], "scope": None, "evidence_refs": [], "replacement_claim_id": None}
            results.append((oid, "review", request))
        else:
            operations = [{"op": "put_record", "record_id": record["record_id"], "expected_revision": record["revision"],
                           "draft": json.loads(item["draft_json"])} for item, record in entries]
            results.append((oid, "commit", {"schema_version": 1, "request_id": rid, "actor": actor,
                "owner_id": oid, "expected_head": heads[oid], "operations": operations}))
    return results


def review(coordinator, raw):
    state = None
    try:
        raw = object_fields(json_value(raw), {"plan", "expected_digest"})
        proposed = json_value(parse(raw["plan"], MaintenancePlan))
        saved = _load(coordinator.root, proposed["plan_id"], raw["expected_digest"])
        with _locked(coordinator.root, proposed["plan_id"]):
            # 两端按同一契约补齐可选默认字段。旧回执没有 figures 时，
            # JSON 回填解析会补 []；这不是篡改。实际正文、图像和引用仍逐值核对。
            original = json_value(parse(saved["plan"], MaintenancePlan))
            protected = ("plan_id", "plan_digest", "basis", "context_items", "read_receipt", "unchecked_regions")
            if any(proposed[key] != original[key] for key in protected):
                raise QueryError("CONFLICT", "审查不得篡改已交付依据、上下文、读取回执或原版本")
            if not proposed["semantic_reviewer"] or not proposed["semantic_reviewer"].strip() or proposed["reviewer_kind"] not in {"human", "ai"} or not proposed["review_note"].strip():
                raise QueryError("VALIDATION", "审查必须记录具体身份、人工/AI类型及审查说明")
            if len(proposed["items"]) != len(original["items"]) or any(
                    item["ref"] != old["ref"] or item["affected_refs"] != old["affected_refs"] for item, old in zip(proposed["items"], original["items"])):
                raise QueryError("CONFLICT", "审查不能增删或替换服务端计划项")
            delivered = {_key(ref) for ref in saved["delivered_refs"]}
            reviewed = {_key(ref) for ref in proposed["reviewed_refs"]}
            if not reviewed <= delivered:
                raise QueryError("DENIED", "不能自报已审查尚未交付的固定内容")
            scope = parse(saved["request"]["scope"], Scope)
            state, reader = _operation(coordinator, scope)
            with state.ledger.active():
                _verify_basis(reader, saved)
                originals = {}
                for item in proposed["items"]:
                    if not item["reasons"] or any(not text.strip() for text in item["reasons"]):
                        raise QueryError("VALIDATION", "每个维护动作需要具体原因")
                    required = {tuple(key) for key in saved["requirements"][item["ref"]["id"]]}
                    for affected in item["affected_refs"]:
                        required.add(_key(affected))
                        required.update(tuple(key) for key in saved["requirements"].get(affected["id"], []))
                    if item["action"] != "defer" and not required <= reviewed:
                        raise QueryError("DENIED", "此项完整内容或必要来源尚未交付并确认审查")
                    record = _read_fixed(reader, parse(item["ref"], FixedRef), scope)
                    originals[record["record_id"]] = record
                    _draft(item, record, delivered)
                service = _writer(coordinator, state, reader, scope)
                preflight_id = str(uuid.uuid5(uuid.NAMESPACE_URL, proposed["plan_id"] + ":" + digest(proposed)))
                for _, action, request in _requests(proposed, originals, preflight_id):
                    api.dispatch(service, "validate-draft" if action == "commit" else "review", {**request, "dry_run": True})
                reader.ledger.checkpoint()
                metadata = {key: deepcopy(value) for key, value in saved.items() if key not in {"schema_version", "plan", "storage_digest", "parent_digest", "reviewed", "consumed"}}
                metadata.update(reviewed=True, parent_digest=original["plan_digest"], consumed=state.ledger.snapshot())
                _save(coordinator.root, proposed, metadata)
            return _result(proposed, state=state, basis=proposed["basis"], warnings=["已保存明确审查记录；读取交付与草案预检不证明语义或科学有效性"])
    except (QueryError, MemoryError, OSError, ValueError) as exc:
        return _error(exc, state)


def apply(coordinator, raw):
    state, value, basis = None, None, None
    try:
        raw = object_fields(json_value(raw), {"plan_id", "expected_digest", "request_id"})
        try:
            request_id = str(uuid.UUID(raw["request_id"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise QueryError("VALIDATION", "维护应用request_id必须为UUID") from exc
        saved = _load(coordinator.root, raw["plan_id"], raw["expected_digest"])
        if not saved["reviewed"]:
            raise QueryError("DENIED", "维护计划尚未经过显式审查")
        scope, basis = parse(saved["request"]["scope"], Scope), saved["plan"]["basis"]
        state, reader = _operation(coordinator, scope)
        binding = {"plan_id": raw["plan_id"], "plan_digest": raw["expected_digest"], "request_id": request_id}
        with _locked(coordinator.root, raw["plan_id"]), state.ledger.active():
            _write_once(_path(coordinator.root, f"{BASE}/requests/{request_id}.json"), binding)
            attempt = f"{BASE}/{raw['plan_id']}/apply/{request_id}"
            start_path = _path(coordinator.root, attempt + "/start.json")
            receipts = {}
            originals = {item["ref"]["id"]: _read_fixed(reader, parse(item["ref"], FixedRef), scope) for item in saved["plan"]["items"]}
            derived_requests = [list(item) for item in _requests(saved["plan"], originals, request_id)]
            if start_path.exists():
                start = _read(start_path)
                if start["binding"] != binding or start.get("requests") != derived_requests or start.get("basis") != basis:
                    raise QueryError("CONFLICT", "维护应用请求身份已绑定其他内容")
                requests = start["requests"]
            else:
                _verify_basis(reader, saved)
                requests = derived_requests
                start = {"binding": binding, "requests": requests, "basis": basis,
                         "recovery_note": "逐owner规范提交；没有跨owner原子回滚。保留旧修订，以原request_id核查重试；不覆盖后续修改。"}
                _write_once(start_path, start)
            # 已有正式 ledger 可识别“提交成功但临时回执落盘前中断”，不重新
            # 提交内容，也不能把其他人的 HEAD 变化误认为本次完成。
            completed = {}
            for position, (oid, action, request) in enumerate(requests):
                path = _path(coordinator.root, attempt + f"/owner-{position:04d}.json")
                owner = reader.owner(oid)
                head, manifest = reader.store.head_manifest(owner)
                request_hash = (Writer.request_hash(request) if action == "commit" else memory_contracts.canonical_hash({
                    "operation": "review", "request": {key: item for key, item in request.items() if key not in {"request_id", "dry_run"}}}))
                # 正式存储的带哈希回执是完成身份的权威来源；临时恢复文件
                # 只加索引说明，不能自报某个别人的 COM 已完成本次请求。
                canonical = reader.store._receipt(owner, {"manifest": manifest}, request["request_id"], request_hash)
                if path.exists():
                    receipt = _read(path)
                    if canonical is None or any(receipt.get(key) != canonical.get(key) for key in
                            ("request_id", "owner_id", "commit_id", "save_status", "record_results")):
                        raise QueryError("CONFLICT", "临时完成回执不匹配规范提交")
                    receipts[oid] = receipt
                    completed[oid] = receipt["commit_id"]
                elif canonical and head and canonical["commit_id"] == head["commit_id"]:
                    completed[oid] = canonical["commit_id"]
            _verify_basis(reader, saved, completed=completed)
            pending = [item["ref"]["id"] for item in saved["plan"]["items"] if item["action"] == "defer"
                       or item["action"] in WRITE_ACTIONS and reader.locate(item["ref"]["id"])["owner_id"] not in receipts]
            recovery_ref = attempt + "/start.json"
            value = {"commits": [[oid, receipt["commit_id"]] for oid, receipt in receipts.items()], "pending_items": pending,
                     "index_status": "pending" if any(r["index_status"] != "indexed" for r in receipts.values()) else "indexed", "recovery_receipt": recovery_ref}
            service = _writer(coordinator, state, reader, scope)
            for position, (oid, action, request) in enumerate(requests):
                if oid in receipts:
                    continue
                reader.ledger.checkpoint()
                receipt = api.dispatch(service, action, request)
                if receipt.get("save_status") not in {"committed", "no_change"} or not receipt.get("commit_id"):
                    raise QueryError("INTERNAL", "规范提交没有返回可验证成功身份")
                receipts[oid] = receipt
                value["commits"].append([oid, receipt["commit_id"]])
                applied_ids = {item["ref"]["id"] for item in saved["plan"]["items"] if item["action"] in WRITE_ACTIONS
                               and reader.locate(item["ref"]["id"])["owner_id"] == oid}
                value["pending_items"] = [rid for rid in value["pending_items"] if rid not in applied_ids]
                if receipt.get("index_status") != "indexed":
                    value["index_status"] = "pending"
                _write_once(_path(coordinator.root, attempt + f"/owner-{position:04d}.json"), receipt)
            _write_once(_path(coordinator.root, attempt + "/completed.json"), value)
            warnings = []
            if value["index_status"] != "indexed":
                warnings.append("规范内容已保存，索引尚待补偿；使用memory reconcile重试投影，不重复业务写入")
            if value["pending_items"]:
                warnings.append("延后项保持未处理")
            return _result(value, state=state, basis=basis, warnings=warnings)
    except (QueryError, MemoryError, OSError, ValueError) as exc:
        if value is not None and not value["commits"]:
            value = None
        return _error(exc, state, value=value, basis=basis)


def _status_files(reader, folder, pattern):
    """只枚举给定计划的直接子项；每项计入候选预算，不递归扫描其他计划。"""
    if not folder.exists():
        return []
    selected = []
    for path in folder.iterdir():
        reader.ledger.checkpoint()
        reader.ledger.charge("candidates", 1)
        if pattern.fullmatch(path.name):
            selected.append(_path(reader.root, path.relative_to(reader.root).as_posix()))
    return sorted(selected, key=lambda path: path.name)


def _status_read_fixed(state, reader, ref, scope):
    """当前调用与原计划范围同时有效；计划身份本身不能扩大重新授权。"""
    from .coordinator import current_scope_allows
    if ref.kind == "file" and any(selected.source_ids is not None and ref.id not in selected.source_ids
            for selected in (state.request.scope, state.request.scope_ceiling)):
        raise QueryError("DENIED", "维护来源不在当前允许范围")
    value = _read_fixed(reader, ref, scope)
    # 状态读取用于审计已执行事务，必须能回读计划原版；当前授权与筛选
    # 仍复核。是否可继续应用由 basis_stale / HEAD 校验独立表达。
    from dataclasses import replace
    audit_request = replace(state.request, freshness="fixed")
    if ref.kind in {"record", "representation"} and not current_scope_allows(reader, value, audit_request):
        raise QueryError("DENIED", "维护材料不满足当前查询范围")
    return value


def _status_request_hash(action, request):
    return Writer.request_hash(request) if action == "commit" else memory_contracts.canonical_hash({
        "operation": "review", "request": {key: item for key, item in request.items() if key not in {"request_id", "dry_run"}}})


def _status_attempt(reader, plan_id, path, versions, originals):
    """临时 start 只定位请求；完成事实始终回到有哈希的规范 request ledger。"""
    try:
        request_id = str(uuid.UUID(path.name))
    except ValueError as exc:
        raise QueryError("INTERNAL", "维护执行目录身份损坏") from exc
    start = _read(_path(reader.root, path.relative_to(reader.root).as_posix() + "/start.json"), reader)
    if not isinstance(start, dict) or not isinstance(start.get("binding"), dict):
        raise QueryError("INTERNAL", "维护执行回执结构损坏")
    binding = start.get("binding", {})
    plan_digest = binding.get("plan_digest")
    if (binding != {"plan_id": plan_id, "plan_digest": plan_digest, "request_id": request_id}
            or plan_digest not in versions):
        raise QueryError("CONFLICT", "维护执行回执与保存的计划不匹配")
    saved = versions[plan_digest]
    expected = [list(item) for item in _requests(saved["plan"], originals[plan_digest], request_id)]
    if start.get("requests") != expected or start.get("basis") != saved["plan"]["basis"]:
        raise QueryError("CONFLICT", "维护执行请求与固定计划不匹配")
    receipts, pending, local_receipts = [], [], []
    for position, (oid, action, request) in enumerate(expected):
        owner = reader.owner(oid)
        _head, manifest = reader.store.head_manifest(owner)
        canonical = reader.store._receipt(owner, {"manifest": manifest}, request["request_id"], _status_request_hash(action, request))
        local = _path(reader.root, path.relative_to(reader.root).as_posix() + f"/owner-{position:04d}.json")
        if local.exists():
            stored = _read(local, reader)
            if not isinstance(stored, dict) or canonical is None or any(stored.get(key) != canonical.get(key) for key in
                    ("request_id", "owner_id", "commit_id", "save_status", "record_results")):
                raise QueryError("CONFLICT", "维护临时回执不匹配规范完成事实")
            local_receipts.append(oid)
        if canonical is None:
            pending.append(oid)
        else:
            receipts.append(canonical)
    completed_path = _path(reader.root, path.relative_to(reader.root).as_posix() + "/completed.json")
    if completed_path.exists():
        completed = _read(completed_path, reader)
        if not isinstance(completed, dict) or pending or completed.get("commits") != [[row["owner_id"], row["commit_id"]] for row in receipts]:
            raise QueryError("CONFLICT", "维护完成摘要与规范事务不一致")
    return {"request_id": request_id, "plan_digest": plan_digest,
            "state": "partial" if pending and receipts else "started" if pending else "committed" if expected else "no_changes",
            "completed_owner_ids": [row["owner_id"] for row in receipts], "pending_owner_ids": pending,
            "local_receipt_owner_ids": local_receipts, "local_completed": completed_path.exists(),
            "recovery_receipt": path.relative_to(reader.root).as_posix() + "/start.json"}, receipts


def _status_commit(reader, receipt):
    """投影明确类型的提交事实，不把任意旧回执字典塞入新契约。"""
    owner, changes = reader.owner(receipt["owner_id"]), []
    for change in receipt["record_results"]:
        record = reader.store.read_record(owner, change["record_id"], change["revision"])
        ref = fixed_record(record)
        reader.record(ref)
        if record["content_hash"] != change["content_hash"]:
            raise QueryError("INTERNAL", "规范回执与提交记录的内容指纹不一致")
        changes.append({"ref": asdict(ref), "content_hash": change["content_hash"],
                        "client_key": change["client_key"], "status": change["status"]})
    return {key: receipt[key] for key in ("request_id", "owner_id", "commit_id", "generation", "save_status")} | {
        "changes": changes, "receipt_sha256": memory_contracts.canonical_hash(receipt)}


def _status_indexes(reader, owner_ids):
    """只读实际 HEAD 与派生水位，既不调用全 owner 正文 status 也不补偿索引。"""
    db = index.connect(reader.root, create=False)
    output = []
    try:
        available = db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_index_state'").fetchone()
        for oid in sorted(owner_ids):
            reader.ledger.checkpoint()
            owner = reader.owner(oid)
            head, _manifest = reader.store.head_manifest(owner)
            generation = head["generation"] if head else 0
            row = db.execute("SELECT * FROM memory_index_state WHERE owner_id=?", (oid,)).fetchone() if available else None
            watermark = dict(row) if row else {}
            compatible = (watermark.get("native_fingerprint") == owner["fingerprint"]
                          and watermark.get("projection_version") == index.PROJECTION_VERSION)
            lexical_ready = (compatible and watermark.get("fts_status") == "indexed"
                             and watermark.get("indexed_generation") == generation)
            vector_ready = (watermark.get("vector_status") == "disabled" or compatible
                            and watermark.get("vector_status") == "indexed"
                            and watermark.get("vector_generation") == generation
                            and watermark.get("encoder_version") == index.ENCODER_VERSION)
            output.append({"owner_id": oid, "head": head["commit_id"] if head else None,
                "target_generation": generation, "indexed_generation": watermark.get("indexed_generation"),
                "vector_generation": watermark.get("vector_generation"),
                "fts_status": "indexed" if lexical_ready else "failed" if watermark.get("fts_status") == "failed" else "pending",
                "vector_status": watermark.get("vector_status") if vector_ready else "failed" if watermark.get("vector_status") == "failed" else "pending",
                "coverage": "complete" if lexical_ready and vector_ready else "partial"})
        return output
    finally:
        if db is not None:
            db.close()


def status(coordinator, raw):
    """重新授权后读取持久维护状态；重启用新 query，不执行或修复下一步。

    plan_id 可以包含多个不可覆盖版本。返回全部经核验的版本与逐请求事实，
    不以文件时间猜一个“最新计划”，不因临时回执丢失重做规范提交。
    """
    state, locked = None, False
    try:
        raw = json_value(parse(json_value(raw), MaintenanceStatusRequest))
        if not isinstance(raw["query_id"], str) or not isinstance(raw["plan_id"], str) or not PLAN_ID.fullmatch(raw["plan_id"]):
            raise QueryError("VALIDATION", "维护状态需要有效查询与计划身份")
        state = coordinator.store.get(raw["query_id"])
        locked = state.lock.acquire(blocking=False)
        if not locked:
            raise QueryError("CONFLICT", "同一查询已有活动操作")
        with state.ledger.active():
            reader = coordinator.reader(state)
            folder = _path(coordinator.root, f"{BASE}/{raw['plan_id']}")
            paths = _status_files(reader, folder, re.compile(r"[0-9a-f]{64}\.json"))
            if not paths:
                raise QueryError("SOURCE_MISSING", "维护计划不存在")
            versions = {path.stem: _load(coordinator.root, raw["plan_id"], path.stem, reader) for path in paths}
            parents = {saved.get("parent_digest") for saved in versions.values()} - {None}
            if not parents <= versions.keys():
                raise QueryError("INTERNAL", "维护计划版本链缺失")
            for plan_digest in versions:
                seen, current = set(), plan_digest
                while current is not None:
                    reader.ledger.checkpoint()
                    if current in seen:
                        raise QueryError("INTERNAL", "维护计划版本链存在循环")
                    seen.add(current)
                    current = versions[current].get("parent_digest")
            # Every saved version still requires the same current source access.
            # Withholding the whole result on denial prevents exposing the title,
            # count or transaction identity of a newly inaccessible plan.
            originals, current_records, expected_heads, warnings = {}, {}, {}, []
            stale_basis = False
            for plan_digest, saved in versions.items():
                scope = parse(saved["request"]["scope"], Scope)
                reader.excluded_ids.update((*scope.exclude_ids, *scope.excluded_owner_ids, *(ref.id for ref in scope.excluded_refs)))
                original = {}
                for item in saved["plan"]["items"]:
                    ref = parse(item["ref"], FixedRef)
                    record = _status_read_fixed(state, reader, ref, scope)
                    original[ref.id] = record
                    current_records[ref.id] = reader.current_record(ref.id)
                originals[plan_digest] = original
                for fixed in saved["plan"]["basis"]["refs"]:
                    try:
                        _status_read_fixed(state, reader, parse(fixed, FixedRef), scope)
                    except QueryError as exc:
                        if exc.code != "STALE":
                            raise
                        stale_basis = True
                        warnings.append("固定依据内容已变化；状态读取不授权继续应用旧计划")
                for oid, expected in saved["plan"]["basis"]["owner_heads"]:
                    reader.owner(oid)
                    expected_heads.setdefault(oid, set()).add(expected)
            attempts, commits, completed_by_version, known_heads = [], {}, {}, {}
            for path in _status_files(reader, folder / "apply", re.compile(r"[0-9a-f-]{36}")):
                attempt, receipts = _status_attempt(reader, raw["plan_id"], path, versions, originals)
                attempts.append(attempt)
                completed_by_version.setdefault(attempt["plan_digest"], set()).update(attempt["completed_owner_ids"])
                for receipt in receipts:
                    oid = receipt["owner_id"]
                    commits[(oid, receipt["request_id"])] = receipt
                    known_heads.setdefault(oid, set()).add(receipt["commit_id"])
            pending_owners, pending_items, pending_reviews = set(), set(), {}
            for plan_digest in versions.keys() - parents:
                saved = versions[plan_digest]
                for item in saved["plan"]["items"]:
                    ref = parse(item["ref"], FixedRef)
                    oid = originals[plan_digest][ref.id]["owner_id"]
                    if item["action"] == "defer" or item["action"] in WRITE_ACTIONS and oid not in completed_by_version.get(plan_digest, set()):
                        pending_owners.add(oid)
                        pending_items.add(ref.id)
                    if not saved["reviewed"] or item["action"] == "defer":
                        pending_reviews[_key(ref)] = asdict(ref)
            if len(versions.keys() - parents) > 1:
                warnings.append("计划存在多个审查分支；状态不替用户选择应用版本")
            index_states = _status_indexes(reader, expected_heads)
            for entry in index_states:
                if entry["head"] not in expected_heads[entry["owner_id"]] | known_heads.get(entry["owner_id"], set()):
                    stale_basis = True
            if stale_basis:
                warnings.append("依据HEAD或来源已变化；已核实历史提交保留，续作须重新核对")
            if any(entry["coverage"] != "complete" for entry in index_states):
                warnings.append("派生索引尚未覆盖当前内容；状态查询未执行补偿")
            from .evidence import Evidence
            evidence, review_states = Evidence(reader), []
            for record in current_records.values():
                if not record["payload"].get("claims"):
                    continue
                try:
                    assessments = evidence.assess(record, state.request.applicability or None)
                    for assessment in assessments:
                        ref = FixedRef("claim", assessment["claim_id"], None, assessment["sha256"], None)
                        review_states.append({"ref": asdict(ref), "review_state": assessment["review_state"],
                            "validity": "valid" if assessment["effective_validity"] else "unknown" if assessment["review_state"] == "not-reviewed" else "invalid",
                            "reasons": [error["code"] for error in assessment["errors"]]})
                        if not assessment["effective_validity"]:
                            pending_reviews[_key(ref)] = asdict(ref)
                except QueryError as exc:
                    if exc.code not in {"STALE", "SOURCE_MISSING", "UNSUPPORTED"}:
                        raise
                    warnings.append("部分结论当前状态待核验；未沿用缓存复核")
                    for claim in record["payload"]["claims"]:
                        ref = FixedRef("claim", claim["claim_id"], None, memory_contracts.canonical_hash(claim), None)
                        review_states.append({"ref": asdict(ref), "review_state": "not-assessed", "validity": "unknown", "reasons": [exc.code]})
                        pending_reviews[_key(ref)] = asdict(ref)
            committed_values = [_status_commit(reader, commits[key]) for key in sorted(commits)]
            for entry in index_states:
                head, _manifest = reader.store.head_manifest(reader.owner(entry["owner_id"]))
                if (head["commit_id"] if head else None) != entry["head"]:
                    stale_basis = True
                    warnings.append("状态读取期间HEAD变化；输出只绑定已核实的固定提交")
            basis = reader.basis([(entry["owner_id"], str(entry["indexed_generation"])) for entry in index_states])
            value = {"plan_id": raw["plan_id"], "plan_versions": [{"plan_digest": key, "parent_digest": saved.get("parent_digest"),
                "reviewed": saved["reviewed"], "leaf": key not in parents, "item_count": len(saved["plan"]["items"])} for key, saved in sorted(versions.items())],
                "commits": committed_values, "pending_owner_ids": sorted(pending_owners),
                "pending_items": sorted(pending_items), "review_states": review_states,
                "pending_reviews": list(pending_reviews.values()), "index_states": index_states,
                "attempts": attempts, "resume_cursor": None, "basis_stale": stale_basis}
            # Whole-result reservation avoids disclosing an unpaid prefix and
            # preserves the query ledger if the status payload cannot fit.
            parse(value, MaintenanceStatusReceipt)
            state.ledger.charge("output_chars", len(json.dumps(value, ensure_ascii=False)))
        return _result(value, state=state, basis=basis, warnings=warnings)
    except (QueryError, MemoryError, OSError, ValueError, sqlite3.Error) as exc:
        return _error(exc, state)
    finally:
        if locked:
            state.lock.release()
