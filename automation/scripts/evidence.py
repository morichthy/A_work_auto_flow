"""结论准入与跨文档证据关系；只用标准库，不判断科学命题真假。

正式使用要求固定版本、明确 scope、复核记录和有效依赖。探索允许读取
旧记录并展示风险。图每次从源元数据重建，撤回不依赖过期索引；所有修改
均限定单个 manifest，使用锁、版本比较和原子替换，保留复核历史。
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote

STATES = {"not-reviewed", "accepted", "disputed", "retracted", "superseded"}
UNSAFE = {"disputed", "retracted", "superseded"}
RELATIONS = {"supports", "input", "background", "contradicts"}
DEPENDENT = {"supports", "input"}
KINDS = {"fact", "calculation", "inference", "recommendation"}
HASH = re.compile(r"[0-9a-f]{64}")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    """流式读取固定引用的文件，不复制原件。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(value):
    """版本是内容身份；复核与封存事件单独影响有效性，不改变内容版本。

    递归排除复核字段使 claim 的复核不会意外使所有固定 Run 引用过期。
    结论正文、依赖、输入、参数和产物变更仍会改变指纹。
    """
    def content(item):
        if isinstance(item, dict):
            return {k: content(v) for k, v in item.items()
                    if k not in {"review", "review_history", "finalization", "finalization_history"}}
        if isinstance(item, list):
            return [content(v) for v in item]
        return item
    return hashlib.sha256(json.dumps(content(value), sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def inside(root, path):
    path = Path(path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"证据写入或元数据路径越出工作区：{path}")
    return path


def owner_fingerprint(raw):
    """复核绑定承载计算的版本；新增其他 claim 不使已有 claim 无故过期。"""
    return fingerprint({k: v for k, v in raw.items() if k != "claims"})


def reference_path(root, target):
    """外部引用只接受 sources 中已启用的逐文件登记，不跟随正文链接扩权。"""
    if not isinstance(target, str) or not target.strip() or "://" in target:
        raise ValueError("证据路径必须是非空文件路径，不能自动读取 URL")
    raw = (root / target).absolute()
    # Do not resolve a junction first and then mistake its destination for a
    # directly authorized file. The same rule applies to local legacy refs.
    if any(parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), "st_file_attributes", 0) & 0x400)
           for parent in [raw, *raw.parents]):
        raise ValueError("证据来源含符号链接或联接")
    path = raw.resolve()
    registry = root / "retrieval/sources.json"
    entries = [item for item in read(registry).get("sources", [])
               if (root / item["path"]).resolve() == path] if registry.is_file() else []
    # Explicit revocation also applies to a source physically inside root. A
    # legacy path reference must not bypass a newer source-registration denial.
    if any(not item.get("enabled", True) or item.get("sensitivity") == "restricted" for item in entries):
        raise ValueError("证据来源登记已禁用或限制访问")
    # A moved historical Run keeps its original bytes, including file locators.
    # Resolve only an explicit per-file registration when that original is
    # absent. Never guess by basename, replace an existing original, or follow
    # a chain of redirects. The pinned digest makes this a location repair,
    # rather than silently accepting different evidence under an old name.
    if not path.exists() and registry.is_file():
        moved = [item for item in read(registry).get("sources", [])
                 if item.get("relocated_from") == target]
        if moved:
            if len(moved) != 1:
                raise ValueError("历史来源迁移登记不唯一")
            item = moved[0]
            if not item.get("enabled", True) or item.get("sensitivity") == "restricted":
                raise ValueError("历史来源迁移登记已禁用或限制访问")
            pinned = item.get("sha256")
            if not isinstance(pinned, str) or not HASH.fullmatch(pinned):
                raise ValueError("历史来源迁移登记缺少固定指纹")
            destination = (root / item["path"]).absolute()
            if any(parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), "st_file_attributes", 0) & 0x400)
                   for parent in [destination, *destination.parents]):
                raise ValueError("历史来源迁移目标含符号链接或联接")
            destination = destination.resolve()
            destinations = [entry for entry in read(registry).get("sources", [])
                            if (root / entry["path"]).resolve() == destination]
            if any(not entry.get("enabled", True) or entry.get("sensitivity") == "restricted" for entry in destinations):
                raise ValueError("历史来源迁移目标已禁用或限制访问")
            if not destination.is_file() or sha256(destination) != pinned:
                raise ValueError("历史来源迁移目标缺失或固定指纹不匹配")
            return destination
    if path.is_relative_to(root.resolve()):
        return path
    if len(entries) != 1:
        raise ValueError("外部证据未逐文件登记")
    return path


@contextmanager
def locked(path):
    """同目录排他锁；不自动删除可能仍被其他任务持有的锁。"""
    lock = path.with_name(path.name + ".evidence-lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError(f"证据记录正被修改，稍后重试：{path.name}") from exc
    os.close(fd)
    try:
        yield
    finally:
        lock.unlink()


def replace(path, data, expected, dry_run=False):
    """预览不写；正式写入前比较原字节，避免覆盖本次读取后的修改。"""
    if dry_run:
        return
    with locked(path):
        if sha256(path) != expected:
            raise ValueError("证据记录在检查后变化，请重新检查")
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".evidence-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class EvidenceGraph:
    """只扫描约定元数据；不把任意 JSON 当结论，不加载大产物正文。"""
    def __init__(self, root, overrides=None, *, file_hasher=None):
        self.root = Path(root).resolve()
        self.nodes, self.owners, self.documents, self.edges = {}, [], {}, {}
        self._identities = set()
        self.errors = []
        # 一次证据图快照内复用文件检查；下一次正式读取会创建新图并重验。
        self.run_checks = {}
        # 正式复核默认完整检查；只读观察可注入更窄的范围/大小预算。
        # 注入器必须在不能核验时抛错，不能用已登记摘要冒充当前字节。
        self.file_hasher = file_hasher or sha256
        self.overrides = overrides or {}
        from manifest_discovery import manifests
        cards = {'run.json': 'run_id', 'research.json': 'research_id', 'module.json': 'module_id'}
        paths = [(p, cards[p.name]) for p in manifests(self.root, cards)]
        # 任意深度的知识/报告只认逐文档旁文件，跳过模板和生成件。
        paths += [(p, "evidence_id") for base in ("knowledge", "reports/sources", "reports/manifests")
                  for p in (self.root / base).rglob("*.evidence.json")]
        for path, key in sorted(paths):
            if "_template" in path.parts or path.name.startswith("example."):
                continue
            try:
                self._load(inside(self.root, path), key)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.errors.append(f"{path.relative_to(self.root)}: {exc}")
        self._connect()

    def _load(self, path, key):
        raw = self.overrides.get(path, read(path))
        if not isinstance(raw, dict) or not isinstance(raw.get(key), str) or not raw[key]:
            raise ValueError(f"缺少有效 {key}")
        oid = raw[key]
        if key == 'run_id' and raw.get('owner_id') is not None and (not isinstance(raw['owner_id'], str) or not raw['owner_id'].strip()):
            raise ValueError('owner_id 必须为非空对象 ID 或 null')
        if not isinstance(raw.get("review", {}), dict):
            raise ValueError("review 必须为对象")
        if not isinstance(raw.get("parent_run_ids", []), list) or not all(isinstance(p, str) for p in raw.get("parent_run_ids", [])):
            raise ValueError("parent_run_ids 必须为字符串数组")
        self._add(oid, raw, path, "owner")
        if key == "evidence_id":
            document = inside(self.root, self.root / raw["document_path"])
            if not any(document.is_relative_to(self.root / base) for base in ("knowledge", "reports/sources")):
                raise ValueError("旁文件仅声明知识或报告源，不能覆盖 Run/研究/算法对象的身份")
            if not document.is_file() or document in self.documents:
                raise ValueError("document_path 缺失或重复声明")
            self.documents[document] = oid
        else:
            self.owners.append((path.parent, oid))
        claims = raw.get("claims", [])
        if not isinstance(claims, list):
            raise ValueError("claims 必须为数组")
        for claim in claims:
            if not isinstance(claim, dict) or not re.fullmatch(r"CLM-[A-Za-z0-9_-]+", str(claim.get("claim_id", ""))):
                raise ValueError("claim_id 必须为 CLM- 开头的稳定 ID")
            if not isinstance(claim.get("review", {}), dict) or not isinstance(claim.get("review_history", []), list):
                raise ValueError("claim review/review_history 格式无效")
            self._add(claim["claim_id"], claim, path, "claim", owner=oid)

    def _add(self, nid, raw, path, kind, owner=None):
        if nid.casefold() in self._identities:
            raise ValueError(f"重复证据 ID：{nid}")
        self._identities.add(nid.casefold())
        self.nodes[nid] = {"id": nid, "raw": raw, "path": path, "kind": kind, "owner": owner,
                           "fingerprint": fingerprint(raw), "blockers": set(), "issues": []}
        self.edges[nid] = set()

    def owner_for(self, path):
        path = Path(path).resolve()
        if path in self.documents:
            return self.documents[path]
        candidates = [(len(base.parts), nid) for base, nid in self.owners if path.is_relative_to(base)]
        return max(candidates)[1] if candidates else None

    def refs(self, node):
        key = "evidence_refs" if node["kind"] == "claim" else "dependencies"
        refs = node["raw"].get(key, [])
        if not isinstance(refs, list):
            node["issues"].append(f"{key} 必须为数组")
            return []
        return refs

    def _target(self, target):
        if target in self.nodes:
            node = self.nodes[target]
            return target, node["fingerprint"]
        if re.match(r"^(RUN|CLM|RES|MOD|EVD)-", target):
            raise ValueError(f"证据对象不存在：{target}")
        path = reference_path(self.root, target)
        if not path.is_file():
            raise ValueError(f"证据文件不存在：{target}")
        return self.owner_for(path), self.file_hasher(path)

    def _connect(self):
        for nid, node in self.nodes.items():
            raw = node["raw"]
            review = raw.get("review", {})
            status = review.get("status", "not-reviewed") if isinstance(review, dict) else "invalid"
            if status in UNSAFE or status not in STATES:
                node["blockers"].add(nid)
            if raw.get("run_id") and raw.get("status") in {"failed", "cancelled"}:
                node["blockers"].add(nid)
            if node["owner"]:
                # 所属对象撤回影响子结论，但不继承整个 Run 的 accepted。
                self.edges[nid].add(node["owner"])
                # 已接受的上游也必须有完整定义，不能靠手填 accepted 绕过。
                if (not isinstance(raw.get("statement"), str) or not raw.get("statement", "").strip()
                        or not isinstance(raw.get("scope"), str) or not raw.get("scope", "").strip()
                        or raw.get("kind") not in KINDS):
                    node["issues"].append("结论需要 statement、scope 与有效 kind")
                if not any(isinstance(ref, dict) and ref.get("relation") in DEPENDENT for ref in self.refs(node)):
                    node["issues"].append("结论没有支持证据")
                if status == "accepted":
                    if not all(isinstance(review.get(k), str) and review[k].strip()
                               for k in ("reviewer", "reason", "evidence", "scope", "date")) or review.get("scope") != raw.get("scope"):
                        node["issues"].append("accepted 复核字段或 scope 不完整")
                    if review.get("content_fingerprint") != node["fingerprint"]:
                        node["blockers"].add("review-content-changed:" + nid)
                    if review.get("owner_fingerprint") != owner_fingerprint(self.nodes[node["owner"]]["raw"]):
                        node["blockers"].add("review-owner-changed:" + nid)
            for parent in raw.get("parent_run_ids", []):
                if parent in self.nodes:
                    self.edges[nid].add(parent)
                    self.edges[nid].update(cid for cid, child in self.nodes.items() if child.get("owner") == parent)
                else:
                    node["blockers"].add(str(parent))
            for ref in self.refs(node):
                if not isinstance(ref, dict) or ref.get("relation") not in RELATIONS or not isinstance(ref.get("target"), str):
                    node["issues"].append("引用需要 target 与有效 relation")
                    continue
                # 背景/反证保留为关系数据，不因被引用结论撤回而失效。
                if ref["relation"] not in DEPENDENT:
                    continue
                try:
                    target, digest = self._target(ref["target"])
                    if target:
                        self.edges[nid].add(target)
                        # 消费整个其他对象时，同时消费它声明的结论状态。
                        # 不给本对象的输入/输出文件添加自己的所有子结论，
                        # 避免把“结论依赖计算结果”变成自证环。
                        if target != node.get("owner") and self.nodes[target]["kind"] == "owner":
                            self.edges[nid].update(cid for cid, child in self.nodes.items() if child.get("owner") == target)
                    if not HASH.fullmatch(str(ref.get("sha256", ""))):
                        node["issues"].append(f"未固定版本：{ref['target']}")
                    elif digest != ref["sha256"]:
                        node["blockers"].add("version-changed:" + ref["target"])
                    if not isinstance(ref.get("locator"), str) or not ref["locator"].strip():
                        node["issues"].append(f"缺少证据定位：{ref['target']}")
                except (OSError, ValueError) as exc:
                    node["blockers"].add(str(exc))
            if node["issues"]:
                node["blockers"].add("invalid-evidence:" + nid)
        # Kahn 删除无依赖节点。剩下的是循环及其下游；全部禁止正式使用，
        # 不递归，因此大图和历史环形依赖不会造成递归溢出或无限循环。
        pending = {nid: set(edges) for nid, edges in self.edges.items()}
        while True:
            leaves = {nid for nid, edges in pending.items() if not edges}
            if not leaves:
                break
            pending = {nid: edges - leaves for nid, edges in pending.items() if nid not in leaves}
        for nid in pending:
            self.nodes[nid]["blockers"].add("dependency-cycle:" + nid)
        changed = True
        while changed:
            changed = False
            for nid, deps in self.edges.items():
                before = len(self.nodes[nid]["blockers"])
                for dep in deps:
                    self.nodes[nid]["blockers"].update(self.nodes[dep]["blockers"])
                changed |= before != len(self.nodes[nid]["blockers"])

    def claim_errors(self, nid, scope, require_finalized=True):
        node = self.nodes[nid]
        raw = node["raw"]
        errors = list(node["issues"]) + list(node["blockers"]) + list(self.errors)
        if node["kind"] != "claim":
            return ["目标不是 claim"]
        for key in ("statement", "scope"):
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                errors.append(f"缺少 {key}")
        if raw.get("kind") not in KINDS:
            errors.append("无效 claim kind")
        if not scope or raw.get("scope") != scope:
            errors.append("scope 不匹配；需明确选择已复核的适用范围")
        review = raw.get("review", {})
        if not isinstance(review, dict) or review.get("status") != "accepted" or not all(
                isinstance(review.get(k), str) and review[k].strip() for k in ("reviewer", "reason", "evidence", "scope", "date")):
            errors.append("结论尚无完整 accepted 复核")
        elif review["scope"] != raw.get("scope"):
            errors.append("复核 scope 与结论不一致")
        if not any(isinstance(ref, dict) and ref.get("relation") in DEPENDENT for ref in self.refs(node)):
            errors.append("结论没有支持证据")
        # 实际支持的上游结论必须已复核；容器仅检查失效，不能用其 accepted
        # 覆盖子 claim。显式消费整个 Run 时仍要求该 Run 已复核且执行成功。
        visited, queue = set(), [nid]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            for dep in self.edges[current]:
                target = self.nodes[dep]
                if target["raw"].get("run_id"):
                    if target["raw"].get("status") != "succeeded":
                        errors.append(f"上游 Run 未执行成功：{dep}")
                    if require_finalized or dep != node.get("owner"):
                        seal = target["raw"].get("finalization", {})
                        if not isinstance(seal, dict) or seal.get("fingerprint") != target["fingerprint"]:
                            errors.append(f"Run 尚未有效 finalize：{dep}")
                        # seal 固定的是 manifest 内容，不能证明外部输入/产物
                        # 字节仍未改变。正式复用必须重新核对这些文件及必要字段。
                        if dep not in self.run_checks:
                            self.run_checks[dep] = run_record_errors(self.root, target["raw"], file_hasher=self.file_hasher)
                        errors.extend(f"{dep}: {error}" for error in self.run_checks[dep])
                if dep != self.nodes[current].get("owner"):
                    state = target["raw"].get("review", {}).get("status", "not-reviewed")
                    if state != "accepted":
                        errors.append(f"上游未复核：{dep}")
                    if target["raw"].get("run_id") and target["raw"].get("status") != "succeeded":
                        errors.append(f"上游 Run 未执行成功：{dep}")
                queue.append(dep)
        return sorted(set(errors))

    def document_state(self, path, body="", scope=None):
        oid = self.owner_for(path)
        if not oid:
            return {"owner_id": None, "blocking_evidence_ids": [], "claims": [], "formal_eligible": False,
                    "issues": ["未登记结论"]}
        owner = self.nodes[oid]
        blockers = set(owner["blockers"])
        declared = set()
        for ref in self.refs(owner):
            if isinstance(ref, dict):
                declared.add(ref.get("target"))
        # 旧 Markdown 没声明关系类型时，遇到失效引用给出待分类提示。
        # 显式 background/contradicts 可解除此不确定性，不伪判它是实际依赖。
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", body):
            target = unquote(target.split("#", 1)[0].strip().strip("<>"))
            if not target or "://" in target:
                continue
            other_path = (Path(path).parent / target).resolve()
            other = self.owner_for(other_path)
            relative = other_path.relative_to(self.root).as_posix() if other_path.is_relative_to(self.root) else str(other_path)
            if other and other != oid and other not in declared and relative not in declared and self.nodes[other]["blockers"]:
                blockers.add("unclassified-reference:" + other)
        claims = []
        for nid, node in self.nodes.items():
            if node.get("owner") == oid:
                errors = self.claim_errors(nid, scope or node["raw"].get("scope"))
                claims.append({"claim_id": nid, "scope": node["raw"].get("scope"), "errors": errors,
                               "eligible": not errors, "review": node["raw"].get("review", {})})
                blockers.update(node["blockers"])
        return {"owner_id": oid, "fingerprint": owner["fingerprint"], "blocking_evidence_ids": sorted(blockers),
                "claims": claims, "formal_eligible": bool(claims) and all(c["eligible"] for c in claims) and not blockers,
                "issues": owner["issues"] + self.errors}

    def formal_text(self, path, scope, excluded=()):
        state = self.document_state(path, scope=scope)
        # 只导出逐条已复核结论，不夹带同一正文里其他尚未复核的论断。
        lines = []
        for item in state["claims"]:
            if item["eligible"] and item["claim_id"] not in excluded:
                raw = self.nodes[item["claim_id"]]["raw"]
                lines += [f"Claim: {item['claim_id']}", f"Scope: {scope}", raw["statement"],
                          "Review: " + json.dumps(raw["review"], ensure_ascii=False),
                          "Evidence: " + json.dumps(raw["evidence_refs"], ensure_ascii=False), ""]
        return "\n".join(lines), state

    def status(self, target=None, scope=None):
        if target in self.nodes:
            node = self.nodes[target]
            errors = self.claim_errors(target, scope) if node["kind"] == "claim" else sorted(node["blockers"])
            return {"target": target, "fingerprint": node["fingerprint"], "errors": errors,
                    "eligible": not errors if node["kind"] == "claim" else False,
                    "affected_ids": sorted(nid for nid in self.nodes if target in self.nodes[nid]["blockers"] and nid != target)}
        if target:
            path = reference_path(self.root, target)
            if not path.is_file():
                raise ValueError("证据文档不存在")
            return self.document_state(path, path.read_text(encoding="utf-8", errors="replace") if path.suffix == ".md" else "", scope)
        return {"errors": self.errors, "objects": len(self.owners) + len(self.documents),
                "claims": sum(n["kind"] == "claim" for n in self.nodes.values()),
                "affected": {nid: sorted(n["blockers"]) for nid, n in self.nodes.items() if n["blockers"]}}


def review_claim(root, claim_id, status, reviewer, reason, evidence="", scope="", replacement="", dry_run=False):
    graph = EvidenceGraph(root)
    node = graph.nodes.get(claim_id)
    if not node or node["kind"] != "claim":
        raise ValueError("找不到结论 ID")
    if status not in STATES or not reviewer.strip() or not reason.strip():
        raise ValueError("需要有效状态、reviewer 和 reason")
    if status == "superseded" and (replacement not in graph.nodes or replacement == claim_id or graph.nodes[replacement]["kind"] != "claim"):
        raise ValueError("superseded 必须引用另一个已存在结论")
    if replacement and status != "superseded":
        raise ValueError("replacement 仅用于 superseded")
    path = node["path"]
    expected = sha256(path)
    data = read(path)
    claim = next(c for c in data["claims"] if c["claim_id"] == claim_id)
    previous = dict(claim.get("review", {}))
    current = {"status": status, "reviewer": reviewer, "reason": reason, "evidence": evidence,
               "scope": scope, "date": datetime.now(timezone.utc).isoformat(), "replacement_claim_id": replacement or None}
    current.update(content_fingerprint=fingerprint(claim), owner_fingerprint=owner_fingerprint(data))
    claim["review"] = current
    claim.setdefault("review_history", []).append({"previous": previous, "current": current})
    proposed = EvidenceGraph(root, {path: data})
    if status == "accepted":
        errors = proposed.claim_errors(claim_id, scope, require_finalized=False)
        if errors:
            raise ValueError("结论不能接受：" + "; ".join(errors))
    replace(path, data, expected, dry_run)
    return {"claim_id": claim_id, "review": current, "dry_run": dry_run,
            "affected_ids": proposed.status(claim_id, scope)["affected_ids"]}


def run_record_errors(root, raw, *, file_hasher=None):
    """检查实际文件与运行字段，供封存及正式读取共用，不递归访问结论图。"""
    errors = []
    file_hasher = file_hasher or sha256
    if raw.get("status") != "succeeded":
        errors.append("Run 尚未执行成功")
    for group in ("inputs", "artifacts"):
        items = raw.get(group, [])
        if not isinstance(items, list) or not items:
            errors.append(f"缺少 {group}")
            continue
        for item in items:
            try:
                if not isinstance(item, dict) or not HASH.fullmatch(str(item.get("sha256", ""))):
                    raise ValueError("需要 path 和 SHA-256")
                path = reference_path(Path(root), item.get("path"))
                if file_hasher(path) != item["sha256"]:
                    raise ValueError("文件版本变化")
            except (OSError, ValueError) as exc:
                errors.append(f"{group}: {exc}")
    code = raw.get("code", {})
    if not isinstance(code, dict) or not re.fullmatch(r"[0-9a-f]{40,64}", str(code.get("commit", ""))) or code.get("dirty") is not False:
        errors.append("代码需固定 commit 且 dirty=false；先保存代码版本")
    environment = raw.get("environment", {})
    if not isinstance(environment, dict) or not environment.get("python") or not HASH.fullmatch(str(environment.get("lock_or_image_digest", ""))):
        errors.append("环境需记录 Python 与 lock_or_image_digest（SHA-256）")
    checks = raw.get("quality_results", [])
    # 不能静默忽略损坏条目，否则混入一条 passed 就可能掩盖其他必要检查。
    if not isinstance(checks, list) or any(not isinstance(q, dict) or not isinstance(q.get("required", True), bool) for q in checks):
        errors.append("quality_results 必须为对象数组，required 必须为布尔值")
    required = [q for q in checks if isinstance(q, dict) and q.get("required", True)] if isinstance(checks, list) else []
    if not required or any(q.get("status") != "passed" or not q.get("check") for q in required):
        errors.append("必要验证必须具名并全部 passed，不能用 skipped 代替")
    return errors


def check_run(root, run_id, scope, check_seal=True):
    """正式 Run 的记录完整性检查；不执行计算，不自动科学复核。"""
    graph = EvidenceGraph(root)
    node = graph.nodes.get(run_id)
    if not node or not node["raw"].get("run_id"):
        raise ValueError("找不到 Run")
    raw = node["raw"]
    errors = list(graph.errors) + sorted(node["blockers"]) + run_record_errors(root, raw)
    claims = [nid for nid, n in graph.nodes.items() if n.get("owner") == run_id]
    if not claims:
        errors.append("正式 Run 至少需要一条已复核结论")
    for nid in claims:
        errors.extend(f"{nid}: {e}" for e in graph.claim_errors(nid, scope, require_finalized=False))
    seal = raw.get("finalization")
    if check_seal and seal and (not isinstance(seal, dict) or seal.get("fingerprint") != node["fingerprint"]):
        errors.append("封存后内容已变化，需复核并重新 finalize")
    return {"run_id": run_id, "scope": scope, "eligible": not errors,
            "errors": sorted(set(errors)), "fingerprint": node["fingerprint"],
            "note": "记录准入检查，不证明科学模型真实有效"}


def finalize_run(root, run_id, scope, dry_run=False):
    graph = EvidenceGraph(root)
    node = graph.nodes.get(run_id)
    if not node:
        raise ValueError("找不到 Run")
    expected = sha256(node["path"])
    # 重新 finalize 必须重新通过全部检查；允许生成新的封存指纹，旧版
    # 封存仍随前一版文件/Git 保留，不把旧 seal 本身作为永久阻塞。
    result = check_run(root, run_id, scope, check_seal=False)
    if result["eligible"]:
        data = read(node["path"])
        if not isinstance(data.get("finalization_history", []), list):
            raise ValueError("finalization_history 必须为数组")
        previous = data.get("finalization")
        data["finalization"] = {"fingerprint": result["fingerprint"], "scope": scope,
                                "checked_at": datetime.now(timezone.utc).isoformat(), "check_version": 1}
        data.setdefault("finalization_history", []).append({"previous": previous, "current": data["finalization"]})
        replace(node["path"], data, expected, dry_run)
    return {**result, "dry_run": dry_run, "finalized": result["eligible"] and not dry_run}
