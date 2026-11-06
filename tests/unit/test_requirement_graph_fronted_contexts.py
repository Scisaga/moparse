"""Fronted nominal contexts have their own operators and exact boundaries."""

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph

PATH = "<invented-fronted-nominal-context>"


def graph(text):
    source = {"path": PATH, "lines": [1, 1]}
    target = {"id": "printed:1", "kind": "text", "text": text, "raw_text": text, "raw": text,
        "reference": source, "cells": [], "parents": [], "has_children": False, "context": [],
        "selected_heading_context": [], "outside_selection_context": [], "pages": [1], "heading_level": None}
    return compile_requirement_graph({"sample_id": "invented-fronted-nominal-context", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": [target],
        "scope": [{"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]})


def business(material):
    nodes = {node["id"]: node for node in material["nodes"]}
    return [nodes[ident] for ident in material["projections"]["B"]]


def span(origin, bounds):
    assert origin["path"] == PATH and origin["lines"] == [1, 1]
    assert origin["text_span"] == bounds


@pytest.mark.parametrize("text,subject,attribute,value,entry,pp_span,np_span,comma_span,actor_span,verb_span,value_span", [
    ('Under our “user first, AI-driven” strategy, we have sharpened our business focus.',
        "we", "sharpen", "our business focus",
        {"preposition": "Under", "operator": "under", "role": "context", "text": 'our “user first, AI-driven” strategy'},
        [0, 42], [6, 42], [42, 43], [44, 46], [52, 61], [62, 80]),
    ('In the retail sector, Lumen supports research.', "Lumen", "support", "research",
        {"preposition": "In", "operator": "in", "role": "domain", "text": "the retail sector"},
        [0, 20], [3, 20], [20, 21], [22, 27], [28, 36], [37, 45]),
])
def test_one_fronted_nominal_context_qualifies_only_one_child_assertion_with_its_own_sources(
        text, subject, attribute, value, entry, pp_span, np_span, comma_span, actor_span, verb_span, value_span):
    material = graph(text)
    [fact] = business(material)
    assert (fact["subject"], fact["attribute"], fact["value"]) == (subject, attribute, value)
    assert fact["qualifiers"]["fronted_contexts"] == [entry]
    assert "conditions" not in fact["qualifiers"] and "condition" not in fact["qualifiers"]
    [proof] = fact["qualifier_sources"]["fronted_contexts"]
    span(proof["preposition_source"], [0, len(entry["preposition"])])
    span(proof["context_source"], np_span)
    span(proof["separator_source"], comma_span)
    assert text[slice(*np_span)] == entry["text"]
    assert text[slice(*comma_span)] == ","
    span(fact["subject_source"], actor_span)
    span(fact["predicate_source"], verb_span)
    span(fact["value_source"], value_span)
    [tree] = material["logic"]
    assert tree["kind"] == "fronted_context" and tree["operator"] == entry["operator"]
    assert tree["child"], "the context must qualify the actual child, not become a second business assertion"
    span(tree["source"], [0, len(text) - 1])  # Sentence-final '.' is outside the expression scope.
    assert any(source["text"] == text for source in material["sources"])
    context_edges = [edge for edge in material["relations"] if edge["type"] == "narrative_fronted_context_scope"]
    assert len(context_edges) == 1
    assert "fronted_nominal_context" in material["required_matcher_features"]
    assert material["semantic_complete"] is True and not material["unresolved"]
    validate_requirement_graph(material)


@pytest.mark.parametrize("text", [
    "Under rules that prohibit exports, Lumen supports research.",
    "Under a rule unless Gate is open, Lumen supports research.",
    "Under rules hiding exports, Lumen supports research.",
    'Under our “user first, AI-driven strategy, Lumen supports research.',
])
def test_failure_closed_fronted_clausal_or_unclosed_context_is_not_a_nominal_domain(text):
    material = graph(text)
    assert material["semantic_complete"] is False
    assert business(material) == [], "unread restrictions cannot be dropped while asserting an unqualified child"
    assert any(issue["text"] == text and {"B", "L"} <= set(issue["layers"])
               for issue in material["unresolved"])
    assert any(source["text"] == text for source in material["sources"])
    atoms = [node for node in material["nodes"] if node["id"] in material["projections"]["T"]]
    assert "".join(atom["text"] for atom in atoms) == text
