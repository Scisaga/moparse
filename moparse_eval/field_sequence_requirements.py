"""Source-only decoding of bounded, explicitly typed field sequences.

A plain prefix is not automatically an attribute. Complete date selectors
are delegated to the common period reader, and unresolved comparison periods
never come from sorting the years or inspecting the values.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from .measurement_evidence import read_measurement_label, read_measurement_literal
from .period_evidence import read_period_label

_PAIR = re.compile(r"\s*([^:：\n]+?)\s*[:：]\s*(.*?)\s*", re.S)
_ATTRIBUTE_ROLE = re.compile(
    r"(?:primary|main|core)\s+(?:purpose|function|application|use)|purpose|application|"
    r"revenue|profit|amount|sales|income|cost|gross\s+margin|net\s+margin|operating\s+profit|"
    r"total\s+assets|cash\s+flow|count|quantity|status|"
    r"核心用途|主要用途|主要目的|核心功能|收入|營業收入|营业收入|銷售收入|销售收入|"
    r"利潤|利润|金額|金额|成本|毛利率|淨利率|净利率|數量|数量|狀態|状态", re.I)
_DECLARATION = re.compile(r"Metric|Attribute|Property|Indicator|指标|指標|属性|屬性", re.I)
_YEAR = re.compile(r"(?:19|20)\d{2}年?")
_TIME_CUE = re.compile(r"\b(?:year|period|quarter|month|week)\s+ended\b|\bas\s+of\b|截至|截止|年度|期末|"
                       r"^(?:19|20)\d{2}年|[〇零一二三四五六七八九]{4}年|"
                       r"(?:19|20)\d{2}(?:年.+月|\-\d{1,2}\-\d{1,2})", re.I)
_CHANGE = re.compile(r"Change|(?:YoY|year.over.year)(?:\s+change)?|變動|变动|同比(?:變動|变动)?|"
                     r"金[額额]同比[變变][動动]", re.I)
_METADATA = re.compile(r"Units?|Currency|Period|Scope|Note|单位|單位|币种|幣種|期间|期間|口径|口徑|附注|附註", re.I)
_RECORD_METRIC = re.compile(
    r'(?:(?:期初|期末|本期|當期|当期|本年|上期|上年|其他)?'
    r'(?:金額|金额|餘額|余额|變動|变动|公允(?:價值|价值)(?:變動|变动)(?:損益|损益)?|'
    r'(?:計提|计提)的(?:減值|减值)|(?:購買|购买|出售|贖回|赎回)(?:/(?:出售|贖回|赎回))?(?:金額|金额))|'
    r'(?:計入|计入)(?:權益|权益|損益|损益)的(?:累計|累计)(?:公允(?:價值|价值))?(?:變動|变动)|'
    r'(?:營業|营业|銷售|销售|經營|经营)?(?:收入|成本|利潤|利润)|(?:毛|淨|净)?利率(?:[（(](?:註|注)[）)])?|'
    r'資金來源|资金来源)(?:(?:比上年同期|比上年|比上期)(?:增減|增减))?')


def _result():
    return {"matched": False, "facts": [], "relations": [], "text_atoms": [], "controls": [],
            "consumed_spans": [], "text_projection_complete": False, "blockers": [], "issues": [],
            "pending_requirements": [], "scope": {},
            "projection_inputs": {"objects": [], "locators": [], "source_fragments": []}}


def _offset(source):
    span = source.get("text_span")
    return span[0] if isinstance(span, (list, tuple)) and len(span) == 2 and type(span[0]) is int else 0


def _source(source, start, end):
    offset = _offset(source)
    return {**copy.deepcopy(source), "text_span": [offset + start, offset + end]}


def _trim(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _parts(text):
    return [_trim(text, match.start(), match.end()) for match in re.finditer(r"[^;；]+", text) if match[0].strip()]


def _atom(result, text, source, start, end, role):
    if start < end and not any(item["span"] == [start, end] and item["role"] == role for item in result["text_atoms"]):
        result["text_atoms"].append({"text": text[start:end], "role": role, "span": [start, end],
                                     "source": _source(source, start, end)})


def _proof_atom(result, text, source, proof, role):
    a, b = proof["text_span"]
    _atom(result, text, source, a - _offset(source), b - _offset(source), role)


def _project(result, text, source):
    owned = {position for item in [*result["text_atoms"], *result["controls"]] for position in range(*item["span"])}
    for match in re.finditer(r"[^\s;；:：()（）,.。，]+|[\s;；:：()（）,.。，]+", text):
        uncovered = [position for position in range(*match.span()) if position not in owned]
        if not uncovered:
            continue
        groups, start = [], uncovered[0]
        previous = start
        for position in uncovered[1:]:
            if position != previous + 1:
                groups.append((start, previous + 1))
                start = position
            previous = position
        groups.append((start, previous + 1))
        for a, b in groups:
            fragment = text[a:b]
            if re.fullmatch(r"[\s;；:：()（）,.。，]+", fragment):
                result["controls"].append({"text": fragment, "span": [a, b], "source": _source(source, a, b),
                                           "reason": "explicit_field_sequence_separator"})
            else:
                _atom(result, text, source, a, b, "unresolved_text")
                _pending(result, "field_sequence_unconsumed_wording", fragment, _source(source, a, b))
    result["consumed_spans"] = [copy.deepcopy(item) for item in [*result["text_atoms"], *result["controls"]]]
    covered = {position for item in result["consumed_spans"] for position in range(*item["span"])}
    result["text_projection_complete"] = all(position in covered for position in range(len(text)))


def _pending(result, reason, text, source, *, kind="field_sequence_role", **detail):
    item = {"kind": kind, "reason": reason, "text": text, "source": copy.deepcopy(source), "layers": ["B", "L"], **detail}
    result["pending_requirements"].append(item)
    result["blockers"].append(copy.deepcopy(item))


def _measurement(text, source, start, end):
    parsed = read_measurement_literal(text[start:end], _source(source, start, end))
    if not parsed["matched"] and text[start:end].endswith((".", "。")):
        shorter = read_measurement_literal(text[start:end - 1], _source(source, start, end - 1))
        if shorter["matched"]:
            parsed, end = shorter, end - 1
    return parsed, end


def read_labelled_record(text, source, *, scope=(), qualifiers=None, qualifier_sources=None, parents=()):
    """Expose every printed label/scalar in a closed record, not an opaque value.

    Only already named financial columns and lossless scalars enter this
    grammar. A nested record must independently retain its own fields and a
    source-proved parent record label; parent amounts never fill child slots.
    """
    result = _result()
    selections = _read_selection_record(text, source, scope=scope)
    if selections['matched']:
        return selections
    outer = re.match(r'(?P<name>[^:：;；。\n]{1,80})[:：](?P<body>.+)', text)
    if outer is None or not re.search(r'[;；]', outer['body']):
        return result
    if re.search(r'主要|因為|因为|由於|由于|其中|[為为].*\d|https?://', outer['name']):
        return result
    fields, unread = [], []
    for match in re.finditer(r'[^;；]+', text[outer.start('body'):]):
        a, b = _trim(text, outer.start('body') + match.start(), outer.start('body') + match.end())
        candidates = []
        for cut in range(a + 1, b):
            label = text[a:cut].rstrip(':： ')
            if not _RECORD_METRIC.fullmatch(label):
                continue
            scalar, raw_end = _measurement(text, source, cut, b)
            if scalar['matched']:
                candidates.append((label, cut, scalar, raw_end))
            elif text[cut:b].rstrip('。.') in {'不適用', '不适用', '–', '—', '-'}:
                candidates.append((label, cut, {'matched': True, 'value': text[cut:b].rstrip('。.'), 'unit': None, 'currency': None,
                    'sources': {'value': _source(source, cut, b - int(text[b - 1:b] in '。.'))}}, b - int(text[b - 1:b] in '。.')))
        if len(candidates) != 1:
            unread.append((a, b))
        else:
            fields.append((a, b, *candidates[0]))
    if len(fields) < 2:
        return result
    result['matched'] = True
    name = outer['name'].strip()
    name_start = outer.start('name') + len(outer['name']) - len(outer['name'].lstrip())
    name_source = _source(source, name_start, name_start + len(name))
    rows = [{'role': 'record_label', 'text': name, 'source': copy.deepcopy(name_source)}]
    groups = []
    for parent in parents:
        if not isinstance(parent, dict) or not parent.get('source', {}).get('path'):
            _pending(result, 'labelled_record_parent_source_unavailable', text, source)
            continue
        own = read_labelled_record(parent['text'], parent['source'])
        if not own['matched'] or own['blockers'] or {f['attribute'] for f in own['facts']} != {f[2] for f in fields}:
            _pending(result, 'labelled_record_parent_roles_unresolved', text, source, parent=copy.deepcopy(parent))
            continue
        label = own['record_label']
        rows.append({'role': 'row_group', **copy.deepcopy(label)})
        groups.append(label['text'])
    result['record_label'] = {'text': name, 'source': copy.deepcopy(name_source)}
    result['projection_inputs']['locators'] = [{'role': 'record_label', **copy.deepcopy(result['record_label'])}]
    result['projection_inputs']['source_fragments'] = [{'text': text, 'source': copy.deepcopy(source)}]
    _atom(result, text, source, name_start, name_start + len(name), 'locator')
    for a, _b, label, cut, measured, raw_end in fields:
        label_source = _source(source, a, a + len(label))
        q, qs = copy.deepcopy(qualifiers or {}), copy.deepcopy(qualifier_sources or {})
        if label in {'資金來源', '资金来源'} or re.search(r'率|比上年|比上期', label):
            for key in ('unit', 'currency'):
                q.pop(key, None)
                qs.pop(key, None)
        for key in ('unit', 'currency'):
            if measured[key]:
                q[key], qs[key] = measured[key], copy.deepcopy(measured['sources'][key])
        if measured['unit'] in {'%', '‰'}:
            q.pop('currency', None)
            qs.pop('currency', None)
        position = re.match(r'期初|期末|本期', label)
        if position:
            q['period'] = position[0]
            qs['period'] = _source(source, a, a + position.end())
        if cumulative := re.search(r'累計|累计', label):
            q['aggregation'] = cumulative[0]
            qs['aggregation'] = _source(source, a + cumulative.start(), a + cumulative.end())
        basis = re.search(r'比上年同期|比上年|比上期', label)
        if basis:
            q['comparison_basis'] = basis[0]
            qs['comparison_basis'] = _source(source, a + basis.start(), a + basis.end())
        fact = {'id': f'labelled-record:{len(result["facts"])}', 'subject': name, 'subject_source': copy.deepcopy(name_source),
            'attribute': label, 'attribute_source': copy.deepcopy(label_source), 'value': measured['value'], 'role': 'metric',
            'qualifiers': q, 'qualifier_sources': qs, 'scope': list(scope), 'identity_facets': {'group': groups} if groups else {},
            'source': _source(source, cut, raw_end), 'value_source': copy.deepcopy(measured['sources']['value']),
            'raw_value': text[cut:raw_end], 'row_evidence': copy.deepcopy(rows),
            'header_evidence': [{'role': 'column_header', 'text': label, 'source': copy.deepcopy(label_source)}],
            'record_id': 'labelled-record:' + json.dumps(name_source, sort_keys=True), 'rule_id': 'printed_financial_label_scalar_record',
            'semantic_type': ('printed_unspecified_value' if measured['value'] in {'–', '—', '-'}
                              else 'printed_not_applicable' if measured['value'] in {'不適用', '不适用'} else 'financial_quantity')}
        result['facts'].append(fact)
        _atom(result, text, source, a, a + len(label), 'label')
        va, vb = measured['sources']['value']['text_span']
        _atom(result, text, source, va - _offset(source), vb - _offset(source), 'value')
        if measured['unit']:
            ua, ub = measured['sources']['unit']['text_span']
            _atom(result, text, source, ua - _offset(source), ub - _offset(source), 'unit')
        result['projection_inputs']['objects'].append({k: copy.deepcopy(fact[k]) for k in (
            'source', 'attribute', 'attribute_source', 'value', 'value_source', 'qualifiers', 'qualifier_sources')})
    for a, b in unread:
        _pending(result, 'labelled_record_field_unresolved', text[a:b], _source(source, a, b))
        _atom(result, text, source, a, b, 'unresolved_text')
    _project(result, text, source)
    return result


def _read_selection_record(text, source, *, scope=()):
    """Explicit person/position and two-level marked field records."""
    result = _result()
    parts = _parts(text)
    if len(parts) < 3 or not re.fullmatch(r'[\u3400-\u9fffA-Za-z .·]{2,80}', text[slice(*parts[0])]):
        return result
    position = _PAIR.fullmatch(text[slice(*parts[1])])
    if position is None or position[1] not in {'職位', '职位', '職務', '职务'} or not re.search(r'[√✓☑×✗☒]', text):
        return result
    name = text[slice(*parts[0])]
    name_source = _source(source, *parts[0])
    result.update(matched=True, record_label={'text': name, 'source': name_source}, scope={'subject': name, 'scope': list(scope)})
    result['projection_inputs']['source_fragments'] = [{'text': text, 'source': copy.deepcopy(source)}]
    _atom(result, text, source, *parts[0], 'locator')

    def field(label, label_source, a, b, *, domain=None, domain_source=None, nominal=False):
        raw = text[a:b]
        headers = ([{'role': 'column_group', 'text': domain, 'source': copy.deepcopy(domain_source)}] if domain else [])
        headers.append({'role': 'column_header', 'text': label, 'source': copy.deepcopy(label_source)})
        fact = {'id': f'labelled-record:{len(result["facts"])}', 'subject': name, 'subject_source': copy.deepcopy(name_source),
                'attribute': label, 'attribute_source': copy.deepcopy(label_source), 'value': raw, 'raw_value': raw,
                'role': 'metric', 'semantic_type': 'printed_position_list' if nominal else 'printed_selection_state',
                'source': _source(source, a, b), 'value_source': _source(source, a, b), 'qualifiers': {}, 'qualifier_sources': {},
                'identity_facets': {'field_domain': domain} if domain else {}, 'scope': list(scope),
                'row_evidence': [{'role': 'record_label', 'text': name, 'source': copy.deepcopy(name_source)}],
                'header_evidence': headers, 'record_id': 'selection-record:' + json.dumps(name_source, sort_keys=True),
                'rule_id': 'printed_position_and_hierarchical_selection_fields'}
        if nominal:
            from .cjk_circumstances import nominal as read_nominal
            from .cjk_narrative_requirements import _CJKReader
            from .narrative_requirements import _Unknown

            if not all(re.fullmatch(r'(?:副)?董事長|(?:獨立|独立)?(?:非)?[執执]行董事|董事|(?:高[級级])?副[總总]裁|[總总]裁|[董監监]事[會会]秘[書书]', item)
                       for item in re.split('、', raw)):
                _pending(result, 'position_list_roles_unresolved', raw, fact['value_source'])
                return
            reader = _CJKReader(raw, fact['value_source'], scope)
            try:
                logic = read_nominal(reader, 0, len(raw))
                reader.annotate_sources(logic)
            except _Unknown:
                _pending(result, 'position_list_roles_unresolved', raw, fact['value_source'])
                return
            fact['value_logic'] = logic
            members = [n for part in logic.get('parts', []) if part.get('kind') == 'coordination'
                       for n in part['children']]
            for member in members:
                result['relations'].append({'type': 'record_position_member', 'left': {'position': member['head']},
                    'right': {'subject': name, 'attribute': label, 'scope': list(scope), 'identity_facets': copy.deepcopy(fact['identity_facets'])}, 'fact_id': fact['id'],
                    'source': copy.deepcopy(member['source']), 'object_anchor': None,
                    'binding_evidence': {'statement_source': copy.deepcopy(fact['source']),
                                         'member_source': copy.deepcopy(member['source']), 'value_logic': copy.deepcopy(logic)},
                    'rule_id': 'printed_position_list_member'})
            result['record_composition'] = True
        result['facts'].append(fact)
        result['record_composition'] = True
        result['relations'].append({'type': 'record_label_scope', 'left': {'record_subject': name},
            'right': {'subject': name, 'attribute': label, 'scope': list(scope), 'identity_facets': copy.deepcopy(fact['identity_facets'])}, 'source': copy.deepcopy(name_source),
            'fact_id': fact['id'], 'object_anchor': None,
            'binding_evidence': {'statement_source': copy.deepcopy(fact['source']), 'row_label_source': copy.deepcopy(name_source),
                                 'headers': copy.deepcopy(headers)}, 'rule_id': 'printed_person_record_prefix'})
        result['projection_inputs']['objects'].append({k: copy.deepcopy(fact[k]) for k in (
            'source', 'attribute', 'attribute_source', 'value', 'value_source', 'qualifiers', 'qualifier_sources')})
        _atom(result, text, source, a, b, 'value')

    pa, pb = parts[1]
    la, lb = pa + position.start(1), pa + position.end(1)
    va, vb = pa + position.start(2), pa + position.end(2)
    _atom(result, text, source, la, lb, 'label')
    field(position[1], _source(source, la, lb), va, vb, nominal=True)
    for pa, pb in parts[2:]:
        pair = _PAIR.fullmatch(text[pa:pb].rstrip('。.'))
        if pair is None:
            _pending(result, 'selection_domain_unresolved', text[pa:pb], _source(source, pa, pb))
            continue
        da, db = pa + pair.start(1), pa + pair.end(1)
        _atom(result, text, source, da, db, 'label')
        for mark in re.finditer(r'[^，,]+', pair[2]):
            item = re.fullmatch(r'(?P<method>[^√✓☑×✗☒]+)(?P<state>[√✓☑×✗☒])', mark[0])
            base = pa + pair.start(2) + mark.start()
            if item is None:
                _pending(result, 'selection_method_or_state_unresolved', mark[0], _source(source, base, base + len(mark[0])))
                continue
            a, b = base + item.start('method'), base + item.end('method')
            _atom(result, text, source, a, b, 'label')
            field(item['method'], _source(source, a, b), b, b + 1, domain=pair[1], domain_source=_source(source, da, db))
    _project(result, text, source)
    return result


def read_field_sequence_requirements(text: str, source: dict[str, Any], *, scope=(), schema=None,
                                     subject="", subject_source=None, qualifiers=None, qualifier_sources=None,
                                     identity_facets=None, record_id=None) -> dict[str, Any]:
    result = _result()
    pieces = _parts(text)
    if len(pieces) < 2:
        return result
    first_start, first_end = pieces[0]
    first = text[first_start:first_end]
    typed = _PAIR.fullmatch(first)
    if typed and not _DECLARATION.fullmatch(typed[1]):
        return result
    attribute_start, attribute_end = ((first_start + typed.start(2), first_start + typed.end(2))
                                      if typed else (first_start, first_end))
    attribute_start, attribute_end = _trim(text, attribute_start, attribute_end)
    prefix = {"text": text[attribute_start:attribute_end], "source": _source(source, attribute_start, attribute_end)}
    declared_label = read_measurement_label(prefix["text"], prefix["source"])
    attribute = declared_label["label"] if declared_label["matched"] else prefix["text"]
    attribute_source = declared_label["sources"]["label"] if declared_label["matched"] else prefix["source"]
    declaration_ok = False
    if isinstance(schema, dict) and isinstance(schema.get("text"), str) and schema.get("source", {}).get("path"):
        declaration = _PAIR.fullmatch(schema["text"])
        declaration_ok = bool(declaration and _DECLARATION.fullmatch(declaration[1]) and declaration[2].strip() == attribute)
    role_proved = bool(attribute) and bool(typed or _ATTRIBUTE_ROLE.fullmatch(attribute) or declaration_ok)
    fields, unread = [], []
    for a, b in pieces[1:]:
        pair = _PAIR.fullmatch(text[a:b])
        if pair is None or not pair[2].strip():
            unread.append((a, b))
            continue
        la, lb = _trim(text, a + pair.start(1), a + pair.end(1))
        va, vb = _trim(text, a + pair.start(2), a + pair.end(2))
        fields.append({"label": text[la:lb], "value": text[va:vb], "label_span": [la, lb], "value_span": [va, vb],
                       "label_source": _source(source, la, lb), "value_source": _source(source, va, vb), "span": [a, b]})
    if not fields:
        return result
    result["matched"] = True
    result["scope"] = {"attribute": attribute, "scope": list(scope), "attribute_source": copy.deepcopy(attribute_source)}
    if declaration_ok:
        result["scope"]["attribute_declaration"] = copy.deepcopy(schema)
    result["projection_inputs"]["source_fragments"] = [{"text": text, "source": copy.deepcopy(source)}]
    if typed:
        result["controls"].append({"text": text[first_start:attribute_start], "span": [first_start, attribute_start],
            "source": _source(source, first_start, attribute_start), "reason": "printed_attribute_role_declaration"})
    if declared_label["matched"]:
        _proof_atom(result, text, source, declared_label["sources"]["label"], "label")
        _proof_atom(result, text, source, declared_label["sources"]["unit"], "unit")
    else:
        _atom(result, text, source, attribute_start, attribute_end, "label")
    if not role_proved or unread:
        for field in fields:
            _atom(result, text, source, *field["label_span"], "unresolved_label")
            _atom(result, text, source, *field["value_span"], "value")
        for a, b in unread:
            _atom(result, text, source, a, b, "unresolved_text")
        _pending(result, "field_sequence_prefix_role_unresolved" if not role_proved else "field_sequence_value_boundary_unresolved",
                 text, _source(source, 0, len(text)), prefix=copy.deepcopy(prefix), segments=copy.deepcopy(fields))
        _project(result, text, source)
        return result
    inherited, inherited_sources = copy.deepcopy(qualifiers or {}), copy.deepcopy(qualifier_sources or {})
    if declared_label["matched"]:
        for key in ("unit", "currency"):
            if declared_label[key]:
                inherited[key], inherited_sources[key] = declared_label[key], declared_label["sources"][key]
    for field in fields:
        label, label_source = field["label"], field["label_source"]
        field_label = read_measurement_label(label, label_source)
        core_label = field_label["label"] if field_label["matched"] else label
        core_label_source = field_label["sources"]["label"] if field_label["matched"] else label_source
        va, vb = field["value_span"]
        period = read_period_label(label, label_source)
        if not period["matched"] and _YEAR.fullmatch(core_label):
            period = {"matched": True, "qualifiers": {"period": core_label}, "qualifier_sources": {"period": core_label_source}}
            if field_label["matched"]:
                for key in ("unit", "currency"):
                    if field_label[key]:
                        period["qualifiers"][key] = field_label[key]
                        period["qualifier_sources"][key] = field_label["sources"][key]
        temporal = bool(period["matched"] or _TIME_CUE.search(label))
        change = bool(_CHANGE.fullmatch(core_label))
        q, qs = copy.deepcopy(inherited), copy.deepcopy(inherited_sources)
        own_subject, own_subject_source = subject, copy.deepcopy(subject_source)
        if temporal:
            if not period["matched"] or "period" not in period["qualifiers"]:
                _atom(result, text, source, *field["label_span"], "unresolved_period_selector")
                _atom(result, text, source, va, vb, "value")
                _pending(result, "field_sequence_period_selector_unresolved", text[slice(*field["span"])],
                         _source(source, *field["span"]), kind="period_selector", **{k: copy.deepcopy(field[k]) for k in
                             ("label", "value", "label_source", "value_source")})
                continue
            q.update(period["qualifiers"])
            qs.update(period["qualifier_sources"])
            for control in period.get("controls", []):
                a, b = control["source"]["text_span"]
                result["controls"].append({**copy.deepcopy(control), "span": [a - _offset(source), b - _offset(source)]})
            for key in ("period", "period_basis", "unit"):
                if key in period["qualifier_sources"]:
                    _proof_atom(result, text, source, period["qualifier_sources"][key], key)
        elif change:
            _proof_atom(result, text, source, core_label_source, "label")
            if field_label["matched"]:
                for key in ("unit", "currency"):
                    if field_label[key]:
                        q[key], qs[key] = field_label[key], field_label["sources"][key]
                _proof_atom(result, text, source, field_label["sources"]["unit"], "unit")
            if not all(key in q and key in qs and qs[key].get("path") for key in ("from_period", "to_period")):
                _atom(result, text, source, va, vb, "value")
                _pending(result, "field_sequence_comparison_periods_unresolved", text[slice(*field["span"])],
                         _source(source, *field["span"]), kind="comparison_period_binding", **{k: copy.deepcopy(field[k]) for k in
                             ("label", "value", "label_source", "value_source")})
                continue
        elif _METADATA.fullmatch(label):
            _atom(result, text, source, *field["label_span"], "label")
            _atom(result, text, source, va, vb, "value")
            _pending(result, "field_sequence_metadata_scope_unresolved", text[slice(*field["span"])],
                     _source(source, *field["span"]), kind="qualifier_scope", **{k: copy.deepcopy(field[k]) for k in
                         ("label", "value", "label_source", "value_source")})
            continue
        else:
            own_subject, own_subject_source = label, label_source
            _atom(result, text, source, *field["label_span"], "locator")
            result["projection_inputs"]["locators"].append({"text": label, "source": copy.deepcopy(label_source), "role": "record_label"})
        measured, raw_end = _measurement(text, source, va, vb)
        if measured["matched"]:
            value, value_source = measured["value"], measured["sources"]["value"]
            _proof_atom(result, text, source, value_source, "value")
            for key in ("unit", "currency"):
                if measured[key]:
                    q[key], qs[key] = measured[key], measured["sources"][key]
            if measured["unit"]:
                _proof_atom(result, text, source, measured["sources"]["unit"], "unit")
        else:
            value, value_source, raw_end = text[va:vb], _source(source, va, vb), vb
            _atom(result, text, source, va, vb, "value")
        own_attribute, own_attribute_source = (core_label, core_label_source) if change else (attribute, attribute_source)
        raw_source = _source(source, va, raw_end)
        missing_sources = [key for key in q if not isinstance(qs.get(key), dict) or not qs[key].get("path")]
        if missing_sources:
            _pending(result, "field_sequence_qualifier_source_unresolved", text[slice(*field["span"])],
                     _source(source, *field["span"]), kind="qualifier_source", qualifiers=copy.deepcopy(q),
                     missing_qualifier_sources=missing_sources)
        if own_subject and (not isinstance(own_subject_source, dict) or not own_subject_source.get("path")):
            _pending(result, "field_sequence_subject_source_unresolved", text[slice(*field["span"])],
                     _source(source, *field["span"]), kind="subject_source", subject=own_subject)
        record_source = own_subject_source or prefix["source"]
        record_locator = {key: record_source[key] for key in ("path", "lines", "block", "cell", "native_path", "row", "col", "text_span")
                          if key in record_source}
        own_record = record_id or "field-sequence-record:" + json.dumps(record_locator, sort_keys=True, ensure_ascii=False)
        rows = [{"text": own_subject, "source": copy.deepcopy(own_subject_source), "role": "record_label"}] if own_subject_source else []
        headers = [{"text": own_attribute, "source": copy.deepcopy(own_attribute_source), "role": "attribute_declaration"}]
        fact = {"id": f"field-sequence:{len(result['facts'])}", "subject": own_subject, "attribute": own_attribute,
                "value": value, "role": "metric", "qualifiers": q, "qualifier_sources": copy.deepcopy(qs),
                "identity_facets": copy.deepcopy(identity_facets or {}), "scope": list(scope), "record_id": own_record,
                "attribute_source": copy.deepcopy(own_attribute_source), "value_source": copy.deepcopy(value_source),
                "source": {**raw_source, "attribute_source": copy.deepcopy(own_attribute_source), "qualifier_sources": copy.deepcopy(qs)},
                "raw_value": text[va:raw_end], "row_evidence": rows, "header_evidence": headers,
                "rule_id": "printed_attribute_and_independent_field_sequence"}
        if own_subject_source:
            fact["subject_source"] = copy.deepcopy(own_subject_source)
        result["facts"].append(fact)
        endpoint = {key: copy.deepcopy(fact[key]) for key in ("subject", "attribute", "qualifiers", "identity_facets", "scope")}
        result["relations"].append({"type": "field_binding", "left": {"subject": own_subject, "attribute": own_attribute},
                                    "right": endpoint, "source": copy.deepcopy(raw_source),
                                    "binding_evidence": {"rows": copy.deepcopy(rows), "headers": copy.deepcopy(headers)}})
        result["relations"].extend({"type": "qualifier_scope", "left": {"type": key, "text": item},
                                    "right": copy.deepcopy(endpoint), "source": copy.deepcopy(qs[key])}
                                   for key, item in q.items() if key not in missing_sources)
        result["projection_inputs"]["objects"].append({"source": copy.deepcopy(raw_source), "attribute": own_attribute,
            "attribute_source": copy.deepcopy(own_attribute_source), "value": value, "value_source": copy.deepcopy(value_source),
            "qualifiers": copy.deepcopy(q), "qualifier_sources": copy.deepcopy(qs), "row_sources": copy.deepcopy(rows)})
    _project(result, text, source)
    return result
