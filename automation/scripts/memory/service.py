"""草案、固定引用与存储的统一入口；前端和 CLI 不各自实现业务规则。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid

from . import contracts, owners, policy
from .errors import MemoryError
from .store import MemoryStore, utc_now


class MemoryService:
    def __init__(self, root, *, clock=utc_now, id_factory=None, fault=None):
        self.root = Path(root).resolve()
        self.store = MemoryStore(root, clock=clock, id_factory=id_factory, fault=fault)
        self.clock = clock

    def _read_bytes(self, path):
        """Read hook for bounded application adapters; defaults keep old I/O.

        An adapter can reserve byte budget before this read without replacing
        transaction/CAS logic or monkey-patching global Path methods.
        """
        return path.read_bytes()

    def _evidence_adapter(self):
        """Allow a bounded application to supply the same evidence contract.

        The default adapter and review transaction stay unchanged. A specialized
        writer can localize evidence reads without copying trusted CAS logic.
        """
        from .evidence_adapter import EvidenceAdapter
        return EvidenceAdapter(self)

    def inspect(self, owner_id, revision=None, *, record_id=None):
        owner = owners.resolve_owner(self.root, owner_id)
        if owner["native_data"].get("sensitivity") == "restricted":
            raise MemoryError("ACCESS_DENIED", "此对象不在当前可读范围")
        if record_id:
            record = self.store.read_record(owner, record_id, revision)
            if record["sensitivity"] == "restricted":
                raise MemoryError("ACCESS_DENIED", "此记录不在当前可读范围")
            from .evidence_adapter import EvidenceAdapter
            denied = [item for item in EvidenceAdapter(self).access_errors(record_id, revision=record["revision"]) if item["code"] in {"ACCESS_DENIED", "UNSAFE_PATH"}]
            if denied:
                raise MemoryError("ACCESS_DENIED", "此记录的来源授权已变化", errors=denied)
            return {"owner": owner, "record": record}
        snapshot = self.store.read_snapshot(owner)
        from . import index
        state = index.status(self.root, owner_id)
        snapshot["records"] = {rid:r for rid,r in snapshot["records"].items() if r["sensitivity"] != "restricted"}
        from .evidence_adapter import EvidenceAdapter
        adapter = EvidenceAdapter(self)
        omitted = []
        for rid in list(snapshot["records"]):
            if any(item["code"] in {"ACCESS_DENIED", "UNSAFE_PATH"} for item in adapter.access_errors(rid)):
                snapshot["records"].pop(rid)
                omitted.append({"record_id": rid, "code": "ACCESS_DENIED"})
        claim_ids = [claim["claim_id"] for record in snapshot["records"].values() for claim in record["payload"].get("claims", [])]
        claim_states = {}
        if claim_ids:
            claim_states = {cid: adapter.claim_state(cid) for cid in claim_ids}
        return {"owner": owner, **snapshot, "policy": self._policy(owner, snapshot),
                **state, "claim_states": claim_states, "omitted": omitted, "warnings": []}

    def _policy(self, owner, snapshot):
        pointer = (snapshot["manifest"] or {}).get("pointers", {}).get("policy")
        selected = snapshot["records"].get(pointer["record_id"]) if pointer else None
        return policy.resolve(owner, owner_policy=selected["payload"] if selected else {})

    def _request(self, request, *, allow_review=False):
        result = contracts.validate_request(request, allow_review=allow_review)
        if not result["valid"]:
            raise MemoryError("INVALID_SCHEMA", "提交请求不符合契约", errors=result["errors"])
        # Request IDs become filenames and retry identities. Production callers
        # cannot inject record IDs, revisions or persisted authorship fields.
        try:
            uuid.UUID(request["request_id"])
        except (ValueError, TypeError, AttributeError) as exc:
            raise MemoryError("INVALID_ARGUMENT", "request_id 必须为 UUID") from exc
        return deepcopy(request)

    @staticmethod
    def request_hash(request):
        return contracts.canonical_hash({k: v for k, v in request.items() if k not in {"request_id", "dry_run"}})

    def _file(self, ref):
        """Only an enabled registry ID can select a file; text never grants access.

        Existing registries may omit source_id; their established retrieval ID
        remains usable. Explicit IDs are preserved for imported source cards.
        """
        registry_path = owners.safe_path(self.root, "retrieval/sources.json")
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise MemoryError("UNRESOLVED_REFERENCE", "来源登记不可用") from exc
        import retrieval
        matches = []
        for item in registry.get("sources", []):
            raw = self.root / item["path"]
            identity = item.get("source_id") or item.get("id") or retrieval.source_id(raw.resolve())
            if identity == ref["target_id"]:
                matches.append((item, raw))
        if len(matches) != 1:
            raise MemoryError("UNRESOLVED_REFERENCE", "来源 ID 不存在或重复", {"target_id": ref["target_id"]})
        item, raw = matches[0]
        if not item.get("enabled", True) or item.get("sensitivity") == "restricted":
            raise MemoryError("ACCESS_DENIED", "来源未启用或不允许当前 AI 读取")
        # Registered external originals remain read-only. Refuse redirection even
        # for an enabled registry entry, rather than following a junction later.
        absolute = Path(raw.absolute())
        if absolute.resolve() != absolute or any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in [absolute, *absolute.parents]):
            raise MemoryError("UNSAFE_PATH", "来源含符号链接或联接")
        if not absolute.is_file():
            raise MemoryError("UNRESOLVED_REFERENCE", "已登记来源不存在", {"target_id": ref["target_id"]})
        return absolute, item

    def _resolve_ref(self, ref, pending, source_checks):
        target = ref["target_id"]
        if ref["target_kind"] == "record":
            if target in pending and pending[target]["revision"] == ref["revision"]:
                value = pending[target]
                if ref.get('sha256') is not None and 'record_hash' not in value:
                    raise MemoryError('INVALID_SCHEMA', '带 SHA 的固定引用必须先保存目标并回读 record_hash，不能引用尚未完成的批次草案')
                # New batch references obey the same optional full-record hash
                # check as committed references; client keys cannot bypass it.
                if ref.get("sha256") is not None and ref["sha256"] != value["record_hash"]:
                    raise MemoryError("STALE_BASIS", "批次记录固定版本与附加指纹不一致", {"target_id": target})
                return value
            # A revision can cite its own committed predecessor (goal evolution).
            # Only the new revision is resolved from the batch; historical refs
            # must still pass the immutable store lookup below.
            matches = []
            for owner in owners.list_owners(self.root):
                snapshot = self.store.read_snapshot(owner)
                if target in snapshot["records"]:
                    matches.append((owner, snapshot))
            if len(matches) != 1:
                raise MemoryError("UNRESOLVED_REFERENCE", "记录引用不存在或身份重复", {"target_id": target})
            owner, snapshot = matches[0]
            owners.require_readable_owner(owner)
            if snapshot['records'][target]['sensitivity'] == 'restricted':
                raise MemoryError('ACCESS_DENIED', '引用记录当前已限制访问')
            value = self.store.read_record(owner, target, ref["revision"])
            if value['sensitivity'] == 'restricted':
                raise MemoryError('ACCESS_DENIED', '固定引用修订已限制访问')
            if ref.get("sha256") is not None and ref["sha256"] != value["record_hash"]:
                raise MemoryError("STALE_BASIS", "记录固定版本与附加指纹不一致", {"target_id": target})
            source_checks.append({"kind": "head", "owner_id": owner["owner_id"], "head": snapshot["head"]})
            return value
        if ref["target_kind"] == "file":
            path, metadata = self._file(ref)
            actual = hashlib.sha256(self._read_bytes(path)).hexdigest()
            source_checks.append({"kind": "file", "ref": deepcopy(ref), "hash": actual})
            value = {"sha256": actual, "sensitivity": metadata.get("sensitivity", "internal")}
        elif ref["target_kind"] == "owner":
            owner = owners.resolve_owner(self.root, target)
            sensitivity = owner["native_data"].get("sensitivity", "internal")
            if sensitivity == "restricted":
                raise MemoryError("ACCESS_DENIED", "归属来源不允许当前 AI 使用")
            import evidence
            # Preserve the old evidence fingerprint algorithm instead of hashing
            # a new memory descriptor and silently invalidating prior reviews.
            graph = evidence.EvidenceGraph(self.root)
            node = graph.nodes.get(target)
            actual = node["fingerprint"] if node else owner["fingerprint"]
            value = {"sha256": actual, "owner": owner, "sensitivity": sensitivity}
            source_checks.append({"kind": "ref", "ref": deepcopy(ref), "hash": actual})
        elif ref["target_kind"] == "claim":
            from .evidence_adapter import EvidenceAdapter
            value = self._evidence_adapter().resolve_claim(target)
            if value["sha256"] != ref["sha256"]:
                raise MemoryError("STALE_BASIS", "结论指纹已变化", {"target_id": target})
            source_checks.append({"kind": "ref", "ref": deepcopy(ref), "hash": value["sha256"]})
            return value
        else:
            raise MemoryError("INVALID_SCHEMA", "未知引用类型")
        if value["sha256"] != ref["sha256"]:
            raise MemoryError("STALE_BASIS", "引用指纹与当前可取得版本不同", {"target_id": target})
        return value

    def _prepare(self, request, snapshot, *, allow_review=False):
        owner_id = request["owner_id"]
        operations = request["operations"]
        current_owner = owners.require_readable_owner(owners.resolve_owner(self.root, owner_id))
        effective = self._policy(current_owner, snapshot)
        now = self.clock()
        mapping, pending, ids = {}, {}, set()
        # Permission is a live prepublication condition even for a draft with
        # only a provenance gap and no source refs to trigger another check.
        source_checks, resolved_refs = [{"kind": "owner_access", "owner_id": owner_id}], {}
        def resolve_ref(ref):
            # Cache only within this immutable prepare pass. A new lock-time
            # prepare starts fresh, and prepublish rechecks each unique basis.
            key = contracts.canonical_hash(ref)
            if key not in resolved_refs:
                resolved_refs[key] = self._resolve_ref(ref, pending, source_checks)
            return resolved_refs[key]
        for operation in operations:
            if "record_id" in operation:
                rid = operation["record_id"]
                old = snapshot["records"].get(rid)
                if not old:
                    raise MemoryError("NOT_FOUND", "要修订的记录不属于此对象", {"record_id": rid})
                if old["revision"] != operation["expected_revision"]:
                    raise MemoryError("VERSION_CONFLICT", "记录修订已经变化", {"record_id": rid, "current_revision": old["revision"]})
            else:
                key = operation["client_key"]
                if key in mapping:
                    raise MemoryError("INVALID_SCHEMA", "单批 client_key 重复")
                # A UUID namespace tied to the request makes dry-run predictions
                # stable without writing a ledger or permitting caller-chosen IDs.
                rid = "MEM-" + str(uuid.uuid5(uuid.UUID(request["request_id"]), owner_id + ":" + key))
                mapping[key] = rid
            if rid in ids:
                raise MemoryError("INVALID_SCHEMA", "单批记录 ID 重复")
            ids.add(rid)
        resolved_operations = []

        def replace_refs(value):
            if isinstance(value, list):
                return [replace_refs(v) for v in value]
            if not isinstance(value, dict):
                return value
            if "client_key" in value:
                if value["client_key"] not in mapping:
                    raise MemoryError("UNRESOLVED_REFERENCE", "未知批次临时引用", {"client_key": value["client_key"]})
                extra = set(value) - {"client_key", "target_kind", "revision", "sha256", "locator", "relation"}
                if extra:
                    raise MemoryError("INVALID_SCHEMA", "临时引用含未知属性")
                return {"target_kind": "record", "target_id": mapping[value["client_key"]],
                        "revision": 1, "sha256": None, "locator": value.get("locator", ""), "relation": value.get("relation", "references")}
            return {k: replace_refs(v) for k, v in value.items()}

        for operation in operations:
            rid = operation.get("record_id") or mapping[operation["client_key"]]
            draft = replace_refs(deepcopy(operation["draft"]))
            draft.setdefault("discovery", effective["values"]["discovery"])
            if draft.get("owner_id") != owner_id:
                raise MemoryError("INVALID_SCHEMA", "单批只允许一个规范归属", errors=[{"path": "/owner_id", "message": "归属不匹配"}])
            old = snapshot["records"].get(rid)
            if old and draft.get("kind") != old["kind"]:
                # 层级收敛只允许作者提交完整的新正文，并固定引用上一修订。
                # 保持身份不变让当前索引替换旧类型；不可变旧修订仍供历史引用。
                # 不能将这个入口扩大成任意类型改名，也不能在读取时自动迁移。
                transition = (old["kind"], draft.get("kind"))
                predecessor = any(
                    ref.get("target_kind") == "record"
                    and ref.get("target_id") == rid
                    and ref.get("revision") == old["revision"]
                    and ref.get("sha256") == old["record_hash"]
                    and ref.get("relation") == "references"
                    for ref in draft.get("sources", []) if isinstance(ref, dict)
                )
                if (transition not in {("event", "narrative"), ("map", "overview")}
                        or draft.get("schema_version") != 4 or not predecessor
                        or not str(draft.get("body_markdown", "")).strip()
                        or not str(draft.get("change_reason", "")).strip()):
                    raise MemoryError("INVALID_SCHEMA", "类别迁移仅允许事件→研究经过、地图→整体概览；须提交 v4 正文、变更原因及上一修订的固定来源")
            pending[rid] = {**draft, "record_id": rid, "revision": old["revision"] + 1 if old else 1}
            resolved_operations.append((operation, rid, draft, old))

        def read_source(ref):
            path, _metadata = self._file(ref)
            raw = self._read_bytes(path)
            if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
                raise MemoryError("STALE_BASIS", "逐字来源读取时发生变化")
            return raw.decode("utf-8-sig")

        changed, results = [], []
        for operation, rid, draft, old in resolved_operations:
            context = {"allow_review": allow_review, "read_source": read_source,
                       "resolve_ref": resolve_ref}
            validated = contracts.validate_record(draft, context)
            if not validated["valid"]:
                errors = validated["errors"]
                raise MemoryError(errors[0].get("code", "INVALID_SCHEMA"), "记忆草案验证失败", errors=errors)
            record = validated["record"]
            from .research import validate_change
            validate_change(old, record, record_id=rid,
                            resolve_ref=resolve_ref)
            replacement = record["payload"].get("replacement_ref")
            if record["kind"] in {"question", "route"} and replacement:
                if replacement["target_id"] == rid:
                    raise MemoryError("INVALID_TRANSITION", "问题或路线不能替代自身")
                target = resolve_ref(replacement)
                if target.get("kind") != record["kind"]:
                    raise MemoryError("INVALID_TRANSITION", "替代目标必须是相同类别的问题或路线")
            # Independently resolve every typed reference: schema validation only
            # proves shape, not that the promised target exists or is accessible.
            def visit(value):
                if isinstance(value, dict):
                    if "target_kind" in value and "target_id" in value:
                        resolved = resolve_ref(value)
                        ranks = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
                        if ranks.get(resolved.get("sensitivity", "internal"), 3) > ranks[record["sensitivity"]]:
                            raise MemoryError("ACCESS_DENIED", "不能降低来源的敏感级别")
                    else:
                        for key, child in value.items():
                            if key != "missing_refs":
                                visit(child)
                elif isinstance(value, list):
                    for child in value:
                        visit(child)
            visit(record)
            digest = contracts.content_hash(record)
            if old and digest == old["content_hash"]:
                record = old
                status = "no_change"
            else:
                # Validation selected the record's schema version. The commit
                # envelope remains independently versioned; never force v2
                # detail or revised prose into a v1 record after validation.
                record.update(record_id=rid, revision=old["revision"] + 1 if old else 1,
                              previous_revision=old["revision"] if old else None, content_hash=digest,
                              created_at=old["created_at"] if old else now,
                              created_by=old["created_by"] if old else request["actor"],
                              updated_at=now, updated_by=request["actor"])
                record["change_reason"] = record.get("change_reason") or record["record_reason"]
                record["record_hash"] = contracts.canonical_hash({k: v for k, v in record.items() if k != "record_hash"})
                changed.append(record)
                status = "would_update" if old else "would_create"
            pending[rid] = record
            results.append({"client_key": operation.get("client_key"), "record_id": rid,
                            "revision": record["revision"], "content_hash": record["content_hash"], "status": status})
        # Reject circular self-support within the batch, while navigation cycles
        # remain legal and will be bounded by later graph traversal services.
        edges = {rid: set() for rid in pending}
        def support_refs(value):
            if isinstance(value, dict):
                if value.get("target_kind") == "record" and value.get("relation") in {"supports", "input"}:
                    yield value["target_id"]
                else:
                    for key, child in value.items():
                        if key != "missing_refs":
                            yield from support_refs(child)
            elif isinstance(value, list):
                for child in value:
                    yield from support_refs(child)
        for rid, record in pending.items():
            edges[rid] = set(support_refs(record)) & pending.keys()
        visited, active = set(), set()
        def walk(rid):
            if rid in active:
                raise MemoryError("INVALID_SCHEMA", "supports/input 不能形成自证环")
            if rid in visited:
                return
            active.add(rid)
            for target in edges[rid]:
                walk(target)
            active.remove(rid)
            visited.add(rid)
        for rid in edges:
            walk(rid)
        return changed, results, source_checks

    def _recheck(self, checks):
        unique = {contracts.canonical_hash(check): check for check in checks}
        for check in unique.values():
            if check["kind"] == "owner_access":
                owners.require_readable_owner(owners.resolve_owner(self.root, check["owner_id"]))
            elif check["kind"] == "legacy_file":
                path = owners.safe_path(self.root, check["path"])
                if hashlib.sha256(self._read_bytes(path)).hexdigest() != check["hash"]:
                    raise MemoryError("STALE_BASIS", "旧证据复核文件在提交期间变化")
            elif check["kind"] == "head":
                current = self.store.read_snapshot(owners.resolve_owner(self.root, check["owner_id"]))["head"]
                if current != check["head"]:
                    raise MemoryError("STALE_BASIS", "引用对象在提交期间发生变化", {"owner_id": check["owner_id"]})
            else:
                self._resolve_ref(check["ref"], {}, [])

    def validate_draft(self, request):
        request = self._request(request)
        owner = owners.resolve_owner(self.root, request["owner_id"])
        owners.require_readable_owner(owner)
        snapshot = self.store.read_snapshot(owner)
        current = snapshot["head"]["commit_id"] if snapshot["head"] else None
        if current != request["expected_head"]:
            raise MemoryError("VERSION_CONFLICT", "预检依据 HEAD 已变化", {"current_head": snapshot["head"]})
        _changed, results, checks = self._prepare(request, snapshot)
        self._recheck(checks)
        return {"valid": True, "errors": [], "dry_run": True, "owner_id": owner["owner_id"],
                "head": snapshot["head"], "record_results": results, "writes": 0}

    def commit(self, request):
        return self._commit(request)

    def _commit(self, request, *, request_hash=None, basis_heads=None):
        """Internal operation builders may bind retries to their public request.

        Their derived update operation can change after the first successful
        commit; hashing that derived operation would falsely reject a retry.
        Public callers cannot override this hash through request JSON.
        """
        request = self._request(request)
        owner = owners.resolve_owner(self.root, request["owner_id"])
        owners.require_readable_owner(owner)
        if request.get("dry_run", False):
            self._basis_checks(basis_heads or {})
            return self.validate_draft(request)
        request_hash = request_hash or self.request_hash(request)
        snapshot = self.store.read_snapshot(owner)
        prior = self.store._receipt(owner, snapshot, request["request_id"], request_hash)
        if prior:
            return self._indexed_receipt(prior, sync=False)
        self._basis_checks(basis_heads or {})
        # Invalid input must not create owner directories. Repeat under the lock
        # after this read-only pass to close the optimistic concurrency window.
        self.validate_draft(request)
        checks = []
        def prepare(current):
            changed, results, sources = self._prepare(request, current)
            checks[:] = sources + self._basis_checks(basis_heads or {})
            return changed, results
        receipt = self.store.commit_batch(owner, request["expected_head"], request["request_id"], request["operations"],
                                       actor=request["actor"], request_hash=request_hash, prepare=prepare,
                                       prepublish=lambda: self._recheck(checks), source_checks=lambda: deepcopy(checks))
        return self._indexed_receipt(receipt, sync=receipt["save_status"] == "committed")

    def _indexed_receipt(self, receipt, *, sync):
        """索引失败不撤销已提交记录；状态派生读取不改不可变事务回执。"""
        from . import index
        result = deepcopy(receipt)
        try:
            if sync:
                # Canonical publication invalidates the independent compressed
                # discovery projection before any other derived sync can fail.
                # Repair uses rebuild-discovery against this exact HEAD and
                # never repeats the already-published business commit.
                from . import discovery
                owner = owners.resolve_owner(self.root, result["owner_id"])
                head = self.store.read_snapshot(owner)["head"]
                discovery.mark_pending(self.root, result["owner_id"], head)
                index.sync_owner(self.root, result["owner_id"], result.get("generation"))
            state = index.status(self.root, result["owner_id"])
            result.update(index_status=state["index_status"], index_details=state["index_details"])
            if state["index_status"] == "indexed":
                result.update(error=None, warnings=[])
            else:
                result.update(error={"code": "INDEX_PENDING", "message": "记录已保存；索引待补偿"},
                              warnings=["运行 memory reconcile 可继续索引，不要重复业务记录"])
        except Exception as exc:
            # This boundary runs strictly after HEAD publication. Even a backend
            # exception must return the successful business identity for retry.
            result.update(index_status="pending", index_details={"reason": str(exc)},
                          error={"code": "INDEX_PENDING", "message": "记录已保存；索引同步失败"})
        return result

    def _basis_checks(self, basis_heads):
        """固定材料包水位必须再次回源；不能借旧草案覆盖新的研究结果。"""
        checks, changed = [], []
        for owner_id, expected in basis_heads.items():
            head = self.store.read_snapshot(owners.resolve_owner(self.root, owner_id))["head"]
            actual = head["commit_id"] if head else "none"
            if actual != expected:
                changed.append({"owner_id": owner_id, "expected": expected, "actual": actual})
            checks.append({"kind": "head", "owner_id": owner_id, "head": head})
        if changed:
            raise MemoryError("STALE_BASIS", "材料包依据对象已变化", {"changed_owners": changed})
        return checks

    def review(self, request):
        """专用复核事务：可信草案只由证据门生成，且在锁内重验依据。

        幂等键绑定原始复核请求。重放先于动态证据检查，避免已经成功的
        复核在后来来源变化时被误当作尚未执行；当前有效性另行回源计算。
        """
        from .evidence_adapter import EvidenceAdapter
        request = deepcopy(request)
        if not isinstance(request, dict):
            raise MemoryError("INVALID_ARGUMENT", "复核请求必须是对象")
        try:
            uuid.UUID(request.get("request_id", ""))
        except (ValueError, TypeError, AttributeError) as exc:
            raise MemoryError("INVALID_ARGUMENT", "复核 request_id 必须为 UUID") from exc
        errors = contracts.validate_schema(request.get("actor"), contracts.SCHEMA["$defs"]["Actor"], contracts.SCHEMA["$defs"])
        if errors:
            raise MemoryError("INVALID_SCHEMA", "复核执行者不符合契约", errors=errors)
        adapter = self._evidence_adapter()
        value = adapter.resolve_claim(request.get("target_claim_id"))
        if value.get("legacy"):
            adapter.prepare_review(request)  # Validate the public field allowlist.
            import evidence
            return evidence.review_claim(self.root, request["target_claim_id"], request["state"],
                request["actor"]["id"], request["reason"],
                evidence=json.dumps(request.get("evidence_refs", []), ensure_ascii=False),
                scope=request.get("scope") or "", replacement=request.get("replacement_claim_id") or "",
                dry_run=request.get("dry_run", False))
        owner = owners.resolve_owner(self.root, value["owner_id"])
        owners.require_readable_owner(owner)
        digest = contracts.canonical_hash({"operation": "review", "request": {
            k: v for k, v in request.items() if k not in {"request_id", "dry_run"}}})
        snapshot = self.store.read_snapshot(owner)
        if not request.get("dry_run", False):
            prior = self.store._receipt(owner, snapshot, request["request_id"], digest)
            if prior:
                return self._indexed_receipt(prior, sync=False)
        checks = []
        def prepare(current):
            prepared = self._evidence_adapter().prepare_review(request)
            operation = {"op": "put_record", "draft": prepared["draft"]}
            if prepared["record_id"]:
                operation.update(record_id=prepared["record_id"], expected_revision=prepared["expected_revision"])
            else:
                operation["client_key"] = "review"
            internal = self._request({"schema_version": request.get("schema_version", 1),
                "request_id": request["request_id"], "actor": request["actor"], "owner_id": owner["owner_id"],
                "expected_head": request["expected_head"], "operations": [operation], "dry_run": False}, allow_review=True)
            changed, results, sources = self._prepare(internal, current, allow_review=True)
            checks[:] = sources + prepared["basis_checks"]
            return changed, results
        current_head = snapshot["head"]["commit_id"] if snapshot["head"] else None
        if current_head != request["expected_head"]:
            raise MemoryError("VERSION_CONFLICT", "复核依据 HEAD 已变化", {"current_head": snapshot["head"]})
        _changed, results = prepare(snapshot)
        self._recheck(checks)
        if request.get("dry_run", False):
            return {"valid": True, "dry_run": True, "record_results": results, "writes": 0}
        receipt = self.store.commit_batch(owner, request["expected_head"], request["request_id"], [],
            actor=request["actor"], request_hash=digest, prepare=prepare,
            prepublish=lambda: self._recheck(checks), source_checks=lambda: deepcopy(checks))
        return self._indexed_receipt(receipt, sync=receipt["save_status"] == "committed")
