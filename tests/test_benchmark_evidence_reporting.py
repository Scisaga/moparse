from __future__ import annotations

import copy
import json

import pytest

from benchmark import moparse_benchmark as bench
from benchmark.tools import enrich_evidence as reporting


def write(path, value):
    path.write_text(json.dumps(value))
    return path


@pytest.fixture
def evidence():
    return {
        "schema": "moparse-evidence/1",
        "id": "captured",
        "method_id": "mineru-advanced-txt-vllm-c2-glm",
        "cohort_id": "regression-504",
        "origin": "fresh_HTTP",
        "output_stage": "public-HTTP-GFM",
        "fresh_model_inference": None,
        "quality": {
            "core209": {
                "pass": 209,
                "total": 209,
                "gold_fingerprint": "frozen",
                "reader_fingerprint": "reader",
            }
        },
        "performance": {},
        "provenance": [],
        "qualification": {"deployment_acceptance": False},
        "received_MD_proofs": [{"document_id": "1210860446", "sha256": "a" * 64}],
        "server_deployment_verified": False,
    }


@pytest.fixture
def public_evaluation():
    return {
        "schema": "moparse-public-evaluation/1",
        "coverage": {"complete": True},
        "public_structure_aware": {
            "cases": [{"source": "1210860446", "MD_SHA256": "a" * 64}],
            "financial30": {"pass": 30},
            "stock": [{"source": "1210860446", "status": "pass"}],
            "normal_header_leaves_pass": 10,
            "supplements": {
                "normal33": {
                    "literal": {"target_count": 33, "literal_row_and_complete_header_pass": 32}
                }
            },
        },
    }


def test_source_reporting_extracts_separate_fixed_denominators(evidence, public_evaluation):
    original = copy.deepcopy(public_evaluation)
    result = reporting.source_gate_metrics(public_evaluation, evidence)
    assert {key: (value["pass"], value["total"]) for key, value in result.items()} == {
        "financial30": (30, 30),
        "shareholder_count1": (1, 1),
        "normal_continuation33": (32, 33),
        "normal_header10": (10, 10),
    }
    assert all(value["reader_fingerprint"] == "reader" for value in result.values())
    assert public_evaluation == original


def test_source_reporting_rejects_different_markdown(evidence, public_evaluation):
    public_evaluation["public_structure_aware"]["cases"][0]["MD_SHA256"] = "b" * 64
    with pytest.raises(ValueError, match="identity differs"):
        reporting.source_gate_metrics(public_evaluation, evidence)


def test_source_reporting_rejects_partial_coverage(evidence, public_evaluation):
    public_evaluation["coverage"]["complete"] = False
    with pytest.raises(ValueError, match="complete source coverage"):
        reporting.source_gate_metrics(public_evaluation, evidence)


def test_source_reporting_rejects_changed_frozen_total(evidence, public_evaluation):
    public_evaluation["public_structure_aware"]["supplements"]["normal33"]["literal"][
        "target_count"
    ] = 32
    with pytest.raises(ValueError, match="denominator differs"):
        reporting.source_gate_metrics(public_evaluation, evidence)


def test_external_readback_does_not_upgrade_inference_or_release(tmp_path, monkeypatch, evidence):
    monkeypatch.setattr(bench, "BENCH", tmp_path / "benchmark")
    source = write(tmp_path / "input.json", evidence)
    source_hash = bench.digest(source)
    deployment = write(
        tmp_path / "deployment.json",
        {"schema": "moparse-observed-deployment/1", "ready_and_source_matched": True},
    )
    output = tmp_path / "enriched.json"
    result = reporting.enrich(source, output, deployment=deployment)
    assert result["qualification"]["external_source_identity_verified"] is True
    assert result["server_deployment_verified"] is False
    assert result["fresh_model_inference"] is None
    assert result["qualification"]["deployment_acceptance"] is False
    assert bench.digest(source) == source_hash
    assert not bench.validate_evidence(result)
    with pytest.raises(ValueError, match="new output"):
        reporting.enrich(source, output)
    with pytest.raises(ValueError, match="new output"):
        reporting.enrich(source, source)


def test_release_proof_must_match_received_markdown(evidence):
    proof = {
        "schema": "moparse-source-release-acceptance/1",
        "documents": [{"document_id": "1210860446", "MD_SHA256": "b" * 64}],
    }
    with pytest.raises(ValueError, match="Markdown differs"):
        reporting.bind_release_gates(evidence, proof)


def test_evidence_schema_permits_unknown_inference():
    schema = bench.read(bench.BENCH / "schemas/evidence.schema.json")
    assert schema["properties"]["fresh_model_inference"]["type"] == ["boolean", "null"]
