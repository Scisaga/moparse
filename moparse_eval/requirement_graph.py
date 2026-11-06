"""Read-only, source-bound expected requirements and independent projections.

The JSON graph is the computational view; XML is a rendering of the same
objects. Neither is an editable reference or a corpus validation result.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from .measurement_evidence import read_measurement_literal
from .source_requirements import plan_field_body, plan_mixed_source

LAYERS = ("T", "L", "B")
# User-retained pending declarations only. These identities never select a
# parser answer, remove a target, or waive publication of complete grades.
_DEFERRED_SCOPE = {
    "alibaba-strategies-p009-010": ("complex-alibaba-2025-annual", 230, [10, 11], [11]),
    "midea-strategy-p025-036": ("complex-midea-2024-annual", 417, [36, 37], [37]),
    "pboc-macro-columns-p011-018": ("complex-pboc-stability-2024", 252, [18, 19], [19]),
    "pboc-policy-columns-p019-026": ("complex-pboc-stability-2024", 252, [18, 19], [18]),
    "pboc-banking-columns-p029-040": ("complex-pboc-stability-2024", 540, [40, 41], [41]),
}


def is_deferred_input_scope(sample_id: str, issue: dict[str, Any]) -> bool:
    """Fence the five authorized deferrals; all other unknown scopes block."""
    declaration = _DEFERRED_SCOPE.get(sample_id)
    if issue.get("reason") != "input_scope_context" or declaration is None:
        return False
    document, line, pages, absent = declaration
    source = issue.get("source", {})
    if source.get("lines") != [line, line] or Path(source.get("path", "")).parts[-2:] != (document, "expected.md"):
        return False
    outside = issue.get("outside_selection", [])
    return len(outside) == 1 and (outside[0].get("kind") == "mixed_page_selection_declaration"
        and outside[0].get("declared_source_pages") == pages and outside[0].get("outside_source_pages") == absent)


def _key(source: dict[str, Any]) -> tuple[Any, ...]:
    return source.get("path"), tuple(source.get("lines", [])), source.get("cell")


def _sources(expected: dict[str, Any]) -> list[dict[str, Any]]:
    from .prose_requirements import _sentence_spans

    result = []
    for target in expected.get("targets", []):
        reference = copy.deepcopy(target["reference"])
        text = target.get("raw_text", target.get("text", ""))
        plan = None if target["kind"] in {"heading", "table", "image_caption"} or target.get("has_children") else plan_mixed_source(text, reference)
        if plan is None and target["kind"] in {"text", "paragraph", "item"} and not target.get("has_children") and not re.match(r"[^:：=\n]{1,160}[:：=]", text):
            sentences = _sentence_spans(text)
            if len(sentences) > 1:
                plan = {"rule_id": "printed_sentence_source_inventory", "fragments": [
                    {"text": text[a:b], "source": {**copy.deepcopy(reference), "text_span": [a, b]}, "syntax": "sentence"}
                    for a, b in sentences if text[a:b].strip()]}
        field_fragments = []
        parts = plan["fragments"] if plan else [{"text": text, "source": reference, "syntax": "whole"}]
        for part in parts:
            body = plan_field_body(part["text"], part["source"]) if target["kind"] not in {"heading", "table", "image_caption"} else None
            if body:
                field_fragments.append({"text": body["label"], "source": body["label_source"], "syntax": "field_label"})
                for a, b in _sentence_spans(body["body"]):
                    offset = body["body_source"]["text_span"][0]
                    field_fragments.append({"text": body["body"][a:b], "syntax": "field_body_sentence",
                        "source": {**copy.deepcopy(body["body_source"]), "text_span": [offset + a, offset + b]}})
            elif plan:
                field_fragments.append(part)
        if field_fragments:
            plan = {"rule_id": "printed_field_body_source_inventory", "fragments": field_fragments}
        if plan:
            for fragment in plan["fragments"]:
                result.append({"id": f"source:{len(result)}", "kind": "fragment", "text": fragment["text"],
                               "raw": fragment["text"], "source": fragment["source"], "target_id": target["id"],
                               "fragment_of": copy.deepcopy(reference), "fragment_syntax": fragment["syntax"],
                               "interpretation_rule": plan["rule_id"]})
        result.append({"id": f"source:{len(result)}", "kind": target["kind"], "text": text,
                       "raw": target.get("raw", text), "source": reference,
                       "target_id": target["id"], "has_children": target.get("has_children", False),
                       "parents": copy.deepcopy(target.get("parents", []))})
        if target["kind"] in {"heading", "image_caption"} and text:
            from .narrative_requirements import read_narrative
            from .proposition_requirements import read_propositions

            result[-1]["contains_explicit_statement"] = bool(
                read_propositions(text, reference)["matched"] or read_narrative(text, reference)["logic"])
        for cell in target.get("cells", []):
            source = {**reference, "cell": cell.get("id", cell.get("native_path")),
                      "row": cell.get("row"), "column": cell.get("col")}
            result.append({"id": f"source:{len(result)}", "kind": "cell", "text": cell.get("text", ""),
                           "raw": cell.get("text", ""), "source": source,
                           "target_id": target["id"], "native": copy.deepcopy(cell)})
    return result


def _cover(entry: dict[str, Any], source: dict[str, Any]) -> bool:
    own = entry["source"]
    if own.get("path") != source.get("path"):
        return False
    if source.get("cell"):
        return own.get("cell") == source["cell"]
    if own.get("cell"):
        return False
    a, b = own.get("lines", [0, 0])
    c, d = source.get("lines", [0, 0])
    if not a <= c <= d <= b:
        return False
    if own.get("text_span"):
        bounds = source.get("text_span")
        return bool(bounds and own["text_span"][0] <= bounds[0] <= bounds[1] <= own["text_span"][1])
    return True


def _walk_sources(value):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and ("lines" in value or "cell" in value):
            yield value
        for item in value.values():
            yield from _walk_sources(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_sources(item)


def _literal(sources, source):
    for entry in sources:
        if not _cover(entry, source):
            continue
        text = entry["text"]
        bounds = source.get("text_span")
        if bounds is None:
            return text
        offset = entry["source"].get("text_span", [0, 0])[0]
        a, b = bounds
        if 0 <= a - offset <= b - offset <= len(text):
            return text[a - offset:b - offset]
    return None


def _literal_source(sources, source, text):
    """Bound a known readback literal within its own printed source only."""
    value = _literal(sources, source)
    if value is None:
        return copy.deepcopy(source)
    offset = source.get("text_span", [0, 0])[0]
    if value == text:
        return {**copy.deepcopy(source), "text_span": [offset, offset + len(text)]}
    measurement = read_measurement_literal(value, source)
    if measurement["matched"] and measurement["value"] == text:
        return copy.deepcopy(measurement["sources"]["value"])
    # This is a source subrange operation, not document-wide answer search.
    # Multiple occurrences remain ambiguous and are never resolved by value.
    positions = [match.start() for match in re.finditer(re.escape(text), value)] if text else [0]
    if len(positions) == 1:
        start = offset + positions[0]
        return {**copy.deepcopy(source), "text_span": [start, start + len(text)]}
    return copy.deepcopy(source)


def _node_sources(node):
    return list(_walk_sources(node))


def _normalize_fact(fact, sources):
    item = copy.deepcopy(fact)
    for fragment in item.get("source", {}).get("joined_fragments", []):
        original = next((entry for entry in sources if _cover(entry, fragment["source"])), None)
        if original:
            fragment["projected_text"] = fragment["text"]
            fragment["text"] = original["text"]
            fragment["join_rule"] = "legal_whitespace_projection"
    item["kind"] = "logical_group" if item.get("role") == "logical_group" else "proposition" if item.get("role") == "description" else "fact"
    origin = item.get("value_source", item.get("source", {}))
    item["value_source"] = _literal_source(sources, origin, item["value"])
    attribute_origin = item.get("attribute_source", item.get("source", {}).get("attribute_source", {}))
    if attribute_origin:
        item["attribute_source"] = _literal_source(sources, attribute_origin, item["attribute"])
    elif item.get("data_evidence"):
        labels = [*item.get("row_evidence", []), *item.get("header_evidence", [])]
        label = next((entry for entry in labels if str(entry.get("text", "")).strip() == item["attribute"]), None)
        if label:
            item["attribute_source"] = _literal_source(sources, label["source"], item["attribute"])
    basis = item.get("role_basis")
    item.setdefault("rule_id", basis if isinstance(basis, str) and basis else "explicit_typed_business_requirement")
    if item.get("predicate"):
        item.setdefault("predicate_source", copy.deepcopy(item.get("attribute_source", {})))
        item.setdefault("object_source", copy.deepcopy(item["value_source"]))
    return item


def _unresolved(projected, sources):
    result, seen = [], set()
    pending = projected.get("pending_requirements", [])
    for issue in [*projected.get("blockers", []), *pending]:
        item = copy.deepcopy(issue)
        source = item.get("source", {})
        layer = item.get("layers") or ["B", "L"]
        entry = next((entry for entry in sources if _cover(entry, source)), None)
        if not entry:
            # A declaration outside the selected scope is retained as a
            # dependency, never imported as a business requirement.
            entry = {"id": None, "text": item.get("text", ""), "source": source}
        item["source_id"] = entry["id"]
        item["layers"] = list(layer)
        item.setdefault("text", entry["text"])
        item.setdefault("reason", item.get("kind", "uninterpreted_requirement"))
        fragments = item.get("fragments", item.get("clauses", item.get("conditions", [])))
        if fragments:
            item["fragments"] = copy.deepcopy(fragments)
        signature = json.dumps([item["reason"], source, item["text"], sorted(layer)], sort_keys=True, ensure_ascii=False)
        if signature in seen:
            continue
        seen.add(signature)
        item["id"] = f"unresolved:{len(result)}"
        result.append(item)
    return result


def _reference_business_disposition(entry, projected):
    """Only fully covered navigation syntax is exempt from extra B votes."""
    dispositions = projected.get("reference_dispositions", [])
    if not dispositions or not entry["text"].strip():
        return None
    pieces = []
    for item in dispositions:
        pieces.append({"text": item["text"], "source": item["source"], "role": "explicit_reference"})
        proof = item.get("proof", {}).get("owner_proof") or {}
        pieces.extend({"text": evidence["text"], "source": evidence["source"], "role": "reference_field_label"}
                      for evidence in proof.get("evidence", []) if evidence.get("kind") == "printed_field_label")
    pieces.extend({"text": control.get("text", ""), "source": control.get("source", {}), "role": "reference_field_syntax"}
                  for control in projected.get("text_projection", {}).get("controls", [])
                  if control.get("reason") in {"explicit_field_delimiter", "explicit_record_sequence_separator"})
    own, offset, text = entry["source"], entry["source"].get("text_span", [0, 0])[0], entry["text"]
    covered, evidence = [False] * len(text), []
    for piece in pieces:
        source, span = piece["source"], piece["source"].get("text_span")
        if not span or any(source.get(key) != own.get(key) for key in ("path", "lines", "cell", "block", "block_lines")):
            continue
        a, b = span[0] - offset, span[1] - offset
        if 0 <= a <= b <= len(text) and text[a:b] == piece["text"]:
            covered[a:b] = [True] * (b - a)
            evidence.append(copy.deepcopy(piece))
    if all(covered[index] or char.isspace() for index, char in enumerate(text)):
        return ("source_proven_navigation_reference", "Every source character belongs to a printed reference or its independently sourced field syntax; navigation adds no business vote.",
                {"source_disposition_proof": evidence})
    return None


def _not_applicable(entry, layer, projected, business_sources=()):
    kind, text = entry["kind"], entry["text"]
    if layer == "T":
        from .source_obligations import toc_schema_control

        if control := toc_schema_control(entry, projected):
            return ("source_proven_toc_schema_control", "The original TOC header control binds actual navigation records.", control)
    if layer == "B":
        enumeration = next((context for context in projected.get("enumeration_contexts", [])
                            if context["declaration"].get("lexical_complete") and context.get("members")
                            and _cover(entry, context["source"])
                            and context["declaration"]["introduction"]["text"] == text), None)
        if enumeration:
            return ("source_proven_enumeration_declaration", "The declaration binds independently interpreted members rather than adding a business assertion.",
                    {"declaration": copy.deepcopy(enumeration["declaration"]), "boundary": copy.deepcopy(enumeration["boundary"])})
    if layer == "B" and (reference := _reference_business_disposition(entry, projected)):
        return reference
    controls = projected.get("text_projection", {}).get("controls", [])
    role = next((control for control in controls
                 if control.get("reason") == "explicit_record_schema_role"
                 and _cover(entry, control.get("source", {}))
                 and control.get("text", "").strip() == text.strip()), None)
    if kind == "cell" and layer in {"T", "B"} and role:
        return ("source_proven_record_schema_control", "The complete source cell declares a schema role, not an additional business fact.",
                {"control": copy.deepcopy(role)})
    labels = projected.get("scope_schema", {}).get("context_labels", [])
    label = next((label for label in labels
                  if label.get("role") == "printed_context_label"
                  and _cover(entry, label.get("source", {}))
                  and label.get("text", "").strip() == text.strip()), None)
    if layer == "B" and label and re.fullmatch(r"[^:：。.!?！？;；]+[:：]", text.strip()):
        return ("printed_empty_context_label", "This source explicitly labels following content and asserts no independent value.",
                {"label": copy.deepcopy(label)})
    syntax = next((item for item in projected.get("syntax", [])
                   if item.get("semantic_role") == "metric_declaration"
                   and _cover(entry, item.get("source", {})) and item.get("text") == text), None)
    if layer == "B" and syntax:
        return ("source_proven_metric_declaration", "The metric declaration supplies independently bound children, not an empty additional fact.",
                {"declaration": copy.deepcopy(syntax)})
    if kind == "table" and not text:
        return "table_requirements_are_owned_by_cells", "The table container delegates literal and semantic requirements to its original cells."
    if kind == "cell" and entry.get("native", {}).get("is_column_header"):
        if layer == "B":
            return "header_is_not_a_separate_business_vote", "The header declares the role or qualifier of independently bound data."
        if layer == "T" and re.fullmatch(r"Attribute|Property|Field|Value|Metric|属性|屬性|字段|值|指标|指標|项目|項目", text.strip(), re.I):
            return "explicit_property_value_schema_control", "This complete header is structural schema syntax; actual business labels remain text."
    if layer == "B" and kind in {"heading", "image_caption"}:
        if entry.get("contains_explicit_statement"):
            return None
        return "context_or_caption_is_not_independent_business_vote", "The printed context remains in T; its bindings are evaluated separately."
    if layer == "B" and re.match(r"^(?:Units?|Currency|单位|單位|币种|幣種|期间|期間|年度)\s*[:：]", text, re.I):
        return "qualifier_is_not_an_additional_business_vote", "An explicit qualifier constrains facts instead of adding another fact."
    if kind == "cell" and not text.strip():
        return "empty_printed_cell_has_no_literal_requirement", "The empty slot is retained by its actual table structure."
    if layer == "L" and (_not_applicable(entry, "B", projected, business_sources) or any(
            _cover(entry, source) for source in business_sources)):
        return "no_additional_independent_relation_declared", "A positive source interpretation establishes no additional relation beyond the bound facts or schema."
    if layer == "T" and kind == "table" and not text:
        return "table_text_is_owned_by_source_cells", "The original table is preserved; its cell literals supply the text requirements."
    return None


def compile_requirement_graph(expected: dict[str, Any]) -> dict[str, Any]:
    """Compile one selected reference before any candidate is read."""
    from .reference_compiler import compile_reference_semantics
    from .source_obligations import audit_source_obligations, build_source_obligation_inventory

    inventory = build_source_obligation_inventory(expected)
    sources = _sources(expected)
    projected = compile_reference_semantics(expected)
    text_nodes = [{**copy.deepcopy(item), "kind": "text"} for item in projected["text"]]
    facts = [_normalize_fact(item, sources) for item in projected["business"]]
    operands = [{**_normalize_fact(item, sources), "id": f"operand:{index}", "kind": "semantic_operand"}
                for index, item in enumerate(projected.get("semantic_operands", []))]
    relations = copy.deepcopy(projected["relations"])
    by_fact = {item["id"]: item for item in facts}
    for relation in relations:
        if relation["type"] == "qualifier_scope" and relation.get("fact_id") in by_fact:
            fact = by_fact[relation["fact_id"]]
            key = relation["left"].get("type")
            origin = fact.get("qualifier_sources", {}).get(key) or fact.get("qualifier_provenance", {}).get(key, {}).get("source")
            if origin:
                relation["source"] = copy.deepcopy(origin)
        relation.setdefault("rule_id", "explicit_" + relation["type"])
    nodes = [*text_nodes, *facts, *operands]
    node_sources = {item["id"]: _node_sources(item) for item in [*text_nodes, *facts, *relations]}
    business_sources = [source for fact in facts for source in node_sources[fact["id"]]]
    unresolved = _unresolved(projected, sources)
    graph = {"sample_id": expected["sample_id"], "standard": "canonical_expected_derived_view",
             "sources": sources, "nodes": nodes, "relations": relations,
             "projections": {"T": [item["id"] for item in text_nodes],
                             "L": [item["id"] for item in relations], "B": [item["id"] for item in facts]},
             "logic": copy.deepcopy(projected.get("logical_statements", [])),
             "operand_relations": copy.deepcopy(projected.get("semantic_operand_relations", [])),
             "required_matcher_features": copy.deepcopy(projected.get("required_matcher_features", [])),
             "explicit_references": copy.deepcopy(projected.get("explicit_references", [])),
             "reference_roles": copy.deepcopy(projected.get("reference_roles", [])),
             "reference_dispositions": copy.deepcopy(projected.get("reference_dispositions", [])),
             "unresolved": unresolved, "dispositions": [],
             "context": {key: copy.deepcopy(value) for key, value in projected.items()
                         if key not in {"text", "business", "relations", "blockers", "pending_requirements", "requirement_ledger",
                                        "logical_statements", "semantic_operands", "semantic_operand_relations", "required_matcher_features",
                                        "explicit_references", "reference_roles", "reference_dispositions"}}}
    for entry in sources:
        dispositions = {}
        for layer, bank in (("T", text_nodes), ("L", relations), ("B", facts)):
            ids = [item["id"] for item in bank if any(_cover(entry, source) for source in node_sources[item["id"]])]
            issues = [item for item in unresolved if layer in item["layers"] and _cover(entry, item["source"])]
            if issues:
                disposition = {"status": "unresolved", "requirements": ids,
                               "unresolved": [item["id"] for item in issues],
                               "rule_id": "source_interpretation_incomplete", "reason": "Every unresolved source obligation remains explicit."}
            elif ids:
                disposition = {"status": "interpreted", "requirements": ids,
                               "rule_id": "source_bound_" + layer, "reason": "Requirements retain their actual source and role."}
            elif (non_requirement := _not_applicable(entry, layer, projected, business_sources)):
                disposition = {"status": "not_applicable", "requirements": [],
                               "rule_id": non_requirement[0], "reason": non_requirement[1]}
                if len(non_requirement) > 2:
                    disposition["evidence"] = non_requirement[2]
            else:
                issue = {"id": f"unresolved:{len(unresolved)}", "kind": "source_disposition", "source_id": entry["id"],
                         "source": copy.deepcopy(entry["source"]), "text": entry["text"], "layers": [layer],
                         "reason": "source_has_no_supported_semantic_disposition"}
                unresolved.append(issue)
                disposition = {"status": "unresolved", "requirements": [], "unresolved": [issue["id"]],
                               "rule_id": "unknown_source_is_not_nonbusiness", "reason": "No positive interpretation or non-applicability rule exists."}
            dispositions[layer] = disposition
        graph["dispositions"].append({"source_id": entry["id"], "layers": dispositions})
    graph["source_obligation_inventory"] = inventory
    coverage = audit_source_obligations(inventory, graph)
    graph["source_obligation_coverage"] = coverage
    obligations = {item["id"]: item for item in inventory["obligations"]}
    obligations.update({item["id"]: {**item, "layers": ["T", "L", "B"]}
                        for item in inventory["authorized_raw_inventory"]["obligations"]})
    for row in coverage["dispositions"]:
        if row["status"] != "pending":
            continue
        obligation = obligations[row["obligation_id"]]
        # A retained external dependency keeps its exact user-authorized
        # identity. New software gaps never become one of the five deferrals.
        retained = [item for item in unresolved if item["id"] in {
            proof.get("unresolved") for proof in row["evidence"]}]
        if not retained:
            retained = [item for item in unresolved if _cover({"source": item.get("source", {})}, obligation["source"])
                        and set(obligation["layers"]) <= set(item.get("layers", []))
                        and item.get("reason") not in {"source_obligation_pending", "input_scope_context"}]
        if retained:
            for item in retained:
                item.setdefault("source_obligation_ids", []).append(obligation["id"])
            continue
        unresolved.append({"id": f"unresolved:{len(unresolved)}", "kind": "source_obligation",
            "reason": "source_obligation_pending", "obligation_id": obligation["id"],
            "obligation_kind": obligation["kind"], "source": copy.deepcopy(obligation["source"]),
            "text": obligation["text"], "layers": obligation["layers"],
            "interpretation_rule": obligation["interpretation_rule"], "explanation": row["reason"]})
    # The source-level summary cannot claim interpretation when the independent
    # inventory retained an unexplained part of that very source. Requirements
    # already recovered from it remain present alongside the missing meaning.
    by_source = {entry["id"]: entry for entry in sources}
    for row in graph["dispositions"]:
        entry = by_source[row["source_id"]]
        for layer, disposition in row["layers"].items():
            issues = [item for item in unresolved if layer in item["layers"] and _cover(entry, item["source"])]
            if issues:
                disposition.update(status="unresolved", unresolved=[item["id"] for item in issues],
                    rule_id="independent_source_obligation_incomplete",
                    reason="Recovered requirements do not explain every independently inventoried source obligation.")
    graph["complete"] = not unresolved
    graph["semantic_complete"] = not any(not is_deferred_input_scope(expected["sample_id"], item) for item in unresolved)
    # The in-memory model has the same JSON types as its sole authoritative
    # serialization; XML never supplies a second editable representation.
    return json.loads(json.dumps(graph, ensure_ascii=False))


def evaluation_projection(graph: dict[str, Any]) -> dict[str, Any]:
    """Materialize scorer inputs from graph references, with no other answers."""
    nodes = {node["id"]: node for node in graph["nodes"]}
    relations = {edge["id"]: edge for edge in graph["relations"]}
    result = copy.deepcopy(graph["context"])
    result.update(sample_id=graph["sample_id"],
                  text=[copy.deepcopy(nodes[ident]) for ident in graph["projections"]["T"]],
                  business=[copy.deepcopy(nodes[ident]) for ident in graph["projections"]["B"]],
                  relations=[copy.deepcopy(relations[ident]) for ident in graph["projections"]["L"]],
                  blockers=copy.deepcopy(graph["unresolved"]), pending_requirements=copy.deepcopy(graph["unresolved"]))
    result["requirement_ledger"] = copy.deepcopy(result["business"])
    result["logical_statements"] = copy.deepcopy(graph.get("logic", []))
    result["semantic_operands"] = [copy.deepcopy(node) for node in graph["nodes"] if node["kind"] == "semantic_operand"]
    result["semantic_operand_relations"] = copy.deepcopy(graph.get("operand_relations", []))
    result["required_matcher_features"] = copy.deepcopy(graph.get("required_matcher_features", []))
    for key in ("explicit_references", "reference_roles", "reference_dispositions"):
        result[key] = copy.deepcopy(graph.get(key, []))
    return result


def _semantic_literal(sources, origin):
    """Resolve source spans, including independently checked prose joins."""
    if not isinstance(origin, dict):
        return None
    fragments = origin.get("joined_fragments")
    if not fragments:
        return _literal(sources, origin)
    first = fragments[0].get("source", {})
    if origin.get("path") != first.get("path") or origin.get("lines") != first.get("lines"):
        return None
    joined = ""
    for fragment in fragments:
        actual = _literal(sources, fragment.get("source", {}))
        projected = fragment.get("projected_text", fragment.get("text"))
        bounds = fragment.get("joined_span")
        if (actual is None or not isinstance(projected, str) or not isinstance(bounds, (list, tuple))
                or len(bounds) != 2 or any(type(n) is not int for n in bounds)):
            return None
        def normalize(value):
            return re.sub(r"\s+", " ", value).strip()
        if (normalize(actual) != normalize(projected) or not isinstance(fragment.get("text"), str)
                or normalize(actual) != normalize(fragment["text"])):
            return None
        a, b = bounds
        if a < len(joined) or b - a != len(projected):
            return None
        joined += " " * (a - len(joined)) + projected
    offset = first.get("text_span", [0, 0])[0]
    a, b = origin.get("text_span", [offset, offset + len(joined)])
    return joined[a - offset:b - offset] if 0 <= a - offset <= b - offset <= len(joined) else None


def _semantic_dicts(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _semantic_dicts(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _semantic_dicts(item)


def _semantic_token_matches(dimension, claimed, literal):
    from .cjk_measurement_requirements import _CHANGES, _COMPARISONS
    from .narrative_requirements import _ACTIONS, _PAST, _REPORT_ACTIONS, _REPORT_PAST
    from .quantity import canonical_currency

    raw = re.sub(r"\s+", " ", literal.strip()).casefold()
    wanted = re.sub(r"[_\s]+", " ", str(claimed).strip()).casefold()
    if wanted == raw:
        return True
    if dimension == "currency":
        return canonical_currency(claimed) == canonical_currency(literal)
    if dimension in {"operator", "comparison_operator"} and raw in _COMPARISONS:
        return _COMPARISONS[raw] == wanted
    if dimension == "comparison_basis":
        return wanted == "year on year" and raw == "同比"
    if dimension == "change_direction":
        return raw in {text[2:] for text, direction in _CHANGES.items() if direction == wanted}
    if dimension == "aspect":
        return raw in {"perfect": {"have", "has"}, "progressive": {"is", "are"}}.get(wanted, set())
    if dimension in {"polarity", "modal_polarity"}:
        return wanted == "negative" and raw in {"not", "never", "no", "cannot", "不", "不能", "不得"}
    if dimension in {"operator", "condition_operator", "exception_operator"}:
        return raw in {"if": {"如果", "若"}, "unless": {"除非"}, "only if": {"只有"},
                       "except": {"除外"}}.get(wanted, set())
    if dimension == "modality":
        if wanted == "ability" and re.fullmatch(r"(?:is|are|was|were) (?:not )?able to", raw):
            return True
        return raw in {"can": {"cannot"}, "may": {"可以", "不可以"}, "must": {"必须", "必須", "不得"},
                       "should": {"应当", "應當"}, "ability": {"能", "能够", "能夠", "不能", "不能够", "不能夠"}}.get(wanted, set())
    if dimension == "tense":
        past = _PAST | _REPORT_PAST | {"did", "had"}
        present = (set(_ACTIONS) | set(_REPORT_ACTIONS) | {"do", "does", "am", "has", "have"}) - past
        return raw in (past if wanted == "past" else present if wanted == "present" else set())
    if dimension == "reporting_action":
        return _REPORT_ACTIONS.get(raw) == wanted
    return False


def _validate_semantic_sources(graph, nodes):
    """Guard interpreted operand, qualifier and operator evidence, not counts."""
    from .narrative_requirements import _Reader

    sources = graph["sources"]
    facts = [nodes[ident] for ident in graph["projections"]["B"]]
    operands = [node for node in nodes.values() if node.get("kind") == "semantic_operand"]
    trees = [*graph.get("logic", []), *(node.get("logic", {}) for node in [*facts, *operands]),
             *graph.get("operand_relations", [])]
    tree_nodes = [node for tree in trees for node in _semantic_dicts(tree)]

    def literal(origin, label):
        text = _semantic_literal(sources, origin)
        if text is None:
            raise ValueError(f"semantic source is outside original literal evidence: {label} {origin!r}")
        return text

    def cut(value, origin, label):
        actual = literal(origin, label)
        if actual != value:
            raise ValueError(f"semantic literal differs from its original source: {label} "
                             f"required={value!r} printed={actual!r} source={origin!r}")

    def token(value, origin, dimension):
        actual = literal(origin, dimension)
        if not _semantic_token_matches(dimension, value, actual):
            raise ValueError(f"semantic operator or qualifier differs from its original source: {dimension} "
                             f"required={value!r} printed={actual!r} source={origin!r}")

    for node in tree_nodes:
        if "path" in node and ("lines" in node or "cell" in node):
            literal(node, "logic source")
        if not ("source" in node or "span" in node):
            continue  # Endpoint summaries are checked against their bound AST.
        for name in ("subject", "predicate", "object", "speaker", "antecedent"):
            if name in node and node[name] and name + "_source" in node:
                cut(node[name], node[name + "_source"], "logic " + name)
        if node.get("operator_source") and "operator" in node:
            dimension = "modality" if node.get("kind") == "modality" else "operator"
            token(node["operator"], node["operator_source"], dimension)
        if node.get("kind") == "negation" and node.get("operator_source"):
            token("negative", node["operator_source"], "polarity")
        if node.get("tense_source") and "tense" in node:
            token(node["tense"], node["tense_source"], "tense")
        if node.get("kind") == "active_aspect" and "aspect" in node:
            token(node.get("aspect"), node.get("aspect_source"), "aspect")
        if node.get("kind") == "reporting" and "predicate_source" in node:
            token(node["attribute"], node["predicate_source"], "reporting_action")
        if node.get("kind") == "year_on_year_change":
            from .cjk_measurement_requirements import _CHANGES

            raw_operator = literal(node.get("operator_source"), "year-on-year operator")
            if (raw_operator != node.get("operator_text") or _CHANGES.get(raw_operator) != node.get("direction")
                    or node.get("basis") != "year_on_year"):
                raise ValueError("year-on-year logical operator differs from its complete printed source")
        if node.get("kind") == "relative" and "marker_source" in node:
            if literal(node["marker_source"], "relative marker").strip().casefold() not in {"that", "which", "who"}:
                raise ValueError("relative operator differs from its printed source")
        if node.get("kind") == "coordination" and "operator" in node:
            own, span = node.get("source", {}), node.get("span", [0, 0])
            offset = own.get("text_span", [0, 0])[0] - span[0]
            origins = [{**copy.deepcopy(own), "text_span": [offset + a, offset + b]}
                       for a, b in node.get("operator_spans", [])]
            if node.get("operator_sources") != origins:
                raise ValueError("coordination operator sources differ from their original spans")
            printed = [literal(origin, "coordination operator").strip().casefold() for origin in origins]
            joins = {"and": {"and", "和", "与", "與", "及", "并", "並", "且", "并且", "並且", "以及"},
                     "or": {"or", "或"}}
            allowed = joins.get(node.get("operator"), set())
            if (not printed or any(raw not in allowed | {",", "，", "、"} for raw in printed)
                    or node.get("operator") == "or" and not any(raw in allowed for raw in printed)):
                raise ValueError("logical enumeration operator differs from its printed source")

    bindings = [(node, item) for node in tree_nodes if node.get("kind") == "conditions" for item in node.get("bindings", [])]

    def own_operator(node, field, kind):
        paths = field.get("logic", {}).get("operator_path", [])
        return node.get("source") in [entry.get("source") for entry in paths if entry.get("kind") == kind]

    for field in [*facts, *operands]:
        if field.get("kind") == "semantic_operand":
            for name in ("value", "subject", "predicate", "object"):
                if field.get(name):
                    cut(field[name], field.get(name + "_source"), "operand " + name)
        q, proof = field.get("qualifiers", {}), field.get("qualifier_sources", {})
        for name, value in q.items():
            origin = proof.get(name) or field.get("qualifier_provenance", {}).get(name, {}).get("source")
            if name in {"polarity", "modal_polarity"} and value == "negative" and origin is None:
                modal_source = proof.get("modality")
                raw_modal = _semantic_literal(sources, modal_source)
                if raw_modal and raw_modal.strip().casefold() in {"cannot", "不得", "不能", "不可以"}:
                    origin = modal_source  # The same printed token carries both roles.
            if name in {"polarity", "modal_polarity"} and value == "positive" and origin is None:
                continue  # A positive unmarked assertion has no negation token.
            if name == "assertion_context":
                if field.get("logic", {}).get("assertion_context") != value:
                    raise ValueError("semantic qualifier context differs from its source-bound logic")
                continue
            if name == "assertion_contexts":
                context = q.get("assertion_context", field.get("logic", {}).get("assertion_context"))
                if not isinstance(value, list) or not value or value[-1] != context:
                    raise ValueError("nested qualifier contexts differ from their operator scope")
                capacity = Counter()
                for entry in field.get("logic", {}).get("operator_path", []):
                    kind = entry.get("kind")
                    if kind in {"reporting", "relative"}:
                        capacity["reported" if kind == "reporting" else "restrictive_relative"] += 1
                    elif kind == "conditions" and field.get("semantic_role") == "operand":
                        capacity["condition_operand"] += 1
                    elif kind == "modality":
                        actual = [node for node in tree_nodes if node.get("kind") == kind and "operator" in node
                                  and node.get("source") == entry.get("source")
                                  and node.get("operator_source") == entry.get("operator_source")]
                        for role in {"ability" if node["operator"] == "ability" else "modal" for node in actual}:
                            capacity[role] += 1
                    elif kind == "coordination" and any(node.get("kind") == kind and node.get("operator") == "or"
                            and node.get("source") == entry.get("source") for node in tree_nodes):
                        capacity["alternative_member" if field.get("semantic_role") == "operand" else "alternative_group"] += 1
                if Counter(value) - capacity:
                    raise ValueError("nested qualifier role has no original operator source")
                continue
            if name == "coordination":
                paths = [item.get("source") for item in field.get("logic", {}).get("operator_path", [])
                         if item.get("kind") == "coordination"]
                owners = [item for item in tree_nodes if item.get("kind") == "coordination"
                          and "operator" in item and paths and item.get("source") == paths[-1]]
                if not any(item.get("operator") == value for item in owners):
                    raise ValueError("coordination qualifier differs from its source-bound operator logic")
                if not isinstance(origin, list) or not origin or not any(
                        origin == owner.get("operator_sources") for owner in owners if owner.get("operator") == value):
                    raise ValueError("coordination qualifier sources differ from their authoritative operator scope")
                continue
            if name == "conditions":
                if not isinstance(origin, list) or len(origin) != len(value):
                    raise ValueError("condition qualifiers require each original operator and operand source")
                for claim, evidence in zip(value, origin, strict=True):
                    token(claim["operator"], evidence.get("operator_source"), "condition_operator")
                    matched = [binding for owner, binding in bindings if own_operator(owner, field, "conditions")
                               if binding.get("operator_source") == evidence.get("operator_source")
                               and binding.get("operand", {}).get("source") == evidence.get("operand_source")]
                    if not any(_Reader.summary(item["operand"]) == claim["operand"] for item in matched):
                        raise ValueError("condition summary differs from its source-bound logic operand")
                continue
            if name == "reporting":
                if not isinstance(origin, list) or len(origin) != len(value):
                    raise ValueError("reporting qualifiers require each original source proof")
                for claim, evidence in zip(value, origin, strict=True):
                    matches = [node for node in tree_nodes if node.get("kind") == "reporting" and own_operator(node, field, "reporting")
                               and all(node.get(key) == evidence.get(key) for key in ("speaker_source", "predicate_source", "tense_source"))]
                    if not any({"subject": node["speaker"], "attribute": node["attribute"], "polarity": node["polarity"],
                                "tense": node["tense"]} == claim for node in matches):
                        raise ValueError("reporting qualifier differs from its source-bound logic")
                continue
            if name == "subject_restriction":
                if not isinstance(origin, dict):
                    raise ValueError("restrictive qualifier requires its original source proof")
                matches = [node for node in tree_nodes if node.get("kind") == "relative" and own_operator(node, field, "relative")
                           and node.get("antecedent_source") == origin.get("antecedent_source")
                           and node.get("marker_source") == origin.get("marker_source")
                           and node.get("restriction", {}).get("source") == origin.get("restriction_source")]
                if not any(_Reader.summary(node["restriction"]) == value for node in matches):
                    raise ValueError("restrictive qualifier differs from its source-bound logic")
                continue
            if isinstance(value, str):
                if name in {"modality", "polarity", "modal_polarity", "tense", "condition_operator", "exception_operator",
                            "currency", "comparison_operator", "comparison_basis", "change_direction", "aspect"}:
                    token(value, origin, name)
                else:
                    cut(value, origin, "qualifier " + name)


def validate_requirement_graph(graph: dict[str, Any], *, expected: dict[str, Any] | None = None) -> None:
    """Check transport integrity; independent semantic oracles remain required."""
    nodes = {node["id"]: node for node in graph["nodes"]}
    relations = {edge["id"]: edge for edge in graph["relations"]}
    if (graph.get("complete") != (not graph["unresolved"]) or graph.get("semantic_complete") != (
            not any(not is_deferred_input_scope(graph["sample_id"], issue) for issue in graph["unresolved"]))):
        raise ValueError("requirement completeness differs from its explicit unresolved obligations")
    if len(nodes) != len(graph["nodes"]) or len(relations) != len(graph["relations"]):
        raise ValueError("duplicate semantic requirement identity")
    for layer in LAYERS:
        ids = graph["projections"][layer]
        bank = relations if layer == "L" else nodes
        if len(ids) != len(set(ids)) or any(ident not in bank for ident in ids):
            raise ValueError("invalid or duplicated requirement projection")
        if layer == "L":
            required = list(relations)
        elif layer == "T":
            required = [node["id"] for node in graph["nodes"] if node.get("kind") == "text"]
        else:
            required = [node["id"] for node in graph["nodes"] if node.get("kind") in {"fact", "proposition", "logical_group"}]
        if ids != required:
            raise ValueError("requirement projection omits or reorders an interpreted semantic obligation")
    sources = graph["sources"]
    by_source = {entry["id"]: entry for entry in sources}
    actual_sources = {ident: _node_sources(node) for ident, node in {**nodes, **relations}.items()}
    if Counter(row["source_id"] for row in graph["dispositions"]) != Counter({row["id"]: 1 for row in sources}):
        raise ValueError("missing or duplicated source disposition")
    for row in graph["dispositions"]:
        if set(row["layers"]) != set(LAYERS):
            raise ValueError("each source needs all three layer dispositions")
        for layer, item in row["layers"].items():
            if not item.get("rule_id") or not item.get("reason"):
                raise ValueError("source disposition lacks an explicit rule or reason")
            if item["status"] not in {"interpreted", "not_applicable", "unresolved"}:
                raise ValueError("unknown source disposition")
            if item["status"] == "interpreted" and not item["requirements"]:
                raise ValueError("interpreted source has no requirement")
            if not set(item["requirements"]) <= set(graph["projections"][layer]):
                raise ValueError("source disposition references absent requirements")
            if any(not any(_cover(by_source[row["source_id"]], origin) for origin in actual_sources[ident])
                   for ident in item["requirements"]):
                raise ValueError("source disposition borrows an obligation from another actual source")
            issues = {issue["id"] for issue in graph["unresolved"] if layer in issue["layers"]
                      and _cover(by_source[row["source_id"]], issue["source"])}
            if issues and (item["status"] != "unresolved" or set(item.get("unresolved", [])) != issues):
                raise ValueError("source disposition omits independent unresolved source obligations")
    for ident in graph["projections"]["B"]:
        fact = nodes[ident]
        for field, literal in (("value_source", fact["value"]), ("predicate_source", fact.get("predicate")),
                               ("object_source", fact.get("object"))):
            if literal is not None and field in fact and not fact[field].get("joined_fragments"):
                printed = _literal(sources, fact[field])
                if printed is None or printed != literal:
                    raise ValueError(f"{field} does not cut its original printed literal: "
                                     f"{graph['sample_id']} {ident} {fact[field]!r} "
                                     f"required={literal!r} printed={printed!r}")
        if fact.get("predicate") and fact.get("logic", {}).get("kind") in {
                "proposition", "narrative_leaf", "logical_group"}:
            # An interpreted SVO proposition owns its binding even if every
            # printed word is also retained by T. Numeric payload is not used
            # to locate that binding.
            origin = {"source": fact.get("statement_source", fact["source"])}
            if not any(edge.get("type") == "field_binding"
                       and edge.get("right", {}).get("subject") == fact["subject"]
                       and edge.get("right", {}).get("attribute") == fact["attribute"]
                       and _cover(origin, edge.get("source", {})) for edge in relations.values()):
                raise ValueError("interpreted proposition lacks its source-bound semantic relation")
    _validate_semantic_sources(graph, nodes)
    from .quoted_nominal_validation import validate_quoted_nominals

    validate_quoted_nominals(graph,
        [nodes[ident] for ident in graph["projections"]["B"]]
        + [node for node in nodes.values() if node.get("kind") == "semantic_operand"],
        lambda source: _semantic_literal(sources, source))
    from .document_composition_requirements import validate_document_compositions

    validate_document_compositions(graph, [nodes[ident] for ident in graph["projections"]["B"]],
                                   lambda source: _semantic_literal(sources, source))
    from .proposition_requirements import validate_proposition_coordinations

    validate_proposition_coordinations(graph, [nodes[ident] for ident in graph["projections"]["B"]],
                                      lambda source: _semantic_literal(sources, source))
    from .enumeration_binding import validate_enumeration_bindings

    validate_enumeration_bindings(graph, nodes, lambda source: _semantic_literal(sources, source))
    from .source_obligations import validate_source_obligations

    validate_source_obligations(graph, expected=expected)
    if expected is not None:
        # Reinterpret the immutable external input to catch synchronized edits
        # of nodes, projections and dispositions. This is an omission/mutation
        # guard, not independent proof that the interpreter understood prose.
        rebuilt = compile_requirement_graph(expected)
        for key in ("sources", "nodes", "relations", "projections", "dispositions", "unresolved", "logic", "operand_relations", "required_matcher_features",
                    "explicit_references", "reference_roles", "reference_dispositions", "source_obligation_inventory", "source_obligation_coverage"):
            if graph[key] != rebuilt[key]:
                raise ValueError(f"requirement graph changed or omitted source semantics: {key}")


def _xml(parent, key, value):
    tag = key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", key) else "entry"
    attributes = {} if tag == key else {"name": key}
    if isinstance(value, dict):
        element = ET.SubElement(parent, tag, attributes)
        for name, item in value.items():
            _xml(element, name, item)
    elif isinstance(value, list):
        element = ET.SubElement(parent, tag, attributes)
        for item in value:
            _xml(element, "item", item)
    else:
        element = ET.SubElement(parent, tag, attributes)
        element.text = "" if value is None else str(value)


def write_requirement_graph(graph: dict[str, Any], json_path: Path, xml_path: Path) -> None:
    validate_requirement_graph(graph)
    json_path, xml_path = Path(json_path), Path(xml_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    root = ET.Element("expected-requirements")
    for key, value in graph.items():
        _xml(root, key, value)
    ET.indent(root)
    ET.ElementTree(root).write(xml_path, encoding="utf-8", xml_declaration=True)


def compile_saved_requirements(baseline: Path, output: Path, *, expected_root: Path | None = None) -> Path:
    """Compile declared Lite scope only; never read any candidate or PDF."""
    from .cli import ROOT, code_identity
    from .expected_readback import read_expected
    from .packaging import read_json

    baseline, output = Path(baseline).resolve(), Path(output).resolve()
    if not output.is_relative_to(baseline / "requirements"):
        raise ValueError("requirement artifacts must stay in the saved run's local requirements directory")
    if output.exists():
        raise ValueError("requirement output already exists; do not overwrite an active or retained artifact")
    session = read_json(baseline / "run.json")
    manifest = read_json(Path(session["dataset"]) / "manifest.json")
    quality = [case for case in session["cases"]
               if case.get("phase") == "measured" and case.get("suite") == "quality800"]
    declared = {case["sample_id"] for case in quality}
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    lite = manifest.get("suites", {}).get("lite", list(samples))
    occurrences = [(case.get("pipeline"), case["sample_id"]) for case in quality]
    if (not declared or len(samples) != len(manifest["samples"])
            or not isinstance(lite, list) or any(not isinstance(ident, str) for ident in lite)
            or len(lite) != len(set(lite)) or declared != set(lite)
            or not declared <= samples.keys() or len(occurrences) != len(set(occurrences))):
        raise ValueError("saved quality scope must match the complete declared Lite selection without duplicate sample identities")
    expected_root = Path(expected_root or ROOT / "pdf_sample/parsing/expected")
    identity = code_identity()
    output.mkdir(parents=True)
    index: dict[str, Any] = {"purpose": "expected_output_requirements_not_corpus_review", "state": "compiling",
        "software_id": identity["software_id"], "candidate_read": False, "pdf_or_image_read": False,
        "canonical_expected_changed": False, "reference_is_an_editable_answer": False,
        "records": [], "semantic_complete": False, "quality_scores_withheld": True,
        "source_obligation_inventory_complete": False,
        "inventory_validation": {"status": "not_passed", "scope": "source_integrity_not_semantic_oracle"}}
    cache = {}
    reasons = Counter()
    for sample_id in sorted(declared):
        expected = read_expected(samples[sample_id], expected_root, cache=cache)
        json_path, xml_path = output / "samples" / f"{sample_id}.json", output / "samples" / f"{sample_id}.xml"
        try:
            graph = compile_requirement_graph(expected)
            validate_requirement_graph(graph, expected=expected)
            write_requirement_graph(graph, json_path, xml_path)
        except ValueError as error:
            reasons["compiler_source_integrity_failure"] += 1
            index["records"].append({"sample_id": sample_id, "semantic_complete": False,
                "graph_written": False, "error": {"type": type(error).__name__, "message": str(error)},
                "disposition": "software_source_integrity_failure"})
            continue
        semantic = [issue for issue in graph["unresolved"] if not is_deferred_input_scope(sample_id, issue)]
        scopes = [issue for issue in graph["unresolved"] if is_deferred_input_scope(sample_id, issue)]
        reasons.update(issue["reason"] for issue in semantic)
        index["records"].append({"sample_id": sample_id, "json": str(json_path.relative_to(output)),
            "xml": str(xml_path.relative_to(output)), "semantic_complete": not semantic,
            "generated_view_sha256": hashlib.sha256(json_path.read_bytes()).hexdigest(),
            "xml_projection_sha256": hashlib.sha256(xml_path.read_bytes()).hexdigest(),
            "source_obligation_inventory_complete": graph["source_obligation_inventory"]["source_complete"],
            "source_obligation_status": graph["source_obligation_coverage"]["status_counts"],
            "inventory_validation": {"status": "passed" if graph["source_obligation_inventory"]["source_complete"] else "not_passed",
                                     "scope": "source_integrity_not_semantic_oracle"},
            "authorized_raw_source_status": graph["source_obligation_inventory"]["authorized_raw_inventory"]["status_counts"],
            "unresolved_semantics": len(semantic), "input_scope_pending": len(scopes),
            "disposition": "interpreted" if not semantic else "unresolved",
            "layers": {layer: len(graph["projections"][layer]) for layer in LAYERS}})
    index["unresolved_reasons"] = dict(reasons)
    index["semantic_complete"] = not reasons
    index["source_obligation_inventory_complete"] = all(
        row.get("source_obligation_inventory_complete") is True for row in index["records"])
    index["inventory_validation"]["status"] = "passed" if index["source_obligation_inventory_complete"] else "not_passed"
    index["state"] = "structure_compiled_pending_independent_semantic_validation" if not reasons else "structure_blocked"
    index["validation"] = {"status": "not_passed", "reason": "Source integrity and empty pending do not replace independent semantic validation."}
    index["software_unchanged"] = code_identity()["software_id"] == identity["software_id"]
    path = output / "index.json"
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile the authorized expected-only requirement view, without scoring candidates.")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = compile_saved_requirements(args.baseline, args.output)
    index = json.loads(path.read_text())
    print(json.dumps({"index": str(path), "state": index["state"], "semantic_complete": index["semantic_complete"],
                      "unresolved_reasons": index["unresolved_reasons"]}, ensure_ascii=False))
    return 0 if index["semantic_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
