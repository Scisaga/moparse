"""Compare logical bindings using independent endpoint evidence.

Native ids are evidence, not extra questions or a required output format.
When both sides retain the same independent data object, inspect that object
before comparing its bindings. Otherwise use complete declared logical roles,
never its numerical answer. Every candidate relation has capacity one.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from typing import Any

from rapidfuzz.distance import Levenshtein

from .business_labels import role_label
from .scope_correspondence import verify_scope


def _freeze(value, canonicalize, *, dimension=None):
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item, canonicalize, dimension=value.get("type")
                                         if key == "text" and value.get("type") in {
                                             "period", "from_period", "to_period", "comparison_period"} else key))
                            for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item, canonicalize) for item in value)
    if isinstance(value, str):
        text = canonicalize(value)
        if dimension in {"period", "from_period", "to_period", "comparison_period"} and re.fullmatch(r"(?:19|20)\d{2}年?", text):
            return text.removesuffix("年")
        return role_label(text) if dimension == "attribute" else text
    return value


def signature(edge, canonicalize):
    identity = [edge["type"], _endpoint(edge["left"]), _endpoint(edge["right"])]
    if edge["type"] == "heading_parent":
        identity.append(edge.get("required_scope", [edge["left"], edge["right"]]))
    return _freeze(identity, canonicalize)


def _endpoint(value):
    if not isinstance(value, dict) or "scope" not in value:
        return value
    result = copy.deepcopy(value)
    facets = result.get("identity_facets", {})
    group = facets.pop("group", None)
    group = [group] if isinstance(group, str) and group else group or []
    scope = list(result.get("scope", []))
    if group and scope[-len(group):] != group:
        scope.extend(group)
    result["scope"] = scope
    return result


def relation_scope_verification(expected, actual, canonicalize, *, contexts=None, declared_paths=(), context_labels=()):
    required = expected.get("right", {})
    own = actual.get("right", {})
    if expected["type"] == "heading_parent" and actual["type"] in {"heading_parent", "heading_position"} and contexts is not None:
        path = expected.get("required_scope", [expected["left"], expected["right"]])
        return verify_scope(path, {"source": actual["source"], "context_evidence": actual.get("context_evidence", {}),
                                   "field_label_evidence": actual.get("field_label_evidence")},
                            list(declared_paths), contexts=contexts, canonicalize=canonicalize, context_labels=context_labels)
    if contexts is None or not isinstance(required, dict) or not isinstance(own, dict) or not required.get("scope"):
        return None
    binding = actual.get("binding_evidence", {})
    item = {**own, "source": actual["source"], "context_evidence": actual.get("context_evidence", {}),
            "row_evidence": binding.get("rows", []), "header_evidence": binding.get("headers", []),
            "field_label_evidence": actual.get("field_label_evidence")}
    return verify_scope(_endpoint(required)["scope"], item, list(declared_paths), contexts=contexts,
                        canonicalize=canonicalize, context_labels=context_labels)


def logical_roles_equal(expected, actual, canonicalize, *, contexts=None, declared_paths=(), context_labels=()):
    if actual.get("context_evidence", {}).get("status") in {"ambiguous", "conflict"}:
        return False
    proof = relation_scope_verification(expected, actual, canonicalize, contexts=contexts,
                                        declared_paths=declared_paths, context_labels=context_labels)
    if proof is not None and not proof["correct"]:
        return False
    if expected["type"] == "heading_parent" and actual["type"] == "heading_position":
        return bool(proof and proof["correct"] and canonicalize(expected["right"]) == canonicalize(actual["right"]))
    if signature(expected, canonicalize) == signature(actual, canonicalize):
        return True
    if expected["type"] != actual["type"] or _freeze(_endpoint(expected["left"]), canonicalize) != _freeze(_endpoint(actual["left"]), canonicalize):
        return False
    right = actual.get("right")
    if not isinstance(right, dict) or not isinstance(expected.get("right"), dict):
        return False
    for path in [*actual.get("scope_alternatives", []), *([proof["actual_path"]] if proof and proof["correct"] else [])]:
        path = list(path)
        group = right.get("identity_facets", {}).get("group")
        if isinstance(group, str) and group and (not path or path[-1] != group):
            path.append(group)
        required = _endpoint(expected["right"]).get("scope", [])
        if required and (len(path) < len(required) or _freeze(path[-len(required):], canonicalize) != _freeze(required, canonicalize)):
            continue
        revised = _endpoint({**right, "scope": required})
        if _freeze(_endpoint(expected["right"]), canonicalize) == _freeze(revised, canonicalize):
            return True
    return False


def _role(edge):
    left = edge.get("left")
    return ("heading_parent" if edge["type"] == "heading_position" else edge["type"]), left.get("type") if isinstance(left, dict) else None


def _same_scope(left, right, canonicalize):
    a, b = left.get("right", {}), right.get("right", {})
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    keys = ("subject", "scope", "identity_facets")
    if _freeze({key: a.get(key) for key in keys}, canonicalize) == _freeze({key: b.get(key) for key in keys}, canonicalize):
        return True
    # Independently retained row/identity objects can survive a label typo.
    rows_a, rows_b = left.get("row_anchors", []), right.get("row_anchors", [])
    return bool(rows_a and rows_b and sorted(rows_a) == sorted(rows_b))


def unchanged_binding(expected, actual, canonicalize):
    """Allow content errors only when the same endpoint links are proved."""
    headers_a, headers_b = expected.get("header_anchors", []), actual.get("header_anchors", [])
    return bool(actual.get("context_evidence", {}).get("status") not in {"ambiguous", "conflict"}
                and expected.get("object_anchor") and expected.get("object_anchor") == actual.get("object_anchor")
                and headers_a and headers_b and sorted(headers_a) == sorted(headers_b)
                and _role(expected) == _role(actual) and _same_scope(expected, actual, canonicalize))


def _labels(edge):
    if edge["type"] in {"heading_parent", "heading_position"}:
        return [str(edge["right"])]
    left = edge.get("left")
    if isinstance(left, str):
        return [left]
    if isinstance(left, dict):
        if left.get("title"):
            return [str(left["title"])]
        if left.get("attribute"):
            return [str(left["attribute"])]
        right = edge.get("right")
        if isinstance(right, dict) and right.get("attribute"):
            return [str(right["attribute"])]
        identity = left.get("identity") or (right.get("identity") if isinstance(right, dict) else None)
        if isinstance(identity, dict):
            if identity.get("action"):
                return [str(identity["action"])]
            if identity.get("lexical_anchor"):
                return [" ".join(identity["lexical_anchor"])]
        return [str(left[key]) for key in ("subject", "type") if left.get(key)]
    right = edge.get("right")
    if isinstance(right, dict) and isinstance(right.get("identity"), dict):
        identity = right["identity"]
        if identity.get("action"):
            return [str(identity["action"])]
        if identity.get("lexical_anchor"):
            return [" ".join(identity["lexical_anchor"])]
    return []


def _recalled(expected, actual, canonicalize):
    """Recall identities, never a target data value or another cell's answer.

    All exact and nearby label hits remain available for context verification.
    Unrelated edges of the same type are not textual hits.
    """
    wanted, found = _labels(expected), _labels(actual)
    if not wanted or not found:
        return True
    return any(Levenshtein.normalized_similarity(role_label(canonicalize(a)), role_label(canonicalize(b))) >= .7
               for a in wanted for b in found)


def grade_relations(reference: list[dict[str, Any]], candidate: list[dict[str, Any]], *, canonicalize,
                    contexts=None, declared_paths=(), context_labels=()):
    scope_options = {"contexts": contexts, "declared_paths": declared_paths, "context_labels": context_labels}
    available = set(range(len(candidate)))
    # A document-wide reused native id is not a unique object anchor.
    anchors = Counter((edge.get("object_anchor"), _role(edge)) for edge in candidate if edge.get("object_anchor"))
    rows = []
    for item in reference:
        role = _role(item)
        anchor = item.get("object_anchor")
        independent = [i for i in sorted(available) if anchor and candidate[i].get("object_anchor") == anchor
                       and _role(candidate[i]) == role]
        unique_anchor = bool(independent and anchors[anchor, role] == 1)
        pool = independent if unique_anchor else [i for i in sorted(available)
                    if _role(candidate[i]) == role and _recalled(item, candidate[i], canonicalize)]
        hits = []
        for i in pool:
            edge = candidate[i]
            scope_proof = relation_scope_verification(item, edge, canonicalize, **scope_options)
            correct = ((unchanged_binding(item, edge, canonicalize) and (scope_proof is None or scope_proof["correct"]))
                       or logical_roles_equal(item, edge, canonicalize, **scope_options))
            hits.append({"id": edge["id"], "source": edge["source"], "evidence": copy.deepcopy(edge), "correct": correct,
                         "checks": {"type": _role(item) == _role(edge), "raw_type_same": item["type"] == edge["type"],
                                    "left_endpoint": _freeze(item["left"], canonicalize) == _freeze(edge["left"], canonicalize),
                                    "right_endpoint": _freeze(item["right"], canonicalize) == _freeze(edge["right"], canonicalize),
                                    "independent_links": unchanged_binding(item, edge, canonicalize)},
                         "scope_verification": scope_proof,
                         "reason": "same_independent_objects_and_links" if unchanged_binding(item, edge, canonicalize)
                         else "scope_proved_at_actual_heading_position" if correct and edge["type"] == "heading_position"
                         else "same_complete_logical_roles" if correct else "explicit_binding_conflict"})
        selected = next((hit for hit in hits if hit["correct"]), None)
        actual = None
        if selected:
            index = next(i for i in pool if candidate[i]["id"] == selected["id"])
            available.remove(index)
            actual = candidate[index]
        elif unique_anchor:
            actual = candidate[independent[0]]
            available.remove(independent[0])
        rows.append({"id": item["id"], "layer": "L", "role": item["type"], "expected": item,
                     "actual": actual, "outcome": "correct" if selected else "incorrect",
                     "retrieval": {"method": "independent_object_anchor" if unique_anchor else "declared_logical_roles",
                                   "query": {"type": item["type"], "endpoint_labels": _labels(item)},
                                   "candidates": hits, "selected": selected["id"] if selected else None},
                     "root_cause": "relation:" + repr(signature(item, canonicalize))})
    numerator, denominator = sum(row["outcome"] == "correct" for row in rows), len(rows)
    return {"numerator": numerator, "denominator": denominator,
            "score": 100 * numerator / denominator if denominator else None, "complete": True}, rows
