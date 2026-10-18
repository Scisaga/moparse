"""Source-bound scalar field; no whole-document digit matching or text repair."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,re
from pathlib import Path
H=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('core_keyvalue',H/'score-result.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);P=H/'critical-shareholder-source.json';SOURCE=json.loads(P.read_text())
def score(result):
 if result['source']['sha256']!=SOURCE['source_sha256']:return None
 primary=m.score(result);pn=SOURCE['source_page'];page=next((p for p in result['pages']if p['page_number']==pn and p['status']=='completed'),None)
 source={'source_page':SOURCE['source_page'],'source_bbox':SOURCE['source_bbox'],'source_page_size':SOURCE['source_page_size'],'rows':SOURCE['source_rows'],'cells':SOURCE['source_cells']}
 table,_,method=m.select_source_table(source,page,m.REPO/Path(SOURCE['source_document']))
 expected=m.compact(SOURCE['source_value']).replace(',','');key=m.row_key(SOURCE['key']);matches=[];candidates=[]
 if table:
  for ri,row in enumerate(table[2]):
   keys=[m.row_key(v)for v in row]
   labelcells=[i for i,k in enumerate(keys)if k==key or k.startswith(key)]
   if len(labelcells)!=1:continue
   ci=labelcells[0];labeltext=m.row_key(row[ci]);suffix=labeltext[len(key):]
   anchors=[c for c in table[1].get('cells',[])if c['row']==ri and c['column']==ci]
   span=anchors[0].get('column_span',1)if len(anchors)==1 else 1
   adjacent_column=ci+span;adjacent=row[adjacent_column]if adjacent_column<len(row)else ''
   candidates.append({'row':ri,'label_cell_text':row[ci],'declared_key_column_span':span,'adjacent_column':adjacent_column,'adjacent_cell_text':adjacent,'embedded_suffix':suffix})
   # A whole scalar must be either the exact suffix of its own key cell or
   # the adjacent cell. Digits elsewhere in the table cannot rescue it.
   if (suffix and m.compact(suffix).replace(',','')==expected)or(not suffix and m.compact(adjacent).replace(',','')==expected):matches.append(ri)
 unavailable=pn in primary['coverage']['not_applicable_pages']or page is None
 status='not_evaluated_page_unavailable'if unavailable else 'pass'if len(candidates)==1 and len(matches)==1 else 'mismatch_or_ambiguous'
 return {'schema_version':'critical-keyvalue-score/1','run_id':result['run_id'],'config_id':result['config_id'],'source':result['source'],'source_page':pn,'expected_key':SOURCE['key'],'expected_value':SOURCE['source_value'],'quantity_kind':SOURCE['quantity_kind'],'table_id':table[1]['table_id']if table else None,'selection_method':method,'candidates':candidates,'status':status,'source_contract_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'scorer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'no_digit_borrowing_from_other_rows':True}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);ap.add_argument('--output',type=Path);a=ap.parse_args();out=score(json.loads(a.result.read_text()));p=a.output or a.result.with_name('critical-keyvalue-score.json');p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(p),'status':out['status']if out else None},ensure_ascii=False))
if __name__=='__main__':main()
