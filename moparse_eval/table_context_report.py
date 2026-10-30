"""Reproduce three-way comparisons from frozen scores and run metadata only."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from .packaging import inside, read_json, write_json
from .reporting import _quality
from .scoring import require_complete_target_grading
from .service_report import _paired_units, _performance, _scope_signature

VERSION = "table-information-context-2"


def _summary(scores: list[dict[str, Any]]) -> dict[str, Any]:
    return _quality(scores, "quality800")


def _transitions(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [p for p in pairs if p["field_index"] is not None]
    transitions: Counter[str] = Counter()
    gains, losses, introduced_errors = [], [], []
    for pair in fields:
        before, after = pair.get("baseline") or {}, pair.get("final") or {}
        if before.get("status") == after.get("status") == "not_scored":
            continue
        a = before.get("information", {}).get("status")
        b = after.get("information", {}).get("status")
        if a not in {"correct", "incorrect"} or b not in {"correct", "incorrect"}:
            raise ValueError("target grading incomplete: paired targets require correct/incorrect outcomes")
        transitions[f"{a}->{b}"] += 1
        if a != "correct" and b == "correct":
            gains.append(pair)
        if a == "correct" and b != "correct":
            losses.append(pair)
        if a != "incorrect" and b == "incorrect":
            introduced_errors.append(pair)
    return {"field_state_transitions": dict(transitions), "new_correct": len(gains),
            "lost_correct": len(losses), "new_incorrect": len(introduced_errors),
            "attribute_losses": {key: [pair for pair in fields
                if pair.get("changes", {}).get(key + "_target_success", {}).get("transition") == "loss"]
                for key in ("field", "unit", "period", "note_markers")},
            "gains": gains, "losses": losses, "introduced_errors": introduced_errors}


def compare_run(run: Path) -> dict[str, Any]:
    record = read_json(run / "run.json")
    index = read_json(inside(run, record["latest_scores"]))
    if index["software"]["software_id"] != record["scoring_software_id"]:
        raise ValueError("comparison score identity differs from the declared freeze")
    sides: dict[str, list[dict[str, Any]]] = {"native": [], "previous": [], "final": []}
    comparisons: dict[str, list[dict[str, Any]]] = {
        "native_to_previous": [], "previous_to_final": [], "native_to_final": [],
    }
    for entry in index["results"]:
        case = next(c for c in record["cases"] if c["case_id"] == entry["case_id"])
        scored = {side: read_json(inside(run, entry[key])) for side, key in (
            ("native", "baseline_score"), ("previous", "previous_score"), ("final", "final_score"))}
        for candidate_score in scored.values():
            require_complete_target_grading(candidate_score)
        signatures = [_scope_signature(score) for score in scored.values()]
        if any(signature != signatures[0] for signature in signatures[1:]):
            raise ValueError("three-way comparison has different target or reference scopes")
        for side, score in scored.items():
            sides[side].append(score)
        for name, left, right in (("native_to_previous", "native", "previous"),
                                  ("previous_to_final", "previous", "final"),
                                  ("native_to_final", "native", "final")):
            comparisons[name].extend(_paired_units(case, scored[left], scored[right]))
    result = {"pipeline": record["native_pipeline"]["pipeline"], "score_id": index["score_id"],
              "software": index["software"], "native_pipeline": record["native_pipeline"],
              "previous_execution": record["previous_outputs"],
              "quality": {side: _summary(scores) for side, scores in sides.items()},
              "transitions": {name: _transitions(pairs) for name, pairs in comparisons.items()},
              "postprocessing": {suite: _performance(record["cases"], suite) for suite in ("quality800", "perf80")},
              "conversion": dict(Counter({key: sum(c.get("conversion", {}).get(key, 0) for c in record["cases"]
                  if c["suite"] == "quality800" and c["phase"] == "measured")
                  for key in ("total_views", "converted", "partial", "retained")})),
              "environment": record["execution_environment"],
              "status": record["state"], "deployment_status": "not_deployed", "inference_calls": 0}
    write_json(run / "three-way.json", result)
    write_json(run / "three-way-pairs.json", comparisons)
    return result


def render_report(directory: Path, baseline: Path, runs: list[Path]) -> Path:
    compared = [compare_run(run) for run in runs]
    if len({c["software"]["software_id"] for c in compared}) != 1:
        raise ValueError("pipelines do not share identical scoring software")
    summary = {"version": VERSION, "software_id": compared[0]["software"]["software_id"],
               "protocol": "mo-parse-eval-information-v5", "pipelines": compared,
               "scope": "same_frozen_native_outputs_previous_final_and_new_final",
               "native_report": str(baseline), "deployment_status": "not_deployed"}
    write_json(directory / "comparison.json", summary)
    adoption_path = directory / "adoption.json"
    adoption = read_json(adoption_path) if adoption_path.is_file() else {}
    lines = ["# MO-Parse 评分读取与原生表格范围优化", "",
             f"报告版本：`{VERSION}`；评分协议：`mo-parse-eval-information-v5`；软件：`{summary['software_id']}`。", "",
             adoption.get("headline", "三方量化结果已生成；采用结论仍需结合原页与实际交付正文的独立目读。"), "",
             "本轮统一重评八组既有有效原生产物，P07/P08各完成800页CPU后处理回放及固定80页三轮计时。没有重新运行八组模型，没有Full推理、部署、GPU服务或TTS操作。原件、expected、冻结标注、映射与资产保持只读。", "",
             "## 采用判断与配对结果", "",
             "以下三种输出由同一冻结评分器读取；原生到旧正文反映既有处理，旧正文到新正文反映本轮实际后处理改变。评分读取修正单独见原生报告的读取切换记录，不能将跨评分器差额称为解析质量提升。", "",
             "| 配置 | 候选 | 值与标签正确 / 目标 | 完整业务信息正确 / 目标 | 完整信息错误 |",
             "| --- | --- | ---: | ---: | ---: |"]
    for item in compared:
        for side, label in (("native", "原生"), ("previous", "旧正文"), ("final", "新正文")):
            metrics = item["quality"][side]["micro"]["table_records"]
            lines.append(f"| {item['pipeline']} | {label} | {metrics['correct_fields']} / {metrics['target_fields']} | "
                         f"{metrics['information_correct_fields']} / {metrics['target_fields']} | "
                         f"{metrics['information_incorrect_fields']} |")
    lines += ["", "| 配置 | 旧正文到新正文新增正确 | 原正确项损失 | 新增确认错误 | 采用判断 |",
              "| --- | ---: | ---: | ---: | --- |"]
    for item in compared:
        transition = item["transitions"]["previous_to_final"]
        decision = "需逐项审阅退化，暂不整体采用" if (transition["lost_correct"] or transition["new_incorrect"]
            or any(transition["attribute_losses"].values())) else (
            "计分门槛通过，待结合目读确定采用范围" if transition["new_correct"] else "未实测到完整信息增益，保留工程改动并说明限制")
        decision = adoption.get("pipelines", {}).get(item["pipeline"], decision)
        lines.append(f"| {item['pipeline']} | {transition['new_correct']} | {transition['lost_correct']} | {transition['new_incorrect']} | {decision} |")
    lines += ["", "各项新增正确、原正确项损失、新增错误和状态迁移分别保存在每组`three-way.json`；逐字段来源与比较见`three-way-pairs.json`。这些均是候选评分，不构成参考或整套语料的目视验收。", "",
              "## 正文保全与成本", "",
              "信息覆盖、业务归属和文字保全分别查看每组报告；新增关系只能来自候选实际已表达的文字。原生未保存的缩进与分部层级不能靠参考补齐，所有已纳入业务目标均以正确或错误进入固定分母。没有固定下游抽取器及独立标注，本轮不报告实体、关系或事件抽取准确率或F1。", "",
              "| 配置 | 800页后处理秒，n=1 | 80页三轮秒 | 80页中位秒 | 转换 / 部分转换 / 保留视图 |",
              "| --- | ---: | --- | ---: | --- |"]
    for item in compared:
        q, perf = item["postprocessing"]["quality800"], item["postprocessing"]["perf80"]
        # The source measurement schema is reproduced in machine output too.
        qtime = q.get("median_postprocessing_seconds")
        rounds = [r.get("postprocessing_seconds") for r in perf.get("rounds", [])]
        c = item["conversion"]
        quality_time = f"{qtime:.3f}" if qtime is not None else "未知"
        median = perf.get("median_postprocessing_seconds")
        median_time = f"{median:.3f}" if median is not None else "未知"
        lines.append(f"| {item['pipeline']} | {quality_time} | {', '.join(f'{s:.3f}' if s is not None else '未知' for s in rounds)} | {median_time} | {c['converted']} / {c['partial']} / {c['retained']} |")
    lines += ["", "后处理沿用8 CPU配额、8 GiB内存、外层并发1、无网络、无GPU设备的隔离容器，预热及软件身份单独记录。计时包括来源处理、忠实读取、导出、图片保全、语义与最终正文步骤，纯加载和结果持久化另记；没有把历史原生耗时与本轮后处理耗时相加冒充端到端实测。原生历史性能仍按其真实共享GPU和不受控TTS条件解释。视图状态不是独立表格分类准确率。", "",
              "## 实际正文与未解决范围", "",
              "[实际正文对照与案例](case-notes.md)记录已目读范围和开发暴露；没有列出的页面不视为重新目读或验收。", ""]
    lines += [paragraph for text in adoption.get("limitations", []) for paragraph in (text, "")]
    lines += ["## 证据与复现", "",
              f"[八管线当前原生比较](../{baseline.name}/report.md) · [原生详细字段](../{baseline.name}/field-details.csv) · [三方机器汇总](comparison.json) · [目读与采用记录](../../reference-decisions/20261030-table-context/visual-review.md)。", ""]
    for run in runs:
        relative = run.relative_to(directory)
        lines.append(f"[{relative.name.upper()}原生与新正文报告]({relative}/report.md) · [三方配对]({relative}/three-way.json) · [逐项明细]({relative}/three-way-pairs.json) · [评分冻结]({relative}/scoring-freeze.json)。")
        lines.append("")
    lines += ["用冻结候选与评分产物重新生成本报告：", "", "```bash",
              f"python -m moparse_eval.table_context_report --output {directory} --baseline {baseline} " + " ".join(f"--run {run}" for run in runs), "```", ""]
    path = directory / "report.md"
    path.write_text("\n".join(lines))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--run", required=True, action="append", type=Path)
    args = parser.parse_args()
    print(render_report(args.output, args.baseline, args.run))


if __name__ == "__main__":
    main()
