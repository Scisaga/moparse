"""Hand-authored period, source-unit and unresolved-tail series contracts."""

from copy import deepcopy

import pytest

from moparse_eval.scalar_evidence import validate_scalar_sources
from moparse_eval.series_requirements import read_series_requirements
from moparse_eval.three_layer import compile_markdown


def source(text, offset=0):
    return {"path": "<invented-series-positions>", "lines": [7, 7], "text_span": [offset, offset + len(text)]}


def signatures(result):
    return [(f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]]


@pytest.mark.parametrize("offset", [0, 40])
def test_explicit_quarters_and_the_printed_total_are_independent_positions_with_source_units(offset):
    text = "Fees / $m: Q1 2028:17; Q2 2028:11; Q3 2028:19; Q4 2028:13; Total 2028:999."
    origin = source(text, offset)
    before = deepcopy(origin)
    result = read_series_requirements(text, origin)
    assert origin == before and result["matched"] is True and result["blockers"] == []
    assert signatures(result) == [
        ("Fees", "17", {"unit": "$m", "period": "Q1 2028"}),
        ("Fees", "11", {"unit": "$m", "period": "Q2 2028"}),
        ("Fees", "19", {"unit": "$m", "period": "Q3 2028"}),
        ("Fees", "13", {"unit": "$m", "period": "Q4 2028"}),
        ("Fees", "999", {"unit": "$m", "period": "Total 2028"}),
    ]
    for f, period, value in zip(result["facts"], ("Q1 2028", "Q2 2028", "Q3 2028", "Q4 2028", "Total 2028"),
                                ("17", "11", "19", "13", "999"), strict=True):
        assert f["attribute_source"]["text_span"] == [offset, offset + 4]
        assert f["qualifier_sources"]["unit"]["text_span"] == [offset + 7, offset + 9]
        a, b = f["qualifier_sources"]["period"]["text_span"]
        assert text[a - offset:b - offset] == period
        a, b = f["value_source"]["text_span"]
        assert text[a - offset:b - offset] == value
        assert "currency" not in f["qualifiers"]
    last = result["facts"][-1]
    assert last["role_basis"]["period_selector"]["kind"] == "annual_total"
    assert last["role_basis"]["period_selector"]["text"] == "Total 2028"
    assert result["text_projection_complete"] is True
    validate_scalar_sources(result["facts"], {"source_fragments": [{"source": origin, "text": text}]}, canonicalize=str.strip)


@pytest.mark.parametrize("period", ["Quarter 1 2028", "2028 Q1", "2028年第一季度"])
def test_other_explicit_quarter_year_forms_keep_their_own_full_selector(period):
    text = f"Revenue:{period}:17万元"
    result = read_series_requirements(text, source(text))
    assert result["blockers"] == []
    assert signatures(result) == [("Revenue", "17", {"period": period, "unit": "万元"})]


@pytest.mark.parametrize("offset", [0, 40])
def test_adjacent_full_valid_calendar_selectors_are_not_truncated_to_a_year(offset):
    text = "Assets / CNYm:2028年3月31日17；2027年3月31日11；同比变动5%。"
    origin = source(text, offset)
    result = read_series_requirements(text, origin)
    assert signatures(result) == [
        ("Assets", "17", {"unit": "CNYm", "currency": "CNY", "period": "2028年3月31日"}),
        ("Assets", "11", {"unit": "CNYm", "currency": "CNY", "period": "2027年3月31日"}),
        ("同比变动", "5", {"unit": "%"}),
    ]
    for f, period in zip(result["facts"][:2], ("2028年3月31日", "2027年3月31日"), strict=True):
        a, b = f["qualifier_sources"]["period"]["text_span"]
        assert text[a - offset:b - offset] == period
        assert f["role_basis"]["period_selector"]["kind"] == "calendar_day"
        assert "period_basis" not in f["qualifiers"]
    assert any(p["text"] == "同比变动5%" for p in result["pending_requirements"])
    assert any(b["reason"] == "series_comparison_periods_unresolved" for b in result["blockers"])
    assert not any("from_period" in f["qualifiers"] or "to_period" in f["qualifiers"] for f in result["facts"])
    validate_scalar_sources(result["facts"], {"source_fragments": [{"source": origin, "text": text}]}, canonicalize=str.strip)


@pytest.mark.parametrize("selector", ["2028年2月30日", "2028年3月", "Q5 2028", "Q1"])
def test_invalid_partial_or_yearless_periods_keep_the_whole_obligation_unresolved(selector):
    text = f"Assets:{selector}:17万元"
    result = read_series_requirements(text, source(text))
    assert result["matched"] is True and result["facts"] == []
    assert result["pending_requirements"] and result["blockers"]
    assert any(selector in p["text"] and "17万元" in p["text"] for p in result["pending_requirements"])


def test_an_english_change_is_not_bound_to_endpoints_and_a_numeric_superscript_is_not_a_footnote():
    text = "Cash / $m:2028:17⁴;2027:11;Change:24%."
    result = read_series_requirements(text, source(text))
    assert signatures(result) == [("Cash", "11", {"unit": "$m", "period": "2027"})]
    assert any(p["text"] == "17⁴" for p in result["pending_requirements"])
    assert any(p["text"] == "Change:24%." for p in result["pending_requirements"])
    assert not any(f["value"] in {"17", "174", "24"} for f in result["facts"])


def test_an_ordinary_slash_label_is_not_erased_as_a_unit_declaration():
    text = "Assets / liabilities:2028:17;2027:11"
    result = read_series_requirements(text, source(text))
    assert result["blockers"] == []
    assert signatures(result) == [("Assets / liabilities", "17", {"period": "2028"}),
                                  ("Assets / liabilities", "11", {"period": "2027"})]


def test_public_source_graph_keeps_the_explicit_quarter_and_total_roles_without_scoring():
    raw = "Fees / $m: Q1 2028:17; Total 2028:999."
    graph = compile_markdown(raw, sample_id="invented-series-source-entry")
    assert graph["blockers"] == []
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
        ("Fees", "17", {"unit": "$m", "period": "Q1 2028"}),
        ("Fees", "999", {"unit": "$m", "period": "Total 2028"})]
    assert [f["role_basis"]["period_selector"]["kind"] for f in graph["business"]] == ["quarter", "annual_total"]
    validate_scalar_sources(graph["business"], graph["text_projection"], canonicalize=str.strip)
