"""Bounded source-only narrative syntax with explicit operator attachment.

Leaves are grammatical propositions, not independent assertions when enclosed
by ability, reporting, relative, condition or alternative operators. Conditions
and restrictions belong to semantic_operands, not extra business questions. OR
creates one structured logical_group requirement with its leaves as operands.
The full tree and source spans are mandatory evidence for a downstream matcher.
This reader does not claim those matcher features have already been integrated.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .action_forms import NARRATIVE_ACTION_FORMS, NARRATIVE_PAST_FORMS
from .prose_requirements import _sentence_spans

_ACTIONS = dict(NARRATIVE_ACTION_FORMS)
_PAST = set(NARRATIVE_PAST_FORMS)
_VERB = re.compile(r"(?<![\w-])(?:" + "|".join(sorted(_ACTIONS, key=len, reverse=True)) + r")(?![\w-])", re.I)
_PRIMARY = re.compile(r"\b(?:is\s+(?:not\s+)?able\s+to|are\s+(?:not\s+)?able\s+to|"
                      r"was\s+(?:not\s+)?able\s+to|were\s+(?:not\s+)?able\s+to|"
                      r"cannot|shall|must|may|can|will|should|could|would|is|are|was|were)\b", re.I)
_MODAL = re.compile(r"(?:cannot|shall|must|may|can|will|should|could|would)\b", re.I)
_ABILITY = re.compile(r"(?:is|are|was|were)\s+(?:not\s+)?able\s+to\b", re.I)
_CONDITION = re.compile(r"\b(?:only if|unless|except when|except if|if)\b", re.I)
_REPORT = re.compile(r"(?P<subject>.+?)\s+(?:(?P<aux>do|does|did)\s+)?(?P<negative>not\s+)?"
                     r"(?P<verb>say|says|said|report|reports|reported|state|states|stated)\s+that\s+", re.I)
_RELATIVE = re.compile(r"\b(?:that|which|who)\b", re.I)
_ACTION_JOIN = re.compile(r"\s+(?P<operator>and|or)\s+(?=(?:not\s+|never\s+)?(?:"
                          + "|".join(sorted(_ACTIONS, key=len, reverse=True)) + r")\b)", re.I)
_UNSUPPORTED = re.compile(r"\b(?:because|although|whereas|while|whether|whose|whom|therefore|otherwise)\b|[:：;；]", re.I)
_REPORT_ACTIONS = {"say": "say", "says": "say", "said": "say", "report": "report", "reports": "report",
                   "reported": "report", "state": "state", "states": "state", "stated": "state"}
_REPORT_PAST = {'said', 'reported', 'stated'}
_CLAUSE_JOIN = re.compile(r'\b(?P<operator>and|or)\b', re.I)
_CONTRAST = re.compile(r'\bbut\b', re.I)
_SHARED_AUXILIARY_JOIN = re.compile(r'\b(?P<operator>and|or)\b\s+(?=(?:do|does|did)\b)', re.I)


class _Unknown(ValueError):
    def __init__(self, reason, *, span=None):
        super().__init__(reason)
        self.span = span


class _Reader:
    def __init__(self, text: str, source: dict[str, Any], scope):
        from .quoted_nominal import scan_quoted_nominals

        self.text, self.source, self.scope = text, copy.deepcopy(source), list(scope)
        self.features: set[str] = set()
        self.quoted = scan_quoted_nominals(text, source)
        self.syntax = self.quoted['syntax_text']
        self.fronted_scopes = []
        if self.quoted['matched']:
            self.features.add('quoted_nominal_scope')
        self.facts: list[dict[str, Any]] = []
        self.relations: list[dict[str, Any]] = []
        self.operands: list[dict[str, Any]] = []
        self.operand_relations: list[dict[str, Any]] = []
        self.unknown_nodes: list[dict[str, Any]] = []
        self.record = ""

    def source_at(self, start: int, end: int) -> dict[str, Any]:
        parent = self.source.get("text_span", [0, 0])
        offset = parent[0] if isinstance(parent, (list, tuple)) and len(parent) == 2 else 0
        return {**copy.deepcopy(self.source), "text_span": [offset + start, offset + end]}

    def interpret(self, start: int, end: int):
        """Commit a clause only after all of its role evidence was emitted.

        Source-role checks can discover unsupported syntax after parsing, for
        example a quoted CJK role in a shared emitter. Keep valid neighbors,
        but never leak the first leaf of a failed compound clause as a fact.
        """
        banks = (self.facts, self.relations, self.operands, self.operand_relations, self.unknown_nodes)
        lengths = [len(bank) for bank in banks]
        try:
            tree = self.parse(start, end)
            self.annotate_sources(tree)
            self.emit(tree)
        except _Unknown:
            for bank, length in zip(banks, lengths, strict=True):
                del bank[length:]
            raise
        return tree

    def trim(self, start: int, end: int) -> tuple[int, int]:
        while start < end and self.text[start].isspace():
            start += 1
        while end > start and (self.text[end - 1].isspace() or self.text[end - 1] in ".!?。！？,，"):
            end -= 1
        return start, end

    def nominal(self, start: int, end: int, *, actor=False) -> tuple[int, int]:
        from .quoted_nominal import quoted_role_evidence

        start, end = self.trim(start, end)
        _, reason = quoted_role_evidence(self.text, start, end, self.quoted, role='subject' if actor else 'object')
        if reason:
            raise _Unknown(reason)
        value = self.syntax[start:end]
        if not value or _UNSUPPORTED.search(value) or _PRIMARY.search(value) or _RELATIVE.search(value):
            raise _Unknown("narrative_nominal_boundary_unresolved")
        if re.search(r"\b(?:to\s+[A-Za-z]+|do|does|did|not|never)\b", value, re.I):
            raise _Unknown("narrative_embedded_predicate_unresolved")
        if actor and re.search(r"[,，]|\b(?:reported|reports|said|says)\b", value, re.I):
            raise _Unknown("narrative_subject_boundary_unresolved")
        if actor and re.search(r'\b(?:and|or)\b', value, re.I):
            from .nominal_syntax import nominal_phrase

            # Coordination belongs to a bounded subject NP. Do not distribute
            # one assertion into multiple inferred actors or opaque text.
            phrase = nominal_phrase(self, start, end)
            if not phrase.get('coordination') or phrase.get('prepositional_complements'):
                raise _Unknown('narrative_subject_coordination_attachment_unresolved')
        if actor and (re.match(r"(?:How|Why|When|What|Whether|In|Under|During|After|Before|From|According)\b", value, re.I)
                      or re.search(r"\bto\b", value, re.I)):
            raise _Unknown("narrative_subject_scope_unresolved")
        if actor and value.lower() in {'there', 'here'}:
            raise _Unknown('narrative_existential_subject_unresolved')
        if actor and value.strip().lower() in {'a', 'an', 'the', 'our', 'their', 'its', 'my', 'your', 'this', 'these', 'those'}:
            raise _Unknown('narrative_subject_head_unresolved')
        return start, end

    def parse(self, start: int, end: int, actor=None, depth=0):
        if depth > 8:
            raise _Unknown("narrative_operator_depth_unresolved")
        start, end = self.trim(start, end)
        if start == end:
            raise _Unknown("narrative_empty_clause")
        fragment = self.syntax[start:end]
        from .infinitival_syntax import read_discourse_scope

        discourse = read_discourse_scope(self, start, end, actor, depth)
        if discourse is not None:
            return discourse
        from .fronted_nominal_context import read_fronted_nominal_context, read_fronted_operation
        from .temporal_prose_requirements import read_temporal_prefix

        operation = read_fronted_operation(self, start, end, actor, depth)
        if operation is not None:
            return operation

        temporal = read_temporal_prefix(self.syntax, self.source, start, end)
        fronted = None if temporal else read_fronted_nominal_context(
            self.text, self.source, start, end, syntax_text=self.syntax, quoted=self.quoted)
        if temporal:
            self.features.add('temporal_prose_scope')
        if fronted is not None:
            # A known family remains claimed even when its original child or
            # nominal boundary is unresolved; no opaque fallback may erase it.
            self.features.add('fronted_nominal_context')
            self.fronted_scopes.append({**copy.deepcopy(fronted), 'source': self.source_at(start, end)})
        errors = [item for item in self.quoted['errors'] if item['span'][0] < end and item['span'][1] > start]
        if errors:
            raise _Unknown(errors[0]['reason'])
        unknown_quotes = [item for item in self.quoted['scopes'] if item['span'][0] < end and item['span'][1] > start
                          and not item['nominal_complete']]
        if unknown_quotes:
            raise _Unknown(unknown_quotes[0]['reason'])
        if temporal:
            self.features.add('temporal_prose_scope')
            child = self.parse(temporal["body_start"], end, actor, depth + 1)

            def has_temporal(value):
                if isinstance(value, dict):
                    return value.get("kind") == "temporal_scope" or any(has_temporal(item) for item in value.values())
                return isinstance(value, list) and any(has_temporal(item) for item in value)

            if has_temporal(child):
                raise _Unknown("narrative_multiple_temporal_scopes_unresolved")
            return {"kind": "temporal_scope", **{key: value for key, value in temporal.items() if key != "body_start"},
                    "child": child, "span": [start, end]}
        if fronted is not None:
            if not fronted['complete']:
                raise _Unknown(fronted['reason'])
            child = self.parse(fronted['body_start'], end, actor, depth + 1)

            def has_fronted(value):
                if isinstance(value, dict):
                    return value.get('kind') == 'fronted_context' or any(has_fronted(item) for item in value.values())
                return isinstance(value, list) and any(has_fronted(item) for item in value)

            if has_fronted(child):
                raise _Unknown('fronted_nominal_nested_scope_unresolved')
            return {key: value for key, value in fronted.items() if key not in {'matched', 'complete', 'body_start'}} | {'child': child}
        contrasts = list(_CONTRAST.finditer(self.syntax, start, end))
        if contrasts:
            if len(contrasts) != 1:
                raise _Unknown('narrative_contrast_scope_unresolved')
            marker = contrasts[0]
            left = self.parse(start, marker.start(), actor, depth + 1)
            right_start, _ = self.trim(marker.end(), end)
            inherited = actor
            # An auxiliary following BUT explicitly shares the subject of
            # the first clause. It does not introduce an implicit new actor.
            if re.match(r'(?:does|do|did)\b', self.syntax[right_start:end], re.I):
                main = left
                while main['kind'] not in {'proposition', 'coordination'}:
                    main = main['child']
                if main['kind'] == 'coordination':
                    actors = {tuple(child['subject_span']) for child in main['children'] if child['kind'] == 'proposition'}
                    if len(actors) != 1:
                        raise _Unknown('narrative_contrast_subject_unresolved')
                    inherited = next(iter(actors))
                else:
                    inherited = tuple(main['subject_span'])
            right = self.parse(right_start, end, inherited, depth + 1)
            return {'kind': 'coordination', 'operator': 'but', 'mode': 'contrast', 'children': [left, right],
                    'operator_spans': [[marker.start(), marker.end()]], 'span': [start, end]}
        leading = _CONDITION.match(self.syntax, start, end)
        if leading:
            comma = self.syntax.find(',', leading.end(), end)
            if comma < 0:
                raise _Unknown("narrative_condition_boundary_unresolved")
            operand = self.parse(leading.end(), comma, depth=depth + 1)
            child = self.parse(comma + 1, end, actor, depth + 1)
            # Adjacent leading/trailing conditions share a child, but retain
            # every source operand and operator instead of overwriting one.
            bindings = [self.condition(leading, operand)]
            if child['kind'] == 'conditions':
                bindings.extend(child['bindings'])
                child = child['child']
            return {'kind': 'conditions', 'bindings': bindings, 'child': child, 'span': [start, end]}
        reporting = _REPORT.match(fragment)
        if reporting and actor is None:
            a, b = self.nominal(start + reporting.start('subject'), start + reporting.end('subject'), actor=True)
            child = self.parse(start + reporting.end(), end, depth=depth + 1)
            node = {'kind': 'reporting', 'speaker': self.text[a:b], 'speaker_span': [a, b],
                    'attribute': _REPORT_ACTIONS[reporting['verb'].lower()], 'predicate': reporting['verb'],
                    'predicate_span': [start + reporting.start('verb'), start + reporting.end('verb')],
                    'polarity': 'negative' if reporting['negative'] else 'positive',
                    'child': child, 'span': [start, end]}
            finite = reporting['aux'] or reporting['verb']
            if reporting['aux'] and reporting['verb'].lower() != node['attribute']:
                raise _Unknown('narrative_auxiliary_form_unresolved')
            finite_key = 'aux' if reporting['aux'] else 'verb'
            node['tense'] = 'past' if finite.lower() in _REPORT_PAST | {'did'} else 'present'
            node['tense_span'] = [start + reporting.start(finite_key), start + reporting.end(finite_key)]
            if reporting['negative']:
                node['negation_span'] = [start + reporting.start('negative'), start + reporting.start('negative') + 3]
            return node
        relatives = list(_RELATIVE.finditer(self.syntax, start, end))
        if relatives:
            if len(relatives) != 1 or actor is not None:
                raise _Unknown("narrative_relative_scope_unresolved")
            marker = relatives[0]
            a, b = self.nominal(start, marker.start(), actor=True)
            boundaries = list(_PRIMARY.finditer(self.syntax, marker.end(), end))
            if not boundaries:
                raise _Unknown("narrative_relative_main_predicate_unresolved")
            boundary = boundaries[-1]
            antecedent = (a, b)
            restriction = self.parse(marker.end(), boundary.start(), antecedent, depth + 1)
            child = self.parse(boundary.start(), end, antecedent, depth + 1)
            return {'kind': 'relative', 'antecedent': self.text[a:b], 'antecedent_span': [a, b],
                    'marker_span': [marker.start(), marker.end()], 'restriction': restriction,
                    'child': child, 'span': [start, end]}
        trailing = list(_CONDITION.finditer(self.syntax, start, end))
        if trailing:
            child = self.parse(start, trailing[0].start(), actor, depth + 1)
            bindings = []
            for index, operator in enumerate(trailing):
                limit = trailing[index + 1].start() if index + 1 < len(trailing) else end
                operand = self.parse(operator.end(), limit, depth=depth + 1)
                bindings.append(self.condition(operator, operand))
            return {'kind': 'conditions', 'bindings': bindings, 'child': child, 'span': [start, end]}
        from .infinitival_syntax import read_infinitival_scope

        infinitive = read_infinitival_scope(self, start, end, actor, depth)
        if infinitive is not None:
            return infinitive
        shared_joins = list(_SHARED_AUXILIARY_JOIN.finditer(self.syntax, start, end))
        if shared_joins:
            if len({join['operator'].lower() for join in shared_joins}) != 1:
                raise _Unknown('narrative_mixed_clause_coordination_unresolved')
            marker = shared_joins[0]
            left = self.parse(start, marker.start(), actor, depth + 1)

            def subjects(node):
                if node['kind'] == 'proposition':
                    return {tuple(node['subject_span'])}
                if node['kind'] == 'coordination':
                    return set().union(*(subjects(child) for child in node['children']))
                return subjects(node['child'])

            owners = subjects(left)
            if len(owners) != 1:
                raise _Unknown('narrative_shared_subject_coordination_unresolved')
            right = self.parse(marker.end(), end, next(iter(owners)), depth + 1)
            return {'kind': 'coordination', 'operator': marker['operator'].lower(), 'mode': 'clauses',
                    'children': [left, right], 'operator_spans': [[marker.start('operator'), marker.end('operator')]],
                    'span': [start, end]}
        if actor is None:
            coordinated = self.full_clause_coordination(start, end)
            if coordinated is not None:
                return coordinated
        return self.clause(start, end, actor)

    def condition(self, operator, operand):
        return {'operator': operator[0].lower().replace(' ', '_'),
                'operator_span': [operator.start(), operator.end()], 'operand': operand}

    def full_clause_coordination(self, start, end):
        """Coordinate only chunks with their own explicit actor and predicate.

        Object lists and shared-predicate syntax stay with their existing
        parsers. This step neither supplies an actor nor distributes negation
        from one chunk to another. Mixed operator precedence remains unknown.
        """
        joins = list(_CLAUSE_JOIN.finditer(self.syntax, start, end))
        if not joins or len(joins) > 16:
            return None
        children, cursor = [], start
        for boundary in [*joins, None]:
            limit = boundary.start() if boundary is not None else end
            a, b = self.trim(cursor, limit)
            try:
                children.append(self.clause(a, b, None))
            except _Unknown:
                return None
            cursor = boundary.end() if boundary is not None else end
        operators = {match['operator'].lower() for match in joins}
        if len(operators) != 1:
            raise _Unknown('narrative_mixed_clause_coordination_unresolved')
        return {'kind': 'coordination', 'operator': next(iter(operators)), 'mode': 'clauses',
                'children': children, 'operator_spans': [[match.start(), match.end()] for match in joins],
                'span': [start, end]}

    def clause(self, start, end, actor):
        from .active_aspect_requirements import read_active_aspect_clause

        active = read_active_aspect_clause(self, start, end, actor)
        if active is not None:
            return active
        auxiliary_span = None
        boundary = (_PRIMARY.search(self.syntax, start, end) or _VERB.search(self.syntax, start, end)) if actor is None else None
        if actor is None:
            if boundary is None:
                raise _Unknown('narrative_predicate_unresolved')
            a, b = self.trim(start, boundary.start())
            auxiliary = re.search(r'\s+(?P<finite>do|does|did)(?:\s+(?:not|never))?\s*$', self.syntax[a:b], re.I)
            negative = None
            if auxiliary:
                auxiliary_span = [a + auxiliary.start('finite'), a + auxiliary.end('finite')]
                aux_text = self.text[a + auxiliary.start():b]
                neg = re.search(r'\b(?:not|never)\b', aux_text, re.I)
                if neg:
                    negative = [a + auxiliary.start() + neg.start(), a + auxiliary.start() + neg.end()]
                b = a + auxiliary.start()
            actor = self.nominal(a, b, actor=True)
            vp = boundary.start()
        else:
            vp, negative = start, None
            auxiliary = re.match(r'(do|does|did)\b\s*(?:(not|never)\b\s*)?', self.syntax[vp:end], re.I)
            if auxiliary:
                auxiliary_span = [vp + auxiliary.start(1), vp + auxiliary.end(1)]
                if auxiliary[2]:
                    negative = [vp + auxiliary.start(2), vp + auxiliary.end(2)]
                vp += auxiliary.end()
        modality = _ABILITY.match(self.syntax, vp, end) or _MODAL.match(self.syntax, vp, end)
        modal_value, modal_negative = None, None
        if modality:
            if auxiliary_span is not None:
                raise _Unknown('narrative_multiple_auxiliaries_unresolved')
            modal_value = 'ability' if _ABILITY.fullmatch(modality[0]) else 'can' if modality[0].lower() == 'cannot' else modality[0].lower()
            if modality[0].lower() == 'cannot':
                modal_negative = [modality.start(), modality.end()]
            elif re.search(r'\bnot\b', modality[0], re.I):
                match = re.search(r'\bnot\b', modality[0], re.I)
                modal_negative = [modality.start() + match.start(), modality.start() + match.end()]
            vp = modality.end()
        finite = None
        if auxiliary_span:
            finite = ('past' if self.text[slice(*auxiliary_span)].lower() == 'did' else 'present', auxiliary_span)
        governed = modality is not None or auxiliary_span is not None
        while vp < end and self.text[vp].isspace():
            vp += 1
        local_neg = re.match(r'(?:not|never)\b\s*', self.syntax[vp:end], re.I)
        if local_neg:
            if negative or modal_negative:
                raise _Unknown('narrative_multiple_negation_scope_unresolved')
            negative = [vp, vp + len(local_neg[0].rstrip())]
            vp += local_neg.end()
        joins = list(_ACTION_JOIN.finditer(self.syntax, vp, end))
        if joins and (negative or modal_negative) and any(match['operator'].lower() != 'or' for match in joins):
            raise _Unknown('narrative_negated_coordination_scope_unresolved')
        if joins:
            operators = {match['operator'].lower() for match in joins}
            if len(operators) != 1:
                raise _Unknown('narrative_mixed_coordination_unresolved')
            chunks, cursor = [], vp
            for join in joins:
                chunks.append((cursor, join.start()))
                cursor = join.end()
            chunks.append((cursor, end))
            last = self.predicate(actor, *chunks[-1], governed=governed, finite=finite)
            shared = last['object_span'] if last['kind'] == 'proposition' else None
            children = [self.predicate(actor, a, b, shared=shared, governed=governed, finite=finite) for a, b in chunks[:-1]] + [last]
            child = {'kind': 'coordination', 'operator': next(iter(operators)), 'mode': 'actions',
                     'children': children,
                     'operator_spans': [[match.start(), match.end()] for match in joins], 'span': [start, end]}
        else:
            child = self.predicate(actor, vp, end, governed=governed, finite=finite)
        if negative:
            # A single copula may place its printed negation after the verb.
            child = {'kind': 'negation', 'operator_span': negative, 'child': child, 'span': [start, end]}
        if modality:
            child = {'kind': 'modality', 'operator': modal_value,
                     'operator_span': [modality.start(), modality.end()], 'polarity': 'negative' if modal_negative else 'positive',
                     'child': child, 'span': [start, end]}
            if modal_negative:
                child['negation_span'] = modal_negative
            if modal_value == 'ability':
                finite_verb = re.match(r'\w+', modality[0])
                child['tense'] = 'past' if finite_verb[0].lower() in _PAST else 'present'
                child['tense_span'] = [modality.start(), modality.start() + finite_verb.end()]
        return child

    def predicate(self, actor, start, end, *, shared=None, governed=False, finite=None):
        start, end = self.trim(start, end)
        predicate = _VERB.match(self.syntax, start, end)
        if predicate is None:
            raise _Unknown('narrative_predicate_unresolved')
        verb = predicate[0].lower()
        if (governed and verb != _ACTIONS[verb]) or (not governed and verb == 'be'):
            raise _Unknown('narrative_auxiliary_form_unresolved')
        a, b = self.trim(predicate.end(), end)
        if a == b and shared is not None:
            a, b = shared
        negative = re.match(r'(?:not|never)\b\s*', self.syntax[a:b], re.I)
        operator_span = None
        if negative:
            operator_span = [a, a + len(negative[0].rstrip())]
            a += negative.end()
        complement = _VERB.match(self.syntax, a, b)
        if _ACTIONS[verb] in {'have', 'be'} and complement and complement[0].lower() in _PAST:
            raise _Unknown('narrative_perfect_or_passive_unresolved')
        return self.predicate_objects(actor, predicate[0], _ACTIONS[verb], [predicate.start(), predicate.end()], a, b,
            statement_start=start, statement_end=end, finite=finite or (('past' if verb in _PAST else 'present', [predicate.start(), predicate.end()]) if not governed else None),
            operator_span=operator_span)

    def predicate_objects(self, actor, printed, attribute, predicate_span, a, b, *, statement_start,
                          statement_end, finite=None, operator_span=None):
        from .nominal_syntax import nominal_phrase, predicate_complements

        self.pending_clause_context = {'actor': actor, 'attribute': attribute,
            'predicate_span': list(predicate_span), 'span': [statement_start, statement_end]}
        if re.search(r'\bor\s+(?:more|fewer|less)\b', self.syntax[a:b], re.I):
            # Establish comparative scope before an unrelated unsupported PP
            # can obscure the reason and enable an opaque OR fallback.
            raise _Unknown('narrative_quantified_comparison_scope_unresolved')
        direct_end, complements = predicate_complements(self, a, b, attribute, predicate_span)
        a, direct_end = self.trim(a, direct_end)
        intransitive = a == direct_end and attribute in {'increase', 'decrease', 'operate', 'engage'} and complements
        if a == direct_end and not intransitive:
            raise _Unknown('narrative_object_unresolved')
        spans, operator, separators = ([(a, a)], None, []) if intransitive else self.objects(a, direct_end)
        if operator and operator_span:
            raise _Unknown('narrative_negated_coordination_scope_unresolved')
        if operator and attribute == 'be':
            members = [self.text[slice(*self.trim(x, y))] for x, y in spans]
            if any(re.search(r'\s', member) for member in members) and not all(
                    re.match(r'(?:a|an|the)\s+', member, re.I) for member in members):
                raise _Unknown('narrative_nominal_coordination_unresolved')
        children = []
        for x, y in spans:
            if not intransitive:
                self.nominal(x, y)
            if re.search(r'\b(?:owned|acquired|operated|managed|produced)\s+by\b', self.syntax[x:y], re.I):
                raise _Unknown('narrative_passive_agent_scope_unresolved')
            leaf = {'kind': 'proposition', 'subject': self.text[slice(*actor)], 'subject_span': list(actor),
                'predicate': printed, 'predicate_span': list(predicate_span),
                'attribute': attribute, 'object': self.text[x:y], 'object_span': [x, y],
                'subject_phrase': nominal_phrase(self, *actor),
                'object_phrase': None if intransitive else nominal_phrase(self, x, y),
                'prepositional_complements': copy.deepcopy(complements),
                'role': 'entity_description' if attribute == 'be' and re.match(r'(?:a|an|the)\s+', self.text[x:y], re.I) else 'description',
                'span': [min(actor[0], statement_start), max(actor[1], statement_end, y)]}
            if finite:
                leaf['tense'], leaf['tense_span'] = finite
            children.append(leaf)
        node = children[0] if len(children) == 1 else {'kind': 'coordination', 'operator': operator,
            'mode': 'objects', 'children': children, 'operator_spans': separators, 'span': [statement_start, statement_end]}
        return {'kind': 'negation', 'operator_span': operator_span, 'child': node, 'span': [statement_start, statement_end]} if operator_span else node

    def objects(self, start, end):
        if start == end:
            raise _Unknown('narrative_object_unresolved')
        from .nominal_syntax import shared_modifier_phrase

        if re.search(r'\s+(?:and|or)\s+', self.syntax[start:end], re.I) and shared_modifier_phrase(self, start, end) is not None:
            return [(start, end)], None, []
        # A conjunction inside an OF complement belongs to that nominal head,
        # never to multiple direct objects of the predicate.
        if re.search(r'\bof\b', self.syntax[start:end], re.I):
            return [(start, end)], None, []
        from .nominal_syntax import _NOMINAL_PP_FRAMES

        for preposition, heads in _NOMINAL_PP_FRAMES.items():
            marker = re.search(r'\b' + re.escape(preposition) + r'\b', self.syntax[start:end], re.I)
            if marker and re.search(r'\b(?:' + '|'.join(heads) + r')\s*$', self.syntax[start:start + marker.start()], re.I):
                return [(start, end)], None, []
        if re.search(r'\bor\s+(?:more|fewer|less)\b', self.syntax[start:end], re.I):
            # A printed comparative quantity is not a disjunction between a
            # number and a noun phrase. Its threshold role needs its own reader.
            raise _Unknown('narrative_quantified_comparison_scope_unresolved')
        commas = list(re.finditer(r'(?<!\d),(?!\d)', self.syntax[start:end]))
        joins = list(re.finditer(r'\s+(and|or)\s+', self.syntax[start:end], re.I))
        if not joins:
            if commas:
                raise _Unknown('narrative_enumeration_boundary_unresolved')
            return [(start, end)], None, []
        operators = {match[1].lower() for match in joins}
        if len(operators) > 1:
            raise _Unknown('narrative_mixed_coordination_unresolved')
        operator = next(iter(operators))
        separators = [(start + match.start(), start + match.end()) for match in commas]
        # Commas delimit list members; internal AND in an earlier member is
        # retained in that printed member, rather than splitting a name.
        last_comma = start + commas[-1].end() if commas else start
        final_joins = [(start + match.start(), start + match.end()) for match in joins
                       if start + match.end() > last_comma]
        if not final_joins:
            # A conjunction inside an earlier member does not classify later
            # comma-attached modifiers or establish the whole list's operator.
            raise _Unknown('narrative_enumeration_operator_scope_unresolved')
        separators += final_joins
        separators.sort()
        spans, cursor = [], start
        for a, b in separators:
            x, y = self.trim(cursor, a)
            if x < y:
                spans.append((x, y))
            cursor = max(cursor, b)
        x, y = self.trim(cursor, end)
        if x < y:
            spans.append((x, y))
        if len(spans) < 2:
            raise _Unknown('narrative_enumeration_boundary_unresolved')
        return spans, operator, [list(span) for span in separators]

    @staticmethod
    def summary(node):
        kind = node['kind']
        if kind == 'circumstance_scope':
            return {'kind': kind, 'operator': node['operator'], 'direction': node['direction'],
                    'degree': node['degree'], 'simultaneous': node['simultaneous'],
                    **{key: node[key] for key in ('combined', 'non_exhaustive') if key in node},
                    'operand': _Reader.summary(node['operand']), 'child': _Reader.summary(node['child'])}
        if kind == 'unknown':
            return {'kind': kind, 'status': 'unresolved', 'reason': node['reason'], 'text': node['text']}
        if kind in {'purpose_scope', 'controlled_infinitive_scope'}:
            return {'kind': kind, 'operator': node['operator'], 'control': copy.deepcopy(node['control']),
                    'child': _Reader.summary(node['child']), 'operand': _Reader.summary(node['operand'])}
        if kind == 'discourse_scope':
            return {'kind': kind, 'operator': node['operator'], 'role': node['role'], 'child': _Reader.summary(node['child'])}
        if kind == 'proposition':
            return {'subject': node['subject'], 'attribute': node['attribute'], 'value': node['object'],
                    'polarity': 'positive', **node.get('lexical_qualifiers', {}),
                    **({'tense': node['tense']} if 'tense' in node else {})}
        if kind == 'cjk_measurement_sequence':
            return {'kind': kind, 'clauses': [{key: copy.deepcopy(value) for key, value in clause.items()
                if key in {'kind', 'subject', 'value', 'unit', 'currency', 'direction', 'basis', 'baseline_period'}}
                for clause in node['clauses']]}
        if kind == 'cjk_nominal':
            return {'kind': kind, 'head': node['head'], 'parts': [_Reader.summary(part) for part in node['parts']],
                    **({'quantifier': node['quantifier']} if 'quantifier' in node else {})}
        if kind == 'cjk_dependency':
            return {'kind': kind, 'role': node['role'], 'marker': node['marker'], 'child': _Reader.summary(node['child'])}
        if kind == 'negation':
            result = _Reader.summary(node['child'])
            if 'polarity' in result:
                result['polarity'] = 'negative'
            else:
                result = {'operator': 'not', 'operand': result}
            return result
        if kind == 'coordination':
            return {'operator': node['operator'], 'operands': [_Reader.summary(child) for child in node['children']],
                    **({'shared_actor': node['shared_actor']} if 'shared_actor' in node else {})}
        if kind == 'modality':
            return {'kind': kind, 'modality': node['operator'], 'polarity': node['polarity'],
                    **({'tense': node['tense']} if 'tense' in node else {}), 'child': _Reader.summary(node['child'])}
        if kind == 'reporting':
            return {'kind': kind, 'subject': node['speaker'], 'attribute': node['attribute'],
                    'polarity': node['polarity'], 'tense': node['tense'], 'child': _Reader.summary(node['child'])}
        if kind == 'relative':
            return {'kind': kind, 'antecedent': node['antecedent'], 'restriction': _Reader.summary(node['restriction']),
                    'child': _Reader.summary(node['child'])}
        if kind == 'temporal_scope':
            return {'kind': kind, 'qualifiers': copy.deepcopy(node['qualifiers']), 'child': _Reader.summary(node['child'])}
        if kind == 'active_aspect':
            return {'kind': kind, 'aspect': node['aspect'], 'tense': node['tense'], 'child': _Reader.summary(node['child'])}
        if kind == 'fronted_context':
            return {'kind': kind, **{key: node[key] for key in ('preposition', 'operator', 'role', 'context')},
                    'child': _Reader.summary(node['child'])}
        return {'kind': kind, 'bindings': [{'operator': item['operator'], 'operand': _Reader.summary(item['operand'])}
                                         for item in node['bindings']], 'child': _Reader.summary(node['child'])}

    def annotate_sources(self, node):
        """Give every syntactic span an absolute original-source counterpart."""
        if isinstance(node, list):
            for child in node:
                self.annotate_sources(child)
        elif isinstance(node, dict):
            if node.get('kind') == 'proposition':
                node.setdefault('scope', list(self.scope))
            if node.get('kind') == 'proposition' and 'subject_phrase' not in node:
                from .nominal_syntax import nominal_phrase

                # Both language readers expose exactly the same NP node
                # schema; their own nominal grammar supplies the boundaries.
                node['subject_phrase'] = nominal_phrase(self, *node['subject_span'])
                node['object_phrase'] = nominal_phrase(self, *node['object_span'])
                node['prepositional_complements'] = []
            for name, value in list(node.items()):
                if (name == 'span' or name.endswith('_span') and name not in {'text_span', 'cell_text_span', 'joined_span'}) and isinstance(value, list) and len(value) == 2:
                    node['source' if name == 'span' else name[:-5] + '_source'] = self.source_at(*value)
                elif name in {'operator_spans', 'link_spans'}:
                    node[name[:-6] + '_sources'] = [self.source_at(*span) for span in value]
                elif name == 'lexical_qualifier_spans':
                    node['lexical_qualifier_sources'] = {key: self.source_at(*span) for key, span in value.items()}
                elif isinstance(value, (dict, list)):
                    self.annotate_sources(value)

    @staticmethod
    def endpoint(node):
        """Logical labels exclude object/value payload and serialization ids."""
        if node['kind'] == 'circumstance_scope':
            return {'role': 'circumstance_scope', 'operator': node['operator'],
                    'operand': _Reader.endpoint(node['operand']), 'child': _Reader.endpoint(node['child'])}
        if node['kind'] == 'cjk_measurement_sequence':
            return {'role': 'cjk_measurement_sequence', 'clauses': [
                {'subject': leaf['subject'], 'predicate_kind': leaf['kind'],
                 'attribute': leaf.get('predicate', leaf.get('operator_text'))} for leaf in node['clauses']]}
        if node['kind'] == 'unknown':
            return {'role': 'unresolved', 'reason': node['reason']}
        if node['kind'] in {'purpose_scope', 'controlled_infinitive_scope'}:
            return {'role': node['kind'], 'operator': node['operator'], 'control': copy.deepcopy(node['control']),
                    'child': _Reader.endpoint(node['child']), 'operand': _Reader.endpoint(node['operand'])}
        if node['kind'] == 'discourse_scope':
            return {'role': 'discourse_scope', 'operator': node['operator'], 'child': _Reader.endpoint(node['child'])}
        if node['kind'] == 'proposition':
            return {'subject': node['subject'], 'attribute': node['attribute'],
                    **({'tense': node['tense']} if 'tense' in node else {})}
        if node['kind'] == 'reporting':
            return {'subject': node['speaker'], 'attribute': node['attribute'], 'role': 'reporting',
                    'polarity': node['polarity'], 'tense': node['tense']}
        if node['kind'] == 'coordination':
            return {'role': 'coordination', 'operator': node['operator'],
                    **({'shared_actor': node['shared_actor']} if 'shared_actor' in node else {}),
                    'members': [_Reader.endpoint(child) for child in node['children']]}
        if node['kind'] == 'modality':
            return {'role': 'modality', 'operator': node['operator'], 'polarity': node['polarity'],
                    **({'tense': node['tense']} if 'tense' in node else {}), 'child': _Reader.endpoint(node['child'])}
        if node['kind'] == 'negation':
            return {'role': 'negation', 'child': _Reader.endpoint(node['child'])}
        if node['kind'] == 'relative':
            return {'role': 'restrictive_relative', 'antecedent': node['antecedent'],
                    'restriction': _Reader.endpoint(node['restriction']), 'child': _Reader.endpoint(node['child'])}
        if node['kind'] == 'temporal_scope':
            return {'role': 'temporal_scope', 'qualifiers': copy.deepcopy(node['qualifiers']),
                    'child': _Reader.endpoint(node['child'])}
        if node['kind'] == 'active_aspect':
            return {'role': 'active_aspect', 'aspect': node['aspect'], 'tense': node['tense'],
                    'child': _Reader.endpoint(node['child'])}
        if node['kind'] == 'fronted_context':
            return {'role': 'fronted_context', 'operator': node['operator'], 'context_role': node['role'],
                    'context': node['context'], 'child': _Reader.endpoint(node['child'])}
        return {'role': 'conditions', 'bindings': [{'operator': item['operator'], 'operand': _Reader.endpoint(item['operand'])}
                                                 for item in node['bindings']], 'child': _Reader.endpoint(node['child'])}

    def edge(self, kind, left, fact, source, **evidence):
        edges = self.operand_relations if fact['semantic_role'] == 'operand' else self.relations
        edges.append({'type': kind, 'left': copy.deepcopy(left), 'fact_id': fact['id'],
            'right': {'subject': fact['subject'], 'attribute': fact['attribute'], 'scope': list(self.scope),
                      **({'qualifiers': {'tense': fact['qualifiers']['tense']}} if 'tense' in fact['qualifiers'] else {})},
            'source': copy.deepcopy(source), 'object_anchor': None,
            'binding_evidence': {'statement_source': copy.deepcopy(fact['source']), **copy.deepcopy(evidence)},
            'rule_id': 'source_bound_narrative_' + kind})

    def alternative_group(self, node):
        children = node['children']
        # A wrapper's main proposition retains its actual actor source. A
        # multi-actor group has no common subject; conditions do not supply it.
        def main_leaves(item):
            if item['kind'] == 'proposition':
                return [item]
            if item['kind'] == 'coordination':
                return [leaf for child in item['children'] for leaf in main_leaves(child)]
            return main_leaves(item['child'])

        leaves = [leaf for child in children for leaf in main_leaves(child)]
        actors = {leaf['subject'] for leaf in leaves}
        common = len(actors) == 1
        start = min([node['span'][0], *[child['span'][0] for child in children]])
        end = max([node['span'][1], *[child['span'][1] for child in children]])
        a, b = self.trim(*node['operator_spans'][0])
        return {'kind': 'logical_group', 'subject': leaves[0]['subject'] if common else '',
                'subject_span': leaves[0]['subject_span'] if common else None,
                'attribute': 'logical_alternative', 'predicate': self.text[a:b], 'predicate_span': [a, b],
                'object': self.text[start:end], 'object_span': [start, end],
                'role': 'logical_group', 'span': [start, end], 'tree': copy.deepcopy(node)}

    def emit(self, node, context=None):
        context = copy.deepcopy(context or {'polarity': 'positive', 'assertion_context': 'asserted', 'operators': [], 'contexts': []})
        kind = node['kind']
        context['operators'].append({'kind': kind, 'source': self.source_at(*node['span'])})
        if 'operator_span' in node:
            context['operators'][-1]['operator_source'] = self.source_at(*node['operator_span'])
        if kind == 'unknown':
            self.unknown_nodes.append(copy.deepcopy(node))
            return
        if kind == 'circumstance_scope':
            from .cjk_circumstances import emit_circumstance

            emit_circumstance(self, node, context)
            return
        if kind == 'discourse_scope':
            self.features.add('discourse_scope')
            context.setdefault('discourse_nodes', []).append(node)
            self.emit(node['child'], context)
            return
        if kind in {'purpose_scope', 'controlled_infinitive_scope'}:
            self.features.add(kind)
            operand_context = copy.deepcopy(context)
            operand_context['assertion_context'] = 'purpose_operand' if kind == 'purpose_scope' else 'controlled_infinitive_operand'
            operand_context['contexts'].append(operand_context['assertion_context'])
            operand_context['semantic_operand'] = True
            self.emit(node['operand'], operand_context)
            context.setdefault('infinitival_bindings', []).append(node)
            self.emit(node['child'], context)
            return
        if kind == 'temporal_scope':
            self.features.add('temporal_prose_scope')
            context['temporal'] = node
            self.emit(node['child'], context)
            return
        if kind == 'active_aspect':
            self.features.add('active_aspect_scope')
            context['aspect'], context['aspect_node'] = node['aspect'], node
            context['tense'], context['tense_span'] = node['tense'], node['tense_span']
            self.emit(node['child'], context)
            return
        if kind == 'fronted_context':
            self.features.add('fronted_nominal_context')
            if 'operation' in node:
                operand_context = copy.deepcopy(context)
                operand_context['semantic_operand'] = True
                operand_context['assertion_context'] = node['role'] + '_operand'
                operand_context['contexts'].append(operand_context['assertion_context'])
                operand_context['fronted_control'] = node
                self.emit(node['operation'], operand_context)
            context.setdefault('fronted_nodes', []).append(node)
            self.emit(node['child'], context)
            return
        if kind == 'conditions':
            self.features.add('condition_operands')
            descriptors, bindings = [], []
            for binding in node['bindings']:
                operand_context = copy.deepcopy(context)
                operand_context['assertion_context'] = 'condition_operand'
                operand_context['contexts'].append('condition_operand')
                operand_context['semantic_operand'] = True
                self.emit(binding['operand'], operand_context)
                descriptors.append({'operator': binding['operator'], 'operand': self.summary(binding['operand'])})
                bindings.append(binding)
            context.setdefault('conditions', []).extend(descriptors)
            context.setdefault('condition_bindings', []).extend(bindings)
            self.emit(node['child'], context)
            return
        if kind == 'relative':
            self.features.add('restrictive_relative')
            relative_context = copy.deepcopy(context)
            relative_context['assertion_context'] = 'restrictive_relative'
            relative_context['contexts'].append('restrictive_relative')
            relative_context['semantic_operand'] = True
            self.emit(node['restriction'], relative_context)
            context['subject_restriction'] = self.summary(node['restriction'])
            context['relative_node'] = node
            self.emit(node['child'], context)
            return
        if kind == 'reporting':
            self.features.add('scoped_reporting')
            context.setdefault('reporting', []).append({'subject': node['speaker'], 'attribute': node['attribute'],
                                                       'polarity': node['polarity'], 'tense': node['tense']})
            context.setdefault('reporting_nodes', []).append(node)
            context['assertion_context'] = 'reported'
            context['contexts'].append('reported')
            self.emit(node['child'], context)
            return
        if kind == 'modality':
            self.features.add('ability_operator' if node['operator'] == 'ability' else 'modal_operator')
            context['modality'], context['modal_node'], context['modal_polarity'] = node['operator'], node, node['polarity']
            context['assertion_context'] = 'ability' if node['operator'] == 'ability' else 'modal'
            context['contexts'].append(context['assertion_context'])
            if 'tense' in node:
                context['tense'], context['tense_span'] = node['tense'], node['tense_span']
            if node.get('polarity') == 'negative':
                context['modal_negation_node'] = node
                self.features.add('negation_scope')
            self.emit(node['child'], context)
            return
        if kind == 'negation':
            self.features.add('negation_scope')
            context['polarity'], context['negation_node'] = 'negative', node
            self.emit(node['child'], context)
            return
        if kind == 'coordination':
            self.features.add('alternative_membership' if node['operator'] == 'or' else 'contrast_scope' if node['operator'] == 'but' else 'coordination_scope')
            context['coordination_source_node'] = node
            context.setdefault('coordination_nodes', []).append(node)
            if node['operator'] == 'or':
                operand_context = copy.deepcopy(context)
                operand_context['assertion_context'] = 'alternative_member'
                operand_context['contexts'].append('alternative_member')
                operand_context['coordination'] = 'or'
                operand_context['semantic_operand'] = True
                for child in node['children']:
                    self.emit(child, operand_context)
                context['coordination'] = 'or'
                context['assertion_context'] = 'alternative_group'
                context['contexts'].append('alternative_group')
                self.emit(self.alternative_group(node), context)
                return
            context['coordination'], context['coordination_node'] = node['operator'], node
            for child in node['children']:
                self.emit(child, context)
            return
        q = {key: copy.deepcopy(context[key]) for key in ('modality', 'modal_polarity', 'polarity', 'coordination', 'reporting', 'conditions', 'subject_restriction', 'tense', 'aspect') if key in context}
        q.update(copy.deepcopy(node.get('lexical_qualifiers', {})))
        tense_span = node.get('tense_span', context.get('tense_span'))
        if 'tense' in node:
            q['tense'] = node['tense']
        if 'tense' in q:
            self.features.add('finite_tense')
        if context['assertion_context'] in {'condition_operand', 'restrictive_relative', 'reported', 'alternative_member', 'alternative_group',
                                            'purpose_operand', 'controlled_infinitive_operand', 'means_operand', 'background_operand', 'cause_operand'}:
            q['assertion_context'] = context['assertion_context']
        if len(context['contexts']) > 1:
            q['assertion_contexts'] = list(context['contexts'])
            self.features.add('nested_operator_scopes')
        collection = self.operands if context.get('semantic_operand') else self.facts
        semantic_role = 'operand' if context.get('semantic_operand') else 'requirement'
        fact = {'id': f'narrative:{semantic_role}:{len(collection)}', 'subject': node['subject'], 'attribute': node['attribute'],
            'value': node['object'], 'predicate': node['predicate'], 'object': node['object'], 'role': node['role'],
            'semantic_role': semantic_role,
            'qualifiers': q, 'identity_facets': {}, 'scope': list(self.scope), 'record_id': self.record,
            'source': self.source_at(*node['span']),
            'subject_source': self.source_at(*node['subject_span']) if node['subject_span'] is not None else None,
            'predicate_source': self.source_at(*node['predicate_span']), 'attribute_source': self.source_at(*node['predicate_span']),
            'value_source': self.source_at(*node['object_span']), 'object_source': self.source_at(*node['object_span']),
            **{key: copy.deepcopy(node[key]) for key in ('subject_phrase', 'object_phrase', 'prepositional_complements') if key in node},
            'logic': {'kind': 'logical_group' if kind == 'logical_group' else 'narrative_leaf',
                      'assertion_context': context['assertion_context'], 'operator_path': context['operators'],
                      **({'tree': copy.deepcopy(node['tree'])} if kind == 'logical_group' else {})},
            'rule_id': 'explicit_narrative_logical_group' if kind == 'logical_group' else 'explicit_narrative_proposition'}
        if 'fronted_control' in context:
            owner = context['fronted_control']
            fact['subject_binding_evidence'] = {**copy.deepcopy(owner['control']), 'kind': 'fronted_operation_controller',
                'operator_source': self.source_at(*owner['operator_span'])}
        from .quoted_nominal import quoted_role_evidence

        quoted_roles = []
        for role, span in (('subject', node['subject_span']), ('object', node['object_span'])):
            if span is not None and not (kind == 'logical_group' and role == 'object'):
                evidence, reason = quoted_role_evidence(self.text, *span, self.quoted, role=role)
                if reason:
                    raise _Unknown(reason)
                quoted_roles.extend(evidence)
        if quoted_roles:
            fact['quoted_nominals'] = quoted_roles
        fact['qualifier_sources'] = {}
        for key, span in node.get('lexical_qualifier_spans', {}).items():
            fact['qualifier_sources'][key] = self.source_at(*span)
        if context.get('circumstance_nodes'):
            from .cjk_circumstances import circumstance_descriptor, circumstance_sources

            fact['qualifiers']['circumstances'] = [circumstance_descriptor(self, item) for item in context['circumstance_nodes']]
            fact['qualifier_sources']['circumstances'] = [circumstance_sources(item) for item in context['circumstance_nodes']]
        if 'coordination_source_node' in context:
            fact['qualifier_sources']['coordination'] = copy.deepcopy(context['coordination_source_node']['operator_sources'])
        if 'fronted_nodes' in context:
            fact['qualifiers']['fronted_contexts'] = [{
                'preposition': item['preposition'], 'operator': item['operator'],
                'role': item['role'], 'text': item['context']} for item in context['fronted_nodes']]
            fact['qualifier_sources']['fronted_contexts'] = [{
                key: self.source_at(*item[key[:-7] + '_span'])
                for key in ('preposition_source', 'context_source', 'separator_source')}
                for item in context['fronted_nodes']]
        if 'temporal' in context:
            temporal = context['temporal']
            fact['qualifiers'].update(copy.deepcopy(temporal['qualifiers']))
            fact['qualifier_sources'].update(copy.deepcopy(temporal['qualifier_sources']))
        if tense_span is not None:
            fact['qualifier_sources']['tense'] = self.source_at(*tense_span)
        if 'aspect_node' in context:
            fact['qualifier_sources']['aspect'] = self.source_at(*context['aspect_node']['aspect_span'])
        if 'modal_node' in context:
            fact['qualifier_sources']['modality'] = self.source_at(*context['modal_node']['operator_span'])
        if 'negation_node' in context:
            fact['qualifier_sources']['polarity'] = self.source_at(*context['negation_node']['operator_span'])
        if 'modal_negation_node' in context:
            fact['qualifier_sources']['modal_polarity'] = self.source_at(*context['modal_negation_node']['negation_span'])
        if 'condition_bindings' in context:
            fact['qualifier_sources']['conditions'] = [
                {'operator_source': self.source_at(*item['operator_span']),
                 'operand_source': self.source_at(*item['operand']['span'])}
                for item in context['condition_bindings']]
        if 'relative_node' in context:
            relative = context['relative_node']
            fact['qualifier_sources']['subject_restriction'] = {
                'antecedent_source': self.source_at(*relative['antecedent_span']),
                'restriction_source': self.source_at(*relative['restriction']['span']),
                'marker_source': self.source_at(*relative['marker_span'])}
        if 'reporting_nodes' in context:
            fact['qualifier_sources']['reporting'] = [
                {'speaker_source': self.source_at(*item['speaker_span']),
                 'predicate_source': self.source_at(*item['predicate_span']),
                 'tense_source': self.source_at(*item['tense_span']),
                 **({'negation_source': self.source_at(*item['negation_span'])} if 'negation_span' in item else {})}
                for item in context['reporting_nodes']]
        collection.append(fact)
        self.edge('field_binding', {'subject': fact['subject'], 'attribute': fact['attribute'],
                  **({'qualifiers': {'tense': q['tense']}} if 'tense' in q else {})}, fact, fact['source'],
                  subject_source=fact['subject_source'], predicate_source=fact['predicate_source'], object_source=fact['object_source'])
        for key, span in node.get('lexical_qualifier_spans', {}).items():
            if key in q:
                self.edge('qualifier_scope', {'type': key, 'text': q[key]}, fact, self.source_at(*span))
        for circumstance in context.get('circumstance_nodes', []):
            self.edge('narrative_circumstance_scope', {
                'operator': circumstance['operator'], 'direction': circumstance['direction'],
                'degree': circumstance['degree'], 'simultaneous': circumstance['simultaneous'],
                'operand': self.endpoint(circumstance['operand'])}, fact, circumstance['operator_source'],
                operator_source=circumstance['operator_source'], operand_logic=circumstance['operand'])
        def nominal_relations(value):
            if isinstance(value, list):
                for item in value:
                    nominal_relations(item)
                return
            if not isinstance(value, dict):
                return
            if value.get('kind') == 'prepositional_complement':
                self.features.update({'prepositional_attachment', 'noun_phrase_composition'})
                prep_source = value['preposition_source']
                self.edge('narrative_prepositional_attachment', {
                    'preposition': value['preposition'], 'semantic_role': value['semantic_role'],
                    'attachment': value['attachment'], 'complement': self.text[slice(*value['complement_span'])]},
                    fact, prep_source, preposition_source=prep_source,
                    head_source=value['head_source'], attachment_source=value['head_source'],
                    complement_source=value['complement_source'])
            if value.get('kind') == 'cjk_dependency':
                self.features.add('noun_phrase_composition')
                self.edge('narrative_cjk_nominal_scope', self.summary(value), fact,
                          value.get('marker_source', value['source']), nominal_logic=value)
            if value.get('kind') == 'cjk_nominal' and value.get('quantifier'):
                self.edge('narrative_cjk_quantifier_scope', {'quantifier': value['quantifier']}, fact,
                          value['quantifier_source'], nominal_logic=value)
            if value.get('kind') == 'quantity_comparison':
                self.features.update({'quantity_comparison', 'noun_phrase_composition'})
                self.edge('narrative_quantity_scope', {
                    key: value[key] for key in ('operator', 'value', 'unit', 'quantity_role')},
                    fact, value['source'], quantity_source=value['source'], value_source=value['value_source'])
            if value.get('kind') == 'nominal_compound':
                self.features.add('noun_phrase_composition')
                self.edge('narrative_nominal_compound_scope', {key: value[key] for key in ('modifier', 'head', 'relation')},
                    fact, value['source'], compound_logic=value, head_source=value['head_source'], modifier_source=value['modifier_source'])
            if value.get('kind') == 'coordination' and value.get('mode') in {'nominal_members', 'nominal_modifiers'}:
                self.features.add('noun_phrase_composition')
                for source in value['operator_sources']:
                    self.edge('narrative_nominal_coordination_scope', {
                        'operator': value['operator'], 'mode': value['mode'], 'member_count': len(value['children'])},
                        fact, source, operator_source=source, coordination_logic=value)
            for child in value.values():
                if isinstance(child, (dict, list)):
                    nominal_relations(child)

        nominal_relations([fact.get('subject_phrase'), fact.get('object_phrase'), fact.get('prepositional_complements', [])])
        for binding in context.get('infinitival_bindings', []):
            self.edge('narrative_' + binding['kind'], {
                'operator': binding['operator'], 'controller': binding['control']['controller'],
                'control_kind': binding['control']['kind'], 'operand': self.endpoint(binding['operand'])},
                fact, binding['operator_source'], operator_source=binding['operator_source'],
                controller_source=binding['control']['controller_source'],
                operand_source=binding['operand']['source'], operand_logic=binding['operand'])
        for discourse in context.get('discourse_nodes', []):
            self.edge('narrative_discourse_scope', {'operator': discourse['operator'], 'role': discourse['role'],
                **({'marker': discourse['marker']} if discourse['role'] == 'item_label' else {})},
                fact, discourse['marker_source'], marker_source=discourse['marker_source'])
        for quoted in quoted_roles:
            self.edge('narrative_quoted_nominal_scope', {'role': 'quoted_nominal', 'nominal_role': quoted['role'],
                      'attachment': quoted['attachment']}, fact, quoted['source'], quoted_nominal=quoted)
        for fronted in context.get('fronted_nodes', []):
            self.edge('narrative_fronted_context_scope', {'operator': fronted['operator'], 'role': fronted['role'],
                      'context': fronted['context']}, fact, self.source_at(*fronted['preposition_span']),
                      context_source=self.source_at(*fronted['context_span']),
                      separator_source=self.source_at(*fronted['separator_span']),
                      **({'context_phrase': fronted['context_phrase']} if 'context_phrase' in fronted else {}),
                      **({'quoted_nominals': fronted['quoted_nominals']} if 'quoted_nominals' in fronted else {}))
        if 'temporal' in context:
            for key, value in context['temporal']['qualifiers'].items():
                self.edge('qualifier_scope', {'type': key, 'text': value}, fact,
                          context['temporal']['qualifier_sources'][key])
        if 'aspect_node' in context:
            self.edge('narrative_active_aspect_scope', {'aspect': q['aspect'], 'tense': q['tense']}, fact,
                      self.source_at(*context['aspect_node']['aspect_span']))
        if kind == 'logical_group':
            self.edge('narrative_alternative_scope', {'operator': 'or',
                      'members': [self.endpoint(child) for child in node['tree']['children']]}, fact,
                      fact['predicate_source'], operand_logic=node['tree'])
        # Each nested composition keeps its own operator owner. An inner
        # object list must not erase the outer clause contrast or conjunction.
        for coordination in context.get('coordination_nodes', []):
            if coordination['operator'] == 'or':
                continue  # OR membership has its explicit alternative group.
            for position, span in enumerate(coordination['operator_spans']):
                a, b = self.trim(*span)
                if a == b:
                    continue  # Commas delimit members without becoming AND tokens.
                self.edge('narrative_coordination_scope', {'operator': coordination['operator'],
                          'mode': coordination['mode'], 'position': position,
                          'member_count': len(coordination['children'])}, fact, self.source_at(a, b),
                          operator_source=self.source_at(a, b), coordination_logic=coordination)
        for binding in context.get('condition_bindings', []):
            self.edge('narrative_condition_scope', {'operator': binding['operator'], 'operand': self.endpoint(binding['operand'])}, fact,
                self.source_at(*binding['operator_span']), operand_logic=copy.deepcopy(binding['operand']))
        if 'modal_node' in context:
            self.edge('narrative_modality_scope', {'operator': context['modality'], 'polarity': context['modal_polarity']}, fact,
                      self.source_at(*context['modal_node']['operator_span']))
        if 'negation_node' in context:
            self.edge('narrative_negation_scope', {'operator': 'not'}, fact,
                      self.source_at(*context['negation_node']['operator_span']))
        if 'modal_negation_node' in context:
            self.edge('narrative_negation_scope', {'operator': 'not', 'target': 'modality'}, fact,
                      self.source_at(*context['modal_negation_node']['negation_span']))
        if 'relative_node' in context:
            self.edge('narrative_relative_attachment', {'role': 'restrictive_relative', **self.endpoint(context['relative_node']['restriction'])}, fact,
                      self.source_at(*context['relative_node']['marker_span']), restriction_logic=context['relative_node']['restriction'])
        for report in context.get('reporting_nodes', []):
            self.edge('narrative_reporting_scope', {'subject': report['speaker'], 'attribute': report['attribute'],
                'polarity': report['polarity'], 'tense': report['tense']}, fact,
                self.source_at(*report['predicate_span']), speaker_source=self.source_at(*report['speaker_span']),
                tense_source=self.source_at(*report['tense_span']))


def read_narrative(text: str, source: dict[str, Any], *, scope=()) -> dict[str, Any]:
    """Expose bounded narrative syntax; unresolved neighbors retain B/L scope.

    ``complete`` means the source syntax was interpreted. It does not certify
    a downstream matcher's support: ``required_matcher_features`` declares the
    nested operators whose semantics must be preserved before comparison.
    Text is a single literal occurrence and is never duplicated per B leaf.
    """
    if not isinstance(text, str) or not isinstance(source, dict) or not isinstance(source.get('path'), str):
        raise ValueError('narrative requires literal text and its actual source identity')
    parent_span = source.get('text_span')
    if parent_span is not None and (not isinstance(parent_span, (list, tuple)) or len(parent_span) != 2
                                   or any(type(value) is not int or value < 0 for value in parent_span)
                                   or parent_span[1] < parent_span[0]):
        raise ValueError('narrative parent source span is invalid')
    reader = _Reader(text, source, scope)
    result: dict[str, Any] = {'matched': bool(text.strip()), 'complete': False, 'semantic_complete': False,
        'facts': reader.facts, 'relations': reader.relations, 'logic': [], 'unresolved': [], 'blockers': [],
        'semantic_operands': reader.operands, 'semantic_operand_relations': reader.operand_relations,
        'pending_requirements': [], 'issues': [], 'text_atoms': [], 'controls': [],
        'text_projection_complete': True, 'required_matcher_features': [], 'consumed_spans': [],
        'source': copy.deepcopy(source), 'raw_text': text, 'comparison_status': 'not_validated_by_this_source_reader'}
    if not result['matched']:
        return result
    result['text_atoms'] = [{'text': text, 'role': 'literal', 'source': reader.source_at(0, len(text))}]
    result['consumed_spans'] = [{'text': text, 'role': 'literal', 'span': [0, len(text)], 'source': reader.source_at(0, len(text))}]
    for ordinal, (start, end) in enumerate(_sentence_spans(text)):
        reader.record = f"{source.get('path')}:{source.get('lines', [])}:{source.get('block')}:{source.get('text_span')}:narrative:{ordinal}"
        from .document_composition_requirements import read_document_composition

        composition = read_document_composition(text[start:end], reader.source_at(start, end), scope=scope)
        if composition['matched']:
            for fact in composition['facts']:
                fact['id'] = f'composition:{ordinal}'
                fact['record_id'] = reader.record
            reader.facts.extend(composition['facts'])
            reader.relations.extend(composition['relations'])
            result['logic'].extend(composition['logic'])
            for key in ('unresolved', 'blockers', 'pending_requirements'):
                result[key].extend(composition[key])
            reader.features.update(composition['required_matcher_features'])
            continue
        try:
            tree = reader.interpret(start, end)
        except _Unknown as error:
            item = {'kind': 'narrative', 'reason': str(error), 'text': text[start:end],
                    'source': reader.source_at(start, end), 'scope': list(scope), 'layers': ['B', 'L'],
                    'category': 'software_unsupported'}
            quoted_scopes = [{key: copy.deepcopy(value) for key, value in quoted.items() if key != 'span'}
                             for quoted in reader.quoted['scopes'] if quoted['span'][0] < end and quoted['span'][1] > start]
            if quoted_scopes:
                item['quoted_scopes'] = quoted_scopes
            fronted_scopes = [copy.deepcopy(fronted) for fronted in reader.fronted_scopes
                              if start <= fronted['span'][0] < fronted['span'][1] <= end]
            if fronted_scopes:
                item['fronted_scopes'] = fronted_scopes
            result['unresolved'].append(item)
            result['blockers'].append(copy.deepcopy(item))
            result['pending_requirements'].append(copy.deepcopy(item))
            continue
        result['logic'].append(tree)
        for unknown in reader.unknown_nodes:
            pending_span = unknown.get('unresolved_span', unknown['span'])
            item = {'kind': 'narrative', 'reason': unknown['reason'], 'text': reader.text[slice(*pending_span)],
                    'source': reader.source_at(*pending_span), 'scope': list(scope), 'layers': ['B', 'L'],
                    'category': 'software_unsupported'}
            if item not in result['unresolved']:
                for key in ('unresolved', 'blockers', 'pending_requirements'):
                    result[key].append(copy.deepcopy(item))
    result['complete'] = result['semantic_complete'] = bool(result['logic']) and not result['unresolved']
    result['required_matcher_features'] = sorted(reader.features)
    return result
