"""Controlled V2 decoding/resolution experiments; no production imports or repairs.

The model is unchanged. Beam search ranks only model log probabilities. No gold,
PDF words, financial labels, header rules or geometry heuristics enter decoding.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[2]
REPO = Path('/opt/mosaic-parse')
ENV_PY = REPO / 'benchmark-results/model-upgrade-20261015/docling-2.139.0-eval/.venv/bin/python'
VARIANTS = [
    {'id': 'official448', 'size': 448, 'beams': 1},
    {'id': 'beam2-448', 'size': 448, 'beams': 2},
    {'id': 'beam4-448', 'size': 448, 'beams': 4},
    {'id': 'greedy672', 'size': 672, 'beams': 1},
    {'id': 'greedy896', 'size': 896, 'beams': 1},
    {'id': 'beam4-672', 'size': 672, 'beams': 4},
]


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + '\n')
    temp.replace(path)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def site():
    import psutil
    import urllib.request
    out = {'UTC': now(), 'containers': {}, 'host_CPU_pct': psutil.cpu_percent(interval=.3),
           'host_available_bytes': psutil.virtual_memory().available, 'CPU_temperatures': {}}
    for key, vals in psutil.sensors_temperatures().items():
        if key == 'coretemp':
            out['CPU_temperatures'][key] = [{'label': v.label, 'C': v.current} for v in vals]
    for name in ['mosaicparse', 'docling_glm_ocr_sdk', 'docling_glm_ocr']:
        d = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]
        out['containers'][name] = {'id': d['Id'], 'image': d['Image'],
                                   'started': d['State']['StartedAt'], 'pid': d['State']['Pid'],
                                   'running': d['State']['Running'], 'restarts': d['RestartCount']}
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with client.open('http://127.0.0.1:12303/ready', timeout=10) as r:
        out['production_ready'] = json.load(r)
    out['GPU_raw'] = subprocess.check_output([
        'nvidia-smi', '--query-gpu=index,name,utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu',
        '--format=csv,noheader,nounits'], text=True)
    return out


def prepare():
    assert not (ROOT / 'plan.json').exists(), 'Do not overwrite the registered plan'
    routing = json.loads((BASE / 'page-routing.json').read_text())
    docs = {Path(d['path']).name: d for d in routing['documents']}
    selected = defaultdict(set)
    for rel in ['scoring/supplemental/source-only-tables.json',
                'scoring/supplemental/130-merged-source-only.json',
                'scoring/same-header-continuation-source.json']:
        for table in json.loads((BASE / rel).read_text())['tables']:
            selected[Path(table['document']).name].add(table['source_page'])
    for source, pages in {'1225474693.pdf': [2, 3], '1210860446.pdf': [2]}.items():
        selected[source].update(pages)
    # General positive controls: first native page containing an existing table
    # for every native-capable source, chosen before these experimental outputs.
    controls = []
    for name, doc in docs.items():
        native = {p['page_number'] for p in doc['pages'] if p['route'] == 'native'}
        if not native:
            continue
        prior = json.loads((BASE / 'native/new139-v2-matching-true-pypdfium-full' / Path(name).stem / 'result.json').read_text())
        first = next((p['page_number'] for p in prior['pages'] if p['page_number'] in native and p['tables']), None)
        if first is not None:
            selected[name].add(first)
            controls.append({'source': name, 'page': first})
    cases = []
    for name in sorted(selected):
        doc = docs[name]
        native = {p['page_number'] for p in doc['pages'] if p['route'] == 'native'}
        pages = sorted(selected[name] & native)
        if not pages:
            continue
        source = REPO / 'pdf_sample' / name
        assert sha(source) == doc['sha256']
        cases.append({'source': name, 'sha256': doc['sha256'], 'pages': pages,
                      'original_page_count': len(doc['pages'])})
    plan = {'schema': 'tableformer-v2-compute/1', 'registered_UTC': now(),
            'scope': 'All existing native source-annotated pages plus predetermined positive controls. Selected page ranges of original PDFs, not a full502-page run.',
            'cases': cases, 'positive_controls': controls, 'variants': VARIANTS,
            'fixed': {'backend': 'PyPdfiumDocumentBackend', 'matching': True, 'FP32': True,
                      'CPU_threads': 4, 'CPU_affinity': [20, 21, 22, 23], 'max_length': 512,
                      'beam_length_penalty': 1.0, 'beam_early_stopping': True,
                      'beam_ranking': 'model log probability only; no source answers, syntax repair, text or bbox-based reranking',
                      'weights': 'unchanged local official V2 weights', 'GLM_calls': 0, 'GPU_used': False},
            'comparison': 'Default448 versus beams2/4 and true672/896 tensor inputs. Separate initialization/warmup, record every table length/EOS, CPU wall/CPU/RSS and shared-host GPU samples.',
            'source_and_judging_files': {str(p.relative_to(REPO)): sha(p) for p in [
                BASE / 'page-routing.json', BASE / 'native/run-native-group.py',
                BASE / 'scoring/score-result.py', BASE / 'scoring/supplemental/source-only-tables.json',
                BASE / 'scoring/supplemental/130-merged-source-only.json',
                REPO / 'pdf_sample/gold/table_fact_gold_v1.json',
                REPO / 'benchmark-results/model-upgrade-20261015/models/docling-project--TableFormerV2/model.safetensors']},
            'runner_SHA256': sha(__file__)}
    save(ROOT / 'site-before.json', site())
    save(ROOT / 'plan.json', plan)
    print(json.dumps({'registered_cases': len(cases), 'selected_native_pages': sum(len(c['pages']) for c in cases),
                      'variants': len(VARIANTS)}, ensure_ascii=False), flush=True)


def beam_tokens(model, images, tokenizer, width, max_length=512, length_penalty=1.0):
    """Probability-only cached beam search; batch size1, explicit EOS handling."""
    import torch
    assert images.shape[0] == 1
    encoded = model.encode_images(images)
    sequences = torch.tensor([[tokenizer.bos_token_id]], device=images.device)
    scores = torch.zeros(1, device=images.device)
    past = None
    completed = []
    steps = 0
    while steps < max_length:
        count = sequences.shape[0]
        expanded = {k: (v.expand(count, *v.shape[1:]) if torch.is_tensor(v) else v)
                    for k, v in encoded.items()}
        outputs = model.forward(input_ids=sequences if past is None else sequences[:, -1:],
                                attention_mask=None, encoder_outputs=expanded,
                                past_key_values=past, use_cache=True, return_dict=True)
        log_probs = outputs.logits[:, -1, :].log_softmax(-1)
        vocab = log_probs.shape[-1]
        proposed = scores[:, None] + log_probs
        values, indices = proposed.flatten().topk(min(width * 2, proposed.numel()))
        active = []
        for rank, (value, index) in enumerate(zip(values.tolist(), indices.tolist())):
            parent, token = divmod(index, vocab)
            seq = torch.cat((sequences[parent], sequences.new_tensor([token])))
            if token == tokenizer.eos_token_id:
                if rank < width:
                    completed.append((value / ((len(seq) - 1) ** length_penalty), value, seq))
            elif len(active) < width:
                active.append((parent, token, value, seq))
            if len(active) == width and rank >= width:
                break
        completed = sorted(completed, key=lambda x: x[0], reverse=True)[:width]
        steps += 1
        if len(completed) >= width or not active:
            break
        parents = sequences.new_tensor([v[0] for v in active])
        sequences = torch.stack([v[3] for v in active])
        scores = scores.new_tensor([v[2] for v in active])
        past = tuple(tuple(t.index_select(0, parents) for t in layer) for layer in outputs.past_key_values)
    if len(completed) < width:
        for score, seq in zip(scores.tolist(), sequences):
            completed.append((score / ((len(seq) - 1) ** length_penalty), score, seq))
    best = max(completed, key=lambda x: x[0])
    return best[2].unsqueeze(0), encoded, {'search_steps': steps, 'normalized_log_probability': best[0],
                                         'log_probability': best[1], 'completed_candidates': len(completed)}


def finish_boxes(model, ids, encoded):
    import torch
    output = model.forward(input_ids=ids, attention_mask=torch.ones_like(ids),
                           encoder_outputs=encoded, past_key_values=None, use_cache=False, return_dict=True)
    positions = [i for i, tok in enumerate(ids[0].tolist()) if tok in model.data_cells]
    boxes = None
    if positions:
        cells = output.hidden_states[0, positions, :]
        boxes = model.bbox_head(cells, encoded['last_hidden_state'],
                                torch.zeros(len(positions), dtype=torch.long, device=ids.device),
                                spatial_size=encoded.get('spatial_size'))[None, :, :]
    return {'generated_ids': ids, 'predicted_bboxes': boxes}


def test_beam_search():
    import torch
    from types import SimpleNamespace
    # Exhaustive fixed-length example: greedy AA has probability .36,
    # whereas the globally better BA has probability .38. Cache stores history,
    # so incorrect parent reordering causes a different result and fails.
    class Toy:
        def encode_images(self, images):
            return {'last_hidden_state': torch.zeros(1, 1, 1)}
        def forward(self, input_ids, past_key_values, **kw):
            old = past_key_values[0][0][:, 0, :, 0].long() if past_key_values else input_ids[:, :0]
            full = torch.cat((old, input_ids), dim=1)
            logits = torch.full((len(full), 1, 4), -100.0)
            for i, seq in enumerate(full.tolist()):
                probs = [.6, .4] if len(seq) == 1 or seq[-1] == 1 else [.95, .05]
                if len(seq) >= 3:
                    logits[i, 0, 3] = 0
                else:
                    logits[i, 0, 1:3] = torch.tensor(probs).log()
            cache = full.float()[:, None, :, None]
            return SimpleNamespace(logits=logits, past_key_values=((cache, cache.clone()),))
    tok = SimpleNamespace(bos_token_id=0, eos_token_id=3)
    for width in [2, 4]:
        ids, _, _ = beam_tokens(Toy(), torch.zeros(1, 1), tok, width, 3, 0.0)
        assert ids.tolist() == [[0, 2, 1, 3]], ids.tolist()
    return {'exhaustive_probability_example': 'pass', 'cached_parent_reordering': 'pass'}


def run_variant(variant_id):
    import psutil
    cfg = next(v for v in VARIANTS if v['id'] == variant_id)
    plan = json.loads((ROOT / 'plan.json').read_text())
    output = ROOT / variant_id
    assert not output.exists(), 'Preserve the existing run; choose a distinct attempt explicitly'
    output.mkdir()
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.sched_setaffinity(0, {20, 21, 22, 23})
    m = module('frozen_native_compute', BASE / 'native/run-native-group.py')
    import torch
    import torchvision.transforms as T
    from docling.models.stages.table_structure.table_structure_model_v2 import TableStructureModelV2
    from docling_ibm_models.tableformer_v2 import TableFormerV2
    renderer = module('frozen_compute_renderer', BASE / 'scoring/faithful-gfm.py')
    judge = module('frozen_compute_judge', BASE / 'followup/20261017/production-baseline/score-baseline.py')
    reader = judge.reader
    model_path = Path(sys.modules[TableFormerV2.__module__].__file__)
    original_generate = TableFormerV2.generate
    original_init = TableStructureModelV2.__init__
    state = {'phase': 'initialize', 'events': [], 'folder': None}
    stop = threading.Event()
    sampler_errors = []

    def sample():
        own = psutil.Process()
        own.cpu_percent()
        n = 0
        while not stop.wait(1):
            row = {'UTC': now(), 'active': {k: state.get(k) for k in ['phase', 'source', 'page']},
                   'process_CPU_pct_one_core_100': own.cpu_percent(), 'RSS_bytes': own.memory_info().rss,
                   'host_CPU_pct': psutil.cpu_percent(), 'host_available_bytes': psutil.virtual_memory().available,
                   'CPU_package_temperatures': [v.current for v in psutil.sensors_temperatures().get('coretemp', []) if 'Package' in v.label],
                   'inference_device': 'cpu', 'inference_GPU_memory_bytes': 0}
            if n % 5 == 0:
                try:
                    row['shared_host_GPU_raw_not_attributed_to_this_process'] = subprocess.check_output([
                        'nvidia-smi', '--query-gpu=index,utilization.gpu,memory.used,power.draw,temperature.gpu',
                        '--format=csv,noheader,nounits'], text=True, timeout=6)
                except Exception as exc:
                    row['GPU_sample_error'] = repr(exc)
            with (output / 'resources.jsonl').open('a') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
            n += 1

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if not self.enabled:
            return
        def transform(pil):
            if state['folder'] is not None:
                index = len(state['events']) + 1
                png = state['folder'] / f'crop-{index:02d}.png'
                pil.save(png)
                state['last_crop'] = {'path': str(png), 'SHA256': sha(png), 'original_size': list(pil.size)}
            return T.Compose([T.Resize((cfg['size'], cfg['size'])), T.ToTensor(),
                              T.Normalize(mean=[.485, .456, .406], std=[.229, .224, .225])])(pil)
        self.transform = transform

    preflight_done = False
    def generate(self, images, tokenizer, *args, **kwargs):
        nonlocal preflight_done
        started, cpu = time.perf_counter(), time.process_time()
        with torch.no_grad():
            if cfg['beams'] == 1:
                value = original_generate(self, images, tokenizer, *args, **kwargs)
                search = {'implementation': 'unchanged official greedy decoder'}
            else:
                ids, encoded, search = beam_tokens(self, images, tokenizer, cfg['beams'], kwargs.get('max_length', 512))
                value = finish_boxes(self, ids, encoded)
        wall = time.perf_counter() - started
        ids = value['generated_ids'][0].tolist()
        event = {'input_shape': list(images.shape), 'input_dtype': str(images.dtype),
                 'input_SHA256': hashlib.sha256(images.detach().cpu().contiguous().numpy().tobytes()).hexdigest(),
                 'crop': state.get('last_crop'), 'generated_ids': ids,
                 'tokens': tokenizer.convert_ids_to_tokens(ids), 'ended_EOS': ids[-1] == tokenizer.eos_token_id,
                 'hit_length_limit': ids[-1] != tokenizer.eos_token_id and len(ids) - 1 >= kwargs.get('max_length', 512),
                 'model_call_seconds': wall, 'model_call_CPU_seconds': time.process_time() - cpu,
                 'search': search, 'predicted_bboxes': value['predicted_bboxes'].tolist() if value['predicted_bboxes'] is not None else None}
        state['events'].append(event)
        if not preflight_done:
            # Search width1 must reproduce official model generation and box head.
            with torch.no_grad():
                official = original_generate(self, images, tokenizer, max_length=512)
                first, enc, _ = beam_tokens(self, images, tokenizer, 1, 512, 0.0)
                one = finish_boxes(self, first, enc)
            assert torch.equal(official['generated_ids'], one['generated_ids']), 'Width1 changed tokens'
            a, b = official['predicted_bboxes'], one['predicted_bboxes']
            assert (a is None and b is None) or torch.equal(a, b), 'Width1 changed boxes'
            save(output / 'preflight.json', {'beam_algorithm_tests': test_beam_search(),
                                             'width1_matches_official_tokens_and_boxes': True,
                                             'comparison_input_shape': list(images.shape),
                                             'warmup_only_not_in_measured_latency': True})
            preflight_done = True
        return value

    TableStructureModelV2.__init__ = init
    TableFormerV2.generate = generate
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    all_started = time.perf_counter()
    try:
        options = m.PdfPipelineOptions(do_ocr=False, do_table_structure=True, allow_external_plugins=False,
            enable_remote_services=False, artifacts_path=m.MODELS, document_timeout=1800,
            accelerator_options=m.AcceleratorOptions(device='cpu', num_threads=4),
            table_structure_options=m.TableStructureV2Options(do_cell_matching=True),
            force_backend_text=False, layout_batch_size=1, table_batch_size=1, ocr_batch_size=1)
        options.layout_options.engine_options.compile_model = False
        engine = m.DocumentConverter(allowed_formats=[m.InputFormat.PDF], format_options={
            m.InputFormat.PDF: m.PdfFormatOption(backend=m.PyPdfiumDocumentBackend,
                 backend_options=m.PdfBackendOptions(), pipeline_options=options)})
        save(output / 'runtime.json', {'started_UTC': now(), 'variant': cfg,
            'fixed_plan_SHA256': sha(ROOT / 'plan.json'), 'script_SHA256': sha(__file__),
            'packages': {k: m.metadata.version(k) for k in ['docling', 'docling-ibm-models', 'torch', 'transformers']},
            'model_implementation_path': str(model_path), 'model_implementation_SHA256': sha(model_path),
            'torch_threads': torch.get_num_threads(), 'CPU_affinity': sorted(os.sched_getaffinity(0)),
            'app_imported': False, 'production_services_changed': False})
        state['phase'] = 'warmup'
        warm = time.perf_counter()
        engine.convert(REPO / 'pdf_sample/1225474693.pdf', page_range=(2, 2))
        warm_seconds = time.perf_counter() - warm
        pages_done = 0
        source_results = []
        for case in plan['cases']:
            source = REPO / 'pdf_sample' / case['source']
            assert sha(source) == case['sha256']
            folder = output / source.stem
            folder.mkdir()
            result = {'schema_version': 'clean-model-result/1', 'run_id': variant_id + ':' + source.stem,
                      'config_id': variant_id, 'status': 'completed', 'evaluation_scope': 'native_only',
                      'experiment_scope': 'selected original native pages; no claim of full-document conversion',
                      'source': {'path': str(source), 'sha256': case['sha256'],
                                 'page_count': case['original_page_count'], 'scope': 'original_pdf_selected_pages'},
                      'pages': [], 'timing': {}, 'resources': {'gpu_used': False}}
            page_timings = []
            for pn in case['pages']:
                state.update(phase='measured', source=source.name, page=pn, events=[], last_crop=None)
                page_dir = folder / f'page-{pn:04d}'
                page_dir.mkdir()
                state['folder'] = page_dir
                print(json.dumps({'variant': variant_id, 'source': source.name, 'page': pn, 'state': 'start'}), flush=True)
                t0, c0 = time.perf_counter(), time.process_time()
                converted = engine.convert(source, page_range=(pn, pn))
                elapsed, cpu = time.perf_counter() - t0, time.process_time() - c0
                doc = converted.document
                save(page_dir / 'raw-docling.json', doc.export_to_dict())
                md = doc.export_to_markdown(page_no=pn)
                (page_dir / 'official-markdown.md').write_text(md)
                tables = [m.table_view(t, doc, {pn: pn}) for t in doc.tables]
                for table in tables:
                    table['bbox_coordinate_space'] = 'source_pdf_points'
                page = {'page_number': pn, 'local_page_number': pn, 'status': 'completed',
                        'native_scope': 'native_model_only', 'markdown': md, 'tables': tables}
                result['pages'].append(page)
                save(page_dir / 'inference.json', {'events': state['events'], 'conversion_seconds': elapsed,
                                                  'CPU_seconds': cpu, 'table_count': len(tables)})
                page_timings.append({'page': pn, 'seconds': elapsed, 'CPU_seconds': cpu,
                                     'model_seconds': sum(e['model_call_seconds'] for e in state['events']),
                                     'calls': len(state['events'])})
                pages_done += 1
                save(output / 'progress.json', {'variant': variant_id, 'completed_pages': pages_done,
                    'planned_pages': sum(len(c['pages']) for c in plan['cases']),
                    'last_source': source.name, 'last_page': pn, 'last_seconds': elapsed})
                print(json.dumps({'variant': variant_id, 'source': source.name, 'page': pn,
                                  'seconds': round(elapsed, 3), 'tables': len(tables), 'state': 'done'}), flush=True)
            result['timing'] = {'conversion_seconds': sum(r['seconds'] for r in page_timings),
                                'per_page': page_timings, 'warmup_and_export_excluded': True}
            save(folder / 'result.json', result)
            state['folder'] = None
            state['phase'] = 'scoring'
            raw_score = judge.score_view(result)
            save(folder / 'raw-frozen-scores.json', raw_score)
            final_md, audit = renderer.render_result(result)
            (folder / 'final-markdown.md').write_text(final_md)
            final, issues = reader.parse_final(final_md, result)
            save(folder / 'final-result.json', final)
            save(folder / 'export-audit.json', {'render_audit': audit, 'readback_issues': issues})
            public_score = judge.score_view(final)
            save(folder / 'public-frozen-scores.json', public_score)
            source_results.append({'source': source.name, 'pages': case['pages'],
                                   'conversion_seconds': result['timing']['conversion_seconds'],
                                   'raw_scores': str(folder / 'raw-frozen-scores.json'),
                                   'public_scores': str(folder / 'public-frozen-scores.json')})
        state['phase'] = 'complete'
        save(output / 'completion.json', {'variant': cfg, 'completed_UTC': now(),
             'sources': source_results, 'selected_pages_completed': pages_done,
             'total_process_seconds': time.perf_counter() - all_started, 'warmup_seconds': warm_seconds,
             'initialization_and_warmup_in_measured_conversion': False,
             'production_or_GPU_model_calls': 0, 'preflight_passed': preflight_done})
    except Exception as exc:
        save(output / 'error.json', {'error': repr(exc), 'traceback': traceback.format_exc(),
                                    'state': {k: state.get(k) for k in ['phase', 'source', 'page']}})
        raise
    finally:
        stop.set()
        sampler.join(timeout=10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--variant', choices=[c['id'] for c in VARIANTS])
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.variant:
        run_variant(args.variant)
    elif args.all:
        for cfg in VARIANTS:
            if (ROOT / cfg['id'] / 'completion.json').exists():
                continue
            if (ROOT / cfg['id']).exists():
                raise RuntimeError('An incomplete attempt exists; inspect it explicitly before retrying')
            with (ROOT / (cfg['id'] + '.log')).open('w') as log:
                proc = subprocess.run(['taskset', '-c', '20-23', str(ENV_PY), str(Path(__file__).resolve()),
                                       '--variant', cfg['id']], stdout=log, stderr=subprocess.STDOUT)
            print(json.dumps({'variant': cfg['id'], 'returncode': proc.returncode, 'UTC': now()}), flush=True)
            if proc.returncode:
                raise SystemExit(proc.returncode)
        after = site()
        before = json.loads((ROOT / 'site-before.json').read_text())
        after['production_container_identities_unchanged'] = after['containers'] == before['containers']
        save(ROOT / 'site-after.json', after)


if __name__ == '__main__':
    main()
