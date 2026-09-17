"""显式转换原六字段引用；不将旧content_hash误作record_hash。

relation属于引用边而非内容身份，转换返回时单独保留；未知身份不能猜成record。
"""
from dataclasses import asdict

from .contracts import FixedRef
from .validation import QueryError, parse


def from_legacy(ref):
    if not isinstance(ref, dict):
        raise QueryError("VALIDATION", "旧引用不是对象")
    expected = {"target_kind", "target_id", "revision", "sha256", "locator", "relation"}
    if set(ref) != expected:
        raise QueryError("VALIDATION", "旧引用必须包含完整六字段")
    value = parse({"kind": ref["target_kind"], "id": ref["target_id"], "revision": ref["revision"],
                   "sha256": ref["sha256"], "locator": ref["locator"]}, FixedRef)
    return value, ref["relation"]


def to_legacy(ref, relation="references"):
    value = asdict(ref) if isinstance(ref, FixedRef) else ref
    kind = "record" if value["kind"] == "representation" else value["kind"]
    return {"target_kind": kind, "target_id": value["id"], "revision": value["revision"],
            "sha256": value["sha256"], "locator": value["locator"] or "", "relation": relation}


def fixed_record(record, locator=None):
    return FixedRef("record", record["record_id"], record["revision"], record["record_hash"], locator)


def memory_error(exc):
    """旧错误文本可能包含内部路径；对新API仅返回固定的公开原因。"""
    mapping = {"ACCESS_DENIED": "DENIED", "UNSAFE_PATH": "DENIED", "STALE_BASIS": "STALE",
               "NOT_FOUND": "SOURCE_MISSING", "UNRESOLVED_REFERENCE": "SOURCE_MISSING",
               "VERSION_CONFLICT": "CONFLICT", "IDEMPOTENCY_CONFLICT": "CONFLICT", "LOCKED": "CONFLICT",
               "INVALID_SCHEMA": "VALIDATION", "INVALID_ARGUMENT": "VALIDATION",
               "CAPABILITY_UNAVAILABLE": "UNSUPPORTED", "INDEX_PENDING": "INDEX_FAILED"}
    code = mapping.get(exc.code, "INTERNAL")
    return QueryError(code, {"DENIED": "材料不在当前可读范围", "STALE": "固定依据或索引已变化",
        "SOURCE_MISSING": "固定来源不可用", "CONFLICT": "版本或操作发生冲突", "VALIDATION": "请求不符合旧存储契约",
        "UNSUPPORTED": "当前提供器不支持该能力", "INDEX_FAILED": "索引尚未完成", "INTERNAL": "材料完整性检查失败"}[code])
