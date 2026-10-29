"""Scoring admission uses invented runtime metadata, never corpus files."""

from __future__ import annotations

import json

import pytest

from moparse_eval import cli


def _runtime_metadata(tmp_path, extra):
    run = tmp_path / "invented-run"
    run.mkdir()
    metadata = run / "run.json"
    metadata.write_text(json.dumps({"dataset": "/invalid-dataset-must-not-be-read", **extra}))
    return run, metadata


def _block_beyond_runtime_metadata(monkeypatch, metadata):
    original_read = cli.read_json
    reads = []

    def read_only_runtime_metadata(path):
        reads.append(path)
        assert path == metadata, "scoring admission must not read dataset or reference files"
        return original_read(path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("blocked scoring must not inspect software or write scoring artifacts")

    monkeypatch.setattr(cli, "read_json", read_only_runtime_metadata)
    monkeypatch.setattr(cli, "code_identity", forbidden)
    monkeypatch.setattr(cli, "snapshot_software", forbidden)
    monkeypatch.setattr(cli, "write_json", forbidden)
    return reads


@pytest.mark.parametrize("state", ["prepared", "running"])
def test_score_rejects_active_run_before_reading_dataset_or_writing_scores(tmp_path, monkeypatch, state):
    run, metadata = _runtime_metadata(tmp_path, {"state": state})
    reads = _block_beyond_runtime_metadata(monkeypatch, metadata)
    with pytest.raises(ValueError, match=f"active run state '{state}'.*service restoration"):
        cli.score_run(run)
    assert reads == [metadata]
    assert not (run / "artifacts").exists()
    assert json.loads(metadata.read_text())["state"] == state


@pytest.mark.parametrize("state, cleanup", [
    ("completed", None),
    ("completed", {}),
    ("completed", {"maintenance_phase": "maintenance"}),
    ("completed", {"maintenance_phase": "restoration_failed"}),
    ("failed", {"maintenance_phase": "maintenance"}),
])
def test_completed_development_arm_waits_for_driver_restoration_record(tmp_path, monkeypatch, state, cleanup):
    extra = {"state": state, "development_experiment": True, "experiment_id": "invented-experiment"}
    if cleanup is not None:
        extra["cleanup_evidence"] = cleanup
    run, metadata = _runtime_metadata(tmp_path, extra)
    reads = _block_beyond_runtime_metadata(monkeypatch, metadata)
    with pytest.raises(ValueError, match="before confirmed service restoration.*driver.*restored"):
        cli.score_run(run)
    assert reads == [metadata]
    assert not (run / "artifacts").exists()


@pytest.mark.parametrize("extra", [
    {"state": "completed", "development_experiment": True, "experiment_id": "invented-experiment",
     "cleanup_evidence": {"maintenance_phase": "restored"}},
    {"state": "failed", "development_experiment": True, "experiment_id": "invented-experiment",
     "cleanup_evidence": {"maintenance_phase": "restored"}},
    {"state": "completed"},
    {"state": "failed"},
    {},
])
def test_terminal_restored_or_legacy_runs_continue_to_normal_dataset_read(tmp_path, monkeypatch, extra):
    run, metadata = _runtime_metadata(tmp_path, extra)
    original_read = cli.read_json
    reads = []

    class NormalDatasetReadReached(RuntimeError):
        pass

    def stop_at_normal_dataset_read(path):
        reads.append(path)
        if path == metadata:
            return original_read(path)
        assert str(path) == "/invalid-dataset-must-not-be-read/manifest.json"
        raise NormalDatasetReadReached("normal dataset read reached without opening a dataset")

    def forbidden(*_args, **_kwargs):
        pytest.fail("this synthetic test must stop before software identity or scoring writes")

    monkeypatch.setattr(cli, "read_json", stop_at_normal_dataset_read)
    monkeypatch.setattr(cli, "code_identity", forbidden)
    monkeypatch.setattr(cli, "write_json", forbidden)
    with pytest.raises(NormalDatasetReadReached):
        cli.score_run(run)
    assert len(reads) == 2 and reads[0] == metadata
    assert not (run / "artifacts").exists()


@pytest.mark.parametrize("operation", ["score", "report"])
@pytest.mark.parametrize("condition", ["missing", "changed", "jobs", "unknown", "restoration_failed"])
def test_formal_gate_rejects_bad_runtime_conditions_before_any_reference_score_or_figure(
    tmp_path, monkeypatch, operation, condition,
):
    run, metadata = _runtime_metadata(tmp_path, {"formal": True, "state": "completed", "cases": [],
                                               "latest_scores": "scores/must-not-be-read.json"})
    maintenance = run / "maintenance.json"
    evidence = {"phase": "restored", "tts_policy": "keep_running",
                "tts_identity_condition": {"status": "unchanged"},
                "tts_no_calls_condition": {"status": "no_observed_activity"},
                "recovery_checks": {"moparse": True, "tts_ready": True}}
    if condition == "changed":
        evidence["tts_identity_condition"] = {"status": "changed"}
    elif condition == "jobs":
        evidence["tts_no_calls_condition"] = {"status": "observed_activity", "new_jobs": 1}
    elif condition == "unknown":
        evidence["tts_no_calls_condition"] = {"status": "unknown"}
    elif condition == "restoration_failed":
        evidence["phase"] = "restoration_failed"
    if condition != "missing":
        maintenance.write_text(json.dumps(evidence))
    original_read = cli.read_json
    reads = []

    def runtime_only(path):
        reads.append(path)
        assert path in {metadata, maintenance}, "blocked formal entry must not read references or scores"
        return original_read(path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("blocked formal entry must not inspect software, score, render or write outputs")

    monkeypatch.setattr(cli, "read_json", runtime_only)
    monkeypatch.setattr(cli, "code_identity", forbidden)
    monkeypatch.setattr(cli, "snapshot_software", forbidden)
    monkeypatch.setattr(cli, "write_json", forbidden)
    with pytest.raises(ValueError, match="formal measurement conditions are not satisfied"):
        (cli.score_run if operation == "score" else cli.report_run)(run)
    assert reads == [metadata, maintenance]
    assert not (run / "artifacts").exists()
    assert not (run / "figures").exists()
    assert not (run / "report.md").exists()


@pytest.mark.parametrize("operation", ["score", "report"])
@pytest.mark.parametrize("state", ["failed", "cancelled", "invalidated", "completed_with_preflight_failures"])
def test_formal_noncompleted_state_is_rejected_before_even_maintenance_read(tmp_path, monkeypatch, operation, state):
    run, metadata = _runtime_metadata(tmp_path, {"formal": True, "state": state})
    reads = _block_beyond_runtime_metadata(monkeypatch, metadata)
    with pytest.raises(ValueError, match="require state='completed'"):
        (cli.score_run if operation == "score" else cli.report_run)(run)
    assert reads == [metadata]


@pytest.mark.parametrize("operation", ["score", "report"])
@pytest.mark.parametrize("schedule", [
    {"suite": "lite"}, {"suite": "quality800"}, {"suite": "perf80"},
    {"cases": [{"suite": "quality800", "phase": "measured"}]},
])
def test_false_formal_flag_does_not_bypass_scheduler_declared_main_comparison(
    tmp_path, monkeypatch, operation, schedule,
):
    run, metadata = _runtime_metadata(tmp_path, {"formal": False, "state": "completed", **schedule})
    original_read = cli.read_json

    def runtime_only(path):
        assert path in {metadata, run / "maintenance.json"}
        return original_read(path)

    monkeypatch.setattr(cli, "read_json", runtime_only)
    with pytest.raises(ValueError, match="formal measurement conditions are not satisfied"):
        (cli.score_run if operation == "score" else cli.report_run)(run)
    assert not (run / "artifacts").exists()


def test_explicit_nonformal_development_keeps_existing_admission_without_reclassifying_perf_suite(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("formal runtime guard must not inspect metadata for an explicit nonformal development arm")

    monkeypatch.setattr(cli, "read_json", forbidden)
    cli._require_formal_measurement_conditions(tmp_path, {"formal": False, "suite": "perf80",
        "development_experiment": True, "experiment_id": "synthetic-development", "state": "completed",
        "cases": [{"suite": "perf80"}]})


@pytest.mark.parametrize("condition", ["changed", "jobs", "unknown"])
def test_formal_observe_only_gate_accepts_tts_variation_and_retains_hard_mo_restore(
    tmp_path, monkeypatch, condition,
):
    run, metadata = _runtime_metadata(tmp_path, {"formal": True, "state": "completed", "cases": []})
    evidence = {"phase": "restored", "tts_policy": "keep_running", "tts_observation_policy": "observe_only",
                "user_instruction_date": "2026-10-26", "tts_identity_condition": {"status": "unchanged"},
                "tts_no_calls_condition": {"status": "no_observed_activity"}}
    if condition == "changed":
        evidence["tts_identity_condition"] = {"status": "changed"}
    elif condition == "jobs":
        evidence["tts_no_calls_condition"] = {"status": "observed_activity", "observed_new_jobs": 1}
    else:
        evidence.pop("tts_identity_condition")
        evidence["tts_no_calls_condition"] = {"status": "unknown"}
    maintenance = run / "maintenance.json"
    maintenance.write_text(json.dumps(evidence))
    original_read = cli.read_json

    def runtime_only(path):
        assert path in {metadata, maintenance}, "admission test reads runtime metadata only"
        return original_read(path)

    monkeypatch.setattr(cli, "read_json", runtime_only)
    session = original_read(metadata)
    cli._require_formal_measurement_conditions(run, session)
    evidence["phase"] = "restoration_failed"
    maintenance.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="formal measurement conditions are not satisfied"):
        cli._require_formal_measurement_conditions(run, session)
