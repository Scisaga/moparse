"""An authorized input-scope deferral cannot absorb a new software omission."""

from copy import deepcopy

import pytest

from moparse_eval import reference_compiler
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    is_deferred_input_scope,
    validate_requirement_graph,
)
from moparse_eval.source_obligations import audit_source_obligations, validate_source_obligations


def selected():
    source = {"path": "<controlled>/complex-alibaba-2025-annual/expected.md", "lines": [230, 230]}
    declaration = {"kind": "mixed_page_selection_declaration", "reference": deepcopy(source),
                   "declared_source_pages": [10, 11], "outside_source_pages": [11]}
    text = "Revenue: 17"
    return {"sample_id": "alibaba-strategies-p009-010", "document_id": "complex-alibaba-2025-annual",
            "source_pages": [9, 10], "scope": [], "targets": [{"id": "printed:230", "kind": "text",
            "text": text, "raw_text": text, "raw": text, "reference": source, "cells": [], "parents": [],
            "has_children": False, "context": [], "selected_heading_context": [],
            "outside_selection_context": [declaration], "pages": [2]}]}


def test_a_retained_declared_boundary_does_not_become_zero_or_drop_the_fact():
    graph = compile_requirement_graph(selected())
    assert graph["semantic_complete"] and not graph["complete"]
    assert len(graph["projections"]["B"]) == 1
    assert len(graph["unresolved"]) == 1
    assert is_deferred_input_scope(graph["sample_id"], graph["unresolved"][0])
    validate_requirement_graph(graph)


def test_same_physical_source_cannot_hide_an_independent_business_omission_in_the_deferral(monkeypatch):
    original = reference_compiler.compile_reference_semantics

    def omit_business(expected):
        projected = original(expected)
        projected["business"] = []
        projected["relations"] = []
        return projected

    monkeypatch.setattr(reference_compiler, "compile_reference_semantics", omit_business)
    graph = compile_requirement_graph(selected())
    assert graph["semantic_complete"] is False
    assert any(is_deferred_input_scope(graph["sample_id"], issue) for issue in graph["unresolved"])
    semantic = [issue for issue in graph["unresolved"] if not is_deferred_input_scope(graph["sample_id"], issue)]
    assert semantic and any(issue.get("reason") == "source_obligation_pending" and "B" in issue["layers"] for issue in semantic)
    preserved = next(issue for issue in graph["unresolved"] if is_deferred_input_scope(graph["sample_id"], issue))
    ids = {item["id"]: item for item in graph["source_obligation_inventory"]["obligations"]}
    assert all(ids[ident]["kind"] == "authorization_dependency" for ident in preserved.get("source_obligation_ids", []))


def test_synchronized_deferral_claims_cannot_swallow_independent_semantic_pending():
    expected = selected()
    text = "The total gyrated 17."
    expected["targets"][0].update(text=text, raw_text=text, raw=text)
    graph = compile_requirement_graph(expected)
    assert graph["semantic_complete"] is False
    scope = next(issue for issue in graph["unresolved"] if is_deferred_input_scope(graph["sample_id"], issue))
    scope["source_obligation_ids"] = [row["obligation_id"] for row in graph["source_obligation_coverage"]["dispositions"]
                                      if row["status"] == "pending"]
    graph["unresolved"] = [scope]
    graph["semantic_complete"], graph["complete"] = True, False
    for row in graph["dispositions"]:
        for disposition in row["layers"].values():
            if disposition.get("status") == "unresolved":
                disposition["unresolved"] = [scope["id"]]
    # This guard must reject without relying on an outer canonical recompile;
    # all derivative lists and the completeness flag were changed together.
    with pytest.raises(ValueError, match="input_scope_context"):
        validate_requirement_graph(graph)


@pytest.mark.parametrize("mutation", ["missing_proof", "wrong_source"])
def test_deferred_authorization_ids_still_need_the_actual_issue_and_source_proof(mutation):
    graph = compile_requirement_graph(selected())
    [scope] = graph["unresolved"]
    assert scope.get("source_obligation_ids")
    if mutation == "missing_proof":
        scope["outside_selection"] = []
    else:
        scope["source"]["lines"] = [231, 231]
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    with pytest.raises(ValueError, match="input_scope_context"):
        validate_source_obligations(graph)
