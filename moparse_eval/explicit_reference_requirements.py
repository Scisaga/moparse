"""Source-only explicit cross-reference directives and target identities.

This reader establishes printed reference syntax, not the existence or truth
of the referenced material. A target's number/title is identity, not a business
value or proof of the directive's owner. Ownership requires independent source
evidence supplied by the surrounding reader; unresolved scope remains explicit.
"""

from __future__ import annotations

import copy
import re
from typing import Any

_DIRECTIVE = re.compile(r'(?<!\w)(?:See(?:\s+also)?|参见|參見|见|見)(?=\s|[“"‘\'《「『]|第|附注|附註|注)', re.I)
_PAIRS = {'“': '”', '"': '"', '‘': '’', "'": "'", '《': '》', '「': '」', '『': '』'}
_ID = r'(?:\d+(?:\.\d+)*(?:\([A-Za-z0-9]+\))*[A-Za-z]?|[IVXLCDM]+)'
_NUMBERED = re.compile(r'(?P<label>Article|Clause|Section|Note)\s*(?P<identifier>' + _ID + r')(?![A-Za-z0-9]|\.\d)', re.I)
_CJK_NUMBERED = re.compile(r'第(?P<identifier>\d+(?:\.\d+)*|[一二三四五六七八九十百千零〇两兩]+)(?P<label>条|條|章|节|節|项|項|号|號)')
_CJK_NOTE = re.compile(r'(?P<label>附注|附註|注)\s*(?P<identifier>' + _ID + r')(?![A-Za-z0-9]|\.\d)', re.I)
_TAIL = re.compile(r'\s*(?:(?P<purpose>for\s+more\s+information)\s*)?[.。;；!?！？]?\s*$', re.I)
_OWNER_KINDS = {'printed_field_label', 'prose_endpoint_roles', 'heading_scope'}


def _source(source, start, end):
    return {**copy.deepcopy(source), 'text_span': [source.get('text_span', [0, 0])[0] + start,
                                                 source.get('text_span', [0, 0])[0] + end]}


def _quoted_regions(text):
    regions, cursor = [], 0
    while cursor < len(text):
        char = text[cursor]
        if char not in _PAIRS or (char == "'" and cursor and cursor + 1 < len(text)
                                 and text[cursor - 1].isalnum() and text[cursor + 1].isalnum()):
            cursor += 1
            continue
        close = text.find(_PAIRS[char], cursor + 1)
        end = close + 1 if close >= 0 else len(text)
        regions.append((cursor, end))
        cursor = end
    return regions


def _region_end(text, start):
    match = re.search(r'[.。;；!?！？\n]', text[start:])
    return start + match.end() if match else len(text)


def _target(text, start):
    while start < len(text) and text[start].isspace():
        start += 1
    if start < len(text) and text[start] in _PAIRS:
        end = text.find(_PAIRS[text[start]], start + 1)
        if end < 0 or not text[start + 1:end].strip():
            raise ValueError('reference_quoted_target_unresolved')
        return {'target': {'role': 'reference_target', 'kind': 'quoted_title', 'title': text[start + 1:end]},
                'target_span': [start, end + 1], 'title_span': [start + 1, end]}
    match = _NUMBERED.match(text, start) or _CJK_NUMBERED.match(text, start) or _CJK_NOTE.match(text, start)
    if match is None:
        raise ValueError('reference_target_schema_unresolved')
    label = 'note' if match['label'] in {'附注', '附註', '注'} else match['label'].lower()
    return {'target': {'role': 'reference_target', 'kind': 'numbered_reference',
                       'reference_kind': label, 'identifier': match['identifier']},
            'target_span': [match.start(), match.end()],
            'identifier_span': [match.start('identifier'), match.end('identifier')],
            'kind_span': [match.start('label'), match.end('label')]}


def _owner_proof(owner, evidence, text, source, reference_span):
    if not isinstance(owner, dict) or not owner.get('identity') or not isinstance(evidence, (list, tuple)) or not evidence:
        return None
    if not isinstance(owner['identity'], dict) or any(key in owner['identity'] for key in ('value', 'target', 'reference_target')):
        return None
    offset = source.get('text_span', [0, 0])[0]
    for item in evidence:
        if not isinstance(item, dict) or item.get('kind') not in _OWNER_KINDS or not isinstance(item.get('text'), str):
            return None
        origin = item.get('source')
        if not item['text'].strip() or not isinstance(origin, dict) or not origin.get('path'):
            return None
        if item['kind'] == 'printed_field_label' and owner['identity'].get('attribute') != item['text']:
            return None
        if item['kind'] == 'prose_endpoint_roles' and item.get('identity') != owner['identity']:
            return None
        if origin.get('path') == source.get('path') and origin.get('lines') == source.get('lines'):
            span = origin.get('text_span')
            if not isinstance(span, (list, tuple)) or len(span) != 2 or any(type(v) is not int for v in span):
                return None
            a, b = span[0] - offset, span[1] - offset
            if a >= b or (max(a, 0) < min(b, len(text)) and
                          (not 0 <= a < b <= len(text) or text[a:b] != item['text'])):
                return None
            if max(a, reference_span[0]) < min(b, reference_span[1]):
                return None
    heading_labels = [item['text'] for item in evidence if item['kind'] == 'heading_scope']
    if heading_labels and heading_labels != owner.get('scope'):
        return None
    return {'owner': copy.deepcopy(owner), 'evidence': copy.deepcopy(evidence),
            'rule_id': 'independent_printed_owner_before_target_comparison'}


def read_explicit_references(text: str, source: dict[str, Any], *, scope=(), owner=None, owner_evidence=()) -> dict[str, Any]:
    """Expose references without adding B facts or certifying their targets.

    ``reference_complete`` concerns the detected directives and their owners.
    ``complete`` additionally requires no residual prose, which the caller must
    read separately. Matcher support is always explicitly declared, not assumed.
    """
    if not isinstance(text, str) or not isinstance(source, dict) or not isinstance(source.get('path'), str):
        raise ValueError('reference reader requires literal text and actual source identity')
    parent = source.get('text_span')
    if parent is not None and (not isinstance(parent, (list, tuple)) or len(parent) != 2
                               or any(type(v) is not int or v < 0 for v in parent) or parent[1] < parent[0]):
        raise ValueError('reference source span is invalid')
    result = {'matched': False, 'complete': False, 'semantic_complete': False, 'reference_complete': False,
              'facts': [], 'relations': [], 'references': [], 'semantic_roles': [], 'source_dispositions': [],
              'blockers': [], 'pending_requirements': [], 'unresolved': [], 'issues': [],
              'text_atoms': [], 'controls': [], 'consumed_spans': [], 'residual_spans': [],
              'required_matcher_features': [], 'text_projection_complete': True,
              'source_fragments': [{'text': text, 'source': _source(source, 0, len(text))}],
              'comparison_status': 'not_validated_by_this_source_reader'}
    quoted = _quoted_regions(text)
    consumed = []
    for match in _DIRECTIVE.finditer(text):
        if any(a <= match.start() < b for a, b in quoted):
            continue
        before = text[:match.start()].rstrip(' \t')
        if before and before[-1] not in '.。;；:：!?！？\n':
            continue
        result['matched'] = True
        start = match.start()
        try:
            parsed = _target(text, match.end())
            end = _region_end(text, parsed['target_span'][1])
            tail = _TAIL.fullmatch(text[parsed['target_span'][1]:end])
            if tail is None:
                raise ValueError('reference_trailing_syntax_unresolved')
        except ValueError as error:
            end = _region_end(text, match.end())
            pending = {'kind': 'explicit_reference', 'reason': str(error), 'text': text[start:end],
                       'source': _source(source, start, end), 'scope': list(scope), 'layers': ['L'],
                       'category': 'software_unsupported'}
            result['unresolved'].append(copy.deepcopy(pending))
            result['pending_requirements'].append(copy.deepcopy(pending))
            result['blockers'].append(pending)
            continue
        kind = re.sub(r'\s+', '_', match[0].lower())
        reference = {'directive_kind': kind, 'directive_text': match[0], 'directive_source': _source(source, start, match.end()),
                     'target': parsed['target'], 'scope': list(scope), 'source': _source(source, start, end),
                     'text': text[start:end], 'object_anchor': None}
        for role, span in [(name[:-5], value) for name, value in parsed.items() if name.endswith('_span')]:
            reference[role + '_text'] = text[slice(*span)]
            reference[role + '_source'] = _source(source, *span)
        if tail['purpose']:
            a = parsed['target_span'][1] + tail.start('purpose')
            b = parsed['target_span'][1] + tail.end('purpose')
            reference['purpose_text'], reference['purpose_source'] = text[a:b], _source(source, a, b)
        proof = _owner_proof(owner, owner_evidence, text, source, [start, end])
        reference['owner_proof'] = proof
        directive = {'role': 'reference_directive', 'directive_kind': kind,
                     'owner': copy.deepcopy(proof['owner']) if proof else None}
        binding = {'directive_source': reference['directive_source'], 'target_source': reference['target_source'],
                   'owner_proof': copy.deepcopy(proof), 'raw_reference': reference['text']}
        result['relations'].append({'type': 'explicit_reference_target', 'left': directive,
                                    'right': copy.deepcopy(reference['target']), 'source': copy.deepcopy(reference['source']),
                                    'object_anchor': None, 'binding_evidence': binding})
        if proof:
            result['relations'].append({'type': 'reference_directive_scope', 'left': copy.deepcopy(proof['owner']),
                                        'right': copy.deepcopy(directive), 'source': copy.deepcopy(reference['directive_source']),
                                        'object_anchor': None, 'binding_evidence': copy.deepcopy(binding)})
        else:
            pending = {'kind': 'explicit_reference', 'reason': 'reference_owner_scope_unproven',
                       'text': reference['text'], 'source': copy.deepcopy(reference['source']), 'scope': list(scope),
                       'layers': ['L'], 'category': 'software_unsupported'}
            result['pending_requirements'].append(copy.deepcopy(pending))
            result['blockers'].append(pending)
        result['references'].append(reference)
        for role in ('directive', 'target'):
            result['semantic_roles'].append({'role': 'reference_' + role, 'text': reference[role + '_text'],
                                              'source': copy.deepcopy(reference[role + '_source']),
                                              'identity': copy.deepcopy(directive if role == 'directive' else reference['target'])})
        if 'purpose_source' in reference:
            result['semantic_roles'].append({'role': 'reference_purpose', 'text': reference['purpose_text'],
                                              'source': copy.deepcopy(reference['purpose_source'])})
        consumed.append((start, end))
        result['consumed_spans'].append({'role': 'explicit_reference', 'text': text[start:end], 'span': [start, end],
                                         'source': _source(source, start, end)})
        result['source_dispositions'].append({'role': 'explicit_reference', 'text': text[start:end],
                                              'source': _source(source, start, end), 'layers': ['L'],
                                              'proof': {'directive': copy.deepcopy(directive), 'target': copy.deepcopy(reference['target']),
                                                        'owner_proof': copy.deepcopy(proof),
                                                        **({'purpose': {'text': reference['purpose_text'], 'source': copy.deepcopy(reference['purpose_source'])}}
                                                           if 'purpose_source' in reference else {})}})
    cursor = 0
    for start, end in sorted(consumed):
        if text[cursor:start].strip():
            result['residual_spans'].append({'text': text[cursor:start], 'span': [cursor, start],
                                             'source': _source(source, cursor, start)})
        cursor = max(cursor, end)
    if text[cursor:].strip():
        result['residual_spans'].append({'text': text[cursor:], 'span': [cursor, len(text)],
                                         'source': _source(source, cursor, len(text))})
    if result['matched']:
        result['required_matcher_features'] = ['explicit_reference_binding']
        result['text_atoms'] = [{'text': text, 'role': 'literal', 'source': _source(source, 0, len(text))}]
    result['reference_complete'] = bool(result['references']) and not result['blockers']
    result['complete'] = result['semantic_complete'] = result['reference_complete'] and not result['residual_spans']
    return result
