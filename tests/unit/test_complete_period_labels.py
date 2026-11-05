"""Printed whole period selectors; dates and grains are authored independently."""

import pytest

from moparse_eval.field_sequence_requirements import read_field_sequence_requirements
from moparse_eval.period_evidence import calendar_date, read_period_label

SOURCE = {"path": "<printed-period>", "lines": [9, 9]}


@pytest.mark.parametrize("raw,iso", [
    ("二零二四年十二月三十一日", "2024-12-31"),
    ("二〇二八年三月三十一日", "2028-03-31"),
    ("2028年6月30日", "2028-06-30"),
    ("31 Dec 2024", "2024-12-31"),
    ("31December2024", "2024-12-31"),
])
def test_complete_calendar_forms_preserve_exact_day(raw, iso):
    assert calendar_date(raw) == iso


@pytest.mark.parametrize("raw,period,basis,unit", [
    ("截至二零二四年十二月三十一日止年度（人民幣）", "二零二四年十二月三十一日", "止年度", "人民幣"),
    ("截至二〇二八年三月三十一日止六个月", "二〇二八年三月三十一日", "止六个月", None),
    ("At 31 Dec 2024", "31 Dec 2024", "At", None),
    ("As of December 31, 2024 ($m)", "December 31, 2024", "As of", "$m"),
    ("For the six months ended 30 June 2028", "30 June 2028", "For the six months ended", None),
])
def test_period_selector_keeps_whole_date_grain_and_own_literal_sources(raw, period, basis, unit):
    parsed = read_period_label(raw, SOURCE)
    assert parsed["matched"] is True
    assert parsed["qualifiers"]["period"] == period
    assert parsed["qualifiers"]["period_basis"] == basis
    assert parsed["qualifiers"].get("unit") == unit
    for key, source in parsed["qualifier_sources"].items():
        a, b = source["text_span"]
        assert raw[a:b] == parsed["qualifiers"][key]


def test_chinese_fiscal_sequence_uses_each_printed_basis_and_date_without_year_truncation():
    raw = "Revenue; 截至二零二四年十二月三十一日止年度（人民幣）:17; 截至二零二三年十二月三十一日止年度（人民幣）:11"
    result = read_field_sequence_requirements(raw, SOURCE)
    assert result["blockers"] == []
    assert [(f["attribute"], f["value"], f["qualifiers"]["period"], f["qualifiers"]["period_basis"])
            for f in result["facts"]] == [
        ("Revenue", "17", "二零二四年十二月三十一日", "止年度"),
        ("Revenue", "11", "二零二三年十二月三十一日", "止年度")]
    assert result["text_projection_complete"] is True


@pytest.mark.parametrize("raw", ["截至二零二四年十二月三十二日止年度", "FY2024", "From 2023 to 2024",
                                 "Year started March 31, 2024", "截至二零二四年十二月止年度"])
def test_invalid_partial_or_different_period_operators_are_not_guessed(raw):
    assert read_period_label(raw, SOURCE)["matched"] is False
