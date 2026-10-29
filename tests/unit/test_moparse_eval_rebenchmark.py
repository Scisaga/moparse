"""Synthetic PDF materialization and calibration observations only."""

from __future__ import annotations

import copy
from pathlib import Path

import pymupdf
import pytest

from moparse_eval import rebenchmark


def manifest():
    return {
        "name": "synthetic-lite", "kind": "lite", "preflight_confirmed": True,
        "samples": [
            {"id": "one", "input": "inputs/one.pdf", "source_pages": [12, 13]},
            {"id": "two", "input": "inputs/two.pdf", "source_pages": [20, 21, 22]},
            {"id": "three", "input": "inputs/three.pdf", "source_pages": [50, 51, 52]},
        ],
        "suites": {"preflight8": ["one", "two", "three"]},
    }


def synthetic_dataset(tmp_path):
    dataset = tmp_path / "dataset"
    (dataset / "inputs").mkdir(parents=True)
    declaration = manifest()
    for sample in declaration["samples"]:
        with pymupdf.open() as document:
            for index, _source_page in enumerate(sample["source_pages"]):
                page = document.new_page(width=100 + 10 * index, height=200 + 10 * index)
                page.set_rotation(90 if index % 2 else 0)
            document.save(dataset / sample["input"])
    return dataset, declaration


def test_schedule_reuses_authored_selection_and_one_reference_free_mount(tmp_path, monkeypatch):
    dataset, declaration = synthetic_dataset(tmp_path)
    original = copy.deepcopy(declaration)
    real_plan = rebenchmark.cli.execution_plan
    calls = []

    def plan(value, root, suite):
        calls.append((value, root, suite))
        return real_plan(value, root, suite)

    monkeypatch.setattr(rebenchmark.cli, "execution_plan", plan)
    jobs, input_root = rebenchmark.build_preflight_jobs(declaration, dataset, tmp_path / "precheck")
    assert calls == [(declaration, dataset, "preflight8")]
    assert declaration == original
    assert input_root == tmp_path / "precheck/inputs" and input_root.name == "inputs"
    assert [job["sample_id"] for job in jobs[:3]] == ["one", "two", "three"]
    assert [job["input_page_count"] for job in jobs[:3]] == [2, 3, 3]
    assert all(job["suite"] == "preflight8" for job in jobs[:3])
    singles = jobs[3:]
    assert len(singles) == 8
    assert [(job["parent_sample_id"], job["local_page"]) for job in singles] == [
        ("one", 1), ("one", 2), ("two", 1), ("two", 2), ("two", 3),
        ("three", 1), ("three", 2), ("three", 3),
    ]
    assert len({job["output_dir"] for job in jobs}) == 11
    assert all(Path(job["pdf_path"]).is_relative_to(input_root) for job in jobs)
    assert all(job["suite"] == "calibration8" and job["input_page_count"] == 1 for job in singles)
    assert all("expected" not in job and "reference" not in job for job in jobs)
    assert not (tmp_path / "precheck/references").exists()
    # These PDF assertions examine synthetic fixture output, never real corpus.
    for job in singles:
        with pymupdf.open(job["pdf_path"]) as document:
            assert document.page_count == 1
            assert document[0].rotation == (90 if (job["local_page"] - 1) % 2 else 0)
            assert document[0].mediabox.width == 100 + 10 * (job["local_page"] - 1)


def test_preparation_does_not_overwrite_or_write_inside_dataset(tmp_path):
    dataset, declaration = synthetic_dataset(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        rebenchmark.build_preflight_jobs(declaration, dataset, dataset / "calibration")
    output = tmp_path / "precheck"
    output.mkdir()
    with pytest.raises(FileExistsError):
        rebenchmark.build_preflight_jobs(declaration, dataset, output)


def test_undeclared_or_reference_directory_input_is_rejected_before_creation(tmp_path):
    dataset, declaration = synthetic_dataset(tmp_path)
    declaration["samples"][0]["input"] = "references/not-input.pdf"
    with pytest.raises(ValueError, match="dataset inputs"):
        rebenchmark.build_preflight_jobs(declaration, dataset, tmp_path / "precheck")
    assert not (tmp_path / "precheck").exists()


def test_different_named_selection_is_not_silently_substituted(tmp_path):
    dataset, declaration = synthetic_dataset(tmp_path)
    declaration["suites"]["preflight8"] = ["one", "two"]
    with pytest.raises(ValueError, match="three samples and eight"):
        rebenchmark.build_preflight_jobs(declaration, dataset, tmp_path / "precheck")


def test_calibration_uses_only_new_successful_direct_single_page_observations():
    observations = [
        {"sample_id": "warmup", "suite": "preflight8", "status": "completed",
         "input_page_count": 3, "timing": {"processing_seconds": 9999}},
        {"sample_id": "one", "suite": "calibration8", "status": "completed",
         "input_page_count": 1, "timing": {"processing_seconds": 12.5}},
        {"sample_id": "two", "suite": "calibration8", "status": "completed",
         "input_page_count": 1, "timing": {"processing_seconds": 27.5}},
        {"sample_id": "failed", "suite": "calibration8", "status": "timeout",
         "input_page_count": 1, "timing": {"processing_seconds": 300},
         "errors": [{"category": "synthetic_timeout"}]},
        {"sample_id": "unknown", "suite": "calibration8", "status": "completed",
         "input_page_count": 1, "timing": {"processing_seconds": None}},
        {"sample_id": "not-single", "suite": "calibration8", "status": "completed",
         "input_page_count": 2, "timing": {"processing_seconds": 1000}},
    ]
    original = copy.deepcopy(observations)
    summary = rebenchmark.calibration_summary(observations)
    assert observations == original
    assert summary["slowest_successful_page_seconds"] == 27.5
    assert len(summary["incomplete_single_pages"]) == 3
    assert summary["incomplete_single_pages"][0]["errors"] == [{"category": "synthetic_timeout"}]
    assert summary["complete_calibration"] is False
    assert "metrics" not in summary and "quality" not in summary


def test_missing_or_failed_calibration_remains_unknown():
    summary = rebenchmark.calibration_summary([
        {"sample_id": "failed", "suite": "calibration8", "status": "failed",
         "input_page_count": 1, "timing": {"processing_seconds": 12}},
    ])
    assert summary["slowest_successful_page_seconds"] is None
    assert summary["complete_calibration"] is False


def test_preserved_native_structure_limit_is_measured_but_engineering_failure_is_not():
    observations = [{"sample_id": "native-limit", "suite": "calibration8", "status": "partial",
        "input_page_count": 1, "timing": {"processing_seconds": 11},
        "errors": [{"category": "candidate_native_structure", "native_preserved": True}]},
        {"sample_id": "adapter-bug", "suite": "calibration8", "status": "partial",
         "input_page_count": 1, "timing": {"processing_seconds": 999},
         "errors": [{"category": "engineering_failure"}]}]
    summary = rebenchmark.calibration_summary(observations)
    assert summary["slowest_successful_page_seconds"] == 11
    assert summary["successful_single_pages"][0]["native_structure_limitations"] == observations[0]["errors"]
    assert summary["incomplete_single_pages"][0]["sample_id"] == "adapter-bug"


@pytest.mark.parametrize("seconds, pages, expected", [(1, 1, 300), (40, 3, 360), (100, 20, 3600)])
def test_timeout_rule_has_declared_floor_multiplier_and_ceiling(seconds, pages, expected):
    assert rebenchmark.calibrated_timeout_seconds(seconds, pages) == expected


@pytest.mark.parametrize("seconds, pages", [(None, 1), (0, 1), (-1, 1), (True, 1),
                                            (float("nan"), 1), (float("inf"), 1),
                                            (1, 0), (1, -1), (1, True), (1, 1.5)])
def test_timeout_cannot_substitute_unknown_zero_or_invalid_declarations(seconds, pages):
    with pytest.raises(ValueError):
        rebenchmark.calibrated_timeout_seconds(seconds, pages)


def stable_runtime_evidence():
    return {"phase": "restored", "tts_policy": "keep_running",
            "tts_identity_condition": {"status": "unchanged", "before": {"MainPID": 10}, "after": {"MainPID": 10}},
            "tts_no_calls_condition": {"status": "no_observed_activity", "before_jobs": 4, "after_jobs": 4}}


def test_measurement_conditions_require_positive_stability_evidence_and_do_not_mutate_input():
    evidence = stable_runtime_evidence()
    original = copy.deepcopy(evidence)
    result = rebenchmark.assess_measurement_conditions(evidence)
    assert result["valid"] is True and result["status"] == "valid"
    assert result["problems"] == []
    assert evidence == original
    result["evidence"]["tts_identity_condition"]["after"]["MainPID"] = 20
    assert evidence == original


@pytest.mark.parametrize("field,value,condition", [
    ("phase", "restoration_failed", "maintenance.phase"),
    ("phase", "maintenance", "maintenance.phase"),
    ("tts_policy", "stop_and_restore", "tts_policy"),
    ("tts_identity_condition", {"status": "changed", "changed_keys": ["MainPID"]}, "tts_identity_condition.status"),
    ("tts_identity_condition", {"status": "unknown"}, "tts_identity_condition.status"),
    ("tts_identity_condition", None, "tts_identity_condition.status"),
    ("tts_no_calls_condition", {"status": "observed_activity", "new_jobs": 4}, "tts_no_calls_condition.status"),
    ("tts_no_calls_condition", {"status": "unknown"}, "tts_no_calls_condition.status"),
    ("tts_no_calls_condition", {}, "tts_no_calls_condition.status"),
])
def test_healthy_restoration_does_not_establish_valid_measurements(field, value, condition):
    evidence = stable_runtime_evidence()
    evidence[field] = value
    evidence["recovery_checks"] = {"moparse": True, "tts_ready": True}
    result = rebenchmark.assess_measurement_conditions(evidence)
    assert result["valid"] is False and result["status"] == "invalidated"
    assert result["problems"][0]["condition"] == condition
    assert result["problems"][0]["expected"] != result["problems"][0]["observed"]


def test_legacy_preflight_missing_identity_remains_unknown_without_rewriting_evidence():
    evidence = stable_runtime_evidence()
    del evidence["tts_identity_condition"]
    original = copy.deepcopy(evidence)
    result = rebenchmark.assess_measurement_conditions(evidence)
    assert result["valid"] is False
    assert result["observed"]["tts_identity_condition.status"] == "unknown"
    assert evidence == original and "tts_identity_condition" not in evidence
    assert rebenchmark.assess_measurement_conditions(None)["valid"] is False


@pytest.mark.parametrize("identity, activity", [
    ({"status": "changed"}, {"status": "observed_activity", "observed_new_jobs": 3}),
    ({"status": "unknown"}, {"status": "unknown", "error": "query unavailable"}),
    (None, None),
    ({"status": "unchanged"}, {"status": "no_observed_activity"}),
])
def test_explicit_observe_only_keeps_tts_conditions_as_qualifications(identity, activity):
    evidence = stable_runtime_evidence()
    evidence.update(tts_observation_policy="observe_only", user_instruction_date="2026-10-26",
                    tts_identity_condition=identity, tts_no_calls_condition=activity)
    original = copy.deepcopy(evidence)
    result = rebenchmark.assess_measurement_conditions(evidence)
    assert result["valid"] is True and result["status"] == "valid"
    assert result["problems"] == []
    assert result["observed"]["tts_observation_policy"] == "observe_only"
    assert result["qualifications"] and "uncontrolled" in result["qualifications"][0]
    if identity is None or identity["status"] != "unchanged":
        assert result["warnings"]
    assert evidence == original


@pytest.mark.parametrize("field,value", [("phase", "maintenance"), ("phase", "restoration_failed"),
                                        ("tts_policy", "stop_and_restore")])
def test_observe_only_still_requires_mo_restoration_and_keep_running(field, value):
    evidence = stable_runtime_evidence()
    evidence.update(tts_observation_policy="observe_only")
    evidence[field] = value
    assert rebenchmark.assess_measurement_conditions(evidence)["valid"] is False
