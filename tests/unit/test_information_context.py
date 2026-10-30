"""Synthetic scope and business-value counterexamples; no corpus access."""

from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells
from moparse_eval.scoring import score_case


def evaluate(html, *, row="Revenue", column="2024", value="17", unit=None, period=None, before=(), after=(), extra=()):
    field = {"column_header_path": [column], "value": value}
    if unit is not None:
        field["unit"] = unit
    if period is not None:
        field["period"] = period
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
    assert evaluate(table, unit="%")["information"]["status"] == "incorrect"
    introduction = {"id": "p", "kind": "text", "text": "The following table is expressed as a percentage of revenue."}
    assert evaluate(table, unit="%", before=[introduction])["information"]["status"] == "correct"
    unrelated = {"id": "p", "kind": "text", "text": "A separate operation earned 17%."}
    assert evaluate(table, unit="%", before=[unrelated])["information"]["status"] == "incorrect"


def test_neighbouring_table_does_not_lend_its_unit_or_total():
    other = {"id": "other", "kind": "table", "cells": html_cells(TABLE, "#/other")}
    table = '<table><tr><th>Metric</th><th>2024</th></tr><tr><td>Total</td><td>17</td></tr></table>'
    f = evaluate(table, row="Total", unit="人民币百万元", extra=[other])
    assert f["information"]["status"] == "incorrect"


def test_empty_section_rows_scope_repeated_labels_without_borrowing_another_group():
    table = '<table><tr><td>Metric</td><td>2024</td></tr><tr><td>North:</td><td></td></tr><tr><td>Other</td><td>17</td></tr><tr><td>South:</td><td></td></tr><tr><td>Other</td><td>11</td></tr></table>'
    assert evaluate(table, row="North / Other")["information"]["status"] == "correct"
    f = evaluate(table, row="South / Other")
    assert f["native_text"] == "11" and f["information"]["status"] == "incorrect"


def test_full_width_group_rows_are_not_mistaken_for_column_headers():
    table = '<table><tr><td>Metric</td><td>2024</td></tr><tr><td colspan="2">North:</td></tr><tr><td>Other</td><td>17</td></tr><tr><td colspan="2">South:</td></tr><tr><td>Other</td><td>11</td></tr></table>'
    assert evaluate(table, row="North / Other")["information"]["status"] == "correct"
    assert evaluate(table, row="South / Other")["native_text"] == "11"
    assert evaluate(table, row="South / Other")["information"]["status"] == "incorrect"


def test_merged_business_column_labels_and_display_year_spacing_keep_the_same_fact():
    table = '<table><tr><td>指标</td><td>2024 年境内审计</td><td>2024 年境外审计</td></tr><tr><td>-营业收入</td><td>17</td><td>11</td></tr></table>'
    assert evaluate(table, row="营业收入", column="2024年境内审计")["information"]["status"] == "correct"
    from moparse_eval.information import endpoint_paths
    from moparse_eval.matching import observation_candidates
    pool = observation_candidates({"pages": [{"page": 1, "blocks": [{"id": "t", "cells": html_cells(table)}]}]})
    endpoints, reason = endpoint_paths(["2024年", "境内审计"], pool, "column", True)
    assert reason is None and len(endpoints) == 1
    assert endpoints[0][0]["id"] == endpoints[0][1]["id"]
    assert evaluate(table, row="营业收入", column="2024年境外审计")["native_text"] == "11"


def test_label_note_typography_does_not_change_the_record_or_the_value():
    table = '<table><tr><td>Metric</td><td>2024</td></tr><tr><td>Trading1,2 ($bn)</td><td>17</td></tr><tr><td>Trading3 ($bn)</td><td>11</td></tr></table>'
    f = evaluate(table, row="Trading¹˒² ($bn)", unit="$bn")
    assert f["information"]["status"] == "correct"
    assert evaluate(table, row="Trading³ ($bn)", unit="$bn")["native_text"] == "11"


def test_currency_printed_on_a_per_share_value_overrides_a_millions_column():
    table = '<table><tr><td>Metric</td><td>2024$m</td></tr><tr><td>Earnings per share</td><td>$0.17</td></tr><tr><td>Revenue</td><td>17</td></tr></table>'
    assert evaluate(table, row="Earnings per share", column="2024$m", value="$0.17", unit="$")["information"]["status"] == "correct"
    assert evaluate(table, row="Earnings per share", column="2024$m", value="$0.17", unit="$m")["information"]["status"] == "incorrect"
    assert evaluate(table, column="2024$m", unit="$m")["information"]["status"] == "correct"


def test_literal_cutoff_date_can_be_read_inside_an_actual_record_title():
    from moparse_eval.information import qualifier_evidence
    cell = {"text": "17", "periods": ["截至2024年9月末股东持股情况"]}
    assert qualifier_evidence({"period": "截至2024年9月末"}, cell, [])["period"]["status"] == "correct"
    assert qualifier_evidence({"period": "截至2023年9月末"}, cell, [])["period"]["status"] != "correct"


def test_metric_specific_scale_overrides_general_column_scale():
    table = '<table><tr><td>Metric</td><td>2024$m</td></tr><tr><td>Average balance ($bn)</td><td>17</td></tr><tr><td>Revenue</td><td>11</td></tr></table>'
    assert evaluate(table, row="Average balance ($bn)", column="2024$m", unit="$bn")["outcome"] == "correct"
    assert evaluate(table, row="Average balance ($bn)", column="2024$m", unit="$m")["outcome"] == "incorrect"


def test_scenario_percent_and_currency_words_are_not_the_unit_of_its_reported_impact():
    table = '<table><tr><td>(人民币百万元)</td><td>2024</td></tr><tr><td>美元贬值5%</td><td>17</td></tr></table>'
    assert evaluate(table, row="美元贬值5%", unit="人民币百万元")["outcome"] == "correct"
    assert evaluate(table, row="美元贬值5%", unit="%")["outcome"] == "incorrect"


def test_explicit_count_measure_and_composed_period_parts():
    from moparse_eval.information import qualifier_evidence
    cell = {"text": "17", "column_header_path": ["2024年", "二季度", "参加会议次数"]}
    assert qualifier_evidence({"unit": "次", "period": "2024年二季度"}, cell, [])["period"]["status"] == "correct"
    assert qualifier_evidence({"unit": "次"}, cell, [])["unit"]["status"] == "correct"
    assert qualifier_evidence({"period": "2024年三季度"}, cell, [])["period"]["status"] == "incorrect"
    cell = {"text": "17", "column_header_path": ["截至12月31日止年度", "2024年"]}
    assert qualifier_evidence({"period": "截至2024年12月31日止年度"}, cell, [])["period"]["status"] == "correct"
    assert qualifier_evidence({"period": "截至2023年12月31日止年度"}, cell, [])["period"]["status"] == "incorrect"


def test_printed_number_and_description_can_jointly_identify_a_record():
    html = '<table><tr><td colspan="2">Matter</td><td>Decision</td></tr><tr><td colspan="3">Management:</td></tr><tr><td>1</td><td>Elect directors</td><td>FOR</td></tr><tr><td>2</td><td>Approve auditor</td><td>AGAINST</td></tr></table>'
    assert evaluate(html, row="Management / 1 Elect directors", column="Decision", value="FOR")["outcome"] == "correct"
    assert evaluate(html, row="Management / 2 Approve auditor", column="Decision", value="FOR")["outcome"] == "incorrect"


def test_label_dot_leaders_are_display_and_do_not_change_the_fact():
    table = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>Revenue (2) ....</td><td>17</td></tr></table>'
    assert evaluate(table, row="Revenue (2)")["outcome"] == "correct"
    assert evaluate(table, row="Revenue (3)")["outcome"] == "incorrect"


def test_transposed_business_dimensions_do_not_require_reference_grid_orientation():
    table = '<table><tr><td>Year</td><td>Revenue</td><td>Cost</td></tr><tr><td>2024</td><td>17</td><td>11</td></tr><tr><td>2023</td><td>11</td><td>17</td></tr></table>'
    assert evaluate(table)["outcome"] == "correct"
    assert evaluate(table, column="2023")["native_text"] == "11"
    assert evaluate(table, column="2023")["outcome"] == "incorrect"
    assert evaluate(table, row="Cost", column="2024")["native_text"] == "11"
    assert evaluate(table, row="Cost", column="2024")["outcome"] == "incorrect"


@pytest.mark.parametrize("actual,correct", [("17", True), ("11", False)])
def test_requested_measure_unit_selects_scope_before_any_value_comparison(actual, correct):
    table = f'<table><tr><td>Item</td><td>2024USD</td><td>2024CNY</td></tr><tr><td>Revenue</td><td>17</td><td>{actual}</td></tr></table>'
    field = evaluate(table, unit="CNY")
    assert field["native_text"] == actual
    assert (field["outcome"] == "correct") is correct


def test_missing_other_measure_does_not_block_a_known_available_measure_or_lend_its_value():
    table = '<table><tr><td>Item</td><td>2024USD</td><td>2024CNY</td></tr><tr><td>Revenue</td><td>17</td></tr></table>'
    assert evaluate(table, unit="USD")["outcome"] == "correct"
    missing = evaluate(table, unit="CNY")
    assert missing["outcome"] == "incorrect" and missing["content_exact"] is False
    assert missing["reason"] == "no_value_at_resolved_native_position"


def test_identical_printed_facts_need_no_unique_physical_cell():
    table = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>Revenue</td><td>17</td></tr><tr><td>Revenue</td><td>17</td></tr></table>'
    field = evaluate(table)
    assert field["outcome"] == "correct" and len(field["equivalent_claim_ids"]) == 2


def test_numeric_business_identifier_cannot_come_from_an_unrelated_count_column():
    table = '<table><tr><td>No.</td><td>Count</td><td>Price</td></tr><tr><td>2</td><td>1</td><td>17</td></tr></table>'
    assert evaluate(table, row="1", column="Price")["outcome"] == "incorrect"
    assert evaluate(table, row="2", column="Price")["outcome"] == "correct"


def test_report_year_qualifies_current_period_only_when_the_field_has_no_own_year():
    report = {"id": "header", "kind": "header", "text": "2024年年度报告"}
    table = '<table><tr><td>Item</td><td>第一季度</td><td>2023年</td></tr><tr><td>Revenue</td><td>17</td><td>11</td></tr></table>'
    assert evaluate(table, column="第一季度", period="2024年", before=[report])["outcome"] == "correct"
    assert evaluate(table, column="2023年", value="11", period="2024年", before=[report])["outcome"] == "incorrect"
    assert evaluate(table, column="第一季度", period="2024年", before=[{**report, "kind": "footer"}])["outcome"] == "incorrect"


@pytest.mark.parametrize("subject,actual,correct", [("North / Revenue", "17", True),
                                                   ("North / Revenue", "11", False),
                                                   ("South / Revenue", "17", False)])
def test_explicit_prose_record_needs_no_private_table_metadata(subject, actual, correct):
    reference = {"sample_id": "invented", "review_status": "confirmed", "units": [{
        "id": "r", "status": "confirmed", "kind": "table_record", "pages": [1], "literal": "Revenue",
        "table": {"row_header_path": ["North", "Revenue"], "fields": [{"column_header_path": ["2024"], "value": "17"}]}}]}
    candidate = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [{"id": "p", "kind": "paragraph",
        "text": f"{subject};2024:{actual};2023:17。"}]}]}
    before = deepcopy((reference, candidate))
    field = score_case(reference, candidate)["units"][0]["fields"][0]
    assert (field.get("information", {}).get("status") == "correct") is correct
    if correct:
        assert field["native_text"] == "17"
    assert (reference, candidate) == before


@pytest.mark.parametrize("period,unit,correct", [("2024", "万元", True), ("2023", "万元", False),
                                               ("2024", "元", False)])
def test_explicit_prose_qualifiers_need_not_be_written_as_column_header_paths(period, unit, correct):
    reference = {"sample_id": "invented", "review_status": "confirmed", "units": [{
        "id": "r", "status": "confirmed", "kind": "table_record", "pages": [1], "literal": "Revenue",
        "table": {"row_header_path": ["Revenue"], "fields": [{"column_header_path": ["2024", "Amount"],
                   "value": "17", "unit": "万元", "period": "2024"}]}}]}
    candidate = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [{"id": "p", "kind": "paragraph",
        "text": f"Name:Revenue;Period:{period};Unit:{unit};Amount:17。"}]}]}
    field = score_case(reference, candidate)["units"][0]["fields"][0]
    assert (field["outcome"] == "correct") is correct


def test_absent_field_and_missing_business_binding_have_final_incorrect_decisions():
    missing = evaluate('<table><tr><td>Item</td><td>2024</td></tr><tr><td>Other</td><td>17</td></tr></table>')
    conflicting = evaluate('<table><tr><td>Item</td><td>2024</td></tr><tr><td>Revenue</td><td>17</td></tr><tr><td>Revenue</td><td>11</td></tr></table>')
    for field in (missing, conflicting):
        assert field["outcome"] == "incorrect"
        assert field["information"]["status"] == "incorrect"
        assert field["content_exact"] is False
        assert field["candidate_evidence"]["field_ids"]


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


@pytest.mark.parametrize("scalar", ["17^4", "17^{4}", "17 ^ 4"])
def test_bare_caret_with_scoped_note_fails_scalar_target_without_format_evidence(scalar):
    table = f'<table><tr><th>Metric</th><th>2024</th></tr><tr><td>Revenue</td><td>{scalar}</td></tr></table>'
    note = {"id": "note", "kind": "table_footnote", "text": "4 Record high."}
    f = evaluate(table, after=[note])
    assert f["information"]["status"] == "incorrect"
    assert f["information"]["reason"] == "ambiguous_note_or_exponent_format"
    assert f["status"] == "compared" and f["content_exact"] is False
    assert f["native_text"] == scalar and f["raw_transcription"]["strict"]["distance"] > 0
    assert evaluate(table, value=scalar, after=[note])["information"]["status"] == "correct"
    assert evaluate(table)["information"]["status"] == "incorrect"
    wrong_note = {**note, "text": "3 Record high."}
    assert evaluate(table, after=[wrong_note])["information"]["status"] == "incorrect"
    barrier = {"id": "next", "kind": "title", "text": "Another business"}
    assert evaluate(table, after=[barrier, note])["information"]["status"] == "incorrect"


def test_ambiguous_note_does_not_hide_a_confirmed_wrong_currency():
    table = '<table><tr><td>(人民币百万元)</td><td>2024</td></tr><tr><td>Revenue</td><td>17^4</td></tr></table>'
    note = {"id": "note", "kind": "table_footnote", "text": "4 Record high."}
    f = evaluate(table, unit="美元", after=[note])
    assert f["information"]["status"] == "incorrect"
    assert f["information"]["qualifiers"]["unit"]["status"] == "incorrect"


def test_attached_chinese_currency_can_be_read_without_matching_other_business_words():
    table = '<table><tr><td>Metric</td><td>金額人民幣千元</td></tr><tr><td>Other business</td><td>17</td></tr></table>'
    assert evaluate(table, row="Other business", column="金額", unit="人民幣千元")["information"]["status"] == "correct"
    assert evaluate(table, row="Other", column="金額")["status"] == "incorrect"


def test_untyped_local_header_switch_does_not_lend_a_period_from_the_previous_scope():
    table = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>Alpha</td><td>17</td></tr><tr><td>Item</td><td>2023</td></tr><tr><td>Beta</td><td>11</td></tr></table>'
    assert evaluate(table, row="Beta", column="2023", value="11")["information"]["status"] == "correct"
    assert evaluate(table, row="Beta", column="2024", value="11")["status"] == "incorrect"


def test_a_group_total_ends_the_group_scope_for_later_records():
    table = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>Expenses</td><td></td></tr><tr><td>Research</td><td>17</td></tr><tr><td>Total expenses</td><td>17</td></tr><tr><td>Profit</td><td>11</td></tr></table>'
    assert evaluate(table, row="Expenses / Research")["information"]["status"] == "correct"
    assert evaluate(table, row="Expenses / Profit", value="11")["status"] == "incorrect"


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
    assert total["status"] == "incorrect"


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
    assert evaluate(html, row="Net income per diluted share", value="$0.17", unit="$ per share")["information"]["status"] == "correct"
    assert evaluate(html, row="Net income per diluted share", value="$0.17", unit="$ in millions")["information"]["status"] == "incorrect"


def test_explicit_enumerated_sibling_stops_the_previous_group_scope():
    table = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>二、Category</td><td></td></tr><tr><td>Child</td><td>17</td></tr><tr><td>三、Total</td><td>11</td></tr></table>'
    assert evaluate(table, row="三、Total", value="11")["information"]["status"] == "correct"
    assert evaluate(table, row="二、Category / 三、Total", value="11")["status"] == "incorrect"


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
    assert scored["status"] == "incorrect"
    ref["units"][0]["table"]["row_header_path"] = ["North", "Other"]
    assert score_case(ref, obs)["units"][0]["fields"][0]["information"]["status"] == "correct"
    obs["pages"][0]["blocks"] = [block("South", "17")]
    assert score_case(ref, obs)["units"][0]["fields"][0]["status"] == "incorrect"


def test_percentage_points_attached_to_an_accounting_scalar_override_a_percent_column():
    html = '<table><tr><td>Item</td><td>Change (%)</td></tr><tr><td>Revenue</td><td>(1.40)個百分點</td></tr></table>'
    f = evaluate(html, column='Change', value='(1.40)個百分點', unit='個百分點')
    assert f['information']['status'] == 'correct'
    assert evaluate(html, column='Change', value='(1.40)個百分點', unit='%')['information']['status'] == 'incorrect'
    wrong_sign = html.replace('(1.40)個百分點', '1.40個百分點')
    assert evaluate(wrong_sign, column='Change', value='(1.40)個百分點', unit='個百分點')['information']['status'] == 'incorrect'


def test_thousand_tonnes_keep_the_full_printed_scale():
    html = '<table><tr><td>Item</td><td>2024年 銷售量(千噸)</td></tr><tr><td>Revenue</td><td>17</td></tr></table>'
    assert evaluate(html, column='2024年', unit='千噸')['information']['status'] == 'correct'
    for wrong in ('噸', '萬噸'):
        assert evaluate(html, column='2024年', unit=wrong)['information']['status'] == 'incorrect'


def test_numbered_plain_notes_only_establish_bare_caret_ambiguity_without_granting_credit():
    html = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>Revenue</td><td>17^4</td></tr></table>'
    notes = [{'id': 'notes', 'kind': 'text', 'text': '1 Basis.\n2 Scope.\n3 Method.\n4 Record high.'}]
    f = evaluate(html, after=notes)
    assert f['information']['status'] == 'incorrect' and f['content_exact'] is False
    assert f['native_text'] == '17^4'
    barrier = {'id': 'next', 'kind': 'title', 'text': 'Other business'}
    assert evaluate(html, after=[barrier, *notes])['information']['status'] == 'incorrect'
    isolated = [{'id': 'notes', 'kind': 'text', 'text': '4 A separate agenda item.'}]
    assert evaluate(html, after=isolated)['information']['status'] == 'incorrect'


def test_multiple_explicit_note_definitions_in_one_block_keep_each_marker():
    html = '<table><tr><td>Item</td><td>2024</td></tr><tr><td>Revenue</td><td>17<sup>4</sup></td></tr></table>'
    note = {'id': 'notes', 'kind': 'table_footnote', 'text': '1 Basis.\n2 Scope.\n3 Method.\n4 Record high.'}
    assert evaluate(html, after=[note])['information']['status'] == 'correct'


def test_last_explicit_annual_introduction_in_a_multiline_block_has_a_bounded_scope():
    html = '<table><tr><td>Item</td><td>Amount</td></tr><tr><td>Revenue</td><td>17</td></tr></table>'
    intro = {'id': 'intro', 'kind': 'text', 'text': '（1）Some context。\n（2）Other context。\n（3）2024 年度测量数据:'}
    assert evaluate(html, column='Amount', period='2024年度', before=[intro])['information']['status'] == 'correct'
    end = {'id': 'end', 'kind': 'title', 'text': '（4）Other operations'}
    assert evaluate(html, column='Amount', period='2024年度', before=[intro, end])['information']['status'] == 'incorrect'


def test_blank_header_corner_does_not_turn_textual_records_into_column_headers():
    table = '<table><tr><td></td><td>Purpose A</td><td>Purpose B</td></tr><tr><td>Primary purpose</td><td>Scientific discovery</td><td>Model training</td></tr><tr><td>Example use cases</td><td>Climate modelling</td><td>Language models</td></tr></table>'
    assert evaluate(table, row='Primary purpose', column='Purpose A', value='Scientific discovery')['outcome'] == 'correct'
    assert evaluate(table, row='Primary purpose', column='Purpose B', value='Model training')['outcome'] == 'correct'


def test_spanning_date_header_keeps_its_explicit_annual_subheaders():
    table = '<table><tr><td colspan="3">As at 31 December</td><td>Change</td></tr><tr><td>Balance sheet item</td><td>2024</td><td>2023</td><td>Amount</td></tr><tr><td>Revenue</td><td>17</td><td>11</td><td>6</td></tr></table>'
    assert evaluate(table)['outcome'] == 'correct'
    assert evaluate(table.replace('<td>2024</td><td>2023</td>', '<td>2023</td><td>2024</td>'))['native_text'] == '11'


def test_a_formatting_only_empty_gfm_header_does_not_hide_actual_column_labels():
    from moparse_eval.adapters import markdown_cells
    ref = {'sample_id': 'invented', 'review_status': 'confirmed', 'units': [
        {'id': 'record', 'kind': 'table_record', 'status': 'confirmed', 'literal': 'Achievement', 'pages': [1],
         'table': {'row_header_path': ['Achievement'], 'fields': [{'column_header_path': ['Plan A'], 'value': '17'}]}}]}
    md = '| | | |\n|---|---|---|\n| Performance | | |\n| | Plan A | Plan B |\n| Achievement | 17 | 11 |'
    obs = {'sample_id': 'invented', 'pages': [{'page': 1, 'blocks': [{'id': 't', 'kind': 'table', 'cells': markdown_cells(md)}]}]}
    assert score_case(ref, obs)['units'][0]['fields'][0]['outcome'] == 'correct'


def test_a_printed_records_other_year_columns_supply_its_generic_change_period_only():
    cell = {'id': 'v', 'text': '5%', 'row_header_path': ['Revenue'], 'column_header_path': ['Change']}
    reference = {'sample_id': 'invented', 'review_status': 'confirmed', 'units': [
        {'id': 'r', 'kind': 'table_record', 'status': 'confirmed', 'literal': 'Revenue', 'pages': [1],
         'table': {'row_header_path': ['Revenue'], 'period': '截至12月31日止年度', 'fields': [
             {'column_header_path': ['Change'], 'value': '5%', 'unit': '%'}]}}]}
    obs = {'sample_id': 'invented', 'pages': [{'page': 1, 'blocks': [{'id': 'record', 'kind': 'text_record', 'cells': [
        cell, {'id': 'a', 'text': '17', 'row_header_path': ['Revenue'], 'column_header_path': ['截至12月31日止年度', '2024年', '万元']},
        {'id': 'b', 'text': '11', 'row_header_path': ['Revenue'], 'column_header_path': ['截至12月31日止年度', '2023年', '万元']}]}]}]}
    assert score_case(reference, obs)['units'][0]['fields'][0]['outcome'] == 'correct'
    reference['units'][0]['table']['fields'][0]['unit'] = '万元'
    assert score_case(reference, obs)['units'][0]['fields'][0]['outcome'] == 'incorrect'
    obs['pages'][0]['blocks'][0]['cells'] = [cell]
    reference['units'][0]['table']['fields'][0]['unit'] = '%'
    assert score_case(reference, obs)['units'][0]['fields'][0]['outcome'] == 'incorrect'


def test_bilingual_year_headers_and_external_date_frame_are_read_from_the_printed_path():
    reference = {'sample_id': 'invented', 'review_status': 'confirmed', 'units': [
        {'id': 'r', 'kind': 'table_record', 'status': 'confirmed', 'literal': 'Revenue', 'pages': [1],
         'table': {'row_header_path': ['Revenue'], 'fields': [{'column_header_path': ['2024'],
             'value': '17', 'unit': "RMB'000", 'period': 'For the year ended 31 December 2024'}]}}]}
    cell = {'id': 'v', 'text': '17', 'row_header_path': ['Revenue', '營業額'],
            'column_header_path': ['For the year ended 31 December截至十二月三十一日止年度', "2024二零二四年RMB'000人民幣千元"]}
    obs = {'sample_id': 'invented', 'pages': [{'page': 1, 'blocks': [{'id': 't', 'kind': 'table', 'cells': [cell]}]}]}
    assert score_case(reference, obs)['units'][0]['fields'][0]['outcome'] == 'correct'
    cell['column_header_path'][1] = "2023二零二三年RMB'000人民幣千元"
    assert score_case(reference, obs)['units'][0]['fields'][0]['outcome'] == 'incorrect'
