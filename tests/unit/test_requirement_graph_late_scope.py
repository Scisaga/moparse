"""Reference scope dependencies resolve from completed source semantics."""

from copy import deepcopy

from moparse_eval.requirement_graph import compile_requirement_graph

PATH = "<invented-late-reference-scope>"
DECLARATION = {"kind": "explicit_unit_or_period", "text": "Period: 2025", "raw": "Period: 2025",
               "reference": {"path": PATH, "lines": [1, 1]}}


def _expected(text):
    return {"sample_id": "invented-late-reference-scope", "document_id": "invented-document", "source_pages": [1],
            "standard": "expected_only", "scope": [{"lines": [9, 9], "pages": [1],
                "declared_source_pages": [1], "outside_source_pages": []}],
            "targets": [{"id": "printed:9", "kind": "text", "text": text, "raw_text": text, "raw": text,
                         "reference": {"path": PATH, "lines": [9, 9]}, "cells": [], "parents": [],
                         "has_children": False, "context": [], "selected_heading_context": [],
                         "outside_selection_context": [deepcopy(DECLARATION)], "pages": [1], "heading_level": None}]}


def _facts(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return [nodes[ident] for ident in graph["projections"]["B"]]


def _scope_pending(graph):
    return [issue for issue in graph["unresolved"] if issue["reason"] == "input_scope_context"]


def test_own_printed_period_resolves_the_outside_dependency_after_all_semantics_are_read():
    text = "In 2028, Lumen holds 17万元."
    expected = _expected(text)
    original = deepcopy(expected)
    graph = compile_requirement_graph(expected)
    [fact] = _facts(graph)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "hold", "17")
    assert fact["qualifiers"]["period"] == "2028" and fact["qualifiers"]["unit"] == "万元"
    assert fact["qualifier_sources"]["period"]["lines"] == [9, 9]
    assert fact["qualifier_sources"]["period"]["text_span"] == [3, 7]
    assert text[3:7] == "2028"
    assert _scope_pending(graph) == []
    assert all(source["source"]["lines"] != [1, 1] for source in graph["sources"])
    assert expected == original


def test_missing_own_period_remains_a_dependency_and_is_not_supplied_from_unselected_text():
    graph = compile_requirement_graph(_expected("Lumen holds 17万元."))
    [fact] = _facts(graph)
    assert fact["value"] == "17" and "period" not in fact["qualifiers"]
    [issue] = _scope_pending(graph)
    assert issue["outside_selection"] == [DECLARATION]
    assert {"B", "L"} <= set(issue["layers"])
    assert graph["complete"] is False
    assert all(source["source"]["lines"] != [1, 1] for source in graph["sources"])


def test_unknown_non_numeric_source_cannot_clear_a_real_dependency_by_absent_keywords():
    graph = compile_requirement_graph(_expected("The lantern shimmers quietly."))
    assert _facts(graph) == []
    [issue] = _scope_pending(graph)
    assert issue["outside_selection"] == [DECLARATION]
    assert {"B", "L"} <= set(issue["layers"])
    assert graph["semantic_complete"] is False and graph["complete"] is False
