"""Document-content proofs alongside the existing interpreted B/L comparator.

The document view never claims that a lexical AST is a parsed business clause.
Exact source-form identity under the same document scope is a sufficient
preservation proof. Different wording requires the semantic comparator; an
unhandled paraphrase remains unresolved. No company or expected value selects
an execution branch, a candidate, or a tolerance.
"""

from __future__ import annotations

import copy
import re

from .requirement_ast import (
    build_document_ast,
    compare_document_ast,
    validate_content_ast,
)
from .source_requirements import original_source_cuts


def _location(source):
    return tuple((key, tuple(source[key]) if isinstance(source.get(key), list) else source.get(key))
                 for key in ('path', 'lines', 'cell', 'block', 'native_path'))


def _same_record(left, right):
    return (left.get('path') == right.get('path') and left.get('lines') == right.get('lines') and all(
        left.get(key) == right.get(key) for key in ('cell', 'native_path') if key in left or key in right)
        and not ('block' in left and 'block' in right and left['block'] != right['block']))


def _grammar_limit(issue):
    # A bounded sentence reader declares its failed interpretation explicitly.
    # This classifies analysis only: exact original ownership, linked source
    # obligations, quantities and structure are checked separately below.
    if issue.get('comparison_domain') == 'sentence_interpretation':
        return (issue.get('kind') in {'narrative', 'proposition'}
                and set(issue.get('layers', ['B', 'L'])) <= {'B', 'L'})
    reason = issue.get('reason', '')
    return reason.startswith(('cjk_narrative_', 'narrative_', 'quoted_nominal_', 'entity_assignment_',
                              'business_preamble_', 'business_clause_', 'prose_clause_')) or reason in {
        'source_obligation_pending', 'source_has_no_supported_semantic_disposition',
        'cjk_measurement_sequence_incomplete', 'proposition_syntax_unsupported', 'proposition_object_unresolved',
        'cjk_circumstance_nominal_operation_unresolved'}


def _original_content_sources(source):
    """Project a joined analysis cut back onto each actual source fragment."""
    return original_source_cuts(source)


def _fallback_blocks(ast, issues, facts=()):
    indices = [index for index, block in enumerate(ast['children'])
            if block['role'] in {'text', 'item', 'heading'}
            and any(_same_record(block['source'], origin) and _grammar_limit(issue)
                    for issue in issues for origin in _original_content_sources(issue.get('source', {})))
            and not any(_same_record(block['source'], origin) and not _grammar_limit(issue)
                        for issue in issues for origin in _original_content_sources(issue.get('source', {})))]
    # Replacing just the tail of a joined, partly interpreted assertion would
    # retain its typed assertion as well and count the same responsibility
    # twice. Expand through that actual joined statement, never through a
    # neighbouring literal or a textual hit from a different source.
    for fact in facts:
        statement = fact.get('statement_source', fact.get('source', {}))
        if not statement.get('joined_fragments'):
            continue
        parts = _original_content_sources(statement)
        own = [i for i, b in enumerate(ast['children']) if any(_same_record(b['source'], s) for s in parts)]
        if (not any(i in indices for i in own) or not own
                or any(ast['children'][i]['role'] not in {'text', 'item'} for i in own)
                or any(ast['children'][i]['scope'] != ast['children'][own[0]]['scope']
                       or ast['children'][i]['parents'] != ast['children'][own[0]]['parents'] for i in own)
                or own != list(range(min(own), max(own) + 1))
                or any(not _grammar_limit(issue) and any(_same_record(origin, part)
                    for origin in _original_content_sources(issue.get('source', {})) for part in parts) for issue in issues)):
            continue
        indices.extend(i for i in own if i not in indices)
    return sorted(indices)


def _contains(source, origin):
    if not _same_record(source, origin):
        return False
    return (source.get('text_span') is None or origin.get('text_span') is not None
            and source['text_span'][0] <= origin['text_span'][0] <= origin['text_span'][1] <= source['text_span'][1])


def _fixed_content_requirements(ast, indices, facts, issues, units):
    """Subtract complete quantities and self-contained nominal compositions.

    Plain SVO guesses remain replaced by the approved whole-content contract.
    The bounded composed-nominal/attachment contract keeps its typed sentence
    only with a proved printed boundary and no external field-label owner.
    """
    typed = [(part, fact['id']) for fact in facts if fact.get('logic', {}).get('kind') == 'quantity_assertion'
             for part in _original_content_sources(fact['logic']['sequence_source'])]
    for fact in facts:
        boundary = fact.get('statement_boundary_evidence', {})
        sentence = boundary.get('sentence_source', {})
        semantic = fact.get('source', {})
        operators = fact.get('logic', {}).get('operator_path', [])
        if (fact.get('logic', {}).get('kind') != 'narrative_leaf' or len(operators) != 1
                or operators[0].get('kind') != 'proposition'
                or fact.get('field_label_evidence')
                or not (fact.get('object_phrase') or {}).get('compound')
                or not fact.get('prepositional_complements')
                or boundary.get('kind') != 'complete_printed_proposition_sentence'
                or boundary.get('semantic_source') != semantic
                or not sentence.get('text_span') or not semantic.get('text_span')
                or not _contains(sentence, semantic)):
            continue
        for unit in units:
            if not _same_record(unit['source'], sentence):
                continue
            raw = unit['text']
            offset = unit['source'].get('text_span', [0])[0]
            a, b = sentence['text_span']
            x, y = semantic['text_span']
            if (0 <= a - offset <= x - offset <= y - offset <= b - offset <= len(raw)
                    and not raw[a - offset:x - offset].strip()
                    and re.fullmatch(r'[.!?。！？]["”’」』）)\]]*\s*', raw[y - offset:b - offset])):
                typed.append((copy.deepcopy(sentence), fact['id']))
                break
    result, anchors = [], []
    for index in indices:
        block = ast['children'][index]
        whole = block['content']['source']['text_span']
        complete = [(source, ident) for source, ident in typed if source
                       and _contains(block['content']['source'], source)
                       and not any(_same_record(source, part) and part.get('text_span') is not None
                           and max(source['text_span'][0], part['text_span'][0])
                               < min(source['text_span'][1], part['text_span'][1])
                           for issue in issues for part in _original_content_sources(issue.get('source', {})))]
        cuts = sorted({tuple(source['text_span']) for source, _ident in complete})
        spans, cursor = [], whole[0]
        for start, end in cuts:
            if cursor < start:
                spans.append([cursor, start])
            cursor = max(cursor, end)
        if cursor < whole[1]:
            spans.append([cursor, whole[1]])
        tokens = block['content']['children']
        def piece(start, end, ident, **extra):
            leaves = [copy.deepcopy(n) for n in tokens if start <= n['source']['text_span'][0] < end]
            if not leaves:
                return None
            source = {**copy.deepcopy(block['content']['source']), 'text_span': [start, end]}
            return {**copy.deepcopy(block), 'source': source,
                'requirement_id': ident, 'block_index': index, **extra,
                'content': {'kind': 'content_sequence', 'source': source, 'children': leaves}}
        own = [p for a, b in spans if (p := piece(a, b, f'content:{index}:{a}:{b}'))]
        result.extend(own)
        if own:
            for start, end in cuts:
                anchors.append(piece(start, end, f'typed-order:{index}:{start}:{end}',
                    comparison_role='typed_order_anchor', typed_requirement_ids=sorted({
                        ident for origin, ident in complete if origin['text_span'] == [start, end]})))
    return result, anchors


def document_order_requirements(graph):
    """Fix reading-order endpoints from exclusive source partitions, before retrieval."""
    content = graph['source_form_requirements']
    anchors = graph['source_form_order_anchors']
    rows = sorted([*content, *anchors], key=lambda b: (b['block_index'], b['source']['text_span'][0]))
    orders = []

    def edge(ident, left, right, role):
        return {'id': ident, 'role': role,
            'left': left['requirement_id'], 'right': right['requirement_id'],
            'sources': [copy.deepcopy(left['source']), copy.deepcopy(right['source'])]}

    for index, (left, right) in enumerate(zip(content, content[1:], strict=False)):
        if left['block_index'] == right['block_index'] and rows.index(right) != rows.index(left) + 1:
            continue  # Its actual mixed neighbours own this partition order.
        orders.append(edge(f'L:content-order:{index}', left, right, 'content_order'))
    for index, (left, right) in enumerate(zip(rows, rows[1:], strict=False)):
        if (left['block_index'] == right['block_index']
                and sum(b.get('comparison_role') == 'typed_order_anchor' for b in (left, right)) == 1):
            orders.append(edge(f'L:mixed-order:{index}', left, right, 'mixed_typed_content_order'))
    return orders


def attach_document_ast(graph, expected):
    units = []
    for target in expected['targets']:
        scopes = target.get('selected_heading_context')
        scope = [item['text'] for item in scopes] if scopes is not None else target.get('context', [])
        if target.get('cells'):
            for cell in target['cells']:
                units.append({'kind': 'table_cell', 'text': cell.get('text', ''), 'scope': scope,
                    'source': {**target['reference'], 'cell': cell.get('id', cell.get('native_path')),
                               'row': cell.get('row'), 'column': cell.get('col'),
                               **({'native_path': cell['native_path']} if cell.get('native_path') is not None else {})},
                    'parents': target.get('parents', [])})
        else:
            units.append({'kind': target['kind'], 'text': target.get('raw_text', target['text']),
                          'source': target['reference'], 'scope': scope, 'parents': target.get('parents', [])})
    graph['comparison_contract'] = 'document_ast'
    graph['document_ast'] = build_document_ast(units)
    facts = [n for n in graph.get('nodes', graph.get('business', [])) if n.get('kind') != 'text']
    graph['source_form_units'] = _fallback_blocks(graph['document_ast'], graph['unresolved'], facts)
    graph['source_form_requirements'], graph['source_form_order_anchors'] = _fixed_content_requirements(
        graph['document_ast'], graph['source_form_units'], facts, graph['unresolved'], units)
    # Keep every semantic-analysis limitation. A preservation proof is not a
    # forged claim that the Chinese grammar reader understood those clauses.
    graph['content_comparison_ready'] = all(any(
        _same_record(graph['document_ast']['children'][index]['source'], issue.get('source', {}))
        for index in graph['source_form_units']) for issue in graph['unresolved'])



def comparison_requirement_coverage(graph):
    """A compiled responsibility map, explicitly separate from acceptance.

    Reuse the independent inventory and its semantic audit. A retained analysis
    limit needs exact source ownership and every linked obligation accounted
    for; its reason name alone never waives a source/structure/binding gap.
    """
    from .requirement_graph import evaluation_projection, is_deferred_input_scope

    blocks = graph['source_form_requirements']
    ast = graph['document_ast']
    projected = evaluation_projection(graph, document_contract=False)
    retained = _without_grammar_analysis(projected, blocks)
    banks = {'T': graph['projections']['T'], 'L': [n['id'] for n in retained['relations']],
             'B': [n['id'] for n in retained['business']]}
    ids = set().union(*map(set, banks.values()))
    inventory = graph['source_obligation_inventory']
    obligations = {n['id']: n for n in [*inventory['obligations'], *inventory['authorized_raw_inventory']['obligations']]}

    def owners(source):
        if source.get('joined_fragments'):
            parts = [owners(origin) for origin in _original_content_sources(source)]
            return sorted({ident for part in parts for ident in part}) if parts and all(parts) else []
        if source.get('text_span') is None:
            original = next((b['content']['source'] for b in ast['children']
                             if b.get('content') and _same_record(b['source'], source)), None)
            source = original or source
        return [b['requirement_id'] for b in blocks if _contains(b['content']['source'], source)]

    responsibility = []
    for row in graph['source_obligation_coverage']['dispositions']:
        obligation = obligations[row['obligation_id']]
        content = owners(obligation.get('source', {})) if 'T' not in row.get('layers', []) else []
        semantic = sorted({ref for proof in row.get('evidence', [])
                           for ref in [proof.get('requirement'), *proof.get('relations', [])] if ref in ids})
        if row['status'] != 'pending':
            status = 'content' if content and not semantic else 'semantic_or_structure'
        elif content:
            status = 'content'
        elif any(is_deferred_input_scope(graph['sample_id'], issue)
                 and obligation['id'] in issue.get('source_obligation_ids', []) for issue in graph['unresolved']):
            status = 'deferred_input_scope'
        else:
            status = 'blocking'
        responsibility.append({'obligation_id': obligation['id'], 'status': status,
            'requirement_ids': content if status == 'content' else semantic,
            'contract': 'document_content_preservation/1' if status == 'content' else 'typed_semantics_and_structure/1',
            'source': copy.deepcopy(obligation.get('source', {})),
            'analysis_disposition': row['status']})
    by_obligation = {row['obligation_id']: row for row in responsibility}
    limitations = []
    for issue in graph['unresolved']:
        linked = issue.get('source_obligation_ids', [])
        content = owners(issue.get('source', {}))
        if is_deferred_input_scope(graph['sample_id'], issue):
            status = 'deferred_input_scope'
        elif (_grammar_limit(issue) and content and 'T' not in issue.get('layers', [])
              and all(by_obligation[n]['status'] != 'blocking' for n in linked)):
            status = 'language_analysis_only'
        else:
            status = 'blocking'
        limitations.append({'issue_id': issue['id'], 'status': status, 'obligation_ids': copy.deepcopy(linked),
            'requirement_ids': content, 'contract': 'document_content_preservation/1' if content else None,
            'source': copy.deepcopy(issue.get('source', {})),
            'basis': 'complete_ordered_content_owns_this_exact_source_and_linked_obligations' if status == 'language_analysis_only' else status})
    return {'source_complete': inventory['source_complete'], 'structure_complete': True,
        'responsibility_complete': not any(r['status'] == 'blocking' for r in [*responsibility, *limitations]),
        'obligations': responsibility, 'analysis_limitations': limitations,
        'retained_semantic_requirements': banks,
        'content_relation_ownership': copy.deepcopy(retained['content_relation_ownership']),
        'content_requirement_ids': [b['requirement_id'] for b in blocks],
        'mixed_order_requirement_ids': [e['id'] for e in document_order_requirements(graph)
                                       if e['role'] == 'mixed_typed_content_order'],
        'required_capabilities': sorted({'source_span_capacity', 'bidirectional_partition', 'bounded_many_to_many',
            'order_without_value_selection', 'four_state_boundary', 'mixed_typed_content_ownership',
            'protected_structure_barriers', *({'mixed_typed_content_order'} if graph['source_form_order_anchors'] else set()),
            *({'statement_parent_scope_single_vote'} if retained['content_relation_ownership'] else set()),
            *({'literal_navigation_role'} if any(f.get('semantic_type') == 'toc_page' for f in retained['business']) else set()),
            *retained.get('required_matcher_features', [])}),
        'independent_acceptance': 'not_established_by_compilation'}

def validate_document_requirements(graph):
    from .requirement_graph import _semantic_literal

    selection = graph['source_obligation_inventory']['selection']
    expected = {'unresolved': graph['unresolved'], 'nodes': graph['nodes']}
    attach_document_ast(expected, selection)
    for key in ('document_ast', 'source_form_units', 'source_form_requirements', 'source_form_order_anchors', 'content_comparison_ready'):
        if graph.get(key) != expected[key]:
            raise ValueError('document AST differs from its complete authorized selection: ' + key)
    for block in graph['document_ast']['children']:
        if block['content'] is not None:
            validate_content_ast(block['content'], lambda source: _semantic_literal(graph['sources'], source))
    for block in graph['source_form_requirements']:
        validate_content_ast(block['content'], lambda source: _semantic_literal(graph['sources'], source))
    for block in graph['source_form_order_anchors']:
        validate_content_ast(block['content'], lambda source: _semantic_literal(graph['sources'], source))
    if graph.get('comparison_coverage') != comparison_requirement_coverage(graph):
        raise ValueError('comparison responsibility coverage differs from its source obligations')


def _resolve(graph, source):
    candidates = graph.get('text_projection', {}).get('source_fragments', [])
    candidates = [*candidates, *graph.get('text_projection', {}).get('source_cells', [])]
    for item in candidates:
        origin = item.get('source', {})
        if not _same_record(origin, source):
            continue
        if any(origin.get(key) != source.get(key) for key in ('block',) if key in origin and key in source):
            continue
        text = item.get('text', '')
        bounds = origin.get('text_span', [0, len(text)])
        cut = source.get('text_span', bounds)
        if bounds[0] <= cut[0] <= cut[1] <= bounds[0] + len(text):
            return text[cut[0] - bounds[0]:cut[1] - bounds[0]]
    return None


def _candidate_ast(evidence):
    units = copy.deepcopy(evidence.get('syntax', []))
    stack = []
    contexts = evidence.get('native_context', {}).get('by_block', {})
    for unit in units:
        # Heading visitors include the heading itself in native scope; the
        # expected reader records its ancestors. Preserve one common meaning.
        if unit.get('kind') == 'heading' and unit.get('scope', [])[-1:] == [unit.get('text')]:
            unit['scope'] = unit['scope'][:-1]
        heading = unit.get('kind') == 'heading'
        level = unit.get('heading_level')
        if heading and level is not None:
            stack = [(depth, name) for depth, name in stack if depth < level]
        record = contexts.get(unit.get('source', {}).get('block'))
        if record is not None:
            paths = [record.get('heading_path', [])]
            paths.extend(path['path'] for path in record.get('explicit_heading_paths', []) if path.get('status') == 'bound')
            if heading:
                paths = [path[:-1] if path[-1:] == [unit.get('text')] else path for path in paths]
            if unit.get('scope', []) not in paths:
                raise ValueError('document scope differs from independent native heading evidence')
        elif stack or heading and level is not None:
            if unit.get('scope', []) != [name for _depth, name in stack]:
                raise ValueError('document scope differs from the actual printed heading stream')
        if heading and level is not None:
            stack.append((level, unit['text']))
    units.extend({'kind': 'table_cell', 'text': item.get('text', ''), 'source': item['source'],
                  'scope': item.get('scope', []), 'parents': []}
                 for item in evidence.get('text_projection', {}).get('source_cells', []))
    ast = build_document_ast(units)
    ast['reading_complete'] = (evidence.get('status') not in {'failed', 'cancelled', 'timeout'}
        and not any(issue.get('reason') in {'candidate_reader_failure', 'native_region_read_failure'}
                    or issue.get('category') == 'engineering_failure'
                    for issue in [*evidence.get('blockers', []), *evidence.get('candidate_issues', [])]))
    return ast


def _without_grammar_analysis(graph, blocks):
    result = copy.deepcopy(graph)
    sources = [block['content']['source'] if block.get('content', {}).get('kind') == 'content_sequence'
               else block['source'] for block in blocks]

    def covered(item):
        origin = item.get('source', {})
        def owned(origin):
            if origin.get('text_span') is None:
                literal = _resolve(graph, origin)
                if isinstance(literal, str):
                    origin = {**origin, 'text_span': [0, len(literal)]}
            return any(_contains(source, origin) for source in sources)
        parts = _original_content_sources(origin)
        return bool(parts) and all(owned(part) for part in parts)

    removed_facts = {fact['id'] for fact in result['business'] if covered(fact)}
    result['business'] = [fact for fact in result['business'] if fact['id'] not in removed_facts]
    retained_fact_ids = {fact['id'] for fact in result['business']}

    def scope_owner(edge):
        # A content requirement owns its particular statement's parent scope.
        # The relation's type or a shared heading/line alone proves nothing:
        # both endpoints, the original cuts and independent scope provenance
        # must describe precisely that same already-owned duty.
        scope = edge.get('left')
        proof = edge.get('scope_evidence', {})
        if (edge.get('type') != 'prose_heading_membership'
                or not isinstance(scope, list) or edge.get('right', {}).get('scope') != scope
                or edge.get('fact_id') in retained_fact_ids
                or proof.get('kind') != 'unit_declared_scope' or proof.get('scope') != scope
                or not proof.get('sources')):
            return None
        owners = []
        for source in [edge.get('source', {}), *proof['sources']]:
            parts = _original_content_sources(source)
            if not parts:
                return None
            for origin in parts:
                if origin.get('text_span') is None:
                    literal = _resolve(graph, origin)
                    if not isinstance(literal, str):
                        return None
                    origin = {**origin, 'text_span': [0, len(literal)]}
                matches = [(index, block) for index, block in enumerate(blocks)
                    if block.get('scope') == scope and block.get('role') in {'text', 'item'}
                    and block.get('requirement_id') and block.get('content')
                    and _contains(block['content']['source'], origin)]
                if len(matches) != 1:
                    return None
                index, block = matches[0]
                owners.append({'requirement_id': block['requirement_id'],
                    'counted_relation_id': f'L:content:{index}',
                    'source': copy.deepcopy(block['content']['source']),
                    'scope': copy.deepcopy(scope), 'parents': copy.deepcopy(block['parents'])})
        unique = {owner['requirement_id']: owner for owner in owners}
        return {'analysis_relation_id': edge['id'], 'relation': 'statement_parent_scope',
            'source': copy.deepcopy(edge['source']), 'parent_scope': copy.deepcopy(scope),
            'owners': list(unique.values()),
            'basis': 'same_source_statement_and_declared_parent_scope_owned_before_candidate_reading'}

    scope_ownership = [proof for edge in result['relations'] if (proof := scope_owner(edge)) is not None]
    transferred_scopes = {proof['analysis_relation_id'] for proof in scope_ownership}
    result['content_relation_ownership'] = scope_ownership
    if 'requirement_ledger' in result:
        result['requirement_ledger'] = copy.deepcopy(result['business'])
    for name in ('logical_statements', 'semantic_operands', 'semantic_operand_relations', 'explicit_references',
                 'reference_roles', 'reference_dispositions'):
        result[name] = [item for item in result.get(name, []) if not covered(item)]
    syntax = []
    for item in result.get('syntax', []):
        if covered(item):
            continue
        text, origin = item.get('text', ''), item['source']
        start = origin.get('text_span', [0])[0]
        end = start + len(text)
        excluded = sorted((max(start, source['text_span'][0]), min(end, source['text_span'][1]))
                          for source in sources if _same_record(source, origin) and source.get('text_span')
                          and max(start, source['text_span'][0]) < min(end, source['text_span'][1]))
        if not excluded:
            syntax.append(item)
            continue
        cursor, remaining = start, []
        for a, b in excluded:
            if cursor < a:
                remaining.append((cursor, a))
            cursor = max(cursor, b)
        if cursor < end:
            remaining.append((cursor, end))
        for a, b in remaining:
            raw = text[a - start:b - start]
            if not raw.strip():
                continue
            own = {**copy.deepcopy(item), 'text': raw, 'source': {**origin, 'text_span': [a, b]}}
            evidence = own.get('syntax_evidence', {})
            if 'item_source' in evidence:
                evidence.update(item_source=copy.deepcopy(own['source']), item_text=raw)
            syntax.append(own)
    result['syntax'] = syntax
    result['relations'] = [edge for edge in result['relations'] if edge.get('fact_id') not in removed_facts
                           and edge['id'] not in transferred_scopes
                           and not (covered(edge) and edge['type'] not in {
                               'prose_heading_membership', 'prose_reading_order', 'heading_parent', 'heading_membership',
                               'heading_order', 'list_membership'})]
    for name in ('blockers', 'pending_requirements'):
        result[name] = [issue for issue in result.get(name, []) if not (covered(issue) and _grammar_limit(issue))]
    result['candidate_issues'] = [issue for issue in result.get('candidate_issues', [])
                                  if not (covered(issue) and _grammar_limit(issue))]
    # Runtime feature discovery still verifies every retained typed tree.
    # Features belonging solely to replaced partial trees are not requirements
    # of a source-form proof. No source or target is removed from that proof.
    from .represented_feature_comparison import REPRESENTED_FEATURES, represented_feature_checks
    from .requirement_ast import AST_FEATURE_COMPARATORS, _feature_present

    probe = {**result, 'required_matcher_features': []}
    represented = set(represented_feature_checks(probe, lambda source: _resolve(result, source))['features'])
    result['required_matcher_features'] = [feature for feature in result.get('required_matcher_features', [])
        if (feature not in AST_FEATURE_COMPARATORS or _feature_present(feature, result.get('logical_statements', [])))
        and (feature not in REPRESENTED_FEATURES or feature in represented)]
    result.pop('comparison_contract', None)
    return result


def grade_document_content(requirements, evidence):
    """Extend one grader with source-form proofs; keep T and typed B/L intact."""
    from .three_layer import _grade_layers

    wanted = requirements['source_form_units']
    expected_ast = requirements['document_ast']
    rebuilt = {'unresolved': requirements.get('blockers', []), 'business': requirements['business']}
    attach_document_ast(rebuilt, requirements['document_selection'])
    if (expected_ast != rebuilt['document_ast'] or wanted != rebuilt['source_form_units']
            or requirements.get('source_form_requirements') != rebuilt['source_form_requirements']
            or requirements.get('source_form_order_anchors') != rebuilt['source_form_order_anchors']):
        raise ValueError('document requirements omit or rebind the authorized source selection')
    base_required = _without_grammar_analysis(requirements, requirements['source_form_requirements'])
    coverage = requirements['comparison_coverage']
    if (coverage['retained_semantic_requirements']['L'] != [e['id'] for e in base_required['relations']]
            or coverage['retained_semantic_requirements']['B'] != [f['id'] for f in base_required['business']]
            or coverage.get('content_relation_ownership') != base_required['content_relation_ownership']
            or coverage.get('mixed_order_requirement_ids') != [e['id'] for e in document_order_requirements(requirements)
                                                              if e['role'] == 'mixed_typed_content_order']):
        raise ValueError('fixed comparison responsibility differs from its source-bound owners')
    candidate_ast = _candidate_ast(evidence)
    if 'document_ast' in evidence and evidence['document_ast'] != candidate_ast:
        raise ValueError('candidate document AST differs from actual native syntax')
    for graph, ast in ((requirements, expected_ast), (evidence, candidate_ast)):
        for block in ast['children']:
            if block['content'] is not None:
                validate_content_ast(block['content'], lambda source, graph=graph: _resolve(graph, source))
    wanted_ast = {'kind': 'document', 'children': sorted([
        *requirements['source_form_requirements'], *requirements['source_form_order_anchors']],
        key=lambda b: (b['block_index'], b['source']['text_span'][0]))}
    decision = compare_document_ast(wanted_ast, candidate_ast,
        source_resolver=lambda side, source: _resolve(requirements if side == 'required' else evidence, source))
    # Only owned raw cuts replace partial language analysis. An unrelated typed
    # fact or local unknown in the same native block must survive unchanged.
    content_rows = [row for row in decision['proof']['rows']
                    if row['required'].get('comparison_role') != 'typed_order_anchor']
    cuts = [span for row in content_rows if row['correspondence_status'] == 'confirmed'
            for span in row['actual_spans']]
    cuts.extend(span for row in content_rows for hit in row['retrieval']['candidates']
                if hit['exact_shape'] and hit['conflicts'] for span in hit['candidate_spans'])
    base_actual = _without_grammar_analysis(evidence, [{'source': span['source']} for span in cuts])
    base = _grade_layers(base_required, base_actual)
    score = copy.deepcopy(base)
    content_index = 0
    for index, row in enumerate(decision['proof']['rows']):
        if row['required'].get('comparison_role') == 'typed_order_anchor':
            continue  # Existing typed B/bindings own this sentence; only order uses its span.
        status = row['decision']['status']
        scope_correct = row['correspondence_status'] == 'confirmed'
        for layer, correct in (('B', status == 'equivalent'), ('L', scope_correct)):
            if layer == 'B' and row['required']['role'] == 'heading':
                continue  # Document labels own T/L; they assert no new fact.
            score['outcomes'].append({'id': f'{layer}:content:{content_index}', 'layer': layer,
                'role': 'source_form_assertion' if layer == 'B' else 'document_scope',
                'expected': row['required'], 'actual': row['actual'],
                'outcome': 'unresolved' if status == 'unresolved' and (layer == 'B' or not scope_correct)
                           else 'correct' if correct else 'incorrect',
                'reason': row['decision']['rule_id'] if layer == 'B' else 'document_scope_and_role',
                **({'software_failure': True, 'semantic_comparison_status': 'unresolved'}
                   if status == 'unresolved' and (layer == 'B' or not scope_correct) else {}),
                'document_ast_comparison': index})
        if status == 'unresolved':
            score['blockers'].append({'side': 'comparison', 'reason': row['decision']['rule_id'],
                                      'source': row['required']['source'], 'layers': ['B'] if scope_correct else ['B', 'L']})
        content_index += 1
    # Reading order is a relation independently of value/content correctness.
    rows = {b['requirement_id']: row for b, row in zip(wanted_ast['children'], decision['proof']['rows'], strict=True)}
    for edge in document_order_requirements(requirements):
        first, second = rows[edge['left']], rows[edge['right']]
        unknown = any(row['decision']['status'] == 'unresolved' and row['correspondence_status'] != 'confirmed'
                      for row in (first, second))
        correct = bool(first['actual_spans'] and second['actual_spans']) and (
            (first['actual_spans'][-1]['actual_index'], first['actual_spans'][-1]['text_span'][1]) <=
            (second['actual_spans'][0]['actual_index'], second['actual_spans'][0]['text_span'][0]))
        score['outcomes'].append({'id': edge['id'], 'layer': 'L',
            'role': 'reading_order',
            'expected': [first['required']['source'], second['required']['source']],
            'actual': [first['actual_spans'], second['actual_spans']],
            'outcome': 'unresolved' if unknown else 'correct' if correct else 'incorrect',
            **({'software_failure': True, 'semantic_comparison_status': 'unresolved'} if unknown else {}),
            'reason': edge['role']})
        if unknown and edge['role'] == 'mixed_typed_content_order':
            score['blockers'].append({'side': 'comparison', 'reason': 'document_order_endpoint_unresolved',
                                      'source': edge['sources'][0], 'layers': ['L']})
    for layer in ('L', 'B'):
        rows = [row for row in score['outcomes'] if row['layer'] == layer]
        complete = not any(layer in blocker.get('layers', ['L', 'B']) for blocker in score['blockers'])
        score['layers'][layer].update(numerator=sum(row['outcome'] == 'correct' for row in rows), denominator=len(rows),
            complete=complete, score=100 * sum(row['outcome'] == 'correct' for row in rows) / len(rows) if rows and complete else None)
    score['publishable'] = not score['blockers']
    score['score'] = sum(layer['score'] for layer in score['layers'].values()) / 3 if score['publishable'] and all(
        layer['score'] is not None for layer in score['layers'].values()) else None
    score['document_comparison'] = {'inputs': {'required': copy.deepcopy(requirements), 'actual': copy.deepcopy(evidence)},
        'decision': decision, 'base_score': base, 'source_form_units': copy.deepcopy(wanted),
        'semantic_limitations_retained': copy.deepcopy(requirements.get('blockers', [])),
        'contract': 'source_form_identity_or_typed_conflict_other_wording_unresolved'}
    return score


def validate_document_evidence(score):
    from .expected_report import validate_evidence

    proof = score['document_comparison']
    validate_evidence(proof['base_score'])
    replay = grade_document_content(proof['inputs']['required'], proof['inputs']['actual'])
    if replay != score:
        raise ValueError('document AST outcomes or evidence differ from complete replay')
    from .layer_aggregation import summarize_layers

    summarize_layers([score])
