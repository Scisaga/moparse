"""Independent dated-list requirements; no candidate or corpus is inspected."""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph

PATH = "<invented-dated-enumeration>"
INTRO = "2028年，Lumen的合作进展包括："


def target(text, line, *, parents=(), children=False, kind="item", list_span=None):
    return {"id": f"printed:{line}", "kind": kind, "text": text, "raw_text": text, "raw": text,
        "reference": {"path": PATH, "lines": [line, line]}, "cells": [], "parents": list(parents),
        "has_children": children, "context": [], "selected_heading_context": [],
        "outside_selection_context": [], "pages": [1], "list_span": list_span,
        "heading_level": None}


def expected(*targets):
    return {"sample_id": "invented-dated-enumeration", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": list(targets),
        "scope": [{"lines": [1, max(t["reference"]["lines"][1] for t in targets)], "pages": [1],
                   "declared_source_pages": [1], "outside_source_pages": []}]}


def dated_list(*extra):
    return expected(target(INTRO, 1, children=True, list_span=[1, 4]),
        target("批准Kappa。", 2, parents=[INTRO], list_span=[1, 4]),
        target("披露Sigma。", 3, parents=[INTRO], list_span=[1, 4]), *extra)


def facts(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return [nodes[ident] for ident in graph["projections"]["B"]]


def own(source, line, span):
    assert source["path"] == PATH
    assert source["lines"] == [line, line]
    assert source["text_span"] == span


def test_complete_dated_introduction_binds_two_omitted_actors_without_an_introduction_business_vote():
    authored = dated_list()
    before = deepcopy(authored)
    graph = compile_requirement_graph(authored)
    assert authored == before
    business = facts(graph)
    assert [(f["subject"], f["attribute"], f["value"]) for f in business] == [
        ("Lumen", "批准", "Kappa"), ("Lumen", "披露", "Sigma")]
    assert len(business) == 2, "the introduction supplies scope and actor evidence, not a third assertion"
    for line, fact in zip((2, 3), business, strict=True):
        assert fact["qualifiers"]["period"] == "2028年"
        own(fact["subject_source"], 1, [6, 11])
        own(fact["qualifier_sources"]["period"], 1, [0, 5])
        own(fact["predicate_source"], line, [0, 2])
        own(fact["value_source"], line, [2, 7])
    membership = [edge for edge in graph["relations"] if edge["type"] == "enumeration_membership"]
    assert len(membership) == 2
    assert [(edge["right"]["subject"], edge["right"]["attribute"]) for edge in membership] == [
        ("Lumen", "批准"), ("Lumen", "披露")]
    for line, edge in zip((2, 3), membership, strict=True):
        own(edge["binding_evidence"]["introduction_source"], 1, [0, 19])
        own(edge["binding_evidence"]["member_source"], line, [0, 8])
    assert graph["semantic_complete"] is True and not graph["unresolved"]
    assert "enumeration_context_scope" in graph["required_matcher_features"]
    validate_requirement_graph(graph)


def test_same_enumeration_keeps_an_explicit_member_actor_instead_of_replacing_it_with_intro_actor():
    graph = compile_requirement_graph(dated_list(
        target("Vega批准Omega。", 4, parents=[INTRO], list_span=[1, 4])))
    assert [(f["subject"], f["attribute"], f["value"]) for f in facts(graph)] == [
        ("Lumen", "批准", "Kappa"), ("Lumen", "披露", "Sigma"), ("Vega", "批准", "Omega")]
    last = facts(graph)[-1]
    assert last["qualifiers"]["period"] == "2028年"
    own(last["subject_source"], 4, [0, 4])
    own(last["predicate_source"], 4, [4, 6])
    own(last["value_source"], 4, [6, 11])
    own(last["qualifier_sources"]["period"], 1, [0, 5])
    assert graph["semantic_complete"] is True and not graph["unresolved"]
    validate_requirement_graph(graph)


def test_non_list_paragraph_after_the_list_does_not_borrow_its_period_or_actor():
    graph = compile_requirement_graph(dated_list(target("Kappa批准Omega。", 5, kind="text")))
    business = facts(graph)
    assert [(f["subject"], f["attribute"], f["value"]) for f in business] == [
        ("Lumen", "批准", "Kappa"), ("Lumen", "披露", "Sigma"), ("Kappa", "批准", "Omega")]
    tail = business[-1]
    assert "period" not in tail["qualifiers"]
    assert "unit" not in tail["qualifiers"] and "currency" not in tail["qualifiers"]
    own(tail["subject_source"], 5, [0, 5])
    assert len([edge for edge in graph["relations"] if edge["type"] == "enumeration_membership"]) == 2
    assert graph["semantic_complete"] is True
    validate_requirement_graph(graph)


@pytest.mark.parametrize('text', ['Vega批准Omega，优化Sigma。', '新的业务叙述尚无解释，优化Sigma。'])
def test_partial_member_does_not_borrow_intro_actor_across_a_new_actor_or_unknown_clause(text):
    graph = compile_requirement_graph(expected(target(INTRO, 1, children=True, list_span=[1, 2]),
        target(text, 2, parents=[INTRO], list_span=[1, 2])))
    assert not graph['semantic_complete']
    assert not any(f.get('subject') == 'Lumen' for f in facts(graph))
    assert any(issue['reason'] == 'enumeration_member_actor_control_unresolved' for issue in graph['unresolved'])
    validate_requirement_graph(graph)


def test_repeated_predicates_in_one_member_do_not_mutate_an_earlier_membership():
    text = 'Vega实现Kappa，Vega实现Sigma。'
    graph = compile_requirement_graph(expected(target(INTRO, 1, children=True, list_span=[1, 2]),
        target(text, 2, parents=[INTRO], list_span=[1, 2])))
    assert [(f['subject'], f['attribute'], f['value']) for f in facts(graph)] == [
        ('Vega', '实现', 'Kappa'), ('Vega', '实现', 'Sigma')]
    assert len([edge for edge in graph['relations'] if edge['type'] == 'enumeration_membership']) == 2
    validate_requirement_graph(graph)


@pytest.mark.parametrize("case", ["missing-actor", "unprinted-parent"])
def test_failure_closed_omitted_actor_requires_one_actual_unambiguous_introduction(case):
    intro = "2028年，合作进展包括：" if case == "missing-actor" else INTRO
    children = [target("批准Kappa。", 2, parents=[intro], list_span=[1, 3]),
                target("披露Sigma。", 3, parents=[intro], list_span=[1, 3])]
    material = expected(*([target(intro, 1, children=True, list_span=[1, 3])] if case == "missing-actor" else []), *children)
    graph = compile_requirement_graph(material)
    assert graph["semantic_complete"] is False
    assert not any(f.get("subject") in {"合作进展", "Lumen"} for f in facts(graph))
    for line in (2, 3):
        assert any(issue.get("source", {}).get("lines") == [line, line] and {"B", "L"} <= set(issue["layers"])
                   for issue in graph["unresolved"])
    # Text retention remains an obligation even when the actor cannot bind.
    literals = [n["text"] for n in graph["nodes"] if n["id"] in graph["projections"]["T"]]
    assert any("Kappa" in text for text in literals)
    assert any("Sigma" in text for text in literals)


def test_transport_guard_rejects_missing_membership_even_after_all_layer_indexes_are_synchronized():
    graph = compile_requirement_graph(dated_list())
    validate_requirement_graph(graph)
    original_t = deepcopy([node for node in graph["nodes"] if node["id"] in graph["projections"]["T"]])
    original_b = deepcopy(facts(graph))
    removed = next(edge for edge in graph["relations"] if edge["type"] == "enumeration_membership")
    graph["relations"] = [edge for edge in graph["relations"] if edge["id"] != removed["id"]]
    graph["projections"]["L"].remove(removed["id"])
    for disposition in graph["dispositions"]:
        for layer in disposition["layers"].values():
            layer["requirements"] = [ident for ident in layer["requirements"] if ident != removed["id"]]
    assert [node for node in graph["nodes"] if node["id"] in graph["projections"]["T"]] == original_t
    assert facts(graph) == original_b
    with pytest.raises(ValueError, match="enumeration|member|scope|source|relation"):
        validate_requirement_graph(graph)


def test_transport_guard_cannot_borrow_the_same_printed_year_from_a_different_introduction():
    second = "2028年，Vega的合作进展包括："
    graph = compile_requirement_graph(expected(
        target(INTRO, 1, children=True, list_span=[1, 3]),
        target("批准Kappa。", 2, parents=[INTRO], list_span=[1, 3]),
        target("披露Sigma。", 3, parents=[INTRO], list_span=[1, 3]),
        target(second, 5, children=True, list_span=[5, 6]),
        target("批准Omega。", 6, parents=[second], list_span=[5, 6])))
    validate_requirement_graph(graph)
    assert [(f["subject"], f["value"], f["qualifiers"]["period"]) for f in facts(graph)] == [
        ("Lumen", "Kappa", "2028年"), ("Lumen", "Sigma", "2028年"), ("Vega", "Omega", "2028年")]
    first = facts(graph)[0]
    foreign_source = {"path": PATH, "lines": [5, 5], "text_span": [0, 5]}
    # Every copied proof for this first member is changed together. Both
    # periods really print 2028年, so token presence cannot establish ownership.
    first["qualifier_sources"]["period"] = deepcopy(foreign_source)
    first["enumeration_evidence"]["roles"]["period"]["source"] = deepcopy(foreign_source)
    for edge in graph["relations"]:
        if edge.get("fact_id") == first["id"] and edge["type"] == "enumeration_membership":
            edge["binding_evidence"]["period_source"] = deepcopy(foreign_source)
    context = next(context for context in graph["context"]["enumeration_contexts"] if context["source"]["lines"] == [1, 1])
    member = next(member for member in context["members"] if member["source"]["lines"] == [2, 2])
    member["member_context"]["qualifier_sources"]["period"] = deepcopy(foreign_source)
    with pytest.raises(ValueError, match="enumeration|period|scope|source|introduction"):
        validate_requirement_graph(graph)


def test_explicit_field_members_keep_intro_owner_and_their_own_attribute_value_sources():
    graph = compile_requirement_graph(expected(
        target(INTRO, 1, children=True, list_span=[1, 3]),
        target("Revenue:17", 2, parents=[INTRO], list_span=[1, 3]),
        target("Profit:5", 3, parents=[INTRO], list_span=[1, 3])))
    business = facts(graph)
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in business] == [
        ("Lumen", "Revenue", "17", "metric"), ("Lumen", "Profit", "5", "metric")]
    for line, fact, attribute_span, value_span in zip((2, 3), business,
            ([0, 7], [0, 6]), ([8, 10], [7, 8]), strict=True):
        own(fact["subject_source"], 1, [6, 11])
        own(fact["qualifier_sources"]["period"], 1, [0, 5])
        own(fact["attribute_source"], line, attribute_span)
        own(fact["value_source"], line, value_span)
        assert fact["qualifiers"]["period"] == "2028年"
    membership = [edge for edge in graph["relations"] if edge["type"] == "enumeration_membership"]
    assert [(edge["right"]["subject"], edge["right"]["attribute"]) for edge in membership] == [
        ("Lumen", "Revenue"), ("Lumen", "Profit")]
    assert graph["semantic_complete"] is True and not graph["unresolved"]
    assert "enumeration_context_scope" in graph["required_matcher_features"]
    validate_requirement_graph(graph)


def test_conflicting_own_metric_period_cannot_leave_business_and_field_binding_with_different_subjects():
    child = "Revenue:2027年17"
    graph = compile_requirement_graph(expected(
        target(INTRO, 1, children=True, list_span=[1, 2]),
        target(child, 2, parents=[INTRO], list_span=[1, 2])))
    [fact] = facts(graph)
    assert (fact["attribute"], fact["value"], fact["qualifiers"]["period"]) == ("Revenue", "17", "2027年")
    own(fact["qualifier_sources"]["period"], 2, [8, 13])
    bindings = [edge for edge in graph["relations"] if edge["type"] == "field_binding"
                and edge["source"].get("lines") == [2, 2] and edge["right"].get("attribute") == "Revenue"]
    assert len(bindings) == 1
    assert bindings[0]["right"]["subject"] == fact["subject"], "a rejected context must not half-rebind the B fact"
    assert graph["semantic_complete"] is False
    assert any(issue["source"]["lines"] == [2, 2] and {"B", "L"} <= set(issue["layers"])
               for issue in graph["unresolved"])
    validate_requirement_graph(graph)


@pytest.mark.parametrize("year", ["2028", "2027"])
def test_own_calendar_year_keeps_its_printed_literal_and_scope_agrees_only_for_the_same_year(year):
    child = f"In {year}, Lumen holds 17万元."
    graph = compile_requirement_graph(expected(
        target(INTRO, 1, children=True, list_span=[1, 2]),
        target(child, 2, parents=[INTRO], list_span=[1, 2])))
    [fact] = facts(graph)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "hold", "17")
    assert fact["qualifiers"]["period"] == year, "enum context must not overwrite an explicitly printed member period"
    own(fact["qualifier_sources"]["period"], 2, [3, 7])
    own(fact["subject_source"], 2, [9, 14])
    own(fact["value_source"], 2, [21, 23])
    assert any(source["text"] == INTRO for source in graph["sources"])
    assert any(source["text"] == child for source in graph["sources"])
    if year == "2028":
        assert graph["semantic_complete"] is True and not graph["unresolved"]
        [membership] = [edge for edge in graph["relations"] if edge["type"] == "enumeration_membership"]
        own(membership["binding_evidence"]["period_source"], 1, [0, 5])
        assert membership["left"]["qualifiers"]["period"] == "2028年"
        assert "enumeration_context_scope" in graph["required_matcher_features"]
    else:
        assert graph["semantic_complete"] is False
        assert any(issue["source"]["lines"] == [2, 2] and {"B", "L"} <= set(issue["layers"])
                   for issue in graph["unresolved"])
    validate_requirement_graph(graph)
