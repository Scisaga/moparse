"""Independent finite post-predicate scope boundaries and admitted controls.

Uninterpreted English PP/scope tails remain pending even when a reader emits
their surface words inside an object. These invented fixtures do not introduce
an interpretation for those relations or use any saved candidate or corpus.
"""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.source_obligations import audit_source_obligations

PATH = "<invented-nominal-tail-scope>"
TAILS = [("after approval", "after"), ("before approval", "before"), ("upon approval", "upon"),
         ("pending approval", "pending"), ("subject to approval", "subject to"),
         ("under the contract", "under"), ("on approval", "on")]


def expected(text):
    return {"sample_id": "invented-nominal-tail-scope", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": [{"id": "printed:1", "kind": "text",
            "text": text, "raw_text": text, "raw": text, "reference": {"path": PATH, "lines": [1, 1]},
            "cells": [], "parents": [], "has_children": False, "context": [], "selected_heading_context": [],
            "outside_selection_context": [], "pages": [1], "heading_level": None}],
        "scope": [{"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]}


def business(graph):
    bank = {node["id"]: node for node in graph["nodes"]}
    return [bank[ident] for ident in graph["projections"]["B"]]


def scope_pending(graph, marker):
    [obligation] = [row for row in graph["source_obligation_inventory"]["obligations"]
                    if row["kind"] == "qualifier" and row["text"] == marker]
    [coverage] = [row for row in graph["source_obligation_coverage"]["dispositions"]
                  if row["obligation_id"] == obligation["id"]]
    assert coverage["status"] == "pending"
    assert set(coverage["layers"]) == {"B", "L"}
    return obligation


@pytest.mark.parametrize("tail,marker", TAILS)
def test_uninterpreted_scope_tail_cannot_become_semantically_complete_by_echoing_an_object(tail, marker):
    text = f"Lumen owns Kappa {tail}."
    authored = expected(text)
    original = deepcopy(authored)
    graph = compile_requirement_graph(authored)
    assert graph["semantic_complete"] is False and graph["complete"] is False
    obligation = scope_pending(graph, marker)
    assert obligation["source"]["text_span"] == [text.index(marker), text.index(marker) + len(marker)]
    assert text in "".join(node["text"] for node in graph["nodes"] if node["id"] in graph["projections"]["T"])
    # Preserve the transparent partial reading instead of deleting its source
    # words to make a guard pass. The independent scope obligation blocks use.
    if marker == "after":
        [fact] = business(graph)
        assert (fact["subject"], fact["attribute"], fact["object"]) == ("Lumen", "own", "Kappa after approval")
    validate_requirement_graph(graph, expected=authored)
    assert authored == original


@pytest.mark.parametrize("text,period", [("In 2028, Lumen owns Kappa.", "2028"),
                                        ("During 2028, Lumen owns Kappa.", "2028")])
def test_supported_fronted_temporal_scope_is_not_a_trailing_object_modifier(text, period):
    graph = compile_requirement_graph(expected(text))
    [fact] = business(graph)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "own", "Kappa")
    assert fact["qualifiers"]["period"] == period
    assert graph["semantic_complete"] is True
    assert any(edge["type"] == "qualifier_scope" and edge["left"].get("type") == "period" for edge in graph["relations"])
    validate_requirement_graph(graph)


def test_supported_fronted_under_context_retains_its_real_scope_relation():
    graph = compile_requirement_graph(expected("Under the strategy, Lumen owns Kappa."))
    [fact] = business(graph)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "own", "Kappa")
    assert fact["qualifiers"]["fronted_contexts"] == [{"preposition": "Under", "operator": "under",
                                                        "role": "context", "text": "the strategy"}]
    assert any(edge["type"] == "narrative_fronted_context_scope" for edge in graph["relations"])
    assert graph["semantic_complete"] is True
    validate_requirement_graph(graph)


@pytest.mark.parametrize("text,actor,action,value", [("Lumen owns Kappa.", "Lumen", "own", "Kappa"),
                                                   ("Vega acquires Sigma.", "Vega", "acquire", "Sigma")])
def test_explicit_atomic_objects_remain_supported_without_a_scope_tail(text, actor, action, value):
    graph = compile_requirement_graph(expected(text))
    [fact] = business(graph)
    assert (fact["subject"], fact["attribute"], fact["value"]) == (actor, action, value)
    assert graph["semantic_complete"] is True
    validate_requirement_graph(graph)


@pytest.mark.parametrize("value", ['"After"', '"Under and On"', '"Before or After"'])
def test_closed_class_words_inside_source_proved_quoted_names_do_not_create_outer_scope(value):
    graph = compile_requirement_graph(expected(f"Lumen owns {value}."))
    [fact] = business(graph)
    assert (fact["attribute"], fact["value"]) == ("own", value)
    assert fact["quoted_nominals"][0]["text"] == value
    assert graph["semantic_complete"] is True
    assert not any(row["kind"] == "qualifier" for row in graph["source_obligation_inventory"]["obligations"])
    validate_requirement_graph(graph)


@pytest.mark.parametrize("value", ["Under and On", "Kappa after approval", "Kappa subject to approval"])
def test_a_source_declared_Name_field_keeps_its_literal_value_without_manufacturing_a_predicate(value):
    graph = compile_requirement_graph(expected("Name: " + value))
    [fact] = business(graph)
    assert (fact["attribute"], fact["value"], fact["role"]) == ("Name", value, "identity")
    assert not fact.get("predicate")
    assert graph["semantic_complete"] is True
    assert not any(row["kind"] == "qualifier" for row in graph["source_obligation_inventory"]["obligations"])
    validate_requirement_graph(graph)


@pytest.mark.parametrize("role", ["modality", "polarity"])
def test_an_unsupported_scope_token_cannot_be_relabelled_as_a_known_operator(role):
    graph = compile_requirement_graph(expected("Lumen owns Kappa after approval."))
    obligation = scope_pending(graph, "after")
    [fact] = business(graph)
    origin = deepcopy(obligation["source"])
    fact["qualifier_sources"][role] = origin
    graph["relations"].append({"id": "L:forged-scope", "type": "qualifier_scope",
        "left": {"type": role, "text": "after"}, "right": {"subject": "Lumen", "attribute": "own"},
        "source": origin, "operator_source": origin,
        "binding_evidence": {"operator_source": origin}})
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    scope_pending(graph, "after")
    assert graph["source_obligation_coverage"]["semantic_complete"] is False


@pytest.mark.parametrize("borrow_neighbor", [False, True], ids=["shortened-own-object", "clean-neighbor-object"])
def test_synchronized_object_source_edits_cannot_remove_the_original_uninterpreted_scope_obligation(borrow_neighbor):
    text = "Lumen owns Kappa after approval." + (" Vega owns Kappa." if borrow_neighbor else "")
    graph = compile_requirement_graph(expected(text))
    facts = business(graph)
    fact = next(row for row in facts if row["subject"] == "Lumen")
    original_T = deepcopy([node for node in graph["nodes"] if node["id"] in graph["projections"]["T"]])
    if borrow_neighbor:
        clean = next(row for row in facts if row["subject"] == "Vega")
        origin = deepcopy(clean["object_source"])
    else:
        origin = {"path": PATH, "lines": [1, 1], "text_span": [11, 16]}
    fact.update(object="Kappa", value="Kappa", object_source=deepcopy(origin), value_source=deepcopy(origin))
    for edge in graph["relations"]:
        if edge.get("fact_id") == fact["id"] or edge.get("right", {}).get("subject") == "Lumen":
            proof = edge.get("binding_evidence", {})
            for key in ("object_source", "value_source"):
                if key in proof:
                    proof[key] = deepcopy(origin)
    graph["unresolved"] = []
    graph["semantic_complete"] = graph["complete"] = True
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False
    scope_pending(graph, "after")
    assert [node for node in graph["nodes"] if node["id"] in graph["projections"]["T"]] == original_T
