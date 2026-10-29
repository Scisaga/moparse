"""Relationship evidence contracts with invented texts and native identities."""

from __future__ import annotations

from copy import deepcopy

import pytest

from moparse_eval.reporting import aggregate_reports
from moparse_eval.scoring import score_case


def _unit(identity, text, **extra):
    return {"id": identity, "literal": text, "kind": "text", "status": "confirmed", "pages": [1], **extra}


def _block(identity, text="", **extra):
    return {"id": identity, "native_path": identity, "kind": "text", "text": text, **extra}


def _case(*units, kind="heading_of"):
    return {
        "sample_id": "synthetic", "review_status": "confirmed", "units": list(units),
        "relations": [{"type": kind, "source": units[0]["id"], "target": units[1]["id"], "status": "confirmed"}],
    }


def _observation(*blocks, **extra):
    return {"sample_id": "synthetic", "pipeline": "P-test", "status": "completed",
            "dataset": "synthetic", "suite": "quality800", "phase": "measured", "repetition": "1",
            "pages": [{"page": 1, "blocks": list(blocks)}], "relations": [], **extra}


def _heading_case():
    return _case(_unit("h", "Business heading"), _unit("p", "A complete business paragraph."))


def test_title_text_is_preserved_while_unprovided_hierarchy_is_unknown_not_wrong():
    source = _observation(_block("h", "Business heading", kind="title"),
                          _block("p", "A complete business paragraph."),
                          native_relation_evidence={"heading_blocks": [
                              {"id": "h", "status": "role_only_without_level"},
                          ]})
    before = deepcopy(source)
    scored = score_case(_heading_case(), source)
    assert source == before
    assert scored["metrics"]["unit_exact"]["recall"] == 1
    row = scored["relations"][0]
    assert row["state"] == "native_not_provided"
    assert row["reason"] == "native_title_role_without_hierarchy"
    assert row["observable"] is False
    detail = scored["metrics"]["relations"]["by_type"]["heading_of"]
    assert detail["denominator"] == 1 and detail["value"] == 0
    assert detail["confirmed_incorrect"] == 0 and detail["native_not_provided"] == 1
    assert detail["conditional_accuracy"]["value"] is None


def test_a_different_declared_direct_heading_owner_is_confirmed_incorrect():
    source = _observation(_block("h", "Business heading"), _block("other", "Another heading"),
                          _block("p", "A complete business paragraph."), relations=[
                              {"type": "heading_of", "source": "other", "target": "p"},
                          ])
    scored = score_case(_heading_case(), source)
    assert scored["relations"][0]["state"] == "confirmed_incorrect"
    detail = scored["metrics"]["relations"]["by_type"]["heading_of"]
    assert detail["conditional_accuracy"]["value"] == 0


def test_two_declared_heading_owners_are_a_conflict_even_if_one_matches():
    source = _observation(_block("h", "Business heading"), _block("other", "Another heading"),
                          _block("p", "A complete business paragraph."), relations=[
                              {"type": "heading_of", "source": "h", "target": "p"},
                              {"type": "heading_of", "source": "other", "target": "p"},
                          ])
    scored = score_case(_heading_case(), source)
    assert scored["relations"][0]["state"] == "unassessable"
    assert scored["relations"][0]["reason"] == "conflicting_native_heading_owners"


def test_source_block_and_container_identity_collision_is_unassessable():
    source = _observation(_block("h", "Business heading"), _block("p", "A complete business paragraph."),
                          native_containers=[{"id": "h", "label": "section"}],
                          relations=[{"type": "heading_of", "source": "h", "target": "p"}])
    scored = score_case(_heading_case(), source)
    assert scored["relations"][0]["state"] == "unassessable"


def test_some_other_outgoing_edge_does_not_prove_an_unreturned_edge_false():
    source = _observation(_block("h", "Business heading"), _block("other", "Another paragraph"),
                          _block("p", "A complete business paragraph."), relations=[
                              {"type": "heading_of", "source": "h", "target": "other"},
                          ])
    scored = score_case(_heading_case(), source)
    assert scored["relations"][0]["state"] == "native_not_provided"


def _caption_inputs(*, reverse=False, cycle=False, other_table=False):
    target = _case(_unit("cap", "Annual results table"),
                   _unit("record", "Revenue: 100", kind="table_record", table={"row_header_path": ["Revenue"]}),
                   kind="caption_for")
    table = _block("body", kind="table_body", parent_id="outer", native_table_container="outer", cells=[
        {"id": "label", "text": "Revenue", "row": 1, "col": 0},
        {"id": "value", "text": "100", "row": 1, "col": 1},
    ])
    edge_target = "unrelated-table" if other_table else "outer"
    edge = {"type": "caption_of", "source": edge_target if reverse else "cap",
            "target": "cap" if reverse else edge_target}
    source = _observation(_block("cap", "Annual results table", kind="table_caption"), table,
                          native_containers=[{"id": "outer", "label": "table", "native_children": ["body"]}],
                          relations=[edge])
    if cycle:
        source["native_containers"][0]["parent_id"] = "body"
    return target, source


def test_caption_alias_follows_the_declared_table_container_to_a_record():
    target, source = _caption_inputs()
    before = deepcopy((target, source))
    scored = score_case(target, source)
    assert (target, source) == before
    assert scored["relations"][0]["state"] == "confirmed_correct"
    assert scored["relations"][0]["evidence"] == "explicit_native_relation_and_containment"
    assert scored["metrics"]["relations"]["by_type"]["caption_for"]["conditional_accuracy"]["value"] == 1


@pytest.mark.parametrize("option", ["reverse", "other_table"])
def test_caption_direction_and_native_container_identity_cannot_be_guessed(option):
    target, source = _caption_inputs(**{option: True})
    scored = score_case(target, source)
    assert scored["relations"][0]["correct"] is False
    assert scored["relations"][0]["state"] == "native_not_provided"


def test_cyclic_native_containment_is_unassessable_not_correct():
    target, source = _caption_inputs(cycle=True)
    scored = score_case(target, source)
    assert scored["relations"][0]["state"] == "unassessable"


def test_conflicting_native_table_owners_do_not_reward_the_more_favorable_one():
    target, source = _caption_inputs()
    source["native_containers"].append({"id": "other", "label": "table"})
    source["pages"][0]["blocks"][1]["parent_id"] = "other"
    scored = score_case(target, source)
    assert scored["relations"][0]["state"] == "unassessable"


def test_outer_table_caption_is_not_a_caption_for_nested_inner_table_records():
    target, source = _caption_inputs()
    source["native_containers"].append({"id": "inner", "label": "table", "parent_id": "outer"})
    source["pages"][0]["blocks"][1].update(parent_id="inner", native_table_container="inner")
    scored = score_case(target, source)
    assert scored["relations"][0]["state"] == "unassessable"


def test_one_native_caption_edge_supporting_two_records_does_not_create_negative_fp():
    target, source = _caption_inputs()
    target["scoring"] = {"exhaustive_relations": True}
    target["units"].append(_unit("second-record", "Costs: 50", kind="table_record", table={"row_header_path": ["Costs"]}))
    target["relations"].append({"type": "caption_for", "source": "cap", "target": "second-record", "status": "confirmed"})
    source["pages"][0]["blocks"][1]["cells"].extend([
        {"id": "cost-label", "text": "Costs", "row": 2, "col": 0},
        {"id": "cost-value", "text": "50", "row": 2, "col": 1},
    ])
    scored = score_case(target, source)
    metric = scored["metrics"]["relations"]
    assert metric["tp"] == 2 and metric["recall"] == 1
    assert metric["fp"] is None and metric["precision"] is None and metric["f1"] is None


def test_one_native_edge_for_disjoint_paragraph_spans_keeps_precision_unknown():
    target = _case(_unit("h", "Business heading"), _unit("a", "The first complete paragraph."))
    target["units"].append(_unit("b", "The second complete paragraph."))
    target["relations"] = [
        {"type": "heading_of", "source": "h", "target": identity, "status": "confirmed"}
        for identity in ("a", "b")
    ]
    target["scoring"] = {"exhaustive_relations": True}
    source = _observation(_block("h", "Business heading"),
                          _block("both", "The first complete paragraph. The second complete paragraph."),
                          relations=[{"type": "heading_of", "source": "h", "target": "both"}])
    scored = score_case(target, source)
    assert scored["metrics"]["relations"]["tp"] == 2
    assert scored["metrics"]["relations"]["fp"] is None


def test_exhaustive_one_to_one_native_edges_still_have_defined_precision():
    target = _heading_case()
    target["scoring"] = {"exhaustive_relations": True}
    source = _observation(_block("h", "Business heading"), _block("p", "A complete business paragraph."),
                          relations=[{"type": "heading_of", "source": "h", "target": "p"}])
    scored = score_case(target, source)
    assert scored["metrics"]["relations"]["precision"] == 1
    assert scored["metrics"]["relations"]["f1"] == 1


def test_heading_assignment_to_table_preserves_record_scope():
    target, source = _caption_inputs()
    target["relations"][0]["type"] = "heading_of"
    source["relations"][0]["type"] = "heading_of"
    scored = score_case(target, source)
    assert scored["relations"][0]["state"] == "confirmed_correct"


def test_endpoint_failure_and_reversed_order_are_separate_states():
    target = _heading_case()
    target["relations"][0]["type"] = "before"
    missing = score_case(target, _observation(_block("h", "Business heading")))
    reversed_order = score_case(target, _observation(_block("p", "A complete business paragraph."),
                                                     _block("h", "Business heading")))
    assert missing["relations"][0]["state"] == "endpoint_unresolved"
    assert reversed_order["relations"][0]["state"] == "confirmed_incorrect"


def test_relation_evidence_aggregation_retains_unknown_and_conditional_denominators():
    target, source = _caption_inputs()
    correct = score_case(target, source)
    unknown = score_case(_heading_case(), _observation(_block("h", "Business heading"),
                                                       _block("p", "A complete business paragraph.")))
    unknown["sample_id"] = "synthetic-other"
    before = deepcopy((correct, unknown))
    aggregate = aggregate_reports([correct, unknown])
    assert (correct, unknown) == before
    detail = aggregate["groups"][0]["quality"]["micro"]["relations"]
    assert detail["evidence_states"] == {
        "confirmed_correct": 1, "confirmed_incorrect": 0, "native_not_provided": 1,
        "endpoint_unresolved": 0, "unassessable": 0,
    }
    assert detail["target_units"] == 2 and detail["recall"] == 0.5
    assert detail["by_type"]["heading_of"]["conditional_accuracy"]["value"] is None
    assert detail["by_type"]["caption_for"]["conditional_accuracy"]["value"] == 1


def test_old_metrics_without_state_counts_remain_unknown_in_the_report():
    unknown = score_case(_heading_case(), _observation(_block("h", "Business heading"),
                                                       _block("p", "A complete business paragraph.")))
    metric = unknown["metrics"]["relations"]
    metric.pop("evidence_states")
    for state in ("confirmed_correct", "confirmed_incorrect", "native_not_provided", "endpoint_unresolved", "unassessable"):
        metric["by_type"]["heading_of"].pop(state)
    detail = aggregate_reports([unknown])["groups"][0]["quality"]["micro"]["relations"]
    assert detail["evidence_states"]["native_not_provided"] is None
    assert detail["by_type"]["heading_of"]["conditional_accuracy"]["value"] is None
