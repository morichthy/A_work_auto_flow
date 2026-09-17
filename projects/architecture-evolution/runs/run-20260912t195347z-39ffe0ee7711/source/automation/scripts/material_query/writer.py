"""材料维护的受限写适配：复用原 CAS/幂等事务，读取和来源哈希继续计量。

写事务不能复用查询的 HEAD 缓存。快照使用当前完整 manifest 与按需记录映射，
既保留未修改 record_heads，又不为更新一个材料加载同 owner 的所有正文。
索引补偿在规范提交之后独立执行；本适配不隐式开启无预算索引/模型任务。
"""
from collections.abc import Mapping
from copy import deepcopy
import json
from types import SimpleNamespace

from memory import index
from memory.contracts import canonical_hash
from memory.evidence_adapter import EvidenceAdapter
from memory.errors import MemoryError
from memory.service import MemoryService

from .evidence import Evidence
from .legacy_adapter import fixed_record, from_legacy
from .reader import MeteredStore, Reader
from .validation import QueryError


class _Records(Mapping):
    """完整 ID 集合来自已核验清单；具体正文只在现有事务真正需要时加载。"""
    def __init__(self, store, owner, manifest):
        self.store, self.owner, self.entries = store, owner, (manifest or {}).get("record_heads", {})

    def __len__(self):
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def __getitem__(self, rid):
        entry = self.entries[rid]
        if rid in self.store.reader.excluded_ids:
            raise QueryError("DENIED", "维护读取被显式排除")
        self.store.reader.owner(self.owner["owner_id"])
        value = self.store._record(self.owner, rid, entry)
        if value["sensitivity"] == "restricted":
            raise QueryError("DENIED", "规范记录当前不可读")
        return value


class FreshMeteredStore(MeteredStore):
    """每次 HEAD/锁/规范重读均计费；禁止缓存跨预检和锁内事务检查。"""
    def __init__(self, root, ledger, reader):
        super().__init__(root, ledger)
        self.reader = reader
        self.cleanup_reserve = 0

    def read_json(self, path):
        self.read_cache.clear()
        return super().read_json(path)

    def read_snapshot(self, owner):
        self.reader.owner(owner["owner_id"])
        head, manifest = self.head_manifest(owner)
        return {"head": head, "manifest": manifest, "records": _Records(self, owner, manifest)}

    def commit_batch(self, *args, **kwargs):
        # 必须在获取写锁之前为“核对并释放自己的锁”留出空间。预留不计作
        # 已消费字节，只有实际清理读取才扣账；未使用的额度仍属于该查询。
        reserve = 4096
        with self.ledger.lock:
            original = self.ledger.limits["read_bytes"]
            if self.ledger.remaining("read_bytes") < reserve:
                raise QueryError("BUDGET", "剩余读取预算不足以安全开启写事务")
            self.ledger.limits["read_bytes"] = original - reserve
            self.cleanup_reserve = reserve
        try:
            return super().commit_batch(*args, **kwargs)
        finally:
            with self.ledger.lock:
                self.ledger.limits["read_bytes"] = original
                self.cleanup_reserve = 0

    def read_lock_for_cleanup(self, path):
        # 清理不执行用户内容/模型。取消之后仍须释放本进程自己的锁，不能
        # 再调用会因取消或业务预算耗尽而失败的普通 checkpoint。
        size = path.stat().st_size
        with self.ledger.lock:
            allowed = self.ledger.limits["read_bytes"] + self.cleanup_reserve
            if not self.cleanup_reserve or size > self.cleanup_reserve or self.ledger.used["read_bytes"] + size > allowed:
                raise MemoryError("LOCKED", "清理锁无法在预留额度内核验")
            self.ledger.used["read_bytes"] += size
        try:
            with path.open("rb") as stream:
                value = stream.read(size)
            if len(value) != size or path.stat().st_size != size:
                raise MemoryError("LOCKED", "锁在清理读取期间变化")
            return json.loads(value.decode("utf-8-sig"))
        except (ValueError, UnicodeError) as exc:
            raise MemoryError("LOCKED", "清理锁内容不可解析") from exc


class _ReviewAdapter(EvidenceAdapter):
    """仅复用旧复核草案和规则；不调用其全库构造或 legacy EvidenceGraph。"""
    def __init__(self, service):
        self.service, self.root, self.reader = service, service.root, service.reader
        self.local = Evidence(self.reader)
        self.records, self.claims, self.reviews = self.local.records, self.local.claims, self.local.reviews
        self.owner_views, self.source_heads, self.basis_checks = {}, {}, []
        self.legacy = SimpleNamespace(nodes={})

    def resolve_claim(self, claim_id):
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise QueryError("VALIDATION", "复核结论身份必须为非空字符串")
        if claim_id not in self.claims:
            # 初始 claim 身份读取不依赖 review 水位，才能让已提交、索引仍
            # pending 的同 request_id 先走旧事务的权威幂等回执分支。
            db = index.connect(self.root, create=False)
            if db is None:
                raise QueryError("SOURCE_MISSING", "复核结论定位索引不可用")
            try:
                row = db.execute("SELECT owner_id,record_id FROM memory_records WHERE canonical_id=? AND entity_kind='claim'", (claim_id,)).fetchone()
            finally:
                db.close()
            if row is None:
                raise QueryError("UNSUPPORTED", "受限维护复核仅支持已索引规范claim")
            self.reader.owner(row["owner_id"])
            record = self.reader.current_record(row["record_id"])
            self.records[record["record_id"]] = record
            for claim in record["payload"].get("claims", []):
                self.claims[claim["claim_id"]] = (claim, record)
        if claim_id not in self.claims:
            raise QueryError("STALE", "复核结论不在当前规范容器中")
        claim, record = self.claims[claim_id]
        self.owner_views[record["owner_id"]] = self.reader.owner(record["owner_id"])
        return {"sha256": canonical_hash(claim), "claim": deepcopy(claim), "record": deepcopy(record),
                "owner_id": record["owner_id"], "sensitivity": record["sensitivity"]}

    def _capture_basis(self):
        self.basis_checks = []
        for oid in self.reader.heads:
            owner = self.reader.owner(oid)
            head, _ = self.reader.store.head_manifest(owner)
            if (head["commit_id"] if head else None) != self.reader.heads[oid]:
                raise QueryError("STALE", "局部复核依据在准备期间变化")
            self.source_heads[oid] = head
            self.basis_checks.append({"kind": "head", "owner_id": oid, "head": head})
        for ref in self.reader.fixed.values():
            if ref.kind == "file":
                from .legacy_adapter import to_legacy
                self.basis_checks.append({"kind": "file", "ref": to_legacy(ref), "hash": ref.sha256})

    def _reference(self, ref):
        value = self.local._reference(ref)
        self._capture_basis()
        return value

    def _analyze(self, target, scope=None, *, allow_decision=False):
        return self.local._analyze(target, scope)

    def prepare_review(self, request):
        self.resolve_claim(request.get("target_claim_id"))
        # 真正的新复核/撤回必须证实当前 review 没有被索引遗漏。
        self.local._claim(request["target_claim_id"])
        self._capture_basis()
        result = super().prepare_review(request)
        self._capture_basis()
        result["basis_checks"] = deepcopy(self.basis_checks)
        return result


class Writer(MemoryService):
    """只替换读取/定位端口；commit/review/锁/回执均沿用原公开事务。"""
    def __init__(self, root, ledger, *, access_owner_ids=None, excluded_ids=(), source_ids=None):
        super().__init__(root)
        self.ledger, self.source_ids = ledger, None if source_ids is None else set(source_ids)
        self.reader = Reader(root, ledger, access_owner_ids=access_owner_ids, excluded_ids=excluded_ids)
        self.store = FreshMeteredStore(root, ledger, self.reader)
        self.reader.store = self.store
        self.reader.service = self

    def _read_bytes(self, path):
        size = path.stat().st_size
        self.ledger.charge("read_bytes", size)
        with path.open("rb") as stream:
            value = stream.read(size)
        if len(value) != size or path.stat().st_size != size:
            raise QueryError("STALE", "来源在维护读取期间发生变化")
        self.ledger.checkpoint()
        return value

    def _file(self, ref):
        target = ref["target_id"]
        if target in self.reader.excluded_ids or self.source_ids is not None and target not in self.source_ids:
            raise QueryError("DENIED", "维护来源不在保存的授权范围内")
        return super()._file(ref)

    def _evidence_adapter(self):
        return _ReviewAdapter(self)

    def _resolve_ref(self, ref, pending, source_checks):
        kind, target = ref["target_kind"], ref["target_id"]
        if kind == "record":
            if target in pending and pending[target]["revision"] == ref["revision"]:
                return super()._resolve_ref(ref, pending, source_checks)
            owner = self.reader.locate(target)
            current = self.store.read_record(owner, target)
            if current["sensitivity"] == "restricted":
                raise QueryError("DENIED", "来源当前不可读")
            record = self.store.read_record(owner, target, ref["revision"])
            if ref.get("sha256") and record["record_hash"] != ref["sha256"]:
                raise QueryError("STALE", "维护来源固定指纹不匹配")
            self.reader.record(fixed_record(record))
            head, _ = self.store.head_manifest(owner)
            source_checks.append({"kind": "head", "owner_id": owner["owner_id"], "head": head})
            return record
        if kind == "file":
            fixed, _ = from_legacy(ref)
            self.reader.file_bytes(fixed)
            _, metadata = self._file(ref)
            source_checks.append({"kind": "file", "ref": deepcopy(ref), "hash": fixed.sha256})
            return {"sha256": fixed.sha256, "sensitivity": metadata.get("sensitivity", "internal")}
        if kind == "claim":
            value = self._evidence_adapter().resolve_claim(target)
            if value["sha256"] != ref.get("sha256"):
                raise QueryError("STALE", "维护结论指纹不匹配")
            source_checks.append({"kind": "ref", "ref": deepcopy(ref), "hash": value["sha256"]})
            return value
        raise QueryError("UNSUPPORTED", "受限维护写入暂不支持旧owner/Run引用")

    def _indexed_receipt(self, receipt, *, sync):
        # HEAD 已发布。索引重建可能调用向量模型，不能在这里静默绕过同一
        # 账本；保留真实保存身份和 pending，由显式补偿入口继续派生任务。
        value = deepcopy(receipt)
        value.update(index_status="pending", index_details={"fts": "pending", "vector": "pending"},
                     error={"code": "INDEX_PENDING", "message": "规范内容已保存；待显式索引补偿"},
                     warnings=["运行memory reconcile补偿派生索引；不要重复规范写入"])
        return value
