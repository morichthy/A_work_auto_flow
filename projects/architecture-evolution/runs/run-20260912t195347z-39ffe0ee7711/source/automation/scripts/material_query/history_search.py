"""显式历史查询的有界适配，不创建第二套持久版本或隐式重建索引。

当前 FTS 只索引最新版。允许旧版时，沿获准 Owner 的不可变 manifest 链
读取有限历史修订，使用与当前投影相同的检索文本。读取/筛掉的历史版本
也消耗预算；没有扫描完会明确报告覆盖缺口，不能冒充全历史检索完成。
"""
from memory import index
from memory.errors import MemoryError
from .content import SOURCE_KINDS
from .contracts import FixedRef
from .legacy_adapter import memory_error
from .validation import QueryError


def append_history(state, reader, manifests):
    if state.request.freshness != "allow_stale":
        return
    job, request = state.recall, state.request
    from .coordinator import record_allowed
    # 给已冻结的当前候选保留评价名额；历史逐项试读不挤掉当前页。
    reserve = min(len(job["groups"]), state.ledger.remaining("candidates"))
    window = max(0, state.ledger.remaining("candidates") - reserve)
    inspected, seen, groups = 0, set(), []
    allowed_kinds = SOURCE_KINDS.get(request.content_source, ())
    targets = {r.id for scope in (request.scope, request.scope_ceiling) for r in scope.include_refs}
    text = job["text"]
    terms = job.get("terms", ())
    exhausted = True
    try:
        for oid, (_head, latest) in manifests.items():
            if not latest:
                continue
            owner = reader.owner(oid)
            current_entries = latest["record_heads"]
            manifest = latest
            commits = set()
            while manifest.get("parent_commit_id"):
                state.ledger.checkpoint()
                parent = manifest["parent_commit_id"]
                if parent in commits:
                    raise QueryError("INTERNAL", "历史清单存在循环")
                commits.add(parent)
                manifest = reader.store._manifest(owner, parent, manifest["parent_manifest_hash"])
                for rid, entry in sorted(manifest["record_heads"].items()):
                    key = (oid, rid, entry["revision"])
                    if key in seen or entry == current_entries.get(rid):
                        continue
                    seen.add(key)
                    if targets and rid not in targets:
                        continue
                    if inspected >= window:
                        exhausted = False
                        return
                    state.ledger.charge("candidates", 1)
                    inspected += 1
                    ref = FixedRef("record", rid, entry["revision"], entry["record_hash"], None)
                    try:
                        record = reader.record(ref)
                        if allowed_kinds and record["kind"] not in allowed_kinds:
                            continue
                        if not all(record_allowed(record, scope) for scope in (request.scope, request.scope_ceiling)):
                            continue
                        projected = index._row(record, owner)
                        entries = [index._entry(projected)]
                        from memory.technical_units import is_unit
                        if is_unit(record):
                            entries.extend(index.block_entry(projected, block) for block in record['payload']['blocks'])
                        # Reuse authored block projections, but never insert old
                        # text into the current index or claim historical BM25.
                        matching = [entry for entry in entries if any(term.casefold() in (
                            entry['title'] + '\n' + entry['text']).casefold() for term in terms)]
                        exact = "identity" in request.channels and (rid == text or rid in targets)
                        lexical = "lexical" in request.channels and bool(matching)
                        if not exact and not lexical:
                            continue
                        channel = "identity" if exact else "lexical"
                        # 分数只在历史扫描结果之间使用，不能假冒 FTS 的 bm25。
                        row = {"canonical_id": rid, "record_id": rid, "owner_id": oid,
                               "entity_kind": "record", "revision": record["revision"],
                               "content_hash": record["record_hash"], "_history": True}
                        hit = {"rank_channels": {channel: len(groups) + 1},
                               "score": float(len(matching)) if lexical else 1.0,
                               "channel_rows": {channel: [{**row, **entry, '_entry_rank': rank}
                                   for rank, entry in enumerate(matching[:4] if lexical and not exact else [{}], 1)]}}
                        groups.append({"record_id": rid, "ref": ref, "charged": True,
                                       "matches": [(hit, row)]})
                    except (QueryError, MemoryError) as exc:
                        error = memory_error(exc) if isinstance(exc, MemoryError) else exc
                        if error.code in {"BUDGET", "CANCELLED"}:
                            raise error
                        job["gaps"].append("部分历史修订未通过当前权限、来源或指纹核验，未返回")
    finally:
        # 已获得的历史命中保留，即使后续预算不足；不会清空先前当前候选。
        job["groups"].extend(groups)
        if not exhausted:
            job["gaps"].append("历史版本扫描达到候选窗口上限，尚未覆盖全部旧修订")
