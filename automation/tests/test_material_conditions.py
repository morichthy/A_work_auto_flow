"""显式条件核对的安全边界；不以主题相近代替适用条件证据。"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from material_query.conditions import evaluate_conditions, validate_conditions


class MaterialConditionTests(unittest.TestCase):
    def check(self, text, *, expected=-20, operator="lt", unit="°C", kind="numeric", field="温度"):
        conditions = [{"id": "c1", "kind": kind, "field": field, "expected": expected, "operator": operator}]
        if unit is not None:
            conditions[0]["unit"] = unit
        return evaluate_conditions(conditions, [{"text": text, "ref": {"id": "fixed", "revision": 2}, "role": "direct"}])[0]

    def test_numeric_operators_and_negative(self):
        for op, expected, status in [("lt", -20, "satisfied"), ("le", -30, "satisfied"), ("gt", -20, "conflict"), ("ge", -30, "satisfied"), ("eq", -30, "satisfied"), ("ne", -30, "conflict")]:
            self.assertEqual(self.check("温度: -30 °C", operator=op, expected=expected)["status"], status)

    def test_units_and_binding(self):
        self.assertEqual(self.check("温度: 243.15 K")["status"], "satisfied")
        self.assertEqual(self.check("压力: 1 MPa", field="压力", expected=1000, unit="kPa", operator="eq")["status"], "satisfied")
        for text in ["温度: -30", "温度: -30 Pa", "温度。压力: -30 °C", "温度: < -30 °C", "温度: -30 °C 至 0 °C"]:
            self.assertEqual(self.check(text)["status"], "unknown", text)

    def test_literal_negation_and_token_boundary(self):
        for text, status in [("型号: X", "satisfied"), ("型号: X2", "conflict"), ("型号: 非 X", "conflict"), ("型号: 不是 X", "conflict"), ("型号: 非 Y", "unknown"), ("型号: X 或 Y", "unknown"), ("型号: X或Y", "unknown")]:
            self.assertEqual(self.check(text, field="型号", kind="literal", expected="X", unit=None, operator="eq")["status"], status)

    def test_ambiguous_and_reference(self):
        result = self.check("温度: -30 °C；温度: 5 ℃")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "ambiguous")
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(result["evidence"][0]["ref"], {"id": "fixed", "revision": 2})
        self.assertIn("-30", result["evidence"][0]["quote"])

    def test_table_and_title(self):
        self.assertEqual(self.check("| 温度 | -30 °C |")["status"], "satisfied")
        cond = [{"id": "c", "kind": "literal", "field": "型号", "expected": "X", "operator": "eq"}]
        self.assertEqual(evaluate_conditions(cond, [{"text": "正文没有型号", "title": "型号: X", "ref": {"id": "r"}}])[0]["status"], "unknown")

    def test_validation_and_regex_data(self):
        base = {"id": "c", "kind": "numeric", "field": "温度", "expected": 0, "operator": "eq"}
        for patch in [{"expected": True}, {"expected": float("nan")}, {"expected": 10 ** 500}, {"field": "x" * 81}, {"operator": "exec"}, {"extra": 1}]:
            with self.assertRaises(ValueError):
                validate_conditions([{**base, **patch}])
        with self.assertRaises(ValueError):
            validate_conditions([base] * 17)
        self.assertEqual(self.check("温度: -30 °C", field=".*")["status"], "unknown")
        self.assertEqual(self.check("温度: -30 °C", field="../../secret")["status"], "unknown")

    def test_unrelated_model_and_prose_never_satisfy_literal_condition(self):
        """Exact field/token binding must reject nearby models and ordinary prose."""
        for text, status in [("型号: X200", "conflict"), ("子型号: X", "unknown"),
                             ("型号: X.", "unknown"), ("型号: X 仅用于校准", "unknown")]:
            result = self.check(text, field="型号", kind="literal", expected="X", unit=None, operator="eq")
            self.assertEqual(result["status"], status, text)

    def test_comparison_nan_and_dimension_mismatch_remain_unknown(self):
        """The module must not invent inequality evidence from ranges or malformed units."""
        for text in ["温度: <= -30 °C", "温度: NaN °C", "温度: 1e309 °C",
                     "温度: -30 bar", "备注: 温度控制器已校准"]:
            self.assertEqual(self.check(text)["status"], "unknown", text)
        # Different dimensions and unregistered units are unknown even if their numbers match.
        self.assertEqual(self.check("压力: 1 bar", field="压力", expected=100000, unit="Pa", operator="eq")["status"], "unknown")

    def test_multiple_objects_or_unrelated_sentences_cannot_be_cherry_picked(self):
        """Mixed explicit values must surface ambiguity rather than choose a favourable object."""
        condition = [{"id": "c", "kind": "numeric", "field": "温度", "expected": -20,
                      "operator": "lt", "unit": "°C"}]
        parts = [
            {"text": "型号: X200；温度: -30 °C", "ref": {"id": "x"}, "role": "direct"},
            {"text": "型号: Y200；温度: 5 °C", "ref": {"id": "y"}, "role": "parent"},
            {"text": "备注：温度控制器已经校准", "ref": {"id": "note"}, "role": "direct"},
        ]
        result = evaluate_conditions(condition, parts)[0]
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "ambiguous")
        self.assertEqual(len(result["evidence"]), 2)

    def test_negation_requires_a_single_complete_value(self):
        """Negated values with another object or qualifier cannot become a condition match."""
        for text in ["型号: 非 X 或 Y", "型号: not X if recalibrated", "型号: 不等于 X，除非复核"]:
            result = self.check(text, field="型号", kind="literal", expected="X", unit=None, operator="eq")
            self.assertEqual(result["status"], "unknown", text)


if __name__ == "__main__":
    unittest.main()
