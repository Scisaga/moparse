"""A financial Unit resumes only after the existing sourced attribution proof."""

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.three_layer import compile_markdown, read_candidate

ZH = ("# 简明合并利润及其他综合收益表\n\n单位：人民币百万元。\n\n"
      "- 净利润归属于\n  - 权益持有人：2028年17；2027年11。\n  - 少数权益：2028年3；2027年2。\n"
      "- 综合收益总额归属于\n  - 权益持有人：2028年21；2027年16。")
EN = ("# Consolidated statement of profit or loss and other comprehensive income\n\nUnit:CNY million.\n\n"
      "- Net income attributable to\n  - Equity holders:2028年17;2027年11\n  - Minority interests:2028年3;2027年2\n"
      "- Total comprehensive income attributable to\n  - Equity holders:2028年21;2027年16")


def graphs(markdown):
    yield compile_markdown(markdown, sample_id="invented-financial-attribution")
    yield read_candidate(markdown_observation(markdown, sample_id="invented-financial-attribution", pipeline="P07", pages=[1]))


@pytest.mark.parametrize("markdown,unit,currency,owner,minority,net,total", [
    (ZH, "人民币百万元", "人民币", "权益持有人", "少数权益", "净利润归属于", "综合收益总额归属于"),
    (EN, "CNY million", "CNY", "Equity holders", "Minority interests", "Net income attributable to", "Total comprehensive income attributable to"),
])
def test_existing_parent_recipient_proofs_resume_the_original_statement_unit_without_new_votes(
        markdown, unit, currency, owner, minority, net, total):
    for graph in graphs(markdown):
        assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"]) for f in graph["business"]] == [
            (subject, attribute, value, {"unit": unit, "period": period, "currency": currency})
            for subject, attribute, value, period in [(owner, net, "17", "2028年"), (owner, net, "11", "2027年"),
                (minority, net, "3", "2028年"), (minority, net, "2", "2027年"), (owner, total, "21", "2028年"), (owner, total, "16", "2027年")]]
        assert len(graph["parent_bindings"]) == 3
        for fact in graph["business"]:
            assert fact["qualifier_provenance"]["unit"]["source"]["lines"] == [3, 3]
            assert fact["qualifier_provenance"]["currency"]["source"]["lines"] == [3, 3]
            assert fact["attribute_source"]["lines"] == ([5, 5] if fact["attribute"] == net else [8, 8])
            assert fact["subject_source"]["lines"] in [[6, 6], [7, 7], [9, 9]]
        assert not any(issue["reason"] in {"unit_scope_boundary_unresolved", "list_group_scope_interpretation_unsupported"}
                       for issue in graph["blockers"])


@pytest.mark.parametrize("placement", ["inline", "header"])
def test_actual_field_unit_overrides_the_caption_and_does_not_change_the_neighbor(placement):
    replacement = ("Equity holders:2028年17USD thousand;2027年11USD thousand" if placement == "inline"
                   else "Equity holders(USD thousand):2028年17;2027年11")
    markdown = EN.replace("Equity holders:2028年17;2027年11", replacement)
    for graph in graphs(markdown):
        assert [f["qualifiers"]["unit"] for f in graph["business"]] == ["USD thousand"] * 2 + ["CNY million"] * 4
        assert [f["qualifiers"]["currency"] for f in graph["business"]] == ["USD"] * 2 + ["CNY"] * 4
        assert [f["value"] for f in graph["business"]] == ["17", "11", "3", "2", "21", "16"]
        assert [f["qualifier_provenance"]["unit"]["source"]["lines"] for f in graph["business"]] == [[6, 6]] * 2 + [[3, 3]] * 4


@pytest.mark.parametrize("boundary", ["Board owns Delta.", "Description: Board owns Delta.", "![Chart](chart.png)",
                                      "## New business"])
def test_an_intervening_boundary_cannot_resume_a_unit_from_before_the_attribution_parent(boundary):
    markdown = EN.replace("- Net income attributable to\n", "- Net income attributable to\n\n" + boundary + "\n\n")
    for graph in graphs(markdown):
        actual = [f for f in graph["business"] if f["attribute"] in {"Net income attributable to", "Total comprehensive income attributable to"}]
        assert actual and all("unit" not in f["qualifiers"] for f in actual)


@pytest.mark.parametrize("change", ["unknown_parent", "unknown_ancestor", "non_financial_scope", "missing_child_proof"])
def test_an_attribution_keyword_or_unproved_ancestor_does_not_clear_unit_pending(change):
    markdown = EN
    if change == "unknown_parent":
        markdown = markdown.replace("- Net income attributable to", "- New business\n  - Revenue:2028年4;2027年3\n- Net income attributable to")
    elif change == "unknown_ancestor":
        markdown = markdown.replace("- Net income attributable to\n  - Equity holders:2028年17;2027年11\n  - Minority interests:2028年3;2027年2",
            "- New business\n  - Net income attributable to\n    - Equity holders:2028年17;2027年11\n    - Minority interests:2028年3;2027年2")
    elif change == "non_financial_scope":
        markdown = markdown.replace("Consolidated statement of profit or loss and other comprehensive income", "Business review")
    else:
        markdown = markdown.replace("  - Equity holders:2028年17;2027年11\n  - Minority interests:2028年3;2027年2", "  - Name:Lumen")
    for graph in graphs(markdown):
        assert all("unit" not in f["qualifiers"] for f in graph["business"])
        assert any(issue["reason"] == "unit_scope_boundary_unresolved" for issue in graph["blockers"])


def test_a_generic_parent_proof_can_resume_through_an_already_proved_financial_classification():
    markdown = ("# Statement of financial position\n\nUnit:USD million\n\n- Assets\n"
                "  - Reserves attributable to\n    - Beneficiaries:2028年17;2027年11")
    for graph in graphs(markdown):
        assert [(f["subject"], f["attribute"], f["value"], f["identity_facets"], f["qualifiers"]) for f in graph["business"]] == [
            ("Beneficiaries", "Reserves attributable to", value, {"group": ["Assets"]},
             {"unit": "USD million", "period": period, "currency": "USD"}) for value, period in [("17", "2028年"), ("11", "2027年")]]
        assert not graph["blockers"]


def test_the_bridge_requires_the_own_parent_and_child_source_objects_not_their_correct_values():
    from copy import deepcopy

    from moparse_eval.financial_group_context import read_financial_attribution_context
    from moparse_eval.series_requirements import read_series_requirements

    heading = {"text": "Statement of financial position", "source": {"path": "<source>", "lines": [1, 1]}}
    parent = {"text": "Reserves attributable to", "source": {"path": "<source>", "lines": [5, 5]}}
    child_source = {"path": "<source>", "lines": [6, 6]}
    text = "Beneficiaries:2028年17;2027年11"
    series = read_series_requirements(text, child_source, parents=[parent["text"]], parent_declarations=[parent])
    syntax = [{"kind": "parent_label", **parent, "parents": [], "scope": [heading["text"]]},
              {"kind": "item", "text": text, "source": child_source, "parents": [parent["text"]], "scope": [heading["text"]]}]
    pending = [{"reason": "unit_scope_boundary_unresolved", "unit": "USD million",
                "unit_source": {"path": "<source>", "lines": [3, 3], "text_span": [5, 16]},
                "source": {"path": "<source>", "lines": [3, 3]}, "scope": [heading["text"]],
                "boundary": {"kind": "parent_label", **parent}}]
    before = deepcopy((series, syntax, pending, parent))
    result = read_financial_attribution_context(series, heading=heading, syntax=syntax, pending=pending, parents=[parent])
    assert result["matched"] is True and result["unit"]["source"] == pending[0]["unit_source"]
    assert (series, syntax, pending, parent) == before
    for target in ("parent", "child"):
        changed = deepcopy(series)
        changed["parent_bindings"][0][target]["source"]["lines"] = [99, 99]
        assert not read_financial_attribution_context(changed, heading=heading, syntax=syntax, pending=pending, parents=[parent])["matched"]
