"""Independent nested nominal decisions through selected expected compilation."""

from copy import deepcopy

import pytest

from moparse_eval.expected_readback import read_expected
from moparse_eval.expected_report import validate_evidence
from moparse_eval.packaging import write_json
from moparse_eval.requirement_ast import compare_requirement_ast
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown

# The business owner, members and cardinality are declared before either
# production compiler is called. They are not copied from an emitted AST.
CASES = [
    ("The company manages the assets of its subsidiaries and affiliates.",
     "The company manages the assets of its affiliates and subsidiaries.",
     {"owner": "its", "members": {"subsidiaries", "affiliates"}, "count": None}),
    ("We have sharpened our business focus to two core businesses of e-commerce and cloud.",
     "We have sharpened our business focus to two core businesses of cloud and e-commerce.",
     {"owner": None, "members": {"e-commerce", "cloud"}, "count": "2"}),
]


def selected_expected(tmp_path, text):
    directory = tmp_path / "invented"
    directory.mkdir()
    path = directory / "expected.md"
    path.write_text(text + "\n", encoding="utf-8")
    write_json(directory / "manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {
        "entries": [{"source_pages": [1], "markdown_lines": [1, 1]}]}})
    selected = read_expected({"id": "synthetic", "document_id": "invented", "source_pages": [1]}, tmp_path)
    graph = compile_requirement_graph(selected)
    validate_requirement_graph(graph, expected=selected)
    assert not graph["unresolved"], graph["unresolved"]
    assert all(row["status"] != "pending" for row in graph["source_obligation_coverage"]["dispositions"])
    return graph, evaluation_projection(graph)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def review_result(result):
    if result["publishable"]:
        validate_evidence(result)
    else:
        # The report entry point is a publication audit. An incomplete
        # candidate interpretation must remain ineligible, rather than being
        # turned into a publishable zero by this controlled regression.
        with pytest.raises(ValueError, match="incomplete software judgments"):
            validate_evidence(result)


@pytest.mark.parametrize("text,candidate,oracle", CASES)
def test_nested_member_reordering_is_equivalent_after_complete_expected_source_audit(tmp_path, text, candidate, oracle):
    _graph, required = selected_expected(tmp_path, text)
    actual = read_candidate_markdown(candidate)
    assert not actual["blockers"]
    for parsed in (required, actual):
        group = next(node for node in walk(parsed["logical_statements"])
                     if node.get("kind") == "noun_phrase" and node.get("coordination"))
        assert group["determiner"] == oracle["owner"]
        assert {child["head"] for child in group["coordination"]["children"]} == oracle["members"]
        if oracle["count"]:
            assert next(node for node in walk(parsed["logical_statements"])
                        if node.get("kind") == "quantity_comparison")["value"] == oracle["count"]
    decision = compare_requirement_ast(required["logical_statements"], actual["logical_statements"])
    assert decision["equivalent"], decision


@pytest.mark.parametrize("candidate", [
    "The company manages the assets of its subsidiaries or affiliates.",
    "The company manages the assets of its subsidiaries.",
    "The company manages the assets of their subsidiaries and affiliates.",
    "The company manages the assets of its subsidiaries and manages its affiliates.",
    "The company manages the assets for its subsidiaries and affiliates.",
])
def test_similar_text_with_changed_members_owner_operator_or_attachment_never_equates(tmp_path, candidate):
    _graph, required = selected_expected(tmp_path, CASES[0][0])
    actual = read_candidate_markdown(candidate)
    assert not compare_requirement_ast(required["logical_statements"], actual["logical_statements"])["equivalent"]


@pytest.mark.parametrize("candidate", [
    "We have sharpened our business focus to three core businesses of e-commerce and cloud.",
    "We have sharpened our business focus to two core businesses of e-commerce or cloud.",
    "We have sharpened our business focus to two core businesses of e-commerce.",
])
def test_count_and_complement_semantics_survive_nominal_surface_delegation(tmp_path, candidate):
    _graph, required = selected_expected(tmp_path, CASES[1][0])
    actual = read_candidate_markdown(candidate)
    assert not compare_requirement_ast(required["logical_statements"], actual["logical_statements"])["equivalent"]


@pytest.mark.parametrize("mutation", ["missing_member", "missing_complement", "short_phrase_source", "missing_phrase"])
def test_complete_raw_object_cannot_hide_incomplete_or_forged_nominal_structure(tmp_path, mutation):
    _graph, required = selected_expected(tmp_path, CASES[0][0])
    actual = read_candidate_markdown(CASES[0][0])
    leaf = actual["logical_statements"][0]
    original_raw = leaf["object"]
    phrase = leaf["object_phrase"]
    if mutation == "missing_member":
        phrase["prepositional_complements"][0]["complement"]["coordination"]["children"].pop()
    elif mutation == "missing_complement":
        phrase["prepositional_complements"] = []
    elif mutation == "short_phrase_source":
        phrase["source"]["text_span"][1] = phrase["head_source"]["text_span"][1]
    else:
        del leaf["object_phrase"]
    assert leaf["object"] == original_raw
    assert not compare_requirement_ast(required["logical_statements"], actual["logical_statements"])["equivalent"]


def test_surface_difference_is_retained_for_text_and_scoped_to_source_closed_nominal(tmp_path):
    _graph, required = selected_expected(tmp_path, CASES[0][0])
    actual = read_candidate_markdown(CASES[0][1])
    assert required["text"][0]["text"] != actual["text"][0]["text"]
    first = deepcopy(required["logical_statements"])
    # Removing the structure restores scalar responsibility, so mere raw
    # spelling changes cannot become equivalent through a blanket key drop.
    del first[0]["object_phrase"]
    assert not compare_requirement_ast(first, actual["logical_statements"])["equivalent"]


@pytest.mark.parametrize("text,candidate,_oracle", CASES)
def test_nested_equivalence_changes_final_votes_and_report_replays_the_same_responsibility(tmp_path, text, candidate, _oracle):
    _graph, required = selected_expected(tmp_path, text)
    result = grade_layers(required, read_candidate_markdown(candidate))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["L"]["numerator"] == result["layers"]["L"]["denominator"]
    assert result["layers"]["T"]["score"] < 100
    assert any(row.get("semantic_responsibility", {}).get("owner") == "complete_source_bound_relation"
               for row in result["outcomes"])
    review_result(result)


@pytest.mark.parametrize("candidate", [
    "The company manages the assets of their affiliates and subsidiaries.",
    "The subsidiary manages the assets of its affiliates and subsidiaries.",
    "The company manages the assets of its affiliates or subsidiaries.",
    "The company manages the assets of its affiliates.",
    "The company manages the assets of its subsidiaries and manages its affiliates.",
])
def test_final_business_rejects_changed_owner_members_or_action_boundaries(tmp_path, candidate):
    _graph, required = selected_expected(tmp_path, CASES[0][0])
    result = grade_layers(required, read_candidate_markdown(candidate))
    assert result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["B"]["numerator"] == 0
    assert not any(row.get("semantic_responsibility") for row in result["outcomes"] if row["layer"] == "B")
    review_result(result)


@pytest.mark.parametrize("mutation", ["lost_fact", "lost_ast_member", "short_phrase_source", "extra_period", "extra_unit", "extra_identity_facet"])
def test_ast_equivalence_never_overrides_missing_facts_or_independent_context_conflicts(tmp_path, mutation):
    _graph, required = selected_expected(tmp_path, CASES[0][0])
    actual = read_candidate_markdown(CASES[0][1])
    if mutation == "lost_fact":
        actual["business"] = []
    elif mutation == "lost_ast_member":
        actual["logical_statements"][0]["object_phrase"]["prepositional_complements"][0]["complement"]["coordination"]["children"].pop()
    elif mutation == "short_phrase_source":
        phrase = actual["logical_statements"][0]["object_phrase"]
        phrase["source"]["text_span"][1] = phrase["head_source"]["text_span"][1]
    elif mutation == "extra_identity_facet":
        actual["business"][0]["identity_facets"] = {"region": "South"}
    else:
        actual["business"][0]["qualifiers"]["period" if mutation == "extra_period" else "unit"] = "2025" if mutation == "extra_period" else "USD"
    result = grade_layers(required, actual)
    assert result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["B"]["numerator"] == 0
    assert not any(row.get("semantic_responsibility") for row in result["outcomes"] if row["layer"] == "B")
    review_result(result)


def test_changed_printed_period_cannot_borrow_a_complete_equivalent_nominal(tmp_path):
    _graph, required = selected_expected(tmp_path, "In 2024, " + CASES[0][0])
    actual = read_candidate_markdown("In 2025, " + CASES[0][1])
    result = grade_layers(required, actual)
    assert result["layers"]["B"]["numerator"] == 0
    assert result["layers"]["L"]["numerator"] < result["layers"]["L"]["denominator"]
    review_result(result)


@pytest.mark.parametrize("required_count,actual_count", [(2, 1), (1, 2)])
def test_statement_capacity_and_duplicate_records_remain_independent_of_nominal_equivalence(tmp_path, required_count, actual_count):
    _graph, required = selected_expected(tmp_path, " ".join(CASES[0][:required_count]))
    actual = read_candidate_markdown(" ".join([CASES[0][1]] * actual_count))
    result = grade_layers(required, actual)
    assert result["layers"]["B"]["denominator"] == required_count
    assert result["layers"]["B"]["score"] != 100
    review_result(result)


def test_uninterpreted_extra_clause_cannot_receive_equivalent_nominal_business_credit(tmp_path):
    _graph, required = selected_expected(tmp_path, CASES[0][0])
    candidate = CASES[0][1][:-1] + " and unknown arrangements glorp."
    result = grade_layers(required, read_candidate_markdown(candidate))
    assert not result["publishable"]
    assert result["layers"]["B"]["numerator"] == 0
    assert result["layers"]["B"]["denominator"] == 1
    review_result(result)
