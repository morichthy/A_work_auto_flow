"""从受控dataclass严格解析HTTP/CLI JSON；类型检查与业务检查分开。

不执行请求中的表达式，也不接受客户端Context。保持JSON的bool/int区别，
未知字段一律拒绝；范围null与空数组保持原样，不用truthiness扩大范围。
"""
from dataclasses import MISSING, fields, is_dataclass
from datetime import datetime
import math
import re
import types
from typing import get_args, get_origin, get_type_hints, Literal, Union, TypeVar

from . import contracts as c


class QueryError(Exception):
    """应用错误只包含可公开原因；不得携带未授权对象的标题或路径。"""
    def __init__(self, code, message, *, fields=(), affected_refs=(), retry=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = tuple(fields)
        self.affected_refs = tuple(affected_refs)
        self.retry = retry


def _bound(typ, bindings):
    """代入Result[T]等参数，不把输出value退化成任意未验证JSON。"""
    if isinstance(typ, TypeVar):
        return bindings.get(typ, typ)
    origin, args = get_origin(typ), get_args(typ)
    if not origin or origin is Literal:
        return typ
    replaced = tuple(_bound(arg, bindings) for arg in args)
    if origin in (Union, types.UnionType):
        return Union[replaced]
    return origin[replaced]


def parse(value, annotation, path="$"):
    """将JSON转换为不可变契约对象；失败给出字段路径，不回显敏感输入。"""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        for branch in args:
            try:
                return parse(value, branch, path)
            except QueryError:
                pass
        raise QueryError("VALIDATION", "字段类型不匹配", fields=(path,))
    if origin is Literal:
        if not any(type(value) is type(item) and value == item for item in args):
            raise QueryError("VALIDATION", "字段枚举不受支持", fields=(path,))
        return value
    if origin is tuple:
        if not isinstance(value, list):
            raise QueryError("VALIDATION", "字段必须为数组", fields=(path,))
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(parse(item, args[0], f"{path}[{i}]") for i, item in enumerate(value))
        if len(value) != len(args):
            raise QueryError("VALIDATION", "固定数组长度不正确", fields=(path,))
        return tuple(parse(item, typ, f"{path}[{i}]") for i, (item, typ) in enumerate(zip(value, args)))
    cls = origin if origin and is_dataclass(origin) else annotation
    if is_dataclass(cls):
        expected = {field.name for field in fields(cls)}
        required = {f.name for f in fields(cls) if f.default is MISSING and f.default_factory is MISSING}
        if not isinstance(value, dict) or not required <= set(value) or set(value) - expected:
            raise QueryError("VALIDATION", "对象字段缺失或包含未知字段", fields=(path,))
        bindings = dict(zip(getattr(cls, "__parameters__", ()), args))
        hints = {key: _bound(typ, bindings) for key, typ in get_type_hints(cls).items()}
        result = cls(**{key: parse(item, hints[key], path + "." + key) for key, item in value.items()})
        semantic(result, path)
        return result
    if annotation is float:
        valid = type(value) in (int, float) and math.isfinite(value)
    else:
        valid = type(value) is annotation
    if not valid:
        raise QueryError("VALIDATION", "字段类型不正确", fields=(path,))
    return value


def semantic(value, path="$"):
    """可在解析时确定的不变量；授权、版本、账本等必须在执行时再次核验。"""
    def require(condition, message):
        if not condition:
            raise QueryError("VALIDATION", message, fields=(path,))
    if isinstance(value, c.FixedRef):
        require(bool(value.id.strip()) and bool(re.fullmatch(r"[0-9a-f]{64}", value.sha256)), "固定引用需要身份和SHA256")
        require(value.revision is None or value.revision > 0, "引用修订号必须为正整数")
        require(value.kind not in {"record", "representation"} or value.revision is not None, "记录/表示引用必须指定修订号")
    elif isinstance(value, c.Budget):
        require(all(getattr(value, f.name) >= 0 for f in fields(value)), "预算不能为负数")
    elif isinstance(value, c.TimeWindow):
        dates = []
        for raw in (value.start_inclusive, value.end_exclusive):
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw is not None else None
                require(raw is None or bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", raw)), "时间必须使用RFC3339格式")
                require(dt is None or dt.tzinfo is not None, "时间必须包含时区")
                dates.append(dt)
            except ValueError:
                require(False, "时间格式不合法")
        require(not all(dates) or dates[0] < dates[1], "时间区间必须左端早于右端")
    elif isinstance(value, c.Scope):
        for key in ("owner_ids", "owner_types", "levels", "kinds", "roles", "outcomes", "review_states", "validities", "excluded_owner_ids"):
            items = getattr(value, key)
            require(items is None or all(item.strip() for item in items), "范围不能包含空白身份")
        require(value.levels is None or set(value.levels) <= {"L0", "L1", "L2", "L3", "L4", "unlayered"}, "层级不受支持")
        dates = []
        for raw in (value.recorded_from, value.recorded_before):
            if raw is None:
                dates.append(None)
                continue
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                require(bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", raw)), "时间必须使用RFC3339格式")
                require(dt.tzinfo is not None, "时间必须包含时区")
                dates.append(dt)
            except ValueError:
                require(False, "时间格式不合法")
        require(not all(dates) or dates[0] < dates[1], "时间区间必须左端早于右端")
    elif isinstance(value, c.AssociationOptions):
        require(value.max_items >= 0 and 0 <= value.output_share <= 1, "联想数量/篇幅比例不合法")
        require(bool(value.strategy.strip()) and bool(value.strategy_version.strip()), "策略及版本不能为空")
    elif isinstance(value, c.QueryRequest):
        require(value.content_source is None or (value.definition.key == "full" and value.missing_policy == "reject" and not value.fallback_definitions),
                "内容来源查询直接读取已有正文，须使用full且不回退或生成")
        require(bool(value.question.strip()) or any(item.strip() for item in value.keywords), "请填写问题或关键词")
        require(0 < value.result_limit <= 100, "结果数量须为1到100")
        require(value.purpose != "formal" or bool(value.applicability.strip()), "正式用途必须说明适用范围")
        require(value.missing_policy == "fallback" or not value.fallback_definitions, "只有显式fallback模式允许回退类型")
        require(value.missing_policy != "fallback" or bool(value.fallback_definitions), "fallback模式必须提供回退类型")
        require(bool(value.channels), "请选择至少一个召回通道")
        require(value.max_staleness_seconds is None or value.max_staleness_seconds >= 0, "索引过期容忍时间不能为负")
    elif isinstance(value, c.TreeRequest):
        require(0 < value.limit <= 100, "分页数量须为1到100")
    elif isinstance(value, (c.AssembleRequest, c.ContentExpandRequest, c.FullDocumentsRequest)):
        require(bool(value.candidate_ids), "请选择实际材料")
        require(len(set(value.candidate_ids)) == len(value.candidate_ids), "候选不能重复")


def object_fields(value, required, optional=()):
    """少量动作包装字段的严格校验；嵌套正文仍交给dataclass解析。"""
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise QueryError("VALIDATION", "动作字段缺失或包含未知字段")
    return value
