"""Hand-fixed compositional semantics through the expected graph and core.

Reading a complete source AST is separate from validating its B/L matcher.
These tests supply their own target sets, meanings and literal source spans.
"""

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.requirement_graph import compile_requirement_graph
from moparse_eval.three_layer import compile_expected, grade_layers, read_candidate


def _expected(text):
    return {"sample_id": "invented-narrative-integration", "document_id": "invented-document",
            "source_pages": [1], "standard": "expected_only",
            "scope": [{"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}],
            "targets": [{"id": "printed:1", "kind": "text", "text": text, "raw_text": text, "raw": text,
                         "reference": {"path": "<invented-narrative-integration>", "lines": [1, 1]}, "cells": [],
                         "parents": [], "has_children": False, "context": [], "selected_heading_context": [],
                         "outside_selection_context": [], "pages": [1], "heading_level": None}]}


def _business(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return [nodes[ident] for ident in graph["projections"]["B"]]


def _operands(graph):
    operands = [node for node in graph["nodes"] if node["kind"] == "semantic_operand"]
    assert not ({node["id"] for node in operands} & set(graph["projections"]["B"]))
    assert all((edge["right"]["subject"], edge["right"]["attribute"])
               not in {(node["subject"], node["attribute"]) for node in operands}
               for edge in graph["relations"] if edge["type"] == "field_binding")
    return operands


def _span(source, expected, text, literal):
    assert source["path"] == "<invented-narrative-integration>"
    assert source["lines"] == [1, 1]
    assert source["text_span"] == expected
    assert text[slice(*expected)] == literal


def _compare_same_text(text):
    required = compile_expected(_expected(text))
    observation = markdown_observation(text, sample_id="invented-narrative-integration", pipeline="test", pages=[1])
    actual = read_candidate(observation)
    return grade_layers(required, actual)


def _comparison_remains_unvalidated(text):
    result = _compare_same_text(text)
    assert result["layers"]["T"]["score"] == 100
    assert result["layers"]["T"]["complete"] is True
    for layer in ("B", "L"):
        assert result["layers"][layer]["score"] is None
        assert result["layers"][layer]["complete"] is False
    assert result["score"] is None and result["publishable"] is False
    assert any(item["reason"] == "narrative_comparison_features_not_validated"
               and {"B", "L"} <= set(item["layers"]) for item in result["blockers"])


def test_two_conditions_are_operands_of_one_main_business_requirement_with_independent_sources():
    text = "If Gate is open, Board may pay Fee unless Permit is valid."
    graph = compile_requirement_graph(_expected(text))
    assert graph["semantic_complete"] is True and graph["complete"] is True and not graph["unresolved"]
    [main] = _business(graph)
    assert (main["subject"], main["attribute"], main["value"]) == ("Board", "pay", "Fee")
    assert main["qualifiers"]["modality"] == "may"
    assert main["qualifiers"]["conditions"] == [
        {"operator": "if", "operand": {"subject": "Gate", "attribute": "be", "value": "open", "polarity": "positive", "tense": "present"}},
        {"operator": "unless", "operand": {"subject": "Permit", "attribute": "be", "value": "valid", "polarity": "positive", "tense": "present"}}]
    operands = _operands(graph)
    assert [(node["subject"], node["attribute"], node["value"]) for node in operands] == [
        ("Gate", "be", "open"), ("Permit", "be", "valid")]
    assert all(node["semantic_role"] == "operand"
               and node["qualifiers"]["assertion_context"] == "condition_operand" for node in operands)
    sources = main["qualifier_sources"]["conditions"]
    assert len(sources) == 2
    _span(sources[0]["operator_source"], [0, 2], text, "If")
    _span(sources[0]["operand_source"], [3, 15], text, "Gate is open")
    _span(sources[1]["operator_source"], [35, 41], text, "unless")
    _span(sources[1]["operand_source"], [42, 57], text, "Permit is valid")
    _span(main["subject_source"], [17, 22], text, "Board")
    _span(main["value_source"], [31, 34], text, "Fee")
    assert len(graph["operand_relations"]) == 2
    assert {edge["right"]["subject"] for edge in graph["operand_relations"]} == {"Gate", "Permit"}
    _comparison_remains_unvalidated(text)


def test_compound_condition_keeps_outer_if_and_inner_and_as_separate_operators():
    text = "If Gate is open and Permit is valid, Board may pay Fee."
    graph = compile_requirement_graph(_expected(text))
    assert graph["semantic_complete"] is True and graph["complete"] is True and not graph["unresolved"]
    [main] = _business(graph)
    assert (main["subject"], main["attribute"], main["value"]) == ("Board", "pay", "Fee")
    assert main["qualifiers"]["conditions"] == [{"operator": "if", "operand": {
        "operator": "and", "operands": [
            {"subject": "Gate", "attribute": "be", "value": "open", "polarity": "positive", "tense": "present"},
            {"subject": "Permit", "attribute": "be", "value": "valid", "polarity": "positive", "tense": "present"}]}}]
    assert [(node["subject"], node["attribute"], node["value"]) for node in _operands(graph)] == [
        ("Gate", "be", "open"), ("Permit", "be", "valid")]
    [condition] = main["qualifier_sources"]["conditions"]
    _span(condition["operator_source"], [0, 2], text, "If")
    _span(condition["operand_source"], [3, 35], text, "Gate is open and Permit is valid")
    _span(main["value_source"], [51, 54], text, "Fee")
    [condition_edge] = [edge for edge in graph["relations"] if edge["type"] == "narrative_condition_scope"]
    assert condition_edge["left"]["operator"] == "if", "an operand's AND cannot replace its enclosing IF"
    _comparison_remains_unvalidated(text)


def test_reported_negative_child_is_one_qualified_requirement_with_separate_reporter_and_child_sources():
    text = "Auditor reported that Lumen is not solvent."
    graph = compile_requirement_graph(_expected(text))
    assert graph["semantic_complete"] is True and graph["complete"] is True and not graph["unresolved"]
    [main] = _business(graph)
    assert (main["subject"], main["attribute"], main["value"]) == ("Lumen", "be", "solvent")
    assert main["qualifiers"]["reporting"] == [
        {"subject": "Auditor", "attribute": "report", "polarity": "positive", "tense": "past"}]
    assert main["qualifiers"]["polarity"] == "negative"
    assert main["qualifiers"]["tense"] == "present"
    assert main["qualifiers"]["assertion_context"] == "reported"
    assert _operands(graph) == []
    [report] = main["qualifier_sources"]["reporting"]
    _span(report["speaker_source"], [0, 7], text, "Auditor")
    _span(report["predicate_source"], [8, 16], text, "reported")
    _span(report["tense_source"], [8, 16], text, "reported")
    _span(main["subject_source"], [22, 27], text, "Lumen")
    _span(main["qualifier_sources"]["tense"], [28, 30], text, "is")
    _span(main["qualifier_sources"]["polarity"], [31, 34], text, "not")
    _span(main["value_source"], [35, 42], text, "solvent")
    _comparison_remains_unvalidated(text)


def test_or_is_one_logical_group_with_two_members_while_and_has_two_independent_requirements():
    disjunction = "Lumen owns Kappa or Sigma."
    conjunction = "Lumen owns Kappa and Sigma."
    alternatives = compile_requirement_graph(_expected(disjunction))
    conjuncts = compile_requirement_graph(_expected(conjunction))
    for graph in (alternatives, conjuncts):
        assert graph["semantic_complete"] is True and graph["complete"] is True and not graph["unresolved"]
    [group] = _business(alternatives)
    assert (group["subject"], group["attribute"], group["role"]) == ("Lumen", "logical_alternative", "logical_group")
    assert group["qualifiers"]["coordination"] == "or"
    assert [(node["subject"], node["attribute"], node["value"]) for node in _operands(alternatives)] == [
        ("Lumen", "own", "Kappa"), ("Lumen", "own", "Sigma")]
    _span(group["predicate_source"], [17, 19], disjunction, "or")
    assert [(node["subject"], node["attribute"], node["value"]) for node in _business(conjuncts)] == [
        ("Lumen", "own", "Kappa"), ("Lumen", "own", "Sigma")]
    assert _operands(conjuncts) == []
    _comparison_remains_unvalidated(disjunction)
    # The ordinary positive AND path predates the new nested/OR matcher. Its
    # independent assertions stay comparable under the existing validation.
    compared = _compare_same_text(conjunction)
    assert compared["layers"]["B"]["denominator"] == compared["layers"]["B"]["numerator"] == 2
    for layer in ("T", "B", "L"):
        assert compared["layers"][layer]["score"] == 100
        assert compared["layers"][layer]["complete"] is True
    assert compared["publishable"] is True
