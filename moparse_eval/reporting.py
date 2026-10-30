"""Aggregate declared output-evaluation results without a weighted total score."""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from .compose_runs import composition_markdown
from .metrics import aggregate_text_metrics, fraction, precision_recall_f1
from .report_overview import table_field_breakdown

_SUCCESS = {"ok", "success", "completed", "succeeded"}
_SCALAR_RATES = {"value", "cer", "normalized_edit_distance", "similarity", "precision", "recall", "f1"}
_SLICE_METRICS = {
    "strict_cer": "text.strict.cer",
    "aligned_cer": "text_aligned.strict.cer",
    "strict_edit_similarity": "text.strict.similarity",
    "content_recall": "unit_presence.recall",
    "table_field_target_correctness": "table_records.field_target_correctness.value",
    "table_field_compared_accuracy": "table_records.field_compared_accuracy.value",
    "information_target_correctness": "table_records.information_target_correctness.value",
    "relation_recall": "relations.by_type.before.value",
}
_SLICE_COVERAGE = (
    "declared_units", "confirmed_units", "scored_units", "localized_units",
    "ambiguous_units", "unresolved_units", "not_localized_units", "reference_unavailable_relations",
)
QUALITY_SLICE_COLUMNS = (
    "pipeline", "dataset", "suite", "scope", "scope_key", "quality_status",
    "samples", "documents", "input_pages", "failed_samples", "unscored_samples",
    "observed_processing_seconds_subtotal", "processing_seconds_including_failures",
    "observed_processing_samples", "missing_processing_samples", "timing_complete",
    "completed_input_pages", "seconds_per_attempted_input_page",
    "completed_pages_per_second_including_failure_cost",
    *_SLICE_COVERAGE,
    "text_reference_chars", "text_aligned_reference_chars", "content_targets", "content_located",
    "table_field_targets", "table_field_correct", "table_fields_observable",
    "table_fields_compared", "table_fields_missing", "table_fields_unresolved",
    "table_information_correct", "table_information_incorrect",
    "relation_targets", "relation_correct", "relation_observable", "relation_unresolved",
    *_SLICE_METRICS,
    *(column for name in _SLICE_METRICS for column in (
        f"macro_document_{name}", f"macro_document_{name}_available_documents",
        f"macro_document_{name}_total_documents",
    )),
)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _micro(results: list[dict[str, Any]]) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    metric_names = sorted({key for result in results for key in result.get("metrics", {})})
    for name in metric_names:
        items = [result["metrics"][name] for result in results if name in result.get("metrics", {})]
        if name in {"text", "text_aligned", "field_text", "table_cell_text"}:
            combined[name] = aggregate_text_metrics(items)
            combined[name]["units"] = sum(item.get("units", 0) for item in items)
        elif name in {"unit_presence", "unit_exact", "relations"}:
            fp = sum(item["fp"] for item in items) if all(item.get("fp") is not None for item in items) else None
            combined[name] = precision_recall_f1(
                sum(item["tp"] for item in items), fp, sum(item["fn"] for item in items)
            )
            exhaustive_items = [item for item in items if item.get("fp") is not None]
            combined[name]["exhaustive_scope_precision"] = fraction(
                sum(item["tp"] for item in exhaustive_items),
                sum(item["tp"] + item["fp"] for item in exhaustive_items),
                available_scopes=len(exhaustive_items), total_scopes=len(items),
            )
            if name == "relations":
                combined[name]["observable"] = sum(item.get("observable", 0) for item in items)
                combined[name]["unresolved"] = sum(item.get("unresolved", 0) for item in items)
                states = ("confirmed_correct", "confirmed_incorrect", "native_not_provided",
                          "endpoint_unresolved", "unassessable")
                combined[name]["evidence_states"] = {
                    state: sum(item["evidence_states"][state] for item in items)
                    if all(isinstance(item.get("evidence_states", {}).get(state), int) for item in items)
                    else None for state in states
                }
                combined[name]["interpretation"] = "target_fulfillment_not_relation_recognition_accuracy"
                kinds = sorted({kind for item in items for kind in item.get("by_type", {})})
                combined[name]["by_type"] = {
                    kind: fraction(
                        sum(item.get("by_type", {}).get(kind, {}).get("numerator", 0) for item in items),
                        sum(item.get("by_type", {}).get(kind, {}).get("denominator", 0) for item in items),
                    )
                    for kind in kinds
                }
                for kind in kinds:
                    typed = [item["by_type"][kind] for item in items if kind in item.get("by_type", {})]
                    detail = combined[name]["by_type"][kind]
                    detail["observable"] = (sum(item["observable"] for item in typed)
                        if all(type(item.get("observable")) is int for item in typed) else None)
                    for state in states:
                        detail[state] = sum(item[state] for item in typed) if all(
                            isinstance(item.get(state), int) for item in typed
                        ) else None
                    correct, incorrect = detail.get("confirmed_correct"), detail.get("confirmed_incorrect")
                    detail["conditional_accuracy"] = (
                        fraction(correct, correct + incorrect)
                        if type(correct) is int and type(incorrect) is int
                        else {"numerator": None, "denominator": None, "value": None}
                    )
                    pairs = [item["by_type"][kind]["pair_classification"] for item in items
                             if "pair_classification" in item.get("by_type", {}).get(kind, {})]
                    if pairs:
                        combined[name]["by_type"][kind]["pair_classification"] = precision_recall_f1(
                            sum(pair["tp"] for pair in pairs), sum(pair["fp"] for pair in pairs),
                            sum(pair["fn"] for pair in pairs),
                        )
        elif name == "table_records":
            counters = ("target_records", "located_records", "target_fields", "observable_fields", "declared_fields", "source_unscoped_fields", "blank_target_fields", "blank_observed_fields",
                        "compared_fields", "target_missing_fields", "unresolved_fields",
                        "graded_fields", "incorrect_fields", "correct_fields", "strict_correct_fields", "information_correct_fields",
                        "information_incorrect_fields", "information_unresolved_fields")
            record_result: dict[str, Any] = {
                key: sum(item[key] for item in items)
                if all(type(item.get(key)) is int and item[key] >= 0 for item in items) else None
                for key in counters
            }
            new_schema = all(record_result[key] is not None for key in (
                "compared_fields", "target_missing_fields", "unresolved_fields", "correct_fields", "strict_correct_fields",
            ))
            rate_names = (
                "field_coverage", "field_strict_accuracy", "field_target_correctness",
                "field_compared_accuracy", "field_strict_target_correctness", "field_comparison_coverage",
                "grid_relation", "binding", "binding_target_coverage",
                "field_annotation_record_coverage",
                "blank_fields", "blank_observed_accuracy",
                "information_target_correctness", "information_compared_accuracy",
            )
            for key in rate_names:
                known = all(isinstance(item.get(key), dict) and type(item[key].get(field)) is int
                            for item in items for field in ("numerator", "denominator"))
                if key in {"field_target_correctness", "field_compared_accuracy", "field_strict_accuracy",
                           "field_strict_target_correctness", "field_comparison_coverage"}:
                    known &= new_schema
                record_result[key] = (fraction(
                    sum(item[key]["numerator"] for item in items),
                    sum(item[key]["denominator"] for item in items),
                ) if known else {"numerator": None, "denominator": None, "value": None})
            record_result["field_text"] = (aggregate_text_metrics([item["field_text"] for item in items])
                if all(isinstance(item.get("field_text"), dict) for item in items) else {})
            record_result["field_text"]["units"] = (
                sum(item["field_text"]["units"] for item in items)
                if all(type(item.get("field_text", {}).get("units")) is int for item in items) else None)
            record_result["whole_record_edit_distance"] = None
            record_result["field_unresolved_reasons"] = dict(sum(
                (Counter(item.get("field_unresolved_reasons", {})) for item in items), Counter()))
            record_result["field_unresolved_diagnoses"] = dict(sum(
                (Counter(item.get("field_unresolved_diagnoses", {})) for item in items), Counter()))
            record_result["field_error_reasons"] = dict(sum(
                (Counter(item.get("field_error_reasons", {})) for item in items), Counter()))
            combined[name] = record_result
        elif all("numerator" in item and "denominator" in item for item in items):
            combined[name] = fraction(
                sum(item["numerator"] for item in items), sum(item["denominator"] for item in items)
            )
            if any("observable" in item for item in items):
                combined[name]["observable"] = sum(item.get("observable", 0) for item in items)
        else:
            combined[name] = {"value": None, "reason": "not_an_automatically_aggregatable_metric"}
    return combined


def _rates(metrics: dict[str, Any], prefix: str = "") -> dict[str, float | None]:
    rates: dict[str, float | None] = {}
    for key, value in metrics.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            rates.update(_rates(value, path))
        elif key in _SCALAR_RATES:
            rates[path] = value if _finite_number(value) else None
    return rates


def _macro(groups: list[dict[str, Any]]) -> dict[str, Any]:
    scalars = [_rates(group) for group in groups]
    keys = sorted({key for item in scalars for key in item})
    output = {}
    for key in keys:
        values = [value for item in scalars if (value := item.get(key)) is not None]
        output[key] = {
            "value": statistics.fmean(values) if values else None,
            "available_groups": len(values), "total_groups": len(groups),
        }
    return output


def _path_value(record: dict[str, Any], path: str) -> Any:
    value: Any = record
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _quality_slices(items: list[dict[str, Any]], pipeline: str, dataset: str,
                    suite: str, quality: dict[str, Any]) -> list[dict[str, Any]]:
    """Project the existing micro and document-macro definitions into flat rows."""
    if "perf" in suite.lower() or quality["status"] == "duplicate_quality_runs_require_explicit_run_selection":
        return []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        keys = (
            ("sample", str(item.get("sample_id") or "unknown_sample")),
            ("document", str(item.get("document_id") or "unknown_document")),
            ("family", str(item.get("family_id") or "unknown_family")),
            ("source", str(item.get("source_category") or "source-unknown")),
            ("development_exposure", str(item.get("development_exposure") or "unknown")),
            *(("tag", str(tag)) for tag in dict.fromkeys(item.get("tags", []))),
        )
        for group_key in keys:
            grouped[group_key].append(item)
    rows = []
    for (scope, key), members in sorted(grouped.items()):
        micro = _micro(members)
        documents: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in members:
            documents[str(item.get("document_id") or "unknown_document")].append(item)
        macro = _macro([_micro(values) for values in documents.values()])
        row: dict[str, Any] = {column: None for column in QUALITY_SLICE_COLUMNS}
        page_counts = [item.get("input_page_count") for item in members]
        row.update(
            pipeline=pipeline, dataset=dataset, suite=suite, scope=scope, scope_key=key,
            quality_status=("evaluated" if all(item.get("scorer_status") == "evaluated" for item in members)
                            else "partially_evaluated" if any(item.get("scorer_status") == "evaluated" for item in members)
                            else "not_scored"),
            samples=len(members), documents=len(documents),
            input_pages=sum(value for value in page_counts if isinstance(value, int))
            if all(type(value) is int and value > 0 for value in page_counts) else None,
            failed_samples=sum(item.get("status") not in _SUCCESS for item in members),
            unscored_samples=sum(item.get("scorer_status") != "evaluated" for item in members),
        )
        # Sum only existing direct processing measurements, including failed
        # attempts. A missing measurement never becomes zero or a full cost.
        durations = [item.get("timing", {}).get("processing_seconds") for item in members]
        known_durations = [value for value in durations if _finite_number(value) and value > 0]
        complete = len(known_durations) == len(members)
        subtotal = sum(known_durations) if known_durations else None
        successful_pages = [item.get("input_page_count") for item in members if item.get("status") in _SUCCESS]
        completed_pages: int | None = sum(value for value in successful_pages if type(value) is int)
        if not all(type(value) is int and value > 0 for value in successful_pages):
            completed_pages = None
        row.update(
            observed_processing_seconds_subtotal=subtotal,
            processing_seconds_including_failures=subtotal if complete else None,
            observed_processing_samples=len(known_durations),
            missing_processing_samples=len(members) - len(known_durations),
            timing_complete=complete, completed_input_pages=completed_pages,
            seconds_per_attempted_input_page=(subtotal / row["input_pages"]
                if complete and subtotal and row["input_pages"] else None),
            completed_pages_per_second_including_failure_cost=(completed_pages / subtotal
                if complete and subtotal and completed_pages is not None else None),
        )
        for name in (*_SLICE_COVERAGE, "text_aligned_reference_chars"):
            values = [item.get("coverage", {}).get(name) for item in members]
            known = [value for value in values if _finite_number(value)]
            row[name] = sum(known) if known else None
        for column, path in {
            "text_reference_chars": "text.strict.reference_chars",
            "content_targets": "unit_presence.target_units", "content_located": "unit_presence.tp",
            "table_field_targets": "table_records.field_target_correctness.denominator",
            "table_field_correct": "table_records.field_target_correctness.numerator",
            "table_fields_observable": "table_records.observable_fields",
            "table_fields_compared": "table_records.compared_fields",
            "table_fields_missing": "table_records.target_missing_fields",
            "table_fields_unresolved": "table_records.unresolved_fields",
            "table_information_correct": "table_records.information_correct_fields",
            "table_information_incorrect": "table_records.information_incorrect_fields",
            "relation_targets": "relations.by_type.before.denominator", "relation_correct": "relations.by_type.before.numerator",
            "relation_observable": "relations.by_type.before.observable", "relation_unresolved": "relations.by_type.before.endpoint_unresolved",
        }.items():
            row[column] = _path_value(micro, path)
        for name, path in _SLICE_METRICS.items():
            row[name] = _path_value(micro, path)
            entry = macro.get(path, {})
            row[f"macro_document_{name}"] = entry.get("value")
            row[f"macro_document_{name}_available_documents"] = entry.get("available_groups")
            row[f"macro_document_{name}_total_documents"] = entry.get("total_groups")
        rows.append(row)
    return rows


def _quality(results: list[dict[str, Any]], suite: str) -> dict[str, Any]:
    if "perf" in suite.lower():
        return {"status": "performance_repetitions_not_pooled_into_quality800", "metrics": None}
    sample_counts: dict[str, int] = defaultdict(int)
    for result in results:
        sample_counts[str(result.get("sample_id"))] += 1
    duplicate_samples = {key: count for key, count in sample_counts.items() if count > 1}
    if duplicate_samples:
        return {
            "status": "duplicate_quality_runs_require_explicit_run_selection",
            "duplicate_samples": duplicate_samples, "metrics": None,
        }
    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_exposure: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_document[str(result.get("document_id") or "unknown_document")].append(result)
        by_family[str(result.get("family_id") or "unknown_family")].append(result)
        by_source[str(result.get("source_category") or "source-unknown")].append(result)
        by_exposure[str(result.get("development_exposure") or "unknown")].append(result)
        for tag in dict.fromkeys(result.get("tags", [])):
            by_tag[str(tag)].append(result)
    document_metrics = {key: _micro(items) for key, items in by_document.items()}
    family_metrics = {key: _micro(items) for key, items in by_family.items()}

    def groups(grouping: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        output = {}
        for key, items in sorted(grouping.items()):
            documents = sorted({str(item.get("document_id") or "unknown_document") for item in items})
            local_document_metrics = [
                _micro([item for item in items if str(item.get("document_id") or "unknown_document") == document])
                for document in documents
            ]
            output[key] = {
                "samples": len(items), "documents": len(documents),
                "input_pages": sum(item.get("input_page_count", 0) or 0 for item in items),
                "micro": _micro(items), "macro_by_document": _macro(local_document_metrics),
            }
        return output

    return {
        "status": "evaluated" if results and all(result.get("scorer_status") == "evaluated" for result in results)
                  else "partially_evaluated" if any(result.get("scorer_status") == "evaluated" for result in results)
                  else "not_scored", "samples": len(results),
        "input_pages": sum(result.get("input_page_count", 0) or 0 for result in results),
        "documents": len(by_document), "families": len(by_family),
        "micro": _micro(results),
        "macro_by_sample": _macro([result.get("metrics", {}) for result in results]),
        "macro_by_document": _macro(list(document_metrics.values())),
        "macro_by_family": _macro(list(family_metrics.values())),
        "by_document": groups(by_document), "by_family": groups(by_family), "by_tag": groups(by_tag),
        "by_source_category": groups(by_source),
        "by_development_exposure": groups(by_exposure),
        "failed_samples": sum(result.get("status") not in _SUCCESS for result in results),
        "unscored_samples": sum(result.get("scorer_status") != "evaluated" for result in results),
        "status_counts": dict(Counter(str(result.get("status", "unknown")) for result in results)),
        "excluded_reference_units": dict(sum(
            (Counter(result.get("coverage", {}).get("excluded_units", {})) for result in results),
            Counter(),
        )),
        "coverage": {
            key: sum(result.get("coverage", {}).get(key, 0) for result in results)
            for key in (
                "declared_units", "confirmed_units", "scored_units", "localized_units",
                "ambiguous_units", "unresolved_units", "not_localized_units", "table_record_targets",
                "table_record_located", "declared_relations", "scored_relations", "reference_unavailable_relations",
                "localization_only_units", "localized_anchors",
                "text_reference_units", "text_aligned_units", "text_reference_chars", "text_aligned_reference_chars",
                "known_image_targets", "image_automatic_identity_targets", "image_output_visual_review_targets",
                "declared_field_pair_bindings", "reference_unavailable_field_pair_bindings",
            )
        },
    }


def _performance(results: list[dict[str, Any]]) -> dict[str, Any]:
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


def aggregate_reports(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Keep each pipeline, dataset and run suite separate, with explicit NA."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        key = (
            str(result.get("pipeline") or "unspecified"),
            str(result.get("dataset") or "unspecified"),
            str(result.get("suite") or "unspecified"),
        )
        grouped[key].append(result)
    groups = []
    quality_slices = []
    for (pipeline, dataset, suite), items in sorted(grouped.items()):
        measured = [item for item in items if item.get("phase", "measured") in {"measured", "preflight"}]
        quality = _quality(measured, suite)
        groups.append({
            "pipeline": pipeline, "dataset": dataset, "suite": suite,
            "quality": quality, "performance": _performance(items),
            "runtime_records": [{
                "sample_id": item.get("sample_id"), "phase": item.get("phase", "measured"),
                "repetition": item.get("repetition"), "run_id": item.get("run_id"),
                "runtime": item.get("runtime"),
            } for item in items],
        })
        quality_slices.extend(_quality_slices(measured, pipeline, dataset, suite, quality))
    return {
        "groups": groups,
        "quality_slices": quality_slices,
        "weighted_total_score": None,
        "notes": [
            "NA is unmeasured or unsupported, never a correct answer or zero cost.",
            "Quality denominators retain failed outputs and unresolved target coverage.",
            "Document/family/tag groups overlap and must not be added together.",
            "Family labels do not establish independence of related issuers or development exposure.",
            "Tag page totals are input pages of member samples, not independently exhaustive page labels; overlapping tags are not additive.",
            "Performance repetitions do not create independent document samples.",
        ],
    }


def _display(value: Any) -> str:
    return f"{value:.4f}" if _finite_number(value) else "NA"


def _cell(value: Any) -> str:
    return str(value if value is not None else "NA").replace("|", "\\|").replace("\n", " ")


def render_quality_slices(report: dict[str, Any]) -> str:
    """Readable projection of the flat comparisons; never choose a quality run."""
    lines = [
        "# MO-Parse 分组质量与成本对照", "",
        "以下使用同一冻结评分定义和已有分母，不计算加权总分。perf重复与预热不进入质量切片；存在重复质量运行的组保持阻断，不任选一轮。NA为缺测或没有适用目标。", "",
        "表内为微平均；文档宏平均CER及可用文档数另列。各项文档宏平均、各自可用文档分母和完整覆盖计数见[扁平对照CSV](quality-slices.csv)。失败与未评分数量同时保留，已知分母不能冒充未评分范围的完整分母。标签页数是成员样本输入页数，标签重叠、各分组及各配置不得相加为语料总量。", "",
        "strict_cer为保留全部已知目标的保守字符口径，未唯一定位参考暂作删除；不能据此断定所有未定位文字均被解析器遗漏。已对齐条件字符成绩及其覆盖另见主报告与summary.json，不把定位成功率当逐字准确率。", "",
        "成本使用同一质量切片成员已有的直接processing_seconds，含已测失败成本，不混入perf重复、初始化或预热。完整秒要求所有成员均有有效计时；缺测时只列已测小计，秒/计划输入页与完成页/秒均为NA。完成页只计完整成功样本的输入页，不能代表部分样本的实际产出页；缺测或未启动不填零。标签及其他重叠切片成本不可相加。", "",
        "[返回主报告](report.md)", "",
    ]
    rows = report.get("quality_slices", [])
    for scope, label in (
        ("source", "来源类别"), ("tag", "内容标签"),
        ("development_exposure", "开发暴露"), ("family", "文档家族"),
        ("document", "原文档"), ("sample", "样本"),
    ):
        lines.extend([f'<a id="{scope.replace("_", "-")}"></a>', "", f"## {label}", ""])
        members = sorted(
            (row for row in rows if row["scope"] == scope),
            key=lambda row: (row["dataset"], row["suite"], row["scope_key"], row["pipeline"]),
        )
        if not members:
            lines.extend(["NA：没有可比较的质量切片；阻断与未测状态见主报告和summary.json。", ""])
            continue
        lines.extend([
            "| 分组 | 数据集 / suite | 配置 | 样本 / 文档 / 输入页 | 失败 / 未评分 | 定位R（命中/目标） | 严格CER（参考字符） | 编辑相似度 | 值与标签全目标正确率 | 完整信息全目标正确率 | 完整信息正确 / 错误 | 阅读顺序工程诊断 | 文档宏CER（可用/总文档） | 成本：完整/已测秒；计时覆盖；完成页；秒/计划页；完成页/秒 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for row in members:
            values = [
                row["scope_key"], f"{row['dataset']} / {row['suite']}", row["pipeline"],
                f"{row['samples']} / {row['documents']} / {_cell(row['input_pages'])}",
                f"{row['failed_samples']} / {row['unscored_samples']}",
                f"{_display(row['content_recall'])} ({_cell(row['content_located'])}/{_cell(row['content_targets'])})",
                f"{_display(row['strict_cer'])} ({_cell(row['text_reference_chars'])})",
                _display(row["strict_edit_similarity"]),
                f"{_display(row['table_field_target_correctness'])} ({_cell(row['table_field_correct'])}/{_cell(row['table_field_targets'])})",
                f"{_display(row.get('information_target_correctness'))} ({_cell(row.get('table_information_correct'))}/{_cell(row.get('table_field_targets'))})",
                f"{_cell(row.get('table_information_correct'))} / {_cell(row.get('table_information_incorrect'))}",
                f"{_display(row['relation_recall'])} ({_cell(row['relation_correct'])}/{_cell(row['relation_targets'])})",
                f"{_display(row['macro_document_strict_cer'])} ({_cell(row['macro_document_strict_cer_available_documents'])}/{_cell(row['macro_document_strict_cer_total_documents'])})",
                f"{_display(row.get('processing_seconds_including_failures'))}/{_display(row.get('observed_processing_seconds_subtotal'))}；"
                f"{_cell(row.get('observed_processing_samples'))}/{row['samples']}（缺{_cell(row.get('missing_processing_samples'))}）；"
                f"{_cell(row.get('completed_input_pages'))}；"
                f"{_display(row.get('seconds_per_attempted_input_page'))}；"
                f"{_display(row.get('completed_pages_per_second_including_failure_cost'))}",
            ]
            lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
        lines.append("")
    return "\n".join(lines)


def _declaration_lines(report: dict[str, Any]) -> list[str]:
    declaration = report.get("dataset_declaration")
    if not declaration:
        return []
    metadata = declaration.get("sample_metadata") or {}
    suites = declaration.get("suites") or {}
    freeze_record = declaration.get("freeze_record") or {}
    global_exposure = freeze_record.get("development_exposure") if isinstance(freeze_record, dict) else None
    lines = [
        "## 冻结声明与评分覆盖", "",
        f"数据集：{_cell(declaration.get('name'))}；类型：{_cell(declaration.get('kind'))}；声明状态：{_cell(declaration.get('state'))}；冻结记录：{'已提供' if declaration.get('freeze_record') else '未提供'}。", "",
        f"冻结记录的全局开发暴露声明：{_cell(global_exposure or 'unknown')}。", "",
        "全局声明与逐样本历史暴露分层保留；单样本历史暴露unknown不代表未见，不据此补写样本属性或认定文档家族独立。", "",
        "以下是冻结清单声明属性与已有评分覆盖的报告投影，不是重新验收语料，不证明未见页面已目读或参考完整。各suite可能重叠，输入页及样本数不可跨suite、八配置或性能轮次累加。", "",
        "| 声明suite | 样本身份数 | 已知原文档 | 已知家族 | 已知输入页 | 元数据缺失样本 | 页数未知样本 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    def declared_members(ids: Iterable[str]) -> list[dict[str, Any]]:
        return [metadata.get(ident) or {} for ident in dict.fromkeys(ids)]

    def counts(members: list[dict[str, Any]]) -> tuple[int, int, int, int]:
        documents = {item["document_id"] for item in members if item.get("document_id")}
        families = {item["family_id"] for item in members if item.get("family_id")}
        pages = [item.get("input_page_count") for item in members]
        known = [value for value in pages if type(value) is int and value > 0]
        return len(documents), len(families), sum(known), len(pages) - len(known)

    declared_suites = suites or {"全部声明样本": list(metadata)}
    for suite, ids in sorted(declared_suites.items()):
        if not isinstance(ids, list):
            lines.append(f"| {_cell(suite)} | NA | NA | NA | NA | NA | NA |")
            continue
        members = declared_members(ids)
        documents, families, pages, unknown_pages = counts(members)
        lines.append(f"| {_cell(suite)} | {len(members)} | {documents} | {families} | {pages if members and unknown_pages < len(members) else 'NA'} | {sum(not item for item in members)} | {unknown_pages} |")
    primary = next((name for name in ("lite", "quality800") if isinstance(suites.get(name), list)), None)
    members = declared_members(suites[primary] if primary else metadata)
    lines.extend([
        "", f"下列分类分布范围：{_cell(primary or '全部声明样本')}，每个声明样本身份只计一次；标签是样本属性，不是对每一页穷尽分类。缺失或未声明的来源与开发暴露保持unknown，不依据外观或候选推断。", "",
        "| 声明维度 | 声明值 | 样本 | 已知原文档 | 已知家族 | 已知输入页 | 页数未知样本 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for field, label, unknown in (
        ("source_category", "来源类别", "source-unknown"),
        ("development_exposure", "开发暴露", "unknown"), ("tags", "内容标签", "untagged"),
    ):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in members:
            values = (item.get(field) or [unknown]) if field == "tags" else [item.get(field) or unknown]
            for value in dict.fromkeys(values):
                grouped[str(value)].append(item)
        for key, items in sorted(grouped.items()):
            documents, families, pages, unknown_pages = counts(items)
            lines.append(f"| {label} | {_cell(key)} | {len(items)} | {documents} | {families} | {pages if unknown_pages < len(items) else 'NA'} | {unknown_pages} |")
    lines.extend([
        "", "| 配置 / suite | 声明 / 确认 / 评分单元 | 定位 / 歧义 / 未解决 / 未定位 | 参考排除原因计数 | 未评分样本 |",
        "| --- | --- | --- | --- | --- |",
    ])
    for group in report.get("groups", []):
        if "perf" in group["suite"].lower() or not group["quality"].get("coverage"):
            continue
        quality, coverage = group["quality"], group["quality"]["coverage"]
        known_coverage = coverage if quality["status"] != "not_scored" else {}
        declared = " / ".join(_cell(known_coverage.get(key)) for key in ("declared_units", "confirmed_units", "scored_units"))
        located = " / ".join(_cell(known_coverage.get(key)) for key in ("localized_units", "ambiguous_units", "unresolved_units", "not_localized_units"))
        exclusions = quality.get("excluded_reference_units") if known_coverage else None
        lines.append(f"| {_cell(group['pipeline'])} / {_cell(group['suite'])} | {declared} | {located} | {_cell(exclusions)} | {_cell(quality.get('unscored_samples'))} |")
    lines.extend(["", "参考排除、定位歧义和未评分不是同一状态；缺少评分参考时，已知单元分母不能代表该样本全部内容。图片输出的视觉保全覆盖另列，未测内容不计为正确。", ""])
    return lines


def _runtime_delivery_lines(report: dict[str, Any]) -> list[str]:
    inspection = report.get("software_inspection") or {}
    record = inspection.get("record") or {}
    checked = record.get("pipelines") or {}
    evidence = report.get("runtime_evidence") or {}
    names = sorted(set(checked) | set(evidence) | {
        config["pipeline"] for config in ((report.get("execution") or {}).get("configurations") or [])
    } | {group["pipeline"] for group in report.get("groups", [])})
    if not names:
        return []
    lines = [
        "## 实际环境证据与初始化成本", "",
        "声明的软件、模型revision和资源预算见run.json；下表把后验不可变镜像检查与原执行记录区分。后验包版本不是逐样本版本测量，也不证明模型推理成功；CPU worker与独立GPU服务环境分别列出，缺测为NA。", "",
    ]
    if inspection:
        lines.extend([
            f"软件检查时间：{_cell(record.get('inspected_at'))}；范围：{_cell(record.get('scope'))}；[检查记录]({_cell(inspection.get('path'))})。", "",
        ])
    lines.extend([
        "| 配置 | 镜像角色 | 后验镜像ID | 后验包版本 | 已记录模型名 |",
        "| --- | --- | --- | --- | --- |",
    ])
    for name in names:
        prepared = checked.get(name) or {}
        entries = [{"role": "CPU worker", "image_id": prepared.get("image_id"), "versions": prepared.get("versions")},
                   *(prepared.get("inference") or [])]
        if len(entries) == 1:
            entries.append({"role": "GPU inference service"})
        for entry in entries:
            versions = entry.get("versions")
            version_text = "; ".join(f"{key}={_cell(value)}" for key, value in sorted(versions.items())) if versions else "NA"
            lines.append("| " + " | ".join(_cell(value) for value in (
                name, entry.get("role"), entry.get("image_id"), version_text, entry.get("model_name"),
            )) + " |")
    lines.extend([
        "", "| 配置 | GPU服务加载至ready秒 | 持久SDK初始化秒 | 共同预热已测处理秒 | 预热有计时 / 声明样本 | 服务初始化状态 |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for name in names:
        lifecycle = ((evidence.get(name) or {}).get("inference_lifecycle") or {}).get("record") or {}
        initializations: dict[Any, Any] = {}
        warmups: dict[Any, dict[str, Any]] = {}
        for group in report.get("groups", []):
            if group["pipeline"] != name:
                continue
            performance = group.get("performance") or {}
            for item in performance.get("initialization", []):
                value = item.get("initialization_seconds")
                if _finite_number(value):
                    initializations[item.get("run_id")] = value
            for item in performance.get("warmup", []):
                warmups[(item.get("run_id"), item.get("sample_id"), item.get("repetition"))] = item
        known_warmups = [item["processing_seconds"] for item in warmups.values() if _finite_number(item.get("processing_seconds"))]
        lines.append("| " + " | ".join(_cell(value) for value in (
            name, _display(lifecycle.get("initialization_to_readiness_host_seconds")),
            _display(sum(initializations.values())) if initializations else "NA",
            _display(sum(known_warmups)) if known_warmups else "NA",
            f"{len(known_warmups)} / {len(warmups)}" if warmups else "NA",
            lifecycle.get("initialization_status"),
        )) + " |")
    lines.extend([
        "", "SDK初始化按持久worker的run_id去重；预热只汇总warmup阶段已测处理时间，未计时项不填零。服务加载为生命周期直接记录，未将并行容器时长相加。以上成本与正式worker处理耗时分列，runtime_records中的编排元数据不作为主处理耗时。", "",
    ])
    return lines


def render_markdown(report: dict[str, Any], figures: list[dict[str, Any]] | None = None) -> str:
    """Render the reader-facing comparison; keep full evidence in the appendix."""
    from .report_overview import render_overview

    return render_overview(report, figures)


def _tts_condition_lines(report: dict[str, Any]) -> list[str]:
    maintenance = report.get("maintenance") or {}
    observe_only = maintenance.get("tts_observation_policy") == "observe_only"
    identity = maintenance.get("tts_identity_condition") or {}
    calls = maintenance.get("tts_no_calls_condition") or {}
    identity = identity if isinstance(identity, dict) else {}
    calls = calls if isinstance(calls, dict) else {}
    identity_status, calls_status = identity.get("status"), calls.get("status")
    identity_status = identity_status if isinstance(identity_status, str) and identity_status else None
    calls_status = calls_status if isinstance(calls_status, str) and calls_status else None
    lines = [
        "## TTS测量条件与服务恢复", "",
        f"TTS观测政策：{_cell(maintenance.get('tts_observation_policy'))}；政策来自本次保存的维护记录，不从当前环境推断。", "",
        "| 维护恢复状态 | TTS策略 | 调用声明或策略 | 身份观测 | " + ("活动观测" if observe_only else "无调用观测") + " |",
        "| --- | --- | --- | --- | --- |",
        f"| {_cell(maintenance.get('phase'))} | {_cell(maintenance.get('tts_policy'))} | "
        f"{_cell(maintenance.get('tts_calls'))} | {_cell(identity_status)} | {_cell(calls_status)} |", "",
        "| TTS身份字段 | 窗口前 | 窗口后 | 首次变化后 |",
        "| --- | --- | --- | --- |",
    ]
    for key in ("MainPID", "InvocationID"):
        values = [identity.get(stage) or {} for stage in ("before", "after", "first_changed_after")]
        cells = [_cell(value.get(key) if isinstance(value, dict) else None) for value in values]
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    changed = identity.get("changed_keys")
    changed_label = (", ".join(str(key) for key in changed) or "[]") if isinstance(changed, list) else None
    lines.extend([
        "", f"身份变化字段：{_cell(changed_label)}；身份观测口径：{_cell(identity.get('scope'))}。", "",
        "| TTS活动观测项 | 窗口前 | 窗口后 |",
        "| --- | --- | --- |",
    ])
    for key in ("active_job", "persistent_active_jobs", "job_count"):
        values = [calls.get(stage) or {} for stage in ("before", "after")]
        cells = [_cell(value.get(key) if isinstance(value, dict) else None) for value in values]
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    lines.extend([
        "", f"已观测新任务计数差：{_cell(calls.get('observed_new_jobs'))}；观测原因：{_cell(calls.get('reason'))}。", "",
        f"记录的观测限制：{_cell(calls.get('limitation'))}。", "",
        "`user_declared_none`仅是当时的用户声明，不能当作无调用事实，也不能覆盖本次保存的观测政策。身份和活动状态来自实际维护观测，缺失为NA。起末健康与持久任务计数没有原子禁止新调用，短调用、非持久请求或保留期清理可能使计数不能证明全程无调用；计数减少记unknown，不据此判为有调用。", "",
    ])
    if observe_only:
        lines.extend([
            "observe_only下TTS保持运行，评测不控制其活动；身份变化、已观测调用和unknown只作披露，不自动判性能无效或阻止报告。性能读数代表实际共驻条件，变化可能干扰耗时和资源，不能据此推断GPU独占条件下的速度排名或确定全程无调用。", "",
            "MO-Parse恢复健康与TTS观测独立记录；已观察到的身份变化即使后续回到原身份也仍保留changed，不把unknown或NA改写为无活动。", "",
        ])
    else:
        lines.extend([
            "旧严格记录中的unknown或NA不能解释为条件满足。TTS身份changed或无调用条件violated独立于MO-Parse恢复结果：恢复为restored、服务健康不能使已违反的性能测量条件重新有效；已观察到的身份变化即使后续回到原身份也仍保留changed。", "",
        ])
    return lines


def render_appendix(report: dict[str, Any]) -> str:
    """Render complete measurements with denominators and unresolved coverage."""
    lines = ["# 附录：完整指标与运行证据", "", "[返回图文主报告](report.md)。本附录保留完整指标、分母、声明分布、执行身份和运行证据；各项质量与成本分开呈现，不计算加权总分。机器明细见[汇总](summary.json)、[运行身份](run.json)及各评分产物。", ""]
    lines.extend([
        "可读切片：[来源类别](group-comparisons.md#source)、[内容标签](group-comparisons.md#tag)、[开发暴露](group-comparisons.md#development-exposure)、[原文档](group-comparisons.md#document)、[家族](group-comparisons.md#family)、[逐样本](group-comparisons.md#sample)；[扁平质量对照CSV](quality-slices.csv)。", "",
    ])
    lines.extend(["## 字符诊断与平均口径", "",
                  "目标CER将未定位参考暂作删除，仅用于定位与文字差异诊断，不是全文OCR错误率或主排名。正文主表使用已定位CER并同时披露覆盖；下面保留目标CER的字符、文档、家族平均对照。", "",
                  "![目标CER的平均口径](figures/averaging.png)", "",
                  "[SVG](figures/averaging.svg) · [PDF](figures/averaging.pdf)", ""])
    lines.extend(["## 字段错误原因", "",
                  "每个已纳入字段已完成正确或错误判定。错误原因区分缺失、数值不符、业务归属和限定语不符；不据此判断原件有误。软件读取故障不发布为质量成绩。逐字段证据见[field-details.csv](field-details.csv)及本次评分产物。", "",
                  "| 配置 | 错误原因 | 字段数 |", "| --- | --- | ---: |"])
    for group in report.get("groups", []):
        if group.get("suite") == "quality800":
            for reason, count in sorted(group.get("quality", {}).get("micro", {}).get("table_records", {}).get("field_error_reasons", {}).items()):
                lines.append(f"| {group['pipeline']} | {reason} | {count} |")
    lines.append("")
    if report.get("qualitative_review"):
        lines.extend([
            f"来源直接目读的有限个案及适用边界见[人工个案记录]({report['qualitative_review']})；不将这些个案扩展为全量质量或图片保全成绩。", "",
        ])
    if report.get("execution_failure_notes"):
        lines.extend([
            f"完整失败和未处理范围另见[执行失败记录]({report['execution_failure_notes']})。", "",
        ])
    if report.get("scoring_notes"):
        lines.extend([
            f"冻结标准与后续评分实现修复的区别见[评分实现说明]({report['scoring_notes']})。", "",
        ])
    adjudications = report.get("reference_adjudications")
    if adjudications:
        decisions = adjudications["record"].get("decisions", [])
        applied = adjudications.get("applied_decision_ids", [])
        unmatched = adjudications.get("unmatched_decision_ids", [])
        lines.extend([
            f"本轮提交{len(decisions)}条来源直接目读支持的参考待判排除，实际生效{len(applied)}条，未命中可评分样本{len(unmatched)}条；规则统一用于全部配置与重复轮次，冻结参考及索引不改写。人工判断、原页证据与生效范围见[评分裁定快照]({adjudications['path']})，逐项分母保留排除原因。", "",
        ])
    execution = report.get("execution", {})
    if execution:
        lines.extend([
            f"运行：{execution.get('run_id')}；编排状态：{execution.get('state')}；正式评测：{execution.get('formal')}。编排结束不表示全部解析成功。", "",
            "quality800计划每组一次正式运行（n=1），实际完成、部分输出、失败与未处理范围逐组保留；perf80计划另测三轮，实际完整计时轮数单列。预检不能作为800页排名。", "",
            "各suite引用同一持久worker的初始化记录，该成本只发生一次，不能跨suite重复相加；GPU服务加载及共同预热另外保留。", "",
        ])
        mixed_execution = bool(execution.get("execution_sources"))
        if mixed_execution:
            lines.extend([composition_markdown(execution), ""])
        if report.get("score_index"):
            scoring_id = (report.get("scoring_software") or {}).get("software_id", "未记录")
            if mixed_execution:
                identity_text = f"执行软件按上表逐管线保留；本轮八配置统一评分软件身份：{scoring_id}。"
            else:
                execution_id = (execution.get("software") or {}).get("software_id") or "未记录"
                identity_text = f"执行软件身份：{execution_id}；评分软件身份：{scoring_id}。"
            lines.extend([
                f"{identity_text}完整身份、源码快照与裁定生效明细见[本次评分索引]({report['score_index']})；重评分不会替换原生产物或原执行记录。", "",
            ])
        configurations = execution.get("configurations") or []
        if configurations:
            lines.extend(["| 配置 | 锁定模型revision | 执行记录 |", "| --- | --- | --- |"])
            observed = {group["pipeline"] for group in report.get("groups", [])}
            for config in configurations:
                name = config["pipeline"]
                revisions = "; ".join(f"{key}={value}" for key, value in config.get("revisions", {}).items())
                quality_group = next((group for group in report.get("groups", [])
                                      if group["pipeline"] == name and group["suite"] == "quality800"), None)
                if quality_group:
                    quality = quality_group["quality"]
                    samples, failed = quality.get("samples"), quality.get("failed_samples")
                    completed = samples - failed if _finite_number(samples) and _finite_number(failed) else None
                    state = (f"质量样本{_cell(samples)}，完成{_cell(completed)}，"
                             f"失败/部分/未处理{_cell(failed)}；状态分布{quality.get('status_counts', {})}")
                else:
                    state = "有样本产物，查看对应范围" if name in observed else "无样本产物，查看准备失败证据"
                lines.append(f"| {name} | {revisions or '见run.json'} | {state} |")
            lines.extend(["", "软件、镜像、解码参数和资源锁见run.json；实际容器、模型启动、CUDA Graphs试验与资源记录见summary.json的runtime_evidence。声明锁定与实际成功执行分别记录。", ""])
        failures = execution.get("errors") or []
        if failures:
            lines.extend(["| 配置 | 失败类型 | 原因 |", "| --- | --- | --- |"])
            for failure in failures:
                reason = str(failure.get("message", "")).replace("|", "\\|").replace("\n", " ")
                lines.append(f"| {failure.get('pipeline', '运行')} | {failure.get('type', 'unknown')} | {reason} |")
            lines.append("")
        maintenance = report.get("maintenance") or {}
        if maintenance:
            if mixed_execution:
                lines.extend(["组合目录未新开维护窗口；各源窗口的恢复状态和原始快照见上表，maintenance.json保存两次源窗口索引。", ""])
            else:
                lines.extend([f"维护恢复状态：{maintenance.get('phase', 'unknown')}；TTS策略：{_cell(maintenance.get('tts_policy'))}；TTS调用条件：{_cell(maintenance.get('tts_calls'))}；详情见maintenance.json。", ""])
    lines.extend(_tts_condition_lines(report))

    def display(value: Any) -> str:
        return f"{value:.4f}" if _finite_number(value) else "NA"

    quality_groups = {
        (group["dataset"], group["pipeline"]): group
        for group in report.get("groups", []) if group["suite"] == "quality800"
    }
    performance_groups = {
        (group["dataset"], group["pipeline"]): group
        for group in report.get("groups", []) if group["suite"] == "perf80"
    }
    datasets = sorted({key[0] for key in quality_groups})
    if not datasets and execution.get("dataset_name"):
        datasets = [execution["dataset_name"]]
    declared_pipelines = {config["pipeline"] for config in execution.get("configurations") or []}
    for dataset in datasets:
        pipelines = sorted(declared_pipelines | {key[1] for key in quality_groups if key[0] == dataset})
        lines.extend([
            f"## 质量与成本对照 · {dataset}", "",
            "| 配置 | 完整样本页/计划输入页 | 内容定位R | 目标保守CER | 已对齐参考字符/目标字符 | 值与标签全目标正确率 | 完整信息全目标正确率 | 阅读顺序before满足率 | quality800秒 / 完整计时轮数 | perf80中位秒 / 完整计时轮数 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for name in pipelines:
            quality_group = quality_groups.get((dataset, name), {})
            quality = quality_group.get("quality", {})
            micro = quality.get("micro", {})
            coverage = quality.get("coverage", {})
            processing = quality_group.get("performance", {})
            rounds = processing.get("rounds", [])
            first_round = rounds[0] if len(rounds) == 1 else {}
            round_summary = processing.get("round_duration_summary", {})
            perf_summary = performance_groups.get((dataset, name), {}).get("performance", {}).get("round_duration_summary", {})
            completed, attempted = first_round.get("completed_input_pages"), first_round.get("attempted_input_pages")
            page_label = f"{completed}/{attempted}" if completed is not None and attempted is not None else "NA"
            aligned, total = coverage.get("text_aligned_reference_chars"), coverage.get("text_reference_chars")
            char_label = f"{aligned}/{total}" if aligned is not None and total is not None else "NA"
            table = table_field_breakdown(micro.get("table_records"))
            lines.append(
                f"| {name} | {page_label} | {display(micro.get('unit_presence', {}).get('recall'))} | "
                f"{display(micro.get('text', {}).get('strict', {}).get('cer'))} | {char_label} | "
                f"{display(table['field_target_correctness']['value'])} | "
                f"{display(table['information_target_correctness']['value'])} | "
                f"{display(micro.get('relations', {}).get('by_type', {}).get('before', {}).get('value'))} | "
                f"{display(round_summary.get('median_seconds'))} / {_cell(round_summary.get('n'))} | "
                f"{display(perf_summary.get('median_seconds'))} / {_cell(perf_summary.get('n'))} |"
            )
        lines.extend([
            "", "内容定位R不等于逐字准确；目标CER含未定位参考的保守删除，条件字符准确率及覆盖见各组明细。表格字段只覆盖独立标注字段。完整样本页只计执行流程全部完成的样本，不表示内容正确或关系齐全，也不包括部分样本的已处理页；计划输入页保留尚未启动的样本。失败处理成本保留，缺测为NA；800页一次与80页三轮分开，重复轮次不增加独立文档样本。", "",
        ])

    lines.extend(_declaration_lines(report))
    lines.extend(_runtime_delivery_lines(report))
    for group in report.get("groups", []):
        lines.extend([
            f"## {group['pipeline']} · {group['dataset']} · {group['suite']}", "",
            f"质量状态：{group['quality']['status']}。", "",
        ])
        quality = group["quality"]
        if quality.get("micro"):
            lines.extend(["| 指标 | 值 | 分母 |", "| --- | --- | --- |"])
            for name in ("unit_presence", "unit_exact", "field_exact", "field_pair_binding", "table_grid", "table_binding"):
                metric = quality["micro"].get(name, {})
                value = metric.get("recall", metric.get("value"))
                denominator = metric.get("target_units", metric.get("denominator"))
                label = display(value)
                lines.append(f"| {name} | {label} | {_cell(denominator)} |")
            for name in ("text", "text_aligned", "field_text", "table_cell_text"):
                metric = quality["micro"].get(name, {}).get("strict", {})
                lines.append(f"| {name} 严格CER | {display(metric.get('cer'))} | {_cell(metric.get('reference_chars'))}字符 |")
                lines.append(f"| {name} 编辑相似度 | {display(metric.get('similarity'))} | max字符长度 |")
                equivalent = quality["micro"].get(name, {}).get("width_equivalent", {})
                lines.append(f"| {name} 排版等价CER | {display(equivalent.get('cer'))} | {_cell(equivalent.get('reference_chars'))}字符 |")
                lines.append(f"| {name} 排版等价编辑相似度 | {display(equivalent.get('similarity'))} | max字符长度 |")
            records = quality["micro"].get("table_records", {})
            for name in ("field_target_correctness", "field_compared_accuracy", "field_comparison_coverage",
                         "field_strict_accuracy", "field_strict_target_correctness", "field_coverage",
                         "binding", "binding_target_coverage", "blank_fields",
                         "information_target_correctness", "information_compared_accuracy"):
                metric = records.get(name, {})
                lines.append(f"| table_records.{name} | {display(metric.get('value'))} | {_cell(metric.get('denominator'))} |")
            for name in ("target_fields", "compared_fields", "target_missing_fields", "unresolved_fields",
                         "correct_fields", "strict_correct_fields", "observable_fields",
                         "information_correct_fields", "information_incorrect_fields", "information_unresolved_fields"):
                lines.append(f"| table_records.{name} | {_cell(records.get(name))} | 字段计数 |")
            for policy, label in (("strict", "严格"), ("width_equivalent", "排版等价")):
                field_text = records.get("field_text", {}).get(policy, {})
                lines.append(f"| table_records 已定位字段{label}CER | {display(field_text.get('cer'))} | {_cell(field_text.get('reference_chars'))}字符 |")
            relations = quality["micro"].get("relations", {})
            tp, fp, fn = (relations.get(key) for key in ("tp", "fp", "fn"))
            relation_denominators = {
                "precision": relations.get("output_units"),
                "recall": relations.get("target_units"),
                "f1": 2 * tp + fp + fn if all(_finite_number(value) for value in (tp, fp, fn)) else None,
            }
            for name in ("precision", "recall", "f1"):
                lines.append(f"| relations.{name} | {display(relations.get(name))} | {_cell(relation_denominators[name])} |")
            lines.append("")
            lines.extend([
                "原始关系字段仅作工程诊断，保存在机器评分记录中；它们不增加本轮 expected 业务信息的正确条件，也不发布读取状态类别作为质量成绩。", "",
            ])
            lines.extend([
                f"参考覆盖排除项：{quality.get('excluded_reference_units', {})}。未定位/歧义与已知遗漏分别保留在逐项记录中。", "",
                "text为保留全部已知目标的保守口径，未唯一定位的参考暂作删除；text_aligned仅评价已唯一定位单元的字符，需结合定位覆盖阅读。前者不能证明所有未定位文字都被解析器漏掉，后者不能代表全部目标准确率。未认领的额外输出由闭合评分范围的存在性precision单列，不加入段落CER。", "",
                "表格两项主指标采用全部固定目标作分母：field_target_correctness=correct_fields/target_fields，information_target_correctness=information_correct_fields/target_fields。每个已纳入目标均完成正确或错误判定，候选缺失或业务归属不满足计入错误并保留具体原因；软件读取故障必须修复后重评，不能直接转成候选错误。已定位字符指标只作严格转写诊断。", "",
                "relations.precision分母为output_units（TP+FP），recall分母为target_units（TP+FN），F1分母为2TP+FP+FN，仅在三个计数均已知时展示。非穷尽参考的全局precision和F1保持NA，不以闭合子范围或方向对分类成绩代填。缺失计数显示NA，明确为零的分母保留0；零分母的比率未定义，不能解释为零分。", "",
                f"状态分布：{quality.get('status_counts', {})}；无质量评分样本：{_cell(quality.get('unscored_samples'))}。图片字节保全需直接视觉证据，资产路径存在仅作为覆盖指标。", "",
                f"已确认图片目标：{_cell(quality.get('coverage', {}).get('known_image_targets'))}；可自动对应目标：{_cell(quality.get('coverage', {}).get('image_automatic_identity_targets'))}；纳入统一量化评分的输出视觉保全目标：{_cell(quality.get('coverage', {}).get('image_output_visual_review_targets'))}。不同资产名不判丢图，未视觉对应的图片保全保持未测；有限人工案例另列，不扩展为全量保全成绩。", "",
            ])
        performance = group["performance"]
        lines.extend([
            f"计划样本执行次数：{performance['scheduled_runs']}；有效计时：{performance['measured_runs']}；已计时完成：{performance['successful_runs']}；未完成（含部分、失败、未处理）：{performance['failed_runs']}；缺测：{len(performance['timing_unavailable'])}。",
            "",
        ])
        if performance.get("rounds"):
            lines.extend(["| 轮次 | 计划输入页 | 完整样本页 | 完整耗时（秒，含失败） | 已测处理秒小计 | 缺测样本数 | 完整样本页/秒（含失败成本） | 输入页平均处理秒（含失败成本） |", "| --- | --- | --- | --- | --- | --- | --- | --- |"])
            for row in performance["rounds"]:
                lines.append(
                    f"| {row['repetition']} | {row['attempted_input_pages']} | {row['completed_input_pages']} | "
                    f"{display(row['processing_seconds_including_failures'])} | "
                    f"{display(row.get('observed_processing_seconds_subtotal'))} | "
                    f"{row['measured_samples'] - row.get('observed_processing_samples', row['measured_samples'])} | "
                    f"{display(row['completed_pages_per_second_including_failure_cost'])} | "
                    f"{display(row['seconds_per_attempted_input_page'])} |"
                )
            lines.append("")
            summary = performance["round_duration_summary"]
            lines.extend([
                f"轮次n={summary['n']}；中位数{display(summary['median_seconds'])}秒；最小/最大{display(summary['min_seconds'])}/{display(summary['max_seconds'])}秒；变异系数{display(summary['coefficient_of_variation'])}。缺失耗时没有填零。输入页平均处理秒使用整样本处理耗时与计划输入页数，不是逐页延迟测量。", "",
            ])
        initialization = performance.get("initialization", [])
        warmup = performance.get("warmup", [])
        if initialization or warmup:
            init_total = sum(item.get("initialization_seconds", 0) for item in initialization)
            warmup_known = [item["processing_seconds"] for item in warmup if _finite_number(item.get("processing_seconds"))]
            lines.extend([
                f"持久SDK初始化：{display(init_total) if initialization else 'NA'}秒；预热处理已测合计：{display(sum(warmup_known)) if warmup_known else 'NA'}秒，{len(warmup_known)}/{len(warmup)}样本有计时。GPU服务加载另见生命周期记录。", "",
            ])
    if report.get("runtime_evidence"):
        exits = []
        for name, evidence in sorted(report["runtime_evidence"].items()):
            lifecycle = (evidence.get("inference_lifecycle") or {}).get("record") or {}
            for container in lifecycle.get("containers", []):
                state = container.get("terminal_state", {})
                if state.get("OOMKilled") or state.get("ExitCode") not in {None, 0}:
                    exits.append((name, container.get("name"), state, lifecycle.get("cleanup_confirmed")))
        if exits:
            lines.extend([
                "## 推理服务异常退出证据", "",
                "下表是本次完整执行服务的退出事实；单凭这些事实不能把根因归于模型、原生SDK或私有执行服务。原生结果、错误和未执行项保留，不自动重试或更改预算。", "",
                "| 配置 | 实验容器 | OOMKilled | ExitCode | 清理确认 |",
                "| --- | --- | --- | --- | --- |",
            ])
            for name, container, state, cleaned in exits:
                lines.append(f"| {name} | {container} | {state.get('OOMKilled')} | {state.get('ExitCode')} | {cleaned} |")
            lines.append("")
        lines.extend([
            "## 自有显存、TTS驻留与整卡余量", "",
            "| 配置 | 受测管线自有显存采样峰值（MiB） | GPU服务宿主内存采样峰值（GiB） | worker宿主内存采样峰值（GiB） |",
            "| --- | --- | --- | --- |",
        ])
        for name, evidence in sorted(report["runtime_evidence"].items()):
            inference = (evidence.get("inference_lifecycle_resources") or {}).get("record") or {}
            worker = (evidence.get("worker_lifecycle_resources") or {}).get("record") or {}
            gpu = inference.get("observed_owned_gpu_peak_memory_mib")
            host = inference.get("observed_shared_host_memory_peak_bytes")
            worker_host = worker.get("observed_shared_host_memory_peak_bytes")
            host_gib = host / 1024 ** 3 if isinstance(host, (int, float)) and _finite_number(host) else None
            worker_gib = (worker_host / 1024 ** 3
                          if isinstance(worker_host, (int, float)) and _finite_number(worker_host) else None)
            lines.append(
                f"| {name} | {display(gpu)} | {display(host_gib)} | {display(worker_gib)} |"
            )
        lines.append("")
        lines.extend([
            "| 配置 | 自有预算（GiB） | 整卡占用采样峰值（MiB） | TTS首次可归属占用（MiB） | TTS占用采样峰值（MiB） | 整卡最小可用余量（MiB） | 已观测自有预算超出 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for name, evidence in sorted(report["runtime_evidence"].items()):
            inference = (evidence.get("inference_lifecycle_resources") or {}).get("record") or {}
            values = [display(inference.get(field)) for field in (
                "owned_gpu_budget_gib", "observed_gpu1_peak_memory_mib",
                "tts_resident_baseline_memory_mib", "observed_tts_gpu_peak_memory_mib",
                "observed_gpu1_min_free_memory_mib",
            )]
            lines.append(f"| {_cell(name)} | " + " | ".join(values)
                         + f" | {_cell(inference.get('gpu_budget_exceeded_in_observed_samples'))} |")
        lines.extend([
            "", "自有显存是归属到本组受测容器及其compute子进程的同时聚合观测；预算比较只使用自有显存。整卡占用包含驻留TTS、其他进程及CUDA/驱动分配，只用于环境与余量观察，不能替代管线显存，也不通过减去TTS峰值推算。TTS首次值不是服务启动前基线；各项峰值和最小余量可能来自不同采样时刻，不能相加或相减。", "",
            "| 配置 | 资源记录 | 已记录自有容器身份 | TTS单位身份 | 自有 / 整卡 / TTS有效采样 | 全部采样 | 采样状态 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for name, evidence in sorted(report["runtime_evidence"].items()):
            resource = evidence.get("inference_lifecycle_resources") or {}
            inference = resource.get("record") or {}
            completeness = inference.get("sampling_completeness") or {}
            identities: dict[str, str] = {}
            tts_identities: set[str] = set()
            for sample in inference.get("samples", []):
                for container, identity in (sample.get("owned_gpu", {}).get("identities") or {}).items():
                    if isinstance(identity, dict):
                        identities[f"{container}:{identity.get('container_id')}:{identity.get('host_pid')}"] = (
                            f"{container}: id={identity.get('container_id')}, host_pid={identity.get('host_pid')}, "
                            f"cgroups={identity.get('cgroups')}"
                        )
                tts = sample.get("tts_gpu", {}).get("unit_identity") or {}
                if tts:
                    tts_identities.add(f"MainPID={tts.get('MainPID')}, ControlGroup={tts.get('ControlGroup')}, InvocationID={tts.get('InvocationID')}")
            counts = " / ".join(_cell(completeness.get(field)) for field in (
                "owned_gpu_memory_samples", "gpu_memory_samples", "tts_gpu_memory_samples"))
            path = resource.get("path")
            link = f"[记录]({_cell(path)})" if path else "NA"
            lines.append(f"| {_cell(name)} | {link} | {_cell('; '.join(identities.values()) or None)} | "
                         f"{_cell('; '.join(sorted(tts_identities)) or None)} | {counts} | "
                         f"{_cell(completeness.get('samples'))} | {_cell(completeness.get('status'))} |")
        lines.extend([
            "", "资源日志按实际采样报告CPU、宿主内存和GPU显存；生命周期峰值包含加载、预热和各轮处理，不能当逐样本精确峰值。进程归属失败、缺失采样和旧格式未记录的自有显存保持NA，不回退到整卡字段；即使状态为complete_observed_samples，也只表示已有采样记录完整，仍可能漏掉更短峰值。TTS用户声明与身份、活动的实际观测分开报告，详见TTS测量条件；观测不是全程零调用证明。硬限制与采样值分开保存。", "",
        ])
    return "\n".join(lines)


summarize_results = aggregate_reports
