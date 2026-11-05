"""Hand-fixed weights and provenance for a printed parent metric declaration."""

from collections import Counter

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

PARENT = "- Revenue\n  - 2027年，万元:17\n  - 2026年，万元:11\n"
MATRIX = "| Metric | 2027年（万元） | 2026年（万元） |\n|---|---|---|\n| Revenue | 17 | 11 |\n"
WORDS = Counter({"Revenue": 2, "2027年": 1, "2026年": 1, "万元": 2, "17": 1, "11": 1})


@pytest.mark.parametrize("text", [PARENT, MATRIX])
def test_two_annual_measurements_have_two_labels_and_32_required_characters(text):
    graph = compile_markdown(text)
    assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
        ("", "Revenue", "17", {"period": "2027年", "unit": "万元"}),
        ("", "Revenue", "11", {"period": "2026年", "unit": "万元"}),
    ]
    assert Counter(item["text"] for item in graph["text"]) == WORDS
    assert sum(len(item["text"]) for item in graph["text"]) == 32
    assert len(graph["relations"]) == 6
    assert Counter(edge["type"] for edge in graph["relations"]) == {"field_binding": 2, "qualifier_scope": 4}


@pytest.mark.parametrize("reference,candidate", [(PARENT, MATRIX), (MATRIX, PARENT)])
def test_parent_metric_and_explicit_matrix_compare_at_identical_text_and_business_weight(reference, candidate):
    score = grade_layers(compile_markdown(reference), read_candidate_markdown(candidate))
    assert score["blockers"] == []
    assert score["layers"]["T"]["denominator"] == 32
    assert score["layers"]["T"]["score"] == 100
    assert score["layers"]["B"]["denominator"] == 2 and score["layers"]["B"]["score"] == 100
    assert score["layers"]["L"]["denominator"] == 6 and score["layers"]["L"]["score"] == 100


def test_metric_label_aliases_point_to_the_actual_parent_line_not_a_child_pseudo_parent():
    graph = compile_markdown(PARENT, path="<fixed-parent-source>")
    labels = [atom for atom in graph["text"] if atom["text"] == "Revenue"]
    assert len(labels) == 2
    assert all(atom["projection_kind"] == "bounded_alias" for atom in labels)
    assert all(atom["source"]["path"] == "<fixed-parent-source>" and atom["source"]["lines"] == [1, 1] for atom in labels)
    assert all(atom["source"]["text_span"] == [0, 7] for atom in labels)
    assert all(atom["source"].get("location") != "declared_parent_text" for atom in labels)


def test_independent_year_fields_have_binding_relations_without_an_invented_metric_order_requirement():
    reordered = "- Revenue\n  - 2026年，万元:11\n  - 2027年，万元:17\n"
    score = grade_layers(compile_markdown(PARENT), read_candidate_markdown(reordered))
    assert score["layers"]["L"]["denominator"] == 6
    assert score["layers"]["L"]["score"] == 100
    assert not [row for row in score["outcomes"] if row["layer"] == "L" and row["role"] == "reading_order"]


def test_one_amount_typo_changes_one_business_item_without_unbinding_the_parent_metric():
    score = grade_layers(compile_markdown(PARENT), read_candidate_markdown(PARENT.replace(":17", ":18")))
    assert score["layers"]["B"]["denominator"] == 2 and score["layers"]["B"]["numerator"] == 1
    assert score["layers"]["L"]["denominator"] == 6 and score["layers"]["L"]["score"] == 100

def test_a_proved_metric_declaration_does_not_erase_or_reuse_its_named_child_identity():
    graph = compile_markdown("- Metric: Revenue\n  - Name: Delta\n  - 2027年，万元：17")
    assert graph["blockers"] == []
    assert [(fact["subject"], fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
        ("", "Name", "Delta", "identity"), ("Delta", "Revenue", "17", "metric")]
    assert len({fact["id"] for fact in graph["business"]}) == 2
