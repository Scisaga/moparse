"""Draw report comparisons from existing aggregate measurements only.

This module never loads pipeline answers, source documents, annotations or
references.  Figure data is an explicit projection of the report dictionary.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from .report_overview import RELATION_STATES, relation_breakdown, table_field_breakdown

PIPELINE_COLORS = {
    "P01": "#4477AA", "P02": "#66AADD", "P03": "#228833", "P04": "#66AA55",
    "P05": "#CC6677", "P06": "#AA7733", "P07": "#AA4499", "P08": "#332288",
}

# These are existing authored content/difficulty tags, selected by meaning, not
# their observed scores.  They overlap and do not partition the dataset.
REPRESENTATIVE_TAGS = (
    ("ordinary-prose", "普通正文"), ("multi-column", "多栏"),
    ("data-table", "数据表"), ("layout-grid-prose", "网格正文"),
    ("cross-page-paragraph", "跨页段落"), ("cross-page-table", "跨页表格"),
    ("mixed-script", "混合文字"), ("negative-values", "负数值"),
)


def _register_cjk_fonts(directory: Path) -> None:
    """Expose the SC face in system TTC collections to Matplotlib.

    Matplotlib may only discover the first face (JP) in a TTC.  Exporting the
    installed SC face is font preparation, not processing any report inputs.
    The files also make the selected Chinese fonts portable with the figures.
    """
    from fontTools.ttLib import TTCollection
    from matplotlib import font_manager

    font_directory = directory / "fonts"
    for style in ("Regular", "Bold"):
        output = font_directory / f"NotoSansCJKSC-{style}.otf"
        if output.is_file():
            font_manager.fontManager.addfont(str(output))
            continue
        sources = sorted(path for path in font_manager.findSystemFonts()
                         if Path(path).name == f"NotoSansCJK-{style}.ttc")
        if not sources:
            try:
                font_manager.findfont(font_manager.FontProperties(family="Noto Sans CJK SC",
                                                                  weight="bold" if style == "Bold" else "normal"),
                                      fallback_to_default=False)
            except ValueError as error:
                raise RuntimeError("Noto Sans CJK SC is required to export readable Chinese charts") from error
            continue
        with TTCollection(sources[0], lazy=True) as collection:
            candidates = [font for font in collection.fonts
                          if font["name"].getBestFamilyName() == "Noto Sans CJK SC"]
            if len(candidates) != 1:
                raise RuntimeError(f"Cannot select Noto Sans CJK SC face in {sources[0]}")
            font_directory.mkdir(parents=True, exist_ok=True)
            candidates[0].recalcTimestamp = False
            candidates[0].save(output)
        font_manager.fontManager.addfont(str(output))
    license_path = Path("/usr/share/doc/fonts-noto-cjk/copyright")
    if font_directory.is_dir() and license_path.is_file():
        (font_directory / "COPYRIGHT.txt").write_text(license_path.read_text(), encoding="utf-8")


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _value(record: dict[str, Any], path: str) -> float | None:
    if path.startswith(("table_records.field_target_correctness.", "table_records.field_compared_accuracy.")):
        _, metric, field = path.split(".")
        return _number(table_field_breakdown(record.get("table_records"))[metric][field])
    current: Any = record
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _number(current)


def _group(report: dict[str, Any], pipeline: str, suite: str) -> dict[str, Any]:
    matches = [group for group in report.get("groups", [])
               if group.get("pipeline") == pipeline and group.get("suite") == suite]
    # Do not silently choose a dataset or one of multiple quality runs.
    return matches[0] if len(matches) == 1 else {}


def _source(report: dict[str, Any], *extra: str) -> list[str]:
    return list(dict.fromkeys(["summary.json", str(report.get("score_index") or "summary.json"), *extra]))


def _scope_label(report: dict[str, Any], pipelines: list[str], suite: str) -> str:
    counts = []
    for pipeline in pipelines:
        group = _group(report, pipeline, suite)
        pages = _number(group.get("quality", {}).get("input_pages"))
        rounds = group.get("performance", {}).get("rounds", [])
        if pages is None and rounds:
            round_pages = {_number(row.get("attempted_input_pages")) for row in rounds}
            pages = next(iter(round_pages)) if len(round_pages) == 1 else None
        counts.append(pages)
    name = "质量集" if suite == "quality800" else "性能子集"
    if counts and all(value is not None for value in counts) and len(set(counts)) == 1:
        return f"{counts[0]:g} 页{name}"
    return f"{name}（各组实际页数见运行记录）"


def _n_label(report: dict[str, Any], pipelines: list[str], suite: str) -> str:
    counts = {len(_group(report, pipeline, suite).get("performance", {}).get("rounds", []))
              for pipeline in pipelines}
    if len(counts) == 1 and next(iter(counts)) > 0:
        return f"每组 n = {next(iter(counts))}"
    return "实际运行次数见记录"


def _style_axis(axis: Any) -> None:
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#CCD1D9")
    axis.set_axisbelow(True)
    axis.grid(axis="x", color="#E6E9EF", linewidth=0.7)
    axis.tick_params(axis="both", length=0, pad=7)


def _bar_panel(axis: Any, pipelines: list[str], values: list[float | None],
               title: str, *, percent: bool = True, xlabel: str = "", unit: str = "",
               full_percent_scale: bool = True) -> None:
    _style_axis(axis)
    known = [value for value in values if value is not None]
    maximum = max(known, default=1.0)
    minimum_limit = 0.01 if percent and not full_percent_scale else 1.0
    limit = max(minimum_limit, maximum * 1.22)
    for index, (pipeline, value) in enumerate(zip(pipelines, values, strict=True)):
        if value is None:
            axis.text(limit * 0.025, index, "NA", va="center", color="#777777")
        else:
            axis.barh(index, value, height=0.62, color=PIPELINE_COLORS.get(pipeline, "#777777"))
            label = f"{value:.2%}" if percent else f"{value:.2f}{unit}"
            axis.text(value + limit * 0.02, index, label, va="center", fontsize=10)
    axis.set_yticks(range(len(pipelines)), pipelines)
    axis.set_ylim(max(1, len(pipelines)) - 0.4, -0.6)
    axis.set_xlim(0, limit)
    axis.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=13)
    axis.set_xlabel(xlabel)
    if percent:
        from matplotlib.ticker import PercentFormatter
        axis.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0 if full_percent_scale else 1))


def _quality(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    definitions = (
        ("content_recall", "内容单元召回 ↑", "unit_presence.recall", "unit_presence.target_units"),
        ("aligned_cer", "已定位正文 CER ↓", "text_aligned.strict.cer", "text_aligned.strict.reference_chars"),
        ("table_target_correctness", "值与行列标签正确覆盖 ↑", "table_records.field_target_correctness.value",
         "table_records.field_target_correctness.denominator"),
        ("information_target_correctness", "完整已标信息正确覆盖 ↑", "table_records.information_target_correctness.value",
         "table_records.information_target_correctness.denominator"),
    )
    figure, axes = plt.subplots(1, 4, figsize=(18.0, 6.2))
    data: dict[str, Any] = {}
    for axis, (key, title, metric, denominator) in zip(axes.flat, definitions, strict=True):
        rows: list[dict[str, Any]] = [{"pipeline": pipeline,
                 "value": _value(_group(report, pipeline, "quality800").get("quality", {}).get("micro", {}), metric),
                 "denominator": _value(_group(report, pipeline, "quality800").get("quality", {}).get("micro", {}), denominator)}
                for pipeline in pipelines]
        _bar_panel(axis, pipelines, [row["value"] for row in rows], title,
                   full_percent_scale=key != "aligned_cer")
        data[key] = {"metric": f"quality.micro.{metric}", "rows": rows}
    figure.suptitle(f"{_scope_label(report, pipelines, 'quality800')}的分项质量结果", x=0.04, ha="left", fontsize=18, fontweight="bold")
    figure.tight_layout(rect=(0.01, 0.02, 1, 0.94), w_pad=3)
    return figure, data


def _relations(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    """Show explicit relation states against all targets, without a mixed score."""
    from matplotlib.patches import Patch
    from matplotlib.ticker import PercentFormatter

    figure, relation_axis = plt.subplots(figsize=(11.8, 7.0))
    data: dict[str, Any] = {}
    for axis, kind in ((relation_axis, "before"),):
        _style_axis(axis)
        rows = []
        for index, pipeline in enumerate(pipelines):
            record = _group(report, pipeline, "quality800").get("quality", {}).get("micro", {}).get("relations", {}).get("by_type", {}).get(kind)
            row = {"pipeline": pipeline, **relation_breakdown(record)}
            rows.append(row)
            total = row["denominator"]
            if not row["available"] or not total:
                label = "NA（无目标）" if row["available"] and total == 0 else "NA（复核中）"
                axis.text(0.025, index, label, va="center", color="#777777", fontsize=10)
                continue
            left = 0.0
            for key, _, color in RELATION_STATES:
                width = row["states"][key] / total
                axis.barh(index, width, left=left, height=0.62, color=color)
                left += width
            axis.text(1.025, index, f"n={total:,}", va="center", fontsize=9, color="#555555")
        axis.set_yticks(range(len(pipelines)), pipelines)
        axis.set_ylim(max(1, len(pipelines)) - 0.4, -0.6)
        axis.set_xlim(0, 1.18)
        axis.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        axis.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        axis.set_title("阅读顺序 · before", loc="left", fontsize=14, fontweight="bold", pad=15)
        axis.set_xlabel("占全部已标目标的比例；n 为本类型目标数")
        data[kind] = {"denominator_scope": "all_targets", "rows": rows}
    figure.legend(handles=[Patch(facecolor=color, label=label) for _, label, color in RELATION_STATES],
                  loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.005))
    figure.suptitle("阅读顺序：全部已标目标与证据状态", x=0.045, ha="left", fontsize=18, fontweight="bold")
    figure.tight_layout(rect=(0.01, 0.12, 1, 0.93), w_pad=3)
    return figure, data


def _averaging(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    from matplotlib.ticker import FixedLocator, NullFormatter, PercentFormatter

    series = (("micro", "字符微平均", "按参考字符数加权"),
              ("macro_by_document", "文档宏平均", "各文档等权"),
              ("macro_by_family", "家族宏平均", "各家族等权"))
    rows = []
    all_values = []
    for pipeline in pipelines:
        quality = _group(report, pipeline, "quality800").get("quality", {})
        row: dict[str, Any] = {"pipeline": pipeline}
        for scope, _, _ in series:
            item = quality.get(scope, {}).get("text.strict.cer", {}) if scope != "micro" else {}
            value = _value(quality, "micro.text.strict.cer") if scope == "micro" else _number(item.get("value"))
            value = value if value is not None and value >= 0 else None
            row[scope] = {"value": value, "available_groups": item.get("available_groups"),
                          "total_groups": item.get("total_groups")}
            if value is not None:
                all_values.append(value)
        rows.append(row)
    y_scale = "log" if all_values and min(all_values) > 0 else "linear"
    if y_scale == "log":
        lower, upper = min(all_values) * 0.78, max(all_values) * 1.32
        exponents = range(math.floor(math.log10(lower * 100)) - 1,
                          math.ceil(math.log10(upper * 100)) + 1)
        ticks = sorted({coefficient * 10 ** exponent / 100
                        for exponent in exponents for coefficient in (1, 1.2, 1.6, 2, 3, 4, 6, 8)
                        if lower <= coefficient * 10 ** exponent / 100 <= upper})
    else:
        lower, upper = 0.0, max(0.01, max(all_values, default=0.8) * 1.3)
        ticks = [upper * index / 4 for index in range(5)]
    figure, axes = plt.subplots(1, 3, figsize=(16.8, 6.6), sharey=True)
    x = list(range(len(pipelines)))
    for axis, (scope, title, weight) in zip(axes, series, strict=True):
        _style_axis(axis)
        axis.grid(axis="x", visible=False)
        axis.grid(axis="y", which="major", color="#E6E9EF", linewidth=0.7)
        axis.set_yscale(y_scale)
        axis.set_ylim(lower, upper)
        axis.yaxis.set_major_locator(FixedLocator(ticks))
        axis.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=None))
        axis.yaxis.set_minor_locator(FixedLocator([]))
        axis.yaxis.set_minor_formatter(NullFormatter())
        values = [row[scope]["value"] for row in rows]
        axis.plot(x, [value if value is not None else math.nan for value in values],
                  color="#A0A6AD", linewidth=1.1, zorder=2)
        for index, (pipeline, value) in enumerate(zip(pipelines, values, strict=True)):
            if value is None:
                axis.text(index, 0.035, "NA", transform=axis.get_xaxis_transform(),
                          ha="center", va="bottom", fontsize=9, color="#888888")
                continue
            axis.scatter(index, value, marker="o", s=60, edgecolors="white", linewidths=0.7,
                         color=PIPELINE_COLORS.get(pipeline, "#777777"), zorder=3, clip_on=False)
            axis.annotate(f"{value * 100:.2f}%", (index, value), xytext=(0, 9),
                          textcoords="offset points", ha="center", va="bottom", fontsize=9,
                          color="#333333")
        axis.set_xticks(x, pipelines)
        axis.set_xlim(-0.55, max(0.55, len(pipelines) - 0.45))
        axis.tick_params(axis="both", labelsize=10)
        axis.set_title(title, loc="left", fontsize=15, fontweight="bold", pad=34)
        coverage = ""
        if scope != "micro":
            counts = [(row[scope]["available_groups"], row[scope]["total_groups"]) for row in rows]
            if counts and all(pair == counts[0] for pair in counts) and all(
                type(value) is int and value >= 0 for value in counts[0]
            ):
                coverage = f" · 可用 {counts[0][0]}/{counts[0][1]}"
            else:
                coverage = " · 可用数各配置不同或未记录"
        axis.text(0, 1.035, weight + coverage, transform=axis.transAxes,
                  fontsize=10, color="#666666", va="bottom")
    axes[0].set_ylabel("严格 CER ↓" + ("（对数刻度）" if y_scale == "log" else "（线性刻度）"), fontsize=11)
    figure.suptitle("聚合权重改变时，CER 如何变化", x=0.045, ha="left", fontsize=19, fontweight="bold")
    figure.text(0.045, 0.025, "横轴为固定配置；细线仅引导视线。三面板使用相同纵轴范围。",
                fontsize=10, color="#666666")
    figure.tight_layout(rect=(0.01, 0.07, 1, 0.90), w_pad=2.6)
    return figure, {"rows": rows, "macro_metric": "text.strict.cer",
                    "layout": "three_shared_y_panels_pipeline_categories",
                    "y_scale": y_scale, "guide_not_fit": True,
                    "y_limits": [lower, upper]}


def _rounds(report: dict[str, Any], pipeline: str, suite: str) -> list[dict[str, Any]]:
    return [{"repetition": row.get("repetition"), "attempted_input_pages": row.get("attempted_input_pages"),
             "completed_input_pages": row.get("completed_input_pages"),
             "processing_seconds": _number(row.get("processing_seconds_including_failures")),
             "timing_complete": row.get("timing_complete"),
             "all_samples_completed": row.get("all_samples_completed")}
            for row in _group(report, pipeline, suite).get("performance", {}).get("rounds", [])]


def _quality_time(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    rows: list[dict[str, Any]] = [{"pipeline": pipeline, "rounds": _rounds(report, pipeline, "quality800")} for pipeline in pipelines]
    values = [row["rounds"][0]["processing_seconds"] / 60
              if len(row["rounds"]) == 1 and row["rounds"][0]["processing_seconds"] is not None else None
              for row in rows]
    figure, axis = plt.subplots(figsize=(12.6, 6.3))
    _bar_panel(axis, pipelines, values, f"{_scope_label(report, pipelines, 'quality800')}直接处理耗时 · {_n_label(report, pipelines, 'quality800')}", percent=False,
               xlabel="分钟 ↓；包含失败尝试成本，排除初始化与预热", unit=" 分钟")
    figure.tight_layout()
    return figure, {"rows": rows, "display_unit": "minutes",
                    "repetitions_by_pipeline": {row["pipeline"]: len(row["rounds"]) for row in rows}}


def _perf(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    figure, axis = plt.subplots(figsize=(12.6, 6.3))
    _style_axis(axis)
    markers = ("o", "s", "^")
    rows = []
    values = []
    for index, pipeline in enumerate(pipelines):
        rounds = _rounds(report, pipeline, "perf80")
        known = [row["processing_seconds"] for row in rounds if row["processing_seconds"] is not None]
        median = statistics.median(known) if len(rounds) == 3 and len(known) == 3 else None
        rows.append({"pipeline": pipeline, "rounds": rounds, "median_seconds": median})
        for offset, row in enumerate(rounds):
            value = row["processing_seconds"]
            if value is not None:
                values.append(value / 60)
                axis.scatter(value / 60, index + (offset - 1) * 0.18, s=52,
                             marker=markers[offset % 3], color=PIPELINE_COLORS.get(pipeline, "#777777"), zorder=3)
        if median is not None:
            axis.plot([median / 60, median / 60], [index - 0.31, index + 0.31], color="#252525", linewidth=1.7)
            # Keep the median label beyond every round, including outliers.
            axis.annotate(f"{median / 60:.2f} 分钟", (max(known) / 60, index), xytext=(12, 0),
                          textcoords="offset points", va="center", fontsize=10)
        elif not known:
            axis.text(0.02, index, "NA", va="center")
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color="#666666", marker=marker, linestyle="none", label=f"第 {index + 1} 轮")
               for index, marker in enumerate(markers)]
    handles.append(Line2D([], [], color="#252525", marker="|", markersize=14, linestyle="none", label="三轮中位数"))
    axis.legend(handles=handles, frameon=False, loc="lower right")
    axis.set_yticks(range(len(pipelines)), pipelines)
    axis.invert_yaxis()
    axis.set_xlim(0, max(1, max(values, default=1) * 1.28))
    axis.set_xlabel("性能子集直接处理耗时（分钟）↓")
    axis.set_title(f"{_scope_label(report, pipelines, 'perf80')}：实际测量点与中位数 · {_n_label(report, pipelines, 'perf80')}", loc="left", fontsize=17, fontweight="bold", pad=20)
    figure.tight_layout()
    return figure, {"rows": rows, "display_unit": "minutes", "confidence_intervals": False}


def _tradeoff(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter, PercentFormatter

    from .pareto import pareto_partition

    figure, axes = plt.subplots(1, 2, figsize=(15.2, 7.1))
    rows: list[dict[str, Any]] = []
    input_pages = {_group(report, pipeline, "quality800").get("quality", {}).get("input_pages")
                   for pipeline in pipelines}
    same_input = len(input_pages) == 1 and None not in input_pages
    definitions = (
        ("content_recall", "内容保全 · 越靠左上越好", "内容定位覆盖 ↑", "unit_presence.recall", True),
        ("information_target_correctness", "表格信息 · 越靠左上越好", "完整已标信息正确覆盖 ↑",
         "table_records.information_target_correctness.value", True),
    )
    for pipeline in pipelines:
        rounds = _rounds(report, pipeline, "quality800")
        group = _group(report, pipeline, "quality800")
        round_record = rounds[0] if len(rounds) == 1 else {}
        seconds = round_record.get("processing_seconds")
        quality = group.get("quality", {})
        micro = quality.get("micro", {})
        complete_input = (same_input and round_record.get("timing_complete") is True
                          and round_record.get("attempted_input_pages") == quality.get("input_pages"))
        row = {"pipeline": pipeline, "processing_seconds": seconds,
               "comparison_eligible": complete_input,
               "comparison_exclusion": None if complete_input else "incomplete_or_different_input_timing",
               "has_failed_or_partial_samples": round_record.get("all_samples_completed") is False,
               **{key: _value(micro, path) for key, _, _, path, _ in definitions}}
        rows.append(row)

    analyses = {}
    offsets = {
        "content_recall": {"P01": (10, 14), "P02": (-15, -24), "P06": (-27, 10),
                "P07": (-10, -24), "P08": (10, -16), "P03": (-30, 13),
                "P04": (8, -15), "P05": (8, 9)},
        "information_target_correctness": {"P01": (-20, -24), "P02": (9, 10),
                "P06": (-27, 12), "P07": (-16, -24), "P08": (10, 10),
                "P03": (-30, 10), "P04": (8, -17), "P05": (8, -18)},
    }
    for axis, (key, title, label, _path, maximize) in zip(axes, definitions, strict=True):
        analysis = pareto_partition(rows, key, maximize_quality=maximize)
        analyses[key] = analysis
        frontier = set(analysis["frontier"])
        excluded = {item["pipeline"] for item in analysis["excluded"]}
        valid = [row for row in rows if row["pipeline"] not in excluded]
        by_name = {row["pipeline"]: row for row in valid}
        ordered = [by_name[name] for name in analysis["frontier"]]
        if ordered:
            axis.step([row["processing_seconds"] / 60 for row in ordered],
                      [row[key] for row in ordered], where="post", linestyle="--",
                      color="#394556", linewidth=1.4, alpha=0.8, zorder=2)
        for row in valid:
            pipeline = row["pipeline"]
            efficient = pipeline in frontier
            color = PIPELINE_COLORS.get(pipeline, "#555555") if efficient else "#B4BBC4"
            point = (row["processing_seconds"] / 60, row[key])
            axis.scatter(*point, s=100 if efficient else 64,
                         marker="o" if efficient else "x", color=color,
                         linewidths=1.3, zorder=4 if efficient else 3)
            suffix = "†" if row["has_failed_or_partial_samples"] else ""
            axis.annotate(pipeline + suffix, point,
                          xytext=offsets[key].get(pipeline, (7, 7)), textcoords="offset points",
                          fontsize=11, fontweight="bold" if efficient else "normal",
                          color=color if efficient else "#7A818B",
                          arrowprops={"arrowstyle": "-", "color": color, "linewidth": 0.7},
                          bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "none", "pad": 1})
        _style_axis(axis)
        axis.set_xscale("log")
        axis.xaxis.set_major_locator(LogLocator(base=10, subs=(1, 2, 3, 5)))
        axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{value:g}"))
        axis.xaxis.set_minor_formatter(NullFormatter())
        axis.grid(axis="both", color="#E6E9EF", linewidth=0.7)
        axis.set_xlabel("同一质量集直接处理耗时（分钟，对数轴）↓")
        axis.set_ylabel(label)
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))
        axis.set_title(title, loc="left", fontsize=15, fontweight="bold", pad=16)
        if valid:
            costs = [row["processing_seconds"] / 60 for row in valid]
            values = [row[key] for row in valid]
            axis.set_xlim(min(costs) / 1.20, max(costs) * 1.25)
            padding = max((max(values) - min(values)) * 0.19, 0.01)
            axis.set_ylim(max(0, min(values) - padding),
                          min(1, max(values) + padding) if maximize else max(values) + padding)
        else:
            axis.text(0.5, 0.5, "NA：没有同范围完整计时", transform=axis.transAxes,
                      ha="center", va="center", color="#777777")
        axis.text(0.03, 0.96, "前沿：" + " → ".join(analysis["frontier"]) if ordered else "前沿：NA",
                  transform=axis.transAxes, va="top", fontsize=9, color="#4B5563")
    figure.legend(handles=[
        Line2D([], [], marker="o", color="#394556", linestyle="--", label="帕累托前沿"),
        Line2D([], [], marker="x", color="#B4BBC4", linestyle="none", label="被支配配置"),
    ], loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.055))
    figure.suptitle(f"质量与成本：离散帕累托前沿 · {_scope_label(report, pipelines, 'quality800')}，{_n_label(report, pipelines, 'quality800')}",
                   x=0.05, ha="left", fontsize=18, fontweight="bold")
    figure.text(0.5, 0.025, "阶梯线标示已测配置的支配边界；不拟合、不插值、不表示组合管线。",
                ha="center", fontsize=10, color="#69717D")
    figure.tight_layout(rect=(0.01, 0.14, 1, 0.91), w_pad=3)
    return figure, {"rows": rows, "time_suite": "quality800", "quality_suite": "quality800",
                    "pareto": analyses, "cost_axis_scale": "log",
                    "frontier_rendering": "discrete_post_step_dominance_boundary",
                    "interpolated_configurations": False}


def _resources(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    definitions = (("worker_host", "Worker 宿主内存", "worker_lifecycle_resources", "observed_shared_host_memory_peak_bytes", 1024 ** 3),
                   ("inference_host", "推理服务宿主内存", "inference_lifecycle_resources", "observed_shared_host_memory_peak_bytes", 1024 ** 3),
                   ("owned_gpu_memory", "受测管线自有显存", "inference_lifecycle_resources", "observed_owned_gpu_peak_memory_mib", 1024))
    figure, axes = plt.subplots(1, 3, figsize=(14.4, 6.0))
    data: dict[str, Any] = {}
    for axis, (key, title, section, field, divisor) in zip(axes, definitions, strict=True):
        rows = []
        for pipeline in pipelines:
            resource = report.get("runtime_evidence", {}).get(pipeline, {}).get(section) or {}
            record = resource.get("record") or {}
            raw = _number(record.get(field))
            rows.append({"pipeline": pipeline, "raw_value": raw, "gib": raw / divisor if raw is not None else None,
                         "path": resource.get("path"), "field": field,
                         "scope": (record.get("owned_gpu_memory_scope")
                                   if key == "owned_gpu_memory" else "named-container host memory"),
                         "sampling_completeness": record.get("sampling_completeness", {})})
        _bar_panel(axis, pipelines, [row["gib"] for row in rows], title, percent=False, xlabel="GiB（采样峰值）")
        data[key] = rows
    figure.suptitle("生命周期资源采样峰值 · 三种范围分别观察", x=0.05, ha="left", fontsize=18, fontweight="bold")
    figure.tight_layout(rect=(0, 0, 1, 0.94), w_pad=3)
    return figure, data


def _categories(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    import numpy as np

    selected = [(tag, label) for tag, label in REPRESENTATIVE_TAGS
                if any(row.get("scope") == "tag" and row.get("scope_key") == tag
                       and row.get("suite") == "quality800" for row in report.get("quality_slices", []))]
    figure, axes = plt.subplots(2, 1, figsize=(13.4, max(8.5, 2.2 + len(selected) * 1.1)))
    data: dict[str, Any] = {"selection": "fixed_semantic_tags_not_score_ranked", "tags_overlap": True, "panels": []}
    definitions = (("content_recall", "content_targets", "内容", "内容定位覆盖 ↑", "viridis"),
                   ("information_target_correctness", "table_field_targets", "字段", "完整已标信息正确覆盖 ↑", "viridis"))
    if not selected:
        for axis in axes:
            axis.text(0.5, 0.5, "无已声明的代表类别结果 · NA", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
    for axis, (metric, denominator, denom_label, title, cmap_name) in zip(axes, definitions, strict=True):
        if not selected:
            continue
        matrix = np.full((len(selected), len(pipelines)), np.nan)
        labels = []
        rows = []
        for y, (tag, label) in enumerate(selected):
            tag_rows = [row for row in report.get("quality_slices", []) if row.get("scope") == "tag"
                        and row.get("scope_key") == tag and row.get("suite") == "quality800"]
            common = tag_rows[0] if tag_rows else {}
            denominator_values = {row.get(denominator) for row in tag_rows}
            denom = common.get(denominator) if len(denominator_values) == 1 else None
            count_values = {row.get("samples") for row in tag_rows}
            document_values = {row.get("documents") for row in tag_rows}
            count = common.get("samples") if len(count_values) == 1 else "各组不同"
            documents = common.get("documents") if len(document_values) == 1 else "各组不同"
            denom_text = f"{denom:,}" if isinstance(denom, (int, float)) else "各组不同/NA"
            labels.append(f"{label}  n={count if count is not None else 'NA'}, d={documents if documents is not None else 'NA'}\n{denom_label}分母={denom_text}")
            for column, pipeline in enumerate(pipelines):
                candidates = [row for row in tag_rows if row.get("pipeline") == pipeline]
                source = candidates[0] if len(candidates) == 1 else {}
                value = _number(source.get(metric))
                if metric == "table_field_target_correctness" and any(
                    type(source.get(key)) is not int for key in
                    ("table_fields_compared", "table_fields_missing", "table_fields_unresolved")
                ):
                    value = None
                if value is not None:
                    matrix[y, column] = value
                rows.append({"pipeline": pipeline, "tag": tag, "samples": source.get("samples"),
                             "documents": source.get("documents"), "denominator": source.get(denominator), "value": value})
        finite = matrix[np.isfinite(matrix)]
        vmax = max(1.0, float(finite.max())) if finite.size else 1.0
        colormap = plt.get_cmap(cmap_name).copy()
        colormap.set_bad("#E8E8EB")
        image = axis.imshow(np.ma.masked_invalid(matrix), vmin=0, vmax=vmax, cmap=colormap, aspect="auto")
        axis.set_xticks(range(len(pipelines)), pipelines)
        axis.set_yticks(range(len(selected)), labels, fontsize=10)
        axis.tick_params(length=0, pad=9)
        axis.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=13)
        for y in range(len(selected)):
            for column in range(len(pipelines)):
                cell_value = float(matrix[y, column])
                text = "NA" if not np.isfinite(cell_value) else f"{cell_value:.1%}"
                if np.isfinite(cell_value):
                    rgb = colormap(cell_value / vmax)[:3]
                    luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
                else:
                    luminance = 1.0
                axis.text(column, y, text, ha="center", va="center", fontsize=10,
                          color="white" if luminance < 0.48 else "#222222")
        from matplotlib.ticker import PercentFormatter
        figure.colorbar(image, ax=axis, shrink=0.8, pad=0.02, format=PercentFormatter(1.0))
        data["panels"].append({"metric": metric, "denominator_field": denominator, "rows": rows})
    figure.suptitle("代表类别差异 · 已有标签，类别可重叠", x=0.05, ha="left", fontsize=18, fontweight="bold")
    figure.tight_layout(rect=(0, 0, 1, 0.96), h_pad=3)
    return figure, data


def _coverage(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    figure, axis = plt.subplots(figsize=(13.2, 6.8))
    _style_axis(axis)
    colors = ("#4477AA", "#EEBB66", "#AA77AA", "#D1D5DD")
    labels = ("唯一定位（含锚点）", "定位歧义", "定位未决", "未定位")
    rows = []
    for index, pipeline in enumerate(pipelines):
        coverage = _group(report, pipeline, "quality800").get("quality", {}).get("coverage", {})
        numbers = {key: _number(coverage.get(key)) for key in (
            "scored_units", "localization_only_units", "localized_units", "localized_anchors",
            "ambiguous_units", "unresolved_units", "not_localized_units")}
        complete = all(value is not None for value in numbers.values())
        known = {key: value for key, value in numbers.items() if value is not None}
        denominator = known["scored_units"] + known["localization_only_units"] if complete else None
        states = ([known["localized_units"] + known["localized_anchors"], known["ambiguous_units"],
                   known["unresolved_units"], known["not_localized_units"]] if complete else [])
        closed = bool(denominator and denominator > 0 and sum(states) == denominator and all(value >= 0 for value in states))
        rows.append({"pipeline": pipeline, "source_counts": numbers, "denominator": denominator,
                     "states": dict(zip(labels, states, strict=True)) if states else {}, "closed": closed})
        if not closed:
            axis.text(0.02, index, "NA：聚合状态未形成同一分母", va="center")
            continue
        assert denominator is not None
        left = 0.0
        for value, color in zip(states, colors, strict=True):
            proportion = value / denominator
            axis.barh(index, proportion, left=left, height=0.63, color=color)
            if proportion >= 0.035:
                axis.text(left + proportion / 2, index, f"{value:,.0f}", va="center", ha="center", fontsize=9,
                          color="white" if color == colors[0] else "#222222")
            left += proportion
        axis.text(1.015, index, f"N={denominator:,.0f}", va="center", fontsize=10)
    from matplotlib.patches import Patch
    from matplotlib.ticker import PercentFormatter
    axis.legend(handles=[Patch(facecolor=color, label=label) for label, color in zip(labels, colors, strict=True)],
                loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=4, frameon=False)
    axis.set_yticks(range(len(pipelines)), pipelines)
    axis.invert_yaxis()
    axis.set_xlim(0, 1.15)
    axis.set_xticks([0, 0.25, 0.5, 0.75, 1])
    axis.xaxis.set_major_formatter(PercentFormatter(1))
    axis.set_xlabel("同一可定位目标范围内的比例；图中数字为目标数")
    axis.set_title("定位覆盖：互斥状态使用同一分母（包含仅定位锚点）", loc="left", fontsize=17,
                   fontweight="bold", pad=19)
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure, {"rows": rows, "denominator_definition": "scored_units + localization_only_units",
                   "located_definition": "localized_units + localized_anchors"}


def _table_coverage(report: dict[str, Any], plt: Any, pipelines: list[str]) -> tuple[Any, dict[str, Any]]:
    from matplotlib.patches import Patch
    from matplotlib.ticker import PercentFormatter

    definitions = (("field_target_correctness", "已证正确字段覆盖率 ↑"),
                   ("field_compared_accuracy", "已比较字段正确率 ↑"))
    figure, axes = plt.subplots(1, 3, figsize=(16.2, 6.8), gridspec_kw={"width_ratios": [1, 1, 1.4]})
    data: dict[str, Any] = {}
    ledgers = {pipeline: table_field_breakdown(
        _group(report, pipeline, "quality800").get("quality", {}).get("micro", {}).get("table_records"))
        for pipeline in pipelines}
    for axis, (metric, title) in zip(axes[:2], definitions, strict=True):
        rows = []
        for pipeline in pipelines:
            record = ledgers[pipeline][metric]
            rows.append({"pipeline": pipeline, "value": _number(record.get("value")),
                         "numerator": record.get("numerator"), "denominator": record.get("denominator")})
        _bar_panel(axis, pipelines, [row["value"] for row in rows], title)
        data[metric] = rows
    axis = axes[2]
    _style_axis(axis)
    states = (("correct_fields", "已比较且正确", "#228833"),
              ("compared_incorrect", "已比较未通过", "#CC6677"),
              ("target_missing_fields", "目标格未取到值", "#DDCC77"),
              ("unresolved_fields", "未判定", "#BBBBBB"))
    rows = []
    for index, pipeline in enumerate(pipelines):
        ledger = ledgers[pipeline]
        total = ledger["target_fields"]
        counts = {key: ledger.get(key) for key, _, _ in states}
        counts["compared_incorrect"] = (ledger["compared_fields"] - ledger["correct_fields"]
                                       if ledger["available"] else None)
        rows.append({"pipeline": pipeline, "available": ledger["available"], "denominator": total,
                     "compared_fields": ledger["compared_fields"], "states": counts})
        if not ledger["available"] or not total:
            axis.text(0.02, index, "NA", va="center", color="#777777")
            continue
        left = 0.0
        for key, _, color in states:
            width = counts[key] / total
            axis.barh(index, width, left=left, height=0.62, color=color)
            left += width
        axis.text(1.02, index, f"n={total:,}", va="center", fontsize=9)
    axis.set_yticks(range(len(pipelines)), pipelines)
    axis.set_ylim(max(1, len(pipelines)) - 0.4, -0.6)
    axis.set_xlim(0, 1.25)
    axis.set_xticks([0, 0.5, 1])
    axis.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axis.set_title("全部目标的字段状态", loc="left", fontsize=14, fontweight="bold", pad=15)
    data["field_states"] = rows
    figure.legend(handles=[Patch(facecolor=color, label=label) for _, label, color in states],
                  loc="lower center", ncol=4, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.005))
    figure.suptitle("表格字段：内容等价正确与未判定范围", x=0.04, ha="left", fontsize=18, fontweight="bold")
    figure.tight_layout(rect=(0, 0.09, 1, 0.94), w_pad=3)
    return figure, data


def render_figures(report: dict[str, Any], directory: Path) -> list[dict[str, Any]]:
    """Export comparison figures and their traceable numeric projections.

    ``directory`` is the run's figures directory.  References in the returned
    metadata are relative to its parent, so Markdown and HTML share the files.
    Unknown values remain ``None`` in JSON and are displayed as NA.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory.mkdir(parents=True, exist_ok=True)
    _register_cjk_fonts(directory)
    pipelines = sorted({str(group["pipeline"]) for group in report.get("groups", []) if group.get("pipeline")})
    settings = {
        "font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"],
        "font.sans-serif": ["DejaVu Sans", "Noto Sans CJK SC"],
        "font.size": 11, "mathtext.fontset": "dejavusans", "text.usetex": False,
        "svg.fonttype": "none", "svg.hashsalt": "moparse-report-figures-v1",
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.unicode_minus": True, "figure.facecolor": "white", "axes.facecolor": "white",
        "savefig.facecolor": "white", "savefig.bbox": "tight",
    }
    specifications = (
        ("quality", "核心质量对比", _quality,
         "同一正式质量集。内容覆盖衡量定位存在性；CER仅针对已定位正文，字符覆盖见主表。表格分别报告值与行列标签正确覆盖、同时满足已标单位期间附注的完整信息正确覆盖。未定位和未确定保持在目标分母。"),
        ("relations", "阅读顺序与证据状态", _relations,
         "仅展示 before 的全部已标目标及五类证据状态；其他关系只见附录。未获关系证据与明确不符分开，未判定保持未知。缺少分型计数或计数不闭合时显示 NA，不把未知算成正确。"),
        ("averaging", "字符、文档与家族平均", _averaging,
         "三面板共享CER纵轴，分别按字符加权、文档等权和家族等权；圆点直接标出实测值。纵轴采用对数刻度，存在真实零值时全图改用线性刻度。横轴是离散管线，细线只引导阅读，不拟合缩放规律。"),
        ("quality-time", "800 页完整运行耗时", _quality_time,
         "800 页完整运行每组仅一次（n=1），直接记录 worker 开始处理至原生结果、忠实导出及必要资产就绪的时间；初始化、预热、评分和纯持久化另计。"),
        ("perf-repeat", "80 页三轮性能", _perf,
         "固定 80 页子集的三轮实际点和中位数。它们不是 800 页三轮结果，不是独立文档样本；不提供置信区间或显著性结论。"),
        ("tradeoff", "质量与运行成本", _tradeoff,
         "同一正式质量集（n=1）：分别比较耗时与内容定位覆盖、耗时与完整已标信息正确覆盖。彩色圆点为非支配配置，灰叉为被支配配置，虚线阶梯标示离散支配边界；横轴对数刻度，不拟合或插值中间方案。"),
        ("resources", "内存与显存采样峰值", _resources,
         "生命周期采样含初始化，可能遗漏更短峰值；这些是已观测峰值而非精确绝对峰值或逐页峰值。显存只使用受测容器及其compute子进程的同时聚合观测，不含驻留TTS；归属未知为NA，不以整卡占用替代。整卡、TTS与余量见附录。Worker、推理宿主内存与自有显存分开绘制，不相加。"),
        ("categories", "代表类别热图", _categories,
         "固定选择已有普通正文、多栏、数据表、网格正文、跨页段落、跨页表格、混合文字和负数值标签。类别可重叠，按语义选取而非按成绩筛选。n 为样本数，d 为原文档数，各面板列出本指标分母；未标注为 NA。来源类别均未知，不绘制原生/扫描比较。"),
        ("coverage", "同分母的定位状态", _coverage,
         "分母为参与定位的内容目标加仅定位锚点；唯一定位数同样包含锚点，四种状态互斥。它与排除锚点的内容召回分母不同；定位歧义、未决和未定位不能全称模型遗漏。未能形成同一分母时显示 NA。"),
        ("table-coverage", "表格两项核心率与字段状态", _table_coverage,
         "已证正确字段覆盖率=内容等价正确/全部目标；已比较字段正确率=内容等价正确/已比较字段。字段状态保留已比较、目标格未取到值和未判定，目标格未取到值不证明全输出遗漏；严格差异见附录，缺项为 NA。"),
    )
    entries = []
    with plt.rc_context(settings):
        for identifier, title, renderer, caption in specifications:
            figure, data = renderer(report, plt, pipelines)
            try:
                caption = caption.replace("同一 800 页质量集", f"同一{_scope_label(report, pipelines, 'quality800')}")
                caption = caption.replace("同一 800 页", f"同一{_scope_label(report, pipelines, 'quality800')}")
                caption = caption.replace("800 页完整运行每组仅一次（n=1）", f"{_scope_label(report, pipelines, 'quality800')}运行（{_n_label(report, pipelines, 'quality800')}）")
                caption = caption.replace("（n=1）", f"（{_n_label(report, pipelines, 'quality800')}）")
                caption = caption.replace("固定 80 页子集的三轮实际点和中位数", f"固定{_scope_label(report, pipelines, 'perf80')}的实际测量点；完整三轮时给出中位数")
                entry = {"id": identifier, "title": title, "caption": caption,
                         "source_paths": _source(report), "data": data}
                if identifier == "resources":
                    entry["source_paths"] = _source(report, *(row["path"] for rows in data.values()
                                                               for row in rows if row.get("path")))
                for extension in ("png", "svg", "pdf"):
                    path = directory / f"{identifier}.{extension}"
                    metadata = ({"CreationDate": None, "ModDate": None} if extension == "pdf"
                                else {"Date": None} if extension == "svg" else {})
                    figure.savefig(path, dpi=170 if extension == "png" else None, metadata=metadata)
                    entry[extension] = f"{directory.name}/{path.name}"
                entries.append(entry)
            finally:
                plt.close(figure)
    index = {"schema": "moparse-report-figures-v1", "source": "existing_aggregate_report_only",
             "pipeline_colors": PIPELINE_COLORS, "figures": entries}
    (directory / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return entries
