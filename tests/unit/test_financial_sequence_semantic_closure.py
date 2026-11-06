"""Independent annual-pair, actual-amount and boundary oracles."""

from copy import deepcopy

import pytest

from moparse_eval.cjk_measurement_requirements import read_cjk_measurements
from moparse_eval.expected_report import validate_evidence
from moparse_eval.series_requirements import read_series_requirements
from moparse_eval.source_obligations import audit_source_obligations
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown
from tests.unit.test_compact_multichange_production import review
from tests.unit.test_represented_feature_production import production

SOURCE = {"path": "<independent-financial-sequence>", "lines": [3, 3]}
SERIES = "现金流：2030年140万元；2029年120万元；同比变动下降3个百分点。\n"


@pytest.mark.parametrize("order", [(2030, 2029), (2029, 2030)])
def test_explicit_yoy_of_a_closed_metric_pair_has_calendar_roles_independent_of_print_order(order):
    text = f"现金流：{order[0]}年140万元；{order[1]}年120万元；同比变动下降3个百分点。"
    result = read_series_requirements(text, SOURCE)
    assert not result["blockers"]
    first, second, change = result["facts"]
    assert (first["attribute"], second["attribute"], change["subject"]) == ("现金流", "现金流", "现金流")
    assert change["qualifiers"] == {"unit": "个百分点", "from_period": "2029年", "to_period": "2030年", "change_direction": "decrease"}
    for key, literal in (("from_period", "2029年"), ("to_period", "2030年")):
        assert text[slice(*change["qualifier_sources"][key]["text_span"])] == literal


@pytest.mark.parametrize("text", [
    "现金流：2030年140万元；2028年120万元；同比变动3%。",
    "现金流：2030年140万元；2029年120万元；2028年80万元；同比变动3%。",
    "现金流：2030年12月31日140万元；2029年6月30日120万元；同比变动3%。",
    "现金流：2030年140万元；同比变动3%。",
    "现金流：2030年140万元；2029年120万元；增减3%。",
])
def test_neighboring_years_do_not_supply_ambiguous_incomplete_or_non_yoy_comparison_roles(text):
    result = read_series_requirements(text, SOURCE)
    assert result["blockers"]
    assert "from_period" not in result["facts"][-1]["qualifiers"]


@pytest.mark.parametrize("changed", [SERIES, SERIES.replace("140万元", "1400000元"),
    SERIES.replace("2030年140万元；2029年120万元", "2029年120万元；2030年140万元")])
def test_closed_annual_pair_reaches_final_comparison_and_report_review(tmp_path, changed):
    _, required = production(tmp_path, SERIES)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id=required["sample_id"]))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 3
    assert result["layers"]["L"]["score"] == 100
    review(result)


@pytest.mark.parametrize("changed", [
    SERIES.replace("2030年", "2031年"), SERIES.replace("2029年120万元；", ""),
    SERIES.replace("；同比变动下降3个百分点", ""), SERIES.replace("百分点", "%"),
    SERIES.replace("下降", "增长"), SERIES.replace("现金流", "经营利润"),
    SERIES.replace("；同比", "。\n\n同比"),
])
def test_period_metric_direction_unit_and_missing_relationships_cannot_receive_full_business_credit(tmp_path, changed):
    _, required = production(tmp_path, SERIES)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["numerator"] < result["layers"]["B"]["denominator"]
    review(result)


@pytest.mark.parametrize("period", ["2030年", "2030年末", "2030年6月30日"])
def test_local_actor_actual_amount_and_absolute_change_have_independently_authored_roles(tmp_path, period):
    text = f"{period}本公司总资产为人民币140万元，比上年末增加人民币12万元。\n"
    graph, required = production(tmp_path, text)
    assert graph["semantic_complete"]
    assert [(f["subject"], f["attribute"], f["value"]) for f in required["business"]] == [
        ("总资产", "为", "140"), ("总资产", "比上年末增加", "12")]
    assert all(f["qualifiers"]["actor"] == "本公司" and f["qualifiers"]["period"] == period for f in required["business"])
    change = required["business"][1]
    assert change["qualifiers"]["comparison_basis"] == "比上年末"
    assert "from_period" not in change["qualifiers"], "an explicit relative basis does not print its calendar year"
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == 2
    validate_evidence(result)


def test_an_absolute_yoy_amount_is_not_a_percentage_or_a_new_metric():
    text = "工业产值超过137万元，同比增长4.3万元。"
    result = read_cjk_measurements(text, SOURCE)
    assert result["complete"]
    assert [(f["subject"], f["value"], f["qualifiers"]["unit"]) for f in result["facts"]] == [
        ("工业产值", "137", "万元"), ("工业产值", "4.3", "万元")]


def test_a_reason_tail_is_not_an_amount_or_an_actor_and_remains_precisely_unresolved():
    text = "2030年本集团合同资产为人民币20万元，较2029年末增长8%，主要由于业务增长所致。"
    before = deepcopy(SOURCE)
    result = read_cjk_measurements(text, SOURCE)
    assert SOURCE == before
    assert [(f["subject"], f["value"]) for f in result["facts"]] == [("合同资产", "20"), ("合同资产", "8")]
    assert not result["complete"]
    [tail] = result["unresolved"][0]["fragments"]
    assert tail["text"] == "主要由于业务增长所致"
    assert text[slice(*tail["source"]["text_span"])] == tail["text"]


PARENTS = ("# 财务状况\n\n金额单位：人民币百万元。\n\n"
    "- 资产合计：2030年120；2029年100；同比变动20%。\n"
    "  - 其中，现金：2030年40；2029年30；同比变动33%。\n"
    "- 所有者权益：2030年8；2029年7；同比变动14%。\n"
    "  - 权益率：2030年6%；2029年7%；同比变动下降1个百分点。\n")


def test_actual_list_parent_label_owns_membership_without_supplying_child_periods_or_units(tmp_path):
    graph, required = production(tmp_path, PARENTS)
    children = [fact for fact in required["business"] if fact["qualifiers"].get("parent_metric")]
    assert len(children) == 6
    assert [fact["qualifiers"]["parent_metric"] for fact in children] == ["资产合计"] * 3 + ["所有者权益"] * 3
    assert [fact["attribute"] for fact in children] == ["现金", "现金", "同比变动", "权益率", "权益率", "同比变动"]
    assert all(fact["qualifiers"]["unit"] == "%" for fact in children[3:5])
    assert all(fact["qualifiers"].get("currency") is None for fact in children[3:])
    result = grade_layers(required, read_candidate_markdown(PARENTS, sample_id=required["sample_id"]))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    validate_evidence(result)


def test_inline_prose_ends_the_default_and_later_fields_do_not_inherit_it():
    text = PARENTS.split("- 所有者权益")[0] + "\n净利润为美元3万元。\n\n- 所有者权益：2030年8；2029年7；同比变动14%。\n"
    graph = compile_markdown(text, sample_id="invented-unit-termination")
    following = [fact for fact in graph["business"] if fact["attribute"] == "所有者权益"]
    assert len(following) == 2 and all("unit" not in fact["qualifiers"] and "currency" not in fact["qualifiers"] for fact in following)
    assert graph["unit_scope_terminations"]
    assert not any(issue["reason"] == "unit_scope_boundary_unresolved" for issue in graph["blockers"])


def test_a_new_heading_does_not_supply_a_unit_from_an_earlier_section():
    graph = compile_markdown(PARENTS + "\n## 新业务\n\n现金：2030年5；2029年4；同比变动25%。\n", sample_id="invented-unit-termination")
    following = [fact for fact in graph["business"] if fact["scope"] == ["财务状况", "新业务"]]
    assert following and all("currency" not in fact["qualifiers"] for fact in following)
    assert all(fact["qualifiers"].get("unit") in {None, "%"} for fact in following)


@pytest.mark.parametrize("dimension", ["from_period", "to_period"])
def test_another_metrics_real_year_token_cannot_replace_this_rows_comparison_source(tmp_path, dimension):
    text = SERIES + "\n利润：2030年9万元；2029年8万元；同比变动4%。\n"
    graph, required = production(tmp_path, text)
    actual = read_candidate_markdown(text, sample_id=required["sample_id"])
    changes = [fact for fact in actual["business"] if fact["attribute"] == "同比变动"]
    changes[0]["qualifier_sources"][dimension] = deepcopy(changes[1]["qualifier_sources"][dimension])
    # All words and values remain identical; only provenance is borrowed.
    with pytest.raises(ValueError, match='source-bound series comparison period'):
        grade_layers(required, actual)
    graph_changes = [node for node in graph["nodes"] if node["id"] in graph["projections"]["B"] and node["attribute"] == "同比变动"]
    graph_changes[0]["qualifier_sources"][dimension] = deepcopy(graph_changes[1]["qualifier_sources"][dimension])
    assert not audit_source_obligations(graph["source_obligation_inventory"], graph)["semantic_complete"]


RATIO = "截至2030年底，总资产余额达到人民币120百万元，同比增长3%，其中现金余额占总资产余额的25%。\n"


def test_reached_amount_and_ratio_keep_all_three_independent_business_requirements(tmp_path):
    _, required = production(tmp_path, RATIO)
    assert [(fact["subject"], fact["attribute"], fact["value"]) for fact in required["business"]] == [
        ("总资产余额", "达到", "120"), ("总资产余额", "同比增长", "3"), ("现金余额", "占", "25")]
    ratio = required["business"][2]
    assert ratio["qualifiers"]["denominator"] == "总资产余额"
    assert ratio["qualifiers"]["period"] == "2030年底"
    assert "currency" not in ratio["qualifiers"]
    score = grade_layers(required, read_candidate_markdown(RATIO, sample_id=required["sample_id"]))
    assert score["publishable"] and score["layers"]["B"]["numerator"] == 3
    validate_evidence(score)


@pytest.mark.parametrize("changed", [RATIO.replace("现金余额占总资产余额", "现金余额占净资产余额"),
    RATIO.replace("现金余额占总资产余额", "债务余额占总资产余额"), RATIO.replace("25%", "26%"),
    RATIO.replace("2030年底", "2030年"), RATIO.replace("同比增长3%，", ""),
    RATIO.replace("，其中现金余额占总资产余额的25%", "")])
def test_share_denominator_numerator_value_time_and_deleted_relations_are_not_interchangeable(tmp_path, changed):
    _, required = production(tmp_path, RATIO)
    score = grade_layers(required, read_candidate_markdown(changed, sample_id=required["sample_id"]))
    assert score["layers"]["B"]["numerator"] < 3
    review(score)


@pytest.mark.parametrize('marker', ['**', '__'])
@pytest.mark.parametrize('candidate_marker', ['**', '__', ''])
def test_balanced_field_emphasis_never_enters_the_actor_metric_or_period(tmp_path, marker, candidate_marker):
    body = '2030年本公司总资产为人民币120万元，比上年末增加人民币7万元。\n'
    text = marker + '总资产：' + marker + body
    graph, required = production(tmp_path, text)
    assert [(fact['subject'], fact['qualifiers']['period'], fact['qualifiers']['actor']) for fact in required['business']] == [
        ('总资产', '2030年', '本公司'), ('总资产', '2030年', '本公司')]
    assert all(fact['scope'] == ['总资产'] for fact in required['business'])
    result = grade_layers(required, read_candidate_markdown(candidate_marker + '总资产：' + candidate_marker + body,
        sample_id=required['sample_id']))
    assert result['publishable'], result['blockers']
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    validate_evidence(result)


def test_an_unbalanced_marker_is_not_swallowed_as_part_of_a_metric_name():
    parsed = read_cjk_measurements('**2030年本公司总资产为人民币120万元，同比增长3%。', SOURCE)
    assert not parsed['complete'] and not parsed['facts']


@pytest.mark.parametrize('actor,metric,realize,equal,change,currency,unit', [
    ('本公司', '营业利润', '实现', '为', '同比减少', '人民币', '万元'),
    ('本集團', '營業利潤', '實現', '為', '同比減少', '人民幣', '萬元'),
])
def test_realization_with_a_printed_actor_and_equality_link_preserves_every_role(tmp_path, actor, metric, realize, equal, change, currency, unit):
    text = f'2032年{actor}{realize}{metric}{equal}{currency}37{unit}，{change}{currency}2{unit}。\n'
    _, required = production(tmp_path, text)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [(metric, realize, '37'), (metric, change, '2')]
    assert required['business'][0]['qualifiers']['assertion_link'] == equal
    assert all(f['qualifiers']['actor'] == actor and f['qualifiers']['period'] == '2032年' for f in required['business'])
    score = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    assert score['publishable'] and score['layers']['B']['numerator'] == 2 and score['layers']['L']['score'] == 100
    validate_evidence(score)
