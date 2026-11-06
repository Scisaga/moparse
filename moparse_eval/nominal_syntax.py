"""Bounded nominal composition and explicit preposition attachment.

This module consumes original spans, not answer indexes. Lexical argument
frames establish predicate complements; an unproved attachment stays unknown.
The same noun_phrase/prepositional_complement schema is language independent.
"""
from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z0-9%]+(?:[-'][A-Za-z0-9]+)*")
_DETERMINERS = {'the', 'a', 'an', 'our', 'its', 'their', 'this', 'these', 'those', 'my', 'your'}
_COUNTS = {'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6',
           'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10'}
_PP = re.compile(r'\b(?:subject\s+to|in\s+comparison\s+with|because\s+of|in\s+order\s+to|'
                 r'for|to|in|on|at|within|under|with|by|from|during|before|after|through|against|of)\b', re.I)
_TEMPORAL = re.compile(r'(?:(?:the\s+)?(?:year|period|quarter|month)\s+)?(?:\d{4}(?:[-–]\d{4})?|'
                       r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})$', re.I)
_NOMINAL_PP_FRAMES = {'in': {'investment', 'investments', 'interest', 'interests', 'stake', 'stakes', 'participation', 'membership'}}


def _unknown(reason, *, span=None):
    from .narrative_requirements import _Unknown
    raise _Unknown(reason, span=span)


def nominal_phrase(reader, start, end, *, depth=0, coordinated=True):
    """Build a right-bounded NP; OF owns its entire nominal complement."""
    if depth > 6:
        _unknown('narrative_nominal_depth_unresolved')
    start, end = reader.trim(start, end)
    if start == end:
        _unknown('narrative_nominal_boundary_unresolved')
    reader.nominal(start, end)
    text, syntax = reader.text, reader.syntax
    raw = syntax[start:end]
    if re.search(r'[\u3400-\u9fff]', raw):
        # Chinese lexical boundaries are supplied by its own grammar reader;
        # do not apply English last-token head guessing to Chinese compounds.
        return {'kind': 'noun_phrase', 'head': text[start:end], 'head_span': [start, end],
                'determiner': None, 'quantifier': None, 'modifiers': [],
                'prepositional_complements': [], 'coordination': None, 'span': [start, end]}
    of = re.search(r'\b(?:of|in)\b', raw, re.I)
    if of:
        marker_start, marker_end = start + of.start(), start + of.end()
        base = nominal_phrase(reader, start, marker_start, depth=depth + 1)
        if base.get('coordination'):
            # A trailing OF can modify either the last member or the shared
            # coordinated nominal. No source syntactic cue settles that here.
            _unknown('narrative_nominal_shared_complement_attachment_unresolved')
        preposition = text[marker_start:marker_end].lower()
        if preposition != 'of' and base['head'].lower() not in _NOMINAL_PP_FRAMES.get(preposition, set()):
            _unknown('narrative_nominal_preposition_attachment_unresolved')
        complement = nominal_phrase(reader, marker_end, end, depth=depth + 1)
        base['prepositional_complements'].append({'kind': 'prepositional_complement', 'preposition': text[marker_start:marker_end],
            'semantic_role': 'complement', 'attachment': {'kind': 'nominal', 'head': base['head']},
            'head_span': list(base['head_span']), 'preposition_span': [marker_start, marker_end],
            'complement': complement, 'complement_span': list(complement['span']), 'span': [marker_start, end]})
        base['span'] = [start, end]
        return base
    joins = list(re.finditer(r'\s+(and|or)\s+', raw, re.I))
    if joins:
        operators = {match[1].lower() for match in joins}
        if len(operators) != 1:
            _unknown('narrative_mixed_nominal_coordination_unresolved')
        if not coordinated:
            _unknown('narrative_nominal_coordination_unresolved')
        commas = list(re.finditer(r'(?<!\d),(?!\d)', raw))
        separators = sorted([(start + match.start(), start + match.end()) for match in commas]
            + [(start + match.start(), start + match.end()) for match in joins])
        members, cursor = [], start
        for left, right in separators:
            lo, hi = reader.trim(cursor, left)
            if lo < hi:
                members.append(nominal_phrase(reader, lo, hi, depth=depth + 1, coordinated=False))
            cursor = max(cursor, right)
        members.append(nominal_phrase(reader, cursor, end, depth=depth + 1, coordinated=False))
        # A multiword final member without its own determiner may modify the
        # whole coordinated nominal (research and development provider).
        if not commas and any(member['modifiers'] and not member['determiner'] for member in members):
            _unknown('narrative_nominal_coordination_unresolved', span=[start, end])
        # A sole leading determiner owns the coordinated nominal: "its
        # subsidiaries and affiliates" keeps the same owner when members
        # are reordered. Independently repeated determiners remain local.
        determiner, determiner_source = None, None
        if members[0].get('determiner') and all(not member.get('determiner') for member in members[1:]):
            determiner = members[0]['determiner']
            determiner_source = members[0]['determiner_source']
            first_start = determiner_source['text_span'][1] - reader.source.get('text_span', [0, 0])[0]
            members[0] = nominal_phrase(reader, first_start, members[0]['span'][1], depth=depth + 1, coordinated=False)
        result = {'kind': 'noun_phrase', 'head': '', 'head_span': [start, start], 'determiner': determiner,
                'quantifier': None, 'modifiers': [], 'prepositional_complements': [],
                'coordination': {'kind': 'coordination', 'operator': next(iter(operators)), 'mode': 'nominal_members',
                    'children': members, 'operator_spans': [[start + m.start(1), start + m.end(1)] for m in joins],
                    'span': [start, end]}, 'span': [start, end]}
        if determiner_source is not None:
            result['determiner_source'] = determiner_source
        return result
    if any(not (marker[0].lower() == 'at' and re.match(r'\s+(?:least|most)\b', raw[marker.end():], re.I))
           for marker in _PP.finditer(raw)):
        _unknown('narrative_nominal_preposition_attachment_unresolved')
    words = list(_WORD.finditer(raw))
    if not words:
        _unknown('narrative_nominal_boundary_unresolved')
    token_positions = {index for word in words for index in range(word.start(), word.end())}
    unhandled = [index for index, char in enumerate(raw) if char.isalnum() and index not in token_positions]
    if unhandled:
        # A footnote marker or unsupported non-ASCII lexical token cannot
        # silently disappear between the original subject and its NP tree.
        _unknown('narrative_nominal_token_boundary_unresolved', span=[start + unhandled[0], start + unhandled[-1] + 1])
    cursor, determiner = 0, None
    if words[0][0].lower() in _DETERMINERS:
        determiner, cursor = text[start + words[0].start():start + words[0].end()], 1
    quantifier = None
    quantity = re.match(r'(?:(?P<comparison>at\s+least|at\s+most|more\s+than|less\s+than)\s+)?(?P<value>\d+(?:\.\d+)?%?|one|two|three|four|five|six|seven|eight|nine|ten)\b', raw[words[cursor].start():], re.I) if cursor < len(words) else None
    if quantity:
        quantity_end = words[cursor].start() + quantity.end()
        if quantity_end < len(raw) and raw[quantity_end] == '%':
            quantity_end += 1
        if any(word.start() < quantity_end < word.end() for word in words):
            # 12-year is one adjectival compound, not a count of twelve
            # followed by an unrepresented suffix. Keep its original token.
            quantity = None
    if quantity and not (cursor == len(words) - 1 and not quantity['comparison']):
        origin = start + words[cursor].start()
        printed = quantity['value']
        value = _COUNTS.get(printed.lower(), printed.rstrip('%'))
        operator = {'at least': 'ge', 'at most': 'le', 'more than': 'gt', 'less than': 'lt'}.get(
            re.sub(r'\s+', ' ', (quantity['comparison'] or '').lower()), 'eq')
        qend = origin + quantity.end()
        # The percentage sign follows a word boundary rather than preceding it.
        if qend < end and text[qend] == '%':
            qend += 1
            printed += '%'
        quantifier = {'kind': 'quantity_comparison', 'operator': operator, 'value': value,
            'unit': '%' if printed.endswith('%') else 'count',
            'quantity_role': 'percentage' if printed.endswith('%') else 'count',
            'span': [origin, qend], 'value_span': [origin + quantity.start('value'), qend]}
        if quantity['comparison']:
            quantifier['operator_span'] = [origin + quantity.start('comparison'), origin + quantity.end('comparison')]
        cursor = next((index for index, word in enumerate(words) if start + word.start() >= qend), len(words))
    if cursor >= len(words):
        # A bare number can still be a nominal complement of a temporal PP.
        cursor = len(words) - 1
    head = words[-1]
    result = {'kind': 'noun_phrase', 'head': text[start + head.start():start + head.end()],
        'head_span': [start + head.start(), start + head.end()], 'determiner': determiner,
        'quantifier': quantifier, 'modifiers': [text[start + word.start():start + word.end()] for word in words[cursor:-1]],
        'prepositional_complements': [], 'coordination': None, 'span': [start, end]}
    if determiner is not None:
        result['determiner_source'] = reader.source_at(start + words[0].start(), start + words[0].end())
    result['modifier_sources'] = [reader.source_at(start + word.start(), start + word.end()) for word in words[cursor:-1]]
    return result


def _role(preposition, attribute, complement):
    prep = re.sub(r'\s+', ' ', preposition.lower())
    if prep in {'in', 'on', 'at', 'during', 'before', 'after', 'from'} and _TEMPORAL.fullmatch(complement.strip()):
        return 'temporal_scope'
    if prep == 'subject to':
        return 'restriction'
    if prep == 'within' and re.fullmatch(r'(?:the\s+)?(?:approved|permitted|specified)\s+(?:range|limit|limits)', complement.strip(), re.I):
        return 'restriction'
    if prep == 'for' and attribute in {'provide', 'offer', 'deliver', 'serve', 'develop'} and re.search(r'\b(?:customers?|clients?|users?|beneficiaries?)$', complement.strip(), re.I):
        return 'beneficiary'
    if prep == 'to' and attribute in {'provide', 'deliver', 'pay', 'sell', 'offer'}:
        return 'recipient'
    if prep == 'to' and attribute in {'sharpen', 'expand', 'reduce', 'increase', 'restrict', 'limit'}:
        return 'complement'
    if prep == 'because of':
        return 'cause'
    if prep == 'in comparison with':
        return 'comparison_target'
    if prep == 'with' and attribute in {'engage', 'interact', 'collaborate'}:
        return 'complement'
    if prep == 'in' and attribute == 'operate' and re.fullmatch(r'(?:a|the|an)\s+(?:[A-Za-z-]+\s+){0,4}(?:way|manner)', complement.strip(), re.I):
        return 'manner'
    return None


def predicate_complements(reader, start, end, attribute, predicate_span):
    """Return the direct-object boundary plus proved predicate PP attachments."""
    matches = list(_PP.finditer(reader.syntax, start, end))
    # OF belongs to the nominal object, and never starts a predicate adjunct.
    candidates = [match for match in matches if match[0].lower() != 'of'
                  and not (match[0].lower() == 'at' and re.match(r'\s+(?:least|most)\b', reader.syntax[match.end():end], re.I))]
    if candidates and candidates[0][0].lower() == 'in':
        prefix = reader.syntax[start:candidates[0].start()].strip()
        if re.search(r'\b(?:' + '|'.join(_NOMINAL_PP_FRAMES['in']) + r')$', prefix, re.I):
            candidates = candidates[1:]
    if not candidates:
        return end, []
    first = candidates[0]
    result = []
    for index, marker in enumerate(candidates):
        limit = candidates[index + 1].start() if index + 1 < len(candidates) else end
        lo, hi = reader.trim(marker.end(), limit)
        complement_text = reader.text[lo:hi]
        role = _role(marker[0], attribute, complement_text)
        if role is None:
            _unknown('narrative_prepositional_attachment_unresolved')
        # A finite/infinitival predicate cannot be replaced with a nominal PP.
        from .narrative_requirements import _VERB

        if (marker[0].lower() == 'to' and _VERB.match(complement_text)
                or re.match(r'(?:expand|increase|reduce|develop|operate|acquire|maintain|support)\b', complement_text, re.I)):
            _unknown('narrative_prepositional_clause_unresolved')
        complement = nominal_phrase(reader, lo, hi)
        result.append({'kind': 'prepositional_complement', 'preposition': reader.text[marker.start():marker.end()],
            'semantic_role': role, 'attachment': {'kind': 'predicate', 'head': reader.text[slice(*predicate_span)], 'attribute': attribute},
            'head_span': list(predicate_span), 'preposition_span': [marker.start(), marker.end()],
            'complement': complement, 'complement_span': [lo, hi], 'span': [marker.start(), hi]})
    return first.start(), result


def validate_nominal_sources(graph, nodes, literal):
    """Independently check NP/PP lexical evidence and actual attachment owners.

    The audit reads the retained graph and source cuts. It does not regenerate
    a graph, call the grammar reader, or use neighboring facts as evidence.
    """
    def cut(source, expected, label):
        if not isinstance(source, dict) or literal(source, label) != expected:
            raise ValueError('nominal source differs from literal: ' + label)

    def within(outer, inner):
        if not isinstance(outer, dict) or not isinstance(inner, dict):
            return False
        if any(outer.get(key) != inner.get(key) for key in ('path', 'lines', 'cell', 'block')):
            return False
        a, b = outer.get('text_span', [0, 0])
        c, d = inner.get('text_span', [0, 0])
        return a <= c <= d <= b

    def pp(node, owner):
        cut(node.get('preposition_source'), node.get('preposition'), 'preposition')
        if node.get('complement_source') != node.get('complement', {}).get('source'):
            raise ValueError('nominal PP complement source differs from child')
        if not within(node.get('source'), node.get('complement_source')):
            raise ValueError('nominal PP complement lies outside its scope')
        attachment = node.get('attachment', {})
        expected_kind = 'nominal' if owner.get('kind') == 'noun_phrase' else 'predicate'
        expected_head = owner.get('head') if expected_kind == 'nominal' else owner.get('predicate')
        expected_source = owner.get('head_source') if expected_kind == 'nominal' else owner.get('predicate_source')
        if (attachment.get('kind') != expected_kind or attachment.get('head') != expected_head
                or node.get('head_source') != expected_source):
            raise ValueError('nominal PP attachment owner differs from actual head')
        if expected_kind == 'nominal':
            prep = node.get('preposition', '').lower()
            if (node.get('semantic_role') != 'complement' or prep != 'of'
                    and owner.get('head', '').lower() not in _NOMINAL_PP_FRAMES.get(prep, set())):
                raise ValueError('nominal PP relation does not match OF attachment')
        else:
            complement = literal(node['complement_source'], 'PP complement')
            if _role(node.get('preposition', ''), owner.get('attribute'), complement) != node.get('semantic_role'):
                raise ValueError('nominal PP semantic role has no argument-frame evidence')
        walk(node.get('complement'), node)

    def quantity(node):
        raw_value = literal(node.get('value_source'), 'quantifier value')
        if not isinstance(raw_value, str):
            raise ValueError('nominal quantity value lacks source evidence')
        expected = _COUNTS.get(raw_value.lower(), raw_value.rstrip('%'))
        if expected != node.get('value'):
            raise ValueError('nominal quantity source differs from value')
        unit = '%' if raw_value.endswith('%') else 'count'
        if node.get('unit') != unit or node.get('quantity_role') != ('percentage' if unit == '%' else 'count'):
            raise ValueError('nominal quantity unit differs from source')
        if node.get('operator_source'):
            raw_operator = re.sub(r'\s+', ' ', literal(node['operator_source'], 'quantifier operator').lower())
            if {'at least': 'ge', 'at most': 'le', 'more than': 'gt', 'less than': 'lt'}.get(raw_operator) != node.get('operator'):
                raise ValueError('nominal quantity comparison operator differs from source')
        elif node.get('operator') != 'eq':
            raise ValueError('nominal quantity comparison lacks operator source')

    def walk(node, owner=None):
        if isinstance(node, list):
            for item in node:
                walk(item, owner)
            return
        if not isinstance(node, dict):
            return
        kind = node.get('kind')
        if kind == 'prepositional_complement':
            pp(node, owner or {})
            return
        if kind == 'quantity_comparison' and isinstance(owner, dict) and owner.get('kind') == 'noun_phrase':
            quantity(node)
        if kind == 'noun_phrase':
            if node.get('head'):
                cut(node.get('head_source'), node['head'], 'nominal head')
            elif not node.get('coordination'):
                raise ValueError('nominal phrase has neither head nor coordination')
            if node.get('determiner') is not None:
                cut(node.get('determiner_source'), node['determiner'], 'nominal determiner')
            modifiers, origins = node.get('modifiers', []), node.get('modifier_sources', [])
            if len(modifiers) != len(origins):
                raise ValueError('nominal modifier sources are incomplete')
            for modifier, source in zip(modifiers, origins, strict=True):
                cut(source, modifier, 'nominal modifier')
            for child in [node.get('quantifier'), node.get('coordination'), *node.get('prepositional_complements', [])]:
                walk(child, node)
            # A preserved raw object string is not evidence that its nominal
            # modifiers, quantity or attachment were interpreted. Every
            # nonpunctuation source token needs its own constituent evidence.
            pieces = [node.get('head_source'), node.get('determiner_source'), *origins]
            if node.get('quantifier'):
                pieces.append(node['quantifier'].get('source'))
            for relation in node.get('prepositional_complements', []):
                pieces.append(relation.get('source'))
            coordination = node.get('coordination')
            if coordination:
                pieces.extend(child.get('source') for child in coordination.get('children', []))
                pieces.extend(coordination.get('operator_sources', []))
            raw = literal(node.get('source'), 'nominal phrase')
            if not isinstance(raw, str):
                raise ValueError('nominal phrase lacks source evidence')
            start = node['source'].get('text_span', [0, 0])[0]
            covered = set()
            for piece in pieces:
                if piece is None:
                    continue
                if not within(node.get('source'), piece):
                    raise ValueError('nominal constituent lies outside its source phrase')
                lo, hi = piece.get('text_span', [0, 0])
                covered.update(range(lo - start, hi - start))
            if any(index not in covered and char.isalnum() for index, char in enumerate(raw)):
                raise ValueError('nominal source has uninterpreted constituent tokens')
            return
        for key, child in node.items():
            if isinstance(child, (dict, list)) and not key.endswith('_source') and key not in {'source', 'sources'}:
                walk(child, node if kind == 'proposition' or 'predicate_source' in node else owner)

    walk(graph.get('logic', []))
    for node in nodes.values():
        walk(node)
