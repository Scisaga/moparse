"""Finite printed UNDER contexts and IN domains with an explicit nominal head.

These are source-qualified adjuncts to a following clause, not extra business
assertions, conditional operators, inferred industries, or locations.
"""

from __future__ import annotations

import re

from .proposition_requirements import VERBS
from .quoted_nominal import _source, quoted_role_evidence, scan_quoted_nominals

_START = re.compile(r"(?P<preposition>Under|In)\b\s+", re.I)
_HEADS = {
    'under': r"(?:strategy|policy|plan|program|framework|rules?)",
    'in': r"(?:sector|industry|market|domain)",
}
_NESTED = re.compile(r"\b(?:that|which|who|whose|if|unless|except|because|although|whether|"
                     r"shall|must|may|might|can|cannot|will|would|should|could|"
                     r"is|are|was|were|has|have|had|do|does|did|to|for|from|by|with|within|"
                     + '|'.join(sorted(VERBS, key=len, reverse=True)) + r")\b", re.I)


def read_fronted_nominal_context(text, source, start=0, end=None, *, syntax_text=None, quoted=None):
    """Return an explicit source prefix and body offset, or None outside it.

    A matched but unresolved result claims no context semantics. The caller
    must retain that whole clause and feature gate instead of falling back to
    an unqualified or opaque business assertion.
    """
    end = len(text) if end is None else end
    quoted = scan_quoted_nominals(text, source) if quoted is None else quoted
    syntax = quoted['syntax_text'] if syntax_text is None else syntax_text
    prefix = _START.match(syntax, start, end)
    if prefix is None:
        return None
    result = {'matched': True, 'complete': False, 'kind': 'fronted_context',
              'preposition': text[slice(*prefix.span('preposition'))],
              'operator': prefix['preposition'].casefold(), 'span': [start, end],
              'preposition_span': list(prefix.span('preposition')),
              'operator_span': list(prefix.span('preposition'))}
    result['role'] = 'context' if result['operator'] == 'under' else 'domain'
    comma = syntax.find(',', prefix.end(), end)
    if comma < 0:
        result['reason'] = 'fronted_nominal_separator_unresolved'
        return result
    a, b = prefix.end(), comma
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    result.update(context=text[a:b], context_span=[a, b], separator_span=[comma, comma + 1], body_start=comma + 1)
    for role in ('preposition', 'operator', 'context', 'separator'):
        result[role + '_source'] = _source(source, *result[role + '_span'])
    # Quote interiors have been hidden solely for locating the outer comma and
    # nominal head; actual context text and every source remain untouched.
    nominal = syntax[a:b]
    if (not nominal or _NESTED.search(nominal) or re.search(r"[^A-Za-z0-9_'’ .-]", nominal)
            or not re.search(r"\b" + _HEADS[result['operator']] + r"(?:\s+Q+)?$", nominal, re.I)):
        result['reason'] = 'fronted_nominal_head_or_embedded_scope_unresolved'
        return result
    evidence, reason = quoted_role_evidence(text, a, b, quoted, role='context')
    if reason:
        result['reason'] = reason
        return result
    if evidence:
        result['quoted_nominals'] = evidence
    result['complete'] = True
    return result
