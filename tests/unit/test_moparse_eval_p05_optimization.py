"""P05 optimization tests use invented metadata and mocked owned services."""

from __future__ import annotations

import asyncio
import copy
import json
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import pytest

from moparse_eval import p05_optimization as optimization
from moparse_eval.packaging import read_json, write_json
from moparse_eval.runtime import PreparationError


def declaration():
    return {
        "name": "invented-lite", "kind": "lite", "state": "frozen",
        "freeze_record": {"author": "invented-author"}, "preflight_confirmed": True,
        "samples": [
            {"id": "alpha", "input": "inputs/alpha.pdf", "source_pages": [1, 2]},
            {"id": "beta", "input": "inputs/beta.pdf", "source_pages": [3, 4]},
            {"id": "gamma", "input": "inputs/gamma.pdf", "source_pages": [5, 6, 7, 8]},
            {"id": "delta", "input": "inputs/delta.pdf", "source_pages": [10]},
        ],
        "suites": {"preflight8": ["alpha", "beta", "gamma"],
                   "perf80": ["delta", "beta"], "lite": ["alpha", "beta", "gamma", "delta"]},
    }


def configuration():
    return {
        "pipeline": "P05", "dpi": 200,
        "timeout_policy": {"frozen": True, "single_page_seconds": 54.0},
        "inference_services": [{
            "role": "glm", "family": "glm", "inference_image": "invented-image",
            "host_model_path": "/invented-model-not-read", "model_name": "invented-glm",
            "port": 12541, "cpus": 4, "memory_gib": 20, "gpu_memory_gib": 20,
        }],
        "graphs": {"mode": "FULL_DECODE_ONLY"},
        "glm_decoding_declared": {"repetition_penalty": 1.1},
    }


def test_pilot_schedule_keeps_existing_ids_order_and_independent_paths(tmp_path):
    authored = declaration()
    before = copy.deepcopy(authored)
    jobs = optimization.optimization_jobs(authored, tmp_path, "pilot8")
    assert authored == before
    assert len(jobs) == 12
    assert [job["sample_id"] for job in jobs] == ["alpha", "beta", "gamma"] * 4
    assert [(job["phase"], job["suite"], job["repetition"]) for job in jobs[::3]] == [
        ("warmup", "preflight8", 1), ("measured", "pilot8", 1),
        ("measured", "pilot8", 2), ("measured", "pilot8", 3),
    ]
    assert len({job["output_dir"] for job in jobs}) == 12
    assert jobs[2]["input_page_count"] == 4
    assert all(Path(job["pdf_path"]).is_relative_to(tmp_path / "inputs") for job in jobs)
    assert all("reference" not in job and "expected" not in job for job in jobs)


def test_perf80_consumes_existing_suite_without_inventing_800_jobs(tmp_path):
    jobs = optimization.optimization_jobs(declaration(), tmp_path, "perf80")
    assert [job["sample_id"] for job in jobs] == ["alpha", "beta", "gamma", "delta", "beta", "delta", "beta", "delta", "beta"]
    assert {job["suite"] for job in jobs} == {"preflight8", "perf80"}
    assert {job["repetition"] for job in jobs if job["phase"] == "measured"} == {1, 2, 3}


@pytest.mark.parametrize("change", ["draft", "no-freeze", "full", "no-preflight"])
def test_pilot_requires_existing_frozen_lite_authorization(tmp_path, change):
    authored = declaration()
    if change == "draft":
        authored["state"] = "draft"
    elif change == "no-freeze":
        authored.pop("freeze_record")
    elif change == "full":
        authored["kind"] = "full"
    else:
        authored["preflight_confirmed"] = False
    with pytest.raises(ValueError):
        optimization.optimization_jobs(authored, tmp_path, "pilot8")


def test_undeclared_suite_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="only"):
        optimization.optimization_jobs(declaration(), tmp_path, "quality800")


def test_controls_change_only_native_glm_rotary_and_share_observation():
    source = configuration()
    before = copy.deepcopy(source)
    configs = optimization.optimization_configs(source)
    assert source == before
    assert list(configs) == ["baseline", "native"]
    baseline, native = configs["baseline"], configs["native"]
    assert baseline["glm_request_observation"] is True
    assert native["glm_request_observation"] is True
    assert native["inference_services"][0].pop("rotary_embedding") == "native"
    assert native == baseline
    assert baseline["graphs"]["mode"] == "FULL_DECODE_ONLY"
    assert baseline["glm_decoding_declared"]["repetition_penalty"] == 1.1
    assert baseline["pipeline"] == "P05"


@pytest.mark.parametrize("arm", ["baseline", "native"])
def test_single_arm_uses_its_own_identity(arm):
    assert list(optimization.optimization_configs(configuration(), arm)) == [arm]


@pytest.mark.parametrize("change", ["pipeline", "other-service", "already-native", "unsupported-custom"])
def test_controls_reject_non_p05_or_confounded_source_config(change):
    config = configuration()
    if change == "pipeline":
        config["pipeline"] = "P01"
    elif change == "other-service":
        config["inference_services"].append({"role": "other"})
    elif change == "already-native":
        config["inference_services"][0]["rotary_embedding"] = "native"
    else:
        config["inference_services"][0]["rotary_embedding"] = "custom"
    with pytest.raises(ValueError):
        optimization.optimization_configs(config)


@pytest.fixture
def mocked_run(tmp_path, monkeypatch):
    dataset = tmp_path / "invented-data"
    dataset.mkdir()
    write_json(dataset / "manifest.json", declaration())
    lock = tmp_path / "invented-config.json"
    write_json(lock, {"pipelines": {"P05": configuration()}})
    output = tmp_path / "new-experiment"
    args = optimization.parser().parse_args([
        "--dataset", str(dataset), "--config", str(lock), "--output", str(output),
        "--maintenance-window",
    ])
    calls: list = []

    monkeypatch.setattr(optimization.cli, "code_identity", lambda: {"software_id": "invented-software"})

    def snapshot(destination, identity):
        calls.append(("snapshot", destination))
        write_json(destination / "software.json", identity)
        (destination / "controller.py").write_text("# invented software snapshot\n")

    monkeypatch.setattr(optimization.cli, "snapshot_software", snapshot)

    @contextmanager
    def window(path):
        calls.append(("window-enter", path))
        write_json(path, {"phase": "maintenance", "research_owners": {}})
        try:
            yield {"research_owners": {}}
        finally:
            calls.append(("window-restored", path))
            write_json(path, {"phase": "restored", "research_owners": {}, "recovery_checks": {"invented-service": True}})

    @asynccontextmanager
    async def service(config, *, artifacts_dir):
        selected = config["inference_services"][0].get("rotary_embedding", "baseline")
        calls.append(("service-enter", selected))
        try:
            yield {**config, "endpoints": {"glm": "http://invented-endpoint"}}
        finally:
            calls.append(("service-cleaned", selected))
            write_json(artifacts_dir / "inference-ownership.json", {"phase": "stopped", "cleanup_confirmed": True})

    async def execute(jobs, config, *, output_dir, inputs_dir):
        calls.append(("execute", config, inputs_dir))
        assert config["endpoints"]["glm"] == "http://invented-endpoint"
        rows = [{"sample_id": job["sample_id"], "status": "completed", "pages": [],
                 "timing": {"processing_seconds": 1.25, "pipeline_initialization_seconds": 3.0}}
                for job in jobs]
        write_json(output_dir / "batch-observations.json", rows)
        return rows

    monkeypatch.setattr(optimization.maintenance, "gpu1_window", window)
    monkeypatch.setattr(optimization.maintenance, "inference_services", service)
    monkeypatch.setattr(optimization.executors, "execute_batch", execute)
    return args, calls


def test_two_arms_share_one_owned_window_and_save_score_compatible_runs(mocked_run):
    args, calls = mocked_run
    assert asyncio.run(optimization.run_experiment(args)) == 0
    experiment = read_json(args.output / "experiment.json")
    assert experiment["state"] == "completed"
    assert experiment["maintenance_phase"] == "restored"
    assert len([row for row in calls if row[0] == "window-enter"]) == 1
    stages = [row[0] for row in calls if row[0] != "snapshot"]
    assert stages == ["window-enter", "service-enter", "execute", "service-cleaned",
                      "service-enter", "execute", "service-cleaned", "window-restored"]
    assert len([row for row in calls if row[0] == "snapshot"]) == 3
    for arm in optimization.ARM_NAMES:
        root = args.output / arm
        run = read_json(root / "run.json")
        assert run["formal"] is False and run["development_experiment"] is True
        assert run["experiment_arm"] == arm and run["configurations"][0]["pipeline"] == "P05"
        assert run["reference_freeze"] == {"author": "invented-author"}
        assert len(run["cases"]) == 12
        assert len([case for case in run["cases"] if case["phase"] == "measured"]) == 9
        assert {case["suite"] for case in run["cases"]} == {"preflight8", "pilot8"}
        assert (root / run["software_snapshot"] / "controller.py").is_file()
        assert read_json(root / "maintenance.json")["phase"] == "restored"
        assert run["cleanup_evidence"]["inference_cleanup_confirmed"] is True
        observation = read_json(root / run["cases"][3]["observation"])
        assert observation["timing"]["processing_seconds"] == 1.25
        assert observation["run_id"] == run["run_id"]


def test_plan_only_never_writes_or_enters_services(mocked_run, capsys):
    args, calls = mocked_run
    args.plan_only = True
    args.maintenance_window = False
    assert asyncio.run(optimization.run_experiment(args)) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["scope"] == "development_experiment_not_formal_lite"
    assert len(record["jobs"]) == 12 and record["arms"] == ["baseline", "native"]
    assert not args.output.exists()
    assert calls == []


def test_execution_requires_explicit_window_before_writing(mocked_run):
    args, calls = mocked_run
    args.maintenance_window = False
    with pytest.raises(ValueError, match="maintenance-window"):
        asyncio.run(optimization.run_experiment(args))
    assert not args.output.exists() and calls == []


def test_existing_output_is_never_reused_or_overwritten(mocked_run):
    args, calls = mocked_run
    args.output.mkdir()
    marker = args.output / "run.json"
    marker.write_text("invented older run\n")
    with pytest.raises(FileExistsError):
        asyncio.run(optimization.run_experiment(args))
    assert marker.read_text() == "invented older run\n" and calls == []


def test_outputs_cannot_write_into_dataset_package(mocked_run):
    args, calls = mocked_run
    args.output = args.dataset / "new-run"
    with pytest.raises(ValueError, match="read-only dataset"):
        asyncio.run(optimization.run_experiment(args))
    assert not args.output.exists() and calls == []


def test_execution_failure_preserves_partial_records_and_not_started_arm(mocked_run, monkeypatch):
    args, calls = mocked_run

    async def failing(jobs, config, *, output_dir, inputs_dir):
        write_json(output_dir / "batch-observations.json", [
            {"sample_id": jobs[0]["sample_id"], "status": "completed", "pages": [],
             "timing": {"processing_seconds": 9.0}},
        ])
        raise PreparationError("invented SDK failure after first saved observation")

    monkeypatch.setattr(optimization.executors, "execute_batch", failing)
    with pytest.raises(PreparationError, match="invented SDK"):
        asyncio.run(optimization.run_experiment(args))
    experiment = read_json(args.output / "experiment.json")
    assert experiment["state"] == "failed" and experiment["maintenance_phase"] == "restored"
    baseline = read_json(args.output / "baseline/run.json")
    assert baseline["state"] == "failed" and len(baseline["cases"]) == 12
    first = read_json(args.output / "baseline" / baseline["cases"][0]["observation"])
    assert first["timing"]["processing_seconds"] == 9.0
    assert read_json(args.output / "baseline" / baseline["cases"][1]["observation"])["status"] == "not_started"
    native = read_json(args.output / "native/run.json")
    assert native["state"] == "not_started" and len(native["cases"]) == 12
    assert native["cleanup_evidence"]["inference_cleanup_confirmed"] is None
    assert len([row for row in calls if row[0] == "service-enter"]) == 1


def test_unknown_execution_is_not_retried_and_next_arm_stays_unstarted(mocked_run, monkeypatch):
    args, calls = mocked_run

    async def unknown(jobs, config, *, output_dir, inputs_dir):
        calls.append(("unknown-execute", config))
        return [{"sample_id": job["sample_id"], "status": "execution_unknown" if index == 0 else "not_processed_due_to_unresolved_execution",
                 "pages": [], "timing": {"processing_seconds": None}}
                for index, job in enumerate(jobs)]

    monkeypatch.setattr(optimization.executors, "execute_batch", unknown)
    assert asyncio.run(optimization.run_experiment(args)) == 2
    experiment = read_json(args.output / "experiment.json")
    assert experiment["state"] == "stopped_after_owned_execution_interruption"
    assert experiment["arms"]["native"]["state"] == "not_started"
    assert len([row for row in calls if row[0] == "unknown-execute"]) == 1
    assert experiment["maintenance_phase"] == "restored"


def test_cancellation_drains_owned_context_before_restoration(mocked_run, monkeypatch):
    args, calls = mocked_run

    async def cancelled(jobs, config, *, output_dir, inputs_dir):
        calls.append(("cancelled-execute",))
        raise asyncio.CancelledError

    monkeypatch.setattr(optimization.executors, "execute_batch", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(optimization.run_experiment(args))
    stages = [row[0] for row in calls if row[0] != "snapshot"]
    assert stages == ["window-enter", "service-enter", "cancelled-execute", "service-cleaned", "window-restored"]
    assert read_json(args.output / "experiment.json")["state"] == "cancelled"
    assert read_json(args.output / "baseline/run.json")["state"] == "cancelled"


def test_restoration_failure_remains_failed_in_ledger(mocked_run, monkeypatch):
    args, _calls = mocked_run

    @contextmanager
    def broken_restoration(path):
        try:
            yield {}
        finally:
            write_json(path, {"phase": "restoration_failed", "restoration_errors": ["invented"]})
            raise RuntimeError("invented restoration failure")

    monkeypatch.setattr(optimization.maintenance, "gpu1_window", broken_restoration)
    with pytest.raises(RuntimeError, match="restoration failure"):
        asyncio.run(optimization.run_experiment(args))
    experiment = read_json(args.output / "experiment.json")
    assert experiment["state"] == "failed" and experiment["maintenance_phase"] == "restoration_failed"
    assert read_json(args.output / "native/run.json")["cleanup_evidence"]["maintenance_phase"] == "restoration_failed"
