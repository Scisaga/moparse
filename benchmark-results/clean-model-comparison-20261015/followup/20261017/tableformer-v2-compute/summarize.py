"""Summarize frozen scores and measured resources; never alter model output."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import statistics

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[2]


def read(path):
    return json.loads(path.read_text())


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def evaluated(counts):
    return sum(v for k, v in counts.items() if not k.startswith('not_evaluated'))


def aggregate_reports(paths):
    reports = [read(p) for p in paths]
    core = Counter()
    finance = Counter()
    funding = Counter()
    supplement = {n: {'counts': Counter(), 'literal': 0, 'full_header': 0, 'total_annotated': 0}
                  for n in ['supplement402', 'source130', 'normal33']}
    fields = {}
    for report in reports:
        c = report['core']
        core.update(c['gold_numeric_bindings']['counts'])
        scopes = c['selected_source_scopes']
        finance.update(scopes['financial_complete_30_source_values']['counts'])
        funding.update(scopes['funding_31_source_nonempty_cells']['counts'])
        for name in supplement:
            s = report['supplements'][name]['scope_calendar']
            a = s['atomic_literal_summary']
            supplement[name]['counts'].update(a['counts'])
            supplement[name]['literal'] += a['literal_and_unique_row_pass']
            supplement[name]['full_header'] += a['literal_row_and_complete_header_pass']
            supplement[name]['total_annotated'] += a['target_count']
            for table in s['tables']:
                for value in table['values']:
                    if not value['source_complete_atomic_literal'] or value['status'].startswith('not_evaluated'):
                        continue
                    key = (Path(table['source_document']).name, table['source_page'], table['source_ordinal'],
                           value['source_cell']['row'], value['source_cell']['column'])
                    fields[(name,) + key] = {'literal': value['literal_and_unique_row_pass'],
                        'full_header': value['literal_row_and_complete_header_pass'],
                        'expected': value['source_cell']['text'], 'labels': value['source_row_labels'],
                        'header': value['source_header_path'], 'status': value['status'],
                        'observed': value['candidate_exact_literal_cells_in_labeled_row']}
    for s in supplement.values():
        s['counts'] = dict(s['counts'])
        s['evaluated'] = evaluated(s['counts'])
    return {'core': {'pass': core['pass'], 'evaluated': evaluated(core)},
            'core_period_pass': sum(r['core_calendar']['calendar_equivalent_source_period_summary']['passed'] for r in reports),
            'financial30': {'pass': finance['pass'], 'evaluated': evaluated(finance)},
            'funding31': {'pass': funding['pass'], 'evaluated': evaluated(funding)},
            'funding7': sum(r['core']['selected_source_scopes']['funding_7_year_type_amount_rows']['complete_leaf_bound_rows'] for r in reports),
            'normal_header_leaves': sum(r['normal_header_leaves']['passed'] for r in reports),
            'stock': [r['stock']['status'] for r in reports if r['stock']],
            'supplements': supplement}, fields


def numbers(vals):
    return {'count': len(vals), 'mean': statistics.mean(vals) if vals else None,
            'min': min(vals) if vals else None, 'max': max(vals) if vals else None}


def content_signature(tables):
    return [{k: t[k] for k in ['num_rows', 'num_cols', 'rows', 'header_rows', 'cells']} for t in tables]


def main():
    plan = read(ROOT / 'plan.json')
    rows = []
    field_maps = {}
    reproduction = []
    for cfg in plan['variants']:
        folder = ROOT / cfg['id']
        if not (folder / 'completion.json').exists():
            continue
        complete = read(folder / 'completion.json')
        row = {'variant': cfg, 'selected_pages': complete['selected_pages_completed'], 'cases': len(complete['sources']),
               'warmup_seconds': complete['warmup_seconds'], 'total_process_seconds': complete['total_process_seconds']}
        for mode in ['raw', 'public']:
            paths = [Path(c[mode + '_scores']) for c in complete['sources']]
            row[mode], fields = aggregate_reports(paths)
            field_maps[(cfg['id'], mode)] = fields
        events = []
        times = []
        for case in plan['cases']:
            for pn in case['pages']:
                path = folder / Path(case['source']).stem / f'page-{pn:04d}/inference.json'
                r = read(path)
                events.extend(r['events'])
                times.append(r['conversion_seconds'])
        samples = []
        for line in (folder / 'resources.jsonl').read_text().splitlines():
            r = json.loads(line)
            if r['active']['phase'] == 'measured':
                samples.append(r)
        row['timing'] = {'sum_page_conversion_seconds': sum(times),
            'sum_model_generate_seconds': sum(e['model_call_seconds'] for e in events),
            'sum_model_generate_CPU_seconds': sum(e['model_call_CPU_seconds'] for e in events),
            'table_calls': len(events), 'EOS_calls': sum(e['ended_EOS'] for e in events),
            'length_limit_calls': sum(e['hit_length_limit'] for e in events),
            'input_shapes': sorted({tuple(e['input_shape']) for e in events}),
            'generated_ID_counts': numbers([len(e['generated_ids']) for e in events]),
            'measurement_repeats': 1, 'single_page_calls_exclude_initialization_warmup_scoring_export': True}
        row['resources'] = {'measured_samples': len(samples),
            'process_CPU_pct_one_core_100': numbers([s['process_CPU_pct_one_core_100'] for s in samples]),
            'peak_process_RSS_GiB': max((s['RSS_bytes'] for s in samples), default=0) / 2**30,
            'inference_GPU_memory_bytes': 0,
            'shared_host_GPU_samples_not_attributed_to_this_CPU_inference': True,
            'CPU_package_temperature_C': numbers([t for s in samples for t in s['CPU_package_temperatures']])}
        if cfg['id'] == 'official448':
            for case in plan['cases']:
                source = Path(case['source']).stem
                old = read(BASE / 'native/new139-v2-matching-true-pypdfium-full' / source / 'result.json')
                prior = {p['page_number']: p for p in old['pages']}
                new = read(folder / source / 'result.json')
                for page in new['pages']:
                    reproduction.append({'source': source, 'page': page['page_number'],
                        'same_cells_as_prior_full_document': content_signature(prior[page['page_number']]['tables']) == content_signature(page['tables'])})
        rows.append(row)
    deltas = []
    for row in rows:
        if row['variant']['id'] == 'official448':
            continue
        for mode in ['raw', 'public']:
            a = field_maps.get(('official448', mode), {})
            b = field_maps[(row['variant']['id'], mode)]
            assert a.keys() == b.keys(), 'Do not change evaluated source-field denominators'
            result = {'variant': row['variant']['id'], 'mode': mode}
            for metric in ['literal', 'full_header']:
                result[metric] = {'improved': [], 'regressed': []}
                for key in a:
                    state = 'improved' if b[key][metric] and not a[key][metric] else 'regressed' if a[key][metric] and not b[key][metric] else None
                    if state:
                        result[metric][state].append({'source_key': key, 'baseline': a[key], 'candidate': b[key]})
            deltas.append(result)
    stopped = read(ROOT / 'stopped-by-user.json') if (ROOT / 'stopped-by-user.json').exists() else None
    summary = {'scope': plan['scope'], 'configs_completed': len(rows),
               'all_registered_configs_completed': len(rows) == len(plan['variants']),
               'experiment_status': 'stopped_by_user' if stopped else 'complete' if len(rows) == len(plan['variants']) else 'running',
               'stopped_run_provenance': stopped,
               'rows': rows, 'per_source_field_differences': deltas,
               'official_baseline_reproduction': reproduction,
               'all_original_PDFs_and_frozen_gold_or_scorers_changed': False,
               'summarizer_SHA256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(ROOT / 'summary.json', summary)
    for row in rows:
        print(json.dumps({'config': row['variant']['id'], 'raw402': row['raw']['supplements']['supplement402'],
            'public402': row['public']['supplements']['supplement402'],
            'raw_funding31': row['raw']['funding31'], 'public_funding31': row['public']['funding31'],
            'model_seconds': row['timing']['sum_model_generate_seconds'],
            'page_conversion_seconds': row['timing']['sum_page_conversion_seconds'],
            'peak_RSS_GiB': row['resources']['peak_process_RSS_GiB']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
