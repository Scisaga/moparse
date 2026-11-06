"""Authored omissions: printed words are not independent proposition proof."""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph
from moparse_eval.source_obligations import audit_source_obligations
from tests.unit.test_source_obligation_oracle import expected, target


@pytest.mark.parametrize("text,subject,predicate,obj", [
    ("Lumen owns Kappa. Vega holds Sigma.", "Lumen", "owns", "Kappa. Vega holds Sigma"),
    ("Lumen owns Kappa because demand increased.", "Lumen", "owns", "Kappa because demand increased"),
    ("Lumen builds tools in order to provide services.", "Lumen", "builds", "tools in order to provide services"),
    ("Lumen builds tools; therefore Vega provides services.", "Lumen", "builds", "tools; therefore Vega provides services"),
    ("甲公司提供服务，乙公司持有工具。", "甲公司提供服务，乙公司", "持有", "工具"),
    ("甲公司持有工具，乙公司提供服务。", "甲公司", "持有", "工具，乙公司提供服务"),
    ("甲公司持有工具并提供服务。", "甲公司", "持有", "工具并提供服务"),
    ("Lumen owns Kappa and Vega holds Sigma.", "Lumen", "owns", "Kappa and Vega holds Sigma"),
    ("总资产为人民币140万元，比上年末增加人民币12万元。", "总资产为人民币140万元，比上年末", "增加", "人民币12万元"),
    ("主要归因于公司加大研发投入，固定资产比上年末增加人民币9万元。", "主要归因于公司加大研发投入，固定资产比上年末", "增加", "人民币9万元"),
])
@pytest.mark.parametrize("synchronize_tags", [False, True])
def test_opaque_svo_cannot_erase_uninterpreted_assertions_even_with_all_original_text(text, subject, predicate, obj, synchronize_tags):
    authored = expected(target(text))
    graph = compile_requirement_graph(authored)
    origin = authored["targets"][0]["reference"]

    def source(value):
        start = text.index(value)
        return {**origin, "text_span": [start, start + len(value)]}

    # Deliberately authored bad interpretation, independent of reader output.
    fact = {"id": "B:opaque", "kind": "proposition", "subject": subject, "predicate": predicate,
        "attribute": {"owns": "own", "builds": "build", "持有": "持有", "增加": "增加"}[predicate],
        "object": obj, "value": obj, "source": {**origin, "text_span": [0, len(text)]},
        "subject_source": source(subject), "predicate_source": source(predicate), "object_source": source(obj),
        "value_source": source(obj), "qualifiers": {}, "scope": [], "logic": {"kind": "proposition"}}
    if synchronize_tags:
        fact.update(kind="fact", role="metric", rule_id="printed_cjk_measurement_clause")
        fact["logic"]["kind"] = "quantity_assertion"
        graph["required_matcher_features"] = []
    graph["nodes"] = [node for node in graph["nodes"] if node["id"] in graph["projections"]["T"]] + [fact]
    graph["projections"]["B"] = [fact["id"]]
    graph["relations"] = [{"id": "L:opaque", "type": "field_binding", "fact_id": fact["id"],
        "left": {"subject": subject, "attribute": fact["attribute"]},
        "right": {"subject": subject, "attribute": fact["attribute"], "scope": []}, "source": deepcopy(fact["source"]),
        "binding_evidence": {"statement_source": deepcopy(fact["source"]), **{
            key: deepcopy(fact[key]) for key in ("subject_source", "predicate_source", "object_source")}}}]
    graph["logic"], graph["operand_relations"], graph["unresolved"] = [], [], []
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert not coverage["semantic_complete"]
    pending = [row for row in coverage["dispositions"] if row["status"] == "pending"]
    assert any("B" in row["layers"] for row in pending)
    assert any("L" in row["layers"] for row in pending)
    assert any(row.get("role_conflicts") for row in pending)


@pytest.mark.parametrize("mutation", ["delete_second", "span_only", "borrow_subject", "borrow_relation"])
def test_independent_sentence_ownership_survives_synchronized_derived_changes(mutation):
    graph = compile_requirement_graph(expected(target("Lumen owns Kappa. Lumen owns Sigma.")))
    first, second = [node for node in graph["nodes"] if node["id"] in graph["projections"]["B"]]
    if mutation == "delete_second":
        graph["nodes"].remove(second)
        graph["projections"]["B"].remove(second["id"])
    elif mutation == "span_only":
        second["predicate_source"] = deepcopy(first["predicate_source"])
    elif mutation == "borrow_subject":
        second["subject_source"] = deepcopy(first["subject_source"])
    else:
        graph["relations"] = [edge for edge in graph["relations"] if edge.get("fact_id") != second["id"]]
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert not coverage["semantic_complete"]


@pytest.mark.parametrize("operator", ["because", "in order to", "if", "unless"])
def test_nonassertive_operands_cannot_fall_back_to_opaque_asserted_objects(operator):
    graph = compile_requirement_graph(expected(target(f"Lumen builds tools {operator} Vega provides services.")))
    # Supported AST or explicit pending; never a single all-text SVO fact.
    facts = [node for node in graph["nodes"] if node["id"] in graph["projections"]["B"]]
    assert not any(operator in fact.get("object", "") for fact in facts)
    assert graph["unresolved"] or any(node.get("kind") != "proposition" for node in graph["logic"])
