"""Bounded Chinese circumstances and their explicitly printed operations.

This extends the existing Narrative AST. Adjunct operations are non-counting
operands; no omitted actor, date, financial cause or numerical answer is filled
in. Unsupported syntax raises the shared reader's unresolved result.
"""

from __future__ import annotations

import copy
import re

from .narrative_requirements import _Unknown

CIRCUMSTANCE_MARKERS = {'借助': 'means', '通过': 'means', '随着': 'background',
                         '由于': 'cause', '因为': 'cause', '受益于': 'cause',
                         '为了': 'purpose', '带来的': 'cause', '受': 'cause', '受到': 'cause'}
_EVENT = re.compile(r'增长|上升|下降|减少|恢复|提升|优化|转型|变动|稳健|发展|建设|变革')
_QUALIFIER = re.compile(r'保持|逐步|持续|同比')


def dependency(reader, role, child, marker=None):
    return {'kind': 'cjk_dependency', 'role': role, 'child': child,
            'marker': reader.text[slice(*marker)] if marker else None,
            **({'marker_span': list(marker)} if marker else {}),
            'span': [min(child['span'][0], marker[0] if marker else child['span'][0]),
                     max(child['span'][1], marker[1] if marker else child['span'][1])]}


def nominal(reader, start, end):
    """A bounded literal nominal, or an explicit coordinated nominal group."""
    start, end = reader.trim(start, end)
    raw = reader.text[start:end]
    if not raw or re.search(r'[，,。；;:：]|借助|随着|通过|受益于|因为|由于|为了|如果|同比|列示|列说明|带动', raw) or re.match(r'[一二三四五六七八九十]+是', raw):
        raise _Unknown('cjk_circumstance_nominal_boundary_unresolved')
    quantifier = re.match(r'部分|全部', raw)
    if quantifier:
        head = start + quantifier.end()
        child = nominal(reader, head, end)
        child.update(quantifier=quantifier[0], quantifier_span=[start, head], span=[start, end])
        return child
    if raw.endswith('投入') and raw.startswith('对'):
        head = end - 2
        orient = re.search(r'面向(?P<target>[^的]+)的', raw[1:-2])
        parts = []
        if orient:
            oa = start + 1 + orient.start()
            ob = start + 1 + orient.end()
            parts.append(dependency(reader, 'target_domain', nominal(reader, start + 1, oa), [start, start + 1]))
            activity = nominal(reader, ob, head)
            activity['parts'].append(dependency(reader, 'orientation',
                nominal(reader, oa + 2, ob - 1), [oa, oa + 2]))
            activity['link_spans'] = [[ob - 1, ob]]
            activity['span'] = [oa, head]
            parts.append(dependency(reader, 'activity', activity))
        else:
            target_end = head - 1 if reader.text[head - 1:head] == '的' else head
            parts.append(dependency(reader, 'target_domain', nominal(reader, start + 1, target_end), [start, start + 1]))
        return {'kind': 'cjk_nominal', 'head': '投入', 'head_span': [head, end], 'parts': parts,
                'link_spans': [[head - 1, head]] if not orient and target_end < head else [], 'span': [start, end]}
    suffix = re.search(r'等(?:领域)?$', raw)
    if suffix:
        middle = start + suffix.start()
        head_start = middle + 1
        return {'kind': 'cjk_nominal', 'head': reader.text[head_start:end], 'head_span': [head_start, end],
                'parts': [dependency(reader, 'non_exhaustive_members', nominal(reader, start, middle), [middle, middle + 1])],
                'span': [start, end]}
    # A nominal event owns its actual participant and change/state predicate.
    if _EVENT.search(raw) and (match := _EVENT.search(raw)) and match.end() == len(raw):
        child = event(reader, start, end)
        return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end],
                'parts': [dependency(reader, 'nominalized_event', child)], 'span': [start, end]}
    joins = list(re.finditer(r'以及|与|和|、', raw))
    if joins:
        spans, cursor = [], start
        for join in joins:
            spans.append((cursor, start + join.start()))
            cursor = start + join.end()
        spans.append((cursor, end))
        children = [nominal(reader, a, b) for a, b in spans]
        return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end],
                'parts': [{'kind': 'coordination', 'operator': 'and', 'mode': 'nominal_members',
                           'children': children, 'operator_spans': [[start + j.start(), start + j.end()] for j in joins],
                           'span': [start, end]}], 'span': [start, end]}
    if '的' in raw or _EVENT.search(raw) and not re.fullmatch(r'.{0,12}(?:规模|能力|费用率|性能|流程|组合)', raw):
        raise _Unknown('cjk_circumstance_nominal_operation_unresolved')
    return {'kind': 'cjk_nominal', 'head': raw, 'head_span': [start, end], 'parts': [], 'span': [start, end]}


def event(reader, start, end):
    """A printed intransitive change/state; nominalized events stay operands."""
    start, end = reader.trim(start, end)
    raw = reader.text[start:end]
    verbs = list(_EVENT.finditer(raw))
    if not verbs or verbs[-1].end() != len(raw):
        raise _Unknown('cjk_circumstance_event_unresolved')
    verb = verbs[-1]
    pa, pb = start + verb.start(), start + verb.end()
    sa, sb = start, pa
    qualifiers, spans = {}, {}
    while True:
        qualifier = next((m for m in _QUALIFIER.finditer(reader.text[sa:sb]) if sa + m.end() == sb), None)
        if qualifier is None:
            break
        key = 'comparison_basis' if qualifier[0] == '同比' else 'manner'
        qualifiers[key] = 'year_on_year' if key == 'comparison_basis' else qualifier[0]
        spans[key] = [sa + qualifier.start(), sa + qualifier.end()]
        sb = sa + qualifier.start()
    if reader.text[sa:sb].endswith('的'):
        spans['nominalization'] = [sb - 1, sb]
        sb -= 1
    phrase = nominal(reader, sa, sb) if sa < sb else None
    return {'kind': 'proposition', 'subject': reader.text[sa:sb], 'subject_span': [sa, sb] if sa < sb else None,
            'subject_phrase': phrase, 'attribute': verb[0], 'predicate': verb[0], 'predicate_span': [pa, pb],
            'object': '', 'object_span': [end, end], 'object_phrase': None, 'prepositional_complements': [],
            'role': 'description', 'lexical_qualifiers': qualifiers, 'lexical_qualifier_spans': spans,
            'span': [start, end]}


def operations(reader, start, end):
    """Only explicit conjunctions with complete event members license a group."""
    start, end = reader.trim(start, end)
    raw = reader.text[start:end]
    if '，' in raw:
        separators = list(re.finditer('，', raw))
        children, cursor = [], start
        for join in separators:
            children.append(operations(reader, cursor, start + join.start()))
            cursor = start + join.end()
        children.append(operations(reader, cursor, end))
        return {'kind': 'coordination', 'operator': 'and', 'mode': 'circumstance_operations',
                'children': children, 'operator_spans': [[start + j.start(), start + j.end()] for j in separators],
                'span': [start, end]}
    brought = re.search(r'带来的', raw)
    if brought:
        pa, pb = start + brought.start(), start + brought.end()
        return {'kind': 'circumstance_scope', 'operator': 'cause', 'direction': 'operand_to_child',
                'degree': None, 'simultaneous': False, 'operator_span': [pa, pb], 'span': [start, end],
                'operand': operations(reader, start, pa), 'child': event(reader, pb, end)}
    action = re.match(r'(?P<manner>持续)?(?P<verb>加大|坚持|优化|偿还)(?P<body>.+)', raw)
    if action:
        pa, pb = start + action.start('verb'), start + action.end('verb')
        obj = nominal(reader, pb, end)
        return {'kind': 'proposition', 'subject': '', 'subject_span': None, 'subject_phrase': None,
                'attribute': action['verb'], 'predicate': action['verb'], 'predicate_span': [pa, pb],
                'object': reader.text[pb:end], 'object_span': [pb, end], 'object_phrase': obj,
                'prepositional_complements': [], 'role': 'description', 'span': [start, end],
                'lexical_qualifiers': {'manner': action['manner']} if action['manner'] else {},
                'lexical_qualifier_spans': {'manner': [start, pa]} if action['manner'] else {}}
    # A separator inside a participant list is not an event conjunction.
    joins = [m for m in re.finditer(r'以及|、|，', raw)
             if any(raw[:m.start()].endswith(v) for v in ('优化', '提升', '增长', '稳健', '转型', '下降'))]
    if not joins:
        return event(reader, start, end)
    children, cursor = [], start
    for join in joins:
        children.append(event(reader, cursor, start + join.start()))
        cursor = start + join.end()
    children.append(event(reader, cursor, end))
    return {'kind': 'coordination', 'operator': 'and', 'mode': 'circumstance_operations',
            'children': children, 'operator_spans': [[start + j.start(), start + j.end()] for j in joins],
            'span': [start, end]}


def parse_circumstance(reader, start, end):
    start, end = reader.trim(start, end)
    leading = re.match(r'(?P<simultaneous>同时)?(?P<marker>借助|通过|随着|由于|因为|为了|受益于)', reader.text[start:end])
    if leading is None:
        return None
    boundary = re.search(r'[，,]', reader.text[start + leading.end():end])
    if boundary is None:
        raise _Unknown('cjk_circumstance_main_boundary_unresolved')
    cut = start + leading.end() + boundary.start()
    child = measurement_tree(reader, cut + 1, end) or operations(reader, cut + 1, end)
    return {'kind': 'circumstance_scope', 'operator': CIRCUMSTANCE_MARKERS[leading['marker']],
            'direction': 'operand_to_child', 'degree': None, 'simultaneous': bool(leading['simultaneous']),
            **({'simultaneous_span': [start, start + 2]} if leading['simultaneous'] else {}),
            'operator_span': [start + leading.start('marker'), start + leading.end('marker')], 'span': [start, end],
            'operand': operations(reader, start + leading.end(), cut),
            'child': child}


def measurement_tree(reader, start, end):
    from .cjk_measurement_requirements import read_cjk_measurements

    result = read_cjk_measurements(reader.text[start:end], reader.source_at(start, end), scope=reader.scope)
    return result['logic'][0] if result['complete'] else None


def measurement_spans(text, start, end):
    """Syntax-only measurement cuts; the enclosing adjunct remains obligatory."""
    raw = text[start:end]
    cause = re.search(r'[，,](?:主要)?受.+的影响[。.]?$', raw)
    if cause:
        return [(start, start + cause.start())]
    if raw.startswith(('通过', '借助')):
        dated = list(re.finditer(r'[，,](?=(?:19|20)\d{2}年)', raw))
        if dated:
            return [(start + dated[-1].end(), end - 1 if text[end - 1] in '。.' else end)]
    return [(start, end)]


def composition_spans(text, start, end):
    """Expose independently asserted clauses; keep each adjunct with its owner."""
    raw = text[start:end]
    if raw.startswith(('通过', '借助')):
        dated = list(re.finditer(r'[，,](?=(?:19|20)\d{2}年)', raw))
        if dated and re.search(r'[，,]', raw[:dated[-1].start()]):
            # Through X, do Y, dated Z: the first comma licenses X -> Y.
            # A later dated assertion does not establish Y -> Z causation.
            cut = start + dated[-1].start()
            return [(start, cut), (cut + 1, end)]
    attached = re.search(r'[，,](?=同时受益于)', raw)
    if attached:
        cut = start + attached.start()
        prefix = text[start:cut]
        comma = re.search(r'[，,]', prefix)
        if comma:
            return [(start, start + comma.start()), (start + comma.end(), cut), (cut + 1, end)]
        return [(start, cut), (cut + 1, end)]
    return [(start, end)]


def parse_composed(reader, start, end):
    composed = parse_circumstance(reader, start, end)
    if composed is not None:
        return composed
    start, end = reader.trim(start, end)
    raw = reader.text[start:end]
    cause = re.search(r'[，,](?P<degree>主要)?(?P<marker>受到|受)(?P<body>.+)的影响$', raw)
    if cause:
        cut = start + cause.start()
        child = measurement_tree(reader, start, cut)
        if child is None:
            raise _Unknown('cjk_causal_result_unresolved')
        pa, pb = start + cause.start('marker'), start + cause.end('marker')
        return {'kind': 'circumstance_scope', 'operator': 'cause', 'direction': 'operand_to_child',
                'degree': '主要' if cause['degree'] else None, 'simultaneous': False,
                **({'degree_span': [start + cause.start('degree'), start + cause.end('degree')]} if cause['degree'] else {}),
                'operator_span': [pa, pb], 'suffix_span': [end - 3, end], 'span': [start, end],
                'operand': operations(reader, start + cause.start('body'), end - 3), 'child': child,
                'target_source': copy.deepcopy(child['clauses'][-1]['source'])}
    if re.match(r'(?:持续)?(?:加大|坚持|优化|偿还)', raw):
        return operations(reader, start, end)
    if re.search(r'\d', raw):
        measured = measurement_tree(reader, start, end)
        if measured is not None:
            return measured
    # A bare 变动/发展/建设 may be a column or activity label. Its nominal
    # use is licensed inside an explicit adjunct, not as an asserted main
    # clause merely because a suffix resembles an event.
    if not re.search(r'[，,]', raw) and re.search(r'(?:增长|上升|下降|减少|恢复|提升)$', raw):
        return event(reader, start, end)
    return None


def validate_cjk_nominal(node, literal):
    """Check every nominal constituent and its complete literal coverage.

    This is a constituent audit, independent of the parser. A whole phrase
    source cannot pay for deleted constituents or borrowed neighboring text.
    """
    if node.get('kind') != 'cjk_nominal':
        raise ValueError('Chinese nominal type missing')
    origin = node.get('source', {})
    raw = literal(origin, 'Chinese nominal')
    bounds = origin.get('text_span', [])
    if not isinstance(raw, str) or len(bounds) != 2 or len(raw) != bounds[1] - bounds[0]:
        raise ValueError('Chinese nominal source missing')
    covered = set()

    def cut(source, value=None):
        span = source.get('text_span', []) if isinstance(source, dict) else []
        if (len(span) != 2 or any(source.get(k) != origin.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                or not bounds[0] <= span[0] <= span[1] <= bounds[1]):
            raise ValueError('Chinese nominal constituent is not local')
        printed = literal(source, 'Chinese nominal constituent')
        if value is not None and printed != value:
            raise ValueError('Chinese nominal constituent differs from source')
        covered.update(range(*span))
        return printed

    cut(node.get('head_source'), node.get('head'))
    if 'quantifier' in node:
        if node['quantifier'] not in {'部分', '全部'}:
            raise ValueError('Chinese nominal quantifier unsupported')
        cut(node.get('quantifier_source'), node['quantifier'])
    for part in node.get('parts', []):
        if part.get('kind') == 'cjk_dependency':
            role, marker = part.get('role'), part.get('marker')
            permitted = {'target_domain': {'对'}, 'orientation': {'面向'},
                         'non_exhaustive_members': {'等'}, 'activity': {None}, 'nominalized_event': {None}}
            if marker not in permitted.get(role, set()):
                raise ValueError('Chinese nominal dependency role differs from marker')
            if marker is not None:
                cut(part.get('marker_source'), marker)
            child = part.get('child', {})
            if child.get('kind') == 'cjk_nominal':
                validate_cjk_nominal(child, literal)
            elif role != 'nominalized_event' or child.get('kind') != 'proposition':
                raise ValueError('Chinese nominal dependency child unsupported')
            else:
                validate_cjk_event(child, literal)
            cut(child.get('source'))
            continue
        if part.get('kind') != 'coordination' or part.get('operator') != 'and' or len(part.get('children', [])) < 2:
            raise ValueError('Chinese nominal relation unsupported')
        for source in part.get('operator_sources', []):
            if cut(source) not in {'以及', '与', '和', '、'}:
                raise ValueError('Chinese nominal conjunction differs from source')
        for child in part['children']:
            validate_cjk_nominal(child, literal)
            cut(child['source'])
    for source in node.get('link_sources', []):
        if cut(source) != '的':
            raise ValueError('Chinese nominal grammatical link differs from source')
    missing = [i for i in range(*bounds) if i not in covered and not raw[i - bounds[0]].isspace()]
    if missing:
        raise ValueError(f'Chinese nominal has unexplained literal constituents: {origin} {missing}')


def validate_cjk_event(node, literal):
    """Audit interpreted event roles and markers without calling its parser."""
    source = node.get('source', {})
    raw = literal(source, 'Chinese event')
    outer = source.get('text_span', [])
    if not isinstance(raw, str) or len(outer) != 2:
        raise ValueError('Chinese event source missing')
    covered = set()

    def own(origin, value):
        span = origin.get('text_span', []) if isinstance(origin, dict) else []
        if (len(span) != 2 or any(origin.get(k) != source.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                or not outer[0] <= span[0] <= span[1] <= outer[1] or literal(origin, 'event constituent') != value):
            raise ValueError('Chinese event constituent not bound to own source')
        covered.update(range(*span))

    if node.get('attribute') != node.get('predicate') or not re.fullmatch(
            _EVENT.pattern + '|加大|坚持|偿还', node.get('predicate', '')):
        raise ValueError('Chinese event predicate differs from interpreted action')
    own(node.get('predicate_source'), node['predicate'])
    for role in ('subject', 'object'):
        value, phrase = node.get(role), node.get(role + '_phrase')
        if value:
            own(node.get(role + '_source'), value)
            if not phrase or phrase.get('source') != node.get(role + '_source'):
                raise ValueError('Chinese event nominal does not own its whole role')
            validate_cjk_nominal(phrase, literal)
        elif phrase is not None:
            raise ValueError('Chinese event has an invented empty participant')
    qs = node.get('lexical_qualifiers', {})
    origins = node.get('lexical_qualifier_sources', {})
    for key, origin in origins.items():
        printed = literal(origin, 'Chinese event qualifier')
        if key == 'nominalization':
            if printed != '的':
                raise ValueError('Chinese event nominalization differs from source')
        elif key == 'comparison_basis':
            if printed != '同比' or qs.get(key) != 'year_on_year':
                raise ValueError('Chinese qualitative comparison basis differs from source')
        elif key != 'manner' or printed not in {'持续', '保持', '逐步'} or qs.get(key) != printed:
            raise ValueError('Chinese qualitative manner differs from source')
        own(origin, printed)
    if set(qs) - set(origins):
        raise ValueError('Chinese event qualifier lacks its printed source')
    if any(i not in covered and not char.isspace() and char not in '，,。' for i, char in enumerate(raw, outer[0])):
        raise ValueError('Chinese event has unexplained source content')


def _leaves(node):
    if node.get('kind') == 'proposition':
        return [node]
    if node.get('kind') == 'cjk_measurement_sequence':
        return node['clauses']
    if node.get('kind') == 'coordination':
        return [leaf for child in node['children'] for leaf in _leaves(child)]
    return _leaves(node['child']) if isinstance(node.get('child'), dict) else []


def _role_sources(node):
    return [node.get('subject_source'), node.get('predicate_source', node.get('operator_source')),
            node.get('object_source', node.get('value_source'))]


def validate_circumstance_graph(graph, literal):
    """Bind every adjunct to its actual main fact and its non-counting operands.

    The audit checks source constituents, role identity and complete edges.
    Retained text, a summary flag, or an equal but unrelated neighbor cannot
    discharge these checks. No candidate or reference answer table is used.
    """
    from .narrative_requirements import _Reader
    from .source_obligations import validate_relation_binding

    if 'projections' in graph:
        business_ids = set(graph['projections']['B'])
        business = [n for n in graph['nodes'] if n['id'] in business_ids]
        operands = [n for n in graph['nodes'] if n.get('kind') == 'semantic_operand']
    else:
        business, operands = graph.get('business', []), graph.get('semantic_operands', [])
    facts = [*business, *operands]
    edges = [*graph.get('relations', []), *graph.get('operand_relations', graph.get('semantic_operand_relations', []))]
    expected = {fact['id']: [] for fact in facts}
    expected_sources = {fact['id']: [] for fact in facts}

    def bound_leaf(leaf, operand):
        candidates = [f for f in (operands if operand else business) if _role_sources(f) == _role_sources(leaf)]
        if len(candidates) != 1:
            raise ValueError('Chinese scope main/operand lacks its independent source-bound fact')
        fact = candidates[0]
        if not any(edge.get('type') == 'field_binding' and edge.get('fact_id') == fact['id']
                   and validate_relation_binding(None, fact, edge)['equivalent'] for edge in edges):
            raise ValueError('Chinese scope fact lacks its own field binding')
        return fact

    def walk(node, operand=False):
        kind = node.get('kind')
        if kind == 'circumstance_scope':
            source = node.get('source', {})
            raw = literal(source, 'Chinese circumstance')
            marker = literal(node.get('operator_source'), 'Chinese circumstance marker')
            if CIRCUMSTANCE_MARKERS.get(marker) != node.get('operator') or node.get('direction') != 'operand_to_child':
                raise ValueError('Chinese circumstance operator/direction differs from source')
            outer = source.get('text_span', [])
            covered = set()
            for name in ('operator_source', 'degree_source', 'simultaneous_source', 'suffix_source'):
                origin = node.get(name)
                if not origin:
                    continue
                span = origin.get('text_span', [])
                if (len(span) != 2 or any(origin.get(k) != source.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                        or not outer[0] <= span[0] < span[1] <= outer[1]):
                    raise ValueError('Chinese circumstance marker borrowed from another source')
                printed = literal(origin, name)
                if name == 'degree_source' and (printed != '主要' or node.get('degree') != printed):
                    raise ValueError('Chinese causal degree differs from source')
                if name == 'simultaneous_source' and (printed != '同时' or node.get('simultaneous') is not True):
                    raise ValueError('Chinese circumstance simultaneity differs from source')
                if name == 'suffix_source' and printed != '的影响':
                    raise ValueError('Chinese causal suffix differs from source')
                covered.update(range(*span))
            if bool(node.get('degree')) != bool(node.get('degree_source')) or bool(node.get('simultaneous')) != bool(node.get('simultaneous_source')):
                raise ValueError('Chinese circumstance restriction lacks its own source')
            for child in (node['operand'], node['child']):
                own = child['source']
                span = own.get('text_span', [])
                if (len(span) != 2 or any(own.get(k) != source.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                        or not outer[0] <= span[0] < span[1] <= outer[1]):
                    raise ValueError('Chinese circumstance child is not local')
                covered.update(range(*span))
            if any(i not in covered and not c.isspace() and c not in '，,。' for i, c in enumerate(raw, outer[0])):
                raise ValueError('Chinese circumstance has unexplained source content')
            leaves = _leaves(node['child'])
            if node.get('target_source'):
                leaves = [leaf for leaf in leaves if leaf.get('source') == node['target_source']]
                if len(leaves) != 1 or node['operator'] != 'cause':
                    raise ValueError('Chinese causal attachment target is not its printed result')
                # A trailing explanation after a YoY clause explains that
                # immediately preceding change, never an earlier amount.
                if node['child'].get('kind') == 'cjk_measurement_sequence' and leaves != node['child']['clauses'][-1:]:
                    raise ValueError('Chinese trailing cause is attached to the wrong metric fact')
            for leaf in leaves:
                fact = bound_leaf(leaf, operand)
                descriptor = circumstance_descriptor(_Reader, node)
                expected[fact['id']].append(descriptor)
                expected_sources[fact['id']].append({key: copy.deepcopy(node[key])
                    for key in ('operator_source', 'simultaneous_source', 'degree_source', 'suffix_source') if key in node})
                owned = [e for e in edges if e.get('type') == 'narrative_circumstance_scope' and e.get('fact_id') == fact['id']
                         and e.get('source') == node['operator_source']]
                left = {k: descriptor[k] for k in ('operator', 'direction', 'degree', 'simultaneous')}
                left['operand'] = _Reader.endpoint(node['operand'])
                if (len(owned) != 1 or owned[0].get('left') != left
                        or owned[0].get('binding_evidence', {}).get('operand_logic') != node['operand']
                        or not validate_relation_binding(None, fact, owned[0])['equivalent']):
                    raise ValueError('Chinese circumstance lacks its independently bound scope relation')
            for leaf in _leaves(node['operand']):
                bound_leaf(leaf, True)
            walk(node['operand'], True)
            walk(node['child'], operand)
        elif kind == 'coordination':
            for child in node.get('children', []):
                walk(child, operand)
        elif kind == 'proposition' and 'lexical_qualifiers' in node:
            validate_cjk_event(node, literal)
            fact = bound_leaf(node, operand)
            if any(fact.get('qualifiers', {}).get(k) != v for k, v in node['lexical_qualifiers'].items()):
                raise ValueError('Chinese qualitative fact differs from its AST qualifiers')
            if any(fact.get('qualifier_sources', {}).get(k) != v for k, v in node.get('lexical_qualifier_sources', {}).items()):
                raise ValueError('Chinese qualitative qualifier source differs from its AST owner')

    for tree in graph.get('logic', graph.get('logical_statements', [])):
        walk(tree)
    for fact in facts:
        if fact.get('qualifiers', {}).get('circumstances', []) != expected[fact['id']]:
            raise ValueError('Chinese fact circumstance summary differs from its owning AST scope')
        if fact.get('qualifier_sources', {}).get('circumstances', []) != expected_sources[fact['id']]:
            raise ValueError('Chinese fact circumstance sources differ from their own AST scope')
        for role in ('subject', 'object'):
            phrase = fact.get(role + '_phrase')
            if isinstance(phrase, dict) and phrase.get('kind') == 'cjk_nominal':
                if phrase.get('source') != fact.get(role + '_source'):
                    raise ValueError('Chinese fact nominal lost its original role boundary')
                validate_cjk_nominal(phrase, literal)
                def require_parts(value, owner_fact=fact):
                    if isinstance(value, dict):
                        if value.get('kind') == 'cjk_dependency':
                            own = [e for e in edges if e.get('type') == 'narrative_cjk_nominal_scope'
                                   and e.get('fact_id') == owner_fact['id'] and e.get('binding_evidence', {}).get('nominal_logic') == value]
                            if len(own) != 1 or own[0].get('left') != _Reader.summary(value) or not validate_relation_binding(None, owner_fact, own[0])['equivalent']:
                                raise ValueError('Chinese nominal dependency lacks its own relation')
                        if value.get('kind') == 'cjk_nominal' and value.get('quantifier'):
                            own = [e for e in edges if e.get('type') == 'narrative_cjk_quantifier_scope'
                                   and e.get('fact_id') == owner_fact['id'] and e.get('source') == value.get('quantifier_source')]
                            if len(own) != 1 or own[0].get('left') != {'quantifier': value['quantifier']}:
                                raise ValueError('Chinese nominal quantifier lacks its own scope relation')
                        for child in value.values():
                            require_parts(child)
                    elif isinstance(value, list):
                        for child in value:
                            require_parts(child)
                require_parts(phrase)


def circumstance_descriptor(reader, node):
    return {'operator': node['operator'], 'direction': node['direction'], 'degree': node['degree'],
            'simultaneous': node['simultaneous'], 'operand': reader.summary(node['operand'])}


def emit_circumstance(reader, node, context):
    reader.features.add('circumstance_scope')
    operand_context = copy.deepcopy(context)
    operand_context['semantic_operand'] = True
    operand_context['assertion_context'] = node['operator'] + '_operand'
    operand_context['contexts'].append(operand_context['assertion_context'])
    reader.emit(node['operand'], operand_context)
    context.setdefault('circumstance_nodes', []).append(node)
    reader.emit(node['child'], context)


def emit_measurements(reader, node, context):
    """Import the existing measurement reader and bind only the stated result."""
    from .cjk_measurement_requirements import read_cjk_measurements

    origin = node['source']
    offset = reader.source.get('text_span', [0])[0]
    a, b = origin['text_span']
    read = read_cjk_measurements(reader.text[a - offset:b - offset], origin, scope=reader.scope)
    if not read['complete'] or read['logic'][0] != node:
        raise _Unknown('cjk_circumstance_measurement_import_unresolved')
    reader.features.update(read['required_matcher_features'])
    identities = {}
    for original in read['facts']:
        fact = copy.deepcopy(original)
        identities[fact['id']] = fact['id'] = f'cjk_measurement:{len(reader.facts)}'
        for wrapper in (context or {}).get('circumstance_nodes', []):
            if wrapper.get('target_source') and fact['source'] != wrapper['target_source']:
                continue
            fact['qualifiers'].setdefault('circumstances', []).append(circumstance_descriptor(reader, wrapper))
            fact['qualifier_sources'].setdefault('circumstances', []).append({
                key: copy.deepcopy(wrapper[key]) for key in ('operator_source', 'simultaneous_source', 'degree_source', 'suffix_source')
                if key in wrapper})
            reader.edge('narrative_circumstance_scope', {
                'operator': wrapper['operator'], 'direction': wrapper['direction'], 'degree': wrapper['degree'],
                'simultaneous': wrapper['simultaneous'], 'operand': reader.endpoint(wrapper['operand'])},
                fact, wrapper['operator_source'], operator_source=wrapper['operator_source'], operand_logic=wrapper['operand'])
        reader.facts.append(fact)
    for original in read['relations']:
        edge = copy.deepcopy(original)
        if edge.get('fact_id') in identities:
            edge['fact_id'] = identities[edge['fact_id']]
        reader.relations.append(edge)
