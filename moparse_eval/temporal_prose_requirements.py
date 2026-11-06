"""Bounded, explicitly printed temporal prefixes in ordinary prose."""

from __future__ import annotations

import re

from .period_evidence import _MONTH_PATTERN, read_period_label

_MONTH_PERIOD = re.compile(rf"(?P<operator>In|During)\s+(?P<period>(?:{_MONTH_PATTERN}\s+)?(?:19|20)\d{{2}})", re.I)
_PREFIX = re.compile(r"As\s+(?:of|at)\b|At\b|(?:For\s+)?(?:the\s+)?(?:fiscal\s+)?"
                     r"(?:(?:one|two|three|four|six|nine|twelve|\d+)\s+)?"
                     r"(?:years?|periods?|quarters?|months?|weeks?)\s+ended\b", re.I)


def read_temporal_prefix(text, source, start, end):
    """Return actual offsets; no fiscal start or calendar year is inferred."""
    month = _MONTH_PERIOD.match(text, start, end)
    if month:
        separator = re.match(r"\s*,\s*", text[month.end():end])
        if separator:
            offset = source.get("text_span", [0])[0]
            a, b = month.span("period")
            return {"qualifiers": {"period": month["period"]}, "qualifier_sources": {
                "period": {**source, "text_span": [offset + a, offset + b]}},
                "operator": month["operator"], "operator_span": list(month.span("operator")),
                "body_start": month.end() + separator.end()}
        return None
    if not _PREFIX.match(text, start, end):
        return None
    # A month-first complete date may contain its own comma. Only a complete
    # period label preceding a comma establishes the clause boundary.
    for comma in re.finditer(",", text[start:end]):
        boundary = start + comma.start()
        offset = source.get("text_span", [0])[0]
        origin = {**source, "text_span": [offset + start, offset + boundary]}
        period = read_period_label(text[start:boundary], origin)
        if period["matched"] and "period" in period["qualifiers"]:
            basis = period["qualifiers"].get("period_basis")
            if not basis:
                return None
            a, b = period["qualifier_sources"]["period_basis"]["text_span"]
            return {"qualifiers": period["qualifiers"], "qualifier_sources": period["qualifier_sources"],
                    "operator": basis, "operator_span": [a - offset, b - offset], "body_start": boundary + 1}
    return None
