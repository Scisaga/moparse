"""Independent compact-requirement oracles; all documents are synthetic."""

from __future__ import annotations

import copy

import pytest

from moparse_eval.compact_requirements import read_compact_requirements, read_compact_schema

SCHEMA_TEXT = ("列说明：2027年金額（萬元）、佔總收入比（%）；"
               "2026年金額（萬元）、佔總收入比（%）；金額同比變動（%）。")
SCHEMA_SOURCE = {"path": "<authored-schema>", "lines": [3, 3]}
ROW_SOURCE = {"path": "<authored-row>", "lines": [7, 7]}
ROW = "Delta：2027年：17、60%；2026年：11、55%；金額同比變動：5%。"
SCHEMA4 = ("截至12月31日止年度。金額單位：人民幣千元。列说明："
           "2027年金額、佔總收入比（%）；2026年金額、佔總收入比（%）。")
FIVE = [
    ("Delta", "金額", "17", {"period": "2027年", "unit": "萬元"}),
    ("Delta", "佔總收入比", "60", {"period": "2027年", "unit": "%"}),
    ("Delta", "金額", "11", {"period": "2026年", "unit": "萬元"}),
    ("Delta", "佔總收入比", "55", {"period": "2026年", "unit": "%"}),
    ("Delta", "金額同比變動", "5", {"from_period": "2026年", "to_period": "2027年", "unit": "%"}),
]


def schema():
    result = read_compact_schema(SCHEMA_TEXT, SCHEMA_SOURCE)
    assert result["matched"] is True
    assert result["blockers"] == []
    return result["schema"]


def facts(result):
    return [(fact["subject"], fact["attribute"], fact["value"], fact["qualifiers"]) for fact in result["facts"]]


def test_declared_columns_are_four_measurements_and_one_comparison():
    result = read_compact_schema(SCHEMA_TEXT, SCHEMA_SOURCE)
    actual = result["schema"]
    assert result["matched"] is True and result["blockers"] == []
    assert [(item["period"], item["attribute"], item["unit"]) for item in actual["columns"]] == [
        ("2027年", "金額", "萬元"), ("2027年", "佔總收入比", "%"),
        ("2026年", "金額", "萬元"), ("2026年", "佔總收入比", "%"),
    ]
    assert actual["change"]["attribute"] == "金額同比變動"
    assert actual["periods"] == ["2027年", "2026年"]
    assert actual["source"] == SCHEMA_SOURCE
    assert result["text_projection_complete"] is True


def test_four_explicit_columns_do_not_require_an_unprinted_comparison_column():
    result = read_compact_schema(SCHEMA4, SCHEMA_SOURCE)
    assert result["matched"] is True and result["blockers"] == []
    assert [(column["period"], column["attribute"], column["unit"]) for column in result["schema"]["columns"]] == [
        ("2027年", "金額", "人民幣千元"), ("2027年", "佔總收入比", "%"),
        ("2026年", "金額", "人民幣千元"), ("2026年", "佔總收入比", "%"),
    ]
    assert result["schema"]["change"] is None
    assert result["schema"]["qualifier_sources"]["period_basis"] == {**SCHEMA_SOURCE, "text_span": [0, 11]}
    assert result["text_projection_complete"] is True


def test_a_four_column_record_keeps_the_fixed_measurements_group_axis_and_shared_basis_source():
    declaration = read_compact_schema(SCHEMA4, SCHEMA_SOURCE)["schema"]
    parent_source = {"path": "<actual-parent-list>", "lines": [5, 5]}
    result = read_compact_requirements("Delta：2027年17、60%；2026年11、55%", ROW_SOURCE,
        schema=declaration, parents=[{"text": "North", "source": parent_source}])
    assert result["blockers"] == []
    assert facts(result) == [
        ("Delta", "金額", "17", {"period_basis": "截至12月31日止年度", "period": "2027年", "unit": "人民幣千元", "currency": "人民幣"}),
        ("Delta", "佔總收入比", "60", {"period_basis": "截至12月31日止年度", "period": "2027年", "unit": "%"}),
        ("Delta", "金額", "11", {"period_basis": "截至12月31日止年度", "period": "2026年", "unit": "人民幣千元", "currency": "人民幣"}),
        ("Delta", "佔總收入比", "55", {"period_basis": "截至12月31日止年度", "period": "2026年", "unit": "%"}),
    ]
    for fact in result["facts"]:
        assert fact["identity_facets"] == {"group": "North"}
        assert next(item for item in fact["row_evidence"] if item["role"] == "row_group") == {
            "role": "row_group", "text": "North", "source": {**parent_source, "text_span": [0, 5]}}
        assert next(item for item in fact["row_evidence"] if item["role"] == "row_header")["text"] == "Delta"
        assert fact["source"]["qualifier_sources"]["period_basis"] == {**SCHEMA_SOURCE, "text_span": [0, 11]}
        assert fact["qualifier_sources"]["period_basis"] == {**SCHEMA_SOURCE, "text_span": [0, 11]}


def test_four_columns_without_comparison_have_no_implied_descending_year_direction():
    text = "列说明：2026年金額（萬元）、佔總收入比（%）；2027年金額（萬元）、佔總收入比（%）。"
    result = read_compact_schema(text, SCHEMA_SOURCE)
    assert result["blockers"] == [] and result["schema"]["change"] is None
    assert result["schema"]["periods"] == ["2026年", "2027年"]
    row = read_compact_requirements("Delta：2026年11、55%；2027年17、60%", ROW_SOURCE, schema=result["schema"])
    assert row["blockers"] == []
    assert [(fact["attribute"], fact["value"], fact["qualifiers"]["period"]) for fact in row["facts"]] == [
        ("金額", "11", "2026年"), ("佔總收入比", "55", "2026年"),
        ("金額", "17", "2027年"), ("佔總收入比", "60", "2027年")]


def test_an_actual_change_clause_without_a_declared_change_column_stays_pending():
    declaration = read_compact_schema(SCHEMA4, SCHEMA_SOURCE)["schema"]
    row = "Delta：2027年17、60%；2026年11、55%；金額同比變動：5%"
    result = read_compact_requirements(row, ROW_SOURCE, schema=declaration)
    assert len(result["facts"]) == 4
    assert [item["reason"] for item in result["blockers"]] == ["compact_change_column_undeclared"]
    assert result["pending_requirements"][0]["attribute"] == "金額同比變動"
    assert result["pending_requirements"][0]["value"] == "5"
    assert any(atom["text"] == "金額同比變動" for atom in result["text_atoms"])
    assert result["text_projection_complete"] is True


def test_four_column_schema_only_consumes_connectors_between_actual_declared_roles():
    text = "列说明：2027年金額（萬元）及佔總收入比（%）；2026年金額（萬元）及佔總收入比（%）。"
    result = read_compact_schema(text, SCHEMA_SOURCE)
    assert result["blockers"] == [] and result["text_projection_complete"] is True
    assert [item["text"] for item in result["controls"] if item["text"] == "及"] == ["及", "及"]
    unknown = read_compact_schema(text + "must exclude denied claims", SCHEMA_SOURCE)
    assert any(item["reason"] == "compact_unconsumed_wording" for item in unknown["blockers"])


def test_offset_schema_keeps_local_inventory_spans_and_absolute_printed_sources():
    text = SCHEMA4.replace("金額、", "金額及")
    source = {**SCHEMA_SOURCE, "text_span": [40, 40 + len(text)]}
    result = read_compact_schema(text, source)
    assert result["blockers"] == [] and result["text_projection_complete"] is True
    assert result["schema"]["qualifier_sources"]["period_basis"] == {**source, "text_span": [40, 51]}
    for item in result["consumed_spans"]:
        start, end = item["span"]
        assert item["text"] == text[start:end]
        assert item["source"]["text_span"] == [40 + start, 40 + end]
    record_source = {**ROW_SOURCE, "text_span": [40, 72]}
    row = "Delta：2027年17、60%；2026年11、55%"
    actual = read_compact_requirements(row, record_source, schema=result["schema"])
    assert actual["blockers"] == []
    assert actual["facts"][0]["source"]["qualifier_sources"]["period_basis"]["text_span"] == [40, 51]
    for item in actual["consumed_spans"]:
        start, end = item["span"]
        assert item["text"] == row[start:end]
        assert item["source"]["text_span"] == [40 + start, 40 + end]


def test_typed_name_and_group_row_evidence_point_only_to_their_own_value_spans():
    declaration = read_compact_schema(SCHEMA4, SCHEMA_SOURCE)["schema"]
    result = read_compact_requirements("2027年金額：17", ROW_SOURCE, schema=declaration, parents=[
        {"text": "Group: North", "source": {"path": "<typed-parents>", "lines": [1, 1], "text_span": [40, 52]}},
        {"text": "Name: Delta", "source": {"path": "<typed-parents>", "lines": [2, 2], "text_span": [40, 51]}},
    ])
    assert result["blockers"] == []
    assert result["facts"][0]["row_evidence"] == [
        {"role": "row_group", "text": "North", "source": {"path": "<typed-parents>", "lines": [1, 1], "text_span": [47, 52]}},
        {"role": "row_header", "text": "Delta", "source": {"path": "<typed-parents>", "lines": [2, 2], "text_span": [46, 51]}},
    ]


def test_compact_row_compiles_exactly_the_five_independent_requirements():
    result = read_compact_requirements(ROW, ROW_SOURCE, schema=schema(), identity_facets={"group": "North"})
    assert result["matched"] is True and result["blockers"] == []
    assert len(result["facts"]) == 5
    assert facts(result) == FIVE
    assert [item["role"] for item in result["facts"]] == ["metric"] * 5
    assert [item["identity_facets"] for item in result["facts"]] == [{"group": "North"}] * 5
    assert result["text_projection_complete"] is True
    assert not any(item["attribute"] == "Name" for item in result["facts"])


@pytest.mark.parametrize("clauses", [
    ["2027年：17、60%", "2026年：11、55%", "金額同比變動：5%"],
    ["2027年金額：17萬元", "2027年佔總收入比：60%", "2026年金額：11萬元", "2026年佔總收入比：55%", "金額同比變動：5%"],
])
def test_split_record_preserves_the_same_five_roles_values_and_weight(clauses):
    output = []
    for index, text in enumerate(clauses):
        result = read_compact_requirements(text, {**ROW_SOURCE, "lines": [7 + index, 7 + index]},
                                           schema=schema(), parents=["Delta"])
        assert result["matched"] is True and result["blockers"] == []
        output.extend(facts(result))
    assert len(output) == 5 and output == FIVE


def test_reordered_year_clauses_use_their_own_printed_year():
    row = "Delta：2026年：11、55%；2027年：17、60%；金額同比變動：5%。"
    result = read_compact_requirements(row, ROW_SOURCE, schema=schema())
    assert result["blockers"] == []
    assert sorted(facts(result), key=repr) == sorted(FIVE, key=repr)


def test_parent_identity_metric_period_unit_and_group_keep_distinct_roles():
    result = read_compact_requirements("金額：17", ROW_SOURCE, schema=schema(), parents=[
        "Name: Entity", "Market: Domestic", "Group: North", "Unit: 萬元", "2027年", "Delta",
    ])
    assert result["blockers"] == []
    assert facts(result) == [FIVE[0]]
    [fact] = result["facts"]
    assert fact["identity_facets"] == {"Market": "Domestic", "group": "North"}
    assert fact["subject"] == "Delta"
    assert all(value not in fact["identity_facets"].values() for value in ("Entity", "2027年", "萬元", "17"))


def test_parent_record_values_do_not_become_part_of_a_group_name():
    result = read_compact_requirements(ROW, ROW_SOURCE, schema=schema(), parents=[
        "按行業劃分", "Parent：2027年17、60%；2026年11、55%；金額同比變動5%",
    ])
    assert result["blockers"] == []
    assert len(result["facts"]) == 5
    assert result["facts"][0]["identity_facets"] == {"group": ["按行業劃分", "Parent"]}
    assert "17" not in str(result["facts"][0]["identity_facets"])


@pytest.mark.parametrize("attribute,selector,value,qualifiers", [
    ("销售收入", "美元百万元", "118,162", {"period": "2024年", "unit": "美元百万元", "currency": "美元"}),
    ("销售收入", "人民币百万元", "862,072", {"period": "2024年", "unit": "人民币百万元", "currency": "人民币"}),
    ("营业利润率", "美元列", "9.2%", {"period": "2024年", "unit": "%", "column_currency": "美元"}),
    ("营业利润率", "人民币列", "9.2%", {"period": "2024年", "unit": "%", "column_currency": "人民币"}),
])
def test_qualified_metric_leaves_preserve_currency_axis_without_false_row_paths(attribute, selector, value, qualifiers):
    text = f"2024年，{selector}：{value}"
    result = read_compact_requirements(text, ROW_SOURCE, parents=[attribute])
    assert result["matched"] is True and result["blockers"] == []
    assert result["text_projection_complete"] is True
    assert facts(result) == [("", attribute, value.rstrip("%"), qualifiers)]
    [fact] = result["facts"]
    assert fact["identity_facets"] == {}
    assert fact["source"]["path"] == ROW_SOURCE["path"]
    assert fact["source"]["attribute_source"]["parent_index"] == 0


def test_explicit_metric_subject_and_year_have_their_own_parent_sources():
    result = read_compact_requirements("2024年：17", ROW_SOURCE, parents=[
        {"text": "Name: Delta", "source": {"path": "<parents>", "lines": [1, 1]}},
        {"text": "Metric: Revenue", "source": {"path": "<parents>", "lines": [2, 2]}},
        {"text": "Unit: 万元", "source": {"path": "<parents>", "lines": [3, 3]}},
    ])
    assert result["blockers"] == []
    assert facts(result) == [("Delta", "Revenue", "17", {"unit": "万元", "period": "2024年"})]
    assert result["facts"][0]["source"]["attribute_source"] == {"path": "<parents>", "lines": [2, 2], "text_span": [8, 15]}


def test_plain_parent_metric_uses_its_actual_line_and_declares_only_the_bound_label():
    result = read_compact_requirements("2027年，万元:17", ROW_SOURCE, parents=[
        {"text": "Revenue", "source": {"path": "<actual-parent>", "lines": [7, 7]}},
    ])
    assert facts(result) == [("", "Revenue", "17", {"period": "2027年", "unit": "万元"})]
    assert result["facts"][0]["source"]["attribute_source"] == {
        "path": "<actual-parent>", "lines": [7, 7], "text_span": [0, 7]}
    assert result["metric_declarations"] == [{
        "text": "Revenue", "role": "label", "source": {"path": "<actual-parent>", "lines": [7, 7], "text_span": [0, 7]},
        "parent_text": "Revenue", "parent_source": {"path": "<actual-parent>", "lines": [7, 7]},
        "parent_index": 0, "provenance": "qualified_period_value_parent",
    }]


def test_a_compact_record_parent_remains_a_subject_locator_instead_of_a_metric_declaration():
    result = read_compact_requirements("2027年：17、60%；2026年：11、55%；金額同比變動：5%。", ROW_SOURCE,
        schema=schema(), parents=[{"text": "Delta", "source": {"path": "<actual-parent>", "lines": [7, 7]}}])
    assert result["blockers"] == [] and len(result["facts"]) == 5
    assert all(fact["subject"] == "Delta" for fact in result["facts"])
    assert result.get("metric_declarations", []) == []


def test_an_explicit_subject_parent_does_not_supply_a_missing_metric_for_a_year_leaf():
    result = read_compact_requirements("2027年，万元:17", ROW_SOURCE, parents=[
        {"text": "Name: Delta", "source": {"path": "<subject-parent>", "lines": [7, 7]}},
    ])
    assert result["facts"] == [] and result.get("metric_declarations", []) == []
    assert [item["reason"] for item in result["blockers"]] == ["period_value_metric_unavailable"]


def test_flattened_year_unit_leaf_keeps_the_outer_metric_instead_of_a_fake_subject():
    result = read_compact_requirements("Revenue：2024年，美元百万元：17", ROW_SOURCE, parents=["Name: Delta"])
    assert result["blockers"] == []
    assert facts(result) == [("Delta", "Revenue", "17", {"period": "2024年", "unit": "美元百万元", "currency": "美元"})]
    assert result["text_atoms"][0]["role"] == "label"


def test_explicit_metric_parent_allows_a_flattened_named_record_leaf():
    result = read_compact_requirements("Delta：2024年：17", ROW_SOURCE, parents=["Metric: Revenue"])
    assert result["blockers"] == []
    assert facts(result) == [("Delta", "Revenue", "17", {"period": "2024年"})]


def test_two_untyped_leaf_labels_do_not_force_a_subject_metric_interpretation():
    result = read_compact_requirements("Revenue：2024年：17", ROW_SOURCE, parents=["North"])
    assert result["matched"] is True
    assert any(blocker["reason"] == "compact_leaf_parent_roles_ambiguous" for blocker in result["blockers"])


def test_percent_leaf_does_not_inherit_the_amount_unit_or_currency():
    result = read_compact_requirements("2024年，美元列：9.2%", ROW_SOURCE, parents=["Margin"],
                                       qualifiers={"unit": "人民币百万元", "currency": "人民币"})
    assert result["blockers"] == []
    assert result["facts"][0]["qualifiers"] == {"unit": "%", "period": "2024年", "column_currency": "美元"}


def test_published_caption_shape_has_five_measurements_with_period_basis_and_local_units():
    text = ("截至12月31日止年度。金額單位：人民幣千元。各項分別列示"
            "2027年金額及佔營業收入比、2026年金額及佔營業收入比、金額同比變動。")
    declaration = read_compact_schema(text, SCHEMA_SOURCE)
    assert declaration["blockers"] == []
    result = read_compact_requirements("Delta：2027年17、60%；2026年11、55%；金額同比變動5%。",
                                       ROW_SOURCE, schema=declaration["schema"])
    assert result["blockers"] == [] and len(result["facts"]) == 5
    assert [fact["attribute"] for fact in result["facts"]] == ["金額", "佔營業收入比", "金額", "佔營業收入比", "金額同比變動"]
    assert result["facts"][0]["qualifiers"] == {"unit": "人民幣千元", "currency": "人民幣", "period": "2027年", "period_basis": "截至12月31日止年度"}
    assert result["facts"][1]["qualifiers"] == {"unit": "%", "period": "2027年", "period_basis": "截至12月31日止年度"}
    assert result["facts"][4]["qualifiers"] == {"unit": "%", "from_period": "2026年", "to_period": "2027年", "period_basis": "截至12月31日止年度"}


def test_every_projected_atom_and_control_has_the_actual_printed_span():
    for text, source, result in (
        (SCHEMA_TEXT, SCHEMA_SOURCE, read_compact_schema(SCHEMA_TEXT, SCHEMA_SOURCE)),
        (ROW, ROW_SOURCE, read_compact_requirements(ROW, ROW_SOURCE, schema=schema())),
    ):
        coverage = [0] * len(text)
        assert result["text_atoms"] and result["controls"]
        for item in result["consumed_spans"]:
            start, end = item["span"]
            assert item["text"] == text[start:end]
            assert item["source"]["path"] == source["path"]
            assert item["source"]["lines"] == source["lines"]
            for position in range(start, end):
                coverage[position] += 1
        assert coverage == [1] * len(text)


@pytest.mark.parametrize("old,new,changed", [
    ("17、", "-17、", ("value", "-17")),
    ("17、", "18、", ("value", "18")),
    ("17、", "17元、", ("unit", "元")),
])
def test_wrong_values_signs_and_units_are_read_faithfully_instead_of_repaired(old, new, changed):
    result = read_compact_requirements(ROW.replace(old, new), ROW_SOURCE, schema=schema())
    assert result["blockers"] == [] and len(result["facts"]) == 5
    assert result["facts"][0].get(changed[0], result["facts"][0]["qualifiers"].get(changed[0])) == changed[1]


def test_unknown_year_and_wrong_tuple_arity_remain_unsupported_instead_of_losing_targets():
    for text in (ROW.replace("2027年：", "2025年："), ROW.replace("17、60%", "17、60%、23")):
        result = read_compact_requirements(text, ROW_SOURCE, schema=schema())
        assert result["matched"] is True
        assert any(blocker["reason"] == "compact_value_arity_ambiguous" for blocker in result["blockers"])


def test_compact_values_need_the_explicit_column_declaration():
    result = read_compact_requirements(ROW, ROW_SOURCE)
    assert result["matched"] is True
    assert result["facts"] == []
    assert result["blockers"][0]["reason"] == "compact_column_schema_unavailable"


@pytest.mark.parametrize("extra", ["must exclude denied claims", "不包括例外", "unknown_metric", "及", "and", "列说明", "Units"])
def test_unrecognized_wording_cannot_disappear_into_relation_controls(extra):
    declaration = read_compact_schema(SCHEMA_TEXT + extra, SCHEMA_SOURCE)
    assert declaration["matched"] is True
    assert any(item["reason"] == "compact_unconsumed_wording" for item in declaration["blockers"])
    assert declaration["text_projection_complete"] is False
    assert not any(item["span"][1] > len(SCHEMA_TEXT) for item in declaration["controls"])


def test_description_without_an_explicit_column_declaration_is_not_a_schema():
    result = read_compact_schema("The 2027年 amount and 2026年 amount changed.", SCHEMA_SOURCE)
    assert result["matched"] is False and result["schema"] is None


@pytest.mark.parametrize("replacement", ["2028年", "2027年"])
def test_comparison_direction_is_not_guessed_from_reversed_or_duplicate_year_columns(replacement):
    result = read_compact_schema(SCHEMA_TEXT.replace("2026年", replacement), SCHEMA_SOURCE)
    assert result["matched"] is True
    assert result["schema"] is None
    assert result["blockers"][0]["reason"] == "compact_comparison_period_order_unsupported"


def test_incomplete_column_declaration_is_not_a_complete_text_projection():
    result = read_compact_schema("列说明：2027年金額、佔總收入比。", SCHEMA_SOURCE)
    assert result["matched"] is True and result["schema"] is None
    assert result["blockers"]
    assert result["text_projection_complete"] is False


def test_source_names_and_numeric_values_never_select_different_roles():
    result = read_compact_requirements(ROW.replace("Delta", "Omega").replace("17", "9901"),
                                       {"path": "<unrelated-file>", "lines": [88, 88]}, schema=schema())
    assert result["blockers"] == []
    assert len(result["facts"]) == 5
    assert [fact["attribute"] for fact in result["facts"]] == [item[1] for item in FIVE]
    assert result["facts"][0]["value"] == "9901"
    assert all(fact["subject"] == "Omega" for fact in result["facts"])


def test_reader_does_not_mutate_declared_context_or_schema():
    declaration = schema()
    saved = copy.deepcopy(declaration)
    qualifiers = {"note": "subject to review"}
    read_compact_requirements(ROW, ROW_SOURCE, schema=declaration, qualifiers=qualifiers)
    assert declaration == saved
    assert qualifiers == {"note": "subject to review"}


def test_period_value_without_a_metric_preserves_an_unresolved_obligation():
    result = read_compact_requirements("2027年：17", ROW_SOURCE)
    assert result["matched"] is True
    assert result["facts"] == []
    assert [item["reason"] for item in result["blockers"]] == ["period_value_metric_unavailable"]
    [pending] = result["pending_requirements"]
    assert pending["value"] == "17" and pending["qualifiers"] == {"period": "2027年"}
    assert pending["source"]["text_span"] == [6, 8]
    assert [atom["text"] for atom in result["text_atoms"]] == ["2027年", "17"]
