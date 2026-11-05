"""Complete printed calendar dates and period-end selectors, without inference."""

from __future__ import annotations

import copy
import re
from datetime import date
from typing import Any

from .measurement_evidence import read_unit_token

_MONTHS = "January February March April May June July August September October November December".split()
_MONTH = {name.lower(): index for index, name in enumerate(_MONTHS, 1)}
_MONTH.update({name[:3].lower(): index for index, name in enumerate(_MONTHS, 1)})
_MONTH_PATTERN = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
                  r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_ZH_DIGITS = "零〇一二三四五六七八九"
_ZH_NUMBER = rf"[\d{_ZH_DIGITS}十]+"
DATE_PATTERN = (rf"(?:{_MONTH_PATTERN}\s+\d{{1,2}},?\s+(?:19|20)\d{{2}}"
                rf"|\d{{1,2}}\s*{_MONTH_PATTERN}\s*(?:19|20)\d{{2}}"
                rf"|(?:19|20)\d{{2}}-\d{{1,2}}-\d{{1,2}}|{_ZH_NUMBER}年{_ZH_NUMBER}月{_ZH_NUMBER}日)")
_DATE = re.compile(DATE_PATTERN, re.I)
_BASIS = re.compile(r"(?:(?:for\s+)?(?:the\s+)?)?(?:(?:fiscal\s+)?"
                    r"(?:(?:one|two|three|four|six|nine|twelve|\d+)\s+)?"
                    r"(?:years?|periods?|quarters?|months?|weeks?)\s+ended)\b|As\s+(?:of|at)\b|At\b|截至|截止|於|于", re.I)
_ZH_BASIS = re.compile(rf"止(?:[個个]?年度|(?:財政|财政)年度|{_ZH_NUMBER}[個个]?月|半年)")


def _source(source, a, b):
    offset = source.get("text_span", [0])[0]
    return {**copy.deepcopy(source), "text_span": [offset + a, offset + b]}


def calendar_date(literal: str) -> str | None:
    text = literal.strip()
    english = re.fullmatch(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+((?:19|20)\d{2})", text)
    numeric = re.fullmatch(r"((?:19|20)\d{2})(?:-|年)(\d{1,2})(?:-|月)(\d{1,2})日?", text)
    day_first = re.fullmatch(r"(\d{1,2})\s*([A-Za-z]+)\.?\s*((?:19|20)\d{2})", text)
    chinese = re.fullmatch(rf"({_ZH_NUMBER})年({_ZH_NUMBER})月({_ZH_NUMBER})日", text)

    def number(raw, *, year=False):
        if raw.isascii() and raw.isdigit():
            return int(raw)
        digits = {char: index for index, char in enumerate("零一二三四五六七八九")}
        digits["〇"] = 0
        if year and len(raw) == 4 and all(char in digits for char in raw):
            return int("".join(str(digits[char]) for char in raw))
        if not year and len(raw) == 1 and raw in digits:
            return digits[raw]
        if not year and re.fullmatch(r"[一二三]?十[一二三四五六七八九]?", raw):
            a, b = raw.split("十")
            return 10 * (digits[a] if a else 1) + (digits[b] if b else 0)
        return None

    try:
        if english and english[1].lower() in _MONTH:
            return date(int(english[3]), _MONTH[english[1].lower()], int(english[2])).isoformat()
        if numeric:
            return date(int(numeric[1]), int(numeric[2]), int(numeric[3])).isoformat()
        if day_first and day_first[2].lower() in _MONTH:
            return date(int(day_first[3]), _MONTH[day_first[2].lower()], int(day_first[1])).isoformat()
        if chinese:
            return date(number(chinese[1], year=True), number(chinese[2]), number(chinese[3])).isoformat()
    except (ValueError, TypeError):
        return None
    return None


def read_period_label(text: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
    source = source or {}
    start = len(text) - len(text.lstrip())
    basis = _BASIS.match(text, start)
    cursor = basis.end() if basis else start
    while cursor < len(text) and text[cursor] in " \t\r\n:：":
        cursor += 1
    matched_date = _DATE.match(text, cursor)
    q, origins, controls = {}, {}, []
    if basis:
        q["period_basis"] = basis[0]
        origins["period_basis"] = _source(source, basis.start(), basis.end())
    if matched_date and calendar_date(matched_date[0]):
        q["period"] = matched_date[0]
        origins["period"] = _source(source, matched_date.start(), matched_date.end())
        cursor = matched_date.end()
    elif not basis or text[cursor:].strip():
        return {"matched": False, "qualifiers": {}, "qualifier_sources": {}, "label": text}
    suffix = _ZH_BASIS.match(text, cursor)
    if suffix:
        q["period_basis"] = suffix[0]
        origins["period_basis"] = _source(source, suffix.start(), suffix.end())
        if basis:
            controls.append({"text": basis[0], "source": _source(source, basis.start(), basis.end()),
                             "reason": "explicit_period_end_prefix"})
        cursor = suffix.end()
    remainder = text[cursor:].strip()
    if remainder:
        if remainder.startswith(("(", "（")):
            if not (remainder[0] == "(" and remainder[-1] == ")" or remainder[0] == "（" and remainder[-1] == "）"):
                return {"matched": False, "qualifiers": {}, "qualifier_sources": {}, "label": text}
            unit_text = remainder[1:-1].strip()
        else:
            unit_text = remainder
        unit = read_unit_token(unit_text)
        if not unit["matched"]:
            return {"matched": False, "qualifiers": {}, "qualifier_sources": {}, "label": text}
        unit_start = text.find(unit_text, cursor)
        printed = read_unit_token(unit_text, _source(source, unit_start, unit_start + len(unit_text)))
        q["unit"], origins["unit"] = printed["unit"], printed["sources"]["unit"]
        if printed["currency"]:
            q["currency"], origins["currency"] = printed["currency"], printed["sources"]["currency"]
    return {"matched": bool(q), "qualifiers": q, "qualifier_sources": origins, "controls": controls, "label": ""}
