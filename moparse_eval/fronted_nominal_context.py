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
_OPERATION_CONTROLLER = re.compile(r'(?:we|they|you|I|he|she|it|the company|the group|the board)', re.I)


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


def read_fronted_operation(reader, start, end, actor, depth):
    """A nonfinite operation modifies its own following finite proposition.

    Reuse the existing fronted-context, proposition and coordination nodes.
    The finite subject is a grammatical controller, never an invented actor;
    the operation is an operand and cannot create unconditional B facts.
    """
    prefix = re.match(r'(?P<marker>By|Through|In order to|For the purpose of)\s+', reader.syntax[start:end], re.I)
    if prefix is None:
        return None
    from .active_aspect_requirements import active_forms
    from .infinitival_syntax import _main_leaves, _unknown_node
    from .narrative_requirements import _ACTIONS, _Unknown

    marker = prefix['marker'].lower()
    infinitival = marker == 'in order to'
    _, progressive = active_forms()
    forms = {base: base for base in _ACTIONS.values()} if infinitival else progressive
    first = re.match(r'[A-Za-z]+\b', reader.syntax[start + prefix.end():end])
    if first is None or first[0].lower() not in forms:
        # A nominal By/Through PP is owned by a different source grammar.
        return None
    reader.features.add('fronted_nominal_context')
    candidates = []
    for comma in re.finditer(',', reader.syntax[start + prefix.end():end]):
        boundary = start + prefix.end() + comma.start()
        reader.pending_clause_context = None
        try:
            child = reader.parse(boundary + 1, end, actor, depth + 1)
            leaves = _main_leaves(child)
            controls = {tuple(leaf['subject_span']) for leaf in leaves}
            main_predicate = leaves[0]['predicate_span'] if leaves else None
        except _Unknown as error:
            known = reader.pending_clause_context
            if not known or known['actor'][0] <= boundary:
                continue
            child = _unknown_node(reader, boundary + 1, end, error)
            child['known_roles'] = {'subject': reader.text[slice(*known['actor'])],
                'subject_source': reader.source_at(*known['actor']), 'attribute': known['attribute'],
                'predicate': reader.text[slice(*known['predicate_span'])],
                'predicate_source': reader.source_at(*known['predicate_span'])}
            controls, main_predicate = {tuple(known['actor'])}, known['predicate_span']
        if (len(controls) == 1 and main_predicate and next(iter(controls))[0] > boundary
                and _OPERATION_CONTROLLER.fullmatch(reader.text[slice(*next(iter(controls)))])):
            candidates.append((boundary, child, next(iter(controls)), main_predicate))
    if len(candidates) != 1:
        raise _Unknown('fronted_operation_main_controller_unresolved')
    boundary, child, controller, main_predicate = candidates[0]
    body_start = start + prefix.end()
    joins = [match for match in re.finditer(r'\b(?P<operator>and|or)\s+(?P<next>[A-Za-z]+)\b',
             reader.syntax[body_start:boundary], re.I) if match['next'].lower() in forms]
    operators = {match['operator'].lower() for match in joins}
    if len(operators) > 1:
        raise _Unknown('fronted_operation_mixed_coordination_unresolved')
    chunks, cursor = [], body_start
    for join in joins:
        chunks.append((cursor, body_start + join.start()))
        cursor = body_start + join.start('next')
    chunks.append((cursor, boundary))
    operations = []
    for a, b in chunks:
        a, b = reader.trim(a, b)
        verb = re.match(r'[A-Za-z]+\b\s*', reader.syntax[a:b])
        if verb is None or verb[0].strip().lower() not in forms:
            raise _Unknown('fronted_operation_verb_form_unresolved')
        printed = verb[0].strip()
        try:
            operation = reader.predicate_objects(controller, reader.text[a:a + len(printed)], forms[printed.lower()],
                [a, a + len(printed)], a + verb.end(), b, statement_start=a, statement_end=b)
        except _Unknown as error:
            operation = _unknown_node(reader, a, b, error)
        operations.append(operation)
    operation = operations[0] if len(operations) == 1 else {'kind': 'coordination', 'mode': 'actions',
        'operator': next(iter(operators)), 'children': operations,
        'operator_spans': [[body_start + join.start('operator'), body_start + join.end('operator')] for join in joins],
        'span': [body_start, max(boundary, controller[1])]}
    marker_span = [start + prefix.start('marker'), start + prefix.end('marker')]
    return {'kind': 'fronted_context', 'preposition': reader.text[slice(*marker_span)], 'operator': marker,
        'role': 'purpose' if marker in {'in order to', 'for the purpose of'} else 'means',
        'context': reader.text[body_start:boundary], 'context_span': [body_start, boundary],
        'preposition_span': marker_span, 'operator_span': marker_span, 'separator_span': [boundary, boundary + 1],
        'control': {'kind': 'subject_control', 'controller': reader.text[slice(*controller)],
                    'controller_source': reader.source_at(*controller), 'main_predicate_source': reader.source_at(*main_predicate)},
        'operation': operation, 'child': child, 'span': [start, end]}


def validate_fronted_operation(node, literal):
    """Verify original marker, controller, action forms and operand ownership."""
    if node.get('operator') == 'according_to':
        from .cjk_circumstances import validate_cjk_nominal

        phrase = node.get('context_phrase', {})
        if (node.get('role') != 'basis' or node.get('preposition') not in {'根據', '根据'}
                or literal(node.get('operator_source'), 'basis marker') != node['preposition']
                or phrase.get('source') != node.get('context_source')
                or literal(node.get('context_source'), 'basis context') != node.get('context')
                or literal(node.get('separator_source'), 'basis separator') not in {'，', ','}):
            raise ValueError('Chinese basis loses its printed marker, context or boundary')
        validate_cjk_nominal(phrase, literal)
        return
    if node.get('operator') not in {'by', 'through', 'in order to', 'for the purpose of'}:
        return
    from .active_aspect_requirements import active_forms
    from .infinitival_syntax import _main_leaves
    from .narrative_requirements import _ACTIONS

    marker = literal(node.get('operator_source'), 'fronted operation marker')
    expected_role = 'purpose' if node['operator'] in {'in order to', 'for the purpose of'} else 'means'
    if not isinstance(marker, str) or marker.lower() != node['operator'] or node.get('role') != expected_role:
        raise ValueError('fronted operation marker/role differs from original source')
    control = node.get('control', {})
    if (control.get('kind') != 'subject_control' or literal(control.get('controller_source'), 'fronted controller') != control.get('controller')
            or not _OPERATION_CONTROLLER.fullmatch(control.get('controller', ''))):
        raise ValueError('fronted operation lacks its literal grammatical controller')
    outer = node.get('source', {})
    outer_span = outer.get('text_span', [])
    for origin in (node.get('operator_source'), control.get('controller_source'), control.get('main_predicate_source')):
        span = origin.get('text_span', []) if isinstance(origin, dict) else []
        if (len(outer_span) != 2 or len(span) != 2 or not outer_span[0] <= span[0] < span[1] <= outer_span[1]
                or any(origin.get(key) != outer.get(key) for key in ('path', 'lines', 'cell', 'block', 'native_path'))):
            raise ValueError('fronted operation borrowed an operator/controller from another statement')
    leaves = _main_leaves(node.get('child', {'kind': 'unknown'}))
    known = node.get('child', {}).get('known_roles', {})
    if not (leaves and all(leaf.get('subject_source') == control.get('controller_source') for leaf in leaves)
            or known.get('subject_source') == control.get('controller_source')):
        raise ValueError('fronted operation controller is not the main subject')
    if control.get('main_predicate_source') not in [leaf.get('predicate_source') for leaf in leaves] + [known.get('predicate_source')]:
        raise ValueError('fronted operation lost its actual main predicate source')
    operation = node.get('operation')
    if not isinstance(operation, dict):
        raise ValueError('fronted operation lacks its structured operand')
    _, progressive = active_forms()
    forms = {base: base for base in _ACTIONS.values()} if node['operator'] == 'in order to' else progressive
    for leaf in _main_leaves(operation):
        raw = literal(leaf.get('predicate_source'), 'nonfinite operation predicate')
        if (not isinstance(raw, str) or forms.get(raw.lower()) != leaf.get('attribute')
                or leaf.get('subject_source') != control.get('controller_source') or 'tense' in leaf):
            raise ValueError('fronted operation has an unbound action/controller or invented tense')


def validate_fronted_operation_graph(graph, resolve):
    """Bind each raw nonfinite frame to its AST, operand bank and main edge.

    Discovery comes from this side's actual syntax, so synchronized feature or
    node-kind changes cannot hide the obligation. No answer is supplied here.
    """
    from .infinitival_syntax import _main_leaves
    from .prose_requirements import _sentence_spans
    from .source_obligations import validate_relation_binding

    def walk(value):
        if isinstance(value, dict):
            yield value
            for key, child in value.items():
                if key != 'source' and not key.endswith('_source'):
                    yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    trees = list(walk(graph.get('logical_statements', [])))
    for item in graph.get('syntax', []):
        text, source = item.get('text', ''), item.get('source', {})
        syntax = scan_quoted_nominals(text, source)['syntax_text']
        for a, b in _sentence_spans(syntax):
            match = re.match(r'\s*(?P<marker>By|Through|In order to|For the purpose of)\s+(?P<verb>[A-Za-z]+)\b', syntax[a:b], re.I)
            if not match or not (match['marker'].lower() == 'in order to' or match['verb'].lower().endswith('ing')):
                continue
            origin = _source(source, a + match.start('marker'), a + match.end('marker'))
            nodes = [node for node in trees if node.get('kind') == 'fronted_context' and node.get('operator_source') == origin]
            if len(nodes) != 1 or 'fronted_nominal_context' not in graph.get('required_matcher_features', []):
                raise ValueError('printed nonfinite operation lost its typed AST or comparison dependency')
            node = nodes[0]
            validate_fronted_operation(node, lambda origin, label: resolve(origin))
            def owns(leaf, bank):
                return [fact for fact in bank if all(fact.get(key) == leaf.get(key) for key in
                    ('subject_source', 'predicate_source', 'object_source'))]
            leaves = _main_leaves(node['operation'])
            main = _main_leaves(node['child'])
            if not leaves or not main or any(len(owns(leaf, graph.get('semantic_operands', []))) != 1 for leaf in leaves):
                raise ValueError('printed nonfinite operation lost independent operand/main evidence')
            for leaf in main:
                facts = owns(leaf, graph.get('business', []))
                if len(facts) != 1 or not any(edge.get('type') == 'narrative_fronted_context_scope'
                        and edge.get('source') == origin and validate_relation_binding(None, facts[0], edge)['equivalent']
                        for edge in graph.get('relations', [])):
                    raise ValueError('printed nonfinite operation lost its main attachment relation')
