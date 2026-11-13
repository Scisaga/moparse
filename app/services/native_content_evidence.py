"""Evidence admission and reverse coverage for the private saved-content handoff.

No source, media, evaluator, reference answer or parser is imported here. The
inventory is re-derived from immutable received JSON, independently of blocks.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from app.adapters.native_config import CONFIGURATIONS
from app.adapters.native_inventory import encoded, inventory_native
from app.adapters.native_readers import audit_copy, html_cells, markdown_cells, resolve_pointer
from app.models.native_content import NativeArtifact, NativeContentContract, NativeExecutionState


class NativeContentError(ValueError):
    """An engineering handoff error, never an upstream partial-content waiver."""


def _require(condition, reason):
    if not condition:
        raise NativeContentError(reason)


def _execution(native, observation, identity, payload):
    from app.adapters.mineru_native import execution_states
    from app.adapters.paddle_native import paddle_execution_states
    entries = native.get('pages', [])
    native_states = [state for index, page in enumerate(entries if isinstance(entries, list) else [])
                     if isinstance(page, Mapping) and page.get('branch') == 'paddle' and isinstance(page.get('raw'), Mapping)
                     for state in ({**s, 'input_pages': [page.get('page')]} for s in
                                   paddle_execution_states(page['raw'], f'#/pages/{index}/raw'))]
    native_states.extend(execution_states(native))
    from app.adapters.visual_native import visual_execution_states
    native_states.extend(visual_execution_states(native))
    state_keys = ('status', 'errors', 'warnings', 'timed_out', 'truncated', 'stop_reason',
                  'unprocessed_pages', 'processed', 'length_limit_reached', 'possible_length_truncation')
    documents: dict[str, list[Any]] = {}
    for index, page in enumerate(entries if isinstance(entries, list) else []):
        if not isinstance(page, Mapping) or not isinstance(page.get('raw'), Mapping):
            continue
        raw = page['raw']
        if page.get('branch') == 'docling' and isinstance(raw.get('native_document'), str):
            documents.setdefault(raw['native_document'], []).append(page.get('page'))
        elif page.get('branch') == 'glm':
            metadata = {k: audit_copy(raw[k]) for k in state_keys if k in raw}
            if metadata:
                native_states.append({'native_path': f'#/pages/{index}/raw', 'input_pages': [page.get('page')],
                                      'scope': 'native_image_call', 'metadata': metadata})
    for path, pages in documents.items():
        envelope = resolve_pointer(native, path)
        if isinstance(envelope, Mapping):
            metadata = {k: audit_copy(envelope[k]) for k in state_keys if k in envelope}
            if metadata:
                native_states.append({'native_path': path, 'input_pages': pages,
                                      'scope': 'native_document', 'metadata': metadata})
    if observation is None:
        _require(payload is None, 'observation bytes require paired metadata')
        return NativeExecutionState(None, None, encoded({'status': 'unknown', 'pages': [],
            'reason': 'original_execution_metadata_missing', **({'native_status_evidence': native_states} if native_states else {})}))
    _require(isinstance(observation, dict), 'execution metadata must be an object')
    if payload is not None:
        _require(json.loads(payload) == observation, 'observation bytes disagree with metadata')
    else:
        payload = json.dumps(observation, ensure_ascii=False, sort_keys=True).encode()
        identity = identity or 'in_memory_execution_metadata'
    _require(observation.get('pipeline') == native.get('pipeline'), 'original execution pipeline conflict')
    if native.get('sample_id') is not None:
        _require(observation.get('sample_id') == native['sample_id'], 'original execution sample conflict')
    # An explicit allowlist: observations must never supply text or relations.
    keys = ('pipeline', 'sample_id', 'run_id', 'status', 'errors', 'warnings', 'timed_out',
            'truncated', 'processed_pages', 'unprocessed_pages', 'stop_reason')
    metadata = {k: audit_copy(observation[k]) for k in keys if k in observation}
    metadata.setdefault('status', 'unknown')
    page_keys = ('page', 'page_number', 'status', 'branch', 'errors', 'warnings',
                 'timed_out', 'truncated', 'stop_reason', 'processed')
    metadata['pages'] = [{k: audit_copy(p[k]) for k in page_keys if k in p}
                         for p in observation.get('pages', []) if isinstance(p, Mapping)]
    if native_states:
        metadata['native_status_evidence'] = native_states
    return NativeExecutionState(identity, hashlib.sha256(payload).hexdigest(), encoded(metadata))


def bind_native_content(result, native, *, selected_pages, source_pages=None, artifact=None,
                        original_observation=None, observation_identity=None, observation_bytes=None):
    artifact = artifact or NativeArtifact.from_object(native)
    _require(isinstance(artifact, NativeArtifact) and artifact.read() == native,
             'received native bytes disagree with decoded input')
    _require(native.get('sample_id') in {None, result.document_id}, 'native sample identity conflict')
    if isinstance(original_observation, Mapping) and 'sample_id' in original_observation:
        _require(original_observation['sample_id'] == result.document_id, 'paired execution sample identity conflict')
    original = tuple(source_pages) if source_pages is not None else None
    _require(original is None or len(original) == result.page_count and
             all(type(n) is int and n > 0 for n in original) and len(set(original)) == len(original),
             'original-page mapping must uniquely cover input pages')
    _require(selected_pages and len(set(selected_pages)) == len(selected_pages) and
             all(type(n) is int and 1 <= n <= result.page_count for n in selected_pages),
             'selected input-page mapping is invalid')
    items, bindings = inventory_native(artifact, selected_pages, original)
    contract = NativeContentContract(artifact, native['pipeline'], result.pipeline.primary,
        tuple(selected_pages), original, items,
        _execution(native, original_observation, observation_identity, observation_bytes), encoded(bindings))
    result._native_content = contract
    objects = {(i.input_page, i.identity): i for i in items if i.kind in {'content', 'table', 'picture'}}
    for number, blocks in result._native_page_blocks.items():
        for block in blocks:
            item = objects.get((number, block.get('occurrence_id', block.get('id'))))
            if item is not None:
                block['source_locator'] = asdict(item.locator)
                block['original_pdf_page'] = item.original_page
            for component in block.get('source_components', []):
                own = next((i for i in items if i.parent == block.get('id')
                            and i.input_page == number and i.locator.path == component['native_path']
                            and i.details.get('purpose') == 'native_visual_text_component'), None)
                if own:
                    component['source_locator'] = asdict(own.locator)
            for cell in block.get('cells', []):
                own = next((i for i in items if i.kind == 'cell' and i.input_page == number
                            and i.identity == cell.get('id') and i.parent == block.get('occurrence_id', block.get('id'))), None)
                if own:
                    cell['evidence_locator'] = asdict(own.locator)
    for fragment in result._table_fragments:
        block = next((b for b in result._native_page_blocks.get(fragment.page_number, [])
                      if b.get('service_fragment_id') == fragment.fragment_id), None)
        if block:
            fragment.native_evidence['source_binding'] = copy.deepcopy(block.get('source_locator'))
            fragment.native_evidence['source_cells'] = copy.deepcopy(block.get('cells', []))
    for page in result._source_verification['saved_native_bridge']['pages']:
        for receipt in page.get('native_audit_objects', []):
            own = next((i for i in items if i.locator.path == receipt['native_path']
                        and i.details.get('requires_audit_receipt')), None)
            if own:
                receipt['source_locator'] = asdict(own.locator)
    media = copy.deepcopy(result._source_verification['saved_native_bridge'].get('asset_references', []))
    result._source_verification['native_content'] = {
        'original_execution': contract.execution.metadata,
        'readback': {'status': 'partial' if any(
            p.get('error') or any(b.get('read_error') for b in result._native_page_blocks.get(p['raw_page'], []))
            for p in result._source_verification['saved_native_bridge']['pages']) else 'read'},
        'conversion': {'status': 'not_started'},
        'delivery': {'status': 'not_started'},
        'media': media,
    }
    validate_native_content(result)


def _expected_cell(item):
    raw = item.details['source_cell']
    if item.branch == 'docling':
        raw = raw if isinstance(raw, Mapping) else {}
        return {'id': item.identity, 'native_path': item.locator.path, 'text': raw.get('text', ''),
            'row': raw.get('start_row_offset_idx'), 'col': raw.get('start_col_offset_idx'),
            'row_span': raw.get('row_span'), 'col_span': raw.get('col_span'),
            'is_column_header': raw.get('column_header'), 'is_row_header': raw.get('row_header')}
    return {k: raw.get(k) for k in ('id', 'native_path', 'text', 'row', 'col', 'row_span', 'col_span',
                                    'is_column_header', 'is_row_header')}


def _cell_matches(item, cell):
    expected = _expected_cell(item)
    _require(all(cell.get(k) == v for k, v in expected.items()), 'native source cell content/position/role conflict: ' + item.identity)
    _require(cell.get('evidence_locator') == asdict(item.locator), 'source cell is not rooted in received artifact: ' + item.identity)
    raw = item.details['source_cell']
    if item.branch == 'docling' and isinstance(raw, Mapping):
        fields = ('start_row_offset_idx', 'end_row_offset_idx', 'start_col_offset_idx', 'end_col_offset_idx',
                  'column_header', 'row_header', 'row_section', 'fillable')
        _require(all((k in raw) == (k in cell) and cell.get(k) == raw.get(k) for k in fields),
                 'native cell offsets/role/missing-field evidence changed')
    if item.branch == 'docling' and isinstance(raw, Mapping) and 'bbox' in raw:
        box = raw['bbox']
        _require(cell.get('bbox') == box and cell.get('coordinate_system') == 'pdf_points'
                 and cell.get('coordinate_origin') == (box.get('coord_origin', 'UNKNOWN') if isinstance(box, Mapping) else 'UNKNOWN'),
                 'native cell geometry/frame changed')


def resolve_bound_locator(contract, locator):
    """Resolve JSON, decoded JSON and explicit HTML/GFM syntax paths, without I/O."""
    _require(locator.artifact_sha256 == contract.artifact.sha256, 'locator belongs to another artifact')
    path = locator.path
    if '::html/cell[' in path:
        parent = path.split('::html/cell[', 1)[0]
        source = resolve_pointer(contract.artifact.read(), parent)
        cells = html_cells(source, parent) if isinstance(source, str) else []
        return next((c for c in cells if c['id'] == path), None)
    if '/gfm/rows/' in path:
        parent = path.split('/gfm/rows/', 1)[0]
        source = resolve_pointer(contract.artifact.read(), parent)
        cells = markdown_cells(source, parent) if isinstance(source, str) else []
        return next((c for c in cells if c['id'] == path), None)
    return resolve_pointer(contract.artifact.read(), path)


def _input_decode_gap(root, page):
    """Validate failed-page waivers from input, never from mutable adapter flags."""
    pages = [p for p in root.get('pages', []) if isinstance(p, Mapping) and p.get('page') == page]
    if len(pages) != 1:
        return True
    entry = pages[0]
    branch, raw = entry.get('branch'), entry.get('raw')
    allowed = CONFIGURATIONS.get(root.get('pipeline'), {}).get('branches', set())
    if not isinstance(branch, str) or branch not in allowed or not (
        isinstance(raw, Mapping) or branch == 'visual' and isinstance(raw, list)
    ):
        return True
    if sum(isinstance(p, Mapping) and p.get('page') == page for p in root.get('page_processing', [])) > 1:
        return True
    if branch == 'visual':
        return not isinstance(raw, list)
    if not isinstance(raw, Mapping):
        return True
    if branch == 'glm':
        from app.adapters.native_inventory import _regions
        return not _regions(raw, '#')
    if branch == 'paddle':
        payload = raw.get('res', raw)
        return not isinstance(payload, Mapping) or not isinstance(payload.get('parsing_res_list'), list)
    if branch == 'mineru':
        from app.adapters.mineru_native import source_page
        from app.adapters.native_readers import NativeReadError
        try:
            source_page(root, entry)
        except NativeReadError:
            return True
        return False
    pointer, local = raw.get('native_document'), raw.get('source_page', page)
    if not isinstance(pointer, str) or not pointer.startswith('#/documents/') or type(local) is not int or local < 1:
        return True
    envelope = resolve_pointer(root, pointer)
    if not isinstance(envelope, Mapping):
        return True
    document = envelope.get('document', envelope)
    if not isinstance(document, Mapping) or not isinstance(document.get('body'), Mapping):
        return True
    owners = [p for p in root.get('pages', []) if isinstance(p, Mapping) and p.get('branch') == 'docling'
              and isinstance(p.get('raw'), Mapping) and p['raw'].get('native_document') == pointer]
    locals_ = [p['raw'].get('source_page', p.get('page')) for p in owners]
    if len({encoded(p) for p in locals_}) != len(locals_):
        return True
    group = envelope.get('research_group_pages', [p['page'] for p in owners])
    if not isinstance(group, list) or any(type(p) is not int or p < 1 for p in group):
        return True
    return (len(set(group)) != len(group) or not {p['page'] for p in owners} <= set(group)
            or any(p.get('page') in group and (p.get('branch') != 'docling'
                   or p.get('raw', {}).get('native_document') != pointer)
                   for p in root.get('pages', []) if isinstance(p, Mapping)))


def validate_native_content(result):
    """Validate object identities and relations, not adapter capability flags."""
    contract = result._native_content
    _require(isinstance(contract, NativeContentContract), 'saved content requires a bound native evidence contract')
    root = contract.artifact.read()
    _require(root.get('pipeline') == contract.pipeline and result.pipeline.primary == contract.producer,
             'native configuration/producer identity conflict')
    configuration = root.get('config')
    _require(not isinstance(configuration, Mapping) or configuration.get('pipeline', contract.pipeline) == contract.pipeline,
             'native configuration identity contradicts the artifact pipeline')
    items, bindings = inventory_native(contract.artifact, contract.selected_pages, contract.original_pages)
    _require(items == contract.items and bindings == contract.page_bindings, 'input inventory/page mapping was changed')
    _require(Counter(p.page_number for p in result.pages) == Counter(contract.selected_pages), 'consumer page mapping changed')
    state = result._source_verification.get('native_content', {})
    _require(state.get('original_execution') == contract.execution.metadata, 'original execution state was changed')
    blocks = [(page, b) for page, values in result._native_page_blocks.items() for b in values]
    keys = [(p, b.get('occurrence_id', b.get('id'))) for p, b in blocks]
    _require(len(keys) == len(set(keys)), 'duplicate native occurrence in adapted content')
    expected = {(i.input_page, i.identity): i for i in items if i.kind in {'content', 'table', 'picture'}}
    actual = dict(zip(keys, (b for _, b in blocks), strict=True))
    missing, extra = set(expected) - set(actual), set(actual) - set(expected)
    # A page decoder may have explicitly failed before exposing any objects.
    failed = {p['raw_page'] for p in result._source_verification.get('saved_native_bridge', {}).get('pages', [])
              if p.get('error') and _input_decode_gap(root, p['raw_page'])}
    _require(not any(p not in failed for p, _ in missing), 'native object omitted from adapted content: ' + str(sorted(missing)))
    _require(not any(not actual[k].get('read_error') for k in extra), 'adapted object has no input occurrence')
    expected_cells = {(i.input_page, i.parent, i.identity): i for i in items if i.kind == 'cell'}
    seen_cells = set()
    for key, item in expected.items():
        if key not in actual:
            continue
        block = actual[key]
        node = resolve_pointer(root, item.locator.path)
        _require(block.get('native_path') == item.locator.path and block.get('native_branch') == item.branch,
                 'native locator/branch was rebound: ' + item.identity)
        _require(block.get('source_locator') == asdict(item.locator), 'native locator lacks artifact/view binding')
        _require(block.get('native_payload') == audit_copy(node), 'native payload was altered: ' + item.identity)
        field = 'text' if item.branch == 'docling' else 'block_content' if item.branch == 'paddle' else 'content'
        if item.branch != 'mineru' and isinstance(node, Mapping) and item.kind == 'content' and node.get(field) is not None and not isinstance(node[field], str):
            _require(block.get('read_error') and block.get('read_status') == 'unresolved',
                     'malformed native text was promoted to a successful read')
        _require(block.get('text') == (item.raw_text or ''), 'native literal or selection changed: ' + item.identity)
        _require(block.get('kind') == item.details['label'], 'native role was replaced by a service inference')
        _require(block.get('text_format') == (None if not isinstance(node, Mapping) else
                 item.details['text_format'] if item.branch in {'mineru', 'visual'} else
                 'plain' if item.branch == 'docling' else
                 'html' if re.search(r'<table\b', item.raw_text or '', re.I) else 'markdown'),
                 'native display syntax changed')
        _require(block.get('original_pdf_page') == item.original_page, 'original input-page binding changed')
        _require(block.get('branch_page') == item.branch_page, 'branch-local page binding changed')
        _require(block.get('parent_id') == item.parent, 'native parent relationship changed: ' + item.identity)
        if item.branch == 'docling' and isinstance(node, Mapping):
            base = item.locator.path.rsplit('/' + item.details['family'] + '/', 1)[0]
            spans = [list(s) for s in item.locator.text_spans]
            _require((block.get('text_selection') or []) == spans, 'native source text span changed')
            prov = node.get('prov')
            own = [p for p in prov if isinstance(p, Mapping) and p.get('page_no') == item.branch_page] if isinstance(prov, list) else []
            if own and block.get('coordinate_system'):
                box = own[0].get('bbox')
                _require(block.get('bbox') == box and block.get('coordinate_system') == 'pdf_points'
                         and block.get('coordinate_origin') == (box or {}).get('coord_origin', 'UNKNOWN'),
                         'native geometry/frame changed')
                document = resolve_pointer(root, base)
                pages = document.get('pages', {})
                size = pages.get(str(item.branch_page), pages.get(item.branch_page, {})).get('size') if isinstance(pages, Mapping) else None
                _require(block.get('page_dimensions') == ({**size, 'unit': 'pdf_points'} if isinstance(size, Mapping) else None),
                         'native dimensions/transform changed')
            for field in ('children', 'captions', 'footnotes', 'references'):
                refs = [base + r['$ref'][1:] for r in node.get(field, []) if isinstance(r, Mapping) and isinstance(r.get('$ref'), str)]
                value = block.get('native_children', []) if field == 'children' else block.get('native_references', {}).get(field, [])
                _require(value == refs, 'native reference/scope changed')
        if item.branch == 'glm':
            _require(block.get('order_basis') == item.order_basis, 'unknown order was promoted or index changed')
            _require(block.get('bbox') == (node.get('bbox_2d') if isinstance(node, Mapping) else None), 'native geometry changed')
            _require(block.get('source_view') == 'json_result' and block.get('coordinate_system') == 'normalized_1000',
                     'primary view or GLM coordinate frame changed')
        if item.branch == 'visual':
            from app.adapters.visual_native import (
                MEDIA_FIELDS as VISUAL_MEDIA_FIELDS,
            )
            from app.adapters.visual_native import (
                RELATION_FIELDS,
                STATE_FIELDS,
                visual_geometry,
            )
            raw = node if isinstance(node, Mapping) else {}
            entry = resolve_pointer(root, item.locator.path.rsplit('/raw/', 1)[0])
            _require(block.get('source_view') == 'ContentBlock[]'
                     and block.get('source_kind') == 'native_visual_region'
                     and block.get('page') == item.input_page
                     and block.get('native_array_position') == item.details['array_position']
                     and block.get('native_sequence') == list(item.order)
                     and block.get('order_basis') == item.order_basis,
                     'visual page/region occurrence or order changed')
            _require(block.get('native_fields') == item.details['native_fields']
                     and block.get('native_content') == audit_copy(raw.get('content')),
                     'visual native identity/fields changed')
            _require(block.get('native_relations') == {k: audit_copy(raw[k]) for k in RELATION_FIELDS if k in raw}
                     and block.get('parent_id') is None, 'visual grouping became a fabricated parent or was lost')
            expected_components = []
            for component in item.details['source_components']:
                source = next(i for i in items if i.input_page == item.input_page
                              and i.parent == item.identity and i.locator.path == component['native_path'])
                expected_components.append({**component, 'source_locator': asdict(source.locator)})
            _require(block.get('source_components') == expected_components
                     and block.get('character_provenance') == 'not_available'
                     and block.get('ocr_verification') == 'not_available'
                     and block.get('native_text_span') is None and not block.get('charspan')
                     and not block.get('text_selection') and not block.get('ocr_verified')
                     and all(not p.get('charspan') for p in block.get('provenance', [])),
                     'visual text/description provenance changed or character source fabricated')
            _require(all(block.get('native_' + k if k != 'self_ref' else k) == raw.get(k)
                         for k in ('id', 'index', 'self_ref', 'group_id')),
                     'visual declared object identity changed')
            _require(all(block.get(k) == v for k, v in visual_geometry(root, entry, raw).items()),
                     'visual geometry/frame/polygon/transform changed')
            _require(block.get('native_media_declaration') == {k: audit_copy(raw[k]) for k in VISUAL_MEDIA_FIELDS if k in raw}
                     and block.get('asset') == (raw.get('research_asset') or raw.get('asset')),
                     'visual media declaration changed')
            _require(block.get('native_execution_state') == {k: audit_copy(raw[k]) for k in STATE_FIELDS if k in raw}
                     and all(block.get(k) == raw[k] for k in ('status', 'angle', 'merge_prev') if k in raw),
                     'visual native failure/continuation state changed')
            if item.details['requires_read_failure']:
                _require(block.get('read_error') and block.get('read_status') == 'unresolved',
                         'malformed visual region promoted to successful read')
        if item.branch == 'paddle':
            _require(block.get('order_basis') == item.order_basis, 'unknown Paddle order was promoted')
            _require(block.get('native_array_position') == item.details['array_position'], 'native region occurrence moved')
            _require(block.get('source_view') == item.locator.view, 'Paddle main view changed')
            if isinstance(node, Mapping):
                from app.adapters.paddle_native import paddle_geometry, paddle_group_identity
                page_payload = resolve_pointer(root, item.locator.path.rsplit('/parsing_res_list/', 1)[0])
                _require(block.get('native_group_id') == node.get('group_id')
                         and block.get('group_identity') == paddle_group_identity(item.input_page, node), 'native group identity changed or gained a parent')
                _require(block.get('native_block_order') == node.get('block_order')
                         and block.get('native_block_id') == node.get('block_id'), 'native block id/rank changed')
                _require(block.get('native_field_presence') == item.details['field_presence'], 'native missing-field state changed')
                _require(block.get('bbox') == node.get('block_bbox') and block.get('coordinate_origin') == 'TOPLEFT'
                         and block.get('coordinate_system') == 'pixel', 'Paddle bbox/frame changed')
                expected_geometry = paddle_geometry(page_payload, node)
                _require(all(block.get(k) == v for k, v in expected_geometry.items()), 'Paddle polygon/dimensions/transform evidence changed')
                declared_asset = resolve_pointer(root, item.locator.path.split('/res/parsing_res_list/', 1)[0] + '/research_region_media') if '/res/parsing_res_list/' in item.locator.path else None
                if isinstance(declared_asset, Mapping):
                    _require(block.get('asset') == declared_asset.get(str(item.details['array_position'])), 'Paddle media declaration borrowed another region')
        if item.branch == 'mineru':
            from app.adapters.mineru_native import MEDIA_FIELDS, media_declaration
            raw = node if isinstance(node, Mapping) else {}
            if item.details.get('requires_read_failure'):
                _require(block.get('read_error') and block.get('read_status') == 'unresolved',
                         'malformed MinerU primary content was promoted to a successful read')
            _require(block.get('source_view') == 'docvortex.middle'
                     and block.get('native_block_type') == raw.get('type')
                     and block.get('native_block_id') == raw.get('block_id')
                     and block.get('native_content') == audit_copy(raw.get('content')),
                     'MinerU primary type/id/content changed')
            _require(block.get('native_fields') == {k: audit_copy(raw[k]) for k in raw if k not in ('content', *MEDIA_FIELDS)},
                     'MinerU native reference/state/field changed')
            _require(block.get('native_media_declaration') == media_declaration(raw), 'MinerU media declaration changed')
            _require(block.get('order_basis') == item.order_basis and block.get('native_sequence') == list(item.order),
                     'MinerU native order evidence changed')
            if isinstance(node, Mapping):
                _require(block.get('bbox') == node.get('bbox') and block.get('coordinate_system') == 'normalized'
                         and block.get('coordinate_origin') == 'TOPLEFT', 'MinerU native geometry changed')
            for field in ('continues_prev', 'merge_prev'):
                _require((field in block) == (field in raw) and block.get(field) == raw.get(field), 'MinerU continuation changed')
            if raw.get('type') == 'table_body' and item.parent:
                parent = resolve_pointer(root, item.parent)
                declaration = {k: audit_copy(parent[k]) for k in ('continues_prev', 'cell_merge') if k in parent}
                _require(block.get('native_table_declaration') == declaration, 'native table continuation declaration changed')
        own_cells = block.get('cells', [])
        _require(len({c.get('id') for c in own_cells}) == len(own_cells), 'duplicate source cell')
        for cell in own_cells:
            ck = (item.input_page, item.identity, cell.get('id'))
            _require(ck in expected_cells, 'cell borrowed from another native object')
            _cell_matches(expected_cells[ck], cell)
            seen_cells.add(ck)
    _require(not any(p not in failed for p, _, _ in set(expected_cells) - seen_cells), 'native source cell omitted')
    for page in contract.selected_pages:
        ordered = [expected[(p, b.get('occurrence_id', b.get('id')))] for p, b in blocks
                   if p == page and (p, b.get('occurrence_id', b.get('id'))) in expected]
        known = [i.order for i in ordered if i.order_basis in {'native_index', 'native_reading_tree'}]
        _require(known == sorted(known), 'confirmed native reading order was changed')
        visual = [i.order for i in ordered if i.branch == 'visual']
        _require(visual == sorted(visual), 'visual observed array order changed; reading order remains unknown')
    media = [i for i in items if i.kind == 'media']
    declared = state.get('media', [])
    _require(declared == result._source_verification.get('saved_native_bridge', {}).get('asset_references', []),
             'native media bridge declarations changed')
    media_keys = Counter((i.input_page, i.locator.path, i.locator.text_spans[0] if i.locator.text_spans else None) for i in media)
    actual_media = Counter((d.get('page'), d.get('native_path'), tuple(d['source_text_span']) if 'source_text_span' in d else None) for d in declared)
    _require(media_keys == actual_media, 'native media occurrence omitted, duplicated or rebound')
    _require(all(d.get('status') == 'unverified_not_delivered' and d.get('bytes_accessed') is False for d in declared),
             'unread native media was promoted to delivered')
    for _, block in blocks:
        appearances = [d for d in declared if d['page'] == _ and d['native_path'] == block.get('native_path')]
        if block.get('type') == 'image':
            _require(len(appearances) == 1 and block.get('media') == appearances[0], 'native picture declaration lost at handoff')
    fragments = {f.fragment_id: f for f in result._table_fragments}
    expected_fragments = {b['service_fragment_id'] for _, b in blocks if b.get('service_fragment_id')}
    _require(set(fragments) == expected_fragments, 'adapted table was omitted or duplicated')
    for f in fragments.values():
        verify_table_source(f, contract, required=True)
    containers = [c for page in result._source_verification['saved_native_bridge']['pages'] for c in page.get('native_containers', [])]
    for item in contract.items:
        if item.kind != 'container' or not item.details.get('in_reading_tree'):
            continue
        own = [c for c in containers if c.get('native_path') == item.locator.path]
        base = item.locator.path.split('/document/', 1)[0]
        decoded = any(b.get('native_path', '').startswith(base + '/') for _, b in blocks)
        _require(own or not decoded, 'native parent-chain container omitted')
        if item.branch == 'mineru':
            _require(len(own) == 1 or item.input_page in failed, 'MinerU native container omitted or duplicated')
        for c in own:
            _require(c.get('native_payload') == audit_copy(resolve_pointer(root, item.locator.path))
                     and c.get('parent_id') == item.parent, 'native parent-chain evidence rebound')
            if item.branch == 'mineru':
                _require(c.get('native_children') == item.details['native_children']
                         and c.get('label') == item.details['label']
                         and c.get('native_block_type') == item.details['label']
                         and c.get('order_basis') == item.order_basis
                         and c.get('native_sequence') == list(item.order), 'MinerU container identity/children/order changed')
    receipts = [r for page in result._source_verification['saved_native_bridge']['pages'] for r in page.get('native_audit_objects', [])]
    needed = [i for i in items if i.details.get('requires_audit_receipt')]
    _require(Counter(r.get('native_path') for r in receipts) == Counter(i.locator.path for i in needed),
             'derived native audit occurrence omitted, duplicated or rebound')
    for item in needed:
        receipt = next(r for r in receipts if r['native_path'] == item.locator.path)
        _require(receipt.get('source_locator') == asdict(item.locator)
                 and receipt.get('payload') == audit_copy(resolve_pointer(root, item.locator.path))
                 and receipt.get('used_as_answer') is False, 'derived native view was altered or promoted to an answer')
    # This is transform consistency, deliberately separate from the input
    # inventory and source-relation checks. It prevents consumers from silently
    # discarding a valid display while retaining hidden raw text.
    from app.services.native_content_service import render_native_blocks
    for page, values in result._native_page_blocks.items():
        parents = [c for p in result._source_verification['saved_native_bridge']['pages']
                   if p['raw_page'] == page for c in p.get('native_containers', [])]
        projected = copy.deepcopy(values)
        branch = next((b['native_branch'] for b in projected), 'unknown')
        render_native_blocks(projected, page, branch, copy.deepcopy(parents),
                             include_source_markers=any(b.get('service_marker') for b in values))
        _require(all(all(a.get(k) == b.get(k) for k in ('type', 'content', 'markdown', 'service_rendered', 'service_bbox', 'media', 'heading_projection', 'derived_display'))
                     for a, b in zip(values, projected, strict=True)), 'native/display projection changed')
    return contract


def verify_table_source(fragment, contract, *, required=False):
    """Actual input grid evidence is required; saved_structure is no authority."""
    if not isinstance(contract, NativeContentContract):
        if required:
            raise NativeContentError('table needs a bound native contract')
        return False
    binding = fragment.native_evidence.get('source_binding')
    tables = [i for i in contract.items if i.kind == 'table' and i.input_page == fragment.page_number
              and asdict(i.locator) == binding]
    _require(len(tables) == 1, 'table has no unique input-owned occurrence')
    table = tables[0]
    if table.branch == 'docling':
        raw_table = resolve_pointer(contract.artifact.read(), table.locator.path)
        data = raw_table.get('data', {})
        _require((data.get('num_rows'), data.get('num_cols')) == (fragment.num_rows, fragment.num_cols),
                 'consumer grid contradicts native declared dimensions')
    native_cells = [i for i in contract.items if i.kind == 'cell' and i.input_page == table.input_page and i.parent == table.identity]
    source_cells = fragment.native_evidence.get('source_cells', [])
    _require(len(native_cells) == len(source_cells) == len(fragment.cells), 'consumer grid omitted source cells')
    by_id = {i.identity: i for i in native_cells}
    _require(len(by_id) == len(source_cells), 'source-cell occurrences are not unique')
    occupied: set[tuple[int, int]] = set()
    from app.services.native_content_service import _box
    for raw, cell in zip(source_cells, fragment.cells, strict=True):
        _require(raw.get('id') in by_id, 'consumer cell borrowed another table')
        _cell_matches(by_id[raw['id']], raw)
        _require((cell.row, cell.column, cell.row_span, cell.column_span, cell.text,
                  cell.is_column_header, cell.is_row_header) ==
                 (raw['row'], raw['col'], raw['row_span'], raw['col_span'], raw['text'],
                  raw.get('is_column_header') is True, raw.get('is_row_header') is True), 'consumer/source grid relationship changed')
        _require(cell.normalized_bbox == _box(raw), 'consumer cell transform is not backed by native geometry')
        slots = {(r, c) for r in range(cell.row, cell.row + cell.row_span)
                 for c in range(cell.column, cell.column + cell.column_span)}
        _require(not occupied & slots and all(0 <= r < fragment.num_rows and 0 <= c < fragment.num_cols for r, c in slots),
                 'source grid overlaps or dimensions changed')
        occupied.update(slots)
        _require(fragment.rows[cell.row][cell.column] == cell.text, 'consumer row content changed')
    _require(len(occupied) == fragment.num_rows * fragment.num_cols, 'source grid has unexplained holes')
    return True


def native_partial(result):
    from app.services.native_content_status import native_status_impacts
    return any(impact['requires_partial'] for impact in native_status_impacts(result))


def validate_table_relations(result):
    """Check source locations/scope, independently of rendered edit replay.

    This checks the bounded existing table rules. It does not certify new table
    categories or infer business facts from values appearing in Markdown.
    """
    from app.models.table_semantics import CellRef, TextRef

    validate_native_content(result)
    fragments = {f.fragment_id: f for f in result._table_fragments}
    registry = {CellRef(f.fragment_id, c.row, c.column): c for f in fragments.values() for c in f.cells}
    checked = []
    for view in result._semantic_tables:
        for record in view.records:
            _require(record.source_table_id in fragments, 'record has no source table')
            fragment = fragments[record.source_table_id]
            declared_context = set(fragment.context_refs)
            for reference in (*record.scope_refs, *(r for v in record.values for r in (*v.unit_refs, *v.period_refs, *v.note_refs) if isinstance(r, TextRef))):
                _require(reference in declared_context, 'qualifier borrowed from another table/occurrence')
                locator = fragment.native_evidence.get('context_native_paths', {}).get(reference.token)
                if locator:
                    blocks = result._native_page_blocks.get(reference.page, [])
                    index = reference.block_id.split('.', 1)[0]
                    _require(index.isdecimal() and int(index) < len(blocks) and
                             blocks[int(index)].get('source_locator') == locator.get('evidence_locator'),
                             'qualifier rebound to a neighboring same-literal occurrence')
                    matches = [b for b in blocks if b.get('native_path') == locator['native_path']
                               and b.get('source_locator') == locator.get('evidence_locator')]
                    _require(len(matches) == 1, 'qualifier source locator is not uniquely bound')
                    text = matches[0].get('content', '')
                    _require(text[reference.start:reference.end] == reference.text
                             and locator['source_text_span'] == [reference.start, reference.end],
                             'unit/period/note literal span changed')
                elif reference.block_id.startswith('cell.'):
                    _, row, col = reference.block_id.split('.')
                    source = registry.get(CellRef(fragment.fragment_id, int(row), int(col)))
                    _require(source is not None and source.text[reference.start:reference.end] == reference.text,
                             'table context cell is unbound')
                else:
                    _require(False, 'qualifier has no rooted source slice')
            for relation in record.values:
                _require(relation.value in registry and relation.value.table_id == record.source_table_id,
                         'value source borrowed from another table')
                cell = registry[relation.value]
                _require(cell.row <= record.source_row < cell.row + cell.row_span, 'value assigned to another record')
                if record.subject is not None:
                    _require(record.subject in relation.row_headers and record.subject in registry,
                             'record subject/source row conflict')
                for ref in relation.row_headers:
                    _require(ref in registry and ref.table_id == record.source_table_id,
                             'row header has no source cell')
                    header = registry[ref]
                    _require(header.column < cell.column and (header.row <= record.source_row < header.row + header.row_span
                             or [header.row, header.column] in fragment.native_evidence.get('row_groups', {}).values()),
                             'row header does not own the value record')
                scopes = [s for s in fragment.source_header_scopes if s.get('complete') and record.source_row in s.get('body_rows', [])]
                expected_headers = tuple(CellRef(fragment.fragment_id, h.row, h.column)
                    for h in sorted(fragment.cells, key=lambda c: (c.row, c.column))
                    if any(h.row in s.get('header_rows', []) for s in scopes) and h.text.strip()
                    and h.column <= cell.column and cell.column + cell.column_span <= h.column + h.column_span)
                _require(relation.column_headers == expected_headers, 'column header path is incomplete or misbound')
                labels = set((*relation.row_headers, *relation.column_headers))
                for refs, kind in ((relation.unit_refs, 'unit'), (relation.period_refs, 'period'), (relation.note_refs, 'note')):
                    for ref in refs:
                        if isinstance(ref, TextRef):
                            _require(ref.kind == kind and record.source_row in ref.body_rows and cell.column in ref.columns,
                                     'qualifier kind/record/column scope conflict')
                        else:
                            _require(ref in registry and (ref in labels or kind == 'unit' and ref.column == 0
                                     and any(ref.row in s.get('header_rows', []) for s in scopes)),
                                     'qualifier source cell is outside its owning headers')
                # A period printed on a selected header must remain attached.
                periods = tuple(ref for ref in (*relation.row_headers, *relation.column_headers)
                                if re.search(r'报告期|同期|年度|期末|年末|月末|\d{4}\s*年|(?<!\d)(?:19|20)\d{2}(?!\d)', registry[ref].text))
                _require(set(periods) <= set(relation.period_refs), 'printed header period was detached')
                for ref in fragment.context_refs:
                    if record.source_row not in ref.body_rows or cell.column not in ref.columns:
                        continue
                    if ref.kind == 'note':
                        marker = re.match(r'^\s*([0-9]{1,2}|[*†‡])(?:\s+|[.)、：:])', ref.text)
                        if marker and any(re.search(r'(?:\^\s*\{?|<sup>)' + re.escape(marker[1]) + r'(?:\}|</sup>|\b)', registry[r].text)
                                          for r in (relation.value, *relation.row_headers)):
                            _require(ref in relation.note_refs, 'source note was detached from marked record')
                    elif ref.kind == 'unit' and not relation.unit_refs and re.fullmatch(r'[+\-−]?[\d,.]+', cell.text.strip()):
                        header_text = ' '.join(registry[r].text for r in relation.column_headers)
                        if not re.search(r'%|％|‰|比例|比率|同比|增减率|占|佔|ratio|rate|Notes?|序号|编号|代码', header_text, re.I):
                            _require(False, 'applicable source unit was detached')
                checked.append({'value': relation.value.token, 'record_row': record.source_row,
                                'row_headers': [r.token for r in relation.row_headers],
                                'column_headers': [r.token for r in relation.column_headers],
                                'units': [r.token for r in relation.unit_refs],
                                'periods': [r.token for r in relation.period_refs],
                                'notes': [r.token for r in relation.note_refs]})
    result._source_verification['native_relation_checks'] = checked
    return checked


def validate_ir_handoff(result):
    contract = validate_native_content(result)
    _require(result.parse_result is not None, 'consumer IR missing')
    ir_blocks = {b.block_id: b for unit in result.parse_result.units for b in unit.blocks}
    for blocks in result._native_page_blocks.values():
        for block in blocks:
            if block.get('type') == 'table':
                continue
            ident = block.get('occurrence_id', block['id'])
            _require(ident in ir_blocks and ir_blocks[ident].text == block.get('text', ''), 'native occurrence lost at IR handoff')
            selected = ir_blocks[ident].provenance.selected_source
            _require(selected is None or selected.value == block['native_branch'], 'consumer IR source was fabricated')
            if block.get('source_kind') == 'native_visual_region':
                consumer = ir_blocks[ident]
                reasons = {'native_visual_region', 'no_document_character_provenance',
                           *(c['source_type'] for c in block['source_components'])}
                _require(selected is None and not consumer.provenance.sources
                         and not consumer.provenance.supporting_sources
                         and reasons <= set(consumer.provenance.reason_codes),
                         'visual source category lost or promoted to OCR at IR handoff')
                _require(consumer.unit_id == f"p{block['page']}" and consumer.region_id == ident + ':region',
                         'visual page or region rebound at IR handoff')
                if block['type'] in {'layout_region', 'description', 'region_label'}:
                    _require(consumer.block_type == 'unknown', 'visual region/description promoted to ordinary text in IR')
                box = consumer.bbox
                actual_box = (box.left, box.top, box.right, box.bottom) if box is not None else None
                _require(actual_box == block['service_bbox'], 'visual spatial evidence lost at IR handoff')
    tables = {t.table_id: t for t in result.parse_result.tables}
    for f in result._table_fragments:
        _require(f.fragment_id in tables, 'table omitted at IR handoff')
        table = tables[f.fragment_id]
        _require([(c.row, c.column, c.row_span, c.column_span, c.text) for c in table.cells] ==
                 [(c.row, c.column, c.row_span, c.column_span, c.text) for c in f.cells], 'source cells changed at IR handoff')
    result._source_verification['native_ir_handoff'] = {'artifact_sha256': contract.artifact.sha256,
        'objects': sorted(ir_blocks), 'tables': sorted(tables),
        'native_order': [{'identity': i.identity, 'order': list(i.order), 'basis': i.order_basis}
                         for i in contract.items if i.kind in {'content', 'table', 'picture'}],
        'public_reading_order': 'service_display_index; native order and unknown remain in evidence root'}
