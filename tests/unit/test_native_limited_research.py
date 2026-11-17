"""Invented, source-only evidence for the research projection, never a parser."""

from copy import deepcopy

import pytest

from scripts.native_limited_research import aggregate, build_common, classify, digest, summarize


def fixture_scope():
    graph = {
        "text": [{"id": "t", "text": "代号 A17", "source": {"path": "invented", "lines": [1, 1]}}],
        "relations": [], "business": [{"id": "b", "role": "metric", "value": "17"}],
        "source_form_requirements": [{"role": "text", "block_index": 0,
            "requirement_id": "content:0", "source": {"path": "invented", "text_span": [0, 3]}}],
        "source_form_order_anchors": [],
        "comparison_coverage": {"source_complete": True, "structure_complete": True,
            "responsibility_complete": True, "retained_semantic_requirements": {"L": [], "B": ["b"]}},
    }
    inventories = {"invented": {"requirement_ids": {"T": ["t"], "L": ["L:content:0"],
        "B": ["b", "B:content:0"]}, "denominators": {"T": 5, "L": 1, "B": 2}}}
    common = build_common({"invented": graph}, inventories)
    scores = {}
    for p in range(1, 9):
        pipeline = f"P{p:02}"
        scores["invented", pipeline] = {
            "sample_id": "invented", "pipeline": pipeline, "benchmark": "native",
            "layers": {layer: {"denominator": n} for layer, n in inventories["invented"]["denominators"].items()},
            "outcomes": [
                {"id": "t", "layer": "T", "outcome": "correct", "edits": {"S": 0, "D": 0, "I": 0}},
                {"id": "L:content:0", "layer": "L", "outcome": "correct"},
                {"id": "b", "layer": "B", "outcome": "correct"},
                {"id": "B:content:0", "layer": "B", "outcome": "correct"},
            ],
        }
    return graph, inventories, common, scores


def test_set_uses_reference_capability_and_character_intervals():
    _, _, common, _ = fixture_scope()
    assert common["original_denominators"] == {"T": 5, "L": 1, "B": 2}
    assert common["common_denominators"] == {"T": 5, "L": 1, "B": 1}
    text = common["records"][0]
    assert text["canonical_text"] == "代号A17"


def test_candidates_cannot_choose_membership_or_remove_errors():
    graph, inventories, common, scores = fixture_scope()
    before = digest(common)
    scores["invented", "P01"]["outcomes"][2].update(outcome="incorrect", actual=None)
    result = aggregate(common, scores, inventories)
    row = next(r for r in result["rows"] if r["pipeline"] == "P01" and r["layer"] == "B")
    assert row["N_common"] == 1 and row["incorrect"] == 1 and row["candidate_missing"] == 0
    assert before == digest(build_common({"invented": graph}, inventories))


def test_full_responsibility_and_exact_copy_exclusions_survive():
    _, inventories, common, scores = fixture_scope()
    snapshot = deepcopy(scores)
    result = aggregate(common, scores, inventories)
    assert scores == snapshot
    assert len(result["requirement_records"]) == 32
    row = next(r for r in result["rows"] if r["layer"] == "B")
    assert row["excluded"] == 1 and row["N_common"] == 1
    assert row["independent_full_responsibility"]["N_original"] == 2


@pytest.mark.parametrize("mutation", ["missing_pipeline", "missing_requirement", "duplicate_requirement", "denominator", "foreign_stage"])
def test_rejects_incomplete_or_drifted_comparisons(mutation):
    _, inventories, common, scores = fixture_scope()
    score = scores["invented", "P01"]
    if mutation == "missing_pipeline":
        del scores["invented", "P08"]
    elif mutation == "missing_requirement":
        score["outcomes"].pop()
    elif mutation == "duplicate_requirement":
        score["outcomes"].append(deepcopy(score["outcomes"][0]))
    elif mutation == "denominator":
        score["layers"]["B"]["denominator"] = 1
    else:
        score["benchmark"] = "product"
    with pytest.raises(ValueError):
        aggregate(common, scores, inventories)


@pytest.mark.parametrize("reason,category", [
    ("no_proved_native_parent_chain_for_this_relation", "native_relation_unknown"),
    ("native_arrays_or_bbox_do_not_supply_global_reading_order", "native_relation_unknown"),
    ("existing_comparison_limit:document_block_identity_ambiguous", "correspondence_not_proved"),
])
def test_native_unknown_is_neither_missing_nor_a_software_exception(reason, category):
    decision = classify({"layer": "L", "outcome": "unresolved", "software_failure": True,
                         "research_limitation": reason})
    assert decision["state"] == "unresolved" and decision["category"] == category
    assert not decision["candidate_missing"]


def test_unsupported_legitimate_expression_is_software_blocked():
    decision = classify({"layer": "B", "outcome": "unresolved", "software_failure": True,
        "research_limitation": "existing_comparison_limit:wording_change_requires_semantic_comparison"})
    assert decision["state"] == "software_blocked"
    stats = summarize([{"weight": 1, **decision}], "B")
    assert stats["software_blocked"] == 1 and stats["incorrect"] == 0
    assert stats["lower_bound"] is None and stats["upper_bound"] is None


def test_proved_absence_is_an_error_and_stays_in_denominator():
    decision = classify({"layer": "B", "outcome": "incorrect",
                         "correspondence": {"absence_proven": True}})
    stats = summarize([{"weight": 1, **decision}], "B")
    assert stats["N_common"] == stats["incorrect"] == stats["candidate_missing"] == 1
    assert stats["coverage"] == 1 and stats["lower_bound"] == stats["upper_bound"] == 0


def test_unlocated_text_does_not_establish_absence():
    decision = classify({"layer": "T", "outcome": "incorrect", "actual": None,
                         "correspondence": {"status": "unlocated", "absence_proven": False}})
    assert decision["state"] == "unresolved" and not decision["candidate_missing"]


def test_T_weights_existing_character_ledger_including_insertions():
    records = [
        {"weight": 100, "state": "incorrect", "candidate_missing": False,
         "edits": {"S": 1, "D": 2, "I": 3}},
        {"weight": 10, "state": "unresolved", "candidate_missing": False},
    ]
    result = summarize(records, "T")
    assert (result["N_common"], result["correct"], result["incorrect"], result["unresolved"]) == (110, 94, 6, 10)
    assert result["lower_bound"] == 94 / 110 and result["upper_bound"] == 104 / 110
    assert result["trusted_edits"] == {"S": 1, "D": 2, "I": 3}


def test_T_large_insertion_uses_existing_zero_floor_without_new_votes():
    result = summarize([{"weight": 2, "state": "incorrect", "candidate_missing": False,
                         "edits": {"I": 20}}], "T")
    assert result["N_common"] == result["incorrect"] == 2 and result["correct"] == 0


def test_expected_responsibility_cannot_be_silently_admitted():
    graph, inventories, _, _ = fixture_scope()
    graph["comparison_coverage"]["responsibility_complete"] = False
    with pytest.raises(ValueError):
        build_common({"invented": graph}, inventories)
