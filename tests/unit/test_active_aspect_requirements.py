"""Invented active perfect/progressive semantics and bounded unknown syntax."""

from copy import deepcopy

import pytest

from moparse_eval.narrative_requirements import read_narrative
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph

SOURCE = {"path": "<invented-active-aspect>", "lines": [7, 7]}


@pytest.mark.parametrize("text,subject,predicate,attribute,obj,aspect", [
    ("Lumen has acquired Kappa.", "Lumen", "acquired", "acquire", "Kappa", "perfect"),
    ("The directors have approved Report.", "The directors", "approved", "approve", "Report", "perfect"),
    ("The unit is making components.", "The unit", "making", "make", "components", "progressive"),
    ("The units are storing records.", "The units", "storing", "store", "records", "progressive"),
    ("We have sharpened our focus.", "We", "sharpened", "sharpen", "our focus", "perfect"),
])
@pytest.mark.parametrize("offset", [0, 40])
def test_explicit_active_auxiliary_and_word_form_keep_independent_actual_role_sources(text, subject, predicate, attribute, obj, aspect, offset):
    origin = {**SOURCE, "text_span": [offset, offset + len(text)]}
    before = deepcopy(origin)
    result = read_narrative(text, origin)
    assert result["complete"] is True and result["unresolved"] == []
    [fact] = result["facts"]
    assert (fact["subject"], fact["predicate"], fact["attribute"], fact["value"]) == (subject, predicate, attribute, obj)
    assert fact["qualifiers"] == {"polarity": "positive", "tense": "present", "aspect": aspect}
    for key, literal in (("subject_source", subject), ("predicate_source", predicate), ("value_source", obj)):
        assert fact[key]["text_span"] == [offset + text.index(literal), offset + text.index(literal) + len(literal)]
    auxiliary = "have" if " have " in text else "has" if " has " in text else "are" if " are " in text else "is"
    aux_span = [offset + text.index(auxiliary), offset + text.index(auxiliary) + len(auxiliary)]
    assert fact["qualifier_sources"]["tense"]["text_span"] == fact["qualifier_sources"]["aspect"]["text_span"] == aux_span
    assert "active_aspect_scope" in result["required_matcher_features"]
    assert any(e["type"] == "narrative_active_aspect_scope" for e in result["relations"])
    assert origin == before and result["text_atoms"][0]["text"] == text


@pytest.mark.parametrize("text,wanted,aspect", [
    ("Lumen has acquired shares and approved Budget.", [("acquire", "shares"), ("approve", "Budget")], "perfect"),
    ("Lumen is storing and retrieving records.", [("store", "records"), ("retrieve", "records")], "progressive"),
])
def test_shared_printed_actor_and_aspect_do_not_merge_two_independent_and_actions(text, wanted, aspect):
    result = read_narrative(text, SOURCE)
    assert result["complete"] is True
    assert [(f["attribute"], f["value"]) for f in result["facts"]] == wanted
    assert all(f["subject"] == "Lumen" and f["qualifiers"]["aspect"] == aspect for f in result["facts"])
    assert all(f["subject_source"]["text_span"] == [0, 5] for f in result["facts"])
    if "retrieving" in text:
        assert result["facts"][0]["value_source"] == result["facts"][1]["value_source"]


def test_single_printed_negation_and_a_reporter_keep_their_actual_scopes():
    result = read_narrative("The auditor reported that Lumen has not acquired Kappa.", SOURCE)
    assert result["complete"] is True
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "acquire", "Kappa")
    assert fact["qualifiers"]["polarity"] == "negative" and fact["qualifiers"]["aspect"] == "perfect"
    assert fact["qualifiers"]["tense"] == "present"
    assert fact["qualifiers"]["reporting"] == [{"subject": "The auditor", "attribute": "report", "polarity": "positive", "tense": "past"}]


@pytest.mark.parametrize("text", [
    "Kappa is acquired by Lumen.", "Lumen is approved.", "Lumen has florped cargo.",
    "Lumen is florping cargo.", "Lumen had acquired shares.", "Lumen was storing records.",
    "Lumen is making investments in research.", "Lumen has acquired shares to expand sales.",
    "Lumen is making tools which store records.", "Lumen has acquired shares and approving Budget.",
])
def test_passive_unknown_forms_and_unproved_embedded_scope_are_whole_source_unknowns(text):
    result = read_narrative(text, SOURCE)
    assert result["complete"] is False and result["facts"] == []
    assert result["unresolved"] and any(u["text"].rstrip(".") == text.rstrip(".") for u in result["unresolved"])
    assert result["text_atoms"][0]["text"] == text


def test_lexical_possession_and_plain_copula_are_not_relabelled_as_active_aspect():
    for text, attr, obj in (("Lumen has assets.", "have", "assets"), ("Lumen is portable.", "be", "portable")):
        result = read_narrative(text, SOURCE)
        assert result["complete"] is True
        [fact] = result["facts"]
        assert (fact["attribute"], fact["value"]) == (attr, obj)
        assert "aspect" not in fact["qualifiers"]


def source_graph(raw):
    target = {"id": "printed:7", "kind": "text", "text": raw, "raw_text": raw, "raw": raw,
              "reference": SOURCE, "cells": [], "parents": [], "has_children": False, "context": [],
              "selected_heading_context": [], "outside_selection_context": [], "pages": [1], "heading_level": None}
    return compile_requirement_graph({"sample_id": "invented-active-aspect", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": [target], "scope": []})


def test_public_source_graph_keeps_aspect_sources_and_declares_the_unvalidated_matcher_feature():
    graph = source_graph("Lumen has acquired Kappa.")
    assert graph["semantic_complete"] is True
    facts = [n for n in graph["nodes"] if n["id"] in graph["projections"]["B"]]
    assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"].get("aspect")) for f in facts] == [
        ("Lumen", "acquire", "Kappa", "perfect")]
    assert "active_aspect_scope" in graph["required_matcher_features"]
    validate_requirement_graph(graph)


@pytest.mark.parametrize("raw", ["Lumen is making investments in research.", "Kappa is acquired by Lumen.",
                                  "Lumen has florped cargo."])
def test_public_source_graph_does_not_fall_back_to_an_opaque_have_or_be_answer(raw):
    material = source_graph(raw)
    assert material["semantic_complete"] is False
    assert not material["projections"]["B"]
    assert any(u["text"].rstrip(".") == raw.rstrip(".") for u in material["unresolved"])
    validate_requirement_graph(material)


@pytest.mark.parametrize("mutation", ["qualifier", "tree", "source"])
def test_aspect_canonical_codes_require_the_actual_own_auxiliary_source(mutation):
    material = source_graph("Lumen has acquired Kappa.")
    validate_requirement_graph(material)
    [fact] = [n for n in material["nodes"] if n["id"] in material["projections"]["B"]]
    if mutation == "qualifier":
        fact["qualifiers"]["aspect"] = "progressive"
    elif mutation == "tree":
        material["logic"][0]["aspect"] = "progressive"
    else:
        fact["qualifier_sources"]["aspect"]["text_span"] = [10, 18]  # acquired
    with pytest.raises(ValueError, match="source|qualifier|operator"):
        validate_requirement_graph(material)
