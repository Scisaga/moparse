"""Candidate-only lexical grid bindings, without entity-role interpretation.

An explicitly declared column header and a printed row label can expose a
numeric or single-email cell's syntax even when the business reader cannot
name its record class. Prose-only grids produce no fields. No reference is
accepted.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict

from .enumeration_context import grid_record_axis
from .quantity import exact_number, normalize_unit


def email_token(text):
    """One printed email token, with an optional sentence delimiter."""
    match = re.fullmatch(r"([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)[。.;；]?", text.strip())
    return match[1] if match else None


def identifier_label(text):
    return re.fullmatch(r'电话(?:号码)?|联系电话|手機(?:號碼)?|手机(?:号码)?|传真(?:号码)?|傳真(?:號碼)?|邮编|郵編|邮政编码|账号|帐号|賬號|账户号码'
                        r'|代码|代碼|编号|編號|股票代码|证券代码|债券代码|版本|(?:stock\s+|security\s+|bond\s+)?code|identifier|version'
                        r'|(?:phone|telephone|mobile|fax)(?:\s+(?:number|no\.?))?|zip(?:\s+code)?|postal\s+code|account\s+(?:number|no\.?)|e-?mail|电子信箱|電子信箱|邮箱|郵箱', text.strip(), re.I) is not None


def table_source_owns(table, cell):
    """Authenticate physical ownership without conflating two source tables."""
    if table.get('block') is not None and cell.get('block') is not None:
        if table['block'] != cell['block']:
            return False
    elif table.get('path') != cell.get('path'):
        return False
    for key in ('block_lines', 'lines'):
        if table.get(key) and cell.get(key) and not (table[key][0] <= cell[key][0] <= cell[key][-1] <= table[key][-1]):
            return False
    return True


def syntax_grid_fields(evidence):
    native_tables = [u for u in evidence.get('syntax', []) if u.get('kind') == 'table']
    tables = defaultdict(list)
    for cell in evidence.get('text_projection', {}).get('source_cells', []):
        owners = [i for i, unit in enumerate(native_tables) if table_source_owns(unit['source'], cell['source'])]
        if len(owners) == 1:
            tables[owners[0]].append(cell)
    existing = defaultdict(list)
    for fact in evidence.get('business', []):
        origin = fact.get('value_source', {}).get('cell') or fact.get('source', {}).get('cell')
        if origin:
            existing[origin].append(fact)
    produced = set()
    units, scopes = {}, {}
    previous, table_index = None, -1
    for unit in evidence.get('syntax', []):
        if unit.get('kind') == 'table':
            table_index += 1
            block = table_index
            scopes[block] = unit.get('scope', [])
            if previous and (previous.get('kind') in {'text', 'item', 'table_caption'}
                             or previous.get('semantic_role') == 'qualifier_declaration'):
                raw = previous.get('text', '').strip()
                own = re.fullmatch(r'(?:[（(]?(?:金额单位|金額單位|单位|單位)\s*[:：为為]?\s*)?([^()（）:：]+)[）)]?', raw)
                if own and normalize_unit(own[1])['matched']:
                    units[block] = (own[1], previous['source'])
        previous = unit
    result = []
    for block, cells in tables.items():
        headers = [c for c in cells if 'column_header' in c.get('roles', []) or c.get('native_declarations', {}).get('is_column_header') is True]
        if not headers:
            continue
        header_end = max(c['source'].get('row', 0) + c.get('row_span', 1) for c in headers)
        by_row = defaultdict(list)
        for cell in cells:
            if cell not in headers and cell['source'].get('row', 0) >= header_end:
                by_row[cell['source']['row']].append(cell)
        for row, own in by_row.items():
            own.sort(key=lambda c: c['source']['col'])
            if len(own) < 2 or not own[0]['text'].strip():
                continue
            raw_label = own[0]['text'].strip()
            row_headers = [h for h in headers if h['source']['col'] == own[0]['source']['col'] and h.get('col_span', 1) == 1]
            label = raw_label
            row_unit = None
            row_match = re.fullmatch(r'(.*?)\s*[(（]([^()（）]+)[)）]', label)
            label_is_entity = any(f.get('role') == 'identity' for f in existing.get(own[0]['source'].get('cell'), []))
            if not label_is_entity and row_match and normalize_unit(row_match[2])['matched']:
                label, row_unit = row_match[1].strip(), (row_match[2], own[0]['source'])
            for cell in own[1:]:
                source = cell['source']
                semantic = existing.get(source.get('cell'), [])
                if source.get('cell') in produced or len(semantic) > 1:
                    continue
                raw = cell['text'].strip()
                suffix = re.fullmatch(r'(.+?)\s*(%|‰|百万元|百萬元|万元|萬元|亿元|億元|元|股|人)', raw)
                value, suffix_unit = (suffix[1], suffix[2]) if suffix and exact_number(suffix[1]) is not None else (raw, None)
                email = email_token(raw)
                path = [h for h in headers if h['source']['col'] <= source['col'] < h['source']['col'] + h.get('col_span', 1)]
                references = str(cell.get('native_declarations', {}).get('native_attributes', {}).get('headers', '')).split()
                if references:
                    path = [h for h in headers if h.get('native_declarations', {}).get('native_attributes', {}).get('id') in references
                            or h['source'].get('cell') in references]
                    leaves = list(path)
                    path.extend(h for h in headers if h not in path and any(
                        h['source']['row'] < leaf['source']['row'] and h['source']['col'] <= leaf['source']['col']
                        and leaf['source']['col'] + leaf.get('col_span', 1) <= h['source']['col'] + h.get('col_span', 1)
                        for leaf in leaves))
                path.sort(key=lambda h: (h['source']['row'], h['source']['col']))
                if not path:
                    continue
                names, unit_evidence, header_currency = [], units.get(block), None
                explicit_header_unit = False
                for header in path:
                    name = header['text'].strip()
                    whole_unit = normalize_unit(name)
                    if whole_unit['matched']:
                        header_currency = whole_unit.get('currency') or header_currency
                        unit_evidence = (name, header['source'])
                        explicit_header_unit = True
                        continue
                    match = re.fullmatch(r'(.*?)\s*[(（]([^()（）]+)[)）]', name)
                    if match and normalize_unit(match[2])['matched']:
                        name = match[1].strip()
                        unit_evidence = (match[2], header['source'])
                        header_currency = normalize_unit(match[2]).get('currency') or header_currency
                        explicit_header_unit = True
                    if name and name not in names:
                        names.append(name)
                if not names and not unit_evidence:
                    continue
                identifier = any(identifier_label(v) for v in [label, *names])
                if identifier:
                    value, suffix_unit = raw, None
                if exact_number(value) is None and email is None and not identifier:
                    continue
                qualifiers = copy.deepcopy(semantic[0].get('qualifiers', {})) if semantic else {}
                if identifier:
                    qualifiers.pop('unit', None)
                    qualifiers.pop('currency', None)
                elif email is None:
                    if suffix_unit or row_unit or explicit_header_unit:
                        qualifiers['unit'] = suffix_unit or (row_unit or unit_evidence)[0]
                    elif 'unit' not in qualifiers and unit_evidence:
                        qualifiers['unit'] = unit_evidence[0]
                    printed_unit = normalize_unit(qualifiers.get('unit'))
                    if printed_unit.get('currency'):
                        qualifiers['currency'] = printed_unit['currency']
                    elif explicit_header_unit and header_currency and printed_unit['dimension'] == 'money':
                        qualifiers['currency'] = header_currency
                    final_unit = normalize_unit(qualifiers.get('unit'), qualifiers.get('currency'))
                    if final_unit['dimension'] == 'money' and not qualifiers.get('currency'):
                        if final_unit.get('currency') or header_currency:
                            qualifiers['currency'] = final_unit.get('currency') or header_currency
                strong = bool(semantic and (semantic[0].get('subject') or semantic[0].get('row_evidence')))
                subject = semantic[0].get('subject', '') if strong else label
                attribute = semantic[0].get('attribute', '') if strong else ' / '.join(names)
                if row_unit and subject == raw_label:
                    subject = label
                axis = grid_record_axis(row_headers[0], own[0], attribute) if len(row_headers) == 1 else None
                result.append({**(copy.deepcopy(semantic[0]) if semantic else {}),
                               **({'record_axis': copy.deepcopy(axis)} if axis else {}),
                               'id': 'grid-field:' + str(len(result)), 'kind': 'fact',
                               'role': semantic[0].get('role', 'metric') if semantic else 'metric',
                               'subject': subject, 'attribute': attribute, 'value': value,
                               'raw_value': raw, 'qualifiers': qualifiers, 'scope': semantic[0].get('scope', []) if semantic else scopes.get(block, []),
                               'source': copy.deepcopy(source), 'value_source': copy.deepcopy(source),
                               'header_evidence': copy.deepcopy(path), 'row_evidence': copy.deepcopy(semantic[0].get('row_evidence', [])) if strong else [copy.deepcopy(own[0])],
                               'unit_evidence': copy.deepcopy(unit_evidence),
                               'native_semantic_view': copy.deepcopy(semantic[0]) if semantic else None,
                               'field_interpretation': 'explicit_printed_grid_bindings_only',
                               'semantic_entity_class_inferred': False, 'native_row': row})
                produced.add(source.get('cell'))
    return result
