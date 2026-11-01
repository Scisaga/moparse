"""Reproduce expected-only reports from complete programmatic score outputs."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .expected_evaluation import (
    PIPELINES,
    adoption_status,
    native_preservation,
    paired_changes,
    summarize,
)
from .expected_scoring import PROTOCOL, require_paired_targets
from .packaging import inside, read_json, write_json


def first_failure_stage(group: str, outcome: dict[str, Any], native: dict[str, Any] | None) -> str:
    """Report the first observed failing output, without inventing an SDK cause."""
    if outcome["outcome"] == "correct":
        return "none"
    if group in PIPELINES:
        return "native_output"
    if native is None:
        raise ValueError("final-output error attribution requires the paired native target")
    return "native_output" if native["outcome"] == "incorrect" else "final_markdown_conversion"


def load_complete(index_path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    index = read_json(index_path)
    if (index.get("state") != "completed" or index.get("expected_comparison_complete") is not True
            or index.get("protocol", {}).get("id") != PROTOCOL["id"]):
        raise ValueError("a complete expected-only evaluation is required before report publication")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen = set()
    for record in index["records"]:
        score = read_json(inside(index_path.parent, record["path"]))
        key = record["group"], record["sample_id"]
        if key in seen or score.get("sample_id") != record["sample_id"]:
            raise ValueError("duplicate or mismatched evaluated sample")
        seen.add(key)
        if score.get("protocol") != index["protocol"]:
            raise ValueError("mixed scoring protocols cannot be published")
        if score.get("scoring_software_id") != index["software"]["software_id"]:
            raise ValueError("mixed scoring software cannot be published")
        groups[record["group"]].append(score)
        samples[record["sample_id"]].append(score)
    if set(groups) != set(index["groups"]):
        raise ValueError("a declared comparison group is missing")
    if set(samples) != {row["sample_id"] for row in index["coverage"]}:
        raise ValueError("declared expected coverage and evaluated samples differ")
    for scores in samples.values():
        if len(scores) != len(groups):
            raise ValueError("all groups must cover every declared sample")
        require_paired_targets(scores)
    for coverage in index["coverage"]:
        for score in samples[coverage["sample_id"]]:
            if (score["targets"] != coverage["targets"] or score.get("content_coverage", {}).get("omitted_elements") != 0
                    or score["content_coverage"]["compared_elements"] != score["content_coverage"]["expected_elements"]):
                raise ValueError("expected content comparison is incomplete")
    for group, scores in groups.items():
        if summarize(scores) != index["summary"][group]:
            raise ValueError("aggregate differs from the actual target decisions")
    preservation = {p: native_preservation(groups[p], groups[f"{p}-current"])
                    for p in ("P07", "P08") if f"{p}-current" in groups}
    changes = {p: paired_changes(groups[f"{p}-previous"], groups[f"{p}-current"])
               for p in preservation if f"{p}-previous" in groups}
    incremental = {p: paired_changes(groups[f"{p}-intermediate"], groups[f"{p}-current"])
                   for p in preservation if f"{p}-intermediate" in groups}
    if index.get("adoption", {}) != adoption_status(changes, incremental, preservation):
        raise ValueError("adoption gates differ from the actual native and final decisions")
    return index, dict(groups)


def _cost_lines(index: dict[str, Any]) -> list[str]:
    costs = index.get("execution_costs", {})
    lines = ["## 处理成本与环境", "",
             "原生历史处理时间与CPU后处理回放分别列出；未测量值保留缺失，不估算新的端到端时间。预热和初始化保存在execution-costs.json中，不进入正式轮次。", "",
             "| 管线/版本 | quality800秒 | perf80第1轮秒 | 第2轮秒 | 第3轮秒 |", "| --- | ---: | ---: | ---: | ---: |"]

    def display(value):
        return f"{value:.3f}" if type(value) in {int, float} else "缺失"

    for group, data in costs.get("native", {}).items():
        quality = data["quality800"].get("rounds", [])
        perf = data["perf80"].get("rounds", [])
        q = quality[0].get("processing_seconds_including_failures") if len(quality) == 1 else None
        rounds = {str(r["repetition"]): r.get("processing_seconds_including_failures") for r in perf}
        lines.append(f"| {group}原生 | {display(q)} | " + " | ".join(display(rounds.get(str(i))) for i in (1, 2, 3)) + " |")
    for group, data in costs.get("final", {}).items():
        quality = data["quality800"]["rounds"]
        q = quality[0].get("postprocessing_seconds") if len(quality) == 1 else None
        rounds = {str(r["repetition"]): r.get("postprocessing_seconds") for r in data["perf80"]["rounds"]}
        lines.append(f"| {group}正文 | {display(q)} | " + " | ".join(display(rounds.get(str(i))) for i in (1, 2, 3)) + " |")
    conditions = costs.get("historical_native_conditions") or {}
    tts = conditions.get("evidence", {}).get("tts_no_calls_condition", {})
    lines += ["", f"历史原生运行的TTS观察状态：`{tts.get('status', '未记录')}`；起止计数记录的新增任务：{tts.get('observed_new_jobs', '未记录')}。TTS驻留且工作负载不受控，短调用可能漏观测；不能称为独占或TTS空闲环境。实际条件和观察范围随原执行记录保存。", "",
              "正文回放的CPU、内存、网络、GPU设备及软件身份逐版本保存在execution-costs.json；候选环境不提供expected，不调用模型。本轮未部署或操作运行服务。", ""]
    return lines


def _charts(summary: dict[str, Any], output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    from .report_figures import PIPELINE_COLORS, _register_cjk_fonts

    _register_cjk_fonts(output)
    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"],
                         "font.sans-serif": ["DejaVu Sans", "Noto Sans CJK SC"],
                         "mathtext.fontset": "dejavusans", "text.usetex": False,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
                         "svg.hashsalt": "mo-parse-expected-only-v1"}):
        labels = [p for p in PIPELINES if p in summary]
        if len(labels) != len(PIPELINES):
            return
        counts = [summary[p]["by_kind"].get("business_field", {}) for p in labels]
        values = [c.get("correct", 0) / c["targets"] if c.get("targets") else 0 for c in counts]
        fig, ax = plt.subplots(figsize=(9, 5.2), layout="constrained")
        ax.barh(labels, values, color=[PIPELINE_COLORS[p] for p in labels])
        ax.invert_yaxis()
        ax.set(xlim=(0, 1.12), title="Expected business information: native outputs")
        ax.xaxis.set_major_formatter(PercentFormatter(1))
        for i, (value, count) in enumerate(zip(values, counts, strict=True)):
            ax.text(value + 0.012, i, f"{value:.2%}  ({count.get('correct', 0):,}/{count.get('targets', 0):,})", va="center", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        for extension in ("png", "svg", "pdf"):
            metadata = {"CreationDate": None, "ModDate": None} if extension == "pdf" else {"Date": None} if extension == "svg" else None
            fig.savefig(output / ("native-business." + extension), dpi=160, metadata=metadata)
        plt.close(fig)


def render_expected_report(index_path: Path, *, figures: bool = True, output: Path | None = None) -> Path:
    index, groups = load_complete(index_path)
    output = output or index_path.parent
    output.mkdir(parents=True, exist_ok=True)
    summary = {key: summarize(scores) for key, scores in groups.items()}
    lines = ["# MO-Parse expected统一程序评测", "",
             "本报告以现有expected为唯一验收标准，所有结果由同一冻结评分程序生成。八组原生输出横向比较，P07/P08最终正文按修改前后配对比较。", "",
             f"评分协议：`{index['protocol']['id']}`；软件：`{index['software']['software_id']}`。质量范围为保存的quality800运行；性能重复不增加独立质量样本。", "",
             "## 八组原生输出", "", "| 管线 | 业务字段正确 | 业务字段错误 | 固定目标 |", "| --- | ---: | ---: | ---: |"]
    for pipeline in PIPELINES:
        if pipeline in summary:
            fields = summary[pipeline]["by_kind"].get("business_field", {})
            lines.append(f"| {pipeline} | {fields.get('correct', 0):,} | {fields.get('incorrect', 0):,} | {fields.get('targets', 0):,} |")
    lines += ["", "标题、正文、列表、单位及图题文字分别统计，不与业务字段混合成加权总分。完整分项见summary.json，逐项证据见private/target-details.csv和评分JSON。", ""]
    kinds = sorted({kind for p in PIPELINES if p in summary for kind in summary[p]["by_kind"] if kind != "business_field"})
    lines += ["| 管线 | " + " | ".join(kinds) + " |", "| --- | " + " | ".join("---:" for _ in kinds) + " |"] if kinds else []
    for pipeline in PIPELINES:
        if pipeline in summary and kinds:
            cells = [summary[pipeline]["by_kind"].get(kind, {}) for kind in kinds]
            lines.append(f"| {pipeline} | " + " | ".join(f"{c.get('correct', 0):,}/{c.get('targets', 0):,}" for c in cells) + " |")
    lines.append("")
    if figures:
        _charts(summary, output)
        if all(p in groups for p in PIPELINES):
            lines += ["![八组原生业务信息](native-business.svg)", ""]
    changes = {}
    lines += ["## P07/P08实际正文变化", "", "| 管线 | 新增正确 | 原正确项损失 | 新增正确业务字段 | 丢失正确业务字段 | 数值字面新增一致 | 字面退化 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for pipeline in ("P07", "P08"):
        old, new = f"{pipeline}-previous", f"{pipeline}-current"
        if old in groups and new in groups:
            delta = paired_changes(groups[old], groups[new])
            changes[pipeline] = delta
            gain_fields = sum(x["kind"] == "business_field" for x in delta["gains"])
            loss_fields = sum(x["kind"] == "business_field" for x in delta["losses"])
            lines.append(f"| {pipeline} | {delta['new_correct']:,} | {delta['lost_correct']:,} | {gain_fields:,} | {loss_fields:,} | {delta['raw_literal_new_exact']:,} | {delta['raw_literal_lost_exact']:,} |")
    lines += ["", "以上变化来自实际保存的最终Markdown，内部IR和未打印关系不能补分。数值字面诊断单独比较实际打印的值，不增加业务分母或覆盖业务错误。评分器读取修复本身不算正文改善；原生与最终正文的结果分别保留。", "",
              "## 原生正确信息保留门槛", "",
              "| 管线 | 原生正确业务目标 | 正文仍正确 | 正文丢失 | 门槛通过 |",
              "| --- | ---: | ---: | ---: | --- |"]
    preservation = {p: native_preservation(groups[p], groups[f"{p}-current"])
                    for p in ("P07", "P08") if f"{p}-current" in groups}
    for pipeline, row in preservation.items():
        lines.append(f"| {pipeline} | {row['native_correct_business_targets']:,} | {row['preserved']:,} | {row['lost_correct_business_targets']:,} | {'是' if row['passed'] else '否'} |")
    lines += ["", "这项门槛直接比较原生输出与当前实际Markdown；旧正文到新正文没有新增退化，不能代替原生信息保留。逐项差异见private/native-preservation.json。", "",
              "## expected覆盖与具体错误", "",
              f"共同程序已对本轮{len(index['coverage']):,}个样本的声明expected范围完成比较；每项只有正确或错误。覆盖记录位于coverage.json，内容位置和候选证据保存在逐项结果中。", "",
              "错误按缺失、数值、单位、期间、业务归属、附注及冲突分别保留，不通过历史原图裁定或旧标注状态退出分母。普通正文按完整文本比较，字符差异与业务字段关系分开报告。逐项错误及其最早出现的输出阶段见private/target-details.csv和failure-stages.json：原生已错记为native_output，原生正确而正文错误记为final_markdown_conversion；该归因不冒充识别、适配或渲染内部根因诊断。", "",
              "## 执行与采用", "",
              "本次评分复用保存输出，不产生新的模型推理或解析耗时。各版本执行软件与候选路径保存在评分产物；后处理成本单列，不与原生历史时间相加。", "",
              "程序对照完成不等于所有输出正确。P07/P08仍有错误的条目继续进入正文缺陷清单；有原正确项损失的修改不能据净增益采用。图片语义不在本轮范围。", ""]
    incremental = {}
    if any(f"{p}-intermediate" in groups for p in ("P07", "P08")):
        lines += ["## 本次代码修改的单独效果", "",
                  "上表保留最早版本至最终版本的完整变化；本表只比较本次修改开始时的已保存正文与此次CPU回放正文，两侧仍用同一冻结程序重新评分。", "",
                  "| 管线 | 新增正确 | 原正确项损失 | 数值字面新增一致 | 字面退化 |", "| --- | ---: | ---: | ---: | ---: |"]
        for pipeline in ("P07", "P08"):
            old, new = f"{pipeline}-intermediate", f"{pipeline}-current"
            if old in groups and new in groups:
                delta = paired_changes(groups[old], groups[new])
                incremental[pipeline] = delta
                lines.append(f"| {pipeline} | {delta['new_correct']:,} | {delta['lost_correct']:,} | {delta['raw_literal_new_exact']:,} | {delta['raw_literal_lost_exact']:,} |")
        lines.append("")
    lines += _cost_lines(index)
    lines += ["## 正文版本与资产交付", "", "| 评分组 | 保存正文的运行目录 | 执行软件 |", "| --- | --- | --- |"]
    for group, data in index.get("execution_costs", {}).get("final", {}).items():
        lines.append(f"| {group} | `{data.get('run', '未记录')}` | `{data['software_id']}` |")
    lines += ["", "Markdown图片alt文字仅作字面对照，单列为image_alt_text；图题正文和正文引用仍属于文字目标。资产文件及引用交付另按候选自己的文件和清单记录，不据alt、文件存在或数量声称图像内容理解。", "",
              "| 评分组 | 声明资产文件 | 已保存文件 | Markdown图片引用 | 引用有文件 | 引用缺文件 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for group, data in summary.items():
        delivery = data["asset_delivery"]
        lines.append(f"| {group} | " + " | ".join(str(delivery[k]) for k in (
            "declared_files", "files_present", "image_references", "references_with_file", "references_without_file")) + " |")
    lines.append("")
    first = summary[next(iter(summary))]
    lines += ["## 文档范围与开发暴露", "",
              f"本轮涉及{first['documents']:,}份文档、{len(first.get('by_family', {})):,}个文档家族；逐文档与家族成绩位于summary.json。", "",
              "本轮Lite输出及expected语法已用于读取器和正文转换开发，不能宣称独立测试集成绩。已有样本暴露声明分别保留；性能重复不增加独立文档数。", ""]
    (output / "private").mkdir(exist_ok=True)
    native_targets = {(group, score["sample_id"], row["id"]): row
                      for group, scores in groups.items() if group in PIPELINES
                      for score in scores for row in score["outcomes"]}
    stages: dict[str, Counter] = defaultdict(Counter)
    with (output / "private/target-details.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["group", "sample_id", "target_id", "kind", "outcome", "reason", "first_failure_stage", "reference", "details"])
        writer.writeheader()
        for group, scores in groups.items():
            for score in scores:
                for row in score["outcomes"]:
                    stage = first_failure_stage(group, row, native_targets.get((group.split("-", 1)[0], score["sample_id"], row["id"])))
                    if row["outcome"] == "incorrect":
                        stages[group][stage] += 1
                    writer.writerow({"group": group, "sample_id": score["sample_id"], "target_id": row["id"],
                                     "kind": row["kind"], "outcome": row["outcome"], "reason": row["reason"],
                                     "first_failure_stage": stage,
                                     "reference": json.dumps(row["reference"], ensure_ascii=False),
                                     "details": json.dumps(row, ensure_ascii=False)})
    write_json(output / "summary.json", {"protocol": index["protocol"], "software": index["software"], "groups": summary})
    write_json(output / "evaluation.json", {"score_index": str(index_path.resolve()), "protocol": index["protocol"],
                                            "software_id": index["software"]["software_id"],
                                            "expected_comparison_complete": True})
    write_json(output / "coverage.json", index["coverage"])
    write_json(output / "failure-stages.json", dict(stages))
    write_json(output / "execution-costs.json", index.get("execution_costs", {}))
    write_json(output / "private/paired-changes.json", changes)
    write_json(output / "private/incremental-changes.json", incremental)
    write_json(output / "private/native-preservation.json", preservation)
    write_json(output / "adoption.json", index.get("adoption", {}))
    report = output / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
