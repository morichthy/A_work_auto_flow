"""HTTP/CLI共用窄入口：未知字段拒绝，不接受客户端授权Context。"""
from memory.errors import MemoryError
from . import definitions
from .coordinator import envelope, failure
from .validation import QueryError


def response_status(result):
    if "status" not in result and result.get("api_version") == "0.2":
        return 200
    if result.get("code") == "RUNNING":
        return 202
    if result.get("status") in {"ok", "partial", "cancelled"}:
        return 200
    return {"VALIDATION": 400, "DENIED": 403, "EXPIRED": 410, "CONFLICT": 409,
            "STALE": 409, "UNSUPPORTED": 422, "SOURCE_MISSING": 404, "BUDGET": 429}.get(result.get("code"), 500)


def dispatch(coordinator, action, raw):
    try:
        if not isinstance(raw, dict):
            raise QueryError("VALIDATION", "请求必须是JSON对象")
        if action == "capabilities" and not raw:
            return coordinator.capabilities()
        if action == "definitions" and not raw:
            return envelope(definitions.listing())
        if action.startswith("reading-"):
            from .reading import dispatch as reading_dispatch
            return reading_dispatch(coordinator, action.removeprefix("reading-"), raw)
        if action.startswith("foundation/"):
            from .foundation import Foundation
            return Foundation(coordinator).dispatch(action.removeprefix("foundation/"), raw)
        if action in {"start", "search", "assemble"}:
            return getattr(coordinator, action)(raw)
        fields = {"poll": {"query_id"}, "cancel": {"query_id"}, "resume": {"query_id", "cursor"}}
        if action in fields:
            if set(raw) != fields[action] or any(not isinstance(v, str) or not v for v in raw.values()):
                raise QueryError("VALIDATION", "查询身份或游标字段无效")
            return getattr(coordinator, action)(**raw)
        if action == "structure":
            from .structure import list_page
            return list_page(coordinator, raw)
        if action == "inspect":
            from .representations import inspect
            return inspect(coordinator, raw)
        if action == "deepen":
            from .deepening import deepen
            return deepen(coordinator, raw)
        if action == "expand":
            from .content import expand
            return expand(coordinator, raw)
        if action == "documents":
            from .documents import full_documents
            return full_documents(coordinator, raw)
        if action in {"associations", "association-decision"}:
            from .associations import discover, decide
            return (discover if action == "associations" else decide)(coordinator, raw)
        if action in {"maintenance-plan", "maintenance-review", "maintenance-apply", "maintenance-status"}:
            from . import maintenance
            return getattr(maintenance, action.removeprefix("maintenance-"))(coordinator, raw)
        raise QueryError("VALIDATION", "未知材料查询动作或字段")
    except (QueryError, MemoryError) as exc:
        return failure(exc)
