"""Direct native and postprocessing costs, independent of quality grading."""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any

_SUCCESS = {"ok", "success", "completed", "succeeded"}


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _service_number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _service_count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def native_performance(results: list[dict[str, Any]]) -> dict[str, Any]:
    measured: list[dict[str, Any]] = []
    warmup: list[dict[str, Any]] = []
    initialization: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    seen_initialization: set[Any] = set()
    resource_rows: list[dict[str, Any]] = []
    scheduled: list[dict[str, Any]] = []
    for result in results:
        timing = result.get("timing", {})
        seconds = timing.get("processing_seconds")
        row = {
            "sample_id": result.get("sample_id"), "run_id": result.get("run_id"),
            "repetition": result.get("repetition"), "status": result.get("status"),
            "processing_seconds": seconds,
            "input_pages": result.get("input_page_count"),
        }
        resource_rows.append({"sample_id": result.get("sample_id"), "repetition": result.get("repetition"),
                              "page_inference_runtime": result.get("page_inference_runtime", [
                                  {"page": page.get("page"), "record": page["inference_runtime"]}
                                  for page in result.get("pages", []) if page.get("inference_runtime")
                              ]), **result.get("resources", {})})
        init_seconds = timing.get("pipeline_initialization_seconds")
        identity = result.get("run_id")
        if _finite_number(init_seconds) and identity not in seen_initialization:
            initialization.append({"run_id": identity, "initialization_seconds": init_seconds,
                                   "scope": "persistent_sdk_worker_once"})
            seen_initialization.add(identity)
        phase = result.get("phase", "measured")
        if phase == "warmup":
            warmup.append(row)
            continue
        if phase in {"initialization", "init"}:
            initialization.append(row)
            continue
        if phase in {"measured", "preflight"}:
            scheduled.append(row)
        if phase not in {"measured", "preflight"} or not _finite_number(seconds) or seconds <= 0:
            unavailable.append({**row, "reason": "direct_positive_processing_seconds_unavailable"})
            continue
        pages = result.get("input_page_count")
        row["input_pages"] = pages if type(pages) is int and pages > 0 else None
        row["pages_per_second"] = pages / seconds if row["input_pages"] is not None else None
        measured.append(row)
    successes = [row for row in measured if row["status"] in _SUCCESS]
    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in measured:
        by_sample[str(row["sample_id"])].append(row)
    samples = {}
    for sample_id, rows in sorted(by_sample.items()):
        repetitions = {row["repetition"] for row in rows if row["repetition"] is not None}
        successful = [row["processing_seconds"] for row in rows if row["status"] in _SUCCESS]
        samples[sample_id] = {
            "measured_runs": len(rows), "distinct_declared_repetitions": len(repetitions),
            "at_least_three_measured_repetitions": len(repetitions) >= 3,
            "successful_runs": len(successful),
            "mean_processing_seconds": statistics.fmean(successful) if successful else None,
            "median_processing_seconds": statistics.median(successful) if successful else None,
            "runs": rows,
        }
    throughput_rows = [row for row in successes if row["input_pages"] is not None]
    total_seconds = sum(row["processing_seconds"] for row in throughput_rows)
    total_pages = sum(row["input_pages"] for row in throughput_rows)
    by_repetition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scheduled:
        by_repetition[str(row["repetition"])].append(row)
    rounds: list[dict[str, Any]] = []
    for repetition, rows in sorted(by_repetition.items()):
        timing_complete = all(_finite_number(row["processing_seconds"]) and row["processing_seconds"] > 0 for row in rows)
        known_durations = [row["processing_seconds"] for row in rows
                           if _finite_number(row["processing_seconds"]) and row["processing_seconds"] > 0]
        duration = sum(known_durations) if known_durations else None
        pages_known = all(type(row["input_pages"]) is int and row["input_pages"] > 0 for row in rows)
        planned_pages = sum(row["input_pages"] for row in rows) if pages_known else None
        completed_pages = sum(row["input_pages"] or 0 for row in rows if row["status"] in _SUCCESS)
        rounds.append({
            "repetition": repetition, "measured_samples": len(rows),
            "attempted_input_pages": planned_pages, "completed_input_pages": completed_pages,
            "processing_seconds_including_failures": duration if timing_complete else None,
            "observed_processing_seconds_subtotal": duration,
            "observed_processing_samples": len(known_durations),
            "timing_complete": timing_complete,
            "completed_pages_per_second_including_failure_cost": completed_pages / duration if duration and timing_complete else None,
            "seconds_per_attempted_input_page": duration / planned_pages if planned_pages and timing_complete else None,
            "all_samples_completed": all(row["status"] in _SUCCESS for row in rows),
        })
    round_durations = [row["processing_seconds_including_failures"] for row in rounds if row["timing_complete"]]
    round_mean = statistics.fmean(round_durations) if round_durations else None
    return {
        "boundary": "direct_worker_processing_to_native_and_faithful_export_ready",
        "measured_runs": len(measured), "scheduled_runs": len(scheduled), "successful_runs": len(successes),
        "failed_runs": sum(row["status"] not in _SUCCESS for row in scheduled),
        "samples": samples, "warmup": warmup, "initialization": initialization,
        "timing_unavailable": unavailable,
        "status_counts": dict(Counter(str(result.get("status", "unknown")) for result in results)),
        "rounds": rounds,
        "round_duration_summary": {
            "n": len(round_durations),
            "median_seconds": statistics.median(round_durations) if round_durations else None,
            "min_seconds": min(round_durations) if round_durations else None,
            "max_seconds": max(round_durations) if round_durations else None,
            "sample_stdev_seconds": statistics.stdev(round_durations) if len(round_durations) >= 2 else None,
            "coefficient_of_variation": statistics.stdev(round_durations) / round_mean
            if len(round_durations) >= 2 and round_mean else None,
            "includes_failed_attempts": True,
            "missing_durations_are_not_zero": bool(unavailable),
        },
        "resource_observations": resource_rows,
        "successful_run_throughput": {
            "pages": total_pages, "processing_seconds": total_seconds if throughput_rows else None,
            "pages_per_second": total_pages / total_seconds if total_seconds else None,
            "denominator_runs": len(throughput_rows),
        },
        "repetitions_are_not_independent_documents": True,
    }


def postprocessing_performance(cases: list[dict[str, Any]], suite: str) -> dict[str, Any]:
    cases = [case for case in cases if case.get("suite") == suite and case.get("phase", "measured") == "measured"]
    expected = {str(case.get("sample_id")) for case in cases}
    repetitions = {int(case.get("repetition", 1)) for case in cases}
    if suite == "perf80":
        repetitions |= {1, 2, 3}
    rounds: list[dict[str, Any]] = []
    for repetition in sorted(repetitions):
        items = [case for case in cases if int(case.get("repetition", 1)) == repetition]
        seconds = [_service_number(case.get("timing", {}).get("postprocessing_seconds")) for case in items]
        known = [value for value in seconds if value is not None and value >= 0]
        scope_complete = {str(case.get("sample_id")) for case in items} == expected and bool(items)
        timing_complete = scope_complete and len(known) == len(items)
        pages = [_service_count(case.get("input_pages", case.get("input_page_count"))) for case in items]
        capture = [_service_number(case.get("timing", {}).get("diagnostic_capture_seconds")) for case in items]
        rounds.append({"repetition": repetition, "samples": len(items), "expected_samples": len(expected),
                       "input_pages": sum(page for page in pages if page is not None) if pages and all(page is not None for page in pages) else None,
                       "postprocessing_seconds": sum(known) if timing_complete else None,
                       "observed_seconds_subtotal": sum(known) if known else None,
                       "missing_timing_samples": len(items) - len(known), "timing_complete": timing_complete,
                       "status_counts": dict(Counter(str(case.get("status", "unknown")) for case in items)),
                       "diagnostic_capture_seconds": sum(value for value in capture if value is not None)
                           if capture and all(value is not None for value in capture) else None})
    complete = [value for item in rounds if (value := _service_number(item["postprocessing_seconds"])) is not None]
    return {"suite": suite, "rounds": rounds, "complete_timing_rounds": len(complete),
            "median_postprocessing_seconds": statistics.median(complete) if complete else None,
            "minimum_seconds": min(complete) if complete else None, "maximum_seconds": max(complete) if complete else None,
            "coefficient_of_variation": statistics.pstdev(complete) / statistics.mean(complete)
                if len(complete) > 1 and statistics.mean(complete) else None,
            "meaning": "postprocessing_only_not_new_end_to_end_parse_timing"}
