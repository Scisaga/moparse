"""Literal role and scope oracles for the existing bounded modal reader."""

from copy import deepcopy

import pytest

from moparse_eval.prose_requirements import read_prose_requirements
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

TEXT = "Board may not review Report."
SOURCE = {"path": "<invented-modal-roles>", "lines": [4, 4]}


def test_modal_prose_keeps_its_existing_surface_value_and_exposes_each_real_role():
    offset = 19
    source = {**SOURCE, "text_span": [offset, offset + len(TEXT)]}
    before = deepcopy(source)
    result = read_prose_requirements(TEXT, source)
    [fact] = result["facts"]
    assert result["blockers"] == []
    assert (fact["subject"], fact["attribute"], fact["value"], fact["predicate"], fact["object"]) == (
        "Board", "review", "review Report", "review", "Report")
    for key, bounds, text in [
        ("subject_source", [0, 5], "Board"), ("predicate_source", [14, 20], "review"),
        ("attribute_source", [14, 20], "review"), ("object_source", [21, 27], "Report"),
        ("value_source", [14, 27], "review Report"),
    ]:
        assert fact[key] == {**source, "text_span": [offset + bounds[0], offset + bounds[1]]}
        assert TEXT[slice(*bounds)] == text
    assert fact["qualifiers"] == {"modality": "may", "polarity": "negative"}
    assert fact["qualifier_sources"]["modality"]["text_span"] == [25, 28]
    assert fact["qualifier_sources"]["polarity"]["text_span"] == [29, 32]
    assert source == before


def test_three_layer_reader_retains_distinct_source_bound_predicate_modal_and_negative_edges():
    graph = compile_markdown(TEXT)
    [fact] = graph["business"]
    assert fact["value"] == "review Report"
    assert [edge["type"] for edge in graph["relations"]] == ["field_binding", "qualifier_scope", "qualifier_scope"]
    binding, modal, negation = graph["relations"]
    assert binding["source"]["text_span"] == [14, 20]
    assert binding["binding_evidence"]["subject_source"]["text_span"] == [0, 5]
    assert binding["binding_evidence"]["object_source"]["text_span"] == [21, 27]
    assert modal["left"] == {"type": "modality", "text": "may"}
    assert negation["left"] == {"type": "polarity", "text": "negative"}
    for edge, span in [(modal, [6, 9]), (negation, [10, 13])]:
        assert edge["source"]["text_span"] == span
        assert edge["operator_source"] == edge["binding_evidence"]["operator_source"] == edge["source"]
        assert edge["right"]["subject"] == "Board" and edge["right"]["attribute"] == "review"


@pytest.mark.parametrize("text,span,operator,kind", [
    ("If Gate is open, Board may review Report.", [0, 2], "if", "condition_scope"),
    ("Board may review Report unless Gate is open.", [24, 30], "unless", "condition_scope"),
    ("Board may review Report except when Gate is closed.", [24, 35], "except_when", "exception_scope"),
    ("To participate, Board may review Report.", [0, 2], "To", "purpose_scope"),
])
def test_condition_exception_and_purpose_operators_retain_the_actual_separate_source(text, span, operator, kind):
    result = read_prose_requirements(text, SOURCE)
    assert result["blockers"] == []
    [relation] = [edge for edge in result["relations"] if edge["type"] == kind]
    assert relation["operator_source"]["text_span"] == span
    assert relation["binding_evidence"]["operator_source"] == relation["operator_source"]
    assert text[slice(*span)].lower().replace(" ", "_") == operator.lower()
    assert relation["right"] == {"subject": "Board", "action": "review", "scope": []}


@pytest.mark.parametrize("actual,b_correct,l_correct", [
    (TEXT, 1, 3), ("Board may never review Report.", 1, 3),
    ("Board must review Report.", 0, 1), ("Clerk may not review Report.", 0, 0),
])
def test_independent_synthetic_identity_and_operator_conflicts_do_not_erase_valid_neighbor_links(actual, b_correct, l_correct):
    result = grade_layers(compile_markdown(TEXT), read_candidate_markdown(actual))
    assert result["layers"]["B"]["numerator"] == b_correct
    assert result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["L"]["numerator"] == l_correct
    assert result["layers"]["L"]["denominator"] == 3


def test_modal_predicate_source_mutation_is_rejected_against_the_unchanged_literal():
    expected = {"sample_id": "invented-modal-role-mutation", "document_id": "invented-modal-document",
        "source_pages": [1], "standard": "expected_only",
        "scope": [{"lines": [4, 4], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}],
        "targets": [{"id": "body", "kind": "text", "text": TEXT, "raw_text": TEXT, "raw": TEXT,
            "reference": SOURCE, "cells": [], "parents": [], "has_children": False, "context": [],
            "pages": [1], "selected_heading_context": [], "outside_selection_context": []}]}
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph)
    [fact] = [node for node in graph["nodes"] if node["id"] in graph["projections"]["B"]]
    fact["predicate_source"]["text_span"] = [15, 20]
    with pytest.raises(ValueError, match="source|predicate|literal"):
        validate_requirement_graph(graph)
