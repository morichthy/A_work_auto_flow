"""在已定位的原生 Run 中核验旧结论，不构造全工作区证据图。

这里只恢复读取兼容性；不评估旧结论为有效，也不把旧 claim 转成规范记录。
索引只提供 owner 身份，实际字段、来源权限和固定指纹都重新读取核验。
"""
import re

import evidence
import retrieval
from memory import owners

from .validation import QueryError


def claim_sources(reader, ref, owner_id):
    owner = reader.owner(owner_id)
    if owner["owner_type"] != "run":
        raise QueryError("UNSUPPORTED", "旧结论定位不是原生Run")
    native = reader.store.read_json(owners.safe_path(reader.root, owner["native_ref"]["path"]))
    if native.get("run_id") != owner_id:
        raise QueryError("STALE", "原生结论归属身份已变化")
    claims = [c for c in native.get("claims", []) if c.get("claim_id") == ref["target_id"]]
    if len(claims) != 1:
        raise QueryError("SOURCE_MISSING", "原生结论身份不存在或重复")
    claim = claims[0]
    if any(v.get("sensitivity", "internal") == "restricted" for v in (native, claim)):
        raise QueryError("DENIED", "原生结论或归属已限制读取")
    if evidence.fingerprint(claim) != ref["sha256"]:
        raise QueryError("STALE", "原生结论固定指纹已变化")

    registry = None
    result = []
    for old in [*native.get("dependencies", []), *claim.get("evidence_refs", [])]:
        reader.ledger.checkpoint()
        if not isinstance(old, dict):
            raise QueryError("VALIDATION", "原生依据引用结构无效")
        if "target_kind" in old:
            result.append(old)
            continue
        target, sha = old.get("target") or old.get("path"), old.get("sha256")
        if not isinstance(target, str) or not re.fullmatch(r"[0-9a-f]{64}", sha or ""):
            raise QueryError("SOURCE_MISSING", "原生依据缺少固定身份或指纹")
        if target in reader.excluded_ids:
            raise QueryError("DENIED", "原生依据已排除")
        if target in reader.views:
            linked = reader.owner(target)
            actual = reader.store.read_json(owners.safe_path(reader.root, linked["native_ref"]["path"]))
            if actual.get("sensitivity") == "restricted":
                raise QueryError("DENIED", "原生依据归属已限制读取")
            if evidence.fingerprint(actual) != sha:
                raise QueryError("STALE", "原生依据指纹已变化")
            kind, identity = "owner", target
        elif target.startswith("CLM-"):
            kind, identity = "claim", target
        else:
            # Match only registered identities/paths. This never opens a path
            # supplied by prose or discovers new filesystem sources.
            if registry is None:
                registry = reader.store.read_json(owners.safe_path(reader.root, "retrieval/sources.json"))
            matches = []
            for item in registry.get("sources", []):
                registered = item.get("source_id") or item.get("id") or retrieval.source_id((reader.root / item["path"]).resolve())
                if target == registered or target.replace("\\", "/") == item["path"].replace("\\", "/"):
                    matches.append(registered)
            if len(matches) != 1:
                raise QueryError("SOURCE_MISSING", "原生依据未唯一登记，不能扩大读取范围")
            kind, identity = "file", matches[0]
        result.append({"target_kind": kind, "target_id": identity, "revision": None,
                       "sha256": sha, "locator": "", "relation": old.get("relation", "references")})
    return result
