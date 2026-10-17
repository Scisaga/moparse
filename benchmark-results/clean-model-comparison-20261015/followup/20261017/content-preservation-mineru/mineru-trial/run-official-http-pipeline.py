"""Official two-step HTTP client trial, preserving exact raw model request/response bytes."""
import argparse,base64,datetime,hashlib,importlib.metadata,json,os,time,traceback
os.environ['NO_PROXY']='127.0.0.1,localhost';os.environ['no_proxy']='127.0.0.1,localhost'
from pathlib import Path
import httpx,pymupdf
from PIL import Image
from mineru_vl_utils import MinerUClient
from mineru_vl_utils.post_process import json2md

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--spec',required=True);p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
m={'started_at':datetime.datetime.now().astimezone().isoformat(),'backend':'official http-client -> isolated vLLM 0.19.1','SDK':importlib.metadata.version('mineru-vl-utils'),'client_packages':{n:importlib.metadata.version(n) for n in ['pillow','pymupdf','mineru-vl-utils','httpx']},'runner_SHA256':sha(Path(__file__)),'input_spec_SHA256':sha(a.spec),'source_DPI':200,'layout_image_size':[1036,1036],'model':'mineru-trial','image_analysis':False,'abandon_paratext':False,'cross_page_merge':False,'pages':[],'status':'running'};save(out/'run-manifest.json',m)
current={'dir':out,'calls':[],'counter':0}
def request_hook(r):
 if '/chat/completions' not in str(r.url):return
 i=current['counter'];current['counter']+=1;r.extensions['evidence_id']=i;r.extensions['started']=time.perf_counter();d=current['dir']/'model-http'/f'{i:03d}';d.mkdir(parents=True,exist_ok=True);(d/'request.json').write_bytes(r.content)
 body=json.loads(r.content)
 for j,v in enumerate(body.get('messages',[])):
  if isinstance(v.get('content'),list):
   for k,item in enumerate(v['content']):
    if item.get('type')=='image_url':
     u=item['image_url']['url'];(d/f'image-{j}-{k}.png').write_bytes(base64.b64decode(u.split(',',1)[1]))
def response_hook(r):
 if 'evidence_id' not in r.request.extensions:return
 r.read();i=r.request.extensions['evidence_id'];d=current['dir']/'model-http'/f'{i:03d}';(d/'response.json').write_bytes(r.content);v=r.json();call={'index':i,'HTTP_status':r.status_code,'model_HTTP_seconds':time.perf_counter()-r.request.extensions['started'],'usage':v.get('usage'),'finish_reasons':[c.get('finish_reason') for c in v.get('choices',[])],'request_SHA256':sha(d/'request.json'),'response_SHA256':sha(d/'response.json')};current['calls'].append(call);save(current['dir']/'generation-calls.json',current['calls']);print('MODEL_HTTP',current['dir'].name,round(call['model_HTTP_seconds'],3),call['finish_reasons'],flush=True)
async def arq(r):request_hook(r)
async def ars(r):await r.aread();response_hook(r)
client=MinerUClient(backend='http-client',server_url=a.url,model_name='mineru-trial',max_concurrency=1,batch_size=1,image_analysis=False,abandon_paratext=False,enable_cross_page_table_merge=False,use_tqdm=False,max_retries=0)
client.client._client.event_hooks={'request':[request_hook],'response':[response_hook]}
orig=client.client._new_aio_client
async def new_aio():
 c=await orig();c.event_hooks={'request':[arq],'response':[ars]};return c
client.client._new_aio_client=new_aio
try:
 for spec in json.loads(Path(a.spec).read_text()):
  d=out/f'{spec["id"]}-p{spec["page"]}';d.mkdir(parents=True,exist_ok=True);current.update({'dir':d,'calls':[],'counter':0});pdf=Path(spec['pdf']);doc=pymupdf.open(pdf);page=doc[spec['page']-1];image_path=d/'source-page.png';page.get_pixmap(dpi=200,alpha=False).save(image_path);image=Image.open(image_path).convert('RGB')
  row={'id':spec['id'],'page':spec['page'],'source_pdf_SHA256':sha(pdf),'source_page_SHA256':sha(image_path),'source_page_size':list(image.size),'source_pdf_page_rotation':page.rotation,'source_total_pages':len(doc),'status':'running'};save(d/'request.json',row)
  with httpx.Client(timeout=10,trust_env=False) as c:(d/'metrics-before.prom').write_text(c.get(a.url+'/metrics').text)
  t=time.perf_counter();result=client.two_step_extract(image);row['client_seconds']=time.perf_counter()-t;row['model_HTTP_seconds']=sum(v['model_HTTP_seconds'] for v in current['calls']);row['model_calls']=len(current['calls']);row['blocks']=len(result)
  save(d/'official-blocks.json',[dict(v) for v in result]);(d/'official.md').write_text(json2md(result))
  with httpx.Client(timeout=10,trust_env=False) as c:(d/'metrics-after.prom').write_text(c.get(a.url+'/metrics').text)
  row.update({'status':'complete','blocks_SHA256':sha(d/'official-blocks.json'),'MD_SHA256':sha(d/'official.md')});save(d/'request.json',row);m['pages'].append(row);save(out/'run-manifest.json',m);print('PAGE_COMPLETE',json.dumps(row,ensure_ascii=False),flush=True)
 m['status']='complete'
except BaseException as e:m['status']='failed';m['error']=repr(e);m['traceback']=traceback.format_exc();print(m['traceback'],flush=True)
finally:m['finished_at']=datetime.datetime.now().astimezone().isoformat();save(out/'run-manifest.json',m)
if m['status']=='failed':raise SystemExit(1)
