"""Independent literal-source mutations beyond the primary business value."""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph

PATH = "<invented-semantic-sources>"
POLICY = "the board shall not pay 17 credits unless approved by 4 directors."
NARRATIVE = "If Delta is ready, Board may review Report or Budget."


def graph(text):
    target = {"id": "printed:1", "kind": "text", "text": text, "raw_text": text, "raw": text,
              "reference": {"path": PATH, "lines": [1, 1]}, "cells": [], "parents": [],
              "has_children": False, "context": [], "selected_heading_context": [],
              "outside_selection_context": [], "pages": [1], "heading_level": None}
    return compile_requirement_graph({"sample_id": "invented-semantic-sources", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": [target],
        "scope": [{"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]})


def business(material):
    return next(n for n in material["nodes"] if n["id"] in material["projections"]["B"])


def operand(material):
    return next(n for n in material["nodes"] if n.get("kind") == "semantic_operand" and n["subject"] == "Delta")


@pytest.mark.parametrize("text", [POLICY, NARRATIVE, "Board must review Report and Budget.",
    "The device is not able to store records.", "The auditor reported that the device stores records.",
    "董事会不得支付款项。", "如果条件是有效的，董事会可以公布报告。"])
def test_legal_condition_negation_enumeration_and_canonical_operators_keep_original_sources(text):
    material = graph(text)
    before = deepcopy(material)
    validate_requirement_graph(material)
    assert material == before


@pytest.mark.parametrize("mutation", ["condition_value", "condition_source", "operator_source", "operator_value",
                                      "polarity_source", "modality_source", "missing_condition_source"])
def test_singular_qualifier_literals_and_canonical_operators_are_really_source_guarded(mutation):
    material = graph(POLICY)
    fact = business(material)
    assert fact["qualifiers"]["condition"] == "approved by 4 directors"
    if mutation == "condition_value":
        fact["qualifiers"]["condition"] = "approved by 3 directors"
    elif mutation == "condition_source":
        fact["qualifier_sources"]["condition"]["path"] = "<unprinted-condition>"
    elif mutation == "operator_source":
        fact["qualifier_sources"]["condition_operator"]["text_span"] = [10, 15]  # shall
    elif mutation == "operator_value":
        fact["qualifiers"]["condition_operator"] = "if"
    elif mutation == "polarity_source":
        fact["qualifier_sources"]["polarity"]["text_span"] = [10, 15]
    elif mutation == "modality_source":
        fact["qualifier_sources"]["modality"]["text_span"] = [16, 19]  # not
    else:
        del fact["qualifier_sources"]["condition"]
    with pytest.raises(ValueError, match="source|literal|operator|qualifier"):
        validate_requirement_graph(material)


@pytest.mark.parametrize("mutation", ["value", "predicate", "subject", "value_source"])
def test_semantic_operands_have_the_same_literal_source_obligation_as_main_business(mutation):
    material = graph(NARRATIVE)
    field = operand(material)
    assert (field["subject"], field["predicate"], field["value"]) == ("Delta", "is", "ready")
    if mutation == "value_source":
        field["value_source"]["text_span"] = [36, 42]  # Report
    else:
        field[mutation] = {"value": "blocked", "predicate": "owns", "subject": "Kappa"}[mutation]
    with pytest.raises(ValueError, match="source|literal|operand"):
        validate_requirement_graph(material)


@pytest.mark.parametrize("mutation", ["condition_summary", "condition_proof", "tree_subject", "tree_operator",
                                      "tree_operator_span", "tree_binding_source", "operand_relation"])
def test_nested_logic_and_its_condition_or_enumeration_sources_are_not_just_unchecked_metadata(mutation):
    material = graph(NARRATIVE)
    tree = material["logic"][0]
    fact = business(material)
    if mutation == "condition_summary":
        fact["qualifiers"]["conditions"][0]["operand"]["value"] = "blocked"
    elif mutation == "condition_proof":
        fact["qualifier_sources"]["conditions"][0]["operand_source"]["text_span"] = [36, 42]
    elif mutation == "tree_subject":
        tree["bindings"][0]["operand"]["subject"] = "Kappa"
    elif mutation == "tree_operator":
        tree["child"]["child"]["operator"] = "and"
    elif mutation == "tree_operator_span":
        tree["child"]["child"]["operator_spans"] = [[36, 42]]
    elif mutation == "tree_binding_source":
        tree["bindings"][0]["operator_source"]["text_span"] = [9, 11]  # is
    else:
        edge = next(e for e in material["operand_relations"] if e["type"] == "narrative_condition_scope")
        edge["binding_evidence"]["operand_logic"]["object_source"]["path"] = "<not-printed>"
    with pytest.raises(ValueError, match="source|literal|operator|condition|logic"):
        validate_requirement_graph(material)


@pytest.mark.parametrize("mutation", ["coordination", "context_path", "reporting_summary", "reporting_action", "restriction_summary"])
def test_derived_semantic_qualifiers_are_verified_against_their_own_source_bound_operator_tree(mutation):
    text = (NARRATIVE if mutation in {"coordination", "context_path"} else "The device that stores records is portable."
            if mutation == "restriction_summary" else "The auditor reported that Lumen is not solvent.")
    material = graph(text)
    fact = business(material)
    validate_requirement_graph(material)
    if mutation == "coordination":
        fact["qualifiers"]["coordination"] = "and"
    elif mutation == "context_path":
        fact["qualifiers"]["assertion_contexts"][0] = "unprinted_scope"
    elif mutation == "reporting_summary":
        fact["qualifiers"]["reporting"][0]["subject"] = "Another auditor"
    elif mutation == "reporting_action":
        material["logic"][0]["attribute"] = "say"
    else:
        fact["qualifiers"]["subject_restriction"]["value"] = "files"
    with pytest.raises(ValueError, match="source|literal|operator|qualifier|logic"):
        validate_requirement_graph(material)


def test_a_condition_cannot_borrow_a_valid_summary_and_proof_from_another_statement():
    material = graph(NARRATIVE + " If Kappa is blocked, Clerk may review Ledger or Record.")
    fields = [n for n in material["nodes"] if n["id"] in material["projections"]["B"]]
    assert [f["subject"] for f in fields] == ["Board", "Clerk"]
    assert fields[0]["qualifiers"]["conditions"][0]["operand"]["subject"] == "Delta"
    assert fields[1]["qualifiers"]["conditions"][0]["operand"]["subject"] == "Kappa"
    validate_requirement_graph(material)
    fields[0]["qualifiers"]["conditions"] = deepcopy(fields[1]["qualifiers"]["conditions"])
    fields[0]["qualifier_sources"]["conditions"] = deepcopy(fields[1]["qualifier_sources"]["conditions"])
    with pytest.raises(ValueError, match="condition|source|logic"):
        validate_requirement_graph(material)


def test_a_canonical_currency_is_still_bound_to_its_explicit_printed_currency_name():
    material = graph("Revenue:17人民币百万元")
    fact = business(material)
    assert fact["qualifiers"]["currency"] == "人民币"
    fact["qualifiers"]["currency"] = "CNY"
    validate_requirement_graph(material)
    fact["qualifiers"]["currency"] = "USD"
    with pytest.raises(ValueError, match="source|qualifier"):
        validate_requirement_graph(material)


def test_a_printed_dollar_symbol_cannot_prove_a_named_currency():
    material = graph("Revenue:$17")
    fact = business(material)
    assert "currency" not in fact["qualifiers"]
    fact["qualifiers"]["currency"] = "USD"
    fact.setdefault("qualifier_sources", {})["currency"] = {"path": PATH, "lines": [1, 1], "text_span": [8, 9]}
    with pytest.raises(ValueError, match="source|qualifier"):
        validate_requirement_graph(material)


@pytest.mark.parametrize("text,code", [("交易收入超过137亿元，同比增长5%。", "gt"),
    ("交易收入不超过137亿元，同比下降5%。", "lte")])
def test_comparison_and_change_codes_are_proved_by_their_actual_complete_operator_words(text, code):
    material = graph(text)
    fact = business(material)
    assert fact["qualifiers"]["comparison_operator"] == code
    validate_requirement_graph(material)
    fact["qualifiers"]["comparison_operator"] = "gte" if code == "gt" else "lt"
    with pytest.raises(ValueError, match="source|operator|qualifier"):
        validate_requirement_graph(material)
