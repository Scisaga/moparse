"""Local dataset materialization, isolated execution and read-only evaluation."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import time
import traceback
from collections.abc import Mapping
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .packaging import inside, package_dataset, read_json, write_json

ROOT = Path(__file__).resolve().parent.parent
PIPELINES = tuple(f"P{number:02}" for number in range(1, 9))
SCORING_PROTOCOL = {
    "id": "mo-parse-eval-information-v5",
    "text_policy": "mo-parse-eval-text-v1",
    "field_content_equivalence": "declared_width_spacing_scoped_scalar_units_year_range_dash_terminal_prose_punctuation",
    "field_locator": "candidate_business_labels_and_scoped_context_before_value_comparison",
    "field_grades": "correct_or_incorrect_for_every_fixed_admitted_target",
    "primary_metrics": ["unit_presence", "text_aligned_with_coverage", "field_target_correctness",
                        "information_target_correctness", "measured_cost_and_stability"],
    "diagnostic_metrics": ["unaligned_target_cer", "raw_grid", "reading_order", "heading_levels", "locator_failure_reasons"],
    "scope": "read_only_rescore_existing_native_outputs",
    "qualifier_reading": "candidate_only_table_header_introduction_section_and_note_scopes",
    "reference_unknown": "outside_admitted_targets_references_remain_read_only",
    "reader_failure": "repair_before_final_grading_and_publication",
    "reader_revision": "scoped_literal_formats_13",
    "reference_unit_reading": "explicit_field_then_literal_scalar_or_local_ratio_then_table_scope",
}


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
    for distribution in ("rapidfuzz", "edlib", "markdown-it-py", "PyMuPDF", "psutil"):
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
    from .adjudications import reference_exclusions
    from .native_readback import READBACK_VERSION, read_native_relations
    from .scoring import score_case

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
    dataset = Path(session["dataset"])
    manifest = read_json(dataset / "manifest.json")
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    documents = {document["document_id"]: document for document in manifest.get("documents", [])}
    sample_metadata = {key: _sample_metadata(sample, documents) for key, sample in samples.items()}
    human_record = read_json(adjudications) if adjudications else None
    if human_record is not None:
        reference_exclusions(human_record, "")  # Validate the supplied operation, not the corpus.
    identity = code_identity()
    frozen_scoring = read_scoring_freeze(freeze, identity) if freeze is not None else None
    score_id = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S%f")
    destination = run / "artifacts" / "scores" / f"{score_id}-{identity['software_id'][:12]}"
    destination.mkdir(parents=True, exist_ok=False)
    snapshot_software(destination / "software", identity)
    index: dict[str, Any] = {
        "score_id": destination.name,
        "run_id": session["run_id"],
        "created_at": _now(),
        "formal": session["formal"],
        "software": identity,
        "scoring_protocol": copy.deepcopy(SCORING_PROTOCOL),
        "reference_freeze": manifest.get("freeze_record"),
        "dataset_declaration": {
            "name": manifest.get("name"), "kind": manifest.get("kind"),
            "state": manifest.get("state"), "freeze_record": manifest.get("freeze_record"),
            "suites": manifest.get("suites", {}), "sample_metadata": sample_metadata,
            "scope": "frozen_manifest_declarations_not_corpus_acceptance",
        },
        "results": [],
        "unscored": [],
        "native_readback": {"reader_version": READBACK_VERSION, "software_id": identity["software_id"],
                            "observations": []},
    }
    if frozen_scoring is not None:
        write_json(destination / "scoring-freeze.json", frozen_scoring)
        index["scoring_freeze"] = {
            "path": str((destination / "scoring-freeze.json").relative_to(run)),
            "record": frozen_scoring,
        }
    if human_record is not None:
        write_json(destination / "reference-adjudications.json", human_record)
        index["reference_adjudications"] = {
            "path": str((destination / "reference-adjudications.json").relative_to(run)),
            "record": human_record,
            "applied_decision_ids": [], "unmatched_decision_ids": [], "applied_score_cases": 0,
        }
    applied_decisions: set[str] = set()
    active_pipeline: str | None = None
    for case in session["cases"]:
        if case["phase"] == "warmup":
            continue
        if case["pipeline"] != active_pipeline:
            active_pipeline = case["pipeline"]
            print(f"Scoring saved outputs: {active_pipeline}", file=sys.stderr, flush=True)
        sample = samples[case["sample_id"]]
        reference_path = sample.get("evaluation")
        if not reference_path:
            index["unscored"].append({**sample_metadata[case["sample_id"]], **case,
                                      "reason": "no_authored_scoring_reference"})
            continue
        reference = read_json(inside(dataset, reference_path))
        if reference.get("review_status") != "confirmed":
            index["unscored"].append({**sample_metadata[case["sample_id"]], **case,
                                      "reason": "reference_not_declared_visually_confirmed"})
            continue
        original_observation = inside(run, case["observation"])
        observation = read_json(original_observation)
        source_native = original_observation.with_name("native.json")
        readback_started = time.perf_counter()
        native_exists = source_native.is_file()
        try:
            native = read_json(source_native) if native_exists else None
            if native_exists and not isinstance(native, Mapping):
                raise ValueError("saved native result is not an object")
            observation, diagnostic = read_native_relations(observation, native)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            observation = copy.deepcopy(observation)
            diagnostic = {"reader_version": READBACK_VERSION, "status": "readback_error",
                          "error_type": type(exc).__name__, "message": str(exc), "records": []}
        readback_seconds = time.perf_counter() - readback_started
        derived_relative = f"observations/{case['pipeline']}/{case['suite']}-r{case['repetition']}/{case['sample_id']}.json"
        diagnostic_relative = str(Path(derived_relative).with_suffix(".readback.json"))
        provenance = {
            "reader_version": READBACK_VERSION, "software_id": identity["software_id"],
            "source_observation": str(original_observation.relative_to(run)),
            "source_native": str(source_native.relative_to(run)),
            "native_status": diagnostic["status"], "observation": str((destination / derived_relative).relative_to(run)),
            "diagnostics": str((destination / diagnostic_relative).relative_to(run)),
            "readback_seconds": readback_seconds,
            "timing_scope": "scoring_analysis_only_not_original_worker_processing",
        }
        observation["scoring_readback"] = provenance
        diagnostic.update(provenance)
        write_json(destination / derived_relative, observation)
        write_json(destination / diagnostic_relative, diagnostic)
        index["native_readback"]["observations"].append(provenance)
        declared = sample_metadata[case["sample_id"]]
        reference = {**reference,
                     **{key: reference.get(key, declared[key]) for key in (
                         "document_id", "family_id", "tags", "source_category", "development_exposure",
                     )},
                     **{key: observation.get(key) for key in (
            "suite", "phase", "repetition", "input_page_count", "dataset", "run_id"
        )}}
        scored = score_case(
            reference, observation, dataset,
            reference_exclusions=reference_exclusions(human_record, case["sample_id"]) if human_record else None,
        )
        if human_record is not None and scored["human_reference_adjudications"]:
            applied_decisions.update(item["id"] for item in scored["human_reference_adjudications"])
            index["reference_adjudications"]["applied_score_cases"] += 1
        relative = f"{case['pipeline']}/{case['suite']}-r{case['repetition']}/{case['sample_id']}.json"
        write_json(destination / relative, scored)
        index["results"].append(str((destination / relative).relative_to(run)))
    if human_record is not None:
        index["reference_adjudications"]["applied_decision_ids"] = sorted(applied_decisions)
        index["reference_adjudications"]["unmatched_decision_ids"] = [
            item["id"] for item in human_record.get("decisions", []) if item["id"] not in applied_decisions
        ]
    failed_readbacks = [item for item in index["native_readback"]["observations"]
                        if item.get("native_status") == "readback_error"]
    if failed_readbacks:
        raise ValueError(
            f"cannot publish scores with {len(failed_readbacks)} engineering readback errors; "
            "repair the reader before rescoring"
        )
    if frozen_scoring is not None and code_identity()["software_id"] != identity["software_id"]:
        raise ValueError("scoring software changed during the frozen scoring session")
    write_json(destination / "index.json", index)
    session["latest_scores"] = str((destination / "index.json").relative_to(run))
    write_json(run / "run.json", session)
    return destination / "index.json"


def report_run(run: Path) -> Path:
    run = run.resolve()
    session = read_json(run / "run.json")
    _require_formal_measurement_conditions(run, session)

    import csv

    import matplotlib

    from .report_figures import render_figures
    from .reporting import (
        QUALITY_SLICE_COLUMNS,
        aggregate_reports,
        render_appendix,
        render_markdown,
        render_quality_slices,
    )

    index = read_json(inside(run, session["latest_scores"]))
    declarations = index.get("dataset_declaration", {})
    sample_metadata = declarations.get("sample_metadata", {})
    unscored = {
        tuple(item.get(key) for key in ("pipeline", "sample_id", "suite", "phase", "repetition")): item
        for item in index.get("unscored", [])
    }
    results = [read_json(inside(run, relative)) for relative in index["results"]]
    from .scoring import require_complete_target_grading
    for result in results:
        require_complete_target_grading(result)
    def quality_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
        return tuple(item.get(key) for key in ("pipeline", "sample_id", "suite", "phase", "repetition"))
    required = [quality_key(case) for case in session.get("cases", [])
                if case.get("suite") == "quality800" and case.get("phase") == "measured"
                and unscored.get(quality_key(case), {}).get("reason") not in {
                    "no_authored_scoring_reference", "reference_not_declared_visually_confirmed"}]
    available = [quality_key(result) for result in results
                 if result.get("suite") == "quality800" and result.get("phase") == "measured"]
    if len(available) != len(set(available)) or set(required) - set(available):
        raise ValueError("target grading incomplete: quality cases are missing or duplicated")
    field_details = []
    for relative, result in zip(index["results"], results, strict=True):
        if result.get("suite") != "quality800":
            continue
        for unit in result.get("units", []):
            for field in unit.get("fields", []):
                if field["status"] == "not_scored":
                    continue
                field_details.append({
                    "pipeline": result.get("pipeline"), "sample_id": result.get("sample_id"),
                    "unit_id": unit["id"], "field_index": field["index"], "score_path": relative,
                    "status": field["status"], "reason": field["reason"],
                    "value_correct": field.get("content_exact"),
                    "information_status": field["outcome"],
                    "native_path": field.get("native_path"),
                    "details_json": json.dumps(field, ensure_ascii=False),
                })
    with (run / "field-details.csv").open("w", encoding="utf-8", newline="") as handle:
        detail_writer = csv.DictWriter(handle, fieldnames=(
            "pipeline", "sample_id", "unit_id", "field_index", "score_path", "status", "reason",
            "value_correct", "information_status", "native_path", "details_json"))
        detail_writer.writeheader()
        detail_writer.writerows(field_details)
    scored_identities = {
        tuple(result.get(key) for key in ("pipeline", "sample_id", "suite", "phase", "repetition"))
        for result in results
    }
    for item in session["cases"]:
        identity = tuple(item.get(key) for key in ("pipeline", "sample_id", "suite", "phase", "repetition"))
        if identity in scored_identities:
            continue
        observation = read_json(inside(run, item["observation"]))
        declared = sample_metadata.get(item["sample_id"], {})
        missing = unscored.get(identity, {})
        results.append({**observation, **declared,
                        "input_page_count": observation.get("input_page_count", declared.get("input_page_count")),
                        "metrics": {}, "coverage": {}, "scorer_status": "not_scored",
                        "not_scored_reason": missing.get("reason", "warmup_or_no_score_record")})
    report = aggregate_reports(results)
    report["execution"] = {
        key: session.get(key)
        for key in ("run_id", "formal", "state", "created_at", "finished_at", "errors", "dataset_name", "software", "configurations", "reference_freeze", "execution_sources", "source_runs", "composition", "measurement_conditions")
    }
    report["unscored"] = index["unscored"]
    report["score_id"] = index["score_id"]
    report["score_index"] = session["latest_scores"]
    report["scoring_software"] = index.get("software")
    report["scoring_protocol"] = index.get("scoring_protocol")
    report["scoring_freeze"] = index.get("scoring_freeze")
    report["reference_adjudications"] = index.get("reference_adjudications")
    report["dataset_declaration"] = declarations
    inspection = run / "artifacts/software-inspection.json"
    report["software_inspection"] = {
        "path": str(inspection.relative_to(run)), "record": read_json(inspection),
    } if inspection.is_file() else None
    for key, relative in (("qualitative_review", "visual-review/README.md"),
                          ("execution_failure_notes", "execution-failure-notes.md"),
                          ("scoring_notes", "scoring-implementation-notes.md")):
        report[key] = relative if inside(run, relative).is_file() else None
    # These are declared execution artifacts, never corpus inventory checks.
    # Lifecycle peaks include model loading and warm-up; do not relabel them
    # as per-sample resource maxima.
    report["runtime_evidence"] = {}
    for config in session.get("configurations", []):
        name = config["pipeline"]
        evidence = {}
        for key, relative in (
            ("inference_lifecycle", f"artifacts/{name}/inference/inference-ownership.json"),
            ("inference_lifecycle_resources", f"artifacts/{name}/inference/resources.json"),
            ("worker_lifecycle_resources", f"artifacts/{name}/worker-resources.json"),
            ("worker_exit", f"artifacts/{name}/worker-exit.json"),
        ):
            path = inside(run, relative)
            evidence[key] = {"path": relative, "record": read_json(path)} if path.is_file() else None
        report["runtime_evidence"][name] = evidence
    maintenance_record = run / "maintenance.json"
    report["maintenance"] = read_json(maintenance_record) if maintenance_record.is_file() else None
    # Assess the actual maintenance evidence again rather than treating a
    # cached run summary as proof of either policy or service restoration.
    from .rebenchmark import assess_measurement_conditions
    report["measurement_conditions"] = assess_measurement_conditions(report["maintenance"])
    presentation_notes = inside(run, "presentation-notes.json")
    if presentation_notes.is_file():
        notes = read_json(presentation_notes)
        report["overview_case_studies"] = notes.get("case_studies", [])
        report["overview_configuration_notes"] = notes.get("configuration_notes", [])
    figures = render_figures(report, inside(run, "figures"))
    report["presentation"] = {
        "layout": "comparison_overview_with_full_appendix",
        "generator_software": code_identity(),
        "matplotlib_version": matplotlib.__version__,
        "figure_index": "figures/index.json",
        "appendix": "appendix.md",
        "scope": "existing score and runtime artifacts only; no rescoring, inference or corpus acceptance",
    }
    write_json(run / "summary.json", report)
    markdown = render_markdown(report, figures)
    appendix = render_appendix(report)
    if not session["formal"]:
        markdown = (
            "# 工程预检记录：不构成Lite正式评测\n\n"
            "本次仅运行已目视确认的预检输入；800页正式参考尚未由本次运行证明完成。\n\n"
            + markdown.replace("# MO-Parse 解析评测报告\n\n", "", 1)
        )
    (run / "report.md").write_text(markdown, encoding="utf-8")
    (run / "appendix.md").write_text(appendix, encoding="utf-8")
    (run / "group-comparisons.md").write_text(render_quality_slices(report), encoding="utf-8")
    with (run / "quality-slices.csv").open("w", encoding="utf-8", newline="") as handle:
        slice_writer = csv.DictWriter(handle, fieldnames=QUALITY_SLICE_COLUMNS)
        slice_writer.writeheader()
        slice_writer.writerows(report.get("quality_slices", []))
    with (run / "metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("pipeline", "sample_id", "suite", "phase", "repetition", "metrics_json"))
        for result in results:
            writer.writerow(
                [result.get(key) for key in ("pipeline", "sample_id", "suite", "phase", "repetition")]
                + [json.dumps(result.get("metrics", {}), ensure_ascii=False)]
            )
    return run / "report.md"


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
            child.add_argument("--adjudications", type=Path, help="explicit human source-backed exclusions, uniformly applied")
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
