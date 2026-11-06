"""Independent finite-reader boundary and real owning-graph source oracles."""

from copy import deepcopy

import pytest

from moparse_eval.proposition_requirements import read_propositions
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph

SOURCE = {"path": "<invented-nominal-owner>", "lines": [6, 6]}
TEXT = "Lumen provides an overview of policies and practices."


def expected(text):
    return {"sample_id": "invented-nominal-owner", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only",
        "scope": [{"lines": [6, 6], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}],
        "targets": [{"id": "body", "kind": "text", "text": text, "raw_text": text, "raw": text,
            "reference": SOURCE, "cells": [], "parents": [], "has_children": False, "context": [],
            "pages": [1], "selected_heading_context": [], "outside_selection_context": []}]}


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


@pytest.mark.parametrize("text", [
    TEXT,
    "Lumen provides an overview of policies or practices.",
    "The research section and the Governance Section below provide an overview of policies and practices.",
])
def test_finite_reader_does_not_forge_direct_objects_from_an_of_owned_nominal_conjunction(text):
    result = read_propositions(text, {**SOURCE, "text_span": [25, 25 + len(text)]})
    assert result["complete"] is False
    assert result["facts"] == []
    assert not any(edge["type"] == "proposition_coordination_scope" for edge in result["relations"])
    [pending] = result["pending_requirements"]
    assert pending["reason"] == "proposition_nominal_coordination_attachment_unresolved"
    assert pending["text"] == text
    assert pending["source"] == {**SOURCE, "text_span": [25, 25 + len(text)]}
    assert pending["layers"] == ["B", "L"]


def test_one_unread_nominal_clause_does_not_erase_independent_finite_neighbors():
    text = "Lumen owns Kappa and Sigma. " + TEXT + " Lumen pays Fee."
    result = read_propositions(text, SOURCE)
    assert result["complete"] is False
    assert [(fact["attribute"], fact["object"]) for fact in result["facts"]] == [
        ("own", "Kappa"), ("own", "Sigma"), ("pay", "Fee")]
    [pending] = result["pending_requirements"]
    assert pending["text"] == TEXT
    assert pending["source"]["text_span"] == [28, 81]
    assert text[28:81] == TEXT
    [group] = [edge for edge in result["relations"] if edge["type"] == "proposition_coordination_scope"]
    assert group["operator_source"]["text_span"] == [17, 20]
    assert group["right"]["member_count"] == 2


def test_source_bound_nominal_owner_keeps_one_direct_object_and_two_inner_members():
    reference = expected(TEXT)
    graph = compile_requirement_graph(reference)
    validate_requirement_graph(graph, expected=reference)
    assert graph["semantic_complete"] and graph["complete"]
    [business_id] = graph["projections"]["B"]
    [fact] = [node for node in graph["nodes"] if node["id"] == business_id]
    assert (fact["subject"], fact["attribute"], fact["object"]) == (
        "Lumen", "provide", "an overview of policies and practices")
    assert fact["object_source"]["text_span"] == [15, 52]
    assert TEXT[15:52] == "an overview of policies and practices"
    [membership] = [node for node in walk(graph["logic"]) if node.get("kind") == "coordination"]
    assert (membership["operator"], membership["mode"]) == ("and", "nominal_members")
    assert membership["operator_sources"] == [{**SOURCE, "text_span": [39, 42]}]
    assert [(child["head"], child["head_source"]["text_span"]) for child in membership["children"]] == [
        ("policies", [30, 38]), ("practices", [43, 52])]
    assert {edge["type"] for edge in graph["relations"]} == {
        "field_binding", "narrative_prepositional_attachment", "narrative_nominal_coordination_scope"}
    assert not any(edge["type"] == "proposition_coordination_scope" for edge in graph["relations"])


@pytest.mark.parametrize("mutation", ["member", "operator", "member_source", "attachment", "relation", "fact_source"])
def test_deferring_the_finite_reader_retains_independent_nominal_member_and_relation_guards(mutation):
    graph = compile_requirement_graph(expected(TEXT))
    changed = deepcopy(graph)
    membership = next(node for node in walk(changed["logic"]) if node.get("kind") == "coordination")
    if mutation == "member":
        membership["children"].pop()
    elif mutation == "operator":
        membership["operator"] = "or"
    elif mutation == "member_source":
        membership["children"][1]["head_source"]["text_span"] = [30, 38]
    elif mutation == "attachment":
        next(node for node in walk(changed["logic"]) if node.get("kind") == "prepositional_complement")["attachment"]["head"] = "policies"
    elif mutation == "relation":
        edge = next(edge for edge in changed["relations"] if edge["type"] == "narrative_nominal_coordination_scope")
        changed["relations"].remove(edge)
        changed["projections"]["L"].remove(edge["id"])
    else:
        fact = next(node for node in changed["nodes"] if node["id"] in changed["projections"]["B"])
        fact["object_source"]["text_span"] = [30, 38]
    with pytest.raises(ValueError):
        # No parser reconstruction or derived expected fixture supplies this
        # rejection: the serialized graph's own original source is decisive.
        validate_requirement_graph(changed)
