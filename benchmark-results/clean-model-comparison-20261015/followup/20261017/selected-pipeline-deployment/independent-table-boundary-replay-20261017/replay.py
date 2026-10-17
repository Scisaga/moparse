"""Replay frozen native Docling output through before/after export code only.

No document conversion, OCR, network request or model construction occurs.
Frozen cell anchors, roles and spans are independently compared with every
exported fragment and every assembled public GFM anchor/structure marker.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
REPO = EVIDENCE.parents[4]
sys.path.insert(0, str(REPO))

from app.models.parse_result import PageParseResult  # noqa: E402
from docling_core.types.doc import DoclingDocument, TableItem  # noqa: E402

BASELINE_REF = '6e645e1091fd2d6a35cfec55f3e157e60dbe4572'
MARKER = re.compile(r'<!-- (?:table-fragment: ([^;\s]+)|logical-table: ([^;\s]+); source-pages: ([0-9,]+)) -->')
STRUCTURE = re.compile(r'<!-- table-structure: (.*?) -->')
SOURCE = re.compile(r'<!-- table-source: ([^;]+); source-page: (\d+); source-rows: ([^;]+); logical-rows: ([^;]+); repeated-header-rows: (\d+) -->')


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def text(value):
    return re.sub(r'\s+', ' ', value).strip()


def no_space(value):
    return re.sub(r'\s+', '', value)


def split_gfm(line):
    values = re.split(r'(?<!\\)\|', line.strip()[1:-1])
    return [text(html.unescape(value.strip().replace(r'\|', '|'))) for value in values]


def indices(value):
    if value == 'none':
        return []
    if re.fullmatch(r'\d+-\d+', value):
        start, end = map(int, value.split('-'))
        return list(range(start, end + 1))
    return list(map(int, value.split(',')))


def public_tables(content):
    """Read the actual exported GFM and adjacent public structure comments."""
    output = []
    markers = list(MARKER.finditer(content))
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(content)
        segment = content[marker.end():end]
        structure = STRUCTURE.search(segment)
        matrix = re.search(r'(?m)^\|[^\n]*(?:\n\|[^\n]*)*', segment)
        if not matrix or not structure:
            raise ValueError('Table marker has no adjacent GFM/structure')
        lines = matrix[0].splitlines()
        if len(lines) < 2 or not all(re.fullmatch(r':?-{3,}:?', value)
                                    for value in split_gfm(lines[1])):
            raise ValueError('GFM header separator is missing')
        # Blank model rows are source structure, not GFM separators. Only the
        # second physical line is the declared header separator.
        rows = [split_gfm(line) for index, line in enumerate(lines) if index != 1]
        output.append({'table_id': marker[1] or marker[2],
                       'metadata': json.loads(structure[1]), 'rows': rows,
                       'sources': [{'fragment_id': match[1], 'page': int(match[2]),
                                    'source_rows': match[3], 'logical_rows': match[4],
                                    'skip': int(match[5])} for match in SOURCE.finditer(segment)]})
    return output


def source_cells(table):
    return [{'row': cell.start_row_offset_idx, 'column': cell.start_col_offset_idx,
             'row_span': cell.row_span, 'column_span': cell.col_span,
             'text': cell.text or '', 'is_column_header': bool(cell.column_header),
             'is_row_header': bool(cell.row_header)} for cell in table.data.table_cells]


def canonical_fragment(fragment):
    return {'fragment_id': fragment.fragment_id, 'page': fragment.page_number,
            'rows': fragment.rows, 'num_rows': fragment.num_rows, 'num_cols': fragment.num_cols,
            'cells': [{key: getattr(cell, key) for key in
                       ('row', 'column', 'row_span', 'column_span', 'text',
                        'is_column_header', 'is_row_header')} for cell in fragment.cells],
            'header_rows': list(fragment.header_row_indices), 'caption': fragment.caption,
            'unit_text': fragment.unit_text, 'valid': fragment.valid,
            'bbox': list(fragment.normalized_bbox)}


def narrative(content):
    without_gfm = re.sub(r'(?m)^\|[^\n]*(?:\n\|[^\n]*)*', '', content)
    return no_space(re.sub(r'<!--.*?-->', '', without_gfm, flags=re.S))


def assert_public_coverage(tables, fragments, frozen_header_rows):
    """Map every source anchor into its emitted logical position, independent of linker."""
    by_id = {fragment.fragment_id: fragment for fragment in fragments}
    seen, allowed_headers_removed, anchor_count = set(), 0, 0
    for table in tables:
        meta = table['metadata']
        mappings = table['sources'] or [
            {'fragment_id': table['table_id'], 'page': by_id[table['table_id']].page_number,
             'skip': 0}]
        expected_rows, expected_spans, expected_header_anchors = [], [], set()
        expected_source_pages = []
        for mapping in mappings:
            fid, skip = mapping['fragment_id'], mapping['skip']
            if fid in seen:
                raise AssertionError(f'Duplicate source table projection {fid}')
            seen.add(fid)
            fragment = by_id[fid]
            expected_source_pages.append(fragment.page_number)
            if mapping['page'] != fragment.page_number:
                raise AssertionError('Source page association changed')
            headers = frozen_header_rows[fid]
            if skip and (headers != list(range(skip)) or fid == mappings[0]['fragment_id']):
                raise AssertionError('Deleted rows extend outside the frozen complete repeated header')
            if skip:
                first = by_id[mappings[0]['fragment_id']]
                expected = [first.rows[row] for row in frozen_header_rows[first.fragment_id]]
                observed = fragment.rows[:skip]
                if [[no_space(v) for v in row] for row in observed] != [[no_space(v) for v in row] for row in expected]:
                    raise AssertionError('Removed header text is not fully repeated')
                def head_cells(item, depth):
                    return sorted((c.row, c.column, c.row_span, c.column_span,
                                   no_space(c.text), c.is_column_header, c.is_row_header)
                                  for c in item.cells if c.row < depth)
                if head_cells(first, len(expected)) != head_cells(fragment, skip):
                    raise AssertionError('Removed header spans/roles differ')
            offset = len(expected_rows)
            expected_rows.extend([[text(value) for value in row] for row in fragment.rows[skip:]])
            for cell in fragment.cells:
                if cell.row < skip:
                    allowed_headers_removed += 1
                    continue
                row = offset + cell.row - skip
                anchor_count += 1
                if cell.is_column_header:
                    expected_header_anchors.add(row)
                if cell.row_span > 1 or cell.column_span > 1:
                    expected_spans.append([row, cell.column, cell.row_span, cell.column_span])
                if text(cell.text) != table['rows'][row][cell.column]:
                    raise AssertionError(f'Source anchor text absent/moved: {fid} {cell.row},{cell.column}')
            if mapping.get('source_rows') is not None:
                if indices(mapping['source_rows']) != list(range(skip + 1, len(fragment.rows) + 1)):
                    raise AssertionError('Source row range changed')
                if indices(mapping['logical_rows']) != list(range(offset + 1, len(expected_rows) + 1)):
                    raise AssertionError('Logical row range changed')
        if expected_rows != table['rows']:
            raise AssertionError('Visible GFM matrix differs from original anchored cells')
        expected_shape = (len(expected_rows), len(expected_rows[0]))
        if expected_shape != (meta['num_rows'], meta['num_cols']):
            raise AssertionError('Public structure shape changed')
        if sorted(set(expected_source_pages)) != meta['source_pages']:
            raise AssertionError('Public source pages changed')
        if expected_spans != meta['spans']:
            raise AssertionError('Merged cell spans lost/moved')
        if (sorted(expected_header_anchors) or None) != meta['header_rows']:
            raise AssertionError('Source column-header roles lost/moved')
        first_headers = frozen_header_rows[mappings[0]['fragment_id']]
        if (first_headers or None) != meta['header_scope_rows']:
            raise AssertionError('Complete header scope changed')
    if seen != set(by_id):
        raise AssertionError(f'Source tables absent from public GFM: {set(by_id) - seen}')
    return {'all_source_tables_projected_once': True, 'emitted_source_cell_anchors': anchor_count,
            'only_equivalent_complete_repeated_header_cells_removed': allowed_headers_removed,
            'source_rows_text_spans_header_roles_and_pages_preserved': True}


def replay(args):
    started = time.monotonic()
    audit_path = EVIDENCE / 'table-export-source-audit.json'
    routing_path = EVIDENCE / 'routing-source-properties-audit.json'
    audit_bytes, routing_bytes = audit_path.read_bytes(), routing_path.read_bytes()
    audit, routing = json.loads(audit_bytes), json.loads(routing_bytes)
    native = {}
    for item in routing['pages']:
        if item['frozen_route'] == 'native':
            native.setdefault(Path(item['document']).stem, set()).add(item['page_number'])
    output = HERE / args.phase
    if output.exists():
        raise ValueError('Refusing to overwrite a prior replay phase')
    output.mkdir()
    if args.phase == 'before':
        code = subprocess.check_output(['git', 'show', BASELINE_REF + ':app/services/table_service.py'], cwd=REPO)
    else:
        code = (REPO / 'app/services/table_service.py').read_bytes()
        if not args.expected_sha or sha(code) != args.expected_sha:
            raise ValueError('After module must match the explicitly reviewed final SHA')
    snapshot = output / 'table-service.py'
    snapshot.write_bytes(code)
    module = load_module(snapshot, 'independent_table_boundary_' + args.phase)
    summary = {'schema': 'frozen-native-table-export-replay/1', 'phase': args.phase,
               'before_git_ref': BASELINE_REF, 'table_service_SHA256': sha(code),
               'docling_core_version': importlib.metadata.version('docling-core'),
               'frozen_audit_SHA256': sha(audit_bytes), 'frozen_routing_SHA256': sha(routing_bytes),
               'documents': [], 'model_calls': 0, 'HTTP_requests': 0,
               'scope': 'All ten PDFs; only 433 frozen native source pages, 632 native tables. Scanned/mixed model outputs are not replayed or claimed re-evaluated.'}
    for doc in audit['documents']:
        source = Path(doc['document']).stem
        path = REPO / doc['raw_docling_path']
        raw = path.read_bytes()
        if sha(raw) != doc['raw_docling_SHA256']:
            raise AssertionError('Frozen raw Docling document changed')
        document = DoclingDocument.model_validate_json(raw)
        selected = native.get(source, set())
        fragments = [fragment for fragment in module.extract_table_fragments(document, (1, len(document.pages)))
                     if fragment.page_number in selected]
        source_items = [item for item, _ in document.iterate_items()
                        if isinstance(item, TableItem) and item.prov and item.prov[0].page_no in selected]
        if len(fragments) != doc['runtime_native_table_fragments'] or len(fragments) != len(source_items):
            raise AssertionError('Frozen table population changed')
        table_records, fragment_snapshots = [], []
        frozen_header_rows = {item['fragment']: item['complete_runtime_header_rows']
                              for item in audit['tables'] if item['document'] == doc['document']}
        for fragment, source_item in zip(fragments, source_items, strict=True):
            record = canonical_fragment(fragment)
            if record['cells'] != source_cells(source_item):
                raise AssertionError('Raw model cell text/span/header roles changed')
            if record['header_rows'] != frozen_header_rows[fragment.fragment_id]:
                raise AssertionError('Complete source header scope differs from frozen audit')
            for cell in record['cells']:
                if fragment.rows[cell['row']][cell['column']] != cell['text']:
                    raise AssertionError('Raw cell anchor text missing from exported matrix')
            fragment_snapshots.append(record)
            table_records.append({'fragment_id': fragment.fragment_id, 'source_ref': source_item.self_ref,
                                  'page': fragment.page_number, 'raw_cell_count': len(record['cells']),
                                  'span_cells': sum(c['row_span'] > 1 or c['column_span'] > 1 for c in record['cells']),
                                  'rows_SHA256': digest(record['rows']), 'cells_SHA256': digest(record['cells']),
                                  'header_rows': record['header_rows'], 'caption': record['caption'],
                                  'unit_text': record['unit_text'], 'source_anchor_text_spans_roles_equal': True})
        pages = [PageParseResult(page_number=number, backend='frozen-docling-output',
                                content=module.export_page_markdown(document, number, fragments))
                 for number in sorted(selected)]
        exported = {page.page_number: page.content for page in pages}
        precoverage = assert_public_coverage([table for page in pages for table in public_tables(page.content)],
                                            fragments, frozen_header_rows)
        candidate_groups = module.link_cross_page_tables(fragments)
        contexts = []
        for group in candidate_groups:
            for left, right in zip(group, group[1:], strict=False):
                contexts.append({'left': left.fragment_id, 'right': right.fragment_id,
                                 'left_tail': exported[left.page_number].partition(left.rendered)[2],
                                 'right_head': exported[right.page_number].partition(right.rendered)[0],
                                 'left_caption': left.caption, 'right_caption': right.caption,
                                 'left_bbox': list(left.normalized_bbox), 'right_bbox': list(right.normalized_bbox)})
        assembled = module.assemble_logical_tables(pages, fragments, enabled=True)
        groups = {}
        for fragment in fragments:
            if fragment.logical_table_id:
                groups.setdefault(fragment.logical_table_id, []).append(fragment.fragment_id)
        if any(narrative(exported[number]) != narrative(assembled[number]) for number in exported):
            raise AssertionError('Non-table narrative changed during logical assembly')
        coverage = assert_public_coverage([table for content in assembled.values() for table in public_tables(content)],
                                         fragments, frozen_header_rows)
        location = output / source
        save(location / 'fragments.json', fragment_snapshots)
        save(location / 'exported-pages.json', exported)
        save(location / 'assembled-pages.json', assembled)
        save(location / 'boundary-contexts.json', contexts)
        row = {'source': source, 'raw_path': str(path), 'raw_SHA256': sha(raw),
               'native_pages': len(selected), 'table_count': len(fragments),
               'cell_count': sum(item['raw_cell_count'] for item in table_records),
               'span_cell_count': sum(item['span_cells'] for item in table_records),
               'tables': table_records, 'candidate_groups': [[f.fragment_id for f in g] for g in candidate_groups],
               'actual_groups': groups, 'pre_assembly_public_coverage': precoverage,
               'assembled_public_coverage': coverage,
               'non_table_narrative_preserved': True}
        summary['documents'].append(row)
        print(json.dumps({'phase': args.phase, 'source': source, 'native_pages': len(selected),
                          'tables': len(fragments), 'logical_groups': len(groups)}), flush=True)
    summary.update(native_pages=sum(d['native_pages'] for d in summary['documents']),
                   table_count=sum(d['table_count'] for d in summary['documents']),
                   cell_count=sum(d['cell_count'] for d in summary['documents']),
                   span_cell_count=sum(d['span_cell_count'] for d in summary['documents']),
                   logical_group_count=sum(len(d['actual_groups']) for d in summary['documents']),
                   wall_seconds=time.monotonic() - started,
                   created_UTC=dt.datetime.now(dt.timezone.utc).isoformat(),
                   replay_script_SHA256=sha(Path(__file__).read_bytes()))
    if (summary['native_pages'], summary['table_count'], summary['cell_count']) != (433, 632, 20569):
        raise AssertionError('Full frozen native cohort coverage was not reached')
    if audit_path.read_bytes() != audit_bytes or routing_path.read_bytes() != routing_bytes:
        raise AssertionError('Frozen historical evidence changed')
    save(output / 'summary.json', summary)
    print(json.dumps({key: summary[key] for key in ['phase', 'native_pages', 'table_count', 'cell_count',
          'span_cell_count', 'logical_group_count', 'wall_seconds']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['before', 'after'], required=True)
    parser.add_argument('--expected-sha', help='Required immutable reviewed table_service SHA for after phase')
    replay(parser.parse_args())


if __name__ == '__main__':
    main()
