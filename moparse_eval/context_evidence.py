"""Candidate-only printed scope evidence, positions and stopping boundaries.

References are not inputs. Native heading levels retain their actual display
meaning; a complete event stream also retains earlier printed headings for a
matcher to verify declared flat-display paths. This reader never invents a
missing parent, upgrades short prose to a title, or derives an amount's topic
from a ratio denominator or numerical agreement.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

from .matrix_evidence import read_matrix
from .native_relations import HEADING_SCOPE_EVIDENCE, heading_evidence
from .representations import visible_text

FURNITURE = {"header", "footer", "page_header", "page_footer", "page_number"}
MEDIA = {"image", "picture", "image_body", "chart", "chart_body", "figure"}
CAPTION_ROLES = {"table_caption"}
NUMBERED_CAPTION = re.compile(r"^(?:Table|Exhibit|附表|表)\s*\d+(?:[.\-]\d+)*(?:\s*[:：.]\s*|\s+)(.+)$", re.I)
PROSE_VERB = re.compile(r"\b(?:shows?|lists?|presents?|describes?|illustrates?|contains?|is|are|was|were|following|below)\b|如下|列示|显示|顯示|表示|見下|见下", re.I)


def _text(block: dict[str, Any]) -> str:
    return visible_text(block.get("text", ""), block.get("text_format", "plain")).strip()


def _source(block: dict[str, Any], position: int, page: Any = None) -> dict[str, Any]:
    return {"path": block.get("native_path", block.get("id")), "block": block.get("id"),
            "position": position, "page": page, "native_sequence": copy.deepcopy(block.get("native_sequence"))}


def _heading(block: dict[str, Any]) -> dict[str, Any] | None:
    if block.get("kind") in FURNITURE | MEDIA or _is_table(block):
        return None
    evidence = heading_evidence(block)
    level = block.get("heading_level")
    if type(level) is int and level > 0:
        evidence.update(resolved_level=level, level_source="heading_level", status="declared_level")
    if evidence["role"] == "heading" or evidence["markdown_status"] == "single_heading":
        return evidence
    return None


def _is_table(block: dict[str, Any]) -> bool:
    return bool(block.get("cells") is not None or block.get("kind") in {"table", "table_body"})


def _caption_candidate(block: dict[str, Any]) -> bool:
    if block.get("kind") in FURNITURE | MEDIA or _is_table(block):
        return False
    text = _text(block)
    if block.get("kind") in CAPTION_ROLES:
        return bool(text)
    return bool(NUMBERED_CAPTION.fullmatch(text) and len(text) <= 180
                and not re.search(r"[。！？!?;；]", text) and not PROSE_VERB.search(text))


def _domains(text: str) -> set[str]:
    # These are generic printed business roles, never company/sample keys.
    cost = bool(re.search(r"營業成本|营业成本|operating costs?|cost of (?:sales|revenue)", text, re.I))
    revenue_text = re.sub(r"cost of (?:sales|revenue)", "", text, flags=re.I)
    revenue = bool(re.search(r"營業收入|营业收入|销售收入|銷售收入|\b(?:operating\s+)?revenue\b|\bsales\b", revenue_text, re.I))
    return ({"cost"} if cost else set()) | ({"revenue"} if revenue else set())


def _table_indicators(block: dict[str, Any], source: dict[str, Any]) -> list[dict[str, Any]]:
    if not block.get("cells"):
        return []
    matrix = read_matrix(block["cells"], source=source)
    found = []
    for fact in matrix["facts"]:
        attribute = fact["attribute"]
        if fact["qualifiers"].get("unit") in {"%", "‰"} or re.search(r"share|ratio|percent|佔.*比|占.*比|比率|同比", attribute, re.I):
            continue
        for text, role in ((fact["attribute"], "metric"), (fact["subject"], "record")):
            domains = _domains(text)
            if domains:
                found.append({"text": text, "role": role, "domains": sorted(domains),
                              "source": copy.deepcopy(fact["source"]),
                              "evidence": "candidate_declared_measurement_role_not_value_or_ratio_denominator"})
    return found


def _flat_heading_paths(result: dict[str, Any], blocks: list[tuple[dict[str, Any], Any]]) -> None:
    """Retain a complete contiguous heading run, without asserting parentage.

    Non-furniture content closes the run to further headings. Its leaf remains
    the current printed context until the next actual heading or document
    boundary, so a paragraph between the leaf and its table cannot erase the
    leaf. A later heading starts a new run and cannot reuse an earlier parent.
    """
    heading_by_block = {event["source"]["block"]: event for event in result["heading_events"]}
    content_types = {event["source"]["block"]: event["type"] for event in result["events"]}
    runs = []
    active = None
    run_open = False
    segment = None
    for block, _page in blocks:
        record = result["by_block"][block["id"]]
        source = record["source"]
        if record["segment"] != segment:
            if active is not None:
                boundary = {"reason": "explicit_document_boundary", "source": source}
                active["boundary"]["scope_stop"] = boundary
                if active["boundary"]["run_stop"] is None:
                    active["boundary"]["run_stop"] = boundary
            active, run_open, segment = None, False, record["segment"]
        heading = heading_by_block.get(block["id"])
        if heading is not None:
            if not run_open:
                if active is not None:
                    active["boundary"]["scope_stop"] = {"reason": "next_actual_heading", "source": source}
                active = {"id": f"flat_heading_run:{len(runs)}", "events": [], "start": source, "end": source,
                          "boundary": {"run_stop": None, "scope_stop": None},
                          "method": "contiguous_actual_heading_run_not_semantic_parentage"}
                runs.append(active)
            active["events"].append(heading)
            active["end"] = source
            run_open = True
        elif block.get("kind") not in FURNITURE:
            if active is not None and run_open:
                active["boundary"]["run_stop"] = {"reason": "intervening_" + content_types[block["id"]], "source": source}
            run_open = False
        record["flat_heading_path"] = [event["text"] for event in active["events"]] if active else []
        record["flat_heading_evidence"] = {
            "run_id": active["id"] if active else None,
            "events": list(active["events"]) if active else [],
            "start": active["start"] if active else None, "end": active["end"] if active else None,
            "boundary": active["boundary"] if active else {"run_stop": None, "scope_stop": None},
            "method": "contiguous_actual_heading_run_not_semantic_parentage",
        }
    for run in runs:
        for key in ("run_stop", "scope_stop"):
            if run["boundary"][key] is None:
                run["boundary"][key] = {"reason": "end_of_saved_input", "source": None}
    result["flat_heading_runs"] = runs


def _explicit_heading_paths(result: dict[str, Any], nodes: dict[str, dict[str, Any]],
                            relations: list[dict[str, Any]], sources: dict[str, dict[str, Any]]) -> None:
    """Expose reference/containment paths for every block, including prose."""
    incoming = defaultdict(list)
    for edge in relations:
        if edge.get("type") == "contains" or (edge.get("type") == "heading_of" and edge.get("evidence") != HEADING_SCOPE_EVIDENCE):
            incoming[edge["target"]].append((edge["source"], edge))
    memo = {}

    def ancestors(ident: str, seen: frozenset[str]) -> list[tuple[list[str], list[dict[str, Any]]]]:
        if ident in seen:
            return []
        if ident in memo:
            return memo[ident]
        paths = []
        for parent, edge in incoming.get(ident, []):
            for prefix, edges in ancestors(parent, seen | {ident}):
                heading = parent in nodes and _heading(nodes[parent]) is not None and bool(_text(nodes[parent]))
                paths.append(([*prefix, parent] if heading else prefix, [*edges, edge]))
        if not incoming.get(ident):
            paths = [([], [])]
        memo[ident] = paths
        return paths

    for ident, record in result["by_block"].items():
        record["explicit_heading_paths"] = []
        record["scope_disagreements"] = []
        record["display_scope"] = list(record["scope"])
        unique = {}
        for path, edges in ancestors(ident, frozenset()):
            if path:
                unique.setdefault(tuple(path), edges)
        # An edge to an ancestor plus an edge to its real descendant is one
        # consistent path. Different source objects remain different paths.
        longest = [path for path in unique if not any(len(other) > len(path) and other[:len(path)] == path for other in unique)]
        for path in longest:
            headings = []
            for heading_id in path:
                if heading_id not in sources:
                    result["issues"].append({"category": "software_unsupported", "reason": "declared_heading_source_unavailable",
                                              "source": record["source"], "heading_id": heading_id})
                    continue
                node = nodes[heading_id]
                headings.append({"text": _text(node), "source": copy.deepcopy(sources[heading_id]),
                                 "level": _heading(node).get("resolved_level"), "role": "explicit_native_heading",
                                 "native_heading_evidence": _heading(node)})
            if len(headings) != len(path):
                continue
            entry = {"path": [heading["text"] for heading in headings], "headings": headings,
                     "edges": copy.deepcopy(unique[path]), "target_source": copy.deepcopy(record["source"]),
                     "method": "explicit_native_heading_reference_path", "status": "bound"}
            if any(result["by_block"][heading_id]["segment"] != record["segment"] for heading_id in path):
                entry["status"] = "cross_document_conflict"
            record["explicit_heading_paths"].append(entry)
            display = record["heading_path"] or record["display_scope"]
            if entry["path"] != display:
                record["scope_disagreements"].append({"explicit_path": copy.deepcopy(entry["path"]),
                    "explicit_sources": [copy.deepcopy(heading["source"]) for heading in headings],
                    "display_path": list(display), "reason": "explicit_native_ownership_differs_from_display_sequence"})
        if len(record["explicit_heading_paths"]) > 1:
            record["conflicts"].append({"reason": "incompatible_explicit_native_heading_parent_paths",
                                         "paths": copy.deepcopy(record["explicit_heading_paths"])})
            record["status"] = "ambiguous"
        elif (record["explicit_heading_paths"] and record["explicit_heading_paths"][0]["status"] == "bound"
              and record["status"] == "unknown"):
            record["status"] = "bound"


def read_contexts(observation: dict[str, Any]) -> dict[str, Any]:
    """Expose candidate scope and its entire actual heading/boundary history."""
    result: dict[str, Any] = {"by_block": {}, "events": [], "heading_events": [], "flat_heading_runs": [], "issues": [],
                              "source_policy": "saved_candidate_only_no_reference_scope_completion"}
    blocks = [(block, page.get("page")) for page in observation.get("pages", []) for block in page.get("blocks", [])]
    counts = defaultdict(int)
    for block, _ in blocks:
        counts[block.get("id")] += 1
    if any(key is None or count != 1 for key, count in counts.items()):
        result["issues"].append({"category": "software_unsupported", "reason": "context_block_identity_not_unique"})
        return result
    nodes = {item["id"]: item for item in observation.get("native_containers", [])}
    nodes.update({block["id"]: block for block, _ in blocks})
    positions = {block["id"]: index for index, (block, _) in enumerate(blocks)}
    sources = {block["id"]: _source(block, index, page) for index, (block, page) in enumerate(blocks)}
    parents = defaultdict(set)
    captions = defaultdict(set)
    linked_headings = defaultdict(set)
    relations = list(observation.get("relations", []))
    for item in nodes.values():
        if item.get("parent_id"):
            relations.append({"type": "contains", "source": item["parent_id"], "target": item["id"], "evidence": "native_parent"})
        for child in item.get("native_children", []):
            relations.append({"type": "contains", "source": item["id"], "target": child, "evidence": "native_children"})
        for caption in item.get("native_references", {}).get("captions", []):
            relations.append({"type": "caption_of", "source": caption, "target": item["id"], "evidence": "native_caption_reference"})
    for edge in relations:
        if edge.get("type") == "contains":
            parents[edge["target"]].add(edge["source"])
        elif edge.get("type") == "caption_of":
            captions[edge["target"]].add(edge["source"])
        elif edge.get("type") == "heading_of":
            linked_headings[edge["target"]].add(edge["source"])
    # Typed body/caption siblings already declare a local table container.
    by_parent = defaultdict(list)
    for block, _ in blocks:
        parent = block.get("native_table_container", block.get("parent_id"))
        if parent:
            by_parent[parent].append(block)
            parents[block["id"]].add(parent)
            if block.get("native_table_container"):
                relations.append({"type": "contains", "source": parent, "target": block["id"], "evidence": "native_table_container"})
    for children in by_parent.values():
        tables = [child for child in children if _is_table(child)]
        if len(tables) == 1:
            captions[tables[0]["id"]].update(child["id"] for child in children if child.get("kind") == "table_caption")
    caption_owners = defaultdict(set)
    for owner, caption_ids in captions.items():
        for caption_id in caption_ids:
            caption_owners[caption_id].add(owner)

    heading_stack = []
    segment = 0
    segment_heading_start = 0
    last_document_title = None
    for index, (block, _page) in enumerate(blocks):
        ident, text, kind = block["id"], _text(block), block.get("kind", "text")
        source = sources[ident]
        heading = _heading(block)
        new_document = (kind in {"document_boundary", "new_document"} or block.get("document_start") is True
                        or kind == "doc_title" and last_document_title is not None and text != last_document_title)
        if new_document:
            segment += 1
            segment_heading_start = len(result["heading_events"])
            heading_stack = []
            result["events"].append({"type": "document_boundary", "source": source, "segment": segment})
            if result["heading_events"]:
                result["heading_events"][-1]["display_end"] = {"reason": "explicit_document_boundary", "source": source}
        if kind == "doc_title" and text:
            last_document_title = text
        if heading is not None:
            level = heading.get("resolved_level")
            event = {"id": f"heading:{len(result['heading_events'])}", "type": "heading", "text": text,
                     "source": source, "level": level, "level_source": heading.get("level_source"),
                     "native_role": kind, "hierarchy_known": level is not None, "segment": segment,
                     "evidence": heading, "next_heading": None, "display_end": None}
            previous = result["heading_events"][-1] if result["heading_events"] else None
            if previous is not None:
                previous["next_heading"] = event["id"]
                if previous["segment"] == segment:
                    previous["display_end"] = {"reason": "next_actual_heading", "source": source}
            if level is None:
                heading_stack = []
            else:
                while heading_stack and (heading_stack[-1]["level"] is None or heading_stack[-1]["level"] >= level):
                    heading_stack.pop()
            if text:
                heading_stack.append(event)
            else:
                heading_stack = []
            result["heading_events"].append(event)
            result["events"].append(event)
        else:
            event_type = ("table" if _is_table(block) else "media" if kind in MEDIA else
                          "page_furniture" if kind in FURNITURE else "ordinary_content")
            result["events"].append({"type": event_type, "text": text if event_type != "table" else "",
                                     "source": source, "segment": segment})
        current = heading_stack[-1] if heading_stack else None
        evidence = [{"text": event["text"], "source": event["source"], "role": "heading",
                     "event_id": event["id"], "method": "actual_heading_role_and_sequence"} for event in heading_stack]
        result["by_block"][ident] = {
            "source": source, "position": index, "segment": segment,
            "scope": [current["text"]] if current else [],
            "heading_path": [event["text"] for event in heading_stack if event["hierarchy_known"]],
            "heading_history_range": [segment_heading_start, len(result["heading_events"])],
            "context_evidence": evidence, "conflicts": [], "rejected_candidates": [],
            "boundary": {"start": current["source"] if current else None, "stop": None,
                         "method": "actual_heading_scope" if current else "no_declared_heading"},
            "status": "bound" if current else "unknown",
        }
    if result["heading_events"] and result["heading_events"][-1]["display_end"] is None:
        result["heading_events"][-1]["display_end"] = {"reason": "end_of_saved_input", "source": None}
    # Preserve real sequence boundaries for each block, including peer/sibling
    # headings. Flat-display reinterpretation belongs to the matcher and must
    # consult these actual events instead of deleting level information.
    for record in result["by_block"].values():
        later = [event for event in result["events"] if event["type"] in {"heading", "document_boundary"}
                 and event["source"]["position"] > record["position"]]
        if later:
            record["boundary"]["stop"] = {"reason": "explicit_document_boundary" if later[0]["type"] == "document_boundary"
                                           else "next_actual_heading", "source": later[0]["source"]}
        else:
            record["boundary"]["stop"] = {"reason": "end_of_saved_input", "source": None}

    _flat_heading_paths(result, blocks)
    _explicit_heading_paths(result, nodes, relations, sources)

    for ident, record in result["by_block"].items():
        block = nodes[ident]
        chain, seen, frontier = [], set(), [ident]
        while frontier:
            child = frontier.pop()
            if child in seen:
                continue
            seen.add(child)
            chain.append(child)
            frontier.extend(parents.get(child, set()))
        direct_captions = set(captions.get(ident, set()))
        for ancestor in chain[1:]:
            parent_node = nodes.get(ancestor, {})
            if parent_node.get("kind", parent_node.get("label")) in {"table", "table_body", "table_region"}:
                direct_captions.update(captions.get(ancestor, set()))
        direct_headings = set().union(*(linked_headings.get(node, set()) for node in chain))
        direct_headings.update(ancestor for ancestor in chain[1:] if ancestor in sources and _heading(nodes[ancestor]) is not None)
        for heading_id in sorted(direct_headings, key=lambda key: positions.get(key, -1)):
            heading_node = nodes.get(heading_id)
            if heading_node is None or heading_id not in sources:
                result["issues"].append({"category": "software_unsupported", "reason": "declared_heading_source_unavailable",
                                          "source": record["source"], "heading_id": heading_id})
                continue
            if heading_node is not None and heading_id in sources and _heading(heading_node) is not None and _text(heading_node):
                if result["by_block"][heading_id]["segment"] != record["segment"]:
                    record["conflicts"].append({"reason": "declared_heading_crosses_explicit_document_boundary",
                                               "heading_source": sources[heading_id], "table_source": record["source"]})
                    continue
                item = {"text": _text(heading_node), "source": sources[heading_id], "role": "heading",
                        "method": "explicit_native_heading_or_parent_relation"}
                if not any(old["source"]["block"] == heading_id for old in record["context_evidence"]):
                    record["context_evidence"].append(item)
                if not record["scope"]:
                    record["scope"] = [item["text"]]
                    record["status"] = "bound"
        if not _is_table(block):
            continue
        caption_items = []
        for caption_id in sorted(direct_captions, key=lambda key: positions.get(key, -1)):
            caption = nodes.get(caption_id)
            if caption is None or caption_id not in sources or not _text(caption):
                result["issues"].append({"category": "software_unsupported", "reason": "declared_caption_source_unavailable",
                                          "source": record["source"], "caption_id": caption_id})
                continue
            if result["by_block"][caption_id]["segment"] != record["segment"]:
                record["conflicts"].append({"reason": "declared_caption_crosses_explicit_document_boundary",
                                           "caption_source": sources[caption_id], "table_source": record["source"]})
                continue
            caption_items.append({"text": _text(caption), "source": sources[caption_id], "role": "table_caption",
                                  "method": "explicit_native_caption_relation"})
        if not caption_items:
            index = record["position"]
            if index > 0:
                previous, _ = blocks[index - 1]
                owned_elsewhere = bool(caption_owners.get(previous["id"], set()) - set(chain))
                if _caption_candidate(previous) and _heading(previous) is None and not owned_elsewhere:
                    caption_items.append({"text": _text(previous), "source": sources[previous["id"]],
                                          "role": "table_caption", "method": "adjacent_declared_or_numbered_caption"})
                elif _caption_candidate(previous) and owned_elsewhere:
                    record["rejected_candidates"].append({"source": sources[previous["id"]], "text": _text(previous),
                        "reason": "caption_already_belongs_to_another_native_table", "owners": sorted(caption_owners[previous["id"]])})
            # A plain short line is never promoted using the table's values
            # or the denominator words in a following ratio header.
            if index > 0 and not caption_items:
                previous, _ = blocks[index - 1]
                if (_text(previous) and _heading(previous) is None and not _is_table(previous)
                        and not any(item["source"]["block"] == previous["id"] for item in record["rejected_candidates"])):
                    record["rejected_candidates"].append({"source": sources[previous["id"]], "text": _text(previous),
                        "reason": "not_an_independently_declared_adjacent_table_title"})
        if caption_items:
            record["context_evidence"].extend(caption_items)
            unique = list(dict.fromkeys(item["text"] for item in caption_items))
            if len(unique) == 1:
                record["scope"] = unique
                record["status"] = "bound"
                record["boundary"]["start"] = caption_items[0]["source"]
                record["boundary"]["method"] = caption_items[0]["method"]
            else:
                record["conflicts"].append({"reason": "multiple_distinct_explicit_table_captions", "sources": caption_items})
                record["status"] = "ambiguous"
        indicators = _table_indicators(block, record["source"])
        record["topic_indicators"] = indicators
        printed_domains = set().union(*(_domains(text) for text in record["scope"]))
        metric_domains = set().union(*(set(item["domains"]) for item in indicators))
        if len(printed_domains) == len(metric_domains) == 1 and printed_domains != metric_domains:
            record["conflicts"].append({"reason": "opposing_explicit_scope_and_measurement_roles",
                "scope_sources": copy.deepcopy(record["context_evidence"]), "measurement_sources": indicators})
            record["status"] = "conflict"
    for record in result["by_block"].values():
        if record["conflicts"]:
            result["issues"].append({"category": "candidate_ambiguity", "reason": "candidate_context_conflict",
                "source": record["source"], "conflicts": copy.deepcopy(record["conflicts"])})
    return result
