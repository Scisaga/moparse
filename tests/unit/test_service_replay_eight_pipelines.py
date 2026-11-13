"""Independent invented native shapes exercise all eight service bridges."""

from copy import deepcopy
from pathlib import Path

import pytest

from app.models.parse_options import ContentParseOptions
from app.models.source import StoredSource
from moparse_eval.service_replay_native import replay_native


def source(pages=1):
    return StoredSource(path=Path('/never-open-this.pdf'), filename='invented.pdf',
                        mime_type='application/pdf', size_bytes=1, page_count=pages)


def docling(pipeline):
    prov = [{"page_no": 1, "bbox": {"l": 10, "t": 10, "r": 90, "b": 50, "coord_origin": "TOPLEFT"}}]
    document = {"body": {"children": [{"$ref": "#/texts/1"}, {"$ref": "#/tables/0"}, {"$ref": "#/texts/0"}]},
                "texts": [{"label": "text", "text": "After", "prov": prov},
                          {"label": "section_header", "text": "Printed heading", "prov": prov}],
                "pages": {"1": {"size": {"width": 100, "height": 100}}},
                "tables": [{"label": "table", "prov": prov, "data": {"num_rows": 2, "num_cols": 2,
                    "table_cells": [
                        {"text": "Unit", "start_row_offset_idx": 0, "start_col_offset_idx": 0,
                         "row_span": 1, "col_span": 2, "column_header": True},
                        {"text": "Printed value", "start_row_offset_idx": 1, "start_col_offset_idx": 0,
                         "row_span": 1, "col_span": 1, "row_header": True},
                        {"text": "17", "start_row_offset_idx": 1, "start_col_offset_idx": 1,
                         "row_span": 1, "col_span": 1, "column_header": False},
                    ]}}]}
    return {"pipeline": pipeline, "documents": [{"document": document, "status": "partial", "errors": ["producer detail"]}],
            "pages": [{"page": 1, "branch": "docling", "raw": {"native_document": "#/documents/0"}}]}


@pytest.mark.parametrize('pipeline', ['P01', 'P02'])
def test_docling_reads_tree_cells_spans_and_conversion_state_without_converter(pipeline):
    native = docling(pipeline)
    before = deepcopy(native)
    result, audit = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert native == before
    text = result.pages[0].content
    assert text.index('Printed heading') < text.index('Printed value') < text.index('After')
    fragment = result._table_fragments[0]
    assert fragment.cells[0].column_span == 2 and fragment.cells[0].is_column_header
    assert fragment.native_evidence['source_cells'][2]['text'] == '17'
    assert fragment.column_boundaries == []
    assert audit['pages'][0]['source_envelope'] == {'status': 'partial', 'errors': ['producer detail']}
    assert audit['pages'][0]['capabilities']['pdf_text'] is True


@pytest.mark.parametrize('pipeline', ['P03', 'P04'])
def test_paddle_preserves_native_wrapper_nullable_order_html_refs_and_media(pipeline):
    native = {'pipeline': pipeline, 'pages': [{'page': 1, 'branch': 'paddle', 'raw': {
        'res': {'width': 100, 'height': 200, 'page_index': None, 'parsing_res_list': [
            {'block_label': 'text', 'block_content': 'Before', 'block_order': None},
            {'block_label': 'table', 'block_order': None, 'block_bbox': [10, 20, 90, 100],
             'block_content': '<table><tr><th id="h" colspan="2">Ready</th></tr>'
                              '<tr><td id="a" headers="h">No</td><td>17</td></tr></table>'},
            {'block_label': 'image', 'block_content': '', 'block_bbox': [10, 110, 90, 180]},
        ]}, 'research_region_media': {'2': 'assets/own.png'},
    }}]}
    before = deepcopy(native)
    result, audit = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert native == before and result.pages[0].content.index('Before') < result.pages[0].content.index('Ready')
    blocks = result._native_page_blocks[1]
    assert blocks[0]['native_payload']['block_order'] is None
    assert blocks[-1]['asset'] == 'assets/own.png'
    assert any(ref['reference'] == 'assets/own.png' for ref in audit['asset_references'])
    original_cells = result._table_fragments[0].native_evidence['source_cells']
    assert original_cells[0]['col_span'] == 2 and original_cells[1]['native_attributes']['headers'] == 'h'
    declaration = audit['asset_references'][0]
    assert declaration['native_geometry']['normalized_bbox'] == (.1, .55, .9, .9)
    assert declaration['native_geometry']['frame'] == 'producer_output_raster'
    assert declaration['native_geometry']['input_transform'] == 'unknown'
    assert declaration['bbox'] is None and declaration['bytes_accessed'] is False
    assert result._native_content is not None
    assert audit['pages'][0]['capabilities']['pdf_text'] is False
    assert audit['pages'][0]['capabilities']['pdf_vector'] is False


@pytest.mark.parametrize('pipeline', ['P01', 'P02', 'P05', 'P06', 'P07'])
def test_each_glm_branch_uses_only_the_declared_primary_view(pipeline):
    native = {'pipeline': pipeline, 'pages': [{'page': 1, 'branch': 'glm', 'raw': {
        'json_result': [[{'label': 'text', 'content': 'Primary', 'bbox_2d': [0, 0, 1000, 1000]}]],
        'raw_json_result': [[{'label': 'text', 'content': 'Forbidden audit answer'}]],
    }}]}
    result, audit = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert result.pages[0].content == 'Primary'
    assert audit['pages'][0]['capabilities']['pdf_text'] is False
    assert audit['pages'][0]['capabilities']['model_inference'] is False


def test_glm_empty_primary_is_not_completed_from_a_favorable_markdown_or_raw_view():
    native = {'pipeline': 'P05', 'pages': [{'page': 1, 'branch': 'glm', 'raw': {
        'json_result': [[]], 'markdown_result': 'Do not supplement the empty primary',
        'raw_json_result': [[{'label': 'text', 'content': 'Do not select this answer'}]],
    }}]}
    result, _ = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert 'Do not' not in result.pages[0].content


@pytest.mark.parametrize('pipeline', ['P06', 'P07'])
def test_saved_mineru_json_keeps_pipeline_identity_and_own_continuation(pipeline):
    block = {'type': 'text', 'bbox': [.1, .1, .9, .2], 'content': [{'type': 'text', 'content': 'Native'}],
             'index': 0, 'continues_prev': True}
    native = {'pipeline': pipeline, 'documents': [{'schema': 'docvortex.middle', 'schema_version': '2.0',
              'extensions': {'mineru': {'tier': 'standard' if pipeline == 'P06' else 'advanced', 'parse_mode': 'txt'}},
              'pages': [{'page_idx': 0, 'blocks': [block]}]}],
              'pages': [{'page': 1, 'branch': 'mineru', 'raw': {'page_idx': 0, 'native_document': '#/documents/0'}}]}
    before = deepcopy(native)
    calls = []
    def project(blocks):
        calls.append(blocks)
        return [{**item, 'markdown': item['content'][0]['content']} for item in blocks], []
    # The former fixture exercised a stand-in projector, not official Typed
    # validation. Keep every original content/identity/continuation assertion
    # through the evidence-bound JSON entry and explicitly reject injection.
    with pytest.raises(ValueError, match='does not accept injected'):
        replay_native(native, source(), ContentParseOptions(), document_id='invented', mineru_projector=project)
    assert calls == []
    result, audit = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert native == before
    assert result.pages[0].content == 'Native'
    assert result._native_page_blocks[1][0]['continues_prev'] is True
    assert ('standard' if pipeline == 'P06' else 'advanced') in result.pipeline.primary
    assert audit['pages'][0]['capabilities']['pdf_vector'] is True
    assert result._native_content.pipeline == pipeline
    assert result._native_page_blocks[1][0]['source_locator']['view'] == 'docvortex.middle'
    assert audit['pages'][0]['projection'] == 'saved_json_only_not_official_typed'


def test_visual_sdk_does_not_gain_native_pdf_capabilities():
    native = {'pipeline': 'P08', 'pages': [{'page': 1, 'branch': 'visual', 'raw': [
        {'type': 'title', 'bbox': [.1, .1, .9, .2], 'content': 'Printed title'},
        {'type': 'text', 'bbox': [.1, .2, .9, .3], 'content': 'Own prose', 'merge_prev': False},
    ]}]}
    result, audit = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert 'Printed title' in result.pages[0].content and 'Own prose' in result.pages[0].content
    assert audit['pages'][0]['capabilities']['pdf_text'] is False


def test_pipeline_identity_cannot_enable_an_undeclared_native_branch():
    native = docling('P08')
    result, audit = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert audit['pages'][0]['error'] == 'saved_branch_outside_declared_pipeline'
    assert result.pages[0].status == 'failed'


@pytest.mark.parametrize('pipeline,branch', [('P05', 'glm'), ('P08', 'visual')])
def test_explicit_aria_header_roles_and_references_survive_the_consumer_projection(pipeline, branch):
    markup = '<table><tr><td role="columnheader" id="c">Amount</td></tr>'
    markup += '<tr><td headers="c" id="v">17</td></tr></table>'
    raw = ({'json_result': [[{'label': 'table', 'content': markup, 'bbox_2d': [0, 0, 1000, 1000]}]]}
           if branch == 'glm' else [{'type': 'table', 'content': markup, 'bbox': [0, 0, 1, 1]}])
    native = {'pipeline': pipeline, 'pages': [{'page': 1, 'branch': branch, 'raw': raw}]}
    result, _ = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    fragment = result._table_fragments[0]
    assert fragment.cells[0].is_column_header is True
    assert fragment.native_evidence['source_cells'][1]['native_attributes']['headers'] == 'c'
    assert fragment.column_boundaries == []


def test_all_td_layout_does_not_acquire_a_fictional_header_in_the_new_bridge():
    native = {'pipeline': 'P03', 'pages': [{'page': 1, 'branch': 'paddle', 'raw': {'res': {
        'width': 100, 'height': 100, 'parsing_res_list': [{'block_label': 'table', 'block_bbox': [0, 0, 100, 100],
            'block_content': '<table><tr><td>Status</td><td>Ready</td></tr><tr><td>Blocked</td><td>No</td></tr></table>'}]}}}]}
    result, _ = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert result._table_fragments[0].has_column_header is False
    assert not any(cell.is_column_header or cell.is_row_header for cell in result._table_fragments[0].cells)


def test_docling_plain_business_text_cannot_invent_markdown_heading_or_list_roles():
    native = docling('P01')
    native['documents'][0]['document']['texts'][0]['text'] = '# Printed hash\n- Printed dash'
    result, _ = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert '&#35; Printed hash' in result.pages[0].content
    assert '&#45; Printed dash' in result.pages[0].content
    assert result._native_page_blocks[1][-1]['text'] == '# Printed hash\n- Printed dash'


def test_malformed_saved_cell_keeps_its_literal_neighbors_and_source_object():
    native = docling('P01')
    native['documents'][0]['document']['tables'][0]['data']['table_cells'][0]['row_span'] = None
    result, audit = replay_native(native, source(), ContentParseOptions(), document_id='invented')
    assert 'Printed heading' in result.pages[0].content and 'After' in result.pages[0].content
    assert 'Printed value' in result.pages[0].content and '17' in result.pages[0].content
    assert audit['pages'][0]['local_read_errors']
    assert result._native_page_blocks[1][1]['native_payload']['data']['table_cells'][0]['row_span'] is None
