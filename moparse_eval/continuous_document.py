"""Continuous document/content judgments used by the shared grading entry.

This is the bounded content-preservation contract, not unrestricted paraphrase
equivalence. Original owners and their weights come from the requirement graph.
"""

from __future__ import annotations

import copy
import re

from .ast_alignment import METHOD, RULES, _join, align_nodes, identity_text, protected


def _title_fragments(text):
    parts = [part.strip() for part in text.splitlines() if part.strip()]
    # A complete CJK title between Latin branding runs remains its own printed
    # language fragment. Never accept an arbitrary substring or a shortened
    # company name from a longer CJK name.
    bilingual = re.fullmatch(r'[A-Za-z][A-Za-z\d\s.,&()\-]*\s*([\u3400-\u9fff（）()·\s]+)\s*[A-Za-z][A-Za-z\d\s.,&()\-]*', text)
    if bilingual:
        parts.append(bilingual[1].strip())
    return parts


def _page_slots(text):
    """Own printed syntax only; return literal page/title cuts, no answers."""
    starts = list(re.finditer(r'(?<!\S)(\d{1,4})(?=\s|[、])\s*', text))
    if not starts or text[:starts[0].start()].strip():
        return []
    slots = []
    for i, match in enumerate(starts):
        stop = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        title = text[match.end():stop].strip()
        if not 2 <= len(title) <= 100 or re.match(r'(?:年|月|日|元|万元|萬元|亿元|億元|%|years?\b|months?\b|days?\b|employees?\b|people\b)', title, re.I) or re.search(r'[;；。]', title):
            return []
        begin = match.end()
        while begin < stop and text[begin].isspace():
            begin += 1
        end = stop
        while end > begin and text[end - 1].isspace():
            end -= 1
        slots.append({'page': match[1], 'title': title, 'page_span': [match.start(1), match.end(1)],
                      'title_span': [begin, end]})
    return slots


def _source_order_ast(ast):
    """Place cells at their own physical table; preserve explicit boundaries."""
    from .native_grid_fields import table_source_owns

    result = copy.deepcopy(ast)
    blocks = [b for b in result['children'] if b['role'] != 'table_cell']
    cells = [b for b in result['children'] if b['role'] == 'table_cell']
    placements, unknown = {}, []
    for cell in cells:
        source = cell['source']
        owners = []
        for i, block in enumerate(blocks):
            if block['role'] != 'table':
                continue
            table = block['source']
            if table_source_owns(table, source):
                owners.append(i)
        if len(owners) == 1:
            placements.setdefault(owners[0], []).append(cell)
        else:
            cell['source_order_known'] = False
            unknown.append(cell)
    children = []
    for i, block in enumerate(blocks):
        children.append(block)
        if i in placements:
            children.extend(placements[i])
            children.append({'role': 'table_end', 'source': copy.deepcopy(block['source']), 'content': None,
                             'control': 'table_region_boundary_without_text'})
    for cell in unknown:
        children.extend([{'role': 'unplaced_cell_boundary', 'source': cell['source'], 'content': None}, cell])
    result.update(children=children, unplaced_cell_sources=[c['source'] for c in unknown],
                  order_projection='own_table_source_positions_and_original_cell_order')
    return result


def _nodes(graph, ast, *, clauses=False):
    from .document_ast_comparison import _resolve
    from .prose_requirements import _sentence_spans

    nodes = []
    # Retain the document's own initial title fragments, including plain-text
    # brand/title lines. Metadata may precede them; prose or a table ends this
    # bounded title zone. This supplies context, never a missing answer.
    preamble = []
    for block in ast['children']:
        if not block.get('content'):
            break
        own_text = _resolve(graph, block['content']['source']) or ''
        if block['role'] != 'heading' and (len(own_text) > 120 or re.search(r'[。！？;；]|[a-z]{2,}\.\s*$', own_text)):
            break
        if block['role'] == 'heading' or not re.search(r'[:：]', own_text):
            preamble.extend(_title_fragments(own_text))
    heading_run, previous_heading, heading_history = [], False, []
    unknown_headings = {e.get('source', {}).get('block') for e in graph.get('native_context', {}).get('heading_events', [])
                        if e.get('hierarchy_known') is False}
    history_unknown, table_contexts = False, {}
    for index, block in enumerate(ast["children"]):
        content = block.get("content")
        if content is None:
            context = {'local_heading_run': list(heading_run), 'heading_history': list(heading_history),
                       'heading_hierarchy_unknown': history_unknown, 'document_preamble': preamble}
            if block['role'] == 'table':
                labels = []
                for prior in reversed(ast['children'][max(0, index - RULES['maximum_group']):index]):
                    if not prior.get('content'):
                        break
                    label = _resolve(graph, prior['content']['source']) or ''
                    if len(label) > 120 or re.search(r'[。！？;；]|[a-z]{2,}\.\s*$', label):
                        break
                    labels.insert(0, label)
                context['local_table_labels'] = labels
                from .quantity import normalize_unit

                for label in reversed(labels):
                    bare = re.sub(r'^[（(]?\s*(?:金额单位|金額單位|单位|單位)\s*[:：为為]?\s*|[）)]$', '', label).strip()
                    reference_intro = re.fullmatch(r'(?:详见下表|詳見下表|见下表|見下表|如下(?:表)?|如下所示|see\s+(?:the\s+)?table\s+below)[：:\s]*', bare, re.I)
                    if not bare or bare.isdigit() or normalize_unit(bare)['matched'] or reference_intro:
                        continue
                    path = list(block.get('scope', []))
                    context['matching_scope'] = path if path[-1:] == [label] else [*path, label]
                    break
                table_contexts[block['source'].get('block', block['source'].get('path'))] = context
            nodes.append({"id": str(index), "text": "", "source": block["source"],
                          "role": block["role"], "barrier": True, "ast_index": index, **context})
            continue
        source = content["source"]
        text = _resolve(graph, source)
        if text is None:
            raise ValueError("document node cannot resolve its own source: " + repr(source))
        if block['role'] == 'heading':
            heading_run = [*heading_run, text] if previous_heading else [text]
            heading_history.append(text)
            history_unknown = history_unknown or block['source'].get('block') in unknown_headings
            previous_heading = True
        else:
            previous_heading = False
        cuts = _sentence_spans(text) if clauses else [(0, len(text))]
        if clauses:
            cuts = [(a + match.start(), a + match.end()) for a, b in cuts
                    for match in re.finditer(r"[^;；]+[;；]?", text[a:b]) if match[0].strip()]
        for a, b in cuts:
            context = {'local_heading_run': list(heading_run), 'heading_history': list(heading_history),
                       'heading_hierarchy_unknown': history_unknown, 'document_preamble': preamble}
            if block['role'] == 'table_cell':
                context = table_contexts.get(source.get('block', source.get('path')), context)
            nodes.append({"id": block.get("requirement_id", str(index)) + f":{a}:{b}",
                          "text": text[a:b], "source": copy.deepcopy(source),
                          "raw_span": [a, b], "role": block["role"],
                          "scope": block.get("scope", []), "parents": block.get("parents", []),
                          'source_order_known': block.get('source_order_known', True),
                          **context,
                          "ast_index": index})
    return nodes


def _literal_audit(graph):
    """Audit literal cell coverage separately from business-role readiness."""
    from .literal_readback import _parts
    from .three_layer import canonical

    cells = {c['source'].get('cell'): c for c in graph.get('text_projection', {}).get('source_cells', [])}
    covered = {key: [] for key in cells}
    def retain(source, text):
        key = source.get('cell')
        if key not in cells:
            return
        raw = cells[key]['text']
        bounds = source.get('cell_text_span', source.get('text_span'))
        if bounds is None:
            if canonical(raw) == canonical(text):
                bounds = [0, len(raw)]
            else:
                start = raw.find(text)
                bounds = [start, start + len(text)] if start >= 0 else [0, 0]
        covered[key].append([max(0, bounds[0]), min(len(raw), bounds[1])])
    for atom in graph['text']:
        for source, text in _parts(atom):
            retain(source, text)
    for control in graph.get('text_projection', {}).get('controls', []):
        retain(control.get('source', {}), control.get('text', ''))
    unread = []
    for key, cell in cells.items():
        cursor = 0
        for a, b in sorted(covered[key]) + [[len(cell['text']), len(cell['text'])]]:
            if cursor < a and canonical(cell['text'][cursor:a]):
                unread.append({'text': cell['text'][cursor:a], 'source': {**cell['source'], 'text_span': [cursor, a], 'cell_text_span': [cursor, a]},
                               'role': 'literal', 'syntax_kind': 'table_cell', 'id': 'native-literal:' + str(len(unread))})
            cursor = max(cursor, b)
    return {'legacy_projection_complete': graph.get('text_projection', {}).get('complete'),
            'source_cells': len(cells), 'faithful_literal_additions': unread,
            'business_role_limits_waive_no_literal': True}


def _text_nodes(graph, *, candidate=False, audit=None):
    from .document_ast_comparison import _resolve
    from .literal_readback import _parts
    from .three_layer import canonical

    def source_key(source):
        return (source.get('path'), tuple(source.get('lines', [])), source.get('cell'), source.get('native_path'))

    field_sources = {}
    for fact in graph.get('business', []):
        value_source = fact.get('value_source', fact.get('source', {}))
        field_sources.setdefault(source_key(value_source), []).append((value_source, '|'.join(_field_axes(fact))))
    result = []
    repeated_slots = sum(len(_page_slots(unit.get('text', ''))) for unit in graph.get('syntax', [])) >= 2
    for atom in graph["text"]:
        source = atom["source"]
        label = source.get("attribute_source") or source.get("subject_source")
        identity = _resolve(graph, label) if label else None
        if atom.get('role') == 'value' or source.get('cell') and atom.get('role') != 'label':
            bounds = source.get('cell_text_span', source.get('text_span'))
            axes = set()
            for field_source, own_axes in field_sources.get(source_key(source), []):
                cut = field_source.get('cell_text_span', field_source.get('text_span'))
                if cut is None or bounds is not None and max(cut[0], bounds[0]) < min(cut[1], bounds[1]):
                    axes.add(own_axes)
            if len(axes) == 1:
                identity = next(iter(axes))
        if atom.get('role') == 'page_reference' and result and result[-1].get('role') == 'toc_title':
            identity = result[-1]['text']
        if candidate:
            for part_source, text in _parts(atom):
                slots = _page_slots(text) if repeated_slots else []
                if slots:
                    for slot in slots:
                        for key, role in (('page', 'page_reference'), ('title', 'toc_title')):
                            result.append({**copy.deepcopy(atom), 'text': slot[key],
                                           'source': copy.deepcopy(part_source),
                                           'own_raw_span': slot[key + '_span'],
                                           'role': role, 'scope': [],
                                           'identity': canonical(slot['title']) if key == 'page' else None,
                                           'projection': 'own_repeated_page_title_slots'})
                else:
                    result.append({**copy.deepcopy(atom), 'text': text, 'source': copy.deepcopy(part_source),
                                   'role': atom.get('role', 'text'),
                                   'identity': canonical(identity) if identity else None})
            continue
        result.append({**copy.deepcopy(atom), "role": atom.get("role", "text"),
                       "identity": canonical(identity) if identity else None})
    if candidate:
        result.extend(copy.deepcopy((audit or _literal_audit(graph))['faithful_literal_additions']))
    return result


def _path(required, actual):

    # A prefix wrapper does not change the nearest business parent. Additional
    # descendants do change it. No Expected labels are inserted into actual.
    wanted = [identity_text(v) for v in required]
    found = [identity_text(v) for v in actual]
    return not wanted or len(found) >= len(wanted) and found[-len(wanted):] == wanted


def _components(required, actual, present=True):
    restrictions = _restrictive_context(required, actual)
    parts = [{"relation": "document_membership", "credit": int(present and restrictions['correct']),
              "restrictive_context": restrictions}]
    for key, name in (("scope", "heading_ownership"), ("parents", "list_parent_chain")):
        if required.get(key):
            parts.append({"relation": name, "expected": required[key],
                          "actual": actual.get(key, []),
                          "credit": int(present and (_scope_matches(required[key], actual) if key == 'scope'
                                                     else _path(required[key], actual.get(key, []))))})
    return parts


def _restrictive_context(required, actual):
    """An extra conditional heading is never an empty display wrapper.

    This finite printed-cue check does not infer arbitrary prose semantics.
    The complete restrictive label must be supported by the required owner's
    own content or context; a matching conditional keyword alone is insufficient.
    """
    cue = re.compile(r'\b(?:if|unless|except|only|not|no|must|shall|may|before|after|subject\s+to|provided\s+that|conditional\s+on)\b'
                     r'|若|如果|假如|除非|不得|不能|不予|不获|不獲|不超过|不超過|必须|必須|仅在|僅在|仅限|僅限|只限|条件下|條件下|为前提|為前提', re.I)
    required_text = identity_text(' '.join(str(v) for v in [required.get('text', ''),
                                   required.get('subject', ''), required.get('attribute', ''),
                                   *required.get('scope', []), *required.get('parents', [])]))
    context = dict.fromkeys([*actual.get('scope', []), *actual.get('parents', []),
                             *actual.get('local_heading_run', []), *actual.get('local_table_labels', [])])
    extra = [label for label in context if cue.search(label) and identity_text(label) not in required_text]
    return {'correct': not extra, 'unsupported_restrictive_labels': extra,
            'rule': 'printed_restrictive_context_must_be_supported_by_same_required_owner'}


def _scope_matches(required, actual):
    scope = actual.get('matching_scope', actual.get('scope', []))
    if _path(required, scope):
        return True
    if 'matching_scope' not in actual and any(_path(required, [*scope, label]) for label in actual.get('local_table_labels', [])):
        return True
    target = identity_text(''.join(required))
    def joined_path(parts):
        return any(identity_text(''.join(parts[i:])) == target for i in range(len(parts)))
    if joined_path(scope):
        return True
    preamble = actual.get('document_preamble', [])
    # Initial title fragments may express a combined document owner. Retain
    # every explicit active parent: a competing chapter cannot be skipped.
    if scope and any(joined_path(preamble[a:b] + scope)
                     for a in range(len(preamble)) for b in range(a + 1, min(a + RULES['maximum_group'], len(preamble)) + 1)):
        return True
    run = actual.get('local_heading_run', [])
    if not scope and actual.get('heading_hierarchy_unknown'):
        # Some faithful readers declare headings but no depth at all. Their
        # complete contiguous title run is usable context; bilingual branding
        # contributes its complete independently printed language fragment.
        own_run = []
        for text in run:
            parts = _title_fragments(text)
            own_run.append(parts[-1] if len(parts) > len(text.splitlines()) else text)
        if joined_path(own_run):
            return True
    if not required or not run or scope and identity_text(scope[-1]) not in [identity_text(t) for t in run]:
        return False
    # Consecutive heading fragments can express one title. The nearest title
    # owns the following body in the serialized AST. A different explicit
    # parent is never erased by this local rule; higher ancestry still needs
    # its own native path.
    same_owner = any(identity_text(''.join(run[i:])) == identity_text(required[-1]) for i in range(len(run)))
    if same_owner and (len(required) == 1 or _path(required[:-1], scope[:-1])):
        return True
    if actual.get('heading_hierarchy_unknown'):
        history = actual.get('heading_history', [])
        candidates = [identity_text(''.join(history[i:])) for i in range(len(history))]
        # Only a contiguous suffix can support the same ordered context. A
        # competing named heading cannot be skipped. Explicit native paths
        # must agree with that same suffix before an unknown-depth fallback.
        if target in candidates and (not scope or identity_text(''.join(scope)) in candidates):
            return True
        # Known outer context plus a contiguous unknown-depth heading run can
        # express the full path. No explicitly conflicting parent is removed.
        for split in range(1, len(required)):
            outer = required[:split]
            if _path(outer, scope[:-1]) and identity_text(''.join(required[split:])) in candidates:
                return identity_text(scope[-1]) == identity_text(required[-1])
    return False


def _outcome(identifier, layer, role, expected, actual, components, **extra):
    weight = sum(part.get("weight", 1) for part in components)
    credit = sum(part["credit"] * part.get("weight", 1) for part in components) / weight if weight else 0
    return {"id": identifier, "layer": layer, "role": role, "expected": expected,
            "actual": actual, "credit": credit, "weight": 1,
            "outcome": "correct" if credit == 1 else "incorrect" if credit == 0 else "partial",
            "components": components, **extra}


def _actual_node(alignment, row):
    pieces = row["actual_pieces"]
    if not pieces:
        return {"text": "", "source": {}, "scope": [], "parents": []}
    first = alignment["actual_nodes"][pieces[0]["index"]]
    text = _join([{'text': p['text']} for p in pieces])[0]
    return {**first, "text": text, "pieces": pieces}


def content_credit(required, actual):
    """Length-weighted printed clauses, each protected against business errors."""
    from .three_layer import _edit, canonical

    wanted, found = canonical(required), canonical(actual)
    edits = _edit(wanted, found)
    expected_tokens, actual_tokens = protected(wanted), protected(found)
    gate = expected_tokens == actual_tokens
    equivalence = None
    if not gate:
        from .requirement_ast import compare_content_ast, read_content_ast

        # Reuse the existing finite exact-number/unit/operator contract. This
        # does not assert arbitrary paraphrase equivalence.
        equivalence = compare_content_ast(read_content_ast(wanted, {'path': '<required-content>'}),
                                          read_content_ast(found, {'path': '<actual-content>'}))
        gate = equivalence['status'] == 'equivalent'
    fraction = max(0, 1 - sum(edits.values()) / len(wanted)) if wanted else float(not found)
    return {"credit": (1 if equivalence and equivalence['status'] == 'equivalent' else fraction) if gate else 0, "content_retention": fraction,
            "protected_values_correct": gate, "expected_tokens": expected_tokens,
            "actual_tokens": actual_tokens, "edits": edits, "token_equivalence": equivalence,
            "semantic_claim": "bounded_content_preservation_only"}


def _source_form(required, candidate_nodes, scalar_owners=()):
    """Score all source-form owners without dropping unparsed prose."""
    ast = {"children": required["source_form_requirements"] + required["source_form_order_anchors"]}
    nodes = _nodes(required, ast, clauses=True)
    aligned = align_nodes(nodes, candidate_nodes)
    rows, owners, positions = [], {}, {}
    count = len(required["source_form_requirements"])
    for index, block in enumerate(ast["children"]):
        own = [(n, r) for n, r in zip(nodes, aligned["rows"], strict=True) if n["ast_index"] == index]
        components, relation_parts, actual = [], [], []
        for node, match in own:
            item = _actual_node(aligned, match)
            detail = content_credit(node["text"], item["text"])
            detail['restrictive_context'] = _restrictive_context(node, item)
            detail['scope_correct'] = (detail['restrictive_context']['correct']
                                       and _scope_matches(node.get('scope', []), item)
                                       and _path(node.get('parents', []), item.get('parents', [])))
            if not detail['scope_correct']:
                detail['credit'] = 0
            from .three_layer import canonical

            components.append({"weight": len(canonical(node["text"])), "expected": node,
                               "actual": item, **detail})
            relation_parts.extend(_components(node, item, match["status"] == "matched"))
            actual.extend(match["actual_pieces"])
        key = block.get("requirement_id")
        positions[key] = [(p["index"], p["span"][0], p["span"][1]) for p in actual]
        if index >= count:
            continue
        unresolved = any(match["status"] == "ambiguous" for _, match in own)
        relation_row = _outcome(f"L:content:{index}", "L", "document_scope", block, actual,
                     relation_parts or [{"credit": 0}], reason="explicit_document_relationship_components")
        if unresolved:
            relation_row.update(outcome="unresolved", credit=None, reason="score_changing_identity_tie")
        rows.append(relation_row)
        if block["role"] != "heading" and f'B:content:{index}' not in scalar_owners:
            b = _outcome(f"B:content:{index}", "B", "source_form_assertion", block, actual,
                         components or [{"credit": 0}], reason="protected_clause_content_retention")
            if unresolved:
                b.update(outcome="unresolved", credit=None, reason="score_changing_identity_tie")
            rows.append(b)
        owners[f"content:{index}"] = {"block": block, "actual": actual}
    return rows, aligned, positions


def _field_axes(fact):
    from .quantity import normalize_unit

    values = [fact.get('subject', ''), fact.get('attribute', '')]
    values.extend(fact.get('qualifiers', {}).get(k, '') for k in ('period', 'year', 'entity'))
    qualifiers = fact.get('qualifiers', {})
    currency = normalize_unit(qualifiers.get('unit'), qualifiers.get('currency')).get('currency')
    if currency:
        values.append('currency:' + currency)
    if fact.get('role') == 'identity' and fact.get('subject') == fact.get('value'):
        values[0] = ''  # The value being graded cannot locate its own entity field.
    return sorted({identity_text(part) for v in values if v for part in (
        str(v).split(' / ') if fact.get('role') == 'metric' else [str(v)])})


def _typed_nodes(facts):
    result = []
    for fact in facts:
        scope = list(fact.get("scope", []))
        scope.extend(fact.get('parent_path', fact.get('identity_facets', {}).get('toc_parent', [])))
        axes = '|'.join(_field_axes(fact))
        result.append({"id": fact["id"], "text": axes or fact['role'], 'identity': axes,
                      "source": fact["source"], "role": fact["role"], "scope": scope,
                      'matching_scope': fact.get('matching_scope', scope),
                      "payload": fact})
    return result


def _navigation(graph):
    """Faithfully expose a repeated title/page syntax, using candidate only.

    This is a printed slot schema, not an inferred document/topic ontology. A
    solitary number beside arbitrary prose cannot establish this schema.
    """
    from .three_layer import canonical

    known = [copy.deepcopy(f) for f in graph["business"] if f.get("semantic_type") == "toc_page"]
    candidates = []
    for unit in graph.get("syntax", []):
        text = unit.get('text', '')
        for slot in _page_slots(text):
            page, title = slot['page'], canonical(slot['title'])
            candidates.append({"id": "navigation-slot:" + str(len(candidates)), "subject": title,
                               "attribute": "Page", "value": page, "role": "metric",
                               "semantic_type": "toc_page", "scope": [], "qualifiers": {},
                               "source": unit["source"], "parent_path": unit.get("parents", []),
                               "slot_basis": "repeated_own_title_page_syntax"})
    # Require a repeated schema in the object's own content. Existing explicit
    # entries retain their own parent evidence and take precedence by source.
    if len(candidates) >= 2:
        known_sources = {str(f["source"].get("block", f["source"].get("path"))) for f in known}
        known.extend(f for f in candidates if str(f["source"].get("block", f["source"].get("path"))) not in known_sources)
    return known


def _native_fields(evidence):
    """A stronger own-source row/column view replaces its weaker cell view."""
    from .native_grid_fields import syntax_grid_fields

    fields = syntax_grid_fields(evidence)
    replaced = {f['source']['cell'] for f in fields if f.get('native_semantic_view')}
    retained = [f for f in evidence['business']
                if (f.get('value_source', {}).get('cell') or f.get('source', {}).get('cell')) not in replaced]
    return [*retained, *fields]


def _scalar_content_views(requirements):
    """Reuse one fully source-bound scalar inside its original content vote.

    No unsupported surrounding prose is discarded: only a complete explicit
    key/value statement whose entire key and numeric payload are accounted for
    can use this view. Original requirement IDs and weights stay unchanged.
    """
    from .document_ast_comparison import _contains, _resolve
    from .quantity import exact_number, normalize_unit
    from .three_layer import canonical

    result = {}
    retained = requirements['comparison_coverage']['retained_semantic_requirements']['B']
    for i, block in enumerate(requirements['source_form_requirements']):
        if block['role'] == 'heading':
            continue
        source = block.get('content', {}).get('source', block['source'])
        text = _resolve(requirements, source) or ''
        statement = re.fullmatch(r'\s*([^:：;；。\n]+)[:：]\s*([+\-−]?\d[\d,]*(?:\.\d+)?)([^\d;；\n]*?)\s*[。.]?\s*', text)
        if not statement:
            continue
        suffix = statement[3].rstrip('。.').strip()
        if suffix and not normalize_unit(suffix)['matched']:
            continue
        label = statement[1].strip()
        unit = re.fullmatch(r'(.*?)\s*[(（]([^()（）]+)[)）]', label)
        if unit and normalize_unit(unit[2])['matched']:
            label = unit[1].strip()
        facts = [f for f in requirements['business'] if _contains(source, f.get('value_source', f['source']))]
        if len(facts) != 1 or facts[0]['id'] in retained:
            continue
        fact = facts[0]
        if fact['role'] != 'metric' or exact_number(fact['value']) is None or identity_text(label) != identity_text(fact['attribute']):
            continue
        if canonical(statement[2]) != canonical(fact['value']):
            continue
        key = f'B:content:{i}'
        result[key] = {**copy.deepcopy(fact), 'id': key, 'source_form_owner': copy.deepcopy(block),
                       'original_scalar_view_id': fact['id'], 'rule_id': 'complete_source_bound_scalar_content_view'}
    return result


def _typed(requirements, evidence, candidate_nodes, scalar_owners=None):
    from .business_correspondence import _qualifier_check, _value_check
    from .equivalence import decide_equivalence
    from .three_layer import canonical

    retained = requirements["comparison_coverage"]["retained_semantic_requirements"]
    required_views = {f.get('native_semantic_view', {}).get('id', f['id']) if f.get('native_semantic_view') else f['id']: f
                      for f in _native_fields(requirements)}
    wanted = [{**copy.deepcopy(required_views.get(f['id'], f)), 'id': f['id']}
              for f in requirements['business'] if f['id'] in retained['B']]
    wanted.extend(copy.deepcopy(list((scalar_owners or {}).values())))
    from .native_grid_fields import email_token, identifier_label

    actual = copy.deepcopy([f for f in _native_fields(evidence) if f.get("semantic_type") != "toc_page"] + _navigation(evidence))
    from .document_ast_comparison import _contains

    def owns(node, source):
        origin = node['source']
        if source.get('cell'):
            return origin.get('cell') == source['cell']
        if source.get('block'):
            return origin.get('block') == source['block']
        return _contains(origin, source)

    for fact in actual:
        source = fact.get('value_source', fact['source'])
        own = next((n for n in candidate_nodes if owns(n, source)), None)
        if own:
            for key in ('local_heading_run', 'heading_history', 'heading_hierarchy_unknown', 'document_preamble', 'local_table_labels'):
                fact[key] = own.get(key, False if key == 'heading_hierarchy_unknown' else [])
            if own.get('matching_scope') is not None:
                fact['matching_scope'] = own['matching_scope']
    aligned = align_nodes(_typed_nodes(wanted), _typed_nodes(actual), maximum=1)
    rows, matches = [], {}
    for fact, match in zip(wanted, aligned["rows"], strict=True):
        own = actual[match["actual_pieces"][0]["index"]] if match["actual_pieces"] else None
        if own:
            value = _value_check(fact, own, canonical)
            label = str(fact.get('attribute', ''))
            required_email, actual_email = email_token(canonical(fact['value'])), email_token(canonical(own['value']))
            if required_email is not None and actual_email is not None:
                literal = {'equivalent': required_email == actual_email,
                           'rule_id': 'printed_email_token_sentence_delimiter_only',
                           'required_token': required_email, 'actual_token': actual_email}
                value = {'correct': literal['equivalent'], 'equivalence': literal,
                         'role_basis': 'printed_email_identifier'}
            elif re.search(r'代码|代碼|编号|編號|版本|\b(?:code|identifier|version)\b', label, re.I) or re.fullmatch(r'date|year|日期|年份|年度', label, re.I) or identifier_label(label):
                literal = decide_equivalence(fact.get('raw_value', fact['value']), own.get('raw_value', own['value']), 'literal', context={'canonicalize': canonical})
                value = {'correct': literal['equivalent'], 'equivalence': literal,
                         'role_basis': 'printed_identifier_or_calendar_field'}
            parts = [{"relation": "value", "expected": fact["value"], "actual": own["value"],
                      "credit": int(value["correct"]), "equivalence": value}]
            identity = _field_axes(fact) == _field_axes(own)
            context = _scope_matches(fact.get('scope', []), own)
            restrictions = _restrictive_context(fact, own)
            context = context and restrictions['correct']
            context = context and _path(fact.get('identity_facets', {}).get('toc_parent', []),
                                       own.get('parent_path', own.get('identity_facets', {}).get('toc_parent', [])))
            qualifiers = []
            for key, val in fact.get("qualifiers", {}).items():
                decision = decide_equivalence(val, own.get("qualifiers", {}).get(key), key, context={"canonicalize": canonical})
                if key in {'period', 'year', 'entity'} and identity_text(str(val)) in _field_axes(own):
                    decision = {'equivalent': True, 'rule_id': 'same_source_bound_field_axis',
                                'proof': {'required_axis': val, 'candidate_axes': _field_axes(own)}}
                if key == 'unit':
                    decision = _qualifier_check(fact, own, key, canonical)['equivalence']
                qualifiers.append({"key": key, "expected": val, "actual": own.get("qualifiers", {}).get(key),
                                   "credit": int(decision["equivalent"]), "equivalence": decision})
            correct = value["correct"] and identity and context and all(q["credit"] for q in qualifiers)
            parts[0].update(credit=int(correct), identity_correct=identity,
                            scope_correct=context, qualifiers=qualifiers,
                            restrictive_context=restrictions)
        else:
            parts = [{"relation": "value", "credit": 0, "reason": "no_corresponding_field"}]
        row = _outcome(fact["id"], "B", fact["role"], fact, own, parts,
                       reason="value_independent_field_correspondence_and_exact_payload")
        if match["status"] == "ambiguous":
            row.update(outcome="unresolved", credit=None, reason="score_changing_identity_tie")
        rows.append(row)
        matches[fact["id"]] = {"required": fact, "actual": own, "match": match}
    return rows, aligned, matches


def _reserve_typed_sources(nodes, matches):
    """One B occurrence cannot also earn a separate source-form vote."""
    from .literal_readback import _identity

    reserved = {}
    for info in matches.values():
        actual = info['actual']
        if not actual:
            continue
        for key in ('source', 'attribute_source', 'subject_source'):
            source = actual.get(key, {})
            bounds = source.get('text_span')
            if bounds is None and source.get('cell'):
                bounds = [0, len(str(actual.get('value', '')))]
            if bounds:
                reserved.setdefault(_identity(source), []).append(bounds)
    result = []
    for node in nodes:
        origin = node['source'].get('text_span', [0])[0] + node.get('raw_span', [0])[0]
        stop = origin + len(node['text'])
        cuts = [(max(origin, a), min(stop, b)) for a, b in reserved.get(_identity(node['source']), [])
                if max(origin, a) < min(stop, b)]
        if not cuts:
            result.append(node)
            continue
        boundaries = sorted({origin, stop, *(p for pair in cuts for p in pair)})
        for a, b in zip(boundaries, boundaries[1:], strict=False):
            result.append({**node, 'text': node['text'][a - origin:b - origin],
                           'raw_span': [a - node['source'].get('text_span', [0])[0], b - node['source'].get('text_span', [0])[0]],
                           'barrier': any(x <= a < b <= y for x, y in cuts),
                           'capacity_basis': 'typed_B_original_source_reservation'})
    return result


def _layout_ties(facts, alignment):
    """Keep value ambiguity while proving independent relation invariants.

    The witness uses source order only. A whole connected set must admit a
    distinct occurrence for each owner before any tied relation is certified.
    """
    used = {p['index'] for f in facts.values() if f['match']['status'] != 'ambiguous'
            for p in f['match']['actual_pieces']}
    choices = {key: sorted({i for a, b in f['match']['alternatives'] for i in range(a, b)} - used)
               for key, f in facts.items() if f['match']['status'] == 'ambiguous'}
    remaining, result = set(choices), {}
    while remaining:
        component, slots = {next(k for k in choices if k in remaining)}, set()
        while True:
            expanded = slots | {i for key in component for i in choices[key]}
            owners = component | {key for key in remaining if set(choices[key]) & expanded}
            if expanded == slots and owners == component:
                break
            slots, component = expanded, owners
        assigned = {}
        def visit(key, seen, assigned=assigned):
            for slot in choices[key]:
                if slot in seen:
                    continue
                seen.add(slot)
                if slot not in assigned or visit(assigned[slot], seen):
                    assigned[slot] = key
                    return True
            return False
        complete = all(visit(key, set()) for key in choices if key in component)
        witness = {key: slot for slot, key in assigned.items()}
        for key in component:
            result[key] = {'capacity_proven': complete, 'witness': witness.get(key),
                           'candidates': [alignment['actual_nodes'][i]['payload'] for i in choices[key]]}
        remaining -= component
    return result


def grade_continuous_document(requirements, evidence):
    from .document_ast_comparison import (
        _candidate_ast,
        document_order_requirements,
        navigation_order_requirements,
    )
    from .native_evaluation import requirement_inventory
    from .relation_correspondence import grade_relations
    from .three_layer import canonical

    if requirements["sample_id"] != evidence["sample_id"]:
        raise ValueError("Expected and candidate selection identities differ")
    if requirements.get("requirement_ledger") != requirements["business"]:
        raise ValueError("requirement ledger was changed before comparison")
    ast = _source_order_ast(_candidate_ast(evidence))
    if not ast["reading_complete"]:
        raise ValueError("candidate_reader_failure_or_incomplete_scope")
    candidate_nodes = _nodes(evidence, ast, clauses=True)
    scalar_owners = _scalar_content_views(requirements)
    typed_rows, typed_alignment, facts = _typed(requirements, evidence, candidate_nodes, scalar_owners)
    layout_ties = _layout_ties(facts, typed_alignment)
    source_rows, source_alignment, positions = _source_form(requirements, _reserve_typed_sources(candidate_nodes, facts), scalar_owners)
    for row in source_rows:
        key = row['id'].replace('L:content:', 'B:content:')
        if row['layer'] == 'L' and key in scalar_owners:
            info = facts[key]
            actual = info['actual']
            components = _components(info['required'], actual or {}, actual is not None)
            components.append({'relation': 'row_column_period_axes', 'credit': int(actual is not None and _field_axes(info['required']) == _field_axes(actual))})
            replacement = _outcome(row['id'], 'L', 'document_scope', row['expected'], actual, components,
                                   reason='complete_source_bound_scalar_relationship')
            if info['match']['status'] == 'ambiguous':
                replacement.update(credit=None, outcome='unresolved', reason='field_correspondence_identity_tie')
            row.clear()
            row.update(replacement)
    rows = []
    own_projection = {**evidence, 'business': _native_fields(evidence)}
    literal_audit = _literal_audit(own_projection)
    t_alignment = align_nodes(_text_nodes(requirements), _text_nodes(own_projection, candidate=True, audit=literal_audit), preserve_identity_ambiguity=False)
    extras = sum(item["I"] for item in t_alignment["insertions"])
    for index, (node, match) in enumerate(zip(requirements["text"], t_alignment["rows"], strict=True)):
        edits = copy.deepcopy(match["edits"])
        if index == 0:
            edits["I"] += extras
        size = len(canonical(node["text"]))
        row = {"id": node["id"], "layer": "T", "role": node.get("role", "text"),
               "expected": node, "actual": match["actual_pieces"], "edits": edits,
               "credit": max(0, 1 - sum(edits.values()) / size) if size else 0,
               "outcome": "correct" if not sum(edits.values()) else "incorrect",
               "reason": "canonical_edit_operations", "correspondence": match,
               "diagnostic_absence_claim": False}
        if match["status"] == "ambiguous":
            # T text can be determined even if two identical, differently bound
            # occurrences would change L/B. It uses the deterministic text edit
            # path; identity ambiguity is still retained separately below.
            row.update(outcome="unresolved", credit=None)
        rows.append(row)
    rows.extend(source_rows)
    rows.extend(typed_rows)
    retained = requirements["comparison_coverage"]["retained_semantic_requirements"]["L"]
    edges = [e for e in requirements["relations"] if e["id"] in retained]
    _, existing = grade_relations(edges, evidence["relations"], canonicalize=canonical)
    existing = {r["id"]: r for r in existing}
    navigation = [row for row in facts.values() if row["required"].get("semantic_type") == "toc_page"]
    for edge in edges:
        kind = edge["type"]
        found, components = None, None
        if kind == "field_binding":
            info = facts.get(edge.get("fact_id"))
            found = info["actual"] if info else None
            components = _components(info["required"] if info else {}, found or {}, found is not None)
            axes = _field_axes(info['required']) if info else []
            actual_axes = _field_axes(found) if found else []
            components.append({'relation': 'row_column_period_axes', 'expected': axes,
                               'actual': actual_axes, 'credit': int(found is not None and axes == actual_axes)})
            tie = layout_ties.get(edge.get('fact_id'))
            if tie and tie['capacity_proven']:
                alternatives = []
                for alternative in tie['candidates']:
                    parts = _components(info['required'], alternative)
                    parts.append({'relation': 'row_column_period_axes', 'expected': axes,
                                  'actual': _field_axes(alternative), 'credit': int(axes == _field_axes(alternative))})
                    alternatives.append(parts)
                if alternatives and len({tuple(p['credit'] for p in parts) for parts in alternatives}) == 1:
                    components = alternatives[0]
                    found = {'alternatives': tie['candidates'], 'capacity_proven': True,
                             'source_order_witness': tie['witness'], 'all_relation_components_invariant': True}
        elif kind in {"toc_entry_page", "toc_parent"}:
            title = edge.get("left", {}).get("title") if kind == "toc_entry_page" else edge.get("right", {}).get("title")
            info = next((row for row in navigation if row["required"]["subject"] == title), None)
            found = info["actual"] if info else None
            components = [{"relation": kind, "credit": int(found is not None)}]
            if kind == "toc_parent" and found:
                parent = edge.get("left", {})
                wanted_path = parent.get("parent_path", []) + [parent.get("title", "")]
                found_path = found.get("parent_path", found.get("identity_facets", {}).get("toc_parent", []))
                components[0].update(credit=int(_path(wanted_path, found_path)), expected=wanted_path, actual=found_path)
        if components is None:
            old = existing[edge["id"]]
            found = old.get("actual")
            components = [{"relation": kind, "credit": int(old["outcome"] == "correct"),
                           "prior_comparator_trace": old}]
        row = _outcome(edge["id"], "L", kind, edge, found, components,
                       reason="independent_explicit_relationship")
        if kind == 'field_binding' and info and info['match']['status'] == 'ambiguous' and not (found or {}).get('all_relation_components_invariant'):
            row.update(credit=None, outcome='unresolved', reason='field_correspondence_identity_tie')
        rows.append(row)
    for edge in document_order_requirements(requirements):
        first, second = positions.get(edge["left"], []), positions.get(edge["right"], [])
        correct = bool(first and second) and max(first) <= min(second)
        row = _outcome(edge["id"], "L", "reading_order", edge, [first, second],
                             [{"relation": "relative_serialized_order", "credit": int(correct)}],
                             reason="candidate_original_positions")
        if any(source_alignment['actual_nodes'][p[0]].get('source_order_known') is False for p in first + second):
            row.update(credit=None, outcome='unresolved', reason='native_table_flow_unresolved')
        rows.append(row)
    for edge in navigation_order_requirements(requirements):
        endpoints = []
        for endpoint in (edge["left"], edge["right"]):
            info = next((r for r in navigation if r["required"]["subject"] == endpoint["title"]
                         and r["required"].get("identity_facets", {}).get("toc_parent", []) == endpoint["parent_path"]), None)
            endpoints.append(info["match"]["actual_pieces"][0]["index"] if info and info["match"]["actual_pieces"] else None)
        correct = all(v is not None for v in endpoints) and endpoints[0] < endpoints[1]
        rows.append(_outcome(edge["id"], "L", "navigation_order", edge, endpoints,
                             [{"relation": "navigation_sequence", "credit": int(correct)}],
                             reason="candidate_original_navigation_positions"))
    inventory = requirement_inventory(requirements)
    layers = {}
    blockers = []
    for layer in ("T", "L", "B"):
        own = [row for row in rows if row["layer"] == layer]
        if set(r["id"] for r in own) != set(inventory["requirement_ids"][layer]) or len(own) != len(inventory["requirement_ids"][layer]):
            raise ValueError("continuous comparison changed original requirement owners")
        unknown = [r["id"] for r in own if r["credit"] is None]
        denominator = inventory["denominators"][layer]
        edits = {k: sum(r["edits"][k] for r in own) for k in ("S", "D", "I")} if layer == "T" else {}
        numerator = denominator - sum(edits.values()) if layer == "T" else sum(r["credit"] or 0 for r in own)
        layers[layer] = {"denominator": denominator, "numerator": numerator if not unknown else None,
                         "score": 100 * max(0, numerator) / denominator if denominator and not unknown else None,
                         "complete": not unknown, "unresolved_requirement_ids": unknown,
                         "compared_requirements": len(own) - len(unknown), "edits": edits}
        if unknown:
            reasons = sorted({r['reason'] for r in own if r['credit'] is None})
            blockers.append({"side": "comparison", "reason": reasons[0] if len(reasons) == 1 else 'multiple_comparison_limits',
                             "reasons": reasons, "layers": [layer], "requirements": unknown})
    values = [v["score"] for v in layers.values()]
    return {"sample_id": requirements["sample_id"], "pipeline": evidence.get("pipeline"),
            "scoring_method": METHOD, "scoring_rules": copy.deepcopy(RULES),
            "layers": layers, "score": sum(values) / 3 if all(v is not None for v in values) else None,
            "comparison_complete": not blockers, "publishable": False,
            "research_only": True, "full_lite_score": False, "publication_authorized": False,
            "blockers": blockers, "outcomes": rows,
            "document_comparison": {"contract": METHOD, "expected_ast": requirements["document_ast"],
                                    "candidate_ast": ast, "alignment": source_alignment,
                                    "typed_alignment": typed_alignment},
            "text_comparison": t_alignment, "unconsumed_candidate_insertions": t_alignment["insertions"],
            "candidate_literal_projection_audit": literal_audit,
            "candidate_issues": copy.deepcopy(evidence.get("candidate_issues", [])),
            "reference_interpretation_issues": copy.deepcopy(requirements.get("candidate_issues", []))}
