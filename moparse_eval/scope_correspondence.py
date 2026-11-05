"""Verify declared scope queries against actual candidate heading positions.

The reference supplies a frozen query tree, never missing candidate headings.
This matcher preserves a printed parent through its declared siblings even
when all are displayed at one level. Unknown peer headings, media and document
boundaries cannot be erased to obtain a desired ancestor. Assertion values are
neither inputs to the query nor read from a candidate item.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from collections.abc import Callable
from functools import lru_cache
from typing import Any

Canonicalize = Callable[[str], str]


def _path(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    return [part for part in value or [] if isinstance(part, str) and part]


def _key(path: list[str], canonicalize: Canonicalize) -> tuple[str, ...]:
    return tuple(canonicalize(part) for part in path)


@lru_cache(maxsize=8)
def _context_label_indices(texts: tuple[str, ...], canonicalize: Canonicalize) -> dict[str, tuple[int, ...]]:
    """Cache only ordered text positions, never declaration metadata or sources."""
    indices: dict[str, list[int]] = defaultdict(list)
    for index, text in enumerate(texts):
        indices[canonicalize(text)].append(index)
    return {label: tuple(positions) for label, positions in indices.items()}


def _frame(node: tuple[str, ...], event: dict[str, Any], role: str = "actual_printed_heading") -> dict[str, Any]:
    return {"node": node, "text": event["text"], "source": copy.deepcopy(event["source"]),
            "heading_event": event.get("id"), "level": event.get("level"), "role": role, "repeated_sources": []}


def _group_evidence(item: dict[str, Any], canonicalize: Canonicalize) -> tuple[list[str], list[dict[str, Any]]]:
    labels = _path(item.get("identity_facets", {}).get("group"))
    block = item.get("source", {}).get("block")
    evidence = [entry for entry in [*item.get("row_evidence", []), *item.get("header_evidence", [])]
                if entry.get("role") in {"row_group", "row_group_value", "record_group"}
                and entry.get("source")
                and (block is None or entry["source"].get("block") == block)]
    matched = []
    for label in labels:
        found = []
        for entry in evidence:
            literal = entry.get("text", "").strip()
            # Only a declared group label's final colon is a separator. Keep
            # internal punctuation, extra words and every value unchanged.
            display_label = literal[:-1].rstrip() if literal.endswith((":", "：")) else literal
            if canonicalize(literal) == canonicalize(label) or canonicalize(display_label) == canonicalize(label):
                found.append(entry)
        if not found:
            return labels, []
        matched.append({"text": found[0]["text"], "source": copy.deepcopy(found[0]["source"]),
                        "role": "actual_record_group_axis", "level": None, "heading_event": None,
                        "repeated_sources": []})
    return labels, matched


def _native_scope_proof(record: dict[str, Any], events: list[dict[str, Any]], nodes: set[tuple[str, ...]],
                        by_label: dict[str, set[tuple[str, ...]]], canonicalize: Canonicalize) -> list[dict[str, Any]]:
    """Read declared hierarchy evidence; media cannot erase native parentage."""
    headings = {event["id"]: event for event in events if event["type"] == "heading"}
    actual = []
    for entry in record.get("context_evidence", []):
        if entry.get("role") != "heading" or entry.get("method") != "actual_heading_role_and_sequence":
            continue
        event = headings.get(entry.get("event_id"))
        if (event is None or event["source"] != entry.get("source") or type(event.get("level")) is not int
                or event["level"] <= 0 or event.get("segment") != record.get("segment")
                or event["source"]["position"] > record["position"]):
            return []
        if actual and actual[-1]["level"] >= event["level"]:
            return []
        actual.append(_frame((), event, "verified_native_heading_path"))
    if _key([entry["text"] for entry in actual], canonicalize) != _key(_path(record.get("heading_path")), canonicalize):
        return []
    options = [actual] if actual else []
    captions = [entry for entry in record.get("context_evidence", []) if entry.get("role") == "table_caption"]
    if len({canonicalize(entry["text"]) for entry in captions}) == 1:
        caption = _frame((), captions[0], "actual_bound_table_caption")
        options.append([*actual, caption])
    proofs = []
    for option in options:
        key = _key([entry["text"] for entry in option], canonicalize)
        for node in nodes:
            if len(key) < len(node) or key[-len(node):] != node:
                continue
            # A single display heading does not override an already printed
            # logical parent when that label is also a declared child.
            if len(node) == 1 and by_label[node[0]] != {node}:
                continue
            frames = copy.deepcopy(option[-len(node):])
            for index, frame in enumerate(frames):
                frame["node"] = node[:index + 1]
            proofs.append(frames)
    return max(proofs, key=len, default=[])


def verify_scope(required: list[str], item: dict[str, Any], declared_paths: list[list[str]], *,
                 contexts: dict[str, Any] | None = None, canonicalize: Canonicalize | None = None,
                 context_labels: list[dict[str, Any]] | tuple[dict[str, Any], ...] = ()) -> dict[str, Any]:
    """Return position evidence for one scope query, without comparing values.

    ``contexts`` is the complete output of ``read_contexts``. Context labels are
    frozen reference declarations with ``text``, ``scope``, ``source`` and an
    optional ``role='external_ancestor'``; they can explain actual complete
    headings, never create one. Candidate row-group suffixes require their own
    native group-axis evidence.
    """
    canonicalize = canonicalize or str.strip
    required = _path(required)
    result: dict[str, Any] = {"correct": False, "status": "unknown", "required": copy.deepcopy(required),
                              "actual_path": [], "actual_sources": [], "boundaries": [], "rejected": [],
                              "display_context_sources": [], "method": "declared_scope_tree_and_actual_candidate_heading_events"}
    record = item.get("context_evidence", {})
    if contexts is not None:
        record = contexts.get("by_block", {}).get(item.get("source", {}).get("block"), record)
    if record.get("status") in {"conflict", "ambiguous"}:
        result.update(status="explicit_conflict", reason="candidate_own_context_is_conflicting",
                      conflicts=copy.deepcopy(record.get("conflicts", [])))
        return result
    if not required:
        result.update(correct=True, status="correct", reason="no_required_scope")
        return result
    # A printed field prefix can express the same local business scope as a
    # heading. Its own source and prefix must prove it; no required label is
    # supplied to the candidate reader or searched for in another block.
    field = item.get("field_label_evidence")
    if field:
        source = field.get("source", {})
        own = item.get("source", {})
        events = contexts.get("events", []) if contexts else []
        actual = [event for event in events if event.get("source", {}).get("block") == source.get("block")
                  and event.get("source", {}).get("path") == source.get("path")]
        span = source.get("text_span")
        from .source_requirements import plan_mixed_source

        proven = []
        for event in actual:
            text = event.get("text", "")
            if not (isinstance(span, list) and len(span) == 2 and all(type(n) is int for n in span)
                    and 0 <= span[0] < span[1] <= len(text) and text[slice(*span)] == field.get("text")):
                continue
            plan = plan_mixed_source(text, event.get("source", {}))
            regions = [fragment["source"]["text_span"] for fragment in plan["fragments"]] if plan else [[0, len(text)]]
            own_span = own.get("text_span")
            for start, end in regions:
                delimiter = re.match(r"\s*[:：]", text[span[1]:end])
                component_sources = [item[key] for key in ("subject_source", "predicate_source", "object_source", "value_source")
                                     if isinstance(item.get(key), dict)]
                components_bound = all(component.get("block") == own.get("block")
                    and component.get("path") == own.get("path") and isinstance(component.get("text_span"), list)
                    and len(component["text_span"]) == 2
                    and span[1] + (delimiter.end() if delimiter else 0) <= component["text_span"][0] <= component["text_span"][1] <= end
                    for component in component_sources)
                if (start <= span[0] < span[1] <= end and re.fullmatch(r"\s*", text[start:span[0]])
                        and delimiter and isinstance(own_span, list) and len(own_span) == 2
                        and span[1] + delimiter.end() <= own_span[0] <= own_span[1] <= end and components_bound):
                    proven.append(event)
        if (field.get("role") != "printed_field_label" or not proven or source.get("block") != own.get("block")
                or source.get("path") != own.get("path")):
            result["reason"] = "local_field_label_lacks_actual_prefix_source"
            return result
        if canonicalize(required[-1]) != canonicalize(field.get("text", "")):
            result.update(status="explicit_conflict", reason="actual_local_field_label_is_another_scope",
                          actual_path=[*item.get("scope", [])], actual_sources=[copy.deepcopy(field)])
            return result
        parent = {key: copy.deepcopy(value) for key, value in item.items() if key != "field_label_evidence"}
        parent["scope"] = _path(item.get("scope"))[:-1]
        verified = verify_scope(required[:-1], parent, declared_paths, contexts=contexts,
                                canonicalize=canonicalize, context_labels=context_labels)
        verified.update(required=copy.deepcopy(required), method="actual_field_prefix_and_verified_parent_scope")
        verified["actual_path"].append(field["text"])
        verified["actual_sources"].append(copy.deepcopy(field))
        return verified
    events = contexts.get("events") if contexts is not None else None
    if events is None or type(record.get("position")) is not int:
        result["reason"] = "complete_candidate_heading_stream_or_position_unavailable"
        return result

    nodes: set[tuple[str, ...]] = set()
    by_label: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    for path in declared_paths:
        normalized = _key(_path(path), canonicalize)
        for end in range(1, len(normalized) + 1):
            nodes.add(normalized[:end])
            by_label[normalized[end - 1]].add(normalized[:end])

    required_key = _key(required, canonicalize)
    groups, group_sources = _group_evidence(item, canonicalize)
    group_key = _key(groups, canonicalize)
    required_heading = required
    if groups and len(required) >= len(groups) and required_key[-len(groups):] == group_key:
        required_heading = required[:-len(groups)]
        if not group_sources:
            result["reason"] = "candidate_group_lacks_independent_native_axis_evidence"
            return result
    elif required_key not in nodes:
        longest = max((end for end in range(len(required)) if required_key[:end] in nodes), default=0)
        result.update(status="explicit_conflict" if groups else "missing",
                      reason="required_scope_suffix_not_proven_by_candidate_group",
                      group_checks={"required": required[longest:], "actual": groups, "correct": False})
        return result
    wanted = _key(required_heading, canonicalize)
    if wanted and wanted not in nodes:
        result["reason"] = "required_heading_scope_not_in_frozen_declarations"
        return result

    explicit = record.get("explicit_heading_paths", [])
    if explicit:
        if len(explicit) != 1 or explicit[0].get("status") != "bound":
            result.update(status="explicit_conflict", reason="native_heading_ownership_is_ambiguous_or_crosses_document_boundary")
            return result
        declaration = explicit[0]
        heading_events = {entry["source"].get("block"): entry for entry in events if entry["type"] == "heading"}
        actual = []
        for heading in declaration.get("headings", []):
            event = heading_events.get(heading.get("source", {}).get("block"))
            if (event is None or event["source"] != heading.get("source")
                    or canonicalize(event["text"]) != canonicalize(heading.get("text", ""))
                    or event.get("segment") != record.get("segment")):
                result["reason"] = "explicit_native_heading_source_not_independently_present_in_stream"
                return result
            actual.append(_frame((), event, "explicit_native_heading_reference"))
        if (_key([entry["text"] for entry in actual], canonicalize)
                != _key(_path(declaration.get("path")), canonicalize) or not actual):
            result["reason"] = "explicit_native_heading_path_has_incomplete_source_evidence"
            return result
        target_heading = heading_events.get(record["source"].get("block"))
        if target_heading is not None and target_heading["source"] == record["source"]:
            actual.append(_frame((), target_heading, "actual_target_heading_after_explicit_parent"))
        options = [actual]
        captions = [entry for entry in record.get("context_evidence", []) if entry.get("role") == "table_caption"]
        if len({canonicalize(entry["text"]) for entry in captions}) == 1:
            options.append([*actual, _frame((), captions[0], "actual_bound_table_caption")])
        matches = [option for option in options if not wanted or len(option) >= len(wanted)
                   and _key([entry["text"] for entry in option[-len(wanted):]], canonicalize) == wanted]
        selected = matches[0] if matches else actual
        result["actual_path"] = [entry["text"] for entry in selected]
        result["actual_sources"] = [{key: copy.deepcopy(value) for key, value in entry.items() if key != "node"}
                                    for entry in selected]
        if groups and group_sources and required_heading != required:
            result["actual_path"].extend(groups)
            result["actual_sources"].extend(copy.deepcopy(group_sources))
            result["group_checks"] = {"required": required[len(required_heading):], "actual": groups,
                                      "correct": True, "sources": copy.deepcopy(group_sources)}
        result["boundaries"].append({"reason": "explicit_native_reference_selects_this_target",
            "source": copy.deepcopy(record["source"]), "target_source": copy.deepcopy(declaration["target_source"]),
            "edges": copy.deepcopy(declaration["edges"]), "display_path": copy.deepcopy(record.get("heading_path", [])),
            "scope_disagreements": copy.deepcopy(record.get("scope_disagreements", [])), "terminates": False})
        result.update(correct=bool(matches), status="correct" if matches else "explicit_conflict",
                      reason="explicit_native_heading_ownership_verified" if matches else "explicit_native_heading_ownership_is_another_scope",
                      method="explicit_native_heading_reference_path")
        selected_ids = {entry["source"].get("block") for entry in selected}
        result["rejected"] = [{"text": event["text"], "source": copy.deepcopy(event["source"]),
            "reason": "display_heading_not_selected_by_explicit_native_ownership"}
            for event in events if event["type"] == "heading" and canonicalize(event["text"]) in required_key
            and event["source"].get("block") not in selected_ids]
        return result

    active: list[dict[str, Any]] = []
    orphan: list[dict[str, Any]] = []
    last_barrier = None
    segment = None
    external_anchors: dict[str, dict[str, Any]] = {}
    display_sources = []
    position = record["position"]
    context_entries = tuple(context_labels)
    label_indices = None

    def boundary(event: dict[str, Any], reason: str, *, terminates: bool = True) -> None:
        nonlocal last_barrier
        entry = {"reason": reason, "source": copy.deepcopy(event["source"]), "terminates": terminates,
                 "prior_path": [frame["text"] for frame in active]}
        result["boundaries"].append(entry)
        if terminates:
            last_barrier = entry

    for event in events:
        if event.get("source", {}).get("position", float("inf")) > position:
            break
        event_segment = event.get("segment")
        if segment is not None and event_segment != segment:
            boundary(event, "explicit_document_boundary")
            active, orphan, external_anchors = [], [], {}
        segment = event_segment
        if event["type"] == "document_boundary":
            if not result["boundaries"] or result["boundaries"][-1]["source"] != event["source"]:
                boundary(event, "explicit_document_boundary")
            active, orphan, external_anchors = [], [], {}
            continue
        if event["type"] == "media":
            boundary(event, "media_terminates_unproven_flat_parent_continuity")
            active, orphan, external_anchors = [], [], {}
            continue
        if event["type"] != "heading":
            continue
        label = canonicalize(event.get("text", ""))
        if not label:
            boundary(event, "empty_declared_heading_ends_scope")
            active, orphan = [], []
            continue
        current = active[-1]["node"] if active else ()
        if label_indices is None:
            cache_key = (tuple(entry.get("text", "") for entry in context_entries), canonicalize)
            try:
                hash(cache_key)
            except TypeError:
                label_indices = _context_label_indices.__wrapped__(*cache_key)
            else:
                label_indices = _context_label_indices(*cache_key)
        declarations = [context_entries[index] for index in label_indices.get(label, ())]
        handled = False
        for declaration in declarations:
            external = declaration.get("role") == "external_ancestor"
            prior = external_anchors.get(label)
            if external and prior is None:
                external_anchors[label] = event
            declared_scope = _key(_path(declaration.get("scope", declaration.get("parent_path", []))), canonicalize)
            shared = min(len(declared_scope), len(current))
            compatible = bool(declared_scope and current and declared_scope[:shared] == current[:shared])
            if active and ((external and prior is not None and compatible) or not external and declared_scope == current):
                display_sources.append({"text": event["text"], "source": copy.deepcopy(event["source"]),
                                        "reference_declaration": {key: copy.deepcopy(declaration[key])
                                                                  for key in ("text", "scope", "source", "role") if key in declaration},
                                        "prior_actual_source": copy.deepcopy(prior["source"]) if external else None,
                                        "method": "actual_complete_heading_matches_frozen_context_label"})
                boundary(event, "declared_display_context_preserves_proven_business_scope", terminates=False)
                handled = True
                break
        if handled:
            continue
        placements = by_label.get(label, set())
        repeated_ancestor = [frame for frame in active[:-1] if frame["node"] in placements]
        if repeated_ancestor:
            repeated_ancestor[-1]["repeated_sources"].append(copy.deepcopy(event["source"]))
            boundary(event, "complete_previously_printed_ancestor_repeated_inside_current_scope", terminates=False)
            continue
        viable = [node for node in placements if len(node) == 1 or current[:len(node) - 1] == node[:-1]
                  and len(current) >= len(node) - 1]
        if len(viable) == 1:
            node = viable[0]
            prefix = active[:len(node) - 1]
            if active and current != node:
                boundary(event, "declared_child_or_sibling_scope_starts",
                         terminates=not prefix)
            active = [*prefix, _frame(node, event)]
            orphan = []
            continue
        if placements:
            boundary(event, "ambiguous_declared_heading_placement" if viable else "required_parent_not_currently_proven")
            active, orphan = [], [_frame((), event)]
            continue
        if active:
            level, root_level = event.get("level"), active[0].get("level")
            if type(level) is int and type(root_level) is int and level > root_level:
                kept = [frame for frame in active if type(frame.get("level")) is int and frame["level"] < level]
                if len(kept) != len(active):
                    boundary(event, "unknown_reliable_heading_closes_declared_child")
                active, orphan = kept, []
                continue
        boundary(event, "unknown_heading_ends_unproven_parent_scope")
        active, orphan = [], [_frame((), event)]

    # A local caption has an independently declared table relation and can be
    # serialized after its body. It extends this table only, never global state.
    captions = [entry for entry in record.get("context_evidence", []) if entry.get("role") == "table_caption"]
    if len({canonicalize(entry["text"]) for entry in captions}) == 1:
        caption = captions[0]
        current = active[-1]["node"] if active else ()
        placements = by_label.get(canonicalize(caption["text"]), set())
        viable = [node for node in placements if len(node) == 1 or current[:len(node) - 1] == node[:-1]
                  and len(current) >= len(node) - 1]
        if len(viable) == 1:
            node = viable[0]
            active = [*active[:len(node) - 1], _frame(node, caption, "actual_bound_table_caption")]
            orphan = []

    native = _native_scope_proof(record, events, nodes, by_label, canonicalize)
    if native:
        proven = native[-1]["node"]
        current = active[-1]["node"] if active else ()
        # A deeper reprint of an already active ancestor is display evidence,
        # not a new parent-direct record. All other complete native paths have
        # their own hierarchy and do not depend on flattened continuity.
        ancestor_repeat = len(current) > len(proven) and current[:len(proven)] == proven
        if not ancestor_repeat and (len(native) > 1 or not active):
            active, orphan = native, []
            result["boundaries"].append({"reason": "native_heading_path_has_independent_parentage",
                "source": copy.deepcopy(record["source"]), "start": copy.deepcopy(native[0]["source"]),
                "stop": copy.deepcopy(record.get("boundary", {}).get("stop")), "terminates": False})

    actual = active or orphan
    result["actual_path"] = [frame["text"] for frame in actual]
    result["actual_sources"] = [{key: copy.deepcopy(value) for key, value in frame.items() if key != "node"} for frame in actual]
    result["display_context_sources"] = display_sources
    matches = not wanted or bool(active and active[-1]["node"] == wanted)
    if groups and group_sources and required_heading != required:
        result["actual_path"].extend(groups)
        result["actual_sources"].extend(copy.deepcopy(group_sources))
        result["group_checks"] = {"required": required[len(required_heading):], "actual": groups, "correct": True,
                                  "sources": copy.deepcopy(group_sources)}
    selected = {source["source"].get("block") for source in result["actual_sources"]}
    for event in events:
        if event["type"] != "heading" or canonicalize(event.get("text", "")) not in required_key:
            continue
        if event["source"].get("block") in selected:
            continue
        result["rejected"].append({"text": event["text"], "source": copy.deepcopy(event["source"]),
            "reason": "heading_occurs_after_candidate_position" if event["source"]["position"] > position
                      else "heading_outside_current_proven_scope_or_superseded_occurrence"})
    if matches:
        result.update(correct=True, status="correct", reason="all_required_scope_nodes_have_actual_current_sources")
    elif active:
        result.update(status="explicit_conflict", reason="another_declared_business_scope_owns_this_candidate_position")
    else:
        structural_barrier = last_barrier and last_barrier["reason"] in {
            "unknown_heading_ends_unproven_parent_scope", "explicit_document_boundary",
            "media_terminates_unproven_flat_parent_continuity", "ambiguous_declared_heading_placement"}
        result.update(status="unknown" if structural_barrier else "missing",
                      reason="required_ancestor_not_proven_at_this_candidate_position")
    return result
