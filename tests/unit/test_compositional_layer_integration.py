"""Independent B/L assertions through the public core, without real candidates."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

CASES = [
    ("The company develops and operates cloud services.", "The company develops or operates cloud services."),
    ("The company provides hardware and software.", "The company provides hardware or software."),
    ("The company provides services for international customers.", "The company provides services to international customers."),
    ("Revenue increased in 2024.", "Revenue increased in 2023."),
    ("The company may acquire the subsidiary if the board approves the transaction.",
     "The company must acquire the subsidiary if the board approves the transaction."),
    ("The company does not acquire or operate the subsidiary.", "The company does not acquire and operate the subsidiary."),
    ("The company owns A and B, but does not operate C.", "The company owns A and B, and does not operate C."),
    ("The company manages the assets of its subsidiaries and affiliates.",
     "The company manages the assets of its subsidiaries and manages its affiliates."),
    ("The company must maintain at least 80% capacity within the approved range.",
     "The company must maintain at least 70% capacity within the approved range."),
]


@pytest.mark.parametrize("text,_opposite", CASES)
def test_supported_composition_executes_comparator_and_keeps_original_target_denominators(text, _opposite):
    required = compile_markdown(text)
    actual = read_candidate_markdown(text)
    result = grade_layers(required, actual)
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["score"] == 100
    assert result["layers"]["L"]["score"] == 100
    assert result["layers"]["B"]["denominator"] == len(required["business"])
    assert result["layers"]["L"]["denominator"] == len(required["relations"])
    assert result["semantic_comparison"]["denominators_changed"] is False
    assert result["semantic_comparison"]["decisions"]["B"]["equivalent"]
    assert result["semantic_comparison"]["decisions"]["L"]["equivalent"]
    assert any(row.get("ast_comparisons") for row in result["outcomes"] if row["layer"] == "B")


@pytest.mark.parametrize("text,opposite", CASES)
@pytest.mark.parametrize("reverse", [False, True])
def test_close_words_with_wrong_composition_never_pass_in_either_direction(text, opposite, reverse):
    first, second = (opposite, text) if reverse else (text, opposite)
    result = grade_layers(compile_markdown(first), read_candidate_markdown(second))
    if first == "The company does not acquire and operate the subsidiary.":
        # The surface negative AND admits more than one operator scope. This
        # source remains pending; it is not a wrong candidate or an N/A vote.
        assert not result["publishable"]
        assert result["layers"]["B"]["score"] is None
        assert any("negated_coordination_scope_unresolved" in blocker["reason"] for blocker in result["blockers"])
        return
    assert result["semantic_comparison"]["decisions"]["B"]["status"] in {"conflict", "missing"}
    assert result["semantic_comparison"]["decisions"]["L"]["status"] in {"conflict", "missing"}
    assert result["layers"]["B"]["numerator"] < result["layers"]["B"]["denominator"]
    assert result["layers"]["L"]["numerator"] < result["layers"]["L"]["denominator"]


def test_ast_relation_deletion_cannot_be_hidden_by_unchanged_flat_fields_and_relations():
    text = "The company provides services for international customers."
    required = compile_markdown(text)
    actual = read_candidate_markdown(text)
    old_fields, old_edges = deepcopy(actual["business"]), deepcopy(actual["relations"])
    actual["logical_statements"][0]["prepositional_complements"] = []
    result = grade_layers(required, actual)
    assert actual["business"] == old_fields and actual["relations"] == old_edges
    assert result["semantic_comparison"]["decisions"]["B"]["status"] == "missing"
    assert result["layers"]["B"]["numerator"] == 0
    assert result["layers"]["B"]["denominator"] == 1


def test_unsupported_feature_name_still_blocks_even_with_a_comparable_ast():
    text = "The company provides hardware and software."
    required = compile_markdown(text)
    required["required_matcher_features"].append("invented_unimplemented_scope")
    result = grade_layers(required, read_candidate_markdown(text))
    assert not result["publishable"]
    assert any(blocker["reason"] == "narrative_comparison_features_not_validated"
               and "invented_unimplemented_scope" in blocker["required_features"] for blocker in result["blockers"])


def test_missing_structured_source_is_unresolved_and_never_equivalent():
    text = "Revenue increased in 2024."
    required = compile_markdown(text)
    actual = read_candidate_markdown(text)
    actual["logical_statements"][0]["prepositional_complements"][0]["source"]["text_span"] = [500, 510]
    result = grade_layers(required, actual)
    assert not result["publishable"]
    assert result["semantic_comparison"]["decisions"]["B"]["unresolved"]
    assert result["layers"]["B"]["score"] is None


def test_same_actor_action_in_distinct_headings_uses_its_printed_scope_before_values():
    text = "# North\n\nRevenue increased in 2024.\n\n# South\n\nRevenue increased in 2023."
    required = compile_markdown(text)
    result = grade_layers(required, read_candidate_markdown(text))
    assert result["semantic_comparison"]["decisions"]["B"]["equivalent"]
    trace = result["semantic_comparison"]["decisions"]["B"]["proof"]["rows"]
    assert [row["actual_index"] for row in trace] == [0, 1]
    assert all(row["retrieval"]["value_used"] is False for row in trace)


@pytest.mark.parametrize("mutation", ["outcome", "proof", "source", "gate", "omitted_comparison", "aggregate"])
def test_report_replays_the_ast_decision_and_rejects_forged_or_omitted_proof(mutation):
    text = "The company provides services for international customers."
    required = compile_markdown(text)
    if mutation == "gate":
        required["required_matcher_features"].append("invented_unimplemented_scope")
    result = grade_layers(required, read_candidate_markdown(text))
    if mutation != "gate":
        validate_evidence(result)
    if mutation == "outcome":
        next(row for row in result["outcomes"] if row["layer"] == "B")["outcome"] = "incorrect"
    elif mutation == "proof":
        result["semantic_comparison"]["decisions"]["B"]["proof"]["rows"][0]["retrieval"]["value_used"] = True
    elif mutation == "source":
        result["semantic_comparison"]["inputs"]["actual"]["logical_statements"][0]["source"]["text_span"] = [300, 400]
    elif mutation == "omitted_comparison":
        result.pop("semantic_comparison")
    elif mutation == "aggregate":
        result["layers"]["B"]["score"] = 99
        result["score"] = 99
    else:
        result["blockers"] = []
        result["publishable"] = True
        for layer in result["layers"].values():
            layer.update(complete=True, score=100)
        result["score"] = 100
    with pytest.raises(ValueError, match="semantic|aggregate|total"):
        validate_evidence(result)


def test_report_preserves_valid_ast_conflict_that_flat_evidence_cannot_distinguish():
    text = "The company provides services for international customers."
    actual = read_candidate_markdown(text)
    # An independent controlled mutation leaves flattened fields and edges
    # intact. The recursive relation is explicitly different, so it fails.
    actual["logical_statements"][0]["prepositional_complements"] = []
    actual["required_matcher_features"] = ["finite_tense"]
    result = grade_layers(compile_markdown(text), actual)
    assert result["layers"]["B"]["numerator"] == 0
    validate_evidence(result)


def test_a_semantic_conflict_cannot_hide_an_unresolved_source_binding_in_its_children():
    text = "Lumen owns Kappa."
    actual = read_candidate_markdown(text)
    [tree] = actual["logical_statements"]
    tree["object"] = "Sigma"
    tree["subject_source"]["text_span"] = [300, 305]
    result = grade_layers(compile_markdown(text), actual)
    assert result["semantic_comparison"]["decisions"]["B"]["conflict"]
    assert not result["publishable"]
    assert result["layers"]["B"]["score"] is None
    assert any(blocker["reason"] == "narrative_ast_comparison_unresolved" for blocker in result["blockers"])


def test_one_wrong_action_does_not_cancel_its_independent_correct_neighbor():
    required = compile_markdown("The company develops and operates cloud services.")
    actual = read_candidate_markdown("The company develops and maintains cloud services.")
    result = grade_layers(required, actual)
    rows = [row for row in result["outcomes"] if row["layer"] == "B"]
    assert [(row["expected"]["attribute"], row["outcome"]) for row in rows] == [
        ("develop", "correct"), ("operate", "incorrect")]
    assert result["layers"]["B"]["numerator"] == 1
    assert result["layers"]["B"]["denominator"] == 2
    field_rows = [row for row in result["outcomes"] if row["layer"] == "L" and row["role"] == "field_binding"]
    assert next(row for row in field_rows if row["expected"]["right"]["attribute"] == "develop")["outcome"] == "correct"
    validate_evidence(result)


@pytest.mark.parametrize("operator", ["and", "or"])
def test_member_reordering_keeps_business_equivalence_and_literal_differences(operator):
    first = f"The company provides hardware {operator} software."
    second = f"The company provides software {operator} hardware."
    result = grade_layers(compile_markdown(first), read_candidate_markdown(second))
    assert result["publishable"]
    assert result["layers"]["B"]["score"] == 100
    assert result["layers"]["L"]["score"] == 100
    assert result["layers"]["T"]["score"] < 100
    validate_evidence(result)


@pytest.mark.parametrize("mutation", ["qualifier_value", "qualifier_and_source_deleted", "subject", "predicate", "object"])
def test_conflicting_fact_and_ast_evidence_is_a_software_blocker(mutation):
    text = "The company may acquire the subsidiary."
    actual = read_candidate_markdown(text)
    [fact] = actual["business"]
    if mutation == "qualifier_value":
        fact["qualifiers"]["modality"] = "must"
    elif mutation == "qualifier_and_source_deleted":
        fact["qualifiers"].pop("modality")
        fact["qualifier_sources"].pop("modality")
    else:
        fact[mutation] = "invented conflicting role"
    result = grade_layers(compile_markdown(text), actual)
    assert not result["publishable"]
    assert result["layers"]["B"]["score"] is None
    assert any(blocker["reason"] == "semantic_fact_ast_evidence_inconsistent" for blocker in result["blockers"])
