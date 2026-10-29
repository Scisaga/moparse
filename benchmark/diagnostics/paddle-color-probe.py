"""CPU-only synthetic pixel probe of fixed-image PaddleX input transport.

Extracts software functions by AST without importing PaddleX, Transformers or
Torch. No model, original PDF, reference, annotation or corpus asset is opened.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

AUDIT_ROOT = Path(__file__).resolve().parent
SOFTWARE = AUDIT_ROOT / 'inspected-software/paddle'
PIPELINE = SOFTWARE / 'paddlex/inference/pipelines/paddleocr_vl/pipeline.py'
FETCH = SOFTWARE / 'paddlex/inference/models/doc_vlm/processors/common.py'
PREDICTOR = SOFTWARE / 'paddlex/inference/models/doc_vlm/predictor.py'
READER = SOFTWARE / 'paddlex/inference/common/reader/image_reader.py'
CROP = SOFTWARE / 'paddlex/inference/pipelines/components/common/crop_image_regions.py'
EXECUTOR = SOFTWARE / 'moparse_eval/executors.py'


def function(path, name, owner=None):
    tree = ast.parse(path.read_text())
    nodes = tree.body
    if owner is not None:
        nodes = next(node for node in nodes if isinstance(node, ast.ClassDef) and node.name == owner).body
    node = copy.deepcopy(next(node for node in nodes if isinstance(node, ast.FunctionDef) and node.name == name))
    node.decorator_list = []
    # Only remove the relative import to bind the exact separately-extracted
    # fetch_image function; no pixel transform or branch is changed.
    if owner == 'DocVLMTransformersPredictor':
        node.body = [item for item in node.body if not isinstance(item, ast.ImportFrom)]
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {'np': np, 'Image': Image, 'copy': copy,
                 'is_in_group': lambda model, group: group == 'PaddleOCR-VL'}
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace[name], namespace


def main():
    executor_tree = ast.parse(EXECUTOR.read_text())
    page_function = next(node for node in executor_tree.body if isinstance(node, ast.FunctionDef) and node.name == '_paddle_page')
    prediction = next(node for node in ast.walk(page_function)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'predict')
    input_expression = ast.Expression(body=copy.deepcopy(prediction.args[0]))
    ast.fix_missing_locations(input_expression)
    convert = compile(input_expression, str(EXECUTOR), 'eval')
    read, _ = function(READER, 'read', 'ReadImage')
    crop, _ = function(CROP, '__call__', 'CropByBoxes')
    collect, _ = function(PIPELINE, '_paddleocr_vl_collect_page_vlm_entries_core', '_PaddleOCRVLPipeline')
    aggregate, _ = function(PIPELINE, '_paddleocr_vl_aggregate_vlm_batches', '_PaddleOCRVLPipeline')
    run_vlm, _ = function(PIPELINE, '_paddleocr_vl_run_vl_recognition_batches', '_PaddleOCRVLPipeline')
    fetch, _ = function(FETCH, 'fetch_image')
    process, namespace = function(PREDICTOR, 'process', 'DocVLMTransformersPredictor')
    namespace['fetch_image'] = fetch
    rgb = np.array([[[255, 0, 0], [0, 0, 255]],
                    [[0, 255, 0], [127, 127, 127]]], dtype=np.uint8)
    records = []
    for version in ('1.5', '1.6'):
        bgr = eval(convert, {'np': np, 'page': {'image': Image.fromarray(rgb)}})
        read_value = read(SimpleNamespace(format='BGR'), bgr)
        blocks = crop(None, read_value, [{'cls_id': 22, 'coordinate': [0, 0, 2, 2], 'label': 'text'}], 'rect')
        cfg = {'image_labels': ['image', 'chart', 'seal'], 'ocr_min_pixels': 112896, 'ocr_max_pixels': 1003520}
        entries, has_spotting, drops = collect(None, 0, blocks, [], cfg)
        _blocks, spotting, _drops, grouped, _ids = aggregate(None, [(0, blocks, entries, has_spotting, drops)])
        captured = {}

        class StopAtImageProcessor(RuntimeError):
            pass

        def preprocess_images(**kwargs):
            captured['image_processor_input_rgb'] = np.asarray(kwargs['images'][0]).tolist()
            captured['image_processor_input_mode'] = kwargs['images'][0].mode
            captured['processor_image_kwargs'] = kwargs['images_kwargs']
            raise StopAtImageProcessor

        fake_predictor = SimpleNamespace(
            model_name=f'PaddleOCR-VL-{version}-0.9B',
            processor=SimpleNamespace(
                apply_chat_template=lambda *args, **kwargs: 'synthetic prompt',
                image_processor=SimpleNamespace(size={'shortest_edge': 112896, 'longest_edge': 1003520})),
            preprocess_images=preprocess_images)

        def predict(data, **kwargs):
            captured['vlm_kwargs'] = kwargs
            return process(fake_predictor, data, **kwargs)

        try:
            run_vlm(SimpleNamespace(vl_rec_model=SimpleNamespace(predict=predict)), grouped, spotting,
                    {'max_new_tokens': None, 'repetition_penalty': None, 'temperature': None, 'top_p': None})
        except StopAtImageProcessor:
            pass
        observed = np.array(captured['image_processor_input_rgb'], dtype=np.uint8)
        assert observed.tolist() == rgb[:, :, ::-1].tolist()
        assert observed[0, 0].tolist() == [0, 0, 255]
        assert observed[1, 1].tolist() == [127, 127, 127]
        records.append({'model_name': fake_predictor.model_name,
                        'synthetic_rgb_input': rgb.tolist(),
                        'research_worker_bgr': bgr.tolist(),
                        'sdk_crop_bgr': blocks[0]['img'].tolist(), **captured,
                        'red_blue_swapped_at_image_processor_input': True,
                        'grayscale_control_unchanged': True,
                        'scope': 'software transport only; no model or token generation'})
    result = {'scope': 'synthetic CPU pixel probe, no model/corpus/reference access',
              'sources': {'executor': str(EXECUTOR), 'pipeline': str(PIPELINE),
                          'fetch_image': str(FETCH), 'predictor': str(PREDICTOR),
                          'reader': str(READER), 'crop': str(CROP)},
              'executor_input_expression': ast.unparse(prediction.args[0]), 'records': records}
    destination = AUDIT_ROOT / 'paddle-color-probe.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'result': str(destination), 'both_paths_red_blue_swap': True,
                      'models_loaded': 0, 'gpu_operations': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
