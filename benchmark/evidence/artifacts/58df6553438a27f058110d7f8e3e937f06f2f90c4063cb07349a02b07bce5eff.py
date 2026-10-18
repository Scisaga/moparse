"""Read already frozen scores/received Markdown; no inference or rescoring."""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path('/opt/mosaic-parse').resolve()
sys.path.insert(0, str(ROOT))
from benchmark import moparse_benchmark as b  # noqa: E402
from benchmark.tools import check_release as release  # noqa: E402

OLD = ROOT / 'benchmark-results/clean-model-comparison-20261015/followup/20261017/content-preservation-mineru/candidate-full10-http'
PRIMARY = ROOT / 'benchmark/runs/candidate-http-20261018'
V4 = ROOT / 'benchmark/runs/header-v4-http-20261018'


def key(document, table, value):
    cell = value['source_cell']
    return (document, table['source_page'], table['source_ordinal'],
            cell['row'], cell['column'], cell['text'])


def status(value):
    return {name: value.get(name) for name in (
        'status', 'literal_and_unique_row_pass', 'literal_row_and_complete_header_pass')}


def load_scores(directory, method, documents):
    values, artifacts = {}, []
    for doc in documents:
        if method == 'production_docling':
            path = directory / 'scoring/public_structure_aware/cases' / doc / 'frozen-scorer-results.json'
        else:
            path = directory / 'regression504-final-public/public_structure_aware' / doc / 'scores.json'
        data = b.read(path)
        artifacts.append(b.artifact(path))
        for table in data['supplements']['supplement402']['literal']['tables']:
            for value in table['values']:
                k = key(doc, table, value)
                assert k not in values
                values[k] = {'table_id': table.get('table_id'),
                    'selection_method': table.get('selection_method'),
                    'raw_shape': table.get('raw_shape'), 'source': value}
    return values, artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    if args.output.exists():
        raise ValueError('Choose a new immutable comparison output')
    _, docs = b.load_dataset(b.DEFAULT_DATASET)
    cohort = next(x for x in b.read(b.DEFAULT_DATASET)['cohorts'] if x['id'] == 'regression-502')
    documents = sorted(x['id'] for x in docs if x['id'] in cohort['document_ids'])
    values, artifacts = {}, []
    for method, path in [('production_docling', OLD), ('pure_advanced_txt', PRIMARY), ('advanced_txt_header_v4', V4)]:
        values[method], proofs = load_scores(path, method, documents)
        artifacts.extend(proofs)
    keys = set(values['production_docling'])
    assert all(set(item) == keys for item in values.values())
    reader = release.load_reader()
    tables = {}
    for method, path in [('production_docling', OLD), ('pure_advanced_txt', PRIMARY / 'regression504'),
                         ('advanced_txt_header_v4', V4 / 'regression504')]:
        tables[method] = {}
        for doc in documents:
            md = path / 'cases' / doc / 'result.md'
            parsed = reader.public_tables(md.read_text())
            tables[method][doc] = {table['id']: table for table in parsed}
            artifacts.append(b.artifact(md))
    fields = []
    for k in sorted(keys):
        document, page, ordinal, row, column, text = k
        item = {'document_id': document, 'source_page': page, 'source_ordinal': ordinal,
                'source_row': row, 'source_column': column, 'source_text': text, 'methods': {}}
        for method, entries in values.items():
            entry = entries[k]
            value = entry['source']
            item['source_complete_atomic_literal'] = value['source_complete_atomic_literal']
            item['source_labels'] = value['source_row_labels']
            item['source_header_path'] = value['source_header_path']
            observed = {**entry, 'frozen_verdict': status(value)}
            model = tables[method][document].get(entry['table_id'])
            if model is not None and row < len(model['rows']) and column < len(model['rows'][row]):
                actual = model['rows'][row][column]
                own_position = release.compact(actual, reader)
                # Sourcegold is plain PDF text, not Markdown: a broken-line minus is not a list bullet.
                source_literal = re.sub(r'\s+', '', text)
                observed['printed_position_observation'] = {
                    'scope': 'Diagnostic selected table original row/column only; logical merges can move rows; never substitutes for frozen unique-row or header verdict',
                    'actual': actual, 'source_compact': source_literal,
                    'actual_compact': own_position, 'literal_equal': own_position == source_literal,
                    'ASCII_width_only_equal': release.fold_ascii_width(own_position) == release.fold_ascii_width(source_literal),
                    'row_cells': model['rows'][row], 'table_sources': model['sources'],
                }
            item['methods'][method] = observed
        fields.append(item)
    atomic = [x for x in fields if x['source_complete_atomic_literal']]
    fragments = [x for x in fields if not x['source_complete_atomic_literal']]
    assert len(atomic) == 402
    summaries = {}
    for method in values:
        summaries[method] = {'target_count': len(atomic),
            'statuses': dict(Counter(x['methods'][method]['source']['status'] for x in atomic)),
            'literal_and_unique_row_pass': sum(x['methods'][method]['source']['literal_and_unique_row_pass'] for x in atomic),
            'literal_row_and_complete_header_pass': sum(x['methods'][method]['source']['literal_row_and_complete_header_pass'] for x in atomic)}
    def changes(left, right):
        return [x for x in atomic if x['methods'][left]['frozen_verdict'] != x['methods'][right]['frozen_verdict']]
    result = {'schema': 'moparse-three-way-frozen-402-comparison/1', 'created_at': b.utc(),
        'scope': 'Same ten complete PDFs502pages, all402 atomic targets, existing strict scores read verbatim',
        'summary': summaries, 'atomic_denominator': len(atomic),
        'source_fragment_observations_outside_denominator': len(fragments),
        'changes': {'production_to_primary': changes('production_docling', 'pure_advanced_txt'),
                    'primary_to_v4': changes('pure_advanced_txt', 'advanced_txt_header_v4'),
                    'production_to_v4': changes('production_docling', 'advanced_txt_header_v4')},
        'all_atomic_fields': atomic, 'fragment_observations': fragments,
        'artifacts': artifacts, 'frozen_reader': b.artifact(release.READER_PATH),
        'policy': {'score_predicates_gold_or_model_outputs_changed': False,
                   'normalization_for_diagnostics_only': 'existing visible Markdown whitespace compaction plus separate limited ASCII-width observation; no numeric/separator correction',
                   'printed_position_observation_replaces_row_or_column_scope': False}}
    b.save(args.output, result)
    print(b.json.dumps({'summary': summaries, 'change_counts': {k: len(v) for k,v in result['changes'].items()},
                       'output': str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
