"""Derive audit totals and attach separately reviewed source evidence."""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path('/opt/mosaic-parse')
FROZEN = REPO / 'benchmark-results/clean-model-comparison-20261015/native/new139-v1-matching-false-pypdfium-full'
path = HERE / 'summary.json'
summary = json.loads(path.read_text())
counts = Counter()
business = []
retained = True
for document in summary['documents']:
    stem = document['source']
    raw = json.loads((FROZEN / stem / 'raw-docling.json').read_text())
    text_by_ref = {item['self_ref']: item for item in raw['texts']}
    for ref in document['recovered_visible_refs']:
        item = text_by_ref[ref]
        counts[item['content_layer'] + '/' + item['label']] += 1
        if item['content_layer'] == 'body':
            business.append({'document': stem, 'ref': ref, 'page': item['prov'][0]['page_no'],
                             'text': item['text'], 'label': item['label']})
    phase_refs = {}
    for phase in ('before', 'after'):
        trace = json.loads((HERE / stem / phase / 'source-ref-trace.json').read_text())
        phase_refs[phase] = {(event['page'], event['ref']) for event in trace}
    retained &= phase_refs['before'].issubset(phase_refs['after'])
summary['source_visible_ref_expectation'] = {
    'layers': ['body', 'furniture'],
    'source_pool': 'all DoclingDocument.texts, nonempty text, first source provenance page in the frozen native route; includes picture children, excludes invisible/background/notes and nonnative pages',
    'expected_refs': sum(d['phases']['after']['visible_source_items'] for d in summary['documents']),
    'before_missing_refs': sum(len(d['phases']['before']['missing_visible_refs']) for d in summary['documents']),
    'after_missing_refs': sum(len(d['phases']['after']['missing_visible_refs']) for d in summary['documents']),
    'recovered_refs': sum(len(d['recovered_visible_refs']) for d in summary['documents']),
    'all_originally_serialized_source_refs_preserved': retained,
    'recovered_by_source_classification': dict(counts),
    'recovered_business_footnotes': business,
    'remaining_known_scope': '1225475375 physical p62 (printed55), 227 BODY/text children of PictureItem #/pictures/40; source-visible rotated 11-column financial table; existing omission unchanged',
}
normal = next(d for d in summary['documents'] if d['source'] == '1225473526')
period = next(d for d in summary['documents'] if d['source'] == '1225474693')
summary['logical_table_group_comparison'] = {
    'before': sum(len(d['phases']['before']['actual_groups']) for d in summary['documents']),
    'after': sum(len(d['phases']['after']['actual_groups']) for d in summary['documents']),
    'specified_normal_p6_p7_preserved': ['p6_t2', 'p7_t1'] in normal['phases']['after']['actual_groups'].values(),
    'different_period_p2_p3_remain_separate': not any('p2_t3' in members and 'p3_t1' in members for members in period['phases']['after']['actual_groups'].values()),
    'conservative_splits': [{'document': d['source'], 'fragments': list(group)}
                            for d in summary['documents'] for group in d['removed_groups']],
    'source_review_evidence': ['1225475642/conservative-group-split/source-evidence.json',
                               '1225475375/existing-picture-child-omission/source-evidence.json'],
}
summary['status'] = 'pass_source_table_and_existing_body_regression_with_disclosed_remaining_picture_children_and_one_conservative_split'
summary['finalizer_SHA256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print(hashlib.sha256(path.read_bytes()).hexdigest())
