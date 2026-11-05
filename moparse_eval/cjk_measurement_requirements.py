"""Finite printed metric thresholds and immediately attached YoY rates.

An explicit 同比 clause may refer to the preceding metric in this one ordered
construction. No actor, unit, currency, baseline year or omitted predicate is
borrowed across another clause, sentence or reader invocation. Unknown tails
retain the whole source as pending beside already exposed local propositions.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .measurement_evidence import read_measurement_literal

_COMPARISONS = {'不超过': 'lte', '不超過': 'lte', '不高于': 'lte', '不高於': 'lte',
                '不低于': 'gte', '不低於': 'gte', '不少于': 'gte', '不少於': 'gte',
                '超过': 'gt', '超過': 'gt', '高于': 'gt', '高於': 'gt', '大于': 'gt', '大於': 'gt',
                '低于': 'lt', '低於': 'lt', '小于': 'lt', '小於': 'lt', '等于': 'eq', '等於': 'eq'}
_COMPARISON = re.compile('|'.join(sorted(_COMPARISONS, key=len, reverse=True)))
_CHANGES = {'同比增长': 'increase', '同比增長': 'increase', '同比增加': 'increase', '同比上升': 'increase',
            '同比下降': 'decrease', '同比减少': 'decrease', '同比減少': 'decrease'}
_CHANGE = re.compile('|'.join(sorted(_CHANGES, key=len, reverse=True)))
_PERIOD = re.compile(r'\s*(?P<period>\d{4}年)\s*[，,]\s*')
_PREFIX = re.compile(r'如果|若|只有|除非|因为|因為|由于|由於|据|據|截至|面向|在|为|為|今年|去年|本年|上年|当年|當年|\d{4}年')
_METRIC = re.compile(r'(?:值|量|额|額|收入|支出|利润|利潤|余额|餘額|资产|資產|负债|負債|人数|人數|指数|指數|率|规模|規模)(?:\s*[（(][A-Za-z][A-Za-z0-9 -]*[）)])?$')
_SUBJECT_SCOPE = re.compile(r'[，,；;:：。！？!?“”"\'‘’]|的|和|与|與|及|或|并|並|同比|如果|除非|因为|因為|由于|由於|表示|认为|認為')


def _source(source, a, b):
    offset = source.get('text_span', [0, 0])[0]
    return {**copy.deepcopy(source), 'text_span': [offset + a, offset + b]}


def _trim(text, a, b):
    while a < b and text[a].isspace():
        a += 1
    while b > a and (text[b - 1].isspace() or text[b - 1] in '。.!?！？'):
        b -= 1
    return a, b


def read_cjk_measurements(text: str, source: dict[str, Any], *, scope=()) -> dict[str, Any]:
    """Return source-bound propositions, never an exact-value replacement for >."""
    if not isinstance(text, str) or not isinstance(source, dict) or not isinstance(source.get('path'), str):
        raise ValueError('CJK measurements require original text and its source')
    parent = source.get('text_span')
    if parent is not None and (not isinstance(parent, (list, tuple)) or len(parent) != 2
                               or any(type(v) is not int or v < 0 for v in parent) or parent[1] < parent[0]):
        raise ValueError('CJK measurement source span is invalid')
    result = {'matched': bool((_COMPARISON.search(text) and re.search(r'\d', text)) or _CHANGE.search(text)),
              'complete': False, 'semantic_complete': False, 'facts': [], 'relations': [], 'logic': [],
              'semantic_operands': [], 'semantic_operand_relations': [], 'unresolved': [], 'blockers': [],
              'pending_requirements': [], 'issues': [], 'text_atoms': [], 'controls': [], 'consumed_spans': [],
              'required_matcher_features': [], 'text_projection_complete': True,
              'source': copy.deepcopy(source), 'raw_text': text, 'comparison_status': 'not_validated_by_this_source_reader'}
    if not result['matched']:
        return result
    result['text_atoms'] = [{'text': text, 'role': 'literal', 'source': _source(source, 0, len(text))}]
    result['consumed_spans'] = [{'text': text, 'role': 'literal', 'span': [0, len(text)], 'source': _source(source, 0, len(text))}]
    start, end = _trim(text, 0, len(text))
    period = _PERIOD.match(text, start, end)
    period_text = period['period'] if period else None
    period_source = _source(source, period.start('period'), period.end('period')) if period else None
    body_start = period.end() if period else start
    parts, cursor = [], body_start
    for separator in re.finditer(r'，|(?<!\d),(?!\d)', text[body_start:end]):
        a, b = _trim(text, cursor, body_start + separator.start())
        parts.append((a, b))
        cursor = body_start + separator.end()
    parts.append(_trim(text, cursor, end))
    unknown, features = [], set()
    tree = {'kind': 'cjk_measurement_sequence', 'source': _source(source, 0, len(text)), 'clauses': [],
            'period': {'text': period_text, 'source': period_source} if period else None}

    def fail(a, b, reason):
        unknown.append({'reason': reason, 'text': text[a:b], 'source': _source(source, a, b)})

    def emit(subject, subject_source, attribute, predicate_source, measurement, own_source, qualifiers, qualifier_sources, logic):
        q = {**qualifiers, **({'unit': measurement['unit']} if measurement['unit'] else {}),
             **({'currency': measurement['currency']} if measurement['currency'] else {})}
        qs = {**qualifier_sources, **{key: copy.deepcopy(measurement['sources'][key])
                                      for key in ('unit', 'currency', 'currency_symbol') if key in measurement['sources']}}
        if period:
            q['period'], qs['period'] = period_text, copy.deepcopy(period_source)
            features.add('shared_period_scope')
        fact = {'id': f'cjk_measurement:{len(result["facts"])}', 'subject': subject, 'attribute': attribute,
                'predicate': attribute, 'object': measurement['value'], 'value': measurement['value'],
                'role': 'description', 'semantic_role': 'requirement', 'qualifiers': q, 'qualifier_sources': qs,
                'identity_facets': {}, 'scope': list(scope), 'source': copy.deepcopy(own_source),
                'subject_source': copy.deepcopy(subject_source), 'predicate_source': copy.deepcopy(predicate_source),
                'attribute_source': copy.deepcopy(predicate_source), 'value_source': copy.deepcopy(measurement['sources']['value']),
                'object_source': copy.deepcopy(measurement['sources']['value']), 'logic': copy.deepcopy(logic),
                'record_id': f'cjk_measurement:{source!r}', 'rule_id': 'printed_cjk_measurement_clause'}
        result['facts'].append(fact)
        endpoint = {'subject': subject, 'attribute': attribute, 'scope': list(scope)}
        result['relations'].append({'type': 'field_binding', 'left': copy.deepcopy(endpoint), 'right': copy.deepcopy(endpoint),
                                    'source': copy.deepcopy(own_source), 'object_anchor': None,
                                    'binding_evidence': {'subject_source': copy.deepcopy(subject_source),
                                        'predicate_source': copy.deepcopy(predicate_source), 'value_source': copy.deepcopy(fact['value_source'])}})
        for key, value in q.items():
            result['relations'].append({'type': 'qualifier_scope', 'left': {'type': key, 'text': value},
                'right': copy.deepcopy(endpoint), 'source': copy.deepcopy(qs[key]), 'object_anchor': None,
                'binding_evidence': {'qualifier_source': copy.deepcopy(qs[key]), 'data_source': copy.deepcopy(fact['value_source'])}})
        tree['clauses'].append(copy.deepcopy(logic))
        return fact

    a, b = parts[0]
    comparison = _COMPARISON.search(text, a, b)
    subject = subject_source = None
    if text.rstrip().endswith(('?', '？')):
        fail(a, b, 'cjk_measurement_interrogative_scope_unresolved')
    elif comparison:
        sa, sb = _trim(text, a, comparison.start())
        subject = text[sa:sb]
        metric_ok = bool(subject and _METRIC.search(subject) and not _PREFIX.match(subject) and not _SUBJECT_SCOPE.search(subject))
        measurement = read_measurement_literal(text[comparison.end():b], _source(source, comparison.end(), b))
        if metric_ok and measurement['matched']:
            subject_source = _source(source, sa, sb)
            operator_source = _source(source, comparison.start(), comparison.end())
            logic = {'kind': 'quantity_comparison', 'subject': subject, 'subject_source': subject_source,
                     'operator': _COMPARISONS[comparison[0]], 'operator_text': comparison[0], 'operator_source': operator_source,
                     'right_role': 'threshold', 'value_source': measurement['sources']['value'],
                     'unit_source': measurement['sources'].get('unit'), 'source': _source(source, a, b)}
            emit(subject, subject_source, comparison[0], operator_source, measurement, _source(source, a, b),
                 {'comparison_operator': _COMPARISONS[comparison[0]]}, {'comparison_operator': operator_source}, logic)
            features.add('quantity_comparison')
        else:
            fail(a, b, 'cjk_metric_comparison_roles_unresolved')
    else:
        fail(a, b, 'cjk_metric_comparison_clause_unresolved')
    if len(parts) > 1:
        a, b = parts[1]
        change = _CHANGE.match(text, a, b)
        if result['facts'] and change:
            measurement = read_measurement_literal(text[change.end():b], _source(source, change.end(), b))
            if measurement['matched'] and measurement['unit'] in {'%', '‰'}:
                predicate_source = _source(source, change.start(), change.end())
                basis_source, direction_source = _source(source, change.start(), change.start() + 2), _source(source, change.start() + 2, change.end())
                logic = {'kind': 'year_on_year_change', 'subject': subject, 'subject_source': subject_source,
                         'operator_text': change[0], 'operator_source': predicate_source, 'basis': 'year_on_year',
                         'direction': _CHANGES[change[0]], 'baseline_period': None, 'value_source': measurement['sources']['value'],
                         'unit_source': measurement['sources']['unit'], 'source': _source(source, a, b)}
                fact = emit(subject, subject_source, change[0], predicate_source, measurement, _source(source, a, b),
                            {'comparison_basis': 'year_on_year', 'change_direction': _CHANGES[change[0]]},
                            {'comparison_basis': basis_source, 'change_direction': direction_source}, logic)
                fact['subject_binding_evidence'] = {'kind': 'immediate_printed_year_on_year_antecedent',
                    'antecedent_source': copy.deepcopy(subject_source), 'relative_operator_source': basis_source,
                    'scope': list(scope)}
                result['relations'].append({'type': 'cjk_year_on_year_subject_binding',
                    'left': {'subject': subject, 'role': 'antecedent_metric', 'scope': list(scope)},
                    'right': {'subject': subject, 'attribute': change[0], 'scope': list(scope)}, 'source': basis_source,
                    'object_anchor': None, 'binding_evidence': copy.deepcopy(fact['subject_binding_evidence'])})
                features.update({'year_on_year_comparison', 'same_subject_relative_clause'})
            else:
                fail(a, b, 'cjk_year_on_year_ratio_measurement_unresolved')
        else:
            fail(a, b, 'cjk_relative_measurement_antecedent_or_operator_unresolved')
    for a, b in parts[2:]:
        fail(a, b, 'cjk_measurement_tail_unresolved')
    if unknown:
        pending = {'kind': 'cjk_measurement_sequence', 'reason': 'cjk_measurement_sequence_incomplete',
                   'text': text, 'source': _source(source, 0, len(text)), 'scope': list(scope),
                   'layers': ['B', 'L'], 'category': 'software_unsupported', 'fragments': unknown}
        result['unresolved'].append(copy.deepcopy(pending))
        result['pending_requirements'].append(copy.deepcopy(pending))
        result['blockers'].append(pending)
    tree['unresolved'] = copy.deepcopy(unknown)
    result['logic'].append(tree)
    result['required_matcher_features'] = sorted(features)
    result['complete'] = result['semantic_complete'] = bool(result['facts']) and not unknown
    return result
