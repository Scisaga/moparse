"""Fixed oracles for extra unbound numerals versus unread business prose.

These invented inputs do not infer a number's property from a reference answer
or from its neighbouring chart-like labels. They exercise the public grader.
"""

from __future__ import annotations

import pytest

from moparse_eval.three_layer import (
    compile_markdown,
    grade_layers,
    read_candidate,
    read_candidate_markdown,
)


def grade(reference: str, candidate: str):
    required = compile_markdown(reference)
    actual = read_candidate_markdown(candidate)
    return required, actual, grade_layers(required, actual)


def b_rows(score):
    return [row for row in score["outcomes"] if row["layer"] == "B"]


def affects(blocker, layer: str):
    return layer in blocker.get("layers", ["T", "L", "B"])


@pytest.mark.parametrize("extra", ["891368", "636,807 642,338", "891368\n\n700000"])
def test_correct_explicit_property_plus_unbound_extra_numerals_keeps_its_business_decision(extra):
    required, actual, score = grade("Revenue: 17\n", f"Revenue: 17\n\n{extra}\n")
    assert [(f["attribute"], f["value"]) for f in required["business"]] == [("Revenue", "17")]
    assert [(f["attribute"], f["value"]) for f in actual["business"]] == [("Revenue", "17")]
    assert [(row["expected"]["attribute"], row["outcome"]) for row in b_rows(score)] == [("Revenue", "correct")]
    assert score["layers"]["B"]["denominator"] == 1
    assert score["layers"]["B"]["complete"] is True
    assert score["layers"]["B"]["score"] == 100
    assert not [b for b in score["blockers"] if affects(b, "B")]
    assert not [b for b in score["blockers"] if b["reason"] == "prose_endpoint_role_collision"]
    # Extra literal text is still printed and auditable. It gains no property
    # identity, and this test does not invent an insertion/hallucination grade.
    for numeral in extra.split("\n\n"):
        assert any(item["text"] == numeral and item["source"] for item in actual["text"])
        assert any(item["text"] == numeral and item["source"]
                   for item in score["layers"]["T"]["unadjudicated_extra_units"])


def test_a_bare_matching_number_cannot_supply_the_missing_required_property():
    _, actual, score = grade("Revenue: 17\n", "17\n")
    assert actual["business"] == []
    assert len(b_rows(score)) == 1
    assert b_rows(score)[0]["outcome"] == "incorrect"
    assert b_rows(score)[0]["actual"] == []
    assert score["layers"]["B"]["denominator"] == 1
    assert score["layers"]["B"]["complete"] is True
    assert score["layers"]["B"]["score"] == 0


def test_a_required_bare_number_remains_unknown_instead_of_becoming_empty_coverage():
    required, actual, score = grade("891368\n", "891368\n")
    assert required["business"] == [] and actual["business"] == []
    assert any(item["text"] == "891368" for item in required["text"])
    assert any(b.get("side") == "expected" and affects(b, "B") for b in score["blockers"])
    assert score["publishable"] is False
    assert score["layers"]["B"]["complete"] is False
    assert score["layers"]["B"]["score"] is None


def test_unread_actual_business_prose_is_not_relabelled_as_unbound_extra_numerals():
    _, actual, score = grade("Revenue: 17\n", "Revenue: 17\n\nRevenue gyrated 17\n")
    assert any(item["text"] == "Revenue gyrated 17" for item in actual["text"])
    assert any(b.get("side") == "candidate" and affects(b, "B") for b in score["blockers"])
    assert score["publishable"] is False
    assert score["layers"]["B"]["complete"] is False
    assert score["layers"]["B"]["score"] is None


def test_unread_reference_business_prose_stays_a_required_software_blocker():
    _, _, score = grade("Revenue gyrated 17\n", "Revenue gyrated 17\n")
    assert any(b.get("side") == "expected" and affects(b, "B") for b in score["blockers"])
    assert score["publishable"] is False
    assert score["layers"]["B"]["complete"] is False
    assert score["layers"]["B"]["score"] is None


def test_supported_increase_predicate_is_a_business_fact_and_its_wrong_amount_is_detected():
    required, actual, score = grade("Revenue increased 17\n", "Revenue increased 18\n")
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in required["business"]] == [
        ("Revenue", "increase", "17", "description")]
    assert actual["business"][0]["value"] == "18"
    assert score["publishable"] is True
    assert score["layers"]["B"]["denominator"] == 1 and score["layers"]["B"]["numerator"] == 0
    assert score["layers"]["L"]["score"] == 100


def test_a_native_picture_parent_proves_containment_without_inventing_a_property():
    parent = "#/document/pictures/0"
    actual = read_candidate({
        "sample_id": "synthetic",
        "pages": [{"page": 1, "blocks": [
            {"id": "field", "kind": "text", "text": "Revenue: 17", "native_path": "#/document/texts/1"},
            {"id": parent, "kind": "picture", "text": "", "native_path": parent,
             "native_children": ["#/document/texts/5"], "native_references": {"captions": [], "footnotes": [], "references": []}},
            {"id": "#/document/texts/5", "kind": "text", "text": "891368", "native_path": "#/document/texts/5",
             "parent_id": parent, "native_parent": parent, "native_children": [],
             "native_references": {"captions": [], "footnotes": [], "references": []}},
        ]}],
    })
    assert [(fact["attribute"], fact["value"]) for fact in actual["business"]] == [("Revenue", "17")]
    literal = next(item for item in actual["text"] if item["text"] == "891368")
    assert literal["source"]["path"] == "#/document/texts/5"
    assert literal["syntax_kind"] == "text"
    score = grade_layers(compile_markdown("Revenue: 17\n"), actual)
    assert score["layers"]["B"]["complete"] is True
    assert b_rows(score)[0]["outcome"] == "correct"
