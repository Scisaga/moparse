"""Independent statement and endpoint identities across reader boundaries."""

from copy import deepcopy

from moparse_eval.proposition_requirements import read_propositions
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import _Graph, _read_narrative, compile_markdown

SOURCE = {"path": "<invented-semantic-transport>", "lines": [9, 9]}


def test_language_dispatch_keeps_both_independent_statements_and_exact_sources():
    text = "Lumen owns Kappa. 星港公司提供物流服务。"
    original = {**SOURCE, "text_span": [20, 20 + len(text)]}
    result = _read_narrative(text, original, scope=["业务"])
    assert result["complete"]
    assert [(fact["subject"], fact["attribute"], fact["value"]) for fact in result["facts"]] == [
        ("Lumen", "own", "Kappa"), ("星港公司", "提供", "物流服务")]
    assert len({fact["id"] for fact in result["facts"]}) == 2
    for fact in result["facts"]:
        for role in ("subject", "predicate", "object"):
            a, b = fact[role + "_source"]["text_span"]
            assert text[a - 20:b - 20] == fact[role]
    assert result["text_atoms"] == [{"text": text, "role": "literal", "source": original}]


def test_partial_neighbor_cannot_erase_the_other_language_or_its_pending_scope():
    text = "Lumen owns Kappa. 业务环境持续演化。星港公司提供物流服务。"
    result = _read_narrative(text, SOURCE)
    assert not result["complete"]
    assert [(fact["subject"], fact["value"]) for fact in result["facts"]] == [
        ("Lumen", "Kappa"), ("星港公司", "物流服务")]
    assert len(result["unresolved"]) == 1
    [pending] = result["unresolved"]
    assert pending["text"] == "业务环境持续演化。"
    assert pending["source"]["text_span"] == [18, 27]
    assert pending["layers"] == ["B", "L"]


def test_shared_subject_predicate_has_distinct_object_evidence_and_global_fact_ids():
    text = "Lumen owns Kappa and Sigma."
    result = read_propositions(text, SOURCE)
    original = deepcopy(result)
    reader = _Graph("invented")
    reader.ingest(result, logical_prose=True)
    assert result == original
    fields = [edge for edge in reader.data["relations"] if edge["type"] == "field_binding"]
    assert [edge["fact_id"] for edge in fields] == ["B:0", "B:1"]
    assert [edge["binding_evidence"]["object_source"]["text_span"] for edge in fields] == [[11, 16], [21, 26]]
    assert all(edge["binding_evidence"]["subject_source"]["text_span"] == [0, 5] for edge in fields)
    assert all(edge["binding_evidence"]["predicate_source"]["text_span"] == [6, 10] for edge in fields)


def test_field_owner_is_preserved_on_logic_and_projection_without_duplicate_facts():
    text = "Policy: If Gate is open, Board may release Cargo."
    expected = {"sample_id": "invented", "targets": [
        {"id": "one", "kind": "paragraph", "text": text, "reference": SOURCE}]}
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    projected = evaluation_projection(graph)
    assert len(projected["business"]) == 1
    [fact] = projected["business"]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Board", "release", "Cargo")
    assert fact["printed_label"] == "Policy"
    assert fact["scope"] == ["Policy"]
    assert projected["logical_statements"] == graph["logic"]
    assert projected["semantic_operand_relations"] == graph["operand_relations"]
    assert projected["required_matcher_features"] == graph["required_matcher_features"]


def test_complete_later_reader_discharges_only_the_clause_it_actually_explained():
    text = "Lumen owns Kappa. Strange arrangements glorp. Board may pay Fee."
    graph = compile_markdown(text)
    assert [(fact["subject"], fact["attribute"]) for fact in graph["business"]] == [
        ("Lumen", "own"), ("Board", "pay")]
    for key in ("blockers", "pending_requirements"):
        assert not any(issue.get("text") == "Lumen owns Kappa" for issue in graph[key])
        assert any("Strange arrangements glorp" in issue.get("text", "") for issue in graph[key])
    assert graph["blockers"]


def test_an_additive_modifier_cannot_be_published_as_the_business_predicate():
    text = "Lumen will also enhance the platform. Vega owns Kappa."
    graph = compile_markdown(text)
    assert not any(fact["attribute"] == "also" for fact in graph["business"])
    assert any((fact["subject"], fact["attribute"], fact["value"]) == ("Vega", "own", "Kappa")
               for fact in graph["business"])
    assert any("also enhance" in issue.get("text", "") for issue in graph["blockers"])
