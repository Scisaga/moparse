"""Independent source-disposition probes over invented syntax only.

Known schema/control evidence must be followed into source dispositions.
Unproven grids and real scope boundaries remain unresolved. No corpus target,
candidate output, old compiler result or published grade supplies an oracle.
"""

from collections import Counter
from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.source_requirements import plan_mixed_source
from moparse_eval.three_layer import compile_expected

PATH = "<invented-source-coverage>"


@pytest.mark.parametrize("text", ["; ;", "；\n；"])
def test_source_plan_empty_fragments_are_a_nonmatching_boundary_control(text):
    assert plan_mixed_source(text, {"path": PATH, "lines": [1, 1]}) is None


def _target(text, line=1, *, kind="text", cells=None, heading_level=None):
    return {"id": f"target:{line}", "kind": kind, "text": text, "raw_text": text, "raw": text,
            "reference": {"path": PATH, "lines": [line, line + text.count("\n")]}, "cells": cells or [],
            "parents": [], "has_children": False, "context": [], "selected_heading_context": [],
            "outside_selection_context": [], "pages": [1], "heading_level": heading_level}


def _expected(*targets):
    return {"sample_id": "invented-source-coverage", "document_id": "invented-document",
            "source_pages": [1], "standard": "expected_only", "targets": list(targets),
            "scope": [{"lines": [1, max(t["reference"]["lines"][1] for t in targets)], "pages": [1],
                       "declared_source_pages": [1], "outside_source_pages": []}]}


def _table(markup):
    # This is the actual HTML syntax reader, not a requirement or answer oracle.
    return _expected(_target("", kind="table", cells=html_cells(markup, "printed-table")))


def _items(graph, layer):
    bank = graph["relations"] if layer == "L" else graph["nodes"]
    by_id = {item["id"]: item for item in bank}
    return [by_id[ident] for ident in graph["projections"][layer]]


def _source(graph, text):
    matches = [entry for entry in graph["sources"] if entry["text"] == text]
    assert len(matches) == 1
    return matches[0]


def _disposition(graph, source):
    [row] = [row for row in graph["dispositions"] if row["source_id"] == source["id"]]
    return row["layers"]


def _same_origin(left, right):
    return (left.get("path"), left.get("lines"), left.get("cell")) == (
        right.get("path"), right.get("lines"), right.get("cell"))


def _own_control(graph, source):
    controls = graph["context"]["text_projection"]["controls"]
    matches = [control for control in controls if _same_origin(control["source"], source["source"])]
    assert matches, (source, controls)
    assert all(control["reason"] for control in matches)
    return matches


@pytest.mark.parametrize("header,rows,wanted", [
    ("<tr><th>Attribute</th><th>Value</th></tr>",
     "<tr><td>Name</td><td>Delta</td></tr><tr><td>Revenue</td><td>17</td></tr><tr><td>Profit</td><td>5</td></tr>",
     [("Name", "Delta", "identity"), ("Revenue", "17", "metric"), ("Profit", "5", "metric")]),
    ("<tr><td>Attribute</td><td>Value</td></tr>",
     "<tr><td>Revenue</td><td>17</td></tr><tr><td>Profit</td><td>5</td></tr>",
     [("Revenue", "17", "metric"), ("Profit", "5", "metric")]),
    ('<tr><th scope="col">Attribute</th><th scope="col">Value</th></tr>',
     "<tr><td>Name</td><td>Delta</td></tr><tr><td>Revenue</td><td>17</td></tr><tr><td>Profit</td><td>5</td></tr>",
     [("Name", "Delta", "identity"), ("Revenue", "17", "metric"), ("Profit", "5", "metric")]),
], ids=["native-th-band", "printed-schema-repeated-measurements", "explicit-col-control"])
def test_complete_contract_proved_schema_controls_have_supported_dispositions(header, rows, wanted):
    expected = _table("<table>" + header + rows + "</table>")
    before = deepcopy(expected)
    graph = compile_requirement_graph(expected)
    assert [(f["attribute"], f["value"], f["role"]) for f in _items(graph, "B")] == wanted
    for label in ("Attribute", "Value"):
        source = _source(graph, label)
        _own_control(graph, source)
        for layer in ("T", "B"):
            disposition = _disposition(graph, source)[layer]
            assert disposition["status"] == "not_applicable", (label, layer, disposition)
            assert disposition["rule_id"] and disposition["reason"]
    assert graph["unresolved"] == [] and graph["semantic_complete"] is True
    validate_requirement_graph(graph, expected=expected)
    assert expected == before


@pytest.mark.parametrize("label", ["Unit", "单位"])
def test_complete_contract_property_unit_key_follows_its_own_qualifier_control(label):
    expected = _table('<table><tr><th scope="col">Attribute</th><th scope="col">Value</th></tr>'
                      '<tr><td>Name</td><td>Delta</td></tr><tr><td>Revenue</td><td>17</td></tr>'
                      '<tr><td>Profit</td><td>5</td></tr><tr><td>' + label + '</td><td>万元</td></tr></table>')
    graph = compile_requirement_graph(expected)
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in _items(graph, "B")] == [
        ("Name", "Delta", {}), ("Revenue", "17", {"unit": "万元"}), ("Profit", "5", {"unit": "万元"})]
    key = _source(graph, label)
    _own_control(graph, key)
    dispositions = _disposition(graph, key)
    assert dispositions["T"]["status"] == dispositions["B"]["status"] == "not_applicable"
    actual_unit = _source(graph, "万元")
    assert _disposition(graph, actual_unit)["T"]["status"] == "interpreted"
    assert _disposition(graph, actual_unit)["B"]["status"] == "interpreted"
    assert not graph["unresolved"]


@pytest.mark.parametrize("label", ["附註：", "Note:"])
def test_complete_contract_proved_context_marker_is_not_an_unknown_business_answer(label):
    expected = _expected(_target("Revenue: 17", 1), _target(label, 2),
                         _target("the board shall publish the notice.", 3))
    graph = compile_requirement_graph(expected)
    assert [(f["attribute"], f["value"]) for f in _items(graph, "B")] == [
        ("Revenue", "17"), ("publish", "publish the notice")]
    marker = _source(graph, label)
    declarations = graph["context"]["scope_schema"]["context_labels"]
    assert any(item["text"] == label and item["role"] == "printed_context_label"
               and _same_origin(item["source"], marker["source"]) for item in declarations)
    disposition = _disposition(graph, marker)
    assert disposition["B"]["status"] == "not_applicable"
    assert disposition["T"]["status"] in {"interpreted", "not_applicable"}
    if disposition["T"]["status"] == "not_applicable":
        _own_control(graph, marker)
    assert not graph["unresolved"]


@pytest.mark.parametrize("markup,printed", [
    ("<table><tr><td>Attribute</td><td>Value</td></tr><tr><td>Monday</td><td>Quiet</td></tr>"
     "<tr><td>Tuesday</td><td>Sunny</td></tr></table>", ["Attribute", "Value", "Monday", "Quiet", "Tuesday", "Sunny"]),
    ("<table><tr><td>Status</td><td>Ready</td></tr><tr><td>Blocked</td><td>No</td></tr></table>",
     ["Status", "Ready", "Blocked", "No"]),
], ids=["schema-words-alone", "layout-status-header-lookalike"])
def test_failure_closed_contract_unproven_grid_keeps_every_literal_and_unknown_role(markup, printed):
    expected = _table(markup)
    graph = compile_requirement_graph(expected)
    assert _items(graph, "B") == []
    assert Counter(n["text"] for n in _items(graph, "T")) == Counter(printed)
    assert any(issue["reason"] == "matrix_data_roles_unproven" for issue in graph["unresolved"])
    assert graph["semantic_complete"] is False
    for literal in printed:
        disposition = _disposition(graph, _source(graph, literal))
        assert disposition["T"]["status"] == "interpreted"
        assert disposition["B"]["status"] == "unresolved"


def test_complete_contract_joined_prose_covers_each_actual_fragment_without_invented_sources():
    first, second = "the board shall pay ", "17 credits only if approved by 4 directors."
    expected = _expected(_target(first, 1), _target(second, 2))
    graph = compile_requirement_graph(expected)
    [fact] = _items(graph, "B")
    assert fact["value"] == "pay 17 credits"
    assert fact["qualifiers"]["condition"] == "approved by 4 directors"
    assert [fragment["text"] for fragment in fact["source"]["joined_fragments"]] == [first, second]
    for text in (first, second):
        disposition = _disposition(graph, _source(graph, text))
        assert disposition["T"]["status"] == disposition["B"]["status"] == "interpreted"
        assert fact["id"] in disposition["B"]["requirements"]
    assert not graph["unresolved"]


def test_failure_closed_contract_heading_boundary_cannot_supply_an_orphan_fragment_business_role():
    expected = _expected(_target("the board shall pay", 1),
                         _target("South", 2, kind="heading", heading_level=1), _target("17 credits.", 3))
    graph = compile_requirement_graph(expected)
    assert all(fact["value"] != "pay 17 credits" for fact in _items(graph, "B"))
    orphan = _source(graph, "17 credits.")
    assert _disposition(graph, orphan)["B"]["status"] == "unresolved"
    assert any(issue.get("source_id") == orphan["id"] and "B" in issue["layers"] for issue in graph["unresolved"])
    assert graph["semantic_complete"] is False


@pytest.mark.parametrize("separator", ["; ", "\n"], ids=["semicolon", "soft-linebreak"])
def test_failure_closed_contract_mixed_fields_and_relation_do_not_hide_inside_an_entity_answer(separator):
    text = separator.join(("Name: Delta", "Revenue: 17", "Board approves Dividend."))
    expected = _expected(_target(text))
    graph = compile_requirement_graph(expected)
    facts = _items(graph, "B")
    assert not any(fact["role"] == "identity" and ("Revenue:" in fact["value"] or "approves" in fact["value"])
                   for fact in facts), "a source-wide opaque Name answer cannot certify its other clauses"
    if graph["semantic_complete"]:
        assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in facts] == [
            ("", "Name", "Delta", "identity"), ("Delta", "Revenue", "17", "metric"),
            ("Board", "approve", "Dividend", "description")]
        [proposition] = [fact for fact in facts if fact["role"] == "description"]
        assert (proposition["predicate"], proposition["object"]) == ("approves", "Dividend")
        assert _items(graph, "L")
    else:
        assert any(issue.get("text") == text and {"B", "L"} <= set(issue["layers"])
                   for issue in graph["unresolved"])
    assert all(printed in "".join(node["text"] for node in _items(graph, "T"))
               for printed in ("Name", "Delta", "Revenue", "17", "Board approves Dividend"))


def test_failure_closed_contract_unknown_third_fragment_cannot_borrow_a_sibling_fact_disposition():
    text = "Name: Delta; Revenue: 17; Delta appoints Kappa."
    expected = _expected(_target(text))
    graph = compile_requirement_graph(expected)
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in _items(graph, "B")] == [
        ("", "Name", "Delta", "identity"), ("Delta", "Revenue", "17", "metric")]
    unknown = _source(graph, "Delta appoints Kappa.")
    assert unknown["kind"] == "fragment" and unknown["fragment_of"]
    assert unknown["source"]["text_span"] == [26, 47]
    assert text[26:47] == unknown["text"]
    disposition = _disposition(graph, unknown)
    assert disposition["B"]["status"] == disposition["L"]["status"] == "unresolved"
    pending_layers = {layer for item in graph["unresolved"] if item.get("source_id") == unknown["id"]
                      for layer in item["layers"]}
    assert {"B", "L"} <= pending_layers
    assert "Delta appoints Kappa." in "".join(node["text"] for node in _items(graph, "T"))
    assert graph["semantic_complete"] is False and graph["complete"] is False


def test_failure_closed_contract_unselected_unit_dependency_survives_graph_and_public_projection():
    selected = _target("Revenue: 17")
    declaration = {"kind": "explicit_unit_or_period", "text": "Unit: CNY million",
                   "raw": "Unit: CNY million", "reference": {"path": "<unselected-unit>", "lines": [40, 40]}}
    selected["outside_selection_context"] = [declaration]
    expected = _expected(selected)
    graph = compile_requirement_graph(expected)
    [fact] = _items(graph, "B")
    assert fact["attribute"] == "Revenue" and fact["value"] == "17" and fact["qualifiers"] == {}
    assert all(source["source"]["path"] != "<unselected-unit>" for source in graph["sources"])
    assert graph["complete"] is False
    [pending] = [item for item in graph["unresolved"] if item["reason"] == "input_scope_context"]
    assert {"B", "L"} <= set(pending["layers"])
    assert pending["outside_selection"] == [declaration]
    projection = compile_expected(expected)
    assert any(item["reason"] == "input_scope_context" and item["outside_selection"] == [declaration]
               for item in projection["blockers"])
