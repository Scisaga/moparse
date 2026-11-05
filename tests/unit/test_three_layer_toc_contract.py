"""Hand-authored navigation requirements through the public text readers."""

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

LIST = "# Contents\n\n- North\n  - Results: Page 17\n- South\n  - Results: Page 29"
GFM = "# Contents\n\n| Parent | Title | Page |\n|---|---|---|\n| North | Results | 17 |\n| South | Results | 29 |"
HTML = ('# Contents\n\n<table><tr><th>Title</th><th>Page</th></tr>'
        '<tr><th scope="rowgroup" colspan="2">North</th></tr><tr><td>Results</td><td>17</td></tr>'
        '<tr><th scope="rowgroup" colspan="2">South</th></tr><tr><td>Results</td><td>29</td></tr></table>')


@pytest.mark.parametrize("reference", [LIST, GFM, HTML])
@pytest.mark.parametrize("candidate", [LIST, GFM, HTML])
def test_two_repeated_leaves_keep_parent_page_and_weight_across_serializations(reference, candidate):
    expected = compile_markdown(reference)
    assert [(f["subject"], f["attribute"], f["value"], f["identity_facets"]) for f in expected["business"]] == [
        ("Results", "Page", "17", {"toc_parent": ["North"]}),
        ("Results", "Page", "29", {"toc_parent": ["South"]})]
    score = grade_layers(expected, read_candidate_markdown(candidate))
    assert score["publishable"] is True, score["blockers"]
    assert score["layers"]["T"]["denominator"] == score["layers"]["T"]["numerator"] == 44
    assert score["layers"]["L"]["denominator"] == score["layers"]["L"]["numerator"] == 4
    assert score["layers"]["B"]["denominator"] == score["layers"]["B"]["numerator"] == 2
    validate_evidence(score)


def test_one_wrong_page_changes_its_business_answer_without_rebinding_the_entry():
    score = grade_layers(compile_markdown(LIST), read_candidate_markdown(GFM.replace("17", "18")))
    assert score["layers"]["B"]["denominator"] == 2 and score["layers"]["B"]["numerator"] == 1
    assert score["layers"]["L"]["denominator"] == score["layers"]["L"]["numerator"] == 4
    [wrong] = [r for r in score["outcomes"] if r["layer"] == "B" and r["outcome"] == "incorrect"]
    assert wrong["expected"]["identity_facets"] == {"toc_parent": ["North"]}
    assert "17" not in repr(wrong["retrieval"]["query"])


def test_parent_value_is_never_borrowed_from_the_other_repeated_leaf():
    actual = GFM.replace("| North | Results | 17 |", "| North | Results | 29 |").replace(
        "| South | Results | 29 |", "| South | Results | 17 |")
    score = grade_layers(compile_markdown(LIST), read_candidate_markdown(actual))
    assert score["layers"]["B"]["numerator"] == 0
    assert score["layers"]["L"]["numerator"] == 4
    for row in [r for r in score["outcomes"] if r["layer"] == "B"]:
        assert len(row["retrieval"]["accepted"]) == 1
        assert len(row["retrieval"]["candidates"]) == 2
