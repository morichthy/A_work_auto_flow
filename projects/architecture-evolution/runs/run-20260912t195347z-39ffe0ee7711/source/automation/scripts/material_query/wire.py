"""在不可变Python契约与严格JSON之间显式转换；tuple不直接传给规范哈希。"""
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from memory.contracts import canonical_hash


def json_value(value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    return value


def digest(value):
    return canonical_hash(json_value(value))


def observe_basis(value):
    """给本次局部观察固定时间和身份；筛选 refs 后重新计算，避免沿用全域身份。

    此戳描述已观察的固定引用和 owner 水位，不声称多个 owner 同时提交。
    """
    if value is None:
        return None
    value = json_value(value)
    value.pop("basis_id", None)
    value["observed_at"] = value.get("observed_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    value["basis_id"] = "BASIS-" + digest(value)
    return value
