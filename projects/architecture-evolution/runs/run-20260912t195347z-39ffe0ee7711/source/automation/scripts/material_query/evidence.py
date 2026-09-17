"""材料查询的局部、只读证据准入；不构造全工作区 EvidenceGraph。

索引只定位 claim 容器和对应 review。读取前用当前 HEAD/索引水位确认定位
没有遗漏新增修订，随后全部规范字节和来源字节经 Reader 重新鉴权、计量。
复用既有复核绑定规则；支持边上的无环性和传播失效在本次有限闭包内计算。
"""
from collections import deque
from copy import deepcopy
import json

from memory import index
from memory.contracts import canonical_hash
from memory.evidence_adapter import DEPENDENT, EvidenceAdapter, iter_refs

from .contracts import FixedRef
from .legacy_adapter import fixed_record, from_legacy
from .validation import QueryError, parse


class Evidence:
    """一次操作一个实例；不能跨查询缓存权限、来源内容或 accepted 状态。"""

    # 该方法只检查传入规范字段，不执行旧适配器的全库扫描。
    _review_errors = EvidenceAdapter._review_errors

    def __init__(self, reader):
        self.reader = reader
        self.records, self.claims, self.reviews = {}, {}, {}
        self.catalogs, self.reviewed = {}, set()
        self.nodes, self.edges, self.files = set(), set(), set()

    def _node(self, key):
        if key not in self.nodes:
            self.reader.ledger.charge("graph_nodes", 1)
            self.nodes.add(key)

    def _edge(self, source, ref):
        key = (source, ref["target_kind"], ref["target_id"], ref.get("revision"), ref.get("sha256"))
        if key not in self.edges:
            self.reader.ledger.charge("graph_edges", 1)
            self.edges.add(key)

    def _depth(self, depth):
        # 跳数是当前查询见过的最大路径深度，不因同层并行分支重复收费。
        used = self.reader.ledger.snapshot()["graph_hops"]
        if depth > used:
            self.reader.ledger.charge("graph_hops", depth - used)

    def _catalog(self, owner_id):
        if owner_id in self.catalogs:
            return self.catalogs[owner_id]
        owner = self.reader.owner(owner_id)
        head, manifest = self.reader.store.head_manifest(owner)
        db = index.connect(self.reader.root, create=False)
        if db is None or head is None:
            if db is not None:
                db.close()
            raise QueryError("SOURCE_MISSING", "正式证据缺少当前定位索引")
        try:
            state = db.execute("SELECT indexed_generation,target_generation,fts_status FROM memory_index_state WHERE owner_id=?", (owner_id,)).fetchone()
            indexed_owner = db.execute("SELECT head,generation FROM memory_owners WHERE owner_id=?", (owner_id,)).fetchone()
            if (state is None or indexed_owner is None or state["fts_status"] != "indexed"
                    or state["indexed_generation"] != head["generation"] or state["target_generation"] != head["generation"]
                    or indexed_owner["generation"] != head["generation"] or json.loads(indexed_owner["head"]) != head):
                raise QueryError("STALE", "正式证据索引未覆盖当前HEAD，不能沿用旧复核")
            # 只读取身份/版本元数据；不读取本 owner 的无关正文。清单对照还
            # 能拒绝“水位正确但索引记录被删除”的损坏投影。
            rows = db.execute("SELECT record_id,revision,kind FROM memory_records WHERE owner_id=? AND entity_kind='record'", (owner_id,)).fetchall()
            positions = {row["record_id"]: dict(row) for row in rows}
            # 规范 representation 专门存于另一投影表；它不是被漏掉的 review。
            representation_ids = {row[0] for row in db.execute(
                "SELECT representation_id FROM memory_representations WHERE owner_id=?", (owner_id,))}
            expected_ids = set(manifest["record_heads"]) - representation_ids
            if set(positions) != expected_ids or any(
                    positions[rid]["revision"] != manifest["record_heads"][rid]["revision"] for rid in positions):
                raise QueryError("STALE", "正式证据定位与当前清单不一致")
            self.catalogs[owner_id] = positions
            self.reader.ledger.checkpoint()
            return positions
        finally:
            db.close()

    def _record(self, record_id):
        if record_id in self.records:
            self.reader.ledger.checkpoint()
            return self.records[record_id]
        owner = self.reader.locate(record_id)
        self._catalog(owner["owner_id"])
        self._node(("record", record_id))
        value = self.reader.current_record(record_id)
        self.records[record_id] = value
        for claim in value["payload"].get("claims", []):
            cid = claim["claim_id"]
            if cid in self.claims and self.claims[cid][1]["record_id"] != record_id:
                raise QueryError("INTERNAL", "结论身份冲突")
            self.claims[cid] = (claim, value)
        return value

    def _claim(self, claim_id):
        if claim_id not in self.claims:
            db = index.connect(self.reader.root, create=False)
            if db is None:
                raise QueryError("SOURCE_MISSING", "结论定位索引不可用")
            try:
                row = db.execute("SELECT record_id,owner_id FROM memory_records WHERE canonical_id=? AND entity_kind='claim'", (claim_id,)).fetchone()
            finally:
                db.close()
            if row is None:
                # 不偷偷回退到全库旧 Run/owner 图；该能力必须显式提供。
                raise QueryError("UNSUPPORTED", "当前局部证据提供器仅支持已索引规范claim")
            self.reader.owner(row["owner_id"])
            self._record(row["record_id"])
        if claim_id not in self.claims:
            raise QueryError("STALE", "结论定位不匹配当前规范内容")
        self._node(("claim", claim_id))
        claim, record = self.claims[claim_id]
        if claim_id not in self.reviewed:
            self._reviews(claim_id, record["owner_id"])
        return claim, record

    def _reviews(self, claim_id, owner_id):
        self._catalog(owner_id)
        db = index.connect(self.reader.root, create=False)
        try:
            # review 的 owner 必须等于 claim owner（既有写服务的约束）。
            # JSON 只用于派生索引定位；返回的正文仍由当前规范记录确认。
            rows = db.execute("""SELECT record_id FROM memory_records
                WHERE owner_id=? AND entity_kind='record' AND kind='review'
                AND json_extract(payload,'$.target_claim_id')=?""", (owner_id, claim_id)).fetchall()
        finally:
            db.close()
        if len(rows) > 1:
            raise QueryError("INTERNAL", "同一结论存在多个当前复核记录")
        for row in rows:
            review = self._record(row["record_id"])
            if review["kind"] != "review" or review["payload"]["target_claim_id"] != claim_id:
                raise QueryError("STALE", "复核定位与当前规范内容不一致")
            self.reviews[claim_id] = review
        self.reviewed.add(claim_id)

    def _reference(self, ref):
        kind, target = ref["target_kind"], ref["target_id"]
        if kind == "record":
            record = self._record(target)
            if record["revision"] != ref["revision"] or (ref.get("sha256") and record["record_hash"] != ref["sha256"]):
                raise QueryError("STALE", "正式证据引用了旧记录修订")
            return target
        if kind == "claim":
            claim, _ = self._claim(target)
            if canonical_hash(claim) != ref.get("sha256"):
                raise QueryError("STALE", "正式证据结论指纹不匹配")
            return target
        if kind == "file":
            key = (target, ref.get("sha256"))
            if key not in self.files:
                self._node(("file", *key))
                fixed, _ = from_legacy(ref)
                self.reader.file_bytes(fixed)
                self.files.add(key)
            return None
        raise QueryError("UNSUPPORTED", "局部正式证据暂不展开旧owner/Run身份")

    @staticmethod
    def _failure(code, target, message):
        # 对外只报告当前已授权的消费方，避免错误详情泄露受限来源身份。
        return {"code": code, "target_id": target, "message": message, "path": [target]}

    def _analyze(self, claim_id, scope):
        queue, dependencies, failures = deque([(claim_id, 0)]), {}, []
        while queue:
            target, depth = queue.popleft()
            self.reader.ledger.checkpoint()
            if target in dependencies:
                continue
            self._depth(depth)
            dependencies[target] = set()
            if target in self.claims:
                claim, record = self._claim(target)
                _, errors = self._review_errors(target, claim, record, scope if target == claim_id else claim["scope"])
                failures.extend(errors)
                if not any(ref.get("relation") in DEPENDENT for ref in claim["evidence_refs"]):
                    failures.append(self._failure("EVIDENCE_INELIGIBLE", target, "结论没有独立支持依据"))
                refs = list(claim["evidence_refs"]) + list(record["sources"])
                if target in self.reviews:
                    refs += self.reviews[target]["payload"]["evidence_refs"]
            else:
                record = self._record(target)
                refs = list(record["sources"])
                if record["kind"] in {"event", "narrative", "experience", "overview"}:
                    children = record["payload"].get("claims", [])
                    if not children:
                        failures.append(self._failure("EVIDENCE_INELIGIBLE", target, "叙述记录没有可独立复核的结论"))
                    for child in children:
                        cid = child["claim_id"]
                        self._edge(target, {"target_kind": "claim", "target_id": cid})
                        dependencies[target].add(cid)
                        queue.append((cid, depth + 1))
                elif record["kind"] == "source":
                    refs.append(dict(record["payload"]["source_ref"], relation="input"))
                else:
                    refs += list(iter_refs(record["payload"]))
            for ref in refs:
                if ref.get("relation") not in DEPENDENT:
                    continue
                self._edge(target, ref)
                self._depth(depth + 1)
                try:
                    child = self._reference(ref)
                except QueryError as exc:
                    if exc.code in {"BUDGET", "CANCELLED", "DENIED", "INTERNAL"}:
                        raise
                    failures.append(self._failure(exc.code, target, exc.message))
                    continue
                if child:
                    dependencies[target].add(child)
                    queue.append((child, depth + 1))
        # 逐次删除无依赖叶子；剩余节点含支持循环及消费该循环的节点。
        pending = {node: set(edges) for node, edges in dependencies.items()}
        while pending:
            self.reader.ledger.checkpoint()
            leaves = {node for node, edges in pending.items() if not edges}
            if not leaves:
                failures.append(self._failure("EVIDENCE_INELIGIBLE", claim_id, "支持依据存在循环"))
                break
            pending = {node: edges - leaves for node, edges in pending.items() if node not in leaves}
        return failures

    def assess(self, record, scope):
        """逐 claim 返回当前状态；旧修订不能继承当前内容的复核结论。"""
        fixed = self.reader.record(fixed_record(record))
        current = self._record(fixed["record_id"])
        stale = current["revision"] != fixed["revision"] or current["record_hash"] != fixed["record_hash"]
        states = []
        for claim in fixed["payload"].get("claims", []):
            cid = claim["claim_id"]
            if stale:
                errors = [self._failure("STALE", cid, "选定修订不是当前正式证据版本")]
                state = "not-reviewed"
            else:
                self._claim(cid)
                # 探索筛选可不指定适用域，此时只报告该 claim 自己声明的
                # 复核范围。正式 project 入口仍强制非空明确 scope。
                effective_scope = scope or claim["scope"]
                state, _ = self._review_errors(cid, claim, fixed, effective_scope)
                errors = self._analyze(cid, effective_scope)
            states.append({"claim_id": cid, "review_state": state, "effective_validity": not errors,
                           "errors": errors, "sha256": canonical_hash(claim), "owner_id": fixed["owner_id"]})
        return states

    def project(self, refs, scope):
        """只投影选定记录/claim中的有效主张；不把导航关系升级成支持。"""
        if not isinstance(scope, str) or not scope.strip():
            raise QueryError("VALIDATION", "正式证据必须指定适用范围")
        selected, rejected, queue, seen = {}, [], deque(), set()
        for ref in refs:
            if not isinstance(ref, FixedRef):
                ref = from_legacy(ref)[0] if "target_kind" in ref else parse(ref, FixedRef)
            if ref.kind == "claim":
                claim, record = self._claim(ref.id)
                if canonical_hash(claim) != ref.sha256:
                    raise QueryError("STALE", "选定结论指纹不匹配")
                selected[ref.id] = record
            elif ref.kind in {"record", "representation"}:
                record = self.reader.record(ref)
                current = self._record(ref.id)
                if record["record_hash"] != current["record_hash"]:
                    rejected.append({"canonical_id": ref.id, "errors": [self._failure("STALE", ref.id, "选定记录修订已过期")]})
                else:
                    queue.append((record, 0))
            else:
                raise QueryError("UNSUPPORTED", "正式投影仅接收规范记录或claim固定引用")
        while queue:
            record, depth = queue.popleft()
            rid = record["record_id"]
            if rid in seen:
                continue
            seen.add(rid)
            self._depth(depth)
            if record["kind"] in {"event", "narrative", "experience", "overview"}:
                selected.update((claim["claim_id"], record) for claim in record["payload"].get("claims", []))
            elif record["kind"] == "association":
                rejected.append({"canonical_id": rid, "errors": [self._failure("EVIDENCE_INELIGIBLE", rid, "导航关系不能供给正式支持")]})
            else:
                for ref in list(iter_refs(record["payload"])) + record["sources"]:
                    self._edge(rid, ref)
                    self._depth(depth + 1)
                    target = self._reference(ref)
                    if target in self.claims:
                        selected[target] = self.claims[target][1]
                    elif target:
                        queue.append((self.records[target], depth + 1))
        claims, assessed = [], {}
        for cid, record in sorted(selected.items()):
            rid = record["record_id"]
            if rid not in assessed:
                assessed[rid] = {item["claim_id"]: item for item in self.assess(record, scope)}
            state = assessed[rid][cid]
            if not state["effective_validity"]:
                rejected.append({"canonical_id": cid, "errors": deepcopy(state["errors"])})
                continue
            claim = next(item for item in record["payload"]["claims"] if item["claim_id"] == cid)
            claims.append({"canonical_id": cid, "claim_id": cid, "owner_id": record["owner_id"],
                           "record_id": rid, "revision": record["revision"], "sha256": state["sha256"],
                           "statement": claim["statement"], "text": claim["statement"], "scope": scope,
                           "review_state": "accepted", "effective_validity": True})
        return {"claims": claims, "text": "\n\n".join(item["text"] for item in claims), "rejected": rejected}
