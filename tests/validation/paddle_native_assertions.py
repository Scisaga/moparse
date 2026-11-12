"""Independent fixed-input normalization assertions, authored from Paddle JSON.

No corpus answer or other pipeline output supplies content. These checks do
not measure parser quality; P03 and P04 keep their own source literals.
"""
from __future__ import annotations

SAMPLE = 'vanke-repurchase-share-changes-p001-003'
VALUES = {
    2: ['15,386,999', '0.14%', '', '15,848,774', '0.14%'],
    4: ['9,718,459,333', '87.96%', '12,480,299', '9,708,327,759', '87.94%'],
    5: ['1,314,955,468', '11.90%', '', '1,314,955,468', '11.91%'],
    6: ['11,033,414,801', '99.86%', '12,480,299', '11,023,283,227', '99.86%'],
    7: ['11,048,801,800', '100.00%', '12,480,299', '11,039,132,001', '100.00%'],
}
HEADER_PATHS = {1: [(0, 1), (1, 1)], 2: [(0, 1), (1, 2)], 3: [(0, 3)],
                4: [(0, 4), (1, 4)], 5: [(0, 4), (1, 5)]}
SOURCE_HEADERS = {
    'P03': ['本次回购前（2015年8月31日）', '本次回购后拟注销数量', '本次回购股份注销后（2016年1月14日）'],
    'P04': ['本次回购前' + chr(92) + 'n（2015 年 8 月 31 日）',
            '本次回购后' + chr(92) + 'n拟注销数量',
            '本次回购股份注销后' + chr(92) + 'n（2016 年 1 月 14 日）'],
}
BODY_LITERAL = {'P03': '证券简称：万科 A、万科 H 代', 'P04': '证券简称：万科A、万科H代'}


def accept_fixed_paddle_output(native, evidence, final):
    pipeline = native['pipeline']
    assert pipeline in {'P03', 'P04'} and evidence['pipeline'] == pipeline
    assert evidence['sample_id'] == SAMPLE
    assert evidence['status'] == 'partial' and evidence['stages'][-1]['markdown'] == final
    assert evidence['states']['original_execution']['status'] == 'completed'
    assert [p['status'] for p in evidence['states']['original_execution']['pages']] == ['completed'] * 3
    assert evidence['states']['readback']['status'] == 'read'
    assert evidence['states']['conversion']['status'] == 'partial'
    assert evidence['states']['delivery']['media']['declared'] == 3
    assert evidence['states']['delivery']['media']['delivered'] == 0
    assert final.count('图片未交付。') == 3 and '<!--' not in final
    assert [len(p['raw']['res']['parsing_res_list']) for p in native['pages']] == [14, 14, 3]
    native_blocks = evidence['native_blocks']
    for page in native['pages']:
        number = page['page']
        raw = page['raw']['res']
        assert (raw['width'], raw['height'], raw['page_index'], raw['page_count']) == (1654, 2339, None, None)
        assert raw['model_settings']['use_doc_preprocessor'] is False
        adapted = native_blocks.get(str(number), native_blocks.get(number))
        assert len(adapted) == len(raw['parsing_res_list'])
        for index, (node, block) in enumerate(zip(raw['parsing_res_list'], adapted, strict=True)):
            path = f'#/pages/{number-1}/raw/res/parsing_res_list/{index}'
            assert block['native_path'] == path and block['id'] == path
            assert block['native_payload'] == node and block['text'] == node['block_content']
            assert block['native_block_id'] == node['block_id'] and block['native_block_order'] == node['block_order']
            assert block['native_group_id'] == node['group_id']
            assert block['group_identity']['input_page'] == number and block['parent_id'] is None
            assert block['group_identity']['parent_relationship'] == 'unknown'
            assert block['order_basis'] == 'native_array_order_unknown_reading_order'
            assert block['polygon'] == node['block_polygon_points'] and block['bbox'] == node['block_bbox']
            assert block['coordinate_system'] == 'pixel' and block['coordinate_origin'] == 'TOPLEFT'
            assert block['page_dimensions'] == {'width': 1654, 'height': 2339, 'unit': 'pixel'}
            assert block['geometry_basis']['original_pdf_transform'] == 'unknown'
            assert block['branch_page'] is None and block['page'] == block['original_pdf_page'] == number
            assert block['source_locator']['view'] == 'res.parsing_res_list'
    assert BODY_LITERAL[pipeline] in final
    assert len(evidence['semantic_tables']) == len(evidence['table_fragments']) == 1
    view = evidence['semantic_tables'][0]
    fragment = evidence['table_fragments'][0]
    assert view['status'] == 'converted' and [r['source_row'] for r in view['records']] == list(VALUES)
    assert (fragment['num_rows'], fragment['num_cols']) == (8, 6)
    assert len(fragment['cells']) == len(fragment['native_evidence']['source_cells']) == 44
    cells = {(c['row'], c['column']): c for c in fragment['cells']}
    assert [cells[0, c]['text'] for c in (1, 3, 4)] == SOURCE_HEADERS[pipeline]
    assert [cells[0, c]['column_span'] for c in (0, 1, 3, 4)] == [1, 2, 1, 2]
    assert [cells[0, c]['row_span'] for c in (0, 1, 3, 4)] == [2, 1, 2, 1]
    assert not any(c['is_column_header'] for c in fragment['cells'])  # actual HTML uses td only
    for cell in fragment['native_evidence']['source_cells']:
        assert cell['source_locator']['kind'] == 'primary_html_projection'
        assert cell.get('bbox') is None and cell.get('polygon') is None
        assert cell['evidence_locator']['view'] == 'res.parsing_res_list'
    for record in view['records']:
        row = record['source_row']
        assert [(v['value']['row'], v['value']['column']) for v in record['values']] == [(row, c) for c in range(1, 6)]
        assert (record['subject']['row'], record['subject']['column']) == (row, 0)
        for col, relation in enumerate(record['values'], 1):
            assert cells[row, col]['text'] == VALUES[row][col - 1]
            assert [(r['row'], r['column']) for r in relation['column_headers']] == HEADER_PATHS[col]
            row_path = [(3, 0), (row, 0)] if row in {4, 5, 6} else [(row, 0)]
            assert [(r['row'], r['column']) for r in relation['row_headers']] == row_path
            assert [(r['row'], r['column']) for r in relation['period_refs']] == (
                [(0, 1)] if col in {1, 2} else [(0, 4)] if col in {4, 5} else [])
            assert not relation['unit_refs'] and not relation['note_refs']
    assert len(evidence['relation_checks']) == 25
    table = next(d for d in evidence['content_dispositions'] if d['classification'] == 'data_table')
    assert len(table['cells']) == 44
    assert sum(c['disposition'] == 'located_in_final' for c in table['cells']) == 37
    assert sum(c['disposition'] == 'empty_literal_not_filled' for c in table['cells']) == 7
    for cell in table['cells']:
        for (a, b), printed in zip(cell['final_spans'], cell['actual_renderings'], strict=True):
            assert final[a:b] == printed
    paths = {d['native_path']: d for d in evidence['content_dispositions']}
    note = paths['#/pages/1/raw/res/parsing_res_list/3']
    assert note['classification'] == 'text' and note['disposition'] == 'retained'
    assert all('2,810,500股' in final[a:b] for a, b in note['final_spans'])
    number = paths['#/pages/1/raw/res/parsing_res_list/12']
    assert number['classification'] == 'text' and number['disposition'] == 'retained'
    assert number['raw_text'] == '万科企业股份有限公司'
    assert all(number['raw_text'] in final[a:b] for a, b in number['final_spans'])
    assert all(d['disposition'] in {'retained', 'converted', 'unresolved_media_delivery'} for d in paths.values())
    assert all(c['equal'] for c in evidence['format_readback_checks'])
    return {'pipeline': pipeline, 'scope': SAMPLE, 'status': 'accepted_native_format_and_bounded_conversion',
            'delivery': 'partial', 'native_regions': 31, 'polygons_preserved': 31,
            'html_projection_cells': 44, 'located_nonempty_cells': 37, 'literal_empty_cells': 7,
            'value_relations': 25, 'undelivered_media_occurrences': 3,
            'global_reading_order': 'unknown', 'group_parentage': 'unknown', 'quality_grade': None}
