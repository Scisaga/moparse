"""Verify every old production asset by HTTP without changing stored results."""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json

import httpx
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--phase', choices=('before', 'after'), required=True)
args = parser.parse_args()
secret = dotenv_values('/root/.cache/mosaic-parse-deploy/20261017/.env.before').get('API_KEY') or ''
headers = {'X-API-Key': secret} if secret else {}
jobs = json.loads((HERE / 'production-old-jobs-before.json').read_text())['jobs']
records = []
with httpx.Client(base_url='http://10.0.6.22:12303', headers=headers, trust_env=False, timeout=60) as client:
    for job in jobs:
        listing = client.get('/v1/content/jobs/' + job['id'] + '/assets')
        listing.raise_for_status()
        for asset in listing.json():
            response = client.get('/v1/content/jobs/' + job['id'] + '/assets/' + asset['asset_id'])
            digest = hashlib.sha256(response.content).hexdigest()
            records.append({'job': job['id'], 'asset': asset['asset_id'], 'HTTP_status': response.status_code,
                            'size_bytes': len(response.content), 'SHA256': digest,
                            'matches_public_metadata': response.status_code == 200 and digest == asset['sha256'] and len(response.content) == asset['size_bytes']})
result = {'UTC': dt.datetime.now(dt.timezone.utc).isoformat(), 'phase': args.phase, 'old_jobs': len(jobs),
          'old_assets': len(records), 'passed': sum(item['matches_public_metadata'] for item in records),
          'model_requests': 0, 'assets': records}
if args.phase == 'after':
    before = json.loads((HERE / 'production-old-assets-before.json').read_text())
    result['identical_to_before'] = records == before['assets']
    assert result['identical_to_before']
(HERE / f'production-old-assets-{args.phase}.json').write_text(json.dumps(result, indent=2) + '\n')
assert result['old_assets'] == result['passed'] == 195
print({key: value for key, value in result.items() if key != 'assets'})
