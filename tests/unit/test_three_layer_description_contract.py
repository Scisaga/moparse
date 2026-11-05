"""Printed Description is a field scope, not one opaque metric answer."""

from copy import deepcopy

import pytest

from moparse_eval.business_correspondence import identity_checks, query_for
from moparse_eval.expected_readback import markdown_observation
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.three_layer import canonical, compile_expected, grade_layers, read_candidate


def _expected(text):
    return {"sample_id": "invented-description-body", "document_id": "invented-document", "source_pages": [1],
            "standard": "expected_only", "scope": [{"lines": [1, 1], "pages": [1],
                "declared_source_pages": [1], "outside_source_pages": []}],
            "targets": [{"id": "printed:1", "kind": "text", "text": text, "raw_text": text, "raw": text,
                         "reference": {"path": "<invented-description-body>", "lines": [1, 1]}, "cells": [],
                         "parents": [], "has_children": False, "context": [], "selected_heading_context": [],
                         "outside_selection_context": [], "pages": [1], "heading_level": None}]}


def _business(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return [nodes[ident] for ident in graph["projections"]["B"]]


@pytest.mark.parametrize("text,wanted,label_span,value_spans", [
    ("Description: Lumen owns Kappa. Lumen acquires Sigma.",
     [("Lumen", "own", "Kappa", "description"), ("Lumen", "acquire", "Sigma", "description")],
     [0, 11], [[24, 29], [46, 51]]),
    ("Name: Anchor; Description: Lumen owns Kappa.",
     [("", "Name", "Anchor", "identity"), ("Lumen", "own", "Kappa", "description")],
     [14, 25], [[38, 43]]),
], ids=["two-statements", "identity-and-description-field"])
def test_description_field_keeps_actual_assertions_and_printed_scope_or_explicit_whole_pending(
        text, wanted, label_span, value_spans):
    expected = _expected(text)
    graph = compile_requirement_graph(expected)
    facts = _business(graph)
    nodes = {node["id"]: node for node in graph["nodes"]}
    literals = "".join(nodes[ident]["text"] for ident in graph["projections"]["T"])
    assert "Description" in literals and "owns" in literals and "Kappa" in literals
    assert literals.count("Lumen") == len(value_spans)
    if len(value_spans) == 2:
        assert "acquires" in literals and "Sigma" in literals
    else:
        assert "Name" in literals and "Anchor" in literals
    assert not any(fact["attribute"] == "Description" and fact["role"] == "metric" for fact in facts), (
        "a supported assertion body is not a new opaque Description metric")
    if not graph["semantic_complete"]:
        assert any({"B", "L"} <= set(item["layers"]) and "Lumen owns Kappa" in item.get("text", "")
                   for item in graph["unresolved"])
        return
    assert [(fact["subject"], fact["attribute"], fact["value"], fact["role"]) for fact in facts] == wanted
    statements = [fact for fact in facts if fact["role"] == "description"]
    assert len(statements) == len(value_spans)
    for fact, value_span in zip(statements, value_spans, strict=True):
        assert fact["scope"][-1] == "Description"
        assert fact["printed_label"] == "Description"
        assert fact["label_source"]["text_span"] == label_span
        assert text[slice(*label_span)] == "Description"
        assert fact["value_source"]["text_span"] == value_span
        assert text[slice(*value_span)] == fact["value"]
    actual = read_candidate(markdown_observation(text, sample_id="invented-description-body", pipeline="test", pages=[1]))
    result = grade_layers(compile_expected(expected), actual)
    assert result["layers"]["B"]["denominator"] == result["layers"]["B"]["numerator"] == len(wanted)
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    for row in result["outcomes"]:
        if row["layer"] == "B" and row["expected"]["role"] == "description":
            assert row["expected"]["value"] not in repr(row["retrieval"]["query"])


@pytest.mark.parametrize("text,attribute,value,role", [
    ("Location: https://example.test/A2028?time=9:00", "Location", "https://example.test/A2028?time=9:00", "metric"),
    ("Date and time: 2028-05-07 9:00", "Date and time", "2028-05-07 9:00", "metric"),
    ("Name: Delta A. Kappa; Holdings Ltd.", "Name", "Delta A. Kappa; Holdings Ltd.", "identity"),
])
def test_metadata_value_punctuation_remains_inside_its_legal_field(text, attribute, value, role):
    graph = compile_requirement_graph(_expected(text))
    [fact] = _business(graph)
    assert (fact["attribute"], fact["value"], fact["role"]) == (attribute, value, role)
    assert fact["qualifiers"] == {}
    source = fact["value_source"]["text_span"]
    assert text[slice(*source)] == value
    assert graph["semantic_complete"] is True and not graph["unresolved"]


@pytest.mark.parametrize("layer", ["B", "L"])
def test_source_completeness_detects_a_synchronized_omission_while_all_text_stays(layer):
    text = "Description: Lumen owns Kappa. Lumen acquires Sigma."
    expected = _expected(text)
    graph = compile_requirement_graph(expected)
    assert len(_business(graph)) == 2 and graph["semantic_complete"] is True
    by_id = {node["id"]: node for node in graph["nodes"]}
    original_text = deepcopy([by_id[ident] for ident in graph["projections"]["T"]])
    if layer == "B":
        [removed] = [fact for fact in _business(graph) if fact["attribute"] == "acquire"]
        # Preserve the stored node and every relation: the attack removes its
        # required vote, not a node that would leave a trivial dangling edge.
    else:
        [removed] = [edge for edge in graph["relations"] if edge["type"] == "field_binding"
                     and edge["right"]["attribute"] == "acquire"]
        graph["relations"].remove(removed)
    graph["projections"][layer].remove(removed["id"])
    remaining = graph["projections"][layer][0]
    for row in graph["dispositions"]:
        disposition = row["layers"][layer]
        if removed["id"] in disposition["requirements"]:
            disposition["requirements"].remove(removed["id"])
            if not disposition["requirements"]:
                # Even a nonempty synchronized declaration must not borrow a
                # first-statement requirement to cover the second statement.
                disposition["requirements"] = [remaining]
    assert [by_id[ident] for ident in graph["projections"]["T"]] == original_text
    with pytest.raises(ValueError):
        validate_requirement_graph(graph)
    with pytest.raises(ValueError):
        validate_requirement_graph(graph, expected=expected)


@pytest.mark.parametrize("synchronize_statement_source", [False, True], ids=["label-only", "label-and-whole-source"])
def test_same_line_field_proof_cannot_borrow_a_neighboring_identical_label(synchronize_statement_source):
    text = "Description: Lumen owns Kappa.; Description: Lumen acquires Sigma."
    expected = compile_expected(_expected(text))
    actual = read_candidate(markdown_observation(text, sample_id="invented-description-body", pipeline="test", pages=[1]))
    [required] = [fact for fact in expected["business"] if fact["attribute"] == "own"]
    [original] = [fact for fact in actual["business"] if fact["attribute"] == "own"]
    [neighbor] = [fact for fact in actual["business"] if fact["attribute"] == "acquire"]
    options = {"contexts": actual["native_context"], "declared_paths": expected["scope_schema"]["paths"],
               "context_labels": expected["scope_schema"]["context_labels"]}
    assert identity_checks(query_for(required), original, canonical, **options)["scope"]["correct"] is True
    forged = deepcopy(original)
    forged["field_label_evidence"] = deepcopy(neighbor["field_label_evidence"])
    forged["label_source"] = deepcopy(neighbor["label_source"])
    if synchronize_statement_source:
        forged["source"] = deepcopy(neighbor["source"])
    # Both prefixes really print Description in the same block. The original
    # predicate/object sources still belong to the first field's actual body.
    assert forged["field_label_evidence"]["text"] == "Description"
    assert forged["value_source"] == original["value_source"]
    assert identity_checks(query_for(required), forged, canonical, **options)["scope"]["correct"] is False
