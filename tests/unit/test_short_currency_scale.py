"""Fixed raw-unit and exact-value oracles for explicitly monetary short scales."""

import pytest

from moparse_eval.equivalence import decide_equivalence
from moparse_eval.measurement_evidence import (
    read_measurement_label,
    read_measurement_literal,
    read_unit_token,
)


@pytest.mark.parametrize("unit,full,currency", [("$m", "$ million", None), ("$bn", "$ billion", None),
                                               ("USDm", "USD million", "USD"), ("CNYk", "CNY thousand", "CNY"),
                                               ("EUR mn", "EUR million", "EUR")])
def test_explicit_currency_or_symbol_makes_a_whole_short_scale_without_changing_raw(unit, full, currency):
    token = read_unit_token(unit, {"path": "<printed-unit>", "text_span": [40, 40 + len(unit)]})
    assert token["matched"] is True and token["unit"] == unit and token["currency"] == currency
    assert token["sources"]["unit"]["text_span"] == [40, 40 + len(unit)]
    measured = read_measurement_literal("17" + unit)
    assert measured["matched"] is True and measured["raw"] == "17" + unit and measured["value"] == "17"
    assert measured["unit"] == unit
    header = read_measurement_label("Revenue(" + unit + ")")
    assert header["matched"] is True and header["label"] == "Revenue" and header["unit"] == unit
    decision = decide_equivalence({"value": "17", "unit": unit}, {"value": "17", "unit": full}, "quantity")
    assert decision["equivalent"] is True
    assert decision["canonical"]["required"]["currency"] == currency


def test_a_symbol_short_scale_can_convert_exactly_but_cannot_choose_its_currency():
    item = {"value": "17", "unit": "$m"}
    assert decide_equivalence(item, {"value": "17000000", "unit": "$"}, "quantity")["equivalent"] is True
    assert decide_equivalence(item, {"value": "17000000", "unit": "USD"}, "quantity")["equivalent"] is False


@pytest.mark.parametrize("unit", ["m", "mn", "bn", "k", "month", "m3", "$m3"])
def test_a_bare_length_month_or_unrecognized_token_is_not_a_monetary_short_scale(unit):
    assert read_unit_token(unit)["matched"] is False
    assert read_measurement_literal("17" + unit)["matched"] is False
    assert decide_equivalence({"value": "17", "unit": unit}, {"value": "17000000", "unit": "$"}, "quantity")["equivalent"] is False
