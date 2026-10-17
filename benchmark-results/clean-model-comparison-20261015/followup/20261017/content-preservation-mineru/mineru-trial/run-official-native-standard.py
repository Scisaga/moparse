"""Official MinerU standard/TXT experiment with read-only stage observations.

Requires an explicit parent-release flag and the GPU owner's handoff receipt.
No application configuration or shared model environment is changed.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
import traceback

HERE = Path(__file__).resolve().parent
OUT = HERE / 'official-native-standard'
os.environ.update({
    'CUDA_VISIBLE_DEVICES': '', 'MINERU_DEVICE_MODE': 'cpu', 'MINERU_TABLE_DEVICE': 'cpu',
    'MINERU_HOME': '/root/.cache/mosaicparse-mineru/native-home',
    'MINERU_MODEL_SMALL_BACKEND': 'onnx', 'MINERU_MODEL_SOURCE': 'local',
    'OMP_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4',
    'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost',
})
if hasattr(os, 'sched_getaffinity'):
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-4:])

import psutil
import httpx
import pypdfium2
from mineru.config import VlmConfig
from mineru.parser import MinerUParser, parse
from mineru.parser.writer import FileBasedDataWriter
from mineru.backend.analysis.pdf import tables, window
from mineru.backend.analysis.pdf.text import content, native
from mineru.model.vlm.runtime import shutdown_cached_models
from mineru.model.runtime.hybrid import HybridLocalModelContextSingleton
from docvortex.analyzers.native.pdf import table_materialization as native_table_materialization


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


CURRENT = {}
EVENTS = []
RECOVERY = []
CASE_DIR = None
HTTP_CALLS = []
HTTP_COUNTER = 0


def observe(owner, name, wrap):
    original = getattr(owner, name)
    setattr(owner, name, wrap(original))


def request_hook(request):
    global HTTP_COUNTER
    if '/chat/completions' not in str(request.url):
        return
    index = HTTP_COUNTER
    HTTP_COUNTER += 1
    request.extensions['native_evidence_index'] = index
    request.extensions['native_evidence_started'] = time.monotonic()
    location = CASE_DIR / 'model-http' / f'{index:03d}'
    location.mkdir(parents=True)
    (location/'request.json').write_bytes(request.content)
    payload = json.loads(request.content)
    for message_index, message in enumerate(payload.get('messages', [])):
        if isinstance(message.get('content'), list):
            for item_index, item in enumerate(message['content']):
                if item.get('type') == 'image_url':
                    url = item['image_url']['url']
                    if url.startswith('data:'):
                        suffix = 'jpg' if url.startswith('data:image/jpeg') else 'png'
                        (location/f'image-{message_index}-{item_index}.{suffix}').write_bytes(
                            base64.b64decode(url.split(',', 1)[1]))


def response_hook(response):
    if 'native_evidence_index' not in response.request.extensions:
        return
    response.read()
    index = response.request.extensions['native_evidence_index']
    location = CASE_DIR / 'model-http' / f'{index:03d}'
    (location/'response.json').write_bytes(response.content)
    payload = response.json()
    HTTP_CALLS.append({'index':index,'HTTP_status':response.status_code,
        'model_HTTP_seconds':time.monotonic()-response.request.extensions['native_evidence_started'],
        'usage':payload.get('usage'),'finish_reasons':[c.get('finish_reason') for c in payload.get('choices',[])],
        'request_SHA256':digest(location/'request.json'),'response_SHA256':digest(location/'response.json')})
    save(CASE_DIR/'generation-calls.json', HTTP_CALLS)


async def async_request_hook(request):
    request_hook(request)


async def async_response_hook(response):
    await response.aread()
    response_hook(response)


def http_init_wrapper(original, asynchronous):
    def call(self, *args, **kwargs):
        hooks = {key:list(values) for key,values in (kwargs.get('event_hooks') or {}).items()}
        hooks.setdefault('request', []).append(async_request_hook if asynchronous else request_hook)
        hooks.setdefault('response', []).append(async_response_hook if asynchronous else response_hook)
        kwargs['event_hooks'] = hooks
        original(self, *args, **kwargs)
    return call


def recovery_wrapper(original):
    def call(*args, **kwargs):
        started = time.monotonic()
        try:
            result = original(*args, **kwargs)
        except BaseException as exc:
            RECOVERY.append({'region': args[1], 'angle': kwargs.get('angle'),
                             'status': 'exception', 'exception_type': type(exc).__name__})
            raise
        if result is None:
            RECOVERY.append({'region': args[1], 'angle': kwargs.get('angle'), 'status': 'rejected'})
        else:
            RECOVERY.append({'region': args[1], 'angle': kwargs.get('angle'),
                'stage':'public_PDFTableResult', 'status': 'accepted',
                'source': result.source, 'confidence': result.confidence,
                'html': result.html,
                'diagnostics': list(result.diagnostics), 'wall_seconds': time.monotonic()-started})
        return result
    return call


def internal_recovery_wrapper(original):
    def call(*args, **kwargs):
        result = original(*args, **kwargs)
        if result is not None:
            html, recovered = result
            RECOVERY.append({'stage':'internal_NativeTableResult',
                'rows':recovered.rows,'cols':recovered.cols,'source':recovered.source,
                'confidence':recovered.confidence,'cells':[asdict(c) for c in recovered.cells],
                'html_with_native_script_markup':html,'diagnostics':list(recovered.diagnostics),
                'coordinate_scope':'Raw official NativeTableResult cell geometry, not reinterpreted as public cell provenance.'})
        return result
    return call


def priority_wrapper(original):
    def call(*args, **kwargs):
        result = original(*args, **kwargs)
        observed = []
        for local_page, blocks in enumerate(args[0]):
            for block in blocks:
                if block.get('type') == 'table':
                    observed.append({'window_page_index': local_page, 'bbox': block.get('bbox'),
                        'angle': block.get('angle'),
                        'native_HTML_accepted': bool(str(block.get('content') or '').strip()),
                        'content_SHA256': hashlib.sha256(str(block.get('content') or '').encode()).hexdigest()})
        EVENTS.append({'stage': 'native_table_priority', 'effort': kwargs.get('effort'),
                       'counts': asdict(result), 'table_routes': observed})
        return result
    return call


def inference_wrapper(original):
    def call(*args, **kwargs):
        result = original(*args, **kwargs)
        state = args[0]
        for index, image in enumerate(state.images_pil_list):
            path = CASE_DIR / f'actual-model-input-{index}.png'
            image.save(path)
        EVENTS.append({'stage': 'actual_VLM_options',
            'image_analysis': result.get('image_analysis'),
            'not_extract_list': sorted(result.get('not_extract_list') or []),
            'image_sizes': [list(image.size) for image in state.images_pil_list],
            'model_inputs': [[{'type': b.get('type'), 'bbox': b.get('bbox'),
                               'has_content': bool(str(b.get('content') or '').strip())}
                              for b in blocks] for blocks in result.get('blocks_list', [])]})
        return result
    return call


def finish_wrapper(original):
    def call(*args, **kwargs):
        model_results = args[1]
        EVENTS.append({'stage':'actual_VLM_results_before_native_body_fill',
            'effort':kwargs.get('effort'), 'tables':[
                {'window_page_index':index, 'bbox':block.get('bbox'), 'content':block.get('content')}
                for index, blocks in enumerate(model_results) for block in blocks
                if block.get('type') == 'table']})
        return original(*args, **kwargs)
    return call


def prepare_wrapper(original):
    def call(*args, **kwargs):
        started = time.monotonic()
        prepared = original(*args, **kwargs)
        original_seconds = time.monotonic()-started
        filename = 'prepared-by-official-page-selection.' + prepared.file_suffix
        (CASE_DIR/filename).write_bytes(prepared.file_bytes)
        EVENTS.append({'stage':'official_input_preparation',
            'file_suffix':prepared.file_suffix,
            'prepared_size_bytes':len(prepared.file_bytes),
            'original_function_seconds':original_seconds,
            'prepared_SHA256':hashlib.sha256(prepared.file_bytes).hexdigest(),
            'retained_original_page_indices_zero_based':prepared.retained_page_indices,
            'broken_original_page_indices_zero_based':prepared.broken_page_indices,
            'derived_input_filename':filename,
            'transformation':'Official default page_range handling; runner did not crop or rewrite the source PDF.'})
        return prepared
    return call


def native_fill_wrapper(original):
    def call(*args, **kwargs):
        result = original(*args, **kwargs)
        EVENTS.append({'stage': 'native_PDF_text_fill', 'returned_spans': len(result),
            'nonempty_text_spans': sum(s.type == 'text' and bool(str(s.content or '').strip()) for s in result),
            'queued_for_post_OCR': sum(s.image is not None for s in result),
            'spans': [{'type': s.type, 'bbox': s.bbox, 'text': s.content,
                       'queued_for_post_OCR': s.image is not None} for s in result]})
        return result
    return call


def post_ocr_wrapper(original):
    def call(*args, **kwargs):
        spans = [s for page in args[1] for lines in page.values() for line in lines for s in line.spans]
        candidates = [s for s in spans if s.image is not None]
        before = {id(s): s.content for s in candidates}
        result = original(*args, **kwargs)
        EVENTS.append({'stage': 'actual_post_OCR', 'candidate_spans': len(candidates),
            'content_changed': sum(s.content != before[id(s)] for s in candidates),
            'spans': [{'bbox': s.bbox, 'before': before[id(s)], 'after': s.content} for s in candidates]})
        return result
    return call


def signal_stop(signum, frame):
    raise KeyboardInterrupt(f'owned experiment received signal {signum}')


def main():
    global CURRENT, CASE_DIR, HTTP_COUNTER, OUT
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument('--execute-after-parent-release', action='store_true')
    options.add_argument('--check-only', action='store_true')
    options.add_argument('--tier', choices=['standard','advanced'], default='standard')
    options.add_argument('--defer-handoff-complete', action='store_true')
    args = options.parse_args()
    OUT = HERE / ('official-native-' + args.tier)
    if args.check_only:
        print(json.dumps({'imports': 'pass', 'torch_present': 'torch' in sys.modules,
                          'GPU_access': False, 'CPU_affinity': sorted(os.sched_getaffinity(0))}))
        return
    if not args.execute_after_parent_release:
        raise SystemExit('Parent release flag required; CPU preparation never starts GPU requests.')
    ready = json.loads((HERE / 'official-native-handoff-ready.json').read_text())
    if ready.get('status') != 'ready_for_official_native':
        raise SystemExit('GPU owner handoff not ready')
    if OUT.exists():
        raise SystemExit('Refusing to overwrite a prior official native experiment')
    OUT.mkdir()
    signal.signal(signal.SIGTERM, signal_stop)
    signal.signal(signal.SIGINT, signal_stop)
    observe(tables, 'recover_table_region', recovery_wrapper)
    observe(native_table_materialization, 'recover_table_result', internal_recovery_wrapper)
    observe(tables, '_apply_native_txt_table_priority', priority_wrapper)
    observe(window, '_inference_options', inference_wrapper)
    observe(window, '_finish_pdf_window', finish_wrapper)
    observe(content, '_fill_native_pdf_text_spans', native_fill_wrapper)
    observe(content, '_apply_window_post_ocr', post_ocr_wrapper)
    observe(MinerUParser, '_prepare_input', prepare_wrapper)
    httpx.Client.__init__ = http_init_wrapper(httpx.Client.__init__, False)
    httpx.AsyncClient.__init__ = http_init_wrapper(httpx.AsyncClient.__init__, True)
    cases = json.loads((HERE / 'first-pages.json').read_text()) + json.loads((HERE / 'remaining-pages.json').read_text())
    cases.append({'id': '1225475375', 'pdf': '/opt/mosaic-parse/pdf_sample/1225475375.pdf', 'page': 62})
    endpoint = ready.get('endpoint') or ready.get('server_url') or 'http://127.0.0.1:12431'
    model = ready.get('model') or 'mineru-trial'
    vlm = VlmConfig(server_url=endpoint, model=model, max_concurrency=1, http_timeout=600)
    record = {'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'script_SHA256': digest(__file__), 'tier':args.tier, 'packages': {k: importlib.metadata.version(k) for k in
            ['mineru','docvortex','mineru-vl-utils','onnxruntime','pypdfium2']},
        'CPU_affinity': sorted(os.sched_getaffinity(0)), 'small_model_backend': 'onnx/CPU',
        'GPU_local_access': False, 'remote_VLM': vlm.model_dump(exclude={'api_key'}),
        'local_process_NO_PROXY':os.environ['NO_PROXY'],
        'Markdown_exports':{'result.md':'official default renderer; filters page auxiliary blocks',
                            'result-full.md':'official public add_markers=True FULL renderer; retains physical-page auxiliary blocks'},
        'timing_boundaries':{'CPU_model_initialization':'preloaded before timed page parsing and recorded separately',
            'parse_seconds':'official parse() call; includes its official input selection, layout/native/VLM/postprocessing and read-only observation writes made inside those calls; excludes CPU model initialization and subsequent Markdown calls',
            'markdown_DEFAULT_and_FULL_seconds':'each measured independently on returned result, before file writing',
            'case_component_seconds':'parse + DEFAULT Markdown + FULL Markdown; excludes standalone exports/file writes/metrics/input fingerprinting',
            'end_to_end_case_seconds':'all case preparation, fingerprints, metrics, parse, both renders, official save and evidence writes',
            'model_HTTP_seconds':'request event hook until response body read; includes request-evidence hook overhead, not pure GPU kernel time'},
        'handoff': ready, 'source_pages': len(cases), 'whole_document_HTTP_acceptance': False,
        'actual_input_scope': 'Original full PDF byte files supplied to official parse(); explicit page_range selects one physical page per call. Original 14 pages and additional p62 are separately labeled. No crop/pre-render supplied by this runner.',
        'planned_cases':cases, 'cases': []}
    samples = []
    stop = threading.Event()
    process = psutil.Process()
    def sample():
        while not stop.wait(0.5):
            samples.append({'time': time.time(), 'case': dict(CURRENT), 'CPU_percent': process.cpu_percent(),
                            'RSS_bytes': process.memory_info().rss, 'threads': process.num_threads()})
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    status = 'failed'
    try:
        init_start = time.monotonic()
        context = HybridLocalModelContextSingleton().get_model()
        initialized = ['ocr_model','layout_model']
        lazy_models = ['mfr_model','table_orientation_cls_model','seal_model'] if args.tier=='standard' else ['mfr_model']
        for name in lazy_models:
            getattr(context, name)
            initialized.append(name)
        record['CPU_model_initialization'] = {'seconds':time.monotonic()-init_start,
            'models':initialized,'GPU_used':False,'model_inference_calls':0}
        save(OUT/'run-manifest.json', record)
        for index, case in enumerate(cases):
            wholecase_start = time.monotonic()
            CURRENT = {'id': case['id'], 'page': case['page'],
                       'scope': 'original_14' if index < 14 else 'additional_p62'}
            CASE_DIR = OUT / f"{case['id']}-p{case['page']}"
            CASE_DIR.mkdir()
            EVENTS.clear()
            RECOVERY.clear()
            HTTP_CALLS.clear()
            HTTP_COUNTER = 0
            sha_before = digest(case['pdf'])
            with pypdfium2.PdfDocument(case['pdf']) as original_pdf:
                source_page_count = len(original_pdf)
                source_page_rotation = original_pdf[case['page']-1].get_rotation()
            request = {**case, 'source_pdf_SHA256': sha_before, 'physical_page_one_based': case['page'],
                'source_pdf_total_pages':source_page_count, 'source_pdf_page_rotation':source_page_rotation,
                'expected_original_page_idx_zero_based': case['page']-1,
                'official_parse_arguments': {'tier': args.tier,'ocr_mode': 'txt',
                    'image_analysis': False,'page_range': str(case['page'])}, 'cohort': CURRENT['scope']}
            save(CASE_DIR/'request.json', request)
            started = time.monotonic()
            try:
                with httpx.Client(timeout=10) as metrics:
                    (CASE_DIR/'metrics-before.prom').write_text(metrics.get(endpoint.rstrip('/')+'/metrics').text)
                parse_start = time.monotonic()
                result = parse(case['pdf'], tier=args.tier, ocr_mode='txt', image_analysis=False,
                               page_range=str(case['page']), vlm_config=vlm)
                parse_seconds = time.monotonic()-parse_start
                render_start = time.monotonic()
                default_MD = result.markdown()
                markdown_DEFAULT_seconds = time.monotonic()-render_start
                render_start = time.monotonic()
                full_MD = result.markdown(add_markers=True)
                markdown_FULL_seconds = time.monotonic()-render_start
                write_start = time.monotonic()
                (CASE_DIR/'result.md').write_text(default_MD)
                (CASE_DIR/'result-full.md').write_text(full_MD)
                direct_MD_write_seconds = time.monotonic()-write_start
                save_start = time.monotonic()
                result.save(FileBasedDataWriter(str(CASE_DIR/'official-saved')))
                official_save_seconds = time.monotonic()-save_start
                save(CASE_DIR/'result.json', result.to_dict())
                page_indices = [p.page_idx for p in result.middle_json.pages]
                row = {**request, 'status':'completed','parse_seconds':parse_seconds,
                       'markdown_DEFAULT_seconds':markdown_DEFAULT_seconds,
                       'markdown_FULL_seconds':markdown_FULL_seconds,
                       'PDF_to_DEFAULT_MD_component_seconds':parse_seconds+markdown_DEFAULT_seconds,
                       'PDF_to_FULL_MD_component_seconds':parse_seconds+markdown_FULL_seconds,
                       'case_component_seconds':parse_seconds+markdown_DEFAULT_seconds+markdown_FULL_seconds,
                       'official_save_seconds':official_save_seconds,
                       'direct_MD_write_seconds':direct_MD_write_seconds,
                       'returned_original_page_indices_zero_based':page_indices,
                       'model_HTTP_calls':len(HTTP_CALLS),
                       'model_HTTP_seconds':sum(c['model_HTTP_seconds'] for c in HTTP_CALLS),
                       'result_full_MD_SHA256':digest(CASE_DIR/'result-full.md'),
                       'result_MD_SHA256':digest(CASE_DIR/'result.md')}
                if page_indices != [case['page']-1]:
                    raise AssertionError(f'Official source-page mapping differs: {page_indices}')
            except BaseException as exc:
                row = {**request,'status':'failed','elapsed_case_seconds_before_failure':time.monotonic()-started,
                       'exception_type':type(exc).__name__,'traceback':traceback.format_exc()}
                save(CASE_DIR/'failure.json', row)
                record['cases'].append(row)
                raise
            finally:
                save(CASE_DIR/'official-stage-observations.json', EVENTS)
                save(CASE_DIR/'native-table-recovery.json', RECOVERY)
                assert digest(case['pdf']) == sha_before
                try:
                    with httpx.Client(timeout=10) as metrics:
                        (CASE_DIR/'metrics-after.prom').write_text(metrics.get(endpoint.rstrip('/')+'/metrics').text)
                except Exception as exc:
                    save(CASE_DIR/'metrics-after-unavailable.json', {'exception_type':type(exc).__name__,
                         'error':str(exc),'original_model_IO_and_stage_observations_preserved':True})
            row['end_to_end_case_seconds'] = time.monotonic()-wholecase_start
            record['cases'].append(row)
            save(OUT/'run-manifest.json', record)
            print(json.dumps({'id':case['id'],'page':case['page'],'seconds':row['case_component_seconds'],
                'native_tables':sum(e.get('counts',{}).get('accepted',0) for e in EVENTS),
                'VLM_table_regions':sum(sum(b['type']=='table' for b in bs)
                    for e in EVENTS if e['stage']=='actual_VLM_options' for bs in e['model_inputs'])}), flush=True)
        status = 'completed'
    except BaseException:
        record['traceback'] = traceback.format_exc()
        raise
    finally:
        shutdown_cached_models()
        stop.set()
        sampler.join(timeout=2)
        started_cases = {(c['id'],c['page']) for c in record['cases']}
        record.update(status=status, finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            unstarted_cases=[c for c in cases if (c['id'],c['page']) not in started_cases])
        save(OUT/'resource-samples.json', samples)
        save(OUT/'run-manifest.json', record)
        if not args.defer_handoff_complete:
            save(HERE/'official-native-handoff-complete.json', {'status':status,
                'finished_at':record['finished_at'],'owner':'preserve_exported_content',
                'runner_no_longer_sends_requests':True,'evidence':str(OUT)})


if __name__ == '__main__':
    main()
