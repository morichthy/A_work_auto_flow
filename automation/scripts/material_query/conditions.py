"""固定正文中的显式字段条件核对；不负责读取、授权或推断自然语言条件。

调用者先固定回读正文，再传入 evidence_parts。本模块只输出有原文依据的
排序特征，不宣称工程适用性已复核。复杂范围、条件句、缺单位保持 unknown。
"""
from copy import deepcopy
import math
import operator as ops
import re


_OPS = {"eq": ops.eq, "ne": ops.ne, "lt": ops.lt, "le": ops.le, "gt": ops.gt, "ge": ops.ge}
_UNITS = {"°C": ("temperature", 1, 273.15), "℃": ("temperature", 1, 273.15),
          "K": ("temperature", 1, 0), "Pa": ("pressure", 1, 0),
          "kPa": ("pressure", 1000, 0), "MPa": ("pressure", 1000000, 0)}
_NUMBER = re.compile(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([^\s\d]+)?")


def validate_conditions(raw):
    """严格接收至多 16 条显式条件；不从问题中猜字段、不执行输入表达式。"""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 16:
        raise ValueError("conditions must be a list of at most 16 items")
    result, ids = [], set()
    for item in raw:
        if not isinstance(item, dict) or set(item) - {"id", "kind", "field", "expected", "operator", "unit"}:
            raise ValueError("invalid condition fields")
        out = deepcopy(item)
        for key, bound in (("id", 80), ("field", 80)):
            value = out.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > bound or any(ord(c) < 32 for c in value):
                raise ValueError("condition id and field must be bounded single-line strings")
            out[key] = value.strip()
        if out["id"] in ids:
            raise ValueError("duplicate condition id")
        ids.add(out["id"])
        if out.get("kind") not in ("literal", "numeric") or out.get("operator") not in _OPS:
            raise ValueError("unsupported condition kind or operator")
        value = out.get("expected")
        if out["kind"] == "literal":
            if out["operator"] not in ("eq", "ne") or not isinstance(value, str) or not value.strip() or len(value) > 160 or any(ord(c) < 32 for c in value) or "unit" in out:
                raise ValueError("literal conditions require bounded text and eq/ne without unit")
            out["expected"] = value.strip()
        else:
            try:
                finite = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError("numeric expected must be finite")
        if "unit" in out and (not isinstance(out["unit"], str) or not out["unit"].strip() or len(out["unit"]) > 24 or any(c.isspace() for c in out["unit"])):
            raise ValueError("unit must be a bounded token")
        result.append(out)
    return result


def _judgment(condition, value):
    """只接受完整标量；多值、范围及自然语言后缀不能降格为一个数字。"""
    expected, op = condition["expected"], condition["operator"]
    if condition["kind"] == "literal":
        neg = re.match(r"^(?:不是|不等于|非|not\s+)(.+)$", value, re.IGNORECASE)
        observed = neg.group(1).strip() if neg else value
        # 空格、连词和句子通常表示条件/多个对象，不把它们当单个型号。
        # A final English stop is normally prose, whereas dots within a token
        # are retained for version-like identifiers such as A7.2.
        if observed.endswith(".") or not re.fullmatch(r"[\w./+\-]+", observed) or re.search(r"(?:或者|以及|可能|至少|至多|仅当|如果|或|且)", observed):
            return None
        if neg:
            return (op == "ne") if observed == expected else None
        return (observed == expected) if op == "eq" else (observed != expected)
    match = _NUMBER.fullmatch(value)
    if not match:
        return None
    observed, unit = float(match.group(1)), match.group(2) or ""
    target_unit = condition.get("unit", "")
    if not math.isfinite(observed):
        return None
    if unit != target_unit:
        source, target = _UNITS.get(unit), _UNITS.get(target_unit)
        if source is None or target is None or source[0] != target[0]:
            return None
        observed = observed * source[1] + source[2]
        expected = expected * target[1] + target[2]
        if not math.isfinite(observed) or not math.isfinite(expected):
            return None
    # 浮点换算误差只在机器精度附近归零，不引入工程公差或模糊阈值。
    if math.isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-12):
        observed = expected
    return _OPS[op](observed, expected)


def evaluate_conditions(conditions, evidence_parts):
    """返回每个条件的 status、reason 与 evidence（ref、quote、role）。

    固定引用由上层验证；本函数不解析 ref、不打开路径。只在正文独立字段句
    或 Markdown 表行中绑定字段和值，title 永远不作为条件证据。
    """
    normalized = validate_conditions(conditions)
    diagnostics = []
    for condition in normalized:
        # 字段是纯数据，转义后才进入正则；限定起点避免“最低温度”匹配“温度”。
        field = re.escape(condition["field"])
        pattern = re.compile(r"^\s*(?:[-*]\s+)?" + field + r"\s*[:：=]\s*(.+?)\s*$")
        table = re.compile(r"^\s*\|\s*" + field + r"\s*\|\s*([^|]+)\s*\|\s*$")
        evidence, judgments = [], []
        for part in evidence_parts:
            if not isinstance(part, dict) or not isinstance(part.get("text"), str) or not isinstance(part.get("ref"), dict) or not part["ref"]:
                continue
            # 中文句号/分号为硬边界，绝不跨句把相邻字段的值绑定过来。
            for sentence in re.split(r"[\n\r；;。]", part["text"]):
                match = pattern.fullmatch(sentence) or table.fullmatch(sentence)
                if not match:
                    continue
                judgment = _judgment(condition, match.group(1).strip())
                judgments.append(judgment)
                evidence.append({"ref": deepcopy(part["ref"]), "quote": sentence.strip(),
                                 "role": part.get("role", "direct"),
                                 "status": "unknown" if judgment is None else ("satisfied" if judgment else "conflict")})
        known = {value for value in judgments if value is not None}
        # 同字段相互冲突，或还有无法解释的字段值，不能只挑有利证据下结论。
        ambiguous = len(known) > 1
        status = "unknown" if not known or ambiguous or None in judgments else ("satisfied" if True in known else "conflict")
        reason = "ambiguous" if ambiguous else ("explicit_field" if status != "unknown" else "insufficient_evidence")
        diagnostics.append({"id": condition["id"], "status": status, "reason": reason, "evidence": evidence})
    return diagnostics
