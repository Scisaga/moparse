"""One shared three-layer evaluation of already saved outputs.

Only expected text, declared selections, native objects, actual Markdown and
original observations are read. Diagnostic traversal is explicitly unpublished;
software blockers never become zero-valued candidate quality measurements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import tempfile
import time
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from functools import wraps
from pathlib import Path
from typing import Any

from .candidate_delivery import final_delivery, native_delivery
from .expected_readback import markdown_observation, read_expected
from .expected_scoring import PROTOCOL, grade_expected
from .layer_aggregation import LAYERS
from .native_readback import READBACK_VERSION, read_native_relations
from .packaging import inside, read_json, write_json
from .saved_native import read_saved_native
from .trace_storage import read_score, share_evidence

PIPELINES = tuple(f"P{i:02}" for i in range(1, 9))
ROOT = Path(__file__).resolve().parent.parent


def _record_failure(function):
    @wraps(function)
    def wrapped(baseline, output, **kwargs):
        output = Path(output)
        owned = not output.exists()
        try:
            return function(baseline, output, **kwargs)
        except BaseException as error:
            status = output / "execution-status.json"
            if owned and status.is_file():
                record = read_json(status)
                record.update(state="failed", expected_comparison_complete=False,
                              error={"type": type(error).__name__, "message": str(error)})
                for key in ("summary", "paired", "adoption"):
                    record.pop(key, None)
                write_json(status, record)
                write_json(output / "index.json", record)
            raise
    return wrapped


def native_observation(run: Path, case: dict[str, Any], *, analysis: Path | None = None,
                       software_id: str | None = None) -> dict[str, Any]:
    source = inside(run, case["observation"])
    if not source.is_file():
        return {"sample_id": case["sample_id"], "pipeline": case["pipeline"], "status": "failed",
                "pages": [], "relations": [], "candidate_source": str(source),
                "errors": [{"reason": "declared_candidate_not_produced"}]}
    observation = read_json(source)
    native_path = source.with_name("native.json")
    started = time.perf_counter()
    try:
        native = read_json(native_path) if native_path.is_file() else None
        if native is not None:
            observation = read_saved_native(native, observation)
        observation, diagnostic = read_native_relations(observation, native)
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise ValueError("native reader failed; repair readback before grading") from error
    if diagnostic.get("status") == "readback_error":
        raise ValueError("native readback must be repaired before expected grading")
    observation["candidate_source"] = str(source)
    observation["asset_delivery"] = native_delivery(source, observation)
    if analysis is not None:
        relative = Path("observations") / case["pipeline"] / "quality800-r1" / (case["sample_id"] + ".json")
        provenance = {"reader_version": READBACK_VERSION, "software_id": software_id,
                      "source_observation": str(source.relative_to(run)), "source_native": str(native_path.relative_to(run)),
                      "native_status": diagnostic["status"], "observation": relative.as_posix(),
                      "diagnostics": str(relative.with_suffix(".readback.json")),
                      "readback_seconds": time.perf_counter() - started,
                      "timing_scope": "analysis_only_not_original_processing"}
        observation["scoring_readback"] = provenance
        write_json(analysis / relative, observation)
        write_json(analysis / relative.with_suffix(".readback.json"), {**diagnostic, **provenance})
    return observation


def quality_cases(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [case for case in run["cases"] if case["phase"] == "measured" and case["suite"] == "quality800"]


def _service_inputs(root: Path, pipeline: str, *, current: bool = False) -> tuple[Path, dict[str, Any]]:
    if current:
        pointer = root if root.is_file() else root / "index.json"
        index = read_json(pointer)
        if index.get("state") != "active" or set(index.get("pipelines", {})) != set(PIPELINES):
            raise ValueError("current delivery must atomically select all eight pipelines")
        selected = index["pipelines"][pipeline]
        directory = Path(selected["run"]).resolve()
        if selected.get("software_id") != index.get("software_id"):
            raise ValueError("current delivery index mixes execution software")
    else:
        directory = root / pipeline.lower()
    run = read_json(directory / "run.json")
    if run.get("state") != "completed":
        raise ValueError("finish candidate processing before evaluating its saved output")
    if current and run.get("software", {}).get("software_id") != selected["software_id"]:
        raise ValueError("current delivery run differs from its activated software")
    return directory, run


def _frozen_requirements(path: Path, sample_ids: set[str], software_id: str,
                         validation: dict[str, Any], *,
                         expected_by_sample: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Require the separate source-interpretation gate before any candidates."""
    from .requirement_gate import validate_expected_structure_gate
    from .requirement_graph import (
        evaluation_projection,
        validate_requirement_graph,
    )

    gate = validation.get("expected_structure_gate", {})
    index = validate_expected_structure_gate(validation, software_id, scope=sample_ids,
                                             expected_by_sample=expected_by_sample)
    if Path(gate["requirement_index"]["path"]).resolve() != path.resolve():
        raise ValueError("expected structure gate must bind the actual requested requirement index")
    if set(expected_by_sample) != sample_ids:
        raise ValueError("formal requirement loading needs every authorized read-only expected selection")
    records = {row["sample_id"]: row for row in index["records"]}
    if len(records) != len(index["records"]) or set(records) != sample_ids:
        raise ValueError("expected requirement model must retain the complete declared sample scope")
    result = {}
    for sample_id, row in records.items():
        if row.get("semantic_complete") is not True or not row.get("json"):
            raise ValueError("resolve every semantic requirement before full comparison")
        graph = read_json(inside(path.parent, row["json"]))
        validate_requirement_graph(graph, expected=expected_by_sample[sample_id])
        result[sample_id] = evaluation_projection(graph)
    return result


def final_observation(source: Path, *, sample_id: str, pipeline: str, pages: list[int],
                      metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if source.is_file():
        markdown = source.read_text(encoding="utf-8")
        observation = markdown_observation(markdown, sample_id=sample_id,
                                           pipeline=pipeline, pages=pages)
        observation["asset_delivery"] = final_delivery(source, markdown, metadata or {})
    else:
        observation = {"sample_id": sample_id, "pipeline": pipeline, "status": "failed",
                       "pages": [], "relations": [], "errors": [{"reason": "final_markdown_not_produced"}]}
    for key in ("timing", "resources"):
        observation[key] = (metadata or {}).get(key, {})
    return observation


def execution_costs(baseline: Path, session: dict[str, Any], service: dict[str, Any]) -> dict[str, Any]:
    """Copy recorded timing/resource evidence, never rerun a parser or infer cost."""
    from .reporting import native_performance, postprocessing_performance

    native: dict[str, list[dict[str, Any]]] = {pipeline: [] for pipeline in PIPELINES}
    for case in session["cases"]:
        source = inside(baseline, case["observation"])
        observation = read_json(source) if source.is_file() else {"status": "failed"}
        native[case["pipeline"]].append({**observation, **case})
    result: dict[str, Any] = {"native": {}, "final": {},
              "historical_native_conditions": session.get("measurement_conditions"),
              "policy": "recorded_native_and_postprocessing_costs_separate_no_new_end_to_end_sum"}
    for pipeline, cases in native.items():
        result["native"][pipeline] = {
            suite: native_performance([c for c in cases if c["suite"] == suite or c["phase"] != "measured"])
            for suite in ("quality800", "perf80")}
    for key, (_directory, _declared, run) in service.items():
        result["final"][key] = {
            "run": str(_directory.resolve()),
            "software_id": run["software"]["software_id"], "execution_environment": run.get("execution_environment"),
            "measurement_notes": run.get("measurement_notes"),
            "quality800": postprocessing_performance(run["cases"], "quality800"),
            "perf80": postprocessing_performance(run["cases"], "perf80"),
            "warmup": [{k: case.get(k) for k in ("case_id", "sample_id", "input_pages", "timing", "resources", "status")}
                       for case in run["cases"] if case["phase"] == "warmup"]}
    return result


def _blocked_score(expected: dict[str, Any], group: str, blocker: dict[str, Any]) -> dict[str, Any]:
    """Represent a software failure without manufacturing any quality result."""
    return {
        "sample_id": expected["sample_id"], "document_id": expected.get("document_id"),
        "family_id": expected.get("family_id"), "pipeline": group, "protocol": PROTOCOL,
        "publishable": False, "blockers": [blocker], "outcomes": [], "score": None,
        "layers": {layer: {"numerator": None, "denominator": None, "score": None, "complete": False}
                   for layer in LAYERS},
        "status": "software_failure",
    }


def _write_compact_score(destination: Path, score: dict[str, Any]) -> None:
    """Stream a complete trace before atomically replacing its destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=destination.name + ".", suffix=".part", delete=False) as stream:
            partial = Path(stream.name)
            json.dump(share_evidence(score), stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
        partial.replace(destination)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)


def _grade_saved_group(task: dict[str, Any]) -> dict[str, Any]:
    """Read and diagnose one saved output, inside an analysis-only CPU process."""
    group, sample_id, expected = task["group"], task["sample_id"], task["expected"]
    directory, case, output = task["directory"], task["case"], task["output"]
    source = inside(directory, case["observation"])
    observation: dict[str, Any] = {}
    try:
        if group in PIPELINES:
            observation = native_observation(directory, case, analysis=output / "private", software_id=task["software_id"])
            source = Path(observation["candidate_source"])
        else:
            relative = case.get("final_markdown") or str(Path(case["observation"]).with_name("final.md"))
            source = inside(directory, relative)
            observation = final_observation(source, sample_id=sample_id, pipeline=case["pipeline"],
                pages=list(range(1, len(expected["source_pages"]) + 1)), metadata=case)
        if expected.get("reader_blocker"):
            score = _blocked_score(expected, group, expected["reader_blocker"])
        else:
            score = grade_expected(expected, observation)
    except (ValueError, IndexError, KeyError, TypeError, AttributeError, RuntimeError, OSError) as error:
        score = _blocked_score(expected, group, {
            "side": "software", "reason": "saved_reader_or_grader_failure",
            "source": {"path": str(source)},
            "error": {"type": type(error).__name__, "message": str(error)},
        })
    score.update(scoring_software_id=task["software_id"], candidate_source=str(source))
    if task.get("execution_id"):
        score["execution_software_id"] = task["execution_id"]
    if (task.get("diagnostic") or score.get("blockers") or score.get("publishable") is not True
            or any(layer.get("complete") is not True for layer in score["layers"].values())):
        score.update(diagnostic_only=bool(task.get("diagnostic")), quality_scores_withheld=True, score=None)
        for layer in score["layers"].values():
            layer["score"], layer["numerator"] = None, None
            layer.pop("diagnostic_score", None)
    relative = f"private/scores/{group}/quality800-r1/{sample_id}.json"
    # Complete traces repeat explicit source evidence; formatting them as
    # indented JSON multiplies analysis storage without adding information.
    destination = output / relative
    _write_compact_score(destination, score)
    return {"group": group, "sample_id": sample_id, "path": relative,
            "readback": observation.get("scoring_readback")}


def _grade_tasks(tasks: list[dict[str, Any]], workers: int):
    pending_by_sample: dict[str, deque[dict[str, Any]]] = {}
    for task in tasks:
        pending_by_sample.setdefault(task["sample_id"], deque()).append(task)
    ready = deque(pending_by_sample)
    if workers == 1:
        while ready:
            sample = ready.popleft()
            record = _grade_saved_group(pending_by_sample[sample].popleft())
            if pending_by_sample[sample]:
                ready.append(sample)
            yield record
        return
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as executor:
        futures = {}
        try:
            while ready or futures:
                while ready and len(futures) < workers:
                    sample = ready.popleft()
                    future = executor.submit(_grade_saved_group, pending_by_sample[sample].popleft())
                    futures[future] = sample
                done, _pending = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    sample = futures.pop(future)
                    record = future.result()
                    if pending_by_sample[sample]:
                        ready.append(sample)
                    yield record
        except BaseException:
            for future in futures:
                future.cancel()
            raise


def _target_fingerprint(score: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for row in score["outcomes"]:
        for chunk in encoder.iterencode({key: row.get(key) for key in ("layer", "id", "role", "expected", "reference")}):
            digest.update(chunk.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _blocker_index(score: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = score.get("blockers", [])
    if (score.get("publishable") is not True or set(score.get("layers", {})) != set(LAYERS) or any(
            layer.get("complete") is not True for layer in score.get("layers", {}).values())) and not blockers:
        blockers = [{"side": "software", "reason": "incomplete_layer_judgments"}]
    return [{"group": record["group"], "sample_id": record["sample_id"],
             "reason": blocker.get("reason", "unspecified_software_failure"),
             "side": blocker.get("side", "software"), "source": blocker.get("source"),
             "detail_path": record["path"], "blocker_index": number}
            for number, blocker in enumerate(blockers)]


@_record_failure
def evaluate_saved(baseline: Path, output: Path, *, expected_root: Path,
                   freeze: Path | None = None, service_baseline_root: Path | None = None,
                   current_root: Path | None = None, workers: int = 16, diagnostic: bool = False,
                   sample_ids: list[str] | None = None, requirements: Path | None = None) -> Path:
    """Traverse all declared saved groups; publish only fully supported judgments.

    Diagnostic mode permits an explicitly declared strict subset without a
    scoring freeze and withholds all quality results. A full diagnostic still
    requires the same current validated freeze and canonical structure gate.
    Formal denominators always retain the entire original declaration.
    """
    if sample_ids is not None and not diagnostic:
        raise ValueError("sample selection is diagnostic-only; formal scoring must retain the full declared scope")
    if sample_ids is not None and (not isinstance(sample_ids, list) or not sample_ids
                                   or any(not isinstance(item, str) or not item for item in sample_ids)
                                   or len(set(sample_ids)) != len(sample_ids)):
        raise ValueError("diagnostic sample selection must declare nonempty distinct sample identities")
    from .cli import (
        _require_formal_measurement_conditions,
        code_identity,
        read_scoring_freeze,
        snapshot_software,
    )

    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("analysis workers must be between 1 and 16")
    if output.resolve().is_relative_to(expected_root.resolve()):
        raise ValueError("evaluation output must be outside the read-only expected directory")
    identity = code_identity()
    if diagnostic:
        frozen = None
    elif freeze is None:
        raise ValueError("formal scoring requires the validated four-stage scoring freeze")
    else:
        frozen = read_scoring_freeze(freeze, identity)
    baseline = baseline.resolve()
    session = read_json(baseline / "run.json")
    _require_formal_measurement_conditions(baseline, session)
    if session.get("state") not in {"completed", "failed"}:
        raise ValueError("saved native run must have completed execution and restoration")
    dataset = Path(session["dataset"]).resolve()
    if output.resolve().is_relative_to(dataset):
        raise ValueError("evaluation output must be outside the read-only dataset package")
    manifest = read_json(dataset / "manifest.json")
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    if len(samples) != len(manifest["samples"]):
        raise ValueError("duplicate declared sample identities")
    cases = quality_cases(session)
    by_pipeline = {pipeline: {case["sample_id"]: case for case in cases if case["pipeline"] == pipeline}
                   for pipeline in PIPELINES}
    if sum(len(items) for items in by_pipeline.values()) != len(cases):
        raise ValueError("duplicate or undeclared pipeline quality cases")
    full_sample_ids = set(by_pipeline[PIPELINES[0]])
    declared_samples = set(manifest.get("suites", {}).get("lite", samples))
    if full_sample_ids != declared_samples or not full_sample_ids <= samples.keys():
        raise ValueError("quality comparison must cover the entire declared Lite selection")
    if not full_sample_ids or any(set(by_pipeline[pipeline]) != full_sample_ids for pipeline in PIPELINES):
        raise ValueError("all eight pipelines must cover the same declared quality samples")
    selected_sample_ids = set(sample_ids) if sample_ids is not None else full_sample_ids
    if not selected_sample_ids <= full_sample_ids:
        raise ValueError("diagnostic sample selection contains an unknown declared sample: "
                         + ", ".join(sorted(selected_sample_ids - full_sample_ids)))
    frozen_requirements = None
    authorized_expected = {}
    if not diagnostic:
        cache = {}
        authorized_expected = {sample_id: read_expected(samples[sample_id], expected_root, cache=cache)
                               for sample_id in sorted(full_sample_ids)}
        frozen_requirements = _frozen_requirements(
            requirements or baseline / "requirements/current/index.json", full_sample_ids,
            identity["software_id"], frozen["validation"], expected_by_sample=authorized_expected)
    groups = list(PIPELINES)
    service = {}
    for label, root in (("baseline", service_baseline_root), ("current", current_root)):
        if root is None:
            continue
        for pipeline in (PIPELINES if label == "current" else ("P07", "P08")):
            directory, run = _service_inputs(root, pipeline, current=label == "current")
            if (Path(run["baseline_run"]).resolve() != baseline
                    or Path(run["dataset"]).resolve() != dataset
                    or run["native_pipeline"]["pipeline"] != pipeline):
                raise ValueError("final output must declare the same baseline, dataset and native pipeline")
            declared_cases = quality_cases(run)
            declared = {case["sample_id"]: case for case in declared_cases}
            if len(declared) != len(declared_cases) or set(declared) != full_sample_ids:
                raise ValueError("saved final outputs must cover the same quality samples without duplicates")
            for sample_id, case in declared.items():
                if case["baseline_observation_source"] != by_pipeline[pipeline][sample_id]["observation"]:
                    raise ValueError("paired final output does not declare the same saved native input")
            key = f"{pipeline}-{label}"
            service[key] = (directory, declared, run)
            groups.append(key)
    output.mkdir(parents=True, exist_ok=False)
    snapshot_software(output / "software", identity)
    if frozen is not None:
        write_json(output / "scoring-freeze.json", frozen)
    index: dict[str, Any] = {
        "state": "running", "protocol": PROTOCOL, "scoring_protocol": PROTOCOL,
        "score_id": output.name, "software": identity, "diagnostic_only": diagnostic,
        "purpose": "software_support_diagnosis_no_quality_results" if diagnostic else "formal_three_layer_evaluation",
        "reference_freeze": manifest.get("freeze_record"), "baseline": str(baseline),
        "expected_root": str(expected_root.resolve()), "dataset": str(dataset),
        "expected_comparison_complete": False, "records": [], "coverage": [], "groups": list(groups),
        "full_declared_samples": len(full_sample_ids),
        "diagnostic_selected_samples": sorted(selected_sample_ids) if diagnostic else None,
        "diagnostic_selection_requested": sample_ids is not None,
        "full_scope_traversed": False,
        "quality_suite": "quality800", "analysis_workers": workers,
        "analysis_scheduling": {
            "policy": "sample_round_robin", "max_active_tasks": workers, "max_active_tasks_per_sample": 1,
            "process_start_method": "spawn" if workers > 1 else "inline",
            "sample_order": "first_declared_task_occurrence", "group_order": "declared_task_order_within_sample",
            "completed_sample": "append_to_ready_queue_tail", "failure_policy": "fail_without_retry",
            "declared_tasks": len(selected_sample_ids) * len(groups),
        },
        "analysis_timing": "excluded_from_parser_and_postprocessing_costs",
        "validation": frozen["validation"] if frozen is not None else None,
        "native_readback": {"reader_version": READBACK_VERSION, "observations": []},
        "historical_adjudications": "not_read_or_applied", "blockers": [],
        "comparisons": {"native": list(PIPELINES), "native_to_final": {
            pipeline: f"{pipeline}-current" for pipeline in PIPELINES if f"{pipeline}-current" in groups}, "service_pairs": {
            pipeline: {label: f"{pipeline}-{label}" for label in ("baseline", "current")
                       if f"{pipeline}-{label}" in groups} for pipeline in ("P07", "P08")}},
        "development_exposure": "saved Lite outputs and expected syntax used during development; no held-out claim",
    }
    write_json(output / "execution-status.json", index)
    reference_cache = {}
    expected_by_sample = {}
    for sample_id in sorted(selected_sample_ids):
        try:
            expected = (authorized_expected[sample_id] if frozen_requirements is not None
                        else read_expected(samples[sample_id], expected_root, cache=reference_cache))
            if diagnostic and selected_sample_ids == full_sample_ids:
                authorized_expected[sample_id] = expected
            if frozen_requirements is None:
                from .requirement_graph import compile_requirement_graph
                from .three_layer import compile_expected

                projection = compile_expected(compile_requirement_graph(expected, comparison_contract='document_ast'))
                projection.pop("requirement_model", None)
            else:
                projection = frozen_requirements[sample_id]
            expected_by_sample[sample_id] = {**expected, **projection}
        except (ValueError, IndexError, KeyError, TypeError, OSError) as error:
            expected_by_sample[sample_id] = {
                "sample_id": sample_id, "document_id": samples[sample_id]["document_id"],
                "source_pages": samples[sample_id]["source_pages"], "scope": [], "targets": [],
                "reader_blocker": {"side": "expected", "reason": "selected_expected_reader_failure",
                                   "error": {"type": type(error).__name__, "message": str(error)}},
            }
    print(json.dumps({"stage": "expected_syntax_read", "samples": len(expected_by_sample)}), flush=True)
    from .requirement_graph import is_deferred_input_scope

    if diagnostic and selected_sample_ids == full_sample_ids and any(
            expected.get("reader_blocker") or any(not is_deferred_input_scope(expected["sample_id"], issue)
                for issue in expected.get("blockers", [])) for expected in expected_by_sample.values()):
        raise ValueError("complete expected semantics before full saved-output diagnosis; use an explicit --sample for bounded software diagnosis")
    if diagnostic and selected_sample_ids == full_sample_ids:
        if freeze is None:
            raise ValueError("full saved-output diagnosis requires the validated four-stage scoring freeze and current expected structure gate; use a strict sample subset for bounded software diagnosis")
        frozen = read_scoring_freeze(freeze, identity)
        frozen_requirements = _frozen_requirements(
            requirements or baseline / "requirements/current/index.json", full_sample_ids,
            identity["software_id"], frozen["validation"], expected_by_sample=authorized_expected)
        expected_by_sample = {sample_id: {**authorized_expected[sample_id], **frozen_requirements[sample_id]}
                              for sample_id in sorted(full_sample_ids)}
        index["validation"] = frozen["validation"]
        write_json(output / "scoring-freeze.json", frozen)
        write_json(output / "execution-status.json", index)
    tasks = []
    for sample_id in sorted(selected_sample_ids):
        for pipeline in PIPELINES:
            tasks.append({"group": pipeline, "sample_id": sample_id, "expected": expected_by_sample[sample_id],
                          "directory": baseline, "case": by_pipeline[pipeline][sample_id], "output": output,
                          "software_id": identity["software_id"], "diagnostic": diagnostic})
        for key, (directory, declared, execution) in service.items():
            tasks.append({"group": key, "sample_id": sample_id, "expected": expected_by_sample[sample_id],
                          "directory": directory, "case": declared[sample_id], "output": output,
                          "software_id": identity["software_id"], "execution_id": execution["software"]["software_id"],
                          "diagnostic": diagnostic})
    completed = {}
    for number, record in enumerate(_grade_tasks(tasks, workers), 1):
        completed[record["group"], record["sample_id"]] = record
        if number % max(1, len(groups)) == 0:
            print(json.dumps({"stage": "saved_output_diagnosis" if diagnostic else "three_layer_comparison",
                              "completed_records": number, "declared_records": len(tasks)}), flush=True)
    for sample_id in sorted(selected_sample_ids):
        expected = expected_by_sample[sample_id]
        paired = []
        for key in groups:
            record = completed[key, sample_id]
            score = read_score(output / record["path"])
            paired.append({"publishable": score.get("publishable"),
                           "layers": {layer: {"denominator": score["layers"][layer]["denominator"]} for layer in LAYERS},
                           "requirements": _target_fingerprint(score)})
            index["records"].append({name: record[name] for name in ("group", "sample_id", "path")})
            index["blockers"].extend(_blocker_index(score, record))
            del score
            if record["readback"]:
                provenance = record["readback"]
                index["native_readback"]["observations"].append({**provenance,
                    "observation": "private/" + provenance["observation"],
                    "diagnostics": "private/" + provenance["diagnostics"]})
        if all(score.get("publishable") for score in paired) and len({score["requirements"] for score in paired}) != 1:
            index["blockers"].append({"sample_id": sample_id, "side": "software",
                                      "reason": "unequal_requirements_between_groups"})
        index["coverage"].append({
            "sample_id": sample_id, "document_id": expected["document_id"], "scope": expected["scope"],
            "layers": {layer: {"denominator": paired[0]["layers"][layer]["denominator"]} for layer in LAYERS},
            "groups_traversed": len(paired),
            "meaning": "partial_compilation_diagnostics_not_complete_semantic_coverage" if diagnostic or any(
                not score.get("publishable") for score in paired) else "frozen_expected_requirements_compared",
        })
    index["full_scope_traversed"] = selected_sample_ids == full_sample_ids
    if code_identity()["software_id"] != identity["software_id"]:
        index["blockers"].append({"side": "software", "reason": "software_changed_during_analysis"})
    if diagnostic and selected_sample_ids != full_sample_ids:
        index["execution_costs"] = {
            "status": "not_aggregated_in_selected_diagnosis",
            "policy": "original_measurements_unchanged_not_filled_or_inferred",
            "scope": "selected_software_diagnosis_not_processing_cost_comparison",
        }
    else:
        try:
            index["execution_costs"] = execution_costs(baseline, session, service)
        except (ValueError, IndexError, KeyError, TypeError, OSError) as error:
            index["execution_costs"] = {"status": "unreadable_original_measurement", "error": str(error),
                                        "policy": "no_missing_cost_filled_or_inferred"}
    if index["blockers"]:
        index.update(state="blocked", expected_comparison_complete=False,
                     blocker_counts=dict(Counter(item["reason"] for item in index["blockers"])))
    elif diagnostic:
        index.update(state="diagnostic_completed", expected_comparison_complete=False,
                     quality_scores_withheld=True, reader_review="pending_independent_text_diagnosis")
    else:
        try:
            from .streaming_aggregation import aggregate_score_files

            aggregated = aggregate_score_files(index["records"], groups=groups, base_dir=output,
                                               expected_sample_ids=full_sample_ids)
            if not aggregated["publishable"]:
                raise ValueError("complete global quality requires all three nonzero layer denominators")
            _write_compact_score(output / "private/pairs.json", aggregated["paired_details"])
            index.update(state="completed", expected_comparison_complete=True, summary=aggregated["summary"],
                         paired=aggregated["paired"], paired_details="private/pairs.json")
        except ValueError as error:
            index.update(state="blocked", expected_comparison_complete=False,
                         blockers=[{"side": "software", "reason": "layer_aggregation_invariant", "error": str(error)}])
    write_json(output / "index.json", index)
    write_json(output / "execution-status.json", index)
    return output / "index.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-root", type=Path, default=ROOT / "pdf_sample/parsing/expected")
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--service-baseline-root", type=Path)
    parser.add_argument("--current-root", type=Path)
    parser.add_argument("--requirements", type=Path, help="independently validated expected requirement index; default saved run requirements/current/index.json")
    parser.add_argument("--workers", type=int, default=16, help="saved-output analysis processes; original execution costs unchanged")
    parser.add_argument("--diagnostic", action="store_true", help="diagnose a strict sample subset without a freeze; full traversal requires a validated freeze; publish no quality scores")
    parser.add_argument("--sample", action="append", help="explicit saved sample identity; diagnostic mode only")
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args()
    if args.sample is not None and not args.diagnostic:
        parser.error("--sample is diagnostic-only; formal scoring always uses the full declared scope")
    if not args.diagnostic and args.freeze is None:
        parser.error("--freeze is required for formal scoring; unfrozen diagnostics must select a strict sample subset")
    if args.diagnostic and args.report_output:
        parser.error("diagnostic traversal cannot publish a formal report")
    index_path = evaluate_saved(args.baseline, args.output, expected_root=args.expected_root, freeze=args.freeze,
                                service_baseline_root=args.service_baseline_root, current_root=args.current_root,
                                workers=args.workers, diagnostic=args.diagnostic, sample_ids=args.sample,
                                requirements=args.requirements)
    print(index_path)
    index = read_json(index_path)
    if index["state"] == "completed" and not args.diagnostic:
        if args.report_output:
            from scripts.render_lite_report import render
            render(index_path, args.report_output)
    return 2 if index["state"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
