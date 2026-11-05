"""Independent printed parent-metric and recipient-field source oracles."""

from copy import deepcopy

import pytest

from moparse_eval.scalar_evidence import validate_scalar_sources
from moparse_eval.series_requirements import read_series_requirements
from moparse_eval.text_projection import project_header_path_text

PARENT = {"text": "Net income attributable to", "source": {"path": "<parent>", "lines": [3, 3], "text_span": [40, 66]}}
CHILD = "Owners:2028年17万元；2027年11万元"
CHILD_SOURCE = {"path": "<child>", "lines": [4, 4], "text_span": [80, 80 + len(CHILD)]}


def test_a_printed_attribution_parent_owns_the_metric_and_the_child_prints_the_recipient():
    before = deepcopy((PARENT, CHILD_SOURCE))
    result = read_series_requirements(CHILD, CHILD_SOURCE, parent_declarations=[PARENT])
    assert (PARENT, CHILD_SOURCE) == before
    assert result["matched"] is True and result["blockers"] == []
    assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("Owners", "Net income attributable to", "17", {"period": "2028年", "unit": "万元"}),
        ("Owners", "Net income attributable to", "11", {"period": "2027年", "unit": "万元"}),
    ]
    for f in result["facts"]:
        assert f["attribute_source"] == PARENT["source"]
        assert f["source"]["attribute_source"] == PARENT["source"]
        assert f["subject_source"] == {**CHILD_SOURCE, "text_span": [80, 86]}
        assert f["role_basis"]["attribution"]["parent"]["text"] == PARENT["text"]
    [binding] = result["parent_bindings"]
    assert binding["parent"] == PARENT
    assert binding["child"] == {"text": "Owners", "source": {**CHILD_SOURCE, "text_span": [80, 86]}}
    assert {item["fact_id"] for item in binding["facts"]} == {f["id"] for f in result["facts"]}
    assert result["text_projection_complete"] is True
    assert len(result["projection_inputs"]["objects"]) == 2
    assert [item["text"] for item in result["projection_inputs"]["locators"]] == ["Owners"]
    for obj in result["projection_inputs"]["objects"]:
        assert any(a["text"] == PARENT["text"] and a["role"] == "label" and a["source"] == PARENT["source"]
                   for a in obj["text_atoms"])
    assert {s["source"]["path"] for s in result["projection_inputs"]["source_fragments"]} == {"<parent>", "<child>"}
    original = deepcopy(result)
    projection = project_header_path_text(result)
    assert result == original
    assert sum(a["role"] == "label" and a["text"] == PARENT["text"] for a in projection["atoms"]) == 2
    assert sum(a["role"] == "locator" and a["text"] == "Owners" for a in projection["atoms"]) == 1
    validate_scalar_sources(result["facts"], projection, canonicalize=str.strip)


@pytest.mark.parametrize("parent_text", ["利润归属于", "利潤歸屬於"])
def test_only_the_actual_full_parent_label_is_bound_without_business_label_rewriting(parent_text):
    parent = {"text": parent_text, "source": {"path": "<actual-parent>", "lines": [8, 8]}}
    result = read_series_requirements("持有人：2028年17；2027年11", {"path": "<actual-child>", "lines": [9, 9]},
                                      parent_declarations=[parent])
    assert result["blockers"] == []
    assert [(f["subject"], f["attribute"], f["value"]) for f in result["facts"]] == [
        ("持有人", parent_text, "17"), ("持有人", parent_text, "11")]


def test_a_plain_group_cannot_replace_the_printed_child_metric_role():
    result = read_series_requirements(CHILD, CHILD_SOURCE,
        parent_declarations=[{"text": "North", "source": {"path": "<group>", "lines": [3, 3]}}])
    assert result.get("parent_bindings", []) == []
    assert [f["attribute"] for f in result["facts"]] == ["Owners", "Owners"]


def test_a_printed_record_entity_keeps_its_separate_identity_and_actual_name_source():
    issuer_source = {"path": "<record-name>", "lines": [2, 2], "text_span": [5, 10]}
    result = read_series_requirements(CHILD, CHILD_SOURCE, parent_declarations=[PARENT],
                                      subject="Lumen", subject_source=issuer_source)
    assert result["blockers"] == []
    for fact in result["facts"]:
        assert fact["subject"] == "Owners"
        assert fact["identity_facets"] == {"record_subject": "Lumen"}
        assert fact["record_evidence"]["record_subject"] == {"text": "Lumen", "source": issuer_source}


def test_an_unsourced_default_record_entity_is_preserved_as_unknown_instead_of_becoming_proved_context():
    result = read_series_requirements(CHILD, CHILD_SOURCE, parent_declarations=[PARENT], subject="Lumen")
    assert [f["subject"] for f in result["facts"]] == ["Owners", "Owners"]
    assert all("record_subject" not in f["identity_facets"] for f in result["facts"])
    assert any(p.get("record_subject") == "Lumen" for p in result["pending_requirements"])
    assert any(set(b["layers"]) >= {"B", "L"} for b in result["blockers"])


@pytest.mark.parametrize("mode", ["string_only", "missing_source", "multiple", "contradictory_path"])
def test_unproved_or_conflicting_attribution_bindings_preserve_the_child_as_unresolved(mode):
    options = {"parents": [PARENT["text"]]}
    if mode == "missing_source":
        options["parent_declarations"] = [{"text": PARENT["text"]}]
    elif mode == "multiple":
        options["parent_declarations"] = [PARENT, {"text": "Comprehensive income attributable to",
            "source": {"path": "<other-parent>", "lines": [2, 2]}}]
    elif mode == "contradictory_path":
        options["parent_declarations"] = [{"text": "Comprehensive income attributable to",
            "source": {"path": "<other-parent>", "lines": [2, 2]}}]
    result = read_series_requirements(CHILD, CHILD_SOURCE, **options)
    assert result["matched"] is True and result["facts"] == []
    assert result["pending_requirements"]
    assert any(p["text"] == CHILD and p["source"] == CHILD_SOURCE for p in result["pending_requirements"])
    assert any(set(b["layers"]) >= {"B", "L"} for b in result["blockers"])
