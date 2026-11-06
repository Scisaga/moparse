"""Independent logical-prose oracles through the shared grading entry."""

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

FIRST = "The board shall pay 17 credits only if approved by 4 directors."
SECOND = "The clerk must publish the notice."
REFERENCE = "## Policy\n\n" + FIRST + "\n\n" + SECOND


def grade(candidate):
    return grade_layers(compile_markdown(REFERENCE), read_candidate_markdown(candidate))


def test_two_actions_and_condition_have_independent_business_and_relation_requirements():
    graph = compile_markdown(REFERENCE)
    assert graph["blockers"] == []
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in graph["business"]] == [
        ("the board", "pay", "pay 17 credits", "description"),
        ("the clerk", "publish", "publish the notice", "description")]
    assert graph["business"][0]["qualifiers"] == {"modality": "shall", "polarity": "positive",
        "condition": "approved by 4 directors", "condition_operator": "only_if"}
    score = grade(REFERENCE)
    assert score["publishable"] is True
    assert score["layers"]["B"]["denominator"] == score["layers"]["B"]["numerator"] == 2
    # Each admitted action now owns an explicit predicate binding and modal
    # binding, alongside the condition, heading memberships and order edge.
    assert [edge["left"] for edge in graph["relations"] if edge["type"] == "field_binding"] == [
        {"subject": "the board", "attribute": "pay"}, {"subject": "the clerk", "attribute": "publish"}]
    assert [edge["left"] for edge in graph["relations"] if edge["type"] == "qualifier_scope"] == [
        {"type": "modality", "text": "shall"}, {"type": "modality", "text": "must"}]
    assert score["layers"]["L"]["denominator"] == score["layers"]["L"]["numerator"] == 8
    assert score["score"] == 100


@pytest.mark.parametrize("before,after", [("17", "18"), ("4 directors", "3 directors"),
                                          ("shall pay", "shall not pay")])
def test_content_changes_do_not_destroy_independently_expressed_prose_bindings(before, after):
    score = grade(REFERENCE.replace(before, after))
    assert score["publishable"] is True
    assert score["layers"]["B"]["numerator"] == 1
    assert score["layers"]["L"]["numerator"] == score["layers"]["L"]["denominator"] == 8
    assert score["layers"]["T"]["score"] < 100
    row = next(r for r in score["outcomes"] if r["layer"] == "B" and r["expected"]["attribute"] == "pay")
    assert "17" not in repr(row["retrieval"]["query"])
    assert "4 directors" not in repr(row["retrieval"]["query"])


def test_reversing_two_complete_actions_retains_text_and_business_but_changes_order():
    score = grade("## Policy\n\n" + SECOND + "\n\n" + FIRST)
    assert score["publishable"] is True
    assert score["layers"]["T"]["score"] == score["layers"]["B"]["score"] == 100
    assert score["layers"]["L"]["numerator"] == 7 and score["layers"]["L"]["denominator"] == 8


def test_a_locally_conflicting_condition_is_not_hidden_by_the_exact_condition():
    conflict = FIRST.replace("4 directors", "3 directors")
    score = grade(REFERENCE + "\n\n" + conflict)
    row = next(r for r in score["outcomes"] if r["layer"] == "B" and r["expected"]["attribute"] == "pay")
    assert row["outcome"] == "incorrect"
    assert len(row["retrieval"]["accepted"]) == 2
    assert {r["qualifiers"]["condition"] for r in row["actual"]} == {
        "approved by 4 directors", "approved by 3 directors"}
    assert score["publishable"] is False  # Duplicate role endpoints still need independent L anchors.
