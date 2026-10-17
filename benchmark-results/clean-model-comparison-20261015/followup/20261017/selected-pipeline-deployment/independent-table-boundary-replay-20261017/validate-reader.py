"""Exercise the independent replay reader's preservation and rejection checks."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('independent_replay_reader_validation', HERE / 'replay.py')
replay = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = replay
spec.loader.exec_module(replay)
table = replay.load_module(HERE / 'before/table-service.py', 'independent_validation_before')


def fragment(page):
    rows = [['项目', '期间'], ['正文 \r\n保留', '10.00'], ['', ''], ['含|竖线', '-0.1']]
    cells = [table.TableCellFragment(row=r, column=c, row_span=1, column_span=1,
                                    text=value, is_column_header=r == 0)
             for r, row in enumerate(rows) for c, value in enumerate(row)]
    markdown = table.render_gfm_rows(rows)
    return table.TableFragment(
        fragment_id=f'p{page}_t1', page_number=page, ordinal=1,
        normalized_bbox=(.1, .1, .9, .9), num_rows=4, num_cols=2, rows=rows,
        column_boundaries=[.1, .5, .9], markdown=markdown,
        rendered=f'<!-- table-fragment: p{page}_t1 -->\n\n' + markdown,
        has_column_header=True, cells=cells,
    )


f = fragment(1)
parsed = replay.public_tables(f.rendered)
headers = {f.fragment_id: [0]}
checks = []
replay.assert_public_coverage(parsed, [f], headers)
assert len(parsed[0]['rows']) == 4 and parsed[0]['rows'][2] == ['', '']
checks.append('blank_source_rows_preserved')
assert parsed[0]['rows'][1][0] == '正文 保留'
checks.append('source_linebreak_and_consecutive_whitespace_only_normalization')
assert parsed[0]['rows'][3] == ['含|竖线', '-0.1']
checks.append('escaped_pipe_and_numeric_minus_preserved')


def rejects(name, mutate):
    candidate = copy.deepcopy(parsed)
    mutate(candidate)
    try:
        replay.assert_public_coverage(candidate, [f], headers)
    except (AssertionError, IndexError):
        checks.append(name)
    else:
        raise AssertionError('Independent reader accepted invalid source projection: ' + name)


rejects('missing_numeric_anchor_rejected', lambda t: t[0]['rows'][1].__setitem__(1, ''))
rejects('wrong_source_page_rejected', lambda t: t[0]['metadata'].__setitem__('source_pages', [2]))
rejects('invented_merged_span_rejected', lambda t: t[0]['metadata'].__setitem__('spans', [[1, 0, 1, 2]]))
rejects('header_role_loss_rejected', lambda t: t[0]['metadata'].__setitem__('header_rows', None))
rejects('source_row_deletion_rejected', lambda t: t[0]['rows'].pop(2))
rejects('missing_whole_table_rejected', lambda t: t.clear())

g = fragment(2)
pages = [replay.PageParseResult(page_number=item.page_number, backend='reader-validation', content=item.rendered)
         for item in [f, g]]
assembled = table.assemble_logical_tables(pages, [f, g], enabled=True)
public = [item for content in assembled.values() for item in replay.public_tables(content)]
coverage = replay.assert_public_coverage(public, [f, g], {'p1_t1': [0], 'p2_t1': [0]})
assert coverage['only_equivalent_complete_repeated_header_cells_removed'] == 2
assert len(public) == 1 and len(public[0]['rows']) == 7
checks.append('equivalent_complete_header_only_removal_with_source_row_mapping_passes')

result = {'schema': 'independent-replay-reader-validation/1', 'status': 'pass', 'checks': checks,
          'reader_SHA256': hashlib.sha256((HERE / 'replay.py').read_bytes()).hexdigest(),
          'model_calls': 0, 'HTTP_requests': 0}
(HERE / 'reader-validation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'status': 'pass', 'checks': len(checks)}))
