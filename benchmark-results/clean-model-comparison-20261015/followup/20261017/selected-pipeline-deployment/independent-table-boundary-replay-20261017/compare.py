"""Compare two completed native export replays without changing their evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--after-dir', default='after')
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--output', type=Path, default=HERE / 'comparison.json')
    args = parser.parse_args()
    before_dir, after_dir = HERE / 'before', HERE / args.after_dir
    before, after = load(before_dir / 'summary.json'), load(after_dir / 'summary.json')
    if after['table_service_SHA256'] != args.expected_sha:
        raise ValueError('After replay does not match the final reviewed module SHA')
    if args.output.exists():
        raise ValueError('Refusing to overwrite a prior comparison')
    source_changes, captions, groups, exported, assembled = [], [], [], [], []
    stable = ('fragment_id', 'page', 'rows', 'num_rows', 'num_cols', 'cells',
              'header_rows', 'unit_text', 'valid', 'bbox')
    for old, new in zip(before['documents'], after['documents'], strict=True):
        stem = old['source']
        if stem != new['source'] or old['raw_SHA256'] != new['raw_SHA256']:
            raise AssertionError('Frozen document input differs between versions')
        left = {f['fragment_id']: f for f in load(before_dir / stem / 'fragments.json')}
        right = {f['fragment_id']: f for f in load(after_dir / stem / 'fragments.json')}
        if left.keys() != right.keys():
            raise AssertionError('Source fragment population changed')
        for key, fragment in left.items():
            changed = [field for field in stable if fragment[field] != right[key][field]]
            if changed:
                source_changes.append({'source': stem, 'fragment': key, 'fields': changed})
            if fragment['caption'] != right[key]['caption']:
                captions.append({'source': stem, 'fragment': key,
                                 'before': fragment['caption'], 'after': right[key]['caption']})
        old_groups = {tuple(members) for members in old['actual_groups'].values()}
        new_groups = {tuple(members) for members in new['actual_groups'].values()}
        groups.append({'source': stem, 'before': old['actual_groups'], 'after': new['actual_groups'],
                       'removed_groups': sorted(old_groups - new_groups),
                       'added_groups': sorted(new_groups - old_groups)})
        for filename, changes in [('exported-pages.json', exported), ('assembled-pages.json', assembled)]:
            a, b = load(before_dir / stem / filename), load(after_dir / stem / filename)
            if a.keys() != b.keys():
                raise AssertionError('Frozen native page population changed')
            for number in a:
                if a[number] != b[number]:
                    changes.append({'source': stem, 'page': int(number),
                                    'before_SHA256': hashlib.sha256(a[number].encode()).hexdigest(),
                                    'after_SHA256': hashlib.sha256(b[number].encode()).hexdigest()})
    changed_groups = [group for group in groups if group['removed_groups'] or group['added_groups']]
    normal = next(group for group in groups if group['source'] == '1225473526')
    normal_continuation = ['p6_t2', 'p7_t1'] in normal['after'].values()
    result = {
        'schema': 'independent-frozen-native-export-comparison/1',
        'before_git_ref': before['before_git_ref'],
        'before_table_service_SHA256': before['table_service_SHA256'],
        'after_table_service_SHA256': after['table_service_SHA256'],
        'native_pages': after['native_pages'], 'native_tables': after['table_count'],
        'source_cell_anchors': after['cell_count'], 'source_merged_cells': after['span_cell_count'],
        'source_anchor_text_numeric_spans_header_scope_and_page_changes': source_changes,
        'source_owned_caption_metadata_changes': captions,
        'pre_assembly_public_page_changes': exported,
        'post_assembly_public_page_changes': assembled,
        'merge_group_comparisons': groups, 'merge_group_changes': changed_groups,
        'normal_p6_p7_continuation_preserved': normal_continuation,
        'before_public_coverage': [d['assembled_public_coverage'] for d in before['documents']],
        'after_public_coverage': [d['assembled_public_coverage'] for d in after['documents']],
        'status': 'pass' if not source_changes and not changed_groups and normal_continuation else 'needs_review',
        'interpretation': 'Same frozen raw model output is replayed. This checks export/assembly regressions and never establishes that every original model answer is correct. Group differences require independent original-PDF review.',
        'model_calls': 0, 'HTTP_requests': 0,
        'historical_raw_model_gold_and_scores_modified': False,
        'script_SHA256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'native_pages': result['native_pages'],
                      'source_cells': result['source_cell_anchors'], 'source_changes': len(source_changes),
                      'caption_metadata_changes': len(captions), 'group_changes': len(changed_groups),
                      'pre_assembly_page_changes': len(exported), 'post_assembly_page_changes': len(assembled),
                      'normal_p6_p7': normal_continuation}, ensure_ascii=False))


if __name__ == '__main__':
    main()
