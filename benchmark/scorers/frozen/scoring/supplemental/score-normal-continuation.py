"""Own-page complete repeated headers and shareholder bindings, no merging."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json
from pathlib import Path
H=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('supplement11_normal',H/'score-supplemental.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);SOURCE=H.parent/'same-header-continuation-source.json';m.TARGETS=json.loads(SOURCE.read_text())
def score(result):
 out=m.score(result);headers=[]
 for t in out['tables']:
  page=next((p for p in result['pages']if p['page_number']==t['source_page']and p['status']=='completed'),None);actual=next((v for v in page.get('tables',[])if v['table_id']==t['table_id']),None)if page else None;source=next(v for v in m.TARGETS['tables']if v['source_page']==t['source_page'])
  rows=m.m.rows_for(actual)if actual else [];universe=source['rows'][0]
  for leaf in universe:
   matches=[]
   for ri,row in enumerate(rows):
    for ci,text in enumerate(row):
     if m.m.label_key(text)==m.m.label_key(leaf):matches.append({'row':ri,'column':ci})
   headers.append({'source_page':t['source_page'],'table_id':t['table_id'],'expected_leaf':leaf,'status':'not_evaluated_page_unavailable'if not page else 'pass'if len(matches)==1 else 'missing_or_ambiguous_leaf','matches':matches})
 out['schema_version']='normal-continuation-score/1';out['source_only_rules_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest();out['wrapper_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();out['complete_repeated_header_leaves']={'passed':sum(v['status']=='pass'for v in headers),'evaluated':sum(not v['status'].startswith('not_evaluated')for v in headers),'checks':headers};out['scope']='Original same-header continuation pages6/7,33 own-page holder-row/column fields plus10 complete literal header leaves; no crosspage reconstruction or inferred period.'
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--result',required=True,type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args();out=score(json.loads(a.result.read_text()));p=a.output or a.result.with_name('normal-continuation-score.json');p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(p),'atomic':out['atomic_literal_summary'],'headers':out['complete_repeated_header_leaves']['passed']},ensure_ascii=False))
if __name__=='__main__':main()
