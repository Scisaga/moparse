"""Quoted nominal roles are not logical operators inside the quotation."""

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph

PATH = "<invented-quoted-nominals>"


def graph(text):
    source = {"path": PATH, "lines": [1, 1]}
    target = {"id": "printed:1", "kind": "text", "text": text, "raw_text": text, "raw": text,
        "reference": source, "cells": [], "parents": [], "has_children": False, "context": [],
        "selected_heading_context": [], "outside_selection_context": [], "pages": [1], "heading_level": None}
    return compile_requirement_graph({"sample_id": "invented-quoted-nominals", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": [target],
        "scope": [{"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]})


def business(material):
    nodes = {node["id"]: node for node in material["nodes"]}
    return [nodes[ident] for ident in material["projections"]["B"]]


def span(origin, bounds):
    assert origin["path"] == PATH and origin["lines"] == [1, 1]
    assert origin["text_span"] == bounds


def nominal(fact, role, raw, content, full_span, content_span):
    [proof] = [entry for entry in fact["quoted_nominals"] if entry["role"] == role]
    assert (proof["text"], proof["content"]) == (raw, content)
    span(proof["source"], full_span)
    span(proof["content_source"], content_span)
    span(proof["opening_source"], [full_span[0], content_span[0]])
    span(proof["closing_source"], [content_span[1], full_span[1]])


def complete(material):
    assert material["semantic_complete"] is True and not material["unresolved"]
    assert not [node for node in material["nodes"] if node["kind"] == "semantic_operand"]
    assert "quoted_nominal_scope" in material["required_matcher_features"]
    validate_requirement_graph(material)


def test_quoted_object_internal_and_is_one_actual_nominal_not_two_business_answers():
    material = graph('Lumen owns "Kappa and Sigma".')
    [fact] = business(material)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "own", '"Kappa and Sigma"')
    nominal(fact, "object", '"Kappa and Sigma"', "Kappa and Sigma", [11, 28], [12, 27])
    span(fact["value_source"], [11, 28])
    complete(material)


@pytest.mark.parametrize("text,value,bounds,content_bounds,polarity", [
    ('Lumen does not own "Kappa and Sigma".', '"Kappa and Sigma"', [19, 36], [20, 35], "negative"),
    ('Lumen owns "not Kappa and Sigma".', '"not Kappa and Sigma"', [11, 32], [12, 31], "positive"),
])
def test_only_the_printed_outer_negation_changes_the_assertion_polarity(text, value, bounds, content_bounds, polarity):
    material = graph(text)
    [fact] = business(material)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "own", value)
    assert fact["qualifiers"]["polarity"] == polarity
    nominal(fact, "object", value, value[1:-1], bounds, content_bounds)
    if polarity == "negative":
        span(fact["qualifier_sources"]["polarity"], [11, 14])
    complete(material)


def test_outer_and_has_two_members_while_inner_quoted_and_stays_inside_the_first_object():
    material = graph('Lumen owns "Kappa and Sigma" and "Omega".')
    facts = business(material)
    assert [(fact["subject"], fact["attribute"], fact["value"]) for fact in facts] == [
        ("Lumen", "own", '"Kappa and Sigma"'), ("Lumen", "own", '"Omega"')]
    nominal(facts[0], "object", '"Kappa and Sigma"', "Kappa and Sigma", [11, 28], [12, 27])
    nominal(facts[1], "object", '"Omega"', "Omega", [33, 40], [34, 39])
    complete(material)


def test_quoted_subject_is_one_actor_role_and_is_never_reused_as_an_object_member():
    material = graph('"Lumen and Vega" owns Kappa.')
    [fact] = business(material)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ('"Lumen and Vega"', "own", "Kappa")
    span(fact["subject_source"], [0, 16])
    span(fact["value_source"], [22, 27])
    nominal(fact, "subject", '"Lumen and Vega"', "Lumen and Vega", [0, 16], [1, 15])
    assert all(entry["role"] != "object" for entry in fact["quoted_nominals"])
    complete(material)


@pytest.mark.parametrize("text", [
    'Lumen owns "The Board Prohibits Exports".',
    'Lumen owns "Kappa Rejects Sigma".',
    'Lumen owns "Kappa Glorps Sigma".',
])
def test_failure_closed_title_case_does_not_prove_a_quoted_finite_clause_is_a_nominal(text):
    material = graph(text)
    assert material["semantic_complete"] is False
    assert business(material) == []
    assert any(issue["text"] == text and {"B", "L"} <= set(issue["layers"])
               for issue in material["unresolved"])
    assert any(source["text"] == text for source in material["sources"])


def test_internal_period_in_unknown_quoted_nominal_does_not_split_its_neighboring_assertion_source():
    text = 'Lumen owns "Kappa. Sigma". Vega acquires Omega.'
    material = graph(text)
    [fact] = business(material)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Vega", "acquire", "Omega")
    span(fact["subject_source"], [27, 31])
    span(fact["value_source"], [41, 46])
    assert material["semantic_complete"] is False
    assert any(issue["text"] == 'Lumen owns "Kappa. Sigma".' and {"B", "L"} <= set(issue["layers"])
               for issue in material["unresolved"])
    assert not any(source["kind"] == "fragment" and source["text"] == 'Lumen owns "Kappa.'
                   for source in material["sources"])


def test_outer_or_has_one_non_nominal_group_and_two_quoted_object_operands():
    text = 'Lumen owns "Kappa and Sigma" or "Omega".'
    material = graph(text)
    [group] = business(material)
    assert (group["subject"], group["attribute"], group["role"]) == ("Lumen", "logical_alternative", "logical_group")
    assert not group.get("quoted_nominals"), "the full OR proposition is not itself a quoted object"
    operands = [node for node in material["nodes"] if node["kind"] == "semantic_operand"]
    assert [(node["subject"], node["attribute"], node["value"]) for node in operands] == [
        ("Lumen", "own", '"Kappa and Sigma"'), ("Lumen", "own", '"Omega"')]
    nominal(operands[0], "object", '"Kappa and Sigma"', "Kappa and Sigma", [11, 28], [12, 27])
    nominal(operands[1], "object", '"Omega"', "Omega", [32, 39], [33, 38])
    assert not ({node["id"] for node in operands} & set(material["projections"]["B"]))
    assert material["semantic_complete"] is True and not material["unresolved"]
    assert {"quoted_nominal_scope", "alternative_membership"} <= set(material["required_matcher_features"])
    validate_requirement_graph(material)


def test_quoted_object_in_a_printed_field_body_keeps_its_own_nominal_and_field_sources():
    text = 'Description: Lumen owns "Kappa and Sigma".'
    material = graph(text)
    [fact] = business(material)
    assert (fact["subject"], fact["attribute"], fact["value"], fact["scope"]) == (
        "Lumen", "own", '"Kappa and Sigma"', ["Description"])
    span(fact["subject_source"], [13, 18])
    span(fact["value_source"], [24, 41])
    span(fact["field_label_evidence"]["source"], [0, 11])
    nominal(fact, "object", '"Kappa and Sigma"', "Kappa and Sigma", [24, 41], [25, 40])
    complete(material)


@pytest.mark.parametrize("downgrade_kind", [False, True])
def test_transport_guard_reconstructs_quote_requirements_even_when_proof_and_edges_are_removed(downgrade_kind):
    material = graph('Lumen owns "Kappa and Sigma".')
    validate_requirement_graph(material)
    [fact] = business(material)
    original_answer = fact["subject"], fact["attribute"], fact["value"]
    fact.pop("quoted_nominals")
    removed = {edge["id"] for edge in material["relations"] if edge["type"] == "narrative_quoted_nominal_scope"}
    assert removed
    material["relations"] = [edge for edge in material["relations"] if edge["id"] not in removed]
    material["projections"]["L"] = [ident for ident in material["projections"]["L"] if ident not in removed]
    for disposition in material["dispositions"]:
        for layer in disposition["layers"].values():
            layer["requirements"] = [ident for ident in layer["requirements"] if ident not in removed]
    if downgrade_kind:
        fact["logic"]["kind"] = "proposition"
        material["required_matcher_features"].remove("quoted_nominal_scope")
    assert (fact["subject"], fact["attribute"], fact["value"]) == original_answer
    with pytest.raises(ValueError, match="quoted|nominal|source|logic|scope"):
        validate_requirement_graph(material)
