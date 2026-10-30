"""Invented native header scopes only; never read corpus or benchmark artifacts."""

from __future__ import annotations

from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells
from moparse_eval.scoring import score_case


def evaluate(cells, label, path, value, *, row_path=None):
    reference = {
        "sample_id": "synthetic", "review_status": "confirmed", "relations": [],
        "units": [{"id": "record", "kind": "table_record", "status": "confirmed",
                   "pages": [1], "literal": label,
                   "table": {"row_header_path": row_path or [label],
                             "fields": [{"column_header_path": path, "value": value}]}}],
    }
    observation = {
        "sample_id": "synthetic", "pipeline": "P-test", "status": "completed", "relations": [],
        "pages": [{"page": 1, "blocks": [{"id": "native-table", "kind": "table", "cells": cells}]}],
    }
    original = deepcopy((reference, observation))
    scored = score_case(reference, observation)
    assert (reference, observation) == original
    metrics = scored["metrics"]["table_records"]
    assert metrics["target_fields"] == metrics["graded_fields"]
    assert metrics["target_fields"] == metrics["information_correct_fields"] + metrics["information_incorrect_fields"]
    assert metrics["unresolved_fields"] == 0
    return scored["units"][-1]["fields"][0], metrics


def two_scopes(*, explicit=False):
    headers24 = ' headers="revenue y24"' if explicit else ""
    headers23 = ' headers="cost y23"' if explicit else ""
    return html_cells(
        '<table><tbody><tr><th scope="col">Item</th><th id="y24" scope="col">2024</th></tr>'
        f'<tr><th id="revenue" scope="row">Revenue</th><td{headers24}>900</td></tr></tbody>'
        '<tbody><tr><th scope="col">Item</th><th id="y23" scope="col">2023</th></tr>'
        f'<tr><th id="cost" scope="row">Cost</th><td{headers23}>200</td></tr></tbody></table>'
    )


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("label,year,value", [("Revenue", "2024", "900"), ("Cost", "2023", "200")])
def test_native_html_each_record_uses_its_own_header_scope(explicit, label, year, value):
    field, metrics = evaluate(two_scopes(explicit=explicit), label, [year], value)
    assert field["status"] == "compared" and metrics["correct_fields"] == 1


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("label,year,value", [("Revenue", "2023", "900"), ("Cost", "2024", "200")])
def test_native_html_cannot_borrow_a_future_or_replaced_period(explicit, label, year, value):
    field, metrics = evaluate(two_scopes(explicit=explicit), label, [year], value)
    assert field["status"] == "incorrect" and metrics["correct_fields"] == 0


def test_same_labels_in_separate_native_header_groups_are_localized_in_the_record_scope():
    cells = two_scopes()
    next(cell for cell in cells if cell["native_attributes"].get("id") == "y23")["text"] = "2024"
    field, metrics = evaluate(cells, "Revenue", ["2024"], "900")
    assert field["status"] == "compared" and metrics["correct_fields"] == 1
    field, metrics = evaluate(cells, "Cost", ["2024"], "200")
    assert field["status"] == "compared" and metrics["correct_fields"] == 1


def test_explicit_html_association_takes_priority_over_physical_header_position():
    cells = html_cells(
        '<table><tr><th id="revenue" scope="row">Revenue</th><td headers="revenue y24">900</td></tr>'
        '<tr><th scope="col">Item</th><th id="y24" scope="col">2024</th></tr></table>'
    )
    field, metrics = evaluate(cells, "Revenue", ["2024"], "900")
    assert field["status"] == "compared" and metrics["correct_fields"] == 1


def test_explicit_html_multilevel_header_chain_can_be_below_the_value():
    cells = html_cells(
        '<table><tr><th id="revenue" scope="row">Revenue</th><td headers="revenue q1">900</td></tr>'
        '<tr><th scope="col">Item</th><th id="year" scope="col">2024</th></tr>'
        '<tr><th scope="col">Item</th><th id="q1" scope="col" headers="year">Q1</th></tr></table>'
    )
    field, metrics = evaluate(cells, "Revenue", ["2024", "Q1"], "900")
    assert field["status"] == "compared" and metrics["correct_fields"] == 1


def test_additional_declared_unit_and_axis_context_does_not_invalidate_supported_header_paths():
    cells = html_cells(
        '<table><tr><th id="units" scope="col" colspan="3">Unit: million</th></tr>'
        '<tr><th id="axis" colspan="3">Operating results</th></tr>'
        '<tr><th scope="col">Item</th><th id="y24" scope="col">2024</th><th>Notes</th></tr>'
        '<tr><th id="revenue" scope="row">Revenue</th>'
        '<td headers="revenue y24 units axis">900</td><td>Reported</td></tr></table>'
    )
    field, metrics = evaluate(cells, "Revenue", ["2024"], "900")
    assert field["status"] == "compared" and metrics["correct_fields"] == 1


def test_explicit_associations_to_independent_column_header_groups_are_unresolved():
    cells = two_scopes(explicit=True)
    next(cell for cell in cells if cell["text"] == "900")["native_attributes"]["headers"] += " y23"
    for year in ("2024", "2023"):
        field, metrics = evaluate(cells, "Revenue", [year], "900")
        assert field["status"] == "incorrect" and metrics["correct_fields"] == 0


@pytest.mark.parametrize("failure", ["missing", "duplicate", "cycle", "nonheader", "empty"])
def test_broken_explicit_html_header_links_never_fall_back_to_a_matching_grid(failure):
    cells = two_scopes(explicit=True)
    value = next(cell for cell in cells if cell["text"] == "900")
    year = next(cell for cell in cells if cell["native_attributes"].get("id") == "y24")
    if failure == "missing":
        value["native_attributes"]["headers"] = "revenue absent"
    elif failure == "duplicate":
        other = deepcopy(year)
        other.update(id="duplicate-year", row=10)
        cells.append(other)
    elif failure == "cycle":
        year["native_attributes"]["headers"] = "y24"
    elif failure == "nonheader":
        year["native_tag"] = "td"
        year.pop("native_header_tag", None)
    else:
        value["native_attributes"]["headers"] = ""
    field, metrics = evaluate(cells, "Revenue", ["2024"], "900")
    assert field["status"] == "incorrect" and metrics["correct_fields"] == 0


def test_explicit_header_ids_without_scope_roles_are_still_explicit_relationships():
    cells = two_scopes(explicit=True)
    for cell in cells:
        cell.pop("is_column_header", None)
        cell.pop("is_row_header", None)
    field, metrics = evaluate(cells, "Revenue", ["2024"], "900")
    assert field["status"] == "compared" and metrics["correct_fields"] == 1
    field, metrics = evaluate(cells, "Revenue", ["2023"], "900")
    assert field["status"] == "incorrect" and metrics["correct_fields"] == 0


def test_adjacent_multilevel_column_headers_and_row_group_spans_remain_readable():
    cells = [
        {"id": "root", "row": 0, "col": 2, "col_span": 2, "text": "2024", "is_column_header": True},
        {"id": "q1", "row": 1, "col": 2, "text": "Q1", "is_column_header": True},
        {"id": "q2", "row": 1, "col": 3, "text": "Q2", "is_column_header": True},
        {"id": "group", "row": 2, "col": 0, "row_span": 2, "text": "Operations", "is_row_header": True},
        {"id": "revenue", "row": 2, "col": 1, "text": "Revenue", "is_row_header": True},
        {"id": "cost", "row": 3, "col": 1, "text": "Cost", "is_row_header": True},
        {"id": "revenue-q1", "row": 2, "col": 2, "text": "900"},
        {"id": "revenue-q2", "row": 2, "col": 3, "text": "800"},
        {"id": "cost-q1", "row": 3, "col": 2, "text": "200"},
    ]
    field, metrics = evaluate(cells, "Revenue", ["2024", "Q1"], "900", row_path=["Operations", "Revenue"])
    assert field["status"] == "compared" and metrics["correct_fields"] == 1


def test_declared_header_row_span_and_value_column_span_are_preserved():
    cells = [
        {"id": "year", "row": 0, "row_span": 2, "col": 1, "col_span": 2,
         "text": "2024", "is_column_header": True},
        {"id": "row", "row": 2, "col": 0, "text": "Revenue", "is_row_header": True},
        {"id": "value", "row": 2, "col": 1, "col_span": 2, "text": "900"},
    ]
    field, metrics = evaluate(cells, "Revenue", ["2024"], "900")
    assert field["status"] == "compared" and metrics["correct_fields"] == 1


def test_value_row_span_crossing_an_internal_header_scope_is_unresolved():
    cells = two_scopes()
    for cell in cells:
        if cell["text"] == "Revenue":
            cell["row_span"] = 3
        if cell["text"] == "900":
            cell["row_span"] = 3
    field, metrics = evaluate(cells, "Revenue", ["2024"], "900")
    assert field["status"] == "incorrect" and metrics["correct_fields"] == 0


def test_undeclared_plain_grid_keeps_the_existing_physical_relation_policy():
    cells = [
        {"id": "label", "row": 0, "col": 0, "text": "Revenue"},
        {"id": "value", "row": 0, "col": 1, "text": "900"},
        {"id": "label-below", "row": 1, "col": 1, "text": "2024"},
    ]
    field, metrics = evaluate(cells, "Revenue", ["2024"], "900")
    assert field["status"] == "compared" and metrics["correct_fields"] == 1


@pytest.mark.parametrize("year,correct", [("2024", True), ("2023", False)])
def test_explicit_json_paths_keep_their_existing_field_policy(year, correct):
    cells = [{"id": "value", "text": "900", "record_id": "revenue",
              "row_header_path": ["Revenue"], "column_header_path": ["2024"]}]
    field, metrics = evaluate(cells, "Revenue", [year], "900")
    assert metrics["correct_fields"] == int(correct)
    assert field["status"] == ("compared" if correct else "incorrect")
