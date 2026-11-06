"""Opaque objects cannot erase a printed condition, duration or causal scope."""

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph


def expected(text):
    return {"sample_id": "invented-unparsed-modifier", "targets": [{"id": "source:1", "kind": "text",
        "text": text, "raw_text": text, "raw": text,
        "reference": {"path": "<independent-unparsed-modifier>", "lines": [1, 1]},
        "cells": [], "parents": [], "has_children": False, "context": [],
        "selected_heading_context": [], "outside_selection_context": []}]}


@pytest.mark.parametrize("body,marker", [("Lumen owns Kappa when authorized.", "when"),
    ("Lumen owns Kappa until revoked.", "until"),
    ("Lumen owns Kappa because Sigma approved.", "because")])
@pytest.mark.parametrize("prefix", ["", "Name: Lumen; Description: "])
def test_a_whole_object_echo_does_not_explain_an_unparsed_scope(body, marker, prefix):
    text = prefix + body
    reference = expected(text)
    graph = compile_requirement_graph(reference)
    assert graph["semantic_complete"] is False
    scopes = [item for item in graph["source_obligation_inventory"]["obligations"]
              if item["kind"] == "qualifier" and item["text"] == marker]
    assert len(scopes) == 1
    a, b = scopes[0]["source"]["text_span"]
    assert text[a:b] == marker
    assert any(row["obligation_id"] == scopes[0]["id"] and row["status"] == "pending"
               for row in graph["source_obligation_coverage"]["dispositions"])
    assert body in "".join(node["text"] for node in graph["nodes"] if node["id"] in graph["projections"]["T"])
    validate_requirement_graph(graph, expected=reference)


@pytest.mark.parametrize("text", ["Lumen owns Kappa.", "Role: Founder and Chairman",
    "URL: https://example.invalid/when?since=2028", "Name: Since; Revenue: 17"])
def test_actual_atomic_fields_keep_their_own_punctuation_and_names(text):
    graph = compile_requirement_graph(expected(text))
    assert graph["semantic_complete"] is True
    validate_requirement_graph(graph)
