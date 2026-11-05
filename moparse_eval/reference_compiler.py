"""Source planning, interpretation and scope resolution for requirements.

The plan is made before semantic readers run. Outside declarations remain
dependencies; only actually selected text is passed to the shared readers.
Scope resolution uses completed semantic readings and their source positions,
never an answer value or the presence of a keyword in the source paragraph.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .expected_readback import _context_kind, _explicit_context


@dataclass(frozen=True)
class SourceUnit:
    target: dict[str, Any]
    scope: tuple[str, ...]
    parents: tuple[str, ...]
    explanations: tuple[dict[str, Any], ...]
    dependencies: tuple[dict[str, Any], ...]


def plan_reference_sources(expected: dict[str, Any]) -> tuple[SourceUnit, ...]:
    """Take independent snapshots; no reader can change the input declaration."""
    selected_headings = {target["text"] for target in expected["targets"] if target["kind"] == "heading"}
    units = []
    for original in expected["targets"]:
        target = copy.deepcopy(original)
        outside = target.get("outside_selection_context", [])
        explanations = [item for item in outside if item.get("kind") == "heading"]
        dependencies = [item for item in outside if item.get("kind") != "heading"]
        external = [name for name in target.get("context", []) if name not in selected_headings]
        if external and not outside:
            explanations.append({"kind": "heading", "text": external})
        scope = ([item["text"] for item in target["selected_heading_context"]]
                 if "selected_heading_context" in target else
                 [name for name in target.get("context", []) if name in selected_headings])
        external_parents = {item.get("text") for item in outside if item.get("kind") == "list_parent"}
        parents = [parent for parent in target.get("parents", []) if parent not in external_parents]
        units.append(SourceUnit(target, tuple(scope), tuple(parents), tuple(explanations), tuple(dependencies)))
    return tuple(units)


def interpret_reference_sources(sample_id: str, units: tuple[SourceUnit, ...]) -> dict[str, Any]:
    """Read the planned source stream through the same faithful components."""
    from .three_layer import _finish, _Graph, _toc_syntax_blocks
    from .toc_evidence import read_toc

    reader = _Graph(sample_id)
    toc = read_toc(blocks=_toc_syntax_blocks([unit.target for unit in units]),
                   source={"path": "<selected-expected-syntax>"})
    handled = reader.toc(toc)
    for unit in units:
        target = unit.target
        source = copy.deepcopy(target["reference"])
        reader.data["scope_context"].extend({"required": False, "target_source": source, **copy.deepcopy(item)}
                                            for item in unit.explanations)
        reader.headings = list(unit.scope)
        if target["id"] in handled:
            if target["kind"] == "heading":
                reader.clear_heading_state()
            reader.data["syntax"].append({"kind": target["kind"], "text": target["text"],
                "source": {**source, "block": target["id"]}, "scope": list(unit.scope), "semantic_role": "toc"})
        elif target.get("cells"):
            reader.table(copy.deepcopy(target["cells"]), source)
        else:
            reader.prose(target.get("raw_text", target["text"]), source,
                         "parent_label" if target.get("has_children") else target["kind"], list(unit.parents),
                         syntax_evidence={"kind": target["kind"], "list_span": copy.deepcopy(target.get("list_span")),
                                          "list_lines": copy.deepcopy(source.get("lines")), "list_stream": source["path"]})
    return _finish(reader)


def _owns(unit: SourceUnit, fact: dict[str, Any]) -> bool:
    reference = unit.target["reference"]
    sources = [fact.get("source", {}), fact.get("statement_source", {})]
    sources.extend(fragment.get("source", {}) for fragment in fact.get("source", {}).get("joined_fragments", []))
    for source in sources:
        if source.get("path") != reference.get("path"):
            continue
        lines, bounds = source.get("lines"), reference.get("lines")
        if (isinstance(lines, (list, tuple)) and isinstance(bounds, (list, tuple))
                and len(lines) == len(bounds) == 2 and bounds[0] <= lines[0] <= lines[1] <= bounds[1]):
            return True
    return False


def resolve_reference_scope(projected: dict[str, Any], units: tuple[SourceUnit, ...]) -> dict[str, Any]:
    """Resolve dependencies after all prose clauses have been interpreted."""
    result = copy.deepcopy(projected)
    for unit in units:
        if not unit.dependencies:
            continue
        local = [fact for fact in result["business"] if _owns(unit, fact)]
        unresolved = []
        for dependency in unit.dependencies:
            if dependency.get("kind") != "explicit_unit_or_period":
                unresolved.append(copy.deepcopy(dependency))
                continue
            key = _context_kind(dependency["text"])
            relevant = [fact for fact in local if not (key == "unit" and fact["role"] == "identity")]
            # An actual selected declaration owns its text rather than relying
            # on an earlier unselected declaration. Unknown bodies remain open.
            if not local and _explicit_context(unit.target["text"]):
                continue
            if relevant:
                if not all(key in fact["qualifiers"] for fact in relevant):
                    unresolved.append(copy.deepcopy(dependency))
            elif not local:
                unresolved.append(copy.deepcopy(dependency))
        if unresolved:
            layers = ["T", "L", "B"] if any(item.get("kind") in {
                "mixed_page_selection_declaration", "partial_syntax_selection"} for item in unresolved) else ["L", "B"]
            result["blockers"].append({"reason": "input_scope_context", "source": copy.deepcopy(unit.target["reference"]),
                                       "layers": layers, "outside_selection": unresolved})
    return result


def compile_reference_semantics(expected: dict[str, Any]) -> dict[str, Any]:
    """Complete each compiler step before projecting any scoring requirement."""
    units = plan_reference_sources(expected)
    interpreted = interpret_reference_sources(expected["sample_id"], units)
    result = resolve_reference_scope(interpreted, units)
    result.update({key: copy.deepcopy(expected.get(key)) for key in (
        "document_id", "family_id", "development_exposure", "source_pages")})
    result["compilation_steps"] = ["plan_authorized_sources", "interpret_selected_semantics",
                                    "resolve_qualifier_and_input_scope", "audit_graph_coverage", "project_independent_layers"]
    return result
