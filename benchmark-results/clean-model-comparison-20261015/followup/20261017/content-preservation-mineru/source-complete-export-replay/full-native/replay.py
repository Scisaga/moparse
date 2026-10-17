"""Audit frozen native source refs through real Markdown serializers; no inference."""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = Path('/opt/mosaic-parse')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
from app.models import PageParseResult
from docling_core.types.doc import ContentLayer, DoclingDocument, TextItem
from docling_core.transforms.serializer.common import DocSerializer
from docling_core.transforms.serializer.markdown import MarkdownTextSerializer

EXPECTED = '1e350e7a20b0da8a299f0add1dbc5467d2973750e431dff507534e8e3bd733df'
OLD = REPO / 'benchmark-results/clean-model-comparison-20261015/followup/20261017/selected-pipeline-deployment'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


helper = module(OLD / 'independent-table-boundary-replay-20261017/replay.py', 'source_coverage_helpers')
source_code = (REPO / 'app/services/table_service.py').read_bytes()
assert sha(source_code) == EXPECTED
before_code = subprocess.check_output(['git', 'show', 'HEAD:app/services/table_service.py'], cwd=REPO)
(OUT / 'before-table-service.py').write_bytes(before_code)
(OUT / 'after-table-service.py').write_bytes(source_code)
versions = {
    'before': module(OUT / 'before-table-service.py', 'source_export_before'),
    'after': module(OUT / 'after-table-service.py', 'source_export_after'),
}
routing = json.loads((OLD / 'routing-source-properties-audit.json').read_text())
frozen = json.loads((OLD / 'table-export-source-audit.json').read_text())
native = {}
for item in routing['pages']:
    if item['frozen_route'] == 'native':
        native.setdefault(Path(item['document']).stem, set()).add(item['page_number'])

# Observe official serialization return values without changing any result.
original_text = MarkdownTextSerializer.serialize
original_captions = DocSerializer.serialize_captions
events = []
active_page = None


def observe_text(self, *, item, **kwargs):
    result = original_text(self, item=item, **kwargs)
    if result.text:
        events.append({'ref': item.self_ref, 'page': active_page,
                       'kind': 'text', 'rendered': result.text})
    return result


def observe_captions(self, item, **kwargs):
    result = original_captions(self, item=item, **kwargs)
    if result.text:
        for source in result.get_unique_doc_items():
            events.append({'ref': source.self_ref, 'page': active_page,
                           'kind': 'caption', 'rendered': result.text})
    return result


MarkdownTextSerializer.serialize = observe_text
DocSerializer.serialize_captions = observe_captions
started = time.monotonic()
summary = {'source_code_SHA256': EXPECTED, 'baseline_code_SHA256': sha(before_code),
           'baseline_git_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
           'model_calls': 0, 'HTTP_calls': 0, 'documents': [], 'exceptions': [],
           'interpretation': 'Frozen model output export and assembly audit only; does not establish that the model extracted every original PDF glyph correctly.'}
for entry in frozen['documents']:
    stem = Path(entry['document']).stem
    raw_path = REPO / entry['raw_docling_path']
    raw = raw_path.read_bytes()
    assert sha(raw) == entry['raw_docling_SHA256']
    input_path = REPO / 'pdf_sample' / f'{stem}.pdf'
    model_result = json.loads((raw_path.parent / 'result.json').read_text())
    assert sha(input_path.read_bytes()) == model_result['source']['sha256']
    selected = native.get(stem, set())
    doc = DoclingDocument.model_validate_json(raw)
    model_sha_before = sha(doc.model_dump_json().encode())
    scopes = {item['fragment']: item['complete_runtime_header_rows']
              for item in frozen['tables'] if item['document'] == entry['document']}
    expected_visible = {item.self_ref: item for item in doc.texts
                        if item.content_layer in {ContentLayer.BODY, ContentLayer.FURNITURE}
                        and item.text.strip() and item.prov and item.prov[0].page_no in selected}
    hidden = {item.self_ref for item in doc.texts
              if item.content_layer not in {ContentLayer.BODY, ContentLayer.FURNITURE}}
    result = {'source': stem, 'input_SHA256': sha(input_path.read_bytes()),
              'raw_SHA256': sha(raw), 'native_pages': len(selected), 'phases': {}}
    fragments_by_phase = {}
    exports_by_phase = {}
    for phase, runtime in versions.items():
        fragments = [f for f in runtime.extract_table_fragments(doc, (1, len(doc.pages)))
                     if f.page_number in selected]
        fragments_by_phase[phase] = [helper.canonical_fragment(f) for f in fragments]
        events.clear()
        pages = []
        for number in sorted(selected):
            active_page = number
            pages.append(PageParseResult(page_number=number,
                content=runtime.export_page_markdown(doc, number, fragments)))
        trace = [dict(item) for item in events]
        exported = {p.page_number: p.content or '' for p in pages}
        exports_by_phase[phase] = exported
        assembled = runtime.assemble_logical_tables(pages, fragments, enabled=True)
        assert all(helper.narrative(exported[p]) == helper.narrative(assembled[p]) for p in exported)
        coverage = helper.assert_public_coverage(
            [table for value in assembled.values() for table in helper.public_tables(value)],
            fragments, scopes)
        groups = {}
        for f in fragments:
            if f.logical_table_id:
                groups.setdefault(f.logical_table_id, []).append(f.fragment_id)
        seen = Counter((e['page'], e['ref']) for e in trace)
        duplicate_refs = [{'page': p, 'ref': ref, 'count': count}
                          for (p, ref), count in seen.items() if count != 1]
        wrong_page = [e for e in trace if e['ref'] in expected_visible
                      and e['page'] != expected_visible[e['ref']].prov[0].page_no]
        absent_rendered = [e for e in trace if e['rendered'] not in exported[e['page']]]
        missing = [{'ref': ref, 'page': item.prov[0].page_no, 'label': item.label.value,
                    'layer': item.content_layer.value, 'text': item.text}
                   for ref, item in expected_visible.items()
                   if (item.prov[0].page_no, ref) not in seen]
        hidden_exported = [e for e in trace if e['ref'] in hidden]
        public_furniture = []
        for page in pages:
            for f in fragments:
                if f.page_number == page.page_number:
                    public_furniture.extend([{'page': src.page_number, 'ref': src.source_ref,
                         'text': src.text, 'label': src.label,
                         'exact_block_present_after_assembly': src.rendered in assembled[src.page_number]}
                        for src in getattr(f, 'page_furniture', [])])
                    break
        result['phases'][phase] = {'tables': len(fragments), 'anchors': sum(len(f.cells) for f in fragments),
            'span_cells': sum(c.row_span > 1 or c.column_span > 1 for f in fragments for c in f.cells),
            'actual_groups': groups, 'public_table_coverage': coverage,
            'visible_source_items': len(expected_visible), 'serialized_source_events': len(trace),
            'duplicate_source_refs': duplicate_refs, 'wrong_source_pages': wrong_page,
            'serialized_blocks_absent_from_page': absent_rendered,
            'missing_visible_refs': missing, 'hidden_source_refs_exported': hidden_exported,
            'non_table_narrative_preserved_during_assembly': True}
        location = OUT / stem / phase
        save(location / 'exported-pages.json', exported)
        save(location / 'assembled-pages.json', assembled)
        save(location / 'source-ref-trace.json', trace)
        save(location / 'source-furniture.json', public_furniture)
    before, after = result['phases']['before'], result['phases']['after']
    assert fragments_by_phase['before'] == fragments_by_phase['after']
    result['source_cells_spans_header_roles_scope_and_pages_unchanged'] = True
    assert sha(doc.model_dump_json().encode()) == model_sha_before
    result['raw_model_unchanged'] = True
    old_missing = {m['ref'] for m in before['missing_visible_refs']}
    result['recovered_visible_refs'] = [ref for ref in old_missing
        if ref not in {m['ref'] for m in after['missing_visible_refs']}]
    old_groups = {tuple(g) for g in before['actual_groups'].values()}
    new_groups = {tuple(g) for g in after['actual_groups'].values()}
    result['removed_groups'] = sorted(old_groups - new_groups)
    result['added_groups'] = sorted(new_groups - old_groups)
    for kind in ['duplicate_source_refs', 'wrong_source_pages', 'serialized_blocks_absent_from_page',
                 'missing_visible_refs', 'hidden_source_refs_exported']:
        if after[kind]:
            summary['exceptions'].append({'source': stem, 'kind': kind, 'count': len(after[kind])})
    save(OUT / stem / 'summary.json', result)
    summary['documents'].append(result)
    print(json.dumps({'source': stem, 'pages': len(selected), 'missing_before': len(before['missing_visible_refs']),
                      'missing_after': len(after['missing_visible_refs']), 'new_groups': len(new_groups),
                      'removed_groups': result['removed_groups']}), flush=True)
summary.update(native_pages=sum(d['native_pages'] for d in summary['documents']),
               native_tables=sum(d['phases']['after']['tables'] for d in summary['documents']),
               native_anchors=sum(d['phases']['after']['anchors'] for d in summary['documents']),
               native_span_cells=sum(d['phases']['after']['span_cells'] for d in summary['documents']),
               wall_seconds=time.monotonic()-started,
               audit_script_SHA256=sha(Path(__file__).read_bytes()))
assert (summary['native_pages'], summary['native_tables'], summary['native_anchors']) == (433,632,20569)
assert sha((REPO / 'app/services/table_service.py').read_bytes()) == EXPECTED
save(OUT / 'summary.json', summary)
print(json.dumps({key: summary[key] for key in ['native_pages','native_tables','native_anchors','native_span_cells','wall_seconds','exceptions']}), flush=True)
