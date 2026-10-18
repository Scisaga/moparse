"""Project native backend duration metadata only from own immutable job logs.
No model, parse API, raw HTML, cell coordinates or public output is written.
"""
from __future__ import annotations
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from benchmark import moparse_benchmark as b
from benchmark.tools.enrich_evidence import snapshot
BASE=Path(__file__).resolve().parent
METHOD='mineru-advanced-txt-vllm-c2-docling-source-glm-v6'


def identity(base=BASE):
    spec=importlib.util.spec_from_file_location('own_source_stage_identity',base/'extract_source_stage.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.data_identity(base)


def project(case,document,storage_identity):
    summary=b.read(case/'summary.json');request=b.read(case/'request.json')
    actual=summary.get('actual_job_status',summary['status'])
    capture=summary.get('capture_status',summary['status'])
    assert capture=='completed' and actual in {'completed','partial'}
    assert summary['source_sha256']==request['source']['sha256']==document['sha256']
    assert summary['MD_SHA256']==b.digest(case/'result.md')
    job=summary['job']
    assert job.startswith('job_') and job[4:].isalnum()
    volume=Path(storage_identity['data_volume']['Source']).resolve()
    raw_path=volume/'jobs'/job/'logs/mineru-native-worker.json'
    assert raw_path.resolve().is_relative_to(volume)
    item={'document_id':document['id'],'source_sha256':document['sha256'],
        'job_id':job,'actual_job_status':actual,'capture_status':capture,
        'captured_summary':b.artifact(case/'summary.json'),'received_MD_sha256':summary['MD_SHA256'],
        'request':b.artifact(case/'request.json'),'actual_storage_identity':storage_identity,
        'worker_response_exists':raw_path.is_file(),'native_backend_wall_seconds':None,
        'source_sha256_is_job_request_binding_not_claimed_worker_payload_field':True}
    if not raw_path.is_file():
        item['observation_status']='unknown_no_private_native_response; absence_not_zero'
        return item
    raw=b.read(raw_path);pages=raw.get('pages');duration=raw.get('duration_ms')
    numbers=[x.get('page_number') for x in pages if isinstance(x,dict)] if isinstance(pages,list) else []
    item['private_worker_response']={'container_path':f'/data/jobs/{job}/logs/mineru-native-worker.json',
        'sha256':b.digest(raw_path),'bytes':raw_path.stat().st_size}
    item['selected_metadata']={key:raw.get(key) for key in ('schema','backend','duration_ms','page_count')}
    item['selected_metadata']['returned_source_pages']=numbers
    valid=(raw.get('schema')=='mineru-native/1' and raw.get('backend')=='mineru-advanced-txt'
        and raw.get('page_count')==document['page_count'] and type(duration)is int and duration>=0
        and isinstance(pages,list) and len(numbers)==len(pages) and bool(numbers)
        and all(type(x)is int and 1<=x<=document['page_count'] for x in numbers)
        and len(set(numbers))==len(numbers))
    item['observation_status']='observed' if valid else 'unknown_invalid_private_metadata'
    if valid:item['native_backend_wall_seconds']=duration/1000
    return item


def collect(name):
    dataset_path=(ROOT/'benchmark/datasets/moparse-addon-20261018/dataset.json'
                  if name=='fresh7' else b.DEFAULT_DATASET)
    cohort_id={'regression504':'regression-504','holdout39':'holdout-20261018','fresh7':'fresh7-20261018'}[name]
    dataset,docs=b.load_dataset(dataset_path)
    expected=next(x['document_ids'] for x in dataset['cohorts'] if x['id']==cohort_id)
    docs={x['id']:x for x in docs if x['id'] in expected}
    capture=BASE/name;run=b.read(capture/'run.json');assert run['status']=='completed'
    observed_identity=identity();records=[project(capture/'cases'/key,docs[key],observed_identity) for key in sorted(docs)]
    measured=[x for x in records if x['observation_status']=='observed']
    result={'schema':'moparse-native-backend-stage-cohort-observation/1','created_at':b.utc(),
        'cohort_id':cohort_id,'run':b.artifact(capture/'run.json'),'dataset':b.artifact(dataset_path),
        'expected_documents':len(docs),'recorded_documents':len(measured),
        'missing_or_invalid_duration_documents':[x['document_id'] for x in records if x['observation_status']!='observed'],
        'observed_native_backend_wall_seconds':sum(x['native_backend_wall_seconds'] for x in measured),
        'full_cohort_native_backend_wall_seconds':sum(x['native_backend_wall_seconds'] for x in measured) if len(measured)==len(docs) else None,
        'returned_native_source_pages':sum(len(x['selected_metadata']['returned_source_pages']) for x in measured),
        'percase':records,'scope':'Sum of worker parse CPU prelayout/formula + GPU calls + typed source assembly elapsed durations; excludes upload/worker queue before parse, GLM/header/source verification; not GPU forward time or CPU core-seconds',
        'GPU_forward_time_seconds':None,'missing_duration_is_zero':False,
        'raw_HTML_or_coordinates_exported':False,'API_or_model_calls':False,
        'source_producer_sha256':b.method(METHOD)['recipe']['application_source_freeze']['source_file_sha256']['native_worker/server.py'],
        'extractor':snapshot(Path(__file__))}
    output=BASE/f'{name}-native-backend-stage-final.json';b.save(output,result)
    record={'schema':'moparse-evidence/1','id':f'source-v6-{name}-native-backend-timing-20261018',
        'method_id':METHOD,'cohort_id':cohort_id,'origin':'fresh_component','fresh_model_inference':False,
        'output_stage':'diagnostic-only','quality':{},'performance':{},
        'provenance':[snapshot(output),result['extractor']],
        'native_backend_stage_observation':{k:result[k] for k in ['expected_documents','recorded_documents','observed_native_backend_wall_seconds','full_cohort_native_backend_wall_seconds','returned_native_source_pages','scope','GPU_forward_time_seconds']},
        'qualification':{'observation_only':True,'gold_or_scores_changed':False,'deployment_acceptance':False}}
    assert not b.validate_evidence(record)
    b.save(ROOT/'benchmark/evidence'/f"{record['id']}.json",record)
    return result


if __name__=='__main__':
    import time
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    for name in ('regression504','holdout39','fresh7'):
        target=ROOT/f'benchmark/evidence/source-v6-{name}-20261018.json'
        while not target.is_file():time.sleep(10)
        assert b.read(target)['status']=='completed','Original cohort failed; do not claim completedstage'
        result=collect(name)
        print(b.json.dumps({'native_backend_stage':name,'recorded':result['recorded_documents'],
            'expected':result['expected_documents'],'observed_seconds':result['observed_native_backend_wall_seconds']}),flush=True)
