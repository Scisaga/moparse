"""Independent literal-capacity tests for candidate-local schema aliases."""

import json
from collections import Counter
from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells
from moparse_eval.compact_requirements import read_compact_requirements, read_compact_schema
from moparse_eval.expected_report import _complete_text_trace, validate_evidence
from moparse_eval.matrix_evidence import read_matrix
from moparse_eval.text_projection import (
    combine_text_projections,
    project_compact_text,
    project_literal_text,
    project_metric_declaration,
    project_table_text,
)
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

TABLE = ('<table><tr><th id="name" scope="col">Name</th><th id="revenue" scope="col">Revenue</th></tr>'
         '<tr><td id="name-one" headers="name">Delta</td><td id="revenue-one" headers="revenue">17</td></tr>'
         '<tr><td id="name-two" headers="name">Kappa</td><td id="revenue-two" headers="revenue">29</td></tr></table>')
PROPERTY = ('<table><tr><th scope="col">Property</th><th scope="col">Value</th></tr>'
            '<tr><td>Name</td><td>Delta</td></tr><tr><td>Revenue</td><td>17</td></tr>'
            '<tr><td>Name</td><td>Kappa</td></tr><tr><td>Revenue</td><td>29</td></tr></table>')
EIGHT = Counter({"Name": 2, "Revenue": 2, "Delta": 1, "17": 1, "Kappa": 1, "29": 1})


def table_projection(html, path="<authored-table>"):
    cells = html_cells(html)
    source = {"path": path}
    matrix = read_matrix(cells, source=source)
    return project_table_text(cells, matrix, source)


def words(projection):
    return Counter(atom["text"] for atom in projection["atoms"])


@pytest.mark.parametrize("html", [TABLE, PROPERTY], ids=["shared-headers", "property-value-records"])
def test_two_records_and_eight_required_literal_occurrences_are_preserved(html):
    projection = table_projection(html)
    assert projection["complete"], projection["blockers"]
    assert words(projection) == EIGHT
    labels = [atom for atom in projection["atoms"] if atom["role"] == "label"]
    assert len(labels) == 4
    assert len({atom["data_object"]["id"] for atom in labels}) == 4
    for atom in labels:
        assert atom["origins"]
        assert atom["data_object"]["source"]["cell"]
        assert atom["origins"][0]["source"]["cell"]


def test_header_capacity_is_bounded_by_actual_objects_and_has_no_reference_argument():
    one = TABLE.replace('<tr><td id="name-two" headers="name">Kappa</td><td id="revenue-two" headers="revenue">29</td></tr>', "")
    actual = table_projection(one)
    assert words(actual) == Counter({"Name": 1, "Revenue": 1, "Delta": 1, "17": 1})
    assert len(actual["aliases"]) == 2
    cells = html_cells(one)
    matrix = read_matrix(cells, source={"path": "one"})
    with pytest.raises(TypeError):
        project_table_text(cells, matrix, {"path": "one"}, expected_count=100)


def test_real_name_value_repetitions_are_not_schema_restatements():
    actual = table_projection(TABLE.replace("Kappa", "Delta"))
    assert words(actual)["Delta"] == 2
    values = [atom for atom in actual["atoms"] if atom["text"] == "Delta"]
    assert [atom["projection_kind"] for atom in values] == ["literal", "literal"]
    assert len({atom["source"]["cell"] for atom in values}) == 2


def test_ordinary_same_word_and_same_unit_repetitions_never_merge():
    projections = [project_literal_text("万元 remains literal.", {"path": "prose", "lines": [line, line]})
                   for line in (1, 3)]
    actual = combine_text_projections(projections)
    assert words(actual) == Counter({"万元 remains literal.": 2})
    assert actual["aliases"] == []


def test_same_named_headers_in_different_tables_remain_separate_origins_and_objects():
    one = TABLE.replace('<tr><td id="name-two" headers="name">Kappa</td><td id="revenue-two" headers="revenue">29</td></tr>', "")
    actual = combine_text_projections([table_projection(one, "table-a"), table_projection(one, "table-b")])
    assert words(actual) == Counter({"Name": 2, "Revenue": 2, "Delta": 2, "17": 2})
    assert len({atom["data_object"]["id"] for atom in actual["atoms"] if atom.get("data_object")}) == 4


def test_explicit_reference_misbinding_does_not_remove_visible_text_capacity():
    changed = TABLE.replace('headers="name"', 'headers="temporary"').replace(
        'headers="revenue"', 'headers="name"').replace('headers="temporary"', 'headers="revenue"')
    assert words(table_projection(changed)) == EIGHT


def test_one_inline_percent_cannot_supply_a_different_quantity_without_common_declaration():
    reference = '<table><tr><th scope="col">Fee</th><th scope="col">Allocation</th></tr><tr><td>10%</td><td>60%</td></tr></table>'
    candidate = reference.replace("10%", "10")
    expected_text = table_projection(reference)
    actual_text = table_projection(candidate)
    assert words(expected_text) == Counter({"Fee": 1, "Allocation": 1, "10": 1, "60": 1, "%": 2})
    assert words(actual_text) == Counter({"Fee": 1, "Allocation": 1, "10": 1, "60": 1, "%": 1})
    percent = [atom for atom in actual_text["atoms"] if atom["text"] == "%"]
    assert len(percent) == 1
    assert percent[0]["data_object"]["source"]["col"] == 1


@pytest.mark.parametrize("suffix", [False, True])
def test_unit_header_and_inline_reiteration_count_once_for_each_actual_quantity(suffix):
    html = ('<table><tr><th scope="col">Revenue（萬元）</th></tr>'
            f'<tr><td>17{"萬元" if suffix else ""}</td></tr></table>')
    actual = table_projection(html)
    assert words(actual) == Counter({"Revenue": 1, "17": 1, "萬元": 1})
    unit = next(atom for atom in actual["atoms"] if atom["text"] == "萬元")
    assert len(unit["origins"]) == (2 if suffix else 1)


def test_known_metric_and_its_printed_unit_suffix_keep_separate_literals():
    html = '<table><tr><th scope="col">金額萬元</th></tr><tr><td>17</td></tr></table>'
    assert words(table_projection(html)) == Counter({"金額": 1, "萬元": 1, "17": 1})


def test_conflicting_inline_unit_does_not_erase_the_actually_printed_header_unit():
    html = '<table><tr><th scope="col">Fee（%）</th></tr><tr><td>10萬元</td></tr></table>'
    assert words(table_projection(html)) == Counter({"Fee": 1, "%": 1, "10": 1, "萬元": 1})


@pytest.mark.parametrize("literal", ["-17", "1 2", "17.00", "(17)"])
def test_sign_decimal_accounting_parentheses_and_numeric_spaces_remain_literal(literal):
    html = f'<table><tr><th scope="col">Revenue</th></tr><tr><td>{literal}</td></tr></table>'
    actual = table_projection(html)
    assert words(actual)[literal] == 1


@pytest.mark.parametrize("label", ["元器件收入", "人工成本", "ISO2027编码"])
def test_lexical_unit_or_year_characters_inside_metric_names_are_not_controls(label):
    html = f'<table><tr><th scope="col">{label}</th></tr><tr><td>17</td></tr></table>'
    assert words(table_projection(html)) == Counter({label: 1, "17": 1})


def test_unproven_layout_grid_keeps_all_real_literals_and_creates_no_aliases():
    html = '<table><tr><td>审核意见</td><td>已阅读并签署</td></tr><tr><td>审核意见</td><td>待批准</td></tr></table>'
    actual = table_projection(html)
    assert words(actual) == Counter({"审核意见": 2, "已阅读并签署": 1, "待批准": 1})
    assert actual["aliases"] == []
    assert not actual["complete"]


def test_projection_does_not_mutate_native_cells_or_candidate_evidence():
    cells = html_cells(TABLE)
    matrix = read_matrix(cells, source={"path": "readonly"})
    before = deepcopy((cells, matrix))
    project_table_text(cells, matrix, {"path": "readonly"})
    assert (cells, matrix) == before


def test_compact_projection_uses_only_its_explicit_schema_and_actual_five_value_objects():
    schema_text = "列说明：2027年金額（萬元）、佔總收入比（%）；2026年金額（萬元）、佔總收入比（%）；金額同比變動（%）。"
    record_text = "Delta：2027年：17、60%；2026年：11、55%；金額同比變動：5%。"
    schema_result = read_compact_schema(schema_text, {"path": "compact", "lines": [1, 1]})
    record_result = read_compact_requirements(record_text, {"path": "compact", "lines": [3, 3]}, schema=schema_result["schema"])
    actual = combine_text_projections([
        project_compact_text(schema_result, schema_result["schema"], {"path": "compact", "lines": [1, 1]}),
        project_compact_text(record_result, schema_result["schema"], {"path": "compact", "lines": [3, 3]}),
    ])
    assert actual["complete"], actual["blockers"]
    assert words(actual) == Counter({"Delta": 1, "金額": 2, "佔總收入比": 2, "金額同比變動": 1,
                                    "2027年": 2, "2026年": 2, "萬元": 2, "%": 3,
                                    "17": 1, "60": 1, "11": 1, "55": 1, "5": 1})
    aliases = [atom for atom in actual["atoms"] if atom.get("data_object")]
    assert len({atom["data_object"]["id"] for atom in aliases}) == 5


def test_parent_metric_declaration_has_exactly_one_alias_for_each_independently_printed_leaf():
    parent = {"text": "Revenue", "source": {"path": "<parent-leaves>", "lines": [1, 1]}}
    projections = []
    for line, text in [(2, "2027年，万元:17"), (3, "2026年，万元:11")]:
        source = {"path": "<parent-leaves>", "lines": [line, line]}
        result = read_compact_requirements(text, source, parents=[parent])
        projections.append(project_compact_text(result, None, source, raw_text=text))
        if line == 2:
            projections.append(project_metric_declaration(result["metric_declarations"][0]))
    actual = combine_text_projections(projections)
    assert actual["complete"] and actual["blockers"] == []
    assert words(actual) == Counter({"Revenue": 2, "2027年": 1, "2026年": 1, "万元": 2, "17": 1, "11": 1})
    assert sum(len(atom["text"]) for atom in actual["atoms"]) == 32
    labels = [atom for atom in actual["atoms"] if atom["text"] == "Revenue"]
    assert len(labels) == 2 and all(atom["projection_kind"] == "bounded_alias" for atom in labels)
    assert all(atom["source"] == {"path": "<parent-leaves>", "lines": [1, 1], "text_span": [0, 7]} for atom in labels)
    assert len({atom["data_object"]["id"] for atom in labels}) == 2


def test_unused_parent_declaration_remains_one_literal_and_never_creates_an_alias_budget():
    projection = project_metric_declaration({
        "text": "Revenue", "role": "label", "source": {"path": "<orphan-parent>", "lines": [1, 1], "text_span": [0, 7]},
        "parent_text": "Revenue", "parent_source": {"path": "<orphan-parent>", "lines": [1, 1]},
        "provenance": "qualified_period_value_parent",
    })
    actual = combine_text_projections([projection])
    assert words(actual) == Counter({"Revenue": 1})
    assert actual["aliases"] == []


def test_explicit_metric_key_is_control_but_its_value_keeps_the_parent_source():
    text, source = "2027年，万元:17", {"path": "<typed-parent>", "lines": [3, 3]}
    result = read_compact_requirements(text, source, parents=[{
        "text": "Metric: Revenue", "source": {"path": "<typed-parent>", "lines": [1, 1]},
    }])
    actual = combine_text_projections([
        project_metric_declaration(result["metric_declarations"][0]),
        project_compact_text(result, None, source, raw_text=text),
    ])
    assert actual["complete"] and actual["blockers"] == []
    assert words(actual) == Counter({"Revenue": 1, "2027年": 1, "万元": 1, "17": 1})
    label = next(atom for atom in actual["atoms"] if atom["text"] == "Revenue")
    assert label["source"] == {"path": "<typed-parent>", "lines": [1, 1], "text_span": [8, 15]}
    assert any(control["text"] == "Metric: " for control in actual["controls"])


def test_a_child_pseudo_parent_source_is_insufficient_to_project_a_metric_declaration():
    result = read_compact_requirements("2027年，万元:17", {"path": "<child>", "lines": [4, 4]}, parents=["Revenue"])
    projection = project_compact_text(result, None, {"path": "<child>", "lines": [4, 4]})
    assert projection["complete"] is False
    assert any(item["reason"] == "compact_parent_declaration_source_unavailable" for item in projection["blockers"])


def test_inline_measurement_projection_rejects_a_partial_value_span_without_rebuilding_an_answer():
    cells = html_cells('<table><tr><th scope="col">Revenue</th></tr><tr><td>$17</td></tr></table>')
    source = {"path": "<own-measurement-cell>"}
    matrix = read_matrix(cells, source=source)
    matrix["facts"][0]["value_source"]["cell_text_span"] = [1, 2]
    actual = project_table_text(cells, matrix, source)
    assert actual["complete"] is False
    assert any(blocker["reason"] == "measurement_literal_source_mismatch" for blocker in actual["blockers"])
    assert words(actual)["$17"] == 1
    assert words(actual)["17"] == 0


def test_duplicate_measurement_metadata_cannot_create_more_than_one_cell_of_text_capacity():
    cells = html_cells('<table><tr><th scope="col">Revenue</th></tr><tr><td>$17</td></tr></table>')
    source = {"path": "<one-actual-measurement>"}
    matrix = read_matrix(cells, source=source)
    matrix["facts"].append(deepcopy(matrix["facts"][0]))
    actual = project_table_text(cells, matrix, source)
    assert actual["complete"] and actual["blockers"] == []
    assert words(actual) == Counter({"Revenue": 1, "$": 1, "17": 1})


def test_inline_measurement_prefix_literals_pass_the_complete_source_capacity_report_guard():
    score = grade_layers(compile_markdown("Revenue:$17"), read_candidate_markdown(
        '<table><tr><th scope="col">Revenue</th></tr><tr><td>$17</td></tr></table>'))
    assert score["layers"]["T"]["score"] == 100
    _complete_text_trace(score)


AMBIGUOUS_HEADER = (
    '<table><tr><th scope="col">Item</th><th scope="col">2027年</th><th scope="col">2026年</th></tr>'
    '<tr><td></td><th colspan="2" scope="col">（美元百万元）（人民币百万元）</th></tr>'
    '<tr><th scope="row">Revenue</th><td>17</td><td>11</td></tr>'
    '<tr><th scope="row">Profit</th><td>5</td><td>3</td></tr></table>'
)


def test_two_printed_units_remain_text_evidence_when_their_business_binding_is_ambiguous():
    cells = html_cells(AMBIGUOUS_HEADER)
    source = {"path": "<ambiguous-two-unit-header>"}
    matrix = read_matrix(cells, source=source)
    assert len(matrix["facts"]) == 4
    assert len(matrix["issues"]) == 4
    assert [issue["category"] for issue in matrix["issues"]] == ["candidate_ambiguity"] * 4
    assert [issue["reason"] for issue in matrix["issues"]] == ["matrix_header_qualifier_ambiguous"] * 4
    assert all("unit" not in fact["qualifiers"] for fact in matrix["facts"])
    assert all(fact["ambiguous_qualifiers"]["unit"] == ["美元百万元", "人民币百万元"] for fact in matrix["facts"])
    header = cells[4]
    assert header["text"] == "（美元百万元）（人民币百万元）"
    assert any(role["id"] == header["id"] and role["role"] == "column_header" for role in matrix["roles"])
    before = deepcopy(matrix)
    projection = project_table_text(cells, matrix, source)
    assert projection["complete"]
    assert matrix == before
    for unit, span in [("美元百万元", [1, 6]), ("人民币百万元", [8, 14])]:
        actual = [atom for atom in projection["atoms"] if atom["text"] == unit]
        assert len(actual) == 4
        assert {(atom["data_object"]["source"]["row"], atom["data_object"]["source"]["col"]) for atom in actual} == {
            (2, 1), (2, 2), (3, 1), (3, 2)}
        assert all(atom["source"]["cell"] == header["id"] and atom["source"]["cell_text_span"] == span for atom in actual)
    # These finite aliases prove text presence over the declared header span.
    # The two alternatives are not resolved or copied into business answers.
    assert all("unit" not in fact["qualifiers"] for fact in matrix["facts"])


def test_stale_ambiguity_metadata_cannot_restore_a_unit_absent_from_the_actual_cell():
    cells = html_cells(AMBIGUOUS_HEADER)
    source = {"path": "<printed-unit-only>"}
    matrix = read_matrix(cells, source=source)
    cells[4]["text"] = "（美元百万元）"
    # Deliberately retain the obsolete alternate in reader diagnostics. Text
    # projection must still obtain words exclusively from the actual cell.
    assert matrix["facts"][0]["ambiguous_qualifiers"]["unit"] == ["美元百万元", "人民币百万元"]
    actual = project_table_text(cells, matrix, source)
    assert words(actual)["美元百万元"] == 4
    assert words(actual)["人民币百万元"] == 0


def test_unclassified_layout_preserves_a_compound_unit_literal_without_inventing_aliases():
    html = '<table><tr><td>审核意见</td><td>（美元百万元）（人民币百万元）</td></tr><tr><td>说明</td><td>待批准</td></tr></table>'
    actual = table_projection(html)
    assert words(actual) == Counter({"审核意见": 1, "（美元百万元）（人民币百万元）": 1, "说明": 1, "待批准": 1})
    assert actual["aliases"] == []
    assert [atom["source"]["cell"] for atom in actual["atoms"]] == [
        "#/html::html/cell[0]", "#/html::html/cell[1]", "#/html::html/cell[2]", "#/html::html/cell[3]"]


def _table_score():
    score = grade_layers(compile_markdown(TABLE), read_candidate_markdown(TABLE))
    validate_evidence(score)
    return score


def test_report_rejects_reused_alias_object_even_when_atom_ids_are_distinct():
    damaged = deepcopy(_table_score())
    rows = [row for row in damaged["outcomes"] if row["layer"] == "T" and row["actual"]["text"] == "Name"]
    assert len(rows) == 2
    assert rows[0]["actual"]["data_object"]["id"] != rows[1]["actual"]["data_object"]["id"]
    identifier = rows[1]["actual"]["id"]
    rows[1]["actual"] = deepcopy(rows[0]["actual"])
    rows[1]["actual"]["id"] = identifier
    with pytest.raises(ValueError):
        validate_evidence(damaged)


@pytest.mark.parametrize("mutation", ["origin_text", "origin_span", "alias_key"])
def test_report_rejects_unproved_alias_origin_and_capacity_keys(mutation):
    damaged = deepcopy(_table_score())
    row = next(row for row in damaged["outcomes"] if row["layer"] == "T" and row["actual"].get("data_object"))
    atom = row["actual"]
    if mutation == "origin_text":
        atom["origins"][0]["text"] = "A word absent from the actual header"
    elif mutation == "origin_span":
        atom["origins"][0]["source"]["cell_text_span"] = [0, 999]
    else:
        atom["alias_key"] = "invented-capacity-without-data-object"
    with pytest.raises(ValueError):
        validate_evidence(damaged)


def test_report_rejects_reusing_one_real_prose_occurrence_under_a_new_id():
    text = "Same sentence.\n\nSame sentence.\n\nName: Delta; Revenue: 17\n"
    damaged = grade_layers(compile_markdown(text), read_candidate_markdown(text))
    # This component checks T occurrence proof. An independent unresolved
    # relation collision must continue to prevent complete publication.
    _complete_text_trace(damaged)
    rows = [row for row in damaged["outcomes"] if row["layer"] == "T" and row["actual"]["text"] == "Same sentence."]
    assert len(rows) == 2
    identifier = rows[1]["actual"]["id"]
    rows[1]["actual"] = deepcopy(rows[0]["actual"])
    rows[1]["actual"]["id"] = identifier
    with pytest.raises(ValueError):
        _complete_text_trace(damaged)


def _replace_candidate_manifest(score, atom):
    candidates = score["text_evidence"]["candidate_atoms"]
    index = next(index for index, old in enumerate(candidates) if old["id"] == atom["id"])
    candidates[index] = deepcopy(atom)


def test_report_rechecks_alias_capacity_even_if_the_duplicated_manifest_agrees_with_outcomes():
    damaged = deepcopy(_table_score())
    rows = [row for row in damaged["outcomes"] if row["layer"] == "T" and row["actual"]["text"] == "Name"]
    identifier = rows[1]["actual"]["id"]
    rows[1]["actual"] = deepcopy(rows[0]["actual"])
    rows[1]["actual"]["id"] = identifier
    _replace_candidate_manifest(damaged, rows[1]["actual"])
    with pytest.raises(ValueError, match="capacity"):
        validate_evidence(damaged)


def test_report_rejects_an_invented_data_object_even_if_source_ids_are_internally_consistent():
    damaged = deepcopy(_table_score())
    atom = next(row["actual"] for row in damaged["outcomes"] if row["layer"] == "T" and row["actual"].get("data_object"))
    obj = atom["data_object"]
    decoded = json.loads(obj["id"].removeprefix("data:"))
    decoded.update(row=999, cell="invented-cell-outside-the-saved-table")
    obj["source"].update(row=999, cell="invented-cell-outside-the-saved-table")
    obj["id"] = "data:" + json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    atom["alias_key"] = ":".join((obj["id"], atom["role"], atom["text"]))
    _replace_candidate_manifest(damaged, atom)
    with pytest.raises(ValueError, match="outside the actual cells"):
        validate_evidence(damaged)


def test_report_rechecks_true_prose_occurrences_when_a_forged_manifest_repeats_the_same_source():
    text = "Same sentence.\n\nSame sentence.\n\nName: Delta; Revenue: 17\n"
    damaged = grade_layers(compile_markdown(text), read_candidate_markdown(text))
    _complete_text_trace(damaged)
    rows = [row for row in damaged["outcomes"] if row["layer"] == "T" and row["actual"]["text"] == "Same sentence."]
    identifier = rows[1]["actual"]["id"]
    rows[1]["actual"] = deepcopy(rows[0]["actual"])
    rows[1]["actual"]["id"] = identifier
    _replace_candidate_manifest(damaged, rows[1]["actual"])
    with pytest.raises(ValueError, match="already consumed"):
        _complete_text_trace(damaged)


@pytest.mark.parametrize("text", [
    "Same sentence. Same sentence.\n\nName: Delta; Revenue: 17\n",
    "The board approves\n\nthe payment.\n\nName: Delta; Revenue: 17\n",
])
def test_report_preserves_real_repetitions_and_legitimate_prose_fragments(text):
    score = grade_layers(compile_markdown(text), read_candidate_markdown(text))
    _complete_text_trace(score)


def test_report_validates_compact_aliases_against_their_actual_raw_fragment_ranges():
    text = ("列说明：2027年金額（萬元）、佔總收入比（%）；2026年金額（萬元）、佔總收入比（%）；金額同比變動（%）。\n\n"
            "Delta：2027年：17、60%；2026年：11、55%；金額同比變動：5%。\n")
    score = grade_layers(compile_markdown(text), read_candidate_markdown(text))
    assert len([row for row in score["outcomes"] if row["layer"] == "B"]) == 5
    validate_evidence(score)
