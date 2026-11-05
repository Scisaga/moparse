"""Explicit record qualifiers are authored facts, including unusual units."""

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


@pytest.mark.parametrize("text", [
    "Name: Delta; Age: 52; Unit: 股",
    "Name: Delta; Unit: 股; Age: 52",
    "Name: Delta; Age: 52; Unit: 万元",
    "- Name: Delta\n  - Age: 52\n  - Unit: 股",
    "| Name | Age | Unit |\n|---|---|---|\n| Delta | 52 | 股 |",
])
def test_record_unit_is_not_deleted_by_a_measurement_type_guess(text):
    graph = compile_markdown(text)
    assert graph["blockers"] == []
    unit = "万元" if "万元" in text else "股"
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
        ("Name", "Delta", {}), ("Age", "52", {"unit": unit})]
    [edge] = [e for e in graph["relations"] if e["type"] == "qualifier_scope"]
    assert edge["left"] == {"type": "unit", "text": unit}
    assert edge["right"]["attribute"] == "Age"


def test_wrong_unusual_unit_cannot_be_deleted_to_make_the_assertion_correct():
    reference = compile_markdown("Name: Delta; Age: 52; Unit: 股")
    actual = read_candidate_markdown("Name: Delta; Age: 52; Unit: 人")
    score = grade_layers(reference, actual)
    assert score["publishable"] is True
    assert score["layers"]["B"]["denominator"] == 2
    assert score["layers"]["B"]["numerator"] == 1


def test_trailing_unit_backfills_only_the_current_named_record():
    graph = compile_markdown("- Name: Delta\n  - Age: 52\n  - Unit: 股\n- Name: Kappa\n  - Age: 31")
    assert graph["blockers"] == []
    assert [(f["subject"], f["attribute"], f["qualifiers"]) for f in graph["business"]] == [
        ("", "Name", {}), ("Delta", "Age", {"unit": "股"}),
        ("", "Name", {}), ("Kappa", "Age", {})]


def test_field_inline_unit_overrides_a_later_record_default_without_rewriting_it():
    graph = compile_markdown("- Name: Delta\n  - Revenue: 17亿元\n  - Unit: 万元")
    assert len(graph["business"]) == 2
    assert graph["business"][1]["qualifiers"] == {"unit": "亿元"}
    assert graph["business"][1]["qualifier_provenance"]["unit"]["level"] == "field_inline"


def test_shared_amount_caption_does_not_assign_money_to_names_or_headcount():
    graph = compile_markdown("Unit: 万元\n\nName: Delta; Headcount: 52; Revenue: 17")
    assert [(f["attribute"], f["qualifiers"]) for f in graph["business"]] == [
        ("Name", {}), ("Headcount", {}), ("Revenue", {"unit": "万元"})]


def test_explicit_column_unit_remains_a_qualifier_despite_an_unusual_attribute_type():
    reference = compile_markdown("Age: 52股")
    actual = read_candidate_markdown("| Age (股) |\n|---|\n| 52 |")
    assert actual["business"][0]["qualifiers"] == {"unit": "股"}
    score = grade_layers(reference, actual)
    assert score["publishable"] is True and score["layers"]["B"]["numerator"] == 1
