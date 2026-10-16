"""Deploy the accepted selected images; retain production data and GPU provider."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time

import httpx
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PRIVATE = Path('/root/.cache/mosaic-parse-deploy/20261017')
BASE = 'http://10.0.6.22:12303'


def read(path):
    return json.loads(Path(path).read_text())


def save(name, data):
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def identity(name):
    value = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]
    return {'ID': value['Id'], 'image': value['Image'], 'started': value['State']['StartedAt'], 'restart_count': value['RestartCount']}


def active_jobs():
    with sqlite3.connect('file:/var/lib/docker/volumes/mosaicparse-data/_data/jobs.db?mode=ro', uri=True) as connection:
        return connection.execute("select count(*) from jobs where status in ('queued','running')").fetchone()[0]


def main():
    capture = HERE / 'final-candidate-http'
    summary = read(capture / 'summary.json')
    scores = read(capture / 'scoring/score-summary.json')
    assets = read(capture / 'source-assets-audit.json')
    assert read(capture / 'run-completion.json')['complete_capture'] is True
    assert len(summary) == 10 and all(case['status'] == 'completed' and not case.get('asset_errors') for case in summary)
    assert scores['frozen']['core_numeric'].get('pass') == 209
    assert scores['frozen']['core_period_pass'] == 209
    assert scores['frozen']['financial30'].get('pass') == 30
    assert scores['frozen']['funding31'].get('pass') == 31 and scores['frozen']['funding7_bound'] == 7
    assert scores['frozen']['supplements']['normal33']['literal']['literal_row_and_complete_header_pass'] == 33
    assert assets['status'] == 'pass' and assets['expected_routed_source_images'] == 69
    assert active_jobs() == 0
    assert hashlib.sha256((ROOT / '.env').read_bytes()).digest() == hashlib.sha256((PRIVATE / '.env.before').read_bytes()).digest()
    before = {name: identity(name) for name in ('mosaicparse', 'docling_glm_ocr_sdk', 'docling_glm_ocr')}
    expected = read(HERE / 'final-image-source-verification.json')
    assert subprocess.check_output(['docker', 'image', 'inspect', 'mosaic-parse:0.4.0-docling139-glm-only-20261017', '--format', '{{.Id}}'], text=True).strip() == expected['image']
    values = dotenv_values(PRIVATE / '.env.selected')
    assert float(values['GLM_SDK_RENDER_SCALE']) == 200 / 72
    environment = os.environ.copy()
    for key in values:
        environment.pop(key, None)
    shutil.copyfile(PRIVATE / '.env.selected', ROOT / '.env')
    (ROOT / '.env').chmod(0o600)
    compose = ['docker', 'compose', '--project-directory', str(ROOT), '--profile', 'glm-sdk']
    config = json.loads(subprocess.check_output(compose + ['config', '--format', 'json'], env=environment, text=True))
    api_environment = config['services']['mosaicparse']['environment']
    legacy = [key for key in api_environment if any(token in key.lower() for token in ('qwen', 'ollama', 'vlm'))]
    assert not legacy
    assert float(api_environment['GLM_SDK_RENDER_SCALE']) == 200 / 72
    assert api_environment['DOCLING_DO_CELL_MATCHING'] == '0'
    assert config['services']['glm-ocr-sdk']['environment']['HF_HUB_OFFLINE'] == '1'
    save('production-deployment-start.json', {'UTC': dt.datetime.now(dt.timezone.utc).isoformat(), 'active_jobs': 0,
        'before': before, 'new_environment_SHA256': hashlib.sha256((ROOT / '.env').read_bytes()).hexdigest(),
        'legacy_model_environment_keys': legacy, 'secret_values_recorded': False})
    with (HERE / 'production-compose-update.log').open('w') as log:
        subprocess.run(compose + ['up', '-d', '--no-deps', '--force-recreate', 'glm-ocr-sdk'], env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
        for attempt in range(180):
            probe = subprocess.run(['docker', 'exec', 'docling_glm_ocr_sdk', 'python', '-c',
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5002/health',timeout=3)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if probe.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Production SDK readiness timed out')
        assert active_jobs() == 0
        subprocess.run(compose + ['up', '-d', '--no-deps', '--force-recreate', 'mosaicparse'], env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
    headers = {'X-API-Key': values['API_KEY']} if values.get('API_KEY') else {}
    with httpx.Client(base_url=BASE, headers=headers, trust_env=False, timeout=15) as client:
        for attempt in range(180):
            try:
                response = client.get('/ready')
                if response.status_code == 200:
                    save('production-ready-after.json', response.json())
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Production API readiness timed out')
        results = []
        for case in read(HERE / 'production-old-jobs-before.json')['jobs']:
            job = client.get('/v1/content/jobs/' + case['id'])
            response = client.get('/v1/content/jobs/' + case['id'] + '/result')
            results.append({'id': case['id'], 'status_HTTP': job.status_code, 'result_HTTP': response.status_code,
                            'MD_SHA256': hashlib.sha256(response.content).hexdigest(),
                            'MD_unchanged': hashlib.sha256(response.content).hexdigest() == case['MD_SHA256']})
        save('production-old-jobs-after.json', {'jobs': results})
        assert all(item['status_HTTP'] == 200 and item['result_HTTP'] == 200 and item['MD_unchanged'] for item in results)
        save('production-health-after.json', client.get('/health').json())
        save('production-backends-after.json', client.get('/v1/backends').json())
    script = """import json,hashlib,importlib.metadata as m; from pathlib import Path; from app.config import Settings; s=Settings(); print(json.dumps({'source_files_SHA256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('app').rglob('*.py'))},'versions':{n:m.version(n) for n in ['docling','docling-core','docling-ibm-models','pypdfium2','torch','transformers']},'configuration':s.public_config(),'SDK_render_scale':s.glm_sdk_render_scale,'SDK_url':s.glm_sdk_url,'orientation_model':str(s.glm_sdk_orientation_model_path)}))"""
    actual = json.loads(subprocess.check_output(['docker', 'exec', 'mosaicparse', 'python', '-c', script], text=True))
    save('production-application-version.json', actual)
    assert actual['source_files_SHA256'] == expected['source_files_SHA256']
    assert actual['SDK_render_scale'] == 200 / 72
    assert actual['configuration']['glm_sdk_orientation_enabled'] is True
    assert actual['configuration']['docling_do_cell_matching'] is False
    assert actual['configuration']['docling_pdf_backend'] == 'pypdfium'
    assert actual['configuration']['glm_sdk_enabled'] is True
    after = {name: identity(name) for name in before}
    assert after['mosaicparse']['image'] == expected['image']
    assert after['docling_glm_ocr_sdk']['image'] == read(capture / 'run-plan.json')['containers']['mosaicparse-sdk-candidate']['image_ID']
    assert before['docling_glm_ocr'] == after['docling_glm_ocr']
    save('production-deployment.json', {'UTC': dt.datetime.now(dt.timezone.utc).isoformat(), 'base_url': BASE,
        'before': before, 'after': after, 'GPU_provider_unchanged': True, 'old_10_job_Markdown_unchanged': True,
        'application_source_files_match_accepted_image': True, 'active_jobs_after': active_jobs(),
        'accepted_full_cohort': 'final-candidate-http', 'post_deployment_HTTP_validation': 'production-http'})
    print('Selected API and SDK deployed; readiness, source hashes and 10 old job results verified.')


if __name__ == '__main__':
    main()
