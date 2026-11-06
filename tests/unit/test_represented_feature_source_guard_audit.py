"""Independent source-only guards distinguish retained unknowns from comparison."""

import json

import pytest

from moparse_eval.expected_readback import read_expected
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown


@pytest.mark.parametrize("tail", ["if the board approves", "unless a separate report is issued"])
def test_retained_composition_pending_is_not_a_comparable_semantic_feature(tmp_path, tail):
    # The independent oracle is: a conditional composition assertion cannot
    # be certified by this finite unconditional source grammar. Retaining its
    # text and pending scope proves transport, without interpreting its scope.
    raw = "Notes on pages 21 to 34 are part of this statement " + tail + ".\n"
    directory = tmp_path / "invented"
    directory.mkdir()
    (directory / "expected.md").write_text(raw, encoding="utf-8")
    (directory / "manifest.json").write_text(json.dumps({
        "markdown": {"path": "expected.md"}, "source_map": {
            "entries": [{"source_pages": [1], "markdown_lines": [1, 1]}]}}), encoding="utf-8")
    selected = read_expected({"id": "synthetic", "document_id": "invented", "source_pages": [1]}, tmp_path)
    graph = compile_requirement_graph(selected)
    validate_requirement_graph(graph, expected=selected)
    assert not graph["semantic_complete"]
    assert any(issue["reason"] == "document_composition_scope_unresolved" for issue in graph["unresolved"])
    assert not graph["logic"] and not graph["projections"]["B"]
    result = grade_layers(evaluation_projection(graph), read_candidate_markdown(raw))
    assert not result["publishable"]
    for side in ("expected", "candidate"):
        checks = result["semantic_comparison"]["feature_checks"][side]
        for feature in ("document_composition", "page_reference_binding"):
            assert checks[feature]["status"] == "unresolved"
            assert not checks[feature]["equivalent"]
    assert (directory / "expected.md").read_text(encoding="utf-8") == raw
