from pathlib import Path
import hashlib,json,time,sys
from PIL import Image
import torch
ROOT=Path('/opt/mosaic-parse');sys.path.insert(0,str(ROOT))
from app.services.orientation_service import DocumentOrientationService
BASE=ROOT/'benchmark-results/clean-model-comparison-20261015'
OUT=Path(__file__).resolve().parent
manifest=json.loads((BASE/'input-manifest.json').read_text())
reference=json.loads((BASE/'paddle/official-orientation/manifest.json').read_text())
ref={Path(d['path']).stem if 'path'in d else d.get('source_id',d.get('source','')):d for d in reference['documents']}
print('document_reference_keys',list(reference['documents'][0]),flush=True)
torch.set_num_threads(4)
service=DocumentOrientationService(BASE/'paddle/models/PP-LCNet_x1_0_doc_ori_safetensors',allow_download=False)
rows=[];start=time.monotonic()
for doc,old in zip(manifest['documents'],reference['documents']):
    # Reference and source manifests are independently keyed by source SHA.
    old=next(d for d in reference['documents'] if d['sha256']==doc['sha256'])
    bypage={p['source_page']:p for p in old['pages']}
    for page in doc['pages']:
        if page['route']!='vision':continue
        source=ROOT/page['image_path'];import base64,io
        uri='data:image/png;base64,'+base64.b64encode(source.read_bytes()).decode()
        oriented,cw,confidence=service.orient(uri);angle=(-cw)%360;expected=bypage[page['page_number']]
        actual_image=Image.open(io.BytesIO(base64.b64decode(oriented.split(',',1)[1]))).convert('RGB')
        expected_image=Image.open(ROOT/expected['output_image_path']).convert('RGB')
        pixels_equal=actual_image.size==expected_image.size and actual_image.tobytes()==expected_image.tobytes()
        source_image=Image.open(source).convert('RGB');lossless=source_image.rotate(angle,expand=True)
        lossless_equal=actual_image.size==lossless.size and actual_image.tobytes()==lossless.tobytes()
        rows.append({'source_SHA256':doc['sha256'],'source_page':page['page_number'],'angle':angle,'expected_angle':expected['predicted_angle'],'confidence':confidence,'reference_affine_rotation_pixels_equal':pixels_equal,'lossless_rotation_pixels_equal':lossless_equal})
result={'pages':len(rows),'angle_mismatches':[r for r in rows if r['angle']!=r['expected_angle']],'lossless_pixel_mismatches':[r for r in rows if not r['lossless_rotation_pixels_equal']],'historical_affine_pixel_differences':[r for r in rows if not r['reference_affine_rotation_pixels_equal']],'CPU_threads':torch.get_num_threads(),'model_device':str(next(service._model.parameters()).device),'model_SHA256':hashlib.sha256((service.model_path/'model.safetensors').read_bytes()).hexdigest(),'seconds':time.monotonic()-start,'rows':rows}
(OUT/'orientation-real-model-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print({k:v for k,v in result.items() if k!='rows'},flush=True)
assert len(rows)==69 and not result['angle_mismatches'] and not result['lossless_pixel_mismatches']
