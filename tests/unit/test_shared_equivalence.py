"""Hand-authored exact quantity and final-label decisions, without compiler oracles."""

import copy

import pytest

from moparse_eval.equivalence import decide_equivalence


def quantity(value, unit, currency=None, role=None):
    return {"value": value, "unit": unit, "currency": currency, "quantity_role": role}


@pytest.mark.parametrize("required,actual", [
    (quantity("17", "万元"), quantity("170000", "元")),
    (quantity("17", "万元"), quantity("0.17", "百万元")),
    (quantity("17", "人民币千元"), quantity("17000", "元", "CNY")),
    (quantity("1", "百分点"), quantity("100", "bps")),
    (quantity("1", "%"), quantity("10", "‰")),
])
def test_exact_conversions_preserve_both_original_inputs(required, actual):
    before = copy.deepcopy((required, actual))
    result = decide_equivalence(required, actual, "quantity")
    assert result["equivalent"] is True and result["status"] == "equivalent"
    assert result["rule_id"] and result["proof"]
    assert result["raw"] == {"required": required, "actual": actual}
    assert (required, actual) == before


@pytest.mark.parametrize("required,actual", [
    (quantity("17", "万元"), quantity("170001", "元")),
    (quantity("17", "万元"), quantity("170000", None)),
    (quantity("17", "CNY million"), quantity("17", "USD million")),
    (quantity("1", "%"), quantity("1", "百分点")),
    (quantity("1", "%"), quantity("100", "bps")),
    (quantity("17", "$"), quantity("17", "USD")),
    (quantity("17", "万元"), quantity("0.2", "百万元")),
])
def test_currency_role_missing_units_and_rounding_cannot_supply_exact_equivalence(required, actual):
    result = decide_equivalence(required, actual, "quantity")
    assert result["equivalent"] is False and result["conflicts"]


CONTEXT = {"independent_checks": [
    {"dimension": "subject", "correct": True, "source": {"path": "<own-row>"}},
    {"dimension": "period", "correct": True, "source": {"path": "<own-year>"}},
]}


def test_one_edit_long_label_has_an_actual_final_decision_with_independent_context():
    result = decide_equivalence("Revenue", "Revene", "label", context=CONTEXT)
    assert result["equivalent"] is True
    assert result["rule_id"] == "label_one_edit_with_independent_context"
    assert result["canonical"]["required"] == result["canonical"]["actual"]


@pytest.mark.parametrize("required,actual,dimension,context", [
    ("Revenue", "Revene", "label", {}),
    ("Gross revenue", "Gros revenue", "label", CONTEXT),
    ("Net revenue", "New revenue", "label", CONTEXT),
    ("ROA", "ROE", "label", CONTEXT),
    ("Delta", "Deltx", "entity", CONTEXT),
])
def test_protected_words_short_unknown_labels_and_entities_do_not_use_the_edit_rule(required, actual, dimension, context):
    assert decide_equivalence(required, actual, dimension, context=context)["equivalent"] is False


@pytest.mark.parametrize("required,actual", [("March 31, 2028", "2028-03-31"),
                                           ("Mar31,2028", "2028年3月31日"),
                                           ("2028年03月31日", "March 31, 2028"),
                                           ("二〇二八年三月三十一日", "2028-03-31"),
                                           ("二零二四年十二月三十一日", "31 Dec 2024"),
                                           ("31March2028", "March 31, 2028")])
def test_complete_calendar_dates_share_only_the_same_exact_day(required, actual):
    assert decide_equivalence(required, actual, "period")["equivalent"] is True


@pytest.mark.parametrize("required,actual", [("2028年", "2028-03-31"), ("2028-03-31", "2028-03-30"),
                                           ("2028-02-30", "2028-03-01"), ("2028年度", "2028年"),
                                           ("二〇二八年三月三十二日", "2028-03-31"),
                                           ("31 March 2028", "2028年")])
def test_complete_dates_never_supply_a_year_end_role_or_a_different_calendar_day(required, actual):
    assert decide_equivalence(required, actual, "period")["equivalent"] is False


def test_an_unchanged_unknown_literal_unit_needs_no_inferred_scale():
    decision = decide_equivalence(quantity("17.0", "credits"), quantity("17", "credits"), "quantity")
    assert decision["equivalent"] is True
    assert decision["rule_id"] == "exact_number_same_literal_unit"


def test_a_printed_currency_conflict_cannot_pass_even_when_both_raw_units_are_equal():
    item = {"unit": "USD", "currency": "CNY"}
    assert decide_equivalence(item, item, "unit")["equivalent"] is False
