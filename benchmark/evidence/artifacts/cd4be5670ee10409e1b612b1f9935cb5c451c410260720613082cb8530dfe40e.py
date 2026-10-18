"""Independent post-freeze benchmark checks catch source evidence corruption."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pymupdf
import pypdfium2 as pdfium
import pytest

from benchmark import moparse_benchmark as bench
from benchmark.tools.check_source_regions import check, expected_png, original_glyphs, public_region


def rendered_region(literal: str, *, fence: str = '```') -> tuple[str, dict]:
    region = {'source_ref': 'source1', 'page_number': 2, 'literal_text': literal,
              'raw_model_table_html': '<table>model-repeat</table>'}
    newline = '' if literal.endswith(('\r', '\n')) else '\n'
    markdown = ('<!-- page: 2 -->\n<!-- source-region: source1; source-page: 2; structure: unknown -->\n\n'
                '![原件区域（结构未知）](/original.png)\n\n' + fence + 'text\n' + literal + newline
                + fence + '\n\n<!-- /source-region: source1 -->')
    return markdown, region


@pytest.mark.parametrize('literal,fence', [
    ('Launch -1,234.56 <literal> &amp;  ', '```'),
    ('Launch\r\n-1,234.56\r\n  ', '```'),
    ('Launch `code` ``` literal\n', '````'),
])
def test_original_fence_preserves_source_bytes_not_rendered_HTML(literal, fence):
    markdown, region = rendered_region(literal, fence=fence)
    assert public_region(markdown, region)['pass']


@pytest.mark.parametrize('before,after', [
    ('-1,234.56', '1,234.56'),
    ('-1,234.56', '-1.234,56'),
    ('<literal>', 'literal'),
    ('&amp;', '&'),
    ('&amp;  ', '&amp; '),
    ('structure: unknown', 'structure: table'),
    ('<!-- /source-region: source1 -->', ''),
    ('![原件区域（结构未知）](/original.png)', ''),
])
def test_public_source_tampering_or_missing_scope_is_rejected(before, after):
    markdown, region = rendered_region('Launch -1,234.56 <literal> &amp;  ')
    assert not public_region(markdown.replace(before, after), region)['pass']


def test_faithful_fence_cannot_hide_extra_generated_data():
    markdown, region = rendered_region('Launch -1,234.56')
    markdown = markdown.replace('<!-- /source-region: source1 -->',
                                'generated amount 999\n\n<!-- /source-region: source1 -->')
    assert not public_region(markdown, region)['pass']


def fixture_glyph_region(source: Path) -> dict:
    with pdfium.PdfDocument(source) as document:
        page = document[0]
        text = page.get_textpage()
        try:
            width, height = page.get_size()
            # This fixture has one visible line and no crop transform; record
            # index evidence as an input then mutate it in the negative tests.
            glyphs = []
            for index in range(text.count_chars()):
                left, bottom, right, top = text.get_charbox(index)
                if right > left and top > bottom:
                    glyphs.append({'character_index': index,
                        'literal_text': text.get_text_range(index=index, count=1),
                        'bbox_top_left': [left, height-top, right, height-bottom]})
            return {'page_number': 1, 'normalized_bbox': [0, 0, 1, 1],
                    'literal_text': text.get_text_bounded(0, 0, width, height),
                    'glyphs': glyphs, 'rotation_degrees': 0,
                    'page_width': width, 'page_height': height}
        finally:
            text.close()
            page.close()


@pytest.mark.parametrize('damage', ['delete', 'character', 'index', 'bbox', 'literal_sign'])
def test_source_glyph_truth_is_read_from_original_PDF(tmp_path, damage):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        page = document.new_page(width=200, height=100)
        page.insert_text((20, 30), 'Launch -1,234.56')
        document.save(source)
    region = fixture_glyph_region(source)
    assert original_glyphs(source, region)['pass']
    broken = deepcopy(region)
    if damage == 'delete':
        broken['glyphs'].pop()
    elif damage == 'character':
        broken['glyphs'][0]['literal_text'] = 'X'
    elif damage == 'index':
        broken['glyphs'][0]['character_index'] = 99
    elif damage == 'bbox':
        broken['glyphs'][0]['bbox_top_left'][0] += 2
    else:
        broken['literal_text'] = broken['literal_text'].replace('-1', '1')
    assert not original_glyphs(source, broken)['pass']


def test_complete_capture_reads_literal_CRLF_without_text_mode_translation(tmp_path):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        page = document.new_page(width=200, height=100)
        page.insert_text((20, 30), 'Launch -1,234.56')
        page.insert_text((20, 50), 'Second line')
        document.save(source)
    region = fixture_glyph_region(source)
    assert '\r\n' in region['literal_text']
    region.update(source_ref='source1', source_sha256=bench.digest(source),
                  raw_model_table_html='<table>model-repeat</table>',
                  original_table={'rows': [['model-repeat']]})
    unknown, _ = rendered_region(region['literal_text'])
    unknown = unknown.replace('page: 2', 'page: 1').replace('source-page: 2', 'source-page: 1')
    pieces = []
    for identifier in ('t1', 't2', 't3', 't4'):
        pieces.append(f'<!-- table-fragment: {identifier} -->\n'
                      '<!-- table-structure: {"source_pages":[1],"spans":[]} -->\n'
                      '| label | value |\n| --- | --- |\n| source | 1 |\n')
    tables = '\n'.join(pieces)
    # rendered_region includes a page marker; table fixtures also remain on p1.
    markdown = '<!-- page: 1 -->\n' + tables + unknown
    prior = '<!-- page: 1 -->\n' + tables
    capture, baseline = tmp_path / 'current', tmp_path / 'previous'
    capture.mkdir()
    baseline.mkdir()
    for path in (capture / 'result.md', capture / 'persisted-result.md'):
        path.write_bytes(markdown.encode())
    (baseline / 'result.md').write_bytes(prior.encode())
    png = tmp_path / 'original.png'
    png.write_bytes(expected_png(source, region))
    current = {'status': 'completed', 'source_sha256': bench.digest(source),
               'MD_SHA256': bench.digest(capture / 'result.md'),
               'persisted_MD_SHA256': bench.digest(capture / 'persisted-result.md'),
               'assets': [{'public_path': '/original.png', 'path': str(png),
                           'sha256': bench.digest(png), 'status': 200}]}
    (capture / 'summary.json').write_text(json.dumps(current))
    (baseline / 'summary.json').write_text(json.dumps({'status': 'completed',
                                                    'source_sha256': bench.digest(source)}))
    (capture / 'assets-list.bin').write_bytes(b'[]')
    evidence = tmp_path / 'private.json'
    evidence.write_text(json.dumps({'source_regions': [region]}))
    outcome = check(capture, baseline, evidence, source)
    assert outcome['pass'], outcome
    assert not outcome['IR_unknown_runtime_serialization_directly_observed']
