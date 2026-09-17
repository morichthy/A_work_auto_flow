"""生成JSON Schema与TypeScript契约，不修改规范数据。

运行：automation/python.ps1 automation/scripts/material_query/generate_types.py [--check]
默认刷新两个受控派生产物，--check只读比较，漂移时返回1；不依赖Node或第三方包。
"""
import argparse
from copy import deepcopy
from dataclasses import MISSING, fields, is_dataclass
import json
from pathlib import Path
import sys
import types
from typing import get_args, get_origin, get_type_hints, Literal, Union, TypeVar

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from material_query import contracts as c


def schema_type(typ):
    origin, args = get_origin(typ), get_args(typ)
    if origin in (Union, types.UnionType):
        return {"anyOf": [schema_type(arg) for arg in args]}
    if origin is Literal:
        return {"enum": list(args)}
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": schema_type(args[0])}
        return {"type": "array", "prefixItems": [schema_type(arg) for arg in args], "minItems": len(args), "maxItems": len(args)}
    if isinstance(typ, TypeVar):
        return {}
    if is_dataclass(typ):
        return {"$ref": "#/$defs/" + typ.__name__}
    return {"type": {str: "string", int: "integer", float: "number", bool: "boolean", type(None): "null"}[typ]}


def ts_type(typ):
    origin, args = get_origin(typ), get_args(typ)
    if origin in (Union, types.UnionType):
        return " | ".join(ts_type(arg) for arg in args)
    if origin is Literal:
        return " | ".join(json.dumps(arg, ensure_ascii=False) for arg in args)
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return f"Array<{ts_type(args[0])}>"
        return "[" + ", ".join(ts_type(arg) for arg in args) + "]"
    if isinstance(typ, TypeVar):
        return "T"
    if is_dataclass(typ):
        return typ.__name__
    return {str: "string", int: "number", float: "number", bool: "boolean", type(None): "null"}[typ]


def rendered():
    defs, lines = {}, ["// Generated from material_query/contracts.py; do not edit."]
    for name, cls in vars(c).items():
        if not isinstance(cls, type) or not is_dataclass(cls) or cls.__module__ != c.__name__:
            continue
        hints = get_type_hints(cls)
        props = {f.name: schema_type(hints[f.name]) for f in fields(cls)}
        required = [f.name for f in fields(cls) if f.default is MISSING and f.default_factory is MISSING]
        defs[name] = {"type": "object", "properties": props, "required": required, "additionalProperties": False}
        generic = "<T = unknown>" if name == "Result" else ""
        lines += [f"export interface {name}{generic} {{", *[f"  {key}{'' if key in required else '?'}: {ts_type(hints[key])};" for key in props], "}", ""]
    # JSON Schema handles structural constraints; semantic request validation is
    # also mandatory (e.g. budget relations and formal applicability).
    for prop in defs["Budget"]["properties"].values():
        prop["minimum"] = 0
    defs["FixedRef"]["properties"]["sha256"]["pattern"] = "^[0-9a-f]{64}$"
    # A generic Result is useful to describe the envelope, but each endpoint
    # needs a concrete value schema so a successful response cannot hide an
    # arbitrary unvalidated payload behind TypeVar T.
    for target in ("SearchReceipt", "MaterialPacket", "QueryJob", "TreePage", "MaintenancePlan", "MaintenanceReceipt", "MaintenanceStatusReceipt", "DeepenReceipt",
                   "RepresentationDefinition", "Realization", "AssociationProposal",
                   "OwnerAssessmentReceipt"):
        result_schema = deepcopy(defs["Result"])
        result_schema["properties"]["value"] = {"anyOf": [{"$ref": "#/$defs/" + target}, {"type": "null"}]}
        defs["Result_" + target] = result_schema
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:rdwork:material-query:0.2", "$defs": defs}
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n", "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    automation = SCRIPTS.parent
    outputs = (automation / "schemas/material-query.schema.json", automation / "frontend/src/generated/material-query.ts")
    different = []
    for path, text in zip(outputs, rendered()):
        # Compare bytes so Windows CRLF drift cannot invalidate archive fingerprints.
        if not path.exists() or path.read_bytes() != text.encode("utf-8"):
            different.append(str(path))
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode("utf-8"))
    print(json.dumps({"status": "drift" if args.check and different else "passed", "changed": different}, ensure_ascii=False))
    return int(args.check and bool(different))


if __name__ == "__main__":
    raise SystemExit(main())
