"""Hand-authored raw table ownership oracles, independent of syntax readers."""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph
from moparse_eval.source_obligations import (
    audit_source_obligations,
    build_source_obligation_inventory,
)

PATH = "<independent-raw-table-scope>"
TABLE = "| Attribute | Value |\n|---|---|\n| Revenue | 17 |\n| Profit | 5 |\n"
RAW = "# North\n\n" + TABLE
NORTH = {"text": "North", "reference": {"path": PATH, "lines": [1, 1]}}


def fixture(*, context=True):
    def target(ident, kind, text, raw, bounds):
        return {"id": ident, "kind": kind, "text": text, "raw_text": text, "raw": raw,
                "reference": {"path": PATH, "lines": bounds}, "pages": [1], "cells": [],
                "parents": [], "has_children": False, "context": [], "selected_heading_context": [],
                "outside_selection_context": [], "heading_level": 1 if kind == "heading" else None}
    heading = target("heading", "heading", "North", "# North\n", [1, 1])
    table = target("table", "table", "", TABLE, [3, 6])
    table["selected_heading_context"] = [deepcopy(NORTH)] if context else []
    table["cells"] = [{"id": f"cell:{row}:{column}", "native_path": f"cell:{row}:{column}",
                       "row": row, "col": column, "row_span": 1, "col_span": 1, "text": text,
                       "is_column_header": row == 0, "native_syntax": {"format": "gfm", "row": row, "column": column}}
                      for row, values in enumerate([["Attribute", "Value"], ["Revenue", "17"], ["Profit", "5"]])
                      for column, text in enumerate(values)]
    return {"sample_id": "raw-table-scope", "document_id": "invented", "source_pages": [1],
            "standard": "expected_only", "scope": [{"lines": [1, 6], "pages": [1],
                "declared_source_pages": [1], "outside_source_pages": []}], "targets": [heading, table],
            "authorized_raw_segments": [{"id": "raw", "source": {"path": PATH, "lines": [1, 6]}, "raw": RAW}]}


def scope_obligations(graph):
    inventory = graph["source_obligation_inventory"]
    return [row for row in inventory["obligations"] if row.get("binding_role") == "heading_scope"]


def test_positive_raw_table_scopes_retain_exact_cell_positions_and_original_heading():
    graph = compile_requirement_graph(fixture())
    assert graph["semantic_complete"] is True
    scopes = scope_obligations(graph)
    assert len(scopes) == 6
    assert all(row["required_scope"] == [NORTH] for row in scopes)
    assert {(proof["row"], proof["column"]) for row in scopes for proof in row["raw_scope_evidence"]} == {
        (row, column) for row in range(3) for column in range(2)}
    assert all([node["scope"] for node in graph["nodes"] if node["id"] in graph["projections"]["B"]])


def test_omitted_derived_table_context_cannot_remove_original_raw_heading_ownership():
    graph = compile_requirement_graph(fixture(context=False))
    assert graph["source_obligation_inventory"]["source_complete"] is True
    assert len(scope_obligations(graph)) == 6
    assert graph["source_obligation_coverage"]["semantic_complete"] is False
    assert graph["semantic_complete"] is False
    assert all(node["scope"] == [] for node in graph["nodes"] if node["id"] in graph["projections"]["B"])


@pytest.mark.parametrize("mutation", ["wrong_heading_text", "wrong_heading_line"])
def test_a_matching_neighbor_heading_does_not_prove_forged_declared_heading_identity(mutation):
    expected = fixture()
    declared = expected["targets"][1]["selected_heading_context"][0]
    if mutation == "wrong_heading_text":
        declared["text"] = "South"
    else:
        declared["reference"]["lines"] = [3, 3]
    graph = compile_requirement_graph(expected)
    assert graph["source_obligation_inventory"]["source_complete"] is True
    assert graph["source_obligation_coverage"]["semantic_complete"] is False
    assert graph["semantic_complete"] is False


def test_correct_neighbor_record_scope_cannot_explain_a_different_original_cell():
    graph = compile_requirement_graph(fixture())
    revenue = next(node for node in graph["nodes"] if node["id"] in graph["projections"]["B"] and node["attribute"] == "Revenue")
    revenue["scope"] = []
    for edge in graph["relations"]:
        if edge.get("type") == "field_binding" and edge.get("right", {}).get("attribute") == "Revenue":
            edge["right"]["scope"] = []
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    scopes = scope_obligations(graph)
    inventory_sources = {entry["id"]: entry for entry in graph["source_obligation_inventory"]["sources"]}
    revenue_scopes = {row["id"] for row in scopes if inventory_sources[row["source_id"]]["text"] in {"Revenue", "17"}}
    profit_scopes = {row["id"] for row in scopes if inventory_sources[row["source_id"]]["text"] in {"Profit", "5"}}
    assert revenue_scopes and profit_scopes
    assert all(row["status"] == "pending" for row in coverage["dispositions"] if row["obligation_id"] in revenue_scopes)
    assert all(row["status"] == "explained" for row in coverage["dispositions"] if row["obligation_id"] in profit_scopes)
    assert coverage["semantic_complete"] is False


@pytest.mark.parametrize("coordinate", ["row", "col"])
def test_a_forged_grid_position_does_not_borrow_a_neighboring_original_cell(coordinate):
    expected = fixture()
    revenue = expected["targets"][1]["cells"][3]
    assert revenue["text"] == "17"
    revenue[coordinate] = 2 if coordinate == "row" else 0
    inventory = build_source_obligation_inventory(expected)
    raw_cells = inventory["authorized_raw_inventory"]["obligations"]
    [missing] = [row for row in raw_cells if row.get("row") == 1 and row.get("column") == 1 and row["status"] == "pending"]
    assert missing["text"] == "17"
    assert inventory["source_complete"] is False
