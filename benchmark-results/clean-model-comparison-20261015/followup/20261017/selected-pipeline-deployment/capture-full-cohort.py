"""Capture full PDF jobs, final public Markdown/assets and read-only resources.

No model selection is passed in a request; the service configuration is tested as
actually deployed. This program never starts, stops or changes monitored services.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time
import traceback
from urllib.parse import urlsplit

import httpx
import psutil

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[2]
REPO = OLD.parents[1]
MANIFEST = OLD / 'input-manifest.json'
CAPTURE = OLD / 'run-http-acceptance-metrics-v3.py'
DEFAULT_SDK = 'docling_glm_ocr_sdk'
DEFAULT_GLM = 'docling_glm_ocr'
TERMINAL = {'completed', 'partial', 'failed', 'cancelled'}
SAFE_CONTAINER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def append(path, payload):
    with Path(path).open('a') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def inspect_container(name):
    if not SAFE_CONTAINER.fullmatch(name):
        raise ValueError('Unsafe container name')
    raw = json.loads(subprocess.check_output(
        ['docker', 'inspect', '--type', 'container', name], text=True, timeout=20
    ))[0]
    state = raw['State']
    if not state.get('Running') or not state.get('Pid'):
        raise RuntimeError(f'Observed container is not running: {name}')
    # Never save Config.Env, command-line credentials or complete docker inspect.
    return {
        'name': name, 'container_ID': raw['Id'], 'image_ID': raw['Image'],
        'started': state['StartedAt'], 'restart_count': raw['RestartCount'],
        'pid': state['Pid'], 'ports': raw.get('NetworkSettings', {}).get('Ports', {}),
        'mounts': [{key: mount.get(key) for key in ('Type', 'Source', 'Destination')}
                   for mount in raw.get('Mounts', [])],
    }


def cohort(args):
    manifest = json.loads(MANIFEST.read_text())
    by_id = {Path(item['path']).stem: item for item in manifest['documents']}
    default = ['1225474693', '1225473526'] + [
        stem for stem in by_id if stem not in {'1225474693', '1225473526'}
    ]
    order = default if args.cohort == 'full10' else args.cohort.split(',')
    if not order or len(set(order)) != len(order) or any(stem not in by_id for stem in order):
        raise ValueError('--cohort must be full10 or unique known source stems separated by commas')
    documents = []
    for stem in order:
        source = args.sources.resolve() / f'{stem}.pdf'
        original = by_id[stem]
        digest = sha(source)
        if digest != original['sha256']:
            raise ValueError(f'Original PDF SHA256 mismatch: {stem}')
        documents.append({
            'source': stem, 'source_path': str(source), 'manifest_path': original['path'],
            'sha256': digest, 'page_count': original['page_count'],
            'size_bytes': source.stat().st_size,
        })
    return documents


class Observer:
    def __init__(self, output, containers, capture, active):
        self.output, self.capture, self.active = output, capture, active
        self.identities = {name: capture.identity(value['pid']) for name, value in containers.items()}
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name='readonly-cohort-monitor')
        self.samples = 0
        self.started = False
        self.intervals = []
        self.peaks = {}
        self.error = None

    def start(self):
        self.started = True
        self.thread.start()

    def run(self):
        previous = {}
        last = None
        try:
            while not self.stop.is_set():
                cycle = time.monotonic()
                if last is not None:
                    self.intervals.append(cycle - last)
                last = cycle
                record = {'UTC': now(), 'monotonic': cycle, 'active_request': dict(self.active),
                          'sampling_target_seconds': 2, 'services': {},
                          'scope': 'Only named container process trees; preexisting GLM/SDK may serve other callers. GPU figures are whole-card, never allocated to this parser.'}
                for name, identity in self.identities.items():
                    try:
                        self.capture.verify_identity(identity)
                        sample = self.capture.process_sample(identity['pid'])
                        self.capture.verify_identity(identity)
                        prior = previous.get(name)
                        cpu = None
                        if prior:
                            elapsed = sample['monotonic_seconds'] - prior['monotonic_seconds']
                            delta = (sample['tree_cpu_seconds_including_reaped_children']
                                     - prior['tree_cpu_seconds_including_reaped_children'])
                            if elapsed > 0 and delta >= 0:
                                cpu = 100 * delta / elapsed
                        sample.update(root_identity=identity,
                                      CPU_percent_100_equals_one_core=cpu,
                                      CPU_interval_status='observed' if cpu is not None else 'unknown_warmup_or_process_turnover')
                        record['services'][name] = sample
                        previous[name] = sample
                        peak = self.peaks.setdefault(name, {'RSS_bytes': 0, 'CPU_percent': None})
                        peak['RSS_bytes'] = max(peak['RSS_bytes'], sample['observed_tree_rss_bytes'])
                        if cpu is not None:
                            peak['CPU_percent'] = max(peak['CPU_percent'] or 0, cpu)
                    except (OSError, psutil.Error, RuntimeError) as error:
                        record['services'][name] = {'unknown': True, 'error': repr(error)}
                        previous.pop(name, None)
                record['host'] = {'cpu_percent': psutil.cpu_percent(),
                                  'available_ram_bytes': psutil.virtual_memory().available}
                try:
                    record['cpu_temperatures'] = {
                        key: [{'label': x.label, 'current': x.current} for x in values]
                        for key, values in psutil.sensors_temperatures().items()
                    }
                except Exception as error:
                    record['cpu_temperatures'] = {'unknown': True, 'error': repr(error)}
                commands = {
                    'gpu': ['--query-gpu=index,uuid,utilization.gpu,utilization.memory,memory.used,power.draw,temperature.gpu,clocks.sm,clocks.mem', '--format=csv,noheader,nounits'],
                    'pmon': ['pmon', '-s', 'um', '-c', '1'],
                }
                for key, arguments in commands.items():
                    start_utc = now()
                    try:
                        raw = subprocess.check_output(['nvidia-smi', *arguments], text=True, timeout=10)
                        record[key] = {'started_UTC': start_utc, 'raw': raw, 'ended_UTC': now(),
                                       'unknown_markers_preserved': True}
                    except Exception as error:
                        record[key] = {'unknown': True, 'error': repr(error)}
                record['observation_seconds'] = time.monotonic() - cycle
                append(self.output / 'resource-samples.jsonl', record)
                self.samples += 1
                self.stop.wait(max(0, 2 - (time.monotonic() - cycle)))
        except Exception as error:
            self.error = repr(error)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=25)
        result = {
            'sample_count': self.samples, 'target_interval_seconds': 2,
            'actual_interval_mean_s': statistics.mean(self.intervals) if self.intervals else None,
            'actual_interval_max_s': max(self.intervals, default=None),
            'service_peaks': self.peaks, 'root_identities': self.identities,
            'thread_joined': not self.thread.is_alive(), 'error': self.error,
            'GPU_scope': 'Whole-card only; pmon - / unsupported counters remain unknown, never zero.',
            'CPU_scope': 'Separate process trees; RSS may include shared pages; no aggregate of API and preexisting inference services.',
            'pure_model_inference_duration': 'Not available from HTTP alone; SDK end-to-end page duration includes preprocessing/layout/region inference/network.',
        }
        save(self.output / 'resource-summary.json', result)
        return result


def copy_local_job_diagnostics(case, job, mounts):
    result = []
    data = next((item['Source'] for item in mounts if item['Destination'] == '/data'), None)
    if data:
        root = Path(data) / 'jobs' / job
        for relative in ('logs/warnings.json', 'output/asset-index.json'):
            path = root / relative
            if path.is_file():
                target = case / path.name
                target.write_bytes(path.read_bytes())
                result.append({'source': str(path), 'saved': target.name, 'sha256': sha(target),
                               'scope': 'Optional local diagnostics; frozen quality reads public Markdown only.'})
    return result


def start_logs(container, output, secret, filename):
    target = (output / filename).open('w')
    process = subprocess.Popen(
        ['docker', 'logs', '--timestamps', '--since', now(), '--follow', container],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    def consume():
        for line in process.stdout:
            target.write(line.replace(secret, '[REDACTED]') if secret else line)
            target.flush()

    thread = threading.Thread(target=consume, daemon=True, name='owned-log-follower')
    thread.start()
    return process, thread, target


def run(args):
    base = args.base_url.rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}):
        raise ValueError('--base-url must be an HTTP origin with no credentials/query/path')
    services = (args.sdk_container, args.glm_container)
    if (any(not SAFE_CONTAINER.fullmatch(name) for name in (args.container, *services))
            or len(set((args.container, *services))) != 3):
        raise ValueError('API, SDK and GLM container names must be valid and distinct')
    output = args.output.resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('All evidence must stay under selected-pipeline-deployment')
    documents = cohort(args)
    plan = {
        'schema': 'selected-pipeline-full-HTTP/1', 'base': base, 'container': args.container,
        'sdk_container': args.sdk_container, 'glm_container': args.glm_container,
        'sources': documents, 'pages': sum(item['page_count'] for item in documents),
        'form': {'scan_policy': 'auto'}, 'unit_range_set': False, 'profile_override': False,
        'parse_timeout_override': False, 'request_concurrency': 1,
        'sampling_target_seconds': 2, 'service_control': False,
        'source_manifest_SHA256': sha(MANIFEST), 'capture_helper_SHA256': sha(CAPTURE),
        'runner_SHA256': sha(__file__), 'api_key_value_recorded': False,
        'authorization_environment_variable': args.api_key_env,
    }
    if args.dry_run:
        print(json.dumps({'dry_run': True, 'HTTP_sent': False, 'docker_invoked': False,
                          'output': str(output), **plan}, ensure_ascii=False, indent=2))
        return 0
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ('run-plan.json', 'cases', 'summary.json')):
        raise ValueError('Refusing to overwrite prior run evidence; choose a new output subdirectory')
    capture = module('frozen_http_capture_selected', CAPTURE)
    names = [args.container, *services]
    containers = {name: inspect_container(name) for name in names}
    bound_ports = {int(binding['HostPort'])
                   for bindings in containers[args.container]['ports'].values()
                   for binding in bindings or []}
    requested_port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if bound_ports and requested_port not in bound_ports:
        raise RuntimeError('Requested HTTP port does not belong to the observed API container')
    plan.update(started_UTC=now(), containers=containers)
    save(output / 'run-plan.json', plan)
    active = {}
    observer = Observer(output, containers, capture, active)
    secret = os.environ.get(args.api_key_env, '')
    headers = {'X-API-Key': secret} if secret else {}
    summaries = []
    followers = []
    resources = None
    try:
        with httpx.Client(headers=headers, trust_env=False, follow_redirects=False,
                          timeout=httpx.Timeout(180, connect=15)) as client:
            for endpoint in ('health', 'ready', 'openapi.json', 'v1/backends'):
                response = client.get(base + '/' + endpoint)
                name = endpoint.replace('/', '-').replace('.', '-') + '-before'
                capture.capture_response(output, name, response, decode_json=True)
                response.raise_for_status()
            health = json.loads((output / 'health-before-response-body.bin').read_bytes())
            if health.get('queue', {}).get('active') != 0:
                raise RuntimeError('Preexisting active jobs; no job has been submitted or cancelled')
            scope = capture.disjoint_service_trees(
                containers[args.container]['pid'], {name: containers[name]['pid'] for name in services}
            )
            save(output / 'service-tree-scope.json', scope)
            if scope['status'] != 'disjoint':
                raise RuntimeError('Observed service process trees overlap')
            observer.start()
            for name, filename in ((args.container, 'container.log'),
                                   (args.sdk_container, 'sdk-container.log'),
                                   (args.glm_container, 'glm-container.log')):
                followers.append(start_logs(name, output, secret, filename))
            for document in documents:
                stem = document['source']
                case = output / 'cases' / stem
                case.mkdir(parents=True, exist_ok=False)
                source = Path(document['source_path'])
                start = time.monotonic()
                record = {'source': stem, 'page_count': document['page_count'],
                          'started_UTC': now(), 'status': 'not_submitted'}
                active.clear()
                active.update(source=stem, job=None)
                save(case / 'request.json', {
                    'method': 'POST', 'url': base + '/v1/content/jobs',
                    'source': str(source), 'source_SHA256': document['sha256'],
                    'multipart_file': {'filename': source.name, 'content_type': 'application/pdf',
                                       'size_bytes': document['size_bytes']},
                    'form': {'scan_policy': 'auto'}, 'unit_range_in_request': False,
                    'profile_in_request': False, 'timeout_in_request': False,
                    'authorization_present': bool(secret), 'authorization_value': '[NOT RECORDED]',
                    'started_UTC': record['started_UTC'],
                })
                stop_on_error = False
                try:
                    with source.open('rb') as handle:
                        response = client.post(base + '/v1/content/jobs', data={'scan_policy': 'auto'},
                                               files={'file': (source.name, handle, 'application/pdf')})
                    capture.capture_response(case, 'submit', response, decode_json=True)
                    response.raise_for_status()
                    job = response.json()['id']
                    if not capture.SAFE_ID.fullmatch(job):
                        raise ValueError('Server returned unsafe job identifier')
                    record['job'] = job
                    active['job'] = job
                    save(case / 'summary.json', record)
                    print(json.dumps({'event': 'submitted', 'source': stem, 'job': job}), flush=True)
                    while True:
                        response = client.get(base + '/v1/content/jobs/' + job)
                        raw = response.content
                        state = response.json()
                        append(case / 'job-polls.jsonl', {
                            'UTC': now(), 'monotonic': time.monotonic(),
                            'http_status': response.status_code, 'response_headers': dict(response.headers),
                            'body_SHA256': hashlib.sha256(raw).hexdigest(),
                            'raw_UTF8_body': raw.decode('utf-8'), 'response': state,
                        })
                        response.raise_for_status()
                        save(case / 'job-latest.json', state)
                        record['status'] = state['status']
                        if state['status'] in TERMINAL:
                            capture.capture_response(case, 'terminal', response, decode_json=True)
                            break
                        if time.monotonic() - start > args.client_deadline:
                            raise RuntimeError('Client observation deadline reached; server job left untouched')
                        time.sleep(1)
                    record['submit_to_terminal_s'] = time.monotonic() - start
                    if state['status'] in {'completed', 'partial'}:
                        response = client.get(base + '/v1/content/jobs/' + job + '/result')
                        capture.capture_response(case, 'result', response)
                        response.raise_for_status()
                        (case / 'result.md').write_bytes(response.content)
                        record.update(submit_to_saved_MD_s=time.monotonic() - start,
                                      MD_SHA256=sha(case / 'result.md'), MD_bytes=len(response.content))
                        assets = capture.capture_assets(client, base, job, response.text, case)
                        record.update(asset_count=len(assets['downloads']), asset_errors=assets['errors'],
                                      asset_status=assets['status'], asset_capture_s=assets['asset_capture_seconds'])
                    record['local_diagnostics'] = copy_local_job_diagnostics(
                        case, job, containers[args.container]['mounts']
                    )
                except Exception as error:
                    record['workflow_error'] = repr(error).replace(secret, '[REDACTED]') if secret else repr(error)
                    save(case / 'workflow-error.json', {'UTC': now(), 'error': record['workflow_error'],
                         'traceback': traceback.format_exc().replace(secret, '[REDACTED]') if secret else traceback.format_exc()})
                    stop_on_error = True  # An unobserved job may still run; never create overlap.
                record.update(completed_UTC=now(), full_capture_s=time.monotonic() - start)
                save(case / 'summary.json', record)
                summaries.append(record)
                save(output / 'summary.json', summaries)
                active.clear()
                print(json.dumps({'event': 'terminal', 'source': stem, 'job': record.get('job'),
                                  'status': record['status'], 'full_capture_s': record['full_capture_s'],
                                  'error': record.get('workflow_error')}, ensure_ascii=False), flush=True)
                if stop_on_error:
                    break
            response = client.get(base + '/health')
            capture.capture_response(output, 'health-after', response, decode_json=True)
            response.raise_for_status()
    finally:
        if observer.started:
            resources = observer.close()
        for log_process, log_thread, log_handle in followers:
            # Signal only our docker-logs client, never a monitored container/process.
            log_process.terminate()
            try:
                log_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log_process.kill()
                log_process.wait(timeout=5)
            log_thread.join(timeout=5)
            log_handle.close()
        after = {}
        for name in names:
            try:
                after[name] = inspect_container(name)
            except Exception as error:
                after[name] = {'unknown': True, 'error': repr(error)}
        complete = len(summaries) == len(documents) and all(
            item['status'] in {'completed', 'partial'} and not item.get('workflow_error')
            and item.get('asset_status') == 'completed' for item in summaries
        )
        save(output / 'run-completion.json', {
            'UTC': now(), 'complete_capture': complete, 'cases_captured': len(summaries),
            'pages_submitted': sum(item['page_count'] for item in summaries if item.get('job')),
            'submit_to_saved_MD_total_s': sum(item.get('submit_to_saved_MD_s', 0) for item in summaries),
            'full_MD_and_assets_total_s': sum(item['full_capture_s'] for item in summaries),
            'containers_after': after, 'service_controlled': False,
            'resource_summary': resources,
        })
    return 0 if complete else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--container', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdk-container', default=DEFAULT_SDK, help='Exact observed SDK container')
    parser.add_argument('--glm-container', default=DEFAULT_GLM, help='Exact observed GLM inference container')
    parser.add_argument('--sources', type=Path, default=REPO / 'pdf_sample', help='Directory of original full PDFs')
    parser.add_argument('--cohort', default='full10', help='full10, or comma-separated frozen source stems')
    parser.add_argument('--api-key-env', default='MOSAICPARSE_API_KEY', help='Environment variable name; key value is never logged')
    parser.add_argument('--client-deadline', type=float, default=7500, help='Client observation limit; never a parse request override')
    parser.add_argument('--dry-run', action='store_true', help='Validate inputs only; no HTTP, Docker, output writes or model calls')
    args = parser.parse_args()
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
