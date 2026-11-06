"""Source-selected heading ownership survives coherent derived scope edits."""

from copy import deepcopy

import pytest

from moparse_eval.expected_readback import read_expected
from moparse_eval.packaging import write_json
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.source_obligations import audit_source_obligations


def expected():
    path = "<independent-heading-ownership>"
    heading_source = {"path": path, "lines": [1, 1]}
    targets = [{"id": "heading", "kind": "heading", "text": "North", "raw_text": "North", "raw": "# North",
                "reference": heading_source, "heading_level": 1, "cells": [], "parents": [], "has_children": False,
                "context": [], "selected_heading_context": [], "outside_selection_context": [], "pages": [1]},
               {"id": "content", "kind": "text", "text": "Revenue: 17", "raw_text": "Revenue: 17", "raw": "Revenue: 17",
                "reference": {"path": path, "lines": [2, 2]}, "cells": [], "parents": [], "has_children": False,
                "context": ["North"], "selected_heading_context": [{"text": "North", "reference": heading_source}],
                "outside_selection_context": [], "pages": [1]}]
    return {"sample_id": "invented-heading-ownership", "targets": targets, "source_pages": [1]}


def test_source_heading_has_actual_role_and_relation_evidence_before_acceptance():
    reference = expected()
    original = deepcopy(reference)
    graph = compile_requirement_graph(reference)
    assert graph["semantic_complete"]
    scope = [item for item in graph["source_obligation_inventory"]["obligations"]
             if item.get("binding_role") == "heading_scope"]
    assert len(scope) == 1 and scope[0]["required_scope"][0]["text"] == "North"
    row = next(item for item in graph["source_obligation_coverage"]["dispositions"] if item["obligation_id"] == scope[0]["id"])
    assert row["status"] == "explained" and any("relation" in item for item in row["evidence"])
    validate_requirement_graph(graph, expected=reference)
    assert reference == original


def test_all_derived_scopes_cannot_move_a_real_fact_to_another_heading():
    graph = compile_requirement_graph(expected())
    for node in graph["nodes"]:
        if node["id"] in graph["projections"]["B"]:
            node["scope"] = ["South"]
    for edge in graph["relations"]:
        if isinstance(edge.get("right"), dict) and "scope" in edge["right"]:
            edge["right"]["scope"] = ["South"]
        if edge["type"] == "prose_heading_membership":
            edge["left"] = ["South"]
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert coverage["semantic_complete"] is False
    obligations = {item["id"]: item for item in graph["source_obligation_inventory"]["obligations"]}
    assert any(row["status"] == "pending" and obligations[row["obligation_id"]].get("binding_role") == "heading_scope"
               for row in coverage["dispositions"])


def test_raw_heading_obligation_survives_upstream_context_omission(tmp_path):
    folder = tmp_path / "invented"
    folder.mkdir()
    raw = "# North\n\nRevenue: 17\n"
    (folder / "expected.md").write_text(raw)
    write_json(folder / "manifest.json", {"markdown": {"path": "expected.md"},
        "source_map": {"entries": [{"source_pages": [1], "markdown_lines": [1, 3]}]}})
    reference = read_expected({"id": "invented-heading", "document_id": "invented", "source_pages": [1]}, tmp_path)
    reference["targets"][1]["selected_heading_context"] = []
    graph = compile_requirement_graph(reference)
    assert graph["source_obligation_inventory"]["source_complete"] is True
    assert graph["semantic_complete"] is False
    raw_scope = [item for item in graph["source_obligation_inventory"]["obligations"]
                 if item.get("raw_scope_evidence") and item["source"]["lines"] == [3, 3]]
    assert raw_scope and raw_scope[0]["required_scope"][0]["text"] == "North"
    assert any(row["obligation_id"] == raw_scope[0]["id"] and row["status"] == "pending"
               for row in graph["source_obligation_coverage"]["dispositions"])
    assert (folder / "expected.md").read_text() == raw


@pytest.mark.parametrize("mutation", ["wrong_owner_scope", "one_owner_binding_missing"])
def test_text_membership_cannot_hide_a_business_owners_missing_or_wrong_scope(mutation):
    reference = expected()
    text = "Board approves dividends. Board reviews the report."
    reference["targets"][1].update(text=text, raw_text=text, raw=text)
    graph = compile_requirement_graph(reference)
    assert graph["semantic_complete"]
    assert any(edge["type"] == "prose_heading_membership" for edge in graph["relations"])
    [fact, _other] = [node for node in graph["nodes"] if node["id"] in graph["projections"]["B"]]
    bindings = [edge for edge in graph["relations"] if edge["type"] == "field_binding"
                and edge.get("right", {}).get("attribute") == fact["attribute"]]
    assert len(bindings) == 1
    if mutation == "wrong_owner_scope":
        fact["scope"] = ["South"]
        bindings[0]["right"]["scope"] = ["South"]
    else:
        graph["relations"].remove(bindings[0])
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    heading_ids = {item["id"] for item in graph["source_obligation_inventory"]["obligations"]
                   if item.get("binding_role") == "heading_scope"}
    assert any(row["obligation_id"] in heading_ids and row["status"] == "pending"
               for row in coverage["dispositions"])
    assert coverage["semantic_complete"] is False


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_a_raw_level_one_heading_rejects_an_invented_selected_ancestor_or_child(tmp_path, order):
    folder = tmp_path / "invented"
    folder.mkdir()
    raw = "# South\n\n# North\n\nRevenue: 17\n"
    (folder / "expected.md").write_text(raw)
    write_json(folder / "manifest.json", {"markdown": {"path": "expected.md"},
        "source_map": {"entries": [{"source_pages": [1], "markdown_lines": [1, 5]}]}})
    reference = read_expected({"id": "invented-heading", "document_id": "invented", "source_pages": [1]}, tmp_path)
    heads = reference["targets"][:2]
    reference["targets"][2]["selected_heading_context"] = [
        {"text": heads[index]["text"], "reference": deepcopy(heads[index]["reference"])} for index in order]
    graph = compile_requirement_graph(reference)
    assert graph["semantic_complete"] is False
    assert graph["source_obligation_inventory"]["source_complete"] is True
    assert any(item.get("scope_is_absolute") for item in graph["source_obligation_inventory"]["obligations"])
