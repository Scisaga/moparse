"""Authored means/purpose operations, independent main facts and mutations."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.narrative_requirements import read_narrative
from moparse_eval.source_obligations import audit_source_obligations
from moparse_eval.source_requirements import plan_field_body
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_compact_multichange_production import review
from tests.unit.test_represented_feature_production import production


@pytest.mark.parametrize("text,role,actions", [
    ("By integrating accounts and products, we improve services.\n", "means", ["integrate", "integrate"]),
    ("Through integrating accounts and products, we improve services.\n", "means", ["integrate", "integrate"]),
    ("By creating tools and integrating systems, we improve services.\n", "means", ["create", "integrate"]),
    ("In order to provide services, we build a platform.\n", "purpose", ["provide"]),
    ("For the purpose of providing services, we build a platform.\n", "purpose", ["provide"]),
])
def test_nonfinite_operations_reach_the_existing_production_comparison_without_extra_business_votes(tmp_path, text, role, actions):
    graph, required = production(tmp_path, text)
    assert len(required["business"]) == 1
    assert [fact["attribute"] for fact in required["semantic_operands"]] == actions
    assert all(fact["qualifiers"]["assertion_context"] == role + "_operand" for fact in required["semantic_operands"])
    [tree] = graph["logic"]
    assert tree["kind"] == "fronted_context" and tree["role"] == role
    assert tree["control"]["controller"] == "we"
    assert tree["operation"] and tree["child"]
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["L"]["score"] == 100
    validate_evidence(result)


TEXT = "By integrating accounts and products, we build a platform.\n"


@pytest.mark.parametrize("mutation", ["operation", "operand", "controller", "main_predicate_source", "role", "relation", "kinds_and_features"])
def test_all_surface_text_cannot_replace_an_operation_controller_or_attachment(tmp_path, mutation):
    graph, required = production(tmp_path, TEXT)
    actual = read_candidate_markdown(TEXT, sample_id=required["sample_id"])
    before = deepcopy(actual["text"])
    if mutation == "operation":
        actual["logical_statements"][0].pop("operation")
        graph["logic"][0].pop("operation")
    elif mutation == "operand":
        actual["semantic_operands"].pop()
        node = next(node for node in graph["nodes"] if node.get("kind") == "semantic_operand")
        graph["nodes"].remove(node)
    elif mutation == "controller":
        actual["logical_statements"][0]["control"]["controller_source"] = deepcopy(actual["business"][0]["object_source"])
        graph["logic"][0]["control"]["controller_source"] = deepcopy(graph["nodes"][-1]["object_source"])
    elif mutation == "main_predicate_source":
        actual["logical_statements"][0]["control"]["main_predicate_source"] = deepcopy(actual["business"][0]["object_source"])
        graph["logic"][0]["control"]["main_predicate_source"] = deepcopy(graph["nodes"][-1]["object_source"])
    elif mutation == "role":
        actual["logical_statements"][0]["role"] = "purpose"
        graph["logic"][0]["role"] = "purpose"
    elif mutation == "relation":
        actual["relations"] = [edge for edge in actual["relations"] if edge["type"] != "narrative_fronted_context_scope"]
        graph["relations"] = [edge for edge in graph["relations"] if edge["type"] != "narrative_fronted_context_scope"]
    else:
        actual["logical_statements"][0]["kind"] = "noun_phrase"
        actual["required_matcher_features"] = []
        graph["logic"][0]["kind"] = "noun_phrase"
        graph["required_matcher_features"] = []
    assert actual["text"] == before
    result = grade_layers(required, actual)
    assert not result["publishable"]
    review(result)
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert not coverage["semantic_complete"]


@pytest.mark.parametrize("changed", [
    TEXT.replace("accounts and products", "accounts"),
    TEXT.replace("By integrating accounts and products, we build a platform.", "We integrate accounts and products. We build a platform."),
    TEXT.replace("By integrating", "For the purpose of integrating"),
    TEXT.replace("we build", "they build"),
])
def test_lost_operand_unconditional_assertion_changed_role_and_actor_are_not_equivalent(tmp_path, changed):
    _, required = production(tmp_path, TEXT)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["numerator"] < result["layers"]["B"]["denominator"] or not result["publishable"]
    review(result)


@pytest.mark.parametrize('text', ['THE INTEGRATED FINANCE STRATEGY',
    'Integrated finance-enabled core competitive moat and customer development'])
def test_participial_modifiers_and_hyphenated_nominals_do_not_invent_finite_subjects(text):
    reading = read_narrative(text, {'path': '<authored-nominal-heading>', 'lines': [1, 1]})
    assert not reading['facts'] and not reading['complete']


def test_action_tokens_inside_a_url_do_not_create_a_label_and_narrative_body():
    text = 'Regional deployment. https://example.test/integrated-services/provides-tools'
    assert plan_field_body(text, {'path': '<authored-uri>', 'lines': [1, 1]}) is None
