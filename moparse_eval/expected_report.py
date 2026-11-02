"""Reproduce expected-only reports from complete programmatic score outputs."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .expected_evaluation import (
    PIPELINES,
    adoption_status,
    native_preservation,
    paired_changes,
    summarize,
)
from .expected_scoring import PROTOCOL, require_paired_targets
from .packaging import inside, read_json
from .prose_metrics import summarize_text
from .target_coverage import require_complete_ranges


def first_failure_stage(group: str, outcome: dict[str, Any], native: dict[str, Any] | None) -> str:
    """Report the first observed failing output, without inventing an SDK cause."""
    if outcome["outcome"] == "correct":
        return "none"
    if group in PIPELINES:
        return "native_output"
    if native is None:
        raise ValueError("final-output error attribution requires the paired native target")
    return "native_output" if native["outcome"] == "incorrect" else "final_markdown_conversion"


def load_complete(index_path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    index = read_json(index_path)
    if (index.get("state") != "completed" or index.get("expected_comparison_complete") is not True
            or index.get("protocol") != PROTOCOL):
        raise ValueError("a complete expected-only evaluation is required before report publication")
    if index.get("validation", {}).get("known_reader_defects"):
        raise ValueError("known reader defects must be repaired before report publication")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen = set()
    for record in index["records"]:
        score = read_json(inside(index_path.parent, record["path"]))
        key = record["group"], record["sample_id"]
        if key in seen or score.get("sample_id") != record["sample_id"]:
            raise ValueError("duplicate or mismatched evaluated sample")
        seen.add(key)
        if score.get("protocol") != index["protocol"]:
            raise ValueError("mixed scoring protocols cannot be published")
        if score.get("scoring_software_id") != index["software"]["software_id"]:
            raise ValueError("mixed scoring software cannot be published")
        decisions = score["outcomes"]
        expected_counts = {kind: {"targets": sum(row["kind"] == kind for row in decisions),
            **{state: sum(row["kind"] == kind and row["outcome"] == state for row in decisions)
               for state in ("correct", "incorrect")}} for kind in {row["kind"] for row in decisions}}
        if (expected_counts != score["by_kind"] or score["correct"] != sum(row["outcome"] == "correct" for row in decisions)
                or score["incorrect"] != sum(row["outcome"] == "incorrect" for row in decisions)
                or score.get("text_metrics") != summarize_text(decisions)):
            raise ValueError("score aggregate differs from its target decisions")
        require_complete_ranges(score.get("content_coverage", {}).get("ranges", []), score["outcomes"])
        if score.get("content_coverage", {}).get("method") != "complete_literal_partition_plus_explicit_business_requirements":
            raise ValueError("expected literal ranges and requirements were not fully traced")
        groups[record["group"]].append(score)
        samples[record["sample_id"]].append(score)
    if set(groups) != set(index["groups"]):
        raise ValueError("a declared comparison group is missing")
    if set(samples) != {row["sample_id"] for row in index["coverage"]}:
        raise ValueError("declared expected coverage and evaluated samples differ")
    for scores in samples.values():
        if len(scores) != len(groups):
            raise ValueError("all groups must cover every declared sample")
        require_paired_targets(scores)
    for coverage in index["coverage"]:
        for score in samples[coverage["sample_id"]]:
            if (score["targets"] != coverage["targets"] or score.get("content_coverage", {}).get("omitted_elements") != 0
                    or score["content_coverage"]["compared_elements"] != score["content_coverage"]["expected_elements"]):
                raise ValueError("expected content comparison is incomplete")
    for group, scores in groups.items():
        if summarize(scores) != index["summary"][group]:
            raise ValueError("aggregate differs from the actual target decisions")
    preservation = {p: native_preservation(groups[p], groups[f"{p}-current"])
                    for p in ("P07", "P08") if f"{p}-current" in groups}
    changes = {p: paired_changes(groups[f"{p}-baseline"], groups[f"{p}-current"])
               for p in preservation if f"{p}-baseline" in groups}
    if index.get("adoption", {}) != adoption_status(changes, preservation):
        raise ValueError("adoption gates differ from the actual native and final decisions")
    return index, dict(groups)
