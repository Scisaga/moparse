"""Fixed public-core quantities, subject boundaries and quoted membership."""

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


def _source_graph(text):
    return compile_requirement_graph({"sample_id": "invented-proposition-boundaries", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only",
        "scope": [{"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}],
        "targets": [{"id": "printed:1", "kind": "text", "text": text, "raw_text": text, "raw": text,
                     "reference": {"path": "<invented-proposition-boundaries>", "lines": [1, 1]}, "cells": [],
                     "parents": [], "has_children": False, "context": [], "selected_heading_context": [],
                     "outside_selection_context": [], "pages": [1], "heading_level": None}]})


def _facts(graph):
    by_id = {node["id"]: node for node in graph["nodes"]}
    return [by_id[ident] for ident in graph["projections"]["B"]]


def _unresolved(graph, text):
    assert graph["semantic_complete"] is False
    assert any(item.get("text", "").rstrip(".") == text.rstrip(".")
               and {"B", "L"} <= set(item["layers"]) for item in graph["unresolved"])
    by_id = {node["id"]: node for node in graph["nodes"]}
    assert "".join(by_id[ident]["text"] for ident in graph["projections"]["T"]) == text


def _quantity_source(graph, text, value, unit, value_span, unit_span):
    [fact] = graph["business"]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "hold", value)
    assert fact["qualifiers"]["unit"] == unit
    assert fact["value_source"]["text_span"] == value_span
    assert text[slice(*value_span)] == value
    sources = []
    if fact.get("qualifier_sources", {}).get("unit"):
        sources.append(fact["qualifier_sources"]["unit"])
    provenance = fact.get("qualifier_provenance", {}).get("unit", {})
    if provenance.get("source"):
        sources.append(provenance["source"])
    sources.extend(item["source"] for item in provenance.get("sources", []))
    assert sources, "the amount's unit needs actual printed provenance"
    for source in sources:
        assert source["text_span"] == unit_span
        assert text[slice(*source["text_span"])] == unit
    edges = [edge for edge in graph["relations"] if edge["type"] == "qualifier_scope"
             and edge["left"].get("type") == "unit"]
    assert len(edges) == 1, "a measurement unit has its own logical binding"
    assert edges[0]["source"]["text_span"] == unit_span
    assert (edges[0]["right"]["subject"], edges[0]["right"]["attribute"]) == ("Lumen", "hold")


@pytest.mark.parametrize("actual,value,unit,value_span,unit_span", [
    ("Lumen holds 17万元.", "17", "万元", [12, 14], [14, 16]),
    ("Lumen holds 170000元.", "170000", "元", [12, 18], [18, 19]),
])
def test_numeric_proposition_preserves_real_subspans_and_exact_quantity_equivalence(actual, value, unit, value_span, unit_span):
    reference = "Lumen holds 17万元."
    required = compile_markdown(reference, sample_id="invented-proposition-boundaries")
    candidate = read_candidate_markdown(actual, sample_id="invented-proposition-boundaries")
    _quantity_source(required, reference, "17", "万元", [12, 14], [14, 16])
    _quantity_source(candidate, actual, value, unit, value_span, unit_span)
    score = grade_layers(required, candidate)
    assert score["layers"]["B"]["denominator"] == score["layers"]["B"]["numerator"] == 1
    assert score["layers"]["B"]["score"] == score["layers"]["L"]["score"] == 100
    if actual != reference:
        assert score["layers"]["T"]["score"] < 100
    else:
        assert score["layers"]["T"]["score"] == 100


def test_fronted_calendar_year_is_not_part_of_the_ownership_actor():
    text = "In 2028, Lumen owns Kappa."
    graph = _source_graph(text)
    assert not any("2028" in fact["subject"] or fact["subject"].startswith("In ") for fact in _facts(graph))
    if graph["semantic_complete"]:
        [fact] = _facts(graph)
        assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "own", "Kappa")
        assert fact["qualifiers"]["period"] == "2028"
        assert fact["qualifier_sources"]["period"]["text_span"] == [3, 7]
        assert fact["subject_source"]["text_span"] == [9, 14]
    else:
        _unresolved(graph, text)


def test_infinitive_how_to_phrase_is_not_an_asserted_actor():
    text = "How to acquire Kappa."
    graph = _source_graph(text)
    assert not any(fact["subject"] == "How to" for fact in _facts(graph))
    _unresolved(graph, text)


def test_quoted_and_is_not_decomposed_into_two_independent_ownership_objects():
    text = "Lumen owns 'Kappa and Sigma'."
    graph = _source_graph(text)
    assert graph["semantic_complete"] is True and not graph["unresolved"]
    [fact] = _facts(graph)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "own", "'Kappa and Sigma'")
    assert fact["value_source"]["text_span"] == [11, 28]
    [quote] = fact["quoted_nominals"]
    assert (quote["role"], quote["content"], quote["attachment"]) == ("object", "Kappa and Sigma", "whole_nominal")
    assert quote["source"]["text_span"] == [11, 28]
    assert quote["content_source"]["text_span"] == [12, 27]
    assert quote["opening_source"]["text_span"] == [11, 12]
    assert quote["closing_source"]["text_span"] == [27, 28]
    assert not any(node["kind"] == "semantic_operand" for node in graph["nodes"])
    assert "coordination_scope" not in graph["required_matcher_features"]
    # The independently validated nominal comparator now consumes this one
    # quoted name. Its internal AND still cannot manufacture a second fact.
    score = grade_layers(compile_markdown(text), read_candidate_markdown(text))
    assert score["layers"]["T"]["score"] == 100
    for layer in ("B", "L"):
        assert score["layers"][layer]["score"] == 100 and score["layers"][layer]["complete"] is True
    assert score["layers"]["B"]["denominator"] == 1
    assert score["publishable"] is True and score["score"] == 100
    changed = grade_layers(compile_markdown(text), read_candidate_markdown(text.replace("and", "or")))
    assert changed["layers"]["B"]["numerator"] == 0
