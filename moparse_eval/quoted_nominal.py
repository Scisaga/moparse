"""Finite quoted nominal scopes, without interpreting a quoted proposition.

The same-length syntax view hides quoted words from outer operator searches.
It is never a replacement source, a text projection, or a canonical answer.
Every exposed role retains the literal delimiters and their original ranges.
"""

from __future__ import annotations

import copy
import re

from .proposition_requirements import VERBS

_PAIRS = {'"': '"', "'": "'", '“': '”', '‘': '’', '「': '」', '『': '』'}
_CLOSING = set(_PAIRS.values())
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)*|[%‰]")
_LOWER_NOMINAL = {
    # Finite nominal vocabulary; absence of a recognized verb alone is not
    # evidence that an arbitrary lower-case clause is a name or noun phrase.
    'a', 'an', 'the', 'and', 'or', 'not', 'never', 'no', 'of', 'first', 'second',
    'user', 'customer', 'client', 'business', 'digital', 'financial', 'annual',
    'global', 'local', 'public', 'private', 'secure', 'new', 'old', 'other',
    'supplier', 'provider', 'strategy', 'platform', 'product', 'service',
    'system', 'device', 'division', 'group', 'record', 'records', 'data',
    'technology', 'research', 'development', 'investment', 'investments',
    'income', 'revenue', 'profit', 'margin', 'growth', 'risk', 'report',
    'policy', 'plan', 'model', 'capital', 'market', 'security', 'value',
    'ai-driven',
}
_NOMINAL_HEADS = _LOWER_NOMINAL - {
    'a', 'an', 'the', 'and', 'or', 'not', 'never', 'no', 'of', 'first', 'second',
    'digital', 'financial', 'annual', 'global', 'local', 'public', 'private',
    'secure', 'new', 'old', 'other',
}
_NAME_PREFIXES = {'not', 'never', 'no'}
_NOMINAL_JOIN = re.compile(r"\b(?:and|or)\b|[,，&/]", re.I)
_FINITE = re.compile(r"\b(?:" + '|'.join(sorted(set(VERBS) | {
    'am', 'is', 'are', 'was', 'were', 'be', 'being', 'been', 'has', 'have', 'had',
    'do', 'does', 'did', 'can', 'cannot', 'could', 'may', 'might', 'shall', 'should',
    'must', 'will', 'would', 'say', 'says', 'said', 'state', 'states', 'stated',
    'reported', 'stores', 'stored', 'retrieves', 'retrieved', 'includes', 'included',
    'supports', 'supported', 'operates', 'operated', 'designs', 'designed',
    'offers', 'offered', 'creates', 'created', 'manages', 'managed', 'produces',
    'produced', 'serves', 'served', 'develops', 'developed', 'builds', 'built',
    'uses', 'used', 'needs', 'needed', 'attends', 'attended', 'votes', 'voted',
}, key=len, reverse=True)) + r")\b", re.I)
_EMBEDDED = re.compile(r"\b(?:if|unless|although|because|whether|that|which|who|whose|when|where|why)\b|[;:!?。！？\n]", re.I)
_OUTER_TAIL = re.compile(r"\b(?:to|for|from|with|within|under|by|about|into|over|through|against|"
                         r"between|among|toward|towards|during|before|after|in|on|at|that|which|who)\b", re.I)


def _source(source, start, end):
    result = copy.deepcopy(source)
    origin = source.get('text_span', [0, 0])[0]
    result['text_span'] = [origin + start, origin + end]
    if 'cell_text_span' in source:
        origin = source['cell_text_span'][0]
        result['cell_text_span'] = [origin + start, origin + end]
    return result


def _nominal_reason(content):
    if not content.strip():
        return 'quoted_nominal_empty_unresolved'
    if _FINITE.search(content) or _EMBEDDED.search(content):
        return 'quoted_nominal_proposition_or_operator_unresolved'
    tokens = list(_TOKEN.finditer(content))
    if not tokens or re.sub(_TOKEN, '', content).strip(' ,，-&()/'):
        return 'quoted_nominal_lexical_role_unresolved'
    # Admission is deliberately finite. Capitalization supplies no part of
    # speech: a title-cased clause is still a clause. A quoted name atom may
    # contain one otherwise opaque identifier, an optional literal NOT/NO
    # prefix and numeric suffixes. Adjacent unknown words are not silently
    # classified as names. Known noun phrases use the finite vocabulary and
    # need a nominal head in each explicitly coordinated member.
    for member in _NOMINAL_JOIN.split(content):
        words = [token[0].casefold() for token in _TOKEN.finditer(member)]
        if not words:
            return 'quoted_nominal_lexical_role_unresolved'
        unknown = [word for word in words if word not in _LOWER_NOMINAL and not word[0].isdigit()
                   and word not in {'%', '‰'}]
        if unknown:
            if len(unknown) != 1:
                return 'quoted_nominal_lexical_role_unresolved'
            index = words.index(unknown[0])
            if (any(word not in _NAME_PREFIXES for word in words[:index])
                    or any(not word[0].isdigit() for word in words[index + 1:])):
                return 'quoted_nominal_lexical_role_unresolved'
        elif not any(word in _NOMINAL_HEADS for word in words):
            return 'quoted_nominal_lexical_role_unresolved'
    return None


def scan_quoted_nominals(text, source):
    """Expose flat, paired quoted spans and a same-length outer syntax view."""
    result = {'matched': False, 'complete': True, 'scopes': [], 'errors': [], 'syntax_text': text}
    opening = None
    syntax = list(text)
    for index, character in enumerate(text):
        if character not in _PAIRS and character not in _CLOSING:
            continue
        # Actual possessive/contraction apostrophes are not quote delimiters.
        if character in {"'", '’'} and index and index + 1 < len(text) and text[index - 1].isalnum() and text[index + 1].isalnum():
            continue
        result['matched'] = True
        if opening is None:
            if character not in _PAIRS:
                result['errors'].append({'reason': 'quoted_nominal_unpaired_delimiter_unresolved', 'span': [index, index + 1]})
                continue
            opening = (index, character)
        elif character == _PAIRS[opening[1]]:
            start = opening[0]
            content = text[start + 1:index]
            reason = _nominal_reason(content)
            scope = {'text': text[start:index + 1], 'content': content, 'span': [start, index + 1],
                     'source': _source(source, start, index + 1), 'content_source': _source(source, start + 1, index),
                     'opening_source': _source(source, start, start + 1), 'closing_source': _source(source, index, index + 1),
                     'nominal_complete': reason is None}
            if reason:
                scope['reason'] = reason
            result['scopes'].append(scope)
            # Preserve indices only; this view must never be emitted as text.
            syntax[start:index + 1] = 'Q' * (index + 1 - start)
            opening = None
        else:
            result['errors'].append({'reason': 'quoted_nominal_nested_or_mismatched_delimiter_unresolved',
                                     'span': [opening[0], index + 1]})
    if opening is not None:
        result['errors'].append({'reason': 'quoted_nominal_unclosed_delimiter_unresolved', 'span': [opening[0], len(text)]})
    for error in result['errors']:
        error['source'] = _source(source, *error['span'])
    result['complete'] = not result['errors'] and all(item['nominal_complete'] for item in result['scopes'])
    result['syntax_text'] = ''.join(syntax)
    return result


def quoted_role_evidence(text, start, end, scan, *, role):
    """Read a whole quoted name or a bounded quoted modifier in one NP role.

    Returns evidence and an unresolved reason. External PP/relative material
    is not absorbed into an opaque nominal merely because a quote is present.
    """
    selected = [item for item in scan['scopes'] if item['span'][0] < end and item['span'][1] > start]
    if not selected:
        return [], None
    if any(not (start <= item['span'][0] < item['span'][1] <= end) for item in selected):
        return [], 'quoted_nominal_role_boundary_unresolved'
    reason = next((item['reason'] for item in selected if not item['nominal_complete']), None)
    if reason:
        return [], reason
    outside = list(text[start:end])
    for item in selected:
        a, b = item['span']
        outside[a - start:b - start] = ' ' * (b - a)
    tail = ''.join(outside).strip()
    if _OUTER_TAIL.search(tail) or _FINITE.search(tail) or _EMBEDDED.search(tail):
        return [], 'quoted_nominal_external_scope_unresolved'
    if len(selected) > 1:
        return [], 'quoted_nominal_role_attachment_unresolved'
    evidence = [{key: copy.deepcopy(item[key]) for key in ('text', 'content', 'source', 'content_source',
                 'opening_source', 'closing_source')} for item in selected]
    for item in evidence:
        item.update(role=role, attachment='nominal_modifier' if tail else 'whole_nominal')
    return evidence, None
