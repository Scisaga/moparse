"""Document-content proofs alongside the existing interpreted B/L comparator.

The document view never claims that a lexical AST is a parsed business clause.
Exact source-form identity under the same document scope is a sufficient
preservation proof. Different wording requires the semantic comparator; an
unhandled paraphrase remains unresolved. No company or expected value selects
an execution branch, a candidate, or a tolerance.
"""

from __future__ import annotations

import copy

from .requirement_ast import build_document_ast, compare_document_ast, validate_content_ast


def _location(source):
    return tuple((key, tuple(source[key]) if isinstance(source.get(key), list) else source.get(key))
                 for key in ('path', 'lines', 'cell', 'block', 'native_path'))


def _same_record(left, right):
    return left.get('path') == right.get('path') and left.get('lines') == right.get('lines') and all(
        left.get(key) == right.get(key) for key in ('cell', 'native_path') if key in left or key in right)


def _grammar_limit(issue):
    reason = issue.get('reason', '')
    return reason.startswith(('cjk_narrative_', 'narrative_', 'quoted_nominal_', 'entity_assignment_',
                              'business_preamble_', 'business_clause_', 'prose_clause_')) or reason in {
        'source_obligation_pending', 'source_has_no_supported_semantic_disposition',
        'cjk_measurement_sequence_incomplete', 'proposition_syntax_unsupported',
        'cjk_circumstance_nominal_operation_unresolved'}


def _fallback_blocks(ast, issues):
    return [index for index, block in enumerate(ast['children'])
            if block['role'] in {'text', 'item', 'heading'}
            and any(_same_record(block['source'], issue.get('source', {})) and _grammar_limit(issue) for issue in issues)
            and not any(_same_record(block['source'], issue.get('source', {})) and not _grammar_limit(issue) for issue in issues)]


def attach_document_ast(graph, expected):
    units = []
    for target in expected['targets']:
        scopes = target.get('selected_heading_context')
        scope = [item['text'] for item in scopes] if scopes is not None else target.get('context', [])
        if target.get('cells'):
            for cell in target['cells']:
                units.append({'kind': 'table_cell', 'text': cell.get('text', ''), 'scope': scope,
                    'source': {**target['reference'], 'cell': cell.get('id', cell.get('native_path')),
                               'row': cell.get('row'), 'column': cell.get('col')},
                    'parents': target.get('parents', [])})
        else:
            units.append({'kind': target['kind'], 'text': target.get('raw_text', target['text']),
                          'source': target['reference'], 'scope': scope, 'parents': target.get('parents', [])})
    graph['comparison_contract'] = 'document_ast'
    graph['document_ast'] = build_document_ast(units)
    graph['source_form_units'] = _fallback_blocks(graph['document_ast'], graph['unresolved'])
    # Keep every semantic-analysis limitation. A preservation proof is not a
    # forged claim that the Chinese grammar reader understood those clauses.
    graph['content_comparison_ready'] = all(any(
        _same_record(graph['document_ast']['children'][index]['source'], issue.get('source', {}))
        for index in graph['source_form_units']) for issue in graph['unresolved'])


def validate_document_requirements(graph):
    from .requirement_graph import _semantic_literal

    selection = graph['source_obligation_inventory']['selection']
    expected = {'unresolved': graph['unresolved']}
    attach_document_ast(expected, selection)
    for key in ('document_ast', 'source_form_units', 'content_comparison_ready'):
        if graph.get(key) != expected[key]:
            raise ValueError('document AST differs from its complete authorized selection: ' + key)
    for block in graph['document_ast']['children']:
        validate_content_ast(block['content'], lambda source: _semantic_literal(graph['sources'], source))


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
    return build_document_ast(units)


def _without_grammar_analysis(graph, blocks):
    result = copy.deepcopy(graph)
    sources = [block['source'] for block in blocks]

    def covered(item):
        return any(_same_record(source, item.get('source', {})) for source in sources)

    removed_facts = {fact['id'] for fact in result['business'] if covered(fact)}
    result['business'] = [fact for fact in result['business'] if fact['id'] not in removed_facts]
    if 'requirement_ledger' in result:
        result['requirement_ledger'] = copy.deepcopy(result['business'])
    for name in ('logical_statements', 'semantic_operands', 'semantic_operand_relations', 'explicit_references',
                 'reference_roles', 'reference_dispositions', 'syntax'):
        result[name] = [item for item in result.get(name, []) if not covered(item)]
    result['relations'] = [edge for edge in result['relations'] if edge.get('fact_id') not in removed_facts
                           and not (covered(edge) and edge['type'] not in {
                               'prose_heading_membership', 'prose_reading_order', 'heading_membership',
                               'heading_order', 'list_membership'})]
    for name in ('blockers', 'pending_requirements'):
        result[name] = [issue for issue in result.get(name, []) if not (covered(issue) and _grammar_limit(issue))]
    result['candidate_issues'] = [issue for issue in result.get('candidate_issues', []) if not covered(issue)]
    # Runtime feature discovery still verifies every retained typed tree.
    # Features belonging solely to replaced partial trees are not requirements
    # of a source-form proof. No source or target is removed from that proof.
    from .requirement_ast import AST_FEATURE_COMPARATORS, _feature_present

    result['required_matcher_features'] = [feature for feature in result.get('required_matcher_features', [])
        if feature not in AST_FEATURE_COMPARATORS or _feature_present(feature, result.get('logical_statements', []))]
    result.pop('comparison_contract', None)
    return result


def grade_document_content(requirements, evidence):
    """Extend one grader with source-form proofs; keep T and typed B/L intact."""
    from .three_layer import _grade_layers

    wanted = requirements['source_form_units']
    expected_ast = requirements['document_ast']
    rebuilt = {'unresolved': requirements.get('blockers', [])}
    attach_document_ast(rebuilt, requirements['document_selection'])
    if expected_ast != rebuilt['document_ast'] or wanted != rebuilt['source_form_units']:
        raise ValueError('document requirements omit or rebind the authorized source selection')
    candidate_ast = _candidate_ast(evidence)
    if 'document_ast' in evidence and evidence['document_ast'] != candidate_ast:
        raise ValueError('candidate document AST differs from actual native syntax')
    for graph, ast in ((requirements, expected_ast), (evidence, candidate_ast)):
        for block in ast['children']:
            validate_content_ast(block['content'], lambda source, graph=graph: _resolve(graph, source))
    actual_fallback = _fallback_blocks(candidate_ast, evidence.get('blockers', []))
    wanted_ast = {'kind': 'document', 'children': [expected_ast['children'][index] for index in wanted]}
    decision = compare_document_ast(wanted_ast, candidate_ast,
        source_resolver=lambda side, source: _resolve(requirements if side == 'required' else evidence, source))
    base_required = _without_grammar_analysis(requirements, wanted_ast['children'])
    consumed = set(actual_fallback) | {i for row in decision['proof']['rows'] for i in row['actual_indices']}
    base_actual = _without_grammar_analysis(evidence, [candidate_ast['children'][i] for i in sorted(consumed)])
    base = _grade_layers(base_required, base_actual)
    score = copy.deepcopy(base)
    for index, row in enumerate(decision['proof']['rows']):
        status = row['decision']['status']
        scope_correct = row['actual_index'] is not None
        for layer, correct in (('B', status == 'equivalent'), ('L', scope_correct)):
            if layer == 'B' and row['required']['role'] == 'heading':
                continue  # Document labels own T/L; they assert no new fact.
            score['outcomes'].append({'id': f'{layer}:content:{index}', 'layer': layer,
                'role': 'source_form_assertion' if layer == 'B' else 'document_scope',
                'expected': row['required'], 'actual': row['actual'], 'outcome': 'correct' if correct else 'incorrect',
                'reason': row['decision']['rule_id'] if layer == 'B' else 'document_scope_and_role',
                **({'software_failure': True, 'semantic_comparison_status': 'unresolved'}
                   if layer == 'B' and status == 'unresolved' else {}),
                'document_ast_comparison': index})
        if status == 'unresolved':
            score['blockers'].append({'side': 'comparison', 'reason': row['decision']['rule_id'],
                                      'source': row['required']['source'], 'layers': ['B']})
    # Reading order is a relation independently of value/content correctness.
    for index, (first, second) in enumerate(zip(decision['proof']['rows'], decision['proof']['rows'][1:], strict=False)):
        correct = first['actual_index'] is not None and second['actual_index'] is not None and first['actual_index'] < second['actual_index']
        score['outcomes'].append({'id': f'L:content-order:{index}', 'layer': 'L',
            'role': 'reading_order',
            'expected': [first['required']['source'], second['required']['source']],
            'actual': [first['actual_index'], second['actual_index']],
            'outcome': 'correct' if correct else 'incorrect', 'reason': 'document_content_reading_order'})
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
