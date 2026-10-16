"""Replace only our idle staging containers, then capture the final full cohort."""
from pathlib import Path
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import time

import httpx
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
PRIVATE = Path('/root/.cache/mosaic-parse-deploy/20261017')
API = 'mosaic-parse:0.4.0-docling139-glm-only-20261017'
SDK = 'docling-glm-ocr-sdk:0.1.5-selected-20261017'


def run(args):
    return subprocess.check_output(args, text=True).strip()


def identity(name):
    value = json.loads(run(['docker', 'inspect', name]))[0]
    return {key: value[key] for key in ('Id', 'Image', 'RestartCount')} | {
        'started': value['State']['StartedAt']}


def main():
    while not (HERE / 'candidate-http/run-completion.json').exists():
        time.sleep(2)
    cases = json.loads((HERE / 'candidate-http/summary.json').read_text())
    assert len(cases) == 10 and all(c['status'] == 'completed' for c in cases), cases
    database = '/var/lib/docker/volumes/mosaicparse-candidate-data-20261017/_data/jobs.db'
    with sqlite3.connect('file:' + database + '?mode=ro', uri=True) as connection:
        active = connection.execute("select count(*) from jobs where status in ('queued','running')").fetchone()[0]
    assert active == 0
    before = {name: identity(name) for name in ('mosaicparse-candidate', 'mosaicparse-sdk-candidate', 'mosaicparse', 'docling_glm_ocr')}
    for name in ('mosaicparse-candidate', 'mosaicparse-sdk-candidate'):
        run(['docker', 'stop', '--time', '30', name])
        run(['docker', 'rm', name])
    values = dotenv_values(PRIVATE / 'candidate.env')
    command = ['docker', 'run', '-d', '--name', 'mosaicparse-sdk-candidate', '--network', 'mosaicparse_default',
               '-v', 'mosaicparse-huggingface-cache:/models/huggingface',
               '-e', 'HF_HOME=/models/huggingface', '-e', 'HF_HUB_OFFLINE=1', '-e', 'TRANSFORMERS_OFFLINE=1',
               '-e', 'GLMOCR_OCR_API_URL=http://glm-ocr:8000/v1/chat/completions',
               '-e', 'GLMOCR_OCR_MODEL=zai-org/GLM-OCR', '-e', 'GLMOCR_LAYOUT_DEVICE=cpu',
               '-e', 'NO_PROXY=' + (values.get('NO_PROXY') or 'glm-ocr,localhost,127.0.0.1'), SDK]
    run(command)
    for attempt in range(120):
        probe = subprocess.run(['docker', 'exec', 'mosaicparse-sdk-candidate', 'python', '-c',
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5002/health',timeout=3)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Final staging SDK did not become ready')
    run(['docker', 'run', '-d', '--name', 'mosaicparse-candidate', '--network', 'mosaicparse_default',
         '--env-file', str(PRIVATE / 'candidate.env'), '-p', '127.0.0.1:12417:12417',
         '-v', 'mosaicparse-candidate-data-20261017:/data',
         '-v', 'mosaicparse-docling-models-selected-20261017:/models/docling:ro',
         '-v', 'mosaicparse-huggingface-cache:/models/huggingface', API])
    headers = {'X-API-Key': values['API_KEY']} if values.get('API_KEY') else {}
    with httpx.Client(trust_env=False, headers=headers, timeout=3) as client:
        for attempt in range(180):
            try:
                response = client.get('http://127.0.0.1:12417/ready')
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Final staging API did not become ready')
    after = {name: identity(name) for name in before}
    assert before['mosaicparse'] == after['mosaicparse']
    assert before['docling_glm_ocr'] == after['docling_glm_ocr']
    (HERE / 'final-staging-recreation.json').write_text(json.dumps({
        'UTC': dt.datetime.now(dt.timezone.utc).isoformat(),
        'active_jobs_before': active, 'before': before, 'after': after,
        'production_API_and_GPU_provider_unchanged': True,
    }, indent=2) + '\n')
    environment = os.environ.copy()
    environment['MOSAICPARSE_API_KEY'] = values.get('API_KEY') or ''
    with (HERE / 'final-candidate-http-capture.log').open('w') as log:
        subprocess.run([sys.executable, str(HERE / 'capture-full-cohort.py'),
            '--base-url', 'http://127.0.0.1:12417', '--container', 'mosaicparse-candidate',
            '--sdk-container', 'mosaicparse-sdk-candidate', '--output', str(HERE / 'final-candidate-http')],
            env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
    for script in ('score-full-cohort.py', 'summarize-performance.py'):
        subprocess.run([sys.executable, str(HERE / script), '--input', str(HERE / 'final-candidate-http')], check=True)


if __name__ == '__main__':
    main()
