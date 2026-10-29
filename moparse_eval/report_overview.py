"""Render a concise comparison from existing benchmark aggregates only.

This presentation layer neither reads reference material nor runs a scorer.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any, cast

_NAMES = {
    "P01": "Docling TableFormer V1 + GLM-OCR SDK",
    "P02": "Docling TableFormer V2 + GLM-OCR SDK",
    "P03": "PaddleOCR-VL 1.5 全页",
    "P04": "PaddleOCR-VL 1.6 全页",
    "P05": "GLM-OCR SDK 全页",
    "P06": "MinerU Standard + TXT + GLM-OCR SDK",
    "P07": "MinerU Advanced + TXT + GLM-OCR SDK",
    "P08": "MinerU 纯视觉官方 SDK + vLLM",
}
_METRICS = (
    ("内容定位召回", "unit_presence.recall", False),
    ("值与行列标签正确覆盖", "table_records.field_target_correctness.value", False),
    ("完整已标信息正确覆盖", "table_records.information_target_correctness.value", False),
)
RELATION_STATES = (
    ("confirmed_correct", "明确正确", "#228833"),
    ("confirmed_incorrect", "明确不符", "#CC6677"),
    ("native_not_provided", "未获关系证据", "#DDCC77"),
    ("endpoint_unresolved", "端点未定位", "#88AABB"),
    ("unassessable", "证据或读取未判定", "#BBBBBB"),
)
_VERSION_PACKAGES = {
    "P01": (("Docling", "docling", None), ("glmocr SDK", "glmocr", None)),
    "P02": (("Docling", "docling", None), ("glmocr SDK", "glmocr", None)),
    "P03": (("PaddleOCR", "paddleocr", "paddle"), ("PaddleX", "paddlex", "paddle"),
            ("Transformers", "transformers", "paddle")),
    "P04": (("PaddleOCR", "paddleocr", "paddle"), ("PaddleX", "paddlex", "paddle"),
            ("Transformers", "transformers", "paddle")),
    "P05": (("glmocr SDK", "glmocr", None), ("vLLM", "vllm", "glm")),
    "P06": (("MinerU", "mineru", None), ("glmocr SDK", "glmocr", None)),
    "P07": (("MinerU", "mineru", None), ("glmocr SDK", "glmocr", None)),
    "P08": (("mineru-vl-utils", "mineru-vl-utils", None), ("vLLM", "vllm", "mineru")),
}


def _package_versions(report: dict[str, Any], pipeline: str) -> str:
    """Read versions from the saved worker or GPU-role image observation."""
    inspection = report.get("software_inspection") or {}
    record = inspection.get("record") or {}
    image = (record.get("pipelines") or {}).get(pipeline) or {}
    labels = []
    for label, package, role in _VERSION_PACKAGES.get(pipeline, ()):
        images = [image] if role is None else [
            item for item in image.get("inference") or [] if item.get("role") == role
        ]
        versions = [(item.get("versions") or {}).get(package) for item in images]
        known = {value for value in versions if isinstance(value, str) and value.strip()}
        version = next(iter(known)) if len(known) == 1 and all(versions) else "NA"
        labels.append(f"{label} {_text(version)}")
    return "；".join(labels) or "NA"


def _value(record: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(record, dict):
            return None
        record = record.get(key)
    return record


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _text(value: Any) -> str:
    return "NA" if value is None else str(value).replace("\n", " ").replace("|", "\\|")


def _pct(value: Any) -> str:
    return f"{value * 100:.2f}%" if _number(value) else "NA"


def _count(value: Any) -> str:
    return f"{value:,}" if type(value) is int else _text(value)


def _minutes(value: Any) -> str:
    return f"{value / 60:.2f}" if _number(value) else "NA"


def _ratio(numerator: Any, denominator: Any) -> str:
    if not _number(numerator) or not _number(denominator):
        return "NA"
    return f"{_count(numerator)} / {_count(denominator)}"


def _shared(records: list[dict[str, Any]], path: str) -> str:
    """Show a shared measured value, never silently select a partial group's value."""
    values = [_value(record, path) for record in records]
    if not values or any(value is None for value in values):
        return "NA"
    if all(value == values[0] for value in values):
        return _count(values[0])
    return "各组不同，见表"


def _figure(figures: dict[str, dict[str, Any]], ident: str) -> list[str]:
    figure = figures.get(ident)
    if not figure:
        return []
    title = _text(figure.get("title") or ident)
    lines = []
    if figure.get("png"):
        lines.extend([f"![{title}]({figure['png']})", ""])
    links = [f"[{kind.upper()}]({figure[kind]})" for kind in ("svg", "pdf") if figure.get(kind)]
    caption = _text(figure.get("caption")) if figure.get("caption") else ""
    if links:
        caption += (" " if caption else "") + " · ".join(links)
    if caption:
        lines.extend([caption, ""])
    return lines


def _leaders(groups: dict[str, dict[str, Any]]) -> list[str]:
    statements = []
    for label, path, lower in _METRICS:
        measured = [(name, _value(group, f"quality.micro.{path}")) for name, group in groups.items()]
        if path.startswith("table_records.field_"):
            metric = path.split(".")[1]
            measured = [(name, table_field_breakdown(_value(group, "quality.micro.table_records"))[metric]["value"])
                        for name, group in groups.items()]
        available = [(name, value) for name, value in measured if _number(value)]
        if not available:
            continue
        best = min(value for _, value in available) if lower else max(value for _, value in available)
        names = "、".join(name for name, value in available if math.isclose(value, best, abs_tol=1e-12))
        statements.append(f"{label}{'最低' if lower else '最高'}为 {names}（{_pct(best)}）")
    if not statements:
        return ["当前没有可比较的正式质量数值；缺测保持 NA，不能从执行完成推定内容正确。", ""]
    return ["；".join(statements) + "。这些指标分别回答不同问题，不合成为总分。", ""]


def _reversals(groups: dict[str, dict[str, Any]]) -> list[str]:
    """Explain observed micro/macro order reversals without hardcoded scores."""
    reversals = []
    for left, right in combinations(sorted(groups), 2):
        a, b = groups[left].get("quality") or {}, groups[right].get("quality") or {}
        am, bm = _value(a, "micro.text.strict.cer"), _value(b, "micro.text.strict.cer")
        ad = (a.get("macro_by_document") or {}).get("text.strict.cer", {}).get("value")
        bd = (b.get("macro_by_document") or {}).get("text.strict.cer", {}).get("value")
        if not all(_number(value) for value in (am, bm, ad, bd)) or (am - bm) * (ad - bd) >= 0:
            continue
        micro_name, macro_name = (left, right) if am < bm else (right, left)
        micro_best, micro_other = (am, bm) if am < bm else (bm, am)
        macro_best, macro_other = (bd, ad) if am < bm else (ad, bd)
        text = (
            f"{micro_name} 的字符微平均 CER 更低（{_pct(micro_best)} 对 {_pct(micro_other)}），"
            f"文档宏平均则由 {macro_name} 更低（{_pct(macro_best)} 对 {_pct(macro_other)}）"
        )
        af = (a.get("macro_by_family") or {}).get("text.strict.cer", {}).get("value")
        bf = (b.get("macro_by_family") or {}).get("text.strict.cer", {}).get("value")
        if all(_number(value) for value in (af, bf)) and (am - bm) * (af - bf) < 0:
            family_best, family_other = (bf, af) if am < bm else (af, bf)
            text += f"，家族宏平均也发生反转（{_pct(family_best)} 对 {_pct(family_other)}）"
        reversals.append((abs(am - bm), text + "。"))
    if not reversals:
        return ["字符微平均按参考字符数加权，文档和家族宏平均给予各组相同权重；它们不可互相替代，NA 组数见附录。", ""]
    lines = [text for _, text in sorted(reversals)[:2]]
    return [" ".join(lines) + " 这说明长内容的权重会影响结论，不能只看一个总体均值。", ""]


def _pareto_lines(figure: dict[str, Any]) -> list[str]:
    """Explain only the discrete frontier calculated from the plotted data."""
    analyses = (figure.get("data") or {}).get("pareto") or {}
    lines = [
        "帕累托判定：另一配置耗时不更高、该项质量不更差，且至少一项更优时，当前配置被支配。"
        "两项质量分别计算，不合成加权总分。", "",
    ]
    labels = (("content_recall", "耗时与内容定位覆盖"), ("information_target_correctness", "耗时与完整信息覆盖"))
    for key, label in labels:
        analysis = analyses.get(key) or {}
        if not analysis:
            continue
        frontier = " → ".join(analysis.get("frontier") or []) or "NA"
        dominated = "、".join(analysis.get("dominated") or []) or "无"
        lines.extend([f"{label}的前沿（按耗时递增）：**{frontier}**；被支配配置：{dominated}。", ""])
    return lines


def _quality_table(names: list[str], groups: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| 配置 | 内容定位覆盖 ↑ | 已定位正文 CER ↓ | 正文字符定位覆盖 | 值与行列标签正确覆盖 ↑ | 完整已标信息正确覆盖 ↑ |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in names:
        micro = _value(groups.get(name), "quality.micro") or {}
        table = table_field_breakdown(micro.get("table_records"))
        aligned = _value(micro, "text_aligned.strict.reference_chars")
        total = _value(micro, "text.strict.reference_chars")
        values = " | ".join([
            _pct(_value(micro, "unit_presence.recall")), _pct(_value(micro, "text_aligned.strict.cer")),
            _pct(aligned / total if _number(aligned) and _number(total) and total else None),
            _pct(table["field_target_correctness"]["value"]),
            _pct(_value(micro, "table_records.information_target_correctness.value")),
        ])
        lines.append(f"| {_text(name)} | {values} |")
    return [*lines, ""]


def _information_table(names: list[str], groups: dict[str, dict[str, Any]]) -> list[str]:
    lines = ["| 配置 | 完整信息正确 / 全部目标 | 明确错误 | 尚未确定 | 可判范围正确率 |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for name in names:
        table = _value(groups.get(name), "quality.micro.table_records") or {}
        lines.append(f"| {name} | {_ratio(table.get('information_correct_fields'), table.get('target_fields'))} | "
                     f"{_count(table.get('information_incorrect_fields'))} | {_count(table.get('information_unresolved_fields'))} | "
                     f"{_pct(_value(table, 'information_compared_accuracy.value'))} |")
    return [*lines, ""]


def relation_breakdown(record: Any) -> dict[str, Any]:
    """Project explicit, closed relation categories; never classify old unknowns.

    The caller supplies aggregate score data only. Missing category counts make
    the row unavailable, even when a legacy overall recall value is present.
    """
    record = record if isinstance(record, dict) else {}
    denominator = record.get("denominator")
    states = {key: record.get(key) for key, _, _ in RELATION_STATES}
    available = (type(denominator) is int and denominator >= 0
                 and all(type(value) is int and value >= 0 for value in states.values())
                 and sum(states.values()) == denominator)
    known = states["confirmed_correct"] + states["confirmed_incorrect"] if available else 0
    return {
        "available": available,
        "denominator": denominator if type(denominator) is int and denominator >= 0 else None,
        "states": states if available else {key: None for key in states},
        "value": record.get("value") if available and _number(record.get("value")) and denominator else None,
        "conditional_accuracy": states["confirmed_correct"] / known if known else None,
        "conditional_denominator": known if available else None,
        "status": "classified" if available else "review_pending",
    }


def _relation_table(names: list[str], groups: dict[str, dict[str, Any]], kind: str,
                    *, conditional: bool = False) -> list[str]:
    lines = [
        "| 配置 | 全部目标 | 明确正确 | 明确不符 | 未获关系证据 | 端点未定位 | 证据或读取未判定 | 全目标满足率 |"
        + (" 可判正确率 |" if conditional else ""),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |" + (" ---: |" if conditional else ""),
    ]
    for name in names:
        record = _value(groups.get(name), f"quality.micro.relations.by_type.{kind}")
        row = relation_breakdown(record)
        states = " | ".join(_count(row["states"][key]) for key, _, _ in RELATION_STATES)
        rate = _pct(row["value"]) if row["available"] else "NA（复核中）"
        suffix = f" {_pct(row['conditional_accuracy'])} |" if conditional else ""
        lines.append(f"| {_text(name)} | {_count(row['denominator'])} | {states} | {rate} |{suffix}")
    return [*lines, ""]


def _relation_section(names: list[str], groups: dict[str, dict[str, Any]],
                      figures: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "### 阅读顺序", "",
        "主比较只展示 before：先独立定位端点，再比较原生顺序。全部已标顺序目标保留在分母，未定位或读取未判定不算正确。"
        "标题层级及其他关系仅列[详细附录](appendix.md)，不作为主比较能力排名。", "",
    ]
    lines.extend(_figure(figures, "relations"))
    lines.extend(_relation_table(names, groups, "before"))
    return lines


def table_field_breakdown(record: Any) -> dict[str, Any]:
    """Project the new candidate-score ledger; legacy accuracy is never reused."""
    record = record if isinstance(record, dict) else {}
    keys = ("target_fields", "compared_fields", "target_missing_fields", "unresolved_fields",
            "correct_fields", "strict_correct_fields")
    counts: dict[str, Any] = {key: record.get(key) if type(record.get(key)) is int and record[key] >= 0 else None
              for key in keys}
    available = (all(value is not None for value in counts.values())
                 and counts["compared_fields"] + counts["target_missing_fields"] + counts["unresolved_fields"] == counts["target_fields"]
                 and counts["strict_correct_fields"] <= counts["correct_fields"] <= counts["compared_fields"])
    rates = {}
    for key in ("field_target_correctness", "field_compared_accuracy"):
        metric = record.get(key) or {}
        denominator = counts["target_fields"] if key == "field_target_correctness" else counts["compared_fields"]
        consistent = (available and metric.get("numerator") == counts["correct_fields"]
                      and metric.get("denominator") == denominator)
        value = metric.get("value")
        if consistent:
            consistent = (value is None if denominator == 0 else
                          _number(value) and math.isclose(cast(float, value), counts["correct_fields"] / denominator, abs_tol=1e-12))
        rates[key] = {field: metric.get(field) if consistent else None
                      for field in ("value", "numerator", "denominator")}
    return {"available": available, **counts, **rates}


def _table_coverage(names: list[str], groups: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| 配置 | 已证正确字段覆盖率（正确/目标） | 已比较字段正确率（正确/已比较） | 已比较 / 目标格未取到值 / 未判定 | 全部字段目标 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in names:
        table = table_field_breakdown(_value(groups.get(name), "quality.micro.table_records"))
        target, compared = table["field_target_correctness"], table["field_compared_accuracy"]
        lines.append(
            f"| {_text(name)} | {_pct(target['value'])} ({_ratio(target['numerator'], target['denominator'])}) | "
            f"{_pct(compared['value'])} ({_ratio(compared['numerator'], compared['denominator'])}) | "
            f"{_count(table['compared_fields'])} / {_count(table['target_missing_fields'])} / {_count(table['unresolved_fields'])} | "
            f"{_count(table['target_fields'])} |"
        )
    return [*lines, ""]


def _timing_table(names: list[str], quality: dict[str, dict[str, Any]], perf: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| 配置 | 完成输入页 / 已计划页 | 正式集分钟 / 完整计时轮数 | 性能子集中位分钟 / 完整计时轮数 | 失败或部分样本 / 未评分样本 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in names:
        q = quality.get(name) or {}
        summary = _value(q, "performance.round_duration_summary") or {}
        rounds = _value(q, "performance.rounds") or []
        first = rounds[0] if len(rounds) == 1 else {}
        ps = _value(perf.get(name), "performance.round_duration_summary") or {}
        complete = _ratio(first.get("completed_input_pages"), first.get("attempted_input_pages"))
        lines.append(
            f"| {_text(name)} | {complete} | {_minutes(summary.get('median_seconds'))} / {_count(summary.get('n'))} | "
            f"{_minutes(ps.get('median_seconds'))} / {_count(ps.get('n'))} | "
            f"{_count(_value(q, 'quality.failed_samples'))} / {_count(_value(q, 'quality.unscored_samples'))} |"
        )
    return [*lines, ""]


def _coverage_lines(groups: dict[str, dict[str, Any]]) -> list[str]:
    qualities = [group.get("quality") or {} for group in groups.values()]
    coverages = [quality.get("coverage") or {} for quality in qualities]
    micros = [quality.get("micro") or {} for quality in qualities]
    return [
        f"评分范围包含 {_shared(coverages, 'scored_units')} 个内容单元、{_shared(coverages, 'text_reference_chars')} 个参考字符、"
        f"{_shared(micros, 'table_records.target_fields')} 个表格字段目标和 {_shared(coverages, 'scored_relations')} 条已标关系。"
        f"声明单元 {_shared(coverages, 'declared_units')}、已确认单元 {_shared(coverages, 'confirmed_units')} 与实际评分单元不是同一个分母。",
        "",
        f"已知图片目标 {_shared(coverages, 'known_image_targets')} 个；本轮没有形成图片输出身份的全量视觉评分，图片保全为 NA。"
        "缺少独立标注的原始结构、未闭合范围的 Precision / F1、不可辨和未标内容保持未测或未知；未测不能计为正确。",
        "",
        "文字投影固定使用 CommonMark 和 HTML，未统一数学扩展；数学定界符与命令可能保留为字符差异。"
        "因此 CER 不能直接解释为数学表达或业务含义错误率，具体实现边界见[评分标准](../../evaluation-tasks.md#42-表示与汇总)。",
        "",
    ]


def render_overview(report: dict[str, Any], figures: list[dict[str, Any]] | None = None) -> str:
    """Present comparison charts and conclusions, linking full detail to appendices."""
    figures_by_id = {str(item.get("id")): item for item in figures or []}
    groups = report.get("groups") or []
    declared = (report.get("execution") or {}).get("configurations") or []
    datasets = sorted({str(group.get("dataset") or "未声明数据集") for group in groups})
    if not datasets and _value(report, "execution.dataset_name"):
        datasets = [str(report["execution"]["dataset_name"])]
    declared_names = {str(item["pipeline"]) for item in declared if item.get("pipeline")}
    names = sorted(declared_names | {str(group["pipeline"]) for group in groups if group.get("pipeline")})
    lines = [
        "# MO-Parse 解析评测报告", "",
        f"运行版本：`{_text(_value(report, 'execution.run_id'))}`；评分版本：`{_text(report.get('score_id'))}`。"
        "八套配置的模型和软件版本见下表，完整执行、评分与报告生成身份分别保存在附录和机器汇总中。", "",
        f"评分协议：`{_text(_value(report, 'scoring_protocol.id'))}`；报告生成身份与执行、评分身份独立记录。", "",
        "本页以expected中的预期信息为主线，比较八套固定管线的信息完整性、准确性、必要归属与成本，不计算加权总分；完整配置与长表移至[详细附录](appendix.md)。"
        "质量读取当前评分索引，耗时使用保存的直接测量；重新评分不意味着重新执行管线，也不构成语料重新验收。", "",
        "本报告比较八套冻结原生配置，不评价MO-Parse最终转换，也没有比较独立的通用原生PDF解析基线；固定配置之间的成绩不代表最终服务经过充分优化后的能力上限。", "",
    ]
    maintenance = report.get("maintenance") or {}
    budget = _shared(declared, "resources.gpu_memory_gib")
    identity_status = _value(maintenance, "tts_identity_condition.status")
    calls_status = _value(maintenance, "tts_no_calls_condition.status")
    observe_only = maintenance.get("tts_observation_policy") == "observe_only"
    if observe_only:
        lines.extend([
            f"本次资源条件：GPU 1 受测后端共享 {budget} GiB 自有显存（owned）预算；"
            "`observe_only`策略下TTS保持运行，评测不控制其活动，性能反映实际共驻条件。"
            f"身份观测 `{_text(identity_status if isinstance(identity_status, str) and identity_status else None)}`，"
            f"活动观测 `{_text(calls_status if isinstance(calls_status, str) and calls_status else None)}`。"
            "缺测显示NA，不代表GPU独占或确定无调用；详情见[环境附录](appendix.md#tts测量条件与服务恢复)。", "",
        ])
        if identity_status == "changed" or calls_status in ("observed_activity", "violated"):
            lines.extend(["已观测到TTS身份变化或活动，可能干扰本轮耗时和资源读数；按observe_only只披露，不据此自动判性能无效或阻止报告。", ""])
    else:
        lines.extend([
            f"本次资源条件：GPU 1 受测后端共享 {budget} GiB 自有显存（owned）预算；"
            f"TTS 策略 `{_text(maintenance.get('tts_policy'))}`，调用条件 `{_text(maintenance.get('tts_calls'))}`。"
            f"身份观测 `{_text(identity_status if isinstance(identity_status, str) and identity_status else None)}`，"
            f"无调用观测 `{_text(calls_status if isinstance(calls_status, str) and calls_status else None)}`。"
            "`user_declared_none`只是用户声明，并非调用监控结论；缺失显示NA，NA或unknown不表示条件满足，起末观测不能证明全程无调用。"
            "身份前后值、观测限制及余量见[环境附录](appendix.md#tts测量条件与服务恢复)。", "",
        ])
    if not observe_only and (identity_status == "changed" or calls_status == "violated"):
        lines.extend(["TTS实际观测条件已被违反，本轮性能测量不能作为既定共驻条件下的正式比较；MO-Parse服务恢复健康单独记录。", ""])
    if not datasets:
        lines.extend(["当前没有正式聚合结果，质量、耗时和资源均为 NA。", ""])
    for dataset in datasets:
        selected = [group for group in groups if str(group.get("dataset") or "未声明数据集") == dataset]
        quality = {str(group["pipeline"]): group for group in selected if group.get("suite") == "quality800"}
        perf = {str(group["pipeline"]): group for group in selected if group.get("suite") == "perf80"}
        lines.extend([f"## 先看主要差异 · {_text(dataset)}", ""])
        lines.extend(_leaders(quality))
        comparable_costs = [
            (name, _value(group, "performance.round_duration_summary.median_seconds"))
            for name, group in quality.items()
            if _value(group, "performance.round_duration_summary.n") == 1
            and _value(group, "performance.rounds")
            and all(row.get("all_samples_completed") and row.get("timing_complete")
                    for row in _value(group, "performance.rounds") or [])
        ]
        available_costs = [(name, seconds) for name, seconds in comparable_costs if _number(seconds)]
        comparable_pages = {_value(quality[name], "quality.input_pages") for name, _ in available_costs}
        if available_costs and len(comparable_pages) == 1 and None not in comparable_pages and not observe_only:
            name, seconds = min(available_costs, key=lambda pair: pair[1])
            lines.extend([f"在具有完整单轮计时和样本完成记录的配置中，{name} 的正式集处理时间最短，为 {_minutes(seconds)} 分钟。质量与成本取舍见下图；单项领先不代表整体优胜。", ""])
        lines.extend([
            "## 测量范围与配置", "",
            f"正式质量集每组记录 {_shared([_value(quality.get(name), 'quality') or {} for name in names], 'input_pages')} 个实际输入页，"
            f"包含 {_shared([_value(quality.get(name), 'quality') or {} for name in names], 'samples')} 个样本、"
            f"{_shared([_value(quality.get(name), 'quality') or {} for name in names], 'documents')} 份原文档和 "
            f"{_shared([_value(quality.get(name), 'quality') or {} for name in names], 'families')} 个家族。"
            "正式集只计划每组一次；独立性能子集另作重复测量，实际完整轮数见耗时表。单页、连续页段与短文档共同构成输入，结论不外推到 Full 或完整超长文档。", "",
            "Lite 包含开发、预检与参考编写暴露，逐样本历史 unknown 也不等于未见测试；性能轮次不增加独立文档数。"
            "来源分类保持冻结声明，source-unknown 不能用于判断原生页或扫描页的方法优势。", "",
            "| 配置 | 固定管线身份 | 本次软件与 SDK 版本 |", "| --- | --- | --- |",
        ])
        lines.extend(f"| {_text(name)} | {_NAMES.get(name, '见运行配置')} | {_package_versions(report, name)} |" for name in names)
        lines.extend([
            "", "表中软件版本来自保存的运行镜像记录；TableFormer V1 / V2 和 PaddleOCR-VL 1.5 / 1.6 是模型版本，PaddleOCR、PaddleX、glmocr 等是软件或 SDK 包版本，缺测保留 NA。"
            "MinerU 各视觉分支使用的模型为 MinerU2.5-Pro；完整权重 revision、推理框架、分支和解码参数见[实际运行配置](run.json)与[环境附录](appendix.md#实际环境证据与初始化成本)。"
            "执行源码身份与评分身份分别保留，不能把后续报告生成的源码身份写成原测量版本。", "",
        ])
        configuration_notes = [item for item in report.get("overview_configuration_notes") or []
                               if isinstance(item, dict) and item.get("note") and item.get("path")]
        if configuration_notes:
            lines.extend([
                "### 配置补充说明", "",
                "| 配置 | 已声明事项与证据 | 适用范围 |", "| --- | --- | --- |",
            ])
            for item in configuration_notes:
                lines.append(
                    f"| {_text(item.get('pipeline'))} | "
                    f"[{_text(item['note'])}]({_text(item['path'])}) | {_text(item.get('scope'))} |"
                )
            lines.append("")
        source_selection = _value(report, "execution.composition.selected_sources") or {}
        if source_selection:
            lines.extend(["本报告组合了运行记录中明确声明的执行来源，各配置的来源与软件身份见附录；组合本身不产生新的推理或修复结论。", ""])
        lines.extend([
            "## 质量与成本对照", "", "### 内容、文字与表格", "",
            "内容定位覆盖只表示已标目标是否定位，不等于内容全部正确。主表CER只比较已经定位的正文，同时给出字符定位覆盖；各组已定位范围不同，不单独凭此CER排名。"
            "表格先比较值及所需行列标签，再检查参考已声明的单位、期间和附注，形成完整已标信息正确覆盖。两者均保留全部字段目标；位置和路径分段差异不单独扣分。", "",
        ])
        lines.extend(_figure(figures_by_id, "quality"))
        lines.extend(_quality_table(names, quality))
        lines.extend(["未定位原因及把未定位参考计为删除的目标CER，连同字符、文档和家族平均对照，放入[诊断附录](appendix.md)。这些诊断不进入主帕累托分析。", ""])
        lines.extend(["### 完整信息：值、对象与限定语", "",
                      "正确要求值、所需行列标签及参考已声明的单位、期间、附注共同成立。明确错误至少有一项可判内容不符；尚未确定包括定位歧义或限定信息读取不足，不能统称模型遗漏。", ""])
        lines.extend(_information_table(names, quality))
        lines.extend(["### 表格：正确与未判定分别保留", "", "已比较字段正确率不含目标格未取到值及未判定字段；已证正确字段覆盖率始终保留全部字段目标。高条件正确率不能替代目标覆盖。目标格未取到值不证明文字在整个输出中遗漏。缺少新版评分字段时保持 NA，不沿用旧准确率。严格字符差异仅在附录作为诊断。", ""])
        lines.extend(_figure(figures_by_id, "table-coverage"))
        lines.extend(_table_coverage(names, quality))
        lines.extend([
            "值与行列标签成绩不代表全部限定信息正确；完整信息指标才同时要求已标限定语。两者均只覆盖已有人工信息目标，不宣称全表穷尽或原版式还原。结构和其他关系仅用于[分项诊断](appendix.md)。", "",
        ])
        lines.extend(_relation_section(names, quality, figures_by_id))
        lines.extend([
            "## 处理成本、波动与稳定性", "",
            "正式集耗时是 worker 开始处理已就绪 PDF 至原生结果、忠实 Markdown 和必要资产就绪的直接测量，包含共同前处理、渲染、解析和导出。"
            "模型初始化、预热及评分另列；HTTP 排队和 MO-Parse 最终语义转换不在主耗时内。", "",
        ])
        lines.extend(_figure(figures_by_id, "quality-time"))
        lines.extend(_timing_table(names, quality, perf))
        lines.extend(_figure(figures_by_id, "perf-repeat"))
        lines.extend([
            "性能子集每轮使用相同样本边界和顺序；图中保留实际轮值及中位数。正式集 n=1 与性能子集的重复测量分开，三轮波动不作为统计显著性或独立文档证据。"
            "失败尝试保留在计划页与耗时口径中，缺失计时为 NA；完成输入页不等于内容正确。", "",
            "### 质量与成本的帕累托分析", "",
        ])
        lines.extend(_figure(figures_by_id, "tradeoff"))
        lines.extend(_pareto_lines(figures_by_id.get("tradeoff") or {}))
        lines.extend([
            "### 宿主内存与显存", "",
        ])
        lines.extend(_figure(figures_by_id, "resources"))
        lines.extend([
            "宿主内存与 GPU 显存分开展示，CPU worker 和 GPU 服务也分别标识；它们不是同一种内存。显存图只统计受测容器及其compute子进程的同时聚合占用，排除驻留TTS；整卡占用和TTS观测另列附录，自有显存未知时保持NA。生命周期采样包含初始化，可能漏掉短时峰值，观测峰值只代表已采到的范围，不能视为精确绝对峰值或单样本成本。"
            "固定资源预算、CUDA Graphs 实际例外及 P03 / P04 修复证据见[环境与运行明细](appendix.md#实际环境证据与初始化成本)。", "",
            "## 哪些类别差异较大", "",
        ])
        lines.extend(_figure(figures_by_id, "categories"))
        lines.extend([
            "类别图使用冻结样本标签及已有质量切片，每格保留样本或文档范围；多标签可以重叠，不能把类别页数相加。小类别和 NA 保持可见，不把单一家族的差异概括为普遍优势。"
            "完整[标签长表](group-comparisons.md#tag)、[原文档对照](group-comparisons.md#document)与[家族对照](group-comparisons.md#family)置于附录入口。", "",
            "## 结论覆盖到哪里", "",
        ])
        lines.extend(_figure(figures_by_id, "coverage"))
        lines.extend(_coverage_lines(quality))
    lines.extend(["### 已目读的有限案例", ""])
    review = report.get("qualitative_review")
    cases = [item for item in report.get("overview_case_studies") or []
             if isinstance(item, dict) and item.get("observation") and item.get("path")]
    if review:
        lines.extend([
            f"[人工个案与证据]({_text(review)})保留原页目读记录、实际输出及各自适用边界，用于解释已列评分项与原生产物之间的具体差异。"
            "正文不增补未目读截图，也不把有限案例外推为全量图片保全或内容验收。", "",
        ])
    if cases:
        lines.extend([
            "| 配置 | 已有人工作业记录中的现象 | 证据边界 |", "| --- | --- | --- |",
        ])
        for item in cases:
            lines.append(
                f"| {_text(item.get('pipeline'))} | "
                f"[{_text(item['observation'])}]({_text(item['path'])}) | {_text(item.get('scope'))} |"
            )
        lines.append("")
    elif not review:
        lines.extend(["未提供可引用的原页目读个案记录，本页不补造错误案例或截图。", ""])
    lines.extend([
        "## 附录与复现入口", "",
        "| 需要了解的内容 | 入口 |", "| --- | --- |",
        "| 完整指标、分母、初始化、软件与逐组明细 | [详细附录](appendix.md) |",
        "| 按文档、家族、标签、来源和样本比较 | [切片长表](group-comparisons.md) · [质量切片 CSV](quality-slices.csv) |",
        "| 机器可读汇总与完整指标 | [summary.json](summary.json) · [metrics.csv](metrics.csv) |",
        "| 逐字段状态、原生证据及未判原因 | [field-details.csv](field-details.csv) |",
        "| 实际执行配置、源码与资源声明 | [run.json](run.json) · [环境明细](appendix.md#实际环境证据与初始化成本) |",
    ])
    for key, label in (
        ("score_index", "逐项评分、匹配诊断及扣分理由"),
        ("scoring_notes", "冻结标准与评分实现修复"),
        ("execution_failure_notes", "失败、部分输出和历史重跑范围"),
    ):
        if report.get(key):
            lines.append(f"| {label} | [记录]({_text(report[key])}) |")
    lines.extend([
        "| 图表的聚合数据与导出 | [图表目录](figures/) |", "",
        "以上只报告本轮 Lite 的质量与成本，不把打包、评分或报告生成当作语料复核证据。Full 本轮没有推理成绩，未知与未测范围继续保留。", "",
    ])
    return "\n".join(lines)
