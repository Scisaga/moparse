"""Hand-authored engineering assertions from the two fixed native JSON inputs.

No expected/corpus answer is used. These assert native-to-delivered handoff,
not parser accuracy. Input walks and relationship checks run separately.
"""
from __future__ import annotations

SAMPLE = 'vanke-repurchase-share-changes-p001-003'
HEADERS = {1: [(0, 1), (1, 1)], 2: [(0, 1), (1, 2)], 3: [(0, 3)],
           4: [(0, 4), (1, 4)], 5: [(0, 4), (1, 5)]}
VALUES = {
    2: ['15,386,999', '0.14%', '', '15,848,774', '0.14%'],
    4: ['9,718,459,333', '87.96%', '12,480,299', '9,708,327,759', '87.94%'],
    5: ['1,314,955,468', '11.90%', '', '1,314,955,468', '11.91%'],
    6: ['11,033,414,801', '99.86%', '12,480,299', '11,023,283,227', '99.86%'],
    7: ['11,048,801,800', '100.00%', '12,480,299', '11,039,132,001', '100.00%'],
}


def accept_fixed_native_output(native, evidence, final):
    """Assert actual emitted bytes and source relations using fixed source facts."""
    pipeline = native['pipeline']
    assert pipeline in {'P01', 'P05'} and evidence['pipeline'] == pipeline
    assert evidence['sample_id'] == SAMPLE
    assert evidence['status'] == ('partial' if pipeline == 'P01' else 'completed')
    assert evidence['stages'][-1]['markdown'] == final
    assert evidence['states']['original_execution']['status'] == 'completed'
    assert [p['status'] for p in evidence['states']['original_execution']['pages']] == ['completed'] * 3
    assert evidence['states']['readback']['status'] == 'read'
    assert evidence['states']['conversion']['status'] == 'completed'
    assert evidence['states']['delivery']['media']['declared'] == (2 if pipeline == 'P01' else 0)
    assert final.count('图片未交付。') == (2 if pipeline == 'P01' else 0)
    assert '<!--' not in final
    assert len(evidence['semantic_tables']) == 1
    view = evidence['semantic_tables'][0]
    assert view['status'] == 'converted'
    assert [r['source_row'] for r in view['records']] == list(VALUES)
    fragment = evidence['table_fragments'][0]
    cells = {(c['row'], c['column']): c for c in fragment['cells']}
    assert (fragment['num_rows'], fragment['num_cols']) == (8, 6)
    assert len(cells) == (45 if pipeline == 'P01' else 44)
    assert (cells[0, 1]['column_span'], cells[0, 3]['row_span'], cells[0, 4]['column_span']) == (2, 2, 2)
    assert '2015' in cells[0, 1]['text'] and '2016' in cells[0, 4]['text']
    assert cells[0, 0]['row_span'] == (1 if pipeline == 'P01' else 2)
    for record in view['records']:
        row = record['source_row']
        assert [(v['value']['row'], v['value']['column']) for v in record['values']] == [(row, c) for c in range(1, 6)]
        assert (record['subject']['row'], record['subject']['column']) == (row, 0)
        for col, relation in enumerate(record['values'], 1):
            # Strip only for this assertion; original cell bytes are checked
            # separately, including P01's trailing spaces and CRLF headings.
            assert cells[row, col]['text'].strip() == VALUES[row][col - 1]
            assert [(h['row'], h['column']) for h in relation['column_headers']] == HEADERS[col]
            rows = [(3, 0), (row, 0)] if row in {4, 5, 6} else [(row, 0)]
            assert [(h['row'], h['column']) for h in relation['row_headers']] == rows
            assert all(ref['table_id'] == fragment['fragment_id'] for ref in (
                relation['value'], *relation['row_headers'], *relation['column_headers']))
            assert [(p['row'], p['column']) for p in relation['period_refs']] == (
                [(0, 1)] if col in {1, 2} else [(0, 4)] if col in {4, 5} else [])
    assert len(evidence['relation_checks']) == 25
    table_disposition = next(d for d in evidence['content_dispositions'] if d['classification'] == 'data_table')
    assert len(table_disposition['cells']) == len(cells)
    for cell in table_disposition['cells']:
        assert cell['disposition'] in {'located_in_final', 'empty_literal_not_filled'}
        for (a, b), actual in zip(cell['final_spans'], cell['actual_renderings'], strict=True):
            assert final[a:b] == actual
    if pipeline == 'P05':
        note_path = '#/pages/1/raw/json_result/0/3'
        note = next(d for d in evidence['content_dispositions'] if d['native_path'] == note_path)
        assert note['classification'] == 'text' and note['disposition'] == 'retained'
        assert '2,810,500股' in note['raw_text']
        assert all('2,810,500股' in final[a:b] for a, b in note['final_spans'])
        assert fragment['native_evidence']['source_binding']['view'] == 'json_result'
        assert fragment['native_evidence']['source_binding']['path'] == '#/pages/1/raw/json_result/0/2'
    else:
        assert fragment['native_evidence']['source_binding']['view'] == 'document'
        assert fragment['native_evidence']['source_binding']['path'] == '#/documents/0/document/tables/0'
    return {'sample_id': SAMPLE, 'pipeline': pipeline, 'status': 'accepted_engineering_scope',
            'parser_quality_grade': None, 'source_records': list(VALUES),
            'value_relationships_checked': 25, 'source_cells': len(cells),
            'actual_note_preserved': pipeline == 'P05', 'media_bytes_verified': False}
