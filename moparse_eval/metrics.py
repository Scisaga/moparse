"""Small, explicit metrics for frozen-reference output evaluation.

These functions do not inspect, accept, repair, or write corpus material.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from importlib import import_module
from typing import Any

try:
    _levenshtein: Any = import_module("rapidfuzz.distance.Levenshtein")
except ImportError:  # The isolated parsing workers do not need scoring dependencies.
    _levenshtein = None

TEXT_POLICY = "mo-parse-eval-text-v1"


@lru_cache(maxsize=8192)
def normalize_text(text: str, *, collapse_whitespace: bool = False) -> str:
    """Apply only the declared width policy, optionally folding whitespace."""
    normalized = "".join(
        chr(ord(char) - 0xFEE0)
        if 0xFF01 <= ord(char) <= 0xFF5E
        else " "
        if char == "\u3000"
        else char
        for char in text
    )
    return re.sub(r"\s+", " ", normalized).strip() if collapse_whitespace else normalized


def edit_counts(reference: str, hypothesis: str) -> dict[str, int]:
    """Return a deterministic minimum-edit alignment, including S/D/I counts.

    Pinned RapidFuzz supplies the production alignment and tie policy. The
    dependency-free fallback prefers substitution, deletion, then insertion;
    it preserves total distance but its tied S/D/I breakdown may differ.
    """
    reference_length, hypothesis_length = len(reference), len(hypothesis)
    if _levenshtein is not None:
        operations = _levenshtein.editops(reference, hypothesis)
        counts = {"replace": 0, "delete": 0, "insert": 0}
        for operation in operations:
            counts[operation.tag] += 1
        return {
            "distance": len(operations),
            "substitutions": counts["replace"],
            "deletions": counts["delete"],
            "insertions": counts["insert"],
            "reference_chars": reference_length,
            "hypothesis_chars": hypothesis_length,
        }
    prefix = 0
    limit = min(reference_length, hypothesis_length)
    while prefix < limit and reference[prefix] == hypothesis[prefix]:
        prefix += 1
    reference, hypothesis = reference[prefix:], hypothesis[prefix:]
    suffix = 0
    limit = min(len(reference), len(hypothesis))
    while suffix < limit and reference[-suffix - 1] == hypothesis[-suffix - 1]:
        suffix += 1
    if suffix:
        reference, hypothesis = reference[:-suffix], hypothesis[:-suffix]
    # Each tuple is (distance, substitutions, deletions, insertions).
    previous = [(index, 0, 0, index) for index in range(len(hypothesis) + 1)]
    for row, reference_char in enumerate(reference, 1):
        current = [(row, 0, row, 0)]
        for column, hypothesis_char in enumerate(hypothesis, 1):
            diagonal = previous[column - 1]
            if reference_char == hypothesis_char:
                current.append(diagonal)
                continue
            above, left = previous[column], current[column - 1]
            options = [
                (diagonal[0] + 1, diagonal[1] + 1, diagonal[2], diagonal[3]),
                (above[0] + 1, above[1], above[2] + 1, above[3]),
                (left[0] + 1, left[1], left[2], left[3] + 1),
            ]
            current.append(min(options, key=lambda item: item[0]))
        previous = current
    distance, substitutions, deletions, insertions = previous[-1]
    return {
        "distance": distance,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "reference_chars": reference_length,
        "hypothesis_chars": hypothesis_length,
    }


def ratios_from_counts(counts: dict[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = dict(counts)
    distance = counts["distance"]
    reference_chars, hypothesis_chars = counts["reference_chars"], counts["hypothesis_chars"]
    maximum = max(reference_chars, hypothesis_chars)
    result["cer"] = distance / reference_chars if reference_chars else None
    result["normalized_edit_distance"] = distance / maximum if maximum else None
    result["similarity"] = 1 - distance / maximum if maximum else None
    return result


def text_metrics(
    reference: str, hypothesis: str, *, collapse_whitespace: bool = False
) -> dict[str, Any]:
    """Keep strict diagnostics alongside the width-equivalent comparison."""
    return {
        "policy": TEXT_POLICY,
        "collapse_whitespace": collapse_whitespace,
        "strict": ratios_from_counts(edit_counts(reference, hypothesis)),
        "width_equivalent": ratios_from_counts(
            edit_counts(
                normalize_text(reference, collapse_whitespace=collapse_whitespace),
                normalize_text(hypothesis, collapse_whitespace=collapse_whitespace),
            )
        ),
    }


def aggregate_text_metrics(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(items)
    keys = ("distance", "substitutions", "deletions", "insertions", "reference_chars", "hypothesis_chars")
    return {
        "policy": TEXT_POLICY,
        "units": len(items),
        "strict": ratios_from_counts(
            {key: sum(item["strict"][key] for item in items) for key in keys}
        ),
        "width_equivalent": ratios_from_counts(
            {key: sum(item["width_equivalent"][key] for item in items) for key in keys}
        ),
    }


def precision_recall_f1(tp: int, fp: int | None, fn: int) -> dict[str, Any]:
    """Use NA when no output denominator or exhaustive annotation exists."""
    target = tp + fn
    precision = tp / (tp + fp) if fp is not None and tp + fp else None
    recall = tp / target if target else None
    f1_denominator = 2 * tp + fp + fn if fp is not None else None
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "target_units": target,
        "output_units": tp + fp if fp is not None else None,
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / f1_denominator if f1_denominator else None,
    }


def fraction(numerator: int, denominator: int, **details: Any) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
        **details,
    }
