import datetime,hashlib,json,re,statistics
from pathlib import Path
p=Path(__file__).resolve().parent;out=p/'vllm-http';m=json.loads((out/'run-manifest.json').read_text());assert m['status']=='complete' and len(m['pages'])==14
controller=json.loads((out/'controller.json').read_text());tf={}
for part in ['first-pages-gpu','remaining-pages-gpu']:
 for r in json.loads((p/part/'run-manifest.json').read_text())['pages']:tf[(r['id'],r['page'])]=r

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def metrics(f):
 d={}
 for line in f.read_text().splitlines():
  if line.startswith('vllm:') and '_sum{' in line:
   key=line.split('{',1)[0];d[key]=d.get(key,0)+float(line.rsplit(' ',1)[1])
 return d
pages=[];all_params={};all_calls=[]
for r in m['pages']:
 d=out/f'{r["id"]}-p{r["page"]}';calls=json.loads((d/'generation-calls.json').read_text());details=[]
 for f in sorted((d/'model-http').glob('*/request.json')):
  req=json.loads(f.read_text());response=json.loads((f.parent/'response.json').read_text());usage=response['usage'];choices=response['choices'];text=''.join(c.get('text','') for v in req['messages'] if isinstance(v.get('content'),list) for c in v['content'])
  params={k:v for k,v in req.items() if k not in ['model','messages']};all_params.setdefault(text,params);assert all_params[text]==params
  detail={'call':f.parent.name,'prompt':text,'params':params,'model':response['model'],'usage':usage,'finish_reasons':[v['finish_reason'] for v in choices],'stop_reasons':[v.get('stop_reason') for v in choices],'input_truncation_requested':req.get('truncate_prompt_tokens') is not None,'custom_stop_requested':req.get('stop') is not None,'request_SHA256':sha(f),'response_SHA256':sha(f.parent/'response.json')}
  assert detail['finish_reasons']==['stop'] and not detail['input_truncation_requested'] and not detail['custom_stop_requested'];assert usage['total_tokens']<=8192 and usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'];details.append(detail)
 before=metrics(d/'metrics-before.prom');after=metrics(d/'metrics-after.prom');delta={k:after.get(k,0)-before.get(k,0) for k in ['vllm:request_inference_time_seconds_sum','vllm:request_prefill_time_seconds_sum','vllm:request_decode_time_seconds_sum','vllm:request_queue_time_seconds_sum','vllm:e2e_request_latency_seconds_sum']}
 assert r['source_pdf_SHA256']==tf[(r['id'],r['page'])]['source_pdf_SHA256'];assert r['source_page_SHA256']==tf[(r['id'],r['page'])]['source_page_SHA256'];assert sha(d/'official.md')==r['MD_SHA256'];assert sha(d/'official-blocks.json')==r['blocks_SHA256']
 pages.append({**r,'timing_boundary':'client_seconds wraps only two_step_extract; excludes PDF rendering/json2md/persistence/metrics snapshots','PDF_render_seconds':None,'MD_conversion_and_persistence_seconds':None,'whole_case_PDF_to_MD_seconds':None,'source_page_PNG_byte_identical_to_TF':True,'model_inference_metrics_delta':delta,'HTTP_calls':details,'all_calls_finish_stop_without_truncation':True});all_calls+=details
logs=(out/'server.log').read_text();caps=re.findall(r'GPU KV cache size: ([\d,]+) tokens',logs);capacity=int(caps[-1].replace(',','')) if caps else None;assert capacity is not None and capacity>=8192
own_ready=controller.get('own_container_processes_ready','');own_pids={int(v.split()[0]) for v in own_ready.splitlines()[1:] if v.strip() and v.split()[0].isdigit()};sm=[];fb=[]
for s in json.loads((out/'resource-samples.json').read_text()):
 if s.get('phase')!='original_14':continue
 for line in s.get('PMON','').splitlines():
  v=line.split()
  if len(v)>10 and v[0].isdigit() and v[1].isdigit() and int(v[1]) in own_pids:
   if v[3]!='-':sm.append(float(v[3]))
   if v[9]!='-':fb.append(float(v[9]))
summary={'created_at':datetime.datetime.now().astimezone().isoformat(),'experiment':'Official SDK2.0.7 two_step_extract via isolated vLLM0.19.1 FP16','source_pages':14,'source_documents':6,'whole_document_HTTP_acceptance':False,'render_MD_persist_fullcase_timers':'unknown; no retrospective timing invented','client_seconds_sum':sum(v['client_seconds'] for v in pages),'model_HTTP_seconds_sum':sum(v['model_HTTP_seconds'] for v in pages),'server_request_inference_seconds_sum':sum(v['model_inference_metrics_delta']['vllm:request_inference_time_seconds_sum'] for v in pages),'server_request_prefill_seconds_sum':sum(v['model_inference_metrics_delta']['vllm:request_prefill_time_seconds_sum'] for v in pages),'server_request_decode_seconds_sum':sum(v['model_inference_metrics_delta']['vllm:request_decode_time_seconds_sum'] for v in pages),'server_start_seconds':controller['server_start_seconds'],'model_calls':len(all_calls),'generated_completion_tokens':sum(v['usage']['completion_tokens'] for v in all_calls),'max_request_prompt_tokens':max(v['usage']['prompt_tokens'] for v in all_calls),'max_request_total_tokens':max(v['usage']['total_tokens'] for v in all_calls),'all_calls_finish_stop':True,'length_abort_error_calls':0,'input_truncation_requested':False,'configured_EOS_ids':[151645,151643],'EOS_verification_scope':'OpenAI finish_reason=stop with no stop strings or input truncation requested; raw request/response plus model EOS config retained. EOS token IDs are not returned by API, so no last-token tracing claim.','KV_cache_bytes':134217728,'actual_KV_capacity_tokens':capacity,'max_model_len':8192,'actual_official_sampling_by_prompt':all_params,'gpu_own_PMON_peak_FB_MiB_original14':max(fb) if fb else None,'gpu_own_PMON_SM_mean_valid_samples_pct_original14':statistics.mean(sm) if sm else None,'gpu_own_PMON_SM_valid_samples_original14':len(sm),'runtime_environment':'Shared GPU1 GLM+TTS unchanged; root confirmed no production GLM inference overlaps this phase. Host CPU shared with170 native Docling pages. Observed component costs; not an exclusive-hardware end-to-end benchmark.','server_packages':controller.get('server_packages'),'pages':pages}
(p/'vllm-official-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ['pages','actual_official_sampling_by_prompt']},ensure_ascii=False,indent=2))
