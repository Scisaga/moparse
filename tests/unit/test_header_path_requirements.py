"""Hand-authored role, value and source oracles for printed header paths."""

from copy import deepcopy

import pytest

from moparse_eval.header_path_requirements import read_header_path_requirements

SOURCE = {"path": "<printed-path-record>", "lines": [9, 9]}
FOUR = ("North: / Delta；截至12月31日止年度 / 2027年 / 金額人民幣千元：17；"
        "截至12月31日止年度 / 2027年 / 佔總收入比：60%；"
        "截至12月31日止年度 / 2026年 / 金額人民幣千元：11；"
        "截至12月31日止年度 / 2026年 / 佔總收入比：55%。")


def projection(facts):
    return [(f["subject"], f["attribute"], f["value"], f["qualifiers"], f["identity_facets"]) for f in facts]


def test_four_measurements_are_independent_without_a_synthetic_name_question():
    result = read_header_path_requirements(FOUR, SOURCE, scope=["Financial review", "Revenue"])
    assert result["matched"] is True and result["blockers"] == []
    assert projection(result["facts"]) == [
        ("Delta", "金額", "17", {"period_basis": "截至12月31日止年度", "period": "2027年", "unit": "人民幣千元", "currency": "人民幣"}, {"group": "North"}),
        ("Delta", "佔總收入比", "60", {"period_basis": "截至12月31日止年度", "period": "2027年", "unit": "%"}, {"group": "North"}),
        ("Delta", "金額", "11", {"period_basis": "截至12月31日止年度", "period": "2026年", "unit": "人民幣千元", "currency": "人民幣"}, {"group": "North"}),
        ("Delta", "佔總收入比", "55", {"period_basis": "截至12月31日止年度", "period": "2026年", "unit": "%"}, {"group": "North"}),
    ]
    assert all(fact["role"] == "metric" and fact["scope"] == ["Financial review", "Revenue"] for fact in result["facts"])
    assert len({fact["record_id"] for fact in result["facts"]}) == 1


def test_yoy_has_one_preserved_assertion_and_pending_period_binding_without_guessing_from_the_other_years():
    text = FOUR.rstrip("。") + "；金額同比變動：5%。"
    result = read_header_path_requirements(text, SOURCE)
    assert len(result["facts"]) == 5
    assert projection(result["facts"])[-1] == ("Delta", "金額同比變動", "5", {"unit": "%"}, {"group": "North"})
    assert [blocker["reason"] for blocker in result["blockers"]] == ["header_path_comparison_periods_unresolved"]
    assert result["pending_requirements"][0]["attribute"] == "金額同比變動"
    assert "from_period" not in result["facts"][-1]["qualifiers"] and "to_period" not in result["facts"][-1]["qualifiers"]


def test_explicit_from_and_to_roles_can_bind_the_comparison_without_a_largest_year_heuristic():
    result = read_header_path_requirements("North / Delta；From:2027年 / To:2026年 / 金額同比變動：5%", SOURCE)
    assert result["blockers"] == []
    assert result["facts"][0]["qualifiers"] == {"from_period": "2027年", "to_period": "2026年", "unit": "%"}


def test_year_and_unit_only_columns_take_a_metric_from_the_actual_measurement_row_label():
    result = read_header_path_requirements("Revenue；2027年 / 人民币千元：17；2026年 / 美元：11", SOURCE)
    assert result["blockers"] == []
    assert projection(result["facts"]) == [
        ("", "Revenue", "17", {"period": "2027年", "unit": "人民币千元", "currency": "人民币"}, {}),
        ("", "Revenue", "11", {"period": "2026年", "unit": "美元", "currency": "美元"}, {}),
    ]


def test_an_opaque_row_name_is_not_guessed_to_be_a_metric_when_columns_only_declare_year_and_unit():
    result = read_header_path_requirements("Delta；2027年 / 万元：17；2026年 / 万元：11", SOURCE)
    assert result["matched"] is True and result["facts"] == []
    assert len(result["pending_requirements"]) == 2
    assert {blocker["reason"] for blocker in result["blockers"]} == {"header_path_row_metric_unproven"}


@pytest.mark.parametrize("group", ["North", "South", "按行業劃分", "按地區劃分"])
def test_group_identity_is_copied_only_from_its_own_row_path(group):
    result = read_header_path_requirements(f"{group}: / Delta；2027年 / 金額万元：17", SOURCE)
    [fact] = result["facts"]
    assert fact["subject"] == "Delta" and fact["identity_facets"] == {"group": group}
    group_source = next(item for item in fact["row_evidence"] if item["role"] == "row_group")["source"]
    assert group_source["text_span"] == [0, len(group)]


def test_multiple_printed_group_levels_remain_a_group_path_with_independent_sources():
    result = read_header_path_requirements("North / Industry / Delta；2027年 / Amount万元：17", SOURCE)
    [fact] = result["facts"]
    assert fact["subject"] == "Delta" and fact["identity_facets"] == {"group": ["North", "Industry"]}
    assert [item["text"] for item in fact["row_evidence"] if item["role"] == "row_group"] == ["North", "Industry"]


@pytest.mark.parametrize("text", [
    "Location:https://example.test/2027/Revenue17", "Date and time:2027-05-02 9:00",
    "Ordinary text / another paragraph.", "North / Delta；A quiet passage.",
    "Header / Body；2027年 / Title：An ordinary paragraph.",
    "North / Delta；Revenue:17", "Revenue:2027年17万元；2026年11万元",
])
def test_urls_times_plain_layout_and_other_supported_grammars_are_not_taken_over(text):
    result = read_header_path_requirements(text, SOURCE)
    assert result["matched"] is False and result["facts"] == [] and result["blockers"] == []


def test_one_conflicting_year_path_keeps_other_explicit_fields_and_its_own_pending_requirement():
    result = read_header_path_requirements("North / Delta；2027年 / 金額万元：17；2027年 / 2026年 / 金額万元：11", SOURCE)
    assert len(result["facts"]) == 1 and result["facts"][0]["value"] == "17"
    assert len(result["pending_requirements"]) == 1
    assert result["blockers"][0]["reason"] == "header_path_qualifier_conflict"


def test_dollar_symbol_and_whole_labels_do_not_acquire_a_default_currency_or_fake_unit():
    result = read_header_path_requirements("Delta；2027年 / Revenue(17%)：$5", SOURCE)
    [fact] = result["facts"]
    assert fact["attribute"] == "Revenue(17%)" and fact["value"] == "5"
    assert fact["qualifiers"] == {"period": "2027年", "unit": "$"}


@pytest.mark.parametrize("value", ["9:00", "https://example.test/Revenue17", "17 mystery-unit"])
def test_unsupported_value_keeps_all_internal_punctuation_and_never_yields_a_partial_number(value):
    result = read_header_path_requirements(f"North / Delta；2027年 / Revenue：{value}", SOURCE)
    assert result["facts"] == []
    assert result["blockers"][0]["reason"] == "header_path_scalar_syntax_unsupported"
    assert any(atom["text"] == value and atom["role"] == "pending_requirement" for atom in result["text_atoms"])
    assert result["text_projection_complete"] is True


def test_source_spans_and_projection_inventory_account_for_every_character_without_copying_values_into_queries():
    source = {**SOURCE, "text_span": [30, 30 + len(FOUR)]}
    before = deepcopy(source)
    result = read_header_path_requirements(FOUR, source)
    assert source == before and result["text_projection_complete"] is True
    covered = [0] * len(FOUR)
    for item in result["consumed_spans"]:
        a, b = item["span"]
        assert item["text"] == FOUR[a:b]
        assert item["source"]["text_span"] == [a + 30, b + 30]
        for index in range(a, b):
            covered[index] += 1
    assert covered == [1] * len(FOUR)
    assert len(result["projection_inputs"]["objects"]) == 4
    for fact in result["facts"]:
        source = fact["source"]
        a, b = source["text_span"]
        assert FOUR[a - 30:b - 30].rstrip("%") == fact["value"]
        assert fact["source"]["attribute_source"]["path"] == SOURCE["path"]
        assert all(item["source"]["path"] == SOURCE["path"] for item in fact["header_evidence"])


@pytest.mark.parametrize("declaration,unit,currency", [
    ("（单位：(人民币百万元)）", "人民币百万元", "人民币"),
    ("(单位:人民币百万元)", "人民币百万元", "人民币"),
    ("（单位：((美元百万元))）", "美元百万元", "美元"),
    ("(Units: (USD millions))", "USD millions", "USD"),
])
def test_post_value_unit_declarations_use_only_their_complete_printed_token_and_exact_spans(declaration, unit, currency):
    text = f"Revenue；2027年 / 美元：17；2026年：11{declaration}。"
    source = {**SOURCE, "text_span": [40, 40 + len(text)]}
    result = read_header_path_requirements(text, source)
    assert result["blockers"] == []
    assert len(result["facts"]) == 2
    fact = result["facts"][1]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("", "Revenue", "11")
    assert fact["qualifiers"] == {"period": "2026年", "unit": unit, "currency": currency}
    assert fact["value_source"]["text_span"] == [40 + text.index("11"), 42 + text.index("11")]
    unit_start = text.index(unit, text.index("11"))
    assert fact["qualifier_sources"]["unit"]["text_span"] == [40 + unit_start, 40 + unit_start + len(unit)]
    assert fact["qualifier_sources"]["currency"]["text_span"] == [40 + unit_start, 40 + unit_start + len(currency)]
    assert any("单位" in item["text"] or "Units" in item["text"] for item in result["controls"])
    cover = [0] * len(text)
    for item in result["consumed_spans"]:
        a, b = item["span"]
        assert text[a:b] == item["text"]
        assert item["source"]["text_span"] == [40 + a, 40 + b]
        for i in range(a, b):
            cover[i] += 1
    assert cover == [1] * len(text)


@pytest.mark.parametrize("declaration", [
    "（单位：(人民币百万元)） extra", "（单位：(人民币百万元）)",
    "（单位：(人民币百万元) mystery）", "（单位：unknown）",
])
def test_unknown_or_unbalanced_post_value_declaration_never_returns_a_partial_scalar(declaration):
    text = f"Revenue；2027年 / 美元：17；2026年：11{declaration}"
    result = read_header_path_requirements(text, SOURCE)
    assert len(result["facts"]) == 1 and result["facts"][0]["value"] == "17"
    assert result["pending_requirements"][0]["reason"] == "header_path_scalar_syntax_unsupported"
    assert result["pending_requirements"][0]["text"] == f"2026年：11{declaration}"
    assert any(atom["text"] == f"11{declaration}" for atom in result["text_atoms"])


@pytest.mark.parametrize("header,declaration", [
    ("人民币百万元", "美元百万元"), ("人民币千元", "人民币百万元"),
])
def test_a_post_value_unit_conflicting_with_its_own_header_is_pending_not_an_override(header, declaration):
    text = f"Revenue；2027年 / {header}：17（单位：({declaration})）"
    result = read_header_path_requirements(text, SOURCE)
    assert result["facts"] == []
    assert result["pending_requirements"][0]["reason"] == "header_path_qualifier_conflict"
    assert "unit" in result["pending_requirements"][0]["conflicts"]
    assert any(atom["text"] == declaration for atom in result["text_atoms"])


def test_a_declared_unit_cannot_silently_replace_a_conflicting_inline_unit():
    result = read_header_path_requirements("Revenue；2027年 / 金額：17美元（单位：人民币）", SOURCE)
    assert result["facts"] == []
    assert result["pending_requirements"][0]["reason"] == "header_path_qualifier_conflict"
    assert "unit" in result["pending_requirements"][0]["conflicts"]
