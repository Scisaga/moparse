"""Inventory input JSON before consulting any adapted/consumer objects."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from app.adapters.native_readers import (
    NativeReadError,
    code_ranges,
    html_cells,
    markdown_cells,
    resolve_pointer,
)
from app.models.native_content import NativeArtifact, NativeContentItem, NativeLocator


def encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _regions(raw, pointer):
    """Independent input walk, with no adapter-result or observation text input."""
    value = raw.get('json_result')
    path = pointer + '/json_result'
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
        path += '::decoded'
    if isinstance(value, Mapping):
        key = next((k for k in ('pages', 'results', 'layout_details') if k in value), None)
        if key is None:
            return []
        value, path = value[key], path + '/' + key
    if not isinstance(value, list):
        return []
    local = None
    if any(isinstance(x, list) for x in value):
        if len(value) != 1 or not isinstance(value[0], list):
            return []
        value, path, local = value[0], path + '/0', 0
    elif len(value) == 1 and isinstance(value[0], Mapping) and 'regions' in value[0]:
        local = value[0].get('page_no', value[0].get('page_index'))
        value, path = value[0]['regions'], path + '/0/regions'
    return [(f'{path}/{i}', item, local) for i, item in enumerate(value)] if isinstance(value, list) else []


def _inline_media(text):
    # Syntax scanning only; targets are never opened, decoded or interpreted.
    protected = code_ranges(text)
    matches = []
    for pattern in (r'!\[[^\]\n]*\]\([^()\s]+(?:\s+"[^"\n]*")?\)', r'<img\b[^>]*>'):
        for match in re.finditer(pattern, text, re.I):
            if not any(a <= match.start() < b for a, b in protected):
                matches.append(tuple(match.span()))
    return sorted(set(matches))


def inventory_native(artifact: NativeArtifact, selected: tuple[int, ...],
                     original_pages: tuple[int, ...] | None):
    root = artifact.read()
    items = []
    bindings = []
    seen_containers = set()
    emitted_unknown_multipage = set()

    def add(kind, path, page, branch, local, *, identity=None, parent=None, text=None,
            spans=(), order=(), basis='unknown', details=None, view=None):
        original = original_pages[page - 1] if original_pages and page is not None and not (branch == 'docling' and local is None) else None
        item = NativeContentItem(identity or path, kind,
            NativeLocator(artifact.sha256, view or ('document' if branch == 'docling' else 'json_result'),
                          path, tuple(tuple(s) for s in spans)), page, branch, local, original,
            parent, tuple(order), basis, text, encoded(details or {}))
        items.append(item)
        return item

    for position, entry in enumerate(root.get('pages', [])):
        if not isinstance(entry, Mapping) or type(entry.get('page')) is not int or entry['page'] not in selected:
            continue
        page, branch, raw = entry['page'], entry.get('branch'), entry.get('raw')
        entry_path = f'#/pages/{position}'
        bindings.append({'input_page': page, 'branch': branch, 'entry': entry_path,
                         'original_page': original_pages[page - 1] if original_pages else None,
                         'raw_identity': raw.get('native_document') if isinstance(raw, Mapping) else None,
                         'branch_page': raw.get('source_page') if isinstance(raw, Mapping) and branch == 'docling' else None})
        if not isinstance(raw, Mapping):
            continue
        if branch == 'mineru':
            from app.adapters.mineru_inventory import inventory_mineru
            binding = inventory_mineru(root, entry, position, add)
            if binding:
                bindings[-1].update(binding)
            continue
        if branch == 'paddle':
            # Independent input walk: never consult read_paddle or adapted blocks.
            payload = raw.get('res', raw)
            if not isinstance(payload, Mapping):
                continue
            base = entry_path + '/raw' + ('/res' if 'res' in raw else '')
            view = 'res.parsing_res_list' if 'res' in raw else 'parsing_res_list'
            local_value = payload.get('page_index')
            local = local_value if type(local_value) is int and local_value >= 0 else None
            bindings[-1].update(branch_page=local, native_page_index=local_value,
                                page_index_present='page_index' in payload, page_count=payload.get('page_count'),
                                source_view=view, dimensions_path=base)
            regions = payload.get('parsing_res_list', [])
            if not isinstance(regions, list):
                regions = []
            for index, node in enumerate(regions):
                path = f'{base}/parsing_res_list/{index}'
                record = node if isinstance(node, Mapping) else {}
                content = record.get('block_content')
                text = content if isinstance(content, str) else ''
                label = str(record.get('block_label', 'unknown'))
                kind = 'table' if label == 'table' else 'picture' if label in {'image', 'picture', 'chart', 'header_image', 'footer_image'} else 'content'
                add(kind, path, page, branch, local, text=text, order=(page, index),
                    basis='native_array_order_unknown_reading_order', view=view,
                    details={'label': label, 'array_position': index, 'native_block_id': record.get('block_id'),
                             'native_block_order': record.get('block_order'), 'native_group_id': record.get('group_id'),
                             'group_membership_semantics': 'unknown_no_parent_chain',
                             'native_bbox': record.get('block_bbox'),
                             'native_polygons': {k: record[k] for k in ('block_polygon_points', 'block_polygon', 'polygon') if k in record},
                             'page_dimensions': {k: payload.get(k) for k in ('width', 'height')},
                             'field_presence': {k: k in record for k in ('block_id', 'block_order', 'group_id', 'block_polygon_points')}})
                cells = []
                try:
                    cells = html_cells(text, path + '/block_content') if re.search(r'<table\b', text, re.I) else markdown_cells(text, path + '/block_content')
                except (NativeReadError, ValueError):
                    pass
                for cell in cells:
                    add('cell', cell['id'], page, branch, local, identity=cell['id'], parent=path,
                        text=cell['text'], view=view, details={'source_cell': cell, 'source_table': path,
                            'origin': 'primary_html_projection' if '::html/' in cell['id'] else 'primary_gfm_projection',
                            'native_independent_ocr_cell': False})
                if kind == 'picture':
                    add('media', path, page, branch, local, identity=path + ':media', parent=path, view=view,
                        details={'appearance': 'native_picture', 'delivery': 'not_read_not_verified_not_delivered'})
                elif not re.search(r'<table\b', text, re.I):
                    for start, end in _inline_media(text):
                        add('media', path, page, branch, local, identity=f'{path}:media:{start}:{end}', parent=path,
                            view=view, spans=((start, end),), details={'appearance': 'inline_reference', 'delivery': 'not_read_not_verified_not_delivered'})
            # Page fields, exported views and detection-only observations remain
            # auditable. A detector region is not a second OCR answer or parent.
            for name in payload:
                if name not in {'parsing_res_list', 'layout_det_res'}:
                    add('metadata', base + '/' + name, page, branch, local, view=view,
                        details={'purpose': 'paddle_page_metadata', 'field': name})
            layout = payload.get('layout_det_res')
            if isinstance(layout, Mapping):
                boxes = layout.get('boxes', [])
                for i, _ in enumerate(boxes if isinstance(boxes, list) else []):
                    add('metadata', base + f'/layout_det_res/boxes/{i}', page, branch, local, view=view,
                        details={'purpose': 'layout_detection_only_not_ocr_answer', 'relation_to_primary': 'not_inferred_from_geometry'})
            for name in raw if 'res' in raw else []:
                if name != 'res':
                    add('metadata', entry_path + '/raw/' + name, page, branch, local, view=view,
                        details={'purpose': 'saved_native_audit_view', 'used_as_answer': False, 'field': name})
            if 'faithful_markdown' in entry:
                add('metadata', entry_path + '/faithful_markdown', page, branch, local, view=view,
                    details={'purpose': 'saved_faithful_export_audit_only', 'used_as_answer': False})
        elif branch == 'docling':
            pointer = raw.get('native_document')
            envelope = resolve_pointer(root, pointer)
            if not isinstance(pointer, str) or not isinstance(envelope, Mapping):
                continue
            document = envelope.get('document', envelope)
            if not isinstance(document, Mapping):
                continue
            base = pointer + '/document' if 'document' in envelope else pointer
            local = raw.get('source_page', page)
            ordered: list[str] = []
            visiting: set[str] = set()

            def visit(ref, *, visiting=visiting, document=document, ordered=ordered, base=base):
                if not isinstance(ref, str) or ref in visiting:
                    return
                visiting.add(ref)
                node = resolve_pointer(document, ref)
                if not isinstance(node, Mapping):
                    return
                ordered.append(base + ref[1:])
                for field in ('children', 'captions', 'footnotes', 'references'):
                    for child in node.get(field, []) if isinstance(node.get(field, []), list) else []:
                        if isinstance(child, Mapping):
                            visit(child.get('$ref', child.get('cref')))

            for tree in ('body', 'furniture'):
                visit('#/' + tree)
            container_nodes = [(base + '/' + t, document[t]) for t in ('body', 'furniture') if isinstance(document.get(t), Mapping)]
            container_nodes += [(f'{base}/groups/{i}', x) for i, x in enumerate(document.get('groups', [])) if isinstance(x, Mapping)]
            for path, node in container_nodes:
                if path in seen_containers:
                    continue
                seen_containers.add(path)
                add('container', path, None, branch, None,
                    parent=base + node['parent']['$ref'][1:] if isinstance(node.get('parent'), Mapping) and isinstance(node['parent'].get('$ref'), str) else None,
                    details={'in_reading_tree': path in ordered, 'native_fields': sorted(node)})
            for family in ('texts', 'tables', 'pictures'):
                for index, node in enumerate(document.get(family, [])):
                    if not isinstance(node, Mapping):
                        continue
                    path = f'{base}/{family}/{index}'
                    prov = node.get('prov', [])
                    valid_prov = isinstance(prov, list) and all(isinstance(p, Mapping) and type(p.get('page_no')) is int for p in prov)
                    own = [p for p in prov if p.get('page_no') == local] if valid_prov else []
                    if not own and valid_prov and prov:
                        continue
                    first_owner = min((p['page'] for p in root.get('pages', [])
                                       if isinstance(p, Mapping) and p.get('branch') == 'docling'
                                       and isinstance(p.get('raw'), Mapping) and p['raw'].get('native_document') == pointer
                                       and p.get('page') in selected), default=page)
                    if not own and page != first_owner:
                        continue
                    literal = node.get('text')
                    text = literal if isinstance(literal, str) else ''
                    spans = []
                    identity = path
                    if valid_prov and len({p['page_no'] for p in prov}) > 1 and text:
                        all_spans = [p.get('charspan') for p in prov]
                        good = all(isinstance(s, (list, tuple)) and len(s) == 2 and all(type(i) is int for i in s)
                                   and 0 <= s[0] < s[1] <= len(text) for s in all_spans)
                        ordered_spans = sorted(all_spans) if good else []
                        good = bool(ordered_spans) and ordered_spans[0][0] == 0 and ordered_spans[-1][1] == len(text) and all(
                            a[1] == b[0] for a, b in zip(ordered_spans, ordered_spans[1:], strict=False))
                        if good:
                            spans = [p['charspan'] for p in own]
                            text = ''.join(text[a:b] for a, b in spans)
                            identity += f'@page={page}'
                        elif path in emitted_unknown_multipage:
                            continue
                        else:
                            emitted_unknown_multipage.add(path)
                    parent = node.get('parent', {})
                    parent = base + parent['$ref'][1:] if isinstance(parent, Mapping) and isinstance(parent.get('$ref'), str) else None
                    ordinal = ordered.index(path) if path in ordered else index
                    role = str(node.get('label', 'unknown'))
                    kind = 'table' if family == 'tables' else 'picture' if family == 'pictures' else 'content'
                    add(kind, path, page, branch, local if valid_prov and prov else None, identity=identity, parent=parent, text=text, spans=spans,
                        order=(page, ordinal), basis='native_reading_tree' if path in ordered else 'unknown',
                        details={'label': role, 'family': family, 'native_provenance': prov,
                                 'native_children': node.get('children', []),
                                 'native_references': {k: node.get(k, []) for k in ('captions', 'footnotes', 'references')},
                                 'native_text': node.get('text'), 'native_original_text': node.get('orig')})
                    if kind == 'picture':
                        add('media', path, page, branch, local, identity=identity + ':media', parent=identity,
                            details={'appearance': 'native_picture', 'delivery': 'not_read_not_verified_not_delivered'})
                    if kind == 'table':
                        data = node.get('data')
                        raw_cells = data.get('table_cells', []) if isinstance(data, Mapping) else []
                        for ci, cell in enumerate(raw_cells if isinstance(raw_cells, list) else []):
                            cellpath = path + f'/data/table_cells/{ci}'
                            add('cell', cellpath, page, branch, local, parent=identity,
                                text=cell.get('text') if isinstance(cell, Mapping) and isinstance(cell.get('text'), str) else None,
                                details={'source_cell': cell, 'source_table': path})
        elif branch == 'glm':
            regions = _regions(raw, entry_path + '/raw')
            indexes = [x.get('index') for _, x, _ in regions if isinstance(x, Mapping)]
            indexed = bool(indexes) and len(indexes) == len(regions) and all(type(i) is int and i >= 0 for i in indexes) and len(set(indexes)) == len(indexes)
            for ordinal, (path, node, local) in enumerate(regions):
                node_map = node if isinstance(node, Mapping) else {}
                content = node_map.get('content')
                text = content if isinstance(content, str) else ''
                label = str(node_map.get('native_label') or node_map.get('label') or 'unknown').casefold()
                kind = 'table' if label == 'table' else 'picture' if label in {'image', 'picture', 'chart', 'header_image', 'footer_image'} else 'content'
                add(kind, path, page, branch, local, text=text,
                    order=(page, node_map['index'] if indexed else ordinal),
                    basis='native_index' if indexed else 'native_array_order_unknown_reading_order',
                    details={'label': label, 'array_position': ordinal, 'index': node_map.get('index'),
                             'native_label': node_map.get('native_label'), 'projection_label': node_map.get('label')})
                cells = []
                try:
                    cells = html_cells(text, path + '/content') if re.search(r'<table\b', text, re.I) else markdown_cells(text, path + '/content')
                except (NativeReadError, ValueError):
                    pass
                for cell in cells:
                    add('cell', cell['id'], page, branch, local, identity=cell['id'], parent=path,
                        text=cell['text'], details={'source_cell': cell, 'source_table': path})
                if kind == 'picture':
                    add('media', path, page, branch, local, identity=path + ':media', parent=path,
                        details={'appearance': 'native_picture', 'delivery': 'not_read_not_verified_not_delivered'})
                elif not re.search(r'<table\b', text, re.I):
                    for start, end in _inline_media(text):
                        add('media', path, page, branch, local, identity=f'{path}:media:{start}:{end}', parent=path,
                            spans=((start, end),), details={'appearance': 'inline_reference', 'delivery': 'not_read_not_verified_not_delivered'})
            for name in ('original_images', 'image_files'):
                if name in raw:
                    add('metadata', entry_path + '/raw/' + name, page, branch, None,
                        details={'purpose': 'input_page_media' if name == 'original_images' else 'media_catalogue',
                                 'read': False, 'decoded': False, 'declared_keys': list(raw[name]) if isinstance(raw[name], Mapping) else None})
    return tuple(items), bindings
