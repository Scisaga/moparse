"""Read captured public Markdown against the independent original-PDF grids.

No parser runtime, frozen benchmark scorer, private coordinates, model output
repair, HTTP request, or inference is used. Source rectangles are not used to
select or align returned cells: source page, printed shape, and row position
must match. The one already established missing closing parenthesis is reported
separately and never counted as an exact source match.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
REPO = EVIDENCE.parents[4]
REFERENCE = EVIDENCE / 'source-independent-recheck-20261017.json'
MARKER = re.compile(r'<!-- (?:table-fragment: ([^;\s]+)|logical-table: ([^;\s]+); source-pages: ([0-9,]+)) -->')
STRUCTURE = re.compile(r'<!-- table-structure: (.*?) -->')
SOURCE = re.compile(r'<!-- table-source: ([^;]+); source-page: (\d+); source-rows: ([^;]+); logical-rows: ([^;]+); repeated-header-rows: (\d+) -->')
PAGE = re.compile(r'<!-- page: (\d+) -->')


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def compact(value):
    return re.sub(r'\s+', '', value or '')


def cells(line):
    # Exported pipes are backslash escaped; HTML entities are decoded once.
    return [html.unescape(value.strip().replace(r'\|', '|'))
            for value in re.split(r'(?<!\\)\|', line.strip()[1:-1])]


def public_tables(content):
    tables = []
    markers = list(MARKER.finditer(content))
    previous_grid_end = 0
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(content)
        segment = content[marker.end():end]
        structures = list(STRUCTURE.finditer(segment))
        grid = re.search(r'(?m)^\|[^\n]*(?:\n\|[^\n]*)*', segment)
        if len(structures) != 1 or not grid:
            raise ValueError('Each public table must have exactly one adjacent structure marker and GFM grid')
        metadata = json.loads(structures[0][1])
        lines = grid[0].splitlines()
        if len(lines) < 2 or not all(re.fullmatch(r':?-{3,}:?', v) for v in cells(lines[1])):
            raise ValueError('Missing GFM separator immediately after the first row')
        rows = [cells(line) for row, line in enumerate(lines) if row != 1]
        pages = list(PAGE.finditer(content, 0, marker.start()))
        table_id = marker[1] or marker[2]
        if metadata.get('table_id') != table_id:
            raise ValueError('Public structure/table identifiers disagree')
        tables.append({'table_id': table_id, 'logical': bool(marker[2]),
                       'marker_pages': list(map(int, marker[3].split(','))) if marker[3] else None,
                       'rendered_page': int(pages[-1][1]) if pages else None,
                       'metadata': metadata, 'rows': rows,
                       'prefix': content[previous_grid_end:marker.start()],
                       'sources': [{'fragment_id': m[1], 'page': int(m[2]),
                                    'source_rows': m[3], 'logical_rows': m[4],
                                    'repeated_header_rows': int(m[5])}
                                   for m in SOURCE.finditer(segment)]})
        previous_grid_end = marker.end() + grid.end()
    return tables


def source_grid(source):
    return [[compact(value) for value in row] for row in source['rows_raw']]


def source_spans(source, row_offset=0):
    return [[cell['row_zero_based'] + row_offset, cell['column_zero_based'],
             cell['rowspan'], cell['colspan']] for cell in source['merged_physical_cells']]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def select_table(tables, pages, row_count, column_count):
    selected = [table for table in tables
                if table['metadata'].get('source_pages') == pages
                and len(table['rows']) == row_count
                and all(len(row) == column_count for row in table['rows'])]
    require(len(selected) == 1, f'Expected one table at source pages {pages}, shape {row_count}x{column_count}; found {len(selected)}')
    table = selected[0]
    meta = table['metadata']
    require(meta.get('structure_valid') is True and meta.get('encoding') == 'anchor_and_blanks',
            'Source structure is not explicitly valid anchor-and-blanks encoding')
    require((meta.get('num_rows'), meta.get('num_cols')) == (row_count, column_count),
            'Public structure shape differs from actual GFM')
    require(table['rendered_page'] == pages[0], 'Rendered page disagrees with source page')
    if len(pages) == 1:
        require(not table['logical'] and not table['sources'], 'Independent source table was merged')
    else:
        require(table['logical'] and table['marker_pages'] == pages,
                'Continuation must have the explicit logical-table source pages')
    return table


def compare_grid(expected, actual, *, known_character_cell=None):
    result = {'positions': sum(map(len, expected)), 'exact_matches': 0,
              'known_character_defects': [], 'unexpected_mismatches': []}
    for row, values in enumerate(expected):
        for column, value in enumerate(values):
            observed = compact(actual[row][column])
            if observed == value:
                result['exact_matches'] += 1
            else:
                defect = {'row_zero_based': row, 'column_zero_based': column,
                          'source': value, 'actual': observed}
                if ((row, column) == known_character_cell and value.endswith('）')
                        and observed == value[:-1]):
                    result['known_character_defects'].append(defect)
                else:
                    result['unexpected_mismatches'].append(defect)
    return result


def check_header(table, expected):
    require([compact(v) for v in table['rows'][0]] == expected,
            'The complete printed header differs at its source row')
    meta = table['metadata']
    require(meta.get('header_scope_complete') is True
            and meta.get('header_scope_rows') == [0] and meta.get('header_rows') == [0],
            'Complete first-row header scope is not publicly retained')


def check_financial(tables, reference):
    checks = {}
    for page in (2, 3):
        source = reference[f'table_p{page}']
        expected = source_grid(source)
        table = select_table(tables, [page], source['grid_rows'], source['grid_columns'])
        check_header(table, expected[0])
        require(table['metadata']['spans'] == source_spans(source), 'Financial spans changed')
        result = compare_grid(expected, table['rows'], known_character_cell=(8, 0) if page == 3 else None)
        if page == 2:
            require(compact(reference['unit_above_p2_source_table_raw']) in compact(table['prefix']),
                    'Printed currency/unit is absent from this table context')
        checks[f'PDF_page_{page}'] = {'table_id': table['table_id'], **result}
    return {'source': reference['source'], 'tables_remain_separate': True,
            'different_complete_headers_retained_at_source_pages': True,
            'currency_unit_retained': True, 'basic_EPS_yuan_per_share_unit_retained': True,
            'positions': sum(v['positions'] for v in checks.values()),
            'exact_matches': sum(v['exact_matches'] for v in checks.values()),
            'known_character_defects': [x for v in checks.values() for x in v['known_character_defects']],
            'unexpected_mismatches': [x for v in checks.values() for x in v['unexpected_mismatches']],
            'tables': checks}


def check_funding(tables, reference):
    source = reference['source_table']
    table = select_table(tables, [reference['PDF_page']], source['grid_rows'], source['grid_columns'])
    expected = source_grid(source)
    result = compare_grid(expected, table['rows'])
    spans = source_spans(source)
    require(table['metadata']['spans'] == spans, 'Fundraising merged-cell spans differ from original PDF')
    require(compact(reference['unit_above_source_table_raw']) in compact(table['prefix']),
            'Fundraising unit is absent from its own table context')
    # All seven printed time/type/amount rows must stay at their source row and
    # under the original eight-row label span, not only somewhere in the file.
    label = reference['merged_label_cell']
    label_span = [label['row_zero_based'], label['column_zero_based'], label['rowspan'], label['colspan']]
    require(label_span in spans, 'Original fundraising label does not cover its source rows')
    bindings = []
    for row in range(2, 9):
        observed = [compact(value) for value in table['rows'][row][1:4]]
        bindings.append({'source_row_zero_based': row, 'expected': expected[row][1:4],
                         'actual': observed, 'matches': observed == expected[row][1:4],
                         'label_span_covers_row': label_span[0] <= row < label_span[0] + label_span[2]})
    return {'source': reference['source'], 'PDF_page': reference['PDF_page'],
            'table_id': table['table_id'], **result, 'merged_spans': spans,
            'all_merged_spans_equal': True, 'unit_retained': True,
            'source_nonempty_cells': reference['nonempty_source_cell_count'],
            'funding_row_bindings': bindings}


def check_continuation(tables, reference):
    first, second = source_grid(reference['table_p6']), source_grid(reference['table_p7'])
    require(first[0] == second[0], 'Independent source headers unexpectedly differ')
    expected = first + second[1:]
    table = select_table(tables, reference['PDF_pages'], len(expected), len(expected[0]))
    check_header(table, first[0])
    actual_sources = table['sources']
    expected_sources = [
        {'fragment_id': 'p6_t2', 'page': 6, 'source_rows': '1-7', 'logical_rows': '1-7', 'repeated_header_rows': 0},
        {'fragment_id': 'p7_t1', 'page': 7, 'source_rows': '2-6', 'logical_rows': '8-12', 'repeated_header_rows': 1}]
    require(actual_sources == expected_sources, 'Continuation source-row mapping or repeated-header deletion differs')
    require(not any(t['table_id'] == 'p7_t1' for t in tables), 'Repeated continuation fragment was emitted a second time')
    spans = source_spans(reference['table_p6']) + source_spans(reference['table_p7'], len(first) - 1)
    require(table['metadata']['spans'] == spans, 'Continuation merged spans were moved or removed')
    require(re.search(r'单位\s*[:：]\s*股', table['prefix']) is not None,
            'Original share unit is absent from continuation context')
    return {'source': reference['source'], 'PDF_pages': reference['PDF_pages'],
            'table_id': table['table_id'], 'body': compare_grid(expected[1:], table['rows'][1:]),
            'complete_header_positions': len(first[0]), 'complete_header_exact': True,
            'one_complete_repeated_header_removed': True,
            'source_row_mapping': actual_sources, 'source_spans': spans,
            'all_merged_spans_equal': True, 'share_unit_retained': True}


def verify(args):
    reference_bytes = args.reference.read_bytes()
    reference = json.loads(reference_bytes)
    summary_bytes = (args.input / 'summary.json').read_bytes()
    summary = json.loads(summary_bytes)
    require(isinstance(summary, list), 'Capture summary must be a list of actual completed cases')
    by_stem = {item['source']: item for item in summary}
    require(len(by_stem) == len(summary), 'Capture has duplicate source entries')
    plan_path = args.input / 'run-plan.json'
    plan = json.loads(plan_path.read_text()) if plan_path.exists() else None
    plan_sources = {item['source']: item for item in plan['sources']} if plan else {}
    result = {'schema': 'independent-PDF-grid-to-captured-public-Markdown/1',
              'created_UTC': dt.datetime.now(dt.UTC).isoformat(), 'input': str(args.input),
              'source_reference': str(args.reference), 'source_reference_SHA256': sha(reference_bytes),
              'capture_summary_SHA256': sha(summary_bytes), 'verifier_SHA256': sha(Path(__file__).read_bytes()),
              'method': 'Original-PDF source grids to positional public GFM anchors, public spans, complete header scope, and table-source row mappings; whitespace only is ignored.',
              'scope': 'Two original PDFs, source pages 2/3 and 6/7 only; no full-cohort or asset-pixel quality claim.',
              'independence': {'HTTP_requests': 0, 'model_calls': 0, 'frozen_scorers_or_gold_read': False,
                               'source_reference_modified': False, 'captured_Markdown_modified': False},
              'documents': [], 'checks': {}, 'errors': []}
    parsed = {}
    for source in reference['source_documents']:
        stem = Path(source['path']).stem
        try:
            require(stem in by_stem, f'Capture is missing required source {stem}')
            case = by_stem[stem]
            require(case['status'] == 'completed', f'{stem} was not completed')
            source_path = REPO / source['path']
            require(sha(source_path.read_bytes()) == source['SHA256'], f'Original PDF SHA differs: {stem}')
            if plan:
                require(plan_sources.get(stem, {}).get('sha256') == source['SHA256'],
                        f'Capture request source SHA differs: {stem}')
            markdown_path = args.input / 'cases' / stem / 'result.md'
            payload = markdown_path.read_bytes()
            require(sha(payload) == case['MD_SHA256'] and len(payload) == case['MD_bytes'],
                    f'Captured Markdown SHA/length differs from response capture: {stem}')
            parsed[Path(source['path']).name] = public_tables(payload.decode('utf-8'))
            result['documents'].append({'source': stem, 'source_SHA256': source['SHA256'],
                                        'job': case.get('job'), 'Markdown': str(markdown_path),
                                        'Markdown_SHA256': sha(payload), 'Markdown_bytes': len(payload),
                                        'source_pages': source['inspected_PDF_page_numbers']})
        except (ValueError, KeyError, OSError, UnicodeError) as exc:
            result['errors'].append({'source': stem, 'error': str(exc)})
    for name, key, checker in [
        ('financial', 'financial_period_headers', check_financial),
        ('funding', 'funding_merged_cell', check_funding),
        ('normal_continuation', 'matching_header_continuation', check_continuation)]:
        spec = reference[key]
        if spec['source'] not in parsed:
            continue
        try:
            check = checker(parsed[spec['source']], spec)
            result['checks'][name] = check
            differences = check.get('unexpected_mismatches', check.get('body', {}).get('unexpected_mismatches', []))
            if differences:
                result['errors'].append({'check': name, 'unexpected_source_cell_mismatches': differences})
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            result['errors'].append({'check': name, 'error': str(exc)})
    require(sha(args.reference.read_bytes()) == result['source_reference_SHA256'], 'Source reference changed during verification')
    known = result['checks'].get('financial', {}).get('known_character_defects', [])
    result['status'] = ('failed' if result['errors'] else
                        'pass_with_known_character_defect' if known else 'pass')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path, help='Actual capture directory with summary.json and cases/*/result.md')
    parser.add_argument('--reference', type=Path, default=REFERENCE)
    parser.add_argument('--output', type=Path, help='Defaults to INPUT/direct-source-recheck.json; existing output is never overwritten')
    args = parser.parse_args()
    args.input = args.input.resolve()
    args.reference = args.reference.resolve()
    output = args.output or args.input / 'direct-source-recheck.json'
    if output.exists():
        parser.error(f'Refusing to overwrite existing evidence: {output}')
    try:
        result = verify(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Input verification failed: {exc}', file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(output),
                      'errors': result['errors'],
                      'financial_positions': result['checks'].get('financial', {}).get('positions'),
                      'financial_exact': result['checks'].get('financial', {}).get('exact_matches'),
                      'funding_positions': result['checks'].get('funding', {}).get('positions'),
                      'normal_body_positions': result['checks'].get('normal_continuation', {}).get('body', {}).get('positions')}, ensure_ascii=False))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
