"""Source-proof counterexamples for misplaced OR and quantified comparatives."""

import pytest

from moparse_eval.narrative_requirements import read_narrative
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph

SOURCE = {"path": "<invented-enumeration-proof>", "lines": [5, 5]}


def graph(text):
    target = {"id": "printed:5", "kind": "text", "text": text, "raw_text": text, "raw": text,
              "reference": SOURCE, "cells": [], "parents": [], "has_children": False, "context": [],
              "selected_heading_context": [], "outside_selection_context": [], "pages": [1], "heading_level": None}
    return compile_requirement_graph({"sample_id": "invented-enumeration-proof", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": [target], "scope": []})


@pytest.mark.parametrize("text", [
    "Lumen includes Alpha, Beta or Gamma, matching limits.",
    "Lumen includes Alpha and Beta, matching limits.",
    "The licensing rule will include Alpha, Beta or Gamma, matching limits.",
    "Orion held 3 or more contracts, with a 91% retention rate.",
    "Orion held 3 or more contracts.",
    "Orion held 3 or fewer contracts.",
    "Orion held 3 or less debt.",
    "Lumen may hold 3 or more contracts, with a retention rate.",
])
def test_unknown_comma_attachment_and_comparative_or_do_not_forge_object_alternatives(text):
    result = read_narrative(text, SOURCE)
    assert result["complete"] is False and result["facts"] == [] and result["semantic_operands"] == []
    assert any(u["text"].rstrip(".") == text.rstrip(".") for u in result["unresolved"])
    material = graph(text)
    assert material["semantic_complete"] is False
    assert not material["projections"]["B"]
    validate_requirement_graph(material)


@pytest.mark.parametrize("operator", ["and", "or"])
def test_a_real_final_enumeration_connector_keeps_its_own_three_members_and_source_proof(operator):
    text = f"Lumen includes Alpha, Beta {operator} Gamma."
    result = read_narrative(text, {**SOURCE, "text_span": [40, 40 + len(text)]})
    assert result["complete"] is True
    if operator == "and":
        assert [(f["subject"], f["attribute"], f["value"]) for f in result["facts"]] == [
            ("Lumen", "include", "Alpha"), ("Lumen", "include", "Beta"), ("Lumen", "include", "Gamma")]
    else:
        assert len(result["facts"]) == 1 and result["facts"][0]["role"] == "logical_group"
        assert [(f["subject"], f["attribute"], f["value"]) for f in result["semantic_operands"]] == [
            ("Lumen", "include", "Alpha"), ("Lumen", "include", "Beta"), ("Lumen", "include", "Gamma")]
    validate_requirement_graph(graph(text))


def test_source_guard_still_rejects_and_or_relabelling_of_a_valid_enumeration():
    material = graph("Lumen includes Alpha, Beta or Gamma.")
    validate_requirement_graph(material)
    material["logic"][0]["operator"] = "and"
    with pytest.raises(ValueError, match="operator|source"):
        validate_requirement_graph(material)
