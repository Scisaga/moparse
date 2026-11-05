"""Verify source-bound scalar claims against independently retained raw text.

This validates provenance, not the business answer. Facts and ledgers are not
source authorities; the original cell/fragment snapshots are the only input
used to check a claimed raw value and its numeric subrange.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

_LOCATION_KEYS = ("path", "cell", "native_path", "lines", "block", "block_lines", "row", "col")


def _location(source: dict[str, Any]) -> str:
    return json.dumps({key: source[key] for key in _LOCATION_KEYS if key in source},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bounds(source: dict[str, Any], offset: int, length: int) -> tuple[int, int] | None:
    span = source.get("cell_text_span", source.get("text_span"))
    if span is None:
        return offset, offset + length
    if (not isinstance(span, (list, tuple)) or len(span) != 2 or not all(type(value) is int for value in span)
            or not offset <= span[0] <= span[1] <= offset + length):
        return None
    return span[0], span[1]


def validate_scalar_sources(facts: Iterable[dict[str, Any]], projection: dict[str, Any], *,
                            canonicalize: Callable[[str], str]) -> None:
    """Reject forged scalar sources even when all derived copies agree.

    The contract applies only when a reader declares both ``raw_value`` and a
    precise ``value_source``. Logical predicates, non-scalars and undeclared
    provenance contracts retain their existing guards.
    """
    snapshots: dict[str, list[tuple[str, int]]] | None = None
    checked = set()
    for fact in facts:
        if not isinstance(fact.get("raw_value"), str) or not isinstance(fact.get("value_source"), dict):
            continue
        source, value_source = fact.get("source"), fact["value_source"]
        if (not isinstance(source, dict) or not source.get("path") or not value_source.get("path")
                or not isinstance(fact.get("value"), str)):
            raise ValueError("source-bound scalar lacks a valid original source")
        token = json.dumps([source, value_source, fact["raw_value"], fact["value"]], ensure_ascii=False, sort_keys=True)
        if token in checked:
            continue
        checked.add(token)
        if snapshots is None:
            snapshots = defaultdict(list)
            for item in [*projection.get("source_cells", []), *projection.get("source_fragments", [])]:
                original = item.get("source", {})
                if not original.get("path") or not isinstance(item.get("text"), str):
                    raise ValueError("source-bound scalar needs intact original text snapshots")
                original_span = original.get("cell_text_span", original.get("text_span"))
                offset = original_span[0] if original_span is not None else 0
                if type(offset) is not int:
                    raise ValueError("source-bound scalar has a malformed original source offset")
                snapshots[_location(original)].append((item["text"], offset))
        if _location(source) != _location(value_source):
            raise ValueError("source-bound scalar value_source is outside its own actual field")
        proven = False
        for text, offset in snapshots.get(_location(source), []):
            outer, inner = _bounds(source, offset, len(text)), _bounds(value_source, offset, len(text))
            if outer is None or inner is None or not outer[0] <= inner[0] <= inner[1] <= outer[1]:
                continue
            raw = text[outer[0] - offset:outer[1] - offset]
            value = text[inner[0] - offset:inner[1] - offset]
            if raw == fact["raw_value"] and canonicalize(value) == canonicalize(fact["value"]):
                proven = True
                break
        if not proven:
            raise ValueError("source-bound scalar differs from its original raw value or value subrange")
