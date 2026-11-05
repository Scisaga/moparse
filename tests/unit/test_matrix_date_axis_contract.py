"""Source-only failure closure for an explicitly printed fiscal date axis.

The fixture is invented native table evidence. No expected text is supplied to
the matrix reader, and date normalization is outside this contract.
"""

from __future__ import annotations

from copy import deepcopy

from moparse_eval.matrix_evidence import read_matrix
from moparse_eval.text_projection import project_table_text
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate

TABLE_SOURCE = {"path": "#/tables/0", "page": 1, "lines": [], "block": "table:0"}
SAMPLE = "controlled-native-date-axis"


def cell(text, row, col, *, column=False, row_header=False, col_span=1):
    return {
        "id": f"cell:{row}:{col}",
        "native_path": f"#/tables/0/cells/{row}/{col}",
        "text": text,
        "row": row,
        "col": col,
        "row_span": 1,
        "col_span": col_span,
        "column_header": column,
        "row_header": row_header,
    }


def fiscal_date_cells():
    return [
        cell("Year Ended", 0, 1, column=True, col_span=2),
        cell("Jan 26, 2027", 1, 1, column=True),
        cell("Jan 28, 2026", 1, 2, column=True),
        cell("Utilization", 2, 0, row_header=True),
        cell(" 17.0 % ", 2, 1),
        cell(" 11.0 % ", 2, 2),
    ]


def actual_date_axis_is_read(facts):
    """An implemented reader must expose the actual full printed dates."""
    return {
        (fact["subject"], fact["attribute"], fact["value"],
         fact["qualifiers"].get("period"), fact["qualifiers"].get("unit"))
        for fact in facts
    } == {
        ("", "Utilization", "17.0", "Jan 26, 2027", "%"),
        ("", "Utilization", "11.0", "Jan 28, 2026", "%"),
    }


def affected_cells(entries):
    return {
        source.get("cell")
        for entry in entries
        for source in [entry.get("source", {}), *entry.get("affected_data_sources", [])]
        if source.get("path") == TABLE_SOURCE["path"]
    }


def assert_original_cells(projection, cells):
    snapshots = {entry["source"]["cell"]: entry for entry in projection["source_cells"]}
    assert set(snapshots) == {entry["id"] for entry in cells}
    for entry in cells:
        snapshot = snapshots[entry["id"]]
        assert snapshot["text"] == entry["text"]
        assert snapshot["source"]["path"] == TABLE_SOURCE["path"]
        assert (snapshot["source"]["row"], snapshot["source"]["col"]) == (entry["row"], entry["col"])
        assert snapshot["row_span"] == entry["row_span"]
        assert snapshot["col_span"] == entry["col_span"]


def test_unread_fiscal_date_axis_keeps_raw_cells_and_has_same_source_pending():
    cells = fiscal_date_cells()
    original = deepcopy(cells)
    result = read_matrix(cells, source=TABLE_SOURCE)
    assert cells == original
    assert_original_cells(project_table_text(cells, result, TABLE_SOURCE), cells)
    if actual_date_axis_is_read(result["facts"]):
        assert result["complete"] is True
        return

    assert result["complete"] is False, "Unread date-axis identity cannot be a complete ordinary business field"
    blockers = [item for item in result["blockers"] if item.get("category") == "software_unsupported"]
    assert {"cell:2:1", "cell:2:2"} <= affected_cells(blockers)
    assert {"cell:0:1", "cell:1:1", "cell:1:2"} <= {
        identifier for item in blockers for identifier in item.get("header_ids", [])
    }
    assert {"cell:2:1", "cell:2:2"} <= affected_cells(result.get("pending_requirements", []))


def test_unread_fiscal_date_axis_withdraws_both_business_and_relation_layers():
    cells = fiscal_date_cells()
    candidate = read_candidate({
        "sample_id": SAMPLE,
        "pipeline": "controlled-native",
        "status": "success",
        "pages": [{"page": 1, "blocks": [{
            "id": "table:0", "kind": "table", "native_path": TABLE_SOURCE["path"], "cells": cells,
        }]}],
        "relations": [],
    })
    assert_original_cells(candidate["text_projection"], cells)
    if actual_date_axis_is_read(candidate["business"]):
        return

    requirements = compile_markdown(
        "- Period: Jan 26, 2027; Utilization: 17.0%\n"
        "- Period: Jan 28, 2026; Utilization: 11.0%",
        sample_id=SAMPLE,
    )
    assert requirements["blockers"] == []
    assert len(requirements["business"]) == 2
    grade = grade_layers(requirements, candidate)
    assert grade["publishable"] is False, "A zero-hit date query is a reader gap, not a publishable candidate error"
    assert {"cell:2:1", "cell:2:2"} <= affected_cells(grade["pending_requirements"]["candidate"])
    for layer in ("B", "L"):
        assert grade["layers"][layer]["complete"] is False
        assert grade["layers"][layer]["score"] is None
        assert any(item["side"] == "candidate" and layer in item.get("layers", ["B", "L"])
                   and item.get("source", {}).get("path") == TABLE_SOURCE["path"]
                   for item in grade["blockers"])


def test_calendar_year_axis_remains_supported():
    result = read_matrix([
        cell("2027年", 0, 1, column=True), cell("2026年", 0, 2, column=True),
        cell("Utilization", 1, 0, row_header=True), cell("17%", 1, 1), cell("11%", 1, 2),
    ], source=TABLE_SOURCE)
    assert result["blockers"] == []
    assert result.get("pending_requirements", []) == []
    assert [(fact["subject"], fact["attribute"], fact["value"], fact["qualifiers"])
            for fact in result["facts"]] == [
        ("", "Utilization", "17", {"period": "2027年", "unit": "%"}),
        ("", "Utilization", "11", {"period": "2026年", "unit": "%"}),
    ]


def test_full_date_in_a_declared_period_column_remains_a_literal_qualifier():
    result = read_matrix([
        cell("Period", 0, 0, column=True), cell("Utilization (%)", 0, 1, column=True),
        cell("Jan 26, 2027", 1, 0), cell("17%", 1, 1),
    ], source=TABLE_SOURCE)
    assert result["blockers"] == []
    assert result.get("pending_requirements", []) == []
    assert [(fact["attribute"], fact["value"], fact["qualifiers"]) for fact in result["facts"]] == [
        ("Utilization", "17", {"period": "Jan 26, 2027", "unit": "%"}),
    ]


def test_status_ready_headers_do_not_acquire_a_date_axis_blocker():
    result = read_matrix([
        cell("Status", 0, 0, column=True), cell("Ready", 0, 1, column=True),
        cell("Blocked", 1, 0), cell("No", 1, 1),
    ], source=TABLE_SOURCE)
    assert result["blockers"] == []
    assert result.get("pending_requirements", []) == []
    assert [(fact["attribute"], fact["value"], fact["qualifiers"]) for fact in result["facts"]] == [
        ("Status", "Blocked", {}), ("Ready", "No", {}),
    ]
