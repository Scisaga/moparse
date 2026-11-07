"""Independent semantic and mutation oracles for complete AST comparison.

All sentences and required decisions are invented. No expected corpus,
candidate output, model or comparator result supplies an oracle.
"""

from copy import deepcopy

import pytest

from moparse_eval.requirement_ast import (
    AST_FEATURE_COMPARATORS,
    compare_feature_ast,
    compare_requirement_ast,
    compare_requirement_ast_collections,
)

SOURCE = {"path": "<invented-ast>", "lines": [8, 8], "text_span": [0, 80]}


def node(kind, **fields):
    return {"kind": kind, "source": deepcopy(SOURCE), **fields}


def proposition(subject="Company", attribute="own", obj="assets", **fields):
    return node("proposition", subject=subject, attribute=attribute, object=obj, **fields)


def nominal(head="assets", **fields):
    return node("noun_phrase", head=head, determiner=None, quantifier=None, modifiers=[],
                prepositional_complements=[], coordination=None) | fields


def pp(role="beneficiary", attachment="predicate", **fields):
    return node("prepositional_complement", preposition="for", semantic_role=role,
                attachment={"kind": attachment, "head": "provide" if attachment == "predicate" else "services"},
                complement=nominal("customers")) | fields


def coordination(operator="and", *children, mode="actions"):
    return node("coordination", operator=operator, mode=mode,
                children=list(children or (proposition(), proposition(attribute="operate"))))


def fixtures():
    atom = proposition()
    return {
        "finite_tense": proposition(tense="past"),
        "coordination_scope": coordination(),
        "alternative_membership": coordination("or"),
        "contrast_scope": coordination("but"),
        "modal_operator": node("modality", operator="may", polarity="positive", child=atom),
        "ability_operator": node("modality", operator="ability", polarity="positive", child=atom),
        "negation_scope": node("negation", child=atom),
        "condition_operands": node("conditions", bindings=[{"operator": "if", "operand": proposition("Board", "approve", "deal")}], child=atom),
        "restrictive_relative": node("relative", antecedent="Company", restriction=proposition("Company", "provide", "services"), child=atom),
        "scoped_reporting": node("reporting", speaker="Auditor", attribute="report", polarity="positive", tense="past", child=atom),
        "temporal_prose_scope": node("temporal_scope", qualifiers={"period": "2024"}, child=atom),
        "active_aspect_scope": node("active_aspect", aspect="perfect", tense="present", child=atom),
        "fronted_nominal_context": node("fronted_context", preposition="under", operator="under", role="restriction", context="the approved policy", child=atom),
        "nested_operator_scopes": node("negation", child=node("modality", operator="may", polarity="positive", child=atom)),
        "noun_phrase_composition": nominal(),
        "prepositional_attachment": pp(),
        "quantity_comparison": node("quantity_comparison", operator="ge", value="80", unit="%"),
        "purpose_scope": node("purpose_scope", operator="purpose", child=proposition(attribute="provide", obj="services"),
                              operand=proposition(attribute="support", obj="customers"), control={"kind": "subject_control", "controller": "Company"}),
        "controlled_infinitive_scope": node("controlled_infinitive_scope", operator="complement", child=proposition(attribute="enable", obj="developers"),
                                            operand=proposition("developers", "build", "platforms"), control={"kind": "object_control", "controller": "developers"}),
        "discourse_scope": node("discourse_scope", operator="for_example", role="example", marker="For example", child=atom),
        "circumstance_scope": node('circumstance_scope', operator='cause', direction='operand_to_child', degree='主要',
                                   simultaneous=False, operand=proposition('Efficiency', 'improve', ''), child=atom),
    }


@pytest.mark.parametrize("feature", sorted(AST_FEATURE_COMPARATORS))
def test_registered_feature_executes_independently_authored_structure_and_rejects_node_deletion(feature):
    required = fixtures()[feature]
    actual = deepcopy(required)
    actual["source"]["path"] = "<independent-candidate>"
    for first, second in ((required, actual), (actual, required)):
        result = compare_feature_ast(feature, first, second)
        assert result["status"] == "equivalent"
        assert sum(result[key] for key in ("equivalent", "conflict", "missing", "unresolved")) == 1
    mutated = deepcopy(actual)
    # Each deletion is chosen from hand-declared semantics, never a parser's
    # list of keys or an implementation-derived expected result.
    key = {"finite_tense": "tense", "coordination_scope": "children", "alternative_membership": "children",
           "contrast_scope": "children", "modal_operator": "child", "ability_operator": "child", "negation_scope": "child",
           "condition_operands": "bindings", "restrictive_relative": "restriction", "scoped_reporting": "speaker",
           "temporal_prose_scope": "qualifiers", "active_aspect_scope": "aspect", "fronted_nominal_context": "context",
           "nested_operator_scopes": "child", "noun_phrase_composition": "head", "prepositional_attachment": "complement",
           "quantity_comparison": "value", "purpose_scope": "operand", "controlled_infinitive_scope": "control",
           "discourse_scope": "child", 'circumstance_scope': 'operand'}[feature]
    del mutated[key]
    assert compare_feature_ast(feature, required, mutated)["status"] == "missing"
    # A source mutation is a distinct uncertainty; equal semantic strings do
    # not establish that an interpreted node has its own original source.
    mutated = deepcopy(actual)
    mutated["source"]["text_span"] = [80, 0]
    assert compare_feature_ast(feature, required, mutated)["status"] == "unresolved"


@pytest.mark.parametrize("feature", sorted(AST_FEATURE_COMPARATORS))
def test_each_feature_rejects_a_near_semantic_opposite_and_lost_or_misbound_relation(feature):
    required = fixtures()[feature]
    actual = deepcopy(required)
    if feature == "finite_tense":
        actual["tense"] = "present"
    elif feature in {"coordination_scope", "alternative_membership", "contrast_scope"}:
        actual["operator"] = "or" if feature != "alternative_membership" else "and"
    elif feature in {"modal_operator", "ability_operator"}:
        actual["operator"] = "must"
    elif feature == "negation_scope":
        actual = proposition()
    elif feature == "condition_operands":
        actual["bindings"][0]["operator"] = "unless"
    elif feature == "restrictive_relative":
        actual["antecedent"] = "Subsidiary"
    elif feature == "scoped_reporting":
        actual["polarity"] = "negative"
    elif feature == "temporal_prose_scope":
        actual["qualifiers"]["period"] = "2025"
    elif feature == "active_aspect_scope":
        actual["aspect"] = "progressive"
    elif feature == "fronted_nominal_context":
        actual["context"] = "the rejected policy"
    elif feature == "nested_operator_scopes":
        actual = node("modality", operator="may", polarity="positive", child=node("negation", child=proposition()))
    elif feature == "noun_phrase_composition":
        required["determiner"] = "our"
        actual["determiner"] = "their"
    elif feature == "prepositional_attachment":
        actual["attachment"] = {"kind": "nominal", "head": "services"}
    elif feature == "quantity_comparison":
        actual["operator"] = "lt"
    elif feature in {"purpose_scope", "controlled_infinitive_scope"}:
        actual["control"]["controller"] = "a different controller"
    elif feature == "discourse_scope":
        actual["operator"], actual["role"], actual["marker"] = "however", "contrast", "However"
    elif feature == 'circumstance_scope':
        actual['direction'] = 'child_to_operand'
    for first, second in ((required, actual), (actual, required)):
        assert compare_requirement_ast(first, second)["status"] == "conflict"
    relation = node("relation", type="scope_owner", left=required,
                    right=proposition(scope=["Products"]), direction="left_to_right")
    deleted = deepcopy(relation)
    del deleted["right"]
    assert compare_feature_ast(feature, relation, deleted)["status"] == "missing"
    misbound = deepcopy(relation)
    misbound["right"]["scope"] = ["Policy"]
    assert compare_feature_ast(feature, relation, misbound)["status"] == "conflict"


@pytest.mark.parametrize("required,actual", [
    (coordination("and"), coordination("or")),
    (coordination("and"), coordination("but")),
    (node("negation", child=coordination()), coordination("and", node("negation", child=proposition()), proposition(attribute="operate"))),
    (node("conditions", bindings=[{"operator": "if", "operand": proposition("Board", "approve", "deal")}], child=proposition()),
     node("conditions", bindings=[{"operator": "if", "operand": proposition()}], child=proposition("Board", "approve", "deal"))),
    (node("conditions", bindings=[{"operator": "if", "operand": proposition("Board", "approve", "deal")}], child=proposition()),
     node("conditions", bindings=[{"operator": "unless", "operand": proposition("Board", "approve", "deal")}], child=proposition())),
    (proposition(), proposition("Subsidiary")),
    (proposition(), proposition(attribute="operate")),
    (proposition(), proposition(obj="licenses")),
    (pp(), pp(attachment="nominal")),
    (pp(), pp(role="condition")),
    (node("modality", operator="may", polarity="positive", child=proposition()), node("modality", operator="must", polarity="positive", child=proposition())),
    (node("temporal_scope", qualifiers={"period": "2024"}, child=proposition()), node("temporal_scope", qualifiers={"period": "2025"}, child=proposition())),
    (node("active_aspect", aspect="perfect", tense="present", child=proposition()), node("active_aspect", aspect="progressive", tense="present", child=proposition())),
    (node("reporting", speaker="Auditor", attribute="report", polarity="positive", tense="past", child=proposition()), node("reporting", speaker="Director", attribute="report", polarity="positive", tense="past", child=proposition())),
    (node("quantity_comparison", operator="ge", value="80", unit="%"), node("quantity_comparison", operator="gt", value="80", unit="%")),
    (node("quantity_comparison", operator="ge", value="80", unit="%"), node("quantity_comparison", operator="ge", value="81", unit="%")),
    (node("relation", type="condition", left=proposition(), right=proposition("Board", "approve", "deal"), direction="left_to_right"),
     node("relation", type="condition", left=proposition("Board", "approve", "deal"), right=proposition(), direction="left_to_right")),
])
def test_semantically_opposed_near_text_and_attachment_mutations_conflict_in_both_directions(required, actual):
    for first, second in ((required, actual), (actual, required)):
        assert compare_requirement_ast(first, second)["status"] == "conflict"


@pytest.mark.parametrize("mutation", ["relation", "scope", "endpoint", "direction"])
def test_relation_loss_wrong_scope_endpoint_and_direction_are_not_equivalent(mutation):
    required = node("relation", type="restriction", left=pp(), right=proposition(scope=["Policy"]), direction="left_to_right")
    actual = deepcopy(required)
    if mutation == "relation":
        del actual["left"]
        status = "missing"
    elif mutation == "scope":
        actual["right"]["scope"] = ["Products"]
        status = "conflict"
    elif mutation == "endpoint":
        actual["right"]["subject"] = "Subsidiary"
        status = "conflict"
    else:
        actual["direction"] = "right_to_left"
        status = "conflict"
    assert compare_requirement_ast(required, actual)["status"] == status


@pytest.mark.parametrize("node_kind", ["unknown", "unsupported_clause", "attachment_unknown"])
def test_unimplemented_syntax_remains_unresolved_even_when_both_sides_are_identical(node_kind):
    required = node(node_kind, text="same literal words")
    assert compare_requirement_ast(required, deepcopy(required))["status"] == "unresolved"


@pytest.mark.parametrize("required", [[], {}, {"subject": "Company", "attribute": "own", "object": "assets"}, [{"text": "identical words"}], "identical words"])
def test_untyped_equal_input_is_not_claimed_as_a_supported_semantic_ast(required):
    assert compare_requirement_ast(required, deepcopy(required))["status"] == "unresolved"


@pytest.mark.parametrize("required", [
    coordination("xor"), node("modality", operator="uninterpreted", polarity="positive", child=proposition()),
    node("quantity_comparison", operator="approximately", value="80", unit="%"),
    node("coordination", operator="and", mode="actions", children=[]),
])
def test_unknown_operator_or_empty_group_is_not_certified_by_same_spelling(required):
    assert compare_requirement_ast(required, deepcopy(required))["status"] != "equivalent"


def test_missing_candidate_is_missing_and_partial_candidate_is_unresolved():
    required = proposition()
    assert compare_requirement_ast(required, None)["status"] == "missing"
    actual = proposition(complete=False)
    result = compare_requirement_ast(required, actual)
    # The explicit partial signal has no opposite business meaning.
    assert result["status"] == "unresolved"


@pytest.mark.parametrize("unit,value", [("元", "170000"), ("百万元", "0.17")])
def test_quantity_and_period_equivalence_reuse_owning_exact_rules(unit, value):
    required = node("quantity", value="17", unit="万元", currency="人民币", quantity_role="level")
    actual = node("quantity", value=value, unit=unit, currency="CNY", quantity_role="level")
    assert compare_requirement_ast(required, actual)["equivalent"]
    required = node("temporal_scope", qualifiers={"period_basis": "for the year ended", "period": "December 31, 2024"}, child=proposition())
    actual = node("temporal_scope", qualifiers={"period_basis": "止年度", "period": "2024-12-31"}, child=proposition())
    assert compare_requirement_ast(required, actual)["equivalent"]


def test_quantity_loss_and_currency_conflict_are_not_repaired_by_ast_comparison():
    required = node("quantity", value="17", unit="万元", currency="CNY")
    assert compare_requirement_ast(required, node("quantity", value="170001", unit="元", currency="CNY"))["status"] == "conflict"
    assert compare_requirement_ast(required, node("quantity", value="17", unit="万元", currency="USD"))["status"] == "conflict"
    assert compare_requirement_ast(required, node("quantity", value="170000", unit=None, currency="CNY"))["status"] != "equivalent"


def test_layout_keeps_quantity_binding_without_regrading_its_scalar_business_value():
    required = node("quantity", value="17", unit="万元", currency="CNY")
    actual = node("quantity", value="180000", unit="元", currency="CNY")
    assert compare_requirement_ast(required, actual)["status"] == "conflict"
    assert compare_requirement_ast(required, actual, {"layer": "L"})["status"] == "equivalent"
    assert compare_requirement_ast(required, {**actual, "currency": "USD"}, {"layer": "L"})["status"] == "conflict"
    threshold = node("quantity_comparison", operator="ge", value="80", unit="%")
    assert compare_requirement_ast(threshold, {**threshold, "value": "90"}, {"layer": "L"})["status"] == "conflict"


@pytest.mark.parametrize("required_value,actual_value,status", [
    ("17万元", "170000元", "equivalent"),
    ("17万元", "170001元", "conflict"),
    ("17万元", "170000", "conflict"),
    ("17万元", "17万美元", "conflict"),
])
def test_complete_scalar_object_and_its_nominal_head_share_exact_quantity_rules(required_value, actual_value, status):
    required = proposition(obj=required_value, object_phrase=nominal(required_value))
    actual = proposition(obj=actual_value, object_phrase=nominal(actual_value))
    assert compare_requirement_ast(required, actual)["status"] == status
    if actual_value == "170001元":
        assert compare_requirement_ast(required, actual, {"layer": "L"})["status"] == "equivalent"


def test_numeric_identity_and_temporal_complements_keep_their_values_in_layout_comparison():
    required = proposition(subject="2024", obj="17", subject_phrase=nominal("2024"), object_phrase=nominal("17"))
    actual = proposition(subject="2025", obj="18", subject_phrase=nominal("2025"), object_phrase=nominal("18"))
    assert compare_requirement_ast(required, actual, {"layer": "L"})["status"] == "conflict"
    first = pp(role="temporal_scope", preposition="in", complement=nominal("2024"))
    second = pp(role="temporal_scope", preposition="in", complement=nominal("2025"))
    assert compare_requirement_ast(first, second, {"layer": "L"})["status"] == "conflict"


def test_direct_scalar_business_answer_is_separate_from_its_layout_binding():
    required = proposition(obj="Control", object_phrase=nominal("Control"))
    actual = proposition(obj="Account", object_phrase=nominal("Account"))
    assert compare_requirement_ast(required, actual)["status"] == "conflict"
    assert compare_requirement_ast(required, actual, {"layer": "L"})["status"] == "equivalent"
    # Keeping the payload rule does not permit dropping the object, changing
    # its owner, or attaching a relation to the wrong predicate.
    assert compare_requirement_ast(required, proposition(obj="", object_phrase=None), {"layer": "L"})["status"] == "missing"
    assert compare_requirement_ast(required, {**actual, "subject": "Subsidiary"}, {"layer": "L"})["status"] == "conflict"
    assert compare_requirement_ast(pp(), pp(attachment="nominal"), {"layer": "L"})["status"] == "conflict"


def test_layout_preserves_condition_and_restriction_operand_meaning_and_set_composition():
    required = node("conditions", bindings=[{"operator": "if", "operand": proposition("Gate", "be", "open")}], child=proposition())
    actual = node("conditions", bindings=[{"operator": "if", "operand": proposition("Gate", "be", "closed")}], child=proposition())
    assert compare_requirement_ast(required, actual, {"layer": "L"})["status"] == "conflict"
    required = node("relative", antecedent="Company", restriction=proposition("Company", "own", "devices"), child=proposition())
    actual = node("relative", antecedent="Company", restriction=proposition("Company", "own", "licenses"), child=proposition())
    assert compare_requirement_ast(required, actual, {"layer": "L"})["status"] == "conflict"
    assert compare_requirement_ast(coordination("and"), coordination("or"), {"layer": "L"})["status"] == "conflict"


@pytest.mark.parametrize("required_value,actual_value", [("①", "1"), ("ﬁ", "fi")])
def test_default_ast_text_policy_does_not_collapse_protected_glyphs(required_value, actual_value):
    assert compare_requirement_ast(proposition(obj=required_value), proposition(obj=actual_value))["status"] == "conflict"
    assert compare_requirement_ast(proposition(subject=required_value), proposition(subject=actual_value))["status"] == "conflict"


def test_absent_feature_ast_does_not_remove_a_feature_gate():
    assert compare_feature_ast("coordination_scope", proposition(), proposition())["status"] == "unresolved"
    assert compare_feature_ast("future_unimplemented_feature", proposition(), proposition())["status"] == "unresolved"
    assert compare_feature_ast("alternative_membership", coordination("and"), coordination("and"))["status"] == "unresolved"
    assert compare_feature_ast("contrast_scope", coordination("and"), coordination("and"))["status"] == "unresolved"


def test_source_span_proof_rejects_borrowed_neighbor_evidence_even_when_words_match():
    text = "Lumen owns assets. Lumen owns assets."
    source = {"path": "<literal-source>", "lines": [3, 3], "text_span": [0, 17]}
    required = {"kind": "proposition", "subject": "Lumen", "attribute": "own", "predicate": "owns", "object": "assets",
                "source": source, "subject_source": {**source, "text_span": [0, 5]},
                "predicate_source": {**source, "text_span": [6, 10]}, "object_source": {**source, "text_span": [11, 17]}}
    def resolver(side, origin):
        return text[slice(*origin["text_span"])]
    assert compare_requirement_ast(required, deepcopy(required), {"source_resolver": resolver})["equivalent"]
    actual = deepcopy(required)
    actual["subject_source"]["text_span"] = [19, 24]
    result = compare_requirement_ast(required, actual, {"source_resolver": resolver})
    assert result["status"] == "unresolved"
    assert "statement_local" in repr(result) and "ast_role_not_bound_to_own_source" in repr(result)


def test_role_source_from_another_line_cannot_supply_same_offset_evidence():
    text = "Lumen owns assets."
    source = {"path": "<literal-source>", "lines": [3, 3], "text_span": [0, 17]}
    required = {"kind": "proposition", "subject": "Lumen", "attribute": "own", "object": "assets",
                "source": source, "subject_source": {**source, "text_span": [0, 5]}}
    actual = deepcopy(required)
    actual["subject_source"]["lines"] = [4, 4]

    def resolver(side, origin):
        return text[slice(*origin["text_span"])]

    assert compare_requirement_ast(required, actual, {"source_resolver": resolver})["status"] == "unresolved"


def test_one_to_one_statement_retrieval_never_uses_a_correct_answer_to_select_a_duplicate_identity():
    required = [proposition(obj="licenses")]
    actual = [proposition(obj="assets"), proposition(obj="licenses")]
    result = compare_requirement_ast_collections(required, actual)
    assert result["status"] == "unresolved"
    [row] = result["proof"]["rows"]
    assert row["actual_index"] is None
    assert row["retrieval"]["value_used"] is False
    assert row["retrieval"]["query"] == {"subjects": ["Company"], "predicates": ["own"], "scopes": []}
    assert len(row["retrieval"]["candidates"]) == 2


def test_statement_retrieval_has_capacity_one_and_rejects_explicit_subject_conflicts():
    result = compare_requirement_ast_collections([proposition(), proposition()], [proposition()])
    assert [row["decision"]["status"] for row in result["proof"]["rows"]] == ["equivalent", "missing"]
    assert result["proof"]["capacity_one"] is True
    result = compare_requirement_ast_collections([proposition()], [proposition("Subsidiary")])
    assert result["status"] == "conflict"
    [hit] = result["proof"]["rows"][0]["retrieval"]["candidates"]
    assert hit["conflicts"] == ["subject_identity"]
    assert not hit["accepted_for_comparison"]


def test_record_facets_locate_same_pronoun_action_before_comparing_values():
    first = proposition("he", "pay", "17", identity_facets={"record": {"Name": "Delta"}},
                        record_evidence=[{"text": "Name: Delta", "source": {"path": "<markdown-parent>"}}])
    second = proposition("he", "pay", "5", identity_facets={"record": {"Name": "Kappa"}})
    # The semantic record is independent of both the answer amount and the
    # native serialization of its original evidence.
    actual_first = proposition("he", "pay", "18", identity_facets={"record": {"Name": "Delta"}},
                               record_evidence=[{"native_ref": "#/texts/2", "source": {"path": "<native-parent>"}}])
    result = compare_requirement_ast_collections([first, second], [second, actual_first])
    rows = result["proof"]["rows"]
    assert [row["actual_index"] for row in rows] == [1, 0]
    assert [row["decision"]["status"] for row in rows] == ["conflict", "equivalent"]
    assert rows[0]["retrieval"]["query"]["identity_facets"] == [{"record": {"Name": "Delta"}}]
    assert rows[0]["retrieval"]["candidates"][0]["conflicts"] == ["record_or_facet_identity"]
    assert "17" not in repr(rows[0]["retrieval"]["query"])
    assert "record_evidence" in rows[0]["decision"]["proof"]


def test_native_block_source_can_prove_a_role_without_invented_line_numbers():
    text = "Lumen owns assets."
    source = {"path": "#/texts/1", "block": "native-body", "native_path": "#/texts/1", "lines": [], "text_span": [0, 17]}
    required = {"kind": "proposition", "subject": "Lumen", "attribute": "own", "object": "assets",
                "source": source, "subject_source": {**source, "text_span": [0, 5]}}

    def resolver(side, origin):
        return text[slice(*origin["text_span"])]

    assert compare_requirement_ast(required, deepcopy(required), {"source_resolver": resolver})["equivalent"]
    actual = deepcopy(required)
    actual["subject_source"]["block"] = "neighbor-body"
    assert compare_requirement_ast(required, actual, {"source_resolver": resolver})["status"] == "unresolved"


def test_condition_operand_is_checked_after_retrieving_main_statement_identity():
    required = node("conditions", bindings=[{"operator": "if", "operand": proposition("Board", "approve", "deal")}], child=proposition())
    actual = node("conditions", bindings=[{"operator": "if", "operand": proposition("Committee", "approve", "deal")}], child=proposition())
    result = compare_requirement_ast_collections([required], [actual])
    assert result["status"] == "conflict"
    [row] = result["proof"]["rows"]
    assert row["actual_index"] == 0
    assert row["retrieval"]["query"]["subjects"] == ["Company"]


def test_unused_candidate_statement_stays_unadjudicated():
    result = compare_requirement_ast_collections([proposition()], [proposition(), proposition("Subsidiary", "operate")])
    assert result["status"] == "unresolved"
    assert result["proof"]["unadjudicated_extra_indices"] == [1]


@pytest.mark.parametrize("required_text,actual_text,status", [
    ('Under our "user first, AI-driven" strategy, we have sharpened our business focus to two core businesses of e-commerce and cloud.',
     'Under our "user first, AI-driven" strategy, we have sharpened our business focus to two core businesses of e-commerce and cloud.', "equivalent"),
    ("The company may acquire the subsidiary.", "The company may acquire the subsidiary.", "equivalent"),
    ("The company may acquire the subsidiary.", "The company must acquire the subsidiary.", "conflict"),
    ("The company provides hardware and software.", "The company provides hardware or software.", "conflict"),
    ("The company does not operate the subsidiary.", "The company operates the subsidiary.", "conflict"),
    ("Revenue increased in 2024.", "Revenue increased in 2025.", "conflict"),
    ("The company provides services for customers.", "The company provides services for users.", "conflict"),
])
def test_real_reader_source_spans_reach_comparator_with_independent_sentence_decisions(required_text, actual_text, status):
    from moparse_eval.narrative_requirements import read_narrative

    required = read_narrative(required_text, {"path": "<required-literal>", "lines": [1, 1]})
    actual = read_narrative(actual_text, {"path": "<actual-literal>", "lines": [5, 5]})
    assert required["complete"] and actual["complete"]
    assert required["facts"] and all(fact["subject"] in {"The company", "Revenue", "we"} for fact in required["facts"])
    original = {"<required-literal>": required_text, "<actual-literal>": actual_text}

    def resolve(side, source):
        return original[source["path"]][slice(*source["text_span"])]

    assert compare_requirement_ast(required["logic"], actual["logic"], {"source_resolver": resolve})["status"] == status
    assert compare_requirement_ast(actual["logic"], required["logic"], {"source_resolver": resolve})["status"] == status


@pytest.mark.parametrize("text,target_kind,field,replacement", [
    ("The company provides hardware and software.", "coordination", "operator", "or"),
    ("The company may acquire the subsidiary.", "modality", "operator", "must"),
    ("The company must maintain at least 80% capacity.", "quantity_comparison", "operator", "le"),
    ("Revenue increased 17.", "proposition", "tense", "present"),
    ("We have sharpened our focus.", "active_aspect", "aspect", "progressive"),
])
def test_synchronized_semantic_mutations_cannot_reuse_a_different_original_operator(text, target_kind, field, replacement):
    from moparse_eval.narrative_requirements import read_narrative

    parsed = read_narrative(text, {"path": "<operator-literal>", "lines": [2, 2]})
    assert parsed["complete"]
    tree = deepcopy(parsed["logic"])

    def all_nodes(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from all_nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from all_nodes(child)

    target = next(item for item in all_nodes(tree) if item.get("kind") == target_kind)
    target[field] = replacement

    def resolve(side, origin):
        return text[slice(*origin["text_span"])]

    # Both derived trees agree with the same wrong operator. Independent
    # original text still makes the claimed interpretation unresolved.
    result = compare_requirement_ast(tree, deepcopy(tree), {"source_resolver": resolve})
    assert result["status"] == "unresolved"
    assert "not_bound_to" in repr(result)


def test_condition_operator_mutation_and_negation_source_loss_stay_unresolved():
    from moparse_eval.narrative_requirements import read_narrative

    for text, mutate in (
        ("The company may acquire assets if the board approves the deal.", "condition"),
        ("The company does not operate assets.", "negation"),
    ):
        parsed = read_narrative(text, {"path": "<operator-literal>", "lines": [2, 2]})
        assert parsed["complete"]
        tree = deepcopy(parsed["logic"][0])
        if mutate == "condition":
            tree["bindings"][0]["operator"] = "unless"
        else:
            del tree["operator_source"]

        def resolve(side, origin, own=text):
            return own[slice(*origin["text_span"])]

        assert compare_requirement_ast(tree, deepcopy(tree), {"source_resolver": resolve})["status"] == "unresolved"


@pytest.mark.parametrize("text,opposite", [
    ("公司必须保存记录。", "公司可以保存记录。"),
    ("公司不得保存记录。", "公司必须保存记录。"),
    ("公司提供硬件以及软件。", "公司提供硬件或软件。"),
])
def test_chinese_reader_uses_same_typed_comparator_and_own_operator_source_contract(text, opposite):
    from moparse_eval.cjk_narrative_requirements import read_cjk_narrative

    first = read_cjk_narrative(text, {"path": "<cn-required>", "lines": [1, 1]})
    second = read_cjk_narrative(opposite, {"path": "<cn-actual>", "lines": [1, 1]})
    assert first["complete"] and second["complete"]
    originals = {"<cn-required>": text, "<cn-actual>": opposite}

    def resolve(side, origin):
        return originals[origin["path"]][slice(*origin["text_span"])]

    assert compare_requirement_ast(first["logic"], deepcopy(first["logic"]), {"source_resolver": resolve})["equivalent"]
    for required, actual in ((first, second), (second, first)):
        assert compare_requirement_ast(required["logic"], actual["logic"], {"source_resolver": resolve})["status"] == "conflict"


@pytest.mark.parametrize("text,opposite,kind,operator", [
    ("The company provides services to support customers.", "The company provides services to support suppliers.", "purpose_scope", "purpose"),
    ("The company enables developers to build platforms.", "The company enables operators to build platforms.", "controlled_infinitive_scope", "complement"),
    ("For example, the company provides services.", "However, the company provides services.", "discourse_scope", "for_example"),
])
def test_source_bound_purpose_controller_and_discourse_oracles_reach_both_comparison_layers(text, opposite, kind, operator):
    from moparse_eval.narrative_requirements import read_narrative

    required = read_narrative(text, {"path": "<scope-required>", "lines": [1, 1]})
    actual = read_narrative(opposite, {"path": "<scope-actual>", "lines": [3, 3]})
    assert required["complete"] and actual["complete"]
    [root] = required["logic"]
    assert (root["kind"], root["operator"]) == (kind, operator)
    if kind != "discourse_scope":
        assert root["operand"]["kind"] == "proposition"
        assert root["operand"].get("tense") is None
        assert [fact["attribute"] for fact in required["facts"]] == ["provide" if kind == "purpose_scope" else "enable"]
        assert [fact["attribute"] for fact in required["semantic_operands"]] == ["support" if kind == "purpose_scope" else "build"]
    originals = {"<scope-required>": text, "<scope-actual>": opposite}

    def resolve(side, source):
        return originals[source["path"]][slice(*source["text_span"])]

    for layer in ("B", "L"):
        context = {"layer": layer, "source_resolver": resolve}
        assert compare_feature_ast(kind, required["logic"], deepcopy(required["logic"]), context)["equivalent"]
        for first, second in ((required["logic"], actual["logic"]), (actual["logic"], required["logic"])):
            assert compare_requirement_ast(first, second, context)["status"] == "conflict"
    corrupted = deepcopy(required["logic"])
    if kind == "discourse_scope":
        corrupted[0]["operator"] = "however"
        corrupted[0]["role"] = "contrast"
    else:
        corrupted[0]["control"]["controller"] = "a different owner"
    assert compare_feature_ast(kind, corrupted, deepcopy(corrupted), {"source_resolver": resolve})["status"] == "unresolved"


def test_partial_purpose_never_turns_successful_operand_into_a_complete_assertion_or_equivalence():
    from moparse_eval.narrative_requirements import read_narrative

    text = "The company provides services through unknown relations to support customers."
    result = read_narrative(text, {"path": "<partial-purpose>", "lines": [1, 1]})
    assert result["complete"] is False and result["unresolved"]
    assert compare_requirement_ast(result["logic"], deepcopy(result["logic"]))["status"] == "unresolved"


@pytest.mark.parametrize("operator", ["and", "or"])
@pytest.mark.parametrize("mode", ["objects", "actions", "nominal_members"])
def test_unordered_members_are_compared_inside_the_bound_group_with_capacity_one(operator, mode):
    members = ([nominal("hardware"), nominal("software")] if mode == "nominal_members" else
               [proposition(attribute="develop"), proposition(attribute="operate")] if mode == "actions" else
               [proposition(obj="hardware"), proposition(obj="software")])
    first = coordination(operator, *members, mode=mode)
    second = coordination(operator, *deepcopy(members[::-1]), mode=mode)
    for required, actual in ((first, second), (second, first)):
        result = compare_requirement_ast(required, actual)
        assert result["equivalent"]
        [group] = [child for child in result["proof"]["children"] if child["path"] == "$.children"]
        assert group["proof"]["rule"] == "bound_group_semantic_multiset"
        assert group["proof"]["capacity_one"] is True
        assert group["proof"]["owning_group_already_bound"] is True
        assert group["proof"]["value_used_for_statement_identity"] is False
        assert [item["actual_index"] for item in group["proof"]["matches"]] == [1, 0]
        assert [child["path"] for child in group["proof"]["children"]] == ["$.children[0]", "$.children[1]"]


@pytest.mark.parametrize("operator", ["and", "or"])
def test_unordered_group_retains_duplicate_multiplicity_missing_members_and_actual_owner(operator):
    alpha, beta = proposition(obj="Alpha"), proposition(obj="Beta")
    required = coordination(operator, alpha, deepcopy(alpha), beta, mode="objects")
    equivalent = coordination(operator, deepcopy(beta), deepcopy(alpha), deepcopy(alpha), mode="objects")
    assert compare_requirement_ast(required, equivalent)["equivalent"]
    wrong_duplicate = coordination(operator, deepcopy(alpha), deepcopy(beta), deepcopy(beta), mode="objects")
    assert compare_requirement_ast(required, wrong_duplicate)["status"] == "conflict"
    missing = coordination(operator, deepcopy(alpha), deepcopy(beta), mode="objects")
    assert compare_requirement_ast(required, missing)["status"] == "missing"
    rebound = deepcopy(equivalent)
    rebound["children"][1]["subject"] = "Subsidiary"
    assert compare_requirement_ast(required, rebound)["status"] == "conflict"


@pytest.mark.parametrize("operator,fields", [("but", {}), ("and", {"mode": "sequence"}), ("and", {"ordered": True})])
def test_explicit_sequence_and_contrast_preserve_member_order(operator, fields):
    first = coordination(operator, proposition(obj="Alpha"), proposition(obj="Beta"), mode="objects") | fields
    second = deepcopy(first)
    second["children"].reverse()
    assert compare_requirement_ast(first, second)["status"] == "conflict"


def test_unordered_scoped_group_lost_member_does_not_change_its_owning_statement_identity():
    required = coordination("and", proposition(attribute="develop", scope=["Products"]),
                            proposition(attribute="operate", scope=["Products"]), mode="actions")
    actual = proposition(attribute="develop", scope=["Products"])
    result = compare_requirement_ast_collections([required], [actual])
    [row] = result["proof"]["rows"]
    assert row["actual_index"] == 0
    assert row["retrieval"]["query"]["scopes"] == [["Products"]]
    assert row["retrieval"]["candidates"][0]["accepted_for_comparison"]


@pytest.mark.parametrize("text,opposite", [
    ("The company provides hardware and software.", "The company provides software and hardware."),
    ("The company provides hardware or software.", "The company provides software or hardware."),
    ("The company develops and operates cloud services.", "The company operates and develops cloud services."),
])
def test_reordered_group_reader_sources_remain_independent_and_business_equivalent(text, opposite):
    from moparse_eval.narrative_requirements import read_narrative

    required = read_narrative(text, {"path": "<ordered-required>", "lines": [1, 1]})
    actual = read_narrative(opposite, {"path": "<ordered-actual>", "lines": [5, 5]})
    assert required["complete"] and actual["complete"]
    original = {"<ordered-required>": text, "<ordered-actual>": opposite}

    def resolve(side, source):
        return original[source["path"]][slice(*source["text_span"])]

    result = compare_requirement_ast_collections(required["logic"], actual["logic"], {"source_resolver": resolve})
    assert result["equivalent"]
    [row] = result["proof"]["rows"]
    assert row["retrieval"]["value_used"] is False
