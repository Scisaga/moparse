"""Hand-fixed identities: neither compiler output nor candidate answers are oracles."""

from copy import deepcopy

import pytest

from moparse_eval.entity_requirements import read_entity_requirements

SOURCE = {"path": "<entity-statement>", "lines": [12, 12]}


@pytest.mark.parametrize("text,attribute,value,role_span,value_span", [
    ("The borrower is Delta.", "borrower", "Delta", [4, 12], [16, 21]),
    ("Borrower:Delta", "Borrower", "Delta", [0, 8], [9, 14]),
    ("借款人为Delta", "借款人", "Delta", [0, 3], [4, 9]),
    ("貸款人為華星銀行。", "貸款人", "華星銀行", [0, 3], [4, 8]),
    ("The guarantor is Kappa.", "guarantor", "Kappa", [4, 13], [17, 22]),
    ("Issuer:Type17 Holdings", "Issuer", "Type17 Holdings", [0, 6], [7, 22]),
])
def test_explicit_role_identity_has_exact_printed_name_role_and_sources(text, attribute, value, role_span, value_span):
    before = deepcopy(SOURCE)
    result = read_entity_requirements(text, SOURCE, scope=["Parties"])
    assert result["matched"] is True and result["blockers"] == []
    assert len(result["facts"]) == 1
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"], fact["role"]) == ("", attribute, value, "identity")
    assert fact["scope"] == ["Parties"]
    assert fact["qualifiers"] == {} and fact["identity_facets"] == {}
    assert fact["attribute_source"]["text_span"] == role_span
    assert fact["value_source"]["text_span"] == value_span
    assert text[slice(*role_span)] == attribute and text[slice(*value_span)] == value
    assert result["text_spans"][0]["text"] == text
    assert SOURCE == before


def test_value_spelling_is_copied_without_case_name_or_business_normalization():
    result = read_entity_requirements("Borrower:Delta-17", SOURCE)
    changed = read_entity_requirements("Borrower:delta-17", SOURCE)
    assert result["facts"][0]["value"] == "Delta-17"
    assert changed["facts"][0]["value"] == "delta-17"
    assert result["facts"][0]["value"] != changed["facts"][0]["value"]


def test_quoted_legal_name_keeps_its_internal_punctuation_and_source():
    text = 'The borrower is "Delta Holdings Ltd.".'
    result = read_entity_requirements(text, SOURCE)
    [fact] = result["facts"]
    assert fact["value"] == "Delta Holdings Ltd."
    assert text[slice(*fact["value_source"]["text_span"])] == "Delta Holdings Ltd."
    assert fact["attribute"] == "borrower"


def test_existing_source_offset_is_preserved_in_role_and_value_provenance():
    result = read_entity_requirements("Borrower:Delta", {**SOURCE, "text_span": [40, 54]})
    [fact] = result["facts"]
    assert fact["attribute_source"]["text_span"] == [40, 48]
    assert fact["value_source"]["text_span"] == [49, 54]


@pytest.mark.parametrize("text", [
    "The collateral administrator is Delta.",
    "Collateral administrator:Delta",
    "The collateral administrator is delta.",
    "The company is Delta.",
    "主体为Delta。",
    "抵押品管理人为Delta。",
    "The borrower's name is Delta.",
    "The borrower means Delta.",
    "Delta is the borrower.",
    "The borrower is Delta or Kappa.",
    "The borrower is Delta and Kappa.",
    "The borrower is not Delta.",
    "The borrower is Delta if approved.",
    "借款人为Delta或Kappa。",
    "借款人不是Delta。",
    "Borrower:",
])
def test_important_unknown_or_qualified_entity_cannot_silently_disappear(text):
    result = read_entity_requirements(text, SOURCE)
    assert result["matched"] is True
    assert result["facts"] == []
    assert result["pending_requirements"]
    assert result["blockers"] and all(item["layers"] == ["B"] for item in result["blockers"])
    assert all(item["source"]["path"] == SOURCE["path"] for item in result["blockers"])


def test_mixed_identity_and_unread_prose_needs_explicit_remaining_scope():
    text = "The borrower is Delta. The board shall pay 17 credits."
    result = read_entity_requirements(text, SOURCE)
    assert len(result["facts"]) == 1 and result["facts"][0]["value"] == "Delta"
    assert result["unmatched_spans"]
    assert any(item["reason"] == "mixed_entity_prose_unsupported" for item in result["blockers"])


def test_two_separate_role_assignments_keep_both_original_occurrences():
    result = read_entity_requirements("The borrower is Delta. The lender is Kappa.", SOURCE)
    assert result["blockers"] == []
    assert [(f["attribute"], f["value"], f["role"]) for f in result["facts"]] == [
        ("borrower", "Delta", "identity"), ("lender", "Kappa", "identity")]
    assert result["facts"][1]["value_source"]["text_span"] == [37, 42]


@pytest.mark.parametrize("text", [
    "The board shall pay 17 credits.",
    "The borrower is required to pay 17 credits.",
    "The ordinary paragraph explains the process.",
    "這是正常的段落。", "天气是晴天。", "Weather is Sunny.", "The sky is Blue.",
    "這是董事會的報告。", "The ordinary paragraph is about the borrower.",
    "That is a director's explanation.",
    "Company:Delta", "Entity:Delta", "主体:Delta",
    "Revenue:17", "Status:Ready", "Name:Anchor",
])
def test_other_prose_and_existing_field_grammars_are_not_reclassified(text):
    result = read_entity_requirements(text, SOURCE)
    assert result["matched"] is False
    assert result["facts"] == [] and result["blockers"] == []
