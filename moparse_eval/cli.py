"""Local dataset materialization, isolated execution and read-only evaluation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import traceback
from collections.abc import Mapping
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .expected_scoring import PROTOCOL as EXPECTED_PROTOCOL
from .packaging import inside, package_dataset, read_json, write_json

ROOT = Path(__file__).resolve().parent.parent
PIPELINES = tuple(f"P{number:02}" for number in range(1, 9))
SCORING_PROTOCOL = EXPECTED_PROTOCOL


def read_scoring_freeze(path: Path, identity: Mapping[str, Any]) -> dict[str, Any]:
    """Read a software-validation record, never inspect corpus materials."""
    record = read_json(path)
    if not isinstance(record, dict):
        raise ValueError("scoring freeze must be an engineering validation record")
    if record.get("software_id") != identity.get("software_id"):
        raise ValueError("scoring software differs from the frozen, validated version")
    if record.get("protocol_id") != SCORING_PROTOCOL["id"]:
        raise ValueError("scoring protocol differs from the frozen version")
    validation = record.get("validation")
    if not isinstance(validation, Mapping) or validation.get("status") != "passed":
        raise ValueError("scoring freeze must record passed engineering validation")
    return record


def code_identity() -> dict[str, Any]:
    """Fingerprint evaluation software only; never read corpus bytes here."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    modules = {}
    for path in sorted(Path(__file__).parent.glob("*.py")):
        modules[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    support_modules = {}
    # These code-only roots are mounted by research workers. A dirty checkout's
    # Git HEAD alone cannot identify the implementation actually used.
    for directory in ("app", "native_worker"):
        for path in sorted((ROOT / directory).rglob("*.py")):
            support_modules[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    dependencies: dict[str, str | None] = {}
    for distribution in ("rapidfuzz", "edlib", "numpy", "markdown-it-py", "PyMuPDF", "psutil"):
        try:
            dependencies[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            dependencies[distribution] = None
    source_identity = {"evaluation": modules, "support": support_modules,
                       "python": sys.version, "dependencies": dependencies}
    digest = hashlib.sha256(json.dumps(source_identity, sort_keys=True).encode()).hexdigest()
    return {"git_head": result.stdout.strip(), "module_sha256": modules,
            "support_module_sha256": support_modules, "software_id": digest,
            "python": sys.version, "dependencies": dependencies}


def _now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def snapshot_software(destination: Path, identity: dict[str, Any]) -> None:
    """Preserve the identified code, independently of corpus and run inputs."""
    relative_paths = [
        *(f"moparse_eval/{name}" for name in identity["module_sha256"]),
        *identity["support_module_sha256"],
    ]
    for relative in relative_paths:
        target = inside(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(inside(ROOT, relative), target)
    # Build inputs are software artifacts too, never dataset/reference bytes.
    for relative in ("pyproject.toml", "uv.lock", "native_worker/requirements.txt",
                     "native_worker/requirements.lock.txt", "native_worker/models.lock.json"):
        source = inside(ROOT, relative)
        if source.is_file():
            target = inside(destination, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    patches = ROOT / "native_worker/patches"
    if patches.is_dir():
        shutil.copytree(patches, destination / "native_worker/patches")
    write_json(destination / "software.json", identity)


def execution_configs(path: Path, selected: list[str]) -> list[dict[str, Any]]:
    lock = read_json(path)
    configurations = lock.get("pipelines", {})
    if isinstance(configurations, list):
        configurations = {item["pipeline"]: item for item in configurations}
    if "pipeline" in lock:
        configurations = {lock["pipeline"]: lock}
    wanted = list(PIPELINES) if "all" in selected else selected
    return [{**configurations[name], "pipeline": name} for name in wanted]


def require_frozen_execution(lock: Mapping[str, Any], software: Mapping[str, Any]) -> None:
    """Admit measured work only with the software identity frozen after preflight."""
    if lock.get("frozen") is not True or not lock.get("freeze_record"):
        raise ValueError("formal execution requires a newly frozen post-preflight execution lock")
    frozen_software = lock.get("software_identity", {})
    if not frozen_software.get("software_id") or frozen_software.get("software_id") != software.get("software_id"):
        raise ValueError("evaluation software changed after the execution freeze; repeat preparation and freeze")


def execution_plan(
    manifest: dict[str, Any], dataset: Path, suite: str
) -> list[dict[str, Any]]:
    """Consume declarations, not infer whether a corpus has passed review."""
    if manifest.get("kind") != "lite":
        raise ValueError("Full inference is outside this authorized run")
    if suite == "preflight8":
        if not manifest.get("preflight_confirmed"):
            raise ValueError("the authored preflight confirmation is absent")
    elif manifest.get("state") != "frozen" or not manifest.get("freeze_record"):
        raise ValueError("formal execution needs an explicitly authored reference freeze record")
    by_id = {sample["id"]: sample for sample in manifest["samples"]}
    declarations = manifest["suites"]
    schedule: list[tuple[str, str, int, list[str]]] = []
    if suite == "preflight8":
        schedule.append(("preflight8", "preflight", 1, declarations["preflight8"]))
    else:
        schedule.append(("preflight8", "warmup", 1, declarations["preflight8"]))
        if suite in {"lite", "quality800"}:
            schedule.append(("quality800", "measured", 1, declarations["lite"]))
        if suite in {"lite", "perf80"}:
            for repetition in range(1, 4):
                schedule.append(("perf80", "measured", repetition, declarations["perf80"]))
    jobs = []
    for label, phase, repetition, sample_ids in schedule:
        for sample_id in sample_ids:
            sample = by_id[sample_id]
            jobs.append(
                {
                    "sample_id": sample_id,
                    "pdf_path": str(inside(dataset, sample["input"])),
                    "suite": label,
                    "phase": phase,
                    "warmup": phase == "warmup",
                    "repetition": repetition,
                    "input_page_count": len(sample["source_pages"]),
                    "output_dir": f"{phase}-{label}-r{repetition}/{sample_id}",
                }
            )
    return jobs


def _sample_metadata(
    sample: dict[str, Any], documents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Carry authored declarations into scoring, including unscored cases.

    This only reports the frozen manifest's declarations. It never inspects
    source PDF bytes or establishes corpus correctness or review completion.
    """
    document = documents.get(sample.get("document_id", ""), {})
    return {
        "sample_id": sample["id"],
        "document_id": sample.get("document_id"),
        "family_id": sample.get("family_id", document.get("family_id")),
        "tags": sample.get("tags", document.get("tags", [])),
        "source_category": sample.get("source_category", document.get("source_category", "source-unknown")),
        "development_exposure": sample.get("development_exposure", document.get("development_exposure", "unknown")),
        "input_page_count": sample.get("input_page_count", len(sample.get("source_pages", []))),
    }


async def run_dataset(args: argparse.Namespace) -> int:
    from . import maintenance
    from .executors import execute_batch, prepare
    from .runtime import PreparationError, validate_execution_config

    dataset = args.dataset.resolve()
    manifest = read_json(dataset / "manifest.json")
    configs = execution_configs(args.config, args.pipeline)
    if args.prepare_only:
        print(json.dumps([prepare(config) for config in configs], ensure_ascii=False, indent=2))
        return 0
    if args.suite != "preflight8":
        require_frozen_execution(read_json(args.config), code_identity())
    jobs = execution_plan(manifest, dataset, args.suite)
    execution_jobs: list[Mapping[str, Any]] = list(jobs)
    for config in configs:
        validate_execution_config(config)
    manager = getattr(maintenance, "inference_services", None)
    if manager is None:
        raise PreparationError("the isolated inference lifecycle is not prepared")
    if not args.maintenance_window:
        raise ValueError("GPU execution requires the explicit --maintenance-window switch")
    output = args.output.resolve()
    if (output / "run.json").exists():
        raise FileExistsError("run destination already owns a run; use a new run identifier")
    output.mkdir(parents=True, exist_ok=True)
    input_root = dataset / "inputs"
    if getattr(args, "calibrate_single_pages", False):
        if args.suite != "preflight8":
            raise ValueError("direct single-page calibration is restricted to preflight8")
        from .rebenchmark import build_preflight_jobs
        jobs, input_root = build_preflight_jobs(manifest, dataset, output / "calibration-inputs")
        execution_jobs = list(jobs)
    session: dict[str, Any] = {
        "run_id": output.name,
        "created_at": _now(),
        "dataset": str(dataset),
        "dataset_name": manifest["name"],
        "reference_freeze": manifest.get("freeze_record"),
        "suite": args.suite,
        "formal": args.suite != "preflight8",
        "state": "prepared",
        "software": code_identity(),
        "configurations": configs,
        "cases": [],
        "errors": [],
        "software_snapshot": "artifacts/software",
    }
    if getattr(args, "calibrate_single_pages", False):
        session["preflight_job_plan"] = jobs
    snapshot_software(output / session["software_snapshot"], session["software"])
    write_json(output / "run.json", session)
    try:
        with maintenance.gpu1_window(output / "maintenance.json") as window:
            session["state"] = "running"
            write_json(output / "run.json", session)
            for config in configs:
                pipeline = config["pipeline"]
                pipeline_output = output / "artifacts" / pipeline
                pipeline_output.mkdir(parents=True, exist_ok=True)
                write_json(pipeline_output / "execution-config.json", config)
                print(f"{pipeline}: starting {args.suite}", flush=True)
                try:
                    async with manager(config, artifacts_dir=pipeline_output / "inference") as live_config:
                        observations = await execute_batch(
                            execution_jobs, live_config, output_dir=pipeline_output, inputs_dir=input_root
                        )
                except Exception as exc:
                    error = {"pipeline": pipeline, "type": type(exc).__name__, "message": str(exc),
                             "category": "engineering_preflight_failure", "traceback": traceback.format_exc()}
                    write_json(pipeline_output / "preparation-error.json", error)
                    if args.suite != "preflight8" or any(
                        state != "stopped" for state in window.get("research_owners", {}).values()
                    ):
                        raise
                    session["errors"].append(error)
                    write_json(output / "run.json", session)
                    print(f"{pipeline}: preparation failed; evidence retained; next independent configuration", flush=True)
                    continue
                for job, observation in zip(jobs, observations, strict=False):
                    case_output = pipeline_output / job["output_dir"]
                    # Identity and suite labels come from the fixed schedule, not SDK guesses.
                    observation.update(
                        {key: job[key] for key in (
                            "sample_id", "suite", "phase", "repetition", "input_page_count"
                        )}
                    )
                    observation["pipeline"] = pipeline
                    observation["dataset"] = manifest["name"]
                    observation["run_id"] = output.name
                    for key in ("parent_sample_id", "local_page"):
                        if key in job:
                            observation[key] = job[key]
                    write_json(case_output / "observation.json", observation)
                    session["cases"].append(
                        {
                            "pipeline": pipeline,
                            "sample_id": job["sample_id"],
                            "suite": job["suite"],
                            "phase": job["phase"],
                            "repetition": job["repetition"],
                            "observation": str((case_output / "observation.json").relative_to(output)),
                        }
                    )
                write_json(output / "run.json", session)
                if len(observations) != len(jobs):
                    raise PreparationError(
                        f"{pipeline}: execution stopped with {len(jobs) - len(observations)} "
                        "scheduled jobs unstarted; see retained execution ownership evidence"
                    )
                print(f"{pipeline}: worker completed; original results retained", flush=True)
        session["execution_outcome"] = "completed_with_preflight_failures" if session["errors"] else "completed"
        session["measurement_conditions"] = _measurement_conditions(output)
        if not session["measurement_conditions"]["valid"]:
            session["state"] = "invalidated"
            return 3
        session["state"] = session["execution_outcome"]
        return 2 if session["errors"] else 0
    except BaseException as exc:
        session["state"] = "cancelled" if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)) else "failed"
        session["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        if "measurement_conditions" not in session:
            session["measurement_conditions"] = _measurement_conditions(output)
        write_json(output / "measurement-conditions.json", session["measurement_conditions"])
        session["finished_at"] = _now()
        write_json(output / "run.json", session)


def _measurement_conditions(run: Path) -> dict[str, Any]:
    from .rebenchmark import assess_measurement_conditions

    try:
        return assess_measurement_conditions(read_json(run / "maintenance.json"))
    except (OSError, ValueError, TypeError) as exc:
        assessment = assess_measurement_conditions(None)
        assessment["evidence_error"] = {"type": type(exc).__name__, "message": str(exc)}
        return assessment


def _require_formal_measurement_conditions(run: Path, session: Mapping[str, Any]) -> None:
    """Reject invalid formal work before references, scores or figures are read."""
    formal_suites = {"lite", "quality800", "perf80"}
    development = session.get("development_experiment") is True and bool(session.get("experiment_id"))
    formal = session.get("formal") is True or (not development and session.get("suite") in formal_suites)
    # The scheduler writes both the suite and cases. A lone false formal flag
    # cannot turn its measured main comparison into a development experiment.
    if (not development
            and any(item.get("suite") in formal_suites for item in session.get("cases", []))):
        formal = True
    if not formal:
        return
    if session.get("state") != "completed":
        raise ValueError("formal scoring and reporting require state='completed' with valid measurement conditions")
    conditions = _measurement_conditions(run)
    if not conditions["valid"]:
        failures = ", ".join(problem["condition"] for problem in conditions["problems"])
        raise ValueError(f"formal measurement conditions are not satisfied: {failures}")


def score_run(run: Path, *, adjudications: Path | None = None,
              freeze: Path | None = None) -> Path:
    from .expected_evaluation import evaluate_saved

    if adjudications is not None:
        raise ValueError("expected-only scoring does not accept adjudications; no decision file was opened")

    run = run.resolve()
    session = read_json(run / "run.json")
    if session.get("state") in {"prepared", "running"}:
        raise ValueError(
            f"cannot score active run state {session['state']!r}; "
            "wait for execution and service restoration to finish"
        )
    _require_formal_measurement_conditions(run, session)
    if session.get("development_experiment") is True and session.get("experiment_id"):
        cleanup = session.get("cleanup_evidence")
        if not isinstance(cleanup, Mapping) or cleanup.get("maintenance_phase") != "restored":
            raise ValueError(
                "cannot score development experiment arm before confirmed service restoration; "
                "wait for the driver to record cleanup_evidence.maintenance_phase='restored'"
            )
    if freeze is None:
        raise ValueError("expected-only scoring requires a validated software freeze")
    score_id = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S%f")
    destination = run / "artifacts" / "scores" / ("expected-" + score_id)
    index = evaluate_saved(run, destination, expected_root=ROOT / "pdf_sample/parsing/expected", freeze=freeze)
    session["latest_scores"] = str(index.relative_to(run))
    write_json(run / "run.json", session)
    return index


def report_run(run: Path) -> Path:
    """Publish only completed canonical expected scores."""
    from .expected_report import render_expected_report

    run = run.resolve()
    session = read_json(run / "run.json")
    _require_formal_measurement_conditions(run, session)
    index_path = inside(run, session["latest_scores"])
    index = read_json(index_path)
    if index.get("protocol", {}).get("id") != SCORING_PROTOCOL["id"]:
        raise ValueError("reporting accepts only completed canonical expected scores")
    return render_expected_report(index_path)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    commands = command.add_subparsers(dest="command", required=True)
    package = commands.add_parser("package", help="materialize an explicit authored selection")
    package.add_argument("--selection", type=Path, required=True)
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--source-root", type=Path, default=ROOT)
    run = commands.add_parser("run", help="execute fixed research configurations")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--config", type=Path, default=ROOT / "benchmark/execution-lock.json")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--pipeline", nargs="+", choices=(*PIPELINES, "all"), default=["all"])
    run.add_argument("--suite", choices=("lite", "quality800", "perf80", "preflight8"), default="lite")
    run.add_argument("--maintenance-window", action="store_true")
    run.add_argument("--prepare-only", action="store_true")
    run.add_argument("--calibrate-single-pages", action="store_true",
                     help="add direct one-page calibration using the declared preflight pages")
    for name in ("score", "report"):
        child = commands.add_parser(name)
        child.add_argument("--run", type=Path, required=True)
        if name == "score":
            child.add_argument("--adjudications", type=Path, help="unsupported in expected-only evaluation; fails without reading the file")
            child.add_argument("--freeze", type=Path, help="validated scoring software and protocol identity")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "package":
        result = package_dataset(args.selection, args.output, source_root=args.source_root)
        print(f"Materialized {result['name']}; state={result['state']}; no corpus acceptance performed")
    elif args.command == "run":
        return asyncio.run(run_dataset(args))
    elif args.command == "score":
        print(score_run(args.run, adjudications=args.adjudications, freeze=args.freeze))
    else:
        print(report_run(args.run))
    return 0
