"""Authored target/candidate unit-scope examples, without corpus access."""

from copy import deepcopy

import pytest

from moparse_eval.matching import match_units
from moparse_eval.scoring import _required_qualifiers, _score_records


def grade(*, header="Movement(%)", value="17", actual="17", candidate_unit=None,
          field_override=None, period=None, candidate_period=None):
    field = {"column_header_path": [header], "value": value}
    if field_override is not None:
        field["unit"] = field_override
    if period is not None:
        field["period"] = period
    reference = {"sample_id": "authored", "review_status": "confirmed", "units": [{
        "id": "record", "kind": "table_record", "status": "confirmed", "pages": [1],
        "literal": "Revenue", "table": {"row_header_path": ["Revenue"],
                                          "unit": "USD million", "fields": [field]},
    }]}
    cell = {"id": "value", "text": actual, "row_header_path": ["Revenue"],
            "column_header_path": [header], "units": ["USD million"]}
    if candidate_unit is not None:
        cell["unit"] = candidate_unit
    if candidate_period is not None:
        cell["period"] = candidate_period
    observation = {"sample_id": "authored", "pages": [{"page": 1, "blocks": [{
        "id": "table", "kind": "table", "cells": [cell],
    }]}]}
    before = deepcopy((reference, observation))
    targets = [{**row, "reference_text": row["literal"]} for row in reference["units"]]
    matching = match_units(targets, observation, threshold=0.8, collapse_whitespace=True)
    units, metrics = _score_records(targets, observation, True, matching)
    assert (reference, observation) == before
    assert metrics["target_fields"] == metrics["graded_fields"] == 1
    assert metrics["information_correct_fields"] + metrics["information_incorrect_fields"] == 1
    return units[0]["fields"][0]


@pytest.mark.parametrize("header", ["Movement(%)", "本年比上年增减（%）", "Variation(‰)"])
def test_local_printed_ratio_overrides_a_wider_target_and_candidate_amount_caption(header):
    field = grade(header=header)
    assert field["outcome"] == "correct"
    expected = "‰" if "‰" in header else "%"
    assert field["information"]["qualifiers"]["unit"]["actual"] == [
        {"actual": expected, "source": "candidate_scoped_unit"}]


@pytest.mark.parametrize("value", ["17%", "(17%)", "17‰"])
def test_literal_ratio_value_also_precedes_a_wider_target_caption(value):
    assert grade(header="Variation", value=value, actual=value)["outcome"] == "correct"


def test_plain_amount_still_requires_the_actual_table_currency_scale():
    assert grade(header="2027", candidate_unit="USD million")["outcome"] == "correct"
    assert grade(header="2027", candidate_unit="%")["outcome"] == "incorrect"


def test_an_explicit_wrong_candidate_unit_cannot_be_repaired_from_a_reference_label():
    assert grade(candidate_unit="USD million")["outcome"] == "incorrect"


def test_field_override_and_explicit_null_are_not_overwritten_by_header_reading():
    table = {"unit": "USD million"}
    assert _required_qualifiers(table, {"column_header_path": ["Variation(%)"], "unit": "EUR"}) == {"unit": "EUR"}
    assert _required_qualifiers(table, {"column_header_path": ["Variation(%)"], "unit": None}) == {}


def test_no_ratio_unit_is_invented_from_a_bare_business_label():
    assert _required_qualifiers({"unit": "USD million"}, {
        "column_header_path": ["Variation"], "value": "17"}) == {"unit": "USD million"}


@pytest.mark.parametrize("actual", ["-17", "18", "17.0"])
def test_ratio_scope_does_not_repair_wrong_sign_digits_or_decimal_spelling(actual):
    assert grade(actual=actual)["outcome"] == "incorrect"


def test_local_unit_reading_does_not_repair_a_wrong_period():
    assert grade(period="2027", candidate_period="2026")["outcome"] == "incorrect"
