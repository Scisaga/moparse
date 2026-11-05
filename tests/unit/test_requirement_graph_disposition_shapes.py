"""Independent source interpretations and explicit remaining unknowns."""

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph

PATH = "<invented-disposition-shapes>"


def _target(text, line=1, *, kind="text", parents=(), children=False):
    source = {"path": PATH, "lines": [line, line]}
    return {"id": f"printed:{line}", "kind": kind, "text": text, "raw_text": text, "raw": text,
            "reference": source, "cells": [], "parents": list(parents), "has_children": children,
            "context": [text] if kind == "heading" else [],
            "selected_heading_context": [{"text": text, "reference": source}] if kind == "heading" else [],
            "outside_selection_context": [], "pages": [1], "heading_level": 1 if kind == "heading" else None}


def _compile(*targets):
    expected = {"sample_id": "invented-disposition-shapes", "document_id": "invented-document",
                "source_pages": [1], "standard": "expected_only", "targets": list(targets),
                "scope": [{"lines": [1, len(targets)], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]}
    return compile_requirement_graph(expected)


def _business(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return [nodes[ident] for ident in graph["projections"]["B"]]


def _text(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return "".join(nodes[ident]["text"] for ident in graph["projections"]["T"])


def _disposition(graph, text):
    [source] = [source for source in graph["sources"] if source["text"] == text]
    [row] = [row for row in graph["dispositions"] if row["source_id"] == source["id"]]
    return row["layers"]


def _assert_unresolved_business_and_relations(graph, text):
    assert graph["semantic_complete"] is False
    disposition = _disposition(graph, text)
    assert disposition["B"]["status"] == disposition["L"]["status"] == "unresolved"
    assert text.rstrip(".") in _text(graph)


def test_complete_parent_attribution_keeps_four_scalar_requirements_and_each_actual_parent_source():
    first, second = "Net profit attributable to", "Comprehensive income attributable to"
    graph = _compile(_target(first, 1, kind="item", children=True),
                     _target("Owners of Lumen: 2028年17万元；2027年11万元", 2, kind="item", parents=[first]),
                     _target(second, 3, kind="item", children=True),
                     _target("Owners of Lumen: 2028年5万元；2027年3万元", 4, kind="item", parents=[second]))
    facts = _business(graph)
    assert [(f["subject"], f["attribute"], f["value"], f["role"], f["qualifiers"]["period"], f["qualifiers"]["unit"])
            for f in facts] == [
        ("Owners of Lumen", first, "17", "metric", "2028年", "万元"),
        ("Owners of Lumen", first, "11", "metric", "2027年", "万元"),
        ("Owners of Lumen", second, "5", "metric", "2028年", "万元"),
        ("Owners of Lumen", second, "3", "metric", "2027年", "万元")]
    assert len(facts) == 4, "parent declarations are sources, not extra business answers"
    for index, fact in enumerate(facts):
        parent_line, child_line = (1, 2) if index < 2 else (3, 4)
        assert fact["attribute_source"]["path"] == PATH
        assert fact["attribute_source"]["lines"] == [parent_line, parent_line]
        assert fact["attribute_source"]["text_span"] == [0, len(first if index < 2 else second)]
        assert fact["subject_source"]["lines"] == [child_line, child_line]
        assert fact["subject_source"]["text_span"] == [0, 15]
        for key in ("period", "unit"):
            assert fact["qualifier_sources"][key]["lines"] == [child_line, child_line]
        assert fact["value_source"]["lines"] == [child_line, child_line]
    assert [fact["value_source"]["text_span"] for fact in facts] == [[22, 24], [32, 34], [22, 23], [31, 32]]
    assert graph["semantic_complete"] is True and not graph["unresolved"]


@pytest.mark.parametrize("case", ["unknown-layout-group", "two-attribution-parents", "unprinted-parent-string"])
def test_failure_closed_parent_attribution_needs_one_actual_relationship_parent(case):
    first, second = "Net profit attributable to", "Comprehensive income attributable to"
    if case == "unknown-layout-group":
        graph = _compile(_target("Panel A", 1, kind="item", children=True),
                         _target("Owners of Lumen: 2028年17万元", 2, kind="item", parents=["Panel A"]))
    elif case == "two-attribution-parents":
        graph = _compile(_target(first, 1, kind="item", children=True),
                         _target(second, 2, kind="item", parents=[first], children=True),
                         _target("Owners of Lumen: 2028年17万元", 3, kind="item", parents=[first, second]))
    else:
        graph = _compile(_target("Owners of Lumen: 2028年17万元", 1, kind="item", parents=[first]))
    assert graph["semantic_complete"] is False
    assert any({"B", "L"} <= set(item["layers"]) for item in graph["unresolved"])


def test_failure_closed_financial_paragraph_does_not_hide_amount_and_unbound_comparison_period():
    text = "人工成本为人民币17万元，同比增长5%。"
    graph = _compile(_target(text))
    # No year or explicit comparison-endpoint declaration is printed. The
    # entire paragraph cannot become ordinary non-business prose or a fully
    # resolved YoY assertion by inventing those endpoints.
    _assert_unresolved_business_and_relations(graph, text)
    assert not any(fact.get("qualifiers", {}).get("from_period") or fact.get("qualifiers", {}).get("to_period")
                   for fact in _business(graph))


def test_part_of_reference_is_either_a_source_bound_relation_or_an_explicit_business_unknown():
    text = "Notes 7 to 11 form part of these Statements."
    graph = _compile(_target(text))
    if graph["semantic_complete"]:
        [fact] = _business(graph)
        assert (fact["subject"], fact["attribute"], fact["value"]) == (
            "Notes 7 to 11", "form", "part of these Statements")
        assert fact["subject_source"] and fact["predicate_source"] and fact["value_source"]
    else:
        _assert_unresolved_business_and_relations(graph, text)


def test_complete_explicit_name_keeps_initials_as_one_value_instead_of_sentence_fragments():
    text = "Name: Delta A. Kappa"
    graph = _compile(_target(text))
    [fact] = _business(graph)
    assert (fact["subject"], fact["attribute"], fact["value"], fact["role"]) == (
        "", "Name", "Delta A. Kappa", "identity")
    assert fact["value_source"]["text_span"] == [6, 20]
    assert text[6:20] == "Delta A. Kappa"
    assert not any(source["kind"] == "fragment" for source in graph["sources"])
    assert not graph["unresolved"] and graph["semantic_complete"] is True


def test_heading_kind_cannot_waive_its_explicit_business_statement_or_turn_its_answer_into_scope():
    text = "Delta owns Kappa."
    graph = _compile(_target(text, kind="heading"))
    if graph["semantic_complete"]:
        [fact] = _business(graph)
        assert (fact["subject"], fact["attribute"], fact["value"]) == ("Delta", "own", "Kappa")
        assert fact.get("scope", []) == [], "the assertion's own answer must not become its retrieval scope"
        assert fact["predicate_source"]["text_span"] == [6, 10]
        assert fact["value_source"]["text_span"] == [11, 16]
    else:
        _assert_unresolved_business_and_relations(graph, text)
