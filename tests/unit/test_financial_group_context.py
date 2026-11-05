"""Accounting classification parents retain their own bounded unit context."""

from copy import deepcopy

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.three_layer import compile_markdown, read_candidate

ZH = ("# 简明合并利润及其他综合收益表\n\n单位：人民币百万元。\n\n"
      "- 其他综合收益（税后及重分类调整后金额，附注9）\n"
      "  - 不能重分类进损益\n"
      "    - 计划重估：2028年(17)；2027年11。\n"
      "    - 小计：2028年(19)；2027年13。\n"
      "  - 能够重分类进损益\n"
      "    - 折算差额：2028年5；2027年3。\n"
      "    - 小计：2028年7；2027年6。")

EN = ("# Consolidated statement of profit or loss and other comprehensive income\n\n"
      "Unit: USD million.\n\n- Other comprehensive income (net of tax, Note 7)\n"
      "  - Items that will not be reclassified to profit or loss\n"
      "    - Remeasurement:2028年(17);2027年11\n"
      "    - Subtotal:2028年(19);2027年13\n"
      "  - Items that may be reclassified to profit or loss\n"
      "    - Translation:2028年5;2027年3\n"
      "    - Subtotal:2028年7;2027年6")


def graphs(markdown):
    yield compile_markdown(markdown, sample_id="invented-financial-groups")
    yield read_candidate(markdown_observation(markdown, sample_id="invented-financial-groups", pipeline="P07", pages=[1]))


@pytest.mark.parametrize("markdown,unit,currency,root,left,right", [
    (ZH, "人民币百万元", "人民币", "其他综合收益（税后及重分类调整后金额，附注9）", "不能重分类进损益", "能够重分类进损益"),
    (EN, "USD million", "USD", "Other comprehensive income (net of tax, Note 7)",
     "Items that will not be reclassified to profit or loss", "Items that may be reclassified to profit or loss"),
])
def test_printed_statement_and_classification_parents_bind_units_and_distinct_groups(
        markdown, unit, currency, root, left, right):
    for graph in graphs(markdown):
        assert len(graph["business"]) == 8, "Classifications and shared unit add no B votes"
        assert [(fact["value"], fact["qualifiers"]) for fact in graph["business"]] == [
            (value, {"period": period, "unit": unit, "currency": currency})
            for value, period in [("(17)", "2028年"), ("11", "2027年"), ("(19)", "2028年"), ("13", "2027年"),
                                  ("5", "2028年"), ("3", "2027年"), ("7", "2028年"), ("6", "2027年")]]
        assert [f["identity_facets"]["group"] for f in graph["business"]] == [[root, left]] * 4 + [[root, right]] * 4
        for fact in graph["business"]:
            rows = fact["row_evidence"]
            assert [row["text"] for row in rows] == fact["identity_facets"]["group"]
            assert [row["source"]["lines"] for row in rows] == ([[5, 5], [6, 6]] if fact in graph["business"][:4]
                                                                      else [[5, 5], [9, 9]])
            for key, literal in (("unit", unit), ("currency", currency)):
                proof = fact["qualifier_provenance"][key]
                assert proof["source"]["lines"] == [3, 3]
                a, b = proof["source"]["text_span"]
                assert markdown.splitlines()[2][a:b] == literal
            edges = [e for e in graph["relations"] if e.get("fact_id") == fact["id"]]
            assert all(e["right"]["identity_facets"]["group"] == fact["identity_facets"]["group"] for e in edges)
        assert not any(b["reason"] in {"unit_scope_boundary_unresolved", "list_group_scope_interpretation_unsupported"}
                       for b in graph["blockers"])
        fragments = graph["text_projection"]["source_fragments"]
        assert all(any(fragment["text"] == literal for fragment in fragments) for literal in (root, left, right))


@pytest.mark.parametrize("boundary", ["Board owns Delta.", "Description: Board owns Delta.",
                                      "![Chart](chart.png)", "## New business"])
def test_prose_images_and_new_business_headings_stop_the_caption_before_a_new_group(boundary):
    markdown = ZH.replace("\n- 其他综合收益", "\n" + boundary + "\n\n- 其他综合收益")
    for graph in graphs(markdown):
        assert all("unit" not in f["qualifiers"] and "currency" not in f["qualifiers"] for f in graph["business"]
                   if f["attribute"] in {"计划重估", "小计", "折算差额"})
        assert not any(f.get("row_evidence") for f in graph["business"]
                       if f["attribute"] in {"计划重估", "小计", "折算差额"})


@pytest.mark.parametrize("change", ["heading", "unknown_parent", "unproved_role", "business_annotation"])
def test_a_unit_and_accounting_words_do_not_prove_an_arbitrary_group(change):
    markdown = ZH
    if change == "heading":
        markdown = markdown.replace("简明合并利润及其他综合收益表", "经营回顾")
    elif change == "unknown_parent":
        markdown = markdown.replace("其他综合收益（税后及重分类调整后金额，附注9）", "新产品业务")
    elif change == "unproved_role":
        markdown = markdown.replace("- 其他综合收益（税后及重分类调整后金额，附注9）\n  - 不能重分类进损益\n", "其他综合收益（税后及重分类调整后金额，附注9）\n\n不能重分类进损益\n")
    else:
        markdown = markdown.replace("税后及重分类调整后金额，附注9", "明年预计增长9%")
    for graph in graphs(markdown):
        assert all("unit" not in f["qualifiers"] for f in graph["business"] if f["attribute"] == "小计")
        assert any(b["reason"] == "unit_scope_boundary_unresolved" for b in graph["blockers"])


def test_one_group_own_field_unit_does_not_replace_or_leak_the_statement_caption():
    markdown = ZH.replace("计划重估：2028年(17)；2027年11", "计划重估：2028年17万元；2027年11万元")
    for graph in graphs(markdown):
        assert [f["qualifiers"]["unit"] for f in graph["business"]] == ["万元", "万元"] + ["人民币百万元"] * 6
        assert [f["value"] for f in graph["business"]] == ["17", "11", "(19)", "13", "5", "3", "7", "6"]


def test_module_requires_the_actual_parent_chain_and_does_not_mutate_sources():
    from moparse_eval.financial_group_context import read_financial_group_context

    heading = {"text": "Statement of financial position", "source": {"path": "<statement>", "lines": [1, 1]}}
    unit = {"text": "USD million", "source": {"path": "<statement>", "lines": [3, 3], "text_span": [6, 17]}, "level": "caption_shared"}
    source = {"path": "<statement>", "lines": [5, 5], "text_span": [21, 27]}
    original = deepcopy((heading, unit, source))
    result = read_financial_group_context("Assets", source, kind="parent_label", heading=heading, parents=[], unit=unit)
    assert result["matched"] is True and result["label"]["text"] == "Assets"
    assert result["label"]["source"] == source
    assert (heading, unit, source) == original
    unproved = read_financial_group_context("Non-current assets", source, kind="parent_label", heading=heading,
        parents=[{"text": "North", "source": {"path": "<statement>", "lines": [4, 4]}}], unit=unit)
    assert unproved["matched"] is False


@pytest.mark.parametrize("change", ["ordinary_title", "missing_parent", "repeated_statement"])
def test_accounting_terms_do_not_supply_missing_native_heading_or_parent_roles(change):
    markdown = ZH
    if change == "ordinary_title":
        markdown = markdown.replace("# 简明合并利润及其他综合收益表", "简明合并利润及其他综合收益表")
    elif change == "missing_parent":
        markdown = markdown.replace("- 其他综合收益（税后及重分类调整后金额，附注9）\n  - 不能重分类进损益",
                                    "- 不能重分类进损益")
    else:
        markdown = ZH + "\n\n" + ZH.replace("单位：人民币百万元。\n\n", "")
    for graph in graphs(markdown):
        sub = [f for f in graph["business"] if f["attribute"] == "小计"]
        if change == "repeated_statement":
            assert all(f["qualifiers"].get("unit") == "人民币百万元" for f in sub[:4])
            assert all("unit" not in f["qualifiers"] for f in sub[4:])
            assert all("group" not in f["identity_facets"] for f in sub[4:])
        else:
            assert all("unit" not in f["qualifiers"] for f in sub)


def test_a_parent_proof_rebound_to_a_same_named_different_source_is_rejected():
    from moparse_eval.financial_group_context import read_financial_group_context

    heading = {"text": "Statement of financial position", "source": {"path": "<statement>", "lines": [1, 1]}}
    unit = {"text": "USD million", "source": {"path": "<statement>", "lines": [3, 3]}, "level": "caption_shared"}
    parent_source = {"path": "<statement>", "lines": [5, 5]}
    parent = read_financial_group_context("Assets", parent_source, kind="parent_label", heading=heading, parents=[], unit=unit)
    child_source = {"path": "<statement>", "lines": [7, 7]}
    proved = {"text": "Assets", "source": parent_source, "financial_group_context": parent}
    assert read_financial_group_context("Non-current assets", child_source, kind="parent_label", heading=heading,
                                       parents=[proved], unit=unit)["matched"]
    rebound = {**proved, "source": {"path": "<statement>", "lines": [6, 6]}}
    assert not read_financial_group_context("Non-current assets", child_source, kind="parent_label", heading=heading,
                                           parents=[rebound], unit=unit)["matched"]


def test_a_single_scalar_field_retains_the_classification_binding_without_an_extra_group_fact():
    markdown = "# Statement of financial position\n\nUnit:USD million\n\n- Assets\n  - Non-current assets\n    - Deposits:17"
    for graph in graphs(markdown):
        [fact] = graph["business"]
        assert (fact["attribute"], fact["value"], fact["qualifiers"]) == ("Deposits", "17", {"unit": "USD million", "currency": "USD"})
        assert fact["identity_facets"] == {"group": ["Assets", "Non-current assets"]}
        assert [row["text"] for row in fact["row_evidence"]] == ["Assets", "Non-current assets"]


def test_identity_child_retains_its_own_value_while_its_unread_group_relation_stays_pending():
    markdown = "# Statement of financial position\n\nUnit:USD million\n\n- Assets\n  - Name:Lumen"
    for graph in graphs(markdown):
        [fact] = graph["business"]
        assert (fact["attribute"], fact["value"], fact["role"], fact["qualifiers"]) == ("Name", "Lumen", "identity", {})
        pending = [item for item in graph.get("pending_requirements", [])
                   if item["reason"] == "financial_classification_identity_binding_unsupported"]
        assert len(pending) == 1 and pending[0]["layers"] == ["L"]
        assert pending[0]["source"]["lines"] == [6, 6]
        assert [row["text"] for row in pending[0]["group_evidence"]] == ["Assets"]


def test_source_graph_represents_classifications_as_bindings_of_two_scalar_requirements():
    rows = [(1, "heading", "Statement of financial position", [], False),
            (3, "text", "Unit:USD million", [], False),
            (5, "item", "Assets", [], True),
            (6, "item", "Non-current assets", ["Assets"], True),
            (7, "item", "Deposits:2028年17;2027年11", ["Assets", "Non-current assets"], False)]
    expected = {"sample_id": "invented-financial-source", "document_id": "invented-document", "source_pages": [1],
                "standard": "expected_only", "scope": [{"lines": [1, 7], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}],
                "targets": [{"id": f"source:{line}", "kind": kind, "text": text, "raw_text": text, "raw": text,
                             "reference": {"path": "<invented-financial-source>", "lines": [line, line]}, "cells": [],
                             "parents": parents, "has_children": children,
                             "context": ["Statement of financial position"], "pages": [1],
                             "heading_level": 1 if kind == "heading" else None,
                             "selected_heading_context": [{"text": "Statement of financial position",
                                 "reference": {"path": "<invented-financial-source>", "lines": [1, 1]}}],
                             "outside_selection_context": []}
                            for line, kind, text, parents, children in rows]}
    model = compile_requirement_graph(expected)
    validate_requirement_graph(model, expected=expected)
    assert model["semantic_complete"] is True and model["unresolved"] == []
    facts = [node for node in model["nodes"] if node["id"] in model["projections"]["B"]]
    assert [(fact["attribute"], fact["value"], fact["identity_facets"], fact["qualifiers"]) for fact in facts] == [
        ("Deposits", value, {"group": ["Assets", "Non-current assets"]},
         {"unit": "USD million", "period": period, "currency": "USD"}) for value, period in [("17", "2028年"), ("11", "2027年")]]
    sources = {row["id"]: row for row in model["sources"]}
    for disposition in model["dispositions"]:
        if sources[disposition["source_id"]]["text"] in {"Assets", "Non-current assets"}:
            assert disposition["layers"]["B"]["requirements"] == model["projections"]["B"]
