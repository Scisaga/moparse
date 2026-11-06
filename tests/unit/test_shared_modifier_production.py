"""One shared head, explicit compounds and beneficiary roles at final B/L."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_ast import compare_requirement_ast
from moparse_eval.requirement_graph import validate_requirement_graph
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_compact_multichange_production import review
from tests.unit.test_represented_feature_production import production

TEXT = "We build a one-stop regional and digital service platform for clients.\n"


@pytest.mark.parametrize("text,first,second,head,compound", [
    (TEXT, "regional", "digital", "platform", "service"),
    ("They develop a public and private service network for users.\n", "public", "private", "network", "service"),
    ("We build a national and regional platform for customers.\n", "national", "regional", "platform", None),
])
def test_shared_categories_have_one_head_one_action_and_equivalent_member_order(tmp_path, text, first, second, head, compound):
    graph, required = production(tmp_path, text)
    [fact] = required["business"]
    phrase = fact["object_phrase"]
    assert phrase["head"] == head
    group = phrase["coordination"]
    assert group["mode"] == "nominal_modifiers" and group["operator"] == "and"
    assert [m["text"] for m in group["children"]] == [first, second]
    assert all(m["role"] == "attributive" for m in group["children"])
    if compound:
        assert phrase["compound"]["modifier"] == compound and phrase["compound"]["relation"] == "classification"
    [beneficiary] = fact["prepositional_complements"]
    assert beneficiary["semantic_role"] == "beneficiary" and beneficiary["attachment"]["kind"] == "predicate"
    changed = text.replace(first + " and " + second, second + " and " + first)
    actual = read_candidate_markdown(changed, sample_id=required["sample_id"])
    result = grade_layers(required, actual)
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["L"]["score"] == 100
    assert result["layers"]["T"]["score"] < 100
    assert graph["semantic_complete"]
    validate_evidence(result)


@pytest.mark.parametrize("text,count", [
    ("We build a regional service platform and a digital service platform for clients.\n", 2),
    ("We build tools and systems for clients.\n", 2),
    ("We build a platform and provide services for clients.\n", 2),
])
def test_independent_objects_complete_nominals_and_actions_remain_separate(tmp_path, text, count):
    _, required = production(tmp_path, text)
    assert len(required["business"]) == count
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["numerator"] == count
    validate_evidence(result)


@pytest.mark.parametrize("changed", [
    TEXT.replace(" and ", " or "),
    TEXT.replace("a one-stop", "two one-stop").replace("platform", "platforms"),
    TEXT.replace("a one-stop", "our one-stop"),
    TEXT.replace("regional and digital", "regional"),
    TEXT.replace("regional and digital", "a regional and a digital"),
    TEXT.replace("service platform", "service system"),
    TEXT.replace(" for clients", " for users"),
    TEXT.replace(" for clients", " for 3 years"),
    TEXT.replace(" for clients", " for 7 dollars"),
    TEXT.replace(" for clients", " because of demand"),
    TEXT.replace("We build", "They build"),
    TEXT.replace("regional and digital service platform", "regional and digital"),
])
def test_similar_words_with_different_scope_count_role_or_attachment_never_restore_full_votes(tmp_path, changed):
    _, required = production(tmp_path, TEXT)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["B"]["numerator"] == 0
    review(result)


def test_a_nominal_for_phrase_keeps_its_nominal_owner(tmp_path):
    text = "The platform for clients supports users.\n"
    _, required = production(tmp_path, text)
    [fact] = required["business"]
    [attachment] = fact["subject_phrase"]["prepositional_complements"]
    assert attachment["attachment"] == {"kind": "nominal", "head": "platform"}
    assert attachment["semantic_role"] == "intended_beneficiary"
    assert fact["prepositional_complements"] == []
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    validate_evidence(result)


@pytest.mark.parametrize("mutation", ["member", "group", "compound", "modifier_source", "head_source", "beneficiary_owner", "fact", "relation"])
def test_retaining_the_entire_surface_never_hides_incomplete_structured_roles(tmp_path, mutation):
    graph, required = production(tmp_path, TEXT)
    actual = read_candidate_markdown(TEXT, sample_id=required["sample_id"])
    leaf = actual["logical_statements"][0]
    phrase = leaf["object_phrase"]
    if mutation == "member":
        phrase["coordination"]["children"].pop()
    elif mutation == "group":
        phrase["coordination"] = None
    elif mutation == "compound":
        del phrase["compound"]
    elif mutation == "modifier_source":
        phrase["coordination"]["children"][0]["source"] = deepcopy(phrase["coordination"]["children"][1]["source"])
    elif mutation == "head_source":
        phrase["head_source"] = deepcopy(phrase["compound"]["modifier_source"])
    elif mutation == "beneficiary_owner":
        leaf["prepositional_complements"][0]["attachment"] = {"kind": "nominal", "head": "platform"}
    elif mutation == "fact":
        actual["business"] = []
    else:
        actual["relations"] = [e for e in actual["relations"] if e["type"] != "narrative_nominal_compound_scope"]
    if mutation not in {"fact", "relation"}:
        assert not compare_requirement_ast(required["logical_statements"], actual["logical_statements"])["equivalent"]
    result = grade_layers(required, actual)
    layer = "L" if mutation == "relation" else "B"
    assert result["layers"][layer]["score"] != 100
    review(result)
    if mutation == "compound":
        changed = deepcopy(graph)
        del changed["logic"][0]["object_phrase"]["compound"]
        with pytest.raises(ValueError, match="nominal|constituent|source"):
            validate_requirement_graph(changed)
