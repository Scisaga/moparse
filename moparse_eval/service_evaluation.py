"""Isolated CPU service replay over saved P01-P08 results.

The isolated worker receives input PDFs and native candidates, never expected
materials. PDF access here is candidate service processing, not corpus review.
Only the separate scoring command reads frozen evaluation references.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import subprocess
import tempfile
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from .packaging import inside, read_json, write_json
from .service_native_adapters import PIPELINE_BRANCHES

ROOT = Path(__file__).resolve().parent.parent
WORKER_CASE_FIELDS = (
    "case_id", "sample_id", "suite", "phase", "repetition", "input_pages", "input", "native", "job_id",
)
CAPTURE_STAGES = ("adapted", "source_pages", "native_pages", "exported", "assets", "semantic", "final")


class NoInference:
    """The CPU replay has no model transport, including optional asset OCR."""

    def __init__(self) -> None:
        self.calls = 0

    async def recognize_image(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise RuntimeError("model inference is forbidden in service replay")

    async def parse(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise RuntimeError("parser execution is forbidden in service replay")


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def prepare_run(baseline: Path, destination: Path, service_config: Path, *, pipeline: str = "P07", validation: Path | None = None,
                ) -> Path:
    """Use declared execution identities; do not validate dataset contents."""
    from .cli import code_identity, snapshot_software

    if pipeline not in PIPELINE_BRANCHES:
        raise ValueError("service comparison requires P01-P08")
    baseline = baseline.resolve()
    session = read_json(baseline / "run.json")
    identity = code_identity()
    checks = read_json(validation) if validation is not None else None
    if checks is not None:
        _require_expected_gate(checks, identity["software_id"])
    dataset = Path(session["dataset"]).resolve()
    manifest = read_json(dataset / "manifest.json")
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    cases = []
    for ordinal, case in enumerate(c for c in session["cases"] if c["pipeline"] == pipeline):
        observation = read_json(inside(baseline, case["observation"]))
        sample = samples[case["sample_id"]]
        native_relative = Path(case["observation"]).relative_to(f"artifacts/{pipeline}").with_name("native.json")
        case_id = f"{case['suite']}-r{case['repetition']}-{case['sample_id']}"
        cases.append({
            "case_id": case_id, "sample_id": case["sample_id"], "suite": case["suite"],
            "phase": case["phase"], "repetition": case["repetition"],
            "input_pages": observation["input_page_count"],
            "input": str(Path(sample["input"]).relative_to("inputs")),
            "native": native_relative.as_posix(),
            "baseline_observation_source": case["observation"],
            "job_id": f"service_{ordinal:04d}",
            **{key: copy.deepcopy(sample.get(key)) for key in (
                "document_id", "family_id", "tags", "development_exposure", "source_category",
            )},
        })
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    configuration = read_json(service_config)
    configuration["diagnostic_capture_stages"] = list(CAPTURE_STAGES)
    runtime = read_json(ROOT / "benchmark/execution-lock.json")["pipelines"][pipeline]["runtime"]
    native_configuration = next(item for item in session["configurations"] if item["pipeline"] == pipeline)
    record = {
        "schema": "moparse-service-evaluation/1", "run_id": destination.name,
        "report_version": "service-paired-v1", "state": "prepared", "created_at": now(),
        "baseline_run": str(baseline), "dataset": str(dataset),
        "dataset_name": manifest.get("name"), "reference_freeze": manifest.get("freeze_record"),
        "reference_policy": "canonical_expected_only_no_adjudications",
        "software": identity,
        "native_pipeline": {**{key: copy.deepcopy(native_configuration.get(key)) for key in (
            "pipeline", "revisions", "native_view_policy", "source_policy", "inference_services",
        )}, "versions": copy.deepcopy(native_configuration.get("versions", {}))},
        "source_capability_policy": {"scope": "actual_saved_page_branch", "native_branches": ["docling", "mineru"],
                                     "visual_branches": ["glm", "paddle", "visual"], "reference_access": False},
        "service_config": configuration, "options": {"describe_images": False, "scan_policy": "auto"},
        "execution_environment": {
            "image": runtime["image"], "cpus": 8, "memory_bytes": 8 * 1024 ** 3,
            "network": "none", "gpu_devices": [], "outer_concurrency": 1,
            "deployment_status": "not_deployed", "tts_actions": [],
        },
        "measurement_notes": [
            f"Saved valid {pipeline} native candidates are replayed; no model inference is repeated.",
            "Every visual page branch rejects PDF text and vector supplementation, including mixed pipelines.",
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
        **({"validation": copy.deepcopy(checks)} if checks is not None else {}),
    }
    write_json(destination / "run.json", record)
    snapshot_software(destination / "software", identity)
    write_json(destination / "candidate" / "worker-plan.json", {
        "run_id": record["run_id"], "dataset_name": record["dataset_name"],
        "software_id": identity["software_id"],
        "pipeline": pipeline,
        "service_config": configuration, "options": record["options"],
        "cases": [{key: case[key] for key in WORKER_CASE_FIELDS}
                  for case in cases],
        **({"expected_structure_gate": copy.deepcopy(checks["expected_structure_gate"])} if checks is not None else {}),
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
    if phase == "warmup" and record.get("state") != "prepared":
        raise ValueError("warmup requires a new prepared execution; completed artifacts are immutable")
    if phase == "measured" and record.get("state") != "frozen":
        raise ValueError("freeze the new service implementation after successful preflight first")
    _require_expected_gate(record.get("validation", {}), record.get("software", {}).get("software_id", ""))
    from .cli import code_identity
    if code_identity()["software_id"] != record["software"]["software_id"]:
        raise ValueError("service implementation changed after preparation or freeze")
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
        for key in ("observation", "final_markdown", "final_json", "edit_ledger", "service_evidence"):
            if key in case:
                case[key] = "candidate/" + case[key]
        for stage in case.get("stage_outputs", []):
            for key in ("observation", "markdown", "audit"):
                if key not in stage:
                    continue
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
    _require_expected_gate(checks, identity["software_id"])
    if identity["software_id"] != record["software"]["software_id"]:
        raise ValueError("code changed after preflight; prepare and preflight the current implementation")
    record.update(state="frozen", frozen_at=now(), validation=checks)
    write_json(run / "execution-freeze.json", {
        "software": identity, "options": record["options"], "service_config": record["service_config"],
        "environment": record["execution_environment"], "validation": checks,
        "frozen_at": record["frozen_at"],
    })
    plan_path = run / "candidate/worker-plan.json"
    plan = read_json(plan_path)
    plan["expected_structure_gate"] = copy.deepcopy(checks["expected_structure_gate"])
    write_json(plan_path, plan)
    write_json(run / "run.json", record)


def _require_expected_gate(validation: dict[str, Any], software_id: str) -> None:
    gate = validation.get("expected_structure_gate", {})
    if not isinstance(software_id, str) or not software_id.strip() or gate.get("status") != "passed" or gate.get("software_id") != software_id:
        raise ValueError("the current expected structure gate must pass before service execution")


def activate_executions(runs: list[Path], pointer: Path, validation: Path) -> None:
    """Atomically select all eight immutable new executions, without moving outputs."""
    from .cli import code_identity
    identity = code_identity()
    checks = read_json(validation)
    if checks.get("status") != "passed":
        raise ValueError("activation requires passed execution validation")
    _require_expected_gate(checks, identity["software_id"])
    selected, roots, sample_sets = {}, set(), set()
    for path in runs:
        path = path.resolve()
        record = read_json(path / "run.json")
        pipeline = record.get("native_pipeline", {}).get("pipeline")
        if pipeline not in PIPELINE_BRANCHES or pipeline in selected:
            raise ValueError("activation requires one distinct execution for every pipeline")
        if record.get("state") != "completed" or record.get("software", {}).get("software_id") != identity["software_id"]:
            raise ValueError("activation requires completed executions from the current software")
        _require_expected_gate(record.get("validation", {}), identity["software_id"])
        quality = [case for case in record["cases"] if case.get("suite") == "quality800" and case.get("phase") == "measured"]
        ids = [case["sample_id"] for case in quality]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("activation requires distinct declared quality samples")
        if any(not inside(path, case["final_markdown"]).is_file() for case in quality):
            raise ValueError("a completed execution lacks an actual delivered Markdown")
        sample_sets.add(tuple(sorted(ids)))
        roots.add(path.parent)
        selected[pipeline] = {"run": str(path), "software_id": identity["software_id"]}
    if set(selected) != set(PIPELINE_BRANCHES) or len(roots) != 1 or len(sample_sets) != 1:
        raise ValueError("activate all eight pipelines from one execution with identical quality scope")
    record = {"schema": "moparse-service-current-selection/1", "state": "active", "created_at": now(),
              "software_id": identity["software_id"], "execution": str(next(iter(roots))),
              "pipelines": selected, "validation": checks}
    pointer = pointer.resolve()
    if pointer.name != "index.json" or pointer.parent.name != "current":
        raise ValueError("activation may replace only the current/index.json selection")
    if any(pointer.is_relative_to(path.resolve()) for path in runs):
        raise ValueError("current selection must be outside immutable executions")
    pointer.parent.mkdir(parents=True, exist_ok=True)
    partial = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=pointer.parent,
                                         prefix=pointer.name + ".", suffix=".part", delete=False) as stream:
            partial = Path(stream.name)
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        partial.replace(pointer)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)


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
    from app.services.export_service import ExportService
    from app.services.final_content_service import FinalContentService
    from app.services.ir_service import DocumentIRService
    from app.services.multimodal_service import MultimodalService
    from app.services.parser_service import ParserService
    from app.services.quality_service import QualityService
    from app.services.storage_service import StorageService
    from app.services.table_semantics_service import TableSemanticsService
    from app.utils.deadline import attach_deadline

    from .runtime import MemoryObservation
    from .service_observation import build_service_observation
    from .service_replay_native import replay_native
    from .service_source_policy import apply_source_stages
    from .service_stages import capture_stage, materialize_stage, stage_edit_ledger

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
    applicability: dict[str, Any] = {}

    def capture(name: str, *, pages_only: bool = False) -> None:
        nonlocal diagnostic_capture_seconds
        selected = plan["service_config"].get("diagnostic_capture_stages")
        if selected is not None and name not in selected:
            return
        capture_started = time.perf_counter()
        snapshots.append(capture_stage(result, stage=name, sample_id=case["sample_id"], pages_only=pages_only,
                                       pipeline=pipeline, applicability=applicability.get(name)))
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
        bridge["native_input"] = case["native"]
        result._source_verification["saved_native_bridge"]["native_input"] = case["native"]
        try:
            require_replay_ready(bridge)
        except RuntimeError:
            write_json(directory / "replay-diagnostics.json", bridge)
            raise
        stages["native_bridge_seconds"] = time.perf_counter() - stage_start
        capture("adapted", pages_only=True)
        # Calling these exact service stages avoids parser initialization or a
        # second model request. No replacement postprocessor is implemented.
        def observe_source_stage(name, detail):
            applicability[name] = detail
            capture(name, pages_only=True)
        evidence, source_timings, source_applicability = await apply_source_stages(
            result, bridge, source, options, settings, on_stage=observe_source_stage)
        stages.update(source_timings)
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
        applicability["semantic"] = {"applicable": bool(settings.semantic_table_output_enabled),
                                     "reason": "configured_semantic_table_service" if settings.semantic_table_output_enabled else "disabled_by_configuration"}
        stages["semantics_seconds"] = time.perf_counter() - stage_start
        capture("semantic")
        stage_start = time.perf_counter()
        FinalContentService().apply(result)
        stages["final_content_seconds"] = time.perf_counter() - stage_start
        capture("final")
        elapsed = time.perf_counter() - started
        if inference.calls:
            raise RuntimeError("unexpected model request: service replay is invalid")
    result.usage.duration_ms = round(elapsed * 1000)
    result.parse_result.runtime.duration_ms = result.usage.duration_ms
    ledger_started = time.perf_counter()
    edit_ledger = stage_edit_ledger(snapshots)
    edit_ledger_seconds = time.perf_counter() - ledger_started
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
    write_json(directory / "stage-edit-ledger.json", {"entries": edit_ledger, "judgment": "unjudged_actual_stage_edits"})
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
        audit_path = directory / "stages" / f"{name}.audit.json"
        write_json(audit_path, snapshot["source_audit"])
        stage_outputs.append({
            "stage": name, "scope": snapshot["scope"],
            "markdown": str(markdown_path.relative_to(output)),
            "observation": str(observation_path.relative_to(output)),
            "audit": str(audit_path.relative_to(output)), "applicability": snapshot["applicability"],
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
        "service_evidence": str((directory / "service-evidence.json").relative_to(output)),
        "timing": {"postprocessing_seconds": elapsed, "native_json_load_seconds": load_seconds,
                   "pure_persistence_and_observation_seconds": time.perf_counter() - persist_start,
                   "diagnostic_capture_seconds": diagnostic_capture_seconds, **stages},
        "stage_outputs": stage_outputs,
        "stage_applicability": source_applicability,
        "edit_ledger": str((directory / "stage-edit-ledger.json").relative_to(output)),
        "diagnostic_edit_ledger_seconds": edit_ledger_seconds,
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
    _require_expected_gate({"expected_structure_gate": plan.get("expected_structure_gate", {})}, plan.get("software_id", ""))
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--baseline", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--service-config", required=True, type=Path)
    prepare.add_argument("--pipeline", choices=list(PIPELINE_BRANCHES), default="P07")
    prepare.add_argument("--validation", type=Path, help="attach a passed current-source expected structure gate without executing")
    execute = commands.add_parser("run")
    execute.add_argument("--run", required=True, type=Path)
    execute.add_argument("--phase", choices=["warmup", "measured"], required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--run", required=True, type=Path)
    freeze.add_argument("--validation", required=True, type=Path)
    activate = commands.add_parser("activate")
    activate.add_argument("--run", required=True, type=Path, action="append")
    activate.add_argument("--pointer", required=True, type=Path)
    activate.add_argument("--validation", required=True, type=Path)
    candidate = commands.add_parser("worker")
    candidate.add_argument("--plan", required=True, type=Path)
    candidate.add_argument("--phase", required=True, choices=["warmup", "measured"])
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare_run(args.baseline, args.output, args.service_config, pipeline=args.pipeline, validation=args.validation))
    elif args.command == "run":
        return launch(args.run, args.phase)
    elif args.command == "freeze":
        freeze_run(args.run, args.validation)
    elif args.command == "activate":
        activate_executions(args.run, args.pointer, args.validation)
    elif args.command == "worker":
        asyncio.run(worker(args.plan, args.phase))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
