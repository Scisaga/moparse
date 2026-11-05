"""Render the sole Lite report only from complete validated three-layer results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moparse_eval.expected_report import (  # noqa: E402
    PIPELINES,
    load_complete,
    text_layer_diagnostics,
)
from moparse_eval.layer_aggregation import LAYERS  # noqa: E402
from moparse_eval.packaging import read_json, write_json  # noqa: E402


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
            "tts_memory_observed_samples": len(tts), "whole_gpu_observed_samples": len(whole),
            "container_names": sorted(names_seen),
            "sample_span_seconds": stamps[-1] - stamps[0] if len(stamps) > 1 else None,
            "median_gap_seconds": statistics.median(gaps) if gaps else None,
            "maximum_gap_seconds": max(gaps, default=None),
            "scope": "whole recorded protocol including initialization, warmup, quality800 and perf80; sampled peaks"}


def collect_resource_comparison(index: dict[str, Any]) -> dict[str, Any]:
    root = Path(index['baseline'])
    native, final = {}, {}
    for pipeline in PIPELINES:
        native[pipeline] = {}
        for role, relative in [('worker', 'worker-resources.json'), ('inference', 'inference/resources.json')]:
            path = root / 'artifacts' / pipeline / relative
            record = summarize_resource_samples(read_json(path) if path.is_file() else {})
            record['source_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            native[pipeline][role] = {**record, 'source': str(path)}
    for group, entry in index.get('execution_costs', {}).get('final', {}).items():
        run = read_json(Path(entry['run']) / 'run.json')
        cases = [case for case in run['cases'] if case['phase'] == 'measured' and case['suite'] == 'quality800']
        values = [finite_nonnegative(case.get('resources', {}).get('peak_rss_bytes')) for case in cases]
        measured = [value for value in values if value is not None]
        final[group] = {'quality800_peak_process_rss_bytes': max(measured, default=None),
                        'measured_samples': len(cases), 'memory_samples_available': len(measured),
                        'scope': 'quality800 CPU process RSS sampled within each saved case',
                        'environment': run.get('execution_environment')}
    return {'native': native, 'final_cpu': final,
            'policy': 'native whole protocol sampled peaks; inference-owned GPU only; worker GPU attribution missing, not zero; independent peaks never summed; TTS/whole GPU context only'}


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _number(value: Any) -> str:
    return f"{value:.3f}" if type(value) in {int, float} and math.isfinite(value) else "N/A"


def _summary_row(group: str, summary: dict[str, Any]) -> str:
    values = [group]
    for layer in LAYERS:
        row = summary["layers"][layer]
        values.append(f"{_number(row['score'])} ({row['numerator']}/{row['denominator']})")
    values.append(_number(summary["score"]))
    return "| " + " | ".join(values) + " |"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def _literal(item: Any) -> str:
    if item is None:
        return "[no located evidence]"
    if isinstance(item, list):
        return "\n".join(_literal(part) for part in item)
    if isinstance(item, dict):
        for key in ("text", "value"):
            if isinstance(item.get(key), str):
                return item[key]
        return json.dumps({key: item[key] for key in ("type", "left", "right") if key in item}, ensure_ascii=False)
    return str(item)


def render(index_path: Path, output: Path) -> list[str]:
    # Validate before creating output directories or touching an existing
    # maintained report. A diagnostic index cannot publish partial grades.
    index, groups = load_complete(index_path)
    required = set(PIPELINES) | {f"{p}-current" for p in PIPELINES} | {"P07-baseline", "P08-baseline"}
    if set(groups) != required:
        raise ValueError("the Lite report requires eight native, eight delivered and two genuine historical baseline groups")
    summary = index["summary"]
    pairs = {}
    for pipeline, comparisons in index["paired"].items():
        pairs[pipeline] = {}
        for comparison, layers in comparisons.items():
            before = pipeline + "-baseline" if comparison == "baseline_to_current" else pipeline
            after = pipeline + ("-baseline" if comparison == "native_to_baseline" else "-current")
            pairs[pipeline][comparison] = {"layers": {layer: {
                "new_correct": row["new_correct"], "lost_correct": row["lost_correct"],
                "remaining_defects": row["remaining_incorrect"],
                "before": summary[before]["layers"][layer], "after": summary[after]["layers"][layer]}
                for layer, row in layers.items()}}
    output.mkdir(parents=True, exist_ok=True)
    data = output / "data"
    data.mkdir(exist_ok=True)
    write_json(data / "results.json", summary)
    text_diagnostics = {group: text_layer_diagnostics(scores) for group, scores in groups.items()}
    write_json(data / "text-diagnostics.json", text_diagnostics)
    write_json(data / "coverage.json", index["coverage"])
    write_json(data / "provenance.json", {key: index.get(key) for key in ("protocol", "software", "validation", "analysis_workers", "development_exposure")})
    write_json(data / "execution.json", index.get("execution_costs", {}))
    write_json(data / "paired.json", {
        pipeline: {comparison: {
            "layers": {layer: {key: row[key] for key in ("new_correct", "lost_correct", "remaining_defects", "before", "after")}
                       for layer, row in pair["layers"].items()},
            "details": str(index_path.parent / "private/pairs.json"),
        } for comparison, pair in comparisons.items()}
        for pipeline, comparisons in pairs.items()
    })
    resource = collect_resource_comparison(index) if index.get("baseline") else {"policy": "no original resource records declared"}
    write_json(data / "resources.json", resource)
    rows = []
    errors = []
    business_examples = []
    score_paths = {(record["group"], record["sample_id"]): record["path"] for record in index["records"]}
    for group, scores in groups.items():
        for score in scores:
            rows.append({"group": group, "sample_id": score["sample_id"], "document_id": score.get("document_id"),
                         "family_id": score.get("family_id"),
                         **{key: score["layers"][key]["score"] for key in LAYERS}, "quality_score": score["score"],
                         **{key + "_denominator": score["layers"][key]["denominator"] for key in LAYERS}})
            for row in score["outcomes"]:
                if row["outcome"] == "incorrect":
                    errors.append({"group": group, "sample_id": score["sample_id"], "layer": row["layer"],
                                   "target": row["id"], "root_cause": row.get("root_cause"),
                                   "score_path": score_paths[group, score["sample_id"]], "outcome_id": row["id"]})
                    if row["layer"] == "B" and len(business_examples) < 8:
                        business_examples.append({**errors[-1], "expected_literal": _literal(row["expected"]),
                            "actual_literal": _literal(row.get("actual")), "source": row["expected"].get("source")})
            if score["outcomes"]:
                del row
            del score
    _write_csv(data / "samples.csv", rows)
    # Evidence stays at the original scoring paths rather than copying entire
    # references or large candidates into a Git-visible report directory.
    write_json(data / "errors.json", errors)
    report = ["# MO-Parse Lite 三层统一评测", "",
        "T比较全部授权文字相对expected的一致性，按完整文字字符分母和S/D/I计分。业务字段中的标签和值继续参加T，文字出现按容量一对应；额外未确定可比较范围的文字单列诊断。该结果不是原PDF逐字OCR精度。", "",
        "L比较expected明确要求的顺序、归属、绑定和限定作用范围，每条逻辑关系一票；B比较按统一角色固定的重要实体、指标和逻辑要求，每条完整要求一票，单位、期间、条件及否定作为限定。三层分别汇总，质量总分固定为(T+L+B)/3，时间与资源不进入质量分。", "",
        "本报告只消费完成独立验证和真实格式诊断的同版程序结果。软件无法判断的表达会阻止发布，不能记作候选零分。某样本无某层要求时该层及样本总分为N/A；全局各层分母独立汇总。完整规则见[评测任务](../../evaluation-tasks.md#three-layer-evaluation)。", "",
        "## P01–P08 原生输出", "",
        "| 原生组 | T分数 (分子/字符分母) | L分数 (正确/关系) | B分数 (正确/要求) | 三层总分 |",
        "| --- | ---: | ---: | ---: | ---: |"]
    report.extend(_summary_row(pipeline, summary[pipeline]) for pipeline in PIPELINES)
    report.extend(["", "| 原生组 | 文字单元定位 | 字符定位 | 全范围S/D/I | 严格S/D/I | 额外未判定单元 |",
                   "| --- | ---: | ---: | --- | --- | ---: |"])
    for pipeline in PIPELINES:
        row = text_diagnostics[pipeline]
        edits = "/".join(str(row["edits"].get(key, 0)) for key in ("S", "D", "I"))
        strict = "/".join(str(row["strict_edits"].get(key, 0)) for key in ("S", "D", "I"))
        report.append(f"| {pipeline} | {row['located_units']}/{row['required_units']} | {row['located_characters']}/{row['required_characters']} | {edits} | {strict} | {row['unadjudicated_extra_units']} |")
    report.extend(["", "## 八组最终交付与原生增损", "",
        "每组最终正文只与自己的同源原生结果配对；真实处理阶段和修改账本负责归因。评分器补读收益不计交付改善，缺失历史阶段保持不可归因。", "",
        "| 组别 | T分数 (分子/字符分母) | L分数 (正确/关系) | B分数 (正确/要求) | 三层总分 |",
        "| --- | ---: | ---: | ---: | ---: |"])
    report.extend(_summary_row(pipeline + "-current", summary[pipeline + "-current"]) for pipeline in PIPELINES)
    report.extend(["", "## P07/P08 保存正文配对", "",
        "P07/P08另保留唯一真实baseline/current配对。P01-P06没有历史baseline，不虚构前后版本，也不与八组原生横向混排。", "",
        "| 组别 | T分数 (分子/字符分母) | L分数 (正确/关系) | B分数 (正确/要求) | 三层总分 |",
        "| --- | ---: | ---: | ---: | ---: |"])
    for pipeline in ("P07", "P08"):
        for group in (pipeline, pipeline + "-baseline", pipeline + "-current"):
            report.append(_summary_row(group, summary[group]))
    report.extend(["", "| 管线 | 比较 | 层 | 新增正确文字单元或要求 | 原正确损失 | 剩余错误 |", "| --- | --- | --- | ---: | ---: | ---: |"])
    for pipeline, comparisons in pairs.items():
        for comparison, pair in comparisons.items():
            for layer in LAYERS:
                row = pair["layers"][layer]
                report.append(f"| {pipeline} | {comparison} | {layer} | {row['new_correct']} | {row['lost_correct']} | {row['remaining_defects']} |")
    report.extend(["", "T配对单元的二元变化仅说明完整文字单元是否完全正确，不能代替T字符主分变化。同一根因影响多层时，逐项证据保留共同根因，不能称为多个独立识别错误。完整配对证据见[配对数据](data/paired.json)。", "",
        "## 关键业务差异与原文", "",
        "以下片段来自程序已经比较的实际expected及候选文字，附原始来源；它们用于说明观察到的差异，不提供人工改分，也不推断解析器内部原因。"])
    if not business_examples:
        report.extend(["", "本次已覆盖的重要业务要求没有程序判错项；该结论限于声明范围和验证支持的表达。"])
    for row in business_examples:
        report.extend(["", f"**{_cell(row['group'])} / {_cell(row['sample_id'])} / {_cell(row['target'])}**", "",
            f"expected来源：`{_cell(row['source'])}`。共同根因：`{_cell(row['root_cause'])}`。", "",
            "```text", row["expected_literal"], "```", "", "实际候选：", "", "```text", row["actual_literal"], "```"])
    report.extend(["", "质量总分较高不等于关键业务要求通过。完整错误索引见[错误数据](data/errors.json)，逐项原文与检索证据仍位于本地评分记录。", "",
        "## 原始成本、覆盖与限制", "",
        "处理时长及资源观测保持原执行记录，初始化、预热、质量执行、三轮性能重复和CPU后处理分别展示于[执行数据](data/execution.json)。评分时间不计入解析成本，也不将原生与后处理时长相加伪造端到端时间。", "",
        "TTS共驻且负载不受控，资源采样峰值可能漏掉短峰；各组件独立峰值不相加，归属缺失保持缺测，不用预算推算实际使用量。原始采样覆盖及环境见[资源数据](data/resources.json)。", "",
        "声明expected范围及三层分母见[覆盖数据](data/coverage.json)，各样本适用层和文档家族见[样本表](data/samples.csv)。Lite expected语法和保存输出已经用于开发，不能称为独立未见集。原生格式证据见[管线说明](../../../docs/pipelines/README.md)，验证范围及软件身份见[溯源数据](data/provenance.json)。", "",
        "本轮没有PDF或候选图片检查、OCR、模型或裁判推理、GPU/TTS/在线服务操作和部署。评测不复核、认证或改写语料。报告复现及算术一致性不能单独证明测量方法有效。"])
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    appendix = ["# 三层评测复现", "", "评分标准由[评测任务](../../evaluation-tasks.md#three-layer-evaluation)统一维护。报告入口先复核每层实际判定、完整范围的字符编辑、一次出现容量、关系端点、业务身份检索、固定软件身份、各组同一要求与层分母，再重新汇总。任何软件阻塞均拒绝覆盖现有报告。", "", "```bash",
                f".venv/bin/python scripts/render_lite_report.py --index {index_path} --output benchmark/reports/lite", "```", "",
                "这一复核只证明报告与已经验证的测量记录一致，不是独立语义验收。来源材料保持只读；大型候选和完整评分逐项材料继续保存在benchmark/runs/lite。"]
    (output / "appendix.md").write_text("\n".join(appendix) + "\n", encoding="utf-8")
    return [str(output / "report.md")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("benchmark/reports/lite"))
    args = parser.parse_args()
    for path in render(args.index, args.output):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
