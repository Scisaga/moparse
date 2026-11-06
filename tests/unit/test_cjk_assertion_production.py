"""Actual amount assertions and local YoY binding, with independent oracles."""

from copy import deepcopy

import pytest

from moparse_eval.cjk_measurement_requirements import read_cjk_measurements
from moparse_eval.cjk_narrative_requirements import read_cjk_narrative
from moparse_eval.expected_report import validate_evidence
from moparse_eval.measurement_evidence import read_measurement_literal
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_compact_multichange_production import review
from tests.unit.test_represented_feature_production import production

TEXT = "2029年实现销售收入人民币281,346百万元，同比增长8.7%。净利润为人民币19,482百万元。\n"


def test_an_unrelated_numeric_tail_cannot_take_over_a_supported_neighbor():
    text = "甲公司提供服务，本项预算为人民币70万元。"
    source = {"path": "<invented-measurement-dispatch>", "lines": [1, 1]}
    assert not read_cjk_measurements(text, source)["matched"]
    parsed = read_cjk_narrative(text, source)
    assert not parsed["complete"]
    assert [(f["subject"], f["attribute"], f["value"]) for f in parsed["facts"]] == [("甲公司", "提供", "服务")]


@pytest.mark.parametrize("period", ["2029年末", "2029年初", "2029年度", "2029年6月30日"])
def test_a_bare_year_reader_does_not_swallow_an_uninterpreted_period_suffix(period):
    parsed = read_cjk_measurements(period + "净利润为人民币42万元。", {"path": "<invented-period-boundary>", "lines": [1, 1]})
    assert not parsed["complete"] and not parsed["facts"]


@pytest.mark.parametrize("variation", [TEXT, TEXT.replace("2029年实现", "2029年，实现"),
    TEXT.replace("281,346百万元", "28134600万元"),
    TEXT.replace("人民币281,346百万元", "28134600万元人民币"),
    TEXT.replace("8.7%", "87‰"),
])
def test_actual_assertions_and_lossless_amounts_reach_final_independent_votes(tmp_path, variation):
    graph, required = production(tmp_path, TEXT)
    assert [(f["subject"], f["attribute"], f["value"]) for f in required["business"]] == [
        ("销售收入", "实现", "281,346"), ("销售收入", "同比增长", "8.7"), ("净利润", "为", "19,482")]
    assert [f["qualifiers"].get("period") for f in required["business"]] == ["2029年", "2029年", None]
    assert required["business"][0]["qualifiers"]["unit"] == "百万元"
    assert required["business"][0]["qualifiers"]["currency"] == "人民币"
    assert required["logical_statements"][0]["clauses"][0]["kind"] == "quantity_assertion"
    assert all(row["status"] != "pending" for row in graph["source_obligation_coverage"]["dispositions"])
    result = grade_layers(required, read_candidate_markdown(variation, sample_id=required["sample_id"]))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 3
    assert result["layers"]["L"]["score"] == 100
    if variation != TEXT:
        assert result["layers"]["T"]["score"] < 100
    validate_evidence(result)


def test_accounting_negative_and_prefix_currency_keep_distinct_original_sources(tmp_path):
    text = "净利润为人民币(6,210)百万元。\n"
    _, required = production(tmp_path, text)
    [fact] = required["business"]
    assert fact["value"] == "(6,210)"
    origins = fact["qualifier_sources"]
    for key, literal in [("unit", "百万元"), ("currency", "人民币")]:
        assert text[slice(*origins[key]["text_span"])] == literal
    result = grade_layers(required, read_candidate_markdown(text.replace("(6,210)", "-6210"), sample_id=required["sample_id"]))
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    validate_evidence(result)
    assert not read_measurement_literal("人民币6210美元")["matched"]


def test_multiple_assertions_reset_the_immediate_relative_metric(tmp_path):
    text = "2030年实现销售收入人民币75百万元，同比增长6%，净利润为人民币9百万元，同比下降2%。\n"
    _, required = production(tmp_path, text)
    assert [(f["subject"], f["attribute"], f["value"]) for f in required["business"]] == [
        ("销售收入", "实现", "75"), ("销售收入", "同比增长", "6"), ("净利润", "为", "9"), ("净利润", "同比下降", "2")]
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["numerator"] == 4
    validate_evidence(result)


@pytest.mark.parametrize("changed", [
    TEXT.replace("281,346", "281,347"),
    TEXT.replace("同比增长", "同比下降"),
    TEXT.replace("同比增长", "环比增长"),
    TEXT.replace("8.7%", "8.7个百分点"),
    TEXT.replace("2029年", "2030年"),
    TEXT.replace("2029年", ""),
    TEXT.replace("实现销售收入", "预计实现销售收入"),
    TEXT.replace("实现销售收入", "目标销售收入为"),
    TEXT.replace("实现销售收入", "未实现销售收入"),
    TEXT.replace("实现销售收入", "如果实现销售收入"),
    TEXT.replace("，同比增长", "。同比增长"),
    TEXT.replace("，同比增长", "\n\n- 同比增长"),
    TEXT.replace("，同比增长", "，其他指标待定，同比增长"),
    TEXT.replace("。净利润为", "，净利润为").replace("，同比增长8.7%", "") + "同比增长8.7%。\n",
])
def test_numeric_relationship_scope_and_actuality_conflicts_never_receive_full_business_credit(tmp_path, changed):
    _, required = production(tmp_path, TEXT)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["denominator"] == 3
    assert result["layers"]["B"]["numerator"] < 3
    if changed == TEXT.replace("281,346", "281,347"):
        assert result["layers"]["L"]["score"] == 100
    review(result)


def test_heading_year_is_an_actual_scope_and_a_prior_sentence_year_is_not(tmp_path):
    text = "# 2030年\n\n净利润为人民币52百万元。\n"
    graph, required = production(tmp_path, text)
    [fact] = required["business"]
    assert fact["scope"] == ["2030年"]
    assert any(e["source"].get("lines") == [1, 1] for e in graph["sources"])
    result = grade_layers(required, read_candidate_markdown(text.replace("# 2030年", "# 2031年"), sample_id=required["sample_id"]))
    assert result["layers"]["B"]["score"] != 100
    review(result)


@pytest.mark.parametrize("mutation", ["fact", "ast", "relation", "period", "currency_source", "relative_metric", "feature"])
def test_all_original_text_cannot_replace_amount_and_relative_binding_evidence(tmp_path, mutation):
    _, required = production(tmp_path, TEXT)
    actual = read_candidate_markdown(TEXT, sample_id=required["sample_id"])
    if mutation == "fact":
        actual["business"].pop(1)
    elif mutation == "ast":
        actual["logical_statements"][0]["clauses"].pop()
    elif mutation == "relation":
        actual["relations"] = [e for e in actual["relations"] if e["type"] != "cjk_year_on_year_subject_binding"]
    elif mutation == "period":
        actual["business"][-1]["qualifiers"]["period"] = "2029年"
        actual["business"][-1]["qualifier_sources"]["period"] = deepcopy(actual["business"][0]["qualifier_sources"]["period"])
    elif mutation == "currency_source":
        actual["business"][-1]["qualifier_sources"]["currency"] = deepcopy(actual["business"][0]["qualifier_sources"]["currency"])
    elif mutation == "feature":
        actual["required_matcher_features"] = []
    else:
        first = actual["business"][1]
        first["subject"], first["subject_source"] = actual["business"][-1]["subject"], deepcopy(actual["business"][-1]["subject_source"])
        for edge in actual["relations"]:
            if edge.get("fact_id") == first["id"]:
                edge["right"]["subject"] = first["subject"]
    result = grade_layers(required, actual)
    assert not result["publishable"]
    review(result)


def test_local_pronouns_are_literal_subjects_without_cross_record_entity_resolution(tmp_path):
    text = "本公司提供服务。\n\n本公司保存数据。\n"
    _, required = production(tmp_path, text)
    assert [f["subject"] for f in required["business"]] == ["本公司", "本公司"]
    assert len({f["record_id"] for f in required["business"]}) == 2
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    validate_evidence(result)
    changed = grade_layers(required, read_candidate_markdown(text.replace("本公司保存", "我们保存"), sample_id=required["sample_id"]))
    assert changed["layers"]["B"]["numerator"] < 2
    review(changed)
