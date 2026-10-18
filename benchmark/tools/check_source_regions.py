"""Read-only posthoc original-region preservation checks; never calls a parser/model.

The source source-region truth and unchanged-table regression are separate from
existing fixed source assertions. Pixel/text preservation does not reconstruct
unknown table/chart semantics or correct pre-existing table defects.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
from pathlib import Path
from typing import Any

import pymupdf
import pypdfium2 as pdfium
from benchmark import moparse_benchmark as bench
from benchmark.tools import check_release as release
from benchmark.tools.capture_transport import inspect_capture
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def normalized_table(table: dict[str, Any]) -> dict[str, Any]:
    return {key: table[key] for key in ('id', 'rows', 'meta', 'sources', 'rendered_page')}


def public_region(markdown: str, region: dict[str, Any]) -> dict[str, Any]:
    ref, page = region['source_ref'], region['page_number']
    opener = f'<!-- source-region: {ref}; source-page: {page}; structure: unknown -->'
    closer = f'<!-- /source-region: {ref} -->'
    result: dict[str, Any] = {'opening_marker_unique': markdown.count(opener) == 1,
                              'closing_marker_unique': markdown.count(closer) == 1}
    if not all(result.values()):
        return {**result, 'pass': False}
    start, stop = markdown.index(opener), markdown.index(closer)
    if stop <= start:
        return {**result, 'markers_ordered': False, 'pass': False}
    payload = markdown[start + len(opener):stop]
    pages = list(re.finditer(r'<!--\s*page:\s*(\d+)\s*-->', markdown[:start]))
    result['source_page_scope_matches'] = bool(pages and int(pages[-1][1]) == page)
    reader = release.load_reader()
    tokens = reader.MARKDOWN.parse(payload)
    fences = [token for token in tokens if token.type == 'fence']
    images = [child for token in tokens for child in token.children or [] if child.type == 'image']
    literal = region['literal_text']
    serialization_newline = '' if literal.endswith(('\n', '\r')) else '\n'
    # CommonMark normalizes CRLF internally. Compare the original fence bytes,
    # preserving source line endings and trailing spaces independently of that
    # rendered-token representation.
    raw_lines = list(re.finditer(r'[^\r\n]*(?:\r\n|\r|\n|$)', payload))
    openings = [(index, line, re.fullmatch(r'(`{3,})text[\r\n]+', line[0]))
                for index, line in enumerate(raw_lines)]
    openings = [entry for entry in openings if entry[2] is not None]
    raw_body = None
    if len(openings) == 1:
        index, opening, match = openings[0]
        assert match is not None
        closing = next((line for line in raw_lines[index + 1:]
                        if line[0].rstrip('\r\n') == match[1]), None)
        if closing is not None:
            raw_body = payload[opening.end():closing.start()]
    result['literal_fence_exact'] = (len(fences) == 1 and fences[0].info == 'text'
                                     and raw_body == literal + serialization_newline)
    result['one_source_image'] = len(images) == 1
    result['image_public_path'] = images[0].attrGet('src') if len(images) == 1 else None
    result['private_HTML_not_exposed'] = not region.get('raw_model_table_html') or region['raw_model_table_html'] not in payload
    # Other visible payload, tables or additional source regions are not a faithful
    # rendering of the one literal source region, even if the correct fence exists.
    allowed = {'paragraph_open', 'paragraph_close', 'inline', 'fence'}
    result['no_extra_payload_blocks'] = all(token.type in allowed for token in tokens)
    result['no_extra_visible_payload'] = all(
        token.type != 'inline' or (len(token.children or []) == 1 and token.children[0].type == 'image')
        for token in tokens)
    result['source_Launch_occurrences'] = len(re.findall(r'\bLaunch\b', literal))
    result['source_region_payload_SHA256'] = hashlib.sha256(payload.encode()).hexdigest()
    conditions = [value for key, value in result.items() if key not in {
        'image_public_path', 'source_Launch_occurrences', 'source_region_payload_SHA256'}]
    result['pass'] = all(value is True for value in conditions)
    return result


def original_glyphs(source: Path, region: dict[str, Any]) -> dict[str, Any]:
    """Independent original-PDF index/bbox/text checks for this unrotated source.

    Unsupported transforms stay unknown; they never become an inferred success.
    This acceptance code imports no application parser or rendering service.
    """
    with pdfium.PdfDocument(source) as document:
        page = document[region['page_number'] - 1]
        textpage = page.get_textpage()
        try:
            width, height = page.get_size()
            if page.get_rotation() != 0 or tuple(page.get_bbox()[:2]) != (0, 0):
                return {'pass': False, 'status': 'unknown_independent_transform_not_implemented'}
            left, top, right, bottom = region['normalized_bbox']
            target = (left * width, top * height, right * width, bottom * height)
            literal = textpage.get_text_bounded(target[0], height-target[3], target[2], height-target[1])
            expected = []
            for index in range(textpage.count_chars()):
                x0, y0, x1, y1 = textpage.get_charbox(index)
                bbox = (x0, height-y1, x1, height-y0)
                if min(bbox[2], target[2]) > max(bbox[0], target[0]) and min(bbox[3], target[3]) > max(bbox[1], target[1]):
                    expected.append({'character_index': index,
                        'literal_text': textpage.get_text_range(index=index, count=1), 'bbox_top_left': bbox})
            observed = region['glyphs']
            mismatches = []
            if len(observed) == len(expected):
                for wanted, actual in zip(expected, observed, strict=True):
                    if (wanted['character_index'] != actual['character_index']
                            or wanted['literal_text'] != actual['literal_text']
                            or len(actual['bbox_top_left']) != 4
                            or not all(math.isclose(a, b, rel_tol=0, abs_tol=1e-6)
                                       for a, b in zip(wanted['bbox_top_left'], actual['bbox_top_left'], strict=True))):
                        mismatches.append({'expected': wanted, 'actual': actual})
            geometry = (region['rotation_degrees'] == 0 and region['page_width'] == width and region['page_height'] == height)
            return {'pass': bool(expected) and geometry and len(expected) == len(observed)
                    and not mismatches and literal == region['literal_text'],
                'status': 'observed', 'original_PDF_glyph_count': len(expected),
                'retained_glyph_count': len(observed), 'all_indices_characters_and_boxes_exact': len(expected) == len(observed) and not mismatches,
                'literal_bounded_text_exact': literal == region['literal_text'], 'page_geometry_exact': geometry,
                'mismatches': mismatches, 'source_literal_text_SHA256': hashlib.sha256(literal.encode()).hexdigest(),
                'source_literal_bytes': len(literal.encode()),
                'source_Launch_occurrences': len(re.findall(r'\bLaunch\b', literal)),
                'model_text_used_as_source_truth': False}
        finally:
            textpage.close()
            page.close()


def expected_png(source: Path, region: dict[str, Any]) -> bytes:
    """Render source pixels at the existing export contract's 144 DPI crop frame."""
    with pymupdf.open(source) as document:
        pixmap = document[region['page_number'] - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        frame = Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)
    left, top, right, bottom = region['normalized_bbox']
    box = (round(left * frame.width), round(top * frame.height),
           round(right * frame.width), round(bottom * frame.height))
    output = io.BytesIO()
    frame.crop(box).save(output, format='PNG')
    return output.getvalue()


def check(capture: Path, baseline: Path, evidence: Path, source: Path,
          *, worker_evidence: Path | None = None) -> dict[str, Any]:
    reader = release.load_reader()
    summary = bench.read(capture / 'summary.json')
    original_summary = bench.read(baseline / 'summary.json')
    markdown = (capture / 'result.md').read_bytes().decode('utf-8')
    before = (baseline / 'result.md').read_bytes().decode('utf-8')
    private = bench.read(evidence)
    regions = private.get('source_regions', [])
    tests: list[dict[str, Any]] = []
    source_sha = bench.digest(source)
    transport = inspect_capture(capture, summary) if summary['status'] == 'partial' else None
    tests.append({'check': 'same_complete_source_and_received_persisted_MD', 'pass': (
        summary['status'] in {'completed', 'partial'} and original_summary['status'] == 'completed'
        and summary['source_sha256'] == original_summary['source_sha256'] == source_sha
        and summary['MD_SHA256'] == bench.digest(capture / 'result.md')
        and summary['persisted_MD_SHA256'] == bench.digest(capture / 'persisted-result.md')
        and (capture / 'result.md').read_bytes() == (capture / 'persisted-result.md').read_bytes()
        and (transport is None or transport['transport_complete'])),
        'actual_job_status': summary['status'], 'transport_receipt': transport,
        'quality_fully_resolved': summary['status'] == 'completed'})
    tests.append({'check': 'one_original_source_region_retained_privately', 'pass': len(regions) == 1})
    if len(regions) != 1:
        return {'schema': 'moparse-posthoc-source-preservation-acceptance/1', 'pass': False, 'checks': tests,
                'reason': 'Expected the independently source-reviewed NASA schedule region; source semantics not reconstructed'}
    region = regions[0]
    tests.append({'check': 'private_region_same_source_SHA', 'pass': region['source_sha256'] == source_sha})
    public = public_region(markdown, region)
    tests.append({'check': 'public_unknown_original_image_literal_source_only', 'pass': public['pass'], 'observation': public})
    glyph = original_glyphs(source, region)
    tests.append({'check': 'original_PDF_indices_character_bboxes_and_bounded_text', 'pass': glyph['pass'], 'observation': glyph})
    tests.append({'check': 'one_Launch_in_original_region_not_generated_repetition',
                  'pass': glyph.get('source_Launch_occurrences') == public.get('source_Launch_occurrences') == 1})
    asset_matches = [asset for asset in summary['assets'] if asset['public_path'] == public.get('image_public_path')]
    image_test: dict[str, Any] = {'check': 'source_region_PNG_original_crop_exact', 'pass': False, 'matching_captured_assets': len(asset_matches)}
    if len(asset_matches) == 1:
        asset = asset_matches[0]
        path = bench.repo_path(asset['path'])
        expected, actual = expected_png(source, region), path.read_bytes()
        image_test.update({'pass': asset['status'] == 200 and bench.digest(path) == asset['sha256']
                          and expected == actual, 'asset': bench.artifact(path),
                          'source_rendered_PNG_SHA256': hashlib.sha256(expected).hexdigest(),
                          'encoded_PNG_bytes_exact': expected == actual})
        with Image.open(io.BytesIO(expected)) as wanted, Image.open(io.BytesIO(actual)) as received:
            image_test['pixels_exact'] = wanted.size == received.size and wanted.convert('RGB').tobytes() == received.convert('RGB').tobytes()
            image_test['pixels'] = list(wanted.size)
    tests.append(image_test)
    rejected = region['source_ref']
    a, z = reader.public_tables(before), reader.public_tables(markdown)
    original_tables = {t['id']: normalized_table(t) for t in a if t['id'] != rejected}
    current_tables = {t['id']: normalized_table(t) for t in z}
    unchanged = original_tables == current_tables
    tests.append({'check': 'other_four_public_tables_cells_spans_scope_and_sources_unchanged_from_V4',
                  'pass': unchanged and len(original_tables) == len(current_tables) == 4,
                  'old_count': len(original_tables), 'new_count': len(current_tables),
                  'changed_or_missing_IDs': sorted(k for k in set(original_tables) | set(current_tables)
                      if original_tables.get(k) != current_tables.get(k))})
    tests.append({'check': 'rejected_generated_table_not_public', 'pass': all(t['id'] != rejected for t in z)
                  and bool(region.get('raw_model_table_html')) and bool(region.get('original_table'))})
    public_assets = json.loads((capture / 'assets-list.bin').read_bytes())
    forbidden = {'glyphs', 'raw_model_table_html', 'original_table', 'character_observation', 'independent_evidence', 'normalized_bbox', 'source_sha256'}
    keys: set[str] = set()
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            keys.update(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(public_assets)
    tests.append({'check': 'private_evidence_not_in_public_asset_index', 'pass': not (keys & forbidden), 'forbidden_keys_found': sorted(keys & forbidden)})
    if worker_evidence is not None:
        tests.append({'check': 'original_native_worker_bytes_retained_privately', 'pass': worker_evidence.is_file() and worker_evidence.stat().st_size > 0,
                      'private_artifact': bench.artifact(worker_evidence)})
    return {'schema': 'moparse-posthoc-source-preservation-acceptance/1', 'created_at': bench.utc(),
        'role': 'B: source preservation and no new regression relative to exposed V4. Separate A checks retain original physical table truth failures.',
        'pass': all(t['pass'] is True for t in tests), 'checks': tests,
        'actual_job_status': summary['status'],
        'capture_status': 'completed' if transport is not None and transport['transport_complete'] else summary.get('capture_status', summary['status']),
        'transport_complete': transport['transport_complete'] if transport is not None else True,
        'quality_fully_resolved': summary['status'] == 'completed',
        'capture_MD': bench.artifact(capture / 'result.md'), 'baseline_MD': bench.artifact(baseline / 'result.md'),
        'private_source_evidence': bench.artifact(evidence), 'original_source': bench.artifact(source),
        'checker': bench.artifact(Path(__file__)), 'source_glyph_truth_from_model': False,
        'claim_recovered_Gantt_semantics': False, 'existing_title_or_shape_defects_repaired_claim': False,
        'IR_unknown_runtime_serialization_directly_observed': False,
        'IR_note': 'This read-only checker verifies actual public unknown markers and retained source evidence. Ephemeral typed IR is covered separately by source-frozen integration tests; not falsely claimed as persisted HTTP telemetry.',
        'fixed28_gold_or_reader_changed': False, 'new_inference_or_HTTP_calls': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('capture', 'baseline', 'evidence', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--worker-evidence', type=Path)
    args = parser.parse_args()
    result = check(args.capture, args.baseline, args.evidence, args.source, worker_evidence=args.worker_evidence)
    bench.save(args.output, result)
    print(json.dumps({'output': str(args.output), 'pass': result['pass'], 'checks': len(result['checks'])}))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
