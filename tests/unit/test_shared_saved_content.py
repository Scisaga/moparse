"""Independent text/JSON contracts; never open sources, media or references."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.native_content import NativeArtifact
from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from app.models.source import StoredSource
from app.services.native_content_evidence import (
    NativeContentError,
    validate_ir_handoff,
    validate_native_content,
    validate_table_relations,
)
from app.services.saved_content_service import SavedContentService
from moparse_eval.saved_content_closure import close_saved_document
from moparse_eval.service_replay_native import replay_native


def execution(pipeline='P05', status='completed', **extra):
    return {'pipeline': pipeline, 'status': status,
            'pages': [{'page': 1, 'status': status}], **extra}


async def finish(native=None, observed='present'):
    native = native or glm_input()
    return await close_saved_document(native, source(), sample_id='synthetic',
        declared_source_sha256='a' * 64, source_pages=[91],
        original_observation=execution(native['pipeline']) if observed == 'present' else observed)


def table_input(pipeline='P05'):
    n = glm_input(pipeline)
    n['pages'][0]['raw']['json_result'] = [[
        {'index': 0, 'label': 'caption', 'content': '单位：万元'},
        {'index': 1, 'label': 'table', 'content':
         '<table><tr><th rowspan="2">Item</th><th colspan="2">2025年度</th></tr>'
         '<tr><th>收入</th><th>成本</th></tr>'
         '<tr><td>Alpha</td><td>17.00</td><td>17.00</td></tr></table>'},
        {'index': 2, 'label': 'text', 'content': 'Same literal.'},
        {'index': 3, 'label': 'text', 'content': 'Same literal.'},
    ]]
    return n


def source():
    return StoredSource(path=Path('/not-mounted/input.pdf'), filename='input.pdf',
                        mime_type='application/pdf', size_bytes=123, page_count=1)


def glm_input(pipeline='P05'):
    return {'pipeline': pipeline, 'pages': [{'page': 1, 'branch': 'glm', 'raw': {
        'json_result': [[
            {'index': 0, 'label': 'text', 'native_label': 'paragraph_title',
             'content': '## Printed results', 'bbox_2d': [10, 10, 900, 100]},
            {'index': 1, 'label': 'text', 'native_label': 'text',
             'content': 'Printed paragraph 17.', 'bbox_2d': [10, 100, 900, 200]},
        ]],
        'raw_json_result': [[{'label': 'text', 'content': 'Forbidden alternate answer'}]],
        'markdown_result': 'Forbidden alternate export',
    }}]}


def test_p05_bridge_emits_the_same_consumer_fields_as_the_shared_services():
    result, _ = replay_native(glm_input(), source(), ContentParseOptions(), document_id='synthetic')
    block = result._native_page_blocks[1][1]
    assert (block['type'], block['content'], block['markdown']) == (
        'text', 'Printed paragraph 17.', 'Printed paragraph 17.')


async def test_a_producer_flag_cannot_admit_unbound_content_to_finalization():
    result = DocumentParseResult(document_id='synthetic', filename='input.pdf',
        mime_type='application/pdf', page_count=1, processed_pages=1,
        pages=[PageParseResult(page_number=1, content='Unbound text')],
        pipeline=ParsePipeline(profile='balanced', primary='unknown'))
    result._source_verification['saved_p01'] = {'status': 'completed', 'media': []}
    with pytest.raises(ValueError, match='(?i)(contract|evidence|bound)'):
        await SavedContentService().finalize(result, source(), ContentParseOptions(),
                                            declared_source_sha256='a' * 64)


@pytest.mark.asyncio
async def test_independent_identical_glm_payloads_share_semantics_but_keep_identities():
    a, ea = await finish(table_input('P01'))
    b, eb = await finish(table_input('P05'))
    assert a.markdown == b.markdown
    assert '2025年度 / 收入：17.00' in a.markdown
    assert '2025年度 / 成本：17.00' in a.markdown
    assert '单位：万元' in a.markdown
    assert ea['semantic_tables'] == eb['semantic_tables']
    assert a._native_content.pipeline == 'P01' and b._native_content.pipeline == 'P05'
    assert a._native_content.artifact.sha256 != b._native_content.artifact.sha256
    assert a.pipeline.primary != b.pipeline.primary
    assert all(i.branch == 'glm' for i in a._native_content.items)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['body', 'table', 'cell', 'region', 'duplicate', 'same_literal', 'display',
                                   'parent', 'locator', 'cross_branch', 'grid', 'capability', 'mapping'])
async def test_input_owned_inventory_rejects_missing_and_rebound_adaptation(damage):
    result, _ = await finish(table_input())
    blocks = result._native_page_blocks[1]
    if damage == 'body':
        blocks.pop(0)
    elif damage == 'table':
        blocks.pop(1)
    elif damage == 'cell':
        blocks[1]['cells'].pop()
    elif damage == 'region':
        blocks.pop(2)
        # A forged read failure must not excuse an omitted valid main region.
        result._source_verification['saved_native_bridge']['pages'][0]['error'] = 'fake'
    elif damage == 'duplicate':
        blocks.append(deepcopy(blocks[2]))
    elif damage == 'same_literal':
        blocks[3] = deepcopy(blocks[2])
    elif damage == 'parent':
        blocks[2]['parent_id'] = blocks[3]['id']
    elif damage == 'display':
        blocks[2]['markdown'] = ''
    elif damage == 'locator':
        blocks[2]['source_locator']['path'] = blocks[3]['native_path']
    elif damage == 'cross_branch':
        blocks[2]['native_branch'] = 'docling'
    elif damage == 'grid':
        result._table_fragments[0].cells[4].column = 2
    elif damage == 'mapping':
        blocks[2]['branch_page'] = 91
    else:
        result._table_fragments[0].native_evidence.update(validated=True, supports_tables=True)
        del result._table_fragments[0].native_evidence['source_binding']
    with pytest.raises(NativeContentError):
        validate_native_content(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['member', 'media', 'native_parent', 'parent_container', 'dimension', 'cell_frame'])
async def test_docling_occurrences_and_list_parent_chain_are_not_replaced_by_literals(damage):
    from tests.unit.test_p01_saved_content import native
    from tests.unit.test_p01_saved_content import source as mixed_source
    n = native(media=True)
    result, _ = replay_native(n, mixed_source(), ContentParseOptions(), document_id='synthetic')
    if damage == 'member':
        result._native_page_blocks[1].pop(3)
    elif damage == 'media':
        result._source_verification['native_content']['media'].pop()
    elif damage == 'parent_container':
        for page in result._source_verification['saved_native_bridge']['pages']:
            page['native_containers'] = [c for c in page.get('native_containers', [])
                                         if c['native_path'] != '#/documents/0/document/groups/1']
    elif damage == 'dimension':
        result._native_page_blocks[1][0]['page_dimensions']['height'] = 200
    elif damage == 'cell_frame':
        result._native_page_blocks[2][1]['cells'][0]['coordinate_origin'] = 'BOTTOMLEFT'
    else:
        result._native_page_blocks[1][3]['parent_id'] = '#/documents/0/document/groups/0'
    with pytest.raises(NativeContentError):
        validate_native_content(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['wrong_header', 'missing_header', 'period', 'unit', 'same_value_record'])
async def test_source_relationships_cannot_be_replaced_by_printed_numbers(damage):
    result, _ = await finish(table_input())
    view = result._semantic_tables[0]
    record = view.records[0]
    value = record.values[0]
    if damage == 'wrong_header':
        value = replace(value, column_headers=record.values[1].column_headers)
    elif damage == 'missing_header':
        value = replace(value, column_headers=value.column_headers[1:])
    elif damage == 'period':
        value = replace(value, period_refs=())
    elif damage == 'unit':
        value = replace(value, unit_refs=())
    else:
        record = replace(record, source_row=0)
    record = replace(record, values=(value, *record.values[1:]))
    result._semantic_tables[0] = replace(view, records=(record, *view.records[1:]))
    with pytest.raises(NativeContentError):
        validate_table_relations(result)


@pytest.mark.asyncio
async def test_note_detachment_is_caught_from_the_native_marked_record():
    from tests.unit.test_p01_saved_content import native, prov
    from tests.unit.test_p01_saved_content import source as mixed_source
    n = native()
    d = n['documents'][0]['document']
    d['tables'][0]['footnotes'] = [{'$ref': '#/texts/7'}]
    d['tables'][0]['data']['table_cells'][4]['text'] = 'Alpha^1'
    d['texts'].append({'label': 'footnote', 'text': '1 Printed note.', 'prov': prov(2)})
    result, _ = await close_saved_document(n, mixed_source(), sample_id='synthetic',
        declared_source_sha256='a' * 64,
        original_observation={'pipeline': 'P01', 'status': 'completed',
                              'pages': [{'page': p, 'status': 'completed'} for p in (1, 2, 3)]})
    view = result._semantic_tables[0]
    record = view.records[0]
    assert record.values[0].note_refs
    value = replace(record.values[0], note_refs=())
    result._semantic_tables[0] = replace(view, records=(replace(record, values=(value, *record.values[1:])),))
    with pytest.raises(NativeContentError, match='note'):
        validate_table_relations(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['failed', 'unknown', 'warning', 'truncated', 'missing'])
async def test_original_execution_is_separate_from_readable_content_and_delivery(state):
    observed = None if state == 'missing' else execution(status='completed' if state in {'warning', 'truncated'} else state)
    if state == 'warning':
        observed['warnings'] = ['information only']
    if state == 'truncated':
        observed['truncated'] = True
    result, evidence = await finish(observed=observed)
    assert 'Printed paragraph 17.' in result.markdown
    assert evidence['states']['readback']['status'] == 'read'
    assert evidence['states']['conversion']['status'] == 'completed'
    assert evidence['status'] == ('completed' if state == 'warning' else 'partial')
    if state == 'failed':
        result._source_verification['native_content']['original_execution']['status'] = 'completed'
        with pytest.raises(NativeContentError, match='execution'):
            validate_native_content(result)


@pytest.mark.asyncio
async def test_missing_primary_never_reads_audit_or_an_export():
    n = glm_input()
    del n['pages'][0]['raw']['json_result']
    result, evidence = await finish(n)
    assert 'Forbidden' not in result.markdown
    assert result.pages[0].status == 'failed' and evidence['status'] == 'partial'
    assert evidence['states']['original_execution']['status'] == 'completed'
    assert evidence['states']['readback']['status'] == 'partial'


@pytest.mark.asyncio
async def test_unknown_order_and_geometry_keep_their_unknown_evidence():
    n = glm_input()
    for b in n['pages'][0]['raw']['json_result'][0]:
        b.pop('index')
        b.pop('bbox_2d')
    result, evidence = await finish(n)
    assert all(i['order_basis'] == 'native_array_order_unknown_reading_order'
               for i in evidence['contract']['inventory'] if i['kind'] == 'content')
    assert all(b.bbox is None and b.provenance.selected_source.value == 'glm'
               for b in result.parse_result.units[0].blocks)
    result._native_page_blocks[1][0]['order_basis'] = 'native_index'
    with pytest.raises(NativeContentError, match='order'):
        validate_native_content(result)


@pytest.mark.asyncio
async def test_native_text_with_no_page_evidence_is_retained_without_fabricating_a_page():
    from tests.unit.test_p01_saved_content import native
    from tests.unit.test_p01_saved_content import source as mixed_source
    n = native()
    item = {'label': 'text', 'text': 'Unlocated native text.', 'prov': []}
    n['documents'][0]['document']['texts'].append(item)
    result, evidence = await close_saved_document(n, mixed_source(), sample_id='synthetic',
        declared_source_sha256='a' * 64)
    assert result.markdown.count('Unlocated native text.') == 1
    block = next(b for blocks in result._native_page_blocks.values() for b in blocks if b.get('text') == item['text'])
    assert block['page'] is None and block['branch_page'] is None and block['original_pdf_page'] is None
    assert block['read_status'] == 'unresolved' and evidence['status'] == 'partial'


def test_unknown_consumer_source_does_not_default_to_docling():
    from app.services.ir_service import _source_kind
    assert _source_kind('unknown') is None


@pytest.mark.asyncio
async def test_ir_omission_is_detected_and_is_a_distinct_actual_stage():
    result, evidence = await finish(table_input())
    ir = next(s for s in evidence['stages'] if s['stage'] == 'ir')
    assert ir['source_audit']['object_inventory']['objects']
    assert evidence['ir_handoff']['objects']
    result.parse_result.units[0].blocks.pop()
    with pytest.raises(NativeContentError, match='IR handoff'):
        validate_ir_handoff(result)


@pytest.mark.asyncio
async def test_actual_stage_edits_and_storage_are_identical_bytes(tmp_path):
    from app.services.final_content_service import apply_text_edits
    from app.services.storage_service import StorageService
    result, evidence = await finish(table_input())
    final = evidence['final_text_evidence']
    assert apply_text_edits(final['assembly_markdown'], final['edits']) == result.markdown
    assert all(e['producer_edits']['status'] in {'verified', 'verified_no_text_change', 'not_applicable'}
               for e in evidence['stage_edit_ledger'])
    paths = await StorageService(SimpleNamespace(data_dir=tmp_path)).write_result('synthetic', result)
    assert paths.result.read_bytes() == result.markdown.encode() == evidence['stages'][-1]['markdown'].encode()
    same = [d for d in evidence['content_dispositions'] if d['raw_text'] == 'Same literal.']
    assert len(same) == 2 and same[0]['final_spans'] != same[1]['final_spans']
    assert all(d.get('locator', {}).get('artifact_sha256') == result._native_content.artifact.sha256
               for d in evidence['native_destinations'])


def test_actual_json_bytes_not_a_declared_checksum_own_the_contract():
    import json
    n = glm_input()
    received = json.dumps(n, indent=4).encode()
    artifact = NativeArtifact('controlled/native.json', received)
    result, _ = replay_native(n, source(), ContentParseOptions(), document_id='synthetic', artifact=artifact)
    assert result._native_content.artifact.payload == received
    with pytest.raises(NativeContentError, match='bytes'):
        replay_native(n, source(), ContentParseOptions(), document_id='synthetic',
                      artifact=NativeArtifact.from_object(glm_input('P01')))


@pytest.mark.asyncio
async def test_every_html_cell_locator_resolves_to_its_own_rooted_syntax():
    from app.services.native_content_evidence import resolve_bound_locator
    result, _ = await finish(table_input())
    items = [i for i in result._native_content.items if i.kind == 'cell']
    assert len(items) == 7
    for item in items:
        cell = resolve_bound_locator(result._native_content, item.locator)
        assert cell['id'] == item.identity and cell['text'] == item.raw_text


def test_inconsistent_original_mapping_and_execution_identity_are_rejected():
    for mapping in ([91, 92], [0]):
        with pytest.raises(NativeContentError, match='mapping'):
            replay_native(glm_input(), source(), ContentParseOptions(), document_id='synthetic', source_pages=mapping)
    with pytest.raises(NativeContentError, match='pipeline'):
        replay_native(glm_input(), source(), ContentParseOptions(), document_id='synthetic', original_observation=execution('P01'))


def test_production_handoff_modules_do_not_depend_on_evaluation_or_oracles():
    import ast
    paths = [*Path('app/adapters').glob('*.py'), Path('app/models/native_content.py'),
             Path('app/services/native_content_evidence.py'), Path('app/services/native_content_service.py'),
             *[Path('app/services') / (name + '_service.py') for name in (
                 'saved_content', 'export', 'ir', 'table_context', 'table_semantics', 'final_content', 'storage')]]
    visited = set()
    while paths:
        p = paths.pop()
        if p in visited:
            continue
        visited.add(p)
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith(('moparse_eval', 'tests'))
                if (node.module or '').startswith('app.'):
                    target = Path(*node.module.split('.')).with_suffix('.py')
                    if target.is_file():
                        paths.append(target)
            elif isinstance(node, ast.Import):
                assert all(not a.name.startswith(('moparse_eval', 'tests')) for a in node.names)
