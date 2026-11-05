"""Independent oracles from the second three-layer implementation audit.

These are invented text and native blocks. They require no source material,
inference, images, PDFs, or reference writes. Unsupported text restatement
may explicitly block publication; a known representation artifact may not
publish as a lower candidate grade.
"""

from __future__ import annotations

import pytest

from moparse_eval.three_layer import (
    compile_markdown,
    grade_layers,
    read_candidate,
    read_candidate_markdown,
)


def _requirements(text):
    return compile_markdown(text, sample_id="audit")


def _grade(reference, candidate):
    return grade_layers(_requirements(reference), read_candidate_markdown(candidate, sample_id="audit", pipeline="P08"))


def _require_equal_text(score):
    assert score["publishable"] is True, score["blockers"]
    assert score["layers"]["T"]["complete"] is True
    assert score["layers"]["T"]["score"] == 100


@pytest.mark.parametrize("reference,candidate", [
    ("The board approved the proposal.", "The board approved\n\nthe proposal."),
    ("這是正常的段落。", "這是正常\n\n的段落。"),
])
def test_report_rechecks_strict_source_fragments_without_rejecting_legal_text_blocks(reference, candidate):
    suffix = "\n\nName: Delta; Revenue: 17"
    score = _grade(reference + suffix, candidate + suffix)
    if reference.startswith("The board approved"):
        assert score["publishable"] is True, score["blockers"]
        claim = next(row for row in score["outcomes"] if row["layer"] == "B" and row["expected"]["attribute"] == "approve")
        assert claim["outcome"] == "correct"
    else:
        assert score["publishable"] is False
        assert any(row["reason"] == "narrative_predicate_unresolved" for row in score["blockers"])
        assert score["layers"]["B"]["complete"] is False
    assert score["layers"]["T"]["score"] == 100
    row = next(row for row in score["outcomes"] if row["layer"] == "T" and row["expected"]["text"] == reference)
    assert len(row["actual"]["source_fragments"]) == 2
    assert "\n" in row["actual"]["strict_text"]
    assert sum(row["strict_edits"].values()) > 0
    from moparse_eval.expected_report import _complete_text_trace

    _complete_text_trace(score)


@pytest.mark.parametrize("interruption", [
    {"id": "image", "kind": "image", "text": "", "text_format": "plain"},
    {"id": "empty-table", "kind": "table", "text": "", "cells": [], "text_format": "plain"},
    {"id": "heading", "kind": "heading", "text": "Interlude", "level": 1, "text_format": "plain"},
    {"id": "empty-heading", "kind": "heading", "text": "", "level": 1, "text_format": "plain"},
], ids=["empty-image", "empty-table", "heading", "empty-heading"])
def test_native_interruption_prevents_skipping_the_block_when_joining_prose(interruption):
    observation = {"sample_id": "audit", "pipeline": "P08", "status": "completed", "pages": [
        {"page": 1, "blocks": [
            {"id": "first", "kind": "text", "text": "The board approved", "text_format": "plain"},
            interruption,
            {"id": "last", "kind": "text", "text": "the proposal.", "text_format": "plain"},
            {"id": "record", "kind": "text", "text": "Name: Delta; Revenue: 17", "text_format": "plain"},
        ]}]}
    evidence = read_candidate(observation)
    assert not any(item["text"] == "The board approved the proposal." for item in evidence["text"])
    score = grade_layers(_requirements("The board approved the proposal.\n\nName: Delta; Revenue: 17"), evidence)
    assert not score["publishable"] or score["layers"]["T"]["score"] < 100


@pytest.mark.parametrize("reverse", [False, True])
def test_shared_table_headers_are_not_false_missing_text_from_record_restatements(reverse):
    records = "- Name: Delta; Revenue: 17\n- Name: Echo; Revenue: 19"
    table = "| Name | Revenue |\n|---|---|\n|Delta|17|\n|Echo|19|"
    reference, candidate = (table, records) if reverse else (records, table)
    requirements = _requirements(reference)
    assert len(requirements["business"]) == 4
    score = _grade(reference, candidate)
    assert score["layers"]["B"]["denominator"] == 4
    _require_equal_text(score)


@pytest.mark.parametrize("reverse", [False, True])
def test_unit_schema_word_has_the_same_relation_syntax_policy_in_table_and_record(reverse):
    table = "| Name | Revenue | Unit |\n|---|---|---|\n|Delta|17|万元|"
    record = "Name: Delta; Revenue: 17; Unit: 万元"
    reference, candidate = (record, table) if reverse else (table, record)
    requirements = _requirements(reference)
    assert len(requirements["business"]) == 2
    score = _grade(reference, candidate)
    assert score["layers"]["B"]["denominator"] == 2
    _require_equal_text(score)


def test_role_identity_attribute_does_not_change_the_subject_in_a_table():
    reference = "Name: Delta; Role: CFO; Revenue: 17"
    table = "| Name | Role | Revenue |\n|---|---|---|\n|Delta|CFO|17|"
    requirements = _requirements(reference)
    evidence = read_candidate_markdown(table, sample_id="audit", pipeline="P08")
    oracle = {
        ("identity", "", "Name", "Delta"),
        ("identity", "Delta", "Role", "CFO"),
        ("metric", "Delta", "Revenue", "17"),
    }
    assert len(requirements["business"]) == len(evidence["business"]) == 3
    assert {(f["role"], f["subject"], f["attribute"], f["value"]) for f in requirements["business"]} == oracle
    assert {(f["role"], f["subject"], f["attribute"], f["value"]) for f in evidence["business"]} == oracle
    score = grade_layers(requirements, evidence)
    assert score["publishable"] is True, score["blockers"]
    assert score["layers"]["B"]["numerator"] == score["layers"]["B"]["denominator"] == 3


def test_monetary_unit_qualifies_the_metric_and_does_not_leak_to_another_record():
    requirements = _requirements("Name: Delta; Revenue: 17; Unit: 万元\n\nName: Echo; Headcount: 5")
    facts = requirements["business"]
    assert len(facts) == 4
    assert {(f["subject"], f["attribute"], f["value"]) for f in facts} == {
        ("", "Name", "Delta"), ("Delta", "Revenue", "17"),
        ("", "Name", "Echo"), ("Echo", "Headcount", "5"),
    }
    assert {f["value"]: f["qualifiers"] for f in facts if f["attribute"] == "Name"} == {"Delta": {}, "Echo": {}}
    assert next(f for f in facts if f["attribute"] == "Revenue")["qualifiers"] == {"unit": "万元"}
    assert next(f for f in facts if f["attribute"] == "Headcount")["qualifiers"] == {}


def test_monetary_record_unit_does_not_turn_headcount_into_an_amount():
    requirements = _requirements("Name: Delta; Revenue: 17; Headcount: 5; Unit: 万元")
    facts = requirements["business"]
    assert len(facts) == 3
    assert {(f["subject"], f["attribute"], f["value"]) for f in facts} == {
        ("", "Name", "Delta"), ("Delta", "Revenue", "17"), ("Delta", "Headcount", "5")}
    assert next(f for f in facts if f["attribute"] == "Name")["qualifiers"] == {}
    assert next(f for f in facts if f["attribute"] == "Revenue")["qualifiers"] == {"unit": "万元"}
    assert next(f for f in facts if f["attribute"] == "Headcount")["qualifiers"] == {}


def test_duplicate_header_native_ids_cannot_silently_choose_the_last_business_identity():
    candidate = ('<table><tr><th id="x" scope="col">Revenue</th><th id="x" scope="col">Profit</th>'
                 '</tr><tr><td headers="x">17</td></tr></table>')
    score = _grade("Profit: 17", candidate)
    assert not score["publishable"] or score["layers"]["B"]["numerator"] == 0
    assert not (score["publishable"] and score["layers"]["B"]["score"] == 100)
