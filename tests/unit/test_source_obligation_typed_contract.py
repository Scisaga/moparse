"""Independent source classification and local relation-binding oracles.

All sources are invented. Expected roles below are authored directly rather
than copied from a semantic reader or a generated requirement view.
"""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph
from moparse_eval.source_obligations import (
    SEMANTIC_OBLIGATION_TYPES,
    _infinitive_bindings,
    audit_source_obligations,
    build_source_obligation_inventory,
    validate_relation_binding,
)
from tests.unit.test_source_obligation_oracle import expected, target


@pytest.mark.parametrize(
    "text,kind,semantic_type",
    [
        ("The company provides services.", "text", "assertive_proposition"),
        ("Name: Lumen", "text", "structured_field"),
        ("Revenue: 17", "text", "structured_field"),
        ("Description: Lumen owns Kappa.", "text", "assertive_proposition"),
        ("Description: An important portfolio", "text", "unknown"),
        ("Unit: credits", "text", "qualifier"),
        ("Operating businesses", "heading", "nominal_label"),
        ('See "Accounting policies".', "text", "navigation_reference"),
        ("An important portfolio of industrial businesses", "text", "unknown"),
        ("重要业务组合及经营安排", "text", "unknown"),
    ],
)
def test_source_fragments_have_positive_typed_contracts_without_inventing_propositions(
    text, kind, semantic_type
):
    authored = expected(target(text, kind=kind))
    before = deepcopy(authored)
    inventory = build_source_obligation_inventory(authored)
    [fragment] = [
        row
        for row in inventory["obligations"]
        if row["interpretation_rule"] == "each_printed_semantic_fragment"
    ]
    assert fragment["semantic_type"] == semantic_type
    assert fragment["source"]["text_span"] == [0, len(text)]
    assert fragment["text"] == text and fragment["expected_roles"]
    assert all(
        row["semantic_type"] in SEMANTIC_OBLIGATION_TYPES for row in inventory["obligations"]
    )
    if semantic_type not in {"assertive_proposition", "document_composition"}:
        assert fragment["kind"] != "proposition"
    if semantic_type == "unknown":
        assert "non_applicability_rule" not in fragment
        graph = compile_requirement_graph(authored)
        disposition = next(
            row
            for row in graph["source_obligation_coverage"]["dispositions"]
            if row["obligation_id"] == fragment["id"]
        )
        assert disposition["status"] == "pending"
        assert disposition["unexplained_ranges"]
        for part in disposition["unexplained_ranges"]:
            lo, hi = part["source"]["text_span"]
            assert text[lo:hi] == part["text"]
    assert authored == before


def test_field_obligation_is_not_duplicated_as_a_second_identical_fragment_binding():
    inventory = build_source_obligation_inventory(expected(target("Revenue: 17")))
    bindings = [
        row
        for row in inventory["obligations"]
        if row.get("binding_role") in {"field_binding", "semantic_binding"}
    ]
    assert len(bindings) == 1
    assert bindings[0]["binding_role"] == "field_binding"
    # Literal and typed field interpretation remain independently required.
    assert {row["kind"] for row in inventory["obligations"]} == {
        "text",
        "semantic_content",
        "relation",
    }


def _source(start, end):
    return {"path": "<authored-local-binding>", "lines": [3, 3], "text_span": [start, end]}


def _binding():
    fact = {
        "id": "B:authored",
        "subject": "Lumen",
        "attribute": "own",
        "predicate": "owns",
        "object": "Kappa",
        "value": "Kappa",
        "scope": ["Operating businesses"],
        "qualifiers": {"tense": "present", "polarity": "positive"},
        "source": _source(20, 36),
        "subject_source": _source(20, 25),
        "predicate_source": _source(26, 30),
        "object_source": _source(31, 36),
    }
    edge = {
        "id": "L:authored",
        "fact_id": "B:authored",
        "type": "field_binding",
        "left": {"subject": "Lumen", "attribute": "own"},
        "right": {
            "subject": "Lumen",
            "attribute": "own",
            "scope": ["Operating businesses"],
            "qualifiers": {"tense": "present"},
        },
        "source": _source(20, 36),
        "binding_evidence": {
            "statement_source": _source(20, 36),
            "subject_source": _source(20, 25),
            "predicate_source": _source(26, 30),
            "object_source": _source(31, 36),
        },
    }
    obligation = {"source": _source(20, 37), "binding_role": "semantic_binding"}
    return obligation, fact, edge


def test_relation_binding_returns_auditable_positive_proof_for_both_endpoints_and_statement():
    obligation, fact, edge = _binding()
    result = validate_relation_binding(obligation, fact, edge)
    assert result["status"] == "equivalent" and result["equivalent"] is True
    assert {item["dimension"] for item in result["proof"]} >= {
        "right_subject",
        "right_attribute",
        "statement_source",
    }
    assert result["conflicts"] == result["missing_evidence"] == result["unresolved_evidence"] == []


@pytest.mark.parametrize(
    "mutation,dimension",
    [
        ("type", "relation_type"),
        ("fact", "fact_id"),
        ("left", "left_subject"),
        ("right", "right_subject"),
        ("predicate", "right_attribute"),
        ("object", "right_object"),
        ("scope", "right_scope"),
        ("qualifier", "right_qualifiers.tense"),
        ("statement", "statement_source"),
        ("statement_scope", "statement_scope"),
        ("object_source", "object_source"),
        ("subject_source", "subject_source"),
        ("direction", "left_subject"),
    ],
)
def test_local_binding_rejects_explicit_endpoint_direction_role_and_scope_conflicts(
    mutation, dimension
):
    obligation, fact, edge = _binding()
    if mutation == "type":
        edge["type"] = "reading_order"
    elif mutation == "fact":
        edge["fact_id"] = "B:neighbor"
    elif mutation == "left":
        edge["left"]["subject"] = "Vega"
    elif mutation == "right":
        edge["right"]["subject"] = "Vega"
    elif mutation == "predicate":
        edge["right"]["attribute"] = "acquire"
    elif mutation == "object":
        edge["right"]["object"] = "Sigma"
    elif mutation == "scope":
        edge["right"]["scope"] = ["Other businesses"]
    elif mutation == "qualifier":
        edge["right"]["qualifiers"]["tense"] = "past"
    elif mutation == "statement":
        edge["binding_evidence"]["statement_source"] = _source(40, 56)
    elif mutation == "statement_scope":
        edge["binding_evidence"]["statement_source"] = _source(26, 30)
    elif mutation == "direction":
        edge["left"] = {"subject": "Kappa", "attribute": "own"}
    else:
        edge["binding_evidence"][mutation] = _source(40, 45)
    result = validate_relation_binding(obligation, fact, edge)
    assert result["status"] == "conflict" and not result["equivalent"]
    assert dimension in {item["dimension"] for item in result["conflicts"]}


@pytest.mark.parametrize(
    "missing", ["left", "right", "subject_source", "predicate_source", "object_source"]
)
def test_local_binding_missing_endpoint_or_role_proof_cannot_pass(missing):
    obligation, fact, edge = _binding()
    if missing in {"left", "right"}:
        edge.pop(missing)
    else:
        edge["binding_evidence"].pop(missing)
    result = validate_relation_binding(obligation, fact, edge)
    assert result["status"] == "missing" and not result["equivalent"]
    assert result["missing_evidence"]


def test_local_binding_retains_unresolved_when_a_role_edge_has_no_exact_statement_bridge():
    obligation, fact, edge = _binding()
    edge["source"] = deepcopy(fact["predicate_source"])
    edge["binding_evidence"].pop("statement_source")
    result = validate_relation_binding(obligation, fact, edge)
    assert result["status"] == "unresolved" and not result["equivalent"]
    assert result["unresolved_evidence"] == ["relation_has_no_exact_statement_bridge"]


@pytest.mark.parametrize(
    "text,preposition,role",
    [
        ("The company provides services for international customers.", "for", "beneficiary"),
        ("Revenue increased in 2024.", "in", "temporal_scope"),
        ("The company operates subject to regulatory approval.", "subject to", "restriction"),
    ],
)
def test_ordinary_PP_is_a_source_bound_attachment_not_an_invented_qualifier(
    text, preposition, role
):
    authored = expected(target(text))
    graph = compile_requirement_graph(authored)
    [obligation] = [
        row
        for row in graph["source_obligation_inventory"]["obligations"]
        if row.get("binding_role") == "prepositional_attachment"
    ]
    assert obligation["kind"] == "relation" and obligation["semantic_type"] == "logical_relation"
    assert obligation["text"] == preposition
    lo, hi = obligation["source"]["text_span"]
    assert text[lo:hi] == preposition
    [edge] = [
        row for row in graph["relations"] if row["type"] == "narrative_prepositional_attachment"
    ]
    assert edge["left"]["semantic_role"] == role
    coverage = graph["source_obligation_coverage"]
    assert (
        next(row for row in coverage["dispositions"] if row["obligation_id"] == obligation["id"])[
            "status"
        ]
        == "explained"
    )
    # Drop the actual relation, preserving every role word and AST node.
    graph["relations"].remove(edge)
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert (
        next(row for row in coverage["dispositions"] if row["obligation_id"] == obligation["id"])[
            "status"
        ]
        == "pending"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "fact_node",
        "head",
        "complement",
        "attachment",
        "scope",
        "direction",
        "left_complement",
        "left_preposition",
    ],
)
def test_preposition_relation_cannot_borrow_a_neighbor_or_change_head_complement_scope(mutation):
    graph = compile_requirement_graph(
        expected(target("The company provides services for international customers."))
    )
    obligation = next(
        row
        for row in graph["source_obligation_inventory"]["obligations"]
        if row.get("binding_role") == "prepositional_attachment"
    )
    edge = next(
        row for row in graph["relations"] if row["type"] == "narrative_prepositional_attachment"
    )
    fact = next(row for row in graph["nodes"] if row["id"] == edge["fact_id"])
    if mutation == "fact_node":
        fact["prepositional_complements"] = []
    elif mutation == "head":
        edge["binding_evidence"]["head_source"] = _source(400, 410)
    elif mutation == "complement":
        edge["binding_evidence"]["complement_source"] = _source(400, 410)
    elif mutation == "attachment":
        edge["left"]["attachment"]["kind"] = "nominal"
    elif mutation == "scope":
        edge["right"]["scope"] = ["Other business"]
    elif mutation == "left_complement":
        edge["left"]["complement"] = "domestic suppliers"
    elif mutation == "left_preposition":
        edge["left"]["preposition"] = "against"
    else:
        edge["right"]["subject"] = "international customers"
    result = validate_relation_binding(obligation, fact, edge)
    assert result["status"] in {"missing", "conflict"} and not result["equivalent"]


def test_obligation_of_first_statement_does_not_borrow_second_statements_valid_binding():
    text = "Lumen owns Kappa. Lumen owns Sigma."
    graph = compile_requirement_graph(expected(target(text)))
    inventory = graph["source_obligation_inventory"]
    first, second = [
        row for row in inventory["obligations"] if row.get("binding_role") == "semantic_binding"
    ]
    first_fact, second_fact = [
        row for row in graph["nodes"] if row["id"] in graph["projections"]["B"]
    ]
    graph["relations"] = [
        edge for edge in graph["relations"] if edge.get("fact_id") != first_fact["id"]
    ]
    coverage = audit_source_obligations(inventory, graph)
    dispositions = {row["obligation_id"]: row for row in coverage["dispositions"]}
    assert dispositions[first["id"]]["status"] == "pending"
    assert dispositions[second["id"]]["status"] == "explained"
    assert {item["requirement"] for item in dispositions[second["id"]]["evidence"]} == {
        second_fact["id"]
    }


def test_a_modality_token_cannot_borrow_the_neighboring_statements_valid_qualifier_relation():
    text = "Lumen may acquire Kappa. Vega shall operate Sigma."
    graph = compile_requirement_graph(expected(target(text)))
    inventory = graph["source_obligation_inventory"]
    obligation = next(
        row
        for row in inventory["obligations"]
        if row["kind"] == "qualifier" and row["text"] == "may"
    )
    own = next(
        row
        for row in graph["relations"]
        if row["type"] == "qualifier_scope" and row["left"].get("text") == "may"
    )
    neighbor = next(
        row
        for row in graph["relations"]
        if row["type"] == "qualifier_scope" and row["left"].get("text") == "shall"
    )
    graph["relations"].remove(own)
    # Retain the neighboring owner's valid endpoint, value and statement;
    # only point its relation at the first source's actual MAY token.
    neighbor["source"] = deepcopy(obligation["source"])
    coverage = audit_source_obligations(inventory, graph)
    disposition = next(
        row for row in coverage["dispositions"] if row["obligation_id"] == obligation["id"]
    )
    assert disposition["status"] == "pending"


def _authored_infinitive():
    raw = "The company provides tools to support customers."
    obligation = next(
        row
        for row in build_source_obligation_inventory(expected(target(raw)))["obligations"]
        if row.get("binding_role") == "attachment"
    )
    origin = obligation["statement_source"]

    def source(a, b):
        return {**origin, "text_span": [a, b]}

    child = {"kind": "proposition", "source": source(0, 26)}
    operand = {
        "kind": "proposition",
        "subject": "The company",
        "attribute": "support",
        "object": "customers",
        "source": source(30, 47),
        "subject_source": source(0, 11),
        "predicate_source": source(30, 37),
        "object_source": source(38, 47),
    }
    control = {
        "kind": "subject_control",
        "controller": "The company",
        "controller_source": source(0, 11),
    }
    wrapper = {
        "kind": "purpose_scope",
        "operator": "purpose",
        "operator_source": source(27, 29),
        "control": control,
        "child": child,
        "operand": operand,
        "source": source(0, 47),
    }
    fact = {
        "id": "B:main",
        "subject": "The company",
        "attribute": "provide",
        "predicate": "provides",
        "object": "tools",
        "value": "tools",
        "source": source(0, 26),
        "scope": [],
        "subject_source": source(0, 11),
        "object_source": source(21, 26),
    }
    edge = {
        "id": "L:purpose",
        "fact_id": "B:main",
        "type": "narrative_purpose_scope",
        "left": {
            "operator": "purpose",
            "controller": "The company",
            "control_kind": "subject_control",
        },
        "right": {"subject": "The company", "attribute": "provide", "scope": []},
        "source": source(27, 29),
        "binding_evidence": {
            "statement_source": source(0, 26),
            "operator_source": source(27, 29),
            "controller_source": source(0, 11),
            "operand_source": source(30, 47),
            "operand_logic": deepcopy(operand),
        },
    }
    return obligation, fact, edge, wrapper


def test_independent_TO_inventory_defers_preposition_vs_infinitive_to_a_source_bound_interpretation():
    obligation, fact, edge, wrapper = _authored_infinitive()
    assert obligation["kind"] == "relation" and obligation["text"] == "to"
    assert obligation["attachment_candidates"] == ["prepositional_complement", "infinitival_marker"]
    [proof] = _infinitive_bindings(obligation, [fact], [edge], [wrapper])
    assert proof["requirement"] == "B:main" and proof["relation"] == "L:purpose"
    assert proof["control"] == {
        "kind": "subject_control",
        "controller": "The company",
        "controller_source": wrapper["control"]["controller_source"],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_node",
        "missing_edge",
        "controller",
        "controller_source",
        "operand",
        "scope",
        "fact_id",
    ],
)
def test_infinitival_attachment_requires_its_own_controller_operand_relation_and_scope(mutation):
    obligation, fact, edge, wrapper = _authored_infinitive()
    edges, nodes = [edge], [wrapper]
    if mutation == "missing_node":
        nodes.clear()
    elif mutation == "missing_edge":
        edges.clear()
    elif mutation == "controller":
        edge["left"]["controller"] = "customers"
    elif mutation == "controller_source":
        edge["binding_evidence"]["controller_source"] = deepcopy(
            wrapper["operand"]["object_source"]
        )
    elif mutation == "operand":
        edge["binding_evidence"]["operand_logic"]["attribute"] = "acquire"
    elif mutation == "scope":
        edge["right"]["scope"] = ["Unrelated business"]
    else:
        edge["fact_id"] = "B:neighbor"
    assert _infinitive_bindings(obligation, [fact], edges, nodes) == []


def test_synchronized_control_text_and_source_cannot_turn_subject_control_into_object_control():
    obligation, fact, edge, wrapper = _authored_infinitive()
    wrapper["control"]["controller"] = edge["left"]["controller"] = "tools"
    wrapper["control"]["controller_source"] = edge["binding_evidence"]["controller_source"] = (
        deepcopy(fact["object_source"])
    )
    assert _infinitive_bindings(obligation, [fact], [edge], [wrapper]) == []


@pytest.mark.parametrize(
    "auxiliary,predicate,aspect", [("is", "making", "progressive"), ("has", "made", "perfect")]
)
def test_lossless_active_inflection_and_nominal_PP_have_own_source_roles(
    auxiliary, predicate, aspect
):
    text = f"Lumen {auxiliary} {predicate} investments in research."
    graph = compile_requirement_graph(expected(target(text)))
    [fact] = [row for row in graph["nodes"] if row["id"] in graph["projections"]["B"]]
    assert (fact["subject"], fact["attribute"], fact["object"], fact["qualifiers"]["aspect"]) == (
        "Lumen",
        "make",
        "investments in research",
        aspect,
    )
    assert graph["semantic_complete"] and graph["unresolved"] == []
    start = text.index(predicate)
    assert fact["predicate_source"]["text_span"] == [start, start + len(predicate)]
    # Keep every source word and synchronize the field edge action. Inflection
    # licenses MAKE, and cannot license the unrelated action ACQUIRE.
    fact["attribute"] = "acquire"
    for edge in graph["relations"]:
        if edge.get("fact_id") == fact["id"]:
            if "attribute" in edge.get("right", {}):
                edge["right"]["attribute"] = "acquire"
            if edge["type"] == "field_binding":
                edge["left"]["attribute"] = "acquire"
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert not coverage["semantic_complete"]


@pytest.mark.parametrize("mutation", [None, "edge", "node", "marker_source", "synchronized_role"])
def test_discourse_scope_is_positive_source_evidence_and_cannot_hide_missing_marker_binding(
    mutation,
):
    text = "For example, Orion is making investments in storage to capture market opportunities."
    graph = compile_requirement_graph(expected(target(text)))
    assert graph["semantic_complete"] and graph["unresolved"] == []
    [edge] = [row for row in graph["relations"] if row["type"] == "narrative_discourse_scope"]
    [wrapper] = [row for row in graph["logic"] if row["kind"] == "discourse_scope"]
    assert edge["left"] == {"operator": "for_example", "role": "example"}
    assert edge["binding_evidence"]["marker_source"]["text_span"] == [0, len("For example")]
    main = [row for row in graph["nodes"] if row["id"] in graph["projections"]["B"]]
    assert [(row["subject"], row["attribute"]) for row in main] == [("Orion", "make")]
    if mutation == "edge":
        graph["relations"].remove(edge)
    elif mutation == "node":
        graph["logic"].remove(wrapper)
    elif mutation == "marker_source":
        edge["binding_evidence"]["marker_source"] = deepcopy(main[0]["subject_source"])
    elif mutation == "synchronized_role":
        wrapper["role"] = edge["left"]["role"] = "contrast"
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert coverage["semantic_complete"] is (mutation is None)


COLLECTIVE = "Orion provides tools to help vendors, clients and partners to leverage resources to engage with users and operate in an efficient way."


def collective_control():
    graph = compile_requirement_graph(expected(target(COLLECTIVE)))
    inventory = graph["source_obligation_inventory"]
    start = COLLECTIVE.index("to leverage")
    obligation = next(
        row
        for row in inventory["obligations"]
        if row.get("binding_role") == "attachment"
        and row["source"]["text_span"] == [start, start + 2]
    )
    from moparse_eval.source_obligations import _walk

    wrapper = next(
        node for node in _walk(graph["logic"]) if node.get("kind") == "controlled_infinitive_scope"
    )
    return graph, obligation, wrapper


def test_collective_object_control_requires_every_exact_member_and_preserves_nonassertion():
    graph, obligation, wrapper = collective_control()
    assert graph["semantic_complete"] and graph["unresolved"] == []
    main = [node for node in graph["nodes"] if node["id"] in graph["projections"]["B"]]
    assert [(node["subject"], node["attribute"], node["object"]) for node in main] == [
        ("Orion", "provide", "tools")
    ]
    operands = [node for node in graph["nodes"] if node.get("kind") == "semantic_operand"]
    assert [
        (node["subject"], node["object"]) for node in operands if node["attribute"] == "help"
    ] == [("Orion", "vendors"), ("Orion", "clients"), ("Orion", "partners")]
    control = "vendors, clients and partners"
    assert wrapper["control"]["controller"] == control
    start = COLLECTIVE.index(control)
    assert wrapper["control"]["controller_source"]["text_span"] == [start, start + len(control)]
    disposition = next(
        row
        for row in graph["source_obligation_coverage"]["dispositions"]
        if row["obligation_id"] == obligation["id"]
    )
    assert disposition["status"] == "explained" and disposition["evidence"]
    for evidence in disposition["evidence"]:
        binding = evidence["controller_binding"]
        assert binding["kind"] == "coordinated_objects" and binding["operator"] == "and"
        assert [member["object"] for member in binding["members"]] == [
            "vendors",
            "clients",
            "partners",
        ]
        for member in binding["members"]:
            lo, hi = member["source"]["text_span"]
            assert COLLECTIVE[lo:hi] == member["object"]


@pytest.mark.parametrize(
    "mutation",
    [
        "fact_delete",
        "field_relation_delete",
        "member_delete",
        "member_reorder",
        "and_to_or",
        "operator_source",
        "controller_narrow",
        "synchronized_subject_control",
        "relation_operator",
        "member_source",
    ],
)
def test_collective_control_cannot_be_proved_by_a_sibling_or_a_subset_of_objects(mutation):
    graph, obligation, wrapper = collective_control()
    operands = [node for node in graph["nodes"] if node.get("kind") == "semantic_operand"]
    client = next(
        node for node in operands if node["attribute"] == "help" and node["object"] == "clients"
    )
    edges = [
        edge
        for edge in graph["operand_relations"]
        if edge.get("type") == "narrative_controlled_infinitive_scope"
        and edge.get("binding_evidence", {}).get("operator_source") == obligation["source"]
    ]
    if mutation == "fact_delete":
        graph["nodes"].remove(client)
    elif mutation == "field_relation_delete":
        graph["operand_relations"] = [
            edge
            for edge in graph["operand_relations"]
            if not (edge.get("type") == "field_binding" and edge.get("fact_id") == client["id"])
        ]
    elif mutation == "member_delete":
        wrapper["child"]["children"].pop(1)
    elif mutation == "member_reorder":
        wrapper["child"]["children"].reverse()
    elif mutation == "and_to_or":
        wrapper["child"]["operator"] = "or"
    elif mutation == "operator_source":
        wrapper["child"]["operator_sources"] = [deepcopy(client["object_source"])]
    elif mutation == "controller_narrow":
        first = next(
            node for node in operands if node["attribute"] == "help" and node["object"] == "vendors"
        )
        wrapper["control"]["controller"] = first["object"]
        wrapper["control"]["controller_source"] = deepcopy(first["object_source"])
        for edge in edges:
            edge["left"]["controller"] = first["object"]
            edge["binding_evidence"]["controller_source"] = deepcopy(first["object_source"])
    elif mutation == "synchronized_subject_control":
        wrapper["control"]["kind"] = "subject_control"
        wrapper["control"]["controller"] = client["subject"]
        wrapper["control"]["controller_source"] = deepcopy(client["subject_source"])
        for edge in edges:
            edge["left"].update(control_kind="subject_control", controller=client["subject"])
            edge["binding_evidence"]["controller_source"] = deepcopy(client["subject_source"])
    elif mutation == "relation_operator":
        for edge in edges:
            edge["left"]["operator"] = "purpose"
    else:
        wrapper["child"]["children"][1]["object_source"] = deepcopy(
            wrapper["child"]["children"][0]["object_source"]
        )
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    disposition = next(
        row for row in coverage["dispositions"] if row["obligation_id"] == obligation["id"]
    )
    assert disposition["status"] == "pending"
