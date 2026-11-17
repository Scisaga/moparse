"""Independent layer aggregation and same-requirement pairing.

These checks consume scoring records only. They neither read references nor
certify that a compiler interpreted them correctly. An incomplete software
judgment blocks publication instead of becoming a candidate error.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

LAYERS = ("T", "L", "B")
VALIDATION_STAGES = (
    "independent_counterexamples",
    "mutations",
    "native_formats",
    "saved_output_diagnosis",
)


def require_validation(validation: Mapping[str, Any]) -> None:
    """Require evidence for each distinct software-validation obligation."""
    if validation.get("status") != "passed":
        raise ValueError("scoring freeze must record passed engineering validation")
    if validation.get("known_reader_defects") or validation.get("blockers"):
        raise ValueError("known reader defects and software blockers must be repaired before scoring")
    for stage in VALIDATION_STAGES:
        evidence = validation.get(stage)
        if not isinstance(evidence, Mapping) or evidence.get("status") != "passed":
            raise ValueError(f"scoring freeze requires passed {stage} evidence")
        if not evidence.get("evidence"):
            raise ValueError(f"scoring freeze requires traceable {stage} evidence")


def _number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return value


def _layer_score(layer: str, numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    # T error counts are pooled before clipping. Per-sample clipping would
    # hide insertions in short samples and produce a different global score.
    return 100.0 * (max(0, numerator) if layer == "T" else numerator) / denominator


def _decisions(score: Mapping[str, Any]) -> dict[str, dict[str, Mapping[str, Any]]]:
    outcomes = score.get("outcomes")
    if not isinstance(outcomes, list):
        raise ValueError("three-layer scoring requires explicit target decisions")
    result: dict[str, dict[str, Mapping[str, Any]]] = {layer: {} for layer in LAYERS}
    for row in outcomes:
        if not isinstance(row, Mapping) or row.get("layer") not in LAYERS:
            raise ValueError("every target decision must declare T, L or B")
        layer = row["layer"]
        identifier = row.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in result[layer]:
            raise ValueError("target identities must be nonempty and unique within each layer")
        if row.get("outcome") not in {"correct", "incorrect"}:
            raise ValueError("software-unsupported judgments cannot publish as binary candidate errors")
        if row.get("reader_failure") or row.get("software_failure") or row.get("unsupported"):
            raise ValueError("software failure cannot publish as a candidate error")
        if not row.get("role") or "expected" not in row:
            raise ValueError("target decisions require their role and expected requirement")
        result[layer][identifier] = row
    return result


def _validate_score(score: Mapping[str, Any]) -> dict[str, dict[str, Mapping[str, Any]]]:
    if not isinstance(score.get("sample_id"), str) or not score["sample_id"]:
        raise ValueError("a scored sample requires its declared identity")
    if score.get("blockers") or score.get("publishable") is not True:
        raise ValueError("incomplete software judgments cannot publish or be counted as zero")
    layers = score.get("layers")
    if not isinstance(layers, Mapping) or set(layers) != set(LAYERS):
        raise ValueError("every sample must retain all three independent layers")
    decisions = _decisions(score)
    for layer in LAYERS:
        counts = layers[layer]
        if not isinstance(counts, Mapping) or counts.get("complete") is not True:
            raise ValueError(f"incomplete {layer} software judgments cannot publish")
        denominator = _number(counts.get("denominator"), f"{layer} denominator")
        numerator = _number(counts.get("numerator"), f"{layer} numerator")
        if denominator < 0 or numerator > denominator or (layer != "T" and numerator < 0):
            raise ValueError(f"invalid {layer} numerator or denominator")
        if denominator == 0 and numerator != 0:
            raise ValueError("a layer without requirements must have zero numerator")
        computed = _layer_score(layer, numerator, denominator)
        supplied = counts.get("score")
        if (computed is None and supplied is not None) or (computed is not None and (
            not isinstance(supplied, (int, float)) or isinstance(supplied, bool)
            or not math.isclose(supplied, computed, rel_tol=1e-12, abs_tol=1e-9)
        )):
            raise ValueError(f"{layer} aggregate differs from its fixed layer formula")
        if layer in {"L", "B"}:
            correct = sum(row["outcome"] == "correct" for row in decisions[layer].values())
            if denominator != len(decisions[layer]) or numerator != correct:
                raise ValueError(f"{layer} aggregate differs from its binary target decisions")
    values = [layers[layer]["score"] for layer in LAYERS]
    expected_total = sum(values) / 3 if all(value is not None for value in values) else None
    supplied = score.get("score")
    if (expected_total is None and supplied is not None) or (expected_total is not None and (
        not isinstance(supplied, (int, float)) or isinstance(supplied, bool)
        or not math.isclose(supplied, expected_total, rel_tol=1e-12, abs_tol=1e-9)
    )):
        raise ValueError("sample quality must be the equal mean of three applicable layer scores")
    return decisions


def summarize_layers(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Pool each fixed layer separately, then average the three layer scores."""
    from .ast_alignment import METHOD

    if scores and all(s.get('scoring_method') == METHOD for s in scores):
        return summarize_continuous(scores)
    seen: set[str] = set()
    for score in scores:
        _validate_score(score)
        if score["sample_id"] in seen:
            raise ValueError("duplicate scored sample cannot enlarge a layer denominator")
        seen.add(score["sample_id"])
    layers = {}
    for layer in LAYERS:
        numerator = sum(score["layers"][layer]["numerator"] for score in scores)
        denominator = sum(score["layers"][layer]["denominator"] for score in scores)
        layers[layer] = {
            "numerator": numerator,
            "denominator": denominator,
            "score": _layer_score(layer, numerator, denominator),
            "complete": True,
            "applicable_samples": sum(score["layers"][layer]["denominator"] > 0 for score in scores),
            "not_applicable_samples": sum(score["layers"][layer]["denominator"] == 0 for score in scores),
        }
    values = [layers[layer]["score"] for layer in LAYERS]
    applicable = all(value is not None for value in values)
    return {
        "samples": len(scores),
        "layers": layers,
        "score": sum(values) / 3 if applicable else None,
        "publishable": applicable,
        "blockers": [],
    }


def summarize_continuous(scores):
    """Pool full responsibilities; never promote internal research to publication."""
    seen = set()
    for score in scores:
        if score['sample_id'] in seen:
            raise ValueError('duplicate continuous sample')
        seen.add(score['sample_id'])
        if score.get('publication_authorized') is not False or score.get('research_only') is not True:
            raise ValueError('continuous contract is bounded research only')
        for layer in LAYERS:
            own = [r for r in score['outcomes'] if r['layer'] == layer]
            if len({r['id'] for r in own}) != len(own):
                raise ValueError('duplicate continuous requirement')
            counts = score['layers'][layer]
            if layer != 'T':
                if len(own) != counts['denominator']:
                    raise ValueError('continuous requirement denominator changed')
                for row in own:
                    if row['credit'] is None:
                        continue
                    parts = row['components']
                    total = sum(p.get('weight', 1) for p in parts)
                    credit = sum(p['credit'] * p.get('weight', 1) for p in parts) / total
                    if not math.isclose(credit, row['credit'], abs_tol=1e-12):
                        raise ValueError('continuous credit differs from fixed components')
                numerator = sum(r['credit'] or 0 for r in own)
            else:
                from .three_layer import canonical

                if sum(len(canonical(r['expected']['text'])) for r in own) != counts['denominator']:
                    raise ValueError('continuous canonical denominator changed')
                numerator = counts['denominator'] - sum(sum(r['edits'].values()) for r in own)
            if counts['complete'] and not math.isclose(numerator, counts['numerator'], abs_tol=1e-9):
                raise ValueError('continuous numerator differs from item evidence')
    layers = {}
    for layer in LAYERS:
        own = [s['layers'][layer] for s in scores]
        n = sum(r['denominator'] for r in own)
        complete = all(r['complete'] for r in own)
        numerator = sum(r['numerator'] for r in own) if complete else None
        layers[layer] = {'denominator': n, 'numerator': numerator,
                         'score': _layer_score(layer, numerator, n) if complete else None,
                         'complete': complete,
                         'compared_requirements': sum(r['compared_requirements'] for r in own)}
    values = [r['score'] for r in layers.values()]
    return {'samples': len(scores), 'layers': layers,
            'score': sum(values) / 3 if all(v is not None for v in values) else None,
            'research_only': True, 'full_lite_score': False,
            'publishable': False, 'publication_authorized': False,
            'blockers': [b for s in scores for b in s['blockers']]}


def continuous_aggregation_record(score):
    """Validate full evidence, then retain only the numeric pooling ledger.

    The complete score must already be persisted. This keeps serial 72-case
    execution within the same memory budget without discarding saved proof.
    """
    summarize_continuous([score])
    result = {k: score[k] for k in ('sample_id', 'pipeline', 'scoring_method', 'layers', 'score',
                                   'research_only', 'publication_authorized', 'blockers', 'comparison_complete')}
    result['outcomes'] = []
    for row in score['outcomes']:
        own = {k: row[k] for k in ('id', 'layer', 'credit', 'outcome')}
        if row['layer'] == 'T':
            own.update(expected={'text': row['expected']['text']}, edits=row['edits'])
        else:
            own['components'] = [{k: part[k] for k in ('credit', 'weight') if k in part} for part in row['components']]
        result['outcomes'].append(own)
    return result


def paired_layers(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare actual decisions only after proving identical sample requirements."""
    left_summary, right_summary = summarize_layers(before), summarize_layers(after)
    left = {score["sample_id"]: score for score in before}
    right = {score["sample_id"]: score for score in after}
    if set(left) != set(right):
        raise ValueError("paired outputs must cover the same declared samples")
    result: dict[str, Any] = {layer: {"gains": [], "losses": [], "remaining_incorrect": []} for layer in LAYERS}
    roots: dict[str, set[tuple[str, str, str]]] = {}
    for sample_id in sorted(left):
        previous, current = _decisions(left[sample_id]), _decisions(right[sample_id])
        for layer in LAYERS:
            if set(previous[layer]) != set(current[layer]):
                raise ValueError("paired outputs must retain identical layer target identities")
            if left[sample_id]["layers"][layer]["denominator"] != right[sample_id]["layers"][layer]["denominator"]:
                raise ValueError("paired outputs must retain identical layer denominators")
            for identifier in sorted(previous[layer]):
                old, new = previous[layer][identifier], current[layer][identifier]
                if any(old.get(key) != new.get(key) for key in ("role", "expected", "reference")):
                    raise ValueError("paired target meaning, role or reference changed")
                item = {"sample_id": sample_id, "id": identifier, "layer": layer,
                        "before": dict(old), "after": dict(new)}
                if old["outcome"] != new["outcome"]:
                    result[layer]["gains" if new["outcome"] == "correct" else "losses"].append(item)
                if new["outcome"] == "incorrect":
                    result[layer]["remaining_incorrect"].append(item)
                    root = new.get("root_cause") or new.get("root_cause_id")
                    if isinstance(root, str):
                        roots.setdefault(root, set()).add((sample_id, layer, identifier))
    for layer in LAYERS:
        row = result[layer]
        row.update(new_correct=len(row["gains"]), lost_correct=len(row["losses"]),
                   remaining_defects=len(row["remaining_incorrect"]),
                   before=left_summary["layers"][layer], after=right_summary["layers"][layer])
    return {
        "samples": len(left),
        "layers": result,
        "before": left_summary,
        "after": right_summary,
        "shared_root_causes": {
            root: [{"sample_id": sample, "layer": layer, "id": identifier}
                   for sample, layer, identifier in sorted(members)]
            for root, members in sorted(roots.items())
        },
        "meaning": "observed_same_target_changes_not_independent_recognition_error_counts",
    }
