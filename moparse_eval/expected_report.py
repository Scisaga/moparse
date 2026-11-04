"""Recheck three-layer evidence before formal publication.

Arithmetic and trace checks do not prove semantic compiler coverage. The
independent validation and real-format diagnosis gates remain separate.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rapidfuzz.distance import Levenshtein

from .layer_aggregation import LAYERS, paired_layers, require_validation, summarize_layers
from .packaging import inside, read_json
from .three_layer import PROTOCOL, canonical

PIPELINES = tuple(f"P{i:02}" for i in range(1, 9))


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(map(_freeze, value))
    return canonical(value) if isinstance(value, str) else value


def _identity(item: dict[str, Any]) -> tuple[Any, ...]:
    return canonical(item["subject"]), canonical(item["attribute"]), _freeze(item.get("scope", [])), _freeze(item.get("identity_facets", {}))


def _source(item: dict[str, Any]) -> None:
    if not isinstance(item.get("source"), dict) or not item["source"].get("path"):
        raise ValueError("requirements and selected candidates must retain their actual source")


def _business_trace(row: dict[str, Any]) -> None:
    expected, trace = row["expected"], row.get("retrieval", {})
    query = {key: expected.get(key, [] if key == "scope" else "") for key in ("subject", "attribute", "scope")}
    query["identity_facets"] = expected.get("identity_facets", {})
    if trace.get("query") != query or not isinstance(trace.get("candidates"), list):
        raise ValueError("business retrieval requires an answer-independent complete identity query")
    if not isinstance(trace.get("textual_hits"), list):
        raise ValueError("business retrieval must retain literal hits independently of data-role proof")
    for hit in trace["textual_hits"]:
        _source(hit)
        if not hit.get("text") or not hit.get("reason") or hit.get("decision") != "literal_evidence_only":
            raise ValueError("a raw literal hit cannot supply an unproved business value")
    accepted, seen = [], set()
    for hit in trace["candidates"]:
        _source(hit)
        if not hit.get("id") or hit["id"] in seen or not hit.get("reason"):
            raise ValueError("retrieval candidates need unique identities and exclusion reasons")
        seen.add(hit["id"])
        checks = hit.get("identity", {})
        if set(checks) != set(query):
            raise ValueError("every recalled candidate must check the complete identity and context")
        for key, check in checks.items():
            if check.get("required") != query[key] or type(check.get("correct")) is not bool:
                raise ValueError("retrieval identity checks do not match the actual query")
            matches = (key == "scope" and not query[key]) or _freeze(check.get("required")) == _freeze(check.get("actual"))
            if check["correct"] != matches:
                raise ValueError("retrieval admitted an inconsistent identity decision")
        eligible = all(check["correct"] for check in checks.values())
        if hit.get("decision") != ("accepted" if eligible else "rejected"):
            raise ValueError("a conflicting retrieval candidate cannot supply a compared value")
        if eligible:
            accepted.append(hit["id"])
    if trace.get("accepted") != accepted:
        raise ValueError("retrieval accepted-set differs from its complete trace")
    actual = row.get("actual")
    if not isinstance(actual, list) or Counter(item["id"] for item in actual) != Counter(accepted):
        raise ValueError("business values must come from the complete identity-validated set")
    for item in actual:
        _source(item)
        required_identity, actual_identity = _identity(expected), _identity(item)
        if (required_identity[:2] != actual_identity[:2] or required_identity[3] != actual_identity[3]
                or (required_identity[2] and required_identity[2] != actual_identity[2])):
            raise ValueError("selected business value has a conflicting identity")


def validate_evidence(score: dict[str, Any]) -> None:
    """Independently read back edits, occurrences, relation endpoints and traces."""
    if score.get("protocol") != PROTOCOL:
        raise ValueError("mixed scoring protocols cannot be published")
    summarize_layers([score])
    text = [row for row in score["outcomes"] if row["layer"] == "T"]
    totals, strict_totals = Counter(), Counter()
    denominator, located_chars, located, used = 0, 0, 0, set()
    relation_used, business = set(), defaultdict(list)
    for row in score["outcomes"]:
        _source(row["expected"])
        if not row.get("root_cause"):
            raise ValueError("each decision must retain its common-cause trace")
        if row["layer"] == "T":
            expected = row["expected"]["text"]
            actual = row["actual"]["text"] if row.get("actual") else ""
            a, b = canonical(expected), canonical(actual)
            denominator += len(a)
            strict_expected = row["expected"].get("strict_text", expected)
            strict_actual = row["actual"].get("strict_text", actual) if row.get("actual") else ""
            for wanted, observed, field, counts in ((a, b, "edits", totals),
                                                   (strict_expected, strict_actual, "strict_edits", strict_totals)):
                operations = Counter(op.tag for op in Levenshtein.editops(wanted, observed))
                edits = {"S": operations["replace"], "D": operations["delete"], "I": operations["insert"]}
                if row.get(field) != edits:
                    raise ValueError("text S/D/I differs from its actual paired literals")
                counts.update(edits)
            if row["outcome"] != ("correct" if a == b else "incorrect"):
                raise ValueError("text decision contradicts its paired literals")
            if row.get("actual"):
                _source(row["actual"])
                identity = row["actual"]["id"]
                if identity in used:
                    raise ValueError("one candidate text occurrence cannot satisfy multiple requirements")
                used.add(identity)
                located += 1
                located_chars += len(a)
        elif row["layer"] == "B":
            _business_trace(row)
            business[_identity(row["expected"])].append(row)
        else:
            actual = row.get("actual")
            if row["outcome"] != ("correct" if actual else "incorrect"):
                raise ValueError("relation decision contradicts its endpoint evidence")
            if actual:
                _source(actual)
                expected = row["expected"]
                if _freeze([expected["type"], expected["left"], expected["right"]]) != _freeze([actual["type"], actual["left"], actual["right"]]):
                    raise ValueError("a relation pass has different endpoints or type")
                if actual["id"] in relation_used:
                    raise ValueError("one candidate relation cannot satisfy multiple requirements")
                relation_used.add(actual["id"])
    counts = score["layers"]["T"]
    expected_counts = {"numerator": denominator - sum(totals.values()), "denominator": denominator,
                       "required_units": len(text), "located_units": located,
                       "located_characters": located_chars, **dict(totals)}
    if any(counts.get(key, 0) != value for key, value in expected_counts.items()):
        raise ValueError("text full-range aggregate differs from its character decisions")
    for members in business.values():
        def signature(item):
            return canonical(item["value"]), _freeze(item["qualifiers"])
        expected_set = Counter(signature(row["expected"]) for row in members)
        actual_set = Counter(signature(item) for item in members[0]["actual"])
        correct = expected_set == actual_set
        if any(row["actual"] != members[0]["actual"] or row["outcome"] != ("correct" if correct else "incorrect") for row in members):
            raise ValueError("business judgment contradicts the complete repeated assertion set")


def _targets(score: dict[str, Any]) -> dict[Any, Any]:
    return {(row["layer"], row["id"]): row["expected"] for row in score["outcomes"]}


def text_layer_diagnostics(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep full-range and strict edits visible without redefining the T score."""
    edits, strict_edits = Counter(), Counter()
    units = located_units = denominator = located_chars = extras = 0
    for score in scores:
        for row in score["outcomes"]:
            if row["layer"] != "T":
                continue
            units += 1
            chars = len(canonical(row["expected"]["text"]))
            denominator += chars
            edits.update(row["edits"])
            strict_edits.update(row["strict_edits"])
            if row.get("actual"):
                located_units += 1
                located_chars += chars
        extras += len(score["layers"]["T"].get("unadjudicated_extra_units", []))
    return {"required_units": units, "located_units": located_units, "required_characters": denominator,
            "located_characters": located_chars, "edits": dict(edits), "strict_edits": dict(strict_edits),
            "unadjudicated_extra_units": extras,
            "meaning": "full_expected_scope_text_consistency_not_original_pdf_ocr_accuracy"}


def load_complete(index_path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    index = read_json(index_path)
    if (index.get("state") != "completed" or index.get("expected_comparison_complete") is not True
            or index.get("protocol") != PROTOCOL or index.get("blockers")):
        raise ValueError("complete validated three-layer comparison is required before publication")
    require_validation(index.get("validation", {}))
    software_id = index.get("software", {}).get("software_id")
    if not software_id:
        raise ValueError("formal results require a frozen software identity")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen = set()
    for record in index["records"]:
        score = read_json(inside(index_path.parent, record["path"]))
        key = record["group"], record["sample_id"]
        if key in seen or score.get("sample_id") != record["sample_id"] or score.get("pipeline") != record["group"].split("-", 1)[0]:
            raise ValueError("duplicate or mismatched evaluated sample/group")
        seen.add(key)
        if score.get("scoring_software_id") != software_id:
            raise ValueError("mixed scoring software cannot be published")
        validate_evidence(score)
        groups[record["group"]].append(score)
        samples[record["sample_id"]].append(score)
    if not groups or set(groups) != set(index["groups"]) or len(index["groups"]) != len(groups):
        raise ValueError("declared comparison groups are missing or duplicated")
    coverage = {row["sample_id"]: row for row in index["coverage"]}
    if set(coverage) != set(samples) or len(coverage) != len(index["coverage"]):
        raise ValueError("declared expected scope and evaluated samples differ")
    for sample, scores in samples.items():
        if len(scores) != len(groups) or any(_targets(score) != _targets(scores[0]) for score in scores):
            raise ValueError("all groups must compare the same complete expected requirements")
        for layer in LAYERS:
            declared = coverage[sample]["layers"][layer]
            if any(score["layers"][layer]["denominator"] != declared["denominator"] for score in scores):
                raise ValueError("a layer differs from the frozen expected denominator")
    if set(index.get("summary", {})) != set(groups):
        raise ValueError("every declared group requires its own three-layer summary")
    for group, scores in groups.items():
        computed = summarize_layers(scores)
        if computed != index["summary"][group]:
            raise ValueError("group summary differs from its actual layer decisions")
        if not computed["publishable"]:
            raise ValueError("global quality requires three legal nonzero layer denominators")
    paired = {}
    for pipeline in ("P07", "P08"):
        if pipeline + "-baseline" in groups and pipeline + "-current" in groups:
            comparisons = {
                "native_to_baseline": (pipeline, pipeline + "-baseline"),
                "native_to_current": (pipeline, pipeline + "-current"),
                "baseline_to_current": (pipeline + "-baseline", pipeline + "-current"),
            }
            paired[pipeline] = {}
            for name, (before, after) in comparisons.items():
                pair = paired_layers(groups[before], groups[after])
                paired[pipeline][name] = {
                    layer: {"new_correct": row["new_correct"], "lost_correct": row["lost_correct"],
                            "remaining_incorrect": row["remaining_defects"], "required_units": row["after"]["denominator"]}
                    for layer, row in pair["layers"].items()
                }
    if index.get("paired", {}) != paired:
        raise ValueError("paired layer summary differs from its actual same-target decisions")
    return index, dict(groups)
