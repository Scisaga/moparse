"""Bounded source-bound discourse and controlled infinitival relations.

Controller spans are grammatical references to explicitly printed actors or
objects. Purpose and complement operands never become unconditional facts.
Unresolved main syntax can retain a separately parsed infinitival operand.
"""
from __future__ import annotations

import re

_DISCOURSE = re.compile(r'(?P<marker>For example|For instance|However|Moreover|In addition|In particular)\s*,\s*', re.I)
_PURPOSE_PREDICATES = {'provide', 'make', 'use', 'develop', 'build', 'create', 'operate', 'support', 'leverage', 'invest', 'capture'}
_OBJECT_CONTROL = {'help', 'enable', 'allow', 'require'}
_NOMINAL_INFINITIVE_HEADS = {'right', 'rights', 'ability', 'permission', 'opportunity', 'opportunities'}


def _main_leaves(node):
    if node['kind'] == 'proposition':
        return [node]
    if node['kind'] == 'coordination':
        return [leaf for child in node['children'] for leaf in _main_leaves(child)]
    if node['kind'] == 'unknown':
        return []
    return _main_leaves(node['child'])


def read_discourse_scope(reader, start, end, actor, depth):
    marker = _DISCOURSE.match(reader.syntax, start, end)
    if marker is None:
        return None
    from .narrative_requirements import _Unknown

    reader.features.add('discourse_scope')
    try:
        child = reader.parse(marker.end(), end, actor, depth + 1)
    except _Unknown as error:
        child = _unknown_node(reader, marker.end(), end, error)
    operator = re.sub(r'\s+', '_', marker['marker'].lower())
    return {'kind': 'discourse_scope', 'operator': operator,
        'role': 'example' if operator in {'for_example', 'for_instance'} else 'contrast' if operator == 'however' else 'addition' if operator in {'moreover', 'in_addition'} else 'focus',
        'marker': reader.text[slice(*marker.span('marker'))], 'marker_span': list(marker.span('marker')),
        'operator_span': list(marker.span('marker')), 'separator_span': [marker.end('marker'), marker.end()],
        'child': child, 'span': [start, end]}


def _unknown_node(reader, start, end, error):
    return {'kind': 'unknown', 'status': 'unresolved', 'reason': str(error),
        'text': reader.text[start:end], 'span': [start, end],
        **({'unresolved_span': list(error.span)} if error.span else {})}


def _infinitive(reader, start, end, actor, depth):
    from .narrative_requirements import _ACTIONS, _Unknown

    try:
        tree = reader.parse(start, end, actor, depth + 1)
    except _Unknown as error:
        return _unknown_node(reader, start, end, error)

    def strip(node):
        if isinstance(node, dict):
            if node.get('kind') == 'proposition' and node.get('subject_span', [start])[0] < start:
                printed = node['predicate'].lower()
                if printed != _ACTIONS.get(printed):
                    raise _Unknown('narrative_infinitival_verb_form_unresolved')
                node.pop('tense', None)
                node.pop('tense_span', None)
            for child in node.values():
                if isinstance(child, (dict, list)):
                    strip(child)
        elif isinstance(node, list):
            for child in node:
                strip(child)
    try:
        strip(tree)
    except _Unknown as error:
        return _unknown_node(reader, start, end, error)
    return tree


def read_infinitival_scope(reader, start, end, actor, depth):
    from .narrative_requirements import _ACTIONS, _Unknown

    expression = re.compile(r'\bto\s+(?P<verb>' + '|'.join(sorted({base for base in _ACTIONS.values()}, key=len, reverse=True)) + r')\b', re.I)
    markers = [marker for marker in expression.finditer(reader.syntax, start, end)
               if not re.search(r'\bable\s*$', reader.syntax[start:marker.start()], re.I)]
    if not markers:
        return None
    marker = markers[0]
    # The printed TO token alone cannot decide an argument's role. Only an
    # actual finite parent frame and its independently read controller do so.
    reader.pending_clause_context = None
    try:
        child = reader.parse(start, marker.start(), actor, depth + 1)
        leaves = _main_leaves(child)
        attributes = {leaf['attribute'] for leaf in leaves}
        actors = {tuple(leaf['subject_span']) for leaf in leaves}
    except _Unknown as error:
        context = reader.pending_clause_context
        if not context or not (start <= context['predicate_span'][0] < marker.start()):
            return None
        attributes = {context['attribute']}
        actors = {tuple(context['actor'])}
        leaves = []
        child = _unknown_node(reader, start, marker.start(), error)
        child['known_roles'] = {'subject': reader.text[slice(*context['actor'])],
            'subject_source': reader.source_at(*context['actor']),
            'predicate': reader.text[slice(*context['predicate_span'])],
            'predicate_source': reader.source_at(*context['predicate_span']), 'attribute': context['attribute']}
    if not attributes or len(actors) != 1:
        return None
    if len(attributes) == 1 and next(iter(attributes)) in _OBJECT_CONTROL:
        if not leaves:
            return None
        controller = [min(leaf['object_span'][0] for leaf in leaves), max(leaf['object_span'][1] for leaf in leaves)]
        kind, operator, control_kind = 'controlled_infinitive_scope', 'complement', 'object_control'
    elif attributes <= _PURPOSE_PREDICATES:
        if any(leaf.get('object_phrase', {}).get('head', '').lower() in _NOMINAL_INFINITIVE_HEADS
               for leaf in leaves if isinstance(leaf.get('object_phrase'), dict)):
            return None
        controller = list(next(iter(actors)))
        kind, operator, control_kind = 'purpose_scope', 'purpose', 'subject_control'
    else:
        return None
    reader.features.add(kind)
    operand = _infinitive(reader, marker.start('verb'), end, tuple(controller), depth)
    return {'kind': kind, 'operator': operator, 'operator_span': [marker.start(), marker.start() + 2],
        'control': {'kind': control_kind, 'controller': reader.text[slice(*controller)],
                    'controller_source': reader.source_at(*controller)},
        'child': child, 'operand': operand, 'span': [start, end]}


def validate_infinitival_sources(graph, nodes, literal):
    """Validate marker/control/operand evidence without running the parser."""
    def cut(source, value, label):
        if not isinstance(source, dict) or literal(source, label) != value:
            raise ValueError('infinitival source differs from original literal: ' + label)

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        kind = node.get('kind')
        if kind == 'discourse_scope':
            cut(node.get('marker_source'), node.get('marker'), 'discourse marker')
            marker = literal(node['marker_source'], 'discourse marker')
            expected = re.sub(r'\s+', '_', marker.lower())
            roles = {'for_example': 'example', 'for_instance': 'example', 'however': 'contrast',
                     'moreover': 'addition', 'in_addition': 'addition', 'in_particular': 'focus'}
            if (node.get('operator') != expected or roles.get(expected) != node.get('role')
                    or node.get('operator_source') != node.get('marker_source')):
                raise ValueError('discourse marker scope differs from original source')
        if kind in {'purpose_scope', 'controlled_infinitive_scope'}:
            marker = literal(node.get('operator_source'), 'infinitival operator')
            if not isinstance(marker, str) or marker.lower() != 'to':
                raise ValueError('infinitival scope lacks its original TO marker')
            control = node.get('control', {})
            cut(control.get('controller_source'), control.get('controller'), 'infinitival controller')
            leaves = _main_leaves(node.get('child', {'kind': 'unknown'}))
            if kind == 'purpose_scope':
                if node.get('operator') != 'purpose' or control.get('kind') != 'subject_control':
                    raise ValueError('purpose has changed infinitival attachment role')
                if leaves:
                    if (any(leaf.get('attribute') not in _PURPOSE_PREDICATES for leaf in leaves)
                            or any(leaf.get('subject_source') != control.get('controller_source') for leaf in leaves)):
                        raise ValueError('purpose controller differs from its actual main subject')
                else:
                    known = node.get('child', {}).get('known_roles', {})
                    if known.get('subject_source') != control.get('controller_source') or known.get('attribute') not in _PURPOSE_PREDICATES:
                        raise ValueError('partial purpose has no independent grammatical controller source')
                    cut(known.get('subject_source'), known.get('subject'), 'partial main subject')
                    cut(known.get('predicate_source'), known.get('predicate'), 'partial main predicate')
                    from .active_aspect_requirements import active_forms
                    from .narrative_requirements import _ACTIONS

                    perfect, progressive = active_forms()
                    printed = known.get('predicate', '').lower()
                    if _ACTIONS.get(printed, perfect.get(printed, progressive.get(printed))) != known.get('attribute'):
                        raise ValueError('partial main predicate attribute differs from its actual source form')
            else:
                if (node.get('operator') != 'complement' or control.get('kind') != 'object_control' or not leaves
                        or len({leaf.get('attribute') for leaf in leaves}) != 1
                        or leaves[0].get('attribute') not in _OBJECT_CONTROL):
                    raise ValueError('controlled infinitive lacks its actual licensing predicate')
                sources = [leaf.get('object_source', {}) for leaf in leaves]
                outer = control.get('controller_source', {})
                if any(any(source.get(key) != outer.get(key) for key in ('path', 'lines', 'cell', 'block')) for source in sources):
                    raise ValueError('object controller has another source identity')
                expected_span = [min(source['text_span'][0] for source in sources), max(source['text_span'][1] for source in sources)]
                if outer.get('text_span') != expected_span:
                    raise ValueError('object controller scope differs from its actual direct objects')
            operand = node.get('operand', {})
            for leaf in _main_leaves(operand):
                if leaf.get('subject_source') != control.get('controller_source'):
                    raise ValueError('infinitival operand subject differs from its grammatical controller')
                if leaf.get('tense') is not None:
                    raise ValueError('infinitival operand cannot manufacture a finite tense')
        for key, child in node.items():
            if isinstance(child, (dict, list)) and key not in {'source', 'sources', 'operator_path'} and not key.endswith('_source'):
                walk(child)

    walk(graph.get('logic', []))
    for node in nodes.values():
        walk(node.get('logic', {}))
