"""Complete bounded comparison owners from existing source-bound AST cuts.

Legacy language-analysis pending is retained, but is not a prerequisite to
compare a complete printed statement or an explicit scalar field. No reference
bytes or original requirement identities are changed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re


def extend_projection(raw_graph, projection):
    from .ast_alignment import identity_text
    from .document_ast_comparison import (
        _contains,
        _resolve,
        _same_record,
        document_order_requirements,
    )
    from .requirement_ast import read_content_ast

    result = copy.deepcopy(projection)
    result['requirement_ledger'] = copy.deepcopy(result['business'])
    coverage = result['comparison_coverage']
    blocked = [r for r in coverage['obligations'] if r['status'] == 'blocking']
    old_orders = copy.deepcopy(document_order_requirements(result))
    handlers, additions = [], []
    grouped = {}
    for row in blocked:
        key = json.dumps(row['source'], sort_keys=True, ensure_ascii=False)
        grouped.setdefault(key, []).append(row)
    for rows in sorted(grouped.values(), key=lambda rows: (str(rows[0]['source'].get('path')), rows[0]['source'].get('lines', []),
                                                         -sum((rows[0]['source'].get('text_span', [0, 0])[1], -rows[0]['source'].get('text_span', [0, 0])[0])))):
        source = rows[0]['source']
        literal = _resolve(result, source)
        if not literal:
            raise ValueError('legacy obligation has no independently retained literal source')
        containing = [(i, b) for i, b in enumerate(result['document_ast']['children'])
                      if b.get('content') and _contains(b['content']['source'], source)]
        if not containing:
            raise ValueError('legacy obligation has no complete source AST owner')
        block_index, block = min(containing, key=lambda pair: pair[1]['content']['source']['text_span'][1] - pair[1]['content']['source']['text_span'][0])
        covered = [f'L:content:{i}' for i, b in enumerate(result['source_form_requirements'])
                   if _contains(b['source'], source)]
        if covered:
            owners, handler = covered, 'existing_complete_content'
        else:
            # Equal/contained source obligations describe the same printed
            # assertion. They share one owner, rather than inventing votes.
            parent = next((entry for entry in additions if _contains(entry['source'], source)), None)
            if parent:
                owners, handler = parent['owners'], parent['handler']
            else:
                serial = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()[:16]
                scalar = re.fullmatch(r'([^\d\n:：]{2,80}?)\s*[:：]?\s*([+\-−]?\d+(?:,\d{3})*(?:\.\d+)?)(%|‰|亿元|萬元|万元|元)?[。.;；]?\s*', literal)
                prior = [f for f in result['business'] if f['id'] in coverage['retained_semantic_requirements']['B'] and _same_record(f['source'], source)]
                if scalar and prior:
                    attributes = {identity_text(f.get('attribute', '')) for f in prior}
                    if len(attributes) != 1:
                        scalar = None
                if scalar and prior:
                    label, value, unit = scalar[1].strip(), scalar[2], scalar[3]
                    offset = source.get('text_span', [0])[0]
                    val_source = {**source, 'text_span': [offset + scalar.start(2), offset + scalar.end(2)]}
                    label_source = {**source, 'text_span': [offset, offset + scalar.end(1)]}
                    fact_id, relation_id = 'B:continuous:' + serial, 'L:continuous:' + serial
                    fact = {'id': fact_id, 'role': 'metric', 'kind': 'fact',
                            'subject': next(iter(attributes)), 'attribute': label, 'value': value,
                            'qualifiers': {'unit': unit} if unit else {}, 'scope': block.get('scope', []),
                            'source': val_source, 'value_source': val_source, 'attribute_source': label_source,
                            'raw_value': value, 'rule_id': 'explicit_source_scalar_field',
                            'source_ast': source, 'original_obligation_ids': [r['obligation_id'] for r in rows]}
                    edge = {'id': relation_id, 'type': 'field_binding', 'left': {'subject': fact['subject'], 'attribute': label},
                            'right': {'subject': fact['subject'], 'attribute': label, 'scope': fact['scope'], 'qualifiers': fact['qualifiers']},
                            'source': val_source, 'fact_id': fact_id, 'rule_id': 'explicit_source_scalar_field_binding'}
                    result['business'].append(fact)
                    result['requirement_ledger'].append(copy.deepcopy(fact))
                    result['relations'].append(edge)
                    coverage['retained_semantic_requirements']['B'].append(fact_id)
                    coverage['retained_semantic_requirements']['L'].append(relation_id)
                    owners, handler = [fact_id, relation_id], 'explicit_source_scalar_field'
                else:
                    # This is source preservation, not a claim to parse every
                    # Chinese proposition. Its numeric/operator gate still runs.
                    node = {**copy.deepcopy(block), 'source': copy.deepcopy(source),
                            'content': read_content_ast(literal, source), 'block_index': block_index,
                            'requirement_id': 'content:continuous:' + serial,
                            'comparison_role': 'complete_source_content',
                            'original_obligation_ids': [r['obligation_id'] for r in rows]}
                    index = len(result['source_form_requirements'])
                    result['source_form_requirements'].append(node)
                    owners, handler = [f'L:content:{index}', f'B:content:{index}'], 'complete_source_content'
                additions.append({'source': source, 'owners': owners, 'handler': handler})
        handlers.extend({**copy.deepcopy(row), 'comparison_owners': owners, 'new_handler': handler} for row in rows)
    if additions:
        new_orders = document_order_requirements(result)
        old_pairs = {(e['left'], e['right']) for e in old_orders}
        extra = []
        for edge in new_orders:
            if (edge['left'], edge['right']) not in old_pairs:
                own = copy.deepcopy(edge)
                own['id'] = 'L:continuous-order:' + hashlib.sha256((edge['left'] + '|' + edge['right']).encode()).hexdigest()[:16]
                extra.append(own)
        result.update(continuous_original_document_orders=old_orders, continuous_extra_document_orders=extra)
    result['continuous_coverage'] = {
        'source_complete': coverage['source_complete'], 'structure_complete': coverage['structure_complete'],
        'legacy_responsibility_complete': coverage['responsibility_complete'],
        'bounded_responsibility_complete': len(handlers) == len(blocked),
        'legacy_obligations': handlers, 'added_owners': additions,
        'legacy_language_limitations_retained': copy.deepcopy(raw_graph.get('unresolved', [])),
        'semantic_equivalence_claim': 'bounded_content_and_explicit_fields_only',
    }
    if result['requirement_ledger'] != result['business']:
        raise ValueError('continuous projection lost original business owners')
    return result
