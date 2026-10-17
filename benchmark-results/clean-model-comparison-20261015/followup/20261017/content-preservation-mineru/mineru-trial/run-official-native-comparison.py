"""Run the two official TXT paths after root release and GPU-owner handoff."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--execute-after-parent-release', action='store_true', required=True)
args = parser.parse_args()
ready = json.loads((HERE/'official-native-handoff-ready.json').read_text())
if ready.get('status') != 'ready_for_official_native':
    raise SystemExit('GPU-owner handoff not ready')
record = {'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'tiers':['standard','advanced'],'phases':[],'runner':str(HERE/'run-official-native-standard.py')}
start = time.monotonic()
try:
    for tier in record['tiers']:
        phase = {'tier':tier,'status':'started','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        with (HERE/f'official-native-{tier}.log').open('w') as log:
            result = subprocess.run([sys.executable,str(HERE/'run-official-native-standard.py'),
                '--execute-after-parent-release','--tier',tier,'--defer-handoff-complete'],
                stdout=log,stderr=subprocess.STDOUT)
        phase.update(exit_code=result.returncode,status='completed' if result.returncode==0 else 'failed',
                     finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        record['phases'].append(phase)
        if result.returncode != 0:
            record['remaining_tiers_not_started']=[x for x in record['tiers']if x not in {p['tier']for p in record['phases']}]
            break
finally:
    record.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  wall_seconds=time.monotonic()-start,
                  status='completed' if len(record['phases'])==2 and all(p['exit_code']==0 for p in record['phases']) else 'incomplete')
    (HERE/'official-native-comparison-execution.json').write_text(json.dumps(record,indent=2)+'\n')
    receipt = 'official-native-handoff-complete.json' if record['status']=='completed' else 'official-native-handoff-attempt-incomplete.json'
    (HERE/receipt).write_text(json.dumps({
        'status':record['status'],'owner':'preserve_exported_content',
        'finished_at':record['finished_at'],'runner_no_longer_sends_requests':True,
        'phases':record['phases'],'remaining_tiers_not_started':record.get('remaining_tiers_not_started',[])},indent=2)+'\n')
if record['status']!='completed':
    raise SystemExit(1)
