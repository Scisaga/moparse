"""Printed direction and absolute-ratio units are independent source roles."""

from copy import deepcopy

import pytest

from moparse_eval.equivalence import decide_equivalence
from moparse_eval.measurement_evidence import read_measurement_literal
from moparse_eval.series_requirements import read_series_context, read_series_requirements

SOURCE = {"path": "<invented-directed-series>", "lines": [4, 4], "text_span": [0, 200]}


@pytest.mark.parametrize("raw", ["0.35个百分点", "0.35個百分點"])
def test_classifier_inside_percentage_point_unit_remains_in_the_printed_unit(raw):
    value = read_measurement_literal(raw, SOURCE)
    assert value["matched"] is True
    assert value["value"] == "0.35" and value["unit"] == raw[4:]
    assert value["sources"]["unit"]["text_span"] == [4, len(raw)]
    assert decide_equivalence({"value": "0.35", "unit": raw[4:]},
                              {"value": "35", "unit": "bp"}, "quantity")["equivalent"] is True
    assert decide_equivalence({"value": "0.35", "unit": raw[4:]},
                              {"value": "0.35", "unit": "%"}, "quantity")["equivalent"] is False


@pytest.mark.parametrize("direction,meaning,unit", [("下降", "decrease", "個百分點"),
    ("增加", "increase", "个百分点"), ("增長", "increase", "%")])
def test_directed_series_change_keeps_positive_magnitude_and_separate_direction(direction, meaning, unit):
    text = f"Margin：2028年40.58%；2027年40.93%；同比變動{direction}0.35{unit}。"
    context = read_series_context("本年：2028年；上年：2027年。", SOURCE)
    material = read_series_requirements(text, SOURCE, context=context)
    assert material["blockers"] == []
    assert len(material["facts"]) == 3
    change = material["facts"][-1]
    assert (change["subject"], change["attribute"], change["value"]) == ("Margin", "同比變動", "0.35")
    assert change["qualifiers"] == {"unit": unit, "from_period": "2027年", "to_period": "2028年",
                                    "change_direction": meaning}
    start = text.index(direction)
    assert change["qualifier_sources"]["change_direction"]["text_span"] == [start, start + len(direction)]
    assert change["value_source"]["text_span"] == [start + len(direction), start + len(direction) + 4]
    assert material["text_projection_complete"] is True


@pytest.mark.parametrize("payload", ["下降-0.35個百分點", "下降約0.35個百分點", "下降0.35個百分點但增长", "下降0.35"])
def test_directed_change_conflict_or_unread_tail_never_becomes_a_complete_scalar(payload):
    context = read_series_context("本年：2028年；上年：2027年。", SOURCE)
    material = read_series_requirements(f"Margin：2028年40.58%；2027年40.93%；同比變動{payload}。", SOURCE, context=context)
    assert len(material["facts"]) == 2
    assert material["blockers"] and material["pending_requirements"]


def test_generic_change_does_not_invent_a_year_from_two_neighboring_year_values():
    material = read_series_requirements("Margin：2028年40.58%；2027年40.93%；增減下降0.35個百分點。", SOURCE)
    assert len(material["facts"]) == 3
    change = material["facts"][-1]
    assert "from_period" not in change["qualifiers"] and "to_period" not in change["qualifiers"]
    assert any(issue["reason"] == "series_comparison_periods_unresolved" for issue in material["blockers"])


@pytest.mark.parametrize("direction,meaning,unit", [
    ("增长", "increase", "%"), ("上升", "increase", "bp"),
    ("减少", "decrease", "基点"), ("減少", "decrease", "基點"),
])
def test_finite_existing_direction_vocabulary_keeps_its_exact_ratio_unit(direction, meaning, unit):
    text = f"Margin：2028年40.58%；2027年40.93%；YoY change:{direction}35{unit}."
    source = {"path": "<own-directed-scalar>", "lines": [8, 8], "text_span": [70, 70 + len(text)]}
    context_source = {"path": "<explicit-comparison-declaration>", "lines": [2, 2]}
    context = read_series_context("本年：2028年；上年：2027年。", context_source)
    original = deepcopy((source, context))
    material = read_series_requirements(text, source, context=context)
    assert material["blockers"] == [] and len(material["facts"]) == 3
    change = material["facts"][-1]
    assert (change["attribute"], change["value"], change["raw_value"]) == ("YoY change", "35", direction + "35" + unit)
    assert change["qualifiers"] == {"unit": unit, "from_period": "2027年", "to_period": "2028年", "change_direction": meaning}
    start = text.index(direction)
    assert change["source"]["text_span"] == [70 + start, 70 + start + len(change["raw_value"])]
    assert change["value_source"]["text_span"] == [70 + start + len(direction), 70 + start + len(direction) + 2]
    assert change["qualifier_sources"]["change_direction"]["text_span"] == [70 + start, 70 + start + len(direction)]
    assert change["qualifier_sources"]["from_period"]["path"] == context_source["path"]
    assert change["qualifier_sources"]["to_period"]["path"] == context_source["path"]
    assert material["text_projection_complete"] is True
    assert (source, context) == original


@pytest.mark.parametrize("payload", [
    "下降+0.35%", "下降−0.35%", "下降(0.35)%", "下降（0.35）%",
    "下降-35bp", "增加-35bp", "增加+35bp", "下降约0.35%", "下降0.35万元",
    "下降—%", "下降0.35%或增加0.35%", "下降幅度0.35%",
])
def test_directed_unsigned_ratio_grammar_rejects_signed_missing_compound_and_nonratio_payloads(payload):
    context = read_series_context("本年：2028年；上年：2027年。", SOURCE)
    text = f"Margin：2028年40.58%；2027年40.93%；同比變動{payload}。"
    material = read_series_requirements(text, SOURCE, context=context)
    assert len(material["facts"]) == 2
    assert material["blockers"] and material["pending_requirements"]
    assert any(issue.get("text") == payload for issue in material["pending_requirements"])
    assert material["text_projection_complete"] is True, "unsupported meaning must still retain the original printed payload"


def test_a_named_shared_ratio_unit_keeps_its_own_declaration_without_borrowing_an_annual_unit():
    declaration = "同比變動单位：bp；本年：2028年；上年：2027年。"
    context = read_series_context(declaration, {"path": "<explicit-shared-change-unit>", "lines": [2, 2]})
    text = "Margin：2028年40.58%；2027年40.93%；同比變動下降35。"
    material = read_series_requirements(text, SOURCE, context=context)
    assert material["blockers"] == []
    change = material["facts"][-1]
    assert (change["value"], change["raw_value"]) == ("35", "下降35")
    assert change["qualifiers"] == {"unit": "bp", "change_direction": "decrease",
                                    "from_period": "2027年", "to_period": "2028年"}
    assert change["qualifier_sources"]["unit"] == {
        "path": "<explicit-shared-change-unit>", "lines": [2, 2], "text_span": [7, 9]}
    assert material["text_projection_complete"] is True


def test_an_annual_percent_unit_does_not_supply_a_missing_change_unit():
    context = read_series_context("单位：%；本年：2028年；上年：2027年。", SOURCE)
    material = read_series_requirements("Margin：2028年40.58；2027年40.93；同比變動下降0.35。", SOURCE, context=context)
    assert len(material["facts"]) == 2
    assert all(fact["qualifiers"]["unit"] == "%" for fact in material["facts"])
    assert any(issue["reason"] == "series_directed_change_ratio_unit_unresolved" for issue in material["blockers"])


def test_direction_grammar_never_reinterprets_a_printed_reason_as_a_change_scalar():
    text = "Margin：2028年40.58%；2027年40.93%；Reason:下降0.35個百分點。"
    material = read_series_requirements(text, SOURCE)
    assert material["blockers"] == []
    reason = material["facts"][-1]
    assert (reason["attribute"], reason["value"], reason["role"]) == ("Reason", "下降0.35個百分點", "description")
    assert "change_direction" not in reason["qualifiers"]


def test_equal_change_magnitudes_keep_separate_direction_and_unit_sources():
    context = read_series_context("本年：2028年；上年：2027年。", SOURCE)
    text = "Margin：2028年40.58%；2027年40.93%；同比變動下降0.35pp；YoY change:增加35bp。"
    material = read_series_requirements(text, SOURCE, context=context)
    assert material["blockers"] == [] and len(material["facts"]) == 4
    first, second = material["facts"][-2:]
    assert (first["value"], first["qualifiers"]["unit"], first["qualifiers"]["change_direction"]) == ("0.35", "pp", "decrease")
    assert (second["value"], second["qualifiers"]["unit"], second["qualifiers"]["change_direction"]) == ("35", "bp", "increase")
    for fact, direction in ((first, "下降"), (second, "增加")):
        assert fact["qualifier_sources"]["change_direction"]["text_span"] == [text.index(direction), text.index(direction) + 2]
    assert first["value_source"] != second["value_source"]
    assert material["text_projection_complete"] is True
