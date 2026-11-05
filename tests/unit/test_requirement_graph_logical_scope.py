"""Independent bounded counterexamples for mixed-source and logical scope."""

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.requirement_graph import compile_requirement_graph
from moparse_eval.three_layer import compile_expected, grade_layers, read_candidate


def _expected(text):
    target = {"id": "printed:1", "kind": "text", "text": text, "raw_text": text, "raw": text,
              "reference": {"path": "<invented-logical-scope>", "lines": [1, 1]}, "cells": [],
              "parents": [], "has_children": False, "context": [], "selected_heading_context": [],
              "outside_selection_context": [], "pages": [1], "heading_level": None}
    return {"sample_id": "invented-logical-scope", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": [target],
        "scope": [{"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]}


def _graph(text):
    return compile_requirement_graph(_expected(text))


def _facts(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return [nodes[ident] for ident in graph["projections"]["B"]]


def _text(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return "".join(nodes[ident]["text"] for ident in graph["projections"]["T"])


def test_failure_closed_contract_unresolved_negation_group_is_not_distributed_into_independent_claims():
    text = "Board shall not review and approve Report."
    # Negating a conjunction does not assert that each member is prohibited;
    # a disjunction likewise does not assert that both actors act. The current
    # finite graph grammar needs a whole-group pending requirement here.
    graph = _graph(text)
    assert graph["semantic_complete"] is False
    assert _facts(graph) == []
    assert any(item.get("text", "").rstrip(".") == text.rstrip(".")
               and {"B", "L"} <= set(item["layers"]) for item in graph["unresolved"])
    assert _text(graph) == text


def test_complete_disjunction_has_one_group_and_two_nonasserted_members_but_matcher_stays_blocked():
    text = "Board shall review Report or Clerk shall approve Budget."
    graph = _graph(text)
    assert graph["semantic_complete"] is True and graph["complete"] is True
    [group] = _facts(graph)
    assert (group["subject"], group["attribute"], group["role"]) == ("", "logical_alternative", "logical_group")
    assert group["qualifiers"]["coordination"] == "or"
    assert group["predicate_source"]["text_span"] == [26, 28]
    operands = [node for node in graph["nodes"] if node["kind"] == "semantic_operand"]
    assert [(node["subject"], node["attribute"], node["value"]) for node in operands] == [
        ("Board", "review", "Report"), ("Clerk", "approve", "Budget")]
    assert all(node["semantic_role"] == "operand" and node["qualifiers"]["modality"] == "shall" for node in operands)
    assert not ({node["id"] for node in operands} & set(graph["projections"]["B"]))
    assert not any(edge["type"] == "field_binding" and edge["right"]["subject"] in {"Board", "Clerk"}
                   for edge in graph["relations"])
    actual = read_candidate(markdown_observation(text, sample_id="invented-logical-scope", pipeline="test", pages=[1]))
    score = grade_layers(compile_expected(_expected(text)), actual)
    assert score["layers"]["T"]["score"] == 100
    for layer in ("B", "L"):
        assert score["layers"][layer]["score"] is None and score["layers"][layer]["complete"] is False
    assert score["publishable"] is False and score["score"] is None
    assert any(block["reason"] == "narrative_comparison_features_not_validated" for block in score["blockers"])


def test_failure_closed_contract_one_identity_field_cannot_swallow_a_separate_known_relation():
    text = "Name: Delta; Board approves Dividend."
    graph = _graph(text)
    facts = _facts(graph)
    assert not any(fact["role"] == "identity" and "approves" in fact["value"] for fact in facts)
    if graph["semantic_complete"]:
        assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in facts] == [
            ("", "Name", "Delta", "identity"), ("Board", "approve", "Dividend", "description")]
    else:
        assert any("approves Dividend" in item.get("text", "") and {"B", "L"} <= set(item["layers"])
                   for item in graph["unresolved"])
    assert all(fragment in _text(graph) for fragment in ("Name", "Delta", "Board approves Dividend"))
