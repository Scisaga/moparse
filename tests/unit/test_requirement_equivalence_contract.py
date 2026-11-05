"""Independent final-equivalence oracles over invented business records.

These cases assert final B/L decisions, rather than approximate retrieval alone.
No corpus, saved candidate, reference compiler output or model supplies answers.
"""

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

REFERENCE = "Period: 2027年\n\nName: Delta; Revenue: 17万元; Profit: 5万元"


def _grade(actual):
    required = compile_markdown(REFERENCE, sample_id="invented-equivalence")
    assert sorted((f["attribute"], f["value"], f["role"]) for f in required["business"]) == [
        ("Name", "Delta", "identity"), ("Profit", "5", "metric"), ("Revenue", "17", "metric"),
    ]
    return grade_layers(required, read_candidate_markdown(actual, sample_id="invented-equivalence"))


def _business_rows(score):
    rows = [row for row in score["outcomes"] if row["layer"] == "B"]
    assert len(rows) == 3
    assert score["layers"]["B"]["denominator"] == 3
    return {row["expected"]["attribute"]: row for row in rows}


@pytest.mark.parametrize("revenue,profit", [("170000元", "50000元"), ("0.17百万元", "0.05百万元")])
def test_exact_same_currency_scale_equivalence_reaches_final_business_and_relation_decisions(revenue, profit):
    score = _grade(f"Period: 2027年\n\nName: Delta; Revenue: {revenue}; Profit: {profit}")
    assert {row["outcome"] for row in _business_rows(score).values()} == {"correct"}
    assert score["layers"]["B"]["numerator"] == 3
    assert score["layers"]["L"]["numerator"] == score["layers"]["L"]["denominator"]
    assert score["layers"]["T"]["score"] < 100


@pytest.mark.parametrize("revenue", ["170001元", "170000", "170000美元", "17.01万元"])
def test_scale_equivalence_does_not_allow_rounding_missing_units_or_foreign_currency(revenue):
    score = _grade(f"Period: 2027年\n\nName: Delta; Revenue: {revenue}; Profit: 5万元")
    rows = _business_rows(score)
    assert rows["Revenue"]["outcome"] == "incorrect"
    assert rows["Profit"]["outcome"] == rows["Name"]["outcome"] == "correct"
    assert score["layers"]["B"]["numerator"] == 2


def test_supported_long_label_typo_is_final_equivalence_with_independent_actual_context():
    score = _grade("Period: 2027年\n\nName: Delta; Revene: 17万元; Profit: 5万元")
    rows = _business_rows(score)
    assert rows["Revenue"]["outcome"] == "correct"
    assert score["layers"]["B"]["numerator"] == 3
    assert score["layers"]["L"]["numerator"] == score["layers"]["L"]["denominator"]
    assert score["layers"]["T"]["score"] < 100
    assert "17" not in repr(rows["Revenue"]["retrieval"]["query"])


@pytest.mark.parametrize("actual", [
    "Period: 2026年\n\nName: Delta; Revene: 17万元; Profit: 5万元",
    "Period: 2027年\n\nName: Deltx; Revene: 17万元; Profit: 5万元",
    "Period: 2027年\n\nName: Delta; Revene: 17美元; Profit: 5万元",
])
def test_label_typo_rule_cannot_override_period_entity_or_currency_conflict(actual):
    assert _business_rows(_grade(actual))["Revenue"]["outcome"] == "incorrect"


@pytest.mark.parametrize("wanted,actual", [
    ("Gross revenue", "Net revenue"), ("ROA", "ROE"), ("Revenue", "Revenue growth"),
])
def test_protected_modifier_or_short_role_is_not_a_supported_label_typo(wanted, actual):
    reference = f"Period: 2027年\n\nName: Delta; {wanted}: 17万元"
    required = compile_markdown(reference, sample_id="invented-protected-role")
    assert len(required["business"]) == 2
    score = grade_layers(required, read_candidate_markdown(
        reference.replace(wanted, actual), sample_id="invented-protected-role"))
    [row] = [item for item in score["outcomes"] if item["layer"] == "B" and item["expected"]["role"] == "metric"]
    assert row["outcome"] == "incorrect"


def test_entity_name_never_inherits_the_field_label_edit_distance_rule():
    score = _grade(REFERENCE.replace("Delta", "Deltx"))
    assert _business_rows(score)["Name"]["outcome"] == "incorrect"
