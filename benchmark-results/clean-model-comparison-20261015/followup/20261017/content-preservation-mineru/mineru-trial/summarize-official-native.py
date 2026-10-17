"""Aggregate captured official MinerU evidence without invoking any models."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def total(records, key):
    return sum(item.get(key, 0) or 0 for item in records)


def summarize_tier(tier):
    folder = HERE / f'official-native-{tier}'
    manifest = read(folder / 'run-manifest.json')
    if manifest is None:
        return {'status': 'not_started'}
    cases = []
    for item in manifest['cases']:
        location = folder / f"{item['id']}-p{item['page']}"
        events = read(location / 'official-stage-observations.json', [])
        recoveries = read(location / 'native-table-recovery.json', [])
        calls = read(location / 'generation-calls.json', [])
        priorities = [event for event in events if event['stage'] == 'native_table_priority']
        fills = [event for event in events if event['stage'] == 'native_PDF_text_fill']
        post = [event for event in events if event['stage'] == 'actual_post_OCR']
        visual = [table for event in events
                  if event['stage'] == 'actual_VLM_results_before_native_body_fill'
                  for table in event['tables']]
        internal = [result for result in recoveries if result.get('stage') == 'internal_NativeTableResult']
        public = [result for result in recoveries if result.get('stage') == 'public_PDFTableResult']
        generations = []
        for path in sorted((location / 'model-http').glob('*/request.json')):
            request = read(path)
            generations.append({'request_file': str(path.relative_to(HERE)),
                                'generation_parameters': {key: value for key, value in request.items()
                                                          if key not in ('messages', 'model')},
                                'model': request.get('model')})
        counts = {}
        for event in priorities:
            for key, value in event['counts'].items():
                counts[key] = counts.get(key, 0) + value
        summary = {key: value for key, value in item.items()
                   if key not in ('pdf', 'official_parse_arguments')}
        summary.update({
            'directory': str(location.relative_to(HERE)),
            'native_table_priority_called': bool(priorities),
            'native_table_route_counts': counts,
            'public_native_recovery_accepts': len(public),
            'native_internal_tables': [
                {'rows': result['rows'], 'cols': result['cols'], 'source': result['source'],
                 'confidence': result['confidence'], 'physical_cell_count': len(result['cells']),
                 'spanning_cells': sum(cell['rowspan'] > 1 or cell['colspan'] > 1 for cell in result['cells']),
                 'cells_with_source_char_indices': sum(bool(cell['source_char_indices']) for cell in result['cells'])}
                for result in internal],
            'visual_table_regions_before_native_body_fill': len(visual),
            'native_body_spans': total(fills, 'returned_spans'),
            'native_body_nonempty_text_spans': total(fills, 'nonempty_text_spans'),
            'post_OCR_candidate_spans': total(post, 'candidate_spans'),
            'post_OCR_changed_spans': total(post, 'content_changed'),
            'actual_rendered_image_sizes': [size for event in events
                                            if event['stage'] == 'actual_VLM_options'
                                            for size in event['image_sizes']],
            'actual_generation_parameters': generations,
            'observed_HTTP_requests': len(calls),
            'observed_HTTP_statuses': [call['HTTP_status'] for call in calls],
            'observed_finish_reasons': [reason for call in calls for reason in call['finish_reasons']],
            'usage': {key: sum((call.get('usage') or {}).get(key, 0) or 0 for call in calls)
                      for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
            'public_cell_geometry_or_header_flags': False,
        })
        cases.append(summary)
    cohorts = {}
    for name in ('original_14', 'additional_p62'):
        selected = [item for item in cases if item['cohort'] == name]
        completed = [item for item in selected if item['status'] == 'completed']
        route_counts = {}
        for item in completed:
            for key, value in item['native_table_route_counts'].items():
                route_counts[key] = route_counts.get(key, 0) + value
        cohorts[name] = {
            'completed_cases': len(completed), 'failed_cases': len(selected) - len(completed),
            'parse_seconds_sum': total(completed, 'parse_seconds'),
            'markdown_DEFAULT_seconds_sum': total(completed, 'markdown_DEFAULT_seconds'),
            'markdown_FULL_seconds_sum': total(completed, 'markdown_FULL_seconds'),
            'PDF_to_DEFAULT_MD_component_seconds_sum': total(completed, 'PDF_to_DEFAULT_MD_component_seconds'),
            'PDF_to_FULL_MD_component_seconds_sum': total(completed, 'PDF_to_FULL_MD_component_seconds'),
            'end_to_end_case_seconds_sum': total(completed, 'end_to_end_case_seconds'),
            'model_HTTP_calls': total(completed, 'observed_HTTP_requests'),
            'model_HTTP_seconds_sum': total(completed, 'model_HTTP_seconds'),
            'native_table_route_counts': route_counts,
            'visual_table_regions': total(completed, 'visual_table_regions_before_native_body_fill'),
            'native_body_spans': total(completed, 'native_body_spans'),
            'post_OCR_candidate_spans': total(completed, 'post_OCR_candidate_spans'),
            'post_OCR_changed_spans': total(completed, 'post_OCR_changed_spans'),
            'usage': {key: sum(item['usage'][key] for item in completed)
                      for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
        }
    samples = read(folder / 'resource-samples.json', [])
    resources = {
        'sampling_seconds': 0.5, 'sample_count': len(samples),
        'own_process_CPU_percent_peak': max((item['CPU_percent'] for item in samples), default=None),
        'own_process_CPU_percent_mean': (sum(item['CPU_percent'] for item in samples) / len(samples)) if samples else None,
        'own_process_RSS_bytes_peak': max((item['RSS_bytes'] for item in samples), default=None),
        'own_process_threads_peak': max((item['threads'] for item in samples), default=None),
        'CPU_affinity': manifest['CPU_affinity'],
        'interpretation': 'Own CPU runner only; psutil CPU percent may exceed 100 for multiple cores. Samples include CPU model initialization; remote GPU process is recorded separately by its owner.',
    }
    acceptance_path = HERE.parent / 'model-evaluation' / f'official-native-{tier}-source-evaluation.json'
    acceptance = read(acceptance_path)
    quality = None
    if acceptance:
        quality = {'evidence_file': str(acceptance_path.relative_to(HERE.parent)),
                   'evidence_SHA256': hashlib.sha256(acceptance_path.read_bytes()).hexdigest(),
                   'views': {key: {'fixed_condition_counts': value['fixed_condition_counts'],
                                   'additional_observation_counts': value['additional_observation_counts']}
                             for key, value in acceptance['views'].items()}}
    extra_quality = {}
    for view in ('DEFAULT', 'FULL', 'raw_model_JSON'):
        path = HERE.parent / 'model-evaluation' / f'official-native-{tier}-extra-p62-{view}-source-acceptance.json'
        if path.exists():
            value = read(path)
            extra_quality[view] = {'evidence_file': str(path.relative_to(HERE.parent)),
                                  'evidence_SHA256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                  'table_restoration_status': value['table_restoration_status'],
                                  'all_99_positions_and_nine_spans_equal': value['all_99_positions_and_nine_spans_equal'],
                                  'public_header_roles_complete_three_levels': value['public_header_roles_complete_three_levels']}
    return {'status': manifest.get('status', 'running'), 'started_at': manifest['started_at'],
            'finished_at': manifest.get('finished_at'),
            'CPU_model_initialization': manifest.get('CPU_model_initialization'),
            'CPU_resource_summary': resources,
            'independent_original_14_quality': quality, 'independent_additional_p62_quality': extra_quality,
            'timing_boundaries': manifest['timing_boundaries'], 'cohorts': cohorts,
            'cases': cases, 'unstarted_cases': manifest.get('unstarted_cases', [])}


def main():
    summary = {
        'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'summary_script_SHA256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'Read-only aggregation of recorded official standard/advanced TXT runs; no model calls.',
        'quality_acceptance': 'Independent original-PDF verification is separate. Table routing counts do not prove content correctness.',
        'public_contract_limit': 'DocVortex public PDFTableResult and MinerU public outputs do not forward internal native cell geometry/source-char indices or header flags. Experimental raw internal cells are retained without reinterpretation.',
        'progress_log_limit': 'Per-case stdout VLM_table_regions counts layout-provided table inputs only; advanced two_step discovers its own layout. Actual visual table counts below use actual_VLM_results_before_native_body_fill events.',
        'GPU_attribution': 'Remote candidate on physical GPU1 only; production GLM PID6977 also GPU1; other GPU0 services are unrelated. Candidate resource evidence is owned by mineru_isolated_trial.',
        'input_scope': 'Same full-byte original PDFs provided to API; page_range selects individual original physical pages. Fourteen scored pages and additional p62 remain separate. This is not full-document HTTP production acceptance.',
        'own_GPU_resources_15_page_phase_windows': read(HERE / 'official-native-GPU-resource-summary.json'),
        'tiers': {tier: summarize_tier(tier) for tier in ('standard', 'advanced')},
    }
    (HERE / 'official-native-comparison-summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    for tier, value in summary['tiers'].items():
        print(json.dumps({'tier': tier, 'status': value['status'], 'cohorts': value.get('cohorts')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
