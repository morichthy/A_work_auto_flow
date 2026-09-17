"""证据只读观察与差异记录；不执行实验、索引、合并或可信状态晋升。

复用获准来源清单与证据图。唯一写入是独立的本机监测日志，使用一份
原子状态文件保存基线、事件及维护候选，避免中断后事件和基线不一致。
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import unicodedata

import evidence as e
import retrieval as r

STATE = "context/monitor/state.json"
SCHEMA = 1


def now():
    return datetime.now(timezone.utc).isoformat()


def relative(root, path):
    path = Path(path).resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def stable_file(path, limit):
    """流式哈希前后检查单文件变化；不把无法读取或超限冒充已删除。"""
    try:
        before = path.stat()
    except FileNotFoundError:
        return {"status": "missing", "sha256": None, "bytes": None}
    if not path.is_file() or before.st_size > limit:
        raise ValueError(f"监测文件不是普通文件或超过 max_file_bytes：{path}")
    digest = e.sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"扫描期间文件变化，保留旧基线并稍后重试：{path}")
    return {"status": "present", "sha256": digest, "bytes": after.st_size}


def downstream(graph, nid):
    """按已登记支持关系反向遍历；最短路径说明影响如何到达下游。"""
    reverse = {key: set() for key in graph.nodes}
    for target, deps in graph.edges.items():
        for dep in deps:
            reverse[dep].add(target)
    paths, queue = {nid: [nid]}, [nid]
    for current in queue:
        for child in sorted(reverse[current]):
            if child not in paths:
                paths[child] = paths[current] + [child]
                queue.append(child)
    paths.pop(nid)
    return paths


def collect(root):
    """生成当前只读快照；不调用索引器，不装载模型或 OCR。

快照不是多文件事务；单文件并发写入会报错，下次轮询再观察。
只保存正文中的明确结论和元数据，不复制大文件内容或工具日志。
"""
    root = Path(root).resolve()
    cfg = r.config(root)
    from memory.owners import ROOT_TYPES, list_owners
    # 监测面是 Owner 记录，不是整个检索来源集，更不是 Run 的所有产物。
    # 发布包和外部原件即使被 Run 引用，也不能因此加入每分钟的哈希扫描。
    def in_scope(path):
        path = Path(path).resolve()
        if not path.is_relative_to(root):
            return False
        parts = path.relative_to(root).parts
        return bool(parts and parts[0] in ROOT_TYPES and not set(parts) & r.SKIP
                    and path.suffix.lower() in r.SUPPORTED)

    checked = {}
    def observed_hash(path):
        """证据图及 Run 校验也共享监测预算，避免它们再次读取大产物。"""
        path = Path(path).resolve()
        if not in_scope(path):
            raise ValueError(f"不在记录监测范围，未核验当前指纹：{relative(root, path)}")
        if path not in checked:
            checked[path] = stable_file(path, cfg["max_file_bytes"])
        if checked[path]["status"] != "present":
            raise ValueError(f"证据文件不存在：{relative(root, path)}")
        return checked[path]["sha256"]

    graph = e.EvidenceGraph(root, file_hasher=observed_hash)

    scan_cfg = {**cfg, "include_directories": [name for name in cfg["include_directories"]
                if (root / name).resolve().is_relative_to(root)
                and Path(name).parts and Path(name).parts[0] in ROOT_TYPES]}
    paths = {Path(item["path"]).resolve() for item in r.discover(root, scan_cfg)
             if in_scope(item["path"])}
    # 公共 Owner 发现覆盖项目/工具卡、单文件对象及各类记忆存储布局。
    # 只观察 HEAD 指针即可发现新提交；不遍历不可变修订和事务日志。
    for owner in list_owners(root, metadata_only=True):
        if owner["native_data"].get("sensitivity") == "restricted":
            continue
        native = e.reference_path(root, owner["native_ref"]["path"])
        paths.add(native)
        if owner["persisted"]:
            paths.add(e.reference_path(root, owner["memory_home"] + "/HEAD.json"))
    # 原有记录目录中的明确引用仍检查授权；不沿引用扩大到分发/缓存目录。
    for node in graph.nodes.values():
        paths.add(node["path"])
        refs = list(graph.refs(node))
        if node["kind"] == "owner":
            for group in ("inputs", "artifacts"):
                items = node["raw"].get(group, [])
                if isinstance(items, list):
                    refs += [{"target": item["path"]} for item in items if isinstance(item, dict) and isinstance(item.get("path"), str)]
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("target"), str) or ref["target"] in graph.nodes:
                continue
            try:
                target = e.reference_path(root, ref["target"])
                if in_scope(target):
                    paths.add(target)
            except (OSError, ValueError):
                pass  # 图/引用明细会报告授权或缺失问题，不尝试越界哈希。
    if len(paths) > cfg["max_files"]:
        raise ValueError("监测来源超过 max_files；未保存部分基线")
    files, file_errors = {}, []
    for path in sorted(paths):
        try:
            files[relative(root, path)] = checked[path] if path in checked else stable_file(path, cfg["max_file_bytes"])
        except (OSError, ValueError) as exc:
            # 页面可以展示其他有效记录及明确诊断；monitor 仍会拒绝提交
            # 含错误的快照，避免把暂时不可读的文件误报为删除/移出范围。
            file_errors.append(str(exc))
    nodes = {}
    for nid, node in sorted(graph.nodes.items()):
        raw = node["raw"]
        owner = graph.nodes.get(node["owner"], node)
        kind = ("claim" if node["kind"] == "claim" else "run" if "run_id" in raw else
                "research" if "research_id" in raw else "algorithm" if "module_id" in raw else
                "report" if str(raw.get("document_path", "")).startswith("reports/") else "knowledge")
        errors = graph.claim_errors(nid, raw.get("scope")) if kind == "claim" else list(node["blockers"]) + node["issues"]
        risks = sorted(set(node["blockers"]) | (set(errors) if raw.get("review", {}).get("status") == "accepted" else set()))
        refs = []
        for ref in graph.refs(node):
            if not isinstance(ref, dict):
                continue
            item = dict(ref)
            try:
                _, digest = graph._target(ref.get("target", ""))
                item.update(current_sha256=digest, version_matches=digest == ref.get("sha256"))
            except (OSError, ValueError, TypeError) as exc:
                item.update(current_sha256=None, version_matches=False, error=str(exc))
            refs.append(item)
        reason = raw.get("record_reason")
        reason_source = "record_reason" if reason else None
        if not reason:
            reason = raw.get("question") or owner["raw"].get("question")
            reason_source = "所属记录的问题（不是单独登记的保存理由）" if reason else None
        reports = []
        assets = []
        for group in ("inputs", "artifacts"):
            entries = raw.get(group, [])
            if isinstance(entries, list):
                for index, entry in enumerate(entries):
                    if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                        try:
                            asset_path = e.reference_path(root, entry["path"])
                            current = files.get(relative(root, asset_path), {})
                            assets.append({"group": group, "index": index, "path": entry["path"], "sha256": entry.get("sha256"),
                                "current_sha256": current.get("sha256"), "version_matches": bool(entry.get("sha256")) and current.get("sha256") == entry.get("sha256")})
                            if not in_scope(asset_path):
                                assets[-1]["error"] = "不在记录监测范围，未核验当前指纹"
                        except (OSError, ValueError) as exc:
                            assets.append({"group": group, "index": index, "path": entry["path"], "error": str(exc)})
        affected = downstream(graph, nid)
        for other, chain in affected.items():
            other_node = graph.nodes[other]
            # 报告中的某条 claim 依赖上游时，也必须定位回报告容器。
            # 这里仅显示包含关系，不向正式证据图添加容器自证环。
            report_node = graph.nodes.get(other_node["owner"], other_node)
            doc = report_node["raw"].get("document_path", "")
            if str(doc).startswith("reports/") and not any(v["id"] == report_node["id"] for v in reports):
                reports.append({"id": report_node["id"], "path": doc, "chain": chain})
        nodes[nid] = {"id": nid, "kind": kind, "owner": node["owner"], "path": relative(root, node["path"]),
            "document_path": raw.get("document_path"), "title": raw.get("title") or raw.get("statement") or nid,
            "statement": raw.get("statement") or raw.get("conclusion") or "", "scope": raw.get("scope"),
            "record_reason": reason or "未记录保存理由", "reason_source": reason_source,
            "fingerprint": node["fingerprint"], "execution_status": raw.get("status"),
            "review": raw.get("review", {}), "review_history": raw.get("review_history", []),
            "created_at": raw.get("created_at"), "refs": refs, "assets": assets, "dependencies": sorted(graph.edges[nid]),
            "reports": reports, "affected_ids": sorted(affected), "risks": risks,
            "formal_errors": errors if kind == "claim" else ["容器不替代逐条结论复核"],
            "formal_eligible": not errors if kind == "claim" else False,
            "state": "invalid" if risks else "eligible" if kind == "claim" and not errors else "needs-review"}
    return {"schema_version": SCHEMA, "observed_at": now(), "files": files, "nodes": nodes, "errors": graph.errors + file_errors,
            "note": "只读观察；引用次数和重复内容不作为独立验证；发现时间不等于实际发生时间"}


def load_state(root):
    path = state_path(root)
    if not path.exists():
        return None
    value = e.read(path)
    if (not isinstance(value, dict) or value.get("schema_version") != SCHEMA
            or not isinstance(value.get("snapshot"), dict) or not isinstance(value.get("events"), list)
            or not isinstance(value.get("candidates"), dict) or not isinstance(value.get("invalid_since"), dict)
            or not isinstance(value["snapshot"].get("files"), dict) or not isinstance(value["snapshot"].get("nodes"), dict)
            or not isinstance(value.get("sequence"), int)):
        raise ValueError("监测状态格式不兼容或损坏；保留原文件，不能自动重置历史")
    return value


def state_path(root):
    """固定日志位置不能经链接重定向到同工作区的业务文件。"""
    expected = Path(root).resolve() / STATE
    path = e.inside(Path(root).resolve(), expected)
    if path != expected:
        raise ValueError("监测状态路径被重定向，拒绝覆盖其他文件")
    return path


def diff(previous, current):
    """只比较观测差异。首轮建立基线，不把已有 succeeded 报成刚完成。"""
    if previous is None:
        return []
    changes = []
    for key in sorted(set(previous["files"]) | set(current["files"])):
        old, new = previous["files"].get(key), current["files"].get(key)
        if old != new:
            kind = "material-added" if old is None else "material-out-of-scope" if new is None else "material-changed"
            changes.append({"kind": kind, "target": key, "before": old, "after": new})
    for nid in sorted(set(previous["nodes"]) | set(current["nodes"])):
        old, new = previous["nodes"].get(nid), current["nodes"].get(nid)
        if old is None or new is None:
            changes.append({"kind": "record-added" if old is None else "record-removed", "target": nid})
            continue
        if old["execution_status"] != new["execution_status"]:
            changes.append({"kind": "experiment-finished" if new["kind"] == "run" and new["execution_status"] in {"succeeded", "failed", "cancelled"} else "execution-changed",
                            "target": nid, "before": old["execution_status"], "after": new["execution_status"]})
        if old["risks"] != new["risks"]:
            changes.append({"kind": "dependency-risk" if new["risks"] else "risk-cleared-observed", "target": nid,
                            "before": old["risks"], "after": new["risks"]})
        if old["review"] != new["review"]:
            changes.append({"kind": "review-changed", "target": nid, "before": old["review"], "after": new["review"]})
    return changes


def suggestions(snapshot):
    """候选仅表达待检查事项；相同文本/指纹绝不变成 accepted 或置信分数。"""
    result, groups = {}, {}
    def add(kind, targets, why, version):
        key = "CAND-" + e.fingerprint([kind, targets, version])[:20]
        result[key] = {"id": key, "kind": kind, "targets": targets, "reason": why, "version": version}
    for nid, node in snapshot["nodes"].items():
        if node["risks"]:
            add("review-dependency", [nid], "检查失效依据及下游引用；不得自动更新复核状态", [node["fingerprint"], node["risks"]])
        if node["kind"] == "claim":
            key = (node["scope"], " ".join(unicodedata.normalize("NFKC", node["statement"]).split()))
            groups.setdefault(key, []).append(nid)
    for targets in groups.values():
        if len(targets) > 1:
            add("compare-claims", sorted(targets), "相同范围内表述相同：人工比较来源及适用条件；重复不构成独立验证",
                [snapshot["nodes"][nid]["fingerprint"] for nid in sorted(targets)])
    groups = {}
    for path, item in snapshot["files"].items():
        if item["status"] == "present" and item["bytes"] and Path(path).suffix.lower() in {".md", ".txt", ".pdf", ".docx", ".pptx"}:
            groups.setdefault(item["sha256"], []).append(path)
    for digest, paths in groups.items():
        if len(paths) > 1:
            add("compare-materials", sorted(paths), "文件字节相同：比较主引用与保留要求；只提出合并候选，不删除材料", digest)
    return result


def monitor(root, dry_run=False):
    """单次监测；即使没有变化也只更新监测时间，事件不会重复新增。"""
    root = Path(root).resolve()
    destination = state_path(root)
    # dry-run 连目录和锁文件都不创建，适合检查将产生的变化。
    if dry_run:
        return advance(load_state(root), collect(root), dry_run=True)[1]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with e.locked(destination):
        previous = load_state(root)
        snapshot = collect(root)
        if snapshot["errors"]:
            raise ValueError("证据图不完整，保留监测基线：" + "; ".join(snapshot["errors"]))
        state, summary = advance(previous, snapshot)
        r.write_json(destination, state)
    return summary


def advance(previous, snapshot, dry_run=False):
    """纯数据转换便于审查：一份新状态包含全部事件与对应基线。"""
    changes = diff(previous["snapshot"] if previous else None, snapshot)
    timestamp = snapshot["observed_at"]
    sequence = previous["sequence"] if previous else 0
    events = list(previous["events"]) if previous else []
    for change in changes:
        sequence += 1
        events.append({"id": f"OBS-{sequence:08d}", "observed_at": timestamp, **change})
    candidates = {key: dict(value) for key, value in previous["candidates"].items()} if previous else {}
    proposed = suggestions(snapshot)
    # 材料变化提出更新引用的候选；它不会因下一次无变化而自动消失。
    for event in events[-len(changes):] if changes else []:
        if event["kind"] in {"material-changed", "material-out-of-scope", "experiment-finished"}:
            cid = "CAND-" + e.fingerprint([event["kind"], event["target"], event.get("after")])[:20]
            proposed[cid] = {"id": cid, "kind": "inspect-update", "targets": [event["target"]], "event_id": event["id"],
                             "reason": "检查变更或实验结果，按证据更新引用；执行完成不等于结论正确"}
    for cid, value in proposed.items():
        old = candidates.get(cid, {})
        candidates[cid] = {**value, "status": "pending", "first_seen": old.get("first_seen", timestamp), "last_seen": timestamp}
    for cid, value in candidates.items():
        if cid not in proposed and value["kind"] != "inspect-update":
            value.update(status="condition-not-observed", last_checked=timestamp)
    invalid_since = {nid: previous["invalid_since"].get(nid, timestamp) if previous else timestamp
                     for nid, node in snapshot["nodes"].items() if node["risks"]}
    state = {"schema_version": SCHEMA, "sequence": sequence, "snapshot": snapshot, "events": events,
             "candidates": candidates, "invalid_since": invalid_since}
    return state, {"observed_at": timestamp, "baseline_created": previous is None, "dry_run": dry_run,
                   "changes": changes, "new_events": len(changes), "pending_candidates": sum(v["status"] == "pending" for v in candidates.values()),
                   "state_path": STATE, "errors": snapshot["errors"], "note": snapshot["note"]}
