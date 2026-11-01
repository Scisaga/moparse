"""Present completed scores and resource records, never reference or answer files."""

from __future__ import annotations

import argparse
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

RESOURCE_MARKER = "<!-- recorded-resource-comparison -->"
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


def render_resource_comparison(index: dict[str, Any], output: Path) -> str:
    comparison = collect_resource_comparison(index)
    write_json(output / "resource-costs.json", comparison)

    def show(value, divisor=1):
        return f"{value / divisor:.3f}" if value is not None else "缺测"

    lines = ["## 内存、显存与质量成本比较", "",
             "质量与800页直接处理耗时取当前冻结结果；资源取原执行完整协议的采样记录，包含初始化、预热、quality800与perf80。记录没有各样本完整起止时刻，不能把全程资源峰值改称800页阶段峰值。", "",
             "| 管线 | 800页秒 | 工作容器内存GiB | 推理容器合计内存GiB | 受测显存GiB | 观测向量的支配者 |",
             "| --- | ---: | ---: | ---: | ---: | --- |"]
    for pipeline, row in comparison["native"].items():
        cost = row["costs"]
        label = ", ".join(row["observed_dominated_by"]) or "无"
        if row["comparison_status"] != "observed_vector_compared":
            label = "缺测，不作结论"
        lines.append(f"| {pipeline} | {show(cost['processing_seconds'])} | {show(cost['worker_host_bytes'], 2**30)} | {show(cost['inference_host_bytes'], 2**30)} | {show(cost['owned_gpu_mib'], 1024)} | {label} |")
    lines += ["", "内存来自Docker stats的已用内存显示；推理侧先在同一采样轮内合计当前受测容器，再取峰值。容器读取有先后；工作容器与推理容器分开采样，因此不相加成整条管线的同时内存峰值。显存使用同次进程查询中归属受测容器及其子进程的合计，不使用Torch allocated/reserved代替总量，也不把预算上限当实测使用。", "",
              "支配检验同时比较业务字段、标题、图片alt字面、列表、正文、单位说明六类正确率及耗时、两项内存、受测显存共十维，不合成加权分数；质量分子分母见report.md。另分别计算只用业务或正文正确率的五维比较，结果保存在resource-costs.json。缺测不按零处理，不给出完整支配结论。结论仅针对记录中的观测向量；有限采样可能漏过更短峰值，不能据此声称实际资源的精确最优或普遍方法优劣。", "",
              "![质量与四项成本的投影](resource-tradeoffs.svg)", "",
              "各面板都是单项成本投影，不以灰叉或阶梯线表示全面支配。速度更快可以同时需要更多内存或显存。", "",
              "### 采样覆盖与共驻环境", "",
              "| 管线 | 工作内存有效轮/总轮 | 推理内存有效轮/总轮 | 显存归属有效轮/总轮 | 工作采样间隔中位数/最大秒 | 推理采样间隔中位数/最大秒 | TTS显存峰GiB | 整卡显存峰GiB |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for pipeline, row in comparison["native"].items():
        worker, inference = (row["resource_observations"][key] for key in ("worker", "inference"))
        lines.append(f"| {pipeline} | {worker['host_complete_samples']}/{worker['samples']} | {inference['host_complete_samples']}/{inference['samples']} | {inference['gpu_complete_samples']}/{inference['samples']} | {show(worker['median_gap_seconds'])}/{show(worker['maximum_gap_seconds'])} | {show(inference['median_gap_seconds'])}/{show(inference['maximum_gap_seconds'])} | {show(inference['tts_peak_mib'], 1024)} | {show(inference['whole_gpu_peak_mib'], 1024)} |")
    lines += ["", "实际采样周期包括串行Docker及GPU查询，0.25秒只是轮间等待，不能称为250毫秒采样精度。缺失轮次保留在覆盖分母中。TTS保持共驻、负载不受控；TTS与整卡值仅描述环境，不进入受测资源支配计算，也不通过相减制造管线显存。", "",
              "### 最终正文CPU后处理内存", "",
              "| 管线 | 800页进程RSS采样峰GiB | 有内存记录的样本 | GPU |",
              "| --- | ---: | ---: | --- |"]
    for pipeline, row in comparison["final_cpu"].items():
        gpu = "未挂载" if row["gpu_devices"] == [] else "缺少隔离证据"
        lines.append(f"| {pipeline} | {show(row['quality800_peak_process_rss_bytes'], 2**30)} | {row['memory_samples_available']}/{row['measured_samples']} | {gpu} |")
    lines += ["", "后处理RSS单列，不能与原生阶段不同时发生的峰值相加。原始测量路径及测量文件身份见resource-costs.json；本次只呈现已有记录，没有重新推理、测量或操作服务。", ""]
    markdown = "\n".join(lines)
    (output / "resource-costs.md").write_text(markdown)
    draw_resource_comparison(comparison, output)
    return markdown


def draw_resource_comparison(comparison: dict[str, Any], output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullFormatter, PercentFormatter, ScalarFormatter

    from moparse_eval.report_figures import PIPELINE_COLORS, _register_cjk_fonts

    _register_cjk_fonts(output)
    columns = [("processing_seconds", 60, "800页直接处理耗时（分钟，对数轴）↓"),
               ("worker_host_bytes", 2**30, "工作容器采样内存峰值（GiB）↓"),
               ("inference_host_bytes", 2**30, "推理容器合计采样内存峰值（GiB）↓"),
               ("owned_gpu_mib", 1024, "受测进程合计采样显存峰值（GiB）↓")]
    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"],
                         "font.sans-serif": ["DejaVu Sans", "Noto Sans CJK SC"],
                         "mathtext.fontset": "dejavusans", "text.usetex": False,
                         "pdf.fonttype": 42, "svg.fonttype": "none", "svg.hashsalt": "mo-parse-resource-costs"}):
        fig, axes = plt.subplots(2, 4, figsize=(21, 9.8), layout="constrained")
        fig.suptitle("质量与资源成本：耗时、内存与显存\n质量与耗时：800页；内存与显存：固定协议全程采样峰值", fontsize=19)
        for row_index, (kind, ylabel) in enumerate((("business_field", "业务字段正确率 ↑"), ("text", "完整正文目标正确率 ↑"))):
            highest = max(record["qualities"][kind] or 0 for record in comparison["native"].values())
            for column, (key, divisor, xlabel) in enumerate(columns):
                ax = axes[row_index, column]
                for pipeline, record in comparison["native"].items():
                    x, y = record["costs"][key], record["qualities"][kind]
                    if x is None or y is None:
                        continue
                    x /= divisor
                    ax.scatter(x, y, color=PIPELINE_COLORS[pipeline], s=62, zorder=3)
                    offset = {"P01": (-10, 10), "P02": (-25, -16), "P03": (8, -27), "P04": (-30, 10),
                              "P05": (5, -18), "P06": (-28, -18), "P07": (7, 10), "P08": (7, 10)}[pipeline]
                    ax.annotate(pipeline, (x, y), xytext=offset, textcoords="offset points", color=PIPELINE_COLORS[pipeline], fontsize=10,
                                arrowprops={"arrowstyle": "-", "color": PIPELINE_COLORS[pipeline], "lw": 0.7})
                if key == "processing_seconds":
                    ax.set_xscale("log")
                    lower, upper = ax.get_xlim()
                    ticks = [base * 10**power for power in range(-2, 6) for base in (1, 2, 3, 5)]
                    ax.set_xticks([tick for tick in ticks if lower <= tick <= upper])
                    ax.xaxis.set_major_formatter(ScalarFormatter())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                ax.set_xlabel(xlabel, fontsize=11)
                if column == 0:
                    ax.set_ylabel(ylabel, fontsize=12)
                ax.set_ylim(0, min(1.08, math.ceil((highest + 0.06) * 10) / 10))
                ax.yaxis.set_major_formatter(PercentFormatter(1))
                ax.margins(x=0.2)
                ax.grid(alpha=0.2)
                ax.spines[["top", "right"]].set_visible(False)
        for extension in ("png", "svg", "pdf"):
            metadata = {"CreationDate": None, "ModDate": None} if extension == "pdf" else {"Date": None} if extension == "svg" else None
            fig.savefig(output / ("resource-tradeoffs." + extension), dpi=150, metadata=metadata)
        plt.close(fig)


def render(index_path: Path, output: Path) -> None:
    index, groups = load_complete(index_path)
    output.mkdir(parents=True, exist_ok=True)
    summary = index["summary"]
    baseline = "intermediate" if "P07-intermediate" in summary else "previous"
    lines = ["# MO-Parse 本轮修复结果", "",
             "本轮目标是保留原生已正确的信息，并让最终Markdown明确表达已有业务关系。唯一答案来源是现有expected；所有组使用同一冻结程序。", "",
             "2026-11-02清理已删除错误的旧评分逻辑及其产物；当前成绩由清理后的程序统一重算。以下正文收益仍比较保存的06与08版实际Markdown，本次清理没有新增正文处理。", "",
             "## 原生到最终正文的信息保留", "",
             "| 管线 | 原生正确的全部目标 | 正文仍正确 | 全部目标损失 | 其中业务目标损失 |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for pipeline in ("P07", "P08"):
        row = index["native_preservation"][pipeline]
        lines.append(f"| {pipeline} | {row['native_correct_targets']:,} | {row['preserved_targets']:,} | {row['lost_correct_targets']:,} | {row['lost_correct_business_targets']:,} |")
    passed = all(row["adoptable"] for row in index["adoption"].values())
    lines += ["", f"采用门槛：**{'通过' if passed else '未通过'}**。同时检查原生到正文，以及修改前后正文的正确项保留；标题、正文、单位和图题文字与业务字段共同纳入。", "",
              "## 本次实际正文修改", "",
              "本表比较本轮开始时保存的06版正文与此次08版CPU回放正文。较早04版至08版的累计变化单独保存在完整报告中。", "",
              "| 管线 | 修改前正确业务字段 | 修改后正确业务字段 | 新增正确业务字段 | 新增正确普通文字目标 | 原正确目标损失 |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for pipeline in ("P07", "P08"):
        before = summary[f"{pipeline}-{baseline}"]["by_kind"]["business_field"]
        after = summary[f"{pipeline}-current"]["by_kind"]["business_field"]
        delta = index["incremental_changes" if baseline == "intermediate" else "changes"][pipeline]
        fields = delta["gains_by_kind"].get("business_field", 0)
        lines.append(f"| {pipeline} | {before['correct']:,} | {after['correct']:,} | {fields} | {delta['new_correct'] - fields} | {delta['lost_correct']} |")
    lines += ["", "实际修复包括年龄错误继承股份单位、属性表与纯文本表转换、完整表头及表名保留、期间片段引用。读取器另修复等价格式、币种作用域、业务标签与连续文字漏读；读取修复对全部版本共同生效，不计作正文新增收益。", "",
              "实例见[实际Markdown变化](delivered-markdown-changes.md)，原因和处理位置见[根因与修复](root-cause-resolution.md)。", "",
              "## expected对照范围与剩余错误", ""]
    first = next(iter(summary.values()))
    targets = sum(row["targets"] for row in index["coverage"])
    content = sum(row["content_coverage"]["expected_elements"] for row in index["coverage"])
    omitted = sum(row["content_coverage"]["omitted_elements"] for row in index["coverage"])
    lines += [f"本轮800页、{len(index['coverage'])}个样本、{first['documents']}份文档、{len(first['by_family'])}个家族。每组{targets:,}个目标，其中业务字段{first['by_kind']['business_field']['targets']:,}个；{content:,}个expected内容元素进入对照，遗漏{omitted}。共{len(index['groups'])}组、{len(index['records']):,}份样本评分，每项只有正确或错误。", ""]
    for pipeline in ("P07", "P08"):
        fields = summary[f"{pipeline}-current"]["by_kind"]["business_field"]
        lines.append(f"{pipeline}最终正文仍有{fields['incorrect']:,}个业务字段错误，正确{fields['correct']:,}/{fields['targets']:,}。")
        lines.append("")
    lines += ["剩余错误的expected位置、候选文件、具体原因与证据入口见[逐项清单](remaining-errors.json)。原生输出中已存在的错误继续保留在分母中。八组原生输出的横向比较单列在[完整报告](report.md)，与P07/P08正文优化分别展示。", "",
              "## 执行与复现", ""]
    for pipeline in ("P07", "P08"):
        costs = index["execution_costs"]["final"][f"{pipeline}-current"]
        quality = costs["quality800"]["rounds"][0]["postprocessing_seconds"]
        repetitions = ", ".join(f"{row['postprocessing_seconds']:.3f}" for row in costs["perf80"]["rounds"])
        lines.append(f"{pipeline}完成800页CPU回放，耗时{quality:.3f}秒；固定80页三轮为{repetitions}秒，预热单列。")
        lines.append("")
    lines += ["原生历史处理时间与CPU后处理分别保存；原生测量中的TTS共驻及不受控负载按实际记录披露。本轮未新增模型推理，未操作GPU、TTS或服务，未部署。", "",
              "[复现说明](reproduce.md)给出统一评分及报告生成命令；[覆盖记录](coverage.json)、[采用门槛](adoption.json)及完整逐项评分保留可追溯证据。Lite已经用于开发，文档与家族暴露记录保留。", "",
              f"评分读取修订：`{index['protocol']['reader_revision']}`；软件：`{index['software']['software_id']}`。", ""]
    (output / "summary.md").write_text("\n".join(lines))
    sources = []
    errors = []
    stages: Counter[str] = Counter()
    paths = {(row["group"], row["sample_id"]): row["path"] for row in index["records"]}
    for pipeline in ("P07", "P08"):
        native = {(score["sample_id"], row["id"]): row
                  for score in groups[pipeline] for row in score["outcomes"]}
        for score in groups[f"{pipeline}-current"]:
            source_ids: dict[str, int] = {}
            for row in score["outcomes"]:
                if row["outcome"] == "correct":
                    continue
                expected_file = row["reference"]["path"]
                if expected_file not in source_ids:
                    source_ids[expected_file] = len(sources)
                    sources.append({"pipeline": pipeline, "sample_id": score["sample_id"],
                        "expected_file": expected_file, "candidate_file": score["candidate_source"],
                        "full_evidence": str((index_path.parent / paths[f"{pipeline}-current", score["sample_id"]]).resolve())})
                stage = first_failure_stage(f"{pipeline}-current", row, native[score["sample_id"], row["id"]])
                stages[stage] += 1
                errors.append([source_ids[expected_file], row["id"], row["kind"], row["reason"], stage,
                               row["reference"]["lines"], (row.get("candidate") or {}).get("native_path")])
    write_json(output / "remaining-errors.json", {"schema": "moparse-error-evidence-index/1",
        "scope": "current_P07_P08_all_incorrect_content_targets_with_complete_evidence_pointers",
        "columns": ["source", "target", "kind", "reason", "first_failure_stage", "expected_lines", "candidate_position"],
        "sources": sources, "errors": errors, "by_stage": dict(stages),
        "lookup": "Each row references sources[source]; locate target in that source's full_evidence outcomes."})
    write_json(output / "presentation.json", {"score_index": str(index_path.resolve()),
        "scoring_software_id": index["software"]["software_id"], "adoptable": passed,
        "generator": "scripts/render_preservation_summary.py",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "presentation_from_completed_uniform_scores_and_recorded_resources_no_regrading",
        "resource_evidence": "resource-costs.json",
        "comparison_details": {"previous_to_current": "private/paired-changes.json",
                               "before_to_current": "private/incremental-changes.json",
                               "native_to_current": "private/native-preservation.json"}})
    coverage = {
        "samples": len(index["coverage"]),
        "pages": sum(len({page for scope in row["scope"] for page in scope["pages"]})
                     for row in index["coverage"]),
        "documents": first["documents"], "families": len(first["by_family"]),
        "expected_content_elements": content, "compared_elements": content - omitted,
        "omitted_elements": omitted, "targets_per_group": targets,
        "business_targets_per_group": first["by_kind"]["business_field"]["targets"],
        "groups": len(index["groups"]), "sample_evaluations": len(index["records"]),
    }
    preservation = index["native_preservation"]
    write_json(output / "native-preservation-summary.json", preservation)
    write_json(output / "conversion-errors.json", {
        pipeline: [row for row in errors if sources[row[0]]["pipeline"] == pipeline
                   and row[4] == "final_markdown_conversion"]
        for pipeline in ("P07", "P08")})
    status = {"state": "completed_and_adoptable" if passed else "completed_not_adoptable",
              "software_id": index["software"]["software_id"], "reader": index["protocol"]["reader_revision"],
              "expected_comparison_complete": True, "coverage": coverage,
              "native_preservation": preservation, "adoption": index["adoption"],
              "completion": "completion.json", "remaining_errors": "remaining-errors.json",
              "deployment": "not_deployed"}
    write_json(output / "current-validation-status.json", status)
    write_json(output / "completion.json", {
        "state": "complete" if passed else "not_adoptable",
        "objective": "expected_only_common_scoring_and_native_to_final_information_preservation",
        "software": index["software"], "score_index": str(index_path.resolve()),
        "coverage": coverage, "adoption": index["adoption"], "native_preservation": preservation,
        "changes": index["changes"], "incremental_changes": index["incremental_changes"],
        "remaining_business_errors": {
            pipeline: summary[f"{pipeline}-current"]["by_kind"]["business_field"]["incorrect"]
            for pipeline in ("P07", "P08")},
        "cleanup": "legacy scoring logic and its products deleted without archival; valid outputs retained",
        "processing": "saved native and actual Markdown reused; original processing costs retained",
        "model_inference_calls": 0, "deployment": "not_deployed"})

    def compact_costs(value):
        if isinstance(value, dict):
            return {key: compact_costs(item) for key, item in value.items() if key != "resource_observations"}
        if isinstance(value, list):
            return [compact_costs(item) for item in value]
        return value

    write_json(output / "execution-cost-summary.json", compact_costs(index["execution_costs"]))
    resources = render_resource_comparison(index, output)
    report = output / "report.md"
    if not report.is_file():
        from moparse_eval.expected_report import render_expected_report

        render_expected_report(index_path, output=output)
    base = report.read_text().split(RESOURCE_MARKER, 1)[0].rstrip()
    if f"软件：`{index['software']['software_id']}`" not in base:
        raise ValueError("base report must be regenerated from the same frozen scoring index")
    report.write_text(base + "\n\n" + RESOURCE_MARKER + "\n\n" + resources)
    summary_path = output / "summary.md"
    summary_path.write_text(summary_path.read_text() + "\n资源成本必须同时查看内存和显存，不能仅按耗时宣布配置被全面支配。见[资源成本与采样覆盖](resource-costs.md)。\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.index, args.output)
