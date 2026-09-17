"""CLI 与 HTTP 共用的固定动作路由；JSON 不能选择任意函数或 shell。"""
from .errors import MemoryError

HTTP_STATUS = {"INVALID_ARGUMENT": 400, "INVALID_SCHEMA": 422, "NOT_FOUND": 404,
    "UNRESOLVED_REFERENCE": 422, "ACCESS_DENIED": 403, "UNSAFE_PATH": 403,
    "VERSION_CONFLICT": 409, "STALE_BASIS": 409, "IDEMPOTENCY_CONFLICT": 409,
    "LOCKED": 423, "INTEGRITY_ERROR": 422, "STORAGE_ERROR": 500,
    "INDEX_PENDING": 202, "EVIDENCE_INELIGIBLE": 422, "INVALID_TRANSITION": 422,
    "CAPABILITY_UNAVAILABLE": 503}

ACTIONS = ("inspect", "list-owners", "adopt-owner", "validate-draft", "commit", "review", "search",
           "history", "document", "outline", "section-context", "document-impact", "figure", "resume", "context", "expand", "prepare", "consolidate", "summaries-prepare",
           "summaries-save", "associations-propose", "associations-decide", "associations-view",
           "feedback", "recover", "reconcile", "rebuild", "export", "migration-export", "migration-preview",
           "rebuild-discovery", "discovery-gaps",
           "migration-import", "migration-recover", "ingest-preview", "ingest-apply",
           "impact", "question-validity", "source-lineage", "raw-materials", "raw-material")
PREVIEW_ACTIONS = {"validate-draft", "commit", "review", "consolidate", "summaries-save",
                   "associations-decide", "feedback", "rebuild", "rebuild-discovery",
                   "migration-import", "migration-recover", "ingest-apply"}


def dispatch(service, action, request):
    if action not in ACTIONS or not isinstance(request, dict):
        raise MemoryError("INVALID_ARGUMENT", "未知记忆动作或请求不是 JSON 对象")
    if request.get("dry_run") and action not in PREVIEW_ACTIONS:
        raise MemoryError("INVALID_ARGUMENT", "此动作没有 dry_run 模式，请使用对应预览入口")
    try:
        if action == "inspect":
            return service.inspect(request["owner_id"], request.get("revision"), record_id=request.get("record_id"))
        if action in {"raw-materials", "raw-material"}:
            from . import raw_materials
            return (raw_materials.listing if action == 'raw-materials' else raw_materials.read)(service, request)
        if action == "list-owners":
            from . import owners
            return {"owners": owners.public_list_owners(service.root)}
        if action == "impact":
            from .impact import reverse_dependencies
            changed = request["changed_ids"]
            if not isinstance(changed, list) or not changed or any(not isinstance(tid, str) or not tid for tid in changed):
                raise MemoryError("INVALID_ARGUMENT", "changed_ids 必须是非空规范身份数组")
            return reverse_dependencies(service.root, changed, service=service)
        if action == "question-validity":
            from .impact import question_resolution_validity
            return question_resolution_validity(service.root, request["question_ref"], scope=request.get("scope"), service=service)
        if action == "source-lineage":
            from .lineage import project
            return project(service, request["target_ids"])
        if action == "adopt-owner":
            from . import owners
            return owners.adopt_owner(service.root, request["native_ref"], request["expected_hash"], actor=request["actor"])
        if action in {"validate-draft", "commit", "review"}:
            return {"validate-draft": service.validate_draft, "commit": service.commit, "review": service.review}[action](request)
        if action == "search":
            from .search import search
            return search(service.root, request)
        if action in {'document', 'outline', 'section-context', 'document-impact'}:
            from . import documents
            return {'document': documents.build_document, 'outline': documents.outline,
                    'section-context': documents.section_context, 'document-impact': documents.document_impact}[action](service, request)
        if action == 'figure':
            from . import document
            return document.figure(service, request['owner_id'], request['record_id'],
                                   request['revision'], request['figure_index'])
        if action in {"history", "resume"}:
            from . import history
            if action == "history":
                return history.build_history(service, request["owner_id"], offset=request.get("offset", 0),
                    limit=request.get("limit", 50), basis_heads=request.get("basis_heads"))
            return history.resume(service, request["owner_id"], budget=request.get("budget"), selection=request.get("selection"))
        if action in {"context", "expand"}:
            from . import packets
            if action == "context":
                return packets.build_context(service, request)
            return packets.expand(service, request["refs"], selection=request.get("selection"), budget=request.get("budget"))
        if action in {"prepare", "consolidate"}:
            from . import consolidation
            return (consolidation.prepare(service, request["owner_id"], request.get("since_commit"), request.get("trigger", "manual"))
                    if action == "prepare" else consolidation.apply(service, request))
        if action in {"summaries-prepare", "summaries-save"}:
            from . import summaries
            return (summaries.prepare(service, request["query"], request["owners"], budget=request.get("budget"), selection=request.get("selection"))
                    if action == "summaries-prepare" else summaries.save(service, request))
        if action.startswith("associations-"):
            from . import associations
            if action == "associations-view":
                value = service.inspect(request["owner_id"], request.get("revision"), record_id=request["record_id"])
                return associations.view(service, value["record"])
            return associations.propose(service, request) if action == "associations-propose" else associations.decide(service, request)
        if action == "feedback":
            from .feedback import save
            return save(service, request)
        if action == "recover":
            from .recovery import recover
            return recover(service.root, request["owner_id"], apply=request.get("apply", False))
        if action in {"reconcile", "rebuild"}:
            from . import index
            return (index.reconcile(service.root, request.get("owner_id"), vector=request.get("vector", "auto"))
                    if action == "reconcile" else index.rebuild(service.root, request.get("scope"), request.get("dry_run", False), vector=request.get("vector", "auto")))
        if action in {"rebuild-discovery", "discovery-gaps"}:
            from . import discovery
            if action == "discovery-gaps":
                return discovery.gaps(service.root, request.get("owner_id"),
                                      offset=request.get("offset", 0), limit=request.get("limit", 50))
            return discovery.rebuild_owner(service.root, request["owner_id"], request["expected_head"],
                projection_version=request["projection_version"], vector=request.get("vector", "auto"),
                dry_run=request.get("dry_run", False))
        if action == "export":
            from .render import export
            return export(service, request)
        if action.startswith("migration-") or action.startswith("ingest-"):
            from . import migration
            if action == "migration-export":
                return migration.export_owner(service.root, request["owner_id"], request["output"], service=service)
            if action == "migration-preview":
                return migration.preview_import(service.root, request["package"], request.get("path_mapping"))
            if action == "migration-import":
                return migration.import_package(service.root, request["plan"], dry_run=request.get("dry_run", False))
            if action == "migration-recover":
                return migration.recover_import(service.root, request["receipt_path"], dry_run=request.get("dry_run", True))
            if action == "ingest-preview":
                return migration.preview(service.root, request["request"], request["source_ref"], service=service)
            if action == "ingest-apply":
                if request.get("dry_run"):
                    return {"dry_run": True, "plan": request["plan"], "writes": 0}
                return migration.apply(service.root, request["plan"], service=service)
    except (KeyError, TypeError, ValueError) as exc:
        raise MemoryError("INVALID_ARGUMENT", "记忆请求参数无效: " + str(exc)) from exc


def response_status(value):
    code = (value.get("error") or {}).get("code")
    if code:
        return HTTP_STATUS.get(code, 500)
    return 201 if value.get("save_status") == "committed" else 200
