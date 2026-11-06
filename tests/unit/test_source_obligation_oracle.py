"""Independent semantic oracles and injected omissions over invented sources.

The assertions below spell out the authored propositions and scopes. Production
reader output supplies only the object under test, never the oracle answer. The
mutations preserve source words while synchronizing the derived indexes that
previously made omission look like a complete interpretation.
"""

import json
from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph

PATH = "<independent-source-obligation-oracle>"
POLICY = "the board shall not pay 17 credits unless approved by 4 directors."


def target(text, line=1, *, kind="text", parents=(), children=False, list_span=None):
    return {"id": f"printed:{line}", "kind": kind, "text": text, "raw_text": text, "raw": text,
        "reference": {"path": PATH, "lines": [line, line]}, "cells": [], "parents": list(parents),
        "has_children": children, "context": [], "selected_heading_context": [],
        "outside_selection_context": [], "pages": [1], "list_span": list_span, "heading_level": None}


def expected(*targets):
    return {"sample_id": "independent-source-obligation-oracle", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": list(targets),
        "scope": [{"lines": [1, max(t["reference"]["lines"][1] for t in targets)], "pages": [1],
                   "declared_source_pages": [1], "outside_source_pages": []}]}


def facts(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return [nodes[ident] for ident in graph["projections"]["B"]]


@pytest.mark.parametrize("opening,closing", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』")])
def test_each_admitted_quote_delimiter_keeps_internal_and_inside_one_nominal(opening, closing):
    text = f"Lumen owns {opening}Kappa and Sigma{closing}."
    graph = compile_requirement_graph(expected(target(text)))
    assert graph["semantic_complete"] is True
    assert [(item["subject"], item["attribute"], item["value"]) for item in facts(graph)] == [
        ("Lumen", "own", opening + "Kappa and Sigma" + closing)]
    assert not any(item["kind"] == "qualifier" and item["text"] == "and"
                   for item in graph["source_obligation_inventory"]["obligations"])
    validate_requirement_graph(graph)


def test_source_inventory_is_independent_of_interpreter_graph_and_dispositions(monkeypatch):
    from moparse_eval import reference_compiler, requirement_graph
    from moparse_eval.source_obligations import build_source_obligation_inventory

    authored = expected(target(POLICY))
    before = deepcopy(authored)

    def forbidden(*_args, **_kwargs):
        pytest.fail("the independent source inventory called the semantic interpreter or graph compiler")

    monkeypatch.setattr(reference_compiler, "compile_reference_semantics", forbidden)
    monkeypatch.setattr(reference_compiler, "interpret_reference_sources", forbidden)
    monkeypatch.setattr(requirement_graph, "compile_requirement_graph", forbidden)
    inventory = build_source_obligation_inventory(authored)
    assert authored == before
    assert {"text", "proposition", "relation", "qualifier"} <= {row["kind"] for row in inventory["obligations"]}
    snapshot = json.dumps(inventory, sort_keys=True, ensure_ascii=False)
    authored["targets"][0]["text"] = "mutated after the source inventory was built"
    authored["targets"][0]["raw_text"] = "mutated after the source inventory was built"
    authored["targets"][0]["reference"]["path"] = "<forged-after-build>"
    assert json.dumps(inventory, sort_keys=True, ensure_ascii=False) == snapshot


@pytest.mark.parametrize("role", ["identity", "metric"])
def test_independent_audit_oracle_does_not_trust_a_forged_scalar_role_for_an_opaque_proposition(role):
    from moparse_eval.source_obligations import (
        audit_source_obligations,
        build_source_obligation_inventory,
    )

    text = "Lumen appoints Kappa."
    authored = expected(target(text))
    graph = compile_requirement_graph(authored)
    # Hand-authored deliberately invalid node: no field label, field syntax,
    # predicate or relation in the source proves the claimed scalar role.
    graph["nodes"].append({"id": "B:opaque", "kind": "fact", "subject": "", "attribute": "Name",
        "value": text, "role": role, "qualifiers": {}, "scope": [], "logic": {"kind": "field"},
        "source": {"path": PATH, "lines": [1, 1]},
        "value_source": {"path": PATH, "lines": [1, 1], "text_span": [0, len(text)]}})
    graph["projections"]["B"] = ["B:opaque"]
    graph["unresolved"] = []
    coverage = audit_source_obligations(build_source_obligation_inventory(authored), graph)
    assert coverage["semantic_complete"] is False
    assert any(row["status"] == "pending" and {"B", "L"} & set(row["layers"])
               for row in coverage["dispositions"])


def test_independent_audit_oracle_cannot_borrow_a_relation_from_the_same_actor_on_the_same_line():
    from moparse_eval.source_obligations import (
        audit_source_obligations,
        build_source_obligation_inventory,
    )

    authored = expected(target("Lumen owns Kappa. Lumen owns Sigma."))
    graph = compile_requirement_graph(authored)
    assert [(fact["subject"], fact["attribute"], fact["value"]) for fact in facts(graph)] == [
        ("Lumen", "own", "Kappa"), ("Lumen", "own", "Sigma")]
    # The second sentence's complete B roles remain. Only its L bindings are
    # removed; equal actor/action and physical line cannot authorize reuse.
    graph["relations"] = [edge for edge in graph["relations"]
                          if edge.get("source", {}).get("text_span", [0, 0])[0] == 0]
    assert graph["relations"]
    coverage = audit_source_obligations(build_source_obligation_inventory(authored), graph)
    assert coverage["semantic_complete"] is False
    assert any(row["status"] == "pending" and "L" in row["layers"] for row in coverage["dispositions"])


def test_synchronized_audit_oracle_fact_id_cannot_waive_actual_statement_and_endpoint_ownership():
    from moparse_eval.source_obligations import audit_source_obligations

    graph = compile_requirement_graph(expected(target("Lumen owns Kappa. Lumen owns Sigma.")))
    [first, second] = facts(graph)
    keep = next(edge for edge in graph["relations"] if edge["type"] == "field_binding"
                and edge["source"]["text_span"][0] == 0)
    remove_derived(graph, relations=[edge["id"] for edge in graph["relations"] if edge["id"] != keep["id"]])
    keep["fact_id"] = second["id"]
    second["logic"]["kind"] = "opaque"
    # Even the recomputed derived coverage must fail closed against the
    # untouched canonical selection inventory. An identifier proves no scope.
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False
    assert first["subject"] == second["subject"] and first["attribute"] == second["attribute"]


def test_synchronized_audit_oracle_field_binding_cannot_replace_removed_operator_scope_relations():
    from moparse_eval.source_obligations import audit_source_obligations

    graph = compile_requirement_graph(expected(target("Board may not review Report.")))
    [fact] = facts(graph)
    assert fact["qualifiers"] == {"modality": "may", "polarity": "negative"}
    removed = [edge["id"] for edge in graph["relations"] if edge["type"] == "qualifier_scope"]
    assert removed
    remove_derived(graph, relations=removed)
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False


def test_synchronized_audit_oracle_T_cannot_silently_lose_an_original_numeric_sign():
    from moparse_eval.source_obligations import audit_source_obligations

    graph = compile_requirement_graph(expected(target("Revenue:-17")))
    [fact] = facts(graph)
    assert fact["value"] == "-17"
    [literal] = [node for node in graph["nodes"] if node["id"] in graph["projections"]["T"] and node["text"] == "-17"]
    literal["text"] = "17"
    literal["source"]["text_span"] = [9, 11]
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False
    assert any(row["status"] == "pending" and row["layers"] == ["T"]
               for row in graph["source_obligation_coverage"]["dispositions"])


@pytest.mark.parametrize("declaration", [
    {"kind": "explicit_unit_or_period", "text": "Unit: CNY million", "raw": "Unit: CNY million",
     "reference": {"path": "<unselected-unit>", "lines": [40, 40]}},
    {"kind": "mixed_page_selection_declaration", "text": "declared two-page continuation",
     "declared_source_pages": [1, 2], "outside_source_pages": [2]},
])
def test_synchronized_audit_oracle_an_unrelated_period_proof_cannot_resolve_a_scope_or_unit_dependency(declaration):
    from moparse_eval.source_obligations import audit_source_obligations

    item = target("Revenue:2028年17")
    item["outside_selection_context"] = [deepcopy(declaration)]
    graph = compile_requirement_graph(expected(item))
    [fact] = facts(graph)
    assert fact["qualifiers"] == {"period": "2028年"}
    assert fact["qualifier_sources"].keys() == {"period"}
    assert any(issue["reason"] == "input_scope_context" for issue in graph["unresolved"])
    graph["unresolved"] = [issue for issue in graph["unresolved"] if issue["reason"] != "input_scope_context"]
    inventory = graph["source_obligation_inventory"]
    graph["source_obligation_coverage"] = audit_source_obligations(inventory, graph)
    [obligation] = [row for row in inventory["obligations"] if row["kind"] == "authorization_dependency"]
    [disposition] = [row for row in graph["source_obligation_coverage"]["dispositions"]
                     if row["obligation_id"] == obligation["id"]]
    assert disposition["status"] == "pending"
    assert graph["source_obligation_coverage"]["semantic_complete"] is False


def test_synchronized_audit_oracle_literal_role_reversal_does_not_explain_the_original_active_assertion():
    from moparse_eval.source_obligations import audit_source_obligations

    graph = compile_requirement_graph(expected(target("Lumen owns Kappa.")))
    [fact] = facts(graph)
    original_subject, original_object = fact["subject"], fact["object"]
    subject_source, object_source = deepcopy(fact["subject_source"]), deepcopy(fact["object_source"])
    fact.update(subject=original_object, subject_source=object_source, object=original_subject,
                object_source=subject_source, value=original_subject, value_source=subject_source)
    for edge in graph["relations"]:
        for key in ("left", "right"):
            if edge.get(key, {}).get("subject") == original_subject:
                edge[key]["subject"] = original_object
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False


def test_synchronized_audit_oracle_a_printed_ownership_action_cannot_be_relabelled_as_acquisition():
    from moparse_eval.source_obligations import audit_source_obligations

    graph = compile_requirement_graph(expected(target("Lumen owns Kappa.")))
    [fact] = facts(graph)
    assert (fact["predicate"], fact["attribute"]) == ("owns", "own")
    fact["attribute"] = "acquire"
    fact["logic"]["action"] = "acquire"
    for edge in graph["relations"]:
        for key in ("left", "right"):
            if edge.get(key, {}).get("attribute") == "own":
                edge[key]["attribute"] = "acquire"
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False


def test_synchronized_audit_oracle_two_real_year_literals_cannot_be_swapped_between_their_scalars():
    from moparse_eval.source_obligations import audit_source_obligations

    graph = compile_requirement_graph(expected(target("Revenue:2028年17万元;2027年11万元")))
    first, second = facts(graph)
    assert [(fact["value"], fact["qualifiers"]["period"]) for fact in (first, second)] == [
        ("17", "2028年"), ("11", "2027年")]
    periods = [(fact["qualifiers"]["period"], deepcopy(fact["qualifier_sources"]["period"]))
               for fact in (first, second)]
    replacements = {fact["id"]: replacement for fact, replacement in zip((first, second), reversed(periods), strict=True)}
    for fact in (first, second):
        value, origin = replacements[fact["id"]]
        fact["qualifiers"]["period"] = value
        fact["qualifier_sources"]["period"] = deepcopy(origin)
        fact["source"]["qualifier_sources"]["period"] = deepcopy(origin)
        fact["role_basis"]["period_selector"].update(text=value, source=deepcopy(origin))
    for edge in graph["relations"]:
        if edge.get("fact_id") in replacements:
            value, origin = replacements[edge["fact_id"]]
        else:
            old = edge.get("right", {}).get("qualifiers", {}).get("period")
            if old not in {periods[0][0], periods[1][0]}:
                continue
            value, origin = periods[1] if old == periods[0][0] else periods[0]
        edge.get("right", {}).get("qualifiers", {})["period"] = value
        if edge["type"] == "qualifier_scope" and edge["left"].get("type") == "period":
            edge["left"]["text"], edge["source"] = value, deepcopy(origin)
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False


def test_synchronized_audit_oracle_two_real_inline_units_cannot_be_swapped_between_their_quantities():
    from moparse_eval.source_obligations import audit_source_obligations

    graph = compile_requirement_graph(expected(target("Revenue:2028年17万元;2027年11亿元")))
    first, second = facts(graph)
    assert [(fact["value"], fact["qualifiers"]["unit"]) for fact in (first, second)] == [("17", "万元"), ("11", "亿元")]
    units = [(fact["qualifiers"]["unit"], deepcopy(fact["qualifier_sources"]["unit"])) for fact in (first, second)]
    replacements = {fact["id"]: replacement for fact, replacement in zip((first, second), reversed(units), strict=True)}
    for fact in (first, second):
        value, origin = replacements[fact["id"]]
        fact["qualifiers"]["unit"] = value
        fact["qualifier_sources"]["unit"] = deepcopy(origin)
        fact["source"]["qualifier_sources"]["unit"] = deepcopy(origin)
    for edge in graph["relations"]:
        if edge.get("fact_id") in replacements:
            value, origin = replacements[edge["fact_id"]]
        else:
            old = edge.get("right", {}).get("qualifiers", {}).get("unit")
            if old not in {units[0][0], units[1][0]}:
                continue
            value, origin = units[1] if old == units[0][0] else units[0]
        edge.get("right", {}).get("qualifiers", {})["unit"] = value
        if edge["type"] == "qualifier_scope" and edge["left"].get("type") == "unit":
            edge["left"]["text"], edge["source"] = value, deepcopy(origin)
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False


def test_synchronized_audit_oracle_an_OR_group_cannot_hide_an_omitted_operand():
    from moparse_eval.source_obligations import audit_source_obligations

    graph = compile_requirement_graph(expected(target("Board owns Kappa or Sigma.")))
    [group] = facts(graph)
    assert group["role"] == "logical_group"
    [omitted] = [node for node in graph["nodes"] if node.get("kind") == "semantic_operand" and node["value"] == "Sigma"]
    remove_derived(graph, nodes=[omitted["id"]])

    def omit_leaf(value):
        if isinstance(value, dict):
            for name, child in list(value.items()):
                if name == "children" and isinstance(child, list):
                    value[name] = [leaf for leaf in child if not isinstance(leaf, dict) or leaf.get("object") != "Sigma"]
                omit_leaf(value[name])
        elif isinstance(value, list):
            for child in value:
                omit_leaf(child)

    for tree in [graph["logic"], graph["operand_relations"], group.get("logic", {})]:
        omit_leaf(tree)
    # The group still echoes the whole printed sentence; that surface string
    # and an OR token cannot substitute for the absent Sigma operand.
    assert "Sigma" in group["value"]
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False


def test_synchronized_audit_oracle_revenue_and_profit_cannot_exchange_real_scalar_tokens():
    from moparse_eval.source_obligations import audit_source_obligations

    graph = compile_requirement_graph(expected(target("Revenue:17; Profit:5")))
    first, second = facts(graph)
    assert [(fact["attribute"], fact["value"]) for fact in (first, second)] == [("Revenue", "17"), ("Profit", "5")]
    values = [(fact["value"], deepcopy(fact["value_source"])) for fact in (first, second)]
    for fact, (value, origin) in zip((first, second), reversed(values), strict=True):
        fact["value"], fact["raw_value"] = value, value
        fact["value_source"] = deepcopy(origin)
        fact["source"] = deepcopy(origin)
        for edge in graph["relations"]:
            if edge.get("fact_id") == fact["id"] or edge.get("right", {}).get("attribute") == fact["attribute"]:
                edge["source"] = deepcopy(origin)
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False


@pytest.mark.parametrize("rows", [
    [["Name", "Revenue", "Profit"], ["Delta", "17", "5"]],
    [["Attribute", "Value"], ["Name", "Delta"], ["Revenue", "17"], ["Profit", "5"]],
], ids=["horizontal-record", "transposed-properties"])
def test_synchronized_audit_oracle_table_cell_text_and_B_facts_cannot_replace_a_missing_field_binding(rows):
    from moparse_eval.source_obligations import audit_source_obligations

    table = target("", kind="table")
    table["cells"] = [{"id": f"cell:{r}:{c}", "native_path": f"cell:{r}:{c}", "row": r, "col": c,
        "row_span": 1, "col_span": 1, "text": text, "is_column_header": r == 0,
        "native_syntax": {"format": "gfm", "row": r, "column": c}}
        for r, row in enumerate(rows) for c, text in enumerate(row)]
    table["raw"] = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    graph = compile_requirement_graph(expected(table))
    assert [(fact["attribute"], fact["value"]) for fact in facts(graph)] == [("Name", "Delta"), ("Revenue", "17"), ("Profit", "5")]
    assert graph["source_obligation_coverage"]["semantic_complete"] is True
    original_B = deepcopy(facts(graph))
    original_T = deepcopy([node for node in graph["nodes"] if node["id"] in graph["projections"]["T"]])
    removed = [edge["id"] for edge in graph["relations"]
               if edge["type"] == "field_binding" and edge.get("right", {}).get("attribute") == "Profit"]
    assert removed
    remove_derived(graph, relations=removed)
    graph["source_obligation_coverage"] = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert graph["source_obligation_coverage"]["semantic_complete"] is False
    assert facts(graph) == original_B
    assert [node for node in graph["nodes"] if node["id"] in graph["projections"]["T"]] == original_T


def remove_derived(graph, *, nodes=(), relations=()):
    """Synchronize the old transport bookkeeping, deliberately not the source inventory."""
    removed = set(nodes) | set(relations)
    graph["nodes"] = [node for node in graph["nodes"] if node["id"] not in removed]
    graph["relations"] = [edge for edge in graph["relations"] if edge["id"] not in removed]
    for layer in ("T", "L", "B"):
        graph["projections"][layer] = [ident for ident in graph["projections"][layer] if ident not in removed]
    for disposition in graph["dispositions"]:
        for row in disposition["layers"].values():
            row["requirements"] = [ident for ident in row["requirements"] if ident not in removed]
            if row["status"] == "interpreted" and not row["requirements"]:
                row.update(status="not_applicable", rule_id="invented_opaque_exemption",
                           reason="A synchronized derived claim cannot establish non-applicability.")


def assert_refused(graph):
    with pytest.raises(ValueError, match="source|obligation|semantic|relation|coverage|logic|inventory"):
        validate_requirement_graph(graph)


@pytest.mark.parametrize("text,wanted", [
    ("Lumen owns Kappa and Sigma.", [("Lumen", "own", "Kappa"), ("Lumen", "own", "Sigma")]),
    ("Lumen owns Kappa. Vega acquires Sigma.", [("Lumen", "own", "Kappa"), ("Vega", "acquire", "Sigma")]),
])
def test_independent_atomic_oracle_requires_every_printed_member_or_clause(text, wanted):
    authored = expected(target(text))
    before = deepcopy(authored)
    graph = compile_requirement_graph(authored)
    assert [(fact["subject"], fact["attribute"], fact["value"]) for fact in facts(graph)] == wanted
    assert len([edge for edge in graph["relations"] if edge["type"] == "field_binding"]) == len(wanted)
    assert graph["semantic_complete"] is True
    validate_requirement_graph(graph, expected=authored)
    assert authored == before


def test_independent_conditional_or_oracle_requires_condition_and_two_alternatives():
    text = "If Delta is ready, Board may review Report or Budget."
    graph = compile_requirement_graph(expected(target(text)))
    [group] = facts(graph)
    assert (group["subject"], group["attribute"], group["role"]) == ("Board", "logical_alternative", "logical_group")
    assert group["qualifiers"]["conditions"] == [{"operator": "if", "operand": {
        "subject": "Delta", "attribute": "be", "value": "ready", "polarity": "positive", "tense": "present"}}]
    operands = [node for node in graph["nodes"] if node.get("kind") == "semantic_operand"]
    assert sorted((node["subject"], node["attribute"], node["value"]) for node in operands) == [
        ("Board", "review", "Budget"), ("Board", "review", "Report"), ("Delta", "be", "ready")]
    assert {"narrative_condition_scope", "narrative_alternative_scope", "narrative_modality_scope"} <= {
        edge["type"] for edge in graph["relations"]}
    assert graph["semantic_complete"] is True
    validate_requirement_graph(graph)


def test_independent_partial_policy_oracle_keeps_outer_scope_without_claiming_an_unread_inner_agent():
    graph = compile_requirement_graph(expected(target(POLICY)))
    [fact] = facts(graph)
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("the board", "pay", "pay 17 credits")
    assert fact["qualifiers"] == {"modality": "shall", "polarity": "negative", "condition": "approved by 4 directors",
                                  "condition_operator": "unless"}
    assert graph["semantic_complete"] is False
    assert [(issue["text"], issue.get("interpretation_rule")) for issue in graph["unresolved"]] == [
        ("by", "printed_preposition_requires_source_bound_attachment")]
    validate_requirement_graph(graph)


@pytest.mark.parametrize("kind,qualifier", [("modality", "modality"), ("negation", "polarity")])
def test_independent_operator_scope_oracle_requires_a_relation_or_explicit_pending(kind, qualifier):
    # Keeping "may" and "not" as words and B metadata does not by itself
    # establish which action each operator constrains in the L layer.
    graph = compile_requirement_graph(expected(target("Board may not review Report.")))
    [fact] = facts(graph)
    assert fact["qualifiers"] == {"modality": "may", "polarity": "negative"}
    own = [edge for edge in graph["relations"] if kind in edge["type"] or
           edge["type"] == "qualifier_scope" and edge.get("left", {}).get("type") == qualifier]
    if own:
        assert all(edge.get("source") or edge.get("binding_evidence") for edge in own)
    else:
        assert graph["semantic_complete"] is False
        assert any("L" in issue["layers"] for issue in graph["unresolved"])
    validate_requirement_graph(graph)


@pytest.mark.parametrize("text", [
    "Lumen appoints Kappa.",
    "If Delta might become ready, Lumen glorps Kappa.",
    "Lumen appoints Kappa and waives any resulting condition.",
])
def test_independent_unknown_syntax_oracle_never_becomes_text_only_business_exemption(text):
    graph = compile_requirement_graph(expected(target(text)))
    assert graph["semantic_complete"] is False
    assert any({"B", "L"} <= set(issue["layers"]) for issue in graph["unresolved"])
    assert text in "".join(node["text"] for node in graph["nodes"] if node["id"] in graph["projections"]["T"])
    validate_requirement_graph(graph)


@pytest.mark.parametrize("text", ["Lumen owns Kappa and Sigma.", "Lumen owns Kappa. Vega acquires Sigma."])
def test_mutation_source_preserved_but_one_business_member_removed_is_rejected(text):
    graph = compile_requirement_graph(expected(target(text)))
    original_sources = deepcopy(graph["sources"])
    [omitted] = [fact for fact in facts(graph) if fact["value"] == "Sigma"]
    removed_edges = [edge["id"] for edge in graph["relations"] if edge.get("right", {}).get("value") == "Sigma"]
    remove_derived(graph, nodes=[omitted["id"]], relations=removed_edges)
    assert graph["sources"] == original_sources
    assert_refused(graph)


@pytest.mark.parametrize("omitted", ["condition", "negation", "modality"])
def test_mutation_source_preserved_but_a_protected_qualifier_removed_is_rejected(omitted):
    graph = compile_requirement_graph(expected(target(POLICY)))
    [fact] = facts(graph)
    if omitted == "condition":
        for key in ("condition", "condition_operator"):
            fact["qualifiers"].pop(key)
            fact["qualifier_sources"].pop(key)
        fact["logic"]["conditions"] = []
    elif omitted == "negation":
        fact["qualifiers"]["polarity"] = "positive"
        fact["qualifier_sources"].pop("polarity")
    else:
        fact["qualifiers"].pop("modality")
        fact["qualifier_sources"].pop("modality")
    # The entire original policy remains in T. No removed relation or feature
    # is left as an easy bookkeeping inconsistency for the validator to find.
    remove_derived(graph, relations=graph["projections"]["L"][:])
    graph["required_matcher_features"] = []
    assert POLICY in "".join(node["text"] for node in graph["nodes"] if node["id"] in graph["projections"]["T"])
    assert_refused(graph)


@pytest.mark.parametrize("kind", ["opaque", "modal_assertion", "logical_group"])
def test_mutation_synchronized_kind_feature_and_relation_downgrade_cannot_bypass_source_binding(kind):
    graph = compile_requirement_graph(expected(target("Lumen owns Kappa.")))
    [fact] = facts(graph)
    fact["logic"]["kind"] = kind
    remove_derived(graph, relations=graph["projections"]["L"][:])
    graph["required_matcher_features"] = []
    assert_refused(graph)


def test_mutation_opaque_business_and_relation_exemption_cannot_be_created_by_disposition_edit():
    graph = compile_requirement_graph(expected(target("Lumen owns Kappa.")))
    remove_derived(graph, nodes=graph["projections"]["B"][:], relations=graph["projections"]["L"][:])
    graph["logic"] = []
    graph["operand_relations"] = []
    graph["required_matcher_features"] = []
    assert_refused(graph)


def test_mutation_synchronized_derived_source_forgery_cannot_replace_the_canonical_origin():
    graph = compile_requirement_graph(expected(target("Lumen owns Kappa.")))

    def forge(value):
        if isinstance(value, dict):
            if value.get("path") == PATH:
                value["path"] = "<forged-but-internally-consistent-source>"
            for item in value.values():
                forge(item)
        elif isinstance(value, list):
            for item in value:
                forge(item)

    for name, value in graph.items():
        if name not in {"source_obligation_inventory", "source_obligation_coverage"}:
            forge(value)
    assert_refused(graph)


def test_mutation_real_list_member_cannot_disappear_behind_its_complete_introduction():
    intro = "2028年，Lumen的合作进展包括："
    authored = expected(target(intro, 1, kind="item", children=True, list_span=[1, 3]),
        target("批准Kappa。", 2, kind="item", parents=[intro], list_span=[1, 3]),
        target("披露Sigma。", 3, kind="item", parents=[intro], list_span=[1, 3]))
    graph = compile_requirement_graph(authored)
    assert [(fact["subject"], fact["attribute"], fact["value"], fact["qualifiers"]["period"])
            for fact in facts(graph)] == [("Lumen", "批准", "Kappa", "2028年"), ("Lumen", "披露", "Sigma", "2028年")]
    [omitted] = [fact for fact in facts(graph) if fact["value"] == "Sigma"]
    removed_edges = [edge["id"] for edge in graph["relations"] if edge.get("fact_id") == omitted["id"]
                     or edge.get("right", {}).get("value") == "Sigma"]
    remove_derived(graph, nodes=[omitted["id"]], relations=removed_edges)
    assert any(source["text"] == "披露Sigma。" for source in graph["sources"])
    assert_refused(graph)


def test_independent_unknown_list_member_cannot_borrow_its_siblings_business_disposition():
    intro = "2028年，Lumen的合作进展包括："
    unknown = "设置虚构且无法解释的新型安排。"
    graph = compile_requirement_graph(expected(
        target(intro, 1, kind="item", children=True, list_span=[1, 3]),
        target("批准Kappa。", 2, kind="item", parents=[intro], list_span=[1, 3]),
        target(unknown, 3, kind="item", parents=[intro], list_span=[1, 3])))
    assert graph["semantic_complete"] is False
    assert any(issue["source"].get("lines") == [3, 3] and "B" in issue["layers"] for issue in graph["unresolved"])
    assert any(source["text"] == unknown for source in graph["sources"])
    validate_requirement_graph(graph)


@pytest.mark.parametrize("text", ["Lumen owns Kappa and Sigma.", "Lumen owns Kappa. Vega acquires Sigma."])
def test_injected_reader_omission_cannot_claim_semantic_completeness(monkeypatch, text):
    from moparse_eval import reference_compiler

    authored = expected(target(text))
    real_interpreter = reference_compiler.compile_reference_semantics

    def defective_interpreter(source):
        projected = real_interpreter(source)
        [omitted] = [fact for fact in projected["business"] if fact["value"] == "Sigma"]
        projected["business"] = [fact for fact in projected["business"] if fact["id"] != omitted["id"]]
        projected["relations"] = [edge for edge in projected["relations"] if edge.get("right", {}).get("value") != "Sigma"]
        return projected

    monkeypatch.setattr(reference_compiler, "compile_reference_semantics", defective_interpreter)
    try:
        graph = compile_requirement_graph(authored)
    except ValueError as error:
        assert any(word in str(error).lower() for word in ("source", "obligation", "semantic", "coverage"))
    else:
        assert graph["semantic_complete"] is False, "independent source obligations must expose the omitted clause"
        assert any({"B", "L"} & set(issue["layers"]) for issue in graph["unresolved"])


@pytest.mark.parametrize("qualifier", ["condition", "polarity", "modality"])
def test_injected_reader_qualifier_omission_cannot_claim_semantic_completeness(monkeypatch, qualifier):
    from moparse_eval import reference_compiler

    real_interpreter = reference_compiler.compile_reference_semantics

    def defective_interpreter(source):
        projected = real_interpreter(source)
        [fact] = projected["business"]
        fact["qualifiers"].pop(qualifier)
        fact["qualifier_sources"].pop(qualifier)
        if qualifier == "condition":
            fact["qualifiers"].pop("condition_operator")
            fact["qualifier_sources"].pop("condition_operator")
            fact["logic"]["conditions"] = []
        projected["relations"] = []
        return projected

    monkeypatch.setattr(reference_compiler, "compile_reference_semantics", defective_interpreter)
    try:
        graph = compile_requirement_graph(expected(target(POLICY)))
    except ValueError as error:
        assert any(word in str(error).lower() for word in ("source", "obligation", "semantic", "coverage"))
    else:
        assert graph["semantic_complete"] is False, "retained words cannot explain an omitted qualifier"
