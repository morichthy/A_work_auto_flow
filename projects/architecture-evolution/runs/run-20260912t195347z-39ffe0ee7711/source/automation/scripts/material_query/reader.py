"""有计量的固定读取适配器，不先read_snapshot加载整个owner正文。

复用MemoryStore的manifest链/记录哈希检查，仅替换read_json为预算读取。
索引只定位候选身份，HEAD和规范字节仍是权威；旧版读取先核对当前权限。
"""
from collections import deque
from dataclasses import asdict
import hashlib
import json

from memory import index, owners
from memory.contracts import canonical_hash
from memory.errors import MemoryError
from memory.evidence_adapter import iter_refs
from memory.service import MemoryService
from memory.store import MemoryStore

from .contracts import FixedRef
from .legacy_adapter import fixed_record, memory_error, to_legacy
from .validation import QueryError
from .wire import observe_basis


class MeteredStore(MemoryStore):
    """每次应用操作新建缓存；不让跨HTTP缓存代替重新授权。"""
    def __init__(self, root, ledger):
        super().__init__(root)
        self.ledger = ledger
        self.read_cache = {}

    def read_json(self, path):
        path = path.absolute()
        # HEAD, lock and receipt pointers can change between preflight and the
        # write lock. Only immutable commit payloads may survive a second read;
        # caching HEAD would weaken the original store's CAS guarantee.
        immutable = "commits" in path.parts
        if immutable and path in self.read_cache:
            self.ledger.checkpoint()
            return self.read_cache[path]
        try:
            size = path.stat().st_size
            self.ledger.charge("read_bytes", size)
            with path.open("rb") as stream:
                raw = stream.read(size)
            if len(raw) != size or path.stat().st_size != size:
                raise QueryError("STALE", "读取期间文件发生变化")
            value = json.loads(raw.decode("utf-8-sig"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if immutable:
                self.read_cache[path] = value
            self.ledger.checkpoint()
            return value
        except (OSError, ValueError, UnicodeError) as exc:
            raise QueryError("SOURCE_MISSING", "规范内容不可读") from exc

    def head_manifest(self, owner):
        path = self.path(owner, "HEAD.json")
        if not path.exists():
            return None, None
        head = self.read_json(path)
        if not isinstance(head, dict) or set(head) != {"commit_id", "generation", "manifest_hash"}:
            raise QueryError("INTERNAL", "HEAD结构损坏")
        manifest = self._manifest(owner, head["commit_id"], head["manifest_hash"])
        if manifest["generation"] != head["generation"] or manifest["owner_id"] != owner["owner_id"]:
            raise QueryError("INTERNAL", "HEAD与清单不一致")
        return head, manifest

    def read_record(self, owner, record_id, revision=None):
        _, manifest = self.head_manifest(owner)
        seen = set()
        while manifest:
            self.ledger.checkpoint()
            cid = manifest["commit_id"]
            if cid in seen:
                raise QueryError("INTERNAL", "历史清单存在循环")
            seen.add(cid)
            entry = manifest["record_heads"].get(record_id)
            if entry and (revision is None or entry["revision"] == revision):
                return self._record(owner, record_id, entry)
            parent = manifest["parent_commit_id"]
            manifest = self._manifest(owner, parent, manifest["parent_manifest_hash"]) if parent else None
        raise QueryError("SOURCE_MISSING", "记录固定版本不存在")


class Reader:
    def __init__(self, root, ledger, *, access_owner_ids=None, excluded_ids=()):
        self.root, self.ledger = root, ledger
        self.store = MeteredStore(root, ledger)
        self.service = MemoryService(root)
        self.service.store = self.store
        self.views = {v["owner_id"]: v for v in owners.list_owners(root)}
        self.access_owner_ids = None if access_owner_ids is None else set(access_owner_ids)
        self.excluded_ids = set(excluded_ids)
        self.records, self.heads, self.fixed = {}, {}, {}
        # A trusted rebuild/list adapter may supply a bounded canonical locator
        # when the derived index is absent. HTTP input cannot configure it.
        self.claim_locator = None

    def owner(self, owner_id):
        owner = self.views.get(owner_id)
        if (owner is None or owner_id in self.excluded_ids or self.access_owner_ids is not None and owner_id not in self.access_owner_ids
                or owner["native_data"].get("sensitivity") == "restricted"):
            raise QueryError("DENIED", "对象不在当前可读范围")
        return owner

    def native(self, ref):
        """按登记身份读取 L0 卡片；原件未版本化时不假装能恢复旧字节。"""
        owner = self.owner(ref.id)
        if ref.kind != "owner" or ref.sha256 != owner["fingerprint"]:
            raise QueryError("STALE", "原始登记已有变化，无法按该固定指纹返回")
        path = owners.safe_path(self.root, owner["native_ref"]["path"])
        size = path.stat().st_size
        self.ledger.charge("read_bytes", size)
        with path.open("rb") as stream:
            raw = stream.read(size)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != ref.sha256:
            raise QueryError("STALE", "原始登记读取期间发生变化")
        text = raw.decode("utf-8-sig")
        native = json.loads(text) if path.suffix.lower() == ".json" else text
        if isinstance(native, dict):
            if native.get("sensitivity") == "restricted" or any(c.get("sensitivity") == "restricted" for c in native.get("claims", [])):
                raise QueryError("DENIED", "原始登记或其中结论限制读取")
            refs = list(iter_refs(native))
            if owner["owner_type"] == "run":
                from .native_sources import claim_sources
                import evidence
                for claim in native.get("claims", []):
                    refs.extend(claim_sources(self, {"target_id": claim["claim_id"], "sha256": evidence.fingerprint(claim)}, ref.id))
            self.authorize_sources({"record_id": ref.id, "revision": ref.sha256, "sources": refs, "payload": {}})
            text = "```json\n" + text.rstrip() + "\n```"
        self.ledger.checkpoint()
        self.fixed[(ref.id, None, ref.sha256)] = ref
        return text, native

    def locate(self, record_id):
        if record_id in self.excluded_ids:
            raise QueryError("DENIED", "材料被排除")
        db = index.connect(self.root, create=False)
        if db is not None:
            try:
                row = db.execute("SELECT DISTINCT owner_id FROM memory_records WHERE record_id=?", (record_id,)).fetchall()
                if len(row) == 1:
                    return self.owner(row[0][0])
                if len(row) > 1:
                    raise QueryError("INTERNAL", "索引身份冲突")
            finally:
                db.close()
        # 未索引的新记录允许按小型manifest定位，不遍历所有正文。
        found = []
        for oid in self.views:
            try:
                owner = self.owner(oid)
            except QueryError:
                continue
            _, manifest = self.store.head_manifest(owner)
            if manifest and record_id in manifest["record_heads"]:
                found.append(owner)
        if len(found) != 1:
            raise QueryError("SOURCE_MISSING", "材料身份不存在或不唯一")
        return found[0]

    def record(self, ref, *, check_sources=True):
        if ref.kind not in {"record", "representation"}:
            raise QueryError("UNSUPPORTED", "此读取入口仅接收记录身份")
        key = (ref.id, ref.revision, ref.sha256)
        try:
            owner = self.locate(ref.id)
            current = self.store.read_record(owner, ref.id)
            if current["sensitivity"] == "restricted":
                raise QueryError("DENIED", "记录当前已限制读取")
            record = self.store.read_record(owner, ref.id, ref.revision)
            if record["record_hash"] != ref.sha256:
                raise QueryError("STALE", "固定引用指纹不匹配")
            if record["sensitivity"] == "restricted":
                raise QueryError("DENIED", "固定修订不允许读取")
            head, _ = self.store.head_manifest(owner)
            if check_sources:
                self.authorize_sources(record)
            # Do not leave a denied candidate's identity in the public basis if
            # its source closure fails after the root record was read.
            self.heads[owner["owner_id"]] = head["commit_id"] if head else None
            self.records[key] = record
            self.fixed[key] = ref
            return record
        except MemoryError as exc:
            raise memory_error(exc) from exc

    def current_record(self, record_id):
        try:
            owner = self.locate(record_id)
            current = self.store.read_record(owner, record_id)
            return self.record(fixed_record(current))
        except MemoryError as exc:
            raise memory_error(exc) from exc

    def authorize_sources(self, initial):
        """验证固定来源闭包与当前权限；遇排除/撤权拒绝衍生正文泄漏。

        文件只做当前授权/存在检查，正文读取/哈希在file()中执行；旧来源内容
        改变不使旧记录字节消失，读取方会报告stale，正式用途另做证据准入。
        """
        queue, seen = deque([initial]), set()
        while queue:
            self.ledger.checkpoint()
            record = queue.popleft()
            key = (record["record_id"], record["revision"])
            if key in seen:
                continue
            seen.add(key)
            for legacy in iter_refs({"sources": record["sources"], "payload": record["payload"]}):
                tid = legacy["target_id"]
                if tid in self.excluded_ids:
                    raise QueryError("DENIED", "材料引用了被排除来源")
                kind = legacy["target_kind"]
                if kind == "record":
                    owner = self.locate(tid)
                    current = self.store.read_record(owner, tid)
                    pinned = self.store.read_record(owner, tid, legacy["revision"])
                    if current["sensitivity"] == "restricted" or pinned["sensitivity"] == "restricted":
                        raise QueryError("DENIED", "来源当前已限制读取")
                    if legacy.get("sha256") and legacy["sha256"] != pinned["record_hash"]:
                        raise QueryError("STALE", "来源固定指纹不匹配")
                    queue.append(pinned)
                elif kind == "file":
                    self.service._file(legacy)
                elif kind == "owner":
                    self.owner(tid)
                elif kind == "claim":
                    # 用索引只定位容器，再读取规范claim；不相信缓存的复核状态。
                    db = index.connect(self.root, create=False)
                    row = None
                    if db is not None:
                        try:
                            row = db.execute("SELECT record_id,entity_kind,owner_id FROM memory_records WHERE canonical_id=? AND entity_kind IN ('claim','legacy-claim')", (tid,)).fetchone()
                        finally:
                            db.close()
                    if row and row[1] == "legacy-claim":
                        from .native_sources import claim_sources
                        refs = claim_sources(self, legacy, row[2])
                        # Internal closure envelope only: it is never published
                        # as a memory record, candidate or invented revision.
                        queue.append({"record_id": "native-claim:" + tid, "revision": legacy["sha256"],
                                      "sources": refs, "payload": {}})
                        continue
                    if row:
                        container = self.store.read_record(self.locate(row[0]), row[0])
                    elif self.claim_locator:
                        located = self.claim_locator(tid)
                        if not located or located["record_id"] in self.excluded_ids:
                            raise QueryError("SOURCE_MISSING", "结论来源不可定位")
                        container = self.store.read_record(self.owner(located["owner_id"]), located["record_id"])
                    else:
                        raise QueryError("SOURCE_MISSING", "结论来源不可定位")
                    if container["sensitivity"] == "restricted":
                        raise QueryError("DENIED", "结论容器不可读")
                    claims = [c for c in container["payload"].get("claims", []) if c["claim_id"] == tid]
                    if len(claims) != 1 or canonical_hash(claims[0]) != legacy["sha256"]:
                        # An old review must remain readable after the statement
                        # changes. Verify the exact historical claim in this one
                        # container, while current access remains authoritative.
                        # Formal Evidence still evaluates current hashes/state.
                        historical = None
                        for revision in range(container["revision"] - 1, 0, -1):
                            self.ledger.checkpoint()
                            previous = self.store.read_record(self.owner(container["owner_id"]), container["record_id"], revision)
                            matching = [c for c in previous["payload"].get("claims", []) if c["claim_id"] == tid and canonical_hash(c) == legacy["sha256"]]
                            if len(matching) == 1:
                                if previous["sensitivity"] == "restricted":
                                    raise QueryError("DENIED", "结论历史来源不可读")
                                historical = previous
                                break
                        if historical is None:
                            raise QueryError("STALE", "结论固定指纹在当前容器历史中不存在")
                        queue.append(historical)
                    queue.append(container)

    def file_bytes(self, ref):
        """读取并校验任意已登记原件；二进制依据也受同一个字节账本约束。"""
        if ref.id in self.excluded_ids:
            raise QueryError("DENIED", "来源已排除")
        try:
            path, metadata = self.service._file(to_legacy(ref))
            size = path.stat().st_size
            self.ledger.charge("read_bytes", size)
            with path.open("rb") as stream:
                raw = stream.read(size)
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != ref.sha256:
                raise QueryError("STALE", "来源字节与固定指纹不同")
            self.ledger.checkpoint()
            self.fixed[(ref.id, ref.revision, ref.sha256)] = ref
            return raw
        except MemoryError as exc:
            raise memory_error(exc) from exc
        except OSError as exc:
            raise QueryError("SOURCE_MISSING", "原始文件不可读") from exc

    def file(self, ref):
        try:
            return self.file_bytes(ref).decode("utf-8-sig")
        except UnicodeError as exc:
            raise QueryError("UNSUPPORTED", "此原件需使用已有文档/OCR预览；不将二进制伪装文本") from exc

    def basis(self, watermarks=()):
        changed = False
        for oid, previous in self.heads.items():
            owner = self.owner(oid)
            path = self.store.path(owner, "HEAD.json")
            # Bypass per-operation cache for final concurrency observation; keep
            # it metered and preserve fixed refs if another owner moved meanwhile.
            self.store.read_cache.pop(path.absolute(), None)
            head, _ = self.store.head_manifest(owner)
            changed |= (head["commit_id"] if head else None) != previous
        return observe_basis({"refs": [asdict(ref) for ref in self.fixed.values()], "owner_heads": list(self.heads.items()),
                "index_watermarks": list(watermarks), "consistency": "cross_owner_optimistic" if len(self.heads) > 1 or changed else "fixed_refs"})
