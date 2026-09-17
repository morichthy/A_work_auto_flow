"""受范围约束的逻辑材料树；不枚举工作区任意目录或读取全部正文。

父节点与分页条件绑定到服务端短期游标。物理视图仅显示注册对象的规范
位置，不能作为任意文件浏览器；每次翻页重新检查当前来源权限。
"""
from dataclasses import replace
from types import SimpleNamespace
import time
import uuid

from memory.errors import MemoryError
from .budget import DEFAULT_BUDGET, Ledger
from .contracts import TreeRequest
from .coordinator import envelope, failure, current_scope_allows, owner_allowed
from .legacy_adapter import fixed_record
from .reader import Reader
from .validation import QueryError, parse
from .wire import digest, json_value


def list_page(coordinator, raw):
    state = SimpleNamespace(ledger=Ledger(DEFAULT_BUDGET))
    try:
        request = parse(raw, TreeRequest)
        if not 1 <= request.limit <= 100:
            raise QueryError("VALIDATION", "树分页大小应为1–100")
        signature = digest(replace(request, cursor=None))
        cursors = getattr(coordinator, "tree_cursors", {})
        coordinator.tree_cursors = cursors
        offset = 0
        if request.cursor:
            saved = cursors.get(request.cursor)
            if saved is None or saved[0] != signature or saved[2] < time.monotonic():
                raise QueryError("EXPIRED", "结构游标到期或范围已改变")
            offset = saved[1]
        scope = request.scope
        scoped_request = SimpleNamespace(scope=scope, scope_ceiling=scope, applicability="")
        state.request = scoped_request
        reader = coordinator.reader(state)
        nodes = []
        with state.ledger.active():
            parent = request.parent_node_id
            selected_record = None
            if request.parent_ref:
                record = reader.record(request.parent_ref)
                selected_record = record
                parent = record["owner_id"] + "::" + (record.get("level") or "unlayered")
            if selected_record and request.view == "storage":
                from memory.evidence_adapter import iter_refs
                from .legacy_adapter import from_legacy
                if not current_scope_allows(reader, selected_record, scoped_request):
                    raise QueryError("DENIED", "父材料不在选定范围")
                seen = set()
                for raw_ref in iter_refs({"sources": selected_record["sources"], "payload": selected_record["payload"]}):
                    if raw_ref["target_kind"] != "file" or raw_ref["target_id"] in seen:
                        continue
                    ref = from_legacy(raw_ref)[0]
                    reader.file_bytes(ref)
                    path, metadata = reader.service._file(raw_ref)
                    seen.add(ref.id)
                    nodes.append(dict(ref=json_value(ref), node_id="source:" + ref.id, parent_id=selected_record["record_id"],
                                      title=metadata.get("title") or path.name, kind="source", layer="L0", has_children=False,
                                      storage_role="source_reference", registered_path=metadata["path"]))
                next_offset = offset + request.limit if offset + request.limit < len(nodes) else None
                nodes = nodes[offset:offset + request.limit]
            elif not parent:
                for oid in sorted(reader.views):
                    try:
                        owner = reader.owner(oid)
                    except QueryError:
                        continue
                    if not owner_allowed(owner, scoped_request):
                        continue
                    if request.owner_query.strip().casefold() not in (owner.get("title", "") + " " + oid).casefold():
                        continue
                    nodes.append(dict(ref=None, node_id=oid, parent_id=None, title=owner.get("title", oid), kind="owner",
                                      layer=None, has_children=True, storage_role="canonical", owner_type=owner["owner_type"],
                                      registered_path=owner["memory_home"] if request.view == "storage" else None))
            else:
                oid, separator, layer = parent.partition("::")
                owner = reader.owner(oid)
                if not owner_allowed(owner, scoped_request):
                    raise QueryError("DENIED", "父节点不在选定范围")
                if not separator and request.view == "storage":
                    for key, title, role, path, children in (
                        ("canonical", "规范材料与固定来源", "canonical", owner["memory_home"], True),
                        ("native", "归属原始登记", "source_reference", owner["native_ref"]["path"], False),
                        ("projection", "检索索引（共享派生文件）", "projection", "retrieval/generated/search.sqlite3", False),
                        ("temporary", "查询与维护临时状态", "temporary", ".local/material-query", False),
                    ):
                        nodes.append(dict(ref=None, node_id=oid + "::" + key, parent_id=oid, title=title, kind="storage",
                                          layer=None, has_children=children, storage_role=role, registered_path=path))
                elif not separator:
                    for level in ("L0", "L1", "L2", "L3", "L4", "unlayered"):
                        if scope.levels is None or level in scope.levels:
                            nodes.append(dict(ref=None, node_id=oid + "::" + level, parent_id=oid,
                                              title=level if level != "unlayered" else "章节与文稿", kind="layer", layer=level,
                                              has_children=True, storage_role="canonical", registered_path=None))
                else:
                    if layer not in {"L0", "L1", "L2", "L3", "L4", "unlayered"} and not (request.view == "storage" and layer == "canonical"):
                        raise QueryError("VALIDATION", "未知逻辑层级")
                    head, manifest = reader.store.head_manifest(owner)
                    reader.heads[oid] = head["commit_id"] if head else None
                    # Manifest IDs are small control metadata. Read bodies only
                    # until one page is filled; offsets count inspected IDs so
                    # filtered entries do not cause duplicates on continuation.
                    ids = sorted(manifest["record_heads"]) if manifest else []
                    position = offset
                    while position < len(ids) and len(nodes) < request.limit:
                        rid = ids[position]
                        position += 1
                        try:
                            record = reader.current_record(rid)
                        except QueryError as exc:
                            if exc.code == "DENIED":
                                continue
                            raise
                        if (layer != "canonical" and (record.get("level") or "unlayered") != layer) or not current_scope_allows(reader, record, scoped_request):
                            continue
                        nodes.append(dict(ref=json_value(fixed_record(record)), node_id=rid, parent_id=parent,
                                          title=record["title"], kind=record["kind"], layer=record.get("level"),
                                          has_children=request.view == "storage" and bool(record["sources"]), storage_role="canonical",
                                          registered_path=owner["memory_home"] + "/" + manifest["record_heads"][rid]["path"] if request.view == "storage" else None))
                    next_offset = position if position < len(ids) else None
            if not selected_record and (not parent or "::" not in parent):
                next_offset = offset + request.limit if offset + request.limit < len(nodes) else None
                nodes = nodes[offset:offset + request.limit]
            cursor = None
            if next_offset is not None:
                for key in list(cursors):
                    if cursors[key][2] < time.monotonic():
                        del cursors[key]
                if len(cursors) >= 1024:
                    cursors.pop(next(iter(cursors)))
                cursor = str(uuid.uuid4())
                cursors[cursor] = (signature, next_offset, time.monotonic() + 900)
            state.ledger.charge("output_chars", sum(len(n["title"]) for n in nodes))
            basis = reader.basis()
        return envelope({"nodes": nodes, "next_cursor": cursor}, state=state, basis=basis)
    except (QueryError, MemoryError) as exc:
        return failure(exc, state)
