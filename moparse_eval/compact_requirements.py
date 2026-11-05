"""Read explicitly declared compact measurements without candidate answers.

The caller supplies only printed text and its own declared context. This
module neither opens files nor looks at another output. Column declarations,
record labels and qualifiers retain separate roles and source spans.
"""

from __future__ import annotations

import copy
import re
from typing import Any

YEAR = r"(?:19|20)\d{2}年?"
_YEAR = re.compile(YEAR)
_PAIR = re.compile(r"^\s*([^:：=]+?)\s*[:：=]\s*(.*)$", re.S)
_INTRO = re.compile(r"各[項项]分[別别]列示|列[說说]明\s*[:：]|Columns?\s*[:：]", re.I)
_AMOUNT = re.compile(r"金[額额]|Amount", re.I)
_SHARE = re.compile(r"[佔占][^、;；。\n（）()]*?比|[佔占]比|Share|Ratio|Percentage|比例", re.I)
_CHANGE = re.compile(r"金[額额](?:同比|按年)(?:[變变][動动]|[變变]化|增[減减])|(?:Amount\s+)?(?:YoY|year.on.year)(?:\s+change)?", re.I)
_UNIT_CAPTION = re.compile(r"(?:(?:金[額额])?(?:單位|单位)|Units?)\s*[:：=]\s*([^。;；\n]+)", re.I)
_BASIS = re.compile(r"截至[^。;；\n]*?(?:止年度|年度)")
_UNIT = re.compile(r"(?:人民[幣币]|美元|港元|港[幣币]|歐元|欧元|日元|RMB|CNY|USD|HKD|EUR|JPY)?\s*(?:百萬|百万|千萬|千万|億|亿|萬|万|百|千)?(?:元|股|人|件|噸|吨)|[%‰]|萬元|万元", re.I)
_CURRENCY = re.compile(r"人民[幣币]|美元|港元|港[幣币]|歐元|欧元|日元|RMB|CNY|USD|HKD|EUR|JPY", re.I)
_PRIMARY = re.compile(r"Name|Entity|Company|Subject|名称|名稱|姓名|主体|主體|公司名称|公司名稱", re.I)
_FACET = re.compile(r"Type|Market|Region|Category|Role|类型|類型|市场|市場|地区|地區|类别|類別|职务|職務", re.I)
_QUALIFIERS = {
    "unit": re.compile(r"Unit|Units|单位|單位", re.I),
    "currency": re.compile(r"Currency|币种|幣種", re.I),
    "period": re.compile(r"Period|Year|期间|期間|年度", re.I),
    "scope": re.compile(r"Scope|口径|口徑", re.I),
    "note": re.compile(r"Note|附注|附註", re.I),
    "condition": re.compile(r"Condition|条件|條件", re.I),
}


def _result(matched: bool = False) -> dict[str, Any]:
    return {"matched": matched, "facts": [], "consumed_spans": [], "text_atoms": [],
            "controls": [], "blockers": [], "scope": {}, "text_projection_complete": False}


def _source(source: dict[str, Any], span: tuple[int, int] | list[int]) -> dict[str, Any]:
    parent = source.get("text_span")
    offset = parent[0] if isinstance(parent, (tuple, list)) and len(parent) == 2 and type(parent[0]) is int else 0
    return {**copy.deepcopy(source), "text_span": [offset + position for position in span]}


def _atom(result: dict[str, Any], text: str, source: dict[str, Any], start: int, end: int, role: str) -> None:
    if start < end:
        item = {"text": text[start:end], "role": role, "span": [start, end], "source": _source(source, [start, end])}
        if not any(old["span"] == item["span"] and old["role"] == role for old in result["text_atoms"]):
            result["text_atoms"].append(item)


def _controls(result: dict[str, Any], text: str, source: dict[str, Any], *, schema: bool = False) -> None:
    """Account only for recognized relation syntax, never arbitrary wording."""
    owned = [False] * len(text)
    for item in result["text_atoms"]:
        for position in range(*item["span"]):
            owned[position] = True
    for item in result["controls"]:
        for position in range(*item["span"]):
            owned[position] = True
    allowed = re.compile(r"[\s:：=;；、，,。()（）.]+|及|和|and", re.I) if schema else re.compile(r"[\s:：=;；、，,。()（）.]+")
    cursor = 0
    while cursor < len(text):
        if owned[cursor]:
            cursor += 1
            continue
        end = cursor + 1
        while end < len(text) and not owned[end]:
            end += 1
        fragment = text[cursor:end]
        position = 0
        for match in allowed.finditer(fragment):
            if match.start() != position:
                break
            if schema and re.fullmatch(r"及|和|and", match[0], re.I):
                declaration = result.get("schema") or {}
                columns, change = declaration.get("columns", []), declaration.get("change")
                last_column = max((proof["text_span"][1] for column in columns
                                   for proof in (column.get("source"), column.get("unit_source")) if proof), default=0)
                declaration_end = change["source"]["text_span"][0] if change else last_column
                parent = source.get("text_span")
                offset = parent[0] if isinstance(parent, (tuple, list)) and len(parent) == 2 and type(parent[0]) is int else 0
                if (not columns or not columns[0]["period_source"]["text_span"][0] - offset
                        <= cursor + match.start() < declaration_end - offset):
                    break
            result["controls"].append({"span": [cursor + match.start(), cursor + match.end()],
                                       "text": match[0], "reason": "explicit_column_declaration_syntax" if schema else "explicit_record_separator",
                                       "source": _source(source, [cursor + match.start(), cursor + match.end()])})
            position = match.end()
        if position != len(fragment) and fragment[position:].strip():
            result["blockers"].append({"reason": "compact_unconsumed_wording", "source": _source(source, [cursor + position, end]),
                                       "text": fragment[position:]})
        cursor = end
    result["consumed_spans"] = sorted([
        {"span": atom["span"], "text": atom["text"], "role": atom["role"], "source": atom["source"]}
        for atom in result["text_atoms"]
    ] + [{"span": control["span"], "text": control["text"], "role": "control", "source": control["source"]}
         for control in result["controls"]], key=lambda item: (item["span"][0], item["span"][1]))
    projected = set(position for item in result["consumed_spans"] for position in range(*item["span"]))
    result["text_projection_complete"] = all(position in projected or character.isspace()
                                              for position, character in enumerate(text))


def _unit_after(text: str, end: int) -> tuple[str | None, tuple[int, int] | None]:
    match = re.match(r"\s*[（(]\s*([^()（）]+?)\s*[)）]", text[end:])
    if match and _UNIT.fullmatch(match[1].strip()):
        start = end + match.start(1)
        return match[1].strip(), (start, end + match.end(1))
    return None, None


def _currency(unit: str | None) -> str | None:
    match = _CURRENCY.search(unit or "")
    return match[0] if match else None


def read_compact_schema(text: str, source: dict[str, Any], *,
                        qualifiers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read two-period amount/share columns and an optional printed change."""
    result = _result()
    result["schema"] = None
    intro = _INTRO.search(text)
    if not intro:
        return result
    result["matched"] = True
    result["controls"].append({"span": [intro.start(), intro.end()], "text": intro[0],
                               "reason": "explicit_column_declaration_introduction",
                               "source": _source(source, [intro.start(), intro.end()])})
    q = dict(qualifiers or {})
    q_sources = {}
    unit_caption = _UNIT_CAPTION.search(text[:intro.start()])
    if unit_caption:
        q["unit"] = unit_caption[1].strip()
        _atom(result, text, source, unit_caption.start(1), unit_caption.end(1), "unit")
        result["controls"].append({"span": [unit_caption.start(), unit_caption.start(1)],
                                   "text": text[unit_caption.start():unit_caption.start(1)],
                                   "reason": "explicit_unit_declaration_key",
                                   "source": _source(source, [unit_caption.start(), unit_caption.start(1)])})
    basis = _BASIS.search(text[:intro.start()])
    if basis:
        q["period_basis"] = basis[0]
        q_sources["period_basis"] = _source(source, [basis.start(), basis.end()])
        _atom(result, text, source, basis.start(), basis.end(), "period_basis")
    years = list(_YEAR.finditer(text, intro.end()))
    change = _CHANGE.search(text, intro.end())
    if len(years) != 2:
        result["blockers"].append({"reason": "compact_column_schema_incomplete", "source": copy.deepcopy(source),
                                   "periods": [match[0] for match in years]})
        return result
    if change and change.start() < years[-1].end():
        result["blockers"].append({"reason": "compact_comparison_column_scope_ambiguous", "source": copy.deepcopy(source)})
        return result
    if change and int(years[0][0][:4]) <= int(years[1][0][:4]):
        result["blockers"].append({"reason": "compact_comparison_period_order_unsupported", "source": copy.deepcopy(source),
                                   "periods": [match[0] for match in years]})
        return result
    columns = []
    for index, year in enumerate(years):
        end = years[index + 1].start() if index + 1 < len(years) else change.start() if change else len(text)
        amount = _AMOUNT.search(text, year.end(), end)
        share = _SHARE.search(text, year.end(), end)
        if amount is None or share is None or amount.start() >= share.start():
            result["blockers"].append({"reason": "compact_column_roles_incomplete", "source": _source(source, [year.start(), end])})
            continue
        _atom(result, text, source, year.start(), year.end(), "period")
        for match, role in ((amount, "amount"), (share, "share")):
            unit, unit_span = _unit_after(text, match.end())
            unit = unit or (q.get("unit") if role == "amount" else None)
            _atom(result, text, source, match.start(), match.end(), "label")
            if unit_span:
                _atom(result, text, source, *unit_span, "unit")
            columns.append({"period": year[0], "attribute": match[0], "kind": role, "unit": unit,
                            "currency": _currency(unit) if role == "amount" else None,
                            "source": _source(source, [match.start(), match.end()]),
                            "period_source": _source(source, [year.start(), year.end()]),
                            "unit_source": _source(source, unit_span) if unit_span else (
                                _source(source, [unit_caption.start(1), unit_caption.end(1)]) if unit_caption and role == "amount" else None)})
    change_column = None
    if change:
        _atom(result, text, source, change.start(), change.end(), "label")
        change_unit, change_unit_span = _unit_after(text, change.end())
        if change_unit_span:
            _atom(result, text, source, *change_unit_span, "unit")
        change_column = {"attribute": change[0], "kind": "change", "unit": change_unit,
                         "source": _source(source, [change.start(), change.end()]),
                         "unit_source": _source(source, change_unit_span) if change_unit_span else None}
    if len(columns) == 4:
        if columns[0]["attribute"] != columns[2]["attribute"] or columns[1]["attribute"] != columns[3]["attribute"]:
            result["blockers"].append({"reason": "compact_year_columns_have_different_roles", "source": copy.deepcopy(source)})
        result["schema"] = {
            "columns": columns,
            "periods": [year[0] for year in years],
            "change": change_column,
            "qualifiers": {key: value for key, value in q.items() if key != "unit"},
            "qualifier_sources": q_sources,
            "source": copy.deepcopy(source),
        }
    _controls(result, text, source, schema=True)
    return result


def _parent_source(parent: str | dict[str, Any], origin: dict[str, Any], text: str,
                   start: int, end: int) -> dict[str, Any]:
    if not isinstance(parent, dict):
        return copy.deepcopy(origin)
    existing = origin.get("text_span", [0, len(text)])
    offset = existing[0] if isinstance(existing, (tuple, list)) and len(existing) == 2 else 0
    return {**copy.deepcopy(origin), "text_span": [offset + start, offset + end]}


def _metric_declaration(parent: str | dict[str, Any], origin: dict[str, Any], text: str,
                        index: int, label: str, start: int, end: int) -> dict[str, Any]:
    return {"text": label, "role": "label", "source": _parent_source(parent, origin, text, start, end),
            "parent_text": text, "parent_source": copy.deepcopy(origin), "parent_index": index,
            "provenance": "qualified_period_value_parent"}


def _parent_scope(parents: list[str | dict[str, Any]], source: dict[str, Any], subject: str,
                  qualifiers: dict[str, Any] | None, identity_facets: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {"subject": subject, "qualifiers": dict(qualifiers or {}),
                              "identity_facets": copy.deepcopy(identity_facets or {}), "labels": [],
                              "attribute": None, "evidence": []}
    for index, parent in enumerate(parents):
        text = parent["text"] if isinstance(parent, dict) else parent
        origin = parent.get("source", {}) if isinstance(parent, dict) else {
            "path": source.get("path"), "parent_index": index, "text": text,
            "location": "declared_parent_text"}
        raw_parent = text

        pair = _PAIR.fullmatch(text)
        if pair:
            key, value = pair[1].strip(), pair[2].strip()
            if _PRIMARY.fullmatch(key):
                result["subject"] = value
                start = pair.start(2) + len(pair[2]) - len(pair[2].lstrip())
                result["evidence"].append({"role": "subject", "text": value,
                                           "source": _parent_source(parent, origin, raw_parent, start, start + len(value))})
                continue
            if _FACET.fullmatch(key):
                result["identity_facets"][key] = value
                result["evidence"].append({"role": "identity_facet", "text": value, "source": origin})
                continue
            if re.fullmatch(r"Group|分组|分組", key, re.I):
                result["identity_facets"]["group"] = value
                start = pair.start(2) + len(pair[2]) - len(pair[2].lstrip())
                result["evidence"].append({"role": "group", "text": value,
                                           "source": _parent_source(parent, origin, raw_parent, start, start + len(value))})
                continue
            if re.fullmatch(r"Metric|指标|指標", key, re.I):
                result["attribute"] = value
                start = pair.start(2) + len(pair[2]) - len(pair[2].lstrip())
                result["attribute_source"] = _parent_source(parent, origin, raw_parent, start, start + len(value))
                result["attribute_declaration"] = _metric_declaration(parent, origin, raw_parent, index, value, start, start + len(value))
                continue
            qualifier = next((kind for kind, pattern in _QUALIFIERS.items() if pattern.fullmatch(key)), None)
            if qualifier:
                result["qualifiers"][qualifier] = value
                result["evidence"].append({"role": qualifier, "text": value, "source": origin})
                continue
            if re.match(rf"^{YEAR}", value):
                text = key  # A parent record name is separate from its values.
        period_selector = re.fullmatch(rf"({YEAR})(?:[，,]\s*(.+))?", text.strip())
        if period_selector:
            result["qualifiers"]["period"] = period_selector[1]
            result["evidence"].append({"role": "period", "text": period_selector[1], "source": origin})
            if period_selector[2] and _UNIT.fullmatch(period_selector[2]):
                result["qualifiers"]["unit"] = period_selector[2]
                if _currency(period_selector[2]):
                    result["qualifiers"]["currency"] = _currency(period_selector[2])
                result["evidence"].append({"role": "unit", "text": period_selector[2], "source": origin})
            elif period_selector[2]:
                result["labels"].append({"text": text.strip(), "source": origin})
        elif _UNIT.fullmatch(text.strip()):
            result["qualifiers"]["unit"] = text.strip()
            result["evidence"].append({"role": "unit", "text": text.strip(), "source": origin})
        else:
            start = raw_parent.find(text.strip())
            result["labels"].append({"text": text.strip(), "source": _parent_source(parent, origin, raw_parent, start, start + len(text.strip())),
                                     "declaration": _metric_declaration(parent, origin, raw_parent, index, text.strip(), start, start + len(text.strip()))
                                     if text == raw_parent else None})
    return result


def _groups(scope: dict[str, Any], labels: list[dict[str, Any]]) -> dict[str, Any]:
    facets = copy.deepcopy(scope["identity_facets"])
    if labels:
        previous = facets.get("group")
        groups = ([previous] if isinstance(previous, str) else list(previous or [])) + [item["text"] for item in labels]
        facets["group"] = groups[0] if len(groups) == 1 else groups
    return facets


def _row_evidence(scope: dict[str, Any], labels: list[dict[str, Any]], subject: str,
                  subject_source: dict[str, Any] | None) -> list[dict[str, Any]]:
    evidence = [{"role": "row_group", "text": item["text"], "source": copy.deepcopy(item["source"])} for item in labels]
    evidence.extend({"role": "row_group", "text": item["text"], "source": copy.deepcopy(item["source"])}
                    for item in scope["evidence"] if item["role"] == "group")
    if subject_source:
        evidence.append({"role": "row_header", "text": subject, "source": copy.deepcopy(subject_source)})
    return evidence


def _value(text: str, start: int, end: int, default_unit: str | None,
           result: dict[str, Any], source: dict[str, Any]) -> tuple[str, str | None]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] == "。"):
        end -= 1
    raw = text[start:end]
    unit = default_unit
    suffix = re.search(r"[%‰]$|(?:人民[幣币]|美元)?(?:百萬|百万|千萬|千万|億|亿|萬|万|百|千)?元$", raw)
    if suffix:
        unit = suffix[0]
        _atom(result, text, source, start + suffix.start(), end, "unit")
        end = start + suffix.start()
        raw = text[start:end].strip()
    _atom(result, text, source, start, end, "value")
    return raw, unit


def read_compact_requirements(text: str, source: dict[str, Any], *, schema: dict[str, Any] | None = None,
                              parents: list[str | dict[str, Any]] | tuple[str | dict[str, Any], ...] = (),
                              subject: str = "", qualifiers: dict[str, Any] | None = None,
                              identity_facets: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read compact rows and explicitly qualified metric leaves.

    Five measurements arise from a declared two-year amount/share/change row,
    never from a file name, particular value or the count of parent list levels.
    """
    result = _result()
    if schema and "schema" in schema:
        schema = schema["schema"]
    scope = _parent_scope(list(parents), source, subject, qualifiers, identity_facets)
    result["scope"] = copy.deepcopy(scope)
    body_start = 0
    outer = _PAIR.fullmatch(text)
    outer_label = None
    if outer and re.match(rf"^\s*{YEAR}", outer[2]) and not _YEAR.match(outer[1].strip()):
        outer_label = outer[1].strip()
        body_start = outer.start(2)
        _atom(result, text, source, outer.start(1), outer.end(1), "locator")
    clauses = []
    for match in re.finditer(r"[^;；]+", text[body_start:]):
        start, end = body_start + match.start(), body_start + match.end()
        while start < end and text[start].isspace():
            start += 1
        while end > start and (text[end - 1].isspace() or text[end - 1] == "。"):
            end -= 1
        if start < end:
            clauses.append((start, end))
    compact = bool(schema and any(_YEAR.match(text[start:end]) or _CHANGE.match(text[start:end])
                                 or (scope["qualifiers"].get("period") and _PAIR.fullmatch(text[start:end])
                                     and any(column["attribute"] == _PAIR.fullmatch(text[start:end])[1].strip()
                                             for column in schema["columns"]))
                                 for start, end in clauses))
    leaf = bool(len(clauses) == 1 and re.match(rf"^{YEAR}(?:[，,].*?)?\s*[:：]", text[clauses[0][0]:clauses[0][1]]))
    if not compact and not leaf:
        if outer and re.match(rf"^\s*{YEAR}", outer[2]) and "、" in outer[2]:
            result["matched"] = True
            result["blockers"].append({"reason": "compact_column_schema_unavailable", "source": copy.deepcopy(source)})
            return result
        return _result()
    result["matched"] = True
    labels = list(scope["labels"])
    if compact:
        subject_source = None
        if outer_label:
            row_subject = outer_label
            start = outer.start(1) + len(outer[1]) - len(outer[1].lstrip())
            subject_source = _source(source, [start, start + len(row_subject)])
        elif labels:
            subject_parent = labels.pop()
            row_subject, subject_source = subject_parent["text"], subject_parent["source"]
        else:
            row_subject = scope["subject"]
            subject_source = next((item["source"] for item in reversed(scope["evidence"])
                                   if item["role"] == "subject" and item["text"] == row_subject), None)
        if not row_subject:
            result["blockers"].append({"reason": "compact_record_subject_unavailable", "source": copy.deepcopy(source)})
        facets = _groups(scope, labels)
        active_period = scope["qualifiers"].get("period")
        columns = schema["columns"]
        for start, end in clauses:
            fragment = text[start:end]
            year = _YEAR.match(fragment)
            change = _CHANGE.match(fragment)
            if year:
                active_period = year[0]
                _atom(result, text, source, start, start + year.end(), "period")
                rest_start = start + year.end()
                while rest_start < end and text[rest_start] in " :：，,":
                    rest_start += 1
                selected = [column for column in columns if column["period"] == active_period]
                # Printed attributes make an independently split field; two
                # bare tuple entries use the declaration's explicit order.
                attribute = _PAIR.fullmatch(text[rest_start:end])
                if attribute:
                    name = attribute[1].strip()
                    bound = [column for column in selected if column["attribute"] == name]
                    if len(bound) != 1:
                        result["blockers"].append({"reason": "compact_declared_attribute_unavailable", "source": _source(source, [rest_start, end]), "attribute": name})
                        continue
                    column = bound[0]
                    _atom(result, text, source, rest_start + attribute.start(1), rest_start + attribute.end(1), "label")
                    values = [(rest_start + attribute.start(2), rest_start + attribute.end(2), column)]
                else:
                    pieces = list(re.finditer(r"[^、]+", text[rest_start:end]))
                    if len(pieces) != len(selected) or not selected:
                        result["blockers"].append({"reason": "compact_value_arity_ambiguous", "source": _source(source, [rest_start, end]),
                                                   "declared_columns": len(selected), "printed_values": len(pieces)})
                        continue
                    values = [(rest_start + piece.start(), rest_start + piece.end(), column)
                              for piece, column in zip(pieces, selected, strict=True)]
            elif change:
                column = schema.get("change")
                _atom(result, text, source, start, start + change.end(), "label")
                value_start = start + change.end()
                while value_start < end and text[value_start] in " :：":
                    value_start += 1
                if column is None:
                    value, unit = _value(text, value_start, end, None, result, source)
                    pending = {"subject": row_subject, "attribute": change[0], "value": value,
                               "qualifiers": {"unit": unit} if unit else {}, "reason": "compact_change_column_undeclared",
                               "source": _source(source, [start, end]), "raw_value": text[value_start:end]}
                    result.setdefault("pending_requirements", []).append(pending)
                    result["blockers"].append({"reason": "compact_change_column_undeclared", "source": pending["source"], "layers": ["B"]})
                    continue
                values = [(value_start, end, column)]
            else:
                pair = _PAIR.fullmatch(fragment)
                bound = [column for column in columns if pair and column["attribute"] == pair[1].strip()
                         and column["period"] == active_period]
                if len(bound) != 1:
                    result["blockers"].append({"reason": "compact_clause_role_unavailable", "source": _source(source, [start, end]), "text": fragment})
                    continue
                _atom(result, text, source, start + pair.start(1), start + pair.end(1), "label")
                values = [(start + pair.start(2), start + pair.end(2), bound[0])]
            for value_start, value_end, column in values:
                value, unit = _value(text, value_start, value_end, column.get("unit"), result, source)
                q = {**scope["qualifiers"], **schema.get("qualifiers", {})}
                q.pop("unit", None)
                if column.get("kind") == "change":
                    # This is the declared comparison order, not the maximum
                    # year and never a direction selected by a matching value.
                    q.pop("period", None)
                    q.update(to_period=schema["periods"][0], from_period=schema["periods"][1])
                else:
                    q["period"] = column["period"]
                if unit:
                    q["unit"] = unit
                if _currency(unit) or column.get("currency"):
                    q["currency"] = _currency(unit) or column["currency"]
                if column["kind"] in {"share", "change"} and not unit:
                    result["blockers"].append({"reason": "compact_ratio_unit_unavailable", "source": _source(source, [value_start, value_end])})
                qualifier_sources = {**copy.deepcopy(schema.get("qualifier_sources", {})),
                                     **{key: copy.deepcopy(column.get(key + "_source")) for key in ("unit", "period")
                                        if column.get(key + "_source")}}
                result["facts"].append({"subject": row_subject, "attribute": column["attribute"], "value": value,
                    "role": "metric", "qualifiers": q, "identity_facets": copy.deepcopy(facets),
                    "row_evidence": _row_evidence(scope, labels, row_subject, subject_source),
                    "qualifier_sources": copy.deepcopy(qualifier_sources),
                    "source": {**_source(source, [value_start, value_end]), "attribute_source": copy.deepcopy(column["source"]),
                               "qualifier_sources": qualifier_sources},
                })
        result["scope"].update(subject=row_subject, identity_facets=facets, labels=copy.deepcopy(labels))
    else:
        start, end = clauses[0]
        match = re.fullmatch(rf"({YEAR})(?:[，,]\s*([^:：]+))?\s*[:：]\s*(.*)", text[start:end], re.S)
        if match is None:
            return _result()
        attribute_source = scope.get("attribute_source")
        leaf_subject = scope["subject"]
        if scope["attribute"]:
            attribute = scope["attribute"]
            attribute_declaration = scope.get("attribute_declaration")
            leaf_subject = outer_label or leaf_subject
        elif outer_label and not labels:
            attribute = outer_label
            attribute_declaration = None
            attribute_source = _source(source, [outer.start(1), outer.end(1)])
            for atom in result["text_atoms"]:
                if atom["span"] == [outer.start(1), outer.end(1)]:
                    atom["role"] = "label"
        elif labels:
            attribute_parent = labels.pop()
            attribute, attribute_source = attribute_parent["text"], attribute_parent["source"]
            attribute_declaration = attribute_parent.get("declaration")
            if outer_label:
                result["blockers"].append({"reason": "compact_leaf_parent_roles_ambiguous", "source": copy.deepcopy(source),
                                           "outer_label": outer_label, "parent_label": attribute})
        else:
            attribute = None
            attribute_declaration = None
        if not attribute:
            result["blockers"].append({"reason": "period_value_metric_unavailable", "source": copy.deepcopy(source)})
        q = dict(scope["qualifiers"])
        q["period"] = match[1]
        _atom(result, text, source, start + match.start(1), start + match.end(1), "period")
        if match[2]:
            selector = match[2].strip()
            if _UNIT.fullmatch(selector):
                q["unit"] = selector
                if _currency(selector):
                    q["currency"] = _currency(selector)
                _atom(result, text, source, start + match.start(2), start + match.end(2), "unit")
            elif selector.endswith("列") and _CURRENCY.fullmatch(selector[:-1]):
                q["column_currency"] = selector[:-1]
                _atom(result, text, source, start + match.start(2), start + match.end(2) - 1, "column_currency")
                result["controls"].append({"span": [start + match.end(2) - 1, start + match.end(2)], "text": "列", "reason": "explicit_column_dimension",
                                           "source": _source(source, [start + match.end(2) - 1, start + match.end(2)])})
            else:
                result["blockers"].append({"reason": "period_value_column_selector_unsupported", "source": _source(source, [start + match.start(2), start + match.end(2)]), "text": selector})
        value_start, value_end = start + match.start(3), start + match.end(3)
        value, unit = _value(text, value_start, value_end, q.get("unit"), result, source)
        if unit:
            q["unit"] = unit
        if unit in {"%", "‰"}:
            q.pop("currency", None)
        requirement = {"subject": leaf_subject, "attribute": attribute, "value": value,
                       "role": "metric", "qualifiers": q, "identity_facets": _groups(scope, labels),
                       "source": {**_source(source, [value_start, value_end]),
                                  "attribute_source": copy.deepcopy(attribute_source),
                                  "parent_context_evidence": copy.deepcopy(scope["evidence"])}}
        if attribute:
            result["facts"].append(requirement)
            if attribute_declaration:
                result["metric_declarations"] = [copy.deepcopy(attribute_declaration)]
        else:
            # Keep the unresolved obligation and its text, rather than passing
            # a non-label to matching or interpreting a year as the metric.
            result.setdefault("pending_requirements", []).append(requirement)
    _controls(result, text, source)
    return result
