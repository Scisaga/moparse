"""Source-aware recursive comparison of bounded semantic requirement trees.

This module does not parse answers or read files. A caller supplies interpreted
trees and, optionally, an independent source resolver. Provenance is checked on
each side rather than compared between different documents. Every semantic key
is retained, including attachment, scope, direction and operator placement.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .equivalence import decide_equivalence
from .measurement_evidence import read_measurement_literal
from .metrics import normalize_text
from .scope_correspondence import verify_scope

_SCHEMAS = {
    # Source-form content has a narrower contract than an interpreted clause:
    # identity of every ordered leaf proves preservation without inventing an
    # actor, predicate or attachment. It does not prove arbitrary paraphrases.
    "content_sequence": {"children"},
    "content_token": {"role", "text"},
    "proposition": {"subject", "attribute", "object"},
    "coordination": {"operator", "children", "mode"},
    "modality": {"operator", "polarity", "child"},
    "negation": {"child"},
    "conditions": {"bindings", "child"},
    "condition": {"operator", "operand", "child"},
    "exception": {"operator", "operand", "child"},
    "relative": {"antecedent", "restriction", "child"},
    "restrictive_relative": {"antecedent", "restriction", "child"},
    "reporting": {"speaker", "attribute", "polarity", "tense", "child"},
    "temporal_scope": {"qualifiers", "child"},
    "active_aspect": {"aspect", "tense", "child"},
    "fronted_context": {"preposition", "operator", "role", "context", "child"},
    "purpose_scope": {"operator", "control", "child", "operand"},
    "controlled_infinitive_scope": {"operator", "control", "child", "operand"},
    "discourse_scope": {"operator", "role", "marker", "child"},
    "logical_group": {"tree"},
    "noun_phrase": {"head", "determiner", "quantifier", "modifiers", "prepositional_complements", "coordination"},
    "nominal_modifier": {"text", "role"},
    "nominal_compound": {"modifier", "head", "relation"},
    "prepositional_complement": {"preposition", "semantic_role", "attachment", "complement"},
    "quantity_comparison": {"operator", "value"},
    "quantity_assertion": {"subject", "predicate", "assertion_mode", "right_role", "value", "unit"},
    "quantity": {"value", "unit"},
    "relation": {"type", "left", "right", "direction"},
    # Attachment descriptors are semantic nodes inside a source-bound PP.
    "nominal": {"head"},
    "predicate": {"head"},
    "subject_control": {"controller"},
    "object_control": {"controller"},
    "document_composition": {"subject", "attribute", "object", "page_reference", "document_identity"},
    "cjk_measurement_sequence": {"clauses", "period"},
    "year_on_year_change": {"subject", "basis", "direction", "baseline_period", "value", "unit"},
    "circumstance_scope": {"operator", "direction", "degree", "simultaneous", "operand", "child"},
    "cjk_nominal": {"head", "parts"},
    "cjk_dependency": {"role", "marker", "child"},
}
_UNSOURCED_DESCRIPTORS = {"nominal", "predicate", "subject_control", "object_control"}
_PROVENANCE = {"id", "rule_id", "record_id", "source", "source_id", "sources", "span", "text_span", "cell_text_span", "joined_span",
               "status", "complete", "unresolved", "pending", "record_evidence", "field_label_evidence", "subject_binding_evidence"}
_PERIOD_KEYS = {"period", "from_period", "to_period", "comparison_period", "period_basis", "currency"}
_UNRESOLVED = {"unknown", "pending", "partial", "unsupported", "unresolved", "scope_unknown", "attachment_unknown"}
_MISSING = object()
_OPERATORS = {
    "coordination": {"and", "or", "but"},
    "modality": {"ability", "may", "must", "shall", "should", "can", "could", "will", "would"},
    "quantity_comparison": {"eq", "ge", "le", "gt", "lt"},
    "condition": {"if", "unless", "only_if", "except_if", "except_when"},
    "exception": {"unless", "except_if", "except_when"},
    "purpose_scope": {"purpose"},
    "controlled_infinitive_scope": {"complement"},
    "discourse_scope": {"for_example", "for_instance", "however", "moreover", "in_addition", "in_particular", "enumeration"},
    "circumstance_scope": {"means", "background", "cause", "purpose", "condition"},
}


def _canonical(value):
    return normalize_text(value, collapse_whitespace=True) if isinstance(value, str) else value


_CONTENT_OPERATORS = ('不得', '不能', '沒有', '没有', '不超過', '不超过', '至少', '最少', '以上', '以下',
                      '過半數', '过半数', '主要', '僅', '仅', '全部', '所有', '均', '必須', '必须', '應當', '应当')
_CONTENT_UNITS = ('人民幣', '人民币', '億元', '亿元', '百萬元', '百万元', '萬元', '万元', '小時', '小时',
                  '季度', '年度', '年', '月', '日', '天', '名', '位', '人', '次', '元', '%')
_CONTENT_NUMBER = re.compile(r'\d+(?:,\d{3})*(?:\.\d+)?')
_CONTENT_TOKEN = re.compile('|'.join(map(re.escape, sorted(
    {*_CONTENT_OPERATORS, *_CONTENT_UNITS}, key=lambda value: (-len(value), value))))
    + r'|\d+(?:,\d{3})*(?:\.\d+)?|[A-Za-z]+|[^\s]')


def _content_role(text, original='', start=0, end=0):
    numeric_unit = text in _CONTENT_UNITS and (bool(re.compile(r'\d\s*$').search(original, 0, start))
        or text in {'人民幣', '人民币'} and bool(re.compile(r'\s*\d').match(original, end)))
    return ('number' if _CONTENT_NUMBER.fullmatch(text) else 'operator' if text in _CONTENT_OPERATORS
            else 'unit' if numeric_unit else 'literal')


def read_content_ast(text, source):
    """Expose an ordered, lossless content AST; infer no Chinese sentence roles.

    Spaces between tokens are presentation; word boundaries, punctuation,
    numbers, printed operators and units remain individual source-bound leaves.
    The contract is preservation, not a claim to understand an unseen grammar.
    """
    offset = source.get('text_span', [0])[0]
    origin = {**copy.deepcopy(source), 'text_span': [offset, offset + len(text)]}
    return {'kind': 'content_sequence', 'source': origin, 'children': [
        {'kind': 'content_token', 'role': _content_role(match[0], text, match.start(), match.end()), 'text': match[0],
         'source': {**copy.deepcopy(source), 'text_span': [offset + match.start(), offset + match.end()]}}
        for match in _CONTENT_TOKEN.finditer(text)]}


def validate_content_ast(node, resolve):
    """Independently check leaf coverage, order, roles and original source cuts."""
    if node.get('kind') == 'content_join':
        if len(node.get('children', [])) < 2 or any(child.get('kind') != 'content_sequence' for child in node['children']):
            raise ValueError('content join needs complete original adjacent fragments')
        for child in node['children']:
            validate_content_ast(child, resolve)
        return
    source = node.get('source', {})
    literal = resolve(source)
    bounds = source.get('text_span')
    if (literal == '' and source.get('cell') and isinstance(bounds, (list, tuple)) and len(bounds) == 2
            and bounds[0] == bounds[1] and node.get('kind') == 'content_sequence' and node.get('children') == []):
        return  # An actual empty cell is retained, never converted into zero.
    if (node.get('kind') != 'content_sequence' or not isinstance(literal, str) or not literal.strip()
            or not isinstance(bounds, (list, tuple)) or len(bounds) != 2 or bounds[1] - bounds[0] != len(literal)):
        raise ValueError('content AST lacks its complete original source')
    cursor = bounds[0]
    for child in node.get('children', []):
        origin = child.get('source', {})
        cut = origin.get('text_span')
        if (child.get('kind') != 'content_token' or not isinstance(cut, (list, tuple)) or len(cut) != 2
                or not cursor <= cut[0] < cut[1] <= bounds[1]
                or any(origin.get(key) != source.get(key) for key in ('path', 'lines', 'cell', 'block', 'native_path'))
                or literal[cursor - bounds[0]:cut[0] - bounds[0]].strip()
                or literal[cut[0] - bounds[0]:cut[1] - bounds[0]] != child.get('text')
                or child.get('role') != _content_role(child.get('text', ''), literal,
                    cut[0] - bounds[0], cut[1] - bounds[0])):
            raise ValueError('content AST leaf was omitted, reordered, forged or borrowed')
        cursor = cut[1]
    if literal[cursor - bounds[0]:].strip() or not node.get('children'):
        raise ValueError('content AST silently omits source content')
    # Prevent merging two words/leaves into a new opaque leaf while retaining
    # the complete literal. This checks lexical representation, not semantics.
    if [child['text'] for child in node['children']] != [m[0] for m in _CONTENT_TOKEN.finditer(literal)]:
        raise ValueError('content AST changed its lexical boundaries')


def compare_content_ast(required, actual, context=None):
    """Prove literal preservation, or a local, explicit typed-value conflict.

    An arbitrary wording change remains unresolved; it is never advertised as
    an incorrect business statement merely because its characters differ.
    """
    context = context or {}
    resolver = context.get('source_resolver')
    if resolver:
        for side, tree in (('required', required), ('actual', actual)):
            try:
                validate_content_ast(tree, lambda source, side=side: resolver(side, source))
            except (ValueError, KeyError, TypeError) as error:
                return _result('unresolved', '$', reason='content_ast_source_inconsistent', proof={'side': side, 'error': str(error)})
    left, right = _content_leaves(required), _content_leaves(actual)
    left_shape = [(n.get('role'), n.get('text') if n.get('role') == 'literal' else None) for n in left]
    right_shape = [(n.get('role'), n.get('text') if n.get('role') == 'literal' else None) for n in right]
    identical = [(n.get('role'), n.get('text')) for n in left] == [(n.get('role'), n.get('text')) for n in right]
    if identical:
        return _result('equivalent', '$', reason='complete_source_form_identity', proof={'ordered_leaves': len(left), 'semantic_inference': False})
    if left_shape == right_shape:
        differences = [{'index': index, 'role': a['role'], 'required': a['text'], 'actual': b['text']}
                       for index, (a, b) in enumerate(zip(left, right, strict=True)) if a['text'] != b['text']]
        for difference in differences:
            difference['decision'] = _content_token_equivalence(difference)
        if all(item['decision']['equivalent'] for item in differences):
            return _result('equivalent', '$', reason='source_form_declared_token_equivalence', proof={'differences': differences})
        # A scale change can compensate a number change. This branch has no
        # owning quantity AST, so delegate rather than inventing a binding.
        changed = {item['role'] for item in differences if not item['decision']['equivalent']}
        if {'number', 'unit'} <= changed or any(item['decision']['status'] == 'unresolved' for item in differences):
            return _result('unresolved', '$', reason='source_form_typed_equivalence_unresolved', proof={'differences': differences})
        return _result('conflict', '$', reason='source_form_typed_value_conflict', proof={'differences': differences})
    return _result('unresolved', '$', reason='wording_change_requires_semantic_comparison',
                   proof={'semantic_inference': False})


def _content_token_equivalence(item):
    from .equivalence import decide_equivalence

    left, right, role = item['required'], item['actual'], item['role']
    if role == 'number':
        return decide_equivalence(left, right, 'number')
    if role == 'unit':
        if left in {'人民幣', '人民币'} or right in {'人民幣', '人民币'}:
            return decide_equivalence(left, right, 'currency')
        durations = {'小時': 'hour', '小时': 'hour', '年度': 'year', '年': 'year',
                     '日': 'day', '天': 'day', '月': 'month', '季度': 'quarter'}
        if left in durations and right in durations:
            return decide_equivalence(durations[left], durations[right], 'duration_unit')
        decision = decide_equivalence(left, right, 'unit')
        proof = decision['proof']
        if (decision['equivalent'] and proof.get('required_unit', {}).get('scale')
                != proof.get('actual_unit', {}).get('scale')):
            decision.update(equivalent=False, status='unresolved', rule_id='quantity_scale_needs_owning_quantity_ast')
        return decision
    operators = {'沒有': '没有', '不超過': '不超过', '過半數': '过半数', '僅': '仅',
                 '必須': '必须', '應當': '应当', '至少': 'lower_inclusive', '最少': 'lower_inclusive',
                 '以上': 'lower_inclusive', '以下': 'upper_inclusive'}
    return decide_equivalence(operators.get(left, left), operators.get(right, right), 'printed_operator')


def _content_leaves(node):
    return [leaf for child in node['children'] for leaf in _content_leaves(child)] if node.get('kind') == 'content_join' else node.get('children', [])


def build_document_ast(units):
    """Keep producer document structure and content; never access expected."""
    blocks = []
    for unit in units:
        text, source = unit.get('text'), unit.get('source', unit.get('reference'))
        if not isinstance(text, str) or not isinstance(source, dict) or not text.strip() and unit.get('kind') != 'table_cell':
            continue
        scope = copy.deepcopy(unit.get('scope', unit.get('context', [])))
        if unit.get('kind') == 'heading' and scope[-1:] == [text]:
            scope = scope[:-1]
        blocks.append({'kind': 'document_block', 'role': unit.get('kind', 'text'),
                       'scope': scope,
                       'parents': copy.deepcopy(unit.get('parents', [])),
                       'source': copy.deepcopy(source), 'content': read_content_ast(text, source)})
    return {'kind': 'document', 'children': blocks}


def compare_document_ast(required, actual, *, source_resolver=None):
    """Align source-form blocks by scope and answer-independent lexical shape.

    Every retrieval hit, conflict and capacity decision is retained. Numeric
    values, units and printed operators cannot choose a candidate. Ambiguous
    repeated shapes remain unresolved, including a unique correct-valued hit.
    """
    from rapidfuzz.distance import Levenshtein

    def shape(block):
        return ''.join(n['text'] if n['role'] == 'literal' else '<' + n['role'] + '>'
                       for n in _content_leaves(block['content']))

    def role(block):
        return 'body' if block['role'] in {'text', 'item'} else block['role']

    windows = []
    for start, own in enumerate(actual['children']):
        windows.append(([start], own, shape(own)))
        if role(own) != 'body':
            continue
        for end in range(start + 2, min(start + 8, len(actual['children'])) + 1):
            parts = actual['children'][start:end]
            if any(role(part) != 'body' or part['scope'] != own['scope'] or part['parents'] != own['parents'] for part in parts):
                break
            joined = {**own, 'content': {'kind': 'content_join', 'children': [part['content'] for part in parts]}}
            windows.append((list(range(start, end)), joined, shape(joined)))
    available = set(range(len(actual['children'])))
    rows = []
    for index, block in enumerate(required['children']):
        hits, trace = [], []
        wanted = shape(block)
        for candidate_indices, own, own_shape in windows:
            candidate_index = candidate_indices[0]
            similarity = Levenshtein.normalized_similarity(wanted, own_shape)
            conflicts = []
            if block['scope'] != own['scope'] or block['parents'] != own['parents']:
                conflicts.append('document_scope')
            if role(block) != role(own):
                conflicts.append('document_role')
            hit = similarity >= .65
            capacity = all(i in available for i in candidate_indices)
            accepted = hit and not conflicts and capacity
            trace.append({'candidate_index': candidate_index, 'candidate_indices': candidate_indices,
                          'lexical_shape_hit': hit, 'similarity': similarity,
                          'conflicts': conflicts, 'capacity_available': capacity,
                          'accepted_for_comparison': accepted, 'value_used': False})
            if accepted:
                hits.append((candidate_indices, own))
        exact_shape = [hit for hit in hits if shape(hit[1]) == wanted]
        # Lexical context may refine a fuzzy hit. Values never break a tie.
        hits = exact_shape or hits
        selected = hits[0] if len(hits) == 1 else None
        chosen = selected[0][0] if selected is not None else None
        if chosen is None:
            decision = _result('unresolved' if hits else 'missing', '$',
                               reason='document_block_identity_ambiguous' if hits else 'document_block_missing_or_scope_conflict')
        else:
            available.difference_update(selected[0])
            decision = compare_content_ast(block['content'], selected[1]['content'],
                                           {'source_resolver': source_resolver} if source_resolver else {})
        rows.append({'required_index': index, 'actual_index': chosen, 'decision': decision,
                     'actual_indices': selected[0] if selected is not None else [],
                     'required': copy.deepcopy(block),
                     'actual': copy.deepcopy(selected[1]) if selected is not None else None,
                     'retrieval': {'candidates': trace, 'value_used': False}})
    return _combine([row['decision'] for row in rows], '$', rows=rows,
                    capacity_one=True, unadjudicated_extra_indices=sorted(available))


def _result(status, path, *, reason=None, proof=None, conflicts=()):
    return {"status": status, "equivalent": status == "equivalent", "conflict": status == "conflict",
            "missing": status == "missing", "unresolved": status == "unresolved", "path": path,
            "rule_id": reason or "recursive_requirement_ast", "proof": proof or {}, "conflicts": list(conflicts)}


def _combine(children, path, **proof):
    status = next((status for status in ("conflict", "missing", "unresolved")
                   if any(child["status"] == status for child in children)), "equivalent")
    return _result(status, path, proof={**proof, "children": children},
                   conflicts=[{"path": child["path"], "status": child["status"], "rule_id": child["rule_id"]}
                              for child in children if not child["equivalent"]])


def _provenance_key(key):
    return key in _PROVENANCE or key.endswith(("_span", "_spans", "_source", "_sources"))


def _semantic_keys(node):
    keys = {key for key in node if not _provenance_key(key)}
    if node.get('kind') == 'cjk_dependency' and node.get('role') in {
            'arithmetic_base', 'arithmetic_group', 'dividend', 'divisor', 'subtrahend', 'addend'}:
        keys.discard('marker')  # The typed role owns the audited arithmetic operation.
    # Surface forms are checked against their own sources. A normalized
    # predicate and decomposed nominal, when present, carry comparison meaning.
    if "attribute" in node:
        keys.discard("predicate")
        keys.discard("operator_text")
    if node.get("kind") == "noun_phrase" and "head" in node:
        keys.discard("text")
    return keys


def _nominal_role_closed(node, role):
    """Verify a decomposed role covers its entire retained surface literal.

    This independent constituent audit does not parse the literal again. It
    binds every interpreted constituent to the original role's exact slice,
    preventing a shorter or forged phrase from replacing an unhandled suffix.
    """
    from .nominal_syntax import validate_nominal_sources

    phrase, origin, raw = node.get(role + "_phrase"), node.get(role + "_source"), node.get(role)
    if (not isinstance(phrase, dict) or phrase.get("kind") not in {"noun_phrase", "cjk_nominal"}
            or not isinstance(origin, dict) or phrase.get("source") != origin or not isinstance(raw, str)):
        return False
    span = origin.get("text_span")
    if not (isinstance(span, (list, tuple)) and len(span) == 2 and span[1] - span[0] == len(raw)):
        return False

    def literal(source, _label):
        if (not isinstance(source, dict) or any(source.get(key) != origin.get(key)
                for key in ("path", "lines", "cell", "block", "native_path"))):
            return None
        cut = source.get("text_span")
        if not (isinstance(cut, (list, tuple)) and len(cut) == 2 and span[0] <= cut[0] <= cut[1] <= span[1]):
            return None
        return raw[cut[0] - span[0]:cut[1] - span[0]]

    try:
        if phrase['kind'] == 'cjk_nominal':
            from .cjk_circumstances import validate_cjk_nominal

            validate_cjk_nominal(phrase, literal)
        else:
            validate_nominal_sources({"logic": [phrase]}, {}, literal)
    except (ValueError, KeyError, TypeError, IndexError):
        return False
    return True


def _source_checks(node, side, path, context):
    if node.get("kind") in _UNSOURCED_DESCRIPTORS:
        return []
    source = node.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("path"), str) or not source["path"]:
        return [_result("unresolved", path, reason="ast_node_source_missing", proof={"side": side})]
    span = source.get("text_span")
    if not (isinstance(span, (list, tuple)) and len(span) == 2
            and all(type(value) is int for value in span) and 0 <= span[0] < span[1]):
        return [_result("unresolved", path, reason="ast_node_source_span_invalid", proof={"side": side, "source": copy.deepcopy(source)})]
    resolver = context.get("source_resolver")
    if resolver is None:
        return []
    literal = resolver(side, copy.deepcopy(source))
    if not isinstance(literal, str) or not literal:
        return [_result("unresolved", path, reason="ast_node_source_unavailable", proof={"side": side, "source": copy.deepcopy(source)})]
    if node.get('kind') == 'content_token':
        if literal != node.get('text'):
            return [_result('unresolved', path, reason='content_token_not_bound_to_source')]
        return []
    if node.get('kind') == 'content_sequence':
        try:
            validate_content_ast(node, lambda source: resolver(side, source))
        except ValueError as error:
            return [_result('unresolved', path, reason='content_ast_source_inconsistent', proof={'error': str(error)})]
        return []
    if node.get("kind") == "cjk_measurement_sequence" or node.get("sequence_source"):
        from .cjk_measurement_requirements import read_cjk_measurements

        sequence_source = node.get("sequence_source", source)
        whole = resolver(side, copy.deepcopy(sequence_source))
        readback = read_cjk_measurements(whole, sequence_source) if isinstance(whole, str) else None
        expected = None
        if readback is not None and readback["complete"]:
            tree = readback["logic"][0]
            expected = tree if node.get("kind") == "cjk_measurement_sequence" else next(
                (clause for clause in tree["clauses"] if clause["source"] == source), None)
        if expected is None or node != expected:
            return [_result("unresolved", path, reason="measurement_sequence_not_bound_to_complete_source",
                            proof={"side": side, "source": copy.deepcopy(source), "sequence_source": copy.deepcopy(sequence_source)})]
        return []
    checks = []

    def local_origin(origin, *, empty=False):
        own_span = origin.get("text_span") if isinstance(origin, dict) else None
        return (isinstance(origin, dict) and origin.get("path") == source.get("path")
                and all(origin.get(part) == source.get(part) for part in ("block", "cell", "native_path") if part in source or part in origin)
                and (not source.get("lines") or origin.get("lines") == source["lines"])
                and isinstance(own_span, (list, tuple)) and len(own_span) == 2
                and span[0] <= own_span[0] <= own_span[1] <= span[1]
                and (own_span[0] < own_span[1] or empty))

    for key in ("subject", "predicate", "object", "head", "preposition", "speaker", "antecedent", "context"):
        origin = node.get(key + "_source")
        if key not in node or not isinstance(node[key], str) or not isinstance(origin, dict):
            continue
        original = resolver(side, copy.deepcopy(origin))
        empty_object = key == "object" and node[key] == "" and node.get("object_phrase") is None
        empty_group_head = (key == "head" and node[key] == "" and (
            node.get('kind') == 'cjk_nominal' and bool(node.get('parts')) or node.get("kind") == "noun_phrase"
            and isinstance(node.get("coordination"), dict) and len(node["coordination"].get("children", [])) >= 2))
        local = local_origin(origin, empty=empty_object or empty_group_head)
        control = node.get('subject_binding_evidence', {})
        if key == 'subject' and control.get('kind') == 'enumeration_subject':
            member, intro = control.get('member_source', {}), control.get('introduction_source', {})
            a, b = member.get('text_span', [None, None])
            local = (origin == control.get('controller_source') and control.get('controller') == node[key]
                     and source.get('path') == member.get('path') == intro.get('path') == origin.get('path')
                     and source.get('lines') == member.get('lines')
                     and len(intro.get('lines', [])) == 2 and intro['lines'][1] < member['lines'][0]
                     and a is not None and a <= span[0] <= span[1] <= b)
        if original != node[key] or not local:
            checks.append(_result("unresolved", path + "." + key, reason="ast_role_not_bound_to_own_source",
                                  proof={"side": side, "source": copy.deepcopy(origin), "claimed": node[key],
                                         "literal": original, "statement_local": local}))
    from .requirement_graph import _semantic_token_matches

    def token(claimed, origin, dimension, token_path):
        raw = resolver(side, copy.deepcopy(origin)) if isinstance(origin, dict) else None
        valid = isinstance(raw, str) and local_origin(origin) and _semantic_token_matches(dimension, claimed, raw)
        if not valid:
            checks.append(_result("unresolved", token_path, reason="ast_operator_not_bound_to_own_source",
                                  proof={"side": side, "source": copy.deepcopy(origin), "claimed": claimed,
                                         "literal": raw, "dimension": dimension}))
        return raw

    kind = node.get("kind")
    if kind == "coordination":
        origins = node.get("operator_sources", [])
        printed = [resolver(side, copy.deepcopy(origin)) if isinstance(origin, dict) else None for origin in origins]
        allowed = {"and": {"and", "和", "与", "與", "及", "并", "並", "且", "并且", "並且", "以及"},
                   "or": {"or", "或"}, "but": {"but"}}.get(node.get("operator"), set())
        if node.get('mode') == 'circumstance_operations' and node.get('operator') == 'and':
            allowed |= {'；', ';'}
        normalized = [raw.strip().casefold() if isinstance(raw, str) else None for raw in printed]
        valid = (bool(origins) and all(local_origin(origin) for origin in origins)
                 and all(raw in allowed | {",", "，", "、"} for raw in normalized)
                 and (node.get("operator") == "and" or any(raw in allowed for raw in normalized)))
        if not valid:
            checks.append(_result("unresolved", path + ".operator", reason="ast_coordination_operator_not_bound_to_source",
                                  proof={"side": side, "operator": node.get("operator"), "literals": printed,
                                         "sources": copy.deepcopy(origins)}))
    elif kind == "modality":
        raw = token(node.get("operator"), node.get("operator_source"), "modality", path + ".operator")
        own_negative = node.get("negation_source")
        if own_negative is not None:
            token("negative", own_negative, "modal_polarity", path + ".polarity")
        lexical_negative = isinstance(raw, str) and (bool(re.search(r"\bnot\b", raw, re.I))
            or _semantic_token_matches("modal_polarity", "negative", raw) or raw.strip() in {"不可以", "不能够", "不能夠"})
        # Chinese prohibition 不得 supplies a MUST modal and negates its
        # action child. It does not express the absence of an obligation.
        if (isinstance(raw, str) and raw.strip() == "不得" and node.get("operator") == "must"
                and node.get("child", {}).get("kind") == "negation"):
            negative_origin = node["child"].get("operator_source")
            modal_span = node.get("operator_source", {}).get("text_span", [])
            negative_span = negative_origin.get("text_span", []) if isinstance(negative_origin, dict) else []
            if (local_origin(negative_origin) and len(modal_span) == len(negative_span) == 2
                    and modal_span[0] == negative_span[0] < negative_span[1] <= modal_span[1]
                    and _semantic_token_matches("polarity", "negative", resolver(side, negative_origin))):
                lexical_negative = False
        if node.get("polarity") != ("negative" if lexical_negative or own_negative is not None else "positive"):
            checks.append(_result("unresolved", path + ".polarity", reason="ast_modal_polarity_not_bound_to_source",
                                  proof={"side": side, "literal": raw, "polarity": node.get("polarity")}))
    elif kind == "negation":
        token("negative", node.get("operator_source"), "polarity", path + ".operator")
    elif kind in {"condition", "exception", "fronted_context", "circumstance_scope"}:
        token(node.get("operator"), node.get("operator_source"), "operator", path + ".operator")
        if kind == "fronted_context":
            from .fronted_nominal_context import validate_fronted_operation

            try:
                validate_fronted_operation(node, lambda origin, label: resolver(side, origin))
            except (ValueError, KeyError, TypeError) as error:
                checks.append(_result("unresolved", path, reason="fronted_operation_not_bound_to_source",
                                      proof={"side": side, "detail": str(error)}))
    elif kind == "quantity_comparison" and (node.get("operator") != "eq" or node.get("operator_source")):
        token(node.get("operator"), node.get("operator_source"), "comparison_operator", path + ".operator")
    if kind == "conditions":
        for position, binding in enumerate(node.get("bindings", [])):
            token(binding.get("operator"), binding.get("operator_source"), "operator", f"{path}.bindings[{position}].operator")
    if "tense" in node:
        token(node["tense"], node.get("tense_source"), "tense", path + ".tense")
    if kind == "active_aspect":
        token(node.get("aspect"), node.get("aspect_source"), "aspect", path + ".aspect")
    if kind == "reporting":
        token(node.get("attribute"), node.get("predicate_source"), "reporting_action", path + ".attribute")
    if kind == "noun_phrase":
        from .nominal_syntax import validate_nominal_sources

        try:
            validate_nominal_sources({"logic": [node]}, {}, lambda origin, label: resolver(side, origin))
        except (ValueError, KeyError, TypeError) as error:
            checks.append(_result("unresolved", path, reason="ast_nominal_evidence_not_bound_to_source",
                                  proof={"side": side, "detail": str(error)}))
    if kind == 'cjk_nominal':
        from .cjk_circumstances import validate_cjk_nominal

        try:
            validate_cjk_nominal(node, lambda origin, label: resolver(side, origin))
        except (ValueError, KeyError, TypeError) as error:
            checks.append(_result('unresolved', path, reason='ast_cjk_nominal_not_bound_to_source',
                                  proof={'side': side, 'detail': str(error)}))
    if kind in {"purpose_scope", "controlled_infinitive_scope", "discourse_scope"}:
        from .infinitival_syntax import validate_infinitival_sources

        try:
            validate_infinitival_sources({"logic": [node]}, {}, lambda origin, label: resolver(side, origin))
        except (ValueError, KeyError, TypeError) as error:
            checks.append(_result("unresolved", path, reason="ast_control_or_discourse_not_bound_to_source",
                                  proof={"side": side, "detail": str(error)}))
    if kind == "document_composition":
        from .document_composition_requirements import read_document_composition

        own = read_document_composition(literal, source)
        interpreted = own["logic"][0] if own["complete"] else None
        if interpreted is None or any(node.get(key) != value for key, value in interpreted.items()):
            checks.append(_result("unresolved", path, reason="document_composition_not_bound_to_complete_source",
                                  proof={"side": side, "source": copy.deepcopy(source)}))
    return checks


def _scalar(required, actual, key, path, context, role=None):
    if role == "value" and key in {"head", "value", "object"} and isinstance(required, str) and isinstance(actual, str):
        first, second = read_measurement_literal(required), read_measurement_literal(actual)
        if first["matched"] and second["matched"]:
            decision = decide_equivalence(first, second, "unit" if context.get("layer") == "L" else "quantity", context=context)
            status = "equivalent" if decision["equivalent"] else "unresolved" if decision["status"] == "unresolved" else "conflict"
            return _result(status, path, reason=decision["rule_id"], proof={"equivalence": decision,
                "whole_printed_measurement": True, "value_compared": context.get("layer") != "L"}, conflicts=decision["conflicts"])
        if context.get("layer") == "L":
            status = "equivalent" if bool(required) == bool(actual) else "missing" if required else "conflict"
            return _result(status, path, reason="asserted_scalar_payload_graded_by_business",
                           proof={"value_compared": False, "required_present": bool(required), "actual_present": bool(actual)})
    dimension = key if key in _PERIOD_KEYS else "label" if key in {"attribute", "action"} else "number" if key == "value" else "literal"
    decision = decide_equivalence(required, actual, dimension, context=context)
    status = "equivalent" if decision["equivalent"] else "unresolved" if decision["status"] == "unresolved" else "conflict"
    return _result(status, path, reason=decision["rule_id"], proof={"equivalence": decision}, conflicts=decision["conflicts"])


def compare_requirement_ast(required: Any, actual: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare complete interpreted trees without flattening their operators.

    ``source_resolver(side, source)`` may return the exact literal for an own
    source span. Without it, source identities and ranges are retained as proof
    and must already have passed the owning graph's source validation. Unknown
    syntax is never equivalent, even when identical on both sides.
    """
    context = {"canonicalize": _canonical, **(context or {})}
    if isinstance(required, dict) and required.get('kind') in {'content_sequence', 'content_join'}:
        if not isinstance(actual, dict) or actual.get('kind') not in {'content_sequence', 'content_join'}:
            return _result('missing', '$', reason='required_content_ast_missing')
        return compare_content_ast(required, actual, context)
    limit = context.get("max_depth", 64)

    def typed_root(value):
        if isinstance(value, dict):
            return isinstance(value.get("kind"), str)
        return isinstance(value, (list, tuple)) and bool(value) and all(typed_root(item) for item in value)

    if not typed_root(required):
        return _result("unresolved", "$", reason="requirement_ast_type_not_declared")

    def compare(first, second, path, key=None, depth=0, role=None):
        if depth > limit:
            return _result("unresolved", path, reason="ast_comparison_depth_exceeded")
        if first is _MISSING:
            return _result("conflict", path, reason="unexpected_semantic_node", proof={"actual": copy.deepcopy(second)})
        if second is _MISSING or second is None and first is not None:
            return _result("missing", path, reason="required_semantic_node_missing", proof={"required": copy.deepcopy(first)})
        if first is None or second is None:
            return _scalar(first, second, key, path, context, role)
        if isinstance(first, dict) and isinstance(second, dict):
            kinds = (first.get("kind"), second.get("kind"))
            source_proof = {"required": copy.deepcopy(first.get("source")), "actual": copy.deepcopy(second.get("source"))}
            if any(kind is not None and kind not in _SCHEMAS for kind in kinds):
                return _result("unresolved", path, reason="ast_kind_not_supported", proof={"kinds": kinds, "sources": source_proof})
            if kinds[0] != kinds[1]:
                return _result("conflict", path, reason="ast_kind_conflict", proof={"kinds": kinds, "sources": source_proof}, conflicts=["operator_placement_or_node_kind"])
            children = []
            if kinds[0] is not None:
                children.extend(_source_checks(first, "required", path, context))
                children.extend(_source_checks(second, "actual", path, context))
                for side, node in (("required", first), ("actual", second)):
                    absent = _SCHEMAS[kinds[0]] - node.keys()
                    if absent:
                        children.append(_result("unresolved" if side == "required" else "missing", path,
                            reason="ast_semantic_schema_incomplete", proof={"side": side, "keys": sorted(absent)}))
                    allowed = _OPERATORS.get(kinds[0])
                    if allowed is not None and "operator" in node and node["operator"] not in allowed:
                        children.append(_result("unresolved", path + ".operator", reason="ast_operator_not_supported",
                                                proof={"side": side, "operator": node["operator"]}))
                    if kinds[0] == "coordination" and isinstance(node.get("children"), list) and len(node["children"]) < 2:
                        children.append(_result("unresolved" if side == "required" else "missing", path + ".children",
                                                reason="coordination_requires_multiple_members", proof={"side": side}))
            for side, node in (("required", first), ("actual", second)):
                if (node.get("status") in _UNRESOLVED or node.get("complete") is False
                        or node.get("unresolved") or node.get("pending")):
                    children.append(_result("unresolved", path, reason="ast_interpretation_incomplete", proof={"side": side}))
            skip = set()
            if kinds[0] in {"quantity", "quantity_assertion", "quantity_comparison", "year_on_year_change"} and "value" in first and "value" in second:
                scalar_count = kinds[0] == "quantity_comparison" and role == "asserted_quantifier" and first.get("operator") == second.get("operator") == "eq"
                quantity = decide_equivalence(first, second, "unit" if context.get("layer") == "L" and (kinds[0] == "quantity" or scalar_count or first.get("sequence_source")) else "quantity", context=context)
                status = "equivalent" if quantity["equivalent"] else "unresolved" if quantity["status"] == "unresolved" else "conflict"
                children.append(_result(status, path + ".quantity", reason=quantity["rule_id"], proof={"equivalence": quantity}, conflicts=quantity["conflicts"]))
                skip.update({"value", "unit", "currency", "quantity_role"})
            first_keys, second_keys = _semantic_keys(first), _semantic_keys(second)
            if (kinds[0] == 'discourse_scope' and first.get('role') == second.get('role') == 'item_label'
                    and context.get('layer') == 'B'):
                first_keys.discard('marker')
                second_keys.discard('marker')
            delegated = []
            if kinds[0] == "proposition":
                for surface_role in ("object", "subject"):
                    closed = [_nominal_role_closed(node, surface_role) for node in (first, second)]
                    # A supplied role origin makes closure enforceable even
                    # without an external resolver. Legacy hand-authored AST
                    # fixtures without role evidence retain scalar comparison.
                    for side, node, complete in zip(("required", "actual"), (first, second), closed, strict=True):
                        if isinstance(node.get(surface_role + "_source"), dict) and node.get(surface_role + "_phrase") is not None and not complete:
                            children.append(_result("unresolved", path + "." + surface_role + "_phrase",
                                reason="ast_nominal_role_not_source_closed", proof={"side": side}))
                    if all(closed):
                        first_keys.discard(surface_role)
                        second_keys.discard(surface_role)
                        delegated.append(surface_role)
            if kinds[0] == 'fronted_context' and first.get('operation') and second.get('operation') and context.get('source_resolver'):
                # Raw adjunct wording remains source/T evidence. The complete
                # controlled operation owns semantic comparison, as a bound
                # noun phrase already owns its surface subject/object.
                from .fronted_nominal_context import validate_fronted_operation

                try:
                    for side, node in (('required', first), ('actual', second)):
                        validate_fronted_operation(node, lambda origin, label, side=side: context['source_resolver'](side, origin))
                except (ValueError, KeyError, TypeError):
                    pass
                else:
                    first_keys.discard('context')
                    second_keys.discard('context')
            for field in sorted((first_keys | second_keys) - skip):
                if field == "scope" and context.get("contexts") is not None and first.get("scope"):
                    scope = verify_scope(first["scope"], second, list(context.get("declared_paths", [])),
                                         contexts=context["contexts"], canonicalize=context["canonicalize"],
                                         context_labels=context.get("context_labels", ()))
                    status = "equivalent" if scope["correct"] else "conflict" if scope["status"] == "explicit_conflict" else "missing" if scope["status"] == "missing" else "unresolved"
                    children.append(_result(status, path + ".scope", reason=scope["reason"], proof={"scope": scope}))
                elif (field == "children" and kinds[0] == "coordination" and first.get("operator") in {"and", "or"}
                      and first.get("mode") != "sequence" and not first.get("ordered") and not first.get("sequence")
                      and first.get("ordering") not in {"ordered", "sequence", "source_order"}
                      and isinstance(first.get(field), list) and isinstance(second.get(field), list)):
                    children.append(compare_group(first[field], second[field], path + ".children", depth + 1, role))
                else:
                    child_role = role
                    if field in {"object", "object_phrase", "value"}:
                        child_role = "logical_operand" if role == "logical_operand" else "value"
                    elif field in {"subject", "subject_phrase"}:
                        child_role = "identity"
                    elif field == "quantifier":
                        child_role = "asserted_quantifier" if role == "value" else "threshold"
                    elif (kinds[0] in {"conditions", "condition", "exception"} and field in {"bindings", "operand"}
                          or kinds[0] in {"relative", "restrictive_relative"} and field == "restriction"
                          or kinds[0] in {"purpose_scope", "controlled_infinitive_scope"} and field == "operand"):
                        child_role = "logical_operand"
                    elif kinds[0] == "prepositional_complement" and field == "complement":
                        child_role = "temporal" if first.get("semantic_role") == "temporal_scope" else "identity"
                    children.append(compare(first.get(field, _MISSING), second.get(field, _MISSING), path + "." + field, field, depth + 1, child_role))
            return _combine(children, path, sources=source_proof, kind=kinds[0],
                            source_closed_nominal_roles=delegated,
                            **{evidence_key: {"required": copy.deepcopy(first.get(evidence_key)),
                                              "actual": copy.deepcopy(second.get(evidence_key))}
                               for evidence_key in ("record_evidence", "field_label_evidence")
                               if evidence_key in first or evidence_key in second})
        if isinstance(first, (list, tuple)) and isinstance(second, (list, tuple)):
            children = [compare(first[index] if index < len(first) else _MISSING,
                                second[index] if index < len(second) else _MISSING,
                                f"{path}[{index}]", key, depth + 1, role)
                        for index in range(max(len(first), len(second)))]
            return _combine(children, path, rule="ordered_semantic_members", required_count=len(first), actual_count=len(second))
        if type(first) is not type(second):
            return _result("conflict", path, reason="ast_value_type_conflict", conflicts=["semantic_value_type"])
        return _scalar(first, second, key, path, context, role)

    def compare_group(first, second, path, depth, role):
        """Compare a complete multiset inside its already bound owning group.

        Statement retrieval has already established subject/predicate/context.
        Full child semantics may now prove a group-wide bijection. Duplicate
        members retain multiplicity; no candidate can prove two members.
        """
        pairs = [[compare(member, candidate, f"{path}[{index}]", "children", depth + 1, role)
                  for candidate in second] for index, member in enumerate(first)]
        actual_to_required = {}

        def augment(index, visited):
            for other in range(len(second)):
                if other in visited or not pairs[index][other]["equivalent"]:
                    continue
                visited.add(other)
                if other not in actual_to_required or augment(actual_to_required[other], visited):
                    actual_to_required[other] = index
                    return True
            return False

        for index in range(len(first)):
            augment(index, set())
        chosen = {index: other for other, index in actual_to_required.items()}
        available = set(range(len(second))) - set(actual_to_required)
        matches, children = [], []
        for index, member in enumerate(first):
            if index not in chosen and available:
                identity = _identity(member, context["canonicalize"])
                own = [other for other in sorted(available)
                       if _identity(second[other], context["canonicalize"]) == identity]
                # Residual failures are paired by independent roles, then by
                # source order. Values never choose a statement or a nearest
                # answer. All exact group matches were already established.
                chosen[index] = own[0] if own else min(available)
                available.remove(chosen[index])
            other = chosen.get(index)
            decision = pairs[index][other] if other is not None else compare(member, _MISSING, f"{path}[{index}]", "children", depth + 1, role)
            children.append(decision)
            matches.append({"required_index": index, "actual_index": other, "decision": decision})
        for other in sorted(available):
            own = compare(second[other], second[other], f"{path}[extra:{other}]", "children", depth + 1, role)
            children.append(_result("conflict", f"{path}[extra:{other}]", reason="unexpected_group_member",
                                    proof={"actual_index": other, "children": [own]}))
        return _combine(children, path, rule="bound_group_semantic_multiset", matches=matches,
                        unadjudicated_extra_indices=sorted(available), required_count=len(first), actual_count=len(second),
                        capacity_one=True, owning_group_already_bound=True, value_used_for_statement_identity=False)

    return compare(required, actual, "$")


def _walk(value):
    if isinstance(value, dict):
        yield value
        for key, item in value.items():
            if not _provenance_key(key):
                yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)


def _feature_present(feature, statements):
    nodes = list(_walk(statements))
    kinds = {node.get("kind") for node in nodes}
    if feature == 'active_aspect_scope' and any(node.get('kind') == 'proposition'
            and node.get('lexical_qualifiers', {}).get('aspect') in {'perfect', 'progressive'} for node in nodes):
        return True
    expected = {
        "coordination_scope": "coordination", "alternative_membership": "coordination",
        "contrast_scope": "coordination", "modal_operator": "modality", "ability_operator": "modality",
        "negation_scope": "negation", "condition_operands": "conditions", "restrictive_relative": "relative",
        "scoped_reporting": "reporting", "temporal_prose_scope": "temporal_scope",
        "active_aspect_scope": "active_aspect", "fronted_nominal_context": "fronted_context",
        "noun_phrase_composition": "noun_phrase", "prepositional_attachment": "prepositional_complement",
        "quantity_comparison": "quantity_comparison",
        "circumstance_scope": "circumstance_scope",
        "purpose_scope": "purpose_scope", "controlled_infinitive_scope": "controlled_infinitive_scope", "discourse_scope": "discourse_scope",
    }
    if feature == "finite_tense":
        return any(isinstance(node.get("tense"), str) and node["tense"] for node in nodes)
    if feature == 'noun_phrase_composition' and 'cjk_nominal' in kinds:
        return True
    if feature == "nested_operator_scopes":
        wrappers = {"negation", "modality", "conditions", "relative", "reporting", "temporal_scope", "active_aspect", "fronted_context", "circumstance_scope"}
        return any(node.get("kind") in wrappers and any(child.get("kind") in wrappers for child in
            _walk([node.get('child'), node.get('operand')])) for node in nodes)
    if feature == "negation_scope" and any(node.get("kind") == "modality" and node.get("polarity") == "negative" for node in nodes):
        return True
    operators = {"coordination_scope": "and", "alternative_membership": "or", "contrast_scope": "but"}
    if feature in operators:
        return any(node.get("kind") == "coordination" and node.get("operator") == operators[feature] for node in nodes)
    if feature in {"modal_operator", "ability_operator"}:
        return any(node.get("kind") == "modality" and (node.get("operator") == "ability") == (feature == "ability_operator") for node in nodes)
    return expected.get(feature) in kinds if feature in expected else False


def compare_feature_ast(feature, required, actual, context=None):
    """Execute a feature's comparator only when its required AST is present."""
    if feature not in AST_FEATURE_COMPARATORS or not _feature_present(feature, required):
        return _result("unresolved", "$", reason="feature_has_no_comparable_requirement_ast", proof={"feature": feature})
    return compare_requirement_ast(required, actual, context)


# Each entry invokes the complete recursive comparator, rather than certifying
# a feature from its name or a flat relation/field count.
AST_FEATURE_COMPARATORS = {feature: compare_feature_ast for feature in (
    "finite_tense", "coordination_scope", "alternative_membership", "contrast_scope", "modal_operator", "ability_operator",
    "negation_scope", "condition_operands", "restrictive_relative", "scoped_reporting", "temporal_prose_scope",
    "active_aspect_scope", "fronted_nominal_context", "nested_operator_scopes", "noun_phrase_composition",
    "prepositional_attachment", "quantity_comparison",
    "purpose_scope", "controlled_infinitive_scope", "discourse_scope",
    "circumstance_scope",
)}


def _identity(tree, canonicalize, *, context=None, side=None):
    # Object/quantity values, modality and condition answers are deliberately
    # absent. They can establish a comparison only after identity retrieval.
    def main_leaves(node):
        if not isinstance(node, dict):
            return []
        if node.get("kind") in {"proposition", "document_composition"}:
            return [node]
        if node.get("kind") == "cjk_measurement_sequence":
            return [{"subject": clause.get("subject"), "attribute": clause.get("operator_text", clause.get("kind"))}
                    for clause in node.get("clauses", []) if isinstance(clause, dict)]
        if node.get("kind") == "coordination":
            return [leaf for child in node.get("children", []) for leaf in main_leaves(child)]
        if node.get("kind") == "logical_group":
            return main_leaves(node.get("tree"))
        return main_leaves(node.get("child"))

    leaves = main_leaves(tree)
    result = {"subjects": sorted({canonicalize(node["subject"]) for node in leaves if isinstance(node.get("subject"), str)}),
            "predicates": sorted({decide_equivalence(node["attribute"], node["attribute"], "label",
                context={"canonicalize": canonicalize})["canonical"]["required"] for node in leaves if isinstance(node.get("attribute"), str)}),
            "scopes": [node["scope"] for node in leaves if node.get("scope")]}

    def normalized(value):
        if isinstance(value, dict):
            return {key: normalized(item) for key, item in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [normalized(item) for item in value]
        return canonicalize(value) if isinstance(value, str) else value

    scopes = {repr(normalized(scope)): normalized(scope) for scope in result["scopes"]}
    result["scopes"] = [scopes[key] for key in sorted(scopes)]
    facets = [normalized(node["identity_facets"]) for node in leaves if node.get("identity_facets")]
    if facets:
        unique = {repr(facet): facet for facet in facets}
        result["identity_facets"] = [unique[key] for key in sorted(unique)]
    if isinstance(tree, dict) and tree.get("kind") == "cjk_measurement_sequence":
        result["periods"] = []
        period = tree.get("period")
        owner = tree.get("source") if isinstance(tree.get("source"), dict) else {}
        if isinstance(period, dict):
            origin = period.get("source") if isinstance(period.get("source"), dict) else {}
            outer, local = owner.get("text_span"), origin.get("text_span")
            resolver = (context or {}).get("source_resolver")
            valid_spans = all(isinstance(span, (list, tuple)) and len(span) == 2
                              and all(type(value) is int for value in span) for span in (outer, local))
            own_source = (owner.get("path") == origin.get("path") and owner.get("lines") == origin.get("lines")
                and all(owner.get(key) == origin.get(key) for key in ("cell", "block", "native_path"))
                and valid_spans and outer[0] <= local[0] < local[1] <= outer[1])
            literal = resolver(side, copy.deepcopy(origin)) if resolver and own_source else None
            if literal == period.get("text") and isinstance(literal, str):
                result["periods"] = [decide_equivalence(literal, literal, "period",
                    context={"canonicalize": canonicalize})["canonical"]["required"]]
            else:
                result["period_identity_source_unresolved"] = True
    return result


def compare_requirement_ast_collections(required, actual, context=None):
    """Retrieve statements by role identity, then compare, with capacity one.

    A unique answer value never chooses among duplicate role identities. Each
    textual/role hit, explicit rejection and unused candidate remains in trace.
    """
    context = {"canonicalize": _canonical, **(context or {})}
    if not required:
        return _result("unresolved", "$", reason="no_interpreted_requirement_ast",
                       proof={"rows": [], "unadjudicated_extra_indices": list(range(len(actual))), "capacity_one": True})
    canonicalize = context["canonicalize"]
    identities = [_identity(tree, canonicalize, context=context, side="actual") for tree in actual]
    available = set(range(len(actual)))
    rows = []
    for index, tree in enumerate(required):
        wanted = _identity(tree, canonicalize, context=context, side="required")
        trace, accepted, rejected_conflicts = [], [], []
        for candidate_index, own in enumerate(identities):
            shared_predicates = set(wanted["predicates"]) & set(own["predicates"])
            shared_subjects = set(wanted["subjects"]) & set(own["subjects"])
            hit = bool(shared_predicates or shared_subjects)
            conflicts = []
            if wanted["subjects"] != own["subjects"]:
                conflicts.append("subject_identity")
            if not shared_predicates:
                conflicts.append("predicate_identity")
            if wanted["scopes"] != own["scopes"]:
                conflicts.append("scope_identity")
            if wanted.get("identity_facets", []) != own.get("identity_facets", []):
                conflicts.append("record_or_facet_identity")
            if wanted.get("periods", []) != own.get("periods", []):
                conflicts.append("printed_period_identity")
            if wanted.get("period_identity_source_unresolved") or own.get("period_identity_source_unresolved"):
                conflicts.append("printed_period_source_unresolved")
            reusable = candidate_index in available
            valid = hit and not conflicts and reusable
            trace.append({"candidate_index": candidate_index, "textual_role_hit": hit,
                          "identity": own, "conflicts": conflicts, "capacity_available": reusable,
                          "accepted_for_comparison": valid, "value_used": False})
            if valid:
                accepted.append(candidate_index)
            elif hit and conflicts:
                rejected_conflicts.append(candidate_index)
        if len(accepted) == 1:
            chosen = accepted[0]
            decision = compare_requirement_ast(tree, actual[chosen], context)
            available.remove(chosen)
        elif len(accepted) > 1:
            chosen = None
            decision = _result("unresolved", f"$[{index}]", reason="ast_statement_identity_ambiguous")
        else:
            chosen = None
            unknown_period = wanted.get("period_identity_source_unresolved") or any(
                hit["textual_role_hit"] and "printed_period_source_unresolved" in hit["conflicts"] for hit in trace)
            decision = _result("unresolved" if unknown_period else "conflict" if rejected_conflicts else "missing", f"$[{index}]",
                               reason="ast_statement_period_source_unresolved" if unknown_period
                               else "ast_statement_identity_conflict" if rejected_conflicts else "ast_statement_missing")
        rows.append({"required_index": index, "actual_index": chosen, "decision": decision,
                     "retrieval": {"query": wanted, "candidates": trace, "value_used": False}})
    result = _combine([row["decision"] for row in rows], "$", rows=rows,
                      unadjudicated_extra_indices=sorted(available), capacity_one=True)
    if available and result["equivalent"]:
        result.update(status="unresolved", equivalent=False, unresolved=True,
                      rule_id="ast_extra_statements_unadjudicated")
    return result
