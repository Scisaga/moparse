"""Printed present/past distinctions through the shared public core."""

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


def _grade(expected_text, actual_text):
    expected = compile_markdown(expected_text, sample_id="invented-finite-tense")
    actual = read_candidate_markdown(actual_text, sample_id="invented-finite-tense")
    return expected, grade_layers(expected, actual)


@pytest.mark.parametrize("reference,actual,required_tense,actual_tense", [
    ("Delta owns Kappa.", "Delta owned Kappa.", "present", "past"),
    ("The board approved Dividend.", "The board approves Dividend.", "past", "present"),
])
def test_printed_finite_tense_changes_the_business_assertion_after_locating_the_same_relation(
        reference, actual, required_tense, actual_tense):
    _, score = _grade(reference, actual)
    [row] = [item for item in score["outcomes"] if item["layer"] == "B"]
    assert score["layers"]["B"]["denominator"] == 1
    assert row["outcome"] == "incorrect", "preserving a tense difference only in T is insufficient"
    assert score["layers"]["B"]["numerator"] == 0
    assert row["expected"]["qualifiers"]["tense"] == required_tense
    [located] = row["actual"]
    assert located["qualifiers"]["tense"] == actual_tense
    assert row["retrieval"]["accepted"] == [located["id"]]
    assert "tense" not in row["retrieval"]["query"].get("qualifiers", {})
    assert score["layers"]["T"]["score"] < 100


def test_same_printed_present_and_past_statements_keep_two_correct_source_bound_requirements():
    text = "Delta owns Kappa.\n\nThe board approved Dividend."
    expected, score = _grade(text, text)
    assert len(expected["business"]) == 2
    assert score["layers"]["B"]["denominator"] == score["layers"]["B"]["numerator"] == 2
    assert score["layers"]["B"]["score"] == score["layers"]["T"]["score"] == 100
    assert [fact["qualifiers"].get("tense") for fact in expected["business"]] == ["present", "past"]
    first, second = expected["business"]
    assert first["qualifier_sources"]["tense"]["text_span"] == [6, 10]
    assert "Delta owns Kappa."[6:10] == "owns"
    assert second["qualifier_sources"]["tense"]["text_span"] == [10, 18]
    assert "The board approved Dividend."[10:18] == "approved"
