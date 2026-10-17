"""Read-only source-to-output diagnostics; no model/API inference calls."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re

os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-4:])
from docvortex.document.pdf import PDFDocument
import pypdfium2

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flatten(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from flatten(item)
    elif isinstance(value, list):
        for item in value:
            yield from flatten(item)
    elif isinstance(value, str):
        yield value


def box(value):
    return list(value.bbox if hasattr(value, 'bbox') else value)


def contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def native_source(path, page_index):
    with PDFDocument(str(path)) as document:
        geometry = document.get_page_chars_with_geometry(page_index)
        # The source footnote is a single explicitly inspected source text object.
        # Selection below records a physical region, not an injected output string.
        chars = [char for char in geometry.chars
                 if 396 < float(box(char['bbox'])[0]) < 410 and not char['char'].isspace()]
        return {'page_size': document.page_size(page_index), 'page_rotation': document.page_rotation(page_index),
                'source_text': ''.join(char['char'] for char in chars),
                'characters': [{'char': char['char'], 'char_idx': char['char_idx'],
                                'bbox': box(char['bbox']), 'tight_bbox': list(geometry.tight_bboxes[char['char_idx']]),
                                'origin': list(geometry.origins[char['char_idx']]),
                                'rotation': char['rotation'], 'writing_angle': char.get('writing_angle'),
                                'text_render_mode': char.get('text_render_mode'),
                                'source_indices': char.get('source_indices')}
                               for char in chars]}


def main():
    folder = HERE / 'official-native-advanced' / '1225475375-p87'
    request = read(folder / 'request.json')
    source = Path(request['pdf'])
    prepared = folder / 'prepared-by-official-page-selection.pdf'
    original = native_source(source, 86)
    derived = native_source(prepared, 0)
    events = read(folder / 'official-stage-observations.json')
    fill = next(event for event in events if event['stage'] == 'native_PDF_text_fill')
    span = next(span for span in fill['spans'] if '债权' in span['text'])
    response_path = folder / 'model-http' / '000' / 'response.json'
    response = read(response_path)['choices'][0]['message']['content']
    layout_line = next(line for line in response.splitlines() if 'table_footnote' in line)
    numbers = [int(value) / 1000 for value in re.search(r'<\|box_start\|>(.*?)<\|box_end\|>', layout_line).group(1).split()]
    width, height = derived['page_size']
    absolute = [numbers[0] * width, numbers[1] * height, numbers[2] * width, numbers[3] * height]
    for char in derived['characters']:
        char['tight_bbox_inside_model_layout'] = contains(absolute, char['tight_bbox'])
        char['tight_bbox_inside_native_fill_span'] = contains(span['bbox'], char['tight_bbox'])
    downstream = {}
    for filename in ('official-saved/model_output.json', 'official-saved/middle_json.json', 'result.json'):
        path = folder / filename
        values = [value for value in flatten(read(path)) if '债权投资公允价值变动源于应收款' in value]
        downstream[filename] = {'SHA256': sha(path), 'matching_raw_strings': values,
                                'contains_full_source_text': derived['source_text'] in values}
    for filename in ('result.md', 'result-full.md'):
        path = folder / filename
        text = path.read_text()
        downstream[filename] = {'SHA256': sha(path), 'contains_full_source_text': derived['source_text'] in text,
                                'contains_native_fill_text': span['text'] in text}
    footnote = {
        'source_PDF': str(source), 'source_SHA256': sha(source), 'original_physical_page_one_based': 87,
        'prepared_PDF_SHA256': sha(prepared),
        'source_original': original, 'source_official_selected_PDF': derived,
        'source_text_preserved_by_official_page_selection': original['source_text'] == derived['source_text'],
        'model_layout_response_file': str(response_path.relative_to(HERE)),
        'model_layout_response_SHA256': sha(response_path), 'model_layout_raw_footnote_line': layout_line,
        'model_layout_normalized_bbox': numbers, 'model_layout_absolute_bbox': absolute,
        'native_fill_returned_span': span,
        'native_fill_returned_text_character_count': len(span['text']),
        'source_text_character_count': len(derived['source_text']),
        'all_source_tight_boxes_inside_model_layout': all(char['tight_bbox_inside_model_layout'] for char in derived['characters']),
        'all_source_tight_boxes_inside_native_fill_span': all(char['tight_bbox_inside_native_fill_span'] for char in derived['characters']),
        'post_OCR': next(event for event in events if event['stage'] == 'actual_post_OCR'),
        'downstream': downstream,
        'observed_failure_layer': 'Native TXT span filling: full source glyphs survive page selection and fit the model layout/native-fill span boxes, but the first recorded return from _fill_native_pdf_text_spans is already truncated. The same truncated content then survives ModelJson, MiddleJson and both Markdown renderers unchanged.',
        'not_proven': 'This observer did not instrument individual Rust/native span matching predicates; the exact lower-level cause of the seven skipped source characters is not established. No new inference, output repair or source-text injection was performed.',
    }
    standard = {}
    for name in ('1225475375-p62', '1225475375-p87', '1225473526-p7', '1225474693-p3'):
        directory = HERE / 'official-native-standard' / name
        recovery_path = directory / 'native-table-recovery.json'
        observations = read(directory / 'official-stage-observations.json')
        standard[name] = {
            'request': read(directory / 'request.json'),
            'native_recovery_file': str(recovery_path.relative_to(HERE)), 'native_recovery_SHA256': sha(recovery_path),
            'routes': [event for event in observations if event['stage'] == 'native_table_priority'],
            'returned_native_tables': [
                {'rows': item['rows'], 'cols': item['cols'], 'source': item['source'],
                 'confidence': item['confidence'], 'diagnostics': item['diagnostics'],
                 'first_cells': [{'row': cell['row'], 'col': cell['col'], 'content': cell['content']} for cell in item['cells'][:5]]}
                for item in read(recovery_path) if item.get('stage') == 'internal_NativeTableResult'],
            'quality_verdict_reference': 'Independent original-PDF source-acceptance JSONs under BASE/model-evaluation; acceptance/confidence above is official routing, not a correctness guarantee.',
        }
    p19 = HERE / 'official-native-standard' / '1225474739-p19'
    quotes = {}
    for label, path, index in (('original', Path(read(p19 / 'request.json')['pdf']), 18),
                                ('official_selected_PDF', p19 / 'prepared-by-official-page-selection.pdf', 0)):
        with pypdfium2.PdfDocument(path) as document:
            text = document[index].get_textpage().get_text_range()
        quotes[label] = {'path': str(path), 'SHA256': sha(path),
                         'quote_counts': {char: text.count(char) for char in ('“', '”', '"')}}
    normalizer = Path(__import__('docvortex').__file__).parent / 'analyzers/native/pdf/spatial_text.py'
    quotes.update({'native_recovered_long_cells': [cell['content']
                  for item in read(p19 / 'native-table-recovery.json') if item.get('stage') == 'internal_NativeTableResult'
                  for cell in item['cells'] if len(cell['content']) > 100],
                  'official_normalizer_file_SHA256': sha(normalizer),
                  'official_source': 'https://github.com/myhloli/DocVortex/blob/f5da4e69022f5b0a935fb64579d7f0f7ec7d08b6/src/docvortex/analyzers/native/pdf/spatial_text.py#L31',
                  'finding': 'Official _PUNCTUATION_TRANSLATION maps U+201C and U+201D to ASCII double quote; _normalize_table_text applies it before NativeTableResult. No VLM was used for p19.'})
    result = {'created_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'model_calls': 0,
              'diagnostic_script_SHA256': sha(Path(__file__)),
              'advanced_p87_footnote': footnote, 'standard_native_failures': standard,
              'standard_p19_punctuation_normalization': quotes}
    (HERE / 'official-native-layer-diagnostics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'source_chars': len(derived['source_text']), 'returned_chars': len(span['text']),
                      'source_preserved': footnote['source_text_preserved_by_official_page_selection'],
                      'all_tight_boxes_in_layout': footnote['all_source_tight_boxes_inside_model_layout'],
                      'all_tight_boxes_in_fill_span': footnote['all_source_tight_boxes_inside_native_fill_span']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
