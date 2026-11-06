"""Fixed literal oracles for the independent matrix and annual readers."""

import pytest

from moparse_eval.adapters import html_cells
from moparse_eval.matrix_evidence import read_matrix
from moparse_eval.series_requirements import read_series_requirements

SOURCE = {"path": "<independent-printed-units>", "lines": [7, 7]}


def matrix(label, value):
    cells = html_cells(f'<table><tr><th scope="col">{label}</th></tr><tr><td>{value}</td></tr></table>')
    return read_matrix(cells, source=SOURCE)


def series(label, value):
    return read_series_requirements(f"{label}:2027年{value}", SOURCE)


@pytest.mark.parametrize("reader", [matrix, series])
@pytest.mark.parametrize("label", ["Revenue(17%)", "Count(17人)"])
def test_a_parenthesized_quantity_remains_the_complete_original_metric_label(reader, label):
    result = reader(label, "5")
    assert result["blockers"] == []
    assert len(result["facts"]) == 1
    fact = result["facts"][0]
    assert fact["attribute"] == label and fact["value"] == "5"
    assert "unit" not in fact["qualifiers"] and "currency" not in fact["qualifiers"]


@pytest.mark.parametrize("reader", [matrix, series])
@pytest.mark.parametrize("literal,unit,currency", [
    ("17人民币千元", "人民币千元", "人民币"), ("17美元", "美元", "美元"),
    ("17万元人民币", "万元人民币", "人民币"), ("17元/股", "元/股", None),
    ("17%", "%", None), ("17‰", "‰", None),
])
def test_inline_full_units_keep_the_same_unscaled_literal_and_own_currency(reader, literal, unit, currency):
    result = reader("Revenue", literal)
    assert result["blockers"] == []
    assert len(result["facts"]) == 1
    fact = result["facts"][0]
    assert fact["value"] == "17"
    assert fact["qualifiers"]["unit"] == unit
    assert fact["qualifiers"].get("currency") == currency
    assert fact["source"]["path"] == SOURCE["path"]


@pytest.mark.parametrize("reader", [matrix, series])
@pytest.mark.parametrize("unit,currency", [("元/股", None), ("万元人民币", "人民币")])
def test_a_valid_complete_unit_in_a_header_is_not_an_opaque_or_partly_truncated_label(reader, unit, currency):
    result = reader(f"Revenue({unit})", "17")
    assert result["blockers"] == [] and len(result["facts"]) == 1
    fact = result["facts"][0]
    assert fact["attribute"] == "Revenue" and fact["value"] == "17"
    assert fact["qualifiers"]["unit"] == unit
    assert fact["qualifiers"].get("currency") == currency


@pytest.mark.parametrize("reader", [matrix, series])
def test_a_dollar_symbol_stays_an_explicit_unit_without_becoming_a_currency_name(reader):
    result = reader("Revenue", "$17")
    assert result["blockers"] == [] and len(result["facts"]) == 1
    fact = result["facts"][0]
    assert fact["value"] == "17" and fact["qualifiers"]["unit"] == "$"
    assert "currency" not in fact["qualifiers"]


@pytest.mark.parametrize("reader", [matrix, series])
def test_identity_strings_ending_in_currency_words_are_not_rewritten_as_amounts(reader):
    if reader is series:
        # This helper prints a complete YYYY-year-prefixed identity literal.
        # A Name field does not authorize splitting it into period and amount.
        from moparse_eval.three_layer import compile_markdown

        text = "Name:2027年17美元"
        result = read_series_requirements(text, SOURCE)
        assert result["matched"] is False
        assert result["facts"] == result["blockers"] == result["pending_requirements"] == []
        graph = compile_markdown(text, sample_id="invented-year-prefixed-identity")
        [fact] = graph["business"]
        assert (fact["attribute"], fact["role"], fact["value"], fact["qualifiers"]) == ("Name", "identity", "2027年17美元", {})
        assert graph["blockers"] == []
        assert text[fact["source"]["text_span"][0]:fact["source"]["text_span"][1]] == "2027年17美元"
        return
    result = reader("Name", "17美元")
    assert result["blockers"] == [] and len(result["facts"]) == 1
    fact = result["facts"][0]
    assert fact["role"] == "identity" and fact["value"] == "17美元"
    assert "unit" not in fact["qualifiers"] and "currency" not in fact["qualifiers"]


@pytest.mark.parametrize("reader", [matrix, series])
@pytest.mark.parametrize("literal,unit,currency", [("-万元", "万元", None), ("-人民币千元", "人民币千元", "人民币")])
def test_an_explicit_missing_marker_is_preserved_with_its_own_full_unit(reader, literal, unit, currency):
    result = reader("Revenue", literal)
    assert result["blockers"] == [] and len(result["facts"]) == 1
    fact = result["facts"][0]
    assert fact["value"] == "-" and fact["qualifiers"]["unit"] == unit
    assert fact["qualifiers"].get("currency") == currency
