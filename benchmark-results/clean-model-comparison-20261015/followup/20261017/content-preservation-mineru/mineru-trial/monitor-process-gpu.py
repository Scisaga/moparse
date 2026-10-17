import datetime,json,subprocess,time,sys
from pathlib import Path
p=Path(sys.argv[1]);samples=[]
while not (p/'run-manifest.json').exists():time.sleep(1)
while True:
 try:
  m=json.loads((p/'run-manifest.json').read_text());pid=m['pid']
  raw=subprocess.check_output(['nvidia-smi','pmon','-s','um','-c','1'],text=True,timeout=5)
  lines=[s for s in raw.splitlines() if not s.startswith('#') and len(s.split())>1 and s.split()[1]==str(pid)]
  samples.append({'at':datetime.datetime.now().astimezone().isoformat(),'pid':pid,'pmon_header':'gpu pid type sm% mem% enc% dec% jpg% ofa% fbMB ccpmMB command','process_gpu_lines':lines})
  (p/'process-resource-samples.json').write_text(json.dumps(samples,indent=2))
  if m['status'] in ['complete','failed']:break
 except FileNotFoundError: pass
 except Exception as e: print(type(e).__name__,str(e),flush=True)
 time.sleep(1)
