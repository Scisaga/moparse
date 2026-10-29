"""Discrete Pareto analysis of existing measurements; no scoring or inference."""

from __future__ import annotations

import math
from typing import Any, TypeGuard


def _finite(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def pareto_partition(rows: list[dict[str, Any]], quality_key: str, *,
                     maximize_quality: bool = False) -> dict[str, Any]:
    """Minimize measured cost and one quality objective, without weighting them.

    Equal coordinates retain all configuration identities. Comparisons use
    unrounded measurements; at least one strict improvement is required.
    Explicitly incomparable measurements never enter the frontier.
    """
    usable = []
    excluded = []
    identities: set[str] = set()
    for row in rows:
        identity = row.get("pipeline")
        if not isinstance(identity, str) or not identity:
            raise ValueError("Pareto input requires a configuration identity")
        if identity in identities:
            raise ValueError("Pareto input contains duplicate configuration identities")
        identities.add(identity)
        cost, quality = row.get("processing_seconds"), row.get(quality_key)
        reason = None
        if row.get("comparison_eligible", True) is not True:
            reason = row.get("comparison_exclusion") or "incomparable_input_or_timing"
        elif not _finite(cost) or cost <= 0:
            reason = "missing_or_invalid_processing_cost"
        elif not _finite(quality):
            reason = "missing_or_nonfinite_quality"
        elif quality < 0 or maximize_quality and quality > 1:
            reason = "quality_out_of_range"
        if reason:
            excluded.append({"pipeline": identity, "reason": reason})
        else:
            usable.append(row)

    dominators: dict[str, list[str]] = {}
    for target in usable:
        better = []
        for candidate in usable:
            lower_cost = candidate["processing_seconds"] <= target["processing_seconds"]
            better_quality = (candidate[quality_key] >= target[quality_key] if maximize_quality
                              else candidate[quality_key] <= target[quality_key])
            strict = (candidate["processing_seconds"] < target["processing_seconds"]
                      or candidate[quality_key] != target[quality_key])
            if lower_cost and better_quality and strict:
                better.append(candidate["pipeline"])
        dominators[target["pipeline"]] = sorted(better)
    ordered = sorted(usable, key=lambda row: (
        row["processing_seconds"], -row[quality_key] if maximize_quality else row[quality_key],
        row["pipeline"],
    ))
    return {
        "quality_metric": quality_key,
        "cost_direction": "minimize",
        "quality_direction": "maximize" if maximize_quality else "minimize",
        "frontier": [row["pipeline"] for row in ordered if not dominators[row["pipeline"]]],
        "dominated": [row["pipeline"] for row in ordered if dominators[row["pipeline"]]],
        "dominated_by": dominators,
        "excluded": excluded,
        "comparison": "unrounded_values_with_at_least_one_strict_improvement",
    }
