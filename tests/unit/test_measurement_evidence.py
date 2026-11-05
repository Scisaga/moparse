"""Independent raw-text oracles for bounded units and unscaled quantities."""

from copy import deepcopy

import pytest

from moparse_eval.measurement_evidence import (
    read_measurement_label,
    read_measurement_literal,
    read_unit_token,
)

SOURCE = {"path": "<printed-measurement>", "lines": [7, 7]}


@pytest.mark.parametrize("unit,currency", [
    ("人民币千元", "人民币"), ("人民幣百萬元", "人民幣"), ("万元人民币", "人民币"),
    ("千元", None), ("万元", None), ("美元", "美元"), ("USD", "USD"), ("RMB million", "RMB"),
    ("%", None), ("‰", None), ("人", None), ("万股", None), ("元/股", None),
])
def test_whole_explicit_unit_tokens_keep_the_complete_printed_literal(unit, currency):
    result = read_unit_token(unit, SOURCE)
    assert result["matched"] is True
    assert result["unit"] == unit and result["unit_span"] == [0, len(unit)]
    assert result["currency"] == currency
    assert result["sources"]["unit"] == {**SOURCE, "text_span": [0, len(unit)]}


@pytest.mark.parametrize("text", ["17%", "17人", "17人民币千元", "Count", "Type17", "mystery-unit", "USD/RMB"])
def test_quantities_and_business_words_are_never_unit_only_tokens(text):
    result = read_unit_token(text, SOURCE)
    assert result["matched"] is False and result["unit"] is None and result["currency"] is None


@pytest.mark.parametrize("text,value,unit,currency", [
    ("17人民币千元", "17", "人民币千元", "人民币"),
    ("17美元", "17", "美元", "美元"),
    ("17万元", "17", "万元", None),
    ("17千元", "17", "千元", None),
    ("17%", "17", "%", None),
    ("17‰", "17", "‰", None),
    ("(17.5)人民币千元", "(17.5)", "人民币千元", "人民币"),
    ("-1,234.50美元", "-1,234.50", "美元", "美元"),
    ("0017", "0017", None, None),
    ("USD 17", "17", "USD", "USD"),
])
def test_measurements_keep_unscaled_number_spelling_and_only_their_own_unit(text, value, unit, currency):
    result = read_measurement_literal(text, SOURCE)
    assert result["matched"] is True
    assert (result["value"], result["unit"], result["currency"]) == (value, unit, currency)
    assert result["raw"] == text
    assert text[slice(*result["value_span"])] == value
    assert result["sources"]["value"]["text_span"] == result["value_span"]
    if unit:
        assert text[slice(*result["unit_span"])] == unit
    if currency:
        assert text[slice(*result["currency_span"])] == currency


@pytest.mark.parametrize("symbol", ["$", "¥", "£", "€"])
def test_a_currency_symbol_is_preserved_without_guessing_its_currency_code(symbol):
    result = read_measurement_literal(f"{symbol}17", SOURCE)
    assert result["matched"] is True and result["value"] == "17"
    assert result["unit"] == symbol and result["currency_symbol"] == symbol
    assert result["currency"] is None and result["currency_span"] is None
    assert "currency" not in result["sources"]


@pytest.mark.parametrize("label", ["Revenue(17%)", "Count(17人)", "Type17", "Revenue", "Revenue(mystery-unit)"])
def test_parenthesized_values_and_opaque_labels_remain_the_original_label(label):
    result = read_measurement_label(label, SOURCE)
    assert result["matched"] is False
    assert result["label"] == label and result["unit"] is None


@pytest.mark.parametrize("label,unit,currency", [
    ("Revenue（人民币千元）", "人民币千元", "人民币"), ("Revenue(美元)", "美元", "美元"),
    ("Margin (%)", "%", None), ("Count（人）", "人", None),
])
def test_a_terminal_full_unit_declaration_can_be_read_without_a_dummy_numeric_prefix(label, unit, currency):
    result = read_measurement_label(label, SOURCE)
    assert result["matched"] is True and result["label"] in {"Revenue", "Margin", "Count"}
    assert (result["unit"], result["currency"]) == (unit, currency)
    assert label[slice(*result["label_span"])] == result["label"]
    assert label[slice(*result["unit_span"])] == unit
    assert result["sources"]["unit"]["text_span"] == result["unit_span"]


@pytest.mark.parametrize("text", [
    "9:00", "2028-05-02 9:00", "https://example.test/Room17", "Type17", "Type17 Revenue",
    "17 mystery-unit", "17,11元", "17、60%", "17万元/unknown", "17e3元", "$17USD",
])
def test_times_urls_identifiers_tuples_and_unsupported_compound_units_are_not_partial_measurements(text):
    result = read_measurement_literal(text, SOURCE)
    assert result["matched"] is False and result["raw"] == text
    assert result["value"] is None and result["unit"] is None and result["currency"] is None


def test_unit_currency_and_percent_differences_remain_literal_differences():
    results = [read_measurement_literal(text, SOURCE) for text in ["17万元", "17千元", "17RMB", "17USD", "17%", "17‰"]]
    assert [(result["value"], result["unit"], result["currency"]) for result in results] == [
        ("17", "万元", None), ("17", "千元", None), ("17", "RMB", "RMB"),
        ("17", "USD", "USD"), ("17", "%", None), ("17", "‰", None)]


def test_sources_keep_their_parent_offset_without_mutating_the_caller():
    source = {**SOURCE, "text_span": [40, 51]}
    before = deepcopy(source)
    result = read_measurement_literal(" 17人民币千元 ", source)
    assert source == before
    assert result["value_span"] == [1, 3] and result["unit_span"] == [3, 8]
    assert result["sources"]["value"]["text_span"] == [41, 43]
    assert result["sources"]["unit"]["text_span"] == [43, 48]
    assert result["sources"]["currency"]["text_span"] == [43, 46]
