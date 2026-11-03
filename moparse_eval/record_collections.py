"""Compare a completely located collection of repeated record identities.

No answer enters localization. Only after every field has the same complete
set of identity-validated source records do we compare whole record vectors.
One matching value cannot rescue a conflicting or extra record.
"""

from __future__ import annotations

from collections import defaultdict

from .information import native_range


def _source_record(alternative):
    selected = alternative.get("selected", [])
    if len(selected) != 1 or selected[0].get("duplicate_native_id"):
        return None
    item = selected[0]
    axis = "col" if alternative.get("orientation") == "transposed" else "row"
    extent = native_range(item["cell"], axis)
    return item["parent_id"], tuple(sorted(extent)) if extent else ()


def _assignment(edges):
    owners = {}

    def assign(identity, seen):
        for key in edges[identity]:
            if key in seen:
                continue
            seen.add(key)
            if key not in owners or assign(owners[key], seen):
                owners[key] = identity
                return True
        return False

    if not all(assign(identity, set()) for identity in edges):
        return None
    return {identity: key for key, identity in owners.items()}


def compare_complete_collections(units, signature, locate, equal):
    """Return field comparisons only for equal, complete record multisets.

    Reordering whole records is harmless. Swapping values between records,
    missing rows, extra contradictory rows and incomplete identity evidence
    cannot satisfy the complete-vector comparison.
    """
    groups = defaultdict(list)
    for unit in units:
        groups[signature(unit)].append(unit)
    resolved = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        views = {}
        source_keys = None
        valid = True
        for unit in group:
            columns = []
            for index, _field in enumerate(unit["table"]["fields"]):
                resolution = locate(unit, index)
                choices = resolution.get("alternatives") or (
                    [resolution] if resolution.get("reason") is None else []
                )
                slots = {}
                for choice in choices:
                    key = _source_record(choice)
                    if key is None or key in slots:
                        valid = False
                        break
                    slots[key] = choice
                if (
                    len(slots) != len(group)
                    or source_keys is not None
                    and set(slots) != source_keys
                ):
                    valid = False
                source_keys = set(slots) if source_keys is None else source_keys
                columns.append((resolution, slots))
            views[unit["id"]] = columns
        if not valid or not source_keys:
            continue
        keys = sorted(source_keys)
        edges = {
            unit["id"]: [
                key
                for key in keys
                if all(
                    equal(unit, index, slots[key])
                    for index, (_resolution, slots) in enumerate(views[unit["id"]])
                )
            ]
            for unit in group
        }
        assignment = _assignment(edges)
        if assignment is None:
            continue
        proof = {
            "method": "complete_record_multiset_equality_after_identity",
            "reference_record_ids": [unit["id"] for unit in group],
            "source_records": [[body, list(rows)] for body, rows in keys],
            "complete_record_assignment": {
                identity: [body, list(rows)] for identity, (body, rows) in assignment.items()
            },
            "extra_or_missing_source_records": False,
        }
        for unit in group:
            for index, (resolution, slots) in enumerate(views[unit["id"]]):
                resolved[unit["id"], index] = {
                    **slots[assignment[unit["id"]]],
                    "reason": None,
                    "diagnostic": {**resolution["diagnostic"], "collection_comparison": proof},
                }
    return resolved
