"""Build the single Lite report from frozen scores and recorded measurements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moparse_eval.expected_report import first_failure_stage, load_complete  # noqa: E402
from moparse_eval.packaging import read_json, write_json  # noqa: E402

COST_KEYS = ("processing_seconds", "worker_host_bytes", "inference_host_bytes", "owned_gpu_mib")


def finite_nonnegative(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def memory_bytes(value: Any) -> float | None:
    """Read Docker's used-memory display, never its limit or a declared quota."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(GiB|MiB|KiB|GB|MB|kB|B)\s*", value.split("/", 1)[0])
    if not match:
        return None
    amount = finite_nonnegative(float(match[1]))
    factor = {"GiB": 2**30, "MiB": 2**20, "KiB": 2**10, "GB": 10**9, "MB": 10**6, "kB": 10**3, "B": 1}[match[2]]
    return amount * factor if amount is not None else None


def summarize_resource_samples(record: dict[str, Any]) -> dict[str, Any]:
    """Aggregate complete sampling rounds; independent component peaks never add."""
    host, owned, whole, tts, stamps = [], [], [], [], []
    names_seen: set[str] = set()
    samples = record.get("samples", [])
    for sample in samples:
        names = set(sample.get("expected_containers", []))
        names_seen.update(names)
        values = {}
        for container in sample.get("containers", []):
            name = container.get("owned_name", container.get("Name"))
            if name in names:
                values[name] = memory_bytes(container.get("MemUsage"))
        if names and names <= values.keys() and all(values[name] is not None for name in names):
            host.append(sum(values[name] for name in names))
        gpu = sample.get("owned_gpu", {})
        attributed = gpu.get("memory_mib_by_container", {})
        if (names and gpu.get("status") == "complete_observed_sample" and names <= attributed.keys()
                and all(finite_nonnegative(attributed[name]) is not None for name in names)):
            owned.append(sum(attributed[name] for name in names))
        for output, value in ((whole, sample.get("gpu1", {}).get("used_memory_mib")),
                              (tts, sample.get("tts_gpu", {}).get("used_memory_mib"))):
            number = finite_nonnegative(value)
            if number is not None:
                output.append(number)
        stamp = finite_nonnegative(sample.get("monotonic_seconds"))
        if stamp is not None:
            stamps.append(stamp)
    gaps = [b - a for a, b in zip(stamps[:-1], stamps[1:], strict=True) if b >= a]
    return {"host_peak_bytes": max(host, default=None), "owned_gpu_peak_mib": max(owned, default=None),
            "whole_gpu_peak_mib": max(whole, default=None), "tts_peak_mib": max(tts, default=None),
            "samples": len(samples), "host_complete_samples": len(host), "gpu_complete_samples": len(owned),
            "container_names": sorted(names_seen),
            "sample_span_seconds": stamps[-1] - stamps[0] if len(stamps) > 1 else None,
            "median_gap_seconds": statistics.median(gaps) if gaps else None,
            "maximum_gap_seconds": max(gaps, default=None),
            "scope": "whole recorded protocol including initialization, warmup, quality800 and perf80; sampled peaks"}


def observed_dominates(left: dict[str, Any], right: dict[str, Any]) -> bool | None:
    """Compare every declared quality and cost dimension, with missing distinct from zero."""
    if not left["qualities"] or left["qualities"].keys() != right["qualities"].keys():
        return None
    pairs = [(left["qualities"][key], right["qualities"][key], True) for key in left["qualities"]]
    pairs += [(left["costs"].get(key), right["costs"].get(key), False) for key in COST_KEYS]
    if any(finite_nonnegative(a) is None or finite_nonnegative(b) is None for a, b, _ in pairs):
        return None
    return all(a >= b if maximize else a <= b for a, b, maximize in pairs) and any(a != b for a, b, _ in pairs)


def collect_resource_comparison(index: dict[str, Any]) -> dict[str, Any]:
    baseline = Path(index["baseline"])
    native = {}
    sources = []
    for pipeline in (f"P{i:02}" for i in range(1, 9)):
        records = {}
        for name, relative in (("worker", "worker-resources.json"), ("inference", "inference/resources.json")):
            path = baseline / "artifacts" / pipeline / relative
            raw = path.read_bytes() if path.is_file() else None
            records[name] = summarize_resource_samples(read_json(path)) if raw is not None else summarize_resource_samples({})
            sources.append({"pipeline": pipeline, "scope": name, "path": str(path.resolve()),
                            "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None})
        rounds = index["execution_costs"]["native"][pipeline]["quality800"].get("rounds", [])
        quality = index["summary"][pipeline]["by_kind"]
        native[pipeline] = {"qualities": {kind: value["correct"] / value["targets"] if value["targets"] else None
                                              for kind, value in sorted(quality.items())},
                            "costs": {"processing_seconds": rounds[0].get("processing_seconds_including_failures") if len(rounds) == 1 else None,
                                      "worker_host_bytes": records["worker"]["host_peak_bytes"],
                                      "inference_host_bytes": records["inference"]["host_peak_bytes"],
                                      "owned_gpu_mib": records["inference"]["owned_gpu_peak_mib"]},
                            "resource_observations": records}
    for pipeline, row in native.items():
        comparable = observed_dominates(row, row) is not None
        row["observed_dominated_by"] = [other for other, candidate in native.items()
                                         if other != pipeline and observed_dominates(candidate, row) is True]
        row["comparison_status"] = "observed_vector_compared" if comparable else "missing_dimensions_no_dominance_claim"
        row["single_quality_dominated_by"] = {
            kind: [other for other, candidate in native.items() if other != pipeline and observed_dominates(
                {"qualities": {kind: candidate["qualities"][kind]}, "costs": candidate["costs"]},
                {"qualities": {kind: row["qualities"][kind]}, "costs": row["costs"]}) is True]
            for kind in ("business_field", "text")}
    final = {}
    for pipeline in ("P07", "P08"):
        path = Path(index["execution_costs"]["final"][pipeline + "-current"]["run"]) / "run.json"
        raw = path.read_bytes()
        run = read_json(path)
        cases = [case for case in run["cases"] if case["phase"] == "measured" and case["suite"] == "quality800"]
        peaks = [finite_nonnegative(case.get("resources", {}).get("peak_rss_bytes")) for case in cases]
        available = [peak for peak in peaks if peak is not None]
        final[pipeline] = {"quality800_peak_process_rss_bytes": max(available, default=None),
                           "measured_samples": len(cases), "memory_samples_available": len(available),
                           "gpu_devices": run["execution_environment"].get("observed_worker", {}).get("gpu_devices"),
                           "scope": "saved quality800 CPU postprocessing process RSS samples; separate from native parsing"}
        sources.append({"pipeline": pipeline, "scope": "final_cpu", "path": str(path.resolve()),
                        "sha256": hashlib.sha256(raw).hexdigest()})
    return {"scoring_software_id": index["software"]["software_id"], "native": native, "final_cpu": final,
            "sources": sources, "quality_dimensions": sorted(next(iter(native.values()))["qualities"]),
            "minimized_cost_dimensions": list(COST_KEYS),
            "interpretation": "observed vector dominance only; projections are not full dominance and finite sampling can miss peaks",
            "memory_policy": "worker and inference RAM stay separate; never add independent peaks; TTS and whole-card GPU are context only"}


PIPELINES = tuple(f"P{i:02}" for i in range(1, 9))
PIPELINE_NAMES = {
    "P01": "Docling TableFormer V1 + GLM", "P02": "Docling TableFormer V2 + GLM",
    "P03": "PaddleOCR-VL 1.5", "P04": "PaddleOCR-VL 1.6", "P05": "GLM-OCR SDK",
    "P06": "MinerU Standard + GLM", "P07": "MinerU Advanced + GLM", "P08": "MinerU 全页视觉",
}
KIND_NAMES = {"business_field": "业务字段", "text": "正文段落", "heading": "标题",
              "item": "列表文字", "unit_caption": "单位说明", "image_alt_text": "图片alt文字"}
COHORTS = (("ordinary-prose", "普通正文"), ("multi-column", "多栏"), ("data-table", "数据表"),
           ("layout-grid-prose", "网格正文"), ("cross-page-paragraph", "跨页段落"),
           ("cross-page-table", "跨页表格"), ("mixed-script", "混合文字"), ("mixed-units", "混合单位"))
ERROR_NAMES = ("定位或表头范围", "范围或位置歧义", "值未表达或不同", "限定不符", "其他")


def display(value: Any, digits: int = 2) -> str:
    return f"{value:,.{digits}f}" if finite_nonnegative(value) is not None else "缺测"


def ratio(row: dict[str, Any]) -> float | None:
    return row["correct"] / row["targets"] if row.get("targets") else None


def fraction_text(row: dict[str, Any]) -> str:
    return f"{row['correct']:,}/{row['targets']:,}（{ratio(row):.2%}）" if row.get("targets") else "无该类目标"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as output:
        if not rows:
            return
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def error_category(reason: str) -> str:
    if reason in {"native_fields_unresolved", "native_header_endpoints_unavailable"}:
        return ERROR_NAMES[0]
    if reason.startswith("ambiguous_") or reason == "native_label_path_scope_conflict":
        return ERROR_NAMES[1]
    if reason in {"value_expression_incorrect", "required_value_not_expressed"}:
        return ERROR_NAMES[2]
    return ERROR_NAMES[3] if reason.startswith("required_qualifier_incorrect:") else ERROR_NAMES[4]


def cohort_rows(groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Declared sample tags group complete sample scores; they never invent target-level tags."""
    rows = []
    for tag, label in COHORTS:
        for pipeline in PIPELINES:
            selected = [score for score in groups[pipeline] if tag in (score.get("tags") or [])]
            for kind in ("business_field", "text"):
                targets = sum(score["by_kind"].get(kind, {}).get("targets", 0) for score in selected)
                correct = sum(score["by_kind"].get(kind, {}).get("correct", 0) for score in selected)
                rows.append({"tag": tag, "label": label, "pipeline": pipeline, "kind": kind,
                             "samples": len(selected), "targets": targets, "correct": correct,
                             "correctness": correct / targets if targets else None})
    return rows


def text_diagnostics(scores: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for score in scores for row in score["outcomes"] if row["kind"] != "business_field"]
    located = [row for row in rows if row.get("candidate")]
    # Source metrics remain separately named; missing text is never counted as a good alignment.
    references = sum(row["text"]["strict"]["reference_chars"] for row in located)
    distance = sum(row["text"]["strict"]["distance"] for row in located)
    return {"targets": len(rows), "located": len(located), "missing": len(rows) - len(located),
            "located_reference_characters": references, "strict_edit_distance": distance,
            "located_strict_cer": distance / references if references else None}


def native_rows(index: dict[str, Any], resources: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for pipeline in PIPELINES:
        summary = index["summary"][pipeline]
        cost = resources["native"][pipeline]["costs"]
        repetitions = index["execution_costs"]["native"][pipeline]["perf80"]["rounds"]
        times = [finite_nonnegative(row.get("processing_seconds_including_failures")) for row in repetitions]
        known = [value for value in times if value is not None]
        row = {"pipeline": pipeline, "configuration": PIPELINE_NAMES[pipeline]}
        for kind in KIND_NAMES:
            counts = summary["by_kind"].get(kind, {})
            row.update({kind + "_correct": counts.get("correct", 0), kind + "_targets": counts.get("targets", 0),
                        kind + "_rate": ratio(counts)})
        row.update(cost)
        row.update(perf80_median_seconds=statistics.median(known) if len(known) == 3 else None,
                   perf80_min_seconds=min(known, default=None), perf80_max_seconds=max(known, default=None))
        rows.append(row)
    return rows


def error_index(index: dict[str, Any], groups: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    sources, errors = [], []
    paths = {(r["group"], r["sample_id"]): r["path"] for r in index["records"]}
    score_root = Path(index["report_score_index"]).parent
    for pipeline in ("P07", "P08"):
        native = {(score["sample_id"], row["id"]): row for score in groups[pipeline] for row in score["outcomes"]}
        for score in groups[pipeline + "-current"]:
            source_id = len(sources)
            sources.append({"pipeline": pipeline, "sample_id": score["sample_id"], "candidate_file": score["candidate_source"],
                            "evidence_file": str((score_root / paths[pipeline + "-current", score["sample_id"]]).resolve())})
            for row in score["outcomes"]:
                if row["outcome"] == "incorrect":
                    errors.append([source_id, row["id"], row["kind"], row["reason"], row["reference"],
                                   first_failure_stage(pipeline + "-current", row, native[score["sample_id"], row["id"]])])
    return {"columns": ["source", "target", "kind", "reason", "expected_location", "first_failure_stage"],
            "sources": sources, "errors": errors, "lookup": "sources[source].evidence_file contains the complete outcome with matching target id"}


def draw_figures(index: dict[str, Any], groups: dict[str, list[dict[str, Any]]], resources: dict[str, Any],
                 cohorts: list[dict[str, Any]], output: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.ticker import NullFormatter, PercentFormatter, ScalarFormatter

    from moparse_eval.report_figures import PIPELINE_COLORS, _register_cjk_fonts

    _register_cjk_fonts(output)
    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    names = []
    labels = list(PIPELINES)
    colors = [PIPELINE_COLORS[p] for p in labels]
    y = np.arange(8)

    def finish(fig, name):
        for ext in ("png", "svg", "pdf"):
            metadata = {"CreationDate": None, "ModDate": None} if ext == "pdf" else {"Date": None} if ext == "svg" else None
            fig.savefig(figures / f"{name}.{ext}", dpi=160, metadata=metadata)
            names.append(f"figures/{name}.{ext}")
        plt.close(fig)

    def style(ax, *, percent=False):
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=0.18)
        if percent:
            ax.xaxis.set_major_formatter(PercentFormatter(1))

    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"],
                         "font.sans-serif": ["DejaVu Sans", "Noto Sans CJK SC"], "font.size": 11,
                         "mathtext.fontset": "dejavusans", "text.usetex": False, "pdf.fonttype": 42,
                         "svg.fonttype": "none", "svg.hashsalt": "mo-parse-lite-report"}):
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout="constrained", sharey=True)
        fig.suptitle("八组原生输出：业务与正文分别比较", fontsize=19)
        for ax, kind in zip(axes, ("business_field", "text"), strict=True):
            counts = [index["summary"][p]["by_kind"][kind] for p in labels]
            values = [ratio(row) for row in counts]
            ax.barh(y, values, color=colors, height=0.6)
            ax.set_yticks(y, labels)
            ax.set_xlim(0, 1)
            ax.set_title(f"{KIND_NAMES[kind]} · 每组 {counts[0]['targets']:,} 个固定目标", fontsize=13)
            for i, (value, row) in enumerate(zip(values, counts, strict=True)):
                ax.text(value + 0.012, i, f"{value:.2%}  {row['correct']:,}/{row['targets']:,}", va="center", fontsize=10)
            style(ax, percent=True)
        axes[0].invert_yaxis()
        finish(fig, "quality")

        fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout="constrained", sharey=True)
        fig.suptitle("处理成本：质量集与固定性能集分开呈现", fontsize=19)
        for ax in axes:
            ax.set_yticks(y, labels)
            style(ax)
        q = [resources["native"][p]["costs"]["processing_seconds"] / 60 for p in labels]
        axes[0].barh(y, q, color=colors, height=0.6)
        for i, value in enumerate(q):
            axes[0].text(value + 2, i, f"{value:.2f}", va="center")
        axes[0].set(xlabel="分钟 ↓", title="800 页质量集 · 一次正式执行", xlim=(0, max(q) * 1.17))
        performance_minutes = []
        for i, pipeline in enumerate(labels):
            times = [r["processing_seconds_including_failures"] / 60 for r in index["execution_costs"]["native"][pipeline]["perf80"]["rounds"]]
            performance_minutes.extend(times)
            axes[1].plot([min(times), max(times)], [i, i], color=colors[i], lw=3, alpha=0.45)
            axes[1].scatter(times, [i - 0.12, i, i + 0.12], color=colors[i], s=35)
            axes[1].text(max(times) + 0.25, i, f"{statistics.median(times):.2f}", va="center")
        axes[1].set(xlabel="分钟 ↓", title="固定 80 页 · 三轮点值与中位数", xlim=(0, max(performance_minutes) * 1.2))
        axes[0].invert_yaxis()
        finish(fig, "processing")

        fig, axes = plt.subplots(1, 3, figsize=(15, 6), layout="constrained", sharey=True)
        fig.suptitle("资源占用：两侧内存与受测显存分别列出", fontsize=19)
        columns = (("worker_host_bytes", 2**30, "工作容器内存"), ("inference_host_bytes", 2**30, "推理容器合计内存"),
                   ("owned_gpu_mib", 1024, "受测容器及子进程显存"))
        for ax, (key, divisor, title) in zip(axes, columns, strict=True):
            values = [resources["native"][p]["costs"][key] / divisor for p in labels]
            ax.barh(y, values, color=colors, height=0.6)
            ax.set_yticks(y, labels)
            ax.set(title=title, xlabel="GiB ↓", xlim=(0, max(values) * 1.24))
            for i, value in enumerate(values):
                ax.text(value + max(values) * 0.025, i, f"{value:.2f}", va="center")
            style(ax)
        axes[0].invert_yaxis()
        fig.supxlabel("原固定协议全程采样峰值；独立峰值不相加；受测显存不含 TTS", fontsize=11)
        finish(fig, "resources")

        fig, axes = plt.subplots(1, 2, figsize=(14, 6.3), layout="constrained")
        fig.suptitle("质量与速度的取舍：点面积表示受测显存", fontsize=19)
        offsets = {"P01": (-8, 13), "P02": (-24, -21), "P03": (10, -25), "P04": (-37, 12),
                   "P05": (8, -22), "P06": (-30, 13), "P07": (10, 12), "P08": (10, 12)}
        for ax, kind in zip(axes, ("business_field", "text"), strict=True):
            for pipeline in labels:
                row = resources["native"][pipeline]
                x, value = row["costs"]["processing_seconds"] / 60, row["qualities"][kind]
                gpu = row["costs"]["owned_gpu_mib"] / 1024
                ax.scatter(x, value, s=gpu * 27, color=PIPELINE_COLORS[pipeline], alpha=0.82, edgecolor="white", lw=0.7)
                ax.annotate(pipeline, (x, value), xytext=offsets[pipeline], textcoords="offset points", color=PIPELINE_COLORS[pipeline],
                            arrowprops={"arrowstyle": "-", "color": PIPELINE_COLORS[pipeline], "lw": 0.7})
            ax.set_xscale("log")
            ax.set_xticks([20, 30, 50, 100, 200])
            ax.xaxis.set_major_formatter(ScalarFormatter())
            ax.xaxis.set_minor_formatter(NullFormatter())
            ax.yaxis.set_major_formatter(PercentFormatter(1))
            ax.set(xlim=(18, 255), ylim=(0, 0.46 if kind == "business_field" else 0.8),
                   xlabel="800页直接处理耗时（分钟，对数轴）↓", ylabel=KIND_NAMES[kind] + "正确率 ↑")
            style(ax)
        for size in (3, 5, 8):
            axes[1].scatter([], [], s=size * 27, color="#777777", alpha=0.65, label=f"{size} GiB")
        axes[1].legend(loc="lower right", title="显存采样峰值", frameon=False)
        fig.supxlabel("二维投影不作整体支配判断；完整取舍同时核对两侧内存和其他质量项", fontsize=11)
        finish(fig, "tradeoffs")

        fig, axes = plt.subplots(1, 2, figsize=(13, 5.4), layout="constrained", sharey=True)
        fig.suptitle("P07/P08：最终正文保留原生信息，并增加可用业务表达", fontsize=18)
        stage_names = ["原生输出", "修复前正文", "修复后正文"]
        for ax, pipeline in zip(axes, ("P07", "P08"), strict=True):
            values = [index["summary"][key]["by_kind"]["business_field"]["correct"] for key in (pipeline, pipeline + "-intermediate", pipeline + "-current")]
            ax.bar(range(3), values, color=["#9ba7b1", "#88aabb", PIPELINE_COLORS[pipeline]], width=0.6)
            ax.set_xticks(range(3), stage_names)
            for i, value in enumerate(values):
                ax.text(i, value + 35, f"{value:,}", ha="center", fontsize=12)
            delta = index["incremental_changes"][pipeline]
            ax.set(title=f"{pipeline}：本轮新增正确业务 {delta['gains_by_kind'].get('business_field', 0)}，损失 {delta['lost_correct']}", ylim=(0, max(values) * 1.2))
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=0.16)
            ax.set_axisbelow(True)
        axes[0].set_ylabel(f"正确业务字段 / 每组 {index['summary']['P07']['by_kind']['business_field']['targets']:,} 个固定目标")
        finish(fig, "postprocessing")

        fig, ax = plt.subplots(figsize=(12.5, 6), layout="constrained")
        palettes = ["#667c9b", "#ba7b88", "#cb9b51", "#76a06b", "#999999"]
        counts = {}
        for pipeline in labels:
            counts[pipeline] = Counter(error_category(row["reason"]) for score in groups[pipeline] for row in score["outcomes"]
                                       if row["kind"] == "business_field" and row["outcome"] == "incorrect")
        left = np.zeros(8)
        for label, color in zip(ERROR_NAMES, palettes, strict=True):
            values = np.array([counts[p][label] for p in labels])
            ax.barh(y, values, left=left, label=label, color=color, height=0.62)
            left += values
        ax.set_yticks(y, labels)
        ax.invert_yaxis()
        ax.set(title="业务错误的程序原因：定位/范围问题与值错误分开", xlabel=f"错误业务目标数（每组固定目标 {index['summary']['P01']['by_kind']['business_field']['targets']:,}）")
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=5, frameon=False, fontsize=10)
        style(ax)
        finish(fig, "errors")

        fig, ax = plt.subplots(figsize=(12.5, 7), layout="constrained")
        matrix = np.array([[next(row["correctness"] for row in cohorts if row["tag"] == tag and row["pipeline"] == pipeline and row["kind"] == "business_field")
                            if any(row["tag"] == tag and row["pipeline"] == pipeline and row["kind"] == "business_field" and row["targets"] for row in cohorts)
                            else np.nan for pipeline in labels] for tag, _label in COHORTS])
        image = ax.imshow(matrix, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto")
        cohort_labels = [f"{label}  n={next(r['samples'] for r in cohorts if r['tag']==tag)}" for tag, label in COHORTS]
        ax.set_xticks(range(8), labels)
        ax.set_yticks(range(len(COHORTS)), cohort_labels)
        for (i, j), value in np.ndenumerate(matrix):
            ax.text(j, i, "无目标" if np.isnan(value) else f"{value:.1%}", ha="center", va="center", color="white" if value > 0.6 else "#172b3a", fontsize=10)
        ax.set_title("预声明版式标签下的业务目标正确率", fontsize=17, pad=15)
        fig.colorbar(image, ax=ax, format=PercentFormatter(1), shrink=0.8)
        fig.supxlabel("按完整样本的已有标签分组；标签可重叠；不是局部表格单元格准确率", fontsize=11)
        finish(fig, "cohorts")
    return names


def render(index_path: Path, output: Path) -> list[str]:
    index, groups = load_complete(index_path)
    index["report_score_index"] = str(index_path.resolve())
    output.mkdir(parents=True, exist_ok=True)
    data = output / "data"
    data.mkdir(exist_ok=True)
    resources = collect_resource_comparison(index)
    rows = native_rows(index, resources)
    cohorts = cohort_rows(groups)
    first = index["summary"]["P01"]
    coverage = {"samples": len(index["coverage"]), "pages": sum(len({p for scope in r['scope'] for p in scope['pages']}) for r in index["coverage"]),
                "documents": first["documents"], "families": len(first["by_family"]),
                "expected_elements": sum(r["content_coverage"]["expected_elements"] for r in index["coverage"]),
                "targets_per_group": sum(r["targets"] for r in index["coverage"]),
                "business_targets": first["by_kind"]["business_field"]["targets"], "groups": len(groups), "sample_evaluations": len(index["records"])}
    write_json(data / "results.json", {"protocol": index["protocol"], "software_id": index["software"]["software_id"],
        "coverage": coverage, "summary": index["summary"], "expected_coverage": index["coverage"],
        "native_preservation": index["native_preservation"], "adoption": index["adoption"],
        "repair_changes": index["incremental_changes"], "earlier_changes": index["changes"]})
    write_json(data / "resources.json", resources)
    costs = index["execution_costs"]
    timing_keys = ("boundary", "measured_runs", "scheduled_runs", "successful_runs", "failed_runs",
                   "status_counts", "rounds", "warmup", "initialization", "timing_unavailable")
    write_json(data / "execution.json", {
        "native": {p: {suite: {k: v for k, v in costs["native"][p][suite].items() if k in timing_keys}
                       for suite in ("quality800", "perf80")} for p in PIPELINES},
        "final": {p: {k: v for k, v in value.items() if k in (
            "run", "software_id", "measurement_notes", "quality800", "perf80", "warmup")}
                  for p, value in costs["final"].items()},
        "historical_native_conditions": costs.get("historical_native_conditions"),
        "shared_native_worker": "initialization and warmup repeated in suite summaries describe the same worker, not additive costs"})
    write_json(data / "errors.json", error_index(index, groups))
    layout = read_json(Path(index["baseline"]) / "layout.json")
    write_json(data / "provenance.json", {"layout": layout, "score_index": str(index_path.resolve()),
        "score_index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(), "scoring_software": index["software"],
        "report_generator": "scripts/render_lite_report.py", "report_generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "resource_sources": resources["sources"], "development_exposure": index["development_exposure"]})
    write_csv(data / "native.csv", rows)
    write_csv(data / "cohorts.csv", cohorts)
    diagnostic_rows = [{"pipeline": p, **text_diagnostics(groups[p])} for p in PIPELINES]
    write_csv(data / "text-diagnostics.csv", diagnostic_rows)
    document_rows, family_rows = [], []
    for pipeline in PIPELINES:
        for scope, target in (("by_document", document_rows), ("by_family", family_rows)):
            for name, summary in sorted(index["summary"][pipeline][scope].items()):
                for kind in ("business_field", "text"):
                    values = summary["by_kind"].get(kind, {})
                    target.append({"scope": name, "pipeline": pipeline, "kind": kind, "samples": summary["samples"],
                                   "correct": values.get("correct", 0), "targets": values.get("targets", 0), "correctness": ratio(values)})
    write_csv(data / "documents.csv", document_rows)
    write_csv(data / "families.csv", family_rows)
    pair_rows = []
    for pipeline in ("P07", "P08"):
        counts = [index["summary"][key]["by_kind"]["business_field"]["correct"] for key in (pipeline, pipeline + "-intermediate", pipeline + "-current")]
        delta, preserved = index["incremental_changes"][pipeline], index["native_preservation"][pipeline]
        pair_rows.append({"pipeline": pipeline, "native_correct": counts[0], "before_correct": counts[1], "after_correct": counts[2],
                          "new_correct_business": delta["gains_by_kind"]["business_field"], "lost_correct_targets": delta["lost_correct"],
                          "native_correct_content_targets": preserved["native_correct_targets"], "native_content_losses": preserved["lost_correct_targets"]})
    write_csv(data / "postprocessing.csv", pair_rows)
    figures = draw_figures(index, groups, resources, cohorts, output)
    quality = {p: index["summary"][p]["by_kind"] for p in PIPELINES}
    business_total = coverage["business_targets"]
    text_total = quality["P01"]["text"]["targets"]
    processing_minutes = [row["processing_seconds"] / 60 for row in rows]
    gains = [index["incremental_changes"][p]["gains_by_kind"].get("business_field", 0) for p in ("P07", "P08")]
    remaining = [index["summary"][p + "-current"]["by_kind"]["business_field"]["incorrect"] for p in ("P07", "P08")]
    cpu_seconds = [index["execution_costs"]["final"][p + "-current"]["quality800"]["rounds"][0]["postprocessing_seconds"] for p in ("P07", "P08")]
    rss_gib = [resources["final_cpu"][p]["quality800_peak_process_rss_bytes"] / 2**30 for p in ("P07", "P08")]
    time_by_pipeline = {row["pipeline"]: row["processing_seconds"] for row in rows}
    p07_gain = quality["P07"]["business_field"]["correct"] - quality["P06"]["business_field"]["correct"]
    p08_gain = quality["P08"]["business_field"]["correct"] - quality["P07"]["business_field"]["correct"]
    p04_business_change = quality["P04"]["business_field"]["correct"] - quality["P03"]["business_field"]["correct"]
    p04_text_change = quality["P04"]["text"]["correct"] - quality["P03"]["text"]["correct"]
    native_losses = sum(index["native_preservation"][p]["lost_correct_targets"] for p in ("P07", "P08"))
    dominated = {p: value["observed_dominated_by"] for p, value in resources["native"].items() if value["observed_dominated_by"]}
    dominance_text = ("本批已观测向量没有全面支配者" if not dominated else f"观测支配关系为{dominated}")
    report = ["# MO-Parse Lite：解析质量、处理成本与正文优化", "",
              f"同一批 **{coverage['pages']}页 / {coverage['samples']}个样本 / {coverage['documents']}份文档 / {coverage['families']}个家族**；expected是唯一答案来源，八组原生结果与P07/P08后处理分别比较。", "",
              "## 结果先看", "",
              "- 原生业务目标正确率：" + "、".join(f"{p}为{ratio(quality[p]['business_field']):.2%}" for p in ("P08", "P07", "P03")) + "；正文段落正确率分别为" + "、".join(f"{ratio(quality[p]['text']):.2%}" for p in ("P08", "P07", "P03")) + "。分母包含全部目标。",
              f"- {coverage['pages']}页原生处理约{min(processing_minutes):.2f}至{max(processing_minutes):.2f}分钟。P03/P04受测显存采样峰约{resources['native']['P03']['costs']['owned_gpu_mib']/1024:.2f}GiB，P07约{resources['native']['P07']['costs']['owned_gpu_mib']/1024:.2f}GiB；质量、速度和占用需要一起比较。",
              f"- P07/P08修复后的实际Markdown分别新增{gains[0]}、{gains[1]}项正确业务目标，改前改后损失及原生信息保留见配对表。",
              f"- 最终正文仍有{remaining[0]:,}、{remaining[1]:,}项业务目标错误，均计入分母，并保留逐项证据。", "",
              "**导航：** [八组质量](#八组原生质量) · [耗时与资源](#耗时与资源) · [P07/P08正文收益](#p07p08正文收益) · [错误与分组](#错误与分组) · [方法和复现](appendix.md)", "",
              "## 八组原生质量", "",
              f"每组固定{business_total:,}个业务目标。业务正确同时要求值、主体、单位、期间、分组和附注满足expected；普通正文按完整段落或连续文字比较，允许已声明的表达等价。标题、列表、单位说明和图片alt字面另报，不合成加权总分。", "",
              f"| 管线 | 固定配置 | 业务正确 / {business_total:,} | 正文正确 / {text_total:,} |", "| --- | --- | ---: | ---: |"]
    for pipeline in PIPELINES:
        summary = index["summary"][pipeline]["by_kind"]
        report.append(f"| {pipeline} | {PIPELINE_NAMES[pipeline]} | {fraction_text(summary['business_field'])} | {fraction_text(summary['text'])} |")
    report += ["", "![八组原生质量](figures/quality.png)", "",
               "P01/P02仅改变TableFormer版本，P03/P04仅改变PaddleOCR-VL模型版本，P06/P07仅改变MinerU层级；P05/P08是各自完整视觉管线。各分支、模型和原生格式见[固定配置](../../pipelines-to-test.md)及[逐管线说明](../../../docs/pipelines/README.md)。", "",
               f"Paddle 1.6相对1.5，正文段落新增正确{p04_text_change:+,}项，业务正确变化{p04_business_change:+,}项。版本变化对内容类型的影响不同，不能只用正文字符指标代表业务关系质量。", "",
               "## 耗时与资源", "",
               "| 管线 | 800页分钟 | 80页三轮中位数分钟 | 工作内存GiB | 推理内存GiB | 受测显存GiB |",
               "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        report.append(f"| {row['pipeline']} | {display(row['processing_seconds']/60)} | {display(row['perf80_median_seconds']/60)} | {display(row['worker_host_bytes']/2**30)} | {display(row['inference_host_bytes']/2**30)} | {display(row['owned_gpu_mib']/1024)} |")
    report += ["", "![原生处理耗时及三轮波动](figures/processing.png)", "",
               "800页只有一次质量执行；80页三轮衡量重复波动，不增加独立文档样本。图中80页文字标中位数，点保留每轮实际值。初始化和预热单列，直接处理边界包含所需渲染、原生解析、忠实导出与资产准备，排除HTTP和MO-Parse后处理。", "",
               "![两侧内存与受测显存](figures/resources.png)", "",
               "内存和显存是原固定协议全程的采样峰值，包含初始化、预热、800页和80页重复；不是800页阶段的精确峰值。工作容器与推理侧分开采样，不把各自峰值相加。受测显存按容器及子进程归属汇总，TTS和整卡占用另列于附录。", "",
               "![质量与速度的取舍](figures/tradeoffs.png)", "",
               f"点面积表示受测显存。完整比较同时核对六类内容正确率、耗时、两侧内存及受测显存；{dominance_text}。TTS共驻、负载不受控；原始采样间隔通常约2秒，P06/P07推理侧约4秒，[覆盖、缺失和原始文件身份见附录](appendix.md#资源采样与共驻环境)。", "",
               f"P07比P06多保留{p07_gain}个正确业务目标，800页多用{(time_by_pipeline['P07']-time_by_pipeline['P06'])/60:.2f}分钟。P08比P07再多{p08_gain}项，耗时再增{(time_by_pipeline['P08']-time_by_pipeline['P07'])/60:.2f}分钟，但受测显存峰值降低{(resources['native']['P07']['costs']['owned_gpu_mib']-resources['native']['P08']['costs']['owned_gpu_mib'])/1024:.2f}GiB，两侧内存也更低。这是本批配置的实际取舍，不能据此推定其他文档上的固定胜者。", "",
               "## P07/P08正文收益", "",
               "这里只比较同组原生输出、本轮修复前正文和修复后正文。修复前是原06版，修复后是原08版；expected始终不变。早期04版仅用于附录中的累计对照，不混入本轮收益。", "",
               "| 管线 | 原生正确业务 | 修复前 | 修复后 | 新增正确业务 | 原正确目标损失 | 原生正确内容损失 |",
               "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in pair_rows:
        report.append("| " + " | ".join(str(row[key]) for key in ("pipeline", "native_correct", "before_correct", "after_correct", "new_correct_business", "lost_correct_targets", "native_content_losses")) + " |")
    report += ["", "![P07/P08实际正文收益](figures/postprocessing.png)", "",
               "改善来自实际打印的Markdown：阻止年龄继承股份单位，保全属性字段、完整表头与表名，并将期间绑定到实际年份片段。评分器读取改善对全部版本共同生效，不算正文收益；内部IR或隐藏关系不补分。具体前后文字及采用门槛见[附录](appendix.md#正文修复与信息保留)。", "",
               f"P07/P08的{coverage['pages']}页CPU后处理分别为{cpu_seconds[0]:.2f}秒、{cpu_seconds[1]:.2f}秒；进程RSS采样峰值为{rss_gib[0]:.3f}GiB、{rss_gib[1]:.3f}GiB，均未挂载GPU。后处理与原生执行来自不同运行，不相加为新的端到端耗时。", "",
               "## 错误与分组", "",
               "![业务错误原因](figures/errors.png)", "",
               f"这些是程序给出的目标错误原因。定位/表头范围不足、范围歧义、值不符和限定不符分开统计，不能将它们一律解释成模型识别缺字。当前P07/P08原生正确而最终正文错误的目标共{native_losses}个；剩余失败仍需从保存的原生结果和读取证据逐项诊断。", "",
               "![预声明样本标签分组](figures/cohorts.png)", "",
               "分组只使用既有样本标签；标签可重叠，不能相加成数据集分区。每行比较该标签下完整样本的业务目标，不称局部表格或局部栏位准确率。完整文档、家族、字符诊断与资产交付见[附录](appendix.md)。", "",
               "## 覆盖、证据与复现", "",
               f"本轮{coverage['expected_elements']:,}个expected内容元素全部进入程序对照，展开为每组{coverage['targets_per_group']:,}个目标，遗漏0；同一列表元素可包含多个业务字段。全部目标只有正确或错误。{coverage['groups']}个比较组共{coverage['sample_evaluations']:,}份评分，质量主表只用{coverage['pages']}页，性能重复不充当额外独立质量样本。", "",
               "Lite内容已用于读取和转换开发，不宣称独立未见测试集。图片语义理解不在范围内；alt文字、引用和资产交付分别处理。", "",
               "- [完整分项与采用门槛](data/results.json)", "- [P07/P08逐项错误及证据入口](data/errors.json)",
               "- [资源数据与测量来源](data/resources.json) · [各轮耗时、预热及环境观察](data/execution.json)", "- [文档明细](data/documents.csv) · [家族明细](data/families.csv) · [样本标签明细](data/cohorts.csv)",
               "- [目录用途、方法和复现命令](appendix.md)", "",
               "[目录迁移、评分复算、图件字体与报告重现验证](data/verification.json)。", "",
               f"评分：`{index['protocol']['id']}` / `{index['protocol']['reader_revision']}`；软件身份：`{index['software']['software_id']}`。本次整理复用保存输出，未新增模型推理、部署或服务操作。", ""]
    (output / "report.md").write_text("\n".join(report))
    appendix = ["# MO-Parse Lite：方法、执行目录与证据", "", "[返回主报告](report.md)", "",
                "## 目录与输入角色", "",
                "正式报告只保留当前入口；执行输入和测量留在本地运行目录。原生输出、各版正文及资产独立保存，组织合并不拼接答案，不改写candidate字节。", "",
                "| 旧目录 | 当前位置 | 作用 |", "| --- | --- | --- |",
                "| 20261026-lite-v3 | benchmark/runs/lite | 八组原生结果、原始计时与当前统一评分 |",
                "| 20261026-repaired-preflight-02 | benchmark/runs/lite/preflight | 工程预检、软件及资源冻结依据 |",
                "| 20261031-units-continuations-04 | benchmark/runs/lite/service/earlier | 较早正文，仅用于累计对照 |",
                "| 20261101-expected-only-06 | benchmark/runs/lite/service/before | 本轮修复前实际正文 |",
                "| 20261101-preservation-repair-08 | benchmark/runs/lite/service/after | 修复后实际正文 |", "",
                "原始执行/冻结记录中的历史路径作为原始记录保留，当前位置对应关系见[data/provenance.json](data/provenance.json)。不保留旧路径兼容目录或错误评分归档。", "",
                "## 共同评分与目标覆盖", "",
                "canonical expected只读，是唯一答案标准。现有manifest和来源映射定位授权选段；评分读取完整标题、正文、列表、表格、单位、期间及附注。旧索引不供答案，人工裁定不排除目标；读取故障必须先修复，不能发布第三种质量成绩。", "",
                f"本轮{coverage['pages']}页、{coverage['samples']}样本、{coverage['documents']}文档、{coverage['families']}家族；{coverage['expected_elements']:,}个内容元素、每组{coverage['targets_per_group']:,}个目标，其中业务字段{business_total:,}个。内容位置及各组共同分母完整保存在data/results.json。", "",
                "| 管线 | " + " | ".join(KIND_NAMES.values()) + " |", "| --- | " + " | ".join("---:" for _ in KIND_NAMES) + " |"]
    for pipeline in PIPELINES:
        appendix.append(f"| {pipeline} | " + " | ".join(fraction_text(index['summary'][pipeline]['by_kind'].get(kind,{})) for kind in KIND_NAMES) + " |")
    appendix += ["", "## 字符诊断与数值字面", "",
                 "完整目标正确率是主质量指标。下表严格CER只覆盖已定位的普通文字目标，未定位数量另列；不将其称为整篇OCR错误率。数值字面保留另报，不能用数字相同掩盖单位、期间或业务归属错误。", "",
                 "| 管线 | 普通文字目标 | 已定位 | 未定位 | 已定位严格CER | 数值字面严格一致 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in diagnostic_rows:
        raw = index["summary"][row["pipeline"]]["raw_value_diagnostics"]
        cer = f"{row['located_strict_cer']:.3%}" if row['located_strict_cer'] is not None else "缺测"
        appendix.append(f"| {row['pipeline']} | {row['targets']} | {row['located']} | {row['missing']} | {cer} | {raw['strict_exact']}/{raw['targets']} |")
    appendix += ["", "## 资源采样与共驻环境", "",
                 "Docker stats报告已用内存。推理容器先按同一采样轮内的当前受测容器合计，再取峰值；容器读取有先后。工作容器和推理侧使用不同采样器，不相加独立峰值。显存取同次进程查询中受测容器及子进程的归属合计，不使用Torch allocated/reserved或预算代替总使用。", "",
                 "| 管线 | 工作内存有效/总轮 | 推理内存有效/总轮 | 显存归属有效/总轮 | 工作间隔中位/最大秒 | 推理间隔中位/最大秒 | TTS峰GiB | 整卡峰GiB |",
                 "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for pipeline in PIPELINES:
        w, i = (resources["native"][pipeline]["resource_observations"][key] for key in ("worker", "inference"))
        tts_peak = i['tts_peak_mib'] / 1024 if i['tts_peak_mib'] is not None else None
        card_peak = i['whole_gpu_peak_mib'] / 1024 if i['whole_gpu_peak_mib'] is not None else None
        appendix.append(f"| {pipeline} | {w['host_complete_samples']}/{w['samples']} | {i['host_complete_samples']}/{i['samples']} | {i['gpu_complete_samples']}/{i['samples']} | {display(w['median_gap_seconds'],3)}/{display(w['maximum_gap_seconds'],3)} | {display(i['median_gap_seconds'],3)}/{display(i['maximum_gap_seconds'],3)} | {display(tts_peak)} | {display(card_peak)} |")
    tts = costs.get("historical_native_conditions", {}).get("evidence", {}).get("tts_no_calls_condition", {})
    appendix += ["", f"原生执行起止观察记录的TTS新增任务数为{tts.get('observed_new_jobs', '未记录')}，状态为`{tts.get('status', '未记录')}`；健康检查和持久任务计数并非原子观测，可能漏掉短调用。环境原始观察见[data/execution.json](data/execution.json)，实际模型、资源预算和Graph配置见[执行冻结](../../execution-lock.json)。", ""]
    appendix += ["", "0.25秒是采样轮间等待，实际周期还包含串行Docker和GPU查询。缺失轮留在分母中，短峰可能漏采；结论是观测向量取舍，不是精确容量上界或统计上的普遍最优。TTS共驻且负载不受控，其显存和整卡占用只描述环境，不计入受测支配判断，也不相减制造管线显存。", "",
                 "## 正文修复与信息保留", "",
                 "业务比较只读取实际final.md，内部IR和未打印关系不补分。采用同时要求原生正确内容在修复后仍正确，以及修改前后无正确项损失；布局正文不能伪造成业务字段。", "",
                 "| 管线 | 原生正确全部内容 | 修复后保留 | 内容丢失 | 早期正文至修复后新增业务 | 本轮修复新增业务 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for p in ("P07", "P08"):
        native = index["native_preservation"][p]
        appendix.append(f"| {p} | {native['native_correct_targets']} | {native['preserved_targets']} | {native['lost_correct_targets']} | {index['changes'][p]['gains_by_kind'].get('business_field',0)} | {index['incremental_changes'][p]['gains_by_kind'].get('business_field',0)} |")
    appendix += ["", "| 修复实例 | 修复前保存的表达 | 修复后实际文字 |", "| --- | --- | --- |",
                 "| 年龄单位 | 年龄：52（单位：股） | 年龄：52 |",
                 "| 属性字段 | HTML中公司的中文简称及跨列值 | 公司的中文简称：美的集团。 |",
                 "| 期间片段 | 期间：（3）2024 年度污染物排放情况: | 期间：2024 年度 |", "",
                 "年龄出自`quality800-r1-moutai-governance-p018-029/final.md`，简称出自`quality800-r1-midea-front-p001-012/final.md`，年度片段出自`quality800-r1-moutai-governance-environment-p030-039/final.md`；对应修改前后完整输出位于`benchmark/runs/lite/service/{before,after}/p07/candidate/artifacts/`。", "",
                 "| 软件缺陷 | 修复方式 |", "| --- | --- |",
                 "| 业务名词、单位和普通数字混用，导致年龄继承股单位 | 区分单位声明与业务名词，按字段适用类型继承单位；矛盾陈述不能挑正确一条补分 |",
                 "| 属性分类先于表头识别，使姓名/工作经历等表失去列头 | 先识别完整表头再生成属性记录，保留跨列表名，布局证据继续约束转换 |",
                 "| 合并格、多层路径、连续列表币种及复合主体漏读 | 只读实际跨度、路径和语法范围，先定位业务标签，再比较值与限定；全部候选共同重评 |",
                 "| 标题拆块后仍有完整文字，却按单块判缺失 | 在实际相邻文字中连续对照，保存各组成位置，不跨表、图片、已知页边界或跳过否定 |",
                 "| 只检查正文版本之间的新增损失，漏掉原生到正文的旧损失 | 同时验证原生正确全部内容保留和改前改后零退化，业务字段另列 |", "",
                 "前两项改变实际Markdown，读取修复改变共同测量，不混算正文收益。独立反例见[契约探针](../../diagnostics/expected-preservation-probes-20261102.json)，共同评分身份见data/provenance.json。原生缺失信息没有从expected补写。", "",
                 "## 文档、家族与标签明细", "",
                 "按文档和家族的完整分子/分母见[data/documents.csv](data/documents.csv)、[data/families.csv](data/families.csv)。本轮来源类别元数据主要为source-unknown或未声明，未从候选反推原图类别；分组图只使用既有版式标签。标签重叠，不是独立文档分层，也不是局部目标标注。Lite已暴露于开发，不宣称未见验证集。", "",
                 "## 资产交付", "",
                 "图片内容理解不在本轮范围。这里只核对候选自己的文件清单与引用关联，不打开图像评分；关联缺口不能直接解释为图片文件丢失或模型图像理解错误。", "",
                 "| 管线 | 声明文件 | 保存文件 | 图片引用 | 已关联引用 | 未关联引用 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for key in (*PIPELINES, "P07-current", "P08-current"):
        row = index["summary"][key]["asset_delivery"]
        appendix.append(f"| {key} | " + " | ".join(str(row[k]) for k in ("declared_files","files_present","image_references","references_with_file","references_without_file")) + " |")
    appendix += ["", "## 重复处理与CPU后处理", "",
                 "SDK初始化和8页共同预热单列，不进入800页或80页测量。初始化值指常驻SDK worker，不含GPU服务启动；两个suite摘要中的同一初始化/预热记录只发生一次，不重复相加。CPU后处理各阶段预热保存在data/execution.json。", "",
                 "| 管线 | SDK初始化秒 | 预热样本秒（2页/2页/4页） |", "| --- | ---: | --- |"]
    for p in PIPELINES:
        measured = costs["native"][p]["quality800"]
        initialization = measured.get("initialization", [])
        seconds = initialization[0].get("initialization_seconds") if len(initialization) == 1 else None
        appendix.append(f"| {p} | {display(seconds,3)} | " + " / ".join(display(row.get("processing_seconds"),3) for row in measured.get("warmup", [])) + " |")
    appendix += ["", "正式测量的各轮直接处理时间：", "",
                 "| 管线/阶段 | 800页秒 | 80页第1轮秒 | 第2轮秒 | 第3轮秒 |", "| --- | ---: | ---: | ---: | ---: |"]
    for p in PIPELINES:
        cost = index["execution_costs"]["native"][p]
        appendix.append(f"| {p}原生 | {display(cost['quality800']['rounds'][0]['processing_seconds_including_failures'],3)} | " + " | ".join(display(x['processing_seconds_including_failures'],3) for x in cost['perf80']['rounds']) + " |")
    for p in ("P07", "P08"):
        cost = index["execution_costs"]["final"][p + "-current"]
        appendix.append(f"| {p}修复后CPU | {display(cost['quality800']['rounds'][0]['postprocessing_seconds'],3)} | " + " | ".join(display(x['postprocessing_seconds'],3) for x in cost['perf80']['rounds']) + " |")
    appendix += ["", "CPU回放各800页与80页三轮，预热单列。8 CPU/8GiB、无网络、无GPU，worker不挂载expected、不调用模型。实际RSS来自各处理窗口采样，资源与原生阶段分开；原处理计时不因本次目录或报告整理改变。", "",
                 "## 复现", "",
                 "只重生正式报告不读取expected或原PDF，也不再次处理候选。单一报告命令读取已完成评分和原测量记录，统一产生主报告、附录、图件及数据。", "",
                 "```bash", ".venv/bin/python scripts/render_lite_report.py \\",
                 "  --index benchmark/runs/lite/scores/current/index.json \\", "  --output benchmark/reports/lite", "```", "",
                 "统一重评分保存输出时，必须使用当前冻结程序及只读canonical expected；此操作不重新推理、不回放后处理、不回填处理计时。", "",
                 "```bash", ".venv/bin/python -m moparse_eval.expected_evaluation \\", "  --baseline benchmark/runs/lite \\",
                 "  --previous-root benchmark/runs/lite/service/earlier \\", "  --intermediate-root benchmark/runs/lite/service/before \\",
                 "  --current-root benchmark/runs/lite/service/after \\", "  --freeze benchmark/diagnostics/expected-preservation-validation-20261102.json \\",
                 "  --output benchmark/runs/lite/scores/new-reproduction --workers 8", "```", "",
                 "expected保持只读。改变后处理代码时再按既定隔离及三轮口径执行；仅改变目录和报告时验证输入、判定和产物重现。错误旧评分逻辑、成绩及再生脚本已经删除，不恢复归档。", ""]
    (output / "appendix.md").write_text("\n".join(appendix))
    artifacts = ["report.md", "appendix.md", *("data/" + name for name in ("results.json","resources.json","execution.json","errors.json","provenance.json",
                    "native.csv","postprocessing.csv","cohorts.csv","text-diagnostics.csv","documents.csv","families.csv")), *figures]
    write_json(data / "artifacts.json", {"files": artifacts, "scoring_software_id": index["software"]["software_id"],
                                        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    return artifacts + ["data/artifacts.json"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = render(args.index, args.output)
    print(f"Generated {len(paths)} report artifacts: {args.output / 'report.md'}")
