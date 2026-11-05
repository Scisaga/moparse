"""Independent annual scalar-series oracles, using invented source text."""

from __future__ import annotations

import copy

import pytest

from moparse_eval.series_requirements import read_series_context, read_series_requirements

SOURCE = {"path": "<printed-series>", "lines": [7, 7]}
UNIT_SOURCE = {"path": "<printed-unit>", "lines": [3, 3]}


def compact(facts):
    return [(fact["subject"], fact["attribute"], fact["value"], fact["qualifiers"], fact["role"]) for fact in facts]


def test_two_explicit_annual_scalar_values_are_two_requirements_without_a_guessed_tuple_schema():
    text = "Revenue：2027年17万元；2026年11万元。"
    result = read_series_requirements(text, SOURCE)
    assert result["matched"] is True and result["blockers"] == []
    assert compact(result["facts"]) == [
        ("", "Revenue", "17", {"period": "2027年", "unit": "万元"}, "metric"),
        ("", "Revenue", "11", {"period": "2026年", "unit": "万元"}, "metric"),
    ]
    assert result["text_projection_complete"] is True
    assert [atom["text"] for atom in result["text_atoms"] if atom["role"] == "period"] == ["2027年", "2026年"]


def test_shared_unit_and_period_basis_have_their_own_declared_sources():
    declaration = read_series_context("截至12月31日止年度，金额单位：人民币百万元。", UNIT_SOURCE, scope=["Results"])
    assert declaration["matched"] is True and declaration["blockers"] == []
    assert declaration["qualifiers"] == {"unit": "人民币百万元", "currency": "人民币", "period_basis": "截至12月31日止年度"}
    result = read_series_requirements("Revenue：2027年17；2026年11。", SOURCE, context=declaration, scope=["Results"])
    assert result["blockers"] == [] and len(result["facts"]) == 2
    assert result["facts"][0]["qualifiers"] == {"unit": "人民币百万元", "currency": "人民币", "period_basis": "截至12月31日止年度", "period": "2027年"}
    assert result["facts"][0]["source"]["qualifier_sources"]["unit"]["path"] == UNIT_SOURCE["path"]
    assert result["facts"][0]["source"]["qualifier_sources"]["period"]["path"] == SOURCE["path"]


def test_joined_and_separate_explicit_year_fields_have_the_same_roles_weights_and_qualifiers():
    together = read_series_requirements("Revenue：2027年17万元；2026年11万元。", SOURCE)
    separate = [read_series_requirements(text, SOURCE, attribute="Revenue") for text in ("2027年：17万元", "2026年：11万元")]
    assert len(together["facts"]) == 2
    assert sum(len(item["facts"]) for item in separate) == 2
    assert all(item["blockers"] == [] for item in separate)
    assert compact(together["facts"]) == compact([fact for item in separate for fact in item["facts"]])


def test_an_entity_and_group_do_not_become_part_of_the_metric_path():
    result = read_series_requirements("Revenue：2027年17万元；2026年11万元", SOURCE,
                                      subject="Delta", identity_facets={"group": "North"})
    assert result["blockers"] == []
    assert [fact["subject"] for fact in result["facts"]] == ["Delta", "Delta"]
    assert [fact["attribute"] for fact in result["facts"]] == ["Revenue", "Revenue"]
    assert [fact["identity_facets"] for fact in result["facts"]] == [{"group": "North"}] * 2


@pytest.mark.parametrize("period", ["2027年", "2027年度", "2027年末", "2027年初"])
def test_explicit_period_suffixes_are_preserved_without_collapsing_different_business_periods(period):
    result = read_series_requirements(f"Revenue：{period}17万元", SOURCE)
    assert result["blockers"] == [] and len(result["facts"]) == 1
    assert result["facts"][0]["qualifiers"]["period"] == period


def test_negative_accounting_notation_and_missing_markers_are_not_converted_to_an_answer():
    result = read_series_requirements("Revenue：2027年度(17.3)万元；2026年度-万元；2025年度-11万元", SOURCE)
    assert result["blockers"] == []
    assert [fact["value"] for fact in result["facts"]] == ["(17.3)", "-", "-11"]


def test_named_unit_declaration_only_applies_to_its_own_additional_property():
    declaration = read_series_context("金额单位：人民币百万元；本年比上年增减单位：%。", UNIT_SOURCE)
    assert declaration["blockers"] == []
    assert declaration["attribute_units"]["本年比上年增减"]["unit"] == "%"
    result = read_series_requirements("Revenue：2027年17；2026年11；本年比上年增减(4.3)。", SOURCE, context=declaration)
    assert len(result["facts"]) == 3
    assert compact(result["facts"])[-1] == (
        "Revenue", "本年比上年增减", "(4.3)", {"unit": "%", "comparison_basis": "本年比上年"}, "metric")
    assert any(item["reason"] == "series_comparison_periods_unresolved" for item in result["blockers"])
    assert result["facts"][0]["qualifiers"]["unit"] == "人民币百万元"


def test_explicit_comparison_period_context_can_bind_growth_without_using_the_largest_year():
    declaration = read_series_context("本年：2027年；上年：2026年；金额单位：万元；增减单位：%。", UNIT_SOURCE)
    result = read_series_requirements("Revenue：2027年17；2026年11；增减5%。", SOURCE, context=declaration)
    assert result["blockers"] == []
    assert result["facts"][-1]["qualifiers"] == {"unit": "%", "from_period": "2026年", "to_period": "2027年"}


def test_explanatory_cause_is_independent_of_the_preceding_year_and_money_unit():
    declaration = read_series_context("单位：人民币百万元", UNIT_SOURCE)
    result = read_series_requirements("Revenue：2027年度17；2026年度11；增减5%；报告期内变动的主要原因：业务增加。", SOURCE, context=declaration)
    assert len(result["facts"]) == 4
    cause = result["facts"][-1]
    assert (cause["subject"], cause["attribute"], cause["value"], cause["role"]) == (
        "Revenue", "报告期内变动的主要原因", "业务增加", "description")
    assert "unit" not in cause["qualifiers"] and "period" not in cause["qualifiers"]


def test_an_inline_unit_change_is_retained_as_actual_evidence_instead_of_repaired_by_context():
    declaration = read_series_context("单位：人民币百万元", UNIT_SOURCE)
    result = read_series_requirements("Revenue：2027年17美元百万元；2026年11万元", SOURCE, context=declaration)
    assert result["blockers"] == []
    assert result["facts"][0]["qualifiers"]["unit"] == "美元百万元"
    assert result["facts"][0]["qualifiers"]["currency"] == "美元"
    assert result["facts"][1]["qualifiers"]["unit"] == "万元"


def test_a_named_exception_prevents_shared_unit_injection_without_inventing_a_replacement_unit():
    declaration = read_series_context("金额单位：人民币百万元（總股本另列）。", UNIT_SOURCE)
    assert declaration["blockers"] == []
    result = read_series_requirements("總股本：2027年17；2026年11。", SOURCE, context=declaration)
    assert result["blockers"] == [] and len(result["facts"]) == 2
    assert all("unit" not in fact["qualifiers"] and "currency" not in fact["qualifiers"] for fact in result["facts"])
    assert declaration["unit_exceptions"][0]["attribute"] == "總股本"


def test_context_cannot_cross_an_explicit_business_scope_boundary():
    declaration = read_series_context("单位：万元", UNIT_SOURCE, scope=["North"])
    result = read_series_requirements("Revenue：2027年17；2026年11", SOURCE, context=declaration, scope=["South"])
    assert result["blockers"][0]["reason"] == "series_context_scope_conflict"
    assert all("unit" not in fact["qualifiers"] for fact in result["facts"])


def test_the_metrics_own_parenthetical_unit_is_not_erased_with_a_conflicting_shared_scope():
    declaration = read_series_context("单位：美元", UNIT_SOURCE, scope=["North"])
    result = read_series_requirements("Revenue（万元）：2027年17；2026年11", SOURCE, context=declaration, scope=["South"])
    assert result["blockers"][0]["reason"] == "series_context_scope_conflict"
    assert [fact["attribute"] for fact in result["facts"]] == ["Revenue", "Revenue"]
    assert all(fact["qualifiers"]["unit"] == "万元" for fact in result["facts"])
    assert all("currency" not in fact["qualifiers"] for fact in result["facts"])


def test_the_named_exception_allows_its_own_explicit_stock_unit_and_drops_money_currency():
    declaration = read_series_context("金额单位：人民币百万元（總股本另列）。", UNIT_SOURCE)
    result = read_series_requirements("總股本（百萬股）：2027年17；2026年11", SOURCE, context=declaration)
    assert result["blockers"] == []
    assert all(fact["qualifiers"]["unit"] == "百萬股" and "currency" not in fact["qualifiers"] for fact in result["facts"])


def test_currency_and_period_can_be_separately_declared_with_their_own_sources():
    declaration = read_series_context("币种：美元；期间：2027年；单位：百万元", UNIT_SOURCE)
    assert declaration["blockers"] == []
    assert declaration["qualifiers"] == {"currency": "美元", "period": "2027年", "unit": "百万元"}
    assert declaration["qualifier_sources"]["currency"]["text_span"] == [3, 5]
    assert declaration["qualifier_sources"]["period"]["text_span"] == [9, 14]


def test_unit_characters_inside_a_complete_business_name_remain_unchanged():
    result = read_series_requirements("元器件收入：2027年17万元；2026年11万元", SOURCE)
    assert result["blockers"] == []
    assert [fact["attribute"] for fact in result["facts"]] == ["元器件收入", "元器件收入"]


@pytest.mark.parametrize("text,reason", [
    ("Revenue：2027年17、60%；2026年11、55%", "series_value_roles_unsupported"),
    ("Conversion：2027年1噸約7.25桶；2026年1噸約7.26桶", "series_compound_measurement_unsupported"),
    ("Revenue：2027年末余额17、月均余额11", "series_value_roles_unsupported"),
    ("Revenue：一季度17；二季度11", "series_nonannual_period_unsupported"),
])
def test_multiple_roles_or_nonannual_axes_are_not_guessed_from_value_order(text, reason):
    result = read_series_requirements(text, SOURCE)
    assert result["matched"] is True
    assert result["facts"] == []
    assert result["blockers"][0]["reason"] == reason
    assert result["pending_requirements"]


def test_missing_metric_keeps_an_explicit_requirement_pending_without_a_none_attribute_fact():
    result = read_series_requirements("2027年17万元；2026年11万元", SOURCE)
    assert result["matched"] is True and result["facts"] == []
    assert result["blockers"][0]["reason"] == "series_attribute_unavailable"
    assert len(result["pending_requirements"]) == 2


def test_years_inside_ordinary_prose_are_not_reinterpreted_as_a_scalar_series():
    result = read_series_requirements("This report quotes the 2027 annual report and assumes no liability.", SOURCE)
    assert result["matched"] is False and result["facts"] == []


def test_a_year_after_a_colon_inside_a_quoted_document_title_is_not_an_annual_metric_label():
    result = read_series_requirements("报告依据公开披露的《Delta A：2027年度报告》，并不承担责任。", SOURCE)
    assert result["matched"] is False and result["facts"] == []


def test_a_long_unlabelled_number_is_not_split_into_an_invented_year_and_measurement():
    result = read_series_requirements("Revenue：202717万元；202611万元", SOURCE)
    assert result["matched"] is False and result["facts"] == []


@pytest.mark.parametrize("text", [
    "Period:2027", "Name:2027", "Revenue:2027", "Revenue:2027年", "Revenue:202717", "Revenue:2027.4",
])
def test_a_scalar_or_year_only_key_value_is_not_taken_over_as_an_empty_annual_series(text):
    result = read_series_requirements(text, SOURCE)
    assert result["matched"] is False
    assert result["facts"] == [] and result["pending_requirements"] == [] and result["blockers"] == []


@pytest.mark.parametrize("text", ["Revenue:2027:17万元", "Revenue:2027 17万元", "Revenue:2027年17万元"])
def test_a_bare_year_requires_an_explicit_separator_before_the_scalar_but_the_year_suffix_also_proves_the_boundary(text):
    result = read_series_requirements(text, SOURCE)
    assert result["matched"] is True and result["blockers"] == []
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("Revenue", "17", {"period": "2027年" if "2027年" in text else "2027", "unit": "万元"})]


def test_readers_preserve_caller_state_and_report_every_actual_span():
    declaration = read_series_context("单位：万元", UNIT_SOURCE)
    saved = copy.deepcopy(declaration)
    text = "Revenue：2027年17万元；2026年11万元。"
    result = read_series_requirements(text, SOURCE, context=declaration)
    assert declaration == saved and result["text_projection_complete"] is True
    coverage = [0] * len(text)
    for item in result["consumed_spans"]:
        start, end = item["span"]
        assert item["text"] == text[start:end]
        for position in range(start, end):
            coverage[position] += 1
    assert coverage == [1] * len(text)
