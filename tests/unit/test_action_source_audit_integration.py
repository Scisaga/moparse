"""Independent action-role oracles through the production expected path.

Only invented temporary Markdown and explicit page selections are read. The
oracles below predate compilation; neither reader output nor a derived view
supplies the expected business answers.
"""

import json
from copy import deepcopy

import pytest

from moparse_eval.expected_readback import read_expected
from moparse_eval.expected_report import validate_evidence
from moparse_eval.narrative_requirements import read_narrative
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.source_obligations import (
    audit_source_obligations,
    build_source_obligation_inventory,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown

CASES = [
    ("The company helps customers.", "help", "customers", "present"),
    ("The company helped customers.", "help", "customers", "past"),
    ("The company leverages platforms.", "leverage", "platforms", "present"),
    ("The company leveraged platforms.", "leverage", "platforms", "past"),
    ("The company engages customers.", "engage", "customers", "present"),
    ("The company captures demand.", "capture", "demand", "present"),
]


def _authored(tmp_path, text):
    directory = tmp_path / "invented-action"
    directory.mkdir()
    (directory / "expected.md").write_text(text + "\n", encoding="utf-8")
    (directory / "manifest.json").write_text(json.dumps({
        "markdown": {"path": "expected.md"},
        "source_map": {"entries": [{"source_pages": [1], "markdown_lines": [1, len(text.splitlines())]}]},
    }), encoding="utf-8")
    return read_expected({"id": "invented-action", "document_id": "invented-action", "source_pages": [1]}, tmp_path)


@pytest.mark.parametrize("text,action,obj,tense", CASES)
def test_supported_action_survives_production_compilation_audit_projection_and_final_grade(
        tmp_path, text, action, obj, tense):
    authored = _authored(tmp_path, text)
    before = deepcopy(authored)
    inventory = build_source_obligation_inventory(authored)
    direct = read_narrative(text, authored["targets"][0]["reference"])
    assert direct["complete"]
    assert [(row["subject"], row["attribute"], row["object"]) for row in direct["facts"]] == [
        ("The company", action, obj)]
    graph = compile_requirement_graph(authored)
    assert graph["source_obligation_inventory"] == inventory
    assert graph["semantic_complete"], graph["unresolved"]
    audit = audit_source_obligations(inventory, graph)
    assert audit["semantic_complete"]
    assert all(row["status"] != "pending" for row in audit["dispositions"])
    assert any(row["semantic_type"] == "assertive_proposition" for row in inventory["obligations"])
    validate_requirement_graph(graph, expected=authored)
    projection = evaluation_projection(graph)
    assert [(row["subject"], row["attribute"], row["object"], row["qualifiers"]["tense"])
            for row in projection["business"]] == [("The company", action, obj, tense)]
    result = grade_layers(projection, read_candidate_markdown(text, sample_id="invented-action"))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["L"]["numerator"] == result["layers"]["L"]["denominator"]
    validate_evidence(result)
    assert authored == before


def test_printed_reference_field_bridges_local_label_and_directive_sources(tmp_path):
    authored = _authored(tmp_path, "Revenue: See Note 3.")
    graph = compile_requirement_graph(authored)
    assert graph["semantic_complete"], graph["unresolved"]
    [reference] = graph["explicit_references"]
    assert reference["target"] == {"role": "reference_target", "kind": "numbered_reference",
                                  "reference_kind": "note", "identifier": "3"}
    assert reference["owner_proof"]["owner"] == {
        "identity": {"role": "printed_field", "attribute": "Revenue"}, "scope": []}
    assert graph["projections"]["B"] == []
    assert len(graph["projections"]["L"]) == 2
    validate_requirement_graph(graph, expected=authored)
    result = grade_layers(evaluation_projection(graph),
                          read_candidate_markdown("Revenue: See Note 3.", sample_id="invented-action"))
    assert result["layers"]["L"]["score"] == 100
    assert result["layers"]["L"]["numerator"] == result["layers"]["L"]["denominator"] == 2
    assert result["layers"]["B"]["denominator"] == 0
    validate_evidence(result)


@pytest.mark.parametrize("mutation", ["owner", "neighbor_owner", "neighbor_directive", "missing_scope_edge", "missing_target_edge"])
def test_printed_reference_binding_cannot_borrow_an_owner_or_adjacent_directive(tmp_path, mutation):
    authored = _authored(tmp_path, "Revenue: See Note 3.\n\nCost: See Note 4.")
    graph = compile_requirement_graph(authored)
    assert graph["semantic_complete"], graph["unresolved"]
    reference = graph["explicit_references"][0]
    first_edges = [edge for edge in graph["relations"] if edge["source"]["lines"] == [1, 1]]
    if mutation == "owner":
        reference["owner_proof"]["owner"]["identity"]["attribute"] = "Cost"
        for edge in first_edges:
            edge["binding_evidence"]["owner_proof"]["owner"]["identity"]["attribute"] = "Cost"
            if edge["type"] == "explicit_reference_target":
                edge["left"]["owner"]["identity"]["attribute"] = "Cost"
            else:
                edge["left"]["identity"]["attribute"] = "Cost"
                edge["right"]["owner"]["identity"]["attribute"] = "Cost"
    elif mutation == "neighbor_owner":
        reference["owner_proof"]["evidence"][0]["source"]["lines"] = [3, 3]
        for edge in first_edges:
            edge["binding_evidence"]["owner_proof"]["evidence"][0]["source"]["lines"] = [3, 3]
    elif mutation == "neighbor_directive":
        reference["source"]["lines"] = [3, 3]
        for edge in first_edges:
            edge["source"]["lines"] = [3, 3]
    else:
        drop_type = "reference_directive_scope" if mutation == "missing_scope_edge" else "explicit_reference_target"
        graph["relations"] = [edge for edge in graph["relations"] if edge not in first_edges or edge["type"] != drop_type]
    audit = audit_source_obligations(graph["source_obligation_inventory"], graph)
    obligations = {row["id"]: row for row in graph["source_obligation_inventory"]["obligations"]}
    own = [row for row in audit["dispositions"] if row["obligation_id"] in obligations
           and obligations[row["obligation_id"]].get("binding_role") == "navigation"
           and obligations[row["obligation_id"]]["source"]["lines"] == [1, 1]]
    assert len(own) == 1 and own[0]["status"] == "pending"



@pytest.mark.parametrize("text", ["The company helpeth customers.", "The company leveragged platforms."])
def test_unknown_action_is_not_stemmed_or_discarded(tmp_path, text):
    authored = _authored(tmp_path, text)
    inventory = build_source_obligation_inventory(authored)
    graph = compile_requirement_graph(authored)
    assert inventory["obligations"]
    assert not graph["semantic_complete"]
    assert graph["unresolved"]
    assert not graph["projections"]["B"]
    assert any(row["status"] == "pending" for row in graph["source_obligation_coverage"]["dispositions"])
    validate_requirement_graph(graph, expected=authored)


def test_original_owns_cannot_prove_forged_acquire_even_with_matching_shared_lexicon(tmp_path):
    authored = _authored(tmp_path, "The company owns Kappa.")
    graph = compile_requirement_graph(authored)
    assert graph["semantic_complete"]
    forged = deepcopy(graph)
    fact_ids = set(forged["projections"]["B"])
    for fact in forged["nodes"]:
        if fact["id"] in fact_ids:
            fact["attribute"] = "acquire"
    for edge in forged["relations"]:
        if edge.get("fact_id") in fact_ids:
            edge["left"]["attribute"] = edge["right"]["attribute"] = "acquire"
    audit = audit_source_obligations(graph["source_obligation_inventory"], forged)
    assert not audit["semantic_complete"]
    assert any(row["status"] == "pending" for row in audit["dispositions"])


def test_source_inventory_enumerates_unknown_actions_without_reading_semantic_success(tmp_path, monkeypatch):
    authored = _authored(tmp_path, "The company helps customers.")
    inventory = build_source_obligation_inventory(authored)
    monkeypatch.setattr("moparse_eval.narrative_requirements.read_narrative", lambda *_a, **_k: pytest.fail("inventory imported reader"))
    assert build_source_obligation_inventory(authored) == inventory


@pytest.mark.parametrize("text", [
    "The following chart sets forth the main businesses by segment:",
    "Other operating arrangements：",
    "Unexplained business labels =",
])
def test_empty_field_labels_keep_terminal_delimiter_in_literal_projection_without_erasing_semantic_pending(
        tmp_path, text):
    authored = _authored(tmp_path, text)
    graph = compile_requirement_graph(authored)
    text_nodes = [row for row in graph["nodes"] if row["id"] in graph["projections"]["T"]]
    assert "".join(row["text"] for row in text_nodes) == text
    assert [row["source"]["text_span"] for row in text_nodes] == [[0, len(text)]]
    literal = [row for row in graph["source_obligation_inventory"]["obligations"] if row["kind"] == "text"]
    assert literal
    coverage = {row["obligation_id"]: row for row in graph["source_obligation_coverage"]["dispositions"]}
    assert all(coverage[row["id"]]["status"] == "explained" for row in literal)
    assert not graph["semantic_complete"]
    assert any(set(row["layers"]) & {"B", "L"} for row in graph["unresolved"])
    validate_requirement_graph(graph, expected=authored)


@pytest.mark.parametrize("text", ["Market Report / 市場報告：17", "Allocation Report: 11; Volume Report: 23"])
def test_exact_T_field_sources_bridge_delimiters_without_treating_noun_Report_as_a_predicate(tmp_path, text):
    authored = _authored(tmp_path, text)
    graph = compile_requirement_graph(authored)
    obligations = {row["id"]: row for row in graph["source_obligation_inventory"]["obligations"]}
    literal = [row for row in graph["source_obligation_coverage"]["dispositions"]
               if row["obligation_id"] in obligations and obligations[row["obligation_id"]]["kind"] == "text"]
    assert literal and all(row["status"] == "explained" for row in literal)
    # Lexical ambiguity in B/L remains the responsibility of those layers.
    assert any(row["reason"] == "source_obligation_pending" and row.get("obligation_kind") == "relation"
               for row in graph["unresolved"])
    validate_requirement_graph(graph, expected=authored)


@pytest.mark.parametrize("mutation", ["label_removed", "value_removed", "neighbor_attribute_source", "number_hidden"])
def test_T_delimiter_bridge_requires_both_actual_local_literals_and_never_hides_a_number(tmp_path, mutation):
    authored = _authored(tmp_path, "Market Report / 市場報告：17")
    graph = compile_requirement_graph(authored)
    text_nodes = [row for row in graph["nodes"] if row["id"] in graph["projections"]["T"]]
    label, value = text_nodes
    if mutation in {"label_removed", "value_removed"}:
        graph["projections"]["T"].remove((label if mutation == "label_removed" else value)["id"])
    elif mutation == "neighbor_attribute_source":
        value["source"]["attribute_source"]["lines"] = [3, 3]
    else:
        graph["projections"]["T"].remove(value["id"])
        graph["context"]["text_projection"]["controls"].append({"text": "17", "source": value["source"]})
    audit = audit_source_obligations(graph["source_obligation_inventory"], graph)
    obligations = {row["id"]: row for row in graph["source_obligation_inventory"]["obligations"]}
    literal = [row for row in audit["dispositions"] if row["obligation_id"] in obligations
               and obligations[row["obligation_id"]]["kind"] == "text"]
    assert len(literal) == 1 and literal[0]["status"] == "pending"
