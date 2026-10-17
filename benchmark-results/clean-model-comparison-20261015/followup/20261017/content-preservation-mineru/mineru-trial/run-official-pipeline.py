"""Isolated official MinerU two-step trial; never reads expected answers or changes the server."""
import argparse
import contextlib
import dataclasses
import datetime
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import traceback


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n')


def plain(obj):
    if isinstance(obj,dict): return dict(obj)
    if dataclasses.is_dataclass(obj): return dataclasses.asdict(obj)
    if hasattr(obj,'model_dump'): return obj.model_dump()
    if hasattr(obj,'__dict__'): return dict(obj.__dict__)
    return obj


parser=argparse.ArgumentParser()
parser.add_argument('--model',required=True)
parser.add_argument('--spec',required=True)
parser.add_argument('--out',required=True)
parser.add_argument('--device',choices=['cpu','cuda:0'],default='cpu')
parser.add_argument('--threads',type=int,default=8)
args=parser.parse_args()
out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
lockpath=Path('/root/.cache/mosaicparse-model-experiment.gpu.lock' if args.device!='cpu' else '/root/.cache/mosaicparse-model-experiment.cpu.lock')
lock=lockpath.open('a+');fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
lock.seek(0);lock.truncate();lock.write(f'{os.getpid()} {out}\n');lock.flush()
import psutil
import pymupdf
import torch
from mineru_vl_utils import MinerUClient
from mineru_vl_utils.mineru_client import DEFAULT_PROMPTS,DEFAULT_SAMPLING_PARAMS
from mineru_vl_utils.post_process import json2md
from mineru_vl_utils.transformers_loading import load_transformers_model,load_transformers_processor

torch.set_num_threads(args.threads);torch.set_num_interop_threads(1)
proc=psutil.Process();stop=threading.Event()
resources=[]

def snapshot():
    value={'at':datetime.datetime.now().astimezone().isoformat(),'cpu_percent':proc.cpu_percent(),'rss':proc.memory_info().rss}
    try:
        value['gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu,power.draw,temperature.gpu','--format=csv,noheader,nounits'],text=True,timeout=3).strip()
    except Exception as e: value['gpu_error']=str(e)
    resources.append(value)


def monitor():
    while not stop.wait(1):
        snapshot()
        if len(resources)%10==0: save(out/'resource-samples.json',resources)

snapshot();thread=threading.Thread(target=monitor,daemon=True);thread.start()
manifest={'started_at':datetime.datetime.now().astimezone().isoformat(),'pid':os.getpid(),'model_path':args.model,'model_revision':'08aaea840498d49ce16247b6263196cf02814885','model_weight_SHA256':sha(Path(args.model)/'model.safetensors'),'device':args.device,'dtype':'float32' if args.device=='cpu' else 'float16','attention':'sdpa','threads':args.threads,'batch_size':1,'max_concurrency':1,'input_DPI':200,'SDK_layout_size':[1036,1036],'official_prompts':DEFAULT_PROMPTS,'official_sampling_params':{k:plain(v) for k,v in DEFAULT_SAMPLING_PARAMS.items()},'image_analysis':False,'abandon_paratext':False,'enable_cross_page_table_merge':False,'packages':{n:importlib.metadata.version(n) for n in ['torch','transformers','torchvision','mineru-vl-utils','accelerate','pillow','pymupdf']},'pages':[],'status':'loading'}
manifest['transformers_backend_sampling_caveat']='Official Transformers backend does not implement presence_penalty/frequency_penalty; actual generate kwargs are archived. This is not a vLLM throughput benchmark.'
manifest['runner_SHA256']=sha(Path(__file__))
manifest['input_spec_SHA256']=sha(Path(args.spec))
save(out/'run-manifest.json',manifest)
try:
    assert manifest['model_weight_SHA256']=='abf8681ca63b8dec7b67de257af47b821f179442f72998d0696ae2ed9232a5f0', 'Official model weight SHA256 mismatch'
    if args.device!='cpu':
        free,total=torch.cuda.mem_get_info()
        if free<4608*1024**2: raise RuntimeError(f'Insufficient free GPU memory for safely bounded trial: {free}')
        torch.cuda.set_per_process_memory_fraction(3584*1024**2/total,0)
    start=time.perf_counter()
    model=load_transformers_model(args.model,device_map='cpu')
    model=model.to(dtype=torch.float32 if args.device=='cpu' else torch.float16,device=args.device).eval()
    processor=load_transformers_processor(args.model)
    manifest['load_seconds']=time.perf_counter()-start
    manifest['parameters']=sum(p.numel() for p in model.parameters())
    manifest['actual_dtype']=str(model.dtype)
    manifest['image_processor_config']=processor.image_processor.to_dict()
    manifest['processor_chat_template_SHA256']=hashlib.sha256(processor.chat_template.encode()).hexdigest()
    manifest['actual_attention']=str(model.config._attn_implementation)
    manifest['gpu_allocator_budget_MiB']=3584 if args.device!='cpu' else None
    manifest['existing_CUDA_packages_imported_readonly_from']='/opt/qwen3-tts-openai/.tools/venv-gpu/lib/python3.12/site-packages' if args.device!='cpu' else None
    manifest['status']='running';save(out/'run-manifest.json',manifest)
    client=MinerUClient(backend='transformers',model=model,processor=processor,batch_size=1,max_concurrency=1,image_analysis=False,abandon_paratext=False,enable_cross_page_table_merge=False,use_tqdm=False)
    current={'dir':out,'calls':[],'next':0}
    generate=model.generate
    def timed_generate(*a,**kw):
        if args.device!='cpu': torch.cuda.synchronize()
        t=time.perf_counter()
        with torch.inference_mode(): outputs=generate(*a,**kw)
        if args.device!='cpu': torch.cuda.synchronize()
        call={'seconds':time.perf_counter()-t,'input_tokens':int(kw['input_ids'].shape[-1]),'generated_tokens':int(outputs.shape[-1]-kw['input_ids'].shape[-1]),'output_tokens':int(outputs.shape[-1]),'kwargs':{k:v for k,v in kw.items() if not isinstance(v,torch.Tensor)},'last_token_id':int(outputs[0,-1]),'eos_token_id':model.generation_config.eos_token_id}
        if args.device!='cpu': call.update({'cuda_peak_allocated':torch.cuda.max_memory_allocated(),'cuda_peak_reserved':torch.cuda.max_memory_reserved()})
        raw=processor.batch_decode(outputs[:,kw['input_ids'].shape[-1]:],skip_special_tokens=False,clean_up_tokenization_spaces=False)
        call['raw_generation']=raw
        current['calls'].append(call);save(current['dir']/'generation-calls.json',current['calls'])
        print('GENERATE',current['dir'].name,round(call['seconds'],3),call['generated_tokens'],flush=True)
        return outputs
    model.generate=timed_generate
    predict=client.client._predict_one_batch
    def audited_predict(image_objs,chat_prompts,sampling_params,**kw):
        call_id=current['next'];current['next']+=1
        d=current['dir']/'sdk-calls'/f'{call_id:03d}';d.mkdir(parents=True,exist_ok=True)
        images=[]
        for i,image in enumerate(image_objs):
            if image is not None:
                p=d/f'image-{i}.png';image.save(p);images.append({'path':str(p),'SHA256':sha(p),'size':list(image.size)})
        save(d/'input.json',{'images':images,'chat_prompts':chat_prompts,'sampling_params':plain(sampling_params)})
        result=predict(image_objs=image_objs,chat_prompts=chat_prompts,sampling_params=sampling_params,**kw)
        save(d/'raw-text.json',result)
        return result
    client.client._predict_one_batch=audited_predict
    for spec in json.loads(Path(args.spec).read_text()):
        pdf=Path(spec['pdf']);page_no=spec['page'];d=out/f'{spec["id"]}-p{page_no}';d.mkdir(parents=True,exist_ok=True)
        doc=pymupdf.open(pdf);page=doc[page_no-1];pix=page.get_pixmap(dpi=200,alpha=False);p=d/'source-page.png';pix.save(p)
        from PIL import Image
        image=Image.open(p).convert('RGB')
        row={'id':spec['id'],'page':page_no,'source_pdf':str(pdf),'source_pdf_SHA256':sha(pdf),'source_total_pages':len(doc),'source_page_SHA256':sha(p),'source_page_size':list(image.size),'source_pdf_page_rotation':page.rotation,'status':'running'}
        current.update({'dir':d,'calls':[],'next':0});save(d/'request.json',row)
        if args.device!='cpu': torch.cuda.reset_peak_memory_stats()
        started=time.perf_counter()
        result=client.two_step_extract(image)
        row['client_seconds']=time.perf_counter()-started
        row['pure_generate_seconds']=sum(c['seconds'] for c in current['calls'])
        row['generated_tokens']=sum(c['generated_tokens'] for c in current['calls'])
        row['model_calls']=len(current['calls']);row['blocks']=len(result)
        save(d/'official-blocks.json',[plain(b) for b in result])
        (d/'official.md').write_text(json2md(result))
        row.update({'status':'complete','blocks_SHA256':sha(d/'official-blocks.json'),'MD_SHA256':sha(d/'official.md')})
        save(d/'request.json',row);manifest['pages'].append(row);save(out/'run-manifest.json',manifest)
        print('PAGE_COMPLETE',json.dumps(row,ensure_ascii=False),flush=True)
    manifest['status']='complete'
except BaseException as e:
    manifest['status']='failed';manifest['failed_page']=str(current['dir']) if 'current' in globals() else None;manifest['error']=repr(e);manifest['traceback']=traceback.format_exc();print(manifest['traceback'],flush=True)
finally:
    stop.set();thread.join(timeout=5);snapshot();save(out/'resource-samples.json',resources);manifest['finished_at']=datetime.datetime.now().astimezone().isoformat();save(out/'run-manifest.json',manifest)

if manifest['status']=='failed': raise SystemExit(1)
