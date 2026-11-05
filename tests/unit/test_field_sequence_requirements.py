"""Handwritten semantic and source oracles for explicit field sequences."""

from copy import deepcopy

import pytest

from moparse_eval.field_sequence_requirements import read_field_sequence_requirements
from moparse_eval.scalar_evidence import validate_scalar_sources

SOURCE = {"path": "<own-printed-fields>", "lines": [7, 7]}


def literal(text, source):
    a, b = source["text_span"]
    return text[a:b]


def test_a_generic_explicit_attribute_and_printed_subject_columns_keep_independent_non_numeric_facts():
    text = "Primary purpose; Engine Alpha: Scientific discovery, national security; Engine Beta: AI model training"
    result = read_field_sequence_requirements(text, SOURCE, scope=["Comparison"])
    assert result["matched"] is True and result["blockers"] == []
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in result["facts"]] == [
        ("Engine Alpha", "Primary purpose", "Scientific discovery, national security", "metric"),
        ("Engine Beta", "Primary purpose", "AI model training", "metric")]
    assert result["text_projection_complete"] is True
    for fact in result["facts"]:
        assert literal(text, fact["subject_source"]) == fact["subject"]
        assert literal(text, fact["attribute_source"]) == fact["attribute"]
        assert literal(text, fact["value_source"]) == fact["value"]
        assert fact["scope"] == ["Comparison"]
    assert len([edge for edge in result["relations"] if edge["type"] == "field_binding"]) == 2


@pytest.mark.parametrize("offset", [0, 40])
def test_a_printed_metric_declaration_gives_numeric_fields_precise_own_sources_without_scaling(offset):
    text = "Metric: Throughput; Engine Alpha: 20万元; Engine Beta: 20万元."
    source = {**SOURCE, "text_span": [offset, offset + len(text)]}
    before = deepcopy(source)
    result = read_field_sequence_requirements(text, source)
    assert source == before and result["blockers"] == []
    assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("Engine Alpha", "Throughput", "20", {"unit": "万元"}),
        ("Engine Beta", "Throughput", "20", {"unit": "万元"})]
    for fact, label in zip(result["facts"], ("Engine Alpha", "Engine Beta"), strict=True):
        start = text.index(label + ":") + len(label + ": ")
        assert fact["value_source"]["text_span"] == [offset + start, offset + start + 2]
        assert fact["raw_value"] == "20万元"
        assert fact["attribute_source"]["text_span"] == [offset + 8, offset + 18]
    validate_scalar_sources(result["facts"], {"source_fragments": [{"text": text, "source": source}]}, canonicalize=str.strip)


def test_complete_period_selectors_and_basis_are_not_reduced_to_their_calendar_year():
    text = "Gross margin; Year Ended March 31, 2028: 61%; Year Ended March 30, 2027: 56%; Change: Up 5 pts."
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is True and len(result["facts"]) == 2
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("Gross margin", "61", {"period": "March 31, 2028", "period_basis": "Year Ended", "unit": "%"}),
        ("Gross margin", "56", {"period": "March 30, 2027", "period_basis": "Year Ended", "unit": "%"})]
    for fact in result["facts"]:
        for key in ("period", "period_basis", "unit"):
            assert literal(text, fact["qualifier_sources"][key]) == fact["qualifiers"][key]
    [pending] = [p for p in result["pending_requirements"] if p["kind"] == "comparison_period_binding"]
    assert pending["label"] == "Change" and pending["value"] == "Up 5 pts."
    assert literal(text, pending["value_source"]) == "Up 5 pts."
    assert set().union(*(set(b["layers"]) for b in result["blockers"])) >= {"B", "L"}


def test_an_unknown_prefix_cannot_turn_a_record_name_into_a_metric_or_become_one_opaque_fact():
    text = "Container; Type A: Ready; Type B: Blocked"
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is True and result["facts"] == []
    [pending] = result["pending_requirements"]
    assert pending["text"] == text and pending["prefix"]["text"] == "Container"
    assert [(x["label"], x["value"]) for x in pending["segments"]] == [("Type A", "Ready"), ("Type B", "Blocked")]
    assert result["blockers"] and result["text_projection_complete"] is True


def test_an_actual_printed_schema_can_prove_an_otherwise_unknown_attribute_role():
    text = "Custom property; Alpha: ready; Beta: waiting"
    declaration = {"text": "Attribute: Custom property", "source": {"path": "<own-column-description>", "lines": [2, 2]}}
    result = read_field_sequence_requirements(text, SOURCE, schema=declaration)
    assert result["blockers"] == [] and len(result["facts"]) == 2
    assert result["scope"]["attribute_declaration"] == declaration
    assert {f["attribute"] for f in result["facts"]} == {"Custom property"}


@pytest.mark.parametrize("text", ["Revenue:17; Profit:5", "Narrative: Alpha; Beta",
                                  "Date and time:9:00; Location:https://example.invalid/notice"])
def test_ordinary_key_value_fields_time_and_urls_are_left_to_their_own_reader(text):
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is False and result["facts"] == []


def test_unread_chinese_complete_dates_are_kept_whole_instead_of_becoming_year_only_fields():
    text = "Revenue; 截至二〇二八年三月三十一日止六个月:17; 截至二〇二七年三月三十一日止六个月:11"
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is True
    assert all(f["qualifiers"].get("period") not in {"2028", "2028年", "2027", "2027年"} for f in result["facts"])
    assert len(result["facts"]) == 2 or result["pending_requirements"] and result["blockers"]
    if len(result["facts"]) == 2:
        for fact in result["facts"]:
            assert "三十一日" in fact["qualifiers"]["period"]
            assert literal(text, fact["qualifier_sources"]["period"]) == fact["qualifiers"]["period"]
            assert fact["qualifiers"].get("period_basis")
    assert result["text_projection_complete"] is True


def test_a_change_label_own_unit_does_not_turn_it_into_another_record_subject():
    text = "Gross margin; Year Ended March 31, 2028:61%; Year Ended March 30, 2027:56%; Change (%):5"
    result = read_field_sequence_requirements(text, SOURCE)
    assert len(result["facts"]) == 2
    assert any(item["kind"] == "comparison_period_binding" and item["label"] == "Change (%)"
               for item in result["pending_requirements"])
    assert result["text_projection_complete"] is True


@pytest.mark.parametrize("text", ["Metric:; Alpha:17; Beta:11", "Revenue; 2028年3月:17; 2027年3月:11"])
def test_empty_attributes_and_incomplete_dates_never_create_complete_business_facts(text):
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is True and result["facts"] == []
    assert result["pending_requirements"] and result["blockers"]


def test_caller_qualifiers_without_their_actual_sources_remain_partial_instead_of_borrowing_the_value_source():
    result = read_field_sequence_requirements("Revenue; 2028年:17; 2027年:11", SOURCE, qualifiers={"unit": "万元"})
    assert len(result["facts"]) == 2
    assert any(item["reason"] == "field_sequence_qualifier_source_unresolved" for item in result["pending_requirements"])
