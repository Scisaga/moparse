"""Fixed raw-literal measurement oracles across independently printed forms."""

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


@pytest.mark.parametrize("text", [
    "Revenue:17人民币千元",
    "Revenue（人民币千元）:17",
    '<table><tr><th scope="col">Revenue（人民币千元）</th></tr><tr><td>17</td></tr></table>',
])
def test_explicit_currency_scale_unit_has_the_same_unscaled_value_and_literal_unit(text):
    graph = compile_markdown(text)
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
        ("Revenue", "17", {"unit": "人民币千元", "currency": "人民币"})]


@pytest.mark.parametrize("text", [
    "Revenue:17美元",
    "Revenue（美元）:17",
    '<table><tr><th scope="col">Revenue（美元）</th></tr><tr><td>17</td></tr></table>',
])
def test_an_explicit_dollar_name_is_currency_evidence_from_that_actual_unit(text):
    graph = compile_markdown(text)
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
        ("Revenue", "17", {"unit": "美元", "currency": "美元"})]


@pytest.mark.parametrize("label", ["Revenue(17%)", "Count(17人)"])
def test_a_label_with_its_own_quantity_is_not_a_unit_only_header(label):
    graph = compile_markdown(f"{label}:5")
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [(label, "5", {})]


def test_numeric_business_names_times_and_urls_remain_whole_values_and_labels():
    graph = compile_markdown("Type17 Revenue:5\n\nDate and time:2028-05-02 9:00\n\nLocation:https://example.test/Room17")
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
        ("Type17 Revenue", "5", {}), ("Date and time", "2028-05-02 9:00", {}),
        ("Location", "https://example.test/Room17", {})]


@pytest.mark.parametrize("text", [
    "Unit:美元\n\nRevenue:17",
    "Name:Delta; Revenue:17; Unit:美元",
    "Name:Delta; Unit:美元; Revenue:17",
    "- Name:Delta\n  - Revenue:17\n  - Unit:美元",
])
def test_currency_named_in_an_explicit_unit_does_not_depend_on_declaration_order(text):
    graph = compile_markdown(text)
    [revenue] = [f for f in graph["business"] if f["attribute"] == "Revenue"]
    assert revenue["qualifiers"] == {"unit": "美元", "currency": "美元"}


def test_an_identity_value_that_looks_like_a_quantity_stays_a_whole_name():
    graph = compile_markdown("Name:17美元; Revenue:5")
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
        ("Name", "17美元", {}), ("Revenue", "5", {})]


@pytest.mark.parametrize("unit", ["美元", "万元", "人民币千元"])
def test_a_printed_unit_only_label_and_value_suffix_retain_the_same_literal_words(unit):
    for reference, candidate in [(f"Revenue:17{unit}", f"Revenue（{unit}）:17"),
                                 (f"Revenue（{unit}）:17", f"Revenue:17{unit}")]:
        result = grade_layers(compile_markdown(reference), read_candidate_markdown(candidate))
        assert result["blockers"] == []
        assert {k: v["score"] for k, v in result["layers"].items()} == {"T": 100, "L": 100, "B": 100}
