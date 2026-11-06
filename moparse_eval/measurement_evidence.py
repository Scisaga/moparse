"""Read bounded printed quantities and unit declarations without conversion.

The finite grammar preserves spelling, signs, magnitude words and currency
evidence from this input alone. Unknown syntax has no partial numeric answer.
"""

from __future__ import annotations

import copy
import re
from typing import Any

_CURRENCY_TEXT = (r"人民币|人民幣|美元|港元|港币|港幣|欧元|歐元|日元|英镑|英鎊|澳元|加元|新加坡元"
                  r"|USD|RMB|CNY|HKD|EUR|JPY|GBP|AUD|CAD|SGD")
_CURRENCY = re.compile(_CURRENCY_TEXT, re.I)
_SYMBOL_TEXT = r"[$¥￥€£]"
_SCALE = r"(?:十|百|千|万|萬|百万|百萬|千万|千萬|亿|億|十亿|十億|百亿|百億|万亿|萬億)"
_ENGLISH_SCALE = r"(?:thousands?|millions?|billions?)"
_MONEY_SHORT_SCALE = r"(?:mn|bn|k|m)"
_MONEY_SCALE = rf"(?:{_ENGLISH_SCALE}|{_MONEY_SHORT_SCALE})"
_COUNT = r"(?:股|人|件|吨|噸|户|戶|台|项|項|个|個|天|次|小时|小時|公里)"
_MONEY = rf"(?:(?:{_CURRENCY_TEXT})\s*(?:{_SCALE}?元|{_MONEY_SCALE})?|{_SCALE}?元(?:\s*(?:{_CURRENCY_TEXT}))?|{_MONEY_SHORT_SCALE}\s*(?:{_CURRENCY_TEXT})|{_SYMBOL_TEXT}(?:\s*{_MONEY_SCALE})?)"
_RATIO_DELTA = r"(?:[个個]?百分点|[个個]?百分點|pp|percentage\s+points?|bps?|basis\s+points?|基点|基點)"
_UNIT = re.compile(rf"(?:{_MONEY}(?:\s*/\s*{_COUNT})?|{_SCALE}?{_COUNT}|[%‰]|{_RATIO_DELTA})", re.I)
_MAGNITUDE = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+"
_NUMBER = re.compile(rf"(?:\([+\-−]?(?:{_MAGNITUDE})\)|（[+\-−]?(?:{_MAGNITUDE})）|[+\-−]?(?:{_MAGNITUDE}))")


def _empty(text: str, source: dict[str, Any] | None, reason: str) -> dict[str, Any]:
    return {"matched": False, "raw": text, "source": copy.deepcopy(source or {}), "reason": reason,
            "value": None, "value_span": None, "label": text, "label_span": None,
            "unit": None, "unit_span": None, "currency": None, "currency_span": None,
            "currency_symbol": None, "currency_symbol_span": None, "sources": {}, "controls": []}


def _bounds(text: str) -> tuple[int, int]:
    return len(text) - len(text.lstrip()), len(text.rstrip())


def _source(source: dict[str, Any] | None, start: int, end: int) -> dict[str, Any]:
    result = copy.deepcopy(source or {})
    span = result.get("text_span")
    offset = span[0] if isinstance(span, (list, tuple)) and len(span) == 2 and type(span[0]) is int else 0
    result["text_span"] = [offset + start, offset + end]
    return result


def _shift(unit: dict[str, Any], offset: int, source: dict[str, Any] | None) -> dict[str, Any]:
    result = copy.deepcopy(unit)
    for role in ("unit", "currency", "currency_symbol"):
        if result.get(role + "_span") is not None:
            a, b = result[role + "_span"]
            result[role + "_span"] = [offset + a, offset + b]
            result["sources"][role] = _source(source, offset + a, offset + b)
    return result


def read_unit_token(text: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read a whole unit token. A quantity such as ``17%`` is not a unit."""
    result = _empty(text, source, "not_a_complete_printed_unit")
    start, end = _bounds(text)
    token = text[start:end]
    if not token or _UNIT.fullmatch(token) is None:
        return result
    result.update(matched=True, reason=None, unit=token, unit_span=[start, end])
    result["sources"]["unit"] = _source(source, start, end)
    currency = _CURRENCY.search(token)
    if currency:
        result["currency"] = currency[0]
        result["currency_span"] = [start + currency.start(), start + currency.end()]
        result["sources"]["currency"] = _source(source, *result["currency_span"])
    symbol = re.search(_SYMBOL_TEXT, token)
    if symbol:
        result["currency_symbol"] = symbol[0]
        result["currency_symbol_span"] = [start + symbol.start(), start + symbol.end()]
        result["sources"]["currency_symbol"] = _source(source, *result["currency_symbol_span"])
    return result


def read_measurement_literal(text: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read one complete numeric literal and its own optional unit token.

    No arithmetic, default currency, expected context or amount equivalence is
    applied. A prefix and suffix with two units stay unsupported.
    """
    result = _empty(text, source, "not_a_complete_printed_measurement")
    start, end = _bounds(text)
    payload = text[start:end]
    number = _NUMBER.match(payload)
    unit = None
    if number:
        suffix = payload[number.end():]
        if suffix.strip():
            parsed = read_unit_token(suffix)
            if not parsed["matched"]:
                return result
            unit = _shift(parsed, start + number.end(), source)
        value_start, value_end = start + number.start(), start + number.end()
    else:
        number = _NUMBER.search(payload)
        if number is None or payload[number.end():].strip():
            return result
        prefix = read_unit_token(payload[:number.start()])
        if not prefix["matched"] or not (prefix["currency"] or prefix["currency_symbol"]):
            return result
        unit = _shift(prefix, start, source)
        value_start, value_end = start + number.start(), start + number.end()
    result.update(matched=True, reason=None, value=text[value_start:value_end], value_span=[value_start, value_end])
    result["sources"]["value"] = _source(source, value_start, value_end)
    if unit:
        for role in ("unit", "currency", "currency_symbol"):
            result[role], result[role + "_span"] = unit[role], unit[role + "_span"]
        result["sources"].update(copy.deepcopy(unit["sources"]))
    owned = [result["value_span"], *([result["unit_span"]] if result["unit_span"] else [])]
    cursor = 0
    for a, b in sorted(owned):
        if cursor < a:
            result["controls"].append({"text": text[cursor:a], "span": [cursor, a],
                                       "source": _source(source, cursor, a), "reason": "measurement_whitespace"})
        cursor = b
    if cursor < len(text):
        result["controls"].append({"text": text[cursor:], "span": [cursor, len(text)],
                                   "source": _source(source, cursor, len(text)), "reason": "measurement_whitespace"})
    return result


def read_measurement_label(text: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Split a terminal parenthesized whole unit, preserving all other labels."""
    result = _empty(text, source, "no_terminal_unit_only_declaration")
    match = re.fullmatch(r"(?P<label>.+?)(?P<open>[（(])(?P<unit>[^()（）]+)(?P<close>[）)])\s*", text)
    if match is None or {"(": ")", "（": "）"}[match["open"]] != match["close"]:
        return result
    unit = read_unit_token(match["unit"])
    if not unit["matched"]:
        return result
    label_start = len(match["label"]) - len(match["label"].lstrip())
    label_end = len(match["label"].rstrip())
    if label_start == label_end:
        return result
    unit = _shift(unit, match.start("unit"), source)
    result.update(matched=True, reason=None, label=text[label_start:label_end], label_span=[label_start, label_end])
    result["sources"]["label"] = _source(source, label_start, label_end)
    for role in ("unit", "currency", "currency_symbol"):
        result[role], result[role + "_span"] = unit[role], unit[role + "_span"]
    result["sources"].update(copy.deepcopy(unit["sources"]))
    for a, b in [(0, label_start), (label_end, result["unit_span"][0]), (result["unit_span"][1], len(text))]:
        if a < b:
            result["controls"].append({"text": text[a:b], "span": [a, b], "source": _source(source, a, b),
                                       "reason": "explicit_parenthesized_unit_syntax"})
    return result
