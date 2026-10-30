"""Paired P07/P08 service reports from declared scores and run metadata only.

This module never loads a PDF, reference, annotation, native output or parser.
It does not score, repair, infer source mappings or invent missing measurements.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shlex
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .reporting import _quality
from .scoring import require_complete_target_grading

REPORT_VERSION = "moparse-service-paired-report-7"
_SUCCESS = {"completed", "ok", "success", "succeeded"}
_METRICS = {
    "content_recall": ("内容定位召回 ↑", "unit_presence.recall", True),
    "strict_cer": ("已定位正文 CER ↓", "text_aligned.strict.cer", False),
    "field_target_correctness": ("已证正确字段覆盖率 ↑", "table_records.field_target_correctness.value", True),
    "information_target_correctness": ("完整已标信息正确覆盖 ↑", "table_records.information_target_correctness.value", True),
}
_FORBIDDEN_INPUTS = {"datasets", "pdf_sample", "expected", "annotations", "reference-decisions"}
_STAGES = {
    "bridge_pages": "SDK页导出", "source_pages": "来源结构处理后",
    "native_pages": "原生正文处理后", "exported": "文档组装后",
    "assets": "图片保全后", "final": "最终连续正文",
}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _value(record: Mapping[str, Any], path: str) -> float | None:
    current: Any = record
    for key in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return _number(current)


def _read_json(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if resolved.suffix != ".json" or _FORBIDDEN_INPUTS.intersection(resolved.parts):
        raise ValueError("service reports read declared run/score JSON only")
    value = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("declared run/score JSON is not an object")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _key(case: Mapping[str, Any]) -> str:
    if case.get("case_id") is not None:
        return str(case["case_id"])
    return ":".join(str(case.get(name, default)) for name, default in (
        ("sample_id", "unknown"), ("suite", "quality800"), ("phase", "measured"), ("repetition", 1)))


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _quality_case(case: Mapping[str, Any]) -> bool:
    return case.get("suite") == "quality800" and case.get("phase", "measured") == "measured"


def _metric_values(quality: Mapping[str, Any]) -> dict[str, float | None]:
    micro = quality.get("micro", {})
    return {key: _value(micro, path) for key, (_, path, _) in _METRICS.items()}


def _delta(baseline: Mapping[str, Any], final: Mapping[str, Any]) -> dict[str, float | None]:
    before, after = _metric_values(baseline), _metric_values(final)
    result: dict[str, float | None] = {}
    for key in _METRICS:
        left, right = before[key], after[key]
        result[key] = right - left if left is not None and right is not None else None
    return result


def _scope_signature(score: Mapping[str, Any]) -> dict[str, Any]:
    metrics = score.get("metrics", {})
    units = score.get("units", [])
    identifiers = [str(unit.get("id")) for unit in units if isinstance(unit, Mapping)]
    tp, fn = _value(metrics, "unit_presence.tp"), _value(metrics, "unit_presence.fn")
    return {
        "unit_ids": sorted(identifiers), "duplicate_unit_ids": sorted(key for key, n in Counter(identifiers).items() if n > 1),
        "content_targets": tp + fn if tp is not None and fn is not None else None,
        "text_reference_chars": _value(metrics, "text.strict.reference_chars"),
        "table_target_fields": _value(metrics, "table_records.target_fields"),
        "scored_units": _count(score.get("coverage", {}).get("scored_units")),
        "document_id": score.get("document_id"), "family_id": score.get("family_id"),
        "evaluation_policy": score.get("evaluation_policy"),
        "human_reference_adjudications": score.get("human_reference_adjudications"),
    }


def _load_score(directory: Path, entry: Mapping[str, Any], side: str,
                case: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    declared = entry.get(side + "_score")
    if not isinstance(declared, str):
        return None, "score_path_missing"
    try:
        score = _read_json(directory / declared)
    except (OSError, ValueError, TypeError):
        return None, "score_unreadable"
    if score.get("sample_id") != case.get("sample_id"):
        return None, "score_sample_identity_mismatch"
    if score.get("scorer_status") != "evaluated" or not isinstance(score.get("metrics"), dict):
        return None, "score_not_evaluated"
    return score, None


def _unit_projection(unit: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if unit is None:
        return None
    return {key: unit[key] for key in (
        "id", "index", "kind", "status", "reason", "text", "strict_exact", "policy_exact", "content_exact",
        "native_id", "native_path", "match", "label_match", "grid_relation", "binding", "reference", "information",
        "raw_transcription", "native_text", "outcome", "required_qualifiers",
    ) if key in unit}


def _changes(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None, *,
             is_field: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if before is None or after is None:
        return result
    cer_before, cer_after = _value(before, "text.strict.cer"), _value(after, "text.strict.cer")
    if cer_before is not None and cer_after is not None:
        delta = cer_after - cer_before
        result["strict_cer"] = {"delta": delta, "transition": "gain" if delta < 0 else "loss" if delta > 0 else "unchanged"}
    for key in ("policy_exact", "content_exact", "strict_exact"):
        left, right = before.get(key), after.get(key)
        if type(left) is bool and type(right) is bool:
            result[key] = {"delta": int(right) - int(left),
                           "transition": "gain" if right and not left else "loss" if left and not right else "unchanged"}
    field_states = {"compared", "incorrect"}
    if (is_field and type(before.get("index")) is int and before["index"] >= 0
            and type(after.get("index")) is int and after["index"] == before["index"]
            and before.get("status") in field_states and after.get("status") in field_states):
        left = before.get("status") == "compared" and before.get("content_exact") is True
        right = after.get("status") == "compared" and after.get("content_exact") is True
        result["field_target_success"] = {"delta": int(right) - int(left),
            "transition": "gain" if right and not left else "loss" if left and not right else "unchanged",
            "meaning": "change_in_correct_count_on_fixed_target_set"}
        left_info, right_info = before.get("information"), after.get("information")
        left = isinstance(left_info, Mapping) and left_info.get("status") == "correct"
        right = isinstance(right_info, Mapping) and right_info.get("status") == "correct"
        result["information_target_success"] = {"delta": int(right) - int(left),
            "transition": "gain" if right and not left else "loss" if left and not right else "unchanged"}
        for key in sorted(set(before.get("required_qualifiers", [])) | set(after.get("required_qualifiers", []))):
            left = (left_info or {}).get("qualifiers", {}).get(key, {}).get("status") == "correct"
            right = (right_info or {}).get("qualifiers", {}).get(key, {}).get("status") == "correct"
            result[key + "_target_success"] = {"delta": int(right) - int(left),
                "transition": "gain" if right and not left else "loss" if left and not right else "unchanged"}
    return result


def _paired_units(case: Mapping[str, Any], baseline: Mapping[str, Any] | None,
                  final: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Pair only declared unit IDs and authored field indices; never align text."""
    grouped: list[dict[str, list[dict[str, Any]]]] = []
    for score in (baseline, final):
        by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for unit in (score or {}).get("units", []):
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                by_id[unit["id"]].append(unit)
        grouped.append(by_id)
    rows = []
    for identifier in sorted(set(grouped[0]) | set(grouped[1])):
        left, right = grouped[0].get(identifier, []), grouped[1].get(identifier, [])
        parent_status = ("ambiguous_unit_identity" if len(left) > 1 or len(right) > 1 else
                         "missing_baseline" if not left else "missing_final" if not right else "paired")
        before = left[0] if len(left) == 1 else None
        after = right[0] if len(right) == 1 else None
        common = {"case_id": _key(case), "sample_id": case.get("sample_id"),
                  "document_id": case.get("document_id", case.get("source_document")),
                  "family_id": case.get("family_id", case.get("family")), "unit_id": identifier}
        rows.append({**common, "field_index": None, "pair_status": parent_status,
                     "baseline": _unit_projection(before), "final": _unit_projection(after),
                     "changes": _changes(before, after) if parent_status == "paired" else {}})
        fields: list[dict[int, list[dict[str, Any]]]] = []
        for unit in (before, after):
            by_index: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for field in (unit or {}).get("fields", []):
                if isinstance(field, dict) and type(field.get("index")) is int:
                    by_index[field["index"]].append(field)
            fields.append(by_index)
        for index in sorted(set(fields[0]) | set(fields[1])):
            l_fields, r_fields = fields[0].get(index, []), fields[1].get(index, [])
            status = ("ambiguous_field_identity" if len(l_fields) > 1 or len(r_fields) > 1 else
                      "missing_baseline" if not l_fields else "missing_final" if not r_fields else parent_status)
            l_field = l_fields[0] if len(l_fields) == 1 else None
            r_field = r_fields[0] if len(r_fields) == 1 else None
            rows.append({**common, "field_index": index, "pair_status": status,
                         "baseline": _unit_projection(l_field), "final": _unit_projection(r_field),
                         "changes": _changes(l_field, r_field, is_field=True) if status == "paired" else {}})
    return rows


def _performance(cases: list[dict[str, Any]], suite: str) -> dict[str, Any]:
    cases = [case for case in cases if case.get("suite") == suite and case.get("phase", "measured") == "measured"]
    expected = {str(case.get("sample_id")) for case in cases}
    repetitions = {int(case.get("repetition", 1)) for case in cases}
    if suite == "perf80":
        repetitions |= {1, 2, 3}
    rounds: list[dict[str, Any]] = []
    for repetition in sorted(repetitions):
        items = [case for case in cases if int(case.get("repetition", 1)) == repetition]
        seconds = [_number(case.get("timing", {}).get("postprocessing_seconds")) for case in items]
        known = [value for value in seconds if value is not None and value >= 0]
        scope_complete = {str(case.get("sample_id")) for case in items} == expected and bool(items)
        timing_complete = scope_complete and len(known) == len(items)
        pages = [_count(case.get("input_pages", case.get("input_page_count"))) for case in items]
        capture = [_number(case.get("timing", {}).get("diagnostic_capture_seconds")) for case in items]
        rounds.append({"repetition": repetition, "samples": len(items), "expected_samples": len(expected),
                       "input_pages": sum(page for page in pages if page is not None) if pages and all(page is not None for page in pages) else None,
                       "postprocessing_seconds": sum(known) if timing_complete else None,
                       "observed_seconds_subtotal": sum(known) if known else None,
                       "missing_timing_samples": len(items) - len(known), "timing_complete": timing_complete,
                       "status_counts": dict(Counter(str(case.get("status", "unknown")) for case in items)),
                       "diagnostic_capture_seconds": sum(value for value in capture if value is not None)
                           if capture and all(value is not None for value in capture) else None})
    complete = [value for item in rounds if (value := _number(item["postprocessing_seconds"])) is not None]
    return {"suite": suite, "rounds": rounds, "complete_timing_rounds": len(complete),
            "median_postprocessing_seconds": statistics.median(complete) if complete else None,
            "minimum_seconds": min(complete) if complete else None, "maximum_seconds": max(complete) if complete else None,
            "coefficient_of_variation": statistics.pstdev(complete) / statistics.mean(complete)
                if len(complete) > 1 and statistics.mean(complete) else None,
            "meaning": "postprocessing_only_not_new_end_to_end_parse_timing"}


def _grouped(pairs: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        groups[str(pair.get(key) or "unknown")].append(pair)
    output = []
    for identifier, items in sorted(groups.items()):
        baseline = _quality([item["baseline"] for item in items], "quality800")
        final = _quality([item["final"] for item in items], "quality800")
        output.append({key: identifier, "samples": len(items),
                       "input_pages": sum(item["input_pages"] for item in items if item["input_pages"] is not None),
                       "baseline": baseline, "final": final, "delta": _delta(baseline, final)})
    return output


def _redacted(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[redacted]" if any(word in key.lower() for word in ("api_key", "password", "secret", "authorization"))
                else _redacted(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item) for item in value]
    return value


def _stage_quality(directory: Path, cases: list[dict[str, Any]],
                   indexed: Mapping[str, Any]) -> list[dict[str, Any]]:
    declared = [case for case in cases if _quality_case(case)]
    if not any(indexed.get(_key(case), {}).get("stage_scores") for case in declared):
        return []
    output = []
    captured = {stage.get("stage") for case in declared
                for stage in indexed.get(_key(case), {}).get("stage_scores", [])}
    for name, label in _STAGES.items():
        if name not in captured:
            continue
        scores, errors, scopes = [], [], set()
        for case in declared:
            entry = indexed.get(_key(case), {})
            stages = [stage for stage in entry.get("stage_scores", []) if stage.get("stage") == name]
            if len(stages) != 1:
                errors.append({"case_id": _key(case), "reason": "missing_or_ambiguous_stage"})
                continue
            stage = stages[0]
            if stage.get("scope") not in {"diagnostic_page_export", "actual_document_rendering"}:
                errors.append({"case_id": _key(case), "reason": "unknown_stage_capture_scope"})
                continue
            scored, error = _load_score(directory, {"stage_score": stage.get("score")}, "stage", case)
            final, final_error = _load_score(directory, entry, "final", case)
            if (error or final_error or scored is None or final is None
                    or _scope_signature(scored) != _scope_signature(final)):
                errors.append({"case_id": _key(case), "reason": error or final_error or "stage_reference_scope_mismatch"})
                continue
            scores.append(scored)
            scopes.add(stage.get("scope"))
        output.append({"stage": name, "label": label, "declared_cases": len(declared),
                       "scored_cases": len(scores), "complete": not errors and bool(declared),
                       "capture_scopes": sorted(scopes), "errors": errors,
                       "quality": _quality(scores, "quality800") if not errors and scores else {}})
    return output


def _summarize(directory: Path, run: dict[str, Any], index: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = run.get("cases", [])
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("service run.cases must be an explicit list")
    declared = {_key(case): case for case in cases}
    if len(declared) != len(cases):
        raise ValueError("duplicate service case identity")
    entries = index.get("results", index.get("cases", []))
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise ValueError("service score index.results must be a list")
    indexed = {_key(entry): entry for entry in entries}
    if len(indexed) != len(entries):
        raise ValueError("duplicate paired score case identity")
    pairs, records, units = [], [], []
    for case in cases:
        if not _quality_case(case):
            continue
        identity = _key(case)
        entry = indexed.get(identity, {})
        baseline, baseline_error = _load_score(directory, entry, "baseline", case)
        final, final_error = _load_score(directory, entry, "final", case)
        for scored in (baseline, final):
            if scored is not None:
                require_complete_target_grading(scored)
        status = "missing_or_invalid_score" if baseline_error or final_error else "paired"
        if baseline is not None and final is not None:
            signatures = (_scope_signature(baseline), _scope_signature(final))
            if any(signature["duplicate_unit_ids"] for signature in signatures):
                status = "ambiguous_unit_identity"
            elif signatures[0] != signatures[1]:
                status = "reference_scope_mismatch"
        metadata = {"case_id": identity, "sample_id": case.get("sample_id"),
                    "document_id": case.get("document_id", case.get("source_document", (baseline or {}).get("document_id"))),
                    "family_id": case.get("family_id", case.get("family", (baseline or {}).get("family_id"))),
                    "tags": case.get("tags", (baseline or {}).get("tags", [])),
                    "input_pages": _count(case.get("input_pages", case.get("input_page_count"))),
                    "status": status, "run_status": case.get("status", "unknown"),
                    "baseline_score": entry.get("baseline_score"), "final_score": entry.get("final_score"),
                    "baseline_error": baseline_error, "final_error": final_error}
        record = {**metadata, "baseline": _metric_values({"micro": (baseline or {}).get("metrics", {})}),
                  "final": _metric_values({"micro": (final or {}).get("metrics", {})}),
                  "delta": _delta({"micro": baseline["metrics"]}, {"micro": final["metrics"]})
                    if status == "paired" and baseline is not None and final is not None else {key: None for key in _METRICS}}
        records.append(record)
        paired_units = _paired_units({**case, **metadata}, baseline, final)
        if status != "paired":
            for row in paired_units:
                row["case_pair_status"] = status
                row["changes"] = {}
        units.extend(paired_units)
        if status == "paired":
            pairs.append({**metadata, "baseline": baseline, "final": final})
    baseline_quality = _quality([pair["baseline"] for pair in pairs], "quality800")
    final_quality = _quality([pair["final"] for pair in pairs], "quality800")
    conversion = {}
    quality_cases = [case for case in cases if _quality_case(case)]
    for key in ("converted", "partial", "retained", "unknown"):
        counts = [_count(case.get("conversion", {}).get(
            key, case.get("conversion", {}).get("unknown_kind") if key == "unknown" else None
        )) for case in quality_cases]
        conversion[key] = {"count": sum(count for count in counts if count is not None) if counts and all(count is not None for count in counts) else None,
                           "observed_subtotal": sum(count for count in counts if count is not None),
                           "missing_cases": sum(count is None for count in counts)}
    transitions: dict[str, dict[str, int]] = {}
    for key in ("strict_cer", "policy_exact", "content_exact", "strict_exact", "field_target_success", "information_target_success"):
        transitions[key] = dict(Counter(row["changes"][key]["transition"] for row in units
            if key in row["changes"] and (key != "field_target_success" or row.get("field_index") is not None)))
    pages = [_count(case.get("input_pages", case.get("input_page_count"))) for case in quality_cases]
    summary = {
        "schema": REPORT_VERSION, "report_version": run.get("report_version", REPORT_VERSION),
        "run_id": run.get("run_id", directory.name), "score_id": index.get("score_id"),
        "quality": {"declared_cases": len(quality_cases),
                    "declared_pages": sum(page for page in pages if page is not None) if pages and all(page is not None for page in pages) else None,
                    "paired_cases": len(pairs), "paired_pages": sum(pair["input_pages"] for pair in pairs if pair["input_pages"] is not None),
                    "pair_status_counts": dict(Counter(record["status"] for record in records)),
                    "baseline": baseline_quality, "final": final_quality, "delta": _delta(baseline_quality, final_quality)},
        "samples": records, "by_document": _grouped(pairs, "document_id"), "by_family": _grouped(pairs, "family_id"),
        "unit_transitions": transitions, "conversion": conversion,
        "finalization": {
            "operation_counts": dict(sum((Counter(case.get("finalization", {}).get("operation_counts", {}))
                                          for case in quality_cases), Counter())),
            "joined_paragraphs": sum(len(case.get("finalization", {}).get("joined_paragraphs", [])) for case in quality_cases),
            "unresolved_continuations": sum(len(case.get("finalization", {}).get("unresolved_continuations", [])) for case in quality_cases),
        },
        "stage_quality": _stage_quality(directory, cases, indexed),
        "performance": {suite: _performance(cases, suite) for suite in ("quality800", "perf80")},
        "execution_status_counts": dict(Counter(str(case.get("status", "unknown")) for case in quality_cases)),
        "unlisted_score_cases": sorted(set(indexed) - set(declared)),
        "metadata": _redacted({key: run[key] for key in (
            "created_at", "finished_at", "baseline_run", "baseline_score_id", "software", "code_identity",
            "scoring_protocol", "reference_adjudications", "service_config", "options", "execution_environment",
            "measurement_notes", "limitations", "deployment_status", "case_notes", "scoring_status", "native_pipeline", "entrypoint_analysis",
        ) if key in run}),
        "limitations": [
            "Quality uses only uniquely paired, equal-reference-scope quality800 scores; missing pairs remain disclosed.",
            "Failed/partial parsing results remain in paired quality when both scores exist; performance repetitions do not expand quality samples.",
            "Unit IDs and field indices pair existing scores; no text alignment, reference rewriting or inferred grid is performed.",
            "Postprocessing timing is newly measured separately; old native timing is never added to claim new end-to-end measurements.",
            "Saved stage scores show sequential changes within this candidate path; they are not independent ablation experiments or model parsing reruns.",
            "Image fidelity, unknown structure and unannotated content are not accepted by this report.",
        ],
    }
    scoring_software = index.get("software", {})
    summary["metadata"]["scoring_software_id"] = scoring_software.get("software_id")
    summary["metadata"]["scoring_software"] = scoring_software
    summary["metadata"]["execution_software_id"] = run.get("software", {}).get("software_id")
    return summary, units


def _display(value: Any, *, percent: bool = True) -> str:
    number = _number(value)
    return "NA" if number is None else f"{number:.2%}" if percent else f"{number:.3f}"


def _cell(value: Any) -> str:
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        value = int(value)
    return str(value if value is not None else "unknown").replace("|", "&#124;").replace("\n", " ")


def _rate_with_denominator(quality: Mapping[str, Any], metric: str) -> str:
    micro = quality.get("micro", {})
    value = _metric_values(quality)[metric]
    if metric == "content_recall":
        record = micro.get("unit_presence", {})
        numerator, missing = _number(record.get("tp")), _number(record.get("fn"))
        denominator = numerator + missing if numerator is not None and missing is not None else None
    elif metric == "strict_cer":
        record = micro.get("text_aligned", {}).get("strict", {})
        numerator, denominator = record.get("distance"), record.get("reference_chars")
    else:
        record = micro.get("table_records", {}).get(metric, {})
        numerator, denominator = record.get("numerator"), record.get("denominator")
    return f"{_display(value)} ({_cell(numerator)} / {_cell(denominator)})"


def _render_figures(summary: dict[str, Any], directory: Path) -> list[dict[str, str]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    from .report_figures import _register_cjk_fonts

    directory.mkdir(parents=True, exist_ok=True)
    _register_cjk_fonts(directory)
    entries = []
    settings = {"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"],
                "font.sans-serif": ["DejaVu Sans", "Noto Sans CJK SC"], "text.usetex": False,
                "mathtext.fontset": "dejavusans", "svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42,
                "svg.hashsalt": REPORT_VERSION, "figure.facecolor": "white", "savefig.bbox": "tight"}

    def save(figure: Any, name: str, title: str) -> None:
        entry = {"id": name, "title": title}
        try:
            for extension in ("png", "svg", "pdf"):
                filename = name + "." + extension
                metadata = {"CreationDate": None, "ModDate": None} if extension == "pdf" else {"Date": None} if extension == "svg" else {}
                figure.savefig(directory / filename, dpi=160 if extension == "png" else None, metadata=metadata)
                entry[extension] = directory.name + "/" + filename
            entries.append(entry)
        finally:
            plt.close(figure)

    with plt.rc_context(settings):
        figure, axes = plt.subplots(2, 2, figsize=(12, 7.4))
        for axis, (key, (label, _, _)) in zip(axes.flat, _METRICS.items(), strict=True):
            values = [_metric_values(summary["quality"][side])[key] for side in ("baseline", "final")]
            for position, value in enumerate(values):
                if value is None:
                    axis.text(position, 0.02, "NA", ha="center")
                else:
                    axis.bar(position, value, color=("#4578A8", "#D28041")[position], width=0.55)
                    axis.annotate(_display(value), (position, value), xytext=(0, 5), textcoords="offset points", ha="center")
            native_name = summary['metadata'].get('native_pipeline', {}).get('pipeline', 'P07')
            axis.set_xticks([0, 1], [native_name + " 原生", "MO 最终"])
            axis.set_ylim(0, max([0.01 if key == "strict_cer" else 1.0,
                                  *(value * 1.2 for value in values if value is not None)]))
            axis.yaxis.set_major_formatter(PercentFormatter(1))
            axis.set_title(label, loc="left", fontsize=12)
            axis.spines[["top", "right"]].set_visible(False)
        figure.suptitle("同范围配对评分 · 原生与服务最终结果", fontsize=16)
        figure.tight_layout()
        save(figure, "paired-quality", "同范围的四项质量对照")
        figure, axes = plt.subplots(1, 2, figsize=(12, 4.4))
        for axis, suite, label in zip(axes, ("quality800", "perf80"), ("质量集后处理", "性能子集后处理"), strict=True):
            performance = summary["performance"][suite]
            rounds = performance["rounds"]
            for row in rounds:
                seconds = row["postprocessing_seconds"]
                if seconds is None:
                    axis.text(row["repetition"], 0, "NA", ha="center")
                else:
                    axis.scatter(row["repetition"], seconds, s=70, color="#4578A8")
            if performance["median_postprocessing_seconds"] is not None:
                axis.axhline(performance["median_postprocessing_seconds"], color="#D28041", linestyle="--", label="完整计时轮次中位数")
                axis.legend(fontsize=8)
            axis.set_xticks([row["repetition"] for row in rounds])
            axis.set_title(f"{label} · 完整计时 n={performance['complete_timing_rounds']}", loc="left")
            axis.set_xlabel("实际轮次")
            axis.set_ylabel("后处理秒数")
            axis.spines[["top", "right"]].set_visible(False)
        figure.suptitle("本次后处理测量；不含既有原生解析时间", fontsize=15)
        figure.tight_layout()
        save(figure, "postprocessing-time", "质量集一次与性能子集各轮后处理耗时")
        if summary.get("stage_quality"):
            stages = summary["stage_quality"]
            figure, axes = plt.subplots(1, 2, figsize=(13, 4.8))
            for axis, metric, title in zip(
                axes, ("strict_cer", "field_target_correctness"),
                ("已定位正文 CER ↓", "已证正确字段覆盖率 ↑"), strict=True,
            ):
                values = [_metric_values(stage["quality"])[metric] for stage in stages]
                positions = [i for i, value in enumerate(values) if value is not None]
                axis.plot(positions, [values[i] for i in positions], color="#4578A8", marker="o")
                for i in positions:
                    axis.annotate(_display(values[i]), (i, values[i]), xytext=(0, 7),
                                  textcoords="offset points", ha="center", fontsize=9)
                axis.set_xticks(range(len(stages)), [stage["label"] for stage in stages], rotation=25, ha="right")
                axis.yaxis.set_major_formatter(PercentFormatter(1))
                axis.set_title(title, loc="left")
                axis.margins(y=0.25)
                axis.spines[["top", "right"]].set_visible(False)
            figure.suptitle("同次服务流水线的阶段变化 · 同一目标分母", fontsize=15)
            figure.tight_layout()
            save(figure, "stage-quality", "同次候选流水线各阶段质量变化")
    _write_json(directory / "index.json", {"schema": REPORT_VERSION, "source": "summary.json", "figures": entries})
    return entries


def _render_main(summary: dict[str, Any], figures: list[dict[str, str]]) -> str:
    quality = summary["quality"]
    metadata = summary["metadata"]
    pipeline = metadata.get("native_pipeline", {}).get("pipeline", "P07")
    deployment = metadata.get("deployment_status", metadata.get("execution_environment", {}).get("deployment_status", "unknown"))
    deployment_text = ("后处理结果尚未部署到线上服务" if deployment == "not_deployed"
                       else f"部署状态为 `{_cell(deployment)}`，本报告不构成部署验收")
    scope = (f"同一质量集 {_cell(quality['declared_pages'])} 页、{quality['declared_cases']} 个样本；"
             f"同范围评分配对覆盖 {quality['paired_pages']} 页、{quality['paired_cases']} 个样本。")
    if quality["paired_cases"] != quality["declared_cases"]:
        scope += "缺失或不可配对项保留在[附录](appendix.md)。"
    lines = [f"# MO-Parse {pipeline} 服务后处理配对报告", "",
             f"报告版本：`{_cell(summary['report_version'])}`；生成器：`{REPORT_VERSION}`；运行：`{_cell(summary['run_id'])}`；评分：`{_cell(summary['score_id'])}`。", "",
             scope, "",
             f"本报告比较既有 {pipeline} 原生输出和修复后的 MO-Parse 最终正文。{deployment_text}；运行环境和实际配置见附录。", "",
             "本轮关注下游实体、关系和事件识别所需的正文条件：原句、主体、行为、否定、日期、数值及限定信息保全，明确段落连续性，处理诊断与业务正文分离。未运行下游抽取模型，不把正文指标称为实体、关系或事件抽取F1。", ""]
    versions = metadata.get("native_pipeline", {}).get("versions", {})
    if versions:
        native_version = (f"MinerU {_cell(versions.get('mineru'))} Advanced/TXT + GLM-OCR SDK {_cell(versions.get('glmocr'))}"
                          if pipeline == "P07" else f"MinerU纯视觉SDK {_cell(versions.get('mineru-vl-utils'))}")
        lines.extend([
            f"版本：{native_version}；MO-Parse {_cell(metadata.get('service_config', {}).get('version'))} "
            "工作区修复版。完整源码、镜像和模型身份见附录。", "",
        ])
    values = quality["delta"]
    if all(values.get(key) is not None and (values[key] > 0 if higher else values[key] < 0)
           for key, (_, _, higher) in _METRICS.items()):
        fields = summary["unit_transitions"].get("field_target_success", {})
        lines.extend([
            f"本次四项主指标均改善。已标注字段中，最终输出可定位且正确的目标增加 {_cell(fields.get('gain', 0))} 个，"
            f"原先正确而退步的字段为 {_cell(fields.get('loss', 0))} 个；逐项结果可追溯到最终输出。", "",
        ])
    attribution = (
        "本次保存并同标准评分各阶段的实际候选正文，阶段表展示这条固定顺序流水线内的变化；它不是独立消融实验。"
        if summary.get("stage_quality") else
        "质量变化来自SDK重导出、来源处理、导出清理、IR、资产和语义转换整条路径；现有产物没有逐阶段正文快照，不能仅凭阶段耗时拆分质量贡献。"
    )
    lines.extend(["字段增益不等于新识别出同等数量的原PDF数值。" + attribution, ""])
    lines.extend([f"| 指标 | {pipeline} 原生 | MO 最终 | 最终 − 原生（百分点） |", "|---|---:|---:|---:|"])
    for key, (label, _, _) in _METRICS.items():
        difference = quality["delta"][key]
        change = "NA" if difference is None else f"{difference * 100:+.2f}"
        lines.append(f"| {label} | {_rate_with_denominator(quality['baseline'], key)} | {_rate_with_denominator(quality['final'], key)} | {change} |")
    lines.extend(["", "内容召回衡量定位；CER仅评价已定位正文，须结合字符覆盖。值与业务标签、包含已标单位期间附注的完整信息均按全部固定目标计算正确率，每个已纳入字段只判正确或错误。图片内容保真仍需目视判断。", ""])
    for side, label in (("baseline", "原生"), ("final", "最终")):
        micro = quality[side].get("micro", {})
        aligned = _value(micro, "text_aligned.strict.reference_chars")
        total = _value(micro, "text.strict.reference_chars")
        lines.extend([f"{label}正文字符定位覆盖：{_display(aligned / total if aligned is not None and total else None)}。", ""])
    formatting = summary.get("finalization", {})
    lines.extend([f"连续正文处理：完成 {formatting.get('joined_paragraphs', 0)} 处原生声明的段落续接；"
                  f"{formatting.get('unresolved_continuations', 0)} 处声明缺少可唯一确定的邻接范围，保留分段。具体处理数量与来源范围见机器汇总和候选证据。", ""])
    for entry in figures:
        lines.extend([f"![{entry['title']}]({entry['png']})", ""])
    if summary.get("stage_quality"):
        lines.extend(["| 阶段 | 同范围样本 | 内容定位召回 ↑ | 已定位正文 CER ↓ | 已证正确字段覆盖率 ↑ | 完整已标信息正确覆盖 ↑ |",
                      "|---|---:|---:|---:|---:|---:|"])
        for stage in summary["stage_quality"]:
            values = _metric_values(stage["quality"])
            lines.append(f"| {stage['label']} | {stage['scored_cases']} / {stage['declared_cases']} | "
                         + " | ".join(_display(values[key]) for key in _METRICS) + " |")
        lines.extend(["", "阶段表展示同一次候选流水线实际保存的正文；所有阶段使用同一冻结评分范围，不把阶段结果当作新增管线或独立样本。", ""])
    lines.extend(["| 耗时范围 | 完整计时轮数 | 后处理中位秒 | 各轮秒数 |", "|---|---:|---:|---|"])
    for suite, label in (("quality800", "质量集（计划 n=1）"), ("perf80", "性能子集（计划三轮）")):
        performance = summary["performance"][suite]
        points = ", ".join(f"r{row['repetition']}={_display(row['postprocessing_seconds'], percent=False)}" for row in performance["rounds"]) or "NA"
        lines.append(f"| {label} | {performance['complete_timing_rounds']} | {_display(performance['median_postprocessing_seconds'], percent=False)} | {points} |")
    conversion = summary["conversion"]
    status_labels = {"completed": "完成", "completed_with_warnings": "完成但有警告", "partial": "部分输出", "failed": "失败"}
    statuses = "，".join(f"{status_labels.get(key, key)} {count} 个样本" for key, count in summary["execution_status_counts"].items())
    lines.extend(["", "这些是本次后处理计时，未将既有原生耗时相加并冒充新的端到端实测；性能子集重复不扩大质量样本量，也不提供置信区间或显著性结论。", "",
                  f"表格转换：转换器将 {_cell(conversion['converted']['count'])} 个候选视图标记为converted，部分转换为{_cell(conversion['partial']['count'])}，{_cell(conversion['retained']['count'])} 个保留原表。完整与部分转换分别记录，不能当作真实表格召回率或转换准确率；unknown是转换回退状态，未转换原因和缺失记录见附录。运行状态：{statuses}。", "",
                  "逐样本、原文档和家族的收益与损失、分母、失败及未知项见[附录](appendix.md)；逐项配对见[JSON](paired-units.json)与[CSV](paired-units.csv)，汇总见[summary.json](summary.json)。", "",
                  "复现报告（只读取已有运行与评分产物）：", "", "```bash", summary["reproduction_command"], "```", ""])
    if metadata.get("case_notes"):
        lines.extend([f"已目视对照的案例与读取修正见[案例说明]({_cell(metadata['case_notes'])})。", ""])
    if metadata.get("entrypoint_analysis"):
        lines.extend([f"原生文字进入IR与最终正文的差异、表格入口逐层阻断原因及字段增益解释见[入口分析]({_cell(metadata['entrypoint_analysis'])})。", ""])
    return "\n".join(lines)


def _render_appendix(summary: dict[str, Any]) -> str:
    lines = ["# 附录：配对证据、分母与测量范围", "", "[返回主报告](report.md)。", "",
             "## 分母与平均口径", "", "| 指标 | 原生 | 最终 |", "|---|---:|---:|"]
    for key, (label, _, _) in _METRICS.items():
        lines.append(f"| {label} | {_rate_with_denominator(summary['quality']['baseline'], key)} | {_rate_with_denominator(summary['quality']['final'], key)} |")
    for scope, label in (("macro_by_sample", "样本等权 CER"), ("macro_by_document", "原文档等权 CER"), ("macro_by_family", "家族等权 CER")):
        cells = []
        for side in ("baseline", "final"):
            metric = summary["quality"][side].get(scope, {}).get("text.strict.cer", {})
            cells.append(f"{_display(metric.get('value'))} ({_cell(metric.get('available_groups'))} / {_cell(metric.get('total_groups'))})")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.extend(["", "表中 CER 微平均按参考字符数加权；宏平均仅对已配对且该项可用的组等权。字段正确与错误之和等于全部固定目标数，不能用已比较子集的条件正确率替代全目标正确率。", ""])
    for scope, records in (("样本", summary["samples"]), ("原文档", summary["by_document"]), ("家族", summary["by_family"])):
        lines.extend([f"## {scope}", "", "| 身份 | 配对状态 | 已定位 CER 差（百分点） | 字段覆盖率差（百分点） | 完整信息覆盖差（百分点） |", "|---|---|---:|---:|---:|"])
        for record in records:
            identity = record.get("sample_id", record.get("document_id", record.get("family_id")))
            values = [record["delta"].get(key) for key in ("strict_cer", "field_target_correctness", "information_target_correctness")]
            display = ["NA" if value is None else f"{value * 100:+.3f}" for value in values]
            lines.append(f"| {_cell(identity)} | {_cell(record.get('status', 'paired'))} | " + " | ".join(display) + " |")
        lines.append("")
    lines.extend(["## 逐项变化", "", "以下按指标分别计收益与损失，不合成加权胜者。未配对或不可比较项不强行判好坏。", "",
                  "```json", json.dumps(summary["unit_transitions"], ensure_ascii=False, indent=2), "```", "",
                  "## 配对与失败", "", "```json",
                  json.dumps({"pair_status_counts": summary["quality"]["pair_status_counts"],
                              "execution_status_counts": summary["execution_status_counts"],
                              "conversion": summary["conversion"], "performance": summary["performance"]}, ensure_ascii=False, indent=2),
                  "```", "", "## 实际配置与环境", "", "```json",
                  json.dumps({"execution_and_scoring_metadata": summary["metadata"],
                              "report_generator": summary["report_generator"]}, ensure_ascii=False, indent=2), "```", "",
                  "## 边界", ""])
    lines.extend(["- " + text for text in summary["limitations"]])
    lines.extend(["", "原文档和家族分层取自既有运行/评分元数据，不自动补来源分类。未标注结构、未见内容和输出图片视觉保真不因评分或报告生成而被验收。", ""])
    return "\n".join(lines)


def render_service_report(run_path: str | Path) -> Path:
    """Write a reproducible report from declared artifacts, without executing work."""
    path = Path(run_path)
    path = path / "run.json" if path.is_dir() else path
    if path.name != "run.json":
        raise ValueError("service report entrypoint must be the declared run.json")
    directory = path.parent
    run = _read_json(path)
    if run.get("scoring_status") == "withdrawn":
        raise ValueError("the service scores were withdrawn; an obsolete report cannot be regenerated")
    index_path = directory / str(run.get("score_index", "scores/index.json"))
    index = _read_json(index_path) if index_path.is_file() else {"results": [], "score_id": None}
    if index.get("state") == "primary_complete_stages_pending":
        raise ValueError("stage scoring is still pending; this is not a completed service report")
    outputs = {directory / name for name in ("summary.json", "paired-units.json", "paired-units.csv", "report.md", "appendix.md")}
    protected = {path.resolve(), index_path.resolve()}
    for entry in index.get("results", index.get("cases", [])):
        if isinstance(entry, Mapping):
            protected.update((directory / entry[key]).resolve() for key in ("baseline_score", "final_score")
                             if isinstance(entry.get(key), str))
    if protected.intersection(output.resolve() for output in outputs):
        raise ValueError("report outputs would overwrite declared execution or score inputs")
    summary, units = _summarize(directory, run, index)
    summary["report_generator"] = {
        "version": REPORT_VERSION, "module": "moparse_eval.service_report",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "report_generation_only_separate_from_execution_and_scoring_identity",
    }
    summary["reproduction_command"] = f"python -m moparse_eval.service_report {shlex.quote(str(path))}"
    figures = _render_figures(summary, directory / "figures") if run.get("render_figures", True) else []
    summary["figures"] = figures
    _write_json(directory / "summary.json", summary)
    _write_json(directory / "paired-units.json", {"schema": REPORT_VERSION, "pairs": units})
    columns = ("case_id", "sample_id", "document_id", "family_id", "unit_id", "field_index", "pair_status",
               "baseline_status", "final_status", "strict_cer_delta", "policy_exact_transition", "content_exact_transition")
    with (directory / "paired-units.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in units:
            writer.writerow({**{key: row.get(key) for key in columns[:7]},
                             "baseline_status": (row["baseline"] or {}).get("status"),
                             "final_status": (row["final"] or {}).get("status"),
                             "strict_cer_delta": row["changes"].get("strict_cer", {}).get("delta"),
                             "policy_exact_transition": row["changes"].get("policy_exact", {}).get("transition"),
                             "content_exact_transition": row["changes"].get("content_exact", {}).get("transition")})
    destination = directory / "report.md"
    destination.write_text(_render_main(summary, figures), encoding="utf-8")
    (directory / "appendix.md").write_text(_render_appendix(summary), encoding="utf-8")
    return destination


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render existing paired P07/P08 service scores; never executes parsing or scoring.")
    parser.add_argument("run_path", type=Path)
    print(render_service_report(parser.parse_args().run_path))
