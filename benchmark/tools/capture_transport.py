"""HTTP capture with explicit transport completion and unchanged API quality states.

Uses the existing frozen transport helpers. No quality scorer/gold/reader is
modified. Default document completion retains the historical all-completed gate;
--completion-scope capture explicitly accepts byte-complete partial-quality jobs.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from benchmark import moparse_benchmark as b


def inspect_capture(directory: Path, entry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure filesystem receipt check; never contacts an endpoint or repairs bytes."""
    entry = entry if entry is not None else b.read(directory / 'summary.json')
    errors = []
    actual_status = entry.get('actual_job_status', entry.get('status'))
    if actual_status not in {'completed', 'partial'}:
        errors.append('API job did not reach completed/partial')
    md, persisted = directory / 'result.md', directory / 'persisted-result.md'
    if not md.is_file() or not persisted.is_file():
        errors.append('missing received/persisted Markdown')
    elif (md.read_bytes() != persisted.read_bytes() or b.digest(md) != entry.get('MD_SHA256')
          or b.digest(persisted) != entry.get('persisted_MD_SHA256')):
        errors.append('received/persisted Markdown bytes or SHA differ')
    for name, allowed in [('response', {200, 202}), ('persisted-result-response', {200}),
                          ('events', {200}), ('assets-list', {200})]:
        metadata = directory / (name + '.json')
        if not metadata.is_file() or b.read(metadata).get('status') not in allowed:
            errors.append(name + ' missing or bad HTTP status')
            continue
        record = b.read(metadata)
        raw = directory / ('response-body.bin' if name == 'response' else name + '.bin')
        if not raw.is_file():
            errors.append(name + ' raw response missing')
        elif record.get('body_sha256') and b.digest(raw) != record['body_sha256']:
            errors.append(name + ' raw response SHA differs')
    job_path = directory / 'job.json'
    if not job_path.is_file():
        errors.append('terminal job evidence missing')
    else:
        job = b.read(job_path)
        if job.get('status') != actual_status or job.get('error'):
            errors.append('terminal API status/error differs')
    try:
        listed = json.loads((directory / 'assets-list.bin').read_bytes())
        if not isinstance(listed, list):
            raise ValueError('asset list shape')
    except (OSError, ValueError):
        listed = []
        errors.append('asset response is not complete JSON')
    assets = entry.get('assets')
    if not isinstance(assets, list):
        assets = []
        errors.append('asset download capture missing')
    by_path = {}
    for asset in assets:
        path = b.repo_path(asset['path'])
        if asset.get('status') != 200 or not path.is_file() or b.digest(path) != asset.get('sha256'):
            errors.append('asset GET/bytes/SHA closure failed')
        by_path[urlsplit(asset['public_path']).path] = asset
    for expected in listed:
        actual = by_path.get(urlsplit(expected['download_url']).path)
        if not actual or actual.get('sha256') != expected.get('sha256'):
            errors.append('declared public asset is missing or different')
    if md.is_file() and entry.get('page_count'):
        actual_pages = [int(x) for x in re.findall(rb'<!--\s*page:\s*(\d+)\s*-->', md.read_bytes())]
        if sorted(actual_pages) != list(range(1, entry['page_count'] + 1)):
            errors.append('whole-document page marker coverage differs')
    return {'transport_complete': not errors, 'capture_status': 'completed' if not errors else 'failed',
            'actual_job_status': actual_status, 'quality_fully_resolved': actual_status == 'completed',
            'quality_status_scope': 'API completed/partial state, never an original-source accuracy claim',
            'errors': errors, 'assets_checked': len(assets), 'declared_assets': len(listed),
            'event_response_bytes': (directory / 'events.bin').stat().st_size
                if (directory / 'events.bin').is_file() else None,
            'event_scope': 'Exact successful GET response; terminal SSE may be empty. No complete historical event timeline claim.'}


def aggregate(cases: list[dict[str, Any]], completion_scope: str) -> dict[str, Any]:
    transport_complete = bool(cases) and all(x.get('capture_status') == 'completed' for x in cases)
    fully_resolved = bool(cases) and all(x.get('actual_job_status', x.get('status')) == 'completed' for x in cases)
    return {'status': 'completed' if transport_complete and (completion_scope == 'capture' or fully_resolved) else 'failed',
            'completion_scope': 'transport_capture' if completion_scope == 'capture' else 'documents_completed',
            'transport_complete': transport_complete, 'quality_fully_resolved': fully_resolved,
            'actual_job_status_counts': dict(Counter(x.get('actual_job_status', x.get('status')) for x in cases)),
            'partial_document_ids': [x['id'] for x in cases if x.get('actual_job_status', x.get('status')) == 'partial'],
            'status_definition': 'Experiment capture completion, not all document structures resolved; API states preserved separately' if completion_scope == 'capture' else 'Transport closure plus every API job completed'}


def capture_http(args: argparse.Namespace) -> dict[str, Any]:
    registered = b.method(args.method)
    data, documents = b.load_dataset(args.dataset)
    cohort = next((x for x in data['cohorts'] if x['id'] == args.cohort), None)
    if cohort is None or not cohort.get('whole_documents'):
        raise ValueError('Registered whole-document cohort required')
    validation = b.validate_dataset(args.dataset, require_sources=True)
    if not validation['valid']:
        raise ValueError('; '.join(validation['errors']))
    if args.output.exists():
        raise ValueError('Prior requests are immutable; choose a new output')
    args.output.mkdir(parents=True)
    api_key = args.api_key_file.read_text().strip() if args.api_key_file else os.environ.get(args.api_key_env or 'MOPARSE_API_KEY')
    headers = {'X-API-Key': api_key} if api_key else {}
    run = {'schema': 'moparse-http-run/2', 'started_at': b.utc(), 'method_id': args.method,
           'method_fingerprint': registered['fingerprint'], 'dataset': b.artifact(args.dataset), 'cohort_id': args.cohort,
           'request_policy': {'scan_policy': 'auto', 'unit_range': 'omitted', 'full_document': True},
           'server_deployment': b.read(args.deployment) if args.deployment else None,
           'server_deployment_verified': False, 'method_identity_limit': 'Separately verified deployed identity required',
           'capture_tool': b.artifact(Path(__file__)), 'frozen_transport_helpers': b.artifact(Path(b.__file__)),
           'requested_completion_scope': args.completion_scope, 'cases': []}
    b.save(args.output / 'plan.json', run)
    with httpx.Client(base_url=args.base_url.rstrip('/'), headers=headers, timeout=args.timeout, trust_env=False) as client, b.ResourceSampler(args.output / 'resources.json', args.sample_interval):
        for document in documents:
            if document['id'] not in cohort['document_ids']:
                continue
            source = b.repo_path(document['source_path'])
            directory = args.output / 'cases' / document['id']
            directory.mkdir(parents=True)
            b.save(directory / 'request.json', {'source': b.artifact(source), 'endpoint': '/v1/content/parse',
                                               'form': {'scan_policy': 'auto'}, 'unit_range_omitted': True})
            started = time.perf_counter()
            entry: dict[str, Any] = {'id': document['id'], 'source': document['source_path'],
                                    'source_sha256': document['sha256'], 'page_count': document['page_count'],
                                    'status': 'failed', 'capture_status': 'failed'}
            try:
                with source.open('rb') as handle:
                    response = client.post('/v1/content/parse', data={'scan_policy': 'auto'},
                                           files={'file': (source.name, handle, 'application/pdf')})
                (directory / 'response-body.bin').write_bytes(response.content)
                b.save(directory / 'response.json', {'status': response.status_code, 'headers': dict(response.headers)})
                entry.update(submit_http_status=response.status_code, http_status=response.status_code)
                if response.status_code not in {200, 202}:
                    raise ValueError(f'Parse submission failed HTTP {response.status_code}')
                markdown, job = b.capture_final_result(client, response, directory, entry, started, args.timeout, args.poll_interval)
                entry['actual_job_status'] = job['status']
                entry['assets'] = b.capture_job_assets_and_events(client, markdown, directory, job)
                receipt = inspect_capture(directory, entry)
                entry.update({key: receipt[key] for key in ('capture_status', 'actual_job_status', 'quality_fully_resolved')})
                entry['transport_complete'] = receipt['transport_complete']
                if not receipt['transport_complete']:
                    raise ValueError('; '.join(receipt['errors']))
            except (httpx.HTTPError, ValueError) as error:
                # Preserve a known API partial/completed status even when transport
                # fails later. Failed capture is a separate permanent field.
                entry.setdefault('actual_job_status', entry['status'] if entry.get('job') else None)
                entry.update(capture_status='failed', transport_complete=False, error=str(error))
                entry['quality_fully_resolved'] = entry.get('actual_job_status') == 'completed'
            entry['full_capture_seconds'] = time.perf_counter() - started
            entry['duration_seconds'] = entry['full_capture_seconds']
            b.save(directory / 'summary.json', entry)
            run['cases'].append(entry)
    durations = [x['full_capture_seconds'] for x in run['cases']]
    run.update(aggregate(run['cases'], args.completion_scope), finished_at=b.utc(), performance={
        'scope': 'Full HTTP upload through exact received/persisted Markdown, events and all public assets; API quality states separate',
        'documents': len(durations), 'total_seconds': sum(durations),
        'median_document_seconds': statistics.median(durations) if durations else None,
        'p95_document_seconds': b.percentile(durations, .95),
        'per_page_time_limit': 'Document duration/page count is not measured per-page latency'})
    b.save(args.output / 'run.json', run)
    return {key: run[key] for key in ('method_id', 'cohort_id', 'status', 'completion_scope', 'transport_complete', 'quality_fully_resolved', 'actual_job_status_counts', 'partial_document_ids', 'performance')}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', choices=['run-http'], default='run-http')
    parser.add_argument('--method', required=True)
    parser.add_argument('--dataset', type=Path, default=b.DEFAULT_DATASET)
    parser.add_argument('--cohort', default='regression-502')
    parser.add_argument('--base-url', default='http://127.0.0.1:12303')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--deployment', type=Path)
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument('--api-key-file', type=Path)
    auth.add_argument('--api-key-env')
    parser.add_argument('--timeout', type=float, default=7200)
    parser.add_argument('--poll-interval', type=float, default=2)
    parser.add_argument('--sample-interval', type=float, default=2)
    parser.add_argument('--completion-scope', choices=['documents', 'capture'], default='documents')
    args = parser.parse_args()
    if args.sample_interval <= 0:
        parser.error('sample interval must be positive')
    result = capture_http(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
