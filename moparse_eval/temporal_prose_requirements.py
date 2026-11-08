"""Bounded, explicitly printed temporal prefixes in ordinary prose."""

from __future__ import annotations

import re

from .period_evidence import _MONTH_PATTERN, read_period_label

_MONTH_PERIOD = re.compile(rf"(?P<operator>In|During)\s+(?P<period>(?:{_MONTH_PATTERN}\s+)?(?:19|20)\d{{2}})", re.I)
_PREFIX = re.compile(r"As\s+(?:of|at)\b|At\b|(?:For\s+)?(?:the\s+)?(?:fiscal\s+)?"
                     r"(?:(?:one|two|three|four|six|nine|twelve|\d+)\s+)?"
                     r"(?:years?|periods?|quarters?|months?|weeks?)\s+ended\b", re.I)
_CJK_TIME = r'(?:(?:19|20)\d{2}年(?:\d{1,2}月(?:\d{1,2}日)?|期末|末|初|底)?|本[報报]告期[內内]|本年度[內内]|同日|目前|每年|每月|每季度|定期)'


def read_cjk_temporal(text, source, start, end, *, trailing=False):
    """Expose a printed date/report period or recurrence, without filling dates."""
    expression = re.compile(r'(?P<operator>截至|於|于)?(?P<period>' + _CJK_TIME + r')' + ('$' if trailing else r'(?![\d年月日])'))
    match = expression.search(text, start, end) if trailing else expression.match(text, start, end)
    if match is None:
        return None
    raw = match['period']
    if not trailing and raw == '同日' and match.end() < end and text[match.end()] not in '，, \t':
        return None  # 同日公司 is an ordinary printed name, not a time prefix.
    if re.match(r'(?:19|20)\d{2}年\d', raw):
        month = re.fullmatch(r'(?:19|20)\d{2}年(?P<month>\d{1,2})月', raw)
        if not (month and 1 <= int(month['month']) <= 12 or read_period_label(raw)['matched']):
            return None
    offset = source.get('text_span', [0])[0]
    key = 'frequency' if raw in {'每年', '每月', '每季度', '定期'} else 'period'
    qualifier_source = {**source, 'text_span': [offset + match.start('period'), offset + match.end('period')]}
    result = {'qualifiers': {key: raw}, 'qualifier_sources': {key: qualifier_source},
              'operator': match['operator'] or raw,
              'operator_span': list(match.span('operator') if match['operator'] else match.span('period')),
              'body_start': match.end(), 'actor_end': match.start()}
    if match['operator']:
        result['qualifiers']['period_basis'] = match['operator']
        result['qualifier_sources']['period_basis'] = {**source, 'text_span': [offset + match.start('operator'), offset + match.end('operator')]}
    if not trailing:
        while result['body_start'] < end and text[result['body_start']] in '，, \t':
            result['body_start'] += 1
    return result


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
