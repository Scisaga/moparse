"""Verify source-bound scalar claims against independently retained raw text.

This validates provenance, not the business answer. Facts and ledgers are not
source authorities; the original cell/fragment snapshots are the only input
used to check a claimed raw value and its numeric subrange.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

_LOCATION_KEYS = ("path", "cell", "native_path", "lines", "block", "block_lines", "row", "col")


def _location(source: dict[str, Any]) -> str:
    return json.dumps({key: source[key] for key in _LOCATION_KEYS if key in source},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bounds(source: dict[str, Any], offset: int, length: int) -> tuple[int, int] | None:
    span = source.get("cell_text_span", source.get("text_span"))
    if span is None:
        return offset, offset + length
    if (not isinstance(span, (list, tuple)) or len(span) != 2 or not all(type(value) is int for value in span)
            or not offset <= span[0] <= span[1] <= offset + length):
        return None
    return span[0], span[1]


def validate_scalar_sources(facts: Iterable[dict[str, Any]], projection: dict[str, Any], *,
                            canonicalize: Callable[[str], str], syntax=None, relations=None, blockers=()) -> None:
    """Reject forged scalar sources even when all derived copies agree.

    The contract applies only when a reader declares both ``raw_value`` and a
    precise ``value_source``. Logical predicates, non-scalars and undeclared
    provenance contracts retain their existing guards.
    """
    facts = list(facts)
    snapshots: dict[str, list[tuple[str, int]]] | None = None
    snapshot_records = []
    checked = set()
    for fact in facts:
        if not isinstance(fact.get("raw_value"), str) or not isinstance(fact.get("value_source"), dict):
            continue
        source, value_source = fact.get("source"), fact["value_source"]
        if (not isinstance(source, dict) or not source.get("path") or not value_source.get("path")
                or not isinstance(fact.get("value"), str)):
            raise ValueError("source-bound scalar lacks a valid original source")
        token = json.dumps([source, value_source, fact["raw_value"], fact["value"]], ensure_ascii=False, sort_keys=True)
        if token in checked:
            continue
        checked.add(token)
        if snapshots is None:
            snapshots = defaultdict(list)
            for item in [*projection.get("source_cells", []), *projection.get("source_fragments", [])]:
                original = item.get("source", {})
                if not original.get("path") or not isinstance(item.get("text"), str):
                    raise ValueError("source-bound scalar needs intact original text snapshots")
                original_span = original.get("cell_text_span", original.get("text_span"))
                offset = original_span[0] if original_span is not None else 0
                if type(offset) is not int:
                    raise ValueError("source-bound scalar has a malformed original source offset")
                snapshots[_location(original)].append((item["text"], offset))
                snapshot_records.append(item)
        if _location(source) != _location(value_source):
            raise ValueError("source-bound scalar value_source is outside its own actual field")
        if source.get('joined_fragments') or value_source.get('joined_fragments'):
            from .requirement_graph import _semantic_literal

            def original_literal(origin):
                for record in snapshot_records:
                    own = record['source']
                    if _location(own) != _location(origin):
                        continue
                    own_span = own.get('cell_text_span', own.get('text_span'))
                    if origin.get('cell_text_span', origin.get('text_span')) is None and own_span is not None:
                        continue
                    offset = own_span[0] if own_span is not None else 0
                    bounds = _bounds(origin, offset, len(record['text']))
                    if bounds:
                        return record['text'][bounds[0] - offset:bounds[1] - offset]
                return None

            raw = _semantic_literal([], source, resolver=original_literal)
            value = _semantic_literal([], value_source, resolver=original_literal)
            if raw != fact['raw_value'] or value is None or canonicalize(value) != canonicalize(fact['value']):
                raise ValueError('joined scalar differs from its independently retained original fragments')
            continue
        proven = False
        for text, offset in snapshots.get(_location(source), []):
            outer, inner = _bounds(source, offset, len(text)), _bounds(value_source, offset, len(text))
            if outer is None or inner is None or not outer[0] <= inner[0] <= inner[1] <= outer[1]:
                continue
            raw = text[outer[0] - offset:outer[1] - offset]
            value = text[inner[0] - offset:inner[1] - offset]
            if raw == fact["raw_value"] and canonicalize(value) == canonicalize(fact["value"]):
                proven = True
                break
        if not proven:
            raise ValueError("source-bound scalar differs from its original raw value or value subrange")
    # A correct year string from a neighboring record is still the wrong
    # comparison source. Closed-row YoY must refer to that row's own annual
    # fields; a separate declaration must actually label 本年/上年.
    for fact in facts:
        if (not re.fullmatch(r'(?:金[額额])?同比[變变][動动]|YoY(?:\s+change)?', fact.get('attribute', ''), re.I)
                or fact.get('compact_column') or fact.get('header_evidence')
                or _location(fact.get('attribute_source', {})) != _location(fact.get('source', {}))):
            continue
        for dimension, label in (('from_period', '上年'), ('to_period', '本年')):
            period = fact.get('qualifiers', {}).get(dimension)
            if period is None:
                continue
            origin = fact.get('qualifier_sources', {}).get(dimension, {})
            local = _location(origin) == _location(fact['source'])
            valid = False
            if local:
                for annual in facts:
                    if (annual.get('attribute') != fact.get('subject') or annual.get('record_id') != fact.get('record_id')
                            or _location(annual.get('source', {})) != _location(fact['source'])
                            or annual.get('qualifiers', {}).get('period') != period
                            or annual.get('qualifier_sources', {}).get('period') != origin):
                        continue
                    for text, offset in (snapshots or {}).get(_location(origin), []):
                        bounds = _bounds(origin, offset, len(text))
                        value = _bounds(annual.get('value_source', {}), offset, len(text))
                        if bounds and value and bounds[1] <= value[0] and text[bounds[0] - offset:bounds[1] - offset] == period:
                            valid = True
            else:
                for text, offset in (snapshots or {}).get(_location(origin), []):
                    bounds = _bounds(origin, offset, len(text))
                    if (bounds and text[bounds[0] - offset:bounds[1] - offset] == period
                            and re.search(r'(?:^|[;；。])\s*' + label + r'\s*[:：]\s*$', text[:bounds[0] - offset])):
                        valid = True
            if not valid:
                raise ValueError('source-bound series comparison period is outside its own row or explicit declaration')
    _validate_labelled_records(facts, projection, syntax=syntax, relations=relations, blockers=blockers)


def _validate_labelled_records(facts, projection, *, syntax, relations, blockers):
    """Require every scalar field actually present in a closed native record.

    Discovery reads this side's immutable text, never the other side's answers.
    Locators are source roles before any numeric value is checked. Independent
    semantic fixtures own the correctness of the financial column grammar.
    """
    from .field_sequence_requirements import read_labelled_record
    from .source_obligations import validate_relation_binding

    seen = set()
    for fragment in projection.get('source_fragments', []):
        decoded = read_labelled_record(fragment['text'], fragment['source'])
        if not decoded['matched'] or decoded['blockers']:
            continue
        own_syntax = [s for s in syntax or [] if s['text'] == fragment['text']
                      and _location(s['source']) == _location(fragment['source'])]
        groups = []
        if len(own_syntax) == 1:
            item = own_syntax[0]
            prior = (syntax or [])[:syntax.index(item)]
            for depth, parent in enumerate(item.get('parents', [])):
                declared = [p for p in item.get('parent_evidence', []) if p['text'] == parent]
                choices = [s for s in prior if s['text'] == parent and s.get('kind') == 'parent_label'
                           and s.get('parents', []) == item['parents'][:depth] and s.get('scope') == item.get('scope')]
                if declared:
                    choices = [s for s in choices if any(_location(s['source']) == _location(p['source']) for p in declared)]
                else:
                    choices = [s for s in choices if s.get('syntax_evidence', {}).get('list_span')
                               and s['syntax_evidence']['list_span'] == item.get('syntax_evidence', {}).get('list_span')
                               and s['syntax_evidence'].get('list_stream') == item.get('syntax_evidence', {}).get('list_stream')]
                ancestor = read_labelled_record(choices[-1]['text'], choices[-1]['source']) if choices else None
                if not ancestor or not ancestor['matched'] or ancestor['blockers']:
                    if any(b.get('reason', '').startswith('labelled_record_parent_')
                           and _location(b.get('source', {})) == _location(item['source']) for b in blockers):
                        continue  # The grammar gap already blocks publication.
                    raise ValueError('native labelled record has no source-proved parent context')
                groups.append({'role': 'row_group', **ancestor['record_label']})
        for field in decoded['facts']:
            key = json.dumps([field[k] for k in ('subject_source', 'attribute_source', 'value_source')], sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            own = [f for f in facts if all(f.get(k) == field[k] for k in ('subject_source', 'attribute_source', 'value_source'))]
            if len(own) != 1:
                raise ValueError('native labelled record lost or borrowed a scalar field role')
            fact = own[0]
            if any(fact.get(k) != field[k] for k in ('subject', 'attribute', 'value', 'raw_value', 'semantic_type')):
                raise ValueError('native labelled record payload differs from its own printed field')
            if field.get('semantic_type') in {'printed_position_list', 'printed_selection_state'}:
                facets = {k: v for k, v in fact.get('identity_facets', {}).items() if k != 'enumeration'}
                if 'enumeration' in fact.get('identity_facets', {}) and (not fact.get('enumeration_evidence') or relations is not None
                        and not any(e.get('type') == 'enumeration_membership' and e.get('fact_id') == fact['id'] for e in relations)):
                    raise ValueError('native selection field has an unproved collection owner')
                if (fact.get('value_logic') != field.get('value_logic')
                        or facets != field.get('identity_facets', {})
                        or fact.get('header_evidence') != field.get('header_evidence')):
                    raise ValueError('native position or selection field lost its own typed value or domain')
                def endpoint_owns(edge, fact=fact):
                    right = edge.get('right', {})
                    return (all(right.get(k) == fact[k] for k in ('subject', 'attribute', 'scope'))
                            and right.get('identity_facets', {}) == fact.get('identity_facets', {})
                            and ('qualifiers' not in right or right['qualifiers'] == fact.get('qualifiers', {})))
                if relations is not None and field.get('value_logic'):
                    members = [n for part in field['value_logic'].get('parts', []) if part.get('kind') == 'coordination'
                               for n in part['children']]
                    edges = [e for e in relations if e.get('type') == 'record_position_member' and e.get('fact_id') == fact['id']]
                    if len(edges) != len(members) or any(len([e for e in edges if
                            e.get('left') == {'position': member['head']} and e.get('source') == member['source']
                            and endpoint_owns(e)
                            and e.get('binding_evidence', {}).get('value_logic') == field['value_logic']]) != 1 for member in members):
                        raise ValueError('native position list lost or borrowed a member relation')
                if relations is not None:
                    labels = [e for e in relations if e.get('type') == 'record_label_scope' and e.get('fact_id') == fact['id']
                              and e.get('source') == field['subject_source'] and e.get('left') == {'record_subject': fact['subject']}
                              and endpoint_owns(e)
                              and e.get('binding_evidence', {}).get('headers') == field['header_evidence']]
                    if len(labels) != 1:
                        raise ValueError('native selection field lost its explicit person record scope')
            if syntax is not None and len(own_syntax) == 1:
                if ([r for r in fact.get('row_evidence', []) if r.get('role') == 'row_group'] != groups
                        or fact.get('identity_facets', {}).get('group', []) != [g['text'] for g in groups]):
                    raise ValueError('native labelled record borrows an adjacent parent identity or source')
            if relations is not None:
                edges = [e for e in relations if e.get('type') == 'field_binding' and e.get('fact_id') == fact['id']
                         and validate_relation_binding(None, fact, e)['equivalent']]
                if len(edges) != 1:
                    raise ValueError('native labelled record lacks its unique field binding')
