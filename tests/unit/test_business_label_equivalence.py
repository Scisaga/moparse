"""Frozen business-role spellings preserve text differences and values."""

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


@pytest.mark.parametrize("wanted,actual", [("金額", "金额"), ("佔營業收入比", "占营业收入比"),
                                           ("金額同比變動", "金额同比变动")])
def test_same_declared_metric_role_keeps_its_own_literal_difference(wanted, actual):
    score = grade_layers(compile_markdown(f"{wanted}: 17"), read_candidate_markdown(f"{actual}: 17"))
    assert score["publishable"] is True
    assert score["layers"]["B"]["denominator"] == score["layers"]["B"]["numerator"] == 1
    assert score["layers"]["L"]["denominator"] == score["layers"]["L"]["numerator"] == 1
    assert score["layers"]["T"]["score"] < 100
    [row] = [r for r in score["outcomes"] if r["layer"] == "B"]
    assert row["actual"][0]["attribute"] == actual
    assert row["retrieval"]["candidates"][0]["recall"] == "declared_business_role_equivalence"


@pytest.mark.parametrize("reference,candidate", [
    ("金額: 17", "金额: 18"),
    ("佔營業收入比: 17", "占营业成本比: 17"),
    ("Name: 華夏; 金額: 17", "Name: 华夏; 金额: 17"),
    ("金額: 17人民幣千元", "金额: 17美元千元"),
    ("金額: 17萬元", "金额: 17亿元"),
])
def test_role_equivalence_cannot_change_values_entities_or_measurements(reference, candidate):
    score = grade_layers(compile_markdown(reference), read_candidate_markdown(candidate))
    assert score["layers"]["B"]["numerator"] < score["layers"]["B"]["denominator"]
