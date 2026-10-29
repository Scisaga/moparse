"""Run explicit P05 development controls on existing declared Lite subsets.

This entry point never scores, reviews or changes reference material. Each arm
keeps the P05 parser identity and owns a fresh run directory. GPU execution is
only entered with the explicit maintenance-window switch; importing this module
or requesting a plan does not change services.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import traceback
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import cli, executors, maintenance
from .packaging import inside, read_json, write_json
from .runtime import PreparationError, validate_execution_config

ARM_NAMES = ("baseline", "native")


def _now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def optimization_jobs(
    manifest: dict[str, Any], dataset: Path, suite: str,
) -> list[dict[str, Any]]:
    """Consume an existing named selection without inspecting its PDF bytes."""
    if suite not in {"pilot8", "perf80"}:
        raise ValueError("P05 optimization supports only pilot8 or perf80")
    if manifest.get("state") != "frozen" or not manifest.get("freeze_record"):
        raise ValueError("P05 optimization needs the existing frozen declaration")
    if suite == "perf80":
        return cli.execution_plan(manifest, dataset, "perf80")
    declared = cli.execution_plan(manifest, dataset, "preflight8")
    jobs = []
    for phase, repetition in (("warmup", 1), ("measured", 1),
                              ("measured", 2), ("measured", 3)):
        label = "preflight8" if phase == "warmup" else "pilot8"
        for original in declared:
            job = copy.deepcopy(original)
            job.update(suite=label, phase=phase, repetition=repetition,
                       warmup=phase == "warmup",
                       output_dir=f"{phase}-{label}-r{repetition}/{original['sample_id']}")
            jobs.append(job)
    if not jobs:
        raise ValueError("the authored preflight selection is empty")
    return jobs


def optimization_configs(
    baseline: Mapping[str, Any], arm: str = "both",
) -> dict[str, dict[str, Any]]:
    """Change only native rotary selection between the observed controls."""
    if arm not in {*ARM_NAMES, "both"}:
        raise ValueError("arm must be baseline, native or both")
    if baseline.get("pipeline") != "P05":
        raise ValueError("the optimization entry point is restricted to P05")
    services = baseline.get("inference_services", [])
    glm = [item for item in services if item.get("role") == "glm"]
    if len(services) != 1 or len(glm) != 1 or glm[0].get("family") != "glm":
        raise ValueError("P05 needs its single declared GLM inference service")
    if glm[0].get("rotary_embedding") is not None:
        raise ValueError("the baseline lock already changes the rotary implementation")
    selected = ARM_NAMES if arm == "both" else (arm,)
    configs = {}
    for name in selected:
        config = copy.deepcopy(dict(baseline))
        config["glm_request_observation"] = True
        if name == "native":
            config["inference_services"][0]["rotary_embedding"] = "native"
        validate_execution_config(config)
        configs[name] = config
    return configs


def _error(error: BaseException, stage: str) -> dict[str, Any]:
    return {"type": type(error).__name__, "message": str(error), "stage": stage,
            "retry": False, "traceback": "".join(traceback.format_exception(error))}


def _case_metadata(job: Mapping[str, Any]) -> dict[str, Any]:
    return {key: job[key] for key in (
        "sample_id", "suite", "phase", "repetition", "input_page_count",
    )}


def _retain_observations(
    root: Path, session: dict[str, Any], jobs: list[dict[str, Any]],
    observations: list[dict[str, Any]], *, missing_reason: str,
) -> None:
    """Save known worker output and explicitly account for unstarted jobs."""
    if len(observations) > len(jobs):
        raise PreparationError("worker returned more observations than scheduled jobs")
    session["cases"] = []
    for index, job in enumerate(jobs):
        if index < len(observations):
            observation = copy.deepcopy(observations[index])
            if observation.get("sample_id", job["sample_id"]) != job["sample_id"]:
                raise PreparationError("worker observation does not identify its scheduled sample")
        else:
            observation = {
                "status": "not_started", "pages": [], "relations": [], "assets": [],
                "timing": {"processing_seconds": None},
                "errors": [{"category": "engineering_execution_not_started",
                            "reason": missing_reason, "retry": False}],
            }
        observation.update(_case_metadata(job), pipeline="P05",
                           dataset=session["dataset_name"], run_id=session["run_id"])
        destination = inside(root / "artifacts/P05", job["output_dir"]) / "observation.json"
        write_json(destination, observation)
        session["cases"].append({
            "pipeline": "P05", **_case_metadata(job),
            "observation": str(destination.relative_to(root)),
        })
    write_json(root / "run.json", session)


def _saved_observations(root: Path) -> list[dict[str, Any]]:
    path = root / "artifacts/P05/batch-observations.json"
    if not path.is_file():
        return []
    rows = read_json(path)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise PreparationError("saved worker observations are not an observation list")
    return rows


async def _execute_arm(
    root: Path, session: dict[str, Any], config: dict[str, Any],
    jobs: list[dict[str, Any]], dataset: Path,
) -> bool:
    """Return whether owned unknown/cancelled execution stopped this arm."""
    destination = root / "artifacts/P05"
    session.update(state="running", started_at=_now())
    write_json(root / "run.json", session)
    observations: list[dict[str, Any]] = []
    try:
        print(f"P05 {session['experiment_arm']}: starting {session['suite']}", flush=True)
        async with maintenance.inference_services(
            config, artifacts_dir=destination / "inference",
        ) as live_config:
            execution_jobs: list[Mapping[str, Any]] = list(jobs)
            observations = await executors.execute_batch(
                execution_jobs, live_config, output_dir=destination, inputs_dir=dataset / "inputs",
            )
        _retain_observations(root, session, jobs, observations,
                             missing_reason="worker_ended_before_scheduled_job")
        if len(observations) != len(jobs):
            raise PreparationError("worker ended with unstarted scheduled jobs")
        interrupted = any(row.get("status") in {"execution_unknown", "cancelled"}
                          for row in observations)
        session["state"] = ("stopped_after_owned_execution_interruption" if interrupted else
                            "completed" if all(row.get("status") == "completed" for row in observations)
                            else "completed_with_candidate_failures")
        print(f"P05 {session['experiment_arm']}: {session['state']}; inference cleanup finished", flush=True)
        return interrupted
    except BaseException as error:
        session["state"] = "cancelled" if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)) else "failed"
        session["errors"].append(_error(error, "arm_execution_or_cleanup"))
        try:
            _retain_observations(root, session, jobs, observations or _saved_observations(root),
                                 missing_reason="arm_failed_or_cancelled_before_scheduled_job")
        except Exception as retention_error:
            session["errors"].append(_error(retention_error, "retaining_existing_observations"))
        raise
    finally:
        session["finished_at"] = _now()
        write_json(root / "run.json", session)


async def run_experiment(args: argparse.Namespace) -> int:
    """Own one maintenance window and sequential independent P05 controls."""
    dataset, output = args.dataset.resolve(), args.output.resolve()
    if output.is_relative_to(dataset):
        raise ValueError("experiment output must be outside the read-only dataset package")
    # Reading the authored manifest declares a schedule; no source/reference
    # contents, hashes, mappings or corpus acceptance rules are evaluated here.
    manifest = read_json(dataset / "manifest.json")
    jobs = optimization_jobs(manifest, dataset, args.suite)
    base_config = cli.execution_configs(args.config, ["P05"])[0]
    configs = optimization_configs(base_config, args.arm)
    if args.plan_only:
        import json
        print(json.dumps({"scope": "development_experiment_not_formal_lite",
                          "suite": args.suite, "arms": list(configs),
                          "jobs": jobs, "configurations": configs}, ensure_ascii=False, indent=2))
        return 0
    if not args.maintenance_window:
        raise ValueError("GPU execution requires the explicit --maintenance-window switch")
    output.mkdir(parents=True, exist_ok=False)
    identity = cli.code_identity()
    experiment: dict[str, Any] = {
        "experiment_id": output.name, "created_at": _now(), "state": "prepared",
        "suite": args.suite, "formal": False, "development_experiment": True,
        "dataset": str(dataset), "dataset_name": manifest["name"],
        "reference_freeze": manifest["freeze_record"],
        "software": identity, "software_snapshot": "artifacts/software",
        "arms": {name: {"run": f"{name}/run.json", "state": "prepared"} for name in configs},
        "maintenance": "maintenance.json", "errors": [],
        "analysis_policy": {
            "quality_repetition": 1, "performance_repetitions": [1, 2, 3],
            "pool_repeated_samples_for_quality": False,
            "scope": "existing_declared_development_subset_not_800_page_replacement",
        },
    }
    cli.snapshot_software(output / "artifacts/software", identity)
    write_json(output / "artifacts/source-execution-config.json", base_config)
    write_json(output / "execution-plan.json", jobs)
    sessions = {}
    for name, config in configs.items():
        root = output / name
        root.mkdir(exist_ok=False)
        session: dict[str, Any] = {
            "run_id": f"{output.name}-{name}", "created_at": _now(),
            "dataset": str(dataset), "dataset_name": manifest["name"],
            "reference_freeze": manifest["freeze_record"], "suite": args.suite,
            "formal": False, "development_experiment": True, "experiment_arm": name,
            "experiment_id": output.name, "state": "prepared", "software": identity,
            "software_snapshot": "artifacts/software", "configurations": [config],
            "cases": [], "errors": [],
            "analysis_policy": experiment["analysis_policy"],
            "declared_factor": {"name": "rotary_embedding", "value": name,
                                "other_decoder_parameters": "unchanged_from_source_config"},
            "maintenance_scope": "one_shared_experiment_window; copied final evidence in maintenance.json",
        }
        cli.snapshot_software(root / "artifacts/software", identity)
        write_json(root / "artifacts/P05/execution-config.json", config)
        write_json(root / "run.json", session)
        sessions[name] = session
    write_json(output / "experiment.json", experiment)
    try:
        # The shared window's finally restores production only after each
        # owned worker/inference context has drained and confirmed exit.
        with maintenance.gpu1_window(output / "maintenance.json"):
            experiment.update(state="running", started_at=_now())
            write_json(output / "experiment.json", experiment)
            for name, config in configs.items():
                experiment["arms"][name]["state"] = "running"
                write_json(output / "experiment.json", experiment)
                interrupted = await _execute_arm(output / name, sessions[name], config, jobs, dataset)
                experiment["arms"][name]["state"] = sessions[name]["state"]
                write_json(output / "experiment.json", experiment)
                if interrupted:
                    experiment["state"] = "stopped_after_owned_execution_interruption"
                    break
            else:
                experiment["state"] = (
                    "completed" if all(session["state"] == "completed" for session in sessions.values())
                    else "completed_with_candidate_failures")
    except BaseException as error:
        experiment["state"] = "cancelled" if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)) else "failed"
        experiment["errors"].append(_error(error, "execution_or_service_restoration"))
        raise
    finally:
        restoration_path = output / "maintenance.json"
        restoration = read_json(restoration_path) if restoration_path.is_file() else None
        experiment["maintenance_phase"] = restoration.get("phase") if restoration else "not_entered"
        for name, session in sessions.items():
            root = output / name
            if session["state"] == "prepared":
                session.update(state="not_started", finished_at=_now())
                _retain_observations(root, session, jobs, [],
                                     missing_reason="experiment_stopped_before_this_arm")
            if restoration is not None:
                write_json(root / "maintenance.json", restoration)
            lifecycle_path = root / "artifacts/P05/inference/inference-ownership.json"
            lifecycle = read_json(lifecycle_path) if lifecycle_path.is_file() else None
            session["cleanup_evidence"] = {
                "inference_ownership": str(lifecycle_path.relative_to(root)) if lifecycle else None,
                "inference_cleanup_confirmed": lifecycle.get("cleanup_confirmed") if lifecycle else None,
                "maintenance_record": "maintenance.json" if restoration else None,
                "maintenance_phase": experiment["maintenance_phase"],
                "scope": "shared_window_restoration_does_not_imply_candidate_success",
            }
            write_json(root / "run.json", session)
            experiment["arms"][name].update(state=session["state"], cleanup_evidence=session["cleanup_evidence"])
        experiment["finished_at"] = _now()
        write_json(output / "experiment.json", experiment)
    return 0 if experiment["state"] == "completed" else 2


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--dataset", type=Path, required=True,
                         help="existing frozen Lite package; references remain read-only")
    command.add_argument("--config", type=Path, default=cli.ROOT / "benchmark/execution-lock.json")
    command.add_argument("--output", type=Path, required=True,
                         help="fresh experiment directory; existing directories are never reused")
    command.add_argument("--suite", choices=("pilot8", "perf80"), default="pilot8",
                         help="declared preflight8 or perf80: warmup8 then three measured repetitions")
    command.add_argument("--arm", choices=(*ARM_NAMES, "both"), default="both",
                         help="baseline custom rotary, native rotary control, or both sequentially")
    command.add_argument("--maintenance-window", action="store_true",
                         help="explicitly enter authorized GPU 1 window and restore original services")
    command.add_argument("--plan-only", action="store_true",
                         help="print declaration-based schedule/configs; do not write or start workloads")
    return command


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run_experiment(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
