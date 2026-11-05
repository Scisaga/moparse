"""Scalar-series representation oracle, fixed before public reader changes."""

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

SERIES = "營業收入：2027年17萬元；2026年11萬元。"
SPLIT = "營業收入：2027年17萬元\n\n營業收入：2026年11萬元"
TABLE = "| 指標 | 2027年（萬元） | 2026年（萬元） |\n|---|---|---|\n| 營業收入 | 17 | 11 |"


@pytest.mark.parametrize("reference", [SERIES, SPLIT, TABLE])
@pytest.mark.parametrize("candidate", [SERIES, SPLIT, TABLE])
def test_explicit_year_scalars_have_the_same_text_relations_and_business_weight(reference, candidate):
    graph = compile_markdown(reference)
    assert graph["blockers"] == []
    assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
        ("", "營業收入", "17", {"period": "2027年", "unit": "萬元"}),
        ("", "營業收入", "11", {"period": "2026年", "unit": "萬元"})]
    result = grade_layers(graph, read_candidate_markdown(candidate))
    assert result["publishable"] is True
    # Two data objects each require metric(4), year(5), value(2), unit(2).
    assert result["layers"]["T"]["denominator"] == result["layers"]["T"]["numerator"] == 26
    assert result["layers"]["L"]["denominator"] == result["layers"]["L"]["numerator"] == 6
    assert result["layers"]["B"]["denominator"] == result["layers"]["B"]["numerator"] == 2


def test_one_wrong_year_value_does_not_move_or_merge_the_other_year_requirement():
    result = grade_layers(compile_markdown(SERIES), read_candidate_markdown(TABLE.replace("17", "18")))
    assert result["layers"]["B"]["denominator"] == 2 and result["layers"]["B"]["numerator"] == 1
    assert result["layers"]["L"]["numerator"] == 6
    [wrong] = [r for r in result["outcomes"] if r["layer"] == "B" and r["outcome"] == "incorrect"]
    assert wrong["expected"]["qualifiers"]["period"] == "2027年"
