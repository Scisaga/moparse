from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, contextmanager

import pytest

from moparse_eval.cli import execution_plan, parser, report_run, run_dataset, score_run


def manifest() -> dict:
    return {
        "name": "synthetic-lite",
        "kind": "lite",
        "state": "frozen",
        "freeze_record": {"reviewer": "synthetic-author"},
        "preflight_confirmed": True,
        "samples": [
            {"id": "one", "input": "inputs/one.pdf", "source_pages": [7]},
            {"id": "two", "input": "inputs/two.pdf", "source_pages": [9, 10]},
        ],
        "suites": {"lite": ["one", "two"], "perf80": ["two"], "preflight8": ["one"]},
    }


def stable_maintenance() -> dict:
    return {"phase": "restored", "tts_policy": "keep_running",
            "tts_identity_condition": {"status": "unchanged"},
            "tts_no_calls_condition": {"status": "no_observed_activity"}}


def test_formal_execution_needs_authored_freeze_not_file_count(tmp_path):
    declaration = manifest()
    declaration["state"] = "draft"
    with pytest.raises(ValueError, match="freeze"):
        execution_plan(declaration, tmp_path, "lite")
    assert execution_plan(declaration, tmp_path, "preflight8")[0]["phase"] == "preflight"
    declaration["kind"] = "full"
    with pytest.raises(ValueError, match="outside"):
        execution_plan(declaration, tmp_path, "preflight8")


def test_one_persistent_schedule_separates_warmup_quality_and_repetitions(tmp_path):
    jobs = execution_plan(manifest(), tmp_path, "lite")
    assert [(job["suite"], job["phase"], job["repetition"]) for job in jobs] == [
        ("preflight8", "warmup", 1),
        ("quality800", "measured", 1),
        ("quality800", "measured", 1),
        ("perf80", "measured", 1),
        ("perf80", "measured", 2),
        ("perf80", "measured", 3),
    ]
    assert jobs[2]["input_page_count"] == 2
    assert len({job["output_dir"] for job in jobs}) == len(jobs)
    assert all("reference" not in job and "expected" not in job for job in jobs)


def test_cli_exposes_operations_without_corpus_validation_or_repair():
    args = parser().parse_args(["report", "--run", "/tmp/synthetic-run"])
    assert args.command == "report"
    with pytest.raises(SystemExit):
        parser().parse_args(["check-corpus"])


def test_software_identity_and_snapshot_exclude_synthetic_corpus(tmp_path, monkeypatch):
    from moparse_eval import cli

    root = tmp_path / "checkout"
    for relative in ("app/service.py", "native_worker/worker.py", "moparse_eval/cli.py",
                     "datasets/example/answer.py", "pdf_sample/parsing/expected/answer.py",
                     "benchmark/reports/example/answer.py"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic software or excluded material\n")
    monkeypatch.setattr(cli, "ROOT", root)
    identity = cli.code_identity()
    assert set(identity["support_module_sha256"]) == {"app/service.py", "native_worker/worker.py"}
    # The real module directory is independent of ROOT; use the deliberately
    # small synthetic module set when exercising the snapshot writer.
    identity["module_sha256"] = {"cli.py": "synthetic-software-identity"}
    destination = tmp_path / "snapshot"
    cli.snapshot_software(destination, identity)
    assert (destination / "app/service.py").is_file()
    assert (destination / "moparse_eval/cli.py").is_file()
    assert not (destination / "datasets").exists()
    assert not (destination / "pdf_sample").exists()
    assert not (destination / "benchmark").exists()


def test_current_scoring_requires_a_freeze_without_reading_references(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"state": "completed", "dataset": "/must-not-read", "cases": []}))
    with pytest.raises(ValueError, match="requires a validated software freeze"):
        score_run(run)
    assert not (run / "artifacts").exists()


def test_preflight_passes_live_endpoint_and_continues_only_after_owned_cleanup(tmp_path, monkeypatch):
    from moparse_eval import executors, maintenance, runtime
    dataset = tmp_path / "synthetic-dataset"
    dataset.mkdir()
    (dataset / "manifest.json").write_text(json.dumps(manifest()))
    lock = tmp_path / "software.json"
    lock.write_text(json.dumps({"pipelines": {name: {"pipeline": name} for name in ("P01", "P02")}}))
    calls = []

    @contextmanager
    def window(path):
        yield {"research_owners": {"synthetic-worker": "stopped"}}
        path.write_text(json.dumps(stable_maintenance()))

    @asynccontextmanager
    async def service(config, **_kwargs):
        yield {**config, "endpoints": {"synthetic": "http://bounded-local-service"}}

    async def execute(jobs, config, **_kwargs):
        calls.append(config)
        if config["pipeline"] == "P01":
            raise runtime.PreparationError("synthetic SDK preparation failure")
        return [{"sample_id": job["sample_id"], "status": "completed", "pages": [], "timing": {}} for job in jobs]

    monkeypatch.setattr(maintenance, "gpu1_window", window)
    monkeypatch.setattr(maintenance, "inference_services", service)
    monkeypatch.setattr(runtime, "validate_execution_config", lambda _config: None)
    monkeypatch.setattr(executors, "execute_batch", execute)
    args = parser().parse_args([
        "run", "--dataset", str(dataset), "--config", str(lock), "--pipeline", "P01", "P02",
        "--suite", "preflight8", "--output", str(tmp_path / "run"), "--maintenance-window",
    ])
    assert asyncio.run(run_dataset(args)) == 2
    assert [config["pipeline"] for config in calls] == ["P01", "P02"]
    assert all(config["endpoints"]["synthetic"] for config in calls)
    retained = json.loads((tmp_path / "run/run.json").read_text())
    assert retained["state"] == "completed_with_preflight_failures"
    assert retained["errors"][0]["category"] == "engineering_preflight_failure"
    assert retained["cases"][0]["pipeline"] == "P02"


def test_report_rejects_the_deleted_score_format(tmp_path):
    run = tmp_path / "synthetic-report"
    (run / "scores").mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({
        "run_id": "synthetic", "formal": True, "state": "completed",
        "cases": [], "latest_scores": "scores/index.json",
    }))
    (run / "maintenance.json").write_text(json.dumps(stable_maintenance()))
    (run / "scores/index.json").write_text(json.dumps({
        "results": [], "unscored": [], "score_id": "synthetic-score",
    }))
    with pytest.raises(ValueError, match="canonical expected scores"):
        report_run(run)
    assert not (run / "report.md").exists()


@pytest.mark.parametrize("suite", ["preflight8", "lite"])
@pytest.mark.parametrize("observe_only", [False, True])
@pytest.mark.parametrize("invalid", ["identity_changed", "calls", "unknown", "missing_identity", "restoration_failed", None])
def test_execution_conditions_are_recorded_separately_from_preparation_errors(
    tmp_path, monkeypatch, suite, invalid, observe_only,
):
    from moparse_eval import cli, executors, maintenance

    dataset = tmp_path / "synthetic-dataset"
    dataset.mkdir()
    (dataset / "manifest.json").write_text(json.dumps(manifest()))
    lock = tmp_path / "software.json"
    lock.write_text(json.dumps({"pipelines": {"P01": {"pipeline": "P01"}}}))
    evidence = stable_maintenance()
    if observe_only:
        evidence.update(tts_observation_policy="observe_only", user_instruction_date="2026-10-26")
    if invalid == "identity_changed":
        evidence["tts_identity_condition"] = {"status": "changed"}
    elif invalid == "calls":
        evidence["tts_no_calls_condition"] = {"status": "observed_activity", "new_jobs": 2}
    elif invalid == "unknown":
        evidence["tts_no_calls_condition"] = {"status": "unknown"}
    elif invalid == "missing_identity":
        del evidence["tts_identity_condition"]
    elif invalid == "restoration_failed":
        evidence["phase"] = "restoration_failed"
    evidence["recovery_checks"] = {"moparse": True, "tts_ready": True}
    original = json.dumps(evidence)

    @contextmanager
    def window(path):
        yield {"research_owners": {"synthetic-worker": "stopped"}}
        path.write_text(original)

    @asynccontextmanager
    async def service(config, **_kwargs):
        yield config

    async def execute(jobs, _config, **_kwargs):
        return [{"status": "completed", "pages": [], "timing": {"processing_seconds": 1}}
                for _job in jobs]

    monkeypatch.setattr(maintenance, "gpu1_window", window)
    monkeypatch.setattr(maintenance, "inference_services", service)
    monkeypatch.setattr(executors, "execute_batch", execute)
    monkeypatch.setattr(cli, "snapshot_software", lambda *_args: None)
    monkeypatch.setattr(cli, "code_identity", lambda: {"software_id": "synthetic"})
    monkeypatch.setattr(cli, "require_frozen_execution", lambda *_args: None)
    output = tmp_path / "run"
    args = parser().parse_args(["run", "--dataset", str(dataset), "--config", str(lock),
        "--pipeline", "P01", "--suite", suite, "--output", str(output), "--maintenance-window"])
    rejected = invalid is not None and (not observe_only or invalid == "restoration_failed")
    assert asyncio.run(run_dataset(args)) == (3 if rejected else 0)
    session = json.loads((output / "run.json").read_text())
    assessment = json.loads((output / "measurement-conditions.json").read_text())
    assert session["state"] == ("invalidated" if rejected else "completed")
    assert session["execution_outcome"] == "completed"
    assert assessment == session["measurement_conditions"]
    assert assessment["valid"] is (not rejected)
    if observe_only:
        assert assessment["qualifications"]
    assert session["errors"] == []
    assert session["cases"]
    assert (output / "maintenance.json").read_text() == original
