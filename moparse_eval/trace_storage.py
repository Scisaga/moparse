"""Lossless shared evidence in saved scoring records.

Only storage is changed. Candidate hits, conflicts, ordering, and provenance
are preserved. A reader expands references before any judgment is validated.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

FORMAT = "shared-scoring-evidence"
_REF, _OBJECT = "$trace_ref", "$trace_object"
_MIN_BYTES = 512


def share_evidence(score: dict[str, Any]) -> dict[str, Any]:
    """Intern repeated JSON values; never truncate or select evidence."""
    identities: dict[int, tuple[str, int]] = {}
    frequency: Counter[str] = Counter()
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def signature(value):
        own = id(value)
        if own not in identities:
            digest, length = hashlib.sha256(), 0
            for chunk in encoder.iterencode(value):
                raw = chunk.encode("utf-8")
                digest.update(raw)
                length += len(raw)
            identities[own] = (digest.hexdigest(), length)
        return identities[own]

    def count(value):
        if not isinstance(value, (dict, list, str)):
            return
        digest, length = signature(value)
        if length >= _MIN_BYTES:
            frequency[digest] += 1
        if isinstance(value, dict):
            for item in value.values():
                count(item)
        elif isinstance(value, list):
            for item in value:
                count(item)

    count(score)
    repeated = {key for key, count_ in frequency.items() if count_ > 1}
    if not repeated:
        return score
    catalog: dict[str, Any] = {}

    def encode(value, *, root=False):
        if not isinstance(value, (dict, list, str)):
            return value
        digest, _length = signature(value)
        shared = not root and digest in repeated
        if shared and digest in catalog:
            return {_REF: digest}
        if isinstance(value, dict):
            result = {key: encode(item) for key, item in value.items()}
            if set(result) in ({_REF}, {_OBJECT}):
                result = {_OBJECT: list(result.items())}
        elif isinstance(value, list):
            result = [encode(item) for item in value]
        else:
            result = value
        if shared:
            catalog[digest] = result
            return {_REF: digest}
        return result

    result = encode(score, root=True)
    return {"trace_format": FORMAT, "score": result, "evidence": catalog,
            "storage_policy": "lossless_shared_values_no_hit_or_context_omission"}


def expand_evidence(record: dict[str, Any]) -> dict[str, Any]:
    """Resolve the complete record, rejecting absent or cyclic evidence."""
    if record.get("trace_format") != FORMAT:
        return record
    catalog = record["evidence"]
    resolved: dict[str, Any] = {}
    active: set[str] = set()

    def decode(value):
        if isinstance(value, list):
            return [decode(item) for item in value]
        if not isinstance(value, dict):
            return value
        if set(value) == {_REF}:
            key = value[_REF]
            if key not in catalog:
                raise ValueError("missing shared scoring evidence")
            if key in active:
                raise ValueError("cyclic shared scoring evidence")
            if key not in resolved:
                active.add(key)
                resolved[key] = decode(catalog[key])
                active.remove(key)
            return resolved[key]
        if set(value) == {_OBJECT}:
            return {key: decode(item) for key, item in value[_OBJECT]}
        return {key: decode(item) for key, item in value.items()}

    result = decode(record["score"])
    if not isinstance(result, dict):
        raise ValueError("a saved score must be an object")
    return result


def read_score(path: Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        return expand_evidence(json.load(stream))
