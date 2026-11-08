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
            '支付', '公布', '发布', '發布', '保存', '存储', '存儲', '检索', '檢索', '释放', '釋放', '是指', '是',
            '收購', '收购', '審批', '审批', '審閱', '审阅', '披露', '償還', '偿还', '投資', '投资', '增加', '減少', '减少')
_ACTIONS += ('建立', '健全', '制定', '制訂', '實施', '实施', '列示', '開展', '开展', '符合', '運行', '运行', '實現', '实现')
_ACTIONS += ('平抑', '穩定', '稳定', '防範', '防范')
_VERB = re.compile('|'.join(sorted(set(_ACTIONS), key=lambda word: (-len(word), word))))
_MANNER = re.compile(r'(?:持續|持续|不斷|不断|積極|积极|嚴格|严格|逐步|認真|认真|充分|均|共同|依法合規|依法合规|依法|合規|合规|完整準確全面|完整准确全面|科學|科学|穩步|稳步|高度|始終|始终|努力|及時|及时|定期|獨立|独立|書面|书面|主要)+')
_COMPLETED = re.compile(r'已經|已经|已')
_MODALS = {'能够': ('ability', 'positive'), '能夠': ('ability', 'positive'), '能': ('ability', 'positive'),
           '将': ('will', 'positive'), '將': ('will', 'positive'),
           '不能': ('ability', 'negative'), '不能够': ('ability', 'negative'), '不能夠': ('ability', 'negative'),
           '可以': ('may', 'positive'), '不可以': ('may', 'negative'),
           '必须': ('must', 'positive'), '必須': ('must', 'positive'),
           '应当': ('should', 'positive'), '應當': ('should', 'positive'), '不得': ('must', 'positive')}
_MODAL_SUFFIX = re.compile('(?P<modal>' + '|'.join(sorted(_MODALS, key=len, reverse=True)) + r')(?P<negative>不)?$')
_CONDITIONS = {'如果': 'if', '若': 'if', '除非': 'unless'}
_LEADING = re.compile('|'.join(_CONDITIONS))
_TRAILING = re.compile(r'[，,](?P<operator>除非|如果|若)')
_ACTION_JOIN = re.compile(r'(?:并且|並且|并|並|併|且|以及|和|或)(?=(?:' + _MANNER.pattern + r')?(?:不)?(?:' + _VERB.pattern + '))')
_CONTEXT = re.compile(r'由于|由於|因为|因為|因此|所以|为了|為了|以便|表示|认为|認為|宣布|指出')
_PREFIX = re.compile(r'从|從|面向|针对|針對|在|截至|据|據|于|於|\d{4}年')
_CONSEQUENCE = re.compile(r'^(?:则|則|否则|否則|那么|那麼|就|才)')
_ASPECT = re.compile(r'(?:将|將|已|曾|仍|还|還|会|會|正|再|未|本来|本來|一直|持续|持續)$')
_PRONOUN = re.compile(r'^(?:其|他们|他們|她们|她們|它们|它們|我们|我們|本公司|本集团|本集團|该公司|該公司|他|她|它|我)')
_LOCAL_SUBJECT = {'我们', '我們', '本公司', '本集团', '本集團'}
_PREDICATIVE = {'有效的', '无效的', '無效的', '可靠的', '安全的', '不安全的', '公开的', '公開的', '可用的'}
_NOUN_SUFFIX = re.compile(r'^(?:服务|服務|工具|系统|系統|平台|设备|設備|器|商|方案|功能|业务|業務)$')


def join_following_explanations(text, spans, *, source=None):
    """Keep an explicit following explanation within its original record."""
    joined = []
    for start, end in spans:
        supported = False
        if (joined and text[slice(*joined[-1])].rstrip().endswith(('；', ';'))
                and '\n\n' not in text[joined[-1][0]:end]):
            from .cjk_circumstances import trailing_cause

            supported = trailing_cause(text[slice(*joined[-1])].rstrip('；;')) is not None
        if (joined and isinstance(source, dict) and source.get('path')
                and '\n\n' not in text[joined[-1][0]:end]
                and re.search(r'[\u3400-\u9fff]', text[slice(*joined[-1])])
                and re.match(r'(?:主要|部分)?(?:歸因於|归因于|由于|由於|因为|因為)', text[start:end].lstrip())):
            a, b = joined[-1]
            offset = source.get('text_span', [0])[0]
            origin = {**copy.deepcopy(source), 'text_span': [offset + a, offset + b]}
            supported |= read_cjk_measurements(text[a:b], origin)['complete']
        if supported:
            prior = joined.pop()
            joined.append((prior[0], end))
        else:
            joined.append((start, end))
    return joined


def _units(text: str, source=None) -> list[tuple[int, int]]:
    """Chinese terminal punctuation does not require following whitespace."""
    spans, cursor = [], 0
    for match in re.finditer(r'[。！？!?；;]', text):
        if text[cursor:match.end()].strip():
            spans.append((cursor, match.end()))
        cursor = match.end()
    if text[cursor:].strip():
        spans.append((cursor, len(text)))
    return join_following_explanations(text, spans, source=source)


class _CJKReader(_Reader):
    def emit(self, node, context=None):
        if node.get('kind') == 'proposition' and node.get('lexical_qualifiers', {}).get('aspect'):
            self.features.add('active_aspect_scope')
        if node['kind'] == 'cjk_measurement_sequence':
            from .cjk_circumstances import emit_measurements

            emit_measurements(self, node, context)
            return
        super().emit(node, context)

    def trim(self, start, end):
        while start < end and self.text[start].isspace():
            start += 1
        while end > start and (self.text[end - 1].isspace() or self.text[end - 1] in '。！？!?；;，,'):
            end -= 1
        return start, end

    def nominal(self, start, end, *, actor=False):
        start, end = self.trim(start, end)
        value = self.text[start:end]
        from .cjk_circumstances import CJK_TITLE, FINANCIAL_NOMINAL, NOMINAL_TERM, outside_titles

        if CJK_TITLE.fullmatch(value):
            return start, end
        if not value or re.search(r'[，,；;:：。！？!?“”"]', value):
            raise _Unknown('cjk_narrative_nominal_boundary_unresolved')
        structured = None
        if ('的' in value and value not in _PREDICATIVE or FINANCIAL_NOMINAL.fullmatch(value)
                or NOMINAL_TERM.fullmatch(value) or actor and re.search(r'及|與|与|和', value)):
            from .cjk_circumstances import nominal
            from .cjk_measurement_requirements import _valid_metric

            if actor and '的' not in value and re.search(r'及|與|与|和', value) and not _valid_metric(value):
                raise _Unknown('cjk_narrative_subject_boundary_unresolved')
            structured = nominal(self, start, end)
        if any(word in value for word in _CONDITIONS) or _CONTEXT.search(value):
            raise _Unknown('cjk_narrative_embedded_scope_unresolved')
        if actor:
            if _PRONOUN.match(value) and value not in _LOCAL_SUBJECT:
                raise _Unknown('cjk_narrative_pronoun_identity_unresolved')
            if _PREFIX.match(value) or re.search(r'或|并|並|不再|没有|沒有|已经|已經|正在|曾经|曾經|必须|必須|应当|應當', value) or not structured and re.search(r'和|与|與|及', value):
                raise _Unknown('cjk_narrative_subject_boundary_unresolved')
            institution = re.search(r'(?:董事|股東|股东|委員|委员)會$|(?:董事|股东|委员)会$', value)
            if _CONSEQUENCE.match(value) or _ASPECT.search(value) and not institution:
                raise _Unknown('cjk_narrative_operator_attachment_unresolved')
        for verb in outside_titles(value, _VERB.finditer(value)):
            # A supported action at the beginning of a printed noun compound
            # (e.g. 存储服务) is not an additional finite predicate. Other
            # embedded actions need their own syntax, not an opaque object.
            def contains_operator(node, verb=verb):
                if isinstance(node, dict):
                    if any(a <= start + verb.start() and start + verb.end() <= b for a, b in
                           [node[k] for k in ('marker_span', 'predicate_span') if k in node]):
                        return True
                    if node.get('lexical_role') in {'financial_nominal', 'nominal_term'}:
                        a, b = node['head_span']
                        if a <= start + verb.start() and start + verb.end() <= b:
                            return True
                    return any(contains_operator(v) for v in node.values())
                return isinstance(node, list) and any(contains_operator(v) for v in node)
            if not (structured and contains_operator(structured)) and (actor or verb.start() != 0 or not _NOUN_SUFFIX.fullmatch(value[verb.end():])):
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
        ordinal = re.match(r'(?P<marker>[A-Za-z][.)])\s+', fragment)
        if ordinal:
            marker = [start + ordinal.start('marker'), start + ordinal.end('marker')]
            child = self.parse(start + ordinal.end(), end, actor, depth + 1)
            return {'kind': 'discourse_scope', 'operator': 'enumeration', 'role': 'item_label',
                    'marker': ordinal['marker'], 'marker_span': marker, 'operator_span': marker,
                    'separator_span': [marker[1], start + ordinal.end()], 'child': child, 'span': [start, end]}
        equation = re.fullmatch(r'(?P<metric>[^=：:，,]+)=(?P<expression>.+)', fragment)
        if equation:
            from .cjk_circumstances import arithmetic_nominal, nominal
            from .cjk_measurement_requirements import _valid_metric

            middle = start + equation.end('metric')
            if not _valid_metric(equation['metric']):
                raise _Unknown('cjk_formula_metric_unsupported')
            return {'kind': 'proposition', 'subject': equation['metric'], 'subject_span': [start, middle],
                    'subject_phrase': nominal(self, start, middle), 'attribute': '=', 'predicate': '=',
                    'predicate_span': [middle, middle + 1], 'object': equation['expression'], 'object_span': [middle + 1, end],
                    'object_phrase': arithmetic_nominal(self, middle + 1, end), 'role': 'formula_definition', 'span': [start, end]}
        from .cjk_circumstances import parse_composed

        composed = parse_composed(self, start, end)
        if composed is not None:
            return composed
        from .temporal_prose_requirements import read_cjk_temporal

        temporal = read_cjk_temporal(self.text, self.source, start, end)
        if temporal:
            child = self.parse(temporal['body_start'], end, actor, depth + 1)
            return {'kind': 'temporal_scope', **{k: v for k, v in temporal.items() if k not in {'body_start', 'actor_end'}},
                    'child': child, 'span': [start, end]}
        basis = re.match(r'(?P<actor>[^，,]+?)(?P<marker>根據|根据)(?P<context>[^，,]+)[，,]', fragment)
        if basis:
            owner = self.nominal(start, start + basis.end('actor'), actor=True)
            a, b = start + basis.start('context'), start + basis.end('context')
            from .cjk_circumstances import nominal

            phrase = nominal(self, a, b)
            child = self.parse(start + basis.end(), end, actor=owner, depth=depth + 1)
            marker = [start + basis.start('marker'), start + basis.end('marker')]
            return {'kind': 'fronted_context', 'preposition': basis['marker'], 'operator': 'according_to', 'role': 'basis',
                    'context': basis['context'], 'context_phrase': phrase, 'context_span': [a, b],
                    'preposition_span': marker, 'operator_span': marker, 'separator_span': [b, b + 1],
                    'child': child, 'span': [start, end]}
        if re.search(r'[“”"\'‘’]', fragment):
            raise _Unknown('cjk_narrative_quoted_scope_unresolved')
        if _CONTEXT.search(fragment) or _PREFIX.match(fragment):
            raise _Unknown('cjk_narrative_context_attachment_unresolved')
        commas = list(re.finditer(r'[，,]', fragment))
        if commas and not _LEADING.match(fragment) and not _TRAILING.search(fragment):
            # Only complete local clauses are admitted. An explicitly printed
            # later subject replaces the common actor; no context crosses a
            # record, heading or sentence boundary here.
            boundaries = [start, *[start + m.end() for m in commas], end]
            children, previous_actor = [], actor
            for index, (a, b) in enumerate(zip(boundaries, boundaries[1:], strict=False)):
                limit = b - 1 if index < len(boundaries) - 2 else b
                prefix = _MANNER.match(self.text, a, limit)
                head = prefix.end() if prefix else a
                own_actor = previous_actor if _VERB.match(self.text, head, limit) else None
                child = self.parse(a, limit, own_actor, depth + 1)
                leaves = list(self._main_propositions(child))
                if leaves and all(leaf.get('subject_span') == leaves[0].get('subject_span') for leaf in leaves):
                    previous_actor = leaves[0]['subject_span']
                children.append(child)
            return {'kind': 'coordination', 'operator': 'and', 'mode': 'clauses', 'children': children,
                    'operator_spans': [[start + m.start(), start + m.end()] for m in commas], 'span': [start, end]}
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

    @staticmethod
    def _main_propositions(tree):
        if tree.get('kind') == 'proposition':
            yield tree
        elif tree.get('kind') == 'coordination':
            for child in tree['children']:
                yield from _CJKReader._main_propositions(child)
        elif isinstance(tree.get('child'), dict):
            yield from _CJKReader._main_propositions(tree['child'])

    def clause(self, start, end, actor):
        continuation_negative = actor is not None and self.text[start:end].startswith('不')
        from .cjk_circumstances import outside_titles

        body_start = start + int(continuation_negative)
        head = body_start
        for expression in (_COMPLETED, _MANNER, _COMPLETED):
            token = expression.match(self.text, head, end)
            if token:
                head = token.end()
        verb = next(iter(outside_titles(self.text, _VERB.finditer(self.text, start, end))), None) if actor is None else _VERB.match(self.text, head, end)
        predicate_start = verb.start() if actor is None and verb else body_start
        if verb is None:
            raise _Unknown('cjk_narrative_predicate_unresolved')
        negative, modal_negative, modality, modal_span = [start, start + 1] if continuation_negative else None, None, None, None
        temporal = None
        if actor is None:
            a, b = self.trim(start, verb.start())
            completed = next((m for m in _COMPLETED.finditer(self.text, a, b) if m.end() == b), None)
            if completed:
                b = completed.start()
            manner = next((m for m in _MANNER.finditer(self.text, a, b) if m.end() == b), None)
            if manner:
                b = manner.start()
            if not completed:
                completed = next((m for m in _COMPLETED.finditer(self.text, a, b) if m.end() == b), None)
                if completed:
                    b = completed.start()
            modal = _MODAL_SUFFIX.search(self.text[a:b])
            if modal and modal['modal'] == '能' and self.text[a:b].endswith(
                    ('储能', '儲能', '智能', '性能', '功能', '效能', '本能', '潜能', '潛能')):
                modal = None  # A complete nominal ending is not an ability.
            if modal:
                if modal['modal'] in {'将', '將'} and not modal['negative']:
                    # Restore the existing explicit 将不 polarity contract;
                    # positive future assertion semantics remain unsupported.
                    raise _Unknown('cjk_narrative_future_scope_unresolved')
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
            from .temporal_prose_requirements import read_cjk_temporal

            temporal = read_cjk_temporal(self.text, self.source, a, b, trailing=True)
            if temporal and temporal['actor_end'] > a:
                b = temporal['actor_end']
            elif temporal:
                raise _Unknown('cjk_narrative_temporal_actor_unresolved')
            if a == b and start > 0 and not self.text[:start].rstrip().endswith(('。', '；', ';')):
                raise _Unknown('cjk_narrative_subject_boundary_unresolved')
            actor = self.nominal(a, b, actor=True) if a < b else (a, b)
        joins = [] if verb[0] == '是指' else list(_ACTION_JOIN.finditer(self.text, verb.end(), end))
        if joins and (negative or modal_negative):
            raise _Unknown('cjk_narrative_negated_coordination_scope_unresolved')
        if joins:
            operators = {'or' if match[0] == '或' else 'and' for match in joins}
            if len(operators) != 1:
                raise _Unknown('cjk_narrative_mixed_coordination_unresolved')
            chunks, cursor = [], predicate_start
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
            child = self.predicate(actor, predicate_start, end)
        if actor is not None and ('manner' in locals() and manner or 'completed' in locals() and completed):
            def qualify(node):
                if node['kind'] == 'proposition':
                    q = node.setdefault('lexical_qualifiers', {})
                    spans = node.setdefault('lexical_qualifier_spans', {})
                    if manner:
                        q['manner'] = manner[0]
                        spans['manner'] = list(manner.span())
                    if completed:
                        q['aspect'] = 'perfect'
                        if 'aspect' in spans:
                            spans['completion_link'] = list(completed.span())
                        else:
                            spans['aspect'] = list(completed.span())
                elif node['kind'] == 'coordination':
                    for member in node['children']:
                        qualify(member)
            qualify(child)
        if negative:
            if child['kind'] == 'coordination':
                raise _Unknown('cjk_narrative_negated_coordination_scope_unresolved')
            child = {'kind': 'negation', 'operator_span': negative, 'child': child, 'span': [start, end]}
        if modality:
            child = {'kind': 'modality', 'operator': modality, 'operator_text': self.text[slice(*modal_span)],
                     'operator_span': modal_span, 'polarity': 'negative' if modal_negative else 'positive',
                     'child': child, 'span': [start, end],
                     **({'negation_span': modal_negative} if modal_negative else {})}
        if temporal:
            child = {'kind': 'temporal_scope', **{k: v for k, v in temporal.items() if k not in {'body_start', 'actor_end'}},
                     'child': child, 'span': [start, end]}
        return child

    def predicate(self, actor, start, end, *, shared=None):
        start, end = self.trim(start, end)
        completed_prefix = _COMPLETED.match(self.text, start, end)
        if completed_prefix:
            start = completed_prefix.end()
        manner = _MANNER.match(self.text, start, end)
        if manner:
            start = manner.end()
        if not completed_prefix:
            completed_prefix = _COMPLETED.match(self.text, start, end)
            if completed_prefix:
                start = completed_prefix.end()
        verb = _VERB.match(self.text, start, end)
        if verb is None:
            raise _Unknown('cjk_narrative_predicate_unresolved')
        a, b = self.trim(verb.end(), end)
        completed = a < b and self.text[a] == '了'
        if completed:
            a += 1
        if a == b and shared is not None:
            a, b = shared
        intransitive = a == b and verb[0] in {'經營', '经营', '運行', '运行'}
        spans, operator, separators = ([(a, b)], None, []) if verb[0] == '是指' or intransitive else self.objects(a, b)
        children = []
        for a, b in spans:
            a, b = self.nominal(a, b) if a < b else (a, b)
            from .cjk_circumstances import nominal
            from .nominal_syntax import nominal_phrase

            def phrase(lo, hi):
                node = nominal(self, lo, hi)
                # Bare lexical nouns retain the existing language-neutral NP
                # schema. Only actually decomposed Chinese constructions use
                # their additional typed dependency representation.
                bare = not any(node.get(key) for key in ('parts', 'lexical_role', 'designation', 'quantifier'))
                return nominal_phrase(self, lo, hi) if bare else node

            children.append({'kind': 'proposition', 'subject': self.text[slice(*actor)], 'subject_span': list(actor) if actor[0] < actor[1] else None,
                             'subject_phrase': phrase(*actor) if actor[0] < actor[1] else None,
                             'attribute': verb[0], 'predicate': verb[0], 'predicate_span': [verb.start(), verb.end()],
                             'object': self.text[a:b], 'object_span': [a, b],
                             'object_phrase': phrase(a, b) if a < b else None,
                             **({'lexical_qualifiers': {**({'manner': manner[0]} if manner else {}), **({'aspect': 'perfect'} if completed or completed_prefix else {})},
                                 'lexical_qualifier_spans': {**({'manner': list(manner.span())} if manner else {}),
                                     **({'aspect': list(completed_prefix.span())} if completed_prefix else {'aspect': [verb.end(), verb.end() + 1]} if completed else {}),
                                     **({'completion_link': [verb.end(), verb.end() + 1]} if completed and completed_prefix else {})}}
                                if manner or completed or completed_prefix else {}),
                             'role': 'entity_description' if verb[0] == '是' and self.text[a:b].startswith(('一', '某')) else 'description',
                             'span': [min(actor[0], start), max(end, b)]})
        return children[0] if len(children) == 1 else {
            'kind': 'coordination', 'operator': operator, 'mode': 'objects', 'children': children,
            'operator_spans': separators, 'span': [start, end]}

    def objects(self, start, end):
        if start == end:
            raise _Unknown('cjk_narrative_object_unresolved')
        fragment = self.text[start:end]
        from .cjk_circumstances import CJK_TITLE, outside_titles

        if CJK_TITLE.fullmatch(fragment):
            return [(start, end)], None, []
        if re.fullmatch(r'(?:[^與与]+)?[與与].+?(?:相關|相关)的.+', fragment):
            return [(start, end)], None, []
        if re.fullmatch(r'.+的(?:目標|目标)', fragment):
            return [(start, end)], None, []
        if re.fullmatch(r'(?:本公司|本集[團团])(?:19|20)\d{2}年[及和].+', fragment) or re.fullmatch(
                r'[^類类、及和]+[類类](?:[及和、][^類类、及和]+[類类])+.+(?:[業业]務|业务)', fragment):
            return [(start, end)], None, []
        # A bare 和/及/与 may be internal to a nominal word. Only list
        # punctuation or an explicit multi-character conjunction licenses AND.
        if re.search(r'和|及|与|與', fragment) and '、' not in fragment and not re.search(r'以及', fragment) and not CJK_TITLE.search(fragment):
            raise _Unknown('cjk_narrative_nominal_coordination_unresolved')
        separators = outside_titles(fragment, re.finditer(r'以及|、|和|及|与|與|或者|或', fragment))
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

    def adopt_measurements(reading):
        identifiers = {}
        for fact in reading['facts']:
            existing = next((f for f in reader.facts if all(f.get(key) == fact.get(key)
                for key in ('subject_source', 'predicate_source', 'object_source'))), None)
            if existing is not None:
                identifiers[fact['id']] = existing['id']
                continue
            item = copy.deepcopy(fact)
            item['id'] = f'cjk_measurement:{len(reader.facts)}'
            identifiers[fact['id']] = item['id']
            reader.facts.append(item)
        for edge in reading['relations']:
            item = copy.deepcopy(edge)
            if item.get('fact_id') in identifiers:
                item['fact_id'] = identifiers[item['fact_id']]
            if item not in reader.relations:
                reader.relations.append(item)
        reader.features.update(reading['required_matcher_features'])
        for key in ('logic', 'unresolved', 'blockers', 'pending_requirements', 'issues'):
            for item in reading[key]:
                if item not in result[key]:
                    result[key].append(copy.deepcopy(item))

    for ordinal, (start, end) in enumerate(_units(text, source)):
        fragment = text[start:end]
        from .explicit_reference_requirements import read_explicit_references

        navigation = read_explicit_references(fragment, reader.source_at(start, end), scope=scope)
        if navigation['complete'] and navigation['references'][0].get('owner_roles'):
            # The owning prose sequence emits the independently read reference
            # edges. A difference explanation is not an asserted difference
            # amount, direction, or a new unconditional business proposition.
            reader.features.add('explicit_reference_binding')
            continue
        from .cjk_circumstances import trailing_cause

        composed = bool(re.match(r'借助|通过|随着|(?:同时)?受益于|由于|因为|为了|(?:持续)?(?:加大|坚持)', fragment.lstrip())
                        or re.search(r'(?:主要)?受.+的影响', fragment) or trailing_cause(fragment))
        measurements = read_cjk_measurements(fragment, reader.source_at(start, end), scope=scope)
        if measurements['matched'] and not composed:
            adopt_measurements(measurements)
            continue
        from .cjk_circumstances import composition_spans

        pieces = composition_spans(text, start, end) if composed else [(start, end)]
        from .temporal_prose_requirements import read_cjk_temporal

        temporal = read_cjk_temporal(text, source, start, end)
        if not (composed or _LEADING.match(fragment.lstrip()) or _TRAILING.search(fragment)
                or temporal or re.match(r'[A-Za-z][.)]\s+', fragment.lstrip())
                or _CONTEXT.search(fragment) or _PREFIX.match(fragment.lstrip())):
            commas = list(re.finditer(r'[，,]', fragment))
            if commas:
                boundaries = [start, *[start + match.end() for match in commas], end]
                pieces = [(a, b - 1 if index < len(boundaries) - 2 else b)
                          for index, (a, b) in enumerate(zip(boundaries, boundaries[1:], strict=False))]
        failed, definition_actor, omitted_group = False, None, False
        for piece_index, (a, b) in enumerate(pieces):
            reader.record = f'{source}:{ordinal}:{a}'
            try:
                if definition_actor and re.match(r'(?:不)?包括', text[a:b].lstrip()):
                    tree = reader.parse(a, b, actor=definition_actor)
                    reader.annotate_sources(tree)
                    reader.emit(tree)
                elif omitted_group and _VERB.match(text, a, b):
                    tree = reader.parse(a, b, actor=(a, a))
                    reader.annotate_sources(tree)
                    reader.emit(tree)
                else:
                    tree = reader.interpret(a, b)
            except _Unknown as error:
                failed = True
                item = {'kind': 'cjk_narrative', 'reason': str(error), 'text': text[a:b],
                        'source': reader.source_at(a, b), 'scope': list(scope), 'layers': ['B', 'L'],
                        'category': 'software_unsupported'}
                if str(error) in {'cjk_causal_scope_evidence_unresolved', 'cjk_causal_attachment_declared_uncertain'}:
                    changes = [c['source'] for tree in measurements['logic'] for c in tree.get('clauses', [])
                               if c.get('kind') == 'year_on_year_change']
                    item.update(category='source_attachment_ambiguity' if str(error) == 'cjk_causal_attachment_declared_uncertain' else 'software_unsupported',
                                missing_evidence='printed shared or local cause scope within this closed sentence',
                                attachment_hypotheses=[{'scope': 'latter_change', 'target_sources': changes[-1:]},
                                                       {'scope': 'joint_changes', 'target_sources': changes}])
                    if str(error) == 'cjk_causal_attachment_declared_uncertain':
                        item['attachment_hypotheses'].insert(0, {'scope': 'former_change', 'target_sources': changes[:1]})
                result['unresolved'].append(item)
                result['blockers'].append(copy.deepcopy(item))
                result['pending_requirements'].append(copy.deepcopy(item))
                continue
            result['logic'].append(tree)
            if piece_index == 0:
                main = list(reader._main_propositions(tree))
                omitted_group = bool(main) and all(not n.get('subject') and n.get('subject_span') is None for n in main)
            if tree.get('kind') == 'proposition' and tree.get('attribute') == '是指':
                definition_actor = tree['subject_span']
        if composed and failed and measurements['facts']:
            # An unsupported introduction must not erase quantities the
            # independent measurement reader actually exposed. The complete
            # source and every unhandled clause remain explicitly pending.
            cause = trailing_cause(fragment)
            prefix = (read_cjk_measurements(fragment[:cause.start()], reader.source_at(start, start + cause.start()), scope=scope)
                      if cause else None)
            adopt_measurements(prefix if prefix and prefix['complete'] else measurements)
    result['complete'] = result['semantic_complete'] = bool(result['logic']) and not result['unresolved']
    result['required_matcher_features'] = sorted(reader.features)
    return result
