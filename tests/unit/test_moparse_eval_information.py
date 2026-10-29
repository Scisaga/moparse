"""Independently authored information-level examples; no real corpus is read."""

from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells, markdown_cells
from moparse_eval.information import field_value_text
from moparse_eval.scoring import _declared_path_locates, _label_in_native_cell, score_case


def evaluate(cells, *, row=None, column=None, value="17", qualifiers=None):
    field = {"column_header_path": column or ["2025", "Amount"], "value": value, **(qualifiers or {})}
    reference = {"sample_id": "invented", "review_status": "confirmed", "relations": [],
                 "units": [{"id": "record", "kind": "table_record", "status": "confirmed",
                            "pages": [1], "literal": "Independent example", "table": {
                                "row_header_path": row or ["Revenue"], "fields": [field]}}]}
    observation = {"sample_id": "invented", "pipeline": "synthetic", "status": "completed",
                   "pages": [{"page": 1, "blocks": [{"id": "table", "kind": "table", "cells": cells}]}]}
    before = deepcopy((reference, observation))
    result = score_case(reference, observation)
    assert (reference, observation) == before
    return result["units"][0]["fields"][0], result["metrics"]["table_records"]


def repeated_leaves():
    return html_cells('<table><tr><th>Item</th><th colspan="2">2025</th><th colspan="2">2024</th></tr>'
                      '<tr><th>Item</th><th>Amount</th><th>Rate</th><th>Amount</th><th>Rate</th></tr>'
                      '<tr><td>Revenue</td><td>17</td><td>5%</td><td>99</td><td>8%</td></tr></table>')


@pytest.mark.parametrize("label,text,found", [
    ("$m", "2025$m", True), ("(%)", "占比(%)", True), ("%", "增长率%", True),
    ("元", "万元", False), ("2025", "12025", False), ("Amount", "Amounts", False),
    ("2025", "2025/26", False), ("2025", "2025-2026", False),
    ("2025", "2025.0", False), ("2025", "2025$m", True),
    ("2025", "2025, audited", True), ("2025", "2024/2025", False),
    ("Q1 2025", "Q1 2025/26", False),
])
def test_label_boundary_depends_on_the_actual_label_ends(label, text, found):
    assert _label_in_native_cell(label, text, True) is found


@pytest.mark.parametrize("expected,actual,correct", [
    ("$100.00", "$ 100.00", True), ("75.0%", "75.0 %", True),
    ("100", "1 00", False), ("100", "100%", False), ("100", "-100", False),
    ("1,000.0", "1000.0", False), ("75.0%", "75%", False), ("$100", "€100", False),
])
def test_scalar_display_spacing_does_not_normalize_numbers_or_change_units(expected, actual, correct):
    assert (field_value_text(expected) == field_value_text(actual)) is correct


@pytest.mark.parametrize("reference,native,found", [
    (["2025", "$m"], ["2025$m"], True),
    (["Q1 2025"], ["Q1", "2025"], True),
    (["Group", "Revenue"], ["Group Revenue"], True),
    (["Group Revenue"], ["Group", "Revenue"], True),
    (["Revenue"], ["Group", "Revenue"], False),
    (["2025", "Amount"], ["Amount", "2025"], False),
    (["Amount", "Amount"], ["Amount"], False),
])
def test_path_segmentation_can_change_without_dropping_business_context(reference, native, found):
    assert _declared_path_locates(reference, native, True) is found


def test_whole_column_path_resolves_repeated_leaf_titles_without_using_the_answer():
    field, metrics = evaluate(repeated_leaves())
    assert field["status"] == "compared" and metrics["correct_fields"] == 1
    field, metrics = evaluate(repeated_leaves(), value="99")
    assert field["status"] == "compared" and field["native_text"] == "17"
    assert metrics["correct_fields"] == 0


def test_repeated_row_leaf_is_resolved_by_a_native_row_group_span():
    cells = html_cells('<table><tr><th>Group</th><th>Item</th><th>2025</th></tr>'
                       '<tr><td rowspan="2">Domestic</td><td>Revenue</td><td>17</td></tr>'
                       '<tr><td>Cost</td><td>9</td></tr>'
                       '<tr><td>Overseas</td><td>Revenue</td><td>99</td></tr></table>')
    field, metrics = evaluate(cells, row=["Domestic", "Revenue"], column=["2025"])
    assert field["status"] == "compared" and metrics["correct_fields"] == 1


def test_two_complete_paths_stay_ambiguous_even_if_only_one_answer_is_correct():
    cells = repeated_leaves()
    cells += [{"id": "another-revenue", "row": 3, "col": 0, "text": "Revenue"},
              {"id": "another-value", "row": 3, "col": 1, "text": "99"}]
    field, metrics = evaluate(cells)
    assert field["status"] == "unresolved" and metrics["correct_fields"] == 0


def test_missing_explicit_column_path_is_not_reported_as_a_missing_value():
    field, metrics = evaluate([{"id": "v", "text": "17", "row_header_path": ["Revenue"],
                                "column_header_path": ["2024", "Amount"]}])
    assert field["status"] == "unresolved"
    assert metrics["target_missing_fields"] == 0


@pytest.mark.parametrize("representation", ["json", "html", "markdown"])
def test_equivalent_native_representations_have_the_same_information_score(representation):
    if representation == "json":
        cells = [{"id": "v", "text": "17", "row_header_path": ["Revenue"],
                  "column_header_path": ["2025$m"]}]
    elif representation == "html":
        cells = html_cells('<table><tr><th>Item</th><th>2025$m</th></tr>'
                           '<tr><td>Revenue</td><td>17</td></tr></table>')
    else:
        cells = markdown_cells('| Item | 2025$m |\n| --- | --- |\n| Revenue | 17 |')
    field, metrics = evaluate(cells, column=["2025", "$m"], qualifiers={"unit": "$m", "period": "2025"})
    assert field["status"] == "compared"
    assert metrics["information_correct_fields"] == 1


@pytest.mark.parametrize("unit,state", [("万元", "correct"), ("元", "incorrect"), (None, "unresolved")])
def test_qualifiers_are_required_for_complete_information_but_not_invented(unit, state):
    cell = {"id": "v", "text": "17", "row_header_path": ["Revenue"], "column_header_path": ["2025"]}
    if unit is not None:
        cell["unit"] = unit
    field, metrics = evaluate([cell], column=["2025"], qualifiers={"unit": "万元", "period": "2025"})
    assert metrics["correct_fields"] == 1
    assert field["information"]["status"] == state
    assert metrics[f"information_{state}_fields"] == 1


def test_explicit_wrong_unit_is_not_overridden_by_a_matching_header_word():
    field, metrics = evaluate([{"id": "v", "text": "17", "row_header_path": ["Revenue"],
                                "column_header_path": ["2025$m"], "unit": "$bn"}],
                              column=["2025", "$m"], qualifiers={"unit": "$m"})
    assert field["information"]["status"] == "incorrect"
    assert metrics["information_correct_fields"] == 0


def test_one_output_value_cannot_satisfy_two_independent_targets():
    case = {"sample_id": "invented", "review_status": "confirmed", "units": [
        {"id": name, "kind": "table_record", "status": "confirmed", "literal": "Revenue",
         "table": {"row_header_path": ["Revenue"], "fields": [{"column_header_path": ["2025"], "value": "17"}]}}
        for name in ("first", "second")]}
    observation = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [{"id": "table", "cells": [
        {"id": "v", "text": "17", "row_header_path": ["Revenue"], "column_header_path": ["2025"]}]}]}]}
    result = score_case(case, observation)
    assert result["metrics"]["table_records"]["correct_fields"] == 0
    assert all(row["fields"][0]["reason"] == "native_value_claim_conflict" for row in result["units"])
