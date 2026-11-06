"""Independent metadata/narrative boundaries and guarded literal positives.

These invented source strings test the scope of metadata masking. A field
label never masks a subsequent unlabelled assertion; actual quoted names and
single literal URL/initials fields retain their printed punctuation.
"""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.source_obligations import audit_source_obligations

PATH = "<invented-metadata-boundaries>"


def expected(text):
    return {"sample_id": "invented-metadata-boundaries", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": [{"id": "printed:1", "kind": "text",
            "text": text, "raw_text": text, "raw": text, "reference": {"path": PATH, "lines": [1, 1]},
            "cells": [], "parents": [], "has_children": False, "context": [], "selected_heading_context": [],
            "outside_selection_context": [], "pages": [1], "heading_level": None}],
        "scope": [{"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]}


def business(graph):
    bank = {node["id"]: node for node in graph["nodes"]}
    return [bank[ident] for ident in graph["projections"]["B"]]


@pytest.mark.parametrize("prefix", ["Name: Lumen", "Role: Founder"])
@pytest.mark.parametrize("separator", ["; ", "\n"], ids=["semicolon", "linebreak"])
@pytest.mark.parametrize("modifier,marker", [("when authorized", "when"), ("until revoked", "until"), ("since 2028", "since")])
def test_metadata_cannot_mask_the_unsupported_scope_of_a_subsequent_unlabelled_assertion(prefix, separator, modifier, marker):
    body = f"Lumen owns Kappa {modifier}."
    text = prefix + separator + body
    authored = expected(text)
    graph = compile_requirement_graph(authored)
    assert graph["semantic_complete"] is False
    [operator] = [row for row in graph["source_obligation_inventory"]["obligations"]
                  if row["kind"] == "qualifier" and row["text"] == marker]
    assert operator["source"]["text_span"] == [text.index(marker), text.index(marker) + len(marker)]
    [disposition] = [row for row in graph["source_obligation_coverage"]["dispositions"]
                     if row["obligation_id"] == operator["id"]]
    assert disposition["status"] == "pending"
    assert body in "".join(node["text"] for node in graph["nodes"] if node["id"] in graph["projections"]["T"])
    validate_requirement_graph(graph, expected=authored)


@pytest.mark.parametrize("modifier,marker", [("when authorized", "when"), ("until revoked", "until"), ("since 2028", "since")])
def test_an_explicit_description_label_retains_the_same_unsupported_operator_as_an_unlabelled_assertion(modifier, marker):
    text = f"Name: Lumen; Description: Lumen owns Kappa {modifier}."
    graph = compile_requirement_graph(expected(text))
    assert graph["semantic_complete"] is False
    [operator] = [row for row in graph["source_obligation_inventory"]["obligations"]
                  if row["kind"] == "qualifier" and row["text"] == marker]
    assert text[slice(*operator["source"]["text_span"])] == marker
    assert any(row["obligation_id"] == operator["id"] and row["status"] == "pending"
               for row in graph["source_obligation_coverage"]["dispositions"])
    validate_requirement_graph(graph)


@pytest.mark.parametrize("text,label,value", [
    ("Name: Delta A. Kappa", "Name", "Delta A. Kappa"),
    ("Name: Vega; Holdings Ltd.", "Name", "Vega; Holdings Ltd."),
    ("Company: Sigma; Group LLC", "Company", "Sigma; Group LLC"),
    ('Name: "Lumen; Holdings"', "Name", '"Lumen; Holdings"'),
    ('Name: "Lumen when authorized; Since Holdings"', "Name", '"Lumen when authorized; Since Holdings"'),
    ("URL: https://example.invalid/when?since=2028", "URL", "https://example.invalid/when?since=2028"),
    ("Role: Founder and Chairman", "Role", "Founder and Chairman"),
])
def test_source_bounded_metadata_literals_keep_initials_quoted_semicolons_and_URL_punctuation(text, label, value):
    authored = expected(text)
    original = deepcopy(authored)
    graph = compile_requirement_graph(authored)
    [fact] = business(graph)
    assert (fact["attribute"], fact["value"]) == (label, value)
    assert graph["semantic_complete"] is True and not graph["unresolved"]
    assert not any(row["kind"] == "qualifier" for row in graph["source_obligation_inventory"]["obligations"])
    validate_requirement_graph(graph, expected=authored)
    assert authored == original


def test_a_later_business_assertion_cannot_be_removed_and_widened_into_the_metadata_value():
    text = "Name: Lumen; Lumen owns Kappa."
    graph = compile_requirement_graph(expected(text))
    first, second = business(graph)
    assert [(fact["attribute"], fact["value"]) for fact in (first, second)] == [("Name", "Lumen"), ("own", "Kappa")]
    removed_edges = {row["id"] for row in graph["relations"] if row.get("fact_id") == second["id"]
                     or row.get("right", {}).get("attribute") == "own"}
    graph["nodes"] = [row for row in graph["nodes"] if row["id"] != second["id"]]
    graph["relations"] = [row for row in graph["relations"] if row["id"] not in removed_edges]
    graph["projections"]["B"].remove(second["id"])
    graph["projections"]["L"] = [ident for ident in graph["projections"]["L"] if ident not in removed_edges]
    first["value"] = text[6:]
    first["value_source"] = {"path": PATH, "lines": [1, 1], "text_span": [6, len(text)]}
    first["source"] = deepcopy(first["value_source"])
    for row in graph["dispositions"]:
        for disposition in row["layers"].values():
            disposition["requirements"] = [ident for ident in disposition["requirements"]
                                           if ident != second["id"] and ident not in removed_edges]
            if disposition["status"] == "interpreted" and not disposition["requirements"]:
                disposition.update(status="not_applicable", rule_id="fabricated_metadata_scope", reason="fabricated metadata scope")
    # Neither full T retention nor an opaque Name value may explain owns/Kappa.
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    graph["source_obligation_coverage"] = coverage
    assert coverage["semantic_complete"] is False
    assert any(row["status"] == "pending" and "L" in row["layers"] for row in coverage["dispositions"])
