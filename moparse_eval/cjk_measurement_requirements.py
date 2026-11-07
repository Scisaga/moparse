"""Finite printed metric assertions, thresholds and immediately attached YoY.

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
from .period_evidence import read_period_label

_COMPARISONS = {'不超过': 'lte', '不超過': 'lte', '不高于': 'lte', '不高於': 'lte',
                '不低于': 'gte', '不低於': 'gte', '不少于': 'gte', '不少於': 'gte',
                '超过': 'gt', '超過': 'gt', '高于': 'gt', '高於': 'gt', '大于': 'gt', '大於': 'gt',
                '低于': 'lt', '低於': 'lt', '小于': 'lt', '小於': 'lt', '等于': 'eq', '等於': 'eq'}
_COMPARISON = re.compile('|'.join(sorted(_COMPARISONS, key=len, reverse=True)))
_CHANGES = {'同比增长': 'increase', '同比增長': 'increase', '同比增加': 'increase', '同比上升': 'increase',
            '同比下降': 'decrease', '同比减少': 'decrease', '同比減少': 'decrease'}
_CHANGE = re.compile(r'(?P<basis>同比|(?:相[較较]|[較较比])(?P<baseline>(?:19|20)\d{2}年(?:同期|末)|年初)|比上年末)'
                     r'(?P<direction>增长|增長|增加|上升|下降|减少|減少)')
_PERIOD = re.compile(r'\s*(?P<prefix>於|于|截至)?(?P<period>(?:19|20)\d{2}年(?:\d{1,2}月\d{1,2}日|底|末)?)'
                     r'(?!度|初|中|[内內前后後]|以[来來]|[\d一二三四五六七八九十]+月)\s*(?:[，,]\s*)?')
_PREFIX = re.compile(r'如果|若|只有|除非|因为|因為|由于|由於|据|據|截至|面向|在|为|為|今年|去年|本年|上年|当年|當年|\d{4}年')
_METRIC = re.compile(r'(?:值|量|额|額|收入|支出|利润|利潤|余额|餘額|资产|資產|负债|負債|人数|人數|指数|指數|率|规模|規模|费用|費用|损益|損益|权益|權益|借款|庫存股|库存股|存貨|存货)(?:流出|流入)?(?:\s*[（(][A-Za-z][A-Za-z0-9 -]*[）)])?$')
_SUBJECT_SCOPE = re.compile(r'[，,；;:：。！？!?“”"\'‘’]|中的|或|并|並|同比|比上年|如果|除非|因为|因為|由于|由於|表示|认为|認為')
_NON_ACTUAL = re.compile(r'目标|目標|预计|預計|预期|預期|预测|預測|计划|計劃|预算|預算|拟|擬|将|將|未(?:实现|實現|达|達)|不(?:为|為|是)|没有|沒有|如果|若|除非|假设|假設')
_ASSERTION = re.compile(r'实现|實現|为|為|达到|達到')
_ACTOR = re.compile(r'(?P<actor>本公司|本集[团團]|[该該]事[业業]部)(?:的)?')


def _source(source, a, b):
    offset = source.get('text_span', [0, 0])[0]
    return {**copy.deepcopy(source), 'text_span': [offset + a, offset + b]}


def _trim(text, a, b):
    while a < b and text[a].isspace():
        a += 1
    while b > a and (text[b - 1].isspace() or text[b - 1] in '。.!?！？'):
        b -= 1
    return a, b


def _valid_metric(metric):
    if not _METRIC.search(metric) or _PREFIX.match(metric) or _SUBJECT_SCOPE.search(metric) or _NON_ACTUAL.search(metric) or re.match(r'\*|__', metric):
        return False
    # A fixed compound label may contain conjunctions. Two independently
    # complete metric labels do not jointly own a single unallocated amount.
    return not any(_METRIC.search(metric[:join.start()]) and _METRIC.search(metric[join.end():])
                   for join in re.finditer(r'和|与|與|及|以及', metric))


def _assertion_candidates(text, source, a, b):
    """Source cuts for the two assertion frames, before reader dispatch."""
    actor = _ACTOR.match(text, a, b)
    body = actor.end() if actor else a
    realized = re.match(r'实现|實現', text[body:b])
    equality = re.search(r'为|為|达到|達到', text[body:b]) if not realized else None
    candidates = []
    if realized:
        sa = body + realized.end()
        for sb in range(sa + 1, b):
            if _METRIC.search(text[sa:sb].strip()):
                link = re.match(r'为|為', text[sb:b])
                value_start = sb + link.end() if link else sb
                measurement = read_measurement_literal(text[value_start:b], _source(source, value_start, b))
                if measurement['matched']:
                    if link:
                        measurement['assertion_link'] = {'text': link[0], 'source': _source(source, sb, value_start)}
                    candidates.append((sa, sb, body, body + realized.end(), measurement))
    elif equality:
        sa, sb = _trim(text, body, body + equality.start())
        qa, qb = body + equality.start(), body + equality.end()
        measurement = read_measurement_literal(text[qb:b], _source(source, qb, b))
        if measurement['matched']:
            candidates.append((sa, sb, qa, qb, measurement))
    if actor:
        for *_, measurement in candidates:
            measurement['actor'] = {'text': actor['actor'], 'source': _source(source, *actor.span('actor'))}
            if actor.end() > actor.end('actor'):
                measurement['actor_link'] = {'text': text[actor.end('actor'):actor.end()],
                    'source': _source(source, actor.end('actor'), actor.end())}
    return candidates, bool(realized)


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
    start, end = _trim(text, 0, len(text))
    period = _PERIOD.match(text, start, end)
    period_text = period['period'] if period else None
    period_source = _source(source, period.start('period'), period.end('period')) if period else None
    body_start = period.end() if period else start
    invalid_period = bool(period_text and '月' in period_text and not read_period_label(period_text)['matched'])
    parts, cursor = [], body_start
    for separator in re.finditer(r'，|(?<!\d),(?!\d)', text[body_start:end]):
        a, b = _trim(text, cursor, body_start + separator.start())
        parts.append((a, b))
        cursor = body_start + separator.end()
    parts.append(_trim(text, cursor, end))
    candidates, _realized = _assertion_candidates(text, source, *parts[0])
    if len(candidates) == 1:
        sa, sb, _qa, _qb, _measurement = candidates[0]
        metric = text[sa:sb].strip()
        result['matched'] |= _valid_metric(metric)
    result['matched'] |= bool(re.match(r'(?:其中)?[^，,。]+占[^，,。]+的\d', text[body_start:end]))
    if not result['matched']:
        return result
    result['text_atoms'] = [{'text': text, 'role': 'literal', 'source': _source(source, 0, len(text))}]
    result['consumed_spans'] = [{'text': text, 'role': 'literal', 'span': [0, len(text)], 'source': _source(source, 0, len(text))}]
    unknown, features = [], set()
    tree = {'kind': 'cjk_measurement_sequence', 'source': _source(source, 0, len(text)), 'clauses': [],
            'period': {'text': period_text, 'source': period_source} if period else None}

    def fail(a, b, reason):
        unknown.append({'reason': reason, 'text': text[a:b], 'source': _source(source, a, b)})

    def emit(subject, subject_source, attribute, predicate_source, measurement, own_source, qualifiers, qualifier_sources, logic):
        # The native clause is already interpreted here. Retain the payload
        # alongside its source cuts so the existing recursive comparator does
        # not see a value-less quantity node. B/L still own separate votes.
        logic.update(value=measurement['value'], unit=measurement['unit'],
                     currency=measurement['currency'], sequence_source=copy.deepcopy(tree['source']))
        q = {**qualifiers, **({'unit': measurement['unit']} if measurement['unit'] else {}),
             **({'currency': measurement['currency']} if measurement['currency'] else {})}
        qs = {**qualifier_sources, **{key: copy.deepcopy(measurement['sources'][key])
                                      for key in ('unit', 'currency', 'currency_symbol') if key in measurement['sources']}}
        for key in ('actor', 'actor_link', 'assertion_link'):
            if measurement.get(key):
                q[key], qs[key] = measurement[key]['text'], copy.deepcopy(measurement[key]['source'])
        if period:
            q['period'], qs['period'] = period_text, copy.deepcopy(period_source)
            if period['prefix']:
                q['period_operator'], qs['period_operator'] = period['prefix'], _source(source, *period.span('prefix'))
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
                                    'source': copy.deepcopy(own_source), 'object_anchor': None, 'fact_id': fact['id'],
                                    'binding_evidence': {'subject_source': copy.deepcopy(subject_source),
                                        'statement_source': copy.deepcopy(own_source),
                                        'predicate_source': copy.deepcopy(predicate_source),
                                        'object_source': copy.deepcopy(fact['object_source']),
                                        'value_source': copy.deepcopy(fact['value_source'])}})
        for key, value in q.items():
            result['relations'].append({'type': 'qualifier_scope', 'left': {'type': key, 'text': value,
                    **({'currency': q['currency']} if key == 'unit' and q.get('currency') else {})},
                'right': copy.deepcopy(endpoint), 'source': copy.deepcopy(qs[key]), 'object_anchor': None, 'fact_id': fact['id'],
                'binding_evidence': {'statement_source': copy.deepcopy(own_source),
                    'qualifier_source': copy.deepcopy(qs[key]), 'data_source': copy.deepcopy(fact['value_source'])}})
        tree['clauses'].append(copy.deepcopy(logic))
        return fact

    antecedent = None
    for part_index, (a, b) in enumerate(parts):
        if invalid_period:
            fail(a, b, 'cjk_measurement_calendar_period_unresolved')
            continue
        comparison = _COMPARISON.search(text, a, b)
        change = _CHANGE.search(text, a, b)
        explicit_subject = None
        if change and change.start() > a:
            sa, sb = _trim(text, a, change.start())
            explicit_subject = text[sa:sb]
            if not _valid_metric(explicit_subject):
                change = None
        if text.rstrip().endswith(('?', '？')):
            fail(a, b, 'cjk_measurement_interrogative_scope_unresolved')
            antecedent = None
            continue
        if change:
            if antecedent is None and explicit_subject is None:
                fail(a, b, 'cjk_relative_measurement_antecedent_or_operator_unresolved')
                continue
            subject, subject_source = ((explicit_subject, _source(source, sa, sb)) if explicit_subject is not None
                                       else (antecedent['subject'], antecedent['subject_source']))
            measurement = read_measurement_literal(text[change.end():b], _source(source, change.end(), b))
            if measurement['matched'] and measurement['unit']:
                predicate_source = _source(source, change.start(), change.end())
                basis_source, direction_source = _source(source, *change.span('basis')), _source(source, *change.span('direction'))
                basis = 'year_on_year' if change['basis'] == '同比' else change['basis']
                direction = 'decrease' if change['direction'] in {'下降', '减少', '減少'} else 'increase'
                logic = {'kind': 'year_on_year_change', 'subject': subject, 'subject_source': subject_source,
                         'operator_text': change[0], 'operator_source': predicate_source, 'basis': basis,
                         'direction': direction, 'baseline_period': change['baseline'], 'value_source': measurement['sources']['value'],
                         'unit_source': measurement['sources']['unit'], 'source': _source(source, a, b)}
                qualifiers = {'comparison_basis': basis, 'change_direction': direction}
                qualifier_sources = {'comparison_basis': basis_source, 'change_direction': direction_source}
                if change['baseline']:
                    qualifiers['from_period'] = change['baseline']
                    qualifier_sources['from_period'] = _source(source, *change.span('baseline'))
                if antecedent and antecedent.get('qualifiers', {}).get('actor'):
                    qualifiers['actor'] = antecedent['qualifiers']['actor']
                    qualifier_sources['actor'] = copy.deepcopy(antecedent['qualifier_sources']['actor'])
                fact = emit(subject, subject_source, change[0], predicate_source, measurement, _source(source, a, b),
                            qualifiers, qualifier_sources, logic)
                fact['subject_binding_evidence'] = {'kind': 'explicit_local_metric' if explicit_subject else 'immediate_printed_year_on_year_antecedent',
                    'antecedent_source': copy.deepcopy(subject_source), 'relative_operator_source': basis_source,
                    'scope': list(scope)}
                if explicit_subject is None:
                    result['relations'].append({'type': 'cjk_year_on_year_subject_binding',
                    'left': {'subject': subject, 'role': 'antecedent_metric', 'scope': list(scope)},
                    'right': {'subject': subject, 'attribute': change[0], 'scope': list(scope)}, 'source': basis_source,
                        'object_anchor': None, 'binding_evidence': copy.deepcopy(fact['subject_binding_evidence'])})
                features.add('year_on_year_comparison')
                if explicit_subject is None:
                    features.add('same_subject_relative_clause')
            else:
                fail(a, b, 'cjk_year_on_year_ratio_measurement_unresolved')
            # A second relative clause cannot silently pass over a relation.
            antecedent = None
            continue
        antecedent = None
        ratio = re.fullmatch(r'(?P<scope>其中)?(?P<subject>[^，,。]+?)占(?P<denominator>[^，,。]+?)的(?P<measurement>.+)', text[a:b])
        if ratio:
            measurement = read_measurement_literal(ratio['measurement'], _source(source, a + ratio.start('measurement'), b))
            if not (_valid_metric(ratio['subject']) and _valid_metric(ratio['denominator'])
                    and measurement['matched'] and measurement['unit'] in {'%', '‰'}):
                fail(a, b, 'cjk_ratio_roles_unresolved')
                continue
            subject_source = _source(source, a + ratio.start('subject'), a + ratio.end('subject'))
            predicate_source = _source(source, a + ratio.end('subject'), a + ratio.end('subject') + 1)
            denominator_source = _source(source, a + ratio.start('denominator'), a + ratio.end('denominator'))
            qualifiers = {'denominator': ratio['denominator'], 'ratio_link': '的'}
            qualifier_sources = {'denominator': denominator_source,
                'ratio_link': _source(source, a + ratio.end('denominator'), a + ratio.end('denominator') + 1)}
            if ratio['scope']:
                qualifiers['membership_operator'] = ratio['scope']
                qualifier_sources['membership_operator'] = _source(source, a + ratio.start('scope'), a + ratio.end('scope'))
            logic = {'kind': 'quantity_assertion', 'subject': ratio['subject'], 'subject_source': subject_source,
                'predicate': '占', 'predicate_source': predicate_source, 'assertion_operator': 'share',
                'denominator': ratio['denominator'], 'denominator_source': denominator_source,
                'assertion_mode': 'actual', 'right_role': 'asserted_value', 'value_source': measurement['sources']['value'],
                'unit_source': measurement['sources']['unit'], 'source': _source(source, a, b)}
            antecedent = emit(ratio['subject'], subject_source, '占', predicate_source, measurement,
                _source(source, a, b), qualifiers, qualifier_sources, logic)
            features.add('quantity_assertion')
            continue
        if comparison:
            sa, sb = _trim(text, a, comparison.start())
            subject = text[sa:sb]
            metric_ok = _valid_metric(subject)
            measurement = read_measurement_literal(text[comparison.end():b], _source(source, comparison.end(), b))
            if metric_ok and measurement['matched']:
                subject_source = _source(source, sa, sb)
                operator_source = _source(source, comparison.start(), comparison.end())
                logic = {'kind': 'quantity_comparison', 'subject': subject, 'subject_source': subject_source,
                         'operator': _COMPARISONS[comparison[0]], 'operator_text': comparison[0], 'operator_source': operator_source,
                         'right_role': 'threshold', 'value_source': measurement['sources']['value'],
                         'unit_source': measurement['sources'].get('unit'), 'source': _source(source, a, b)}
                antecedent = emit(subject, subject_source, comparison[0], operator_source, measurement, _source(source, a, b),
                     {'comparison_operator': _COMPARISONS[comparison[0]]}, {'comparison_operator': operator_source}, logic)
                features.add('quantity_comparison')
            else:
                fail(a, b, 'cjk_metric_comparison_roles_unresolved')
            continue
        # Two bounded assertion frames. Realization precedes its metric;
        # equality follows it. Find a complete measurement at a metric boundary,
        # rather than swallowing currency or the action into the subject.
        candidates, realized = _assertion_candidates(text, source, a, b)
        if len(candidates) == 1:
            sa, sb, qa, qb, measurement = candidates[0]
            subject = text[sa:sb].strip()
            if (not _valid_metric(subject)
                    or _NON_ACTUAL.search(text[a:measurement['sources']['value']['text_span'][0] - source.get('text_span', [0])[0]])):
                fail(a, b, 'cjk_metric_assertion_scope_unresolved')
                continue
            subject_source, predicate_source = _source(source, sa, sb), _source(source, qa, qb)
            logic = {'kind': 'quantity_assertion', 'subject': subject, 'subject_source': subject_source,
                     'predicate': text[qa:qb], 'predicate_source': predicate_source,
                     'assertion_operator': 'realize' if realized else 'reach' if text[qa:qb] in {'达到', '達到'} else 'equal',
                     'assertion_mode': 'actual', 'right_role': 'asserted_value',
                     'value_source': measurement['sources']['value'], 'unit_source': measurement['sources'].get('unit'),
                     'source': _source(source, a, b)}
            antecedent = emit(subject, subject_source, text[qa:qb], predicate_source, measurement,
                              _source(source, a, b), {}, {}, logic)
            features.add('quantity_assertion')
        else:
            fail(a, b, 'cjk_metric_assertion_roles_unresolved' if _ASSERTION.search(text[a:b])
                 else 'cjk_metric_comparison_clause_unresolved' if part_index == 0 else 'cjk_measurement_tail_unresolved')
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
