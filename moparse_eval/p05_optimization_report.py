"""Report an already scored, development-only P05 rotary experiment.

Reads experimental execution/score/telemetry outputs only.  Never opens the
dataset, invokes a scorer, performs inference, or changes the formal report.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeGuard

from .reporting import _quality

_ARMS = ("baseline", "native")
_SUCCESS = {"ok", "success", "completed", "succeeded"}
_IDENTITY = ("pipeline", "sample_id", "suite", "phase", "repetition")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected diagnostic object: {path.name}")
    return value


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("experimental artifact path escapes its run directory")
    return path


def _number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _identity(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(value.get(key) for key in _IDENTITY)


def _timing(rows: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [row.get("timing", {}).get("processing_seconds") for row in rows]
    pages = [row.get("input_page_count") for row in rows]
    known = [value for value in durations if _number(value)]
    complete = bool(rows) and len(known) == len(rows)
    page_values = [value for value in pages if isinstance(value, int) and not isinstance(value, bool) and value > 0]
    pages_complete = bool(rows) and len(page_values) == len(rows)
    total = sum(known)
    input_pages = sum(page_values) if pages_complete else None
    completed_pages = sum(row.get("input_page_count", 0) or 0 for row in rows if row.get("status") in _SUCCESS)
    return {"planned_samples": len(rows), "planned_input_pages": input_pages, "attempted_input_pages": input_pages,
        "completed_samples": sum(row.get("status") in _SUCCESS for row in rows),
        "failed_or_incomplete_samples": sum(row.get("status") not in _SUCCESS for row in rows),
        "status_counts": dict(Counter(str(row.get("status", "unknown")) for row in rows)),
        "timing_complete": complete, "timed_samples": len(known),
        "processing_seconds_including_failures": total if complete else None,
        "observed_processing_seconds_subtotal": total if known else None,
        "seconds_per_planned_input_page": total / input_pages if complete and input_pages else None,
        "completed_input_pages": completed_pages if pages_complete else None,
        "completed_pages_per_second_including_failure_cost": completed_pages / total if complete and pages_complete and total > 0 else None}


def _telemetry(rows: list[dict[str, Any]], run: Path) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    cases_with_telemetry = 0
    errors = []
    for row in rows:
        directory = _inside(run, row["source_observation"]).parent / "telemetry"
        found = False
        if directory.is_dir():
            for index_path in sorted(directory.glob("*/index.json")):
                index = _read(index_path)
                found = True
                errors.extend(index.get("recording_errors", []))
                for record in index.get("records", []):
                    saved = {key: record.get(key) for key in ("call_id", "state", "status_code", "task_candidates_from_exact_prompt",
                        "usage", "choice_termination", "elapsed_seconds", "exception_type")}
                    saved.update(sample_id=row.get("sample_id"), repetition=row.get("repetition"),
                                 index=str(index_path.relative_to(run)))
                    request_file = record.get("request_file")
                    request_path = _inside(index_path.parent, request_file) if request_file else None
                    request = _read(request_path) if request_path is not None and request_path.is_file() else {}
                    saved["request_record_available"] = bool(request_path is not None and request_path.is_file())
                    saved["requested_max_tokens"] = request.get("max_tokens")
                    saved["requested_repetition_penalty"] = request.get("repetition_penalty")
                    calls.append(saved)
        cases_with_telemetry += found
    finish_reasons: Counter[str] = Counter()
    for call in calls:
        choices = call.get("choice_termination") or []
        finish_reasons.update(str(choice.get("finish_reason") or "unavailable") for choice in choices)
    usage = {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [(call.get("usage") or {}).get(name) for call in calls]
        available = [value for value in values if _number(value)]
        usage[name] = {"observed_sum": sum(available) if available else None,
                       "available_calls": len(available), "total_calls": len(calls),
                       "complete": bool(calls) and len(available) == len(calls)}
    caps = [call for call in calls if _number((call.get("usage") or {}).get("completion_tokens"))
            and _number(call.get("requested_max_tokens"))]
    return {"scope": "region HTTP diagnostics; never substituted for worker processing time",
        "planned_cases": len(rows), "cases_with_telemetry": cases_with_telemetry,
        "observed_calls": len(calls), "states": dict(Counter(str(call.get("state")) for call in calls)),
        "finish_reasons": dict(finish_reasons), "usage": usage,
        "finish_reason_length_choices": finish_reasons.get("length", 0),
        "token_cap_observable_calls": len(caps),
        "completion_tokens_at_or_above_request_cap_calls": sum(
            call["usage"]["completion_tokens"] >= call["requested_max_tokens"] for call in caps),
        "recording_errors": errors, "calls": calls}


def _configuration(session: dict[str, Any]) -> dict[str, Any]:
    values = session.get("configurations", [])
    if isinstance(values, dict):
        return values.get("P05", values)
    if isinstance(values, list):
        return next((value for value in values if value.get("pipeline") == "P05"), {})
    return {}


def _differences(left: Any, right: Any, prefix: str = "") -> list[str]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return [path for key in sorted(set(left) | set(right)) for path in
                _differences(left.get(key), right.get(key), f"{prefix}.{key}" if prefix else str(key))]
    if isinstance(left, list) and isinstance(right, list):
        return [path for index in range(max(len(left), len(right))) for path in
                _differences(left[index] if index < len(left) else None,
                             right[index] if index < len(right) else None, f"{prefix}[{index}]")]
    return [] if left == right else [prefix]


def _glm_service(config: dict[str, Any]) -> dict[str, Any]:
    services = config.get("inference_services", [])
    if isinstance(services, list):
        return next((service for service in services if service.get("role") == "glm"), {})
    return services.get("glm", {}) if isinstance(services, dict) else {}


def _arm(run: Path) -> dict[str, Any]:
    session = _read(run / "run.json")
    if session.get("formal") is not False or session.get("development_experiment") is not True:
        raise ValueError("P05 optimization reporting requires a declared nonformal development experiment")
    index = _read(_inside(run, session["latest_scores"]))
    scores = {}
    for relative in index.get("results", []):
        result = _read(_inside(run, relative))
        key = _identity(result)
        if key in scores:
            raise ValueError("duplicate experimental score identity")
        scores[key] = result
    declarations = index.get("dataset_declaration", {}).get("sample_metadata", {})
    rows = []
    identities = set()
    for case in session.get("cases", []):
        key = _identity(case)
        if key in identities or case.get("pipeline") != "P05":
            raise ValueError("duplicate or non-P05 experimental case")
        identities.add(key)
        path = _inside(run, case["observation"])
        observed = _read(path) if path.is_file() else {"status": "observation_missing", "timing": {}}
        row = {**declarations.get(case["sample_id"], {}), **observed, **case,
               "source_observation": case["observation"]}
        if key in scores:
            row["score"] = scores[key]
        rows.append(row)
    measured = [row for row in rows if row.get("phase") == "measured"]
    suite = session.get("suite")
    if not suite or any(row.get("suite") != suite for row in measured):
        raise ValueError("one declared measured suite is required per experimental arm")
    quality_rows = [row for row in measured if row.get("repetition") == 1]
    if not quality_rows or len({row["sample_id"] for row in quality_rows}) != len(quality_rows):
        raise ValueError("experimental quality requires measured first-round cases")
    if any(row.get("repetition") not in {1, 2, 3} for row in measured):
        raise ValueError("experimental performance repetitions must be 1, 2, and 3")
    quality_inputs = []
    for row in quality_rows:
        scored = row.get("score")
        quality_inputs.append(scored if scored is not None else {**row, "metrics": {}, "coverage": {}, "scorer_status": "not_scored"})
    # The first repetition is explicitly selected even if the experiment uses
    # the perf80 suite.  The ordinary report correctly suppresses quality for
    # that suite, so use a distinct analysis label only inside this projection.
    quality = _quality(quality_inputs, "p05_optimization_selected_first_round")
    quality["source_suite"] = suite
    quality["selected_repetition"] = 1
    quality["planned_samples"] = len(quality_rows)
    quality["target_denominator_complete"] = quality["unscored_samples"] == 0
    if quality["unscored_samples"]:
        quality["available_scored_subset_micro"] = quality["micro"]
        quality["micro"] = None
        quality["macro_by_document"] = None
        quality["macro_by_family"] = None
    rounds = []
    planned_members = sorted(str(row["sample_id"]) for row in quality_rows)
    for repetition in (1, 2, 3):
        observed_members = [row for row in measured if row.get("repetition") == repetition]
        membership_matches = sorted(str(row["sample_id"]) for row in observed_members) == planned_members
        observed_ids = {row["sample_id"] for row in observed_members}
        missing: list[dict[str, Any]] = [{**{key: row.get(key) for key in ("sample_id", "input_page_count")},
                    "status": "scheduled_member_missing", "timing": {}}
                   for row in quality_rows if row["sample_id"] not in observed_ids]
        result = _timing(observed_members + missing)
        result.update(repetition=repetition, membership_matches_first_round=membership_matches,
                      missing_first_round_members=[row["sample_id"] for row in missing])
        if not result["membership_matches_first_round"]:
            result["timing_complete"] = False
            result["processing_seconds_including_failures"] = None
            result["seconds_per_planned_input_page"] = None
            result["completed_pages_per_second_including_failure_cost"] = None
        result["telemetry"] = _telemetry(observed_members, run)
        result["telemetry"]["planned_cases"] = result["planned_samples"]
        rounds.append(result)
    complete_rounds = [item["processing_seconds_including_failures"] for item in rounds if item["timing_complete"]]
    init = [row.get("timing", {}).get("pipeline_initialization_seconds") for row in rows]
    unique_init = sorted({value for value in init if _number(value)})
    warmups = [row for row in rows if row.get("phase") == "warmup"]
    artifacts = {}
    for name, relative in (
        ("inference_lifecycle", "artifacts/P05/inference/inference-ownership.json"),
        ("inference_resources", "artifacts/P05/inference/resources.json"),
        ("worker_resources", "artifacts/P05/worker-resources.json"),
        ("software_inspection", "artifacts/software-inspection.json"),
    ):
        path = run / relative
        artifacts[name] = {"path": relative, "record": _read(path)} if path.is_file() else None
    return {"run_id": session.get("run_id"), "state": session.get("state"), "suite": suite,
        "run_path": str(run), "software": session.get("software"), "scoring_software": index.get("software"),
        "score_index": session["latest_scores"], "reference_freeze": index.get("reference_freeze"),
        "config": _configuration(session), "artifacts": artifacts,
        "quality": quality, "quality_members": planned_members, "performance_rounds": rounds,
        "performance_summary": {"expected_rounds": 3, "complete_rounds": len(complete_rounds),
            "median_seconds": statistics.median(complete_rounds) if len(complete_rounds) == 3 else None,
            "min_seconds": min(complete_rounds) if len(complete_rounds) == 3 else None,
            "max_seconds": max(complete_rounds) if len(complete_rounds) == 3 else None},
        "initialization": {"sdk_initialization_seconds": unique_init[0] if len(unique_init) == 1 else None,
            "unique_observed_values_seconds": unique_init,
            "scope": "one persistent SDK lifecycle; per-case references deduplicated, not summed"},
        "warmup": _timing(warmups), "warmup_telemetry": _telemetry(warmups, run),
        "errors": session.get("errors", [])}


def _display(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{value:.4f}" if isinstance(value, float) else str(value).replace("|", "\\|").replace("\n", " ")


def _metric(arm: dict[str, Any], path: str) -> Any:
    value: Any = arm["quality"]["micro"]
    for key in path.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _markdown(summary: dict[str, Any]) -> str:
    lines = ["# P05 MRoPE 受控优化实验", "",
        "这是开发实验，质量仅采用两组同一输入套件的第一轮；三轮性能分别保留。它不替换正式800页结果，也不代表独立未见测试。评分沿用已有冻结标准，报告只读取已生成的实验产物。", "",
        "| 对照组 | 套件 | 首轮计划样本/页 | 完整评分样本 | 内容召回 | 目标保守CER | 表格字段目标正确率 | 已标关系召回 |", "|---|---|---|---|---|---|---|---|"]
    for name, arm in summary["arms"].items():
        quality = arm["quality"]
        first = arm["performance_rounds"][0]
        lines.append("| " + " | ".join(_display(value) for value in (name, arm["suite"],
            f"{quality['planned_samples']}/{_display(first['planned_input_pages'])}",
            quality["planned_samples"] - quality["unscored_samples"],
            _metric(arm, "unit_presence.recall"), _metric(arm, "text.strict.cer"),
            _metric(arm, "table_records.field_target_correctness.value"), _metric(arm, "relations.recall"))) + " |")
    lines.extend(["", "首轮失败保留在已有评分的目标分母内；评分缺项时主质量指标为NA，已有子集值仅存机器文件，不能按子集宣称整体改善。", "",
        "| 对照组 | 第1轮秒 | 第2轮秒 | 第3轮秒 | 三轮中位数秒 | SDK初始化秒 | 推理服务就绪秒 | 预热秒 |", "|---|---|---|---|---|---|---|---|"])
    for name, arm in summary["arms"].items():
        lifecycle = (arm["artifacts"]["inference_lifecycle"] or {}).get("record", {})
        lines.append("| " + " | ".join(_display(value) for value in (name,
            *(row["processing_seconds_including_failures"] for row in arm["performance_rounds"]),
            arm["performance_summary"]["median_seconds"], arm["initialization"]["sdk_initialization_seconds"],
            lifecycle.get("initialization_to_readiness_host_seconds"),
            arm["warmup"]["processing_seconds_including_failures"])) + " |")
    lines.extend(["", "计时来自每个实际observation的processing_seconds，包含已测失败成本；缺测不填零。三轮成员不一致或计时不完整时总秒为NA，已测小计另存机器文件。两组都在worker处理计时内同步采集和保存相同诊断遥测，因此本轮秒数包含额外诊断与写盘开销，只作本轮两组间比较，不能与旧正式800页或80页的绝对耗时直接并列。初始化、预热及区域调用遥测单列；不从旧duration相减伪造去开销时间。", "",
        "| 对照组/轮次 | 完成样本/计划样本 | 遥测样本/计划样本 | 区域调用 | finish_reason=length | 已知生成tokens | token记录调用数 |", "|---|---|---|---|---|---|---|"])
    for name, arm in summary["arms"].items():
        for row in arm["performance_rounds"]:
            telemetry = row["telemetry"]
            usage = telemetry["usage"]["completion_tokens"]
            lines.append("| " + " | ".join(_display(value) for value in (
                f"{name}/r{row['repetition']}", f"{row['completed_samples']}/{row['planned_samples']}",
                f"{telemetry['cases_with_telemetry']}/{telemetry['planned_cases']}", telemetry["observed_calls"],
                telemetry["finish_reason_length_choices"], usage["observed_sum"],
                f"{usage['available_calls']}/{usage['total_calls']}")) + " |")
    lines.extend(["", "length或达到请求token上限是截断诊断信号，不能单独证明缺失内容。没有遥测记录不表示零tokens或没有失败。完整原始调用保留在各样本telemetry目录，报告不重新解释图片或参考。", "",
        "| 对照组 | glmocr版本声明 | 推理镜像声明 | 模型声明 | rotary设置 | repetition_penalty覆盖 |", "|---|---|---|---|---|---|"])
    for name, arm in summary["arms"].items():
        config = arm["config"]
        service = _glm_service(config)
        lines.append("| " + " | ".join(_display(value) for value in (name,
            config.get("versions", {}).get("glmocr"), service.get("inference_image", service.get("image", config.get("inference_image"))),
            service.get("model_name", config.get("glm_model")), service.get("rotary_embedding", "baseline custom-op dispatch"),
            config.get("glm_page_loader", {}).get("repetition_penalty", "official default"))) + " |")
    lines.extend(["", "表中版本/模型来自本次配置声明，不能替代实际包探测；实际镜像身份、CUDA Graph试验、资源采样及初始化就绪耗时见机器文件artifacts记录，缺测保持NA。", "",
        "两组配置差异路径：`" + "`, `".join(summary["configuration_difference_paths"]) + "`。预声明变量为native rotary；若还有其他差异，需先核对执行记录再作归因。", "",
        "同套件、同首轮成员配对：" + str(summary["paired_first_round_membership"]) + "。性能重复不增加独立文档数，不合成加权总分，不将本次开发实验覆盖推广到完整Lite或长文档。", "",
        "评分身份比较：同版评分代码=" + str(summary["comparison_identity"]["same_scoring_software"]) +
        "；同冻结参考=" + str(summary["comparison_identity"]["same_reference_freeze"]) +
        "；允许将首轮质量差异用于本实验归因=" + str(summary["comparison_identity"]["quality_attribution_ready"]) +
        "。身份缺失或不匹配、成员不一致、评分覆盖不完整时，各组原始结果仍保留，但不能据此宣称优化改善。", "",
        "机器明细：[optimization-summary.json](optimization-summary.json)。基线：[run.json](baseline/run.json)；native：[run.json](native/run.json)。", ""])
    return "\n".join(lines)


def generate_p05_optimization_report(experiment_root: Path) -> Path:
    """Write deterministic JSON and Markdown from two existing scored arms."""
    root = Path(experiment_root).resolve()
    experiment = _read(root / "experiment.json")
    arms = {name: _arm(root / name) for name in _ARMS}
    if arms["baseline"]["suite"] != arms["native"]["suite"]:
        raise ValueError("baseline and native quality must use the same suite")
    scoring_ids = [(arm.get("scoring_software") or {}).get("software_id") for arm in arms.values()]
    freezes = [arm.get("reference_freeze") for arm in arms.values()]
    identities = {"same_scoring_software": bool(scoring_ids[0]) and scoring_ids[0] == scoring_ids[1],
                  "same_reference_freeze": freezes[0] is not None and freezes[0] == freezes[1]}
    paired = arms["baseline"]["quality_members"] == arms["native"]["quality_members"]
    identities["quality_attribution_ready"] = paired and all(identities.values()) and all(
        arm["quality"]["target_denominator_complete"] for arm in arms.values())
    summary = {"schema": "moparse-p05-optimization-report-v1", "experiment": experiment,
        "scope": "development_only_existing_output_report_no_formal_result_replacement",
        "quality_repetition": 1, "performance_repetitions": [1, 2, 3],
        "paired_first_round_membership": paired, "comparison_identity": identities,
        "configuration_difference_paths": _differences(arms["baseline"]["config"], arms["native"]["config"]),
        "arms": arms, "corpus_review_or_acceptance": False, "weighted_total_score": None,
        "timing_scope": "both arms include synchronous diagnostic collection and artifact writes inside worker processing_seconds; compare within this experiment only, not absolute formal benchmark durations"}
    (root / "optimization-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    destination = root / "optimization-report.md"
    destination.write_text(_markdown(summary), encoding="utf-8")
    return destination
