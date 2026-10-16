"""Repeatable read-only summaries of one captured HTTP cohort's timing/resources.

Accepts running snapshots and completed runs. Missing/unsupported observations
remain null; client/server/SDK/converter scopes are never added together.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
UTC = dt.timezone.utc
SDK_PAGE = re.compile(r'GLM_SDK_PAGE source_id=(\S+) page=(\d+) status=(\S+) sdk_requests=(\d+) page_duration_ms=(\d+) http_duration_ms=(\d+)')
CONVERTER = re.compile(r'Finished converting document (.+?)\.pdf in ([\d.]+) sec\.')
ORIENTATION = re.compile(r'GLM SDK orientation page=(\d+) clockwise_rotation=(\d+) confidence=([\d.]+)')
THROUGHPUT = re.compile(r'Avg prompt throughput: ([\d.]+) tokens/s, Avg generation throughput: ([\d.]+) tokens/s, Running: (\d+) reqs, Waiting: (\d+) reqs, GPU KV cache usage: ([\d.]+)%')


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if math.isfinite(value) else None
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def instant(value):
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def stat(values):
    known = sorted(value for raw in values if (value := number(raw)) is not None)
    def quantile(q):
        if not known:
            return None
        position = (len(known) - 1) * q
        left, right = math.floor(position), math.ceil(position)
        return known[left] + (known[right] - known[left]) * (position - left)
    return {'known_samples': len(known), 'unknown_samples': len(values) - len(known),
            'mean': statistics.mean(known) if known else None,
            'min': known[0] if known else None, 'max': known[-1] if known else None,
            'p50': quantile(.5), 'p95': quantile(.95)}


class Reader:
    def __init__(self):
        self.inputs = []

    def bytes(self, path):
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
        self.inputs.append({'path': str(path), 'snapshot_SHA256': hashlib.sha256(payload).hexdigest(),
                            'snapshot_bytes': len(payload), 'size_after_read': after.st_size,
                            'mutated_during_read': before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns})
        return payload

    def json(self, path, default=None):
        return json.loads(self.bytes(path)) if path.is_file() else default

    def jsonl(self, path):
        if not path.is_file():
            return [], 0
        records, invalid = [], 0
        for line in self.bytes(path).decode().splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                invalid += 1  # A currently appended final line is explicitly unobserved.
        return records, invalid

    def log(self, path):
        if not path.is_file():
            return []
        output = []
        for line in self.bytes(path).decode(errors='replace').splitlines():
            timestamp = instant(line.split(' ', 1)[0])
            if timestamp is not None:
                output.append((timestamp, line))
        return output


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def interval_union(intervals):
    intervals = sorted(intervals)
    if not intervals:
        return None
    total, left, right = 0., intervals[0][0], intervals[0][1]
    for start, end in intervals[1:]:
        if start <= right:
            right = max(right, end)
        else:
            total += right - left
            left, right = start, end
    return total + right - left


def in_windows(timestamp, windows):
    return any(start <= timestamp <= end for start, end in windows)


def parse_pmon(raw):
    header, rows = None, []
    for line in raw.splitlines():
        fields = line.strip().split()
        if line.startswith('#'):
            if len(fields) > 2 and fields[1:3] == ['gpu', 'pid']:
                header = fields[1:]
            continue
        if not header or len(fields) < len(header):
            continue
        item = dict(zip(header, fields[:len(header)], strict=True))
        if number(item.get('gpu')) is None or number(item.get('pid')) is None:
            continue
        if 'command' in item:
            item['command'] = ' '.join(fields[header.index('command'):])
        rows.append(item)
    return rows


def resource_summary(samples, windows, source=None):
    selected = [sample for sample in samples if source is None or sample.get('active_request', {}).get('source') == source]
    service_names = sorted({name for sample in samples for name in sample.get('services', {})})
    services = {}
    for name in service_names:
        rss, cpu, threads, observed_seconds, core_seconds = [], [], [], 0., 0.
        previous = None
        observed_pids = set()
        boundary_unknown = 0
        for sample in samples:
            value = sample.get('services', {}).get(name, {})
            same_window = source is None or sample.get('active_request', {}).get('source') == source
            prior_same = previous is not None and (source is None or previous[0].get('active_request', {}).get('source') == source)
            if same_window:
                rss.append(value.get('observed_tree_rss_bytes'))
                threads.append(sum(process['threads'] for process in value.get('processes', []))
                               if 'processes' in value else None)
                observed_pids.update((process['pid'], process.get('create_time')) for process in value.get('processes', []))
                observed_cpu = number(value.get('CPU_percent_100_equals_one_core'))
                elapsed = (number(value.get('monotonic_seconds')) or 0) - (number(previous[1].get('monotonic_seconds')) or 0) if previous else None
                if prior_same and observed_cpu is not None and elapsed and elapsed > 0:
                    cpu.append(observed_cpu)
                    core_seconds += observed_cpu / 100 * elapsed
                    observed_seconds += elapsed
                else:
                    cpu.append(None)
                    boundary_unknown += 1
            previous = (sample, value)
        services[name] = {
            'CPU_percent_100_equals_one_core': stat(cpu),
            'CPU_time_weighted_mean_percent': core_seconds / observed_seconds * 100 if observed_seconds else None,
            'observed_CPU_core_seconds': core_seconds if observed_seconds else None,
            'CPU_observed_interval_seconds': observed_seconds if observed_seconds else None,
            'CPU_unknown_or_boundary_intervals': boundary_unknown,
            'tree_RSS_bytes': stat(rss), 'tree_threads': stat(threads),
            'observed_process_identities': [{'pid': pid, 'created': created} for pid, created in sorted(observed_pids)],
        }
    gpu_rows = defaultdict(list)
    pmon_rows = defaultdict(list)
    for sample in selected:
        timestamp = instant(sample.get('UTC'))
        active = timestamp is not None and in_windows(timestamp, windows)
        gpu = sample.get('gpu', {})
        for fields in csv.reader(io.StringIO(gpu.get('raw', ''))):
            if len(fields) != 9:
                continue
            fields = [field.strip() for field in fields]
            record = dict(zip(('index', 'uuid', 'GPU_utilization_percent', 'memory_engine_utilization_percent',
                               'VRAM_used_MiB', 'power_W', 'temperature_C', 'SM_clock_MHz', 'memory_clock_MHz'), fields, strict=True))
            record['during_observed_SDK_window'] = active
            gpu_rows[(fields[0], fields[1])].append(record)
        owners = defaultdict(list)
        for name, value in sample.get('services', {}).items():
            for process in value.get('processes', []):
                owners[process['pid']].append((name, process.get('create_time')))
        for row in parse_pmon(sample.get('pmon', {}).get('raw', '')):
            identity = owners.get(int(row['pid']), [])
            owner = identity[0][0] if len(identity) == 1 else 'unattributed_or_ambiguous'
            created = identity[0][1] if len(identity) == 1 else None
            row['during_observed_SDK_window'] = active
            pmon_rows[(row['gpu'], int(row['pid']), created, owner, row.get('command'))].append(row)
    cards = []
    for (index, uuid), rows in sorted(gpu_rows.items()):
        fields = [key for key in rows[0] if key not in {'index', 'uuid', 'during_observed_SDK_window'}]
        missing = [None] * max(0, len(selected) - len(rows))
        active_expected = sum(instant(sample.get('UTC')) is not None and in_windows(instant(sample.get('UTC')), windows) for sample in selected)
        active_missing = [None] * max(0, active_expected - sum(row['during_observed_SDK_window'] for row in rows))
        cards.append({'index': index, 'uuid': uuid,
                      'scope': 'Whole card, includes unrelated resident/running processes.',
                      'all_observed_samples': {key: stat([row[key] for row in rows] + missing) for key in fields},
                      'during_observed_SDK_windows': {key: stat([row[key] for row in rows if row['during_observed_SDK_window']] + active_missing) for key in fields}})
    processes = []
    for (gpu, pid, created, owner, command), rows in sorted(pmon_rows.items(), key=lambda pair: (pair[0][0], pair[0][1])):
        fields = [key for key in ('sm', 'mem', 'fb') if any(key in row for row in rows)]
        processes.append({'GPU_index': gpu, 'pid': pid, 'created': created, 'owner': owner, 'command': command,
                          'present_samples': len(rows), 'not_seen_samples': len(selected) - len(rows),
                          'all_observed_samples': {key: stat([row.get(key) for row in rows]) for key in fields},
                          'during_observed_SDK_windows': {key: stat([row.get(key) for row in rows if row['during_observed_SDK_window']]) for key in fields},
                          'units': {'sm': 'percent', 'mem': 'memory engine percent', 'fb': 'MB as labeled by nvidia-smi pmon'},
                          'attribution': 'PID belongs to exactly one recorded service tree in the same sampling cycle; otherwise unknown. No current-live PID lookup.'})
    return {'sample_count': len(selected), 'CPU_and_RAM_by_service': services,
            'whole_GPU_cards': cards, 'GPU_processes': processes,
            'host_CPU_percent': stat([sample.get('host', {}).get('cpu_percent') for sample in selected]),
            'CPU_package_temperature_C': stat([
                item.get('current') for sample in selected
                for item in sample.get('cpu_temperatures', {}).get('coretemp', [])
                if item.get('label', '').startswith('Package')
            ]),
            'limitations': ['Sampling misses peaks between observations.',
                            'Service trees have separate CPU/RSS scopes; shared RSS is not deduplicated.',
                            'GPU means use known samples only; pmon - and absent process observations are not zero.',
                            'SDK windows are recorded/log-derived page windows, not pure GPU model execution.',
                            'Whole-card GPU values must not be attributed to one parser process.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.input.resolve()
    output = (args.output or root / 'performance-summary.json').resolve()
    if not root.is_relative_to(HERE) or not output.is_relative_to(HERE):
        raise ValueError('Run inputs and summaries must stay under selected-pipeline-deployment')
    read = Reader()
    plan = read.json(root / 'run-plan.json')
    if plan is None:
        raise ValueError('Capture run-plan.json is required')
    completion = read.json(root / 'run-completion.json')
    samples, invalid_lines = read.jsonl(root / 'resource-samples.jsonl')
    api_log = read.log(root / 'container.log')
    sdk_log = read.log(root / 'sdk-container.log')
    glm_log = read.log(root / 'glm-container.log')
    summaries = {item['source']: item for item in read.json(root / 'summary.json', [])}
    cases = []
    for source in plan['sources']:
        stem = source['source']
        case_root = root / 'cases' / stem
        case = dict(summaries.get(stem, read.json(case_root / 'summary.json', {})))
        # Read running case state too: summary.json intentionally holds terminal cases only.
        latest = read.json(case_root / 'job-latest.json', {})
        case.update(source=stem, page_count=source['page_count'], status=latest.get('status', case.get('status', 'not_started')))
        case['server_queue_wait_s'] = (instant(latest.get('started_at')) - instant(latest.get('created_at'))
                                       if instant(latest.get('started_at')) is not None and instant(latest.get('created_at')) is not None else None)
        case['server_job_duration_s'] = (instant(latest.get('completed_at')) - instant(latest.get('started_at'))
                                         if instant(latest.get('completed_at')) is not None and instant(latest.get('started_at')) is not None else None)
        warnings = read.json(case_root / 'warnings.json')
        routed = [item for item in (warnings or {}).get('document_warnings', []) if item['code'] == 'glm_sdk_scan_routing_used']
        case['SDK_expected_pages'] = routed[-1].get('details', {}).get('pages') if routed else ([] if warnings is not None else None)
        case['docling_converters'] = []
        case['SDK_page_records'] = []
        case['legacy_orientation_records'] = []
        case['legacy_orientation_to_HTTP_intervals'] = []
        case['API_observed_SDK_HTTP_responses'] = 0 if (root / 'container.log').is_file() else None
        case['SDK_access_POST_completions'] = 0 if (root / 'sdk-container.log').is_file() else None
        cases.append(case)
    by_job = {case['job']: case for case in cases if case.get('job')}
    by_source = {case['source']: case for case in cases}
    def case_at(timestamp):
        found = [case for case in cases if (start := instant(case.get('started_UTC'))) is not None
                 and start <= timestamp and ((end := instant(case.get('completed_UTC'))) is None or timestamp <= end)]
        return found[0] if len(found) == 1 else None
    pending = None
    windows = []
    unmatched_sdk_records = []
    for timestamp, line in api_log:
        converter = CONVERTER.search(line)
        if converter and (case := by_source.get(Path(converter[1]).name)):
            elapsed = float(converter[2])
            case['docling_converters'].append({'finished_UTC': dt.datetime.fromtimestamp(timestamp, UTC).isoformat(),
                                              'duration_s': elapsed, 'inferred_start_epoch': timestamp - elapsed,
                                              'finished_epoch': timestamp})
        page = SDK_PAGE.search(line)
        if page:
            job, page_number, status, requests, duration, http_duration = page.groups()
            case = by_job.get(job) or by_source.get(job)
            if case is None:
                unmatched_sdk_records.append({'source_id': job, 'page': int(page_number), 'epoch': timestamp})
            if case:
                record = {'source_id': job, 'page': int(page_number), 'status': status,
                          'sdk_requests': int(requests), 'page_duration_ms': int(duration),
                          'http_duration_ms': int(http_duration), 'finished_epoch': timestamp}
                case['SDK_page_records'].append(record)
                windows.append((timestamp - int(duration) / 1000, timestamp))
        orientation = ORIENTATION.search(line)
        if orientation:
            case = case_at(timestamp)
            pending = (case, timestamp, int(orientation[1]))
            if case:
                case['legacy_orientation_records'].append({'page': int(orientation[1]),
                  'clockwise_rotation': int(orientation[2]), 'confidence': float(orientation[3]), 'epoch': timestamp})
        if 'HTTP Request: POST ' in line and '/glmocr/parse ' in line:
            case = case_at(timestamp)
            if case:
                case['API_observed_SDK_HTTP_responses'] += 1
            if pending and case is pending[0] and timestamp >= pending[1]:
                record = {'page': pending[2], 'duration_s': timestamp - pending[1],
                          'start_epoch': pending[1], 'finished_epoch': timestamp}
                case['legacy_orientation_to_HTTP_intervals'].append(record)
                if not case['SDK_page_records']:
                    windows.append((pending[1], timestamp))
                pending = None
    for timestamp, line in sdk_log:
        if '"POST /glmocr/parse ' in line and (case := case_at(timestamp)):
            case['SDK_access_POST_completions'] += 1
    all_throughput, glm_peers = [], Counter()
    for timestamp, line in glm_log:
        match = THROUGHPUT.search(line)
        if match:
            all_throughput.append({'epoch': timestamp, **dict(zip(
                ('prompt_tokens_per_s', 'generation_tokens_per_s', 'running_requests', 'waiting_requests', 'KV_cache_percent'),
                map(float, match.groups()), strict=True))})
        peer = re.search(r'([0-9.]+):\d+ - "POST /v1/chat/completions ', line)
        if peer:
            glm_peers[peer[1]] += 1
    for case in cases:
        converters = case['docling_converters']
        intervals = [(item['inferred_start_epoch'], item['finished_epoch']) for item in converters]
        case['docling_logged_pipeline_work_s'] = sum(item['duration_s'] for item in converters) if converters else None
        case['docling_logged_pipeline_union_s'] = interval_union(intervals)
        case['docling_logged_pipeline_elapsed_span_s'] = max(end for _, end in intervals) - min(start for start, _ in intervals) if intervals else None
        expected = case['SDK_expected_pages']
        records = case['SDK_page_records']
        exact = expected is not None and len(records) == len(expected) and {item['page'] for item in records} == set(expected)
        case['SDK_timing_status'] = ('not_invoked' if exact and not expected else 'complete_observed_page_logs' if exact
                                     else 'unknown_missing_complete_page_logs')
        case['SDK_page_pipeline_total_s'] = sum(item['page_duration_ms'] for item in records) / 1000 if exact else None
        case['SDK_HTTP_total_s'] = sum(item['http_duration_ms'] for item in records) / 1000 if exact else None
        case['SDK_actual_POST_count'] = sum(item['sdk_requests'] for item in records) if exact else None
        case['SDK_observed_page_duration_ms'] = stat([item['page_duration_ms'] for item in records])
        case['legacy_orientation_to_HTTP_s'] = stat([item['duration_s'] for item in case['legacy_orientation_to_HTTP_intervals']])
        case['GLM_pure_model_inference_duration_s'] = None
        case['resources'] = resource_summary(samples, windows, case['source'])
    finished = [case for case in cases if case.get('full_capture_s') is not None]
    full = bool(completion and completion.get('complete_capture')) and len(finished) == len(cases)
    def total(field, require_all=True):
        values = [number(case.get(field)) for case in cases]
        known = [value for value in values if value is not None]
        return {'total_s': sum(known) if len(known) == len(cases) and (full or not require_all) else None,
                'observed_partial_sum_s': sum(known) if known else None,
                'known_case_count': len(known), 'unknown_case_count': len(cases) - len(known)}
    timestamps = [number(sample.get('monotonic')) for sample in samples]
    timestamps = [value for value in timestamps if value is not None]
    intervals = [right - left for left, right in zip(timestamps, timestamps[1:], strict=False)]
    status = 'complete' if full else 'incomplete_running_or_failed_capture'
    summary = {
        'schema': 'selected-pipeline-performance-summary/1', 'status': status,
        'as_of_UTC': dt.datetime.now(UTC).isoformat(),
        'as_of_Asia_Shanghai': dt.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'run': str(root), 'expected_documents': len(cases), 'expected_pages': plan['pages'],
        'finished_capture_documents': len(finished), 'finished_capture_pages': sum(case['page_count'] for case in finished),
        'case_statuses': dict(Counter(case['status'] for case in cases)),
        'timing': {key: total(key) for key in ('submit_to_terminal_s', 'submit_to_saved_MD_s', 'full_capture_s',
                                             'asset_capture_s', 'server_queue_wait_s', 'server_job_duration_s',
                                             'SDK_page_pipeline_total_s', 'SDK_HTTP_total_s')},
        'timing_scopes': {
            'client': 'Upload start through terminal job / saved Markdown / all downloaded public assets; includes polling.',
            'server_job': 'Persisted started_at through completed_at; includes native parsing, SDK, rendering/export and assets.',
            'docling': 'Official Finished converting logs include the full converter pipeline. Sum is parallel work; interval union/span is estimated wall time from 0.01s-rounded logs. Never sum with server/client durations.',
            'SDK_page_pipeline': 'Observed GLM_SDK_PAGE duration includes source PDF/image rendering, orientation, SDK semaphore, HTTP/retries and response parsing.',
            'SDK_HTTP': 'Observed accumulated POST-await time includes network, SDK CPU layout, GLM region recognition and retry HTTP attempts; excludes direction and retry sleep.',
            'legacy': 'Orientation-result log to next SDK HTTP response is only a separate log-derived interval, never a substitute for missing exact SDK page timing.',
            'pure_model': 'No kernel/model-forward/request-specific engine duration is available; remains null.'},
        'sampling': {'count': len(samples), 'invalid_or_in_progress_lines': invalid_lines,
                     'interval_seconds': stat(intervals), 'target_seconds': 2},
        'resources': resource_summary(samples, windows),
        'SDK_observed_window_union_s': interval_union(windows),
        'SDK_request_counts': {
            'exact_actual_POST_total': sum(case['SDK_actual_POST_count'] for case in cases) if full and all(case['SDK_actual_POST_count'] is not None for case in cases) else None,
            'observed_page_log_POST_sum': sum(item['sdk_requests'] for case in cases for item in case['SDK_page_records']) if any(case['SDK_page_records'] for case in cases) else None,
            'API_response_log_count': sum(case['API_observed_SDK_HTTP_responses'] for case in cases) if all(case['API_observed_SDK_HTTP_responses'] is not None for case in cases) else None,
            'SDK_access_log_POST_count': sum(case['SDK_access_POST_completions'] for case in cases) if all(case['SDK_access_POST_completions'] is not None for case in cases) else None,
            'unmatched_page_logs': unmatched_sdk_records,
            'interpretation': 'Page POSTs can contain multiple GLM region requests; access/response logs are observations, not exact attempts when requests fail before a logged response.'},
        'GLM_service_log': {'scope': 'Shared inference service; no attribution of throughput/region calls to individual parser jobs.',
                            'log_present': (root / 'glm-container.log').is_file(),
                            'POST_completions_by_peer': dict(glm_peers),
                            'throughput': {key: stat([item[key] for item in all_throughput]) for key in
                                           ('prompt_tokens_per_s', 'generation_tokens_per_s', 'running_requests', 'waiting_requests', 'KV_cache_percent')}},
        'cases': cases, 'capture_plan': plan,
        'input_snapshots': read.inputs, 'summarizer_SHA256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'read_only': True, 'services_or_models_controlled': False,
        'missing_values_are_null_not_zero': True,
    }
    save(output, summary)
    print(json.dumps({'output': str(output), 'status': status, 'finished_cases': len(finished),
                      'resource_samples': len(samples),
                      'exact_SDK_page_logs': sum(len(case['SDK_page_records']) for case in cases),
                      'legacy_SDK_intervals': sum(len(case['legacy_orientation_to_HTTP_intervals']) for case in cases)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
