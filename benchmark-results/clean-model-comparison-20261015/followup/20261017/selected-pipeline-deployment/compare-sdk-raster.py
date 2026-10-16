"""Controlled same-page SDK inputs: resolution, then orthogonal rotation method."""
from pathlib import Path
from types import SimpleNamespace
import base64
import hashlib
import io
import json
import subprocess
import time

import httpx
from PIL import Image
import torch

from app.parsers.glm_sdk_remote import GlmSdkRemoteParser
from app.services.orientation_service import DocumentOrientationService

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = HERE / 'dpi-controlled'
OUT.mkdir(exist_ok=False)
torch.set_num_threads(4)
orientation = DocumentOrientationService(Path('/var/lib/docker/volumes/mosaicparse-huggingface-cache/_data/PP-LCNet_x1_0_doc_ori_safetensors'), allow_download=False)
source = SimpleNamespace(path=ROOT / 'pdf_sample/1225475375.pdf', mime_type='application/pdf')
container = json.loads(subprocess.check_output(['docker', 'inspect', 'mosaicparse-sdk-candidate'], text=True))[0]
address = container['NetworkSettings']['Networks']['mosaicparse_default']['IPAddress']
endpoint = f'http://{address}:5002/glmocr/parse'
records = []
with httpx.Client(trust_env=False, timeout=300) as client:
    for label, dpi in [('144-lossless', 144), ('200-lossless', 200), ('200-historical-affine', 200)]:
        directory = OUT / label
        directory.mkdir()
        if label.endswith('historical-affine'):
            payload = (ROOT / 'benchmark-results/clean-model-comparison-20261015/paddle/official-orientation/images/1225475375/p0008.png').read_bytes()
            angle = 90
            raw_matches = None
        else:
            renderer = object.__new__(GlmSdkRemoteParser)
            renderer.scale, renderer.max_pixels = dpi / 72, 8_000_000
            original_uri = renderer._render_page(source, 8)
            original = base64.b64decode(original_uri.split(',', 1)[1])
            frozen = (ROOT / 'benchmark-results/clean-model-comparison-20261015/inputs/1225475375/page-0008.png').read_bytes()
            with Image.open(io.BytesIO(original)) as actual, Image.open(io.BytesIO(frozen)) as reference:
                raw_matches = actual.size == reference.size and actual.convert('RGB').tobytes() == reference.convert('RGB').tobytes()
            uri, angle, confidence = orientation.orient(original_uri)
            payload = base64.b64decode(uri.split(',', 1)[1])
        (directory / 'sdk-input.png').write_bytes(payload)
        uri = 'data:image/png;base64,' + base64.b64encode(payload).decode()
        with Image.open(io.BytesIO(payload)) as image:
            size = list(image.size)
        request = {'source': '1225475375', 'page': 8, 'DPI': dpi, 'rotation_clockwise': angle,
                   'input_size': size, 'input_SHA256': hashlib.sha256(payload).hexdigest(),
                   'unrotated_pixels_equal_frozen_200DPI': raw_matches, 'SDK_image_ID': container['Image'],
                   'request': {'method': 'POST', 'endpoint': endpoint, 'JSON_fields': ['images'], 'images_count': 1},
                   'no_business_text_or_gold_in_request': True}
        (directory / 'request-manifest.json').write_text(json.dumps(request, indent=2) + '\n')
        started = time.monotonic()
        response = client.post(endpoint, json={'images': [uri]})
        seconds = time.monotonic() - started
        (directory / 'response.json').write_bytes(response.content)
        response.raise_for_status()
        value = response.json()
        regions = GlmSdkRemoteParser._page_regions(value.get('layout_details', value.get('json_result')))
        markdown, fragments = GlmSdkRemoteParser._render_regions(regions, 8)
        (directory / 'result.md').write_text(markdown)
        rows = [row for fragment in fragments for row in fragment.rows if any('短期借款' in text for text in row)]
        record = request | {'label': label, 'HTTP_status': response.status_code, 'SDK_HTTP_seconds': seconds,
                            'short_term_borrowing_rows': rows,
                            'source_comparison_value_in_same_row': any('142,000,000.00' in row for row in rows)}
        records.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        (OUT / 'comparison.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
