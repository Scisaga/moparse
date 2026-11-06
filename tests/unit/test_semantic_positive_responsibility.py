"""Independent final-vote oracles through the production expected entry point."""

import json
from copy import deepcopy

import pytest

from moparse_eval.expected_readback import read_expected
from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown

ASSETS = "The company manages the assets of its subsidiaries and affiliates."
SWAPPED = "The company manages the assets of its affiliates and subsidiaries."
FOCUS = "We have sharpened our business focus to two core businesses of e-commerce and cloud."
FOCUS_SWAP = "We have sharpened our business focus to two core businesses of cloud and e-commerce."


def production(tmp_path, text):
    document = tmp_path / "invented"
    document.mkdir(exist_ok=True)
    (document / "expected.md").write_text(text + "\n")
    (document / "manifest.json").write_text(json.dumps({"markdown": {"path": "expected.md"},
        "source_map": {"entries": [{"source_pages": [1], "markdown_lines": [1, len(text.splitlines())]}]}}))
    expected = read_expected({"id": "fixture", "document_id": "invented", "source_pages": [1]}, tmp_path)
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    return graph, evaluation_projection(graph)


@pytest.mark.parametrize("text,candidate", [(ASSETS, ASSETS), (ASSETS, SWAPPED), (FOCUS, FOCUS_SWAP)])
def test_complete_semantic_responsibility_changes_final_votes_and_replays(tmp_path, text, candidate):
    # Oracle fixed before compiling: one main assertion; all its printed
    # attachments and both AND members retained, with literal T differences.
    oracle = {"business": 1, "B": 100, "L": 100, "literal_same": text == candidate}
    graph, required = production(tmp_path, text)
    assert graph["semantic_complete"], graph["unresolved"]
    assert len(required["business"]) == oracle["business"]
    result = grade_layers(required, read_candidate_markdown(candidate, sample_id="fixture"))
    assert result["publishable"], result["blockers"]
    for layer in ("B", "L"):
        assert result["layers"][layer]["score"] == oracle[layer]
        assert result["layers"][layer]["numerator"] == result["layers"][layer]["denominator"]
    assert (result["layers"]["T"]["score"] == 100) == oracle["literal_same"]
    assert len(required["business"]) == len(graph["projections"]["B"])
    assert len(required["relations"]) == len(graph["projections"]["L"])
    validate_evidence(result)


@pytest.mark.parametrize("candidate", [
    "The company manages the assets of its subsidiaries or affiliates.",
    "The company manages the assets of its subsidiaries.",
    "The company manages the assets of their affiliates and subsidiaries.",
    "The company manages the assets of its subsidiaries and manages its affiliates.",
    "The company manages the assets for its affiliates and subsidiaries.",
    "Another company manages the assets of its affiliates and subsidiaries.",
    SWAPPED + " " + SWAPPED,
])
def test_semantic_equivalence_never_cancels_identity_capacity_or_content_conflicts(tmp_path, candidate):
    graph, required = production(tmp_path, ASSETS)
    assert graph["semantic_complete"]
    result = grade_layers(required, read_candidate_markdown(candidate, sample_id="fixture"))
    assert result["layers"]["B"]["numerator"] == 0
    if result["publishable"]:
        validate_evidence(result)
    else:
        # A genuinely unsupported interpretation stays unavailable, never a
        # formally publishable zero. Report publication must reject it too.
        with pytest.raises(ValueError, match="incomplete software judgments"):
            validate_evidence(result)


@pytest.mark.parametrize("mutation", ["fact_value", "missing_relation", "wrong_relation_owner", "forged_complement"])
def test_ast_equivalence_cannot_supply_a_missing_fact_or_relation(tmp_path, mutation):
    _graph, required = production(tmp_path, FOCUS)
    actual = read_candidate_markdown(FOCUS_SWAP, sample_id="fixture")
    if mutation == "fact_value":
        actual["business"][0]["value"] = "unprinted value"
    else:
        edge = next(e for e in actual["relations"] if e["type"] == "narrative_prepositional_attachment")
        if mutation == "missing_relation":
            actual["relations"].remove(edge)
        elif mutation == "wrong_relation_owner":
            edge["right"]["subject"] = "Another company"
        else:
            edge["left"]["complement"] = "unprinted complement"
    result = grade_layers(required, actual)
    if mutation == "fact_value":
        assert not result["publishable"]
    else:
        assert result["layers"]["L"]["numerator"] < result["layers"]["L"]["denominator"]


def test_report_rejects_forged_positive_vote_and_responsibility_proof(tmp_path):
    _graph, required = production(tmp_path, ASSETS)
    result = grade_layers(required, read_candidate_markdown(SWAPPED, sample_id="fixture"))
    assert result["layers"]["B"]["score"] == 100
    validate_evidence(result)
    forged = deepcopy(result)
    row = next(row for row in forged["outcomes"] if row["layer"] == "B")
    row["semantic_comparison_status"] = "unearned"
    with pytest.raises(ValueError, match="semantic comparison"):
        validate_evidence(forged)
