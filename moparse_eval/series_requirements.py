"""Source-only explicit period scalar series and printed unit declarations.

This reader has no file or reference-writing interface. Each year is an
explicit position. Multiple values and deictic comparison periods are never
assigned roles merely by their position among numbers.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .measurement_evidence import read_measurement_label, read_measurement_literal, read_unit_token
from .period_evidence import DATE_PATTERN, read_period_label
from .quantity import normalize_unit

_YEAR_TEXT = r"(?:19|20)\d{2}(?:年(?:度|末|初)?|(?!\d))"
_YEAR = re.compile(_YEAR_TEXT)
_PAIR = re.compile(r"^\s*([^:：;；\n]+?)\s*[:：]\s*(.*)$", re.S)
_CURRENCY_TEXT = r"人民币|人民幣|美元|港元|港币|港幣|欧元|歐元|日元|USD|RMB|CNY|HKD|EUR|JPY|[$€£¥]"
_CURRENCY = re.compile(_CURRENCY_TEXT, re.I)
_GROWTH = re.compile(r"本年比上年增[減减]|較上年同期增[減减]|较上年同期增[減减]|金[額额]同比[變变][動动]|同比[變变][動动]|增[減减](?:幅度)?|YoY(?:\s+change)?", re.I)
_CHANGE_DIRECTIONS = {"增长": "increase", "增長": "increase", "增加": "increase", "上升": "increase",
                      "下降": "decrease", "减少": "decrease", "減少": "decrease"}
_DIRECTED_CHANGE = re.compile("|".join(_CHANGE_DIRECTIONS))
_UNSIGNED_MAGNITUDE = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+")
_CAUSE = re.compile(r"(?:报告期内变动的主要原因|報告期內變動的主要原因|变动原因|變動原因|主要原因|原因|Reason|Cause)", re.I)
_BASIS = re.compile(r"(?:截至|於|于)[^。;；\n，,]{1,35}(?:止年度|止期间|止期間|年度)|(?:於|于)\d{1,2}月\d{1,2}日")
_NONANNUAL = re.compile(r"[一二三四1234]季度|全年|(?:月均|年末)(?:余额|餘額|金[額额])|(?:Q[1-4]|Quarter\s+[1-4])", re.I)
_IDENTITY = re.compile(r"Name|Entity|Company|Subject|名称|名稱|姓名|主体|主體|公司名称|公司名稱|ID|Code|Ticker", re.I)
_ORDINARY_FIELD = re.compile(
    r"Date(?:\s*Time)?|Time|Timestamp|(?:Issue|Start|End|Maturity|Effective|Settlement)\s+date|"
    r"URL|URI|Website|Link|Identifier|Reference(?:\s+(?:No\.?|Number))?|Serial(?:\s+(?:No\.?|Number))?|"
    r"No\.?|编号|編號|序号|序號|日期|时间|時間|网址|網址|链接|鏈接|"
    r"(?:起息|到期|成立|生效|签署|簽署|发行|發行)日", re.I)
_CALENDAR_VALUE = re.compile(
    rf"{DATE_PATTERN}(?:(?:\s*|T)\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:Z|[+\-]\d{{2}}:\d{{2}})?)?[。.]?", re.I)
_CALENDAR_PREFIX = re.compile(DATE_PATTERN, re.I)
_YEAR_DIGITS = r"(?:19|20)\d{2}"
_QUARTER_FIRST = re.compile(rf"(?:Q(?P<short>\d+)|Quarter\s+(?P<long>\d+))\s+{_YEAR_DIGITS}(?=$|[\s:：，,])", re.I)
_QUARTER_YEAR_FIRST = re.compile(rf"{_YEAR_DIGITS}(?:\s+Q(?P<short>\d+)|年\s*第?(?P<zh>[一二三四\d]+)季度)(?=$|[\s:：，,])", re.I)
_ANNUAL_TOTAL = re.compile(rf"Total\s+{_YEAR_DIGITS}(?=$|[\s:：，,])", re.I)
_ATTRIBUTION = re.compile(r"(?P<metric>[^:：;；。！？!?\n]+?)(?P<relation>\s+attributable\s+to|[归歸][属屬][于於])\s*[:：]?\s*$", re.I)


def _ordinary_field(label: str) -> bool:
    # A printed enumeration belongs to this field's label; this view is only
    # used to determine its role and never changes its text or source span.
    role = re.sub(r"^\s*\d+\s*[、.)）]\s*", "", label).strip()
    return bool(_IDENTITY.fullmatch(role) or _ORDINARY_FIELD.fullmatch(role))


def is_ordinary_scalar_field(label: str, value: str) -> bool:
    """Recognize a printed atomic metadata field without interpreting its value.

    This routing guard shares no field answer or expected context. A complete
    calendar-looking value stays intact even if the calendar date is invalid.
    """
    return not re.search(r"[;；\n]", value) and bool(_ordinary_field(label) or _CALENDAR_VALUE.fullmatch(value.strip()))


def _period_position(text: str, source: dict[str, Any], start: int = 0) -> dict[str, Any] | None:
    """Read a printed selector, retaining its role rather than inventing dates."""
    fragment = text[start:]
    calendar = _CALENDAR_PREFIX.match(fragment)
    if calendar:
        end = start + calendar.end()
        # A Chinese day marker proves the boundary before an adjacent scalar.
        # Numeric/English endings require a separator; 2028-03-3117 cannot be
        # split into an invented March 31 position followed by 17.
        bounded = calendar[0].endswith("日") or end == len(text) or text[end] in " \t:：，,"
        if bounded:
            label = calendar[0]
            parsed = read_period_label(label, _source(source, start, end))
            return {"kind": "calendar_day", "valid": parsed["matched"], "text": label,
                    "end": end, "source": _source(source, start, end)}
    for expression in (_QUARTER_FIRST, _QUARTER_YEAR_FIRST):
        quarter = expression.match(fragment)
        if quarter:
            number = next(value for value in quarter.groupdict().values() if value is not None)
            return {"kind": "quarter", "valid": number in {"1", "2", "3", "4", "一", "二", "三", "四"},
                    "text": quarter[0], "end": start + quarter.end(), "source": _source(source, start, start + quarter.end())}
    total = _ANNUAL_TOTAL.match(fragment)
    if total:
        return {"kind": "annual_total", "valid": True, "text": total[0], "end": start + total.end(),
                "source": _source(source, start, start + total.end())}
    year = _YEAR.match(fragment)
    if year:
        end = start + year.end()
        if "年" in year[0] and re.match(r"\d{1,2}月", text[end:]):
            return {"kind": "incomplete_calendar_selector", "valid": False, "text": fragment,
                    "end": len(text), "source": _source(source, start, len(text))}
        return {"kind": "year", "valid": True, "text": year[0], "end": end, "source": _source(source, start, end)}
    return None


def _annual_scalar_start(text: str) -> bool:
    """Require a bounded printed selector and a following quantity to route.

    A bare YYYY key/value is still one ordinary scalar. A decimal starting
    with those digits cannot be divided into an invented year and value.
    """
    if _CALENDAR_VALUE.fullmatch(text.strip()):
        return False
    position = _period_position(text, {})
    if position is None:
        return False
    if not position["valid"]:
        return True
    remainder = text[position["end"]:]
    if position["kind"] == "year" and "年" not in position["text"] and (not remainder or remainder[0] not in " \t:：，,"):
        return False
    payload = remainder.lstrip(" \t:：，,")
    if re.match(rf"(?:{_CURRENCY_TEXT})?\s*(?:[（(][+\-−]?\s*\d|[+\-−]?(?:\d|\.\d)|[—–-])", payload, re.I):
        return True
    # Explicit but unsupported annual multi-role labels remain pending. They
    # carry their own following quantity, rather than being an empty year.
    return bool(re.match(r"(?:余额|餘額|金[額额])\s*[+\-−]?\d", payload))


def _result() -> dict[str, Any]:
    return {"matched": False, "facts": [], "text_atoms": [], "controls": [], "consumed_spans": [],
            "text_projection_complete": False, "blockers": [], "issues": [], "pending_requirements": [], "scope": {}}


def _source(source: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    span = source.get("text_span")
    offset = span[0] if isinstance(span, (tuple, list)) and len(span) == 2 and type(span[0]) is int else 0
    return {**copy.deepcopy(source), "text_span": [offset + start, offset + end]}


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] == "。"):
        end -= 1
    return start, end


def _parts(text: str, start: int = 0) -> list[tuple[int, int]]:
    return [_trim(text, start + match.start(), start + match.end())
            for match in re.finditer(r"[^;；。\n]+", text[start:]) if match[0].strip()]


def _atom(result: dict[str, Any], text: str, source: dict[str, Any], start: int, end: int, role: str) -> None:
    start, end = _trim(text, start, end)
    if start < end:
        result["text_atoms"].append({"text": text[start:end], "span": [start, end], "role": role,
                                     "source": _source(source, start, end)})


def _control(result: dict[str, Any], text: str, source: dict[str, Any], start: int, end: int, reason: str) -> None:
    if start < end:
        result["controls"].append({"text": text[start:end], "span": [start, end], "reason": reason,
                                   "source": _source(source, start, end)})


def _project(result: dict[str, Any], text: str, source: dict[str, Any]) -> None:
    owned = [False] * len(text)
    for item in [*result["text_atoms"], *result["controls"]]:
        for position in range(*item["span"]):
            owned[position] = True
    cursor = 0
    while cursor < len(text):
        if owned[cursor]:
            cursor += 1
            continue
        end = cursor + 1
        while end < len(text) and not owned[end]:
            end += 1
        fragment = text[cursor:end]
        if re.fullmatch(r"[\s:：;；，,。()（）.]+", fragment):
            _control(result, text, source, cursor, end, "explicit_series_separator")
        elif fragment.strip():
            result["blockers"].append({"reason": "series_unconsumed_text", "source": _source(source, cursor, end),
                                       "text": fragment, "layers": ["T", "B"]})
        cursor = end
    result["consumed_spans"] = sorted([
        {"span": item["span"], "text": item["text"], "role": item["role"], "source": item["source"]}
        for item in result["text_atoms"]
    ] + [{"span": item["span"], "text": item["text"], "role": "control", "source": item["source"]}
         for item in result["controls"]], key=lambda item: (item["span"][0], item["span"][1]))
    covered = {position for item in result["consumed_spans"] for position in range(*item["span"])}
    result["text_projection_complete"] = all(position in covered or character.isspace()
                                              for position, character in enumerate(text))


def _block(result: dict[str, Any], reason: str, text: str, source: dict[str, Any], start: int, end: int, **extra: Any) -> None:
    result["blockers"].append({"reason": reason, "source": _source(source, start, end), "layers": ["B"], **extra})
    result["pending_requirements"].append({"text": text[start:end], "source": _source(source, start, end), "reason": reason, **extra})
    _atom(result, text, source, start, end, "pending_requirement")


def _attribution_parent(parents, parent_declarations):
    names = [parent["text"] if isinstance(parent, dict) else parent for parent in parents]
    names = [name for name in names if isinstance(name, str) and _ATTRIBUTION.fullmatch(name)]
    declarations = (list(parent_declarations) if parent_declarations is not None else
                    [parent for parent in parents if isinstance(parent, dict)])
    declared = [item for item in declarations if isinstance(item, dict)
                and isinstance(item.get("text"), str) and _ATTRIBUTION.fullmatch(item["text"])]
    if not names and not declared:
        return None
    if len(names) > 1 or len(declared) > 1:
        return {"reason": "series_attribution_parent_ambiguous", "parents": copy.deepcopy(declared), "parent_labels": names}
    if not declared:
        return {"reason": "series_attribution_parent_source_unavailable", "parent_labels": names}
    parent = declared[0]
    origin = parent.get("source")
    if not isinstance(origin, dict) or not origin.get("path") or origin.get("location") == "declared_parent_text":
        return {"reason": "series_attribution_parent_source_unavailable", "parent_labels": names or [parent["text"]]}
    if names and names != [parent["text"]]:
        return {"reason": "series_attribution_parent_path_conflict", "parents": copy.deepcopy(declared), "parent_labels": names}
    raw = parent["text"]
    start = len(raw) - len(raw.lstrip())
    end = len(raw.rstrip().rstrip(":：").rstrip())
    return {"parent": {"text": raw[start:end], "source": _source(origin, start, end)},
            "original": {"text": raw, "source": copy.deepcopy(origin)}, "label_span": [start, end],
            "rule_id": "printed_attribution_parent_and_recipient"}


def _attribution_projection(result, text, source, binding):
    """Expose bounded aliases over only this reader's actual scalar objects."""
    child, parent, original = binding["child"], binding["parent"], binding["original"]
    objects, fields = [], []
    for index, fact in enumerate(result["facts"]):
        if "attribution" not in fact.get("role_basis", {}):
            continue
        fact["id"] = f"series-attribution:{index}"
        fields.append({"fact_id": fact["id"], "attribute_source": copy.deepcopy(fact["attribute_source"]),
                       "value_source": copy.deepcopy(fact["value_source"]), "source": copy.deepcopy(fact["source"])})
        atoms = [{"text": fact["attribute"], "role": "label", "source": copy.deepcopy(fact["attribute_source"])},
                 {"text": fact["value"], "role": "value", "source": copy.deepcopy(fact["value_source"])}]
        for key in ("period", "period_basis", "unit"):
            if key in fact["qualifiers"] and key in fact["qualifier_sources"]:
                atoms.append({"text": fact["qualifiers"][key], "role": key, "source": copy.deepcopy(fact["qualifier_sources"][key])})
        objects.append({"source": copy.deepcopy(fact["source"]), "attribute": fact["attribute"],
                        "attribute_source": copy.deepcopy(fact["attribute_source"]), "value": fact["value"],
                        "value_source": copy.deepcopy(fact["value_source"]), "qualifiers": copy.deepcopy(fact["qualifiers"]),
                        "qualifier_sources": copy.deepcopy(fact["qualifier_sources"]), "text_atoms": atoms})
    if not fields:
        return
    result["parent_bindings"] = [{"kind": "attribution", "rule_id": binding["rule_id"],
        "parent": copy.deepcopy(parent), "child": copy.deepcopy(child), "facts": fields,
        **({"record_evidence": copy.deepcopy(binding["record_evidence"])} if binding.get("record_evidence") else {})}]
    result["projection_inputs"] = {"objects": objects, "locators": [{**copy.deepcopy(child), "role": "record_label"}],
        "source_fragments": [{"text": text, "source": copy.deepcopy(source)}, copy.deepcopy(original)]}
    a, b = binding["label_span"]
    for lo, hi in ((0, a), (b, len(original["text"]))):
        if hi > lo:
            result["controls"].append({"text": original["text"][lo:hi],
                "source": _source(original["source"], lo, hi), "reason": "explicit_attribution_parent_syntax"})


def read_series_context(text: str, source: dict[str, Any], *, scope: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """Read only explicit declaration clauses, with property-specific units."""
    result = _result()
    result.update(qualifiers={}, qualifier_sources={}, attribute_units={}, unit_exceptions=[],
                  comparison_periods={}, scope=list(scope), source=copy.deepcopy(source))
    marker = re.search(r"(?:单位|單位|Units?|币种|幣種|Currency|期间|期間|Period|本年|上年)\s*[:：]", text, re.I)
    if not marker:
        return result
    result["matched"] = True
    for start, end in _parts(text):
        fragment = text[start:end]
        basis = _BASIS.match(fragment)
        if basis:
            result["qualifiers"]["period_basis"] = basis[0]
            result["qualifier_sources"]["period_basis"] = _source(source, start, start + basis.end())
            _atom(result, text, source, start, start + basis.end(), "period_basis")
            start += basis.end()
            while start < end and text[start] in " ，,":
                start += 1
            if start == end:
                continue
            fragment = text[start:end]
        year_prefix = re.match(rf"({_YEAR_TEXT})\s*[，,]\s*", fragment)
        if year_prefix:
            result["qualifiers"]["period"] = year_prefix[1]
            result["qualifier_sources"]["period"] = _source(source, start, start + year_prefix.end(1))
            _atom(result, text, source, start, start + year_prefix.end(1), "period")
            start += year_prefix.end()
            fragment = text[start:end]
        pair = _PAIR.fullmatch(fragment)
        if pair and re.fullmatch(r"币种|幣種|Currency", pair[1].strip(), re.I) and _CURRENCY.fullmatch(pair[2].strip()):
            result["qualifiers"]["currency"] = pair[2].strip()
            result["qualifier_sources"]["currency"] = _source(source, start + pair.start(2), start + pair.end(2))
            _atom(result, text, source, start + pair.start(2), start + pair.end(2), "currency")
            _control(result, text, source, start + pair.start(1), start + pair.start(2), "explicit_currency_declaration_key")
            continue
        if pair and re.fullmatch(r"期间|期間|Period", pair[1].strip(), re.I) and _YEAR.fullmatch(pair[2].strip()):
            result["qualifiers"]["period"] = pair[2].strip()
            result["qualifier_sources"]["period"] = _source(source, start + pair.start(2), start + pair.end(2))
            _atom(result, text, source, start + pair.start(2), start + pair.end(2), "period")
            _control(result, text, source, start + pair.start(1), start + pair.start(2), "explicit_period_declaration_key")
            continue
        if pair and pair[1].strip() in {"本年", "上年"} and _YEAR.fullmatch(pair[2].strip()):
            key, value = pair[1].strip(), pair[2].strip()
            result["comparison_periods"]["to_period" if key == "本年" else "from_period"] = {
                "value": value, "source": _source(source, start + pair.start(2), start + pair.end(2))}
            _atom(result, text, source, start + pair.start(2), start + pair.end(2), "period")
            _control(result, text, source, start + pair.start(1), start + pair.start(2), "explicit_comparison_period_label")
            continue
        declaration = re.fullmatch(r"(?P<label>.*?)(?:单位|單位|Units?)\s*[:：]\s*(?P<unit>[^()（）]+?)(?:[（(](?P<exception>[^()（）]+?)(?:另列)[)）])?", fragment, re.I)
        if declaration is None or not read_unit_token(declaration["unit"].strip())["matched"]:
            _block(result, "series_context_declaration_unsupported", text, source, start, end)
            continue
        label, unit = declaration["label"].strip(), declaration["unit"].strip()
        unit_start, unit_end = start + declaration.start("unit"), start + declaration.end("unit")
        unit_start, unit_end = _trim(text, unit_start, unit_end)
        unit_source = _source(source, unit_start, unit_end)
        _atom(result, text, source, unit_start, unit_end, "unit")
        _control(result, text, source, start, start + declaration.start("unit"), "explicit_unit_declaration_key")
        if label in {"", "金额", "金額", "Amount"}:
            result["qualifiers"]["unit"] = unit
            result["qualifier_sources"]["unit"] = unit_source
            printed_unit = read_unit_token(unit, unit_source)
            if printed_unit["currency"]:
                result["qualifiers"]["currency"] = printed_unit["currency"]
                result["qualifier_sources"]["currency"] = printed_unit["sources"]["currency"]
        else:
            result["attribute_units"][label] = {"unit": unit, "source": unit_source}
        if declaration["exception"]:
            exception_start, exception_end = start + declaration.start("exception"), start + declaration.end("exception")
            result["unit_exceptions"].append({"attribute": declaration["exception"].strip(), "source": _source(source, exception_start, exception_end)})
            _atom(result, text, source, exception_start, exception_end, "unit_scope_exception")
            _control(result, text, source, exception_end, start + declaration.end() - 1, "explicit_unit_scope_exception_marker")
    _project(result, text, source)
    return result


def _read_scalar(text: str, source: dict[str, Any], start: int, end: int, result: dict[str, Any],
                 q: dict[str, Any], sources: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    start, end = _trim(text, start, end)
    payload = text[start:end]
    if "、" in payload or _NONANNUAL.match(payload):
        _block(result, "series_value_roles_unsupported", text, source, start, end)
        return None
    if re.search(r"約|约|[=×÷]|\bper\b", payload, re.I):
        _block(result, "series_compound_measurement_unsupported", text, source, start, end)
        return None
    printed = read_measurement_literal(payload, _source(source, start, end))
    if not printed["matched"] and payload.endswith("."):
        without_terminator = read_measurement_literal(payload[:-1], _source(source, start, end - 1))
        if without_terminator["matched"]:
            printed = without_terminator
            end -= 1
            payload = text[start:end]
    if not printed["matched"] and (missing := re.fullmatch(r"([—–-])\s*(.*)", payload)):
        unit = read_unit_token(missing[2], _source(source, start + missing.start(2), end))
        if not missing[2].strip() or unit["matched"]:
            printed.update(matched=True, value=missing[1], value_span=[0, 1], unit=unit["unit"], currency=unit["currency"])
            printed["unit_span"] = [missing.start(2) + a for a in unit["unit_span"]] if unit["unit_span"] else None
            printed["sources"].update(unit["sources"])
    if not printed["matched"]:
        _block(result, "series_scalar_syntax_unsupported", text, source, start, end)
        return None
    q, sources = copy.deepcopy(q), copy.deepcopy(sources)
    value_start, value_end = [start + a for a in printed["value_span"]]
    value_start, value_end = _trim(text, value_start, value_end)
    value = text[value_start:value_end]
    _atom(result, text, source, value_start, value_end, "value")
    if printed["unit"]:
        unit_start, unit_end = [start + a for a in printed["unit_span"]]
        unit = printed["unit"]
        q["unit"], sources["unit"] = unit, copy.deepcopy(printed["sources"]["unit"])
        _atom(result, text, source, unit_start, unit_end, "unit")
        if printed["currency"]:
            q["currency"] = printed["currency"]
            sources["currency"] = copy.deepcopy(printed["sources"]["currency"])
        elif (unit.endswith("股") or unit in {"%", "‰", "人", "吨", "噸", "件", "天", "次", "户", "戶"}
              or normalize_unit(unit)["dimension"] == "ratio_delta"):
            q.pop("currency", None)
            sources.pop("currency", None)
    return value, q, sources, {"value_source": _source(source, value_start, value_end),
                              "raw_source": _source(source, start, end), "raw_value": text[start:end]}


def _read_growth_scalar(text: str, source: dict[str, Any], start: int, end: int, result: dict[str, Any],
                        q: dict[str, Any], sources: dict[str, Any]
                        ) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    """Keep a printed ratio-change direction separate from unsigned magnitude.

    This finite form does not turn a direction into a numeric sign, infer a
    unit from the annual values, or resolve comparison years. A named shared
    unit is usable only with its own actual source declaration.
    """
    start, end = _trim(text, start, end)
    direction = _DIRECTED_CHANGE.match(text, start, end)
    if direction is None:
        return _read_scalar(text, source, start, end, result, q, sources)
    magnitude_start = direction.end()
    while magnitude_start < end and text[magnitude_start].isspace():
        magnitude_start += 1
    payload = text[magnitude_start:end]
    printed = read_measurement_literal(payload, _source(source, magnitude_start, end))
    if not printed["matched"] and payload.endswith("."):
        printed = read_measurement_literal(payload[:-1], _source(source, magnitude_start, end - 1))
    if not printed["matched"] or _UNSIGNED_MAGNITUDE.fullmatch(printed["value"]) is None:
        _block(result, "series_directed_change_magnitude_unsupported", text, source, start, end)
        return None
    unit = printed["unit"] or q.get("unit")
    unit_source = printed["sources"].get("unit") if printed["unit"] else sources.get("unit")
    if (not unit or normalize_unit(unit)["dimension"] not in {"ratio", "ratio_delta"}
            or not isinstance(unit_source, dict) or not unit_source.get("path")):
        _block(result, "series_directed_change_ratio_unit_unresolved", text, source, start, end)
        return None
    parsed = _read_scalar(text, source, magnitude_start, end, result, q, sources)
    if parsed:
        parsed[1]["change_direction"] = _CHANGE_DIRECTIONS[direction[0]]
        parsed[2]["change_direction"] = _source(source, direction.start(), direction.end())
        _atom(result, text, source, direction.start(), direction.end(), "change_direction")
        # Preserve the complete printed payload while retaining an exact,
        # separate source span for the unsigned numeric token itself.
        raw_end = magnitude_start + len(parsed[3]["raw_value"])
        parsed[3]["raw_source"] = _source(source, start, raw_end)
        parsed[3]["raw_value"] = text[start:raw_end]
    return parsed


def read_series_requirements(text: str, source: dict[str, Any], *, context: dict[str, Any] | None = None,
                              subject: str = "", attribute: str | None = None,
                              subject_source: dict[str, Any] | None = None,
                              attribute_source: dict[str, Any] | None = None,
                              parents: tuple[str, ...] | list[str] = (), qualifiers: dict[str, Any] | None = None,
                              parent_declarations: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
                              qualifier_sources: dict[str, Any] | None = None,
                              identity_facets: dict[str, Any] | None = None,
                              scope: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """Read explicit period scalars; never infer roles from multiple values."""
    result = _result()
    record_subject = subject
    fact_facets = copy.deepcopy(identity_facets or {})
    result["scope"] = {"subject": subject, "attribute": attribute, "identity_facets": copy.deepcopy(identity_facets or {}), "scope": list(scope)}
    pair = _PAIR.fullmatch(text.strip())
    if (pair and _ordinary_field(pair[1])) or (attribute and _ordinary_field(attribute)):
        return result
    body_start = 0
    main_attribute_source = copy.deepcopy(attribute_source)
    field_unit, field_unit_source = None, None
    if (pair and not re.search(r"[。！？!?《》“”「」]", pair[1])
            and (_annual_scalar_start(pair[2].strip()) or _NONANNUAL.match(pair[2].strip()))):
        attribute = pair[1].strip()
        # Locate the match in the unstripped original input for exact spans.
        outer = _PAIR.fullmatch(text)
        body_start = outer.start(2)
        label = outer[1]
        declared = read_measurement_label(label, _source(source, outer.start(1), outer.end(1)))
        if not declared["matched"]:
            suffix = re.fullmatch(r"(?P<label>.+?)\s+/\s+(?P<unit>[^/]+?)\s*", label)
            if suffix:
                unit_source = _source(source, outer.start(1) + suffix.start("unit"), outer.start(1) + suffix.end("unit"))
                unit = read_unit_token(suffix["unit"], unit_source)
                if unit["matched"]:
                    declared = {"matched": True, "label": suffix["label"], "unit": unit["unit"],
                        "label_span": [suffix.start("label"), suffix.end("label")],
                        "unit_span": [suffix.start("unit"), suffix.end("unit")],
                        "sources": {"label": _source(source, outer.start(1) + suffix.start("label"), outer.start(1) + suffix.end("label")),
                                    "unit": copy.deepcopy(unit["sources"]["unit"])}}
                    _control(result, text, source, outer.start(1) + suffix.end("label"), outer.start(1) + suffix.start("unit"),
                             "explicit_unit_suffix_separator")
        if declared["matched"]:
            attribute, field_unit = declared["label"], declared["unit"]
            main_attribute_source = copy.deepcopy(declared["sources"]["label"])
            _atom(result, text, source, *[outer.start(1) + a for a in declared["label_span"]], "label")
            _atom(result, text, source, *[outer.start(1) + a for a in declared["unit_span"]], "unit")
            field_unit_source = copy.deepcopy(declared["sources"]["unit"])
        else:
            main_attribute_source = _source(source, outer.start(1), outer.end(1))
            _atom(result, text, source, outer.start(1), outer.end(1), "label")
    parts = _parts(text, body_start)
    if not parts or not (_annual_scalar_start(text[parts[0][0]:parts[0][1]]) or _NONANNUAL.match(text[parts[0][0]:parts[0][1]])):
        return _result()
    result["matched"] = True
    attribution = _attribution_parent(parents, parent_declarations)
    if attribution:
        issue = attribution.get("reason")
        if issue or main_attribute_source is None or pair is None:
            result["text_atoms"], result["controls"] = [], []
            _block(result, issue or "series_attribution_recipient_source_unavailable", text, source, 0, len(text),
                   layers=["B", "L"], attribution=copy.deepcopy(attribution))
            _project(result, text, source)
            return result
        child = {"text": attribute, "source": copy.deepcopy(main_attribute_source)}
        attribution["child"] = child
        for atom in result["text_atoms"]:
            if atom["role"] == "label" and atom["source"] == main_attribute_source:
                atom["role"] = "locator"
        subject, attribute = child["text"], attribution["parent"]["text"]
        main_attribute_source = copy.deepcopy(attribution["parent"]["source"])
        result["scope"]["subject"] = subject
        if record_subject:
            proved = isinstance(subject_source, dict) and subject_source.get("path") and subject_source.get("location") != "declared_parent_text"
            conflict = "record_subject" in fact_facets and fact_facets["record_subject"] != record_subject
            if not proved or conflict:
                issue = {"reason": "series_attribution_record_scope_conflict" if conflict else "series_attribution_record_subject_source_unavailable",
                         "kind": "record_subject_scope", "text": text, "source": copy.deepcopy(source),
                         "layers": ["B", "L"], "record_subject": record_subject,
                         "subject_source": copy.deepcopy(subject_source), "identity_facets": copy.deepcopy(fact_facets)}
                result["pending_requirements"].append(issue)
                result["blockers"].append(copy.deepcopy(issue))
                fact_facets.pop("record_subject", None)
            else:
                fact_facets["record_subject"] = record_subject
                attribution["record_evidence"] = {"record_subject": {"text": record_subject, "source": copy.deepcopy(subject_source)},
                                                  "recipient": copy.deepcopy(child)}
    if (_NONANNUAL.match(text[parts[0][0]:parts[0][1]])
            and _period_position(text[parts[0][0]:parts[0][1]], {}) is None):
        _block(result, "series_nonannual_period_unsupported", text, source, body_start, len(text))
        _project(result, text, source)
        return result
    context = copy.deepcopy(context or {})
    inherited = {**context.get("qualifiers", {}), **(qualifiers or {})}
    inherited_sources = {**context.get("qualifier_sources", {}), **(qualifier_sources or {})}
    if context.get("scope") and list(context["scope"]) != list(scope):
        result["blockers"].append({"reason": "series_context_scope_conflict", "source": copy.deepcopy(source), "layers": ["B"],
                                   "required_context_scope": context["scope"], "actual_scope": list(scope)})
        inherited, inherited_sources = dict(qualifiers or {}), dict(qualifier_sources or {})
        context = {}
    if attribute is None:
        typed = [re.fullmatch(r"(?:Metric|指标|指標)\s*[:：]\s*(.+)", parent, re.I) for parent in parents if isinstance(parent, str)]
        attribute = next((match[1].strip() for match in reversed(typed) if match), None)
    for exception in context.get("unit_exceptions", []):
        if attribute == exception["attribute"]:
            for key in ("unit", "currency"):
                inherited.pop(key, None)
                inherited_sources.pop(key, None)
    if field_unit:
        inherited["unit"], inherited_sources["unit"] = field_unit, field_unit_source
        printed_unit = read_unit_token(field_unit, field_unit_source)
        if printed_unit["currency"]:
            inherited["currency"] = printed_unit["currency"]
            inherited_sources["currency"] = printed_unit["sources"]["currency"]
        elif (field_unit.endswith("股") or field_unit in {"%", "‰", "人", "吨", "噸", "件", "天", "次", "户", "戶"}
              or normalize_unit(field_unit)["dimension"] == "ratio_delta"):
            inherited.pop("currency", None)
            inherited_sources.pop("currency", None)
    if not attribute:
        for start, end in parts:
            _block(result, "series_attribute_unavailable", text, source, start, end)
        _project(result, text, source)
        return result
    result["scope"]["attribute"] = attribute
    for start, end in parts:
        fragment = text[start:end]
        position = _period_position(fragment, _source(source, start, end))
        q, sources = copy.deepcopy(inherited), copy.deepcopy(inherited_sources)
        field_subject, field_attribute, role = subject, attribute, "identity" if _IDENTITY.fullmatch(attribute) else "metric"
        field_attribute_source = copy.deepcopy(main_attribute_source)
        if position:
            if not position["valid"]:
                _block(result, "series_period_selector_unresolved", text, source, start, end,
                       layers=["B", "L"], selector=copy.deepcopy(position))
                continue
            q["period"] = position["text"]
            sources["period"] = copy.deepcopy(position["source"])
            _atom(result, text, source, start, start + position["end"], "period")
            value_start = start + position["end"]
            while value_start < end and text[value_start] in " :：，,":
                value_start += 1
            if role == "identity":
                q.pop("unit", None)
                q.pop("currency", None)
                sources.pop("unit", None)
                sources.pop("currency", None)
                value_start, value_end = _trim(text, value_start, end)
                _atom(result, text, source, value_start, value_end, "value")
                parsed = text[value_start:value_end], q, sources, {
                    "value_source": _source(source, value_start, value_end), "raw_source": _source(source, value_start, value_end),
                    "raw_value": text[value_start:value_end]}
            else:
                parsed = _read_scalar(text, source, value_start, end, result, q, sources)
        else:
            if attribution:
                _block(result, "series_attribution_additional_field_unresolved", text, source, start, end,
                       layers=["B", "L"], attribution=copy.deepcopy(attribution))
                continue
            extra = _PAIR.fullmatch(fragment)
            growth = _GROWTH.match(fragment)
            if extra:
                field_attribute = extra[1].strip()
                label_start = start + extra.start(1)
                value_start = start + extra.start(2)
                label_end = start + extra.end(1)
            elif growth:
                field_attribute = growth[0]
                label_start = start + growth.start()
                value_start = start + growth.end()
                while value_start < end and text[value_start] in " :：":
                    value_start += 1
                label_end = start + growth.end()
            else:
                _block(result, "series_independent_field_role_unsupported", text, source, start, end)
                continue
            field_subject = attribute
            field_attribute_source = _source(source, label_start, label_end)
            _atom(result, text, source, start, label_end, "label")
            for key in ("unit", "currency"):
                q.pop(key, None)
                sources.pop(key, None)
            if not _CAUSE.fullmatch(field_attribute):
                q.pop("period", None)
                sources.pop("period", None)
            named_unit = context.get("attribute_units", {}).get(field_attribute)
            if named_unit:
                q["unit"], sources["unit"] = named_unit["unit"], copy.deepcopy(named_unit["source"])
            if _CAUSE.fullmatch(field_attribute):
                role = "description"
                value_start, value_end = _trim(text, value_start, end)
                _atom(result, text, source, value_start, value_end, "value")
                parsed = text[value_start:value_end], q, sources, {
                    "value_source": _source(source, value_start, value_end), "raw_source": _source(source, value_start, value_end),
                    "raw_value": text[value_start:value_end]}
            elif _GROWTH.fullmatch(field_attribute):
                parsed = _read_growth_scalar(text, source, value_start, end, result, q, sources)
                comparison = context.get("comparison_periods", {})
                if {"from_period", "to_period"} <= comparison.keys():
                    if parsed:
                        for key in ("from_period", "to_period"):
                            parsed[1][key], parsed[2][key] = comparison[key]["value"], copy.deepcopy(comparison[key]["source"])
                else:
                    if parsed and field_attribute.startswith(("本年比上年", "較上年同期", "较上年同期")):
                        basis = re.match(r"本年比上年|較上年同期|较上年同期", field_attribute)
                        parsed[1]["comparison_basis"] = basis[0]
                        parsed[2]["comparison_basis"] = _source(source, label_start + basis.start(), label_start + basis.end())
                    result["blockers"].append({"reason": "series_comparison_periods_unresolved", "source": _source(source, start, end), "layers": ["B"]})
                    result["pending_requirements"].append({"role": "comparison_period_binding", "attribute": field_attribute,
                                                           "text": fragment, "source": _source(source, start, end)})
            else:
                _block(result, "series_independent_field_role_unsupported", text, source, start, end)
                continue
        if parsed:
            value, q, sources, scalar = parsed
            field_sources = {"attribute_source": copy.deepcopy(field_attribute_source)} if field_attribute_source is not None else {}
            result["facts"].append({"subject": field_subject, "attribute": field_attribute, "value": value, "role": role,
                "qualifiers": q, "identity_facets": copy.deepcopy(fact_facets), "scope": list(scope),
                "source": {**scalar["raw_source"], "qualifier_sources": copy.deepcopy(sources), **field_sources},
                "raw_value": scalar["raw_value"], "value_source": scalar["value_source"],
                "qualifier_sources": copy.deepcopy(sources), **field_sources})
            if position:
                result["facts"][-1]["role_basis"] = {"period_selector": {key: copy.deepcopy(position[key])
                    for key in ("kind", "text", "source")}}
            if attribution:
                fact = result["facts"][-1]
                fact["subject_source"] = copy.deepcopy(attribution["child"]["source"])
                fact.setdefault("role_basis", {})["attribution"] = {"rule_id": attribution["rule_id"],
                    "parent": copy.deepcopy(attribution["parent"]), "child": copy.deepcopy(attribution["child"])}
                if attribution.get("record_evidence"):
                    fact["record_evidence"] = copy.deepcopy(attribution["record_evidence"])
    _project(result, text, source)
    if attribution:
        _attribution_projection(result, text, source, attribution)
    return result
