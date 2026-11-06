"""Invented gate-transport artifacts; never evidence for a real replay grant."""

import hashlib

from moparse_eval.packaging import write_json
from moparse_eval.requirement_gate import _EVIDENCE_CATEGORIES
from moparse_eval.requirement_graph import compile_requirement_graph, write_requirement_graph


def artifact(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def controlled_expected(sample_id="fixture"):
    target = {"id": "expected:L1:text", "kind": "text", "text": "Name: Delta; Revenue: 17",
              "raw_text": "Name: Delta; Revenue: 17", "raw": "Name: Delta; Revenue: 17",
              "reference": {"path": "<invented-gate-source>", "lines": [1, 1]},
              "pages": [1], "cells": [], "parents": [], "has_children": False,
              "context": [], "selected_heading_context": [], "outside_selection_context": []}
    return {"sample_id": sample_id, "document_id": "invented-document", "source_pages": [1],
                "standard": "expected_only", "targets": [target], "scope": [
                    {"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]}


def controlled_source_run(root, sample_id="fixture"):
    """Only authorization metadata; no candidate, source PDF or model output."""
    dataset, baseline = root / "dataset", root / "baseline"
    write_json(dataset / "manifest.json", {"samples": [
        {"id": sample_id, "document_id": "invented-document", "source_pages": [1]}]})
    write_json(baseline / "run.json", {"dataset": str(dataset), "cases": [
        {"sample_id": sample_id, "suite": "quality800", "phase": "measured"}]})
    return baseline


def controlled_gate(root, software_id="controlled-source", sample_id="fixture"):
    expected = controlled_expected(sample_id)
    graph = compile_requirement_graph(expected)
    assert graph["semantic_complete"] is True
    view = root / "samples" / f"{sample_id}.json"
    write_requirement_graph(graph, view, view.with_suffix(".xml"))
    row = {"sample_id": sample_id, "json": str(view.relative_to(root)),
           "generated_view_sha256": artifact(view)["sha256"], "semantic_complete": True,
           "source_obligation_inventory_complete": True, "inventory_validation": {"status": "passed"}}
    index = root / "index.json"
    write_json(index, {"purpose": "expected_output_requirements_not_corpus_review", "software_id": software_id,
                      "software_unchanged": True, "semantic_complete": True,
                      "source_obligation_inventory_complete": True, "inventory_validation": {"status": "passed"},
                      "records": [row]})
    return controlled_evidence(root, index, software_id)


def controlled_evidence(root, index, software_id):
    """Bind invented validation observations to an existing generated index."""
    gate = {"status": "passed", "software_id": software_id,
            "requirement_index": artifact(index), "evidence": {}}
    # These observations are invented transport fixtures. Actual validation
    # artifacts must carry observations made by independently executed cases.
    for purpose, categories in _EVIDENCE_CATEGORIES.items():
        evidence = root / f"{purpose}.json"
        write_json(evidence, {"schema": "moparse-independent-validation/1", "purpose": purpose,
            "software_id": software_id, "status": "passed", "requirement_index_sha256": artifact(index)["sha256"],
            "oracle_origin": "hand_authored_source_independent", "known_defects": [],
            "cases": [{"case_id": f"controlled-{category}", "category": category,
                       "input": {"fixture": category}, "expected": {"accepted": False}, "observed": {"accepted": False}}
                      for category in sorted(categories)]})
        gate["evidence"][purpose] = artifact(evidence)
    return {"status": "passed", "expected_structure_gate": gate}
