"""Printed ratio and ratio-change units retain their complete source tokens."""

import pytest

from moparse_eval.measurement_evidence import (
    read_measurement_label,
    read_measurement_literal,
    read_unit_token,
)
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


@pytest.mark.parametrize("unit", ["百分点", "百分點", "pp", "percentage point", "percentage points",
                                "bps", "bp", "basis point", "basis points", "基点", "基點"])
def test_whole_delta_unit_and_raw_measurement_and_header_all_keep_the_same_printed_unit(unit):
    source = {"path": "<printed-ratio-change>", "text_span": [40, 40 + len(unit)]}
    token = read_unit_token(unit, source)
    assert token["matched"] is True and token["unit"] == unit and token["currency"] is None
    assert token["sources"]["unit"]["text_span"] == [40, 40 + len(unit)]
    raw = " 1" + unit + " "
    literal = read_measurement_literal(raw, {"path": "<printed-scalar>"})
    assert literal["matched"] is True and literal["raw"] == raw and literal["value"] == "1"
    assert literal["value_span"] == [1, 2] and literal["unit_span"] == [2, 2 + len(unit)]
    header = read_measurement_label("Margin(" + unit + ")")
    assert header["matched"] is True and header["label"] == "Margin" and header["unit"] == unit


def test_explicit_percentage_point_and_basis_point_inputs_reach_the_final_exact_delta_decision():
    score = grade_layers(compile_markdown("Margin:1百分点"), read_candidate_markdown("Margin:100bps"))
    assert score["publishable"] is True
    assert score["layers"]["B"]["numerator"] == score["layers"]["B"]["denominator"] == 1
    assert score["layers"]["L"]["numerator"] == score["layers"]["L"]["denominator"]
    assert score["layers"]["T"]["score"] < 100


@pytest.mark.parametrize("literal", ["1pp", "1百分点", "100bps"])
def test_a_quantity_inside_a_header_is_not_relabelled_as_a_pure_delta_unit(literal):
    label = "Margin(" + literal + ")"
    assert read_unit_token(literal)["matched"] is False
    parsed = read_measurement_label(label)
    assert parsed["matched"] is False and parsed["label"] == label


def test_raw_ratio_and_delta_inputs_do_not_gain_business_equivalence_from_equal_fractions():
    score = grade_layers(compile_markdown("Margin:1%"), read_candidate_markdown("Margin:100bps"))
    assert score["publishable"] is True
    assert score["layers"]["B"]["denominator"] == 1 and score["layers"]["B"]["numerator"] == 0
