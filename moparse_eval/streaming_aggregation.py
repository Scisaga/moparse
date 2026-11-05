"""Pool validated saved scores without retaining their full evidence graphs.

Records must be contiguous by sample. Only one expanded score is read at a
time; the current sample retains requirement digests and binary decisions.
Pair details point to complete saved outcomes instead of copying their text.
This formal-only entry point rejects blocked or withheld software judgments.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .layer_aggregation import LAYERS, summarize_layers
from .trace_storage import read_score

_ENCODER = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    result = hashlib.sha256()
    for chunk in _ENCODER.iterencode(value):
        result.update(chunk.encode("utf-8"))
    return result.hexdigest()


@dataclass(frozen=True, slots=True)
class _Decision:
    meaning: str
    outcome: str
    root: str | None


@dataclass(frozen=True, slots=True)
class _CompactScore:
    sample_id: str
    path: str
    summary: dict[str, Any]
    decisions: dict[str, dict[str, _Decision]]
    target_order: tuple[tuple[str, str], ...]
    scope: str


def _compact(score: Mapping[str, Any], record: Mapping[str, Any]) -> _CompactScore:
    summary = summarize_layers([score])
    if score["sample_id"] != record["sample_id"]:
        raise ValueError("score identity differs from its declared sample metadata")
    decisions = {layer: {} for layer in LAYERS}
    order = []
    for row in score["outcomes"]:
        meaning = _digest({key: row.get(key) for key in ("role", "expected", "reference")})
        root = row.get("root_cause") or row.get("root_cause_id")
        decisions[row["layer"]][row["id"]] = _Decision(meaning, row["outcome"], root if isinstance(root, str) else None)
        order.append((row["layer"], row["id"]))
    scope = _digest({key: score.get(key) for key in ("document_id", "family_id", "source_pages", "expected_scope")})
    return _CompactScore(score["sample_id"], record["path"], summary, decisions, tuple(order), scope)


def _empty_totals() -> dict[str, Any]:
    return {"samples": 0, "layers": {layer: {"numerator": 0, "denominator": 0, "complete": True,
            "applicable_samples": 0, "not_applicable_samples": 0} for layer in LAYERS}}


def _add_totals(totals: dict[str, Any], sample: _CompactScore) -> None:
    totals["samples"] += 1
    for layer in LAYERS:
        row, incoming = totals["layers"][layer], sample.summary["layers"][layer]
        for key in ("numerator", "denominator", "applicable_samples", "not_applicable_samples"):
            row[key] += incoming[key]


def _finish_totals(totals: dict[str, Any]) -> dict[str, Any]:
    for layer, row in totals["layers"].items():
        denominator, numerator = row["denominator"], row["numerator"]
        row["score"] = None if denominator == 0 else 100.0 * (max(0, numerator) if layer == "T" else numerator) / denominator
    values = [totals["layers"][layer]["score"] for layer in LAYERS]
    applicable = all(value is not None for value in values)
    totals.update(score=sum(values) / 3 if applicable else None, publishable=applicable, blockers=[])
    return totals


def _require_same_targets(left: _CompactScore, right: _CompactScore) -> None:
    if left.scope != right.scope or left.target_order != right.target_order:
        raise ValueError("output groups changed frozen target identities, order or scope")
    for layer in LAYERS:
        if left.summary["layers"][layer]["denominator"] != right.summary["layers"][layer]["denominator"]:
            raise ValueError("output groups changed a fixed layer requirement denominator")
        if any(left.decisions[layer][ident].meaning != right.decisions[layer][ident].meaning for ident in left.decisions[layer]):
            raise ValueError("paired target meaning, role or reference changed")


def _default_comparisons(groups: tuple[str, ...]) -> dict[str, dict[str, tuple[str, str]]]:
    result = {}
    for number in range(1, 9):
        pipeline = f"P{number:02}"
        pairs = {}
        if pipeline in groups and pipeline + "-current" in groups:
            pairs["native_to_current"] = pipeline, pipeline + "-current"
        if pipeline in {"P07", "P08"}:
            if pipeline in groups and pipeline + "-baseline" in groups:
                pairs["native_to_baseline"] = pipeline, pipeline + "-baseline"
            if pipeline + "-baseline" in groups and pipeline + "-current" in groups:
                pairs["baseline_to_current"] = pipeline + "-baseline", pipeline + "-current"
        if pairs:
            result[pipeline] = pairs
    return result


def _empty_pair() -> dict[str, Any]:
    return {"samples": 0, "layers": {layer: {"gains": [], "losses": [], "remaining_incorrect": []} for layer in LAYERS},
            "roots": {}}


def _add_pair(pair: dict[str, Any], left: _CompactScore, right: _CompactScore) -> None:
    pair["samples"] += 1
    for layer in LAYERS:
        for ident in sorted(left.decisions[layer]):
            old, new = left.decisions[layer][ident], right.decisions[layer][ident]
            if old.outcome == new.outcome == "correct":
                continue
            reference = {"sample_id": left.sample_id, "layer": layer, "id": ident,
                         "before": {"path": left.path, "outcome_id": ident},
                         "after": {"path": right.path, "outcome_id": ident}}
            if old.outcome != new.outcome:
                pair["layers"][layer]["gains" if new.outcome == "correct" else "losses"].append(reference)
            if new.outcome == "incorrect":
                pair["layers"][layer]["remaining_incorrect"].append(reference)
                if new.root is not None:
                    pair["roots"].setdefault(new.root, set()).add((left.sample_id, layer, ident))


def _path(base: Path, raw: str) -> Path:
    relative = Path(raw)
    if relative.is_absolute() or not (base / relative).resolve().is_relative_to(base.resolve()):
        raise ValueError("score path must stay inside the declared scoring output directory")
    return base / relative


def aggregate_score_files(
    records: Iterable[Mapping[str, Any]], *, groups: Iterable[str], base_dir: Path | str,
    reader: Callable[[Path], dict[str, Any]] = read_score,
    comparisons: Mapping[str, Mapping[str, tuple[str, str]]] | None = None,
    expected_sample_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Consume one sample cohort at a time and retain only outcome references.

    ``groups`` declares all required groups for every sample. Supplying
    ``expected_sample_ids`` also proves complete declared sample coverage at
    EOF. Missing scope, duplicate records, software-version differences and
    reader/validation failures raise; no partial summary is returned.
    """
    group_order = tuple(groups)
    if not group_order or any(not isinstance(group, str) or not group for group in group_order) or len(set(group_order)) != len(group_order):
        raise ValueError("declared score groups must be nonempty and unique")
    declared_samples = set(expected_sample_ids) if expected_sample_ids is not None else None
    if declared_samples is not None and (not declared_samples or any(not isinstance(sample, str) or not sample for sample in declared_samples)):
        raise ValueError("declared sample scope must contain nonempty identities")
    links = comparisons if comparisons is not None else _default_comparisons(group_order)
    for pairs in links.values():
        for endpoints in pairs.values():
            if len(endpoints) != 2 or any(group not in group_order for group in endpoints):
                raise ValueError("every comparison requires two declared score groups")
    totals = {group: _empty_totals() for group in group_order}
    details = {pipeline: {kind: _empty_pair() for kind in pairs} for pipeline, pairs in links.items()}
    coverage, finished, current = [], set(), {}
    sample_id = software = protocol = None
    processed = 0

    def close_sample():
        if set(current) != set(group_order):
            raise ValueError("sample cohort does not cover every declared output group")
        first = current[group_order[0]]
        for sample in current.values():
            _require_same_targets(first, sample)
        for pipeline, pairs in links.items():
            for kind, (before, after) in pairs.items():
                _add_pair(details[pipeline][kind], current[before], current[after])
        coverage.append({"sample_id": first.sample_id, "groups_traversed": len(current),
                         "layers": {layer: {"denominator": first.summary["layers"][layer]["denominator"]} for layer in LAYERS}})
        finished.add(first.sample_id)
        current.clear()

    for record in records:
        if not isinstance(record, Mapping) or any(not isinstance(record.get(key), str) or not record[key] for key in ("sample_id", "group", "path")):
            raise ValueError("every score file requires group, sample identity and path metadata")
        incoming = record["sample_id"]
        if record["group"] not in totals:
            raise ValueError("score record belongs to an undeclared output group")
        if sample_id is not None and incoming != sample_id:
            close_sample()
        if incoming in finished:
            raise ValueError("a completed sample cannot reenter the one-shot score stream")
        if declared_samples is not None and incoming not in declared_samples:
            raise ValueError("score sample lies outside the declared comparison scope")
        sample_id = incoming
        if record["group"] in current:
            raise ValueError("duplicate scored sample/group cannot enlarge a denominator")
        score = reader(_path(Path(base_dir), record["path"]))
        identity = score.get("scoring_software_id")
        if identity is not None:
            if not isinstance(identity, str) or not identity or software is not None and software != identity:
                raise ValueError("saved score software versions differ")
            software = identity
        if score.get("protocol") is not None:
            incoming_protocol = _digest(score["protocol"])
            if protocol is not None and protocol != incoming_protocol:
                raise ValueError("saved score protocols differ")
            protocol = incoming_protocol
        compact = _compact(score, record)
        del score  # Do not retain a full previous score while reading its successor.
        current[record["group"]] = compact
        _add_totals(totals[record["group"]], compact)
        processed += 1
    if sample_id is None:
        raise ValueError("an empty score stream cannot establish comparison scope")
    close_sample()
    if declared_samples is not None and finished != declared_samples:
        raise ValueError("the score stream omitted part of the declared sample scope")
    summary = {group: _finish_totals(value) for group, value in totals.items()}
    paired = {}
    for pipeline, pairs in links.items():
        paired[pipeline] = {}
        for kind, (before, after) in pairs.items():
            pair = details[pipeline][kind]
            pair.update(before=summary[before], after=summary[after],
                        meaning="observed_same_target_changes_not_independent_recognition_error_counts")
            for layer, row in pair["layers"].items():
                row.update(new_correct=len(row["gains"]), lost_correct=len(row["losses"]),
                           remaining_defects=len(row["remaining_incorrect"]),
                           before=summary[before]["layers"][layer], after=summary[after]["layers"][layer])
            roots = pair.pop("roots")
            pair["shared_root_causes"] = {
                root: [{"sample_id": sample, "layer": layer, "id": ident} for sample, layer, ident in sorted(members)]
                for root, members in sorted(roots.items())}
            paired[pipeline][kind] = {layer: {"new_correct": row["new_correct"], "lost_correct": row["lost_correct"],
                "remaining_incorrect": row["remaining_defects"], "required_units": row["after"]["denominator"]}
                for layer, row in pair["layers"].items()}
    return {"summary": summary, "paired": paired, "paired_details": details, "coverage": coverage,
            "records_processed": processed, "publishable": all(item["publishable"] for item in summary.values()),
            "declared_scope_checked": declared_samples is not None}
