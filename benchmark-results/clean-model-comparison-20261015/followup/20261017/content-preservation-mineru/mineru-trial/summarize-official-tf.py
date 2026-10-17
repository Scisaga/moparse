import datetime,hashlib,json,statistics
from pathlib import Path
p=Path(__file__).resolve().parent;parts=['first-pages-gpu','remaining-pages-gpu'];pages=[];cpu=[];rss=[];device=[];sm=[];fb=[];indexes=[]
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
for part in parts:
 d=p/part;m=json.loads((d/'run-manifest.json').read_text());assert m['status']=='complete'
 for row in m['pages']:
  page=d/f'{row["id"]}-p{row["page"]}';calls=json.loads((page/'generation-calls.json').read_text());checks=[]
  for c in calls:
   eos=c['eos_token_id'];checks.append(c['last_token_id'] in eos if isinstance(eos,list) else c['last_token_id']==eos)
  assert sha(page/'official.md')==row['MD_SHA256'];assert sha(page/'official-blocks.json')==row['blocks_SHA256']
  pages.append({**row,'all_generation_calls_finish_with_EOS':all(checks),'EOS_calls':sum(checks),'cuda_peak_allocated_MiB':max(c['cuda_peak_allocated'] for c in calls)/1024**2,'cuda_peak_reserved_MiB':max(c['cuda_peak_reserved'] for c in calls)/1024**2,'actual_max_length_values':sorted({c['kwargs'].get('max_length') for c in calls}),'output_dir':str(page.relative_to(p))})
 for s in json.loads((d/'resource-samples.json').read_text()):cpu.append(s['cpu_percent']);rss.append(s['rss'])
 for s in json.loads((d/'process-resource-samples.json').read_text()):
  for line in s['process_gpu_lines']:
   v=line.split()
   if v[3]!='-':sm.append(float(v[3]))
   if v[9]!='-':fb.append(float(v[9]))
 indexes.extend([{'path':str(f.relative_to(p)),'bytes':f.stat().st_size,'SHA256':sha(f)} for f in d.glob('*.json')])
summary={'created_at':datetime.datetime.now().astimezone().isoformat(),'experiment':'official MinerU2.5-Pro-2605 1.2B two-step full-page Transformers backend','source_documents':len({(r['id'],r['source_pdf_SHA256']) for r in pages}),'source_pages':len(pages),'whole_document_HTTP_acceptance':False,'model_weight_SHA256':'abf8681ca63b8dec7b67de257af47b821f179442f72998d0696ae2ed9232a5f0','model_revision':'08aaea840498d49ce16247b6263196cf02814885','precision':'FP16 explicit for SM75; no quantization','SDK':'2.0.7','transformers':'5.10.1','torch':'2.7.1+cu126','batch_size':1,'max_concurrency':1,'source_DPI':200,'layout_image_size':[1036,1036],'official_region_max_pixels':1605632,'keep_paratext':True,'model_calls':sum(r['model_calls'] for r in pages),'generated_tokens':sum(r['generated_tokens'] for r in pages),'client_seconds_sum':sum(r['client_seconds'] for r in pages),'pure_generate_seconds_sum':sum(r['pure_generate_seconds'] for r in pages),'load_seconds_sum':sum(json.loads((p/part/'run-manifest.json').read_text())['load_seconds'] for part in parts),'all_calls_finish_EOS':all(r['all_generation_calls_finish_with_EOS'] for r in pages),'gpu_own_peak_allocated_MiB':max(r['cuda_peak_allocated_MiB'] for r in pages),'gpu_own_peak_reserved_MiB':max(r['cuda_peak_reserved_MiB'] for r in pages),'gpu_own_nvidia_pmon_peak_FB_MiB':max(fb) if fb else None,'gpu_own_SM_mean_valid_samples_pct':statistics.mean(sm) if sm else None,'gpu_own_SM_valid_samples':len(sm),'cpu_own_mean_percent':statistics.mean(cpu),'cpu_own_peak_percent':max(cpu),'cpu_own_peak_RSS_MiB':max(rss)/1024**2,'runtime_scope_caveat':'Shared GPU1 with unchanged production GLM and TTS; parent production HTTP requests may overlap some pages. Observed costs, not a controlled speedup comparison. PMON is own PID only; missing SM values excluded. CUDA allocator peaks exclude CUDA context/external allocations.','backend_sampling_caveat':'Official Transformers backend ignores presence/frequency penalty; official vLLM comparison is separately scheduled after production HTTP capture. No OOM or stop is a quality result.','quality_scope':'Independent source acceptance maintained by source_acceptance_corpus; this summary verifies raw artifact integrity/completion, not correctness by token presence.','pages':pages,'artifact_manifests':indexes}
assert len(pages)==14
(p/'tf-official-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['pages','artifact_manifests']},ensure_ascii=False,indent=2))
