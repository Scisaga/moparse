"""Decode bounded, actually printed row/column header-path scalar records.

No file, pipeline, reference answer or geometric input is accepted. A slash is
syntax only when printed as `` / `` inside a qualified scalar-record grammar.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from .matrix_evidence import MEASUREMENT, YEAR, _compose_unit, _printed_qualifiers
from .measurement_evidence import read_measurement_literal, read_unit_token

_SEPARATOR = re.compile(r" / ")
_COMPARISON = re.compile(r"金[額额]同比[變变][動动]|同比|按年|YoY|year.over.year", re.I)
_PERIOD_ROLE = re.compile(r"\s*(From(?:_period)?|To(?:_period)?|本年|上年|上期|本期|從|从|自|至)\s*[:：]\s*(.+)\s*", re.I)


def _result() -> dict[str, Any]:
    return {"matched": False, "facts": [], "relations": [], "text_atoms": [], "controls": [],
            "consumed_spans": [], "text_projection_complete": False, "pending_requirements": [],
            "blockers": [], "scope": {}, "projection_inputs": {"objects": [], "locators": [], "source_fragments": []}}


def _source(source: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    span = source.get("text_span")
    offset = span[0] if isinstance(span, (tuple, list)) and len(span) == 2 and type(span[0]) is int else 0
    return {**copy.deepcopy(source), "text_span": [offset + start, offset + end]}


def _trim(text: str, start: int, end: int, *, terminal: bool = False) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while start < end and (text[end - 1].isspace() or terminal and text[end - 1] == "。"):
        end -= 1
    return start, end


def _paths(text: str, start: int, end: int) -> list[tuple[int, int]]:
    result, cursor = [], start
    for separator in _SEPARATOR.finditer(text, start, end):
        result.append(_trim(text, cursor, separator.start()))
        cursor = separator.end()
    result.append(_trim(text, cursor, end))
    return result


def _field(text: str, start: int, end: int) -> dict[str, Any] | None:
    paths = _paths(text, start, end)
    a, b = paths[-1]
    pair = re.fullmatch(r"(.+?)[:：]\s*(.+)", text[a:b], re.S)
    if pair is None:
        return None
    header = _trim(text, a + pair.start(1), a + pair.end(1))
    value = _trim(text, a + pair.start(2), a + pair.end(2), terminal=True)
    return {"columns": [*paths[:-1], header], "value": value, "source_span": [start, end],
            "has_column_path": len(paths) > 1}


def _parenthesized(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Unwrap exactly one complete, balanced ASCII or fullwidth group."""
    start, end = _trim(text, start, end)
    pairs = {"(": ")", "（": "）"}
    if start == end or text[start] not in pairs:
        return None
    stack = []
    for position in range(start, end):
        char = text[position]
        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                return None
            if not stack:
                return _trim(text, start + 1, end - 1) if position == end - 1 else None
    return None


def _value(text: str, source: dict[str, Any]) -> dict[str, Any]:
    """Read a scalar plus its own optional terminal labelled unit declaration."""
    plain = read_measurement_literal(text, source)
    plain.update(conflicts=[], declaration_controls=[], declaration_atoms=[])
    if plain["matched"]:
        return plain
    _, end = _trim(text, 0, len(text))
    for opening in re.finditer(r"[(（]", text):
        group = _parenthesized(text, opening.start(), end)
        if group is None:
            continue
        start, stop = group
        label = re.match(r"(?:单位|單位|units?)\s*[:：]\s*", text[start:stop], re.I)
        if label is None:
            continue
        unit_start, unit_end = _trim(text, start + label.end(), stop)
        while (inner := _parenthesized(text, unit_start, unit_end)) is not None:
            unit_start, unit_end = inner
        unit = read_unit_token(text[unit_start:unit_end], _source(source, unit_start, unit_end))
        measured = read_measurement_literal(text[:opening.start()], source)
        if not unit["matched"] or not measured["matched"]:
            return plain  # Preserve the whole unknown value; no partial numeric answer.
        measured.update(conflicts=[], declaration_controls=[(opening.start(), unit_start), (unit_end, end)],
                        declaration_atoms=[(unit_start, unit_end, "unit")])
        if measured["unit"] and measured["unit"] != unit["unit"]:
            measured["conflicts"].append("unit")
            if measured["currency"] and unit["currency"] and measured["currency"] != unit["currency"]:
                measured["conflicts"].append("currency")
        elif not measured["unit"]:
            for role in ("unit", "currency", "currency_symbol"):
                span = unit[role + "_span"]
                measured[role] = unit[role]
                measured[role + "_span"] = [unit_start + span[0], unit_start + span[1]] if span else None
            measured["sources"].update(copy.deepcopy(unit["sources"]))
        return measured
    return plain


def _column(text: str, source: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    literal = text[start:end]
    explicit = _PERIOD_ROLE.fullmatch(literal)
    if explicit:
        q, label, conflicts = _printed_qualifiers(explicit[2].strip())
        if q.keys() == {"period"} and not label and not conflicts:
            key = "from_period" if explicit[1].lower().startswith("from") or explicit[1] in {"上年", "上期", "從", "从", "自"} else "to_period"
            a, b = _trim(text, start + explicit.start(2), start + explicit.end(2))
            return {"qualifiers": {key: text[a:b]}, "label": "", "sources": {key: _source(source, a, b)},
                    "atoms": [(a, b, "period")], "controls": [(start, a, "explicit_comparison_period_key")], "conflicts": []}
    q, label, conflicts = _printed_qualifiers(literal)
    sources, atoms = {}, []
    for key, value in q.items():
        if key == "currency":
            continue  # Currency is an overlapping part of the unit literal.
        if key == "period":
            year = YEAR.search(literal)
            if year:
                a, b = start + year.start(), start + year.end()
                q[key] = text[a:b]  # Keep actual spelling; B/L own calendar equivalence.
            else:
                conflicts.append("period_source_unavailable")
                continue
        else:
            position = literal.find(value)
            if position < 0:
                conflicts.append(key + "_source_unavailable")
                continue
            a, b = start + position, start + position + len(value)
        sources[key] = _source(source, a, b)
        atoms.append((a, b, "period_basis" if key == "period_basis" else key))
    if q.get("unit"):
        unit_source = sources.get("unit")
        if unit_source:
            unit = read_unit_token(q["unit"], unit_source)
            if unit["currency"]:
                sources["currency"] = unit["sources"]["currency"]
    if label:
        position = literal.find(label)
        if position < 0:
            conflicts.append("noncontiguous_metric_label")
        else:
            sources["attribute"] = _source(source, start + position, start + position + len(label))
            atoms.append((start + position, start + position + len(label), "label"))
    return {"qualifiers": q, "label": label, "sources": sources, "atoms": atoms, "controls": [], "conflicts": conflicts}


def _atom(result: dict[str, Any], text: str, source: dict[str, Any], start: int, end: int, role: str) -> None:
    if start < end and not any(item["span"] == [start, end] for item in result["text_atoms"]):
        result["text_atoms"].append({"text": text[start:end], "role": role, "span": [start, end], "source": _source(source, start, end)})


def _pending(result: dict[str, Any], reason: str, text: str, source: dict[str, Any], start: int, end: int, **detail: Any) -> None:
    item = {"reason": reason, "text": text[start:end], "source": _source(source, start, end), **copy.deepcopy(detail)}
    result["pending_requirements"].append(item)
    result["blockers"].append({**copy.deepcopy(item), "layers": ["B"]})


def _project(result: dict[str, Any], text: str, source: dict[str, Any]) -> None:
    owned = [False] * len(text)
    for item in [*result["text_atoms"], *result["controls"]]:
        owned[item["span"][0]:item["span"][1]] = [True] * (item["span"][1] - item["span"][0])
    cursor = 0
    while cursor < len(text):
        if owned[cursor]:
            cursor += 1
            continue
        end = cursor + 1
        while end < len(text) and not owned[end]:
            end += 1
        for fragment in re.finditer(r"[\s:：;；。()（）/]+|[^\s:：;；。()（）/]+", text[cursor:end]):
            a, b = cursor + fragment.start(), cursor + fragment.end()
            if re.fullmatch(r"[\s:：;；。()（）/]+", fragment[0]):
                result["controls"].append({"text": fragment[0], "span": [a, b], "source": _source(source, a, b),
                                           "reason": "explicit_header_path_separator"})
            else:
                _atom(result, text, source, a, b, "pending_requirement")
                actual = _source(source, a, b)["text_span"]
                if not any(item["source"]["text_span"][0] <= actual[0] and actual[1] <= item["source"]["text_span"][1]
                           for item in result["pending_requirements"]):
                    result["blockers"].append({"reason": "header_path_unconsumed_wording", "text": fragment[0],
                                               "source": _source(source, a, b), "layers": ["B"]})
        cursor = end
    result["consumed_spans"] = sorted([
        {"text": item["text"], "span": item["span"], "source": item["source"], "role": item.get("role", "control")}
        for item in [*result["text_atoms"], *result["controls"]]
    ], key=lambda item: item["span"])
    result["text_projection_complete"] = True
    result["projection_inputs"]["source_fragments"] = [{"text": text, "source": copy.deepcopy(source)}]


def read_header_path_requirements(text: str, source: dict[str, Any], *, scope: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """Read an explicit row path followed by qualified column-path scalars."""
    result = _result()
    if " / " not in text or not re.search(r"[;；]", text):
        return result
    pieces = [_trim(text, match.start(), match.end(), terminal=True) for match in re.finditer(r"[^;；]+", text)]
    if len(pieces) < 2:
        return result
    row_span = pieces[0]
    fields = [_field(text, *bounds) for bounds in pieces[1:]]
    decoded = [[_column(text, source, *bounds) for bounds in field["columns"]] if field else [] for field in fields]
    if not any(field and field["has_column_path"] and any(node["qualifiers"] for node in columns)
               and (any(node["label"] and MEASUREMENT.search(node["label"]) for node in columns)
                    or MEASUREMENT.search(text[slice(*row_span)])
                    or read_measurement_literal(text[slice(*field["value"])])["matched"])
               for field, columns in zip(fields, decoded, strict=True)):
        return result
    result["matched"] = True
    row = []
    for a, b in _paths(text, *row_span):
        if b > a and text[b - 1] in ":：":
            b -= 1
            a, b = _trim(text, a, b)
        if a == b or "://" in text[a:b]:
            _pending(result, "header_path_row_identity_unsupported", text, source, *row_span)
            _atom(result, text, source, a, b, "pending_requirement")
            _project(result, text, source)
            return result
        row.append({"text": text[a:b], "source": _source(source, a, b), "span": [a, b]})
        _atom(result, text, source, a, b, "locator")
    groups = [item["text"] for item in row[:-1]]
    facets = {"group": groups[0] if len(groups) == 1 else groups} if groups else {}
    result["scope"] = {"scope": list(scope), "row_path": copy.deepcopy(row), "identity_facets": copy.deepcopy(facets)}
    result["projection_inputs"]["locators"] = copy.deepcopy(row)
    record_key = json.dumps({key: source[key] for key in ("path", "lines", "block", "text_span") if key in source},
                            sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    for bounds, field, columns in zip(pieces[1:], fields, decoded, strict=True):
        start, end = bounds
        if field is None:
            _pending(result, "header_path_field_syntax_unsupported", text, source, start, end)
            _atom(result, text, source, start, end, "pending_requirement")
            continue
        q, q_sources, labels, evidence, conflicts = {}, {}, [], [], []
        for span, node in zip(field["columns"], columns, strict=True):
            for a, b, role in node["atoms"]:
                _atom(result, text, source, a, b, role)
            for a, b, reason in node["controls"]:
                result["controls"].append({"text": text[a:b], "span": [a, b], "source": _source(source, a, b), "reason": reason})
            evidence.append({"role": "column_header", "text": text[slice(*span)], "source": _source(source, *span)})
            conflicts.extend(node["conflicts"])
            if node["label"]:
                labels.append((node["label"], node["sources"].get("attribute")))
            for key, value in node["qualifiers"].items():
                if key in q and q[key] != value:
                    composed = _compose_unit(q[key], value) if key == "unit" else None
                    if composed:
                        q[key] = composed
                        q_sources.pop(key, None)
                        continue
                    conflicts.append(key)
                else:
                    q[key], q_sources[key] = value, node["sources"].get(key)
        if len(labels) == 1 and labels[0][1] and MEASUREMENT.search(labels[0][0]):
            attribute, attribute_source = labels[0]
            subject = row[-1]["text"]
        elif not labels and MEASUREMENT.search(row[-1]["text"]):
            subject, attribute, attribute_source = "", row[-1]["text"], row[-1]["source"]
            for atom in result["text_atoms"]:
                if atom["source"] == attribute_source:
                    atom["role"] = "label"
            result["projection_inputs"]["locators"] = copy.deepcopy(row[:-1])
        else:
            _pending(result, "header_path_metric_roles_ambiguous" if labels else "header_path_row_metric_unproven", text, source, start, end)
            _atom(result, text, source, *field["value"], "pending_requirement")
            continue
        a, b = field["value"]
        measured = _value(text[a:b], _source(source, a, b))
        if not measured["matched"]:
            _pending(result, "header_path_scalar_syntax_unsupported", text, source, start, end, attribute=attribute)
            _atom(result, text, source, a, b, "pending_requirement")
            continue
        for role in ("value", "unit"):
            if measured[role + "_span"]:
                lo, hi = measured[role + "_span"]
                _atom(result, text, source, a + lo, a + hi, role)
        for lo, hi, role in measured["declaration_atoms"]:
            _atom(result, text, source, a + lo, a + hi, role)
        for lo, hi in measured["declaration_controls"]:
            if lo < hi:
                result["controls"].append({"text": text[a + lo:a + hi], "span": [a + lo, a + hi],
                                           "source": _source(source, a + lo, a + hi),
                                           "reason": "explicit_post_value_unit_declaration"})
        conflicts.extend(measured["conflicts"])
        if measured["unit"]:
            if measured["unit"] in {"%", "‰"} and q.get("currency"):
                q["column_currency"], q_sources["column_currency"] = q.pop("currency"), q_sources.pop("currency", None)
            if q.get("unit") and q["unit"] != measured["unit"] and measured["unit"] not in {"%", "‰"}:
                composed = _compose_unit(q["unit"], measured["unit"])
                if composed:
                    q["unit"] = composed
                    q_sources.pop("unit", None)
                else:
                    conflicts.append("unit")
            else:
                q["unit"], q_sources["unit"] = measured["unit"], measured["sources"]["unit"]
        if measured["currency"]:
            if q.get("currency") and q["currency"] != measured["currency"]:
                conflicts.append("currency")
            else:
                q["currency"], q_sources["currency"] = measured["currency"], measured["sources"]["currency"]
        if conflicts:
            _pending(result, "header_path_qualifier_conflict", text, source, start, end, attribute=attribute,
                     conflicts=list(dict.fromkeys(conflicts)))
            continue
        row_evidence = [{"role": "row_group", "text": item["text"], "source": copy.deepcopy(item["source"])} for item in row[:-1]]
        row_evidence.append({"role": "row_header", "text": row[-1]["text"], "source": copy.deepcopy(row[-1]["source"])})
        fact = {"subject": subject, "attribute": attribute, "value": measured["value"], "role": "metric", "qualifiers": q,
                "identity_facets": copy.deepcopy(facets), "scope": list(scope), "record_id": "header-path-record:" + record_key,
                "source": {**_source(source, a, b), "attribute_source": copy.deepcopy(attribute_source),
                           "qualifier_sources": copy.deepcopy(q_sources)},
                "value_source": copy.deepcopy(measured["sources"]["value"]),
                "attribute_source": copy.deepcopy(attribute_source), "qualifier_sources": copy.deepcopy(q_sources),
                "raw_value": text[a:b], "row_path": [item["text"] for item in row],
                "column_path": [text[slice(*span)] for span in field["columns"]],
                "row_evidence": row_evidence, "header_evidence": evidence}
        result["facts"].append(fact)
        endpoint = {key: copy.deepcopy(fact[key]) for key in ("subject", "attribute", "qualifiers", "identity_facets", "scope")}
        result["relations"].append({"type": "field_binding", "left": {"subject": subject, "attribute": attribute},
                                    "right": endpoint, "source": _source(source, a, b),
                                    "binding_evidence": {"rows": copy.deepcopy(row_evidence), "headers": copy.deepcopy(evidence)}})
        result["relations"].extend({"type": "qualifier_scope", "left": {"type": key, "text": value},
                                     "right": copy.deepcopy(endpoint), "source": copy.deepcopy(q_sources.get(key) or fact["source"])}
                                    for key, value in q.items())
        result["projection_inputs"]["objects"].append({"source": _source(source, a, b), "attribute": attribute,
            "attribute_source": copy.deepcopy(attribute_source), "qualifiers": copy.deepcopy(q),
            "qualifier_sources": copy.deepcopy(q_sources), "value": measured["value"],
            "value_source": copy.deepcopy(measured["sources"]["value"]), "row_sources": copy.deepcopy(row),
            "text_atoms": [copy.deepcopy(atom) for atom in result["text_atoms"]
                           if atom["role"] in {"value", "unit", "label", "period", "period_basis"}
                           and (start <= atom["span"][0] < atom["span"][1] <= end or atom["source"] == attribute_source)]})
        if _COMPARISON.search(attribute) and not {"from_period", "to_period"} <= q.keys():
            _pending(result, "header_path_comparison_periods_unresolved", text, source, start, end, attribute=attribute)
    _project(result, text, source)
    return result
