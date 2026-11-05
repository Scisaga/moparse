"""Calendar identity and strict spelling are independent layer requirements."""

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


@pytest.mark.parametrize("reference,candidate,relations", [
    ("Period:2027年\n\nRevenue:17", "Period:2027\n\nRevenue:17", 2),
    ("Revenue:2027年17万元", "Revenue:2027:17万元", 3),
])
def test_same_calendar_year_with_a_different_printed_suffix_has_only_a_text_spelling_difference(reference, candidate, relations):
    score = grade_layers(compile_markdown(reference), read_candidate_markdown(candidate))
    assert score["blockers"] == []
    assert score["layers"]["T"]["score"] < 100
    assert score["layers"]["B"]["denominator"] == 1 and score["layers"]["B"]["score"] == 100
    assert score["layers"]["L"]["denominator"] == relations and score["layers"]["L"]["score"] == 100


@pytest.mark.parametrize("actual", ["2026年", "2027年度", "2027年末"])
def test_another_year_or_explicitly_different_annual_basis_is_not_plain_calendar_equivalence(actual):
    score = grade_layers(compile_markdown("Period:2027年\n\nRevenue:17"),
                         read_candidate_markdown(f"Period:{actual}\n\nRevenue:17"))
    assert score["layers"]["B"]["denominator"] == 1
    assert score["layers"]["B"]["numerator"] == 0
