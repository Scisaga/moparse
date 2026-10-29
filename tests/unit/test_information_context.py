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
    bare_change = TABLE.replace('<td>Revenue</td>', '<td>Revenue (人民币百万元)</td>').replace('<td>5%</td>', '<td>5</td>')
    f = evaluate(bare_change, row="Revenue (人民币百万元)", column="同比", value="5", unit="人民币百万元")
    assert f["information"]["status"] != "correct"


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
    assert f["raw_transcription"]["strict"]["distance"] > 0
    barrier = {"id": "next", "kind": "title", "text": "Another business"}
    assert evaluate(table, after=[barrier, note])["information"]["status"] == "incorrect"


def test_attached_chinese_currency_can_be_read_without_matching_other_business_words():
    table = '<table><tr><td>Metric</td><td>金額人民幣千元</td></tr><tr><td>Other business</td><td>17</td></tr></table>'
    assert evaluate(table, row="Other business", column="金額", unit="人民幣千元")["information"]["status"] == "correct"
    assert evaluate(table, row="Other", column="金額")["status"] == "unresolved"


def test_untyped_local_header_switch_does_not_lend_a_period_from_the_previous_scope():
    table = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>Alpha</td><td>17</td></tr><tr><td>Item</td><td>2023</td></tr><tr><td>Beta</td><td>11</td></tr></table>'
    assert evaluate(table, row="Beta", column="2023", value="11")["information"]["status"] == "correct"
    assert evaluate(table, row="Beta", column="2024", value="11")["status"] == "unresolved"


def test_a_group_total_ends_the_group_scope_for_later_records():
    table = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>Expenses</td><td></td></tr><tr><td>Research</td><td>17</td></tr><tr><td>Total expenses</td><td>17</td></tr><tr><td>Profit</td><td>11</td></tr></table>'
    assert evaluate(table, row="Expenses / Research")["information"]["status"] == "correct"
    assert evaluate(table, row="Expenses / Profit", value="11")["status"] == "unresolved"


def test_repeated_total_uses_the_actual_table_scope_across_separate_rendered_records():
    reference = {"sample_id": "invented", "review_status": "confirmed", "units": [
        {"id": identity, "kind": "table_record", "status": "confirmed", "literal": label, "pages": [1],
         "table": {"id": "authored-scope-a", "row_header_path": [label],
                   "fields": [{"column_header_path": ["2024"], "value": value}]}}
        for identity, label, value in [("anchor", "Alpha", "11"), ("total", "Total", "17")]]}
    blocks = []
    for identity, container, label, value in [("alpha", "table-a", "Alpha", "11"),
                                               ("total-a", "table-a", "Total", "17"),
                                               ("total-b", "table-b", "Total", "99")]:
        blocks.append({"id": identity, "native_table_container": container, "parent_id": container,
                       "kind": "table_body", "cells": [{"id": identity + ":r", "text": label, "is_row_header": True},
                       {"id": identity + ":c", "text": "2024", "is_column_header": True},
                       {"id": identity + ":v", "text": value,
                       "row_header_path": [label], "column_header_path": ["2024"]}]})
    observation = {"sample_id": "invented", "pages": [{"page": 1, "blocks": blocks}],
                   "native_containers": [{"id": table, "label": "table"} for table in ("table-a", "table-b")]}
    result = score_case(reference, observation)
    total = next(row for row in result["units"] if row["id"] == "total")["fields"][0]
    assert total["native_text"] == "17" and total["information"]["status"] == "correct"
    # Removing the independent table anchor cannot select the favorable total.
    observation["pages"][0]["blocks"].pop(0)
    result = score_case(reference, observation)
    total = next(row for row in result["units"] if row["id"] == "total")["fields"][0]
    assert total["status"] == "unresolved"


def test_column_qualifier_layout_can_vary_without_skipping_business_groups_or_years():
    from moparse_eval.information import column_path_locates, path_locates
    assert column_path_locates(["2024年", "金額"], ["截至12月31日止年度", "2024年", "金額人民幣千元"], True)
    assert column_path_locates(["Change"], ["Year Ended", "Change"], True)
    assert column_path_locates(["Year Ended", "2024"], ["Year Ended", "2024", "$m"], True)
    assert not column_path_locates(["2024", "Amount"], ["2023", "Amount"], True)
    assert not column_path_locates(["Amount"], ["Group", "Amount"], True)
    assert not path_locates(["Other"], ["North", "Other"], True)
    assert path_locates(["North", "Other"], ["North:", "Other"], True)


def test_unit_lexer_keeps_scale_and_compound_denominator_instead_of_short_suffixes():
    from moparse_eval.information_reading import units
    assert units("单位：1000元") == ["1000元"]
    assert units("单位(1000元)") == ["1000元"]
    assert units("单位：百万股") == ["百万股"]
    assert units("单位：元/股") == ["元/股"]
    assert units("(人民币亿元)") == ["人民币亿元"]
    assert units("(毫克/立方米)") == ["毫克/立方米"]
    assert units("单位：元 币种：人民币") == ["元"]
    assert units("单位：元币种：人民币") == ["元"]
    from moparse_eval.information import qualifier_evidence
    assert qualifier_evidence({"unit": "万元"}, {"unit": "(万元)"}, [])["unit"]["status"] == "correct"
    assert qualifier_evidence({"unit": "元"}, {"unit": "1000元"}, [])["unit"]["status"] == "incorrect"
    assert qualifier_evidence({"unit": "股"}, {"unit": "(元/股)"}, [])["unit"]["status"] == "incorrect"
    assert qualifier_evidence({"unit": "元/股"}, {"unit": "(元 / 股)"}, [])["unit"]["status"] == "correct"
    assert qualifier_evidence({"unit": "元"}, {"units": ["元/股"]}, [])["unit"]["status"] == "incorrect"
    assert qualifier_evidence({"unit": "$m"}, {"units": ["$bn"]}, [])["unit"]["status"] == "incorrect"


def test_shared_currency_scale_exception_for_explicit_per_share_records():
    html = '<table><tr><td>Item</td><td>2024</td></tr><tr><td colspan="2">($ in millions, except per share data)</td></tr><tr><td>Revenue</td><td>$ 17</td></tr><tr><td>Net income per diluted share</td><td>$ 0.17</td></tr></table>'
    assert evaluate(html, value="$17", unit="$ in millions")["information"]["status"] == "correct"
    assert evaluate(html, value="$17", unit="$")["information"]["status"] == "incorrect"
    assert evaluate(html, row="Net income per diluted share", value="$0.17", unit="$")["information"]["status"] == "correct"


def test_explicit_enumerated_sibling_stops_the_previous_group_scope():
    table = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>二、Category</td><td></td></tr><tr><td>Child</td><td>17</td></tr><tr><td>三、Total</td><td>11</td></tr></table>'
    assert evaluate(table, row="三、Total", value="11")["information"]["status"] == "correct"
    assert evaluate(table, row="二、Category / 三、Total", value="11")["status"] == "unresolved"


def test_explicit_record_path_units_are_read_without_lending_currency_to_change():
    from moparse_eval.information import qualifier_evidence
    cell = {"text": "17", "row_header_path": ["Trading ($bn)"], "column_header_path": ["2024"]}
    assert qualifier_evidence({"unit": "$bn"}, cell, [])["unit"]["status"] == "correct"
    cell["column_header_path"] = ["Change"]
    assert qualifier_evidence({"unit": "$bn"}, cell, [])["unit"]["status"] != "correct"
    cell["column_header_path"] = ["2024"]
    cell["row_header_path"] = ["Other trading"]
    assert qualifier_evidence({"unit": "$bn"}, cell, [])["unit"]["status"] != "correct"


def test_math_wrapper_is_a_footnote_only_with_an_actually_emitted_definition():
    from moparse_eval.information_reading import scalar_notes
    marked = {"text": r"\( 17^4 \)", "notes": ["4 Declared source note"]}
    assert scalar_notes(marked) == ("17", ["4"])
    assert scalar_notes({"text": marked["text"]}) == (marked["text"], None)
    assert scalar_notes({"text": "17^4", "notes": marked["notes"]}) == ("17^4", None)
    assert scalar_notes({"text": r"\( 17^3 \)", "notes": marked["notes"]}) == (r"\( 17^3 \)", None)


def test_single_annual_section_period_survives_attached_business_words():
    from moparse_eval.information import qualifier_evidence
    cell = {"text": "17", "periods": ["（3）2024年度排放情况："]}
    assert qualifier_evidence({"period": "2024年度"}, cell, [])["period"]["status"] == "correct"
    assert qualifier_evidence({"period": "2023年度"}, cell, [])["period"]["status"] != "correct"
    for text in ("2024年度至2025年度排放情况：", "2024年度与2023年度排放情况："):
        assert qualifier_evidence({"period": "2024年度"}, {"text": "17", "periods": [text]}, [])["period"]["status"] != "correct"
    for value in ("2024", "2024年", "2024年度"):
        assert qualifier_evidence({"period": value}, {"text": "17", "periods": ["2024年–2025年"]}, [])["period"]["status"] != "correct"
    unrelated = {"text": "17", "information_context": [{"kind": "paragraph", "text": "Unrelated 2024年度 paragraph"}]}
    assert qualifier_evidence({"period": "2024年度"}, unrelated, [])["period"]["status"] != "correct"


def test_visible_column_units_can_be_printed_as_separate_qualifiers():
    from moparse_eval.information import column_path_locates
    assert column_path_locates(["2024", "(人民币百万元)"], ["2024"], True, ["(人民币百万元)"])
    assert not column_path_locates(["2024", "(人民币百万元)"], ["2024"], True, ["(美元百万元)"])
    assert column_path_locates(["2024年", "金額"], ["於12月31日", "2024年", "金額 人民幣千元"], True)
    assert not column_path_locates(["2024年", "金額"], ["於2023年12月31日", "2024年", "金額"], True)


def test_row_path_keeps_all_annotated_business_levels_and_only_adds_leading_context():
    from moparse_eval.information import row_path_locates
    assert row_path_locates(["North", "Other"], ["Company", "North", "Other"], True)
    assert not row_path_locates(["North", "Other"], ["South", "Other"], True)
    assert not row_path_locates(["North", "Other"], ["North", "South", "Other"], True)
    assert not row_path_locates(["Other"], [None, "Other"], True)
    assert not row_path_locates(["Other"], ["", "Other"], True)
    assert row_path_locates(["Revenue"], ["Revenue (USD)"], True)
    assert not row_path_locates(["Revenue"], ["Revenue and other income"], True)
    assert not row_path_locates(["Revenue and other income"], ["Revenue and other income less expenses"], True)


def test_extra_leading_context_still_requires_a_unique_full_target_and_never_selects_by_value():
    ref = {"sample_id": "invented", "review_status": "confirmed", "units": [{
        "id": "other", "kind": "table_record", "literal": "Other", "status": "confirmed", "pages": [1],
        "table": {"row_header_path": ["Other"], "fields": [{"column_header_path": ["2024"], "value": "17"}]}}]}
    def block(group, value):
        return {"id": group, "kind": "table_body", "cells": [{"id": group + ":value", "text": value,
                "row_header_path": [group, "Other"], "column_header_path": ["2024"]}]}
    obs = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [block("North", "17"), block("South", "99")]}]}
    scored = score_case(ref, obs)["units"][0]["fields"][0]
    assert scored["status"] == "unresolved"
    ref["units"][0]["table"]["row_header_path"] = ["North", "Other"]
    assert score_case(ref, obs)["units"][0]["fields"][0]["information"]["status"] == "correct"
    obs["pages"][0]["blocks"] = [block("South", "17")]
    assert score_case(ref, obs)["units"][0]["fields"][0]["status"] == "unresolved"
