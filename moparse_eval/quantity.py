"""Exact comparison views for independently printed quantities and units.

This module never changes source text, supplies a missing unit, exchanges
currencies, rounds a value, or calculates a value missing from the input.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

_SCALES = {"": 1, "十": 10, "百": 100, "千": 1000, "万": 10000, "萬": 10000,
           "百万": 1000000, "百萬": 1000000, "千万": 10000000, "千萬": 10000000,
           "亿": 100000000, "億": 100000000, "十亿": 1000000000, "十億": 1000000000,
           "百亿": 10000000000, "百億": 10000000000, "万亿": 1000000000000, "萬億": 1000000000000,
           "thousand": 1000, "thousands": 1000, "million": 1000000, "millions": 1000000,
           "billion": 1000000000, "billions": 1000000000}
_MONEY_SHORT_SCALES = {"k": 1000, "m": 1000000, "mn": 1000000, "bn": 1000000000}
_CURRENCIES = {"人民币": "CNY", "人民幣": "CNY", "rmb": "CNY", "cny": "CNY",
               "美元": "USD", "usd": "USD", "港元": "HKD", "港币": "HKD", "港幣": "HKD", "hkd": "HKD",
               "欧元": "EUR", "歐元": "EUR", "eur": "EUR", "日元": "JPY", "jpy": "JPY",
               "英镑": "GBP", "英鎊": "GBP", "gbp": "GBP", "澳元": "AUD", "aud": "AUD",
               "加元": "CAD", "cad": "CAD", "新加坡元": "SGD", "sgd": "SGD"}
_COUNTS = {"人": "people", "person": "people", "persons": "people", "people": "people",
           "employees": "people", "股": "shares", "share": "shares", "shares": "shares",
           "件": "items", "个": "items", "個": "items", "item": "items", "items": "items",
           "户": "households", "戶": "households", "台": "machines", "次": "occurrences"}
_NUMBER = re.compile(r"[+\-−]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)")


def _text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def canonical_currency(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    text = _text(value)
    return _CURRENCIES.get(text.casefold(), text)


def exact_number(value: Any) -> Fraction | None:
    if not isinstance(value, str):
        return None
    text = _text(value)
    negative = text.startswith("(") and text.endswith(")")
    payload = text[1:-1].strip() if negative else text
    if _NUMBER.fullmatch(payload) is None:
        return None
    try:
        number = Fraction(Decimal(payload.replace(",", "").replace("−", "-")))
    except (InvalidOperation, ValueError):
        return None
    return -number if negative else number


def ratio(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def normalize_unit(raw_unit: str | None, currency: str | None = None,
                   quantity_role: str | None = None) -> dict[str, Any]:
    explicit_currency = canonical_currency(currency)
    raw = raw_unit
    text = _text(raw_unit) if isinstance(raw_unit, str) else ""
    role = quantity_role
    result = {"matched": False, "raw": raw, "dimension": None, "family": None,
              "currency": explicit_currency, "quantity_role": role, "scale": None, "conflicts": []}

    def finish(dimension, family, scale, own_currency=None, own_role="level"):
        if own_currency and explicit_currency and own_currency != explicit_currency:
            result["conflicts"].append("printed_currency_conflicts_with_explicit_currency")
            return result
        result.update(matched=True, dimension=dimension, family=family,
                      currency=own_currency or explicit_currency, quantity_role=role or own_role,
                      scale=ratio(Fraction(scale)))
        return result

    if not text:
        return finish("dimensionless", "scalar", 1, own_role="scalar")
    folded = text.casefold()
    if folded in {"%", "‰", "percent", "percentage"}:
        if role in {"absolute_ratio_change", "percentage_points", "basis_points"}:
            result["conflicts"].append("ratio_literal_is_not_a_percentage_point_literal")
            return result
        return finish("ratio", "ratio", Fraction(1, 1000 if text == "‰" else 100), own_role="ratio")
    if folded in {"百分点", "百分點", "pp", "percentage point", "percentage points"}:
        if role not in {None, "absolute_ratio_change"}:
            result["conflicts"].append("percentage_point_role_conflict")
            return result
        return finish("ratio_delta", "ratio_delta", Fraction(1, 100), own_role="absolute_ratio_change")
    if folded in {"bp", "bps", "basis point", "basis points", "基点", "基點"}:
        if role not in {None, "absolute_ratio_change"}:
            result["conflicts"].append("basis_point_role_conflict")
            return result
        return finish("ratio_delta", "ratio_delta", Fraction(1, 10000), own_role="absolute_ratio_change")
    if "/" in text:
        parts = re.split(r"\s*/\s*", text)
        if len(parts) == 2 and parts[1].casefold() in _COUNTS:
            numerator = normalize_unit(parts[0], currency, quantity_role)
            if numerator["matched"] and numerator["dimension"] == "money":
                numerator.update(raw=raw, dimension="money_per_" + _COUNTS[parts[1].casefold()],
                                 family=numerator["family"] + "/" + _COUNTS[parts[1].casefold()])
                return numerator
        return result
    for literal in sorted(_CURRENCIES, key=len, reverse=True):
        own_currency, remaining = _CURRENCIES[literal], None
        if folded.startswith(literal):
            remaining = text[len(literal):].strip()
        elif folded.endswith(literal):
            remaining = text[:-len(literal)].strip()
        if remaining is not None:
            scale_name = remaining[:-1] if remaining.endswith("元") else remaining.casefold()
            if scale_name in _SCALES or scale_name in _MONEY_SHORT_SCALES:
                return finish("money", "currency", {**_SCALES, **_MONEY_SHORT_SCALES}[scale_name], own_currency)
    for symbol in ("$", "¥", "￥", "€", "£"):
        scales = {**_SCALES, **_MONEY_SHORT_SCALES}
        if text.startswith(symbol) and text[len(symbol):].strip().casefold() in scales:
            return finish("money", "symbol:" + symbol, scales[text[len(symbol):].strip().casefold()])
    if text.endswith("元") and text[:-1] in _SCALES:
        return finish("money", "currency" if explicit_currency else "yuan_unspecified", _SCALES[text[:-1]])
    for literal, family in sorted(_COUNTS.items(), key=lambda pair: len(pair[0]), reverse=True):
        if folded.endswith(literal) and (scale_name := text[:-len(literal)].strip().casefold()) in _SCALES:
            return finish("count", family, _SCALES[scale_name])
    if folded in _SCALES and folded:
        return finish("scalar", "scalar", _SCALES[folded])
    return result


def unit_key(unit: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(unit[key] for key in ("dimension", "family", "currency", "quantity_role"))


def normalize_quantity(item: dict[str, Any]) -> dict[str, Any]:
    unit = normalize_unit(item.get("unit"), item.get("currency"), item.get("quantity_role"))
    number = exact_number(item.get("value"))
    result = {"matched": bool(unit["matched"] and number is not None), "unit": unit,
              "value": None, "conflicts": list(unit["conflicts"])}
    if number is None:
        result["conflicts"].append("not_an_exact_printed_number")
    if result["matched"]:
        factor = Fraction(unit["scale"]["numerator"], unit["scale"]["denominator"])
        result["value"] = ratio(number * factor)
    return result
