"""Whole-claim table ownership regressions using synthetic in-memory records."""

from __future__ import annotations

import copy

import pytest

from moparse_eval.scoring import score_case

SOURCE_FRAGMENTS = ("Source alpha fragment.", "Source beta fragment.")
TARGET_FRAGMENTS = ("Target gamma fragment.", "Target delta fragment.")


def _inputs(source_parents, target_parents, kind):
    reference = {
        "sample_id": "synthetic", "review_status": "confirmed",
        "units": [
            {"id": "source", "kind": "text", "literal": " ".join(SOURCE_FRAGMENTS[:len(source_parents)]),
             "status": "confirmed", "pages": [1]},
            {"id": "target", "kind": "text", "literal": " ".join(TARGET_FRAGMENTS[:len(target_parents)]),
             "status": "confirmed", "pages": [1]},
        ],
        "relations": [{"type": kind, "source": "source", "target": "target", "status": "confirmed"}],
    }
    blocks = []
    for prefix, parents, fragments in (
        ("source", source_parents, SOURCE_FRAGMENTS), ("target", target_parents, TARGET_FRAGMENTS),
    ):
        for index, parent in enumerate(parents):
            block = {"id": f"{prefix}-{index}", "text": fragments[index],
                     "kind": "table_footnote" if parent is not None else "text"}
            if parent is not None:
                block["parent_id"] = parent
            blocks.append(block)
    table_ids = sorted({parent for parent in (*source_parents, *target_parents) if parent is not None})
    observation = {
        "sample_id": "synthetic", "pipeline": "P-synthetic", "status": "completed",
        "pages": [{"page": 1, "blocks": blocks}],
        "native_containers": [{"id": identity, "kind": "table", "label": "table"} for identity in table_ids],
        "relations": [{"type": kind, "source": source_parents[0], "target": target_parents[0],
                       "evidence": "synthetic_explicit_table_pair"}],
        "timing": {"processing_seconds": 1.5},
    }
    return reference, observation


def _score_unchanged(reference, observation):
    before = copy.deepcopy((reference, observation))
    result = score_case(reference, observation)
    assert (reference, observation) == before
    assert result["metrics"]["unit_presence"]["recall"] == 1
    assert result["timing"] == {"processing_seconds": 1.5}
    return result, {row["id"]: row for row in result["units"]}


@pytest.mark.parametrize("kind", ["continues", "separate"])
@pytest.mark.parametrize("source_parents,target_parents", [
    (("T1", "T2"), ("T3",)),
    (("T1",), ("T3", "T4")),
    (("T1", "T2"), ("T3", "T4")),
], ids=["source-crosses-tables", "target-crosses-tables", "both-cross-tables"])
def test_favorable_first_claim_cannot_establish_a_pair_for_a_cross_table_stream(
    kind, source_parents, target_parents,
):
    reference, observation = _inputs(source_parents, target_parents, kind)
    result, units = _score_unchanged(reference, observation)
    assert len(units["source"]["match"]["claims"]) == len(source_parents)
    assert len(units["target"]["match"]["claims"]) == len(target_parents)
    relation = result["relations"][0]
    assert relation["correct"] is False
    assert relation["observable"] is False
    assert result["metrics"]["relations"]["target_units"] == 1
    assert result["metrics"]["relations"]["tp"] == 0


@pytest.mark.parametrize("kind", ["continues", "separate"])
@pytest.mark.parametrize("source_parents,target_parents", [
    (("T1", None), ("T3",)),
    (("T1",), ("T3", None)),
    (("T1", None), ("T3", None)),
], ids=["source-has-ordinary-prose", "target-has-ordinary-prose", "both-have-ordinary-prose"])
def test_table_claim_mixed_with_ordinary_prose_does_not_borrow_the_table_pair(
    kind, source_parents, target_parents,
):
    reference, observation = _inputs(source_parents, target_parents, kind)
    result, units = _score_unchanged(reference, observation)
    assert len(units["source"]["match"]["claims"]) == len(source_parents)
    assert len(units["target"]["match"]["claims"]) == len(target_parents)
    assert result["relations"][0]["correct"] is False
    assert result["relations"][0]["observable"] is False


@pytest.mark.parametrize("kind", ["continues", "separate"])
def test_multiple_footnote_blocks_per_endpoint_keep_their_unique_table_pair(kind):
    reference, observation = _inputs(("T1", "T1"), ("T3", "T3"), kind)
    result, units = _score_unchanged(reference, observation)
    assert len(units["source"]["match"]["claims"]) == 2
    assert len(units["target"]["match"]["claims"]) == 2
    assert result["relations"][0]["correct"] is True
    assert result["relations"][0]["observable"] is True


@pytest.mark.parametrize("kind", ["continues", "separate"])
def test_multiple_native_cells_do_not_confuse_cell_or_body_ids_with_real_table_ownership(kind):
    reference, observation = _inputs(("T1", "T1"), ("T3", "T3"), kind)
    observation["pages"][0]["blocks"] = [
        {"id": "body-left", "kind": "table_body", "parent_id": "T1", "native_table_container": "T1",
         "cells": [
             {"id": "source-cell-a", "row": 0, "col": 0, "text": SOURCE_FRAGMENTS[0]},
             {"id": "source-cell-b", "row": 0, "col": 1, "text": SOURCE_FRAGMENTS[1]},
         ]},
        {"id": "body-right", "kind": "table_body", "parent_id": "T3", "native_table_container": "T3",
         "cells": [
             {"id": "target-cell-a", "row": 0, "col": 0, "text": TARGET_FRAGMENTS[0]},
             {"id": "target-cell-b", "row": 0, "col": 1, "text": TARGET_FRAGMENTS[1]},
         ]},
    ]
    result, units = _score_unchanged(reference, observation)
    assert {claim["candidate_id"] for claim in units["source"]["match"]["claims"]} == {
        "source-cell-a", "source-cell-b",
    }
    assert {claim["candidate_id"] for claim in units["target"]["match"]["claims"]} == {
        "target-cell-a", "target-cell-b",
    }
    assert result["relations"][0]["correct"] is True
    assert result["relations"][0]["observable"] is True


@pytest.mark.parametrize("kind", ["continues", "separate", "references"])
def test_explicit_relations_between_ordinary_non_table_claims_keep_existing_behavior(kind):
    reference, observation = _inputs((None, None), (None, None), kind)
    observation["relations"] = [
        {"type": kind, "source": f"source-{left}", "target": f"target-{right}",
         "evidence": "synthetic_explicit_text_relation"}
        for left in range(2) for right in range(2)
    ]
    result, units = _score_unchanged(reference, observation)
    assert len(units["source"]["match"]["claims"]) == 2
    assert len(units["target"]["match"]["claims"]) == 2
    assert result["relations"][0]["correct"] is True
    assert result["relations"][0]["observable"] is True
    assert result["relations"][0]["evidence"] == "explicit_native_relation"


@pytest.mark.parametrize("body_kind", ["table_body", "table"])
@pytest.mark.parametrize("container_reference", ["explicit", "parent_only"])
def test_distinct_body_ids_with_multiple_cells_in_one_table_do_not_prove_separation(
    body_kind, container_reference,
):
    reference, observation = _inputs(("T1", "T1"), ("T1", "T1"), "continues")
    reference["relations"].append({
        "type": "separate", "source": "source", "target": "target", "status": "confirmed",
    })
    observation["relations"] = []
    observation["pages"][0]["blocks"] = [
        {"id": "body-left", "kind": body_kind, "parent_id": "T1", "native_table_container": "T1",
         "cells": [
             {"id": "source-cell-a", "row": 0, "col": 0, "text": SOURCE_FRAGMENTS[0]},
             {"id": "source-cell-b", "row": 0, "col": 1, "text": SOURCE_FRAGMENTS[1]},
         ]},
        {"id": "body-right", "kind": body_kind, "parent_id": "T1", "native_table_container": "T1",
         "cells": [
             {"id": "target-cell-a", "row": 1, "col": 0, "text": TARGET_FRAGMENTS[0]},
             {"id": "target-cell-b", "row": 1, "col": 1, "text": TARGET_FRAGMENTS[1]},
         ]},
    ]
    if container_reference == "parent_only":
        for block in observation["pages"][0]["blocks"]:
            block.pop("native_table_container")
    result, units = _score_unchanged(reference, observation)
    assert len(units["source"]["match"]["claims"]) == 2
    assert len(units["target"]["match"]["claims"]) == 2
    relations = {row["type"]: row for row in result["relations"]}
    assert relations["continues"]["observable"] is True and relations["continues"]["correct"] is True
    assert relations["separate"]["observable"] is True and relations["separate"]["correct"] is False
