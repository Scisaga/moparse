"""One current three-layer scoring entry point; no legacy grading fallback."""

from __future__ import annotations

from typing import Any

from .three_layer import PROTOCOL, grade_expected

__all__ = ["PROTOCOL", "grade_expected", "require_paired_targets"]


def require_paired_targets(scores: list[dict[str, Any]]) -> None:
    """All output groups must use identical independent requirements."""
    if not scores:
        raise ValueError("paired comparison requires scored samples")
    def targets(score):
        return [(row["layer"], row["id"], row["role"], row["expected"]) for row in score["outcomes"]]
    reference = targets(scores[0])
    if any(targets(score) != reference for score in scores[1:]):
        raise ValueError("paired outputs use different requirements or scope")
