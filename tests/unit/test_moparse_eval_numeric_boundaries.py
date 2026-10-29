"""Numeric localization regressions using invented in-memory inputs only."""

from __future__ import annotations

import copy

import pytest

from moparse_eval.scoring import score_case

SCOPES = ("same_block_pair", "native_contains")


def _scoped_inputs(expected: str, candidate_text: str, scope: str) -> tuple[dict, dict]:
    label = {
        "id": "label", "kind": "text", "literal": "Metric", "pages": [1],
        "status": "confirmed", "localization_scope": "label_only",
    }
    field = {
        "id": "value", "kind": "field", "literal": expected,
        "pages": [1], "status": "confirmed",
    }
    reference = {
        "sample_id": "synthetic", "review_status": "confirmed",
        "units": [label, field], "relations": [],
    }
    if scope == "same_block_pair":
        field["field_scope"] = {
            "status": "confirmed", "scope_kind": "visual_label_value_pair", "label_unit": "label",
        }
        blocks = [{"id": "native-card", "kind": "text", "text": f"Metric: {candidate_text}"}]
        relations = []
    elif scope == "native_contains":
        field["parent"] = "label"
        blocks = [
            {"id": "native-label", "kind": "text", "text": "Metric"},
            {"id": "native-value", "kind": "text", "text": candidate_text},
        ]
        relations = [{"type": "contains", "source": "native-label", "target": "native-value"}]
    else:
        raise AssertionError(f"Unknown synthetic scope: {scope}")
    observation = {
        "sample_id": "synthetic", "pipeline": "P-synthetic", "status": "completed",
        "pages": [{"page": 1, "blocks": blocks}], "relations": relations,
    }
    return reference, observation


def _score_unchanged(reference: dict, observation: dict) -> tuple[dict, dict]:
    before = copy.deepcopy((reference, observation))
    result = score_case(reference, observation)
    assert (reference, observation) == before
    rows = {row["id"]: row for row in result["units"]}
    return result, rows


WRONG_NUMERIC_EXPRESSIONS = [
    pytest.param("600000", "600000000000", id="original-longer-digits"),
    pytest.param("000001", "0000010", id="original-leading-zero-code"),
    pytest.param("11.61%", "11.61%0", id="original-percent-trailing-digit"),
    pytest.param("600000", "1600000", id="digit-prefix"),
    pytest.param("600000", "16000007", id="digits-both-sides"),
    pytest.param("000001", "9000001", id="leading-zero-code-prefix"),
    pytest.param("600000", "+600000", id="positive-sign"),
    pytest.param("600000", "-600000", id="ascii-negative-sign"),
    pytest.param("600000", "−600000", id="unicode-negative-sign"),
    pytest.param("600000", "600000-", id="trailing-negative-sign"),
    pytest.param("600000", "600000+", id="trailing-positive-sign"),
    pytest.param("600000", "600000-1", id="adjacent-range-endpoint"),
    pytest.param("2024", "2024/2025", id="compound-period-is-not-a-single-year"),
    pytest.param("3", "3/4", id="fraction-numerator-is-not-whole-value"),
    pytest.param("4", "3/4", id="fraction-denominator-is-not-whole-value"),
    pytest.param("11.61%", "−11.61%", id="negative-percentage"),
    pytest.param("11.61%", "11.61%%", id="duplicate-percentage-marker"),
    pytest.param("600000", "600000.25", id="decimal-fraction-appended"),
    pytest.param("600000", "0.600000", id="inside-decimal-fraction"),
    pytest.param("11.61%", "111.61%", id="percentage-integer-prefix"),
    pytest.param("600", "600,000", id="first-thousands-group"),
    pytest.param("000", "1,000", id="last-thousands-group"),
    pytest.param("456", "123,456,789.00", id="middle-thousands-group"),
    pytest.param("600000", "600000e3", id="lowercase-exponent-suffix"),
    pytest.param("600000", "600000E-3", id="uppercase-signed-exponent-suffix"),
    pytest.param("3", "6e3", id="exponent-is-not-a-separate-value"),
    pytest.param("1.2e+3", "1.2e+30", id="longer-complete-exponent"),
    pytest.param("11.61", "11.61%", id="percentage-is-not-bare-decimal"),
    pytest.param("11.61", "11.61‰", id="per-mille-is-not-bare-decimal"),
    pytest.param("61", "11.61%", id="inside-percentage-fraction"),
    pytest.param("600000", "(600000)", id="accounting-negative-parentheses"),
    pytest.param("600000", "（600000）", id="fullwidth-accounting-parentheses"),
    pytest.param("600000", "６００００００", id="fullwidth-digit-suffix"),
    pytest.param("600000", "６６０００００", id="fullwidth-digit-prefix"),
    pytest.param("11.61%", "１１．６１％０", id="fullwidth-percent-trailing-digit"),
]


@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("expected,candidate_text", WRONG_NUMERIC_EXPRESSIONS)
def test_partial_numeric_expression_is_not_localized_or_credited(scope, expected, candidate_text):
    reference, observation = _scoped_inputs(expected, candidate_text, scope)
    result, rows = _score_unchanged(reference, observation)
    assert rows["label"]["status"] == "localized"
    assert "match" not in rows["value"]
    assert rows["value"]["status"] == "not_localized"
    assert rows["value"]["strict_exact"] is False
    exact = result["metrics"]["field_exact"]
    assert exact["numerator"] == 0
    assert exact["denominator"] == 1
    assert exact["value"] == 0
    assert result["coverage"]["confirmed_units"] == 2
    assert result["coverage"]["excluded_units"] == {}


CORRECT_NUMERIC_CONTEXTS = [
    pytest.param("600000", "600000", id="exact-integer"),
    pytest.param("000001", "000001", id="exact-leading-zero-code"),
    pytest.param("11.61%", "11.61%", id="exact-percentage"),
    pytest.param("−600000", "−600000", id="exact-unicode-negative"),
    pytest.param("1.2e+3", "1.2e+3", id="exact-scientific-expression"),
    pytest.param("123,456.78", "123,456.78", id="exact-grouped-decimal"),
    pytest.param("(600000)", "(600000)", id="exact-accounting-negative"),
    pytest.param("11.61‰", "11.61‰", id="exact-per-mille"),
    pytest.param("600000", "人民币600000元。", id="adjacent-chinese-currency-prose"),
    pytest.param("000001", "代码000001，结束。", id="adjacent-chinese-code-prose"),
    pytest.param("11.61%", "11.61%，同比。", id="chinese-percentage-punctuation"),
    pytest.param("600000", "USD 600000.", id="english-currency-and-full-stop"),
    pytest.param("600000", "600000, next value", id="english-comma-without-grouped-digits"),
    pytest.param("600000", "600000. Next value", id="sentence-period-without-fraction-digits"),
    pytest.param("600000", "600000; next value", id="english-semicolon"),
    pytest.param("600000", "[600000]", id="non-accounting-square-brackets"),
]


@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("expected,candidate_text", CORRECT_NUMERIC_CONTEXTS)
def test_complete_value_survives_normal_prose_and_punctuation(scope, expected, candidate_text):
    reference, observation = _scoped_inputs(expected, candidate_text, scope)
    result, rows = _score_unchanged(reference, observation)
    assert rows["label"]["status"] == "localized"
    assert rows["value"]["status"] == "localized"
    assert rows["value"]["match"]["hypothesis"] == expected
    assert result["metrics"]["field_exact"]["numerator"] == 1
    assert result["metrics"]["field_exact"]["denominator"] == 1
    if scope == "same_block_pair" and candidate_text == expected:
        assert result["metrics"]["field_pair_binding"]["value"] == 1


@pytest.mark.parametrize("value", ["123456789", "600000000000", "000001000001000001000001"])
def test_long_bare_number_without_declared_parent_stays_unresolved(value):
    reference = {
        "sample_id": "synthetic", "review_status": "confirmed", "relations": [],
        "units": [{"id": "value", "kind": "field", "literal": value,
                   "pages": [1], "status": "confirmed"}],
    }
    observation = {
        "sample_id": "synthetic", "pipeline": "P-synthetic", "status": "completed",
        "pages": [{"page": 1, "blocks": [{"id": "value", "kind": "text", "text": value}]}],
    }
    result, rows = _score_unchanged(reference, observation)
    assert rows["value"]["status"] == "unresolved"
    assert "parent_scope" in rows["value"]["reason"]
    assert "match" not in rows["value"]
    assert result["metrics"]["field_exact"]["numerator"] == 0
    assert result["metrics"]["field_exact"]["denominator"] == 1


@pytest.mark.parametrize("scope", SCOPES)
def test_fullwidth_localization_does_not_rewrite_strict_candidate_characters(scope):
    reference, observation = _scoped_inputs("123456", "１２３４５６", scope)
    result, rows = _score_unchanged(reference, observation)
    field = rows["value"]
    assert field["status"] == "localized"
    assert field["match"]["hypothesis"] == "１２３４５６"
    assert field["strict_exact"] is False
    assert field["policy_exact"] is True
    assert field["text"]["strict"]["distance"] == 6
    assert field["text"]["width_equivalent"]["distance"] == 0
    assert result["metrics"]["field_exact"]["value"] == 0


@pytest.mark.parametrize("kind", ["text", "table_cell"])
def test_numeric_content_units_cannot_bypass_whole_token_localization(kind):
    reference = {
        "sample_id": "synthetic", "review_status": "confirmed", "units": [
            {"id": "label", "kind": "text", "literal": "Metric", "pages": [1],
             "status": "confirmed", "localization_scope": "label_only"},
            {"id": "value", "kind": kind, "literal": "600000", "parent": "label",
             "pages": [1], "status": "confirmed"},
        ], "relations": [],
    }
    native = {"id": "value", "kind": "text", "text": "600000000000"}
    if kind == "table_cell":
        native = {"id": "table", "kind": "table", "cells": [
            {"id": "value", "row": 0, "col": 0, "text": "600000000000"},
        ]}
    observation = {"sample_id": "synthetic", "pipeline": "P-synthetic", "status": "completed",
                   "pages": [{"page": 1, "blocks": [
                       {"id": "label", "kind": "text", "text": "Metric"}, native,
                   ]}], "relations": [{"type": "contains", "source": "label", "target": "value"}]}
    result, rows = _score_unchanged(reference, observation)
    assert rows["label"]["status"] == "localized"
    assert rows["value"]["status"] == "not_localized"
    assert result["coverage"]["not_localized_units"] == 1
    assert result["metrics"]["unit_exact"]["tp"] == 0


@pytest.mark.parametrize("explicit_paths", [False, True], ids=["native-grid", "explicit-native-paths"])
@pytest.mark.parametrize("expected,actual", [
    ("600000", "600000000000"), ("000001", "0000010"), ("11.61%", "11.61%0"),
])
def test_table_record_keeps_whole_native_value_instead_of_extracting_a_correct_substring(
    explicit_paths, expected, actual,
):
    reference = {
        "sample_id": "synthetic", "review_status": "confirmed", "relations": [],
        "units": [{
            "id": "record", "kind": "table_record", "status": "confirmed", "pages": [1],
            "literal": "Metric", "localization_literal": "Metric", "localization_scope": "label_only",
            "text_comparison": "not_applicable",
            "table": {"id": "synthetic-table", "row_header_path": ["Metric"],
                      "fields": [{"column_header_path": ["Amount"], "value": expected}]},
        }],
    }
    cell = {"id": "native-value", "row": 1, "col": 1, "text": actual}
    if explicit_paths:
        cell.update(row_header_path=["Metric"], column_header_path=["Amount"])
    observation = {
        "sample_id": "synthetic", "pipeline": "P-synthetic", "status": "completed",
        "pages": [{"page": 1, "blocks": [{"id": "table", "kind": "table", "cells": [
            {"id": "column", "row": 0, "col": 1, "text": "Amount"},
            {"id": "row", "row": 1, "col": 0, "text": "Metric"}, cell,
        ]}]}],
    }
    result, rows = _score_unchanged(reference, observation)
    assert rows["record"]["method"] == ("explicit_native_paths" if explicit_paths else "native_grid_relation_probes")
    field = rows["record"]["fields"][0]
    assert field["native_text"] == actual
    assert field["strict_exact"] is False
    metrics = result["metrics"]["table_records"]
    assert metrics["field_coverage"]["value"] == 1
    assert metrics["field_target_correctness"]["numerator"] == 0
    assert metrics["field_target_correctness"]["denominator"] == 1
