"""Synthetic scope and business-value counterexamples; no corpus access."""

from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells
from moparse_eval.scoring import score_case


def evaluate(html, *, row="Revenue", column="2024", value="17", unit=None, before=(), after=(), extra=()):
    field = {"column_header_path": [column], "value": value}
    if unit is not None:
        field["unit"] = unit
    ref = {"sample_id": "invented", "review_status": "confirmed", "units": [{
        "id": "r", "kind": "table_record", "literal": row, "status": "confirmed", "pages": [1],
        "table": {"row_header_path": row.split(" / "), "fields": [field]},
    }]}
    obs = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [*before, {
        "id": "table", "kind": "table", "cells": html_cells(html),
    }, *after, *extra]}]}
    prior = deepcopy((ref, obs))
    result = score_case(ref, obs)
    assert (ref, obs) == prior
    return result["units"][0]["fields"][0]


TABLE = '<table><tr><td>(人民币百万元)</td><td>2024</td><td>2023</td><td>同比</td></tr><tr><td>Revenue</td><td>17</td><td>11</td><td>5%</td></tr></table>'


def test_corner_currency_is_scoped_to_amount_columns():
    assert evaluate(TABLE, unit="人民币百万元")["information"]["status"] == "correct"
    assert evaluate(TABLE, column="同比", value="5%", unit="%")["information"]["status"] == "correct"
    assert evaluate(TABLE, column="同比", value="5%", unit="人民币百万元")["information"]["status"] == "incorrect"


def test_swapped_period_columns_do_not_find_the_expected_value_elsewhere():
    f = evaluate(TABLE.replace('<td>2024</td><td>2023</td>', '<td>2023</td><td>2024</td>'), unit="人民币百万元")
    assert f["native_text"] == "11" and f["information"]["status"] == "incorrect"


@pytest.mark.parametrize("actual,expected,correct", [("100.0%", "100.0", True), ("(0.2%)", "(0.2)", True),
                                                     ("0.2%", "(0.2)", False), ("100%", "100.0", False)])
def test_explicit_unit_scalar_equivalence_keeps_decimal_and_accounting_sign(actual, expected, correct):
    table = f'<table><tr><th>Metric</th><th>2024</th></tr><tr><td>Revenue</td><td>{actual}</td></tr></table>'
    f = evaluate(table, value=expected, unit="%")
    assert f["content_exact"] is correct
    assert f["strict_exact"] is False


def test_bare_percent_without_candidate_unit_is_not_confirmed_correct():
    table = '<table><tr><th>Metric</th><th>2024</th></tr><tr><td>Revenue</td><td>17</td></tr></table>'
    assert evaluate(table, unit="%")["information"]["status"] == "unresolved"
    introduction = {"id": "p", "kind": "text", "text": "The following table is expressed as a percentage of revenue."}
    assert evaluate(table, unit="%", before=[introduction])["information"]["status"] == "correct"
    unrelated = {"id": "p", "kind": "text", "text": "A separate operation earned 17%."}
    assert evaluate(table, unit="%", before=[unrelated])["information"]["status"] == "unresolved"


def test_neighbouring_table_does_not_lend_its_unit_or_total():
    other = {"id": "other", "kind": "table", "cells": html_cells(TABLE, "#/other")}
    table = '<table><tr><th>Metric</th><th>2024</th></tr><tr><td>Total</td><td>17</td></tr></table>'
    f = evaluate(table, row="Total", unit="人民币百万元", extra=[other])
    assert f["information"]["status"] == "unresolved"


def test_empty_section_rows_scope_repeated_labels_without_borrowing_another_group():
    table = '<table><tr><td>Metric</td><td>2024</td></tr><tr><td>North:</td><td></td></tr><tr><td>Other</td><td>17</td></tr><tr><td>South:</td><td></td></tr><tr><td>Other</td><td>11</td></tr></table>'
    assert evaluate(table, row="North / Other")["information"]["status"] == "correct"
    f = evaluate(table, row="South / Other")
    assert f["native_text"] == "11" and f["information"]["status"] == "incorrect"


@pytest.mark.parametrize("annotation", ['17<sup>4</sup>', r'\( 17^4 \)'])
def test_superscript_needs_an_actual_scoped_note_definition(annotation):
    table = f'<table><tr><th>Metric</th><th>2024</th></tr><tr><td>Revenue</td><td>{annotation}</td></tr></table>'
    assert evaluate(table)["information"]["status"] == "incorrect"
    note = {"id": "note", "kind": "table_footnote", "text": "4 Record high."}
    f = evaluate(table, after=[note])
    assert f["native_note_markers"] == ["4"] and f["information"]["status"] == "correct"
    barrier = {"id": "next", "kind": "title", "text": "Another business"}
    assert evaluate(table, after=[barrier, note])["information"]["status"] == "incorrect"


def test_attached_chinese_currency_can_be_read_without_matching_other_business_words():
    table = '<table><tr><td>Metric</td><td>金額人民幣千元</td></tr><tr><td>Other business</td><td>17</td></tr></table>'
    assert evaluate(table, row="Other business", column="金額", unit="人民幣千元")["information"]["status"] == "correct"
    assert evaluate(table, row="Other", column="金額")["status"] == "unresolved"
