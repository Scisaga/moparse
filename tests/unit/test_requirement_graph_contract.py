"""Hand-authored expected requirement graphs, without corpus or model access.

The target sets, roles, edges and source literals below are independent oracles.
The syntax fixtures are constructed here; no requirement compiler builds them.
Failure-closed contracts are named separately from complete semantic contracts.
"""

import json
import xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    validate_requirement_graph,
    write_requirement_graph,
)

PATH = "<invented-requirements>"


def _target(text, *, line=1, kind="text", raw=None, cells=None, parents=(), children=False,
            context=(), heading_level=None, end_line=None):
    return {
        "id": f"expected:L{line}:{kind}", "kind": kind, "text": text, "raw_text": text,
        "raw": text if raw is None else raw, "reference": {"path": PATH, "lines": [line, end_line or line]},
        "pages": [1], "cells": cells or [], "parents": list(parents), "has_children": children,
        "context": list(context), "selected_heading_context": [], "outside_selection_context": [],
        "heading_level": heading_level, "list_span": [1, 9] if kind == "item" else None,
    }


def _expected(*targets):
    return {
        "sample_id": "invented-requirements", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": list(targets),
        "scope": [{"lines": [1, max(t["reference"]["lines"][1] for t in targets)], "pages": [1],
                   "declared_source_pages": [1], "outside_source_pages": []}],
    }


def _cells(rows):
    return [{"id": f"printed/r{r}/c{c}", "native_path": f"printed/r{r}/c{c}",
             "row": r, "col": c, "row_span": 1, "col_span": 1, "text": text,
             "is_column_header": r == 0, "native_syntax": {"format": "gfm", "row": r, "column": c}}
            for r, row in enumerate(rows) for c, text in enumerate(row)]


REPRESENTATIONS = {
    "paragraph": _expected(_target("Name: Delta; Revenue: 17; Profit: 5")),
    "flat-list": _expected(_target("Name: Delta", kind="item", line=1),
                           _target("Revenue: 17", kind="item", line=2),
                           _target("Profit: 5", kind="item", line=3)),
    "nested-list": _expected(_target("Name: Delta", kind="item", line=1, children=True),
                             _target("Revenue: 17", kind="item", line=2, parents=["Name: Delta"]),
                             _target("Profit: 5", kind="item", line=3, parents=["Name: Delta"])),
    "horizontal": _expected(_target("", kind="table", end_line=3,
        raw="| Name | Revenue | Profit |\n|---|---|---|\n| Delta | 17 | 5 |",
        cells=_cells([["Name", "Revenue", "Profit"], ["Delta", "17", "5"]]))),
    "transposed": _expected(_target("", kind="table", end_line=5,
        raw="| Attribute | Value |\n|---|---|\n| Name | Delta |\n| Revenue | 17 |\n| Profit | 5 |",
        cells=_cells([["Attribute", "Value"], ["Name", "Delta"], ["Revenue", "17"], ["Profit", "5"]]))),
}


def _projected(graph, layer):
    bank = graph["relations"] if layer == "L" else graph["nodes"]
    by_id = {item["id"]: item for item in bank}
    ids = graph["projections"][layer]
    assert len(ids) == len(set(ids)), f"duplicate {layer} requirements"
    assert all(ident in by_id for ident in ids)
    return [by_id[ident] for ident in ids]


def _business(graph):
    return _projected(graph, "B")


def _assert_three_business_requirements(graph):
    facts = _business(graph)
    assert sorted((f["subject"], f["attribute"], f["value"], f["role"], f["qualifiers"]) for f in facts) == [
        ("", "Name", "Delta", "identity", {}),
        ("Delta", "Profit", "5", "metric", {}),
        ("Delta", "Revenue", "17", "metric", {}),
    ]
    assert len(facts) == 3
    assert not graph["unresolved"]
    return facts


def _span_literal(graph, source):
    assert source.get("path") and len(source.get("text_span", [])) == 2, source
    matching = [entry for entry in graph["sources"]
                if entry["source"].get("path") == source["path"]
                and entry["source"].get("lines") == source.get("lines")]
    assert matching, source
    result = []
    for entry in matching:
        offset = entry["source"].get("text_span", [0, 0])[0]
        a, b = source["text_span"]
        if 0 <= a - offset <= b - offset <= len(entry["text"]):
            result.append(entry["text"][a - offset:b - offset])
    assert result, source
    assert len(set(result)) == 1, result
    return result[0]


@pytest.mark.parametrize("expected", REPRESENTATIONS.values(), ids=REPRESENTATIONS)
def test_complete_contract_record_obligations_roles_and_counts_are_serialization_independent(expected):
    original = deepcopy(expected)
    graph = compile_requirement_graph(expected)
    _assert_three_business_requirements(graph)
    assert len([e for e in _projected(graph, "L") if e["type"] == "field_binding"]) == 3
    text = "".join(node["text"] for node in _projected(graph, "T"))
    for printed in ("Name", "Delta", "Revenue", "17", "Profit", "5"):
        assert text.count(printed) == 1, (printed, text)
    validate_requirement_graph(graph, expected=expected)
    assert expected == original


def test_complete_contract_every_source_has_three_explicit_layer_dispositions():
    graph = compile_requirement_graph(REPRESENTATIONS["paragraph"])
    source_ids = {source["id"] for source in graph["sources"]}
    assert source_ids
    dispositions = graph["dispositions"]
    assert Counter(row["source_id"] for row in dispositions) == Counter({ident: 1 for ident in source_ids})
    for row in dispositions:
        assert set(row["layers"]) == {"T", "L", "B"}
        for layer, disposition in row["layers"].items():
            assert disposition["status"] in {"interpreted", "not_applicable", "unresolved"}
            assert disposition["rule_id"] and disposition["reason"]
            if disposition["status"] == "interpreted":
                assert disposition["requirements"]
                assert set(disposition["requirements"]) <= set(graph["projections"][layer])


def test_complete_contract_numeric_and_attribute_sources_cut_the_original_printed_text():
    graph = compile_requirement_graph(REPRESENTATIONS["paragraph"])
    _assert_three_business_requirements(graph)
    for fact in _business(graph):
        assert _span_literal(graph, fact["value_source"]) == fact["value"]
        assert _span_literal(graph, fact["attribute_source"]) == fact["attribute"]


@pytest.mark.parametrize("statement,subject,predicate,obj", [
    ("Delta owns Kappa.", "Delta", "owns", "Kappa"),
    ("Delta acquires Sigma.", "Delta", "acquires", "Sigma"),
    ("Board approves Dividend.", "Board", "approves", "Dividend"),
])
def test_complete_contract_important_relations_have_actual_subject_predicate_object(statement, subject, predicate, obj):
    graph = compile_requirement_graph(_expected(_target(statement)))
    assert not graph["unresolved"]
    [fact] = _business(graph)
    assert (fact["subject"], fact["predicate"], fact["object"], fact["role"]) == (subject, predicate, obj, "description")
    assert _span_literal(graph, fact["subject_source"]) == subject
    assert _span_literal(graph, fact["predicate_source"]) == predicate
    assert _span_literal(graph, fact["object_source"]) == obj
    assert _projected(graph, "L")


@pytest.mark.parametrize("statement,wanted", [
    ("Board shall review and approve Report.", [("Board", "review", "Report"), ("Board", "approve", "Report")]),
    ("Board shall review Report and Budget.", [("Board", "review", "Report"), ("Board", "review", "Budget")]),
])
def test_complete_contract_explicit_and_preserves_each_action_or_object(statement, wanted):
    graph = compile_requirement_graph(_expected(_target(statement)))
    facts = _business(graph)
    assert len(facts) == 2 and not graph["unresolved"]
    assert [(fact["subject"], fact["predicate"], fact["object"]) for fact in facts] == wanted
    assert all(fact["qualifiers"]["modality"] == "shall" for fact in facts)
    assert len(_projected(graph, "L")) >= 2


POLICY = "the board shall not pay 17 credits unless approved by 4 directors."


def test_partial_contract_preserves_condition_negation_and_obligation_without_claiming_the_inner_agent():
    graph = compile_requirement_graph(_expected(_target(POLICY)))
    [fact] = _business(graph)
    assert (fact["subject"], fact["attribute"], fact["value"], fact["role"]) == (
        "the board", "pay", "pay 17 credits", "description")
    assert fact["qualifiers"] == {"modality": "shall", "polarity": "negative",
                                  "condition": "approved by 4 directors", "condition_operator": "unless"}
    assert _span_literal(graph, fact["qualifier_sources"]["condition"]) == "approved by 4 directors"
    assert _span_literal(graph, fact["qualifier_sources"]["polarity"]) == "not"
    assert len([e for e in _projected(graph, "L") if e["type"] == "condition_scope"]) == 1
    assert graph["semantic_complete"] is False
    assert [(issue["text"], issue.get("interpretation_rule")) for issue in graph["unresolved"]] == [
        ("by", "uninterpreted_postpredicate_scope_requires_its_own_relation")]


def test_partial_contract_keeps_exception_distinct_while_its_inner_comparison_remains_pending():
    text = "the board must report every transfer except transfers below 5 credits."
    graph = compile_requirement_graph(_expected(_target(text)))
    [fact] = _business(graph)
    assert fact["qualifiers"] == {"modality": "must", "polarity": "positive",
                                  "exception": "transfers below 5 credits", "exception_operator": "except"}
    assert "condition" not in fact["qualifiers"]
    assert len([e for e in _projected(graph, "L") if e["type"] == "exception_scope"]) == 1
    assert graph["semantic_complete"] is False
    assert [(issue["text"], issue.get("interpretation_rule")) for issue in graph["unresolved"]] == [
        ("below", "uninterpreted_postpredicate_scope_requires_its_own_relation")]


@pytest.mark.parametrize("text,role,literal,edge_type", [
    ("the board shall not pay 17 credits unless approved.", "condition", "approved", "condition_scope"),
    ("the board must report every transfer except refunds.", "exception", "refunds", "exception_scope"),
])
def test_admitted_atomic_condition_or_exception_still_has_complete_outer_scope(text, role, literal, edge_type):
    reference = _expected(_target(text))
    graph = compile_requirement_graph(reference)
    [fact] = _business(graph)
    assert fact["subject"] == "the board"
    assert fact["qualifiers"][role] == literal
    assert len([edge for edge in _projected(graph, "L") if edge["type"] == edge_type]) == 1
    assert graph["semantic_complete"] is True and not graph["unresolved"]
    validate_requirement_graph(graph, expected=reference)


@pytest.mark.parametrize("statement,operands", [
    ("If A is ready, Board may pay if B is ready.", ["A is ready", "B is ready"]),
    ("If A is ready, Board may pay except B is blocked.", ["A is ready", "B is blocked"]),
])
def test_failure_closed_contract_two_connectors_never_overwrite_the_first(statement, operands):
    graph = compile_requirement_graph(_expected(_target(statement)))
    pending = graph["unresolved"]
    assert pending, "uninterpreted compound scope cannot silently become one simpler assertion"
    [whole] = [item for item in pending if item.get("text") == statement]
    assert {"B", "L"} <= set(whole["layers"])
    assert [part["text"] for part in whole["fragments"]] == operands
    assert all(part["operator"] and part["operator_source"] and part["source"] for part in whole["fragments"])
    assert "".join(node["text"] for node in _projected(graph, "T")) == statement
    assert not _business(graph), "no answer-shrinking partial fact"


SERIES = "營業收入：2027年17萬元；2026年11萬元。"
SERIES_TABLE = _target("", kind="table", end_line=3,
    raw="| 指標 | 2027年（萬元） | 2026年（萬元） |\n|---|---|---|\n| 營業收入 | 17 | 11 |",
    cells=_cells([["指標", "2027年（萬元）", "2026年（萬元）"], ["營業收入", "17", "11"]]))


@pytest.mark.parametrize("expected", [_expected(_target(SERIES)), _expected(SERIES_TABLE)], ids=["series", "year-headers"])
def test_complete_contract_period_series_and_table_headers_have_two_scalar_obligations(expected):
    graph = compile_requirement_graph(expected)
    facts = _business(graph)
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in facts] == [
        ("", "營業收入", "17", "metric"), ("", "營業收入", "11", "metric")]
    assert [f["qualifiers"] for f in facts] == [
        {"period": "2027年", "unit": "萬元"}, {"period": "2026年", "unit": "萬元"}]
    assert len(_projected(graph, "L")) == 6 and not graph["unresolved"]


FULL_DATES = {
    "inline-date-selectors": _expected(_target(
        "Revenue; Year Ended March 31, 2028: 17万元; Year Ended March 31, 2027: 11万元.")),
    "header-date-axis": _expected(_target("", kind="table", end_line=3,
        raw="| Metric | Year Ended March 31, 2028 (万元) | Year Ended March 31, 2027 (万元) |\n"
            "|---|---|---|\n| Revenue | 17 | 11 |",
        cells=_cells([["Metric", "Year Ended March 31, 2028 (万元)", "Year Ended March 31, 2027 (万元)"],
                      ["Revenue", "17", "11"]]))),
}


@pytest.mark.parametrize("expected", FULL_DATES.values(), ids=FULL_DATES)
def test_complete_contract_full_fiscal_dates_keep_the_printed_basis_and_ending_date(expected):
    graph = compile_requirement_graph(expected)
    facts = _business(graph)
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in facts] == [
        ("", "Revenue", "17", "metric"), ("", "Revenue", "11", "metric")]
    assert [f["qualifiers"]["period"] for f in facts] == ["March 31, 2028", "March 31, 2027"]
    assert all(f["qualifiers"]["period_basis"] == "Year Ended" for f in facts)
    assert all(f["qualifiers"]["unit"] == "万元" for f in facts)
    for fact in facts:
        assert fact["qualifier_sources"]["period"]
        assert fact["qualifier_sources"]["period_basis"]
    assert not graph["unresolved"]
    validate_requirement_graph(graph, expected=expected)


def test_complete_contract_toc_repeated_leaf_keeps_parent_page_and_two_requirements():
    expected = _expected(_target("Contents", kind="heading", heading_level=1),
        _target("North", kind="item", line=2, children=True),
        _target("Results: Page 17", kind="item", line=3, parents=["North"]),
        _target("South", kind="item", line=4, children=True),
        _target("Results: Page 29", kind="item", line=5, parents=["South"]))
    graph = compile_requirement_graph(expected)
    facts = _business(graph)
    assert [(f["subject"], f["attribute"], f["value"], f["identity_facets"]) for f in facts] == [
        ("Results", "Page", "17", {"toc_parent": ["North"]}),
        ("Results", "Page", "29", {"toc_parent": ["South"]})]
    assert len(_projected(graph, "L")) == 4 and not graph["unresolved"]


def test_partial_contract_adjacent_sentence_fragments_keep_both_original_sources_and_inner_pending():
    first, second = "the board shall pay ", "17 credits only if approved by 4 directors."
    expected = _expected(_target(first, line=1), _target(second, line=2))
    graph = compile_requirement_graph(expected)
    [fact] = _business(graph)
    assert fact["value"] == "pay 17 credits"
    assert fact["qualifiers"]["condition"] == "approved by 4 directors"
    fragments = fact["source"]["joined_fragments"]
    assert [part["text"] for part in fragments] == [first, second]
    assert [part["source"]["lines"] for part in fragments] == [[1, 1], [2, 2]]
    assert graph["semantic_complete"] is False
    assert [(issue["text"], issue.get("interpretation_rule")) for issue in graph["unresolved"]] == [
        ("by", "uninterpreted_postpredicate_scope_requires_its_own_relation")]


def _delete_requirement(graph, ident):
    """Synchronize all public projections/dispositions, rather than leave a dangling ID."""
    graph["nodes"] = [item for item in graph["nodes"] if item["id"] != ident]
    graph["relations"] = [item for item in graph["relations"] if item["id"] != ident]
    for layer in ("T", "L", "B"):
        graph["projections"][layer] = [old for old in graph["projections"][layer] if old != ident]
    for row in graph["dispositions"]:
        for disposition in row["layers"].values():
            disposition["requirements"] = [old for old in disposition["requirements"] if old != ident]


def test_mutation_deleting_business_target_and_its_projection_cannot_hide_behind_full_text():
    expected = REPRESENTATIONS["paragraph"]
    graph = compile_requirement_graph(expected)
    before = deepcopy(_projected(graph, "T"))
    [profit] = [f for f in _business(graph) if f["attribute"] == "Profit"]
    _delete_requirement(graph, profit["id"])
    assert _projected(graph, "T") == before
    with pytest.raises(ValueError):
        validate_requirement_graph(graph, expected=expected)


def test_mutation_storing_fact_but_removing_its_business_obligation_is_not_complete_coverage():
    expected = REPRESENTATIONS["paragraph"]
    graph = compile_requirement_graph(expected)
    [profit] = [f for f in _business(graph) if f["attribute"] == "Profit"]
    graph["projections"]["B"].remove(profit["id"])
    for row in graph["dispositions"]:
        row["layers"]["B"]["requirements"] = [
            ident for ident in row["layers"]["B"]["requirements"] if ident != profit["id"]]
    assert any(node["id"] == profit["id"] for node in graph["nodes"])
    assert len(_projected(graph, "T")) > 0 and len(_projected(graph, "L")) == 3
    with pytest.raises(ValueError):
        validate_requirement_graph(graph, expected=expected)


def test_mutation_false_not_applicable_cannot_reclassify_known_business_as_only_text():
    expected = REPRESENTATIONS["paragraph"]
    graph = compile_requirement_graph(expected)
    graph["projections"]["B"] = []
    for row in graph["dispositions"]:
        row["layers"]["B"] = {"status": "not_applicable", "requirements": [],
                                "rule_id": "ordinary_non_business_prose", "reason": "Only ordinary prose remains."}
    assert len(_projected(graph, "T")) > 0
    with pytest.raises(ValueError):
        validate_requirement_graph(graph, expected=expected)


def test_mutation_deleting_relation_and_its_projection_is_detected_even_with_all_business_facts():
    expected = REPRESENTATIONS["paragraph"]
    graph = compile_requirement_graph(expected)
    _delete_requirement(graph, _projected(graph, "L")[0]["id"])
    _assert_three_business_requirements(graph)
    with pytest.raises(ValueError):
        validate_requirement_graph(graph, expected=expected)


def test_mutation_deleting_condition_and_its_scope_edge_does_not_preserve_complete_requirement():
    expected = _expected(_target(POLICY))
    graph = compile_requirement_graph(expected)
    [fact] = _business(graph)
    del fact["qualifiers"]["condition"]
    del fact["qualifiers"]["condition_operator"]
    fact.get("qualifier_sources", {}).pop("condition", None)
    for edge in list(_projected(graph, "L")):
        if edge["type"] == "condition_scope":
            _delete_requirement(graph, edge["id"])
    assert "4 directors" in "".join(node["text"] for node in _projected(graph, "T"))
    with pytest.raises(ValueError):
        validate_requirement_graph(graph, expected=expected)


@pytest.mark.parametrize("missing", ["rule_id", "reason"])
def test_mutation_not_applicable_requires_an_explicit_rule_and_reason(missing):
    expected = _expected(_target("A quiet afternoon."))
    graph = compile_requirement_graph(expected)
    [disposition] = graph["dispositions"]
    disposition["layers"]["B"] = {"status": "not_applicable", "requirements": [],
                                      "rule_id": "ordinary_non_business_prose", "reason": "No declared important role."}
    del disposition["layers"]["B"][missing]
    with pytest.raises(ValueError):
        validate_requirement_graph(graph, expected=expected)


@pytest.mark.parametrize("mutation", ["path", "span"])
def test_mutation_business_literal_source_is_checked_against_independent_expected(mutation):
    expected = REPRESENTATIONS["paragraph"]
    graph = compile_requirement_graph(expected)
    [fact] = [f for f in _business(graph) if f["attribute"] == "Revenue"]
    if mutation == "path":
        fact["value_source"]["path"] = "<forged-other-source>"
    else:
        fact["value_source"]["text_span"] = [0, 2]
    with pytest.raises(ValueError):
        validate_requirement_graph(graph)
    with pytest.raises(ValueError):
        validate_requirement_graph(graph, expected=expected)


def test_complete_contract_json_and_xml_exports_preserve_raw_sources_and_semantic_ids(tmp_path):
    expected = _expected(_target('Name: Delta & "子公司"; Revenue: 17; Profit: 5'))
    original = deepcopy(expected)
    graph = compile_requirement_graph(expected)
    before = deepcopy(graph)
    json_path, xml_path = tmp_path / "requirements.json", tmp_path / "requirements.xml"
    write_requirement_graph(graph, json_path, xml_path)
    assert json.loads(json_path.read_text(encoding="utf-8")) == graph
    tree = ET.parse(xml_path)
    xml_literals = set(tree.getroot().itertext())
    xml_values = {value for element in tree.iter() for value in element.attrib.values()}
    for source in graph["sources"]:
        assert source["id"] in xml_values | xml_literals
        assert source["text"] in xml_literals
    for ident in (*graph["projections"]["B"], *graph["projections"]["L"]):
        assert ident in xml_values | xml_literals
    assert graph == before and expected == original
