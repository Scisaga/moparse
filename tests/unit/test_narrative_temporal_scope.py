"""Printed temporal prefixes own clauses; dates never become actor names."""

import pytest

from moparse_eval.narrative_requirements import read_narrative


@pytest.mark.parametrize("prefix,period,basis,period_span", [
    ("As of 31 December 2028", "31 December 2028", "As of", [6, 22]),
    ("For the year ended 31 December 2028", "31 December 2028", "For the year ended", [19, 35]),
    ("In April 2028", "April 2028", None, [3, 13]),
])
def test_explicit_temporal_prefix_has_sourced_period_and_independent_actor(prefix, period, basis, period_span):
    text = prefix + ", Lumen owns Kappa."
    parsed = read_narrative(text, {"path": "<invented-temporal-prose>", "lines": [7, 7]})
    assert parsed["complete"] is True
    [fact] = parsed["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "own", "Kappa")
    assert fact["qualifiers"]["period"] == period
    assert fact["qualifier_sources"]["period"]["text_span"] == period_span
    assert text[slice(*period_span)] == period
    if basis:
        assert fact["qualifiers"]["period_basis"] == basis
        assert text[slice(*fact["qualifier_sources"]["period_basis"]["text_span"])] == basis
    else:
        assert "period_basis" not in fact["qualifiers"]
    assert text[slice(*fact["subject_source"]["text_span"])] == "Lumen"
    assert text[slice(*fact["value_source"]["text_span"])] == "Kappa"
    assert "temporal_prose_scope" in parsed["required_matcher_features"]


@pytest.mark.parametrize("text", [
    "In April 2028, Lumen has grown its presence by helping Kappa to enter new markets.",
    "As of 31 February 2028, Lumen owns Kappa.",
    "After April 2028, Lumen owns Kappa.",
])
def test_unknown_or_invalid_temporal_scope_cannot_be_swallowed_into_actor(text):
    parsed = read_narrative(text, {"path": "<invented-temporal-prose>", "lines": [7, 7]})
    assert parsed["complete"] is False and parsed["blockers"]
    assert not any(fact["subject"].startswith(("In ", "As ", "After ")) for fact in parsed["facts"])


def test_temporal_offsets_remain_absolute_inside_an_already_bounded_field_body():
    text = "As of 31 December 2028, Lumen owns Kappa."
    result = read_narrative(text, {"path": "<invented-temporal-prose>", "lines": [9, 9],
                                   "text_span": [27, 27 + len(text)]})
    assert result["complete"] is True
    [fact] = result["facts"]
    assert fact["qualifier_sources"]["period"]["text_span"] == [33, 49]
    assert result["logic"][0]["qualifier_sources"]["period"] == fact["qualifier_sources"]["period"]
    assert "text_source" not in fact["qualifier_sources"]["period"]
