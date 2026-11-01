"""Present completed score artifacts; never read references or candidates."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moparse_eval.expected_report import first_failure_stage, load_complete  # noqa: E402
from moparse_eval.packaging import write_json  # noqa: E402


def render(index_path: Path, output: Path) -> None:
    index, groups = load_complete(index_path)
    output.mkdir(parents=True, exist_ok=True)
    summary = index["summary"]
    baseline = "intermediate" if "P07-intermediate" in summary else "previous"
    lines = ["# MO-Parse 本轮修复结果", "",
             "本轮目标是保留原生已正确的信息，并让最终Markdown明确表达已有业务关系。唯一答案来源是现有expected；所有组使用同一冻结程序。", "",
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
        "scope": "presentation_only_from_completed_uniform_scores_no_regrading",
        "comparison_details": {"previous_to_current": "private/paired-changes.json",
                               "before_to_current": "private/incremental-changes.json",
                               "native_to_current": "private/native-preservation.json"}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.index, args.output)
