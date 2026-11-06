"""Invented AND groups with independently declared operator/member ranges."""

from copy import deepcopy

import pytest

from moparse_eval.proposition_requirements import (
    read_propositions,
    validate_proposition_coordinations,
)
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.three_layer import compile_markdown

SOURCE = {"path": "<invented-and-groups>", "lines": [6, 6]}


@pytest.mark.parametrize("text,mode,operators,members", [
    ("Lumen owns Kappa and Sigma.", "objects", [[17, 20]], [([6, 10], [11, 16]), ([6, 10], [21, 26])]),
    ("Lumen reviews Report and approves Notice.", "actions", [[21, 24]], [([6, 13], [14, 20]), ([25, 33], [34, 40])]),
    ("Lumen reviews and approves Report.", "actions", [[14, 17]], [([6, 13], [27, 33]), ([18, 26], [27, 33])]),
])
def test_finite_and_groups_retain_literal_operator_and_each_member_role_without_answer_location_keys(text, mode, operators, members):
    result = read_propositions(text, SOURCE, scope=["North"])
    assert result["complete"] is True
    assert result["required_matcher_features"] == ["coordination_scope"]
    groups = [edge for edge in result["relations"] if edge["type"] == "proposition_coordination_scope"]
    assert len(groups) == len(operators)
    for edge, operator in zip(groups, operators, strict=True):
        assert edge["source"]["text_span"] == operator
        assert edge["operator_source"] == edge["source"]
        assert edge["left"]["mode"] == mode and edge["left"]["operator"] == "and"
        assert text[slice(*operator)] == "and"
        assert edge["right"]["member_count"] == 2 and edge["right"]["scope"] == ["North"]
        assert "Kappa" not in repr(edge["left"]) + repr(edge["right"])
        assert [(member["predicate_source"]["text_span"], member["object_source"]["text_span"])
                for member in edge["binding_evidence"]["members"]] == members
        assert all(member["subject_source"]["text_span"] == [0, 5] for member in edge["binding_evidence"]["members"])


def test_every_connector_in_three_members_has_its_own_position_and_full_group_evidence():
    text = "Lumen owns Kappa and Sigma and Tau."
    result = read_propositions(text, SOURCE)
    groups = [edge for edge in result["relations"] if edge["type"] == "proposition_coordination_scope"]
    assert [edge["source"]["text_span"] for edge in groups] == [[17, 20], [27, 30]]
    assert [edge["left"]["position"] for edge in groups] == [0, 1]
    assert all(len(edge["binding_evidence"]["members"]) == edge["right"]["member_count"] == 3 for edge in groups)


def test_modal_and_members_have_separate_operator_to_member_scope_evidence():
    text = "Board shall review Report and Budget."
    result = read_propositions(text, SOURCE)
    assert result["complete"] and len(result["facts"]) == 2
    modals = [edge for edge in result["relations"] if edge["type"] == "qualifier_scope"]
    assert len(modals) == 2
    assert all(edge["left"] == {"type": "modality", "text": "shall"} for edge in modals)
    assert all(edge["source"]["text_span"] == [6, 11] for edge in modals)
    assert [edge["binding_evidence"]["object_source"]["text_span"] for edge in modals] == [[19, 25], [30, 36]]
    assert all(edge["right"]["subject"] == "Board" and edge["right"]["attribute"] == "review" for edge in modals)


def test_single_negative_proposition_retains_both_actual_modal_and_negative_operator_cuts():
    result = read_propositions("Board may not review Report.", SOURCE)
    operators = [edge for edge in result["relations"] if edge["type"] == "qualifier_scope"]
    assert [(edge["left"], edge["source"]["text_span"]) for edge in operators] == [
        ({"type": "modality", "text": "may"}, [6, 9]), ({"type": "polarity", "text": "negative"}, [10, 13])]


@pytest.mark.parametrize("text", [
    "Lumen owns Kappa or Sigma.", "Lumen reviews Report or approves Notice.",
    "Lumen does not own Kappa and Sigma.", 'Lumen owns "Kappa and Sigma".',
])
def test_unadmitted_or_negative_and_quoted_forms_do_not_gain_asserted_and_relations(text):
    result = read_propositions(text, SOURCE)
    assert result["complete"] is False and result["blockers"]
    assert not any(edge["type"] == "proposition_coordination_scope" for edge in result["relations"])


def test_public_reader_preserves_the_required_comparison_gate_for_the_new_group_relation():
    result = compile_markdown("Lumen owns Kappa and Sigma.")
    assert "coordination_scope" in result["required_matcher_features"]
    [group] = [edge for edge in result["relations"] if edge["type"] == "proposition_coordination_scope"]
    assert group["operator_source"]["text_span"] == [17, 20]


@pytest.mark.parametrize("mutation", ["relation", "operator", "member_source", "member_fact", "synchronized"])
def test_source_derived_guard_rejects_and_group_projection_and_member_mutations(mutation):
    text = "Lumen owns Kappa and Sigma."
    parsed = read_propositions(text, SOURCE)
    fields = deepcopy(parsed["facts"])
    transport = {"sources": [{"text": text, "source": SOURCE}],
        "required_matcher_features": deepcopy(parsed["required_matcher_features"]), "relations": deepcopy(parsed["relations"])}

    def literal(source):
        a, b = source["text_span"]
        return text[a:b]

    validate_proposition_coordinations(transport, fields, literal)
    [edge] = [edge for edge in transport["relations"] if edge["type"] == "proposition_coordination_scope"]
    if mutation == "relation":
        transport["relations"].remove(edge)
    elif mutation == "operator":
        edge["source"]["text_span"] = edge["operator_source"]["text_span"] = [16, 20]
    elif mutation == "member_source":
        edge["binding_evidence"]["members"][1]["object_source"]["text_span"] = [11, 16]
    elif mutation == "member_fact":
        fields.pop()
    else:
        transport["required_matcher_features"] = []
        transport["relations"].remove(edge)
        for field in fields:
            field["logic"] = {"kind": "opaque"}
    with pytest.raises(ValueError, match="coordination"):
        validate_proposition_coordinations(transport, fields, literal)


@pytest.mark.parametrize("text", [
    "Merchants’ Guild, provides tools through channels and partners.",
    "It requires an ecosystem: tools, systems, and providers with support and training.",
])
def test_an_alternate_reader_cannot_force_unresolved_source_into_its_own_coordination_answers(text):
    # These invented forms reproduce the owning-reader/alternate-reader
    # disagreement found in actual expected text. No company or document id
    # selects the rule, and no candidate or original page is read.
    alternate = read_propositions(text, SOURCE)
    assert alternate["complete"] and any(edge["type"] == "proposition_coordination_scope"
                                           for edge in alternate["relations"])
    expected = {"sample_id": "invented-unresolved-coordination", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only",
        "scope": [{"lines": [6, 6], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}],
        "targets": [{"id": "body", "kind": "text", "text": text, "raw_text": text, "raw": text,
            "reference": SOURCE, "cells": [], "parents": [], "has_children": False, "context": [],
            "pages": [1], "selected_heading_context": [], "outside_selection_context": []}]}
    model = compile_requirement_graph(expected)
    before = deepcopy(model)
    validate_requirement_graph(model, expected=expected)
    assert model == before
    assert model["semantic_complete"] is False and model["unresolved"]
    assert not any(edge["type"] == "proposition_coordination_scope" for edge in model["relations"])
    assert any({"B", "L"} <= set(issue["layers"]) and text.strip().rstrip(".") in issue.get("text", "")
               for issue in model["unresolved"])


@pytest.mark.parametrize("defect", ["missing", "one_layer", "partial", "fabricated_literal", "input_scope"])
def test_uninterpreted_coordination_needs_a_full_literal_bound_pending_obligation(defect):
    text = "Lumen owns Kappa and Sigma."
    pending = {"reason": "narrative_scope_unresolved", "source": {**SOURCE, "text_span": [0, len(text)]},
               "text": text, "layers": ["B", "L"]}
    transport = {"sources": [{"text": text, "source": SOURCE}], "relations": [],
                 "required_matcher_features": [], "unresolved": [pending]}

    def literal(source):
        a, b = source["text_span"]
        return text[a:b]

    validate_proposition_coordinations(transport, [], literal)
    if defect == "missing":
        transport["unresolved"] = []
    elif defect == "one_layer":
        pending["layers"] = ["B"]
    elif defect == "partial":
        pending["source"]["text_span"] = [0, 10]
        pending["text"] = text[:10]
    elif defect == "fabricated_literal":
        pending["text"] = "different literal"
    else:
        pending["reason"] = "input_scope_context"
    with pytest.raises(ValueError, match="coordination"):
        validate_proposition_coordinations(transport, [], literal)


def test_retained_pending_cannot_hide_a_missing_member_of_an_interpreted_group():
    text = "Lumen owns Kappa and Sigma."
    parsed = read_propositions(text, SOURCE)
    transport = {"sources": [{"text": text, "source": SOURCE}], "relations": parsed["relations"],
        "required_matcher_features": parsed["required_matcher_features"],
        "unresolved": [{"reason": "narrative_scope_unresolved", "text": text,
                        "source": {**SOURCE, "text_span": [0, len(text)]}, "layers": ["B", "L"]}]}

    def literal(source):
        a, b = source["text_span"]
        return text[a:b]

    for fields in ([], parsed["facts"][:1]):
        with pytest.raises(ValueError, match="coordination"):
            validate_proposition_coordinations(transport, fields, literal)
