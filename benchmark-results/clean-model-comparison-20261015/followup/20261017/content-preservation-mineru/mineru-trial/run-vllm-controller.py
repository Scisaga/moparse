"""Own only one isolated candidate container, with a shared GPU experiment lock."""
import datetime,fcntl,hashlib,json,os,subprocess,time,traceback
from pathlib import Path
import httpx
os.environ['NO_PROXY']='127.0.0.1,localhost';os.environ['no_proxy']='127.0.0.1,localhost'
base=Path(__file__).resolve().parent;server_only=os.environ.get('MINERU_TRIAL_SERVER_ONLY')=='1';out=base/('vllm-native-server' if server_only else 'vllm-http');out.mkdir(parents=True,exist_ok=True);name='mosaicparse-mineru-vllm-trial-20261017';lock=Path('/root/.cache/mosaicparse-model-experiment.gpu.lock').open('a+')

def save(p,v):p.write_text(json.dumps(v,indent=2,default=str)+'\n')
def now():return datetime.datetime.now().astimezone().isoformat()
def gpu_snapshot():
 raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.free,utilization.gpu,power.draw','--format=csv,noheader,nounits'],text=True)
 if int(raw.splitlines()[1].split(',')[2])<512:raise RuntimeError('Own candidate interrupted by GPU1 safety guard: <512MiB free, preserving existing workloads; not a model quality result')
 return raw
def cmd(args,check=True):return subprocess.run(args,text=True,capture_output=True,check=check)
m={'created_at':now(),'status':'waiting_for_gpu_experiment_lock','container_name':name,'server_image':'mosaicparse-mineru-vllm-trial:2.0.7-v0.19.1','GPU':1,'model':'opendatalab/MinerU2.5-Pro-2605-1.2B','model_revision':'08aaea840498d49ce16247b6263196cf02814885','memory_utilization':0.16,'KV_cache_memory_bytes':134217728,'max_num_seqs':1,'max_model_len':8192,'max_num_batched_tokens':2048,'dtype':'float16','enforce_eager':True};m['controller_SHA256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();(out/'controller-source.py').write_bytes(Path(__file__).read_bytes());save(out/'controller.json',m)
fcntl.flock(lock.fileno(),fcntl.LOCK_EX);lock.seek(0);lock.truncate();lock.write(f'{os.getpid()} {out}\n');lock.flush();container=None
try:
 m['GPU_free_gate_samples']=[]
 for _ in range(31):
  raw=cmd(['nvidia-smi','--query-gpu=index,memory.free,memory.total,utilization.gpu','--format=csv,noheader,nounits']).stdout;free=int(raw.splitlines()[1].split(',')[1]);m['GPU_free_gate_samples'].append({'at':now(),'GPU1_free_MiB':free});save(out/'controller.json',m)
  if free>=4800:break
  time.sleep(1)
 m['hardware_before']=raw;m['compute_apps_before']=cmd(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv']).stdout;assert free>=4800,f'Only {free}MiB free on GPU1 after waiting for previous owned CUDA context teardown; safe gate requires 4800MiB'
 existing=cmd(['docker','ps','-aq','--filter','name=^/'+name+'$']).stdout.strip();assert not existing,'Own candidate name already exists; do not replace implicitly'
 modelrepo='/root/.cache/huggingface/hub/models--opendatalab--MinerU2.5-Pro-2605-1.2B';modelpath='/models/mineru/snapshots/08aaea840498d49ce16247b6263196cf02814885'
 argv=['docker','run','-d','--name',name,'--label','mosaicparse.experiment=mineru-content-20261017','--gpus','device=1','--cpus','4','--memory','20g','--shm-size','2g','-p','127.0.0.1:12431:8000','-v',modelrepo+':/models/mineru:ro','-e','HF_HUB_OFFLINE=1','-e','TRANSFORMERS_OFFLINE=1','-e','VLLM_NO_USAGE_STATS=1','-e','OMP_NUM_THREADS=4','-e','TOKENIZERS_PARALLELISM=false','mosaicparse-mineru-vllm-trial:2.0.7-v0.19.1',modelpath,'--served-model-name','mineru-trial','--host','0.0.0.0','--port','8000','--dtype','half','--gpu-memory-utilization','0.16','--kv-cache-memory-bytes','134217728','--max-model-len','8192','--max-num-seqs','1','--max-num-batched-tokens','2048','--limit-mm-per-prompt','{"image":1,"video":0}','--enforce-eager','--logits-processors','mineru_vl_utils:MinerULogitsProcessor']
 m['docker_run_args']=argv;m['starting_at']=now();m['status']='starting';save(out/'controller.json',m);container=cmd(argv).stdout.strip();m['container_id']=container;save(out/'controller.json',m);t=time.perf_counter();samples=[]
 ready=False
 while time.perf_counter()-t<300:
  state=json.loads(cmd(['docker','inspect','--format','{{json .State}}',name]).stdout)
  samples.append({'at':now(),'state':state,'GPU':gpu_snapshot()})
  save(out/'startup-resource-samples.json',samples)
  (out/'server.log').write_text(cmd(['docker','logs',name],check=False).stdout+cmd(['docker','logs',name],check=False).stderr)
  if not state['Running']:raise RuntimeError('Candidate server exited during startup; inspect server.log and startup-resource-samples.json')
  try:
   r=httpx.get('http://127.0.0.1:12431/health',timeout=2,trust_env=False)
   if r.status_code==200:ready=True;break
  except httpx.HTTPError:pass
  time.sleep(2)
 assert ready,'Server readiness timeout after 300 seconds'
 m['ready_at']=now();m['server_start_seconds']=time.perf_counter()-t;m['status']='running_http_pages';m['own_container_processes_ready']=cmd(['docker','top',name,'-eo','pid,ppid,args']).stdout;save(out/'controller.json',m)
 m['server_packages']=cmd(['docker','exec',name,'python3','-c',"import importlib.metadata as m,json; print(json.dumps({n:m.version(n) for n in ['vllm','torch','transformers','huggingface-hub','mineru-vl-utils','pillow','pydantic']}))"]).stdout;save(out/'controller.json',m)
 save(out/'server-inspect.json',json.loads(cmd(['docker','inspect',name]).stdout));save(out/'models.json',httpx.get('http://127.0.0.1:12431/v1/models',trust_env=False).json());(out/'metrics-server-ready.prom').write_text(httpx.get('http://127.0.0.1:12431/metrics',trust_env=False).text)
 if not server_only:
  specs=json.loads((base/'first-pages.json').read_text())+json.loads((base/'remaining-pages.json').read_text());save(base/'all-pages.json',specs)
  with (base/'vllm-http-client.log').open('w') as log:
   client=subprocess.Popen(['/root/.cache/mosaicparse-mineru/venv/bin/python','-u',str(base/'run-official-http-pipeline.py'),'--url','http://127.0.0.1:12431','--spec',str(base/'all-pages.json'),'--out',str(out)],stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','TOKENIZERS_PARALLELISM':'false'})
   m['client_pid']=client.pid;save(out/'controller.json',m)
   while client.poll() is None:
    samples.append({'at':now(),'phase':'original_14','GPU':gpu_snapshot(),'PMON':cmd(['nvidia-smi','pmon','-s','um','-c','1']).stdout});save(out/'resource-samples.json',samples);time.sleep(1)
   m['client_exit_code']=client.returncode;assert client.returncode==0,'Official HTTP client failed; inspect vllm-http-client.log'
  m['original_14_pages_exit_code']=0
  extra_spec=base/'additional-p62.json';save(extra_spec,[{'id':'1225475375','pdf':'/opt/mosaic-parse/pdf_sample/1225475375.pdf','page':62}])
  extra_out=base/'vllm-additional-p62'
  with (base/'vllm-additional-p62-client.log').open('w') as extra_log:
   extra=subprocess.Popen(['/root/.cache/mosaicparse-mineru/venv/bin/python','-u',str(base/'run-official-http-pipeline.py'),'--url','http://127.0.0.1:12431','--spec',str(extra_spec),'--out',str(extra_out)],stdout=extra_log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','TOKENIZERS_PARALLELISM':'false'})
   while extra.poll() is None:
    samples.append({'at':now(),'phase':'additional_p62_not_in_original_14','GPU':gpu_snapshot(),'PMON':cmd(['nvidia-smi','pmon','-s','um','-c','1']).stdout});save(out/'resource-samples.json',samples);time.sleep(1)
   m['additional_p62_exit_code']=extra.returncode
 else:
  existing=json.loads((base/'vllm-http/run-manifest.json').read_text());assert existing['status']=='complete' and len(existing['pages'])==14;m['original_14_existing_completed_artifact']='vllm-http/run-manifest.json';samples=[]
 handoff_requested=base/'official-native-handoff-requested.json'
 if handoff_requested.exists():
  save(base/'official-native-handoff-ready.json',{'at':now(),'status':'ready_for_official_native','server_url':'http://127.0.0.1:12431','model':'mineru-trial','original14_complete':True,'extra_p62_exit_code':m.get('additional_p62_exit_code'),'container_id':container})
  m['status']='waiting_for_official_native_handoff';save(out/'controller.json',m)
  handoff_start=time.perf_counter()
  while not (base/'official-native-handoff-complete.json').exists() and time.perf_counter()-handoff_start<2400:
   samples.append({'at':now(),'phase':'official_native','GPU':gpu_snapshot(),'PMON':cmd(['nvidia-smi','pmon','-s','um','-c','1']).stdout});save(out/'resource-samples.json',samples);time.sleep(3)
  m['official_native_handoff_finished']=(base/'official-native-handoff-complete.json').exists()
 m['status']='complete'
except BaseException as e:m['status']='failed';m['error']=repr(e);m['traceback']=traceback.format_exc();print(m['traceback'],flush=True)
finally:
 if container:
  logs=cmd(['docker','logs',name],check=False);(out/'server.log').write_text(logs.stdout+logs.stderr)
  save(out/'final-container-inspect.json',json.loads(cmd(['docker','inspect',name]).stdout))
  m['cleanup_stop']=cmd(['docker','stop','-t','15',name],check=False).stdout;m['cleanup_rm']=cmd(['docker','rm',name],check=False).stdout
 m['finished_at']=now();m['hardware_after']=cmd(['nvidia-smi','--query-gpu=index,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits']).stdout;save(out/'controller.json',m)
if m['status']=='failed':raise SystemExit(1)
