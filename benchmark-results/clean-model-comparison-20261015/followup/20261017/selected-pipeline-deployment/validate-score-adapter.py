"""No-HTTP checks for public structure decoding and frozen baseline parity."""
import copy
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('selected_score_adapter', HERE / 'score-full-cohort.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
FROZEN = M.load_frozen()
BEFORE = M.contract(FROZEN)


def marker(table_id, pages, row_count=3):
    return {
        'version': 1, 'table_id': table_id, 'source_pages': pages,
        'num_rows': row_count, 'num_cols': 3, 'encoding': 'anchor_and_blanks',
        'structure_valid': True, 'header_rows': [0, 1], 'header_scope_rows': [0, 1],
        'header_scope_complete': True, 'spans': [[0, 0, 2, 1], [0, 1, 1, 2]],
    }


def synthetic_checks():
    rows = [['项目', '原件期间', ''], ['', '本期', '上期'], ['甲', '10.00', '-9.00']]
    metadata = marker('p7_t1', [7])
    table = {'table_id': 'p7_gfm1', 'rows': rows}
    before = copy.deepcopy((table, metadata))
    cells = M.metadata_cells(table, metadata, 7)
    assert (table, metadata) == before
    assert next(cell for cell in cells if cell['text'] == '项目')['row_span'] == 2
    assert next(cell for cell in cells if cell['text'] == '原件期间')['column_span'] == 2
    assert [cell['text'] for cell in cells] == ['项目', '原件期间', '本期', '上期', '甲', '10.00', '-9.00']
    assert {cell['source_page'] for cell in cells} == {7}
    rejected = []
    for damage in ('shape', 'overlap', 'covered_text', 'invalid', 'unknown_spans'):
        broken_table, broken_meta = copy.deepcopy((table, metadata))
        if damage == 'shape':
            broken_meta['num_cols'] = 4
        elif damage == 'overlap':
            broken_meta['spans'].append([1, 0, 1, 2])
        elif damage == 'covered_text':
            broken_table['rows'][1][0] = '不可删除文字'
        elif damage == 'invalid':
            broken_meta['structure_valid'] = False
        else:
            broken_meta['spans'] = None
        try:
            M.metadata_cells(broken_table, broken_meta, 7)
        except ValueError:
            rejected.append(damage)
        else:
            raise AssertionError(damage)
    logical_id = 'table_p6_t1_p7_t1'
    logical_metadata = marker(logical_id, [6, 7], 4)
    markdown = '\n'.join([
        '<!-- page: 6 -->',
        f'<!-- logical-table: {logical_id}; source-pages: 6,7 -->',
        '<!-- table-source: p6_t1; source-page: 6; source-rows: 1-3; logical-rows: 1-3; repeated-header-rows: 0 -->',
        '<!-- table-source: p7_t1; source-page: 7; source-rows: 3-3; logical-rows: 4-4; repeated-header-rows: 2 -->',
        '<!-- table-structure: ' + json.dumps(logical_metadata, ensure_ascii=False) + ' -->',
        '| 项目 | 原件期间 |  |', '| --- | --- | --- |', '|  | 本期 | 上期 |',
        '| 甲 | 10.00 | -9.00 |', '| 乙 | 20.00 | -19.00 |',
        '<!-- page: 7 -->', '原件第7页其他正文',
    ])
    template = {'pages': [{'page_number': page, 'status': 'completed', 'tables': []} for page in (6, 7)]}
    literal, issues = FROZEN.reader.parse_final(markdown, template)
    assert not issues
    assert literal['pages'][0]['tables'][0]['header_rows'] is None
    enhanced = M.with_public_metadata(literal)
    projected = M.project_metadata_view(enhanced, FROZEN)
    for page in projected['pages']:
        [projected_table] = page['tables']
        assert projected_table['source_pages'] == [page['page_number']]
        assert projected_table['header_rows'] == [0, 1]
        assert next(cell for cell in projected_table['cells'] if cell['text'] == '项目')['row_span'] == 2
        assert next(cell for cell in projected_table['cells'] if cell['text'] == '原件期间')['column_span'] == 2
        assert projected_table['public_structure_projection_status'] == 'decoded_declared_public_source_rows'
    assert projected['pages'][1]['tables'][0]['rows'][2] == ['乙', '20.00', '-19.00']
    assert literal['pages'][0]['tables'][0]['header_rows'] is None
    return {'valid_metadata_preserves_text_and_spans': True,
            'invalid_metadata_rejected': rejected, 'logical_source_projection_preserves_spans_and_headers': True,
            'frozen_view_unmodified': True}


def parity_checks():
    root = HERE.parent / 'production-baseline'
    expected = json.loads((root / 'score-summary.json').read_text())
    manifest = {Path(item['path']).stem: item for item in FROZEN.MANIFEST['documents']}
    rows, proofs = [], []
    for case in sorted((root / 'cases').iterdir()):
        if not (case / 'result.md').exists():
            continue
        digest = M.sha(case / 'result.md')
        template = json.loads((case / 'received-MD-literal-view.json').read_text())
        for page in template['pages']:
            page['tables'] = []  # No source-side table objects or coordinates enter the reader.
        final, issues = FROZEN.reader.parse_final((case / 'result.md').read_text(), template)
        projected = FROZEN.project_public_logical_tables(final)
        scores = FROZEN.score_view(projected)
        metadata = json.loads((case / 'summary.json').read_text())
        rows.append(M.row_summary(case.name, metadata, manifest[case.name], final, scores, issues, digest))
        public = M.project_metadata_view(M.with_public_metadata(final), FROZEN)
        assert public['pages'] == projected['pages']
        assert digest == M.sha(case / 'result.md')
        proofs.append({'source': case.name, 'MD_SHA256': digest,
                       'structure_absent_does_not_change_frozen_pages': True})
    observed = M.aggregate(rows)
    for key in ('cases_scored', 'pages_scored', 'core_numeric', 'core_period_pass',
                'financial30', 'funding31', 'funding7_bound', 'supplements'):
        assert observed[key] == expected[key], (key, observed[key], expected[key])
    return {key: value for key, value in observed.items() if key != 'cases'} | {'source_proofs': proofs}


if __name__ == '__main__':
    result = {'adapter_SHA256': M.sha(HERE / 'score-full-cohort.py'),
              'validator_SHA256': M.sha(__file__),
              'synthetic': synthetic_checks(), 'original_baseline_exact_parity': parity_checks(),
              'no_HTTP_or_model_calls': True, 'frozen_contract_unchanged': M.contract(FROZEN) == BEFORE}
    assert result['frozen_contract_unchanged']
    M.save(HERE / 'scorer-validation.json', result)
    print(json.dumps({'synthetic_pass': True, 'baseline_exact_parity': True,
                      'cases': result['original_baseline_exact_parity']['cases_scored'],
                      'pages': result['original_baseline_exact_parity']['pages_scored'],
                      'frozen_files_unchanged': True}, ensure_ascii=False))
