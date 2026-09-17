"""本地材料应用入口；单次搜索可显式组装当前页，不把进程内游标持久化。"""
import json
from pathlib import Path

from .api import dispatch
from .coordinator import Coordinator, failure
from .validation import QueryError, object_fields


def add_commands(parsers):
    parser = parsers.add_parser("material-query", help="材料查询、组包与语义维护；请求采用运行JSON契约")
    parser.add_argument("action", choices=("capabilities", "definitions", "foundation-capabilities", "foundation", "search", "structure", "maintenance-plan", "maintenance-review", "maintenance-apply", "maintenance-status",
        "reading-template", "reading-start", "reading-recall", "reading-page", "reading-read", "reading-note", "reading-decide", "reading-resume",
        "reading-list", "reading-view", "reading-bind", "reading-archive", "reading-delegate", "reading-handoff",
        "reading-configure", "reading-assess", "reading-assess-owners", "reading-synthesize",
        "reading-recall-fulltext"))
    parser.add_argument("--owner", help="reading-list按归属对象筛选；不改变读取授权")
    parser.add_argument("--session", help="reading-view/handoff读取该RS，无需手填请求JSON")
    parser.add_argument("--markdown", action="store_true", help="reading-view/handoff输出Markdown；handoff仍受交接上限约束")
    parser.add_argument("--request", type=Path, help="UTF-8 JSON请求文件，最多500KB")
    parser.add_argument("--assemble", action="store_true", help="search后显式组装当前页全部候选；不会继续翻页")
    parser.add_argument("--expand", choices=("process", "technical"), help="search后沿当前页候选的固定关联展开正文；沿用同一预算")
    parser.add_argument("--documents", choices=("research_process", "research_report"), help="search后返回命中所属对象的已有文稿，按固定文稿去重")


def execute(root, args):
    coordinator = Coordinator(root)
    try:
        owner, session = getattr(args, 'owner', None), getattr(args, 'session', None)
        if owner and args.action != 'reading-list' or session and args.action not in {'reading-view', 'reading-handoff'}:
            raise QueryError('VALIDATION', '--owner只用于reading-list，--session只用于reading-view/handoff')
        if getattr(args, 'markdown', False) and args.action not in {'reading-view', 'reading-handoff'}:
            raise QueryError('VALIDATION', '--markdown只用于reading-view/handoff')
        if args.request and (owner or session):
            raise QueryError('VALIDATION', '请求文件与简便参数不能混用')
        if args.assemble and args.action != "search":
            raise QueryError("VALIDATION", "--assemble仅用于search")
        expand_target = getattr(args, "expand", None)
        documents = getattr(args, "documents", None)
        if expand_target and args.action != "search":
            raise QueryError("VALIDATION", "--expand仅用于search")
        if documents and (args.action != "search" or expand_target or args.assemble):
            raise QueryError("VALIDATION", "--documents用于search，不能与--expand/--assemble同时使用")
        if args.request:
            if args.request.stat().st_size > 500000:
                raise QueryError("VALIDATION", "请求文件超过500KB")
            raw = json.loads(args.request.read_text(encoding="utf-8-sig"))
        elif args.action == 'reading-list':
            raw = {'owner_id': owner} if owner else {}
        elif args.action in {'reading-view', 'reading-handoff'} and session:
            raw = {'session_id': session}
        elif args.action in {"capabilities", "definitions", "foundation-capabilities", "reading-template"}:
            raw = {}
        else:
            raise QueryError("VALIDATION", "此动作需要--request文件")
        if args.action == "maintenance-status":
            # A read-only status call can establish a fresh authorized context
            # after process restart; it never resumes or reapplies the write.
            object_fields(raw, {"query", "plan_id"})
            search = coordinator.search(raw["query"])
            if not search.get("value"):
                return search, 2
            result = dispatch(coordinator, "maintenance-status", {"plan_id": raw["plan_id"], "query_id": search["value"]["query_id"]})
        elif args.action == "foundation":
            # One explicit query supplies the immutable scope and shared ledger.
            # Multi-step plans/commits need the persistent HTTP session; a later
            # CLI process cannot manufacture a new lifetime for an old query ID.
            object_fields(raw, {"query", "action", "request"})
            if not isinstance(raw["action"], str) or not isinstance(raw["request"], dict) or "query_id" in raw["request"]:
                raise QueryError("VALIDATION", "foundation需要动作及无query_id的请求对象")
            search = coordinator.search(raw["query"])
            if not search.get("value"):
                return search, 2
            result = dispatch(coordinator, "foundation/" + raw["action"],
                              {**raw["request"], "query_id": search["value"]["query_id"]})
        else:
            result = dispatch(coordinator, "foundation/capabilities" if args.action == "foundation-capabilities" else args.action, raw)
        original = result
        if documents and result.get("value") and result["value"].get("candidates"):
            receipt = result["value"]
            packet = dispatch(coordinator, "documents", {"query_id": receipt["query_id"], "expected_request_digest": receipt["request_digest"],
                "candidate_ids": [c["candidate_id"] for c in receipt["candidates"]], "document_type": documents})
            return {"search": original, "documents": packet}, 0 if original["status"] == packet["status"] == "ok" else 2
        expansion = None
        if expand_target and result.get("value") and result["value"].get("candidates"):
            receipt = result["value"]
            expansion = dispatch(coordinator, "expand", {"query_id": receipt["query_id"], "target": expand_target,
                "expected_request_digest": receipt["request_digest"], "candidate_ids": [c["candidate_id"] for c in receipt["candidates"]]})
            if not expansion.get("value"):
                # Failed expansion must not fall through and assemble the
                # original page as though the requested technical body existed.
                return {"search": original, "expansion": expansion}, 2
            if expansion.get("value"):
                # Keep the query identity while assembly selects exactly the
                # expanded candidates; a second CLI process cannot reuse it.
                result = {**expansion, "value": {**receipt, "candidates": expansion["value"]["candidates"]}}
        if args.assemble and result.get("value") and result["value"].get("candidates"):
            receipt = result["value"]
            packet = coordinator.assemble({"query_id": receipt["query_id"], "expected_request_digest": receipt["request_digest"],
                                           "candidate_ids": [c["candidate_id"] for c in receipt["candidates"]]})
            complete = packet["status"] == "ok" and original["status"] == "ok" and (
                expansion is None or expansion["status"] == "ok")
            return {"search": original, **({"expansion": expansion} if expansion else {}), "assembly": packet}, 0 if complete else 2
        if expansion is not None:
            return {"search": original, "expansion": expansion}, 0 if expansion["status"] == "ok" else 2
        return result, 0 if result.get("status", "ok") == "ok" else 2
    except (OSError, ValueError, QueryError) as exc:
        return failure(exc if isinstance(exc, QueryError) else QueryError("VALIDATION", "请求文件不可读或JSON格式错误")), 2
    finally:
        # The CLI process owns these identities. HTTP is the interactive entry
        # for poll/resume/deepen; a later CLI invocation cannot reset this ledger.
        coordinator.close()
