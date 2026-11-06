"""Printed page references restrict one document-composition assertion."""

from copy import deepcopy

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.three_layer import compile_markdown, read_candidate

CN = "第21页至第34页所载的附注为本财务报表的组成部分。"
EN = "Notes on pages 21 to 34 are part of this statement."
SOURCE = {"path": "<invented-document-composition>", "lines": [3, 3]}


def read(text, source=SOURCE, **kwargs):
    from moparse_eval.document_composition_requirements import read_document_composition

    return read_document_composition(text, source, **kwargs)


@pytest.mark.parametrize("text,subject,attribute,value,page_range", [
    (CN, "附注", "组成部分", "本财务报表", "第21页至第34页"),
    (EN, "Notes", "part of", "this statement", "pages 21 to 34"),
])
def test_public_reader_preserves_one_complete_assertion_with_printed_page_identity(
        text, subject, attribute, value, page_range):
    for graph in (compile_markdown(text), read_candidate(markdown_observation(text, sample_id="invented-composition", pipeline="P07", pages=[1]))):
        assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
            (subject, attribute, value, {"polarity": "positive", "page_range": page_range})]
        assert {"document_composition", "page_reference_binding"} <= set(graph["required_matcher_features"])
        assert {edge["type"] for edge in graph["relations"]} == {"document_part_of", "page_reference_scope"}
        assert not graph["blockers"]


@pytest.mark.parametrize("text,subject_span,predicate_span,object_span,marker_span,page_span,start_span,end_span", [
    (CN, [12, 14], [14, 15], [15, 20], [21, 25], [0, 9], [1, 3], [6, 8]),
    (EN, [0, 5], [24, 27], [36, 50], [28, 35], [9, 23], [15, 17], [21, 23]),
])
def test_every_component_and_each_page_endpoint_has_an_exact_original_subrange(
        text, subject_span, predicate_span, object_span, marker_span, page_span, start_span, end_span):
    source = {**SOURCE, "text_span": [19, 19 + len(text)]}
    original = deepcopy(source)
    result = read(text, source, scope=["North"])
    assert result["complete"] and result["semantic_complete"] and not result["pending_requirements"]
    [fact] = result["facts"]
    [tree] = result["logic"]
    for key, span in [("subject_source", subject_span), ("predicate_source", predicate_span),
                      ("object_source", object_span), ("attribute_source", marker_span)]:
        assert fact[key] == {**source, "text_span": [19 + span[0], 19 + span[1]]}
    assert fact["qualifier_sources"]["page_range"] == {**source, "text_span": [19 + page_span[0], 19 + page_span[1]]}
    pages = tree["page_reference"]
    assert (pages["start"]["id"], pages["end"]["id"]) == ("21", "34")
    assert pages["start"]["source"]["text_span"] == [19 + start_span[0], 19 + start_span[1]]
    assert pages["end"]["source"]["text_span"] == [19 + end_span[0], 19 + end_span[1]]
    assert pages["role"] == "printed_page_reference_range"
    assert tree["document_identity"] == {"text": fact["value"], "source": fact["value_source"], "resolution": "printed_name_only"}
    assert all("unit" not in f["qualifiers"] and f["scope"] == ["North"] for f in result["facts"])
    assert result["semantic_operands"] == [] and len(result["facts"]) == 1
    assert result["text_atoms"] == [{"text": text, "role": "literal", "source": {**source, "text_span": [19, 19 + len(text)]}}]
    assert source == original


@pytest.mark.parametrize("text", [
    "如果董事会批准，第21页至第34页所载的附注为本财务报表的组成部分。",
    "第21页至第34页所载的附注不是本财务报表的组成部分。",
    "第21页至第34页所载的附注为本财务报表的组成部分，如果董事会批准。",
    "第21页至第34页所载的附注为本财务报表的组成部分，因为本期存在变更。",
    "If Board approves, notes on pages 21 to 34 are part of this statement.",
    "Notes on pages 21 to 34 are not part of this statement.",
    "Notes on pages 21 to 34 may form part of this statement.",
    "Notes on pages 21 to 34 are part of this statement if Board approves.",
])
def test_unsupported_negation_modality_conditions_and_causes_remain_whole_pending(text):
    result = read(text)
    assert result["matched"] and not result["complete"] and result["facts"] == []
    [pending] = result["pending_requirements"]
    assert pending["text"] == text and pending["source"] == {**SOURCE, "text_span": [0, len(text)]}
    assert pending["layers"] == ["B", "L"] and not result["logic"]
    public = compile_markdown(text)
    assert public["business"] == []
    assert any(issue["reason"] == "document_composition_scope_unresolved" for issue in public["blockers"])


def test_page_order_and_printed_document_changes_are_not_normalized_or_used_to_choose_positions():
    changed = read("第34页至第21页所载的附注为该合并财务报表摘要的组成部分。")
    [fact] = changed["facts"]
    pages = changed["logic"][0]["page_reference"]
    assert (pages["start"]["id"], pages["end"]["id"]) == ("34", "21")
    assert fact["value"] == "该合并财务报表摘要"
    assert fact["qualifiers"]["page_range"] == "第34页至第21页"
    assert all(edge["object_anchor"] is None for edge in changed["relations"])


def test_ordinary_terminal_numbers_are_not_page_roles_or_composition():
    result = read("Revenue:21; Cost:34")
    assert not result["matched"] and not result["facts"] and not result["logic"]


@pytest.mark.parametrize("statement", [CN, EN])
def test_source_graph_retains_the_assertion_and_two_reference_endpoints_with_no_extra_page_votes(statement):
    expected = {"sample_id": "invented-composition-source", "document_id": "invented-document", "source_pages": [1],
                "standard": "expected_only", "scope": [{"lines": [3, 3], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}],
                "targets": [{"id": "body", "kind": "text", "text": statement, "raw_text": statement, "raw": statement, "reference": SOURCE,
                             "cells": [], "parents": [], "has_children": False, "context": [], "pages": [1],
                             "selected_heading_context": [], "outside_selection_context": []}]}
    model = compile_requirement_graph(expected)
    validate_requirement_graph(model, expected=expected)
    assert model["semantic_complete"] and len(model["projections"]["B"]) == 1
    assert len(model["projections"]["L"]) == 2
    assert set(model["required_matcher_features"]) == {"document_composition", "page_reference_binding"}


def test_valid_composition_and_neighboring_business_clause_keep_separate_original_ranges():
    from moparse_eval.narrative_requirements import read_narrative

    text = CN + " Lumen owns Sigma."
    result = read_narrative(text, SOURCE)
    assert result["complete"] is True
    assert [(fact["subject"], fact["attribute"], fact["value"]) for fact in result["facts"]] == [
        ("附注", "组成部分", "本财务报表"), ("Lumen", "own", "Sigma")]
    assert [fact["source"]["text_span"] for fact in result["facts"]] == [[0, 26], [27, 43]]
    assert result["text_atoms"] == [{"text": text, "role": "literal", "source": {**SOURCE, "text_span": [0, len(text)]}}]


def test_unresolved_composition_does_not_swallow_its_valid_neighbor():
    from moparse_eval.narrative_requirements import read_narrative

    clause = "Notes on pages 21 to 34 are not part of this statement."
    text = clause + " Lumen owns Sigma."
    result = read_narrative(text, SOURCE)
    assert result["complete"] is False
    assert [(fact["subject"], fact["attribute"], fact["value"]) for fact in result["facts"]] == [("Lumen", "own", "Sigma")]
    [pending] = result["pending_requirements"]
    assert pending["text"] == clause and pending["source"]["text_span"] == [0, len(clause)]


def composition_transport():
    parsed = read(CN)
    transport = {"sources": [{"text": CN, "source": SOURCE}], "logic": parsed["logic"],
                 "required_matcher_features": parsed["required_matcher_features"],
                 "relations": parsed["relations"], "unresolved": parsed["unresolved"]}
    return transport, parsed["facts"]


def validate_transport(transport, facts):
    from moparse_eval.document_composition_requirements import validate_document_compositions

    def literal(source):
        assert source["path"] == SOURCE["path"] and source["lines"] == SOURCE["lines"]
        a, b = source["text_span"]
        return CN[a:b] if 0 <= a <= b <= len(CN) else None

    validate_document_compositions(transport, facts, literal)


@pytest.mark.parametrize("mutation", ["document_relation", "page_relation", "page_endpoint", "source", "fact", "synchronized"])
def test_source_obligations_survive_relationship_endpoint_and_synchronized_derived_mutations(mutation):
    transport, facts = composition_transport()
    validate_transport(transport, facts)
    if mutation == "document_relation":
        transport["relations"] = [edge for edge in transport["relations"] if edge["type"] != "document_part_of"]
    elif mutation == "page_relation":
        transport["relations"] = [edge for edge in transport["relations"] if edge["type"] != "page_reference_scope"]
    elif mutation == "page_endpoint":
        for tree in [transport["logic"][0], facts[0]["logic"]]:
            tree["page_reference"]["end"]["id"] = "35"
        for edge in transport["relations"]:
            edge["binding_evidence"]["page_reference"]["end"]["id"] = "35"
            if edge["type"] == "page_reference_scope":
                edge["left"]["end"]["id"] = "35"
    elif mutation == "source":
        facts[0]["qualifier_sources"]["page_range"]["text_span"] = [1, 9]
    elif mutation == "fact":
        facts.clear()
    else:
        facts[0]["logic"] = {"kind": "proposition"}
        transport["logic"] = []
        transport["relations"] = []
        transport["required_matcher_features"] = []
    with pytest.raises(ValueError, match="composition"):
        validate_transport(transport, facts)


def test_removing_unresolved_composition_scope_fails_the_source_transport_guard():
    clause = "Notes on pages 21 to 34 are not part of this statement."
    parsed = read(clause)
    transport = {"sources": [{"text": clause, "source": SOURCE}], "logic": [], "relations": [],
                 "required_matcher_features": [], "unresolved": []}
    from moparse_eval.document_composition_requirements import validate_document_compositions

    def literal(source):
        a, b = source["text_span"]
        return clause[a:b]

    with pytest.raises(ValueError, match="unresolved document composition"):
        validate_document_compositions(transport, [], literal)
    transport["unresolved"] = parsed["unresolved"]
    validate_document_compositions(transport, [], literal)
