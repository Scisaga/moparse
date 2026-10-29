"""Concise reporting uses synthetic aggregates, never corpus files."""

from __future__ import annotations

from copy import deepcopy

from moparse_eval.report_overview import (
    _reversals,
    relation_breakdown,
    render_overview,
    table_field_breakdown,
)


def _quality(name: str = "P01", *, cer: float = 0.2, doc_cer: float = 0.3,
             family_cer: float = 0.35, pages: int = 17) -> dict:
    return {
        "pipeline": name, "dataset": "synthetic-lite", "suite": "quality800",
        "quality": {
            "status": "evaluated", "input_pages": pages, "samples": 4,
            "documents": 3, "families": 2, "failed_samples": 0, "unscored_samples": 0,
            "micro": {
                "unit_presence": {"recall": 0.6}, "text": {"strict": {"cer": cer, "reference_chars": 100}},
                "text_aligned": {"strict": {"cer": cer / 2, "reference_chars": 80}},
                "table_records": {
                    "target_fields": 10, "observable_fields": 4,
                    "compared_fields": 4, "target_missing_fields": 0, "unresolved_fields": 6,
                    "correct_fields": 3, "strict_correct_fields": 2,
                    "field_target_correctness": {"numerator": 3, "denominator": 10, "value": 0.3},
                    "field_compared_accuracy": {"numerator": 3, "denominator": 4, "value": 0.75},
                    "field_strict_accuracy": {"numerator": 2, "denominator": 4, "value": 0.5},
                },
                "relations": {"recall": 0.5},
            },
            "macro_by_document": {"text.strict.cer": {"value": doc_cer}},
            "macro_by_family": {"text.strict.cer": {"value": family_cer}},
            "coverage": {
                "declared_units": 15, "confirmed_units": 14, "scored_units": 10,
                "text_reference_chars": 1200, "scored_relations": 5, "known_image_targets": 2,
            },
        },
        "performance": {
            "round_duration_summary": {"n": 1, "median_seconds": 120.0},
            "rounds": [{
                "attempted_input_pages": pages, "completed_input_pages": pages,
                "all_samples_completed": True, "timing_complete": True,
            }],
        },
    }


def _performance(name: str = "P01", *, n: int = 2) -> dict:
    return {
        "pipeline": name, "dataset": "synthetic-lite", "suite": "perf80",
        "quality": {"status": "performance_repetitions_not_pooled_into_quality800"},
        "performance": {"round_duration_summary": {"n": n, "median_seconds": 80.0}},
    }


def test_overview_uses_actual_values_and_round_counts_without_mutating_input():
    report = {"groups": [_quality(), _performance()], "execution": {"run_id": "synthetic-v3"},
              "score_id": "synthetic-score-v1"}
    before = deepcopy(report)
    text = render_overview(report)
    assert text.startswith("# MO-Parse 解析评测报告\n")
    assert "运行版本：`synthetic-v3`；评分版本：`synthetic-score-v1`" in text
    assert "## 质量与成本对照" in text
    assert "每组记录 17 个实际输入页" in text
    assert "包含 4 个样本、3 份原文档和 2 个家族" in text
    assert "| P01 | 17 / 17 | 2.00 / 1 | 1.33 / 2 | 0 / 0 |" in text
    assert "| P01 | 60.00% | 10.00% | 80.00% | 30.00% | NA |" in text
    assert "各组已定位范围不同，不单独凭此CER排名" in text
    assert "正式集 n=1 与性能子集" in text
    assert report == before


def test_micro_macro_reversals_are_computed_from_scores():
    report = {"groups": [
        _quality("P03", cer=0.1, doc_cer=0.3, family_cer=0.4),
        _quality("P05", cer=0.2, doc_cer=0.1, family_cer=0.2),
    ]}
    text = "".join(_reversals({group["pipeline"]: group for group in report["groups"]}))
    assert "P03 的字符微平均 CER 更低（10.00% 对 20.00%）" in text
    assert "文档宏平均则由 P05 更低（10.00% 对 30.00%）" in text
    assert "家族宏平均也发生反转（20.00% 对 40.00%）" in text
    assert "P04 的字符微平均" not in text


def test_coverage_is_not_replaced_by_conditional_field_accuracy():
    text = render_overview({"groups": [_quality()]})
    assert "| P01 | 30.00% (3 / 10) | 75.00% (3 / 4) | 4 / 0 / 6 | 10 |" in text
    assert "高条件正确率不能替代目标覆盖" in text
    assert "1,200 个参考字符" in text
    assert "已知图片目标 2 个" in text
    assert "图片保全为 NA" in text
    assert "未闭合范围的 Precision / F1" in text


def test_new_table_main_metrics_keep_denominators_and_protocol_separate_from_strict_diagnostics():
    quality = _quality()
    report = {"groups": [quality], "scoring_protocol": {"id": "synthetic-fields-v2"}}
    before = deepcopy(report)
    text = render_overview(report)
    assert "已证正确字段覆盖率" in text and "已比较字段正确率" in text
    assert "评分协议：`synthetic-fields-v2`" in text
    assert "目标格未取到值不证明文字在整个输出中遗漏" in text
    assert "heading_of" not in text
    assert "50.00%" not in text  # The strict-only field ratio is not a main result.
    assert report == before


def test_legacy_table_scores_never_fall_back_to_old_target_or_observable_accuracy():
    quality = _quality()
    table = quality["quality"]["micro"]["table_records"]
    for key in ("compared_fields", "target_missing_fields", "unresolved_fields", "correct_fields", "strict_correct_fields"):
        table.pop(key)
    text = render_overview({"groups": [quality]})
    assert "| P01 | 60.00% | 10.00% | 80.00% | NA | NA |" in text
    assert "已证正确字段覆盖率最高" not in text
    assert "已比较字段正确率最高" not in text
    assert "| P01 | NA (NA) | NA (NA) | NA / NA / NA | 10 |" in text


def test_table_field_projection_preserves_confirmed_zero_and_rejects_unclosed_or_stale_rates():
    table = {"target_fields": 0, "compared_fields": 0, "target_missing_fields": 0,
             "unresolved_fields": 0, "correct_fields": 0, "strict_correct_fields": 0,
             "field_target_correctness": {"numerator": 0, "denominator": 0, "value": None},
             "field_compared_accuracy": {"numerator": 0, "denominator": 0, "value": None}}
    before = deepcopy(table)
    row = table_field_breakdown(table)
    assert row["available"] and row["target_fields"] == 0
    assert row["field_compared_accuracy"] == {"numerator": 0, "denominator": 0, "value": None}
    assert table == before
    table["unresolved_fields"] = 1
    assert not table_field_breakdown(table)["available"]
    table = _quality()["quality"]["micro"]["table_records"]
    table["field_target_correctness"] = {"numerator": 2, "denominator": 10, "value": 0.2}
    assert table_field_breakdown(table)["field_target_correctness"]["value"] is None


def test_missing_declared_pipeline_remains_na_in_quality_and_cost():
    report = {
        "groups": [_quality()],
        "execution": {"configurations": [{"pipeline": "P01"}, {"pipeline": "P04"}]},
    }
    text = render_overview(report)
    assert "| P04 | NA | NA | NA | NA | NA |" in text
    assert "| P04 | NA | NA / NA | NA / NA | NA / NA |" in text
    assert "每组记录 NA 个实际输入页" in text
    assert "P03 / P04 使用内存修复后的完整重跑" not in text


def test_partial_timing_is_not_reported_as_shortest_complete_run():
    quality = _quality()
    quality["quality"]["failed_samples"] = 1
    quality["quality"]["unscored_samples"] = 1
    quality["performance"]["rounds"][0].update(
        completed_input_pages=12, all_samples_completed=False, timing_complete=False,
    )
    quality["performance"]["round_duration_summary"].update(n=0, median_seconds=None)
    text = render_overview({"groups": [quality]})
    assert "| P01 | 12 / 17 | NA / 0 | NA / NA | 1 / 1 |" in text
    assert "处理时间最短" not in text
    assert "失败尝试保留在计划页与耗时口径中" in text


def test_absent_metrics_and_nonfinite_values_do_not_become_zero():
    quality = _quality(cer=float("nan"))
    quality["quality"]["micro"]["unit_presence"]["recall"] = None
    quality["quality"]["micro"]["relations"]["recall"] = float("inf")
    text = render_overview({"groups": [quality]})
    assert "| P01 | NA | NA | 80.00% | 30.00% |" in text
    assert "nan" not in text.lower()
    assert "inf%" not in text.lower()
    quality["quality"]["micro"]["text_aligned"]["strict"]["cer"] = 1.2
    assert "120.00%" in render_overview({"groups": [quality]})


def test_empty_and_preflight_only_reports_do_not_claim_formal_quality():
    assert "当前没有正式聚合结果" in render_overview({})
    text = render_overview({"groups": [{
        "pipeline": "P08", "dataset": "synthetic-preflight", "suite": "preflight8",
        "quality": {"status": "not_scored"}, "performance": {},
    }]})
    assert "当前没有可比较的正式质量数值" in text
    assert "| P08 | NA | NA | NA |" in text
    assert "处理时间最短" not in text


def test_figures_are_embedded_with_export_links_and_existing_case_navigation():
    ids = [
        "quality", "averaging", "table-coverage", "quality-time", "perf-repeat",
        "tradeoff", "resources", "categories", "coverage", "relations",
    ]
    figures = [{
        "id": ident, "title": f"synthetic {ident}", "png": f"figures/{ident}.png",
        "svg": f"figures/{ident}.svg", "pdf": f"figures/{ident}.pdf",
        "caption": f"caption {ident}",
    } for ident in ids]
    report = {
        "groups": [_quality()], "qualitative_review": "visual-review/README.md",
        "score_index": "synthetic-score/index.json", "scoring_notes": "scoring-notes.md",
    }
    text = render_overview(report, figures)
    for ident in (item for item in ids if item != "averaging"):
        assert f"![synthetic {ident}](figures/{ident}.png)" in text
        assert f"[SVG](figures/{ident}.svg)" in text
        assert f"[PDF](figures/{ident}.pdf)" in text
    assert text.count("![") == 9
    assert "figures/averaging.png" not in text
    assert "[人工个案与证据](visual-review/README.md)" in text
    assert "[详细附录](appendix.md)" in text
    assert "[质量切片 CSV](quality-slices.csv)" in text
    assert "[记录](synthetic-score/index.json)" in text


def test_composed_sources_do_not_invent_pipeline_specific_repair_history():
    report = {
        "groups": [_quality()],
        "execution": {"composition": {"selected_sources": {"P03": "rerun", "P04": "rerun"}}},
    }
    text = render_overview(report)
    assert "组合了运行记录中明确声明的执行来源" in text
    assert "内存修复后的完整重跑" not in text
    report["execution"]["composition"]["selected_sources"]["P04"] = "base"
    assert "组合了运行记录中明确声明的执行来源" in render_overview(report)


def test_curated_human_cases_are_presented_without_inventing_additional_findings():
    report = {
        "groups": [_quality()], "qualitative_review": "synthetic-review/README.md",
        "overview_case_studies": [{
            "pipeline": "P01", "observation": "synthetic author finding",
            "scope": "one invented page, all other content unknown",
            "path": "synthetic-review/case-a.md",
        }, {"pipeline": "P02", "observation": "no evidence link"}],
    }
    text = render_overview(report)
    assert "[synthetic author finding](synthetic-review/case-a.md)" in text
    assert "one invented page, all other content unknown" in text
    assert "no evidence link" not in text
    assert "新增验收全部页面" not in text


def test_declared_configuration_notes_follow_versions_without_changing_scores():
    report = {
        "groups": [_quality()],
        "overview_configuration_notes": [{
            "pipeline": "P23", "note": "Synthetic execution limitation",
            "path": "synthetic-followup/report.md",
            "scope": "Follow-up measurements retain separate identities",
        }, {"pipeline": "P24", "note": "Missing evidence is not displayed"}],
    }
    before = deepcopy(report)
    text = render_overview(report)
    assert "| P23 | [Synthetic execution limitation](synthetic-followup/report.md) | Follow-up measurements retain separate identities |" in text
    assert "Missing evidence is not displayed" not in text
    assert text.index("表中软件版本来自保存的运行镜像记录") < text.index("### 配置补充说明")
    assert text.index("### 配置补充说明") < text.index("## 质量与成本对照")
    assert "| P01 | 60.00% | 10.00% | 80.00% | 30.00% | NA |" in text
    assert report == before
    report.pop("overview_configuration_notes")
    assert "### 配置补充说明" not in render_overview(report)


def test_relations_are_separate_from_quality_leaders_and_legacy_values_stay_pending():
    report = {"groups": [_quality()]}
    text = render_overview(report)
    assert "阅读及其他已标关系召回最高" not in text
    assert "已标关系召回 ↑" not in text
    assert "### 阅读顺序" in text
    assert "NA（复核中）" in text
    assert "50.00%" not in text
    assert "主比较只展示 before" in text
    assert "heading_of" not in text


def test_reading_order_states_are_main_and_heading_states_remain_outside_main():
    quality = _quality("P08")
    quality["quality"]["micro"]["relations"]["by_type"] = {"heading_of": {
        "denominator": 10, "numerator": 2, "value": 0.2,
        "confirmed_correct": 2, "confirmed_incorrect": 1,
        "native_not_provided": 4, "endpoint_unresolved": 2, "unassessable": 1,
    }}
    before = deepcopy(quality)
    text = render_overview({"groups": [quality]})
    assert "heading_of" not in text
    assert "| P08 | 10 | 2 | 1 | 4 | 2 | 1 | 20.00% |" not in text
    assert "标题层级及其他关系仅列" in text
    assert quality == before
    row = quality["quality"]["micro"]["relations"]["by_type"]["heading_of"]
    row.update(confirmed_correct=0, confirmed_incorrect=0, native_not_provided=7, value=0)
    text = render_overview({"groups": [quality]})
    assert "| P08 | 10 | 0 | 0 | 7 | 2 | 1 | 0.00% | NA |" not in text


def test_relation_status_requires_closed_new_counts_without_legacy_fallback():
    legacy = {"denominator": 5, "numerator": 0, "value": 0, "observable": 5}
    assert relation_breakdown(legacy)["available"] is False
    assert relation_breakdown(legacy)["value"] is None
    assert all(value is None for value in relation_breakdown(legacy)["states"].values())
    row = {"denominator": 5, "value": 0.2, "confirmed_correct": 1,
           "confirmed_incorrect": 1, "native_not_provided": 1,
           "endpoint_unresolved": 1, "unassessable": 0}
    assert relation_breakdown(row)["available"] is False
    row["unassessable"] = 1
    assert relation_breakdown(row)["available"] is True
    assert relation_breakdown(row)["conditional_accuracy"] == 0.5
    row["unassessable"] = -1
    assert relation_breakdown(row)["available"] is False
