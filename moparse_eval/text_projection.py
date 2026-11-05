"""Candidate-local, bounded text aliases for explicit record schemas.

An alias expands an actually printed schema term to an independently present
data object. It never invents a value, uses a reference, inspects a grade, or
deduplicates wording merely because strings or heading scopes agree. The same
projection is used for authored requirement syntax and candidate syntax.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from .matrix_evidence import UNIT as _PRINTED_UNIT

_SCHEMA_KEYS = re.compile(r"Group|Item|Record|Section|Property|Attribute|Field|Metric|Value|分組|分组|組別|组别|项目|項目|指标|指標|属性|屬性|字段|值|數值|数值", re.I)
_QUALIFIER_KEYS = re.compile(r"Units?|Currency|Period|Year|Scope|单位|單位|币种|幣種|期间|期間|年度|口径|口徑", re.I)
_SEPARATORS = re.compile(r"^[\s:：/;；,，、()（）]+$")


def _key(source: dict[str, Any]) -> str:
    # Source identity excludes literal values and business answers.
    names = ("path", "cell", "native_path", "lines", "block", "block_lines", "row", "col", "text_span", "cell_text_span")
    return json.dumps({name: source[name] for name in names if name in source}, ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))


def _origin(text: str, role: str, source: dict[str, Any]) -> dict[str, Any]:
    return {"id": role + ":" + _key(source), "text": text, "role": role, "source": copy.deepcopy(source)}


def _projection() -> dict[str, Any]:
    return {"atoms": [], "origins": [], "controls": [], "aliases": [], "source_cells": [],
            "source_fragments": [], "blockers": [], "complete": True}


def _literal(result: dict[str, Any], origin: dict[str, Any]) -> None:
    if not origin["text"].strip():
        return
    result["origins"].append(copy.deepcopy(origin))
    result["atoms"].append({**copy.deepcopy(origin), "projection_kind": "literal", "origins": [copy.deepcopy(origin)]})


def _alias(result: dict[str, Any], origin: dict[str, Any], obj: dict[str, Any]) -> None:
    result["origins"].append(copy.deepcopy(origin))
    endpoint = {"id": obj["id"], "source": copy.deepcopy(obj["source"])}
    atom = {**copy.deepcopy(origin), "projection_kind": "bounded_alias", "data_object": endpoint,
            "origins": [copy.deepcopy(origin)], "alias_key": obj["id"] + ":" + origin["role"] + ":" + origin["text"]}
    result["atoms"].append(atom)
    result["aliases"].append({"origin": copy.deepcopy(origin), "data_object": copy.deepcopy(endpoint)})


def combine_text_projections(projections: list[dict[str, Any]]) -> dict[str, Any]:
    """Join local projections, merging only aliases of the same data object.

    Schema declarations with no actual data object remain one literal
    occurrence. Distinct physical values and ordinary prose never merge.
    """
    result = _projection()
    aliases: dict[str, dict[str, Any]] = {}
    origins: dict[str, dict[str, Any]] = {}
    declarations: dict[str, dict[str, Any]] = {}
    claimed: set[str] = set()
    snapshots: dict[str, dict[str, dict[str, Any]]] = {"source_cells": {}, "source_fragments": {}}
    for projection in projections:
        result["complete"] &= projection.get("complete", False)
        result["blockers"].extend(copy.deepcopy(projection.get("blockers", [])))
        result["controls"].extend(copy.deepcopy(projection.get("controls", [])))
        result["aliases"].extend(copy.deepcopy(projection.get("aliases", [])))
        for field, values in snapshots.items():
            for snapshot in projection.get(field, []):
                identity = _key(snapshot["source"])
                if identity in values and values[identity] != snapshot:
                    raise ValueError("one text source has conflicting actual evidence snapshots")
                values.setdefault(identity, copy.deepcopy(snapshot))
        for origin in projection.get("origins", []):
            origins.setdefault(origin["id"], copy.deepcopy(origin))
        for origin in projection.get("declarations", []):
            declarations.setdefault(origin["id"], copy.deepcopy(origin))
        for atom in projection.get("atoms", []):
            if atom.get("projection_kind") != "bounded_alias":
                result["atoms"].append(copy.deepcopy(atom))
                continue
            identifier = atom["alias_key"]
            target = aliases.get(identifier)
            if target is None:
                target = aliases[identifier] = copy.deepcopy(atom)
                result["atoms"].append(target)
            else:
                known = {item["id"] for item in target["origins"]}
                target["origins"].extend(copy.deepcopy(item) for item in atom["origins"] if item["id"] not in known)
            claimed.update(item["id"] for item in atom["origins"])
    for identifier, origin in declarations.items():
        if identifier not in claimed:
            result["atoms"].append({**origin, "projection_kind": "literal", "origins": [copy.deepcopy(origin)]})
    for index, atom in enumerate(result["atoms"]):
        atom["id"] = f"projected-text:{index}"
    result["origins"] = list(origins.values())
    for field, values in snapshots.items():
        result[field] = list(values.values())
    return result


def project_literal_text(text: str, source: dict[str, Any], *, role: str = "literal") -> dict[str, Any]:
    """Keep one real literal occurrence, including all internal whitespace."""
    result = _projection()
    _literal(result, _origin(text, role, source))
    result["source_fragments"].append({"source": copy.deepcopy(source), "text": text})
    return result


def project_metric_declaration(declaration: dict[str, Any]) -> dict[str, Any]:
    """Project one proven parent metric; only actual child objects may use it.

    This entry consumes the source-only compact reader's declaration event,
    never an arbitrary parent word. An unused declaration remains literal.
    """
    result = _projection()
    origin_source = declaration.get("source", {})
    parent_source = declaration.get("parent_source", {})
    text, parent_text = declaration.get("text"), declaration.get("parent_text")
    bounds = origin_source.get("text_span")
    parent_bounds = parent_source.get("text_span", [0, len(parent_text or "")])
    valid = (declaration.get("provenance") == "qualified_period_value_parent"
             and declaration.get("role") == "label" and isinstance(text, str) and isinstance(parent_text, str)
             and origin_source and parent_source and origin_source.get("location") != "declared_parent_text"
             and isinstance(bounds, (list, tuple)) and len(bounds) == 2
             and isinstance(parent_bounds, (list, tuple)) and len(parent_bounds) == 2)
    if valid:
        start, end = bounds[0] - parent_bounds[0], bounds[1] - parent_bounds[0]
        valid = 0 <= start < end <= len(parent_text) and parent_text[start:end] == text
    if not valid:
        result["complete"] = False
        result["blockers"].append({"reason": "compact_parent_declaration_source_unavailable", "source": copy.deepcopy(origin_source)})
        return result
    # Only a plain parent label or an explicit Metric label is a supported
    # declaration. A parent containing ordinary prose is never swallowed.
    prefix, suffix = parent_text[:start], parent_text[end:]
    if suffix.strip() or (prefix.strip() and not re.fullmatch(r"\s*(?:Metric|指标|指標)\s*[:：=]\s*", prefix, re.I)):
        result["complete"] = False
        result["blockers"].append({"reason": "compact_parent_declaration_syntax_unsupported", "source": copy.deepcopy(parent_source)})
        return result
    origin = _origin(text, "label", origin_source)
    result["declarations"] = [origin]
    result["origins"] = [copy.deepcopy(origin)]
    result["source_fragments"].append({"source": copy.deepcopy(parent_source), "text": parent_text})
    for a, b in [(0, start), (end, len(parent_text))]:
        if a < b:
            result["controls"].append({"text": parent_text[a:b], "source": {
                **copy.deepcopy(parent_source), "text_span": [parent_bounds[0] + a, parent_bounds[0] + b]},
                "span": [a, b], "reason": "explicit_metric_declaration_key"})
    return result


def _cell_source(cell: dict[str, Any], source: dict[str, Any], span: tuple[int, int] | None = None) -> dict[str, Any]:
    result = {**source, "cell": cell.get("id", cell.get("native_path")), "row": cell.get("row"), "col": cell.get("col")}
    if cell.get("native_path"):
        result["native_path"] = cell["native_path"]
    if span is not None:
        result["cell_text_span"] = list(span)
    return result


def _parts(text: str, qualifiers: list[dict[str, str]], source: dict[str, Any], attributes: set[str]) -> list[dict[str, Any]]:
    """Split only explicitly printed qualifier atoms, preserving metric words."""
    spans: list[tuple[int, int, str]] = []
    local = [*qualifiers, *({"unit": match[1]} for match in re.finditer(r"[（(]([^()（）]+)[)）]", text)
                           if _PRINTED_UNIT.fullmatch(match[1]))]
    for q in local:
        for role in ("unit", "period", "currency"):
            literal = q.get(role)
            if not literal:
                continue
            for match in re.finditer(re.escape(literal), text):
                a, b = match.span()
                before, after = text[:a], text[b:]
                whole = not before.strip() and not after.strip()
                bracketed = bool(re.search(r"[（(]\s*$", before) and re.match(r"\s*[)）]", after))
                labelled = bool(re.fullmatch(r"(?:Units?|Currency|Period|Year|单位|單位|币种|幣種|期间|期間|年度)\s*[:：]\s*", before, re.I))
                prefix_period = role == "period" and a == 0 and (not after or re.match(r"[\s/（(]|[\u3400-\u9fff]", after))
                metric_unit_suffix = role == "unit" and not after.strip() and before.strip() in attributes
                if whole or bracketed or labelled or prefix_period or metric_unit_suffix:
                    if not any(a < stop and start < b for start, stop, _ in spans):
                        spans.append((a, b, role))
    result = []
    cursor = 0
    for a, b, role in sorted(spans):
        if a > cursor:
            result.append(_origin(text[cursor:a], "label", {**source, "cell_text_span": [cursor, a]}))
        result.append(_origin(text[a:b], role, {**source, "cell_text_span": [a, b]}))
        cursor = b
    if cursor < len(text):
        result.append(_origin(text[cursor:], "label", {**source, "cell_text_span": [cursor, len(text)]}))
    return result


def _covers(header: dict[str, Any], data: dict[str, Any], role: str) -> bool:
    attrs = header.get("native_attributes", {})
    column = attrs.get("scope") in {"col", "colgroup"} or attrs.get("role") == "columnheader" or header.get("is_column_header") or header.get("column_header")
    row = attrs.get("scope") in {"row", "rowgroup"} or attrs.get("role") == "rowheader" or header.get("is_row_header") or header.get("row_header")
    column = column or role == "column_header" and not row
    row = row or role == "row_header" and not column
    if column and header["col"] <= data["col"] < header["col"] + header.get("col_span", 1) and data["row"] >= header["row"] + header.get("row_span", 1):
        return True
    return bool(row and header["row"] <= data["row"] < header["row"] + header.get("row_span", 1)
                and data["col"] >= header["col"] + header.get("col_span", 1) and role != "row_group")


def _measurement_cell(result: dict[str, Any], obj: dict[str, Any], source: dict[str, Any]) -> bool:
    """Use existing cell-local measurement spans without interpreting answers."""
    cell = obj["cell"]
    raw = cell.get("text", "")
    own = _cell_source(cell, source)
    facts = obj["facts"]
    if any(fact.get("role") == "identity" for fact in facts):
        return False
    proofs = [fact for fact in facts if fact.get("value_source")]
    if not proofs:
        return False
    emitted = []
    for fact in proofs:
        parts = [("value", fact["value"], fact["value_source"])]
        unit = fact.get("qualifiers", {}).get("unit")
        unit_source = fact.get("qualifier_sources", {}).get("unit")
        if unit and unit_source:
            parts.append(("unit", unit, unit_source))
        local = []
        for role, text, proof in parts:
            span = proof.get("cell_text_span", proof.get("text_span"))
            identity = all(proof.get(key) == own.get(key) for key in
                           ("path", "cell", "native_path", "lines", "block", "block_lines", "row", "col"))
            if (not identity or not isinstance(span, (list, tuple)) or len(span) != 2
                    or not all(type(position) is int for position in span)
                    or not 0 <= span[0] < span[1] <= len(raw) or raw[span[0]:span[1]] != text):
                local = []
                break
            local.append((span[0], span[1], role, text))
        occupied = [False] * len(raw)
        for a, b, _, _ in local:
            if any(occupied[a:b]):
                local = []
                break
            occupied[a:b] = [True] * (b - a)
        if not local or any(not present and not character.isspace() for present, character in zip(occupied, raw, strict=True)):
            result["complete"] = False
            result["blockers"].append({"reason": "measurement_literal_source_mismatch", "source": own})
            _literal(result, _origin(raw, "value", _cell_source(cell, source, (0, len(raw)))))
            return True
        if emitted and emitted != local:
            result["complete"] = False
            result["blockers"].append({"reason": "measurement_literal_source_conflict", "source": own})
            _literal(result, _origin(raw, "value", _cell_source(cell, source, (0, len(raw)))))
            return True
        emitted = local
    for a, b, role, text in emitted:
        origin = _origin(text, role, _cell_source(cell, source, (a, b)))
        if role == "unit":
            _alias(result, origin, obj)
        else:
            _literal(result, origin)
    return True


def project_table_text(cells: list[dict[str, Any]], matrix_result: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Expose source literals plus finite schema aliases over existing cells.

    Header text capacity follows native structural declarations, independently
    of successful business comparison or explicit-reference correctness.
    """
    result = _projection()
    for cell in cells:
        result["source_cells"].append({
            "source": _cell_source(cell, source), "text": cell.get("text", ""),
            "row_span": cell.get("row_span", 1), "col_span": cell.get("col_span", 1),
            "roles": [item["role"] for item in matrix_result.get("roles", []) if item.get("id") == cell.get("id")],
            "native_declarations": {name: copy.deepcopy(cell[name]) for name in (
                "native_attributes", "native_header_tag", "native_header_section", "is_column_header",
                "is_row_header", "column_header", "row_header", "row_section") if name in cell},
        })
    by_id = {cell.get("id", cell.get("native_path")): cell for cell in cells}
    facts = matrix_result.get("facts", [])
    objects: dict[str, dict[str, Any]] = {}
    for fact in facts:
        data = fact.get("data_evidence", {})
        cell = by_id.get(data.get("id", fact.get("source", {}).get("cell")))
        if cell is None:
            continue
        origin = _cell_source(cell, source)
        objects.setdefault(_key(origin), {"id": "data:" + _key(origin), "source": origin, "cell": cell, "facts": []})["facts"].append(fact)
    roles = {item.get("id"): item.get("role") for item in matrix_result.get("roles", [])}
    qualifiers = [fact.get("qualifiers", {}) for fact in facts]
    attributes = {fact["attribute"] for fact in facts}
    handled: set[Any] = set()
    for obj in objects.values():
        cell = obj["cell"]
        text = cell.get("text", "")
        handled.add(cell.get("id", cell.get("native_path")))
        if _measurement_cell(result, obj, source):
            continue
        unit = next((f.get("qualifiers", {}).get("unit") for f in obj["facts"] if f.get("qualifiers", {}).get("unit")), None)
        if unit and text.endswith(unit) and len(text) > len(unit):
            stop = len(text) - len(unit)
            # Only printed suffixes split; signs and internal number spaces
            # remain in the actual numeric token.
            _literal(result, _origin(text[:stop], "value", _cell_source(cell, source, (0, stop))))
            _alias(result, _origin(unit, "unit", _cell_source(cell, source, (stop, len(text)))), obj)
        else:
            _literal(result, _origin(text, "value", _cell_source(cell, source, (0, len(text)))))
    for cell in cells:
        identifier = cell.get("id", cell.get("native_path"))
        if identifier in handled:
            continue
        text = cell.get("text", "")
        if not isinstance(text, str) or not text.strip():
            continue
        cell_source = _cell_source(cell, source)
        role = roles.get(identifier)
        related = [obj for obj in objects.values() if _covers(cell, obj["cell"], role or "")]
        references = [obj for obj in objects.values() if any(
            item.get("id") == identifier for fact in obj["facts"]
            for item in [*fact.get("header_evidence", []), *fact.get("row_evidence", [])])]
        # A printed Unit row has no geometric header span. Its reader supplies
        # actual record-qualifier references to its finite eligible objects.
        if role == "qualifier_value":
            related = references
        is_attribute = any(fact.get("attribute") == text.strip() for fact in facts)
        if role == "qualifier_label" or (_SCHEMA_KEYS.fullmatch(text.strip()) and role == "column_header" and not is_attribute):
            result["controls"].append({"text": text, "source": cell_source, "reason": "explicit_record_schema_role"})
            continue
        if role in {"row_group", "row_header"} and not is_attribute and not _QUALIFIER_KEYS.fullmatch(text.strip()):
            _literal(result, _origin(text, "locator", cell_source))
            continue
        parts = _parts(text, qualifiers, cell_source, attributes) if role else [_origin(text, "literal", cell_source)]
        for part in parts:
            if _SEPARATORS.fullmatch(part["text"]) or _QUALIFIER_KEYS.fullmatch(part["text"].strip().rstrip(":：")):
                result["controls"].append({"text": part["text"], "source": part["source"], "reason": "explicit_qualifier_or_schema_syntax"})
                continue
            # Boundary brackets/separators are relationship syntax. Whitespace
            # inside a word or number is preserved verbatim.
            if part["role"] == "label":
                original = part["text"]
                value = original.strip() if original.strip() in attributes else original.strip(" \t\r\n（）():：/")
                offset = original.find(value) if value else 0
                if value != original and value:
                    a = part["source"]["cell_text_span"][0]
                    for lo, hi in ((0, offset), (offset + len(value), len(original))):
                        if hi > lo:
                            result["controls"].append({"text": original[lo:hi], "source": {**part["source"], "cell_text_span": [a + lo, a + hi]}, "reason": "explicit_header_separator"})
                    part = _origin(value, "label", {**part["source"], "cell_text_span": [a + offset, a + offset + len(value)]})
            if related and part["role"] in {"label", "period", "unit", "currency"}:
                for obj in related:
                    _alias(result, part, obj)
            else:
                _literal(result, part)
    if not matrix_result.get("complete", not matrix_result.get("blockers")):
        result["complete"] = False
        result["blockers"] = copy.deepcopy(matrix_result.get("blockers", []))
    return combine_text_projections([result])


def project_header_path_text(decoded: dict[str, Any]) -> dict[str, Any]:
    """Project printed column paths over only their own actual scalar objects.

    Row locators occur once. Labels, periods and units have finite per-object
    capacity, with the original literal spans retained even for pending fields.
    """
    result = _projection()
    inputs = decoded.get("projection_inputs", {})
    result["source_fragments"] = copy.deepcopy(inputs.get("source_fragments", []))
    result["controls"] = copy.deepcopy(decoded.get("controls", []))
    result["complete"] = decoded.get("text_projection_complete", False)
    claimed: set[str] = set()
    for item in inputs.get("objects", []):
        obj = {"id": "data:" + _key(item["source"]), "source": copy.deepcopy(item["source"])}
        for atom in item.get("text_atoms", []):
            origin = _origin(atom["text"], atom["role"], atom["source"])
            if atom["role"] in {"label", "period", "period_basis", "unit"}:
                _alias(result, origin, obj)
            else:
                _literal(result, origin)
            claimed.add(origin["id"])
    for atom in decoded.get("text_atoms", []):
        origin = _origin(atom["text"], atom["role"], atom["source"])
        if origin["id"] not in claimed:
            _literal(result, origin)
    return result


def project_compact_text(result: dict[str, Any], schema: dict[str, Any] | None, source: dict[str, Any], *,
                         raw_text: str | None = None) -> dict[str, Any]:
    """Project complete compact syntax using only its own source declarations.

    Combine a schema projection and its actual record projections together with
    ``combine_text_projections``. Orphan declarations remain literal; used
    declarations acquire exactly one alias per existing data object.
    """
    projection = _projection()
    projection["declarations"] = []
    if raw_text is not None:
        projection["source_fragments"].append({"source": copy.deepcopy(source), "text": raw_text})
    if not result.get("text_projection_complete"):
        projection["complete"] = False
        projection["blockers"] = copy.deepcopy(result.get("blockers", [])) or [{"reason": "compact_source_ranges_unavailable", "source": copy.deepcopy(source)}]
        for atom in result.get("text_atoms", []):
            _literal(projection, _origin(atom["text"], atom["role"], atom["source"]))
        return projection
    projection["controls"] = copy.deepcopy(result.get("controls", []))
    atoms = result.get("text_atoms", [])
    if not result.get("facts"):
        projection["declarations"] = [_origin(atom["text"], atom["role"], atom["source"]) for atom in atoms]
        projection["origins"] = copy.deepcopy(projection["declarations"])
        return projection
    claimed: set[str] = set()
    for fact in result["facts"]:
        fact_source = fact.get("source", {})
        obj = {"id": "data:" + _key(fact_source), "source": copy.deepcopy(fact_source)}
        bounds = fact_source.get("text_span")
        if not bounds:
            projection["complete"] = False
            projection["blockers"].append({"reason": "compact_value_object_span_unavailable", "source": copy.deepcopy(fact_source)})
            continue
        for atom in atoms:
            span = atom["source"].get("text_span")
            if span and bounds[0] <= span[0] and span[1] <= bounds[1] and atom["role"] in {"value", "unit"}:
                origin = _origin(atom["text"], atom["role"], atom["source"])
                if atom["role"] == "unit":
                    _alias(projection, origin, obj)
                else:
                    _literal(projection, origin)
                claimed.add(origin["id"])
        attribute_source = fact_source.get("attribute_source")
        q_sources = fact_source.get("qualifier_sources", {})
        for role, text, origin_source in [
            ("label", fact["attribute"], attribute_source),
            *[(name, value, q_sources.get(name)) for name, value in fact.get("qualifiers", {}).items()
              if name in {"period", "period_basis", "unit"}],
        ]:
            if origin_source:
                if origin_source.get("location") == "declared_parent_text":
                    projection["complete"] = False
                    projection["blockers"].append({"reason": "compact_parent_declaration_source_unavailable",
                                                    "source": copy.deepcopy(origin_source)})
                    continue
                _alias(projection, _origin(text, role, origin_source), obj)
        # Inline reiterations retain their own source while sharing only the
        # declaration for this independently present value object.
        for atom in atoms:
            if atom["role"] not in {"label", "period"}:
                continue
            wanted = fact["attribute"] if atom["role"] == "label" else fact.get("qualifiers", {}).get("period")
            if wanted and atom["text"] == wanted:
                origin = _origin(atom["text"], atom["role"], atom["source"])
                _alias(projection, origin, obj)
                claimed.add(origin["id"])
    for atom in atoms:
        origin = _origin(atom["text"], atom["role"], atom["source"])
        if origin["id"] not in claimed:
            _literal(projection, origin)
    return projection
