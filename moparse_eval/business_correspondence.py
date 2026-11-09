"""Answer-independent business retrieval and complete assertion comparison.

The reader has already exposed its own facts and text. Position dimensions are
checked before values: each year, unit and business scope keeps its own target,
while indistinguishable repeated records retain a complete multiset contract.
"""

from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any

from rapidfuzz.distance import Levenshtein

from .business_labels import role_label
from .equivalence import decide_equivalence
from .quantity import exact_number, normalize_quantity, ratio
from .scope_correspondence import verify_scope
from .scoring_evidence import snapshot_copy

Canonicalize = Callable[[str], str]
KNOWN_QUALIFIERS = frozenset({
    "unit", "currency", "period", "scope", "business_scope", "column_currency", "period_basis",
    "from_period", "to_period", "comparison_period", "condition", "exception", "note", "notes",
    "note_texts", "note_markers", "negation", "basis", "as_of", "date", "market",
    "modal", "modality", "polarity", "purpose", "condition_operator", "exception_operator",
    "conditions", "circumstances", "manner",
    "quantity_role", "tense",
})
POSITION_QUALIFIERS = frozenset({
    "unit", "currency", "period", "scope", "business_scope", "column_currency", "period_basis",
    "from_period", "to_period", "comparison_period", "basis", "as_of", "date", "market",
    "quantity_role",
})


def freeze(value: Any, canonicalize: Canonicalize, *, dimension: str | None = None) -> Any:
    """Retain typed values, lists and dictionaries; never sort literal words."""
    if isinstance(value, dict):
        return tuple(sorted((key, freeze(decide_equivalence(
            {"unit": item, "currency": value.get("currency"), "quantity_role": value.get("quantity_role")},
            {"unit": item, "currency": value.get("currency"), "quantity_role": value.get("quantity_role")}, "unit")["canonical"]["required"], canonicalize)
            if key == "unit" else freeze(item, canonicalize, dimension=key)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item, canonicalize, dimension=dimension) for item in value)
    if isinstance(value, str):
        normalized = decide_equivalence(value, value, dimension or "literal", context={"canonicalize": canonicalize})["canonical"]["required"]
        return freeze(normalized, canonicalize) if isinstance(normalized, (dict, list, tuple)) else normalized
    return value


def _path(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    return [item for item in value or [] if isinstance(item, str) and item]


def _ends_with(actual: list[str], required: list[str], canonicalize: Canonicalize) -> bool:
    return not required or (len(actual) >= len(required) and
                            freeze(actual[-len(required):], canonicalize) == freeze(required, canonicalize))


def logical_context(item: dict[str, Any], canonicalize: Canonicalize) -> list[str]:
    """A printed heading and an explicit row group can state the same scope."""
    context = _path(item.get("scope"))
    group = _path(item.get("identity_facets", {}).get("group"))
    if group and not _ends_with(context, group, canonicalize):
        context.extend(group)
    return context


def context_options(item: dict[str, Any], canonicalize: Canonicalize) -> list[list[str]]:
    result = [logical_context(item, canonicalize)]
    for path in item.get("scope_alternatives", []):
        option = logical_context({**item, "scope": path}, canonicalize)
        if option not in result:
            result.append(option)
    return result


def query_for(item: dict[str, Any]) -> dict[str, Any]:
    """No value, raw spelling or expected answer enters location selection."""
    return {"subject": item.get("subject", ""), "attribute": item["attribute"],
            "scope": copy.deepcopy(item.get("scope", [])),
            "identity_facets": copy.deepcopy(item.get("identity_facets", {})),
            "qualifiers": {key: copy.deepcopy(value) for key, value in item.get("qualifiers", {}).items()
                           if key in POSITION_QUALIFIERS}}


def _check(required: Any, actual: Any, canonicalize: Canonicalize, *, key: str | None = None,
           present: bool = True, context=None, operands=None) -> dict[str, Any]:
    decision = decide_equivalence(*(operands or (required, actual)), key or "literal",
                                  context={"canonicalize": canonicalize, **(context or {})})
    correct = present and decision["equivalent"]
    result = {"required": copy.deepcopy(required), "actual": copy.deepcopy(actual), "correct": bool(correct),
              "status": "correct" if correct else "explicit_conflict" if present else "missing"}
    if key in {"attribute", "unit", "currency", "quantity", "period_basis"}:
        result["equivalence"] = decision
    return result


def identity_checks(query: dict[str, Any], item: dict[str, Any], canonicalize: Canonicalize, *, contexts=None,
                    declared_paths=(), context_labels=()) -> dict[str, Any]:
    checks = {"subject": _check(query["subject"], item.get("subject", ""), canonicalize, key="entity")}
    own_context = item.get("context_evidence", {})
    if own_context:
        checks["candidate_context"] = {"correct": own_context.get("status") not in {"conflict", "ambiguous"},
                                       "status": own_context.get("status"),
                                       "conflicts": snapshot_copy(own_context.get("conflicts", [])),
                                       "source": snapshot_copy(own_context.get("source", {}))}
    required_context, actual_context = logical_context(query, canonicalize), logical_context(item, canonicalize)
    options = context_options(item, canonicalize)
    matched = [path for path in options if _ends_with(path, required_context, canonicalize)]
    context_ok = bool(matched)
    scope_verification = None
    if contexts is not None and required_context:
        scope_verification = verify_scope(required_context, item, list(declared_paths), contexts=contexts,
                                           canonicalize=canonicalize, context_labels=context_labels)
        context_ok = scope_verification["correct"]
    checks["scope"] = {"required": copy.deepcopy(query["scope"]), "actual": copy.deepcopy(item.get("scope", [])),
                       "effective_required": required_context, "effective_actual": actual_context,
                       "correct": context_ok, "status": "correct" if context_ok else "explicit_conflict" if actual_context else "missing",
                       "basis": "candidate_printed_heading_or_explicit_group_context",
                       "candidate_paths": copy.deepcopy(options), "matched_paths": copy.deepcopy(matched),
                       "context_evidence": snapshot_copy(item.get("context_evidence", {}))}
    if scope_verification is not None:
        checks["scope"]["verification"] = scope_verification
    wanted_facets, actual_facets = query["identity_facets"], item.get("identity_facets", {})
    facet_checks = {}
    effective_facets = copy.deepcopy(actual_facets)
    for key, required in wanted_facets.items():
        if key == "group":
            actual = actual_facets.get("group", item.get("scope", []))
            correct = (_ends_with(_path(actual), _path(required), canonicalize) or
                       "group" not in actual_facets and any(_ends_with(path, _path(required), canonicalize) for path in options))
            if "group" not in actual_facets and scope_verification and scope_verification["correct"]:
                correct = _ends_with(scope_verification["actual_path"], _path(required), canonicalize)
            effective_facets[key] = copy.deepcopy(actual)
            facet_checks[key] = {"required": copy.deepcopy(required), "actual": copy.deepcopy(actual),
                                 "correct": correct, "status": "correct" if correct else "explicit_conflict" if _path(actual) else "missing",
                                 "basis": "explicit_candidate_group_or_candidate_heading_path"}
        else:
            facet_checks[key] = _check(required, actual_facets.get(key), canonicalize, key=key, present=key in actual_facets)
    checks["identity_facets"] = {"required": copy.deepcopy(wanted_facets), "actual": effective_facets,
                                "checks": facet_checks, "correct": all(check["correct"] for check in facet_checks.values()),
                                "status": "correct" if all(check["correct"] for check in facet_checks.values()) else "missing_or_conflicting_identity_facet"}
    wanted_q, actual_q = query["qualifiers"], item.get("qualifiers", {})
    qualifier_checks = {key: _check(required, actual_q.get(key), canonicalize, key=key, present=key in actual_q,
                        operands=({"unit": required, "currency": wanted_q.get("currency"), "quantity_role": wanted_q.get("quantity_role")},
                                  {"unit": actual_q.get(key), "currency": actual_q.get("currency"), "quantity_role": actual_q.get("quantity_role")})
                        if key == "unit" else None)
                        for key, required in wanted_q.items()}
    checks["qualifiers"] = {"required": copy.deepcopy(wanted_q), "actual": copy.deepcopy(actual_q),
                            "checks": qualifier_checks, "correct": all(check["correct"] for check in qualifier_checks.values()),
                            "extra": {key: copy.deepcopy(value) for key, value in actual_q.items() if key not in wanted_q},
                            "status": "correct" if all(check["correct"] for check in qualifier_checks.values()) else "missing_or_conflicting_qualifier"}
    independent = [{"dimension": "subject", "correct": checks["subject"]["correct"] and bool(query["subject"]), "source": item["source"]},
                   {"dimension": "scope", "correct": context_ok and bool(required_context), "source": item["source"]}]
    independent.extend({"dimension": dimension, "correct": check["correct"], "source": item["source"]}
                       for dimension, check in qualifier_checks.items())
    checks["attribute"] = _check(query["attribute"], item.get("attribute", ""), canonicalize, key="attribute",
                                 context={"independent_checks": independent})
    return checks


def requirement_key(item: dict[str, Any], canonicalize: Canonicalize) -> tuple[Any, ...]:
    """Position qualifiers locate; logical conditions remain asserted answers.

    A changed condition, note or negation must not make a contradictory local
    statement disappear from the assertion comparison.
    """
    return (freeze(item.get("subject", ""), canonicalize), freeze(item["attribute"], canonicalize, dimension="attribute"),
            freeze(logical_context(item, canonicalize), canonicalize),
            freeze({key: value for key, value in item.get("identity_facets", {}).items() if key != "group"}, canonicalize),
            freeze(query_for(item)["qualifiers"], canonicalize))


def assertion_signature(item: dict[str, Any], canonicalize: Canonicalize) -> tuple[Any, ...]:
    q = item.get("qualifiers", {})
    if item.get('semantic_type') == 'toc_page':
        return ('printed_navigation_reference', freeze(item['value'], canonicalize)), freeze(q, canonicalize)
    if item.get('semantic_type') == 'printed_selection_state':
        state = decide_equivalence(item['value'], item['value'], 'selection_state')['canonical']['required']
        return ('printed_selection_state', state), freeze(q, canonicalize)
    if item.get('semantic_type') == 'printed_position_list':
        root = item['value_logic']
        members = [child['head'] for part in root.get('parts', []) if part.get('kind') == 'coordination'
                   for child in part['children']] or [root['head']]
        return ('printed_position_list', tuple(sorted(canonicalize(member) for member in members))), freeze(q, canonicalize)
    quantity = normalize_quantity({"value": item["value"], "unit": q.get("unit"), "currency": q.get("currency"),
                                   "quantity_role": item.get("quantity_role", q.get("quantity_role"))})
    number = exact_number(item["value"])
    value = (quantity["value"] if quantity["matched"] else ratio(number) if number is not None else item["value"]
             ) if item.get("role") != "identity" else item["value"]
    return freeze(value, canonicalize), freeze(q, canonicalize)


def _value_check(required, actual, canonicalize):
    if required.get('semantic_type') == 'toc_page' or actual.get('semantic_type') == 'toc_page':
        return {**_check(required['value'], actual['value'], canonicalize),
                'role_basis': 'printed_navigation_reference', 'quantity_equivalence_applicable': False}
    if required.get('semantic_type') == actual.get('semantic_type') == 'printed_position_list':
        from .requirement_ast import compare_requirement_ast

        decision = compare_requirement_ast(required.get('value_logic'), actual.get('value_logic'),
                                           context={'canonicalize': canonicalize, 'layer': 'B'})
        return {'required': required['value'], 'actual': actual['value'], 'correct': decision['equivalent'],
                'status': 'correct' if decision['equivalent'] else 'explicit_conflict', 'equivalence': decision}
    if required.get('semantic_type') == actual.get('semantic_type') == 'printed_selection_state':
        return _check(required['value'], actual['value'], canonicalize, key='selection_state')
    if (required.get("role") != "identity" and actual.get("role") != "identity"
            and exact_number(required["value"]) is not None and exact_number(actual["value"]) is not None):
        operands = tuple({"value": item["value"], "unit": item.get("qualifiers", {}).get("unit"),
                          "currency": item.get("qualifiers", {}).get("currency"),
                          "quantity_role": item.get("quantity_role", item.get("qualifiers", {}).get("quantity_role"))}
                         for item in (required, actual))
        return _check(required["value"], actual["value"], canonicalize, key="quantity", operands=operands)
    return _check(required["value"], actual["value"], canonicalize)


def _qualifier_check(required, actual, dimension, canonicalize):
    wanted, found = required.get("qualifiers", {}), actual.get("qualifiers", {})
    operands = tuple({"unit": q.get("unit"), "currency": q.get("currency"),
                      "quantity_role": item.get("quantity_role", q.get("quantity_role"))}
                     for item, q in ((required, wanted), (actual, found))) if dimension == "unit" else None
    return _check(wanted.get(dimension), found.get(dimension), canonicalize, key=dimension,
                  present=dimension in wanted and dimension in found, operands=operands)


def _literal_hits(attribute: str, literals: list[dict[str, Any]], canonicalize: Canonicalize, *,
                  allow_approximate: bool) -> list[dict[str, Any]]:
    wanted = canonicalize(attribute)
    hits = []
    for item in literals:
        text = canonicalize(item.get("text", ""))
        positions = [list(match.span()) for match in re.finditer(re.escape(wanted), text)] if wanted else []
        equivalent = text != wanted and role_label(text) == role_label(wanted)
        if equivalent:
            positions = [[0, len(text)]]
        if positions:
            hits.append({"id": item["id"], "source": snapshot_copy(item["source"]), "text": item["text"],
                         "scope": snapshot_copy(item.get("scope", [])), "role": item.get("role", "literal"),
                         "normalized_spans": positions, "recall": "declared_business_role_equivalence" if equivalent else "exact_or_declared_typographic_equivalence",
                         "decision": "literal_evidence_only", "reason": "literal_alone_does_not_prove_a_value_binding"})
    if not allow_approximate or not wanted:
        return hits
    exact_ids = {item["id"] for item in hits}
    for item in literals:
        text = canonicalize(item.get("text", ""))
        if item["id"] not in exact_ids and text and len(text) <= max(3 * len(wanted), 20):
            similarity = Levenshtein.normalized_similarity(wanted, text)
            if similarity >= 0.65:
                hits.append({"id": item["id"], "source": snapshot_copy(item["source"]), "text": item["text"],
                             "scope": snapshot_copy(item.get("scope", [])), "role": item.get("role", "literal"),
                             "recall": "approximate_literal_with_retained_difference", "similarity": similarity,
                             "required_literal": attribute, "actual_literal": item["text"],
                             "decision": "literal_evidence_only", "reason": "literal_alone_does_not_prove_a_value_binding"})
    return hits


def retrieve(query: dict[str, Any], candidates: list[dict[str, Any]], *, literals: list[dict[str, Any]],
             canonicalize: Canonicalize, contexts=None, declared_paths=(), context_labels=()) -> dict[str, Any]:
    scope_options = {"contexts": contexts, "declared_paths": declared_paths, "context_labels": context_labels}
    exact = [item for item in candidates if role_label(canonicalize(item["attribute"])) == role_label(canonicalize(query["attribute"]))]
    recalled = exact + [item for item in candidates if item not in exact and Levenshtein.normalized_similarity(
        canonicalize(query["attribute"]), canonicalize(item["attribute"])) >= 0.65]
    hits = []
    for item in recalled:
        checks = identity_checks(query, item, canonicalize, **scope_options)
        accepted = all(check["correct"] for check in checks.values())
        conflicting = [key for key, check in checks.items() if not check["correct"]]
        hits.append({"id": item["id"], "source": snapshot_copy(item["source"]), "candidate": snapshot_copy(item),
                     "identity": checks, "decision": "accepted" if accepted else "rejected",
                     "reason": "identity_and_context_verified_before_value_comparison" if accepted else "required_identity_missing_or_explicit_conflict",
                     "conflicting_dimensions": conflicting,
                     "recall": ("declared_business_role_equivalence" if item in exact and canonicalize(item["attribute"]) != canonicalize(query["attribute"])
                                else "same_complete_attribute" if item in exact else "approximate_attribute_with_retained_difference"),
                     "context_evidence": {"candidate_scope": snapshot_copy(item.get("scope", [])),
                                          "candidate_facets": snapshot_copy(item.get("identity_facets", {})),
                                          "row_evidence": snapshot_copy(item.get("row_evidence", [])),
                                          "header_evidence": snapshot_copy(item.get("header_evidence", [])),
                                          "source": snapshot_copy(item["source"])}})
    return {"query": copy.deepcopy(query), "candidates": hits,
            "textual_hits": _literal_hits(query["attribute"], literals, canonicalize, allow_approximate=True),
            "accepted": [hit["id"] for hit in hits if hit["decision"] == "accepted"]}


def _family(item: dict[str, Any], canonicalize: Canonicalize) -> tuple[Any, ...]:
    return (freeze(item.get("subject", ""), canonicalize), freeze(logical_context(item, canonicalize), canonicalize),
            freeze({key: value for key, value in item.get("identity_facets", {}).items() if key != "group"}, canonicalize))


def _record_id(item: dict[str, Any]) -> Any:
    return item.get("record_id") or item.get("source", {}).get("record_id")


def record_vector(fields: list[dict[str, Any]], canonicalize: Canonicalize, *, attribute_labels=None) -> Any:
    attribute_labels = attribute_labels or {}
    return tuple(sorted(Counter((freeze(attribute_labels.get(item["id"], item["attribute"]), canonicalize, dimension="attribute"),
                                 assertion_signature(item, canonicalize)) for item in fields).items(), key=repr))


def _record_comparison(members: list[dict[str, Any]], candidates: list[dict[str, Any]],
                       canonicalize: Canonicalize, *, identity_owners=None, **scope_options) -> dict[str, Any] | None:
    metric_members = [item for item in members if item.get("role") != "identity"]
    occurrences = Counter(requirement_key(item, canonicalize) for item in metric_members)
    if len(occurrences) < 2 or max(occurrences.values(), default=0) < 2:
        return None
    relevant, labels, field_equivalence = [], {}, []
    for item in candidates:
        if item.get("role") == "identity":
            continue
        matched = []
        for wanted in metric_members:
            if identity_owners is not None and identity_owners.get(item["id"]) != requirement_key(wanted, canonicalize):
                continue
            checks = identity_checks(query_for(wanted), item, canonicalize, **scope_options)
            if all(part["correct"] for part in checks.values()):
                matched.append((wanted, checks["attribute"].get("equivalence")))
        attributes = {freeze(wanted["attribute"], canonicalize, dimension="attribute") for wanted, _ in matched}
        if len(attributes) > 1:
            return {"rule": "complete_record_vector_multiset", "complete": False, "equal": None,
                    "reason": "duplicate_record_field_identity_ambiguous", "required_records": [], "actual_records": []}
        if matched:
            relevant.append(item)
            labels[item["id"]] = matched[0][0]["attribute"]
            field_equivalence.append({"candidate_id": item["id"], "required_attribute": labels[item["id"]],
                                      "equivalence": copy.deepcopy(matched[0][1])})
    if any(not _record_id(item) for item in [*metric_members, *relevant]):
        return {"rule": "complete_record_vector_multiset", "complete": False, "equal": None,
                "reason": "duplicate_record_provenance_unsupported", "required_records": [], "actual_records": []}
    by_record: list[dict[Any, list[dict[str, Any]]]] = []
    for collection in (metric_members, relevant):
        records: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for item in collection:
            records[_record_id(item)].append(item)
        by_record.append(records)
    if len(by_record[0]) == len(by_record[1]) == 1:
        # Complete assertion sets still reject a conflicting repeated field.
        # With only one record there is no cross-record association to check;
        # its other independent fields must retain their own outcomes.
        return None
    equal = Counter(record_vector(fields, canonicalize) for fields in by_record[0].values()) == Counter(
        record_vector(fields, canonicalize, attribute_labels=labels) for fields in by_record[1].values())
    return {"rule": "complete_record_vector_multiset", "complete": True, "equal": equal,
            "reason": "complete_record_vectors_equal" if equal else "complete_record_vectors_differ",
            "field_equivalence": field_equivalence,
            "required_records": [{"record_id": key, "fields": snapshot_copy(fields)} for key, fields in by_record[0].items()],
            "actual_records": [{"record_id": key, "fields": snapshot_copy(fields)} for key, fields in by_record[1].items()]}


def _bind_candidate_capacity(groups, traces, canonicalize):
    """Give an actual occurrence at most one answer-independent identity owner.

    Exact declared labels outrank the controlled typo rule. More specific
    printed position constraints outrank a broader compatible position. A tie
    remains insufficient; neither expected values nor iteration order choose
    between indistinguishable positions. Repeated identical requirements keep
    their multiset comparison within one group and still require occurrences.
    """
    eligibility = defaultdict(list)
    for key in groups:
        query = traces[key]["query"]
        scope = logical_context(query, canonicalize)
        specificity = (len(scope), len(query["identity_facets"]), len(query["qualifiers"]))
        for hit in traces[key]["candidates"]:
            if hit["decision"] != "accepted":
                continue
            exact_label = hit["recall"] != "approximate_attribute_with_retained_difference"
            eligibility[hit["id"]].append((key, (int(exact_label), *specificity)))
    owners, proofs = {}, {}
    for ident, options in eligibility.items():
        best = max(rank for _key, rank in options)
        preferred = [key for key, rank in options if rank == best]
        owner = preferred[0] if len(preferred) == 1 else None
        owners[ident] = owner
        proofs[ident] = {
            "candidate_id": ident,
            "eligible_requirement_groups": [groups[key][0]["id"] for key, _rank in options],
            "best_identity_groups": [groups[key][0]["id"] for key in preferred],
            "owner_requirement_group": groups[owner][0]["id"] if owner is not None else None,
            "status": "bound" if owner is not None else "insufficient",
            "identity_rank": list(best), "values_used": False,
        }
    for key, trace in traces.items():
        trace["identity_accepted"] = list(trace["accepted"])
        evidence = []
        for hit in trace["candidates"]:
            if hit["decision"] != "accepted":
                continue
            proof = proofs[hit["id"]]
            evidence.append(copy.deepcopy(proof))
            hit["capacity"] = copy.deepcopy(proof)
            if owners[hit["id"]] != key:
                hit["decision"] = "rejected"
                hit["reason"] = ("candidate_identity_capacity_insufficient" if owners[hit["id"]] is None
                                 else "candidate_occurrence_owned_by_another_requirement")
        trace["accepted"] = [hit["id"] for hit in trace["candidates"] if hit["decision"] == "accepted"]
        trace["capacity"] = {"rule": "single_actual_occurrence_owner_before_values",
                             "required_occurrences": len(groups[key]), "evidence": evidence}
    return owners


def grade_business(reference: list[dict[str, Any]], candidates: list[dict[str, Any]], *,
                   literals: list[dict[str, Any]], canonicalize: Canonicalize,
                   contexts=None, declared_paths=(), context_labels=()) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scope_options = {"contexts": contexts, "declared_paths": declared_paths, "context_labels": context_labels}
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    families: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for item in reference:
        groups[requirement_key(item, canonicalize)].append(item)
        families[_family(item, canonicalize)].append(item)
    candidate_ids = [item["id"] for item in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate business objects require unique actual identities")
    traces = {key: retrieve(query_for(members[0]), candidates, literals=literals, canonicalize=canonicalize, **scope_options)
              for key, members in groups.items()}
    owners = _bind_candidate_capacity(groups, traces, canonicalize)
    record_checks = {key: _record_comparison(members, candidates, canonicalize, identity_owners=owners, **scope_options)
                     for key, members in families.items()}
    rows, blockers = [], []
    for key, members in groups.items():
        trace = traces[key]
        accepted = set(trace["accepted"])
        actual = [item for item in candidates if item["id"] in accepted]
        same = Counter(assertion_signature(item, canonicalize) for item in members) == Counter(
            assertion_signature(item, canonicalize) for item in actual)
        record = record_checks[_family(members[0], canonicalize)]
        unsupported_extra = sorted({extra for item in actual for extra in item.get("qualifiers", {})
                                    if extra not in members[0].get("qualifiers", {}) and extra not in KNOWN_QUALIFIERS})
        unresolved_units = []
        for hit in trace["candidates"]:
            checks = hit["identity"]
            qualifier_checks = checks["qualifiers"]["checks"]
            unresolved = qualifier_checks.get("unit", {}).get("equivalence", {}).get("status") == "unresolved"
            if (unresolved and qualifier_checks["unit"]["status"] != "missing"
                    and all(check["correct"] for dimension, check in checks.items() if dimension != "qualifiers")
                    and all(check["correct"] for dimension, check in qualifier_checks.items() if dimension != "unit")):
                unresolved_units.append(hit)
        unsupported = unsupported_extra or unresolved_units or (record is not None and not record["complete"])
        if unsupported:
            reason = ("extra_qualifier_semantics_unsupported" if unsupported_extra else "unit_equivalence_unsupported"
                      if unresolved_units else record.get("reason", "duplicate_record_provenance_unsupported"))
            blockers.append({"reason": reason, "source": snapshot_copy(members[0]["source"]), "layers": ["B"],
                             "extra_qualifiers": unsupported_extra,
                             "unit_decisions": [copy.deepcopy(hit["identity"]["qualifiers"]["checks"]["unit"]["equivalence"])
                                                for hit in unresolved_units]})
        else:
            reason = ("complete_assertion_set_equal" if same else "missing_or_conflicting_identity_position" if not actual
                      else "complete_assertion_value_or_qualifier_set_different")
        if record and record["complete"] and not record["equal"]:
            same = False
            reason = "complete_record_vector_multiset_different"
        for item in members:
            row = {"id": item["id"], "layer": "B", "role": item["role"], "expected": snapshot_copy(item),
                   "actual": snapshot_copy(actual), "outcome": "correct" if same and not unsupported else "incorrect",
                   "retrieval": snapshot_copy(trace), "reason": reason,
                   "comparisons": [{"id": candidate["id"],
                                    "value": _value_check(item, candidate, canonicalize),
                                    "qualifiers": {dimension: _qualifier_check(item, candidate, dimension, canonicalize)
                                         for dimension in sorted(set(item.get("qualifiers", {})) | set(candidate.get("qualifiers", {})))}}
                                   for candidate in actual],
                   "root_cause": ("record_family:" + repr(_family(item, canonicalize))
                                  if record and not record.get("equal") else "binding:" + repr(key))}
            if record:
                row["record_comparison"] = snapshot_copy(record)
            if unsupported:
                row["software_failure"] = True
            rows.append(row)
    numerator, denominator = sum(row["outcome"] == "correct" for row in rows), len(rows)
    return {"numerator": numerator if not blockers else None, "denominator": denominator,
            "score": 100 * numerator / denominator if denominator and not blockers else None,
            "complete": not blockers, "blockers": blockers}, rows
