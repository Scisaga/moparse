"""Bounded Chinese source syntax, reusing the language-neutral narrative AST.

No segmentation model, pronoun resolution, implicit actor or time inference is
used. Clear lexical clauses and printed operators can be exposed; ambiguous
nominal compounds, contextual prefixes and unsupported neighbors stay pending.
The shared emitter keeps conditions/restrictions out of business denominators
and represents an OR as one logical group, never as asserted AND members.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .cjk_measurement_requirements import read_cjk_measurements
from .narrative_requirements import _Reader, _Unknown

_ACTIONS = ('提供', '拥有', '擁有', '持有', '包括', '包含', '支持', '批准', '审查', '審查',
            '支付', '公布', '发布', '發布', '保存', '存储', '存儲', '检索', '檢索', '释放', '釋放', '是')
_VERB = re.compile('|'.join(sorted(_ACTIONS, key=len, reverse=True)))
_MODALS = {'能够': ('ability', 'positive'), '能夠': ('ability', 'positive'), '能': ('ability', 'positive'),
           '不能': ('ability', 'negative'), '不能够': ('ability', 'negative'), '不能夠': ('ability', 'negative'),
           '可以': ('may', 'positive'), '不可以': ('may', 'negative'),
           '必须': ('must', 'positive'), '必須': ('must', 'positive'),
           '应当': ('should', 'positive'), '應當': ('should', 'positive'), '不得': ('must', 'positive')}
_MODAL_SUFFIX = re.compile('(?P<modal>' + '|'.join(sorted(_MODALS, key=len, reverse=True)) + r')(?P<negative>不)?$')
_CONDITIONS = {'如果': 'if', '若': 'if', '除非': 'unless'}
_LEADING = re.compile('|'.join(_CONDITIONS))
_TRAILING = re.compile(r'[，,](?P<operator>除非|如果|若)')
_ACTION_JOIN = re.compile(r'(?:并且|並且|并|並|且|以及|和|或)(?=(?:不)?(?:' + _VERB.pattern + '))')
_CONTEXT = re.compile(r'由于|由於|因为|因為|因此|所以|为了|為了|以便|表示|认为|認為|宣布|指出')
_PREFIX = re.compile(r'从|從|面向|针对|針對|在|截至|据|據|于|於|\d{4}年')
_CONSEQUENCE = re.compile(r'^(?:则|則|否则|否則|那么|那麼|就|才)')
_ASPECT = re.compile(r'(?:将|將|已|曾|仍|还|還|会|會|正|再|未|本来|本來|一直|持续|持續)$')
_PRONOUN = re.compile(r'^(?:其|他们|他們|她们|她們|它们|它們|我们|我們|本公司|本集团|本集團|该公司|該公司|他|她|它|我)')
_PREDICATIVE = {'有效的', '无效的', '無效的', '可靠的', '安全的', '不安全的', '公开的', '公開的', '可用的'}
_NOUN_SUFFIX = re.compile(r'^(?:服务|服務|工具|系统|系統|平台|设备|設備|器|商|方案|功能|业务|業務)$')


def _units(text: str) -> list[tuple[int, int]]:
    """Chinese terminal punctuation does not require following whitespace."""
    spans, cursor = [], 0
    for match in re.finditer(r'[。！？!?；;]', text):
        if text[cursor:match.end()].strip():
            spans.append((cursor, match.end()))
        cursor = match.end()
    if text[cursor:].strip():
        spans.append((cursor, len(text)))
    return spans


class _CJKReader(_Reader):
    def trim(self, start, end):
        while start < end and self.text[start].isspace():
            start += 1
        while end > start and (self.text[end - 1].isspace() or self.text[end - 1] in '。！？!?；;，,'):
            end -= 1
        return start, end

    def nominal(self, start, end, *, actor=False):
        start, end = self.trim(start, end)
        value = self.text[start:end]
        if not value or re.search(r'[，,；;:：。！？!?“”"]', value):
            raise _Unknown('cjk_narrative_nominal_boundary_unresolved')
        if '的' in value and value not in _PREDICATIVE:
            raise _Unknown('cjk_narrative_relative_scope_unresolved')
        if any(word in value for word in _CONDITIONS) or _CONTEXT.search(value):
            raise _Unknown('cjk_narrative_embedded_scope_unresolved')
        if actor:
            if _PRONOUN.match(value):
                raise _Unknown('cjk_narrative_pronoun_identity_unresolved')
            if _PREFIX.match(value) or re.search(r'和|与|與|及|或|并|並|不再|没有|沒有|已经|已經|正在|曾经|曾經|必须|必須|应当|應當', value):
                raise _Unknown('cjk_narrative_subject_boundary_unresolved')
            if _CONSEQUENCE.match(value) or _ASPECT.search(value):
                raise _Unknown('cjk_narrative_operator_attachment_unresolved')
        for verb in _VERB.finditer(value):
            # A supported action at the beginning of a printed noun compound
            # (e.g. 存储服务) is not an additional finite predicate. Other
            # embedded actions need their own syntax, not an opaque object.
            if actor or verb.start() != 0 or not _NOUN_SUFFIX.fullmatch(value[verb.end():]):
                raise _Unknown('cjk_narrative_embedded_predicate_unresolved')
        if any(value.startswith(token) for token in _MODALS if len(token) > 1):
            raise _Unknown('cjk_narrative_embedded_modality_unresolved')
        if re.match(r'[（(]?[+−-]?\d', value):
            raise _Unknown('cjk_narrative_quantity_role_unresolved')
        return start, end

    def parse(self, start, end, actor=None, depth=0):
        if depth > 8:
            raise _Unknown('cjk_narrative_operator_depth_unresolved')
        if self.text[start:end].strip().endswith(('?', '？')) or re.search(r'是否|是不是|能否|可否|吗|嗎', self.text[start:end]):
            raise _Unknown('cjk_narrative_interrogative_scope_unresolved')
        start, end = self.trim(start, end)
        fragment = self.text[start:end]
        if not fragment:
            raise _Unknown('cjk_narrative_empty_clause')
        if re.search(r'[“”"\'‘’]', fragment):
            raise _Unknown('cjk_narrative_quoted_scope_unresolved')
        if _CONTEXT.search(fragment) or _PREFIX.match(fragment):
            raise _Unknown('cjk_narrative_context_attachment_unresolved')
        leading = _LEADING.match(self.text, start, end)
        if leading:
            comma = re.search(r'[，,]', self.text[leading.end():end])
            if comma is None:
                raise _Unknown('cjk_narrative_condition_boundary_unresolved')
            boundary = leading.end() + comma.start()
            operand = self.parse(leading.end(), boundary, depth=depth + 1)
            child = self.parse(boundary + 1, end, actor, depth + 1)
            bindings = [{'operator': _CONDITIONS[leading[0]], 'operator_span': [leading.start(), leading.end()],
                         'operand': operand}]
            if child['kind'] == 'conditions':
                bindings.extend(child['bindings'])
                child = child['child']
            return {'kind': 'conditions', 'bindings': bindings, 'child': child, 'span': [start, end]}
        trailing = list(_TRAILING.finditer(self.text, start, end))
        if trailing:
            child = self.parse(start, trailing[0].start(), actor, depth + 1)
            bindings = []
            for index, match in enumerate(trailing):
                limit = trailing[index + 1].start() if index + 1 < len(trailing) else end
                bindings.append({'operator': _CONDITIONS[match['operator']],
                                 'operator_span': [match.start('operator'), match.end('operator')],
                                 'operand': self.parse(match.end(), limit, depth=depth + 1)})
            return {'kind': 'conditions', 'bindings': bindings, 'child': child, 'span': [start, end]}
        return self.clause(start, end, actor)

    def clause(self, start, end, actor):
        verb = _VERB.search(self.text, start, end) if actor is None else _VERB.match(self.text, start, end)
        if verb is None:
            raise _Unknown('cjk_narrative_predicate_unresolved')
        negative, modal_negative, modality, modal_span = None, None, None, None
        if actor is None:
            a, b = self.trim(start, verb.start())
            modal = _MODAL_SUFFIX.search(self.text[a:b])
            if modal:
                modal_span = [a + modal.start('modal'), a + modal.end('modal')]
                modality, modal_polarity = _MODALS[modal['modal']]
                if modal_polarity == 'negative':
                    modal_negative = [modal_span[0], modal_span[0] + 1]
                if modal['modal'] == '不得':
                    negative = [modal_span[0], modal_span[0] + 1]
                if modal['negative']:
                    if negative or modal_negative:
                        raise _Unknown('cjk_narrative_multiple_negation_unresolved')
                    negative = [a + modal.start('negative'), a + modal.end('negative')]
                b = a + modal.start()
            elif self.text[a:b].endswith('不'):
                negative, b = [b - 1, b], b - 1
            actor = self.nominal(a, b, actor=True)
        joins = list(_ACTION_JOIN.finditer(self.text, verb.end(), end))
        if joins and (negative or modal_negative):
            raise _Unknown('cjk_narrative_negated_coordination_scope_unresolved')
        if joins:
            operators = {'or' if match[0] == '或' else 'and' for match in joins}
            if len(operators) != 1:
                raise _Unknown('cjk_narrative_mixed_coordination_unresolved')
            chunks, cursor = [], verb.start()
            for join in joins:
                chunks.append((cursor, join.start()))
                cursor = join.end()
            chunks.append((cursor, end))
            last = self.predicate(actor, *chunks[-1])
            shared = last['object_span'] if last['kind'] == 'proposition' else None
            children = [self.predicate(actor, a, b, shared=shared) for a, b in chunks[:-1]] + [last]
            child = {'kind': 'coordination', 'operator': next(iter(operators)), 'mode': 'actions',
                     'children': children, 'operator_spans': [[item.start(), item.end()] for item in joins],
                     'span': [start, end]}
        else:
            child = self.predicate(actor, verb.start(), end)
        if negative:
            if child['kind'] == 'coordination':
                raise _Unknown('cjk_narrative_negated_coordination_scope_unresolved')
            child = {'kind': 'negation', 'operator_span': negative, 'child': child, 'span': [start, end]}
        if modality:
            child = {'kind': 'modality', 'operator': modality, 'operator_text': self.text[slice(*modal_span)],
                     'operator_span': modal_span, 'polarity': 'negative' if modal_negative else 'positive',
                     'child': child, 'span': [start, end],
                     **({'negation_span': modal_negative} if modal_negative else {})}
        return child

    def predicate(self, actor, start, end, *, shared=None):
        start, end = self.trim(start, end)
        verb = _VERB.match(self.text, start, end)
        if verb is None:
            raise _Unknown('cjk_narrative_predicate_unresolved')
        a, b = self.trim(verb.end(), end)
        if a == b and shared is not None:
            a, b = shared
        spans, operator, separators = self.objects(a, b)
        children = []
        for a, b in spans:
            a, b = self.nominal(a, b)
            children.append({'kind': 'proposition', 'subject': self.text[slice(*actor)], 'subject_span': list(actor),
                             'attribute': verb[0], 'predicate': verb[0], 'predicate_span': [verb.start(), verb.end()],
                             'object': self.text[a:b], 'object_span': [a, b],
                             'role': 'entity_description' if verb[0] == '是' and self.text[a:b].startswith(('一', '某')) else 'description',
                             'span': [min(actor[0], start), max(end, b)]})
        return children[0] if len(children) == 1 else {
            'kind': 'coordination', 'operator': operator, 'mode': 'objects', 'children': children,
            'operator_spans': separators, 'span': [start, end]}

    def objects(self, start, end):
        if start == end:
            raise _Unknown('cjk_narrative_object_unresolved')
        fragment = self.text[start:end]
        # A bare 和/及/与 may be internal to a nominal word. Only list
        # punctuation or an explicit multi-character conjunction licenses AND.
        if re.search(r'和|及|与|與', fragment) and '、' not in fragment and not re.search(r'以及', fragment):
            raise _Unknown('cjk_narrative_nominal_coordination_unresolved')
        separators = list(re.finditer(r'以及|、|和|及|与|與|或者|或', fragment))
        operators = {'or' if item[0] in {'或', '或者'} else 'and' for item in separators}
        if len(operators) > 1:
            raise _Unknown('cjk_narrative_mixed_coordination_unresolved')
        if not separators:
            return [(start, end)], None, []
        spans, cursor = [], start
        for match in separators:
            a, b = self.trim(cursor, start + match.start())
            if a == b:
                raise _Unknown('cjk_narrative_enumeration_boundary_unresolved')
            spans.append((a, b))
            cursor = start + match.end()
        a, b = self.trim(cursor, end)
        if a == b:
            raise _Unknown('cjk_narrative_enumeration_boundary_unresolved')
        spans.append((a, b))
        return spans, next(iter(operators)), [[start + item.start(), start + item.end()] for item in separators]


def read_cjk_narrative(text: str, source: dict[str, Any], *, scope=()) -> dict[str, Any]:
    """Read explicit CJK clauses; completeness never certifies matcher support."""
    if not isinstance(text, str) or not isinstance(source, dict) or not isinstance(source.get('path'), str):
        raise ValueError('CJK narrative requires literal text and its actual source identity')
    parent_span = source.get('text_span')
    if parent_span is not None and (not isinstance(parent_span, (list, tuple)) or len(parent_span) != 2
                                   or any(type(value) is not int or value < 0 for value in parent_span)
                                   or parent_span[1] < parent_span[0]):
        raise ValueError('CJK narrative parent source span is invalid')
    reader = _CJKReader(text, source, scope)
    result = {'matched': bool(re.search(r'[\u3400-\u9fff]', text)), 'complete': False, 'semantic_complete': False,
              'facts': reader.facts, 'relations': reader.relations, 'semantic_operands': reader.operands,
              'semantic_operand_relations': reader.operand_relations, 'logic': [], 'unresolved': [],
              'blockers': [], 'pending_requirements': [], 'issues': [], 'text_atoms': [], 'controls': [],
              'text_projection_complete': True, 'required_matcher_features': [], 'consumed_spans': [],
              'source': copy.deepcopy(source), 'raw_text': text,
              'comparison_status': 'not_validated_by_this_source_reader'}
    if not result['matched']:
        return result
    result['text_atoms'] = [{'text': text, 'role': 'literal', 'source': reader.source_at(0, len(text))}]
    result['consumed_spans'] = [{'text': text, 'role': 'literal', 'span': [0, len(text)],
                                 'source': reader.source_at(0, len(text))}]
    for ordinal, (start, end) in enumerate(_units(text)):
        fragment = text[start:end]
        measurements = read_cjk_measurements(fragment, reader.source_at(start, end), scope=scope)
        if measurements['matched']:
            for fact in measurements['facts']:
                item = copy.deepcopy(fact)
                item['id'] = f'cjk_measurement:{len(reader.facts)}'
                reader.facts.append(item)
            reader.relations.extend(copy.deepcopy(measurements['relations']))
            reader.features.update(measurements['required_matcher_features'])
            result['logic'].extend(copy.deepcopy(measurements['logic']))
            for key in ('unresolved', 'blockers', 'pending_requirements', 'issues'):
                result[key].extend(copy.deepcopy(measurements[key]))
            continue
        pieces = [(start, end)]
        if not (_LEADING.match(fragment.lstrip()) or _TRAILING.search(fragment)
                or _CONTEXT.search(fragment) or _PREFIX.match(fragment.lstrip())):
            commas = list(re.finditer(r'[，,]', fragment))
            if commas:
                boundaries = [start, *[start + match.end() for match in commas], end]
                pieces = [(a, b - 1 if index < len(boundaries) - 2 else b)
                          for index, (a, b) in enumerate(zip(boundaries, boundaries[1:], strict=False))]
        for a, b in pieces:
            reader.record = f'{source}:{ordinal}:{a}'
            try:
                tree = reader.parse(a, b)
            except _Unknown as error:
                item = {'kind': 'cjk_narrative', 'reason': str(error), 'text': text[a:b],
                        'source': reader.source_at(a, b), 'scope': list(scope), 'layers': ['B', 'L'],
                        'category': 'software_unsupported'}
                result['unresolved'].append(item)
                result['blockers'].append(copy.deepcopy(item))
                result['pending_requirements'].append(copy.deepcopy(item))
                continue
            reader.annotate_sources(tree)
            result['logic'].append(tree)
            reader.emit(tree)
    result['complete'] = result['semantic_complete'] = bool(result['logic']) and not result['unresolved']
    result['required_matcher_features'] = sorted(reader.features)
    return result
