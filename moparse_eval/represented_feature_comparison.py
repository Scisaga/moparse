"""Source guards for features whose answers already live in B/L relations.

These checks introduce no new votes or matcher. Existing grade_business and
grade_relations own the comparison; this module establishes that their typed
inputs still express the source-bound reference or collection completely.
"""

from __future__ import annotations

import json

from .cjk_measurement_requirements import read_cjk_measurements
from .document_composition_requirements import (
    read_document_composition,
    validate_document_compositions,
)
from .enumeration_binding import member_for_source, plan_from_syntax, validate_enumeration_bindings
from .explicit_reference_requirements import read_explicit_references
from .quoted_nominal import scan_quoted_nominals
from .quoted_nominal_validation import validate_quoted_nominals

REPRESENTED_FEATURES = frozenset({"explicit_reference_binding", "enumeration_context_scope",
                                  "document_composition", "page_reference_binding", "quoted_nominal_scope",
                                  "shared_period_scope", "same_subject_relative_clause", "year_on_year_comparison",
                                  "quantity_assertion", "compact_column_binding"})
REPRESENTED_INPUT_KEYS = (
    "syntax", "enumeration_contexts", "relations", "explicit_references", "reference_roles", "reference_dispositions",
    "semantic_operands", "semantic_operand_relations", "compact_schemas",
)


def _key(source):
    return json.dumps(source, ensure_ascii=False, sort_keys=True)


def _same_relation(actual, expected):
    return all(actual.get(key) == expected.get(key) for key in ("type", "left", "right", "source", "binding_evidence"))


def _reference_sources(graph):
    """Discover directives in source text even when a derived feature is cut."""
    found = {}
    for item in graph.get("syntax", []):
        text, source = item.get("text"), item.get("source")
        if not isinstance(text, str) or not isinstance(source, dict):
            continue
        for reference in read_explicit_references(text, source)["references"]:
            found[_key(reference["directive_source"])] = reference
    return found


def _check_owner(reference, graph, resolve):
    proof = reference.get("owner_proof")
    if not proof or not proof.get("evidence"):
        raise ValueError("reference has no independently printed owner")
    owner, evidence = proof["owner"], proof["evidence"]
    syntax = graph.get("syntax", [])
    if all(item.get("kind") == "heading_scope" for item in evidence):
        if owner != {"identity": {"role": "heading_scope"}, "scope": [item["text"] for item in evidence]}:
            raise ValueError("reference heading identity differs from its printed owner")
        for index, item in enumerate(evidence):
            if not any(node.get("kind") == "heading" and node.get("text") == item["text"]
                       and node.get("source") == item["source"] and node.get("scope") == owner["scope"][:index + 1]
                       for node in syntax):
                raise ValueError("reference owner borrows an adjacent heading source")
        if owner["scope"] != reference["scope"]:
            raise ValueError("reference scope differs from its actual owner")
    elif len(evidence) == 1 and evidence[0].get("kind") == "printed_field_label":
        item = evidence[0]
        if owner != {"identity": {"role": "printed_field", "attribute": item["text"]}, "scope": reference["scope"]}:
            raise ValueError("reference field identity differs from its printed owner")
        if not any(node.get("kind") == "field_body" and node.get("printed_label") == item["text"]
                   and node.get("label_source") == item["source"] and node.get("scope") == reference["scope"]
                   for node in syntax):
            raise ValueError("reference owner has no actual field label")
    else:
        raise ValueError("reference owner representation is not independently supported")
    for item in evidence:
        if resolve(item["source"]) != item["text"]:
            raise ValueError("reference owner differs from its original source")
    return proof


def _check_references(graph, resolve, discovered):
    stored = graph.get("explicit_references", [])
    if not stored or len({_key(item["directive_source"]) for item in stored}) != len(stored):
        raise ValueError("reference requirements are missing or duplicated")
    if set(discovered) != {_key(item["directive_source"]) for item in stored}:
        raise ValueError("source reference directives differ from retained requirements")
    relation_types = {"explicit_reference_target", "reference_directive_scope"}
    expected_relations, expected_roles, expected_dispositions = [], [], []
    for reference in stored:
        if resolve(reference["source"]) != reference["text"]:
            raise ValueError("reference literal differs from its original source")
        owner = _check_owner(reference, graph, resolve)
        readback = read_explicit_references(reference["text"], reference["source"], scope=reference["scope"],
            owner=owner["owner"], owner_evidence=owner["evidence"])
        if not readback["complete"] or readback["references"] != [reference]:
            raise ValueError("reference target or role differs from its complete source interpretation")
        expected_relations.extend(readback["relations"])
        expected_roles.extend(readback["semantic_roles"])
        expected_dispositions.extend(readback["source_dispositions"])
    actual_relations = [edge for edge in graph.get("relations", []) if edge.get("type") in relation_types]
    remaining = list(actual_relations)
    for expected in expected_relations:
        matches = [edge for edge in remaining if _same_relation(edge, expected)]
        if len(matches) != 1:
            raise ValueError("reference source-bound relation is missing, changed or duplicated")
        remaining.remove(matches[0])
    if remaining or graph.get("reference_roles", []) != expected_roles or graph.get("reference_dispositions", []) != expected_dispositions:
        raise ValueError("reference relation, role or disposition transport is incomplete")
    return {"reference_sources": [item["source"] for item in stored], "relation_types": sorted(relation_types),
            "comparison_owner": "grade_relations", "business_votes_added": 0}


def _check_enumerations(graph, resolve, planned):
    contexts = graph.get("enumeration_contexts", [])
    if not contexts or contexts != planned["contexts"] or planned.get("blockers"):
        raise ValueError("collection source syntax differs from retained context scope")
    facts = graph.get("business", [])
    transport = {"context": {"syntax": graph.get("syntax", []), "enumeration_contexts": contexts},
        "required_matcher_features": graph.get("required_matcher_features", []),
        "relations": graph.get("relations", []), "projections": {"B": [fact["id"] for fact in facts]}}
    validate_enumeration_bindings(transport, {fact["id"]: fact for fact in facts}, resolve)
    for context in contexts:
        for member in context["members"]:
            owned = [fact for fact in facts if (binding := member_for_source(planned, fact["source"]))
                     and binding[0] == context and binding[1] == member]
            if not owned or any(not fact.get("enumeration_evidence") for fact in owned):
                raise ValueError("collection member lacks its complete source-bound business disposition")
    expected = sum(bool(fact.get("enumeration_evidence")) for fact in facts)
    actual = sum(edge.get("type") == "enumeration_membership" for edge in graph.get("relations", []))
    if actual != expected:
        raise ValueError("collection membership is duplicated or borrowed from another source")
    return {"collection_sources": [context["source"] for context in contexts],
            "relation_types": ["enumeration_declaration", "enumeration_membership", "qualifier_scope"],
            "comparison_owner": "grade_business_and_grade_relations", "business_votes_added": 0}


def _composition_sources(graph):
    from .prose_requirements import _sentence_spans
    from .quoted_nominal import _source

    sources = {}
    for item in graph.get("syntax", []):
        text, source = item.get("text"), item.get("source")
        if not isinstance(text, str) or not isinstance(source, dict):
            continue
        for start, end in _sentence_spans(text):
            origin = _source(source, start, end)
            readback = read_document_composition(text[start:end], origin)
            if readback["matched"]:
                sources[_key(origin)] = {"text": text[start:end], "source": origin}
    return list(sources.values())


def _check_compositions(graph, resolve, sources):
    if not sources:
        raise ValueError("document composition lacks its original source assertion")
    if any(not read_document_composition(item["text"], item["source"])["complete"] for item in sources):
        raise ValueError("document composition source semantics remain unresolved")
    transport = {"sources": sources, "logic": graph.get("logical_statements", []),
                 "required_matcher_features": graph.get("required_matcher_features", []),
                 "relations": graph.get("relations", []), "unresolved": graph.get("blockers", [])}
    validate_document_compositions(transport, graph.get("business", []), resolve)
    return {"composition_sources": [item["source"] for item in sources],
            "relation_types": ["document_part_of", "page_reference_scope"],
            "comparison_owner": "native_document_composition_ast_and_grade_relations", "business_votes_added": 0}


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


def _has_quoted_roles(graph):
    for node in [*graph.get("business", []), *graph.get("semantic_operands", []),
                 *_walk(graph.get("logical_statements", []))]:
        if node.get("quoted_nominals"):
            return True
        for role in ("subject", "object"):
            if isinstance(node.get(role), str) and isinstance(node.get(role + "_source"), dict):
                if scan_quoted_nominals(node[role], node[role + "_source"])["matched"]:
                    return True
    return False


def _check_quoted_roles(graph, resolve):
    fields = [*graph.get("business", []), *graph.get("semantic_operands", [])]
    if not _has_quoted_roles(graph) or not fields:
        raise ValueError("quoted nominal scope lacks its interpreted source role")
    transport = {"relations": graph.get("relations", []),
                 "operand_relations": graph.get("semantic_operand_relations", []),
                 "required_matcher_features": graph.get("required_matcher_features", [])}
    validate_quoted_nominals(transport, fields, resolve)
    proofs = [proof for fact in fields for proof in fact.get("quoted_nominals", [])]
    if not proofs:
        raise ValueError("quoted nominal source has no complete retained constituent proof")
    return {"nominal_sources": [proof["source"] for proof in proofs],
            "relation_types": ["narrative_quoted_nominal_scope"],
            "comparison_owner": "source_closed_nominal_ast_and_grade_relations", "business_votes_added": 0}


def _measurement_sources(graph):
    from .prose_requirements import _sentence_spans
    from .quoted_nominal import _source

    sources = {}
    for item in graph.get("syntax", []):
        text, source = item.get("text"), item.get("source")
        if not isinstance(text, str) or not isinstance(source, dict):
            continue
        for start, end in _sentence_spans(text):
            origin = _source(source, start, end)
            readback = read_cjk_measurements(text[start:end], origin, scope=item.get("scope", []))
            if readback["matched"]:
                sources[_key(origin)] = readback
    return list(sources.values())


def _check_measurements(graph, resolve, readings, feature):
    selected = [readback for readback in readings if feature in readback["required_matcher_features"]]
    if not selected or any(not readback["complete"] for readback in selected):
        raise ValueError("measurement feature lacks a complete native source sequence")
    relation_types = set()
    for readback in selected:
        if resolve(readback["source"]) != readback["raw_text"]:
            raise ValueError("measurement sequence differs from its original source")
        if not all(tree in graph.get("logical_statements", []) for tree in readback["logic"]):
            raise ValueError("measurement sequence dropped or changed its typed source structure")
        for fact in readback["facts"]:
            # The reference projection may use the value cut as its public
            # source. Its independent role cuts still identify this exact
            # source clause without selecting by the expected numeric value.
            own = [item for item in graph.get("business", []) if all(item.get(key) == fact.get(key)
                   for key in ("subject_source", "predicate_source", "object_source"))]
            keys = ("subject", "attribute", "predicate", "value", "object", "qualifiers", "subject_source",
                    "predicate_source", "value_source", "object_source", "qualifier_sources", "logic", "subject_binding_evidence")
            if len(own) != 1 or any(own[0].get(key) != fact.get(key) for key in keys):
                raise ValueError("measurement fact, antecedent or qualifier does not match its complete source")
        for expected in readback["relations"]:
            relation_types.add(expected["type"])
            if sum(_same_relation(edge, expected) for edge in graph.get("relations", [])) != 1:
                raise ValueError("measurement qualifier or relative-subject relation is missing or source-inconsistent")
    return {"sequence_sources": [readback["source"] for readback in selected], "relation_types": sorted(relation_types),
            "comparison_owner": "native_measurement_ast_and_grade_business_and_grade_relations", "business_votes_added": 0}


def _check_compact_sources(graph):
    from .source_obligations import _bound_relations, _compact_source_bindings, _residue

    entries = [{"id": f"syntax:{i}", "text": item["text"], "source": item["source"],
                "source_kind": item["kind"]} for i, item in enumerate(graph.get("syntax", []))]
    view = {"nodes": graph.get("business", []), "projections": {"B": [f["id"] for f in graph.get("business", [])]},
            "context": {"compact_schemas": graph.get("compact_schemas", [])}}
    evidence = _compact_source_bindings({"sources": entries}, view, lambda f: _bound_relations(f, graph.get("relations", [])))
    required = {f["id"] for f in graph.get("business", []) if f.get("compact_column")}
    proved = {p["requirement"] for proofs in evidence.values() for p in proofs if p.get("role") == "source_bound_compact_value"}
    if not required or required != proved:
        raise ValueError("compact facts do not retain their own printed column/value sources")
    for entry in entries:
        if entry["id"] in evidence and _residue(entry["text"], (0, len(entry["text"])), evidence[entry["id"]]):
            raise ValueError("compact record contains unbound printed content")
    for declaration in graph.get("compact_schemas", []):
        if not any(e["source"] == declaration["schema"]["source"] and e["id"] in evidence for e in entries):
            raise ValueError("a declared compact column has no independently bound record")
    return {"fact_count": len(proved), "source_count": len(evidence), "comparison_owner": "printed_columns_and_scalar_B_L"}


def represented_feature_checks(graph, resolve):
    """Return runtime source checks, never certify independent acceptance.

    Discovery follows source syntax and retained representations, so deleting a
    feature name cannot suppress the check. No narrative AST is manufactured.
    ``resolve`` reads this side's retained literal source bank only.
    """
    declared = set(graph.get("required_matcher_features", []))
    discovered = _reference_sources(graph)
    planned = plan_from_syntax(graph.get("syntax", []))
    compositions = _composition_sources(graph)
    measurements = _measurement_sources(graph)
    features = declared & REPRESENTED_FEATURES
    if graph.get("compact_schemas") or any(f.get("compact_column") for f in graph.get("business", [])):
        features.add("compact_column_binding")
    if discovered or graph.get("explicit_references") or any(edge.get("type") in {
            "explicit_reference_target", "reference_directive_scope"} for edge in graph.get("relations", [])):
        features.add("explicit_reference_binding")
    if planned["contexts"] or graph.get("enumeration_contexts") or any(fact.get("enumeration_evidence")
            for fact in graph.get("business", [])):
        features.add("enumeration_context_scope")
    if compositions or any(tree.get("kind") == "document_composition" for tree in graph.get("logical_statements", [])):
        features.update({"document_composition", "page_reference_binding"})
    if _has_quoted_roles(graph):
        features.add("quoted_nominal_scope")
    for reading in measurements:
        features.update(set(reading["required_matcher_features"]) & REPRESENTED_FEATURES)
    checks = {}
    for feature in sorted(features):
        try:
            if feature not in declared:
                raise ValueError("source-bound representation lost its comparison dependency")
            if feature == "explicit_reference_binding":
                proof = _check_references(graph, resolve, discovered)
            elif feature == "enumeration_context_scope":
                proof = _check_enumerations(graph, resolve, planned)
            elif feature == "quoted_nominal_scope":
                proof = _check_quoted_roles(graph, resolve)
            elif feature in {"shared_period_scope", "same_subject_relative_clause", "year_on_year_comparison", "quantity_assertion"}:
                proof = _check_measurements(graph, resolve, measurements, feature)
            elif feature == "compact_column_binding":
                proof = _check_compact_sources(graph)
            else:
                proof = _check_compositions(graph, resolve, compositions)
            check = {"equivalent": True, "status": "equivalent", "reason": "source_bound_relation_inputs_complete",
                     "proof": {"representation": "source_bound_relations", **proof}}
        except (KeyError, TypeError, ValueError) as error:
            check = {"equivalent": False, "status": "unresolved", "reason": "source_bound_relation_inputs_incomplete",
                     "proof": {"representation": "source_bound_relations", "failure": str(error)}}
        checks[feature] = check
    return {"features": sorted(features), "checks": checks}
