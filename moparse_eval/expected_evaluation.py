"""Uniform evaluation of saved native and public Markdown outputs.

This command never launches parsing, opens PDFs, edits references, or consumes
historical annotation answers/adjudications. All groups use the same targets.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import wraps
from pathlib import Path
from typing import Any

from .candidate_delivery import final_delivery, native_delivery
from .expected_readback import markdown_observation, read_expected
from .expected_scoring import PROTOCOL, grade_expected, require_paired_targets
from .native_readback import READBACK_VERSION, read_native_relations
from .packaging import inside, read_json, write_json
from .prose_metrics import summarize_text
from .saved_native import read_saved_native

PIPELINES = tuple(f"P{i:02}" for i in range(1, 9))
ROOT = Path(__file__).resolve().parent.parent


def _record_failure(function):
    @wraps(function)
    def wrapped(baseline, output, **kwargs):
        owned = not output.exists()
        try:
            return function(baseline, output, **kwargs)
        except BaseException as error:
            status = output / "execution-status.json"
            if owned and status.is_file():
                record = read_json(status)
                record.update(state="failed", expected_comparison_complete=False,
                              error={"type": type(error).__name__, "message": str(error)})
                write_json(status, record)
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


def _service_inputs(root: Path, pipeline: str) -> tuple[Path, dict[str, Any]]:
    directory = root / pipeline.lower()
    run = read_json(directory / "run.json")
    if run.get("state") != "completed":
        raise ValueError("finish candidate processing before evaluating its saved output")
    return directory, run


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


def summarize(scores: list[dict[str, Any]], *, grouped: bool = True) -> dict[str, Any]:
    kinds: dict[str, Counter] = defaultdict(Counter)
    reasons: Counter = Counter()
    for score in scores:
        for kind, counts in score["by_kind"].items():
            kinds[kind].update(counts)
        reasons.update(row["reason"] for row in score["outcomes"] if row["outcome"] == "incorrect")
    durations = [s.get("timing", {}).get("processing_seconds") for s in scores]
    measured = [value for value in durations if type(value) in {int, float} and math.isfinite(value)]
    result = {"samples": len(scores), "documents": len({s["document_id"] for s in scores}),
              "by_kind": dict(kinds), "incorrect_reasons": dict(reasons),
              "status_counts": dict(Counter(s.get("status") for s in scores)),
              "processing_seconds": sum(measured) if len(measured) == len(scores) else None,
              "observed_processing_seconds_subtotal": sum(measured) if measured else None,
              "measured_processing_samples": len(measured), "missing_processing_samples": len(scores) - len(measured)}
    literals = [row["raw_value_text"] for score in scores for row in score["outcomes"] if row.get("raw_value_text")]
    result["raw_value_diagnostics"] = {"targets": len(literals),
        "width_equivalent_exact": sum(row["width_equivalent"]["distance"] == 0 for row in literals),
        "strict_exact": sum(row["strict"]["distance"] == 0 for row in literals),
        "meaning": "printed_value_spelling_only_separate_from_business_correctness"}
    result["text_metrics"] = summarize_text([row for score in scores for row in score["outcomes"]])
    fields = [row for score in scores for row in score["outcomes"] if row["kind"] == "business_field"]
    result["business_metrics"] = {
        "targets": len(fields), "value_and_labels_correct": sum(row.get("value_and_labels_correct", False) for row in fields),
        "complete_information_correct": sum(row["outcome"] == "correct" for row in fields),
        "readable": sum(row.get("actual") is not None for row in fields),
        "conditional_correctness_diagnostic": (sum(row["outcome"] == "correct" for row in fields)
            / sum(row.get("actual") is not None for row in fields)) if any(row.get("actual") is not None for row in fields) else None}
    deliveries = [score["asset_delivery"] for score in scores if score.get("asset_delivery")]
    result["asset_delivery"] = {"observed_samples": len(deliveries), "missing_delivery_records": len(scores) - len(deliveries),
        **{key: sum(row.get(key, 0) for row in deliveries) for key in (
            "declared_files", "files_present", "image_references", "references_with_file", "references_without_file")},
        "meaning": "candidate_delivery_observation_not_image_content_correctness"}
    if grouped:
        for key in ("document_id", "family_id"):
            members = defaultdict(list)
            for score in scores:
                members[score.get(key) or "not_declared"].append(score)
            result["by_" + key.removesuffix("_id")] = {name: summarize(group, grouped=False) for name, group in members.items()}
        result["development_exposure"] = dict(Counter(str(s.get("development_exposure") or "not_declared") for s in scores))
    return result


def paired_changes(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    old = {score["sample_id"]: score for score in previous}
    gains: list[dict[str, Any]] = []
    losses: list[dict[str, Any]] = []
    literal_gains: list[dict[str, Any]] = []
    literal_losses: list[dict[str, Any]] = []
    for score in current:
        before = old[score["sample_id"]]
        require_paired_targets([before, score])
        states = {row["id"]: row for row in before["outcomes"]}
        for row in score["outcomes"]:
            prior = states[row["id"]]
            if row.get("raw_value_text") and prior.get("raw_value_text"):
                left = prior["raw_value_text"]["width_equivalent"]["distance"] == 0
                right = row["raw_value_text"]["width_equivalent"]["distance"] == 0
                if left != right:
                    (literal_gains if right else literal_losses).append({"sample_id": score["sample_id"],
                        "id": row["id"], "before": prior, "after": row})
            if prior["outcome"] == row["outcome"]:
                continue
            item = {"sample_id": score["sample_id"], "target": row["id"], "kind": row["kind"],
                    "reference": row["reference"], "expected": row["expected"],
                    "before": prior, "after": row}
            (gains if row["outcome"] == "correct" else losses).append(item)
    return {"new_correct": len(gains), "lost_correct": len(losses), "gains": gains, "losses": losses,
            "raw_literal_new_exact": len(literal_gains), "raw_literal_lost_exact": len(literal_losses),
            "raw_literal_gains": literal_gains, "raw_literal_losses": literal_losses}


def _change_summary(changes: dict[str, Any], *, details: str = "private/paired-changes.json") -> dict[str, Any]:
    return {pipeline: {"new_correct": delta["new_correct"], "lost_correct": delta["lost_correct"],
                       "raw_literal_new_exact": delta["raw_literal_new_exact"],
                       "raw_literal_lost_exact": delta["raw_literal_lost_exact"],
                       "gains_by_kind": dict(Counter(x["kind"] for x in delta["gains"])),
                       "losses_by_kind": dict(Counter(x["kind"] for x in delta["losses"])),
                       "details": details}
            for pipeline, delta in changes.items()}


def native_preservation(native: list[dict[str, Any]], final: list[dict[str, Any]]) -> dict[str, Any]:
    """Require every native-correct target to survive public export."""
    delta = paired_changes(native, final)
    losses = [row for row in delta["losses"] if row["kind"] == "business_field"]
    correct = sum(row["kind"] == "business_field" and row["outcome"] == "correct"
                  for score in native for row in score["outcomes"])
    all_correct = sum(row["outcome"] == "correct" for score in native for row in score["outcomes"])
    return {"native_correct_business_targets": correct, "preserved": correct - len(losses),
            "lost_correct_business_targets": len(losses), "losses": delta["losses"],
            "native_correct_targets": all_correct, "preserved_targets": all_correct - delta["lost_correct"],
            "lost_correct_targets": delta["lost_correct"], "passed": delta["lost_correct"] == 0,
            "comparison": "native_to_actual_final_markdown_under_one_shared_scorer"}


def adoption_status(changes: dict[str, Any], preservation: dict[str, Any]) -> dict[str, Any]:
    return {pipeline: {
        "no_lost_correct_targets": delta["lost_correct"] == 0,
        "native_correct_business_preserved": preservation[pipeline]["lost_correct_business_targets"] == 0,
        "native_correct_content_preserved": preservation[pipeline]["passed"],
        "native_to_final_business_losses": preservation[pipeline]["lost_correct_business_targets"],
        "native_to_final_content_losses": preservation[pipeline]["lost_correct_targets"],
        "adoptable": delta["lost_correct"] == 0 and preservation[pipeline]["passed"],
        "comparison": "sole_baseline_to_current_and_native_to_current",
    } for pipeline, delta in changes.items()}


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


def _grade_saved_group(task: dict[str, Any]) -> dict[str, Any]:
    """Compute one saved candidate in an analysis-only CPU process."""
    group, sample_id, expected = task["group"], task["sample_id"], task["expected"]
    directory, case, output = task["directory"], task["case"], task["output"]
    if group in PIPELINES:
        observation = native_observation(directory, case, analysis=output / "private", software_id=task["software_id"])
        source = observation["candidate_source"]
    else:
        relative = case.get("final_markdown") or str(Path(case["observation"]).with_name("final.md"))
        source = inside(directory, relative)
        observation = final_observation(source, sample_id=sample_id, pipeline=group,
            pages=list(range(1, len(expected["source_pages"]) + 1)), metadata=case)
    try:
        score = grade_expected(expected, observation)
    except (ValueError, IndexError, KeyError, TypeError) as error:
        raise ValueError(f"shared grader failed on {group}/{sample_id}; repair before publication: {error}") from error
    score.update(scoring_software_id=task["software_id"], candidate_source=str(source))
    if task.get("execution_id"):
        score["execution_software_id"] = task["execution_id"]
    relative = f"private/scores/{group}/quality800-r1/{sample_id}.json"
    write_json(output / relative, score)
    return {"group": group, "sample_id": sample_id, "path": relative,
            "readback": observation.get("scoring_readback")}


def _grade_tasks(tasks: list[dict[str, Any]], workers: int):
    if workers == 1:
        yield from map(_grade_saved_group, tasks)
        return
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as executor:
        futures = [executor.submit(_grade_saved_group, task) for task in tasks]
        try:
            for future in as_completed(futures):
                yield future.result()
        except BaseException:
            for future in futures:
                future.cancel()
            raise


@_record_failure
def evaluate_saved(baseline: Path, output: Path, *, expected_root: Path,
                   freeze: Path, service_baseline_root: Path | None = None, current_root: Path | None = None,
                   workers: int = 1) -> Path:
    from .cli import (
        _require_formal_measurement_conditions,
        code_identity,
        read_scoring_freeze,
        snapshot_software,
    )

    identity = code_identity()
    frozen = read_scoring_freeze(freeze, identity)
    if not 1 <= workers <= 8:
        raise ValueError("analysis workers must be between 1 and 8")
    if output.resolve().is_relative_to(expected_root.resolve()):
        raise ValueError("evaluation output must be outside the read-only expected directory")
    baseline = baseline.resolve()
    session = read_json(baseline / "run.json")
    _require_formal_measurement_conditions(baseline, session)
    if session.get("state") not in {"completed", "failed"}:
        raise ValueError("saved native run must have completed execution and restoration")
    dataset = Path(session["dataset"])
    if output.resolve().is_relative_to(dataset.resolve()):
        raise ValueError("evaluation output must be outside the read-only dataset package")
    manifest = read_json(dataset / "manifest.json")
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    cases = quality_cases(session)
    by_pipeline = {p: {c["sample_id"]: c for c in cases if c["pipeline"] == p} for p in PIPELINES}
    if sum(len(items) for items in by_pipeline.values()) != len(cases):
        raise ValueError("duplicate or undeclared pipeline quality cases")
    sample_ids = set(by_pipeline[PIPELINES[0]])
    declared_samples = set(manifest.get("suites", {}).get("lite", samples))
    if sample_ids != declared_samples:
        raise ValueError("quality comparison must cover the entire declared Lite selection")
    if not sample_ids or any(set(by_pipeline[p]) != sample_ids for p in PIPELINES):
        raise ValueError("all eight pipelines must be evaluated on the same declared quality samples")
    output.mkdir(parents=True, exist_ok=False)
    snapshot_software(output / "software", identity)
    write_json(output / "scoring-freeze.json", frozen)
    groups: dict[str, list[dict[str, Any]]] = {p: [] for p in PIPELINES}
    service = {}
    for label, root in (("baseline", service_baseline_root), ("current", current_root)):
        if root is None:
            continue
        for pipeline in ("P07", "P08"):
            directory, run = _service_inputs(root, pipeline)
            if (Path(run["baseline_run"]).resolve() != baseline
                    or Path(run["dataset"]).resolve() != dataset.resolve()
                    or run["native_pipeline"]["pipeline"] != pipeline):
                raise ValueError("final output execution must declare the same baseline, dataset and native pipeline")
            declared = {c["sample_id"]: c for c in quality_cases(run)}
            if set(declared) != sample_ids:
                raise ValueError("saved final outputs must cover the same quality samples as all native groups")
            for sample_id, case in declared.items():
                if case["baseline_observation_source"] != by_pipeline[pipeline][sample_id]["observation"]:
                    raise ValueError("paired final output does not declare the same saved native input")
            key = f"{pipeline}-{label}"
            service[key] = (directory, declared, run)
            groups[key] = []
    index: dict[str, Any] = {"state": "running", "protocol": PROTOCOL, "scoring_protocol": PROTOCOL,
                            "score_id": output.name, "software": identity,
                            "reference_freeze": manifest.get("freeze_record"),
                            "baseline": str(baseline), "expected_root": str(expected_root.resolve()),
                            "expected_comparison_complete": False, "results": [], "records": [], "coverage": [],
                            "quality_suite": "quality800", "groups": list(groups),
                            "analysis_workers": workers, "analysis_timing": "excluded_from_parser_and_postprocessing_costs",
                            "validation": frozen["validation"],
                            "native_readback": {"reader_version": READBACK_VERSION, "observations": []},
                            "historical_adjudications": "not_read_or_applied"}
    write_json(output / "execution-status.json", index)
    reference_cache: dict[Path, Any] = {}
    expected_by_sample = {}
    for sample_id in sorted(sample_ids):
        expected_by_sample[sample_id] = read_expected(samples[sample_id], expected_root, cache=reference_cache)
        if len(expected_by_sample) % 10 == 0:
            print(json.dumps({"stage": "expected_readback", "samples_ready": len(expected_by_sample),
                              "samples": len(sample_ids)}), flush=True)
    print(json.dumps({"stage": "expected_readback_ready", "samples": len(expected_by_sample)}), flush=True)
    tasks = []
    for sample_id in sorted(sample_ids):
        for pipeline in PIPELINES:
            tasks.append({"group": pipeline, "sample_id": sample_id, "expected": expected_by_sample[sample_id],
                          "directory": baseline, "case": by_pipeline[pipeline][sample_id], "output": output,
                          "software_id": identity["software_id"]})
        for key, (directory, declared, execution) in service.items():
            tasks.append({"group": key, "sample_id": sample_id, "expected": expected_by_sample[sample_id],
                          "directory": directory, "case": declared[sample_id], "output": output,
                          "software_id": identity["software_id"], "execution_id": execution["software"]["software_id"]})
    completed: dict[tuple[str, str], dict[str, Any]] = {}
    counts: Counter = Counter()
    ready = 0
    for row in _grade_tasks(tasks, workers):
        completed[row["group"], row["sample_id"]] = row
        counts[row["sample_id"]] += 1
        if counts[row["sample_id"]] == len(groups):
            ready += 1
            print(json.dumps({"sample": row["sample_id"], "completed": ready, "samples": len(sample_ids)}), flush=True)
            write_json(output / "execution-status.json", {"state": "running", "software_id": identity["software_id"],
                "expected_comparison_complete": False, "completed_samples": ready, "declared_samples": len(sample_ids),
                "latest_sample": row["sample_id"]})
    for sample_id in sorted(sample_ids):
        expected = expected_by_sample[sample_id]
        paired = []
        for key, members in groups.items():
            row = completed[key, sample_id]
            score = read_json(output / row["path"])
            members.append(score)
            paired.append(score)
            index["results"].append(row["path"])
            index["records"].append({k: row[k] for k in ("group", "sample_id", "path")})
            if row["readback"]:
                provenance = row["readback"]
                index["native_readback"]["observations"].append({**provenance,
                    "observation": "private/" + provenance["observation"],
                    "diagnostics": "private/" + provenance["diagnostics"]})
        require_paired_targets(paired)
        index["coverage"].append({"sample_id": sample_id, "document_id": expected["document_id"],
                                   "scope": expected["scope"], "expected_elements": len(expected["targets"]),
                                   "content_coverage": paired[0]["content_coverage"],
                                   "targets": paired[0]["targets"], "groups_graded": len(paired),
                                   "reference": "canonical_expected_only"})
    if code_identity()["software_id"] != identity["software_id"]:
        raise ValueError("scoring software changed during the run; do not publish mixed identities")
    summary = {key: summarize(members) for key, members in groups.items()}
    changes = {p: paired_changes(groups[f"{p}-baseline"], groups[f"{p}-current"])
               for p in ("P07", "P08") if f"{p}-baseline" in groups and f"{p}-current" in groups}
    write_json(output / "private/paired-changes.json", changes)
    costs = execution_costs(baseline, session, service)
    preservation = {p: native_preservation(groups[p], groups[f"{p}-current"])
                    for p in ("P07", "P08") if f"{p}-current" in groups}
    write_json(output / "private/native-preservation.json", preservation)
    index.update(state="completed", expected_comparison_complete=True, summary=summary, changes=_change_summary(changes),
                 execution_costs=costs,
                 native_preservation={p: {**{k: v for k, v in row.items() if k != "losses"},
                                         "details": "private/native-preservation.json"}
                                      for p, row in preservation.items()},
                 adoption=adoption_status(changes, preservation),
                 development_exposure="Lite outputs and expected syntax used for software development; no independent held-out claim")
    write_json(output / "index.json", index)
    write_json(output / "execution-status.json", {key: value for key, value in index.items() if key != "results"})
    return output / "index.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-root", type=Path, default=ROOT / "pdf_sample/parsing/expected")
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--service-baseline-root", type=Path)
    parser.add_argument("--current-root", type=Path)
    parser.add_argument("--workers", type=int, default=1, help="analysis CPU processes; does not change scoring or processing times")
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args()
    index_path = evaluate_saved(args.baseline, args.output, expected_root=args.expected_root, freeze=args.freeze,
                                service_baseline_root=args.service_baseline_root, current_root=args.current_root,
                                workers=args.workers)
    if index_path.resolve().is_relative_to(args.baseline.resolve()):
        session = read_json(args.baseline / "run.json")
        session["latest_scores"] = str(index_path.resolve().relative_to(args.baseline.resolve()))
        write_json(args.baseline / "run.json", session)
    print(index_path)
    if args.report_output:
        from scripts.render_lite_report import render
        render(index_path, args.report_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
