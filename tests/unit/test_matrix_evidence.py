"""Independent role and endpoint oracles for candidate-only matrix reading."""

from __future__ import annotations

from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells, markdown_cells
from moparse_eval.matrix_evidence import read_matrix


def cell(text, row, col, *, rs=1, cs=1, column=False, header=False, section=False, native_id=None, references=None):
    value = {"id": f"cell:{row}:{col}", "native_path": f"#/table/{row}/{col}", "text": text,
             "row": row, "col": col, "row_span": rs, "col_span": cs,
             "column_header": column, "row_header": header, "row_section": section}
    if native_id:
        value["native_id"] = native_id
    if references:
        value["native_attributes"] = {"headers": references}
    return value


def five_fields(*, reference_ids=False):
    values = [
        cell("2027年", 0, 2, cs=2, column=True, native_id="y27"),
        cell("2026年", 0, 4, cs=2, column=True, native_id="y26"),
        cell("金額同比變動(%)", 0, 6, rs=2, column=True, native_id="yoy"),
        cell("金額(萬元)", 1, 2, column=True, native_id="a27"),
        cell("佔總收入比(%)", 1, 3, column=True, native_id="s27"),
        cell("金額(萬元)", 1, 4, column=True, native_id="a26"),
        cell("佔總收入比(%)", 1, 5, column=True, native_id="s26"),
        cell("North", 2, 0, header=True, section=True, native_id="north"),
        cell("Delta", 2, 1, header=True, native_id="delta"),
    ]
    for col, (text, head) in enumerate(zip(["17", "60%", "11", "55%", "5%"], ["a27", "s27", "a26", "s26", "yoy"], strict=True), 2):
        values.append(cell(text, 2, col, references=f"{head} delta north" if reference_ids else None))
    return values


def read(cells, **kwargs):
    return read_matrix(cells, source={"path": "#/invented/table"}, **kwargs)


@pytest.mark.parametrize("references", [False, True])
def test_five_independent_measurements_bind_to_two_axes_and_group(references):
    inputs = five_fields(reference_ids=references)
    before = deepcopy(inputs)
    result = read(inputs)
    assert inputs == before
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 5
    assert {(f["subject"], f["attribute"], f["value"], f["qualifiers"].get("period"), f["qualifiers"].get("unit"))
            for f in result["facts"]} == {
        ("Delta", "金額", "17", "2027年", "萬元"),
        ("Delta", "佔總收入比", "60", "2027年", "%"),
        ("Delta", "金額", "11", "2026年", "萬元"),
        ("Delta", "佔總收入比", "55", "2026年", "%"),
        ("Delta", "金額同比變動", "5", None, "%"),
    }
    for fact in result["facts"]:
        assert fact["identity_facets"] == {"group": "North"}
        assert fact["source"]["row"] == 2 and fact["source"]["col"] in range(2, 7)
        assert {e["text"] for e in fact["row_evidence"]} >= {"Delta", "North"}
        assert fact["header_evidence"]
    yoy = next(f for f in result["facts"] if f["attribute"] == "金額同比變動")
    assert yoy["qualifiers"]["from_period"] == "2026年"
    assert yoy["qualifiers"]["to_period"] == "2027年"
    assert {e["native_id"] for e in yoy["header_evidence"]} >= {"y27", "y26", "yoy"}
    assert len({f["record_id"] for f in result["facts"]}) == 1


def test_currency_and_units_are_bound_to_their_own_spanned_header_cells():
    inputs = [
        cell("2027", 0, 1, cs=2, column=True), cell("2026", 0, 3, column=True),
        cell("美元百万元", 1, 1, column=True), cell("人民币百万元", 1, 2, cs=2, column=True),
        cell("销售收入", 2, 0, header=True),
        cell("17", 2, 1), cell("11", 2, 2), cell("5", 2, 3),
    ]
    result = read(inputs)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 3
    assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("", "销售收入", "17", {"period": "2027年", "unit": "美元百万元", "currency": "美元"}),
        ("", "销售收入", "11", {"period": "2027年", "unit": "人民币百万元", "currency": "人民币"}),
        ("", "销售收入", "5", {"period": "2026年", "unit": "人民币百万元", "currency": "人民币"}),
    ]
    assert result["facts"][2]["header_evidence"][1]["source"]["col"] == 2


def test_scalar_value_change_does_not_select_another_header_or_record():
    original = five_fields()
    changed = deepcopy(original)
    changed[-5]["text"] = "-18"
    before, after = read(original), read(changed)
    assert len(before["facts"]) == len(after["facts"]) == 5
    assert after["facts"][0]["value"] == "-18"
    for left, right in zip(before["facts"], after["facts"], strict=True):
        assert {k: left[k] for k in ("source", "header_evidence", "row_evidence", "identity_facets", "qualifiers")} == {
            k: right[k] for k in ("source", "header_evidence", "row_evidence", "identity_facets", "qualifiers")}


def test_explicit_header_change_follows_the_declared_reference_and_keeps_value_position():
    original = five_fields(reference_ids=True)
    changed = deepcopy(original)
    changed[-5]["native_attributes"]["headers"] = "a26 delta north"
    result = read(changed)
    assert result["complete"] is True, result["blockers"]
    first = next(f for f in result["facts"] if f["source"]["col"] == 2)
    assert first["value"] == "17" and first["qualifiers"]["period"] == "2026年"
    assert {e["native_id"] for e in first["header_evidence"]} >= {"a26", "y26"}


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "data-reference"])
def test_ambiguous_or_invalid_explicit_references_never_choose_a_header(mutation):
    inputs = five_fields(reference_ids=True)
    if mutation == "duplicate":
        inputs[3]["native_id"] = "a26"
    elif mutation == "missing":
        inputs[-5]["native_attributes"]["headers"] = "not-returned"
    else:
        inputs[-4]["native_id"] = "actual-data"
        inputs[-5]["native_attributes"]["headers"] = "actual-data"
    result = read(inputs)
    assert result["complete"] is False
    assert any(b["reason"] in {"matrix_duplicate_native_ids", "matrix_header_reference_unavailable", "matrix_reference_target_not_a_header"}
               for b in result["blockers"])


def test_status_ready_headers_are_not_read_as_each_others_values():
    cells = html_cells('<table><tr><th scope="col">Status</th><th scope="col">Ready</th></tr>'
                       '<tr><td>Blocked</td><td>No</td></tr></table>')
    result = read(cells)
    assert result["complete"] is True, result["blockers"]
    assert [(f["attribute"], f["value"]) for f in result["facts"]] == [("Status", "Blocked"), ("Ready", "No")]


def test_group_and_item_schema_is_a_record_axis_without_extra_name_questions():
    cells = markdown_cells("| Group | Item | 2027 金額 (萬元) | 2026 金額 (萬元) |\n|---|---|---|---|\n|North|Delta|17|11|")
    result = read(cells)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 2
    assert {(f["subject"], f["attribute"], f["value"], f["identity_facets"]["group"]) for f in result["facts"]} == {
        ("Delta", "金額", "17", "North"), ("Delta", "金額", "11", "North")}


def test_explicit_transposed_record_and_period_axes_retain_original_cell_positions():
    html = ('<table><tr><th colspan="2" scope="row">Group</th><th scope="colgroup">North</th></tr>'
            '<tr><th colspan="2" scope="row">Item</th><th scope="col">Delta</th></tr>'
            '<tr><th rowspan="2" scope="rowgroup">2027年</th><th scope="row">金額（萬元）</th><td>17</td></tr>'
            '<tr><th scope="row">佔總收入比（%）</th><td>60</td></tr>'
            '<tr><th rowspan="2" scope="rowgroup">2026年</th><th scope="row">金額（萬元）</th><td>11</td></tr>'
            '<tr><th scope="row">佔總收入比（%）</th><td>55</td></tr>'
            '<tr><th colspan="2" scope="row">金額同比變動（%）</th><td>5</td></tr></table>')
    result = read(html_cells(html))
    assert result["complete"] is True, result["blockers"]
    assert result["orientation"] == "explicit_transposed_group_item_schema"
    assert len(result["facts"]) == 5
    assert [(f["source"]["row"], f["source"]["col"], f["subject"], f["value"]) for f in result["facts"]] == [
        (2, 2, "Delta", "17"), (3, 2, "Delta", "60"), (4, 2, "Delta", "11"),
        (5, 2, "Delta", "55"), (6, 2, "Delta", "5")]
    assert {f["identity_facets"]["group"] for f in result["facts"]} == {"North"}
    assert result["facts"][0]["qualifiers"] == {"period": "2027年", "unit": "萬元"}
    assert result["facts"][-1]["qualifiers"] == {"unit": "%", "from_period": "2026年", "to_period": "2027年"}


def test_all_td_period_unit_and_repeated_measurement_schema_proves_roles():
    cells = html_cells('<table><tr><td></td><td>2027</td><td>2026</td></tr>'
                       '<tr><td></td><td>美元百万元</td><td>美元百万元</td></tr>'
                       '<tr><td>Revenue</td><td>17</td><td>11</td></tr>'
                       '<tr><td>Profit</td><td>5</td><td>3</td></tr></table>')
    result = read(cells)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 4
    assert result["role_basis"] == "printed_period_unit_measurement_schema_and_repeated_records"
    assert {(f["attribute"], f["value"], f["qualifiers"]["period"]) for f in result["facts"]} == {
        ("Revenue", "17", "2027年"), ("Revenue", "11", "2026年"),
        ("Profit", "5", "2027年"), ("Profit", "3", "2026年")}


@pytest.mark.parametrize("html", [
    '<table><tr><td>Status</td><td>Ready</td></tr><tr><td>Blocked</td><td>No</td></tr></table>',
    '<table><tr><td>2027</td><td>2026</td></tr><tr><td>17</td><td>11</td></tr></table>',
    '<table><tr><td>Note</td><td>Some prose</td></tr><tr><td>17</td><td>11</td></tr></table>',
    '<table><tr><td></td><td>2027</td><td>2026</td></tr><tr><td></td><td>万元</td><td>万元</td></tr>'
    '<tr><td>Revenue</td><td>17</td><td>11</td></tr></table>',
])
def test_untyped_grids_without_a_complete_independent_data_schema_remain_unproven(html):
    result = read(html_cells(html))
    assert result["facts"] == []
    assert result["complete"] is False
    assert result["blockers"][0]["reason"] == "matrix_data_roles_unproven"
    assert result["issues"] == result["blockers"]
    assert {issue["category"] for issue in result["issues"]} == {"software_unsupported"}
    assert result["issues"][0]["affected_data_sources"]


def test_explicitly_ambiguous_unit_header_is_a_candidate_issue_with_its_exact_data_object():
    inputs = [cell("2027", 0, 1, column=True), cell("美元百万元 人民币百万元", 1, 1, column=True),
              cell("Revenue", 2, 0, header=True), cell("17", 2, 1)]
    result = read(inputs)
    assert result["complete"] is True and result["blockers"] == []
    assert len(result["facts"]) == 1
    assert len(result["issues"]) == 1
    issue = result["issues"][0]
    assert issue["category"] == "candidate_ambiguity"
    assert issue["reason"] == "matrix_header_qualifier_ambiguous"
    assert issue["header_ids"] == ["cell:1:1"]
    assert [(s["row"], s["col"], s["cell"]) for s in issue["affected_data_sources"]] == [(2, 1, "cell:2:1")]
    assert issue["alternatives"]["unit"] == ["美元百万元", "人民币百万元"]
    assert result["facts"][0]["ambiguous_qualifiers"]["unit"] == ["美元百万元", "人民币百万元"]
    assert result["facts"][0]["issue_ids"] == [issue["id"]]


def test_known_source_context_is_retained_and_does_not_override_local_units():
    inputs = [cell("2027 金額(美元百万元)", 0, 1, column=True),
              cell("Delta", 1, 0, header=True), cell("17", 1, 1)]
    context = [{"text": "单位：人民币千元", "source": {"path": "#/printed/caption"}}]
    result = read(inputs, context=context)
    assert result["complete"] is True, result["blockers"]
    assert result["facts"][0]["qualifiers"] == {"period": "2027年", "unit": "美元百万元", "currency": "美元"}


def test_record_qualifier_columns_do_not_create_business_questions_or_qualify_names_and_headcounts():
    table = ("| Name | Role | Revenue | Headcount | Unit | Period | Note |\n"
             "|---|---|---|---|---|---|---|\n| Delta | CFO | 17 | 5 | 万元 | 2027年 | Audited |")
    result = read(markdown_cells(table))
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 4
    facts = {f["attribute"]: f for f in result["facts"]}
    assert set(facts) == {"Name", "Role", "Revenue", "Headcount"}
    assert facts["Name"]["subject"] == "" and facts["Name"]["role"] == "identity"
    assert facts["Role"]["subject"] == "Delta" and facts["Role"]["role"] == "identity"
    assert facts["Revenue"]["subject"] == "Delta"
    assert facts["Revenue"]["qualifiers"] == {"unit": "万元", "period": "2027年", "note": "Audited"}
    assert "unit" not in facts["Name"]["qualifiers"]
    assert "unit" not in facts["Role"]["qualifiers"]
    assert "unit" not in facts["Headcount"]["qualifiers"]
    assert facts["Revenue"]["identity_facets"] == {"Role": "CFO"}
    assert facts["Name"]["identity_facets"] == facts["Role"]["identity_facets"] == {}


def test_vertical_property_table_uses_the_same_subject_roles_and_record_qualifiers():
    table = ("| Attribute | Value |\n|---|---|\n|Name|Delta|\n|Role|CFO|\n|Revenue|17|\n|Unit|万元|\n"
             "|Name|Echo|\n|Headcount|5|")
    result = read(markdown_cells(table))
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 5
    assert [(f["subject"], f["attribute"], f["value"]) for f in result["facts"]] == [
        ("", "Name", "Delta"), ("Delta", "Role", "CFO"), ("Delta", "Revenue", "17"),
        ("", "Name", "Echo"), ("Echo", "Headcount", "5")]
    assert result["facts"][2]["qualifiers"] == {"unit": "万元"}
    assert all("unit" not in f["qualifiers"] for i, f in enumerate(result["facts"]) if i != 2)
    assert len({f["record_id"] for f in result["facts"][:3]}) == 1
    assert len({f["record_id"] for f in result["facts"][3:]}) == 1
    assert result["facts"][0]["record_id"] != result["facts"][3]["record_id"]
    assert result["facts"][2]["identity_facets"] == {"Role": "CFO"}


@pytest.mark.parametrize("table", [
    "| Revenue（万元） |\n|---|\n|17|",
    "| Revenue |\n|---|\n|17万元|",
    "| Attribute | Value |\n|---|---|\n|Unit|万元|\n|Revenue|17|",
])
def test_single_explicit_amount_and_value_suffix_are_read_without_reference_answers(table):
    result = read(markdown_cells(table))
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 1
    fact = result["facts"][0]
    assert (fact["attribute"], fact["value"], fact["qualifiers"]) == ("Revenue", "17", {"unit": "万元"})


def test_gfm_source_endpoints_distinguish_cells_in_the_same_printed_table():
    result = read(markdown_cells("| Name | Revenue | Profit |\n|---|---|---|\n|北 京|17|5|"))
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 3
    assert len({f["source"]["cell"] for f in result["facts"]}) == 3
    assert result["facts"][0]["value"] == "北 京"
    assert result["facts"][1]["subject"] == "北 京"


def test_explicit_unit_header_words_and_standalone_currency_are_qualifiers():
    inputs = [cell("期间：2027年", 0, 1, cs=2, column=True),
              cell("单位：美元", 1, 1, column=True), cell("单位：人民币", 1, 2, column=True),
              cell("销售收入", 2, 0, header=True), cell("17", 2, 1), cell("11", 2, 2)]
    result = read(inputs)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 2
    assert [(f["subject"], f["attribute"], f["qualifiers"]) for f in result["facts"]] == [
        ("", "销售收入", {"period": "2027年", "unit": "美元", "currency": "美元"}),
        ("", "销售收入", {"period": "2027年", "unit": "人民币", "currency": "人民币"})]


@pytest.mark.parametrize("label", ["元器件收入", "人工成本", "美元资产", "ISO2027编码", "Model 2027"])
def test_business_words_and_identifiers_are_not_stripped_as_qualifiers(label):
    inputs = [cell(label, 0, 0, column=True), cell("17", 1, 0)]
    result = read(inputs)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 1
    assert result["facts"][0]["attribute"] == label
    assert result["facts"][0]["qualifiers"] == {}


def test_data_evidence_preserves_explicit_reference_and_original_object_identity():
    inputs = five_fields(reference_ids=True)
    inputs[-5]["native_id"] = "observation-amount27"
    result = read(inputs)
    first = next(f for f in result["facts"] if f["source"]["col"] == 2)
    evidence = first["data_evidence"]
    assert evidence["native_id"] == "observation-amount27"
    assert evidence["source"]["row"] == 2 and evidence["source"]["col"] == 2
    assert evidence["declarations"]["native_attributes"]["headers"] == "a27 delta north"


def test_repeated_period_unit_schema_does_not_require_a_dictionary_entry_for_every_row_name():
    cells = html_cells('<table><tr><td></td><td>2027</td><td>2026</td></tr>'
                       '<tr><td></td><td>万元</td><td>万元</td></tr>'
                       '<tr><td>Revenue</td><td>17</td><td>11</td></tr>'
                       '<tr><td>Profit</td><td>5</td><td>3</td></tr>'
                       '<tr><td>Working capital</td><td>9</td><td>8</td></tr></table>')
    result = read(cells)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 6
    assert {f["attribute"] for f in result["facts"]} == {"Revenue", "Profit", "Working capital"}


def test_explicit_group_only_row_does_not_create_empty_business_values():
    cells = html_cells('<table><tr><td></td><td>2027 金額(万元)</td><td>2026 金額(万元)</td></tr>'
                       '<tr><td>Revenue</td><td>17</td><td>11</td></tr>'
                       '<tr><td>按行業劃分：</td><td></td><td></td></tr>'
                       '<tr><td>Shipping</td><td>5</td><td>3</td></tr></table>')
    result = read(cells)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 4
    shipping = [f for f in result["facts"] if f["subject"] == "Shipping"]
    assert len(shipping) == 2
    assert {f["identity_facets"]["group"] for f in shipping} == {"按行業劃分"}


def test_unnamed_numeric_row_cannot_be_promoted_to_a_header_to_skip_its_ambiguity():
    cells = html_cells('<table><tr><td></td><td>2027 金額(万元)</td><td>2026 金額(万元)</td></tr>'
                       '<tr><td></td><td>99</td><td>98</td></tr>'
                       '<tr><td>Revenue</td><td>17</td><td>11</td></tr>'
                       '<tr><td>Profit</td><td>5</td><td>3</td></tr></table>')
    result = read(cells)
    assert result["complete"] is True and result["blockers"] == []
    assert len(result["facts"]) == 4
    assert {f["subject"] for f in result["facts"]} == {"Revenue", "Profit"}
    assert all(f["column_path"] in [["2027 金額(万元)"], ["2026 金額(万元)"]] for f in result["facts"])
    assert {b["reason"] for b in result["issues"]} == {"matrix_record_identity_unavailable"}
    assert {b["category"] for b in result["issues"]} == {"unadjudicated_extra_content"}
    assert {(s["row"], s["col"]) for issue in result["issues"] for s in issue["affected_data_sources"]} == {(1, 1), (1, 2)}
    unknown = {(e["source"]["row"], e["source"]["col"]): e["text"] for e in result["unresolved_cells"]}
    assert unknown[1, 1] == "99" and unknown[1, 2] == "98"


def test_ambiguous_unit_assignment_is_local_and_does_not_erase_explicit_neighbor_columns():
    cells = html_cells('<table><tr><td></td><td colspan="2">2027</td><td>2026</td></tr>'
                       '<tr><td></td><td colspan="2">(美元百万元)(人民币百万元)</td><td>人民币百万元</td></tr>'
                       '<tr><td>Revenue</td><td>17</td><td>11</td><td>9</td></tr>'
                       '<tr><td>Profit</td><td>5</td><td>3</td><td>2</td></tr></table>')
    result = read(cells)
    assert result["complete"] is True and result["blockers"] == []
    assert len(result["facts"]) == 6
    assert len(result["unresolved_cells"]) == 1
    assert result["unresolved_cells"][0]["text"] == "(美元百万元)(人民币百万元)"
    neighbors = [f for f in result["facts"] if f["source"]["col"] == 3]
    assert len(neighbors) == 2
    assert {f["qualifiers"]["unit"] for f in neighbors} == {"人民币百万元"}
    assert {b["reason"] for b in result["issues"]} == {"matrix_header_qualifier_ambiguous"}
    assert {b["category"] for b in result["issues"]} == {"candidate_ambiguity"}
    assert {(s["row"], s["col"]) for issue in result["issues"] for s in issue["affected_data_sources"]} == {(2, 1), (2, 2), (3, 1), (3, 2)}
    assert all(not f["issue_ids"] and not f["ambiguous_qualifiers"] for f in neighbors)
    assert {(f["attribute"], f["value"], f["qualifiers"]["period"], f["qualifiers"]["unit"]) for f in neighbors} == {
        ("Revenue", "9", "2026年", "人民币百万元"), ("Profit", "2", "2026年", "人民币百万元")}


def test_a_named_blank_record_sharing_a_group_row_is_preserved_as_data():
    inputs = five_fields()
    for field in inputs[-5:]:
        field["text"] = ""
    result = read(inputs)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 5
    assert [f["value"] for f in result["facts"]] == [""] * 5
    assert {f["subject"] for f in result["facts"]} == {"Delta"}
    assert {f["source"]["col"] for f in result["facts"]} == {2, 3, 4, 5, 6}


def test_duplicate_same_name_records_keep_separate_position_based_record_bundles():
    cells = markdown_cells("| Name | Revenue | Profit |\n|---|---|---|\n|Delta|17|5|\n|Delta|11|3|")
    result = read(cells)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 6
    by_row = {row: {f["record_id"] for f in result["facts"] if f["source"]["row"] == row} for row in (1, 2)}
    assert len(by_row[1]) == len(by_row[2]) == 1
    assert by_row[1] != by_row[2]
    changed = deepcopy(cells)
    next(c for c in changed if c["row"] == 1 and c["col"] == 1)["text"] = "99"
    assert [f["record_id"] for f in read(changed)["facts"]] == [f["record_id"] for f in result["facts"]]


def test_wrong_role_remains_an_independent_identity_error_and_changes_its_records_metric_context():
    inputs = markdown_cells("| Name | Role | Code | Revenue |\n|---|---|---|---|\n|Delta|CFO|X1|17|")
    result = read(inputs)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 4
    revenue = next(f for f in result["facts"] if f["attribute"] == "Revenue")
    assert revenue["identity_facets"] == {"Role": "CFO", "Code": "X1"}
    changed = deepcopy(inputs)
    next(c for c in changed if c["row"] == 1 and c["col"] == 1)["text"] = "CTO"
    actual = read(changed)
    changed_revenue = next(f for f in actual["facts"] if f["attribute"] == "Revenue")
    assert changed_revenue["value"] == "17"
    assert changed_revenue["source"] == revenue["source"] and changed_revenue["record_id"] == revenue["record_id"]
    assert changed_revenue["identity_facets"] == {"Role": "CTO", "Code": "X1"}
    assert all(f["identity_facets"] == {} for f in actual["facts"] if f["role"] == "identity")


def test_explicit_prefix_record_name_creates_a_record_instead_of_unbound_extra_atoms():
    html = ('<table><tr><td></td><td>2027 金額(万元)</td><td>2026 金額(万元)</td></tr>'
            '<tr><td></td><td>99</td><td>98</td></tr>'
            '<tr><td>Revenue</td><td>17</td><td>11</td></tr>'
            '<tr><td>Profit</td><td>5</td><td>3</td></tr></table>')
    before = read(html_cells(html))
    after = read(html_cells(html.replace('<tr><td></td><td>99', '<tr><td>Extra</td><td>99')))
    assert before["complete"] is True and before["blockers"] == []
    assert len(before["facts"]) == 4
    assert {issue["category"] for issue in before["issues"]} == {"unadjudicated_extra_content"}
    assert after["complete"] is True and after["issues"] == []
    assert len(after["facts"]) == 6
    assert {(f["subject"], f["value"]) for f in after["facts"] if f["subject"] == "Extra"} == {("Extra", "99"), ("Extra", "98")}
    assert {(f["subject"], f["value"], f["qualifiers"]["period"]) for f in before["facts"]} == {
        (f["subject"], f["value"], f["qualifiers"]["period"]) for f in after["facts"] if f["subject"] != "Extra"}


def test_unknown_mixed_prefix_is_not_relabelled_as_extra_numeric_content_to_unlock_publication():
    cells = html_cells('<table><tr><td></td><td>2027 金額(万元)</td><td>2026 金額(万元)</td></tr>'
                       '<tr><td></td><td>Unknown scope description</td><td></td></tr>'
                       '<tr><td>Revenue</td><td>17</td><td>11</td></tr>'
                       '<tr><td>Profit</td><td>5</td><td>3</td></tr></table>')
    result = read(cells)
    assert result["complete"] is False
    assert result["blockers"]
    assert {issue["category"] for issue in result["issues"]} == {"software_unsupported"}
    assert {(source["row"], source["col"]) for issue in result["issues"] for source in issue["affected_data_sources"]} == {(1, 1)}
    assert len(result["facts"]) == 4


def test_independent_header_assignments_resolve_ambiguity_without_changing_any_data_values():
    ambiguous = html_cells('<table><tr><td></td><td colspan="2">2027</td><td>2026</td></tr>'
                           '<tr><td></td><td colspan="2">(美元百万元)(人民币百万元)</td><td>人民币百万元</td></tr>'
                           '<tr><td>Revenue</td><td>17</td><td>11</td><td>9</td></tr>'
                           '<tr><td>Profit</td><td>5</td><td>3</td><td>2</td></tr></table>')
    explicit = html_cells('<table><tr><td></td><td colspan="2">2027</td><td>2026</td></tr>'
                          '<tr><td></td><td>美元百万元</td><td>人民币百万元</td><td>人民币百万元</td></tr>'
                          '<tr><td>Revenue</td><td>17</td><td>11</td><td>9</td></tr>'
                          '<tr><td>Profit</td><td>5</td><td>3</td><td>2</td></tr></table>')
    before, after = read(ambiguous), read(explicit)
    assert len(before["facts"]) == len(after["facts"]) == 6
    assert before["has_candidate_ambiguity"] is True and before["blockers"] == []
    assert after["complete"] is True and after["issues"] == []
    assert [(f["source"]["row"], f["source"]["col"], f["value"]) for f in before["facts"]] == [
        (f["source"]["row"], f["source"]["col"], f["value"]) for f in after["facts"]]
    assert {(f["source"]["col"], f["qualifiers"]["unit"]) for f in after["facts"]} == {
        (1, "美元百万元"), (2, "人民币百万元"), (3, "人民币百万元")}


def test_currency_leaf_and_shared_scale_header_combine_only_their_actual_declarations():
    cells = [cell("单位：百万元", 0, 1, cs=2, column=True),
             cell("2027年", 1, 1, cs=2, column=True),
             cell("美元", 2, 1, column=True), cell("人民币", 2, 2, column=True),
             cell("Revenue", 3, 0, header=True), cell("17", 3, 1), cell("11", 3, 2)]
    result = read(cells)
    assert result["complete"] is True and result["issues"] == []
    assert len(result["facts"]) == 2
    first, second = result["facts"]
    assert (first["value"], first["qualifiers"]) == ("17", {"unit": "美元百万元", "period": "2027年", "currency": "美元"})
    assert (second["value"], second["qualifiers"]) == ("11", {"unit": "人民币百万元", "period": "2027年", "currency": "人民币"})
    assert [(c["literal"], c["source"]["row"], c["source"]["col"]) for c in first["qualifier_compositions"]["unit"]["components"]] == [
        ("百万元", 0, 1), ("美元", 2, 1)]


def test_bounded_printed_scale_caption_combines_with_a_local_currency_header():
    cells = [cell("2027年 美元", 0, 1, column=True), cell("Revenue", 1, 0, header=True), cell("17", 1, 1)]
    context = [{"text": "单位：百万元", "source": {"path": "#/candidate/caption", "lines": [1, 1]}}]
    result = read(cells, context=context)
    assert result["complete"] is True and result["issues"] == []
    assert result["facts"][0]["qualifiers"]["unit"] == "美元百万元"
    assert result["facts"][0]["qualifiers"]["period"] == "2027年"
    assert result["facts"][0]["qualifier_compositions"]["unit"]["components"][-1] == {
        "literal": "百万元", "source": {"path": "#/candidate/caption", "lines": [1, 1]}}


def test_a_complete_currency_unit_is_not_replaced_by_a_conflicting_currency_leaf():
    cells = [cell("2027年 美元百万元", 0, 1, column=True), cell("人民币", 1, 1, column=True),
             cell("Revenue", 2, 0, header=True), cell("17", 2, 1)]
    result = read(cells)
    assert result["complete"] is False
    assert any(issue["reason"] == "matrix_conflicting_header_qualifiers" for issue in result["blockers"])
    assert result["facts"][0]["value"] == "17"


def test_a_currency_unit_with_a_stray_wrapper_remains_readable_without_repairing_other_axes():
    cells = [cell("2027年", 0, 1, cs=2, column=True), cell("202", 0, 3, column=True),
             cell("人民币百万元）", 1, 1, cs=3, column=True),
             cell("Revenue", 2, 0, header=True), cell("17", 2, 1), cell("11", 2, 2), cell("9", 2, 3)]
    result = read(cells)
    assert result["complete"] is True, result["blockers"]
    assert len(result["facts"]) == 3
    assert [f["qualifiers"].get("unit") for f in result["facts"]] == ["人民币百万元"] * 3
    assert "period" not in result["facts"][2]["qualifiers"]
    assert result["facts"][2]["column_path"] == ["202", "人民币百万元）"]
    assert all("美元" not in f["qualifiers"].values() for f in result["facts"])


@pytest.mark.parametrize("references", [False, True])
def test_native_th_leading_band_needs_no_extra_scope_or_thead(references):
    attrs = ['id="entity" headers="n"', 'id="amount" headers="r"', 'id="profit" headers="p"'] if references else ["", "", ""]
    html = ('<table><tr><th id="n">Name</th><th id="r">Revenue</th><th id="p">Profit</th></tr>'
            f'<tr><td {attrs[0]}>Delta</td><td {attrs[1]}>17</td><td {attrs[2]}>5</td></tr></table>')
    result = read(html_cells(html))
    assert result["complete"] is True and result["issues"] == []
    assert len(result["facts"]) == 3
    assert [(f["subject"], f["attribute"], f["value"]) for f in result["facts"]] == [
        ("", "Name", "Delta"), ("Delta", "Revenue", "17"), ("Delta", "Profit", "5")]
    if references:
        assert [f["data_evidence"]["native_id"] for f in result["facts"]] == ["entity", "amount", "profit"]
        assert result["facts"][1]["data_evidence"]["native_attributes"]["headers"] == "r"


def test_a_td_target_does_not_become_a_header_merely_because_another_cell_references_it():
    cells = html_cells('<table><tr><td id="r">Revenue</td></tr><tr><td headers="r">17</td></tr></table>')
    result = read(cells)
    assert result["complete"] is False and result["facts"] == []
    assert {b["reason"] for b in result["blockers"]} == {"matrix_data_roles_unproven"}


def test_comparison_inherits_only_a_basis_proven_on_both_of_its_actual_period_sources():
    cells = [cell("截至12月31日止年度", 0, 1, cs=4, column=True),
             cell("金額同比變動(%)", 0, 5, rs=3, column=True),
             cell("2027年", 1, 1, cs=2, column=True), cell("2026年", 1, 3, cs=2, column=True),
             cell("金額(萬元)", 2, 1, column=True), cell("Share(%)", 2, 2, column=True),
             cell("金額(萬元)", 2, 3, column=True), cell("Share(%)", 2, 4, column=True),
             cell("Delta", 3, 0, header=True), cell("17", 3, 1), cell("60", 3, 2),
             cell("11", 3, 3), cell("55", 3, 4), cell("-5", 3, 5)]
    result = read(cells)
    assert result["complete"] is True and result["issues"] == []
    change = next(f for f in result["facts"] if f["attribute"] == "金額同比變動")
    assert change["qualifiers"] == {"unit": "%", "from_period": "2026年", "to_period": "2027年", "period_basis": "截至12月31日止年度"}
    assert change["value"] == "-5"
    assert any(e["role"] == "comparison_period_basis" and e["source"]["row"] == 0 and e["source"]["col"] == 1
               and e["text"] == "截至12月31日止年度" for e in change["header_evidence"])
    without_prior_basis = deepcopy(cells)
    without_prior_basis[0]["col_span"] = 2
    result = read(without_prior_basis)
    change = next(f for f in result["facts"] if f["attribute"] == "金額同比變動")
    assert "period_basis" not in change["qualifiers"]
