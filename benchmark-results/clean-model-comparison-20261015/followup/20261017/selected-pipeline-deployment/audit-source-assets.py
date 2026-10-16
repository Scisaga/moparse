"""Audit already downloaded HTTP source-page images against the unchanged PDF.

Reads captured public Markdown, download responses and routing warnings only.
No HTTP request, model inference or service control is performed. Independent
PyMuPDF whole-page pixels establish visual preservation, not OCR accuracy.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re

from PIL import Image
import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
PAGE = re.compile(r'<!-- page: (\d+) -->')
ASSET = re.compile(r'/assets/(asset_[A-Za-z0-9]+)')
CATALOG_PAGE = re.compile(r'第\s*(\d+)\s*页')


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def read(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def page_assets(markdown):
    output, current_page, in_catalog = {}, None, False
    for line in markdown.splitlines():
        marker = PAGE.fullmatch(line.strip())
        if marker:
            current_page = int(marker[1])
        if line.strip() == '## 图片资产':
            in_catalog = True
        ids = set(ASSET.findall(line))
        if not ids:
            continue
        # The public asset catalogue is appended after all PDF pages. Its own
        # explicit source-page label, never its physical position or filename,
        # identifies each asset's source page.
        pages = [int(number) for number in CATALOG_PAGE.findall(line)] if in_catalog else [current_page]
        for number in pages:
            if number is not None:
                output.setdefault(number, set()).update(ids)
    return {number: sorted(ids) for number, ids in output.items()}


def source_file(args, planned):
    return args.sources / (planned['source'] + '.pdf')


def audit_case(args, planned):
    stem = planned['source']
    root = args.input / 'cases' / stem
    warnings = read(root / 'warnings.json')
    capture = read(root / 'asset-capture-summary.json')
    md_path = root / 'result.md'
    if warnings is None or capture is None or not md_path.is_file():
        return {'source': stem, 'status': 'unknown_incomplete_capture',
                'source_page_count': planned['page_count'], 'expected_pages': None,
                'pages': [], 'asset_downloads': []}
    md = md_path.read_bytes()
    declared = page_assets(md.decode())
    routing = [item for item in warnings.get('document_warnings', [])
               if item.get('code') == 'glm_sdk_scan_routing_used']
    expected = routing[-1].get('details', {}).get('pages') if routing else []
    if not isinstance(expected, list) or any(type(page) is not int for page in expected):
        raise ValueError(f'{stem}: Invalid captured source-page routing details')
    downloads = {item['asset_id']: item for item in capture.get('downloads', [])}
    metadata = {item['asset_id']: item for item in capture.get('metadata', [])}
    decoded, checks = {}, []
    for asset_id, item in downloads.items():
        path = Path(item['body_path']).resolve()
        if not path.is_relative_to(args.input):
            raise ValueError('Captured download body lies outside this run')
        body = path.read_bytes()
        meta = metadata[asset_id]
        valid = (item.get('http_status') == 200 and sha(body) == meta.get('sha256')
                 and len(body) == meta.get('size_bytes'))
        check = {'asset_id': asset_id, 'HTTP_status': item.get('http_status'),
                 'body_path': str(path), 'body_SHA256': sha(body),
                 'body_bytes': len(body), 'declared_SHA_and_size_match': valid}
        try:
            with Image.open(io.BytesIO(body)) as image:
                pixels = image.convert('RGB').tobytes()
                decoded[asset_id] = (image.size, sha(pixels), valid)
                check.update(decoded_size=list(image.size), RGB_pixels_SHA256=sha(pixels))
        except (OSError, ValueError) as error:
            check['decode_error'] = type(error).__name__
        checks.append(check)
    source = source_file(args, planned)
    source_sha = sha(source.read_bytes())
    if source_sha != planned['sha256']:
        raise ValueError(f'{stem}: Original source SHA differs from the captured request plan')
    pages = []
    with pymupdf.open(source) as document:
        if len(document) != planned['page_count']:
            raise ValueError(f'{stem}: Original page count differs from the captured request plan')
        for number in expected:
            reference = document[number - 1].get_pixmap(
                matrix=pymupdf.Matrix(args.asset_scale, args.asset_scale), alpha=False,
            )
            size, pixel_sha = (reference.width, reference.height), sha(reference.samples)
            linked = declared.get(number, [])
            matches = [asset for asset in linked if decoded.get(asset) == (size, pixel_sha, True)]
            pages.append({'source_page': number, 'source_PDF_rotation': document[number - 1].rotation,
                          'reference_RGB_size': list(size), 'reference_RGB_pixels_SHA256': pixel_sha,
                          'public_MD_linked_asset_ids': linked, 'matching_downloaded_asset_ids': matches,
                          'status': 'pass' if matches else 'missing_or_different_source_image'})
    statuses = Counter(page['status'] for page in pages)
    downloads_ok = all(item['declared_SHA_and_size_match'] for item in checks)
    return {'source': stem, 'source_page_count': planned['page_count'],
            'source_path': str(source), 'source_SHA256': source_sha,
            'public_MD_path': str(md_path), 'public_MD_SHA256': sha(md),
            'expected_pages': expected, 'scope': 'Every SDK-routed scanned/mixed page in captured warnings',
            'pages': pages, 'page_statuses': dict(statuses), 'asset_downloads': checks,
            'all_downloads_SHA_and_size_match': downloads_ok,
            'status': 'pass' if downloads_ok and statuses['pass'] == len(pages) else 'fail'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--sources', type=Path, default=REPO / 'pdf_sample')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--asset-scale', type=float, default=2.0,
                        help='Independent raster scale for source assets, separate from SDK OCR DPI.')
    args = parser.parse_args()
    args.input = args.input.resolve()
    output = (args.output or args.input / 'source-assets-audit.json').resolve()
    if not args.input.is_relative_to(HERE) or not output.is_relative_to(HERE):
        raise ValueError('Capture and audit output must stay under selected-pipeline-deployment')
    if args.asset_scale <= 0:
        raise ValueError('Asset scale must be positive')
    plan = read(args.input / 'run-plan.json')
    if plan is None:
        raise ValueError('Captured run-plan.json is required')
    cases = [audit_case(args, planned) for planned in plan['sources']]
    complete = all(case['status'] != 'unknown_incomplete_capture' for case in cases)
    pages = [page for case in cases for page in case['pages']]
    counts = dict(Counter(page['status'] for page in pages))
    result = {'schema': 'captured-HTTP-source-page-pixel-audit/1', 'run': str(args.input),
              'status': 'incomplete' if not complete else 'pass' if all(case['status'] == 'pass' for case in cases) else 'fail',
              'expected_documents': len(cases), 'expected_document_pages': plan['pages'],
              'finished_documents': sum(case['status'] != 'unknown_incomplete_capture' for case in cases),
              'expected_routed_source_images': len(pages) if complete else None,
              'observed_routed_source_images': len(pages), 'source_image_statuses': counts,
              'observed_download_count': sum(len(case['asset_downloads']) for case in cases),
              'verified_download_count': sum(item['declared_SHA_and_size_match']
                                             for case in cases for item in case['asset_downloads']),
              'asset_raster_scale': args.asset_scale, 'PDF_engine': 'PyMuPDF ' + pymupdf.VersionBind,
              'reference_method': 'Original PDF get_pixmap with scale and original PDF rotation; compare decoded RGB dimensions and pixel SHA. No parser image-render helper is called.',
              'page_association': 'Public asset-catalogue source-page label, or enclosing original page marker for inline links. Never infer source page from asset filename or catalogue position.',
              'limitations': ['Visual preservation does not prove OCR or table accuracy.',
                              'Public HTTP asset metadata does not expose private IR unit.asset_ids; fixture integration tests verify that internal association separately.',
                              'Expected source pages come from captured SDK routing warnings; this does not independently prove page classifier correctness.'],
              'cases': cases, 'audit_script_SHA256': sha(Path(__file__).read_bytes()),
              'models_called': False, 'HTTP_requests_sent': False,
              'source_PDFs_or_received_outputs_modified': False}
    save(output, result)
    print(json.dumps({key: result[key] for key in ['status', 'finished_documents',
          'expected_routed_source_images', 'source_image_statuses', 'verified_download_count']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
