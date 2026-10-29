"""Paired service-output evaluation over saved P07/P08 results.

The isolated worker receives input PDFs and native candidates, never expected
materials. PDF access here is candidate service processing, not corpus review.
Only the separate scoring command reads frozen evaluation references.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import shutil
import subprocess
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from .packaging import inside, read_json, write_json

ROOT = Path(__file__).resolve().parent.parent
SCORING_MODULES = (
    "scoring.py", "matching.py", "metrics.py", "representations.py", "adapters.py",
    "native_relations.py", "native_readback.py", "adjudications.py", "information.py",
    "information_reading.py",
)
WORKER_CASE_FIELDS = (
    "case_id", "sample_id", "suite", "phase", "repetition", "input_pages", "input", "native", "job_id",
)


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def prepare_run(baseline: Path, destination: Path, service_config: Path, *, pipeline: str = "P07",
                previous_run: Path | None = None) -> Path:
    """Use declared execution identities; do not validate dataset contents."""
    from .cli import code_identity, snapshot_software

    if pipeline not in {"P07", "P08"}:
        raise ValueError("service comparison supports P07 and P08")
    baseline = baseline.resolve()
    session = read_json(baseline / "run.json")
    score_index = read_json(inside(baseline, session["latest_scores"]))
    identity = code_identity()
    old_hashes = score_index["software"]["module_sha256"]
    if any(old_hashes.get(name) != identity["module_sha256"].get(name)
           for name in SCORING_MODULES):
        raise ValueError("paired comparison requires the unchanged frozen shared scorer")
    if (identity["python"] != score_index["software"]["python"]
            or identity["dependencies"] != score_index["software"]["dependencies"]):
        raise ValueError("paired scoring requires the frozen scoring runtime dependencies")
    dataset = Path(session["dataset"]).resolve()
    manifest = read_json(dataset / "manifest.json")
    if manifest.get("freeze_record") != score_index.get("reference_freeze"):
        raise ValueError("reference freeze declaration differs from the baseline score")
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    quality_scores: dict[str, tuple[str, dict[str, Any]]] = {}
    for relative in score_index["results"]:
        if f"/{pipeline}/quality800-r1/" not in "/" + relative:
            continue
        scored = read_json(inside(baseline, relative))
        quality_scores[scored["sample_id"]] = relative, scored
    cases = []
    for ordinal, case in enumerate(c for c in session["cases"] if c["pipeline"] == pipeline):
        observation = read_json(inside(baseline, case["observation"]))
        sample = samples[case["sample_id"]]
        score_path, scored = quality_scores[case["sample_id"]]
        native_relative = Path(case["observation"]).relative_to(f"artifacts/{pipeline}").with_name("native.json")
        case_id = f"{case['suite']}-r{case['repetition']}-{case['sample_id']}"
        cases.append({
            "case_id": case_id, "sample_id": case["sample_id"], "suite": case["suite"],
            "phase": case["phase"], "repetition": case["repetition"],
            "input_pages": observation["input_page_count"],
            "input": str(Path(sample["input"]).relative_to("inputs")),
            "native": native_relative.as_posix(), "baseline_score_source": score_path,
            "baseline_observation_source": case["observation"],
            "job_id": f"service_{ordinal:04d}",
            **{key: copy.deepcopy(scored.get(key)) for key in (
                "document_id", "family_id", "tags", "development_exposure", "source_category",
            )},
        })
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    configuration = read_json(service_config)
    runtime = read_json(ROOT / "benchmark/execution-lock.json")["pipelines"]["P07"]["runtime"]
    native_configuration = next(item for item in session["configurations"] if item["pipeline"] == pipeline)
    record = {
        "schema": "moparse-service-evaluation/1", "run_id": destination.name,
        "report_version": "service-paired-v1", "state": "prepared", "created_at": now(),
        "baseline_run": str(baseline), "baseline_score_id": score_index["score_id"],
        "baseline_software": score_index["software"], "dataset": str(dataset),
        "dataset_name": manifest.get("name"), "reference_freeze": manifest.get("freeze_record"),
        "reference_adjudications": score_index.get("reference_adjudications", {}).get("record"),
        "scoring_protocol": score_index["scoring_protocol"], "software": identity,
        "paired_native_rescore_required": True,
        "native_pipeline": {**{key: copy.deepcopy(native_configuration.get(key)) for key in (
            "pipeline", "revisions", "native_view_policy", "source_policy", "inference_services",
        )}, "versions": {key: value for key, value in native_configuration.get("versions", {}).items()
                         if key in {"mineru", "mineru-vl-utils", "docvortex", "glmocr"}}},
        "service_config": configuration, "options": {"describe_images": False, "scan_policy": "auto"},
        "execution_environment": {
            "image": runtime["image"], "cpus": 8, "memory_bytes": 8 * 1024 ** 3,
            "network": "none", "gpu_devices": [], "outer_concurrency": 1,
            "deployment_status": "not_deployed", "tts_actions": [],
        },
        "measurement_notes": [
            f"Saved valid {pipeline} native candidates are replayed; no model inference is repeated.",
            "P08 keeps visual-only source access; PDF text and vector-table supplementation are disabled.",
            "PDF source supplementation is actual candidate service processing, not corpus review.",
            "Reference materials are unavailable to the isolated candidate worker.",
            "Postprocessing wall time includes bridge readback, source processing, export, IR, assets and semantics.",
            "Native JSON loading and final result persistence/scoring/reporting are timed separately.",
            "Asset writes internal to actual asset materialization remain in the measured stage.",
            "Candidate stage snapshots are captured without references; capture CPU overhead stays inside postprocessing time and is recorded separately.",
            "Stage snapshot persistence and all stage scoring are outside postprocessing time.",
            "The historical native duration plus replay time is not a newly measured end-to-end duration.",
        ],
        "cases": cases,
    }
    if previous_run is not None:
        previous_run = previous_run.resolve()
        previous = read_json(previous_run / "run.json")
        previous_freeze = read_json(previous_run / "execution-freeze.json")
        if (previous.get("state") != "completed"
                or previous["software"]["software_id"] != previous_freeze["software"]["software_id"]
                or previous.get("reference_freeze") != record["reference_freeze"]
                or Path(previous["dataset"]).resolve() != dataset
                or Path(previous["baseline_run"]).resolve() != baseline
                or previous["native_pipeline"] != record["native_pipeline"]):
            raise ValueError("previous candidate execution identity or reference scope differs")
        previous_cases = {case["case_id"]: case for case in previous["cases"]}
        for case in cases:
            old = previous_cases.get(case["case_id"])
            if old is None or any(old.get(key) != case.get(key) for key in (
                "sample_id", "suite", "phase", "repetition", "input_pages", "input", "native", "baseline_observation_source",
            )):
                raise ValueError("previous candidate is not the same declared native input")
            case["previous_observation"] = old["observation"]
        record["previous_outputs"] = {
            "run": str(previous_run), "software": previous["software"],
            "execution_freeze": str(previous_run / "execution-freeze.json"),
            "policy": "unchanged_saved_final_bytes_rescored_with_current_shared_frozen_rules",
        }
    write_json(destination / "run.json", record)
    snapshot_software(destination / "software", identity)
    write_json(destination / "candidate" / "worker-plan.json", {
        "run_id": record["run_id"], "dataset_name": record["dataset_name"],
        "pipeline": pipeline,
        "service_config": configuration, "options": record["options"],
        "cases": [{key: case[key] for key in WORKER_CASE_FIELDS}
                  for case in cases],
    })
    return destination


def docker_command(run: Path, phase: str, name: str) -> list[str]:
    record = read_json(run / "run.json")
    environment = record["execution_environment"]
    baseline = Path(record["baseline_run"])
    return [
        "docker", "run", "--name", name, "--network", "none", "--read-only",
        "--cpus", "8", "--memory", "8g", "--pids-limit", "512",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--tmpfs", "/tmp:rw,size=2147483648", "--workdir", "/workspace",
        "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "CUDA_VISIBLE_DEVICES=",
        "--env", "NVIDIA_VISIBLE_DEVICES=void", "--env", "OMP_NUM_THREADS=8",
        "--env", "OPENBLAS_NUM_THREADS=8", "--env", "MKL_NUM_THREADS=8",
        "--volume", f"{run / 'software'}:/workspace:ro",
        "--volume", f"{Path(record['dataset']) / 'inputs'}:/inputs:ro",
        "--volume", f"{baseline / 'artifacts' / record['native_pipeline']['pipeline']}:/native:ro",
        "--volume", f"{run / 'candidate'}:/output:rw", "--entrypoint", "python",
        environment["image"], "-m", "moparse_eval.service_evaluation", "worker",
        "--plan", "/output/worker-plan.json", "--phase", phase,
    ]


def launch(run: Path, phase: str) -> int:
    run = run.resolve()
    record = read_json(run / "run.json")
    name = f"moparse-service-{run.name}-{phase}".lower()
    if phase == "measured" and record.get("state") != "frozen":
        raise ValueError("freeze the new service implementation after successful preflight first")
    if phase == "measured":
        from .cli import code_identity
        if code_identity()["software_id"] != record["software"]["software_id"]:
            raise ValueError("service implementation changed after freeze")
    log_path = run / f"{phase}.log"
    command = docker_command(run, phase, name)
    write_json(run / f"{phase}-command.json", command)
    record["state"] = "running" if phase == "measured" else "preflight_running"
    write_json(run / "run.json", record)
    with log_path.open("wb") as log:
        process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    inspected = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, check=True)
    state = json.loads(inspected.stdout)[0]["State"]
    write_json(run / f"{phase}-exit.json", state)
    if state["Running"]:
        raise RuntimeError("original CPU worker is still running; do not start another attempt")
    subprocess.run(["docker", "rm", name], check=True, capture_output=True)
    record = read_json(run / "run.json")
    if process.returncode:
        record["state"] = "engineering_failure"
        record["failed_phase"] = phase
        write_json(run / "run.json", record)
        return process.returncode
    outcomes = []
    for case in record["cases"]:
        if (case["phase"] == "warmup") != (phase == "warmup"):
            continue
        relative = f"candidate/artifacts/{case['case_id']}/outcome.json"
        outcome = read_json(run / relative)
        case.update(outcome)
        for key in ("observation", "final_markdown", "final_json"):
            case[key] = "candidate/" + case[key]
        for stage in case.get("stage_outputs", []):
            for key in ("observation", "markdown"):
                stage[key] = "candidate/" + stage[key]
        case["outcome"] = relative
        outcomes.append(outcome)
    record["state"] = "completed" if phase == "measured" else "preflight_passed"
    record["execution_environment"]["observed_worker"] = read_json(
        run / "candidate" / f"{phase}-environment.json")
    if phase == "measured":
        record["finished_at"] = now()
    write_json(run / "run.json", record)
    return 0


def freeze_run(run: Path, validation: Path) -> None:
    from .cli import code_identity
    record = read_json(run / "run.json")
    if record.get("state") != "preflight_passed":
        raise ValueError("a successful isolated service preflight is required")
    checks = read_json(validation)
    if checks.get("status") != "passed":
        raise ValueError("service freeze requires passed engineering validation")
    identity = code_identity()
    if identity["software_id"] != record["software"]["software_id"]:
        raise ValueError("code changed after preflight; prepare and preflight the current implementation")
    record.update(state="frozen", frozen_at=now(), validation=checks)
    write_json(run / "execution-freeze.json", {
        "software": identity, "options": record["options"], "service_config": record["service_config"],
        "environment": record["execution_environment"], "validation": checks,
        "baseline_score_id": record["baseline_score_id"], "frozen_at": record["frozen_at"],
    })
    write_json(run / "run.json", record)


def require_shared_scoring(record: dict[str, Any], identity: dict[str, Any], *,
                           paired_native_rescore: bool = False) -> None:
    """Allow a separately validated final reader without altering the shared rules."""
    execution = record["software"]
    allowed = {"service_evaluation.py", "service_observation.py", "service_report.py", "service_artifacts.py"}
    if paired_native_rescore:
        allowed.add("scoring.py")
    names = set(execution["module_sha256"]) | set(identity["module_sha256"])
    if any(execution["module_sha256"].get(name) != identity["module_sha256"].get(name)
           for name in names - allowed):
        raise ValueError("shared scoring or native bridge changed; paired scoring is not admitted")
    if any(execution[key] != identity[key] for key in (
        "support_module_sha256", "python", "dependencies",
    )):
        raise ValueError("service implementation or scoring dependencies changed after execution")


def freeze_scoring(run: Path, validation: Path) -> None:
    from .cli import code_identity, snapshot_software
    record = read_json(run / "run.json")
    if record["state"] != "completed":
        raise ValueError("finish candidate execution before freezing its analysis reader")
    identity = code_identity()
    checks = read_json(validation)
    if checks.get("status") != "passed":
        raise ValueError("final-output readback requires passed synthetic validation")
    paired_native_rescore = checks.get("paired_native_rescore") is True
    if record.get("paired_native_rescore_required") and not paired_native_rescore:
        raise ValueError("this paired run requires native and final outputs to be rescored together")
    require_shared_scoring(record, identity, paired_native_rescore=paired_native_rescore)
    software_path = run / "scoring-software" / identity["software_id"]
    if not software_path.exists():
        snapshot_software(software_path, identity)
    write_json(run / "scoring-freeze.json", {
        "software": identity, "software_id": identity["software_id"],
        "execution_software_id": record["software"]["software_id"],
        "protocol_id": record["scoring_protocol"]["id"], "validation": checks,
        "reader_scope": "faithful final-output readback; same declared label policy in grids and paths",
        "paired_native_rescore": paired_native_rescore,
        "software_snapshot": str(software_path.relative_to(run)),
        "frozen_at": now(),
    })


def oriented_source(path: Path, native: dict[str, Any], destination: Path) -> Path:
    """Apply saved runtime orientation; no orientation prediction or reference lookup."""
    processing = native.get("page_processing", [])
    if not any(item.get("rotation_clockwise", 0) for item in processing):
        return path
    import pymupdf
    with pymupdf.open(path) as source:
        for item in processing:
            number = item["page"]
            rotation = item.get("rotation_clockwise", 0)
            if rotation not in {0, 90, 180, 270}:
                raise ValueError("saved runtime orientation is unsupported")
            page = source[number - 1]
            page.set_rotation((page.rotation + rotation) % 360)
        source.save(destination)
    return destination


def require_replay_ready(diagnostic: dict[str, Any]) -> None:
    """Do not turn a replay identity/schema failure into a parser omission."""
    blocked = [entry for entry in diagnostic.get("errors", [])
               if entry.get("code") or entry.get("error") or entry.get("projection_errors")]
    if blocked:
        raise RuntimeError("native replay engineering readback failed; see replay-diagnostics.json")


async def execute_case(plan: dict[str, Any], case: dict[str, Any], output: Path) -> dict[str, Any]:
    import tempfile
    from types import SimpleNamespace

    from app.models import ContentParseOptions, StoredSource
    from app.parsers.glm_ocr_remote import GlmOcrRemoteAdapter
    from app.services.evidence_service import PageEvidenceService
    from app.services.export_service import ExportService
    from app.services.final_content_service import FinalContentService
    from app.services.ir_service import DocumentIRService
    from app.services.multimodal_service import MultimodalService
    from app.services.native_text_service import NativeTextService
    from app.services.parser_service import ParserService
    from app.services.pdf_table_evidence_service import PDFTableEvidenceService
    from app.services.quality_service import QualityService
    from app.services.storage_service import StorageService
    from app.services.table_semantics_service import TableSemanticsService
    from app.utils.deadline import attach_deadline

    from .runtime import MemoryObservation
    from .service_observation import build_service_observation
    from .service_replay_native import replay_native
    from .service_stages import capture_stage, materialize_stage

    class NoInference:
        calls = 0
        async def recognize_image(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            raise RuntimeError("model inference is forbidden in service replay")

    directory = output / "artifacts" / case["case_id"]
    directory.mkdir(parents=True, exist_ok=False)
    load_start = time.perf_counter()
    native = read_json(Path("/native") / case["native"])
    load_seconds = time.perf_counter() - load_start
    settings = SimpleNamespace(**{**plan["service_config"], "data_dir": output / "data"})
    storage = StorageService(settings)
    await storage.create_job_layout(case["job_id"])
    options = attach_deadline(ContentParseOptions(**plan["options"], timeout_seconds=3600), 3600)
    inference = NoInference()
    stages: dict[str, float] = {}
    snapshots: list[dict[str, Any]] = []
    diagnostic_capture_seconds = 0.0
    pipeline = plan.get("pipeline", "P07")

    def capture(name: str, *, pages_only: bool = False) -> None:
        nonlocal diagnostic_capture_seconds
        selected = plan["service_config"].get("diagnostic_capture_stages")
        if selected is not None and name not in selected:
            return
        capture_started = time.perf_counter()
        snapshots.append(capture_stage(result, stage=name, sample_id=case["sample_id"], pages_only=pages_only,
                                       pipeline=pipeline))
        diagnostic_capture_seconds += time.perf_counter() - capture_started

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="moparse-service-") as temporary, MemoryObservation() as memory:
        stage_start = time.perf_counter()
        original = Path("/inputs") / case["input"]
        path = oriented_source(original, native, Path(temporary) / "oriented.pdf")
        source = StoredSource(path=path, filename=original.name, mime_type="application/pdf",
                              size_bytes=path.stat().st_size, page_count=case["input_pages"])
        stages["saved_orientation_seconds"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        result, bridge = replay_native(native, source, options, document_id=case["job_id"])
        try:
            require_replay_ready(bridge)
        except RuntimeError:
            write_json(directory / "replay-diagnostics.json", bridge)
            raise
        stages["native_bridge_seconds"] = time.perf_counter() - stage_start
        capture("bridge_pages", pages_only=True)
        # Calling these exact service stages avoids parser initialization or a
        # second model request. No replacement postprocessor is implemented.
        stage_start = time.perf_counter()
        evidence = (await asyncio.to_thread(PageEvidenceService(settings).inspect, source,
                                            {page.page_number for page in result.pages})
                    if pipeline == "P07" else {})
        stages["page_evidence_seconds"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        if pipeline == "P07":
            await PDFTableEvidenceService(settings).apply(result, source, options)
        stages["table_source_seconds"] = time.perf_counter() - stage_start
        capture("source_pages", pages_only=True)
        stage_start = time.perf_counter()
        if pipeline == "P07":
            await NativeTextService().apply_async(result, evidence, options)
        stages["native_text_seconds"] = time.perf_counter() - stage_start
        capture("native_pages", pages_only=True)
        stage_start = time.perf_counter()
        service = object.__new__(ParserService)
        service.settings, service.export_service = settings, ExportService()
        service._finalize_exports(result, options)
        stages["exports_seconds"] = time.perf_counter() - stage_start
        capture("exported")
        stage_start = time.perf_counter()
        QualityService(settings).assess(result)
        stages["quality_diagnostics_seconds"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        result.parse_result = DocumentIRService(settings).build(result, source, evidence)
        stages["ir_seconds"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        await MultimodalService(settings, storage, cast(GlmOcrRemoteAdapter, inference)).enrich_page_content(
            result.parse_result, result, source, evidence, options, image_parser=None)
        stages["assets_seconds"] = time.perf_counter() - stage_start
        capture("assets")
        stage_start = time.perf_counter()
        if settings.semantic_table_output_enabled:
            await TableSemanticsService().apply(result, options)
        stages["semantics_seconds"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        FinalContentService().apply(result)
        stages["final_content_seconds"] = time.perf_counter() - stage_start
        capture("final")
        elapsed = time.perf_counter() - started
        if inference.calls:
            raise RuntimeError("unexpected model request: service replay is invalid")
    result.usage.duration_ms = round(elapsed * 1000)
    result.parse_result.runtime.duration_ms = result.usage.duration_ms
    persist_start = time.perf_counter()
    await storage.write_result(case["job_id"], result)
    (directory / "final.md").write_text(result.markdown)
    (directory / "final.txt").write_text(result.plain_text)
    write_json(directory / "final.json", result.parse_result.model_dump(mode="json"))
    write_json(directory / "service-evidence.json", {
        "bridge": bridge, "source_verification": result._source_verification,
        "semantic_tables": [asdict(view) for view in result._semantic_tables],
        "table_fragments": [asdict(cast(Any, fragment)) for fragment in result._table_fragments],
        "table_views": [asdict(cast(Any, view)) for view in result._table_views],
        "source_regions": [asdict(cast(Any, region)) for region in result._source_regions],
        "final_text_evidence": result._final_text_evidence,
        "warnings": [warning.model_dump(mode="json") for warning in result.warnings],
    })
    metadata = {key: case[key] for key in ("suite", "phase", "repetition")}
    metadata.update(run_id=plan["run_id"],
                    timing={"processing_seconds": elapsed, "postprocessing_seconds": elapsed})
    observation = build_service_observation(result, sample_id=case["sample_id"], metadata=metadata,
                                            pipeline=f"{pipeline}+MO-Parse")
    observation["dataset"] = plan["dataset_name"]
    observation["input_page_count"] = case["input_pages"]
    write_json(directory / "observation.json", observation)
    stage_outputs = []
    for captured in snapshots:
        snapshot = materialize_stage(captured)
        name = snapshot["stage"]
        snapshot["observation"].update(
            dataset=plan["dataset_name"], input_page_count=case["input_pages"], **metadata,
        )
        markdown_path = directory / "stages" / f"{name}.md"
        markdown_path.parent.mkdir(exist_ok=True)
        markdown_path.write_text(snapshot["markdown"])
        observation_path = directory / "stages" / f"{name}.json"
        write_json(observation_path, snapshot["observation"])
        stage_outputs.append({
            "stage": name, "scope": snapshot["scope"],
            "markdown": str(markdown_path.relative_to(output)),
            "observation": str(observation_path.relative_to(output)),
        })
    statuses = {page.status.value for page in result.pages}
    status = "partial" if "failed" in statuses or result.parse_result.status == "partial" else (
        "completed_with_warnings" if "warning" in statuses else "completed")
    views = result._semantic_tables
    outcome = {
        "case_id": case["case_id"], "status": status,
        "observation": str((directory / "observation.json").relative_to(output)),
        "final_markdown": str((directory / "final.md").relative_to(output)),
        "final_json": str((directory / "final.json").relative_to(output)),
        "timing": {"postprocessing_seconds": elapsed, "native_json_load_seconds": load_seconds,
                   "pure_persistence_and_observation_seconds": time.perf_counter() - persist_start,
                   "diagnostic_capture_seconds": diagnostic_capture_seconds, **stages},
        "stage_outputs": stage_outputs,
        "resources": {"peak_rss_bytes": memory.peak_bytes, "rss_samples": memory.sample_count},
        "conversion": {"total_views": len(views),
                       "converted": sum(view.status == "converted" for view in views),
                       "partial": sum(view.status == "partial" for view in views),
                       "retained": sum(view.status == "retained" for view in views),
                       "unknown_kind": sum(view.kind == "unknown" for view in views)},
        "asset_count": len(result.parse_result.assets), "inference_calls": inference.calls,
        "warning_codes": sorted({warning.code for warning in result.warnings}),
        "finalization": {key: value for key, value in result._final_text_evidence.items()
                         if key not in {"assembly_markdown", "edits"}},
    }
    write_json(directory / "outcome.json", outcome)
    return outcome


async def worker(plan_path: Path, phase: str) -> None:
    from .runtime import actual_worker_limits, package_versions
    plan = read_json(plan_path)
    output = plan_path.parent
    write_json(output / f"{phase}-environment.json", {
        "limits": actual_worker_limits(),
        "versions": package_versions(["docvortex", "PyMuPDF", "Pillow", "docling-core", "markdown-it-py"]),
        "network": "none", "gpu_devices": [], "started_at": now(),
    })
    if phase == "measured":
        # Each CPU process warms itself. The engineering preflight process is
        # separate and cannot warm imports or caches of this measured worker.
        for declared in plan["cases"]:
            if declared["phase"] != "warmup":
                continue
            warmup = {**declared, "case_id": "measured-warmup-" + declared["case_id"],
                      "job_id": "warmup_" + declared["job_id"]}
            outcome = await execute_case(plan, warmup, output)
            print(json.dumps({"phase": "measured_process_warmup", "case_id": warmup["case_id"],
                              "seconds": outcome["timing"]["postprocessing_seconds"]}), flush=True)
    for case in plan["cases"]:
        if (case["phase"] == "warmup") != (phase == "warmup"):
            continue
        try:
            outcome = await execute_case(plan, case, output)
        except BaseException as exc:
            write_json(output / f"{phase}-failure.json", {
                "case_id": case["case_id"], "error_type": type(exc).__name__, "message": str(exc),
                "state": "engineering_failure_unscored", "created_at": now(),
            })
            raise
        print(json.dumps({"case_id": case["case_id"], "status": outcome["status"],
                          "seconds": outcome["timing"]["postprocessing_seconds"]}), flush=True)


def score_run(run: Path) -> Path:
    from .adjudications import reference_exclusions
    from .cli import code_identity
    from .scoring import score_case
    from .service_artifacts import rebuild_final_result
    from .service_observation import build_service_observation, read_final_observation
    record = read_json(run / "run.json")
    if record["state"] != "completed":
        raise ValueError("complete all declared replay work before scoring")
    identity = code_identity()
    scoring_freeze = read_json(run / "scoring-freeze.json")
    paired_native_rescore = scoring_freeze.get("paired_native_rescore") is True
    require_shared_scoring(record, identity, paired_native_rescore=paired_native_rescore)
    if (scoring_freeze.get("software_id") != identity["software_id"]
            or scoring_freeze.get("validation", {}).get("status") != "passed"
            or scoring_freeze.get("execution_software_id") != record["software"]["software_id"]):
        raise ValueError("analysis software differs from the validated scoring freeze")
    dataset = Path(record["dataset"])
    manifest = read_json(dataset / "manifest.json")
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    destination_name = "scores-" + identity["software_id"][:12]
    destination = run / destination_name
    destination.mkdir(exist_ok=False)
    index: dict[str, Any] = {
        "schema": "moparse-service-scores/1", "score_id": run.name + "-paired-" + identity["software_id"][:12],
        "software": identity, "execution_software": record["software"],
        "scoring_protocol": record["scoring_protocol"],
        "reference_freeze": record["reference_freeze"], "created_at": now(), "results": [],
    }
    baseline_run = Path(record["baseline_run"])
    native_index = read_json(baseline_run / "artifacts" / "scores" / record["baseline_score_id"] / "index.json")
    native_observations = {item["source_observation"]: item["observation"]
                           for item in native_index["native_readback"]["observations"]}
    quality_cases = [case for case in record["cases"]
                     if case["phase"] == "measured" and case["suite"] == "quality800"]
    contexts: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for ordinal, case in enumerate(quality_cases, 1):
        sample = samples[case["sample_id"]]
        reference = read_json(inside(dataset, sample["evaluation"]))
        raw_observation = read_json(inside(run, case["observation"]))
        readback_started = time.perf_counter()
        candidate_dir = inside(run, case["observation"]).parent
        preserved = rebuild_final_result(
            (candidate_dir / "final.md").read_text(), read_json(candidate_dir / "final.json"),
            read_json(candidate_dir / "service-evidence.json"), raw_observation)
        metadata = {key: raw_observation[key] for key in (
            "run_id", "suite", "phase", "repetition", "timing", "resources", "runtime",
        ) if key in raw_observation}
        rebuilt = build_service_observation(preserved, sample_id=case["sample_id"], metadata=metadata,
                                             pipeline=f"{record['native_pipeline']['pipeline']}+MO-Parse")
        rebuilt["input_page_count"] = case["input_pages"]
        rebuilt["dataset"] = record["dataset_name"]
        observation, readback = read_final_observation(rebuilt)
        readback["analysis_seconds"] = time.perf_counter() - readback_started
        readback["timing_scope"] = "scoring_analysis_only_not_service_processing"
        observation_path = f"{destination_name}/observations/{case['sample_id']}.json"
        write_json(run / observation_path, observation)
        write_json(run / f"{destination_name}/observations/{case['sample_id']}.readback.json", readback)
        reference = {**reference, **{key: observation.get(key) for key in (
            "suite", "phase", "repetition", "input_page_count", "dataset", "run_id",
        )}}
        native_path = Path(record["baseline_run"]) / case["baseline_score_source"]
        baseline = read_json(native_path)
        for key in ("document_id", "family_id", "tags", "source_category", "development_exposure"):
            reference.setdefault(key, baseline.get(key))
        human = record.get("reference_adjudications")
        final = score_case(reference, observation, dataset,
                           reference_exclusions=reference_exclusions(human, case["sample_id"])
                           if human else None)
        native_relative = f"{destination_name}/native/{case['sample_id']}.json"
        final_relative = f"{destination_name}/final/{case['sample_id']}.json"
        (run / native_relative).parent.mkdir(parents=True, exist_ok=True)
        if paired_native_rescore:
            native_observation = read_json(inside(baseline_run, native_observations[case["baseline_observation_source"]]))
            native_reference = {**reference, **{key: native_observation.get(key) for key in (
                "suite", "phase", "repetition", "input_page_count", "dataset", "run_id",
            )}}
            native_scored = score_case(native_reference, native_observation, dataset,
                                       reference_exclusions=reference_exclusions(human, case["sample_id"])
                                       if human else None)
            write_json(run / native_relative, native_scored)
        else:
            shutil.copyfile(native_path, run / native_relative)
        write_json(run / final_relative, final)
        entry: dict[str, Any] = {
            "case_id": case["case_id"], "sample_id": case["sample_id"], "suite": case["suite"],
            "phase": case["phase"], "repetition": case["repetition"],
            "baseline_score": native_relative, "final_score": final_relative,
            "final_observation": observation_path, "stage_scores": [],
        }
        if record.get("previous_outputs"):
            previous_root = Path(record["previous_outputs"]["run"])
            previous_path = inside(previous_root, case["previous_observation"])
            previous_raw = read_json(previous_path)
            previous_dir = previous_path.parent
            previous_result = rebuild_final_result(
                (previous_dir / "final.md").read_text(), read_json(previous_dir / "final.json"),
                read_json(previous_dir / "service-evidence.json"), previous_raw)
            previous_observation = build_service_observation(previous_result, sample_id=case["sample_id"],
                metadata=metadata, pipeline=f"{record['native_pipeline']['pipeline']}+MO-Parse:previous")
            previous_observation.update(input_page_count=case["input_pages"], dataset=record["dataset_name"])
            previous_observation, previous_readback = read_final_observation(previous_observation)
            previous_score = score_case(reference, previous_observation, dataset,
                reference_exclusions=reference_exclusions(human, case["sample_id"]) if human else None)
            entry["previous_score"] = f"{destination_name}/previous/{case['sample_id']}.json"
            entry["previous_observation"] = f"{destination_name}/previous-observations/{case['sample_id']}.json"
            write_json(run / entry["previous_score"], previous_score)
            write_json(run / entry["previous_observation"], previous_observation)
            write_json(run / f"{destination_name}/previous-observations/{case['sample_id']}.readback.json", previous_readback)
        index["results"].append(entry)
        contexts.append((case, reference, entry))
        print(json.dumps({"score_phase": "primary", "completed_samples": ordinal,
                          "declared_samples": len(quality_cases)}), flush=True)
    write_json(destination / "primary-index.json", {
        **index, "state": "primary_complete_stages_pending",
    })
    for ordinal, (case, reference, entry) in enumerate(contexts, 1):
        stage_scores = entry["stage_scores"]
        human = record.get("reference_adjudications")
        for stage in case.get("stage_outputs", []):
            name = stage["stage"]
            if name == "final":
                stage_scores.append({"stage": name, "scope": stage["scope"], "score": entry["final_score"],
                                     "observation": entry["final_observation"]})
                continue
            stage_started = time.perf_counter()
            stage_observation, stage_readback = read_final_observation(
                read_json(inside(run, stage["observation"]))
            )
            stage_reference = {**reference, **{key: stage_observation.get(key) for key in (
                "suite", "phase", "repetition", "input_page_count", "dataset", "run_id",
            )}}
            stage_scored = score_case(
                stage_reference, stage_observation, dataset,
                reference_exclusions=reference_exclusions(human, case["sample_id"]) if human else None,
            )
            stage_relative = f"{destination_name}/stages/{name}/{case['sample_id']}.json"
            write_json(run / stage_relative, stage_scored)
            stage_readback["analysis_seconds"] = time.perf_counter() - stage_started
            stage_readback["timing_scope"] = "stage_scoring_analysis_only_not_service_processing"
            write_json(run / f"{destination_name}/stages/{name}/{case['sample_id']}.readback.json", stage_readback)
            stage_scores.append({"stage": name, "scope": stage["scope"], "score": stage_relative,
                                 "observation": stage["observation"]})
        print(json.dumps({"score_phase": "stages", "completed_samples": ordinal,
                          "declared_samples": len(quality_cases)}), flush=True)
    if code_identity()["software_id"] != identity["software_id"]:
        raise ValueError("software changed during scoring")
    index["state"] = "completed"
    write_json(destination / "index.json", index)
    record["latest_scores"] = record["score_index"] = f"{destination_name}/index.json"
    record["scoring_status"] = "completed"
    record["scoring_software_id"] = identity["software_id"]
    write_json(run / "run.json", record)
    return destination / "index.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--baseline", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--service-config", required=True, type=Path)
    prepare.add_argument("--pipeline", choices=["P07", "P08"], default="P07")
    prepare.add_argument("--previous-run", type=Path)
    execute = commands.add_parser("run")
    execute.add_argument("--run", required=True, type=Path)
    execute.add_argument("--phase", choices=["warmup", "measured"], required=True)
    for name in ("freeze", "freeze-scoring"):
        freeze = commands.add_parser(name)
        freeze.add_argument("--run", required=True, type=Path)
        freeze.add_argument("--validation", required=True, type=Path)
    for name in ("score", "report"):
        subparser = commands.add_parser(name)
        subparser.add_argument("--run", required=True, type=Path)
    candidate = commands.add_parser("worker")
    candidate.add_argument("--plan", required=True, type=Path)
    candidate.add_argument("--phase", required=True, choices=["warmup", "measured"])
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare_run(args.baseline, args.output, args.service_config, pipeline=args.pipeline,
                          previous_run=args.previous_run))
    elif args.command == "run":
        return launch(args.run, args.phase)
    elif args.command == "freeze":
        freeze_run(args.run, args.validation)
    elif args.command == "freeze-scoring":
        freeze_scoring(args.run, args.validation)
    elif args.command == "worker":
        asyncio.run(worker(args.plan, args.phase))
    elif args.command == "score":
        print(score_run(args.run))
    elif args.command == "report":
        from .service_report import render_service_report
        print(render_service_report(args.run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
