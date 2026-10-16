"""Score received public Markdown with frozen and metadata-aware views separately.

Frozen scorers, gold and the original Markdown remain untouched. Additional
structure decoding uses only validated public table-structure comments and GFM
anchors; any score difference is output observability, not a model improvement.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[2]
REPO = OLD.parents[1]
FROZEN_ADAPTER = HERE.parent / 'production-baseline' / 'score-baseline.py'
STRUCTURE = re.compile(r'<!-- table-structure: (.*?) -->')
FRAGMENT = re.compile(r'<!-- table-fragment: ([^; ]+) -->')
LOGICAL = re.compile(r'<!-- logical-table: ([^; ]+); source-pages: ([0-9,]+) -->')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def load_frozen():
    spec = importlib.util.spec_from_file_location('selected_frozen_baseline', FROZEN_ADAPTER)
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    return frozen


def contract(frozen):
    modules = [frozen.reader, frozen.core, frozen.scope, frozen.calendar,
               frozen.supplement, frozen.source130, frozen.source28,
               frozen.continuation, frozen.stock]
    paths = {Path(value.__file__) for value in modules}
    paths.update([
        FROZEN_ADAPTER, OLD / 'input-manifest.json',
        REPO / 'pdf_sample/gold/table_fact_gold_v1.json',
        OLD / 'scoring/supplemental/source-only-tables.json',
        OLD / 'scoring/supplemental/130-merged-source-only.json',
        OLD / 'scoring/source28-original-only.json',
        OLD / 'scoring/same-header-continuation-source.json',
        OLD / 'scoring/critical-shareholder-source.json',
    ])
    paths.update((OLD / 'scoring').glob('*contract-lock*.json'))
    return [{'path': str(path), 'SHA256': sha(path)} for path in sorted(paths)]


def metadata_per_table(page):
    output, pending, in_table = [], None, False
    reference = None
    for line in page['markdown'].splitlines():
        marker = STRUCTURE.fullmatch(line.strip())
        fragment, logical = FRAGMENT.fullmatch(line.strip()), LOGICAL.fullmatch(line.strip())
        if fragment:
            reference = {'table_id': fragment[1], 'source_pages': [page['page_number']]}
        if logical:
            reference = {'table_id': logical[1], 'source_pages': list(map(int, logical[2].split(',')))}
        if marker:
            try:
                pending = json.loads(marker[1])
            except json.JSONDecodeError:
                pending = {'invalid_JSON': True}
        if line.lstrip().startswith('|'):
            if not in_table:
                output.append((pending, reference))
                pending = None
                reference = None
            in_table = True
        else:
            in_table = False
    if len(output) != len(page['tables']):
        raise ValueError('Public structure table order differs from frozen GFM groups')
    return output


def metadata_cells(table, metadata, page_number):
    if not isinstance(metadata, dict) or metadata.get('version') != 1:
        raise ValueError('Absent or unsupported public table structure')
    if metadata.get('encoding') != 'anchor_and_blanks' or metadata.get('structure_valid') is not True:
        raise ValueError('Public structure is explicitly unknown or invalid')
    rows = table['rows']
    height, width = len(rows), max(map(len, rows), default=0)
    if (type(metadata.get('num_rows')) is not int or type(metadata.get('num_cols')) is not int
            or metadata['num_rows'] != height or metadata['num_cols'] != width
            or any(len(row) != width for row in rows)):
        raise ValueError('Public shape disagrees with visible GFM')
    if not isinstance(metadata.get('table_id'), str) or not metadata['table_id']:
        raise ValueError('Public table ID is missing')
    spans = metadata.get('spans')
    if not isinstance(spans, list):
        raise ValueError('Public span list is unknown')
    header_rows = metadata.get('header_rows')
    if header_rows is not None and (
        not isinstance(header_rows, list) or len(set(header_rows)) != len(header_rows)
        or any(type(row) is not int or not 0 <= row < height for row in header_rows)
    ):
        raise ValueError('Public header rows are invalid')
    pages = metadata.get('source_pages')
    if (not isinstance(pages, list) or not pages or len(set(pages)) != len(pages)
            or any(type(page) is not int or page <= 0 for page in pages)):
        raise ValueError('Public source pages are invalid')
    occupied, covered, anchors = set(), set(), {}
    for span in spans:
        if (not isinstance(span, list) or len(span) != 4
                or any(type(value) is not int for value in span)):
            raise ValueError('Public span is not four integer coordinates')
        row, column, row_span, column_span = span
        if (row < 0 or column < 0 or row_span < 1 or column_span < 1
                or row + row_span > height or column + column_span > width):
            raise ValueError('Public span lies outside the visible table')
        positions = {(r, c) for r in range(row, row + row_span)
                     for c in range(column, column + column_span)}
        if occupied & positions:
            raise ValueError('Public spans overlap')
        hidden = positions - {(row, column)}
        if any(rows[r][c].strip() for r, c in hidden):
            raise ValueError('Public span would hide nonempty visible GFM content')
        occupied.update(positions)
        covered.update(hidden)
        anchors[(row, column)] = (row_span, column_span)
    cells = []
    for row, values in enumerate(rows):
        for column, text in enumerate(values):
            if (row, column) in covered:
                continue
            row_span, column_span = anchors.get((row, column), (1, 1))
            if text or (row, column) in anchors:
                cells.append({
                    'row': row, 'column': column, 'row_span': row_span,
                    'column_span': column_span, 'text': text,
                    'is_column_header': row in header_rows if header_rows is not None else None,
                    'is_row_header': None, 'source_page': page_number,
                })
    return cells


def with_public_metadata(final):
    out = copy.deepcopy(final)
    audit = []
    for page in out['pages']:
        for table, (metadata, reference) in zip(page['tables'], metadata_per_table(page), strict=True):
            item = {'page': page['page_number'], 'visible_table_id': table['table_id']}
            try:
                if reference and isinstance(metadata, dict) and any(
                    metadata.get(key) != reference[key] for key in ('table_id', 'source_pages')
                ):
                    raise ValueError('Structure metadata disagrees with adjacent public table/source reference')
                cells = metadata_cells(table, metadata, page['page_number'])
                table.update(table_id=metadata['table_id'], cells=cells,
                             header_rows=copy.deepcopy(metadata['header_rows']),
                             source_pages=copy.deepcopy(metadata['source_pages']),
                             span_representation='validated_public_table_structure',
                             public_structure_metadata=copy.deepcopy(metadata))
                item.update(status='decoded', table_id=metadata['table_id'],
                            span_count=len(metadata['spans']),
                            declared_header_rows=metadata['header_rows'],
                            header_scope_complete=metadata.get('header_scope_complete'))
            except (ValueError, TypeError, KeyError) as error:
                item.update(status='unknown_unchanged_frozen_view', reason=str(error))
            audit.append(item)
    out['public_structure_audit'] = {
        'tables': audit, 'status_counts': dict(Counter(item['status'] for item in audit)),
        'source': 'Public table-structure comments plus visible GFM anchors only',
        'gold_used_for_decoding': False, 'private_coordinates_used': False,
        'text_added_or_changed': False,
    }
    return out


def project_metadata_view(view, frozen):
    originals = {table.get('public_structure_metadata', {}).get('table_id'): table
                 for page in view['pages'] for table in page['tables']
                 if 'public_structure_metadata' in table}
    projected = frozen.project_public_logical_tables(view)
    for page in projected['pages']:
        for table in page['tables']:
            source = table.get('source_projection')
            original = originals.get(table.get('logical_table_id')) if source else None
            if original is None:
                continue
            selection = list(range(source['skip'])) + [row - 1 for row in source['logical_rows']]
            row_map = {old: new for new, old in enumerate(selection)}
            if len(row_map) != len(selection):
                table['public_structure_projection_status'] = 'unknown_duplicate_source_rows'
                continue
            cells, invalid = [], None
            for cell in original['cells']:
                source_rows = list(range(cell['row'], cell['row'] + cell.get('row_span', 1)))
                selected_rows = [row for row in source_rows if row in row_map]
                if not selected_rows:
                    continue
                if selected_rows != source_rows or [row_map[row] for row in source_rows] != list(
                    range(row_map[source_rows[0]], row_map[source_rows[0]] + len(source_rows))
                ):
                    invalid = 'unknown_partial_span_across_declared_source_boundary'
                    break
                mapped = copy.deepcopy(cell)
                mapped.update(row=row_map[cell['row']], source_page=page['page_number'])
                cells.append(mapped)
            if invalid:
                table['public_structure_projection_status'] = invalid
                continue
            table.update(cells=cells,
                         header_rows=[row_map[row] for row in original.get('header_rows') or []
                                      if row in row_map] if original.get('header_rows') is not None else None,
                         public_structure_projection_status='decoded_declared_public_source_rows')
    return projected


def row_summary(case_name, metadata, source, final, scores, issues, digest):
    core = scores['core']
    selected = core['selected_source_scopes']
    return {
        'source': case_name, 'job': metadata.get('job'), 'status': metadata['status'],
        'MD_SHA256': digest, 'pages_recorded': len(final['pages']),
        'pages_expected': source['page_count'], 'parse_issues': issues,
        'core_numeric': core['gold_numeric_bindings']['counts'],
        'core_period': scores['core_calendar']['calendar_equivalent_source_period_summary'],
        'financial30': selected['financial_complete_30_source_values']['counts'],
        'funding31': selected['funding_31_source_nonempty_cells']['counts'],
        'funding7_bound': selected['funding_7_year_type_amount_rows']['complete_leaf_bound_rows'],
        'stock': scores['stock'], 'normal_header_leaves': scores['normal_header_leaves'],
        'supplements': {
            name: {'literal': value['literal']['atomic_literal_summary'],
                   'scope_calendar': value['scope_calendar']['atomic_literal_summary']}
            for name, value in scores['supplements'].items()
        },
    }


def aggregate(rows):
    result = {
        'cases_scored': len(rows), 'pages_scored': sum(row['pages_recorded'] for row in rows),
        'core_numeric': dict(sum((Counter(row['core_numeric']) for row in rows), Counter())),
        'core_period_pass': sum(row['core_period']['passed'] for row in rows),
        'financial30': dict(sum((Counter(row['financial30']) for row in rows), Counter())),
        'funding31': dict(sum((Counter(row['funding31']) for row in rows), Counter())),
        'funding7_bound': sum(row['funding7_bound'] for row in rows),
        'stock': [{'source': row['source'], 'status': row['stock']['status']}
                  for row in rows if row['stock']],
        'normal_header_leaves_pass': sum(row['normal_header_leaves']['passed'] for row in rows),
        'supplements': {}, 'cases': rows,
    }
    for name in ('supplement402', 'source130', 'source28', 'normal33'):
        result['supplements'][name] = {
            mode: {key: sum(row['supplements'][name][mode][key] for row in rows)
                   for key in ('literal_and_unique_row_pass', 'literal_row_and_complete_header_pass', 'target_count')}
            for mode in ('literal', 'scope_calendar')
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path, help='Captured run directory containing cases/')
    parser.add_argument('--output', type=Path, help='Derived results only; default INPUT/scoring')
    parser.add_argument('--dry-run', action='store_true', help='Import frozen scorers and hash locks without scoring/writing')
    args = parser.parse_args()
    input_root = args.input.resolve()
    output = (args.output or (input_root / 'scoring')).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('All derived evidence must stay under selected-pipeline-deployment')
    frozen = load_frozen()
    frozen_before = contract(frozen)
    if args.dry_run:
        print(json.dumps({'dry_run': True, 'model_or_HTTP_calls': False,
                          'frozen_files_verified': len(frozen_before), 'output': str(output),
                          'frozen_adapter_SHA256': sha(FROZEN_ADAPTER)}, ensure_ascii=False))
        return 0
    if (output / 'score-summary.json').exists():
        raise ValueError('Refusing to overwrite prior scores; choose another output directory')
    cases = sorted((input_root / 'cases').iterdir())
    by_source = {Path(item['path']).stem: item for item in frozen.MANIFEST['documents']}
    rows = {'frozen': [], 'public_structure_aware': []}
    structure_audits, source_proofs, skipped_cases = [], [], []
    for case in cases:
        if not (case / 'result.md').is_file() or not (case / 'summary.json').is_file():
            skipped_cases.append({'source': case.name, 'reason': 'missing_received_MD_or_summary'})
            continue
        metadata = json.loads((case / 'summary.json').read_text())
        if metadata.get('status') not in {'completed', 'partial'}:
            skipped_cases.append({'source': case.name, 'reason': 'job_not_completed', 'status': metadata.get('status')})
            continue
        source = by_source[case.name]
        digest = sha(case / 'result.md')
        if metadata.get('MD_SHA256') and metadata['MD_SHA256'] != digest:
            raise ValueError(f'Received Markdown no longer matches capture SHA: {case.name}')
        warnings = json.loads((case / 'warnings.json').read_text()) if (case / 'warnings.json').is_file() else {}
        statuses = {item['unit_index']: item['status'] for item in warnings.get('units', [])}
        template = {
            'run_id': input_root.name, 'config_id': 'selected-docling2139-v1-false-pypdfium-glm-oriented',
            'source': {key: source[key] for key in ('path', 'sha256', 'page_count')},
            'status': metadata['status'],
            'pages': [{'page_number': number,
                       'status': 'completed' if statuses.get(number, 'completed') in {'completed', 'warning'} else statuses[number],
                       'tables': []} for number in range(1, source['page_count'] + 1)],
        }
        final, issues = frozen.reader.parse_final((case / 'result.md').read_text(), template)
        final.update(actual_HTTP_MD_path=str(case / 'result.md'), actual_HTTP_MD_SHA256=digest)
        public_structured = with_public_metadata(final)
        structure_audits.append({'source': case.name, **public_structured['public_structure_audit']})
        views = {
            'frozen': frozen.project_public_logical_tables(final),
            'public_structure_aware': project_metadata_view(public_structured, frozen),
        }
        for name, view in views.items():
            location = output / name / 'cases' / case.name
            scores = frozen.score_view(view)
            row = row_summary(case.name, metadata, source, final, scores, issues, digest)
            row['public_logical_projection'] = view['public_logical_projection']
            save(location / 'received-MD-view.json', view)
            save(location / 'frozen-scorer-results.json', scores)
            save(location / 'score-summary.json', row)
            rows[name].append(row)
        if sha(case / 'result.md') != digest:
            raise RuntimeError('Actual received Markdown was altered during scoring')
        source_proofs.append({'source': case.name, 'MD_SHA256': digest, 'unchanged': True})
    if not rows['frozen']:
        raise ValueError('No completed public Markdown cases found; refusing empty score report')
    if contract(frozen) != frozen_before:
        raise RuntimeError('Frozen scorer/gold changed during scoring')
    summary = {
        'schema': 'selected-pipeline-independent-public-MD-score/1',
        'frozen': aggregate(rows['frozen']),
        'public_structure_aware': aggregate(rows['public_structure_aware']),
        'structure_readability': structure_audits,
        'frozen_contract': frozen_before, 'source_MD_proofs': source_proofs,
        'skipped_cases': skipped_cases,
        'adapter_SHA256': sha(__file__),
        'interpretation': 'Frozen scores retain the prior exact reader/criteria. The additional view changes only publicly observable structure; score changes between these two columns are serialization observability, not model improvements.',
        'no_private_sidecars_or_coordinates': True, 'no_model_or_HTTP_calls': True,
        'original_MD_and_frozen_files_unchanged': True,
    }
    save(output / 'score-summary.json', summary)
    print(json.dumps({name: {key: value for key, value in summary[name].items() if key != 'cases'}
                      for name in rows}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
