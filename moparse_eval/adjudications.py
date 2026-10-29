"""Consume explicit human scoring exclusions without changing frozen references.

This is not a reference reviewer. The caller supplies source-backed judgments;
this module only enforces their uniform scoring scope and supported operation.
"""

from __future__ import annotations

from typing import Any


def reference_exclusions(record: dict[str, Any], sample_id: str) -> dict[str, dict[str, Any]]:
    if record.get("scope") != "all_configurations_and_repetitions":
        raise ValueError("human reference adjudications must apply to all configurations and repetitions")
    if not record.get("id"):
        raise ValueError("human reference adjudications need an explicit record ID")
    exclusions: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, str]] = set()
    decision_ids: set[str] = set()
    for item in record.get("decisions", []):
        if item.get("action") != "exclude_unit_pending":
            raise ValueError("only explicit human pending-unit exclusions are supported")
        if any(key in item for key in (
            "pipeline", "pipelines", "repetition", "suite", "replacement", "literal", "reference_text",
        )):
            raise ValueError("human reference exclusions cannot select outputs or replace answers")
        if not all(item.get(key) for key in ("id", "sample_id", "unit_id", "reviewers", "reason", "evidence")):
            raise ValueError("human reference exclusions need identities, reviewers, reason and source evidence")
        key = (item["sample_id"], item["unit_id"])
        if key in seen:
            raise ValueError("duplicate human scoring exclusion")
        if item["id"] in decision_ids:
            raise ValueError("human scoring decision IDs must be unique")
        seen.add(key)
        decision_ids.add(item["id"])
        if item["sample_id"] == sample_id:
            exclusions[item["unit_id"]] = {"record_id": record["id"], **item}
    return exclusions
