"""Read-only whole-public-output consistency diagnostics, never gold evaluation."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmark import moparse_benchmark as b  # noqa: E402
from benchmark.tools import check_release as release  # noqa: E402

LEFT = ROOT / 'benchmark/runs/header-v3-http-20261018/regression504'
RIGHT = ROOT / 'benchmark/runs/header-v4-http-20261018/regression504'
GRID = re.compile(r'(?m)^\|[^\n]*(?:\n\|[^\n]*)*')


def value_hash(value):
    return hashlib.sha256(b.json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def normalize_table(table):
    return {'id': table['id'], 'rendered_page': table['rendered_page'], 'rows': table['rows'],
        'spans': table['meta'].get('spans'), 'sources': table['sources'],
        'structure': {key: table['meta'].get(key) for key in (
            'source_pages', 'num_rows', 'num_cols', 'encoding', 'structure_valid',
            'header_rows', 'header_scope_rows', 'header_scope_complete')}}


def source_keys(table):
    return {(x['fragment'], x['page']) for x in table['sources']}


def relation_groups(left, right):
    pending = [('left', item) for item in left] + [('right', item) for item in right]
    groups = []
    while pending:
        side, table = pending.pop(0)
        group = {'left': [], 'right': []}
        group[side].append(table)
        keys = source_keys(table)
        changed = True
        while changed:
            changed = False
            for item in list(pending):
                kind, candidate = item
                if keys & source_keys(candidate):
                    group[kind].append(candidate)
                    keys |= source_keys(candidate)
                    pending.remove(item)
                    changed = True
        groups.append({'source_fragments': sorted(keys),
            'left_tables': [normalize_table(x) for x in group['left']],
            'right_tables': [normalize_table(x) for x in group['right']],
            'source_mapping_available_on_both_sides': bool(group['left'] and group['right'] and keys),
            'scope': 'Source-fragment association diagnostic only; no missing repeated header reconstructed'})
    return groups


def text_changes(left, right):
    result = []
    for kind, a0, a1, b0, b1 in difflib.SequenceMatcher(a=left, b=right, autojunk=False).get_opcodes():
        if kind != 'equal':
            result.append({'operation': kind, 'left_range': [a0, a1], 'right_range': [b0, b1],
                'left': left[a0:a1], 'right': right[b0:b1]})
    return result


def compare(output, left_root=LEFT, right_root=RIGHT, document_ids=None):
    if output.exists():
        raise ValueError('Choose a new immutable diagnostic output')
    before = b.frozen_contract()
    reader = release.load_reader()
    _, documents = b.load_dataset(b.DEFAULT_DATASET)
    cohort = next(x for x in b.read(b.DEFAULT_DATASET)['cohorts'] if x['id'] == 'regression-504')
    expected = {x['id']: x for x in documents if x['id'] in cohort['document_ids']}
    if document_ids is not None:
        assert set(document_ids) <= set(expected)
        expected = {key: value for key, value in expected.items() if key in document_ids}
    documents_result = []
    for identifier, document in sorted(expected.items()):
        md_paths = [root / 'cases' / identifier / 'result.md' for root in (left_root, right_root)]
        content = []
        for path in md_paths:
            summary = b.read(path.parent / 'summary.json')
            request = b.read(path.parent / 'request.json')
            assert summary['status'] == 'completed' and summary['MD_SHA256'] == b.digest(path)
            assert request['source']['sha256'] == document['sha256']
            content.append(path.read_text())
        tables = [reader.public_tables(text) for text in content]
        by_id = [{x['id']: x for x in group} for group in tables]
        assert all(len(item) == len(group) for item, group in zip(by_id, tables, strict=True))
        common = set(by_id[0]) & set(by_id[1])
        changed, equal_receipts = [], []
        for key in sorted(common):
            a, z = [normalize_table(item[key]) for item in by_id]
            if a != z:
                changed.append({'table_id': key,
                    'grid_raw_exact': a['rows'] == z['rows'], 'spans_exact': a['spans'] == z['spans'],
                    'source_maps_exact': a['sources'] == z['sources'], 'structure_exact': a['structure'] == z['structure'],
                    'left': a, 'right': z})
            else:
                equal_receipts.append({'table_id': key, 'source_pages': a['structure']['source_pages'],
                    'public_table_SHA256': value_hash(a)})
        different_ids = [[x for x in group if x['id'] not in common] for group in tables]
        associations = relation_groups(*different_ids)
        page_maps = [reader.pages(text) for text in content]
        assert all(sorted(pages) == list(range(1, document['page_count'] + 1)) for pages in page_maps)
        body_changes, body_receipts = [], []
        for page in range(1, document['page_count'] + 1):
            # Table grids are judged above. Frozen visible-reader removes comments and target URLs,
            # preserving visible source text; only whitespace has a separate diagnostic comparison.
            a, z = [reader.visible_markdown(GRID.sub('', pages[page])) for pages in page_maps]
            x, y = [re.sub(r'\s+', '', text) for text in (a, z)]
            if a != z:
                body_changes.append({'page': page, 'raw_visible_exact': False,
                    'whitespace_only_equivalent': x == y,
                    'raw_line_changes': text_changes(a.splitlines(keepends=True), z.splitlines(keepends=True)),
                    'visible_character_changes': text_changes(x, y) if x != y else []})
            else:
                body_receipts.append({'page': page, 'visible_body_SHA256': value_hash(a)})
        documents_result.append({'document_id': identifier, 'source_SHA256': document['sha256'],
            'pages': document['page_count'], 'MDs': [b.artifact(path) for path in md_paths],
            'table_counts': [len(x) for x in tables], 'same_table_IDs': len(common),
            'equal_raw_grid_span_structure_and_source_tables': len(equal_receipts),
            'unchanged_table_receipts': equal_receipts, 'changed_same_ID_tables': changed,
            'source_associated_added_removed_or_reassembled_tables': associations,
            'body_visible_sequence': {'same_raw_pages': len(body_receipts), 'changed_pages': body_changes,
                'unchanged_page_receipts': body_receipts},
            'focus_cross_window_p104_p105': [normalize_table(x) for x in tables[1]
                if identifier == '1225474739' and any(key in source_keys(x) for key in
                    [('mineru_p104_t4', 104), ('mineru_p105_t1', 105)])]})
    result = {'schema': 'moparse-resource-revision-public-consistency/1', 'created_at': b.utc(),
        'scope': ('V3 vs V4 explicitlyselected completePDFs only, all publictable grids/spans/source maps and non-table visible body sequences; no newsource gold or accuracy claims'
                  if document_ids is not None else 'V3 vs V4 same11 completePDFs504pages, all publictable grids/spans/source maps and non-table visible body sequences; no newsource gold or accuracy claims'),
        'complete504_comparison_claim': document_ids is None,
        'left_run': b.artifact(left_root / 'run.json') if (left_root / 'run.json').exists() else None,
        'right_run': b.artifact(right_root / 'run.json') if (right_root / 'run.json').exists() else None,
        'frozen_visible_reader': b.artifact(release.READER_PATH), 'documents': documents_result,
        'summary': {'documents': len(documents_result), 'pages': sum(x['pages'] for x in documents_result),
            'same_ID_changed_tables': sum(len(x['changed_same_ID_tables']) for x in documents_result),
            'source_association_groups_with_different_table_IDs': sum(len(x['source_associated_added_removed_or_reassembled_tables']) for x in documents_result),
            'changed_body_pages_raw': sum(len(x['body_visible_sequence']['changed_pages']) for x in documents_result),
            'changed_body_pages_beyond_whitespace': sum(not p['whitespace_only_equivalent'] for x in documents_result for p in x['body_visible_sequence']['changed_pages'])},
        'policy': {'gold_scores_original_outputs_or_reader_changed': False,
            'job_URL_or_asset_target_identity_compared_as_visible_source_text': False,
            'NFKC_or_punctuation_numeric_or_symbol_normalization': False,
            'source_correctness_claim_outside_existing_gold': False}, 'diagnostic_script': b.artifact(Path(__file__))}
    assert b.frozen_contract() == before
    b.save(output, result)
    return result


if __name__ == '__main__':
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(b.json.dumps(compare(args.output)['summary'], ensure_ascii=False, indent=2))
