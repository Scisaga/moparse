"""Strict whole-cell calendar equivalence, judging copy only.

Apply AFTER frozen declared-scope evaluation so equivalent typography cannot
erase any original conflicting span. Public/raw outputs and gold never change.
"""
from __future__ import annotations
import copy,datetime,hashlib,re,unicodedata
from pathlib import Path
LOADED_SCRIPT_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
CHINESE=re.compile(r'([0-9]{4})\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日')
PUNCTUATION=re.compile(r'([0-9]{4})\s*[./-]\s*([0-9]{1,2})\s*[./-]\s*([0-9]{1,2})')
def canonical_date(literal):
 if not isinstance(literal,str):return None
 text=unicodedata.normalize('NFKC',literal).strip();match=CHINESE.fullmatch(text)or PUNCTUATION.fullmatch(text)
 if not match:return None
 try:return datetime.date(*(int(v)for v in match.groups())).isoformat()
 except ValueError:return None
def make_view(scoped):
 if 'declared_scope_view'not in scoped:raise ValueError('Compute frozen scope on original literal cells before calendar review')
 out=copy.deepcopy(scoped);changes=[];accepted=[]
 for page in out['pages']:
  for table in page.get('tables',[]):
   for index,cell in enumerate(table.get('cells',[])):
    literal=cell.get('text');canonical=canonical_date(literal)
    if canonical is None:continue
    record={'page':page['page_number'],'table_id':table['table_id'],'representation':'explicit_literal_cell','cell_index':index,'row':cell['row'],'column':cell['column'],'literal':literal,'canonical_iso':canonical,'changed':literal!=canonical};accepted.append(record)
    if literal!=canonical:cell['text']=canonical;changes.append(record)
   for ri,row in enumerate(table.get('rows',[])):
    for ci,literal in enumerate(row):
     canonical=canonical_date(literal)
     if canonical is None:continue
     record={'page':page['page_number'],'table_id':table['table_id'],'representation':'existing_scoped_grid_cell','row':ri,'column':ci,'literal':literal,'canonical_iso':canonical,'changed':literal!=canonical};accepted.append(record)
     if literal!=canonical:row[ci]=canonical;changes.append(record)
 assert out['declared_scope_view']==scoped['declared_scope_view'],'Original conflict audit changed'
 assert [p.get('markdown')for p in out['pages']]==[p.get('markdown')for p in scoped['pages']],'Public Markdown changed'
 assert out['source']==scoped['source']
 for oldpage,newpage in zip(scoped['pages'],out['pages']):
  assert {k:v for k,v in oldpage.items()if k!='tables'}=={k:v for k,v in newpage.items()if k!='tables'}
  for old,new in zip(oldpage.get('tables',[]),newpage.get('tables',[])):
   assert {k:v for k,v in old.items()if k not in ['rows','cells']}=={k:v for k,v in new.items()if k not in ['rows','cells']}
   assert len(old.get('rows',[]))==len(new.get('rows',[]))and [len(r)for r in old.get('rows',[])]==[len(r)for r in new.get('rows',[])]
   for a,b in zip(old.get('cells',[]),new.get('cells',[])):assert {k:v for k,v in a.items()if k!='text'}=={k:v for k,v in b.items()if k!='text'}
 out['calendar_date_review']={'schema_version':'whole-cell-calendar-equivalence/1','script_sha256':LOADED_SCRIPT_SHA256,'only_existing_complete_single_cell_dates':True,'source_answers_used':False,'indicator_or_amount_inference_used':False,'scope_computed_from_original_literals_before_normalization':True,'original_scope_conflict_audit_preserved':True,'not_for_rendering_or_public_output':True,'public_markdown_changed':False,'raw_files_or_gold_changed':False,'accepted_cells':accepted,'changed_cells':changes,'note':'Rows may already carry a valid explicitly declared span from the frozen scope view. This operation inserts no values or dates and changes no original scope decision. Nonmatching cells remain untouched.'}
 return out
def source_view(targets):
 """Apply the identical full-cell test only to source annotation text fields.

 No source file is written, no missing field is added, and source geometry,
 IDs, parent scopes, value completeness flags and all non-date text stay exact.
 """
 out=copy.deepcopy(targets);accepted=[]
 def text(value,path):
  canonical=canonical_date(value)
  if canonical is None:return value
  accepted.append({'path':path,'literal':value,'canonical_iso':canonical,'changed':value!=canonical})
  return canonical
 for ti,table in enumerate(out.get('tables',[])):
  prefix=f'tables[{ti}]'
  for ri,row in enumerate(table.get('rows',[])):
   for ci,literal in enumerate(row):row[ci]=text(literal,f'{prefix}.rows[{ri}][{ci}]')
  for ci,cell in enumerate(table.get('cells',[])):
   if 'text'in cell:cell['text']=text(cell['text'],f'{prefix}.cells[{ci}].text')
  for key,path in table.get('source_header_paths',{}).items():
   for i,literal in enumerate(path):path[i]=text(literal,f'{prefix}.source_header_paths[{key}][{i}]')
  for vi,value in enumerate(table.get('values',[])):
   vp=f'{prefix}.values[{vi}]'
   if 'text'in value.get('source_cell',{}):value['source_cell']['text']=text(value['source_cell']['text'],f'{vp}.source_cell.text')
   for field in ['source_row_labels','source_header_path']:
    for i,literal in enumerate(value.get(field,[])):value[field][i]=text(literal,f'{vp}.{field}[{i}]')
   for key,literal in (value.get('source_row_scope')or {}).items():
    if isinstance(literal,str):value['source_row_scope'][key]=text(literal,f'{vp}.source_row_scope.{key}')
 return out,accepted
def literal_input(result,scope):
 """Retain literal rows while carrying the original scope audit as provenance.

 Date-only value comparisons must not acquire the separate valid-span gains.
 The audit is computed first on original literals; none of its expanded rows
 or added table metadata are copied into this literal comparison input.
 """
 out=copy.deepcopy(result);audit=scope.make_view(result)['declared_scope_view']
 out['declared_scope_view']=copy.deepcopy(audit)
 out['calendar_literal_context']={'literal_rows_unexpanded':True,'original_scope_audit_retained_as_provenance_only':True,'scope_unknowns_not_applied_for_literal_value_axis':True}
 assert [t.get('rows')for p in out['pages']for t in p.get('tables',[])]==[t.get('rows')for p in result['pages']for t in p.get('tables',[])]
 assert [t.get('cells')for p in out['pages']for t in p.get('tables',[])]==[t.get('cells')for p in result['pages']for t in p.get('tables',[])]
 return out
def compare_supplement(input_scoped,module,scope,apply_scope_unknowns=True):
 """Use an isolated imported wrapper and restore every original target object."""
 view=make_view(input_scoped)
 scorer=module.m if hasattr(module,'m')and hasattr(module.m,'TARGETS')else module
 original=scorer.TARGETS
 # scan28's wrapper recreates TARGETS from ORIGINAL on each score; both handles
 # must point at the same canonical source COPY during this isolated invocation.
 original_wrapper=getattr(module,'ORIGINAL',None)
 canonical,source_audit=source_view(original_wrapper if original_wrapper is not None else original)
 try:
  before=module.score(input_scoped)
  if apply_scope_unknowns:before=scope.apply_supplement_unknowns(before,input_scoped)
  scorer.TARGETS=canonical
  if original_wrapper is not None:module.ORIGINAL=canonical
  after=module.score(view)
  if apply_scope_unknowns:after=scope.apply_supplement_unknowns(after,view)
 finally:
  scorer.TARGETS=original
  if original_wrapper is not None:module.ORIGINAL=original_wrapper
 assert scorer.TARGETS is original
 if original_wrapper is not None:assert module.ORIGINAL is original_wrapper
 # Amount/status/parent identities may not change; date literals are the only
 # source/output text difference allowed to change matching or its header path.
 assert [(t['source_page'],t['source_ordinal'],t['table_id'],t['selection_method'])for t in before['tables']]==[(t['source_page'],t['source_ordinal'],t['table_id'],t['selection_method'])for t in after['tables']],'Calendar review changed geometry/source-label table selection'
 differences=[]
 for bt,at in zip(before['tables'],after['tables']):
  for i,(b,a)in enumerate(zip(bt['values'],at['values'])):
   source=b['source_cell']['text']
   if canonical_date(source)is None:
    assert b['literal_and_unique_row_pass']==a['literal_and_unique_row_pass'],'Non-date source value changed'
    assert b['matched_row_indices']==a['matched_row_indices'],'Calendar review changed row identity for a non-date source value'
    assert [{k:v for k,v in c.items()if k!='header_evidence'}for c in b['candidate_exact_literal_cells_in_labeled_row']]==[{k:v for k,v in c.items()if k!='header_evidence'}for c in a['candidate_exact_literal_cells_in_labeled_row']],'Calendar review changed the actual non-date value or its physical position'
   if b['literal_and_unique_row_pass']!=a['literal_and_unique_row_pass']or b['literal_row_and_complete_header_pass']!=a['literal_row_and_complete_header_pass']:
    differences.append({'source_page':bt['source_page'],'source_ordinal':bt['source_ordinal'],'value_index':i,'source_cell_original':b['source_cell'],'source_cell_calendar_view':a['source_cell'],'source_header_path_original':b['source_header_path'],'source_header_path_calendar_view':a['source_header_path'],'literal_before':b['literal_and_unique_row_pass'],'literal_after':a['literal_and_unique_row_pass'],'complete_header_before':b['literal_row_and_complete_header_pass'],'complete_header_after':a['literal_row_and_complete_header_pass']})
 return {'schema_version':'calendar-source-supplement-review/1','comparison_basis':'original_scope_plus_calendar'if apply_scope_unknowns else'literal_date_only_without_span_expansion_or_scope_overlay','original_summary':before['atomic_literal_summary'],'calendar_equivalent_summary':after['atomic_literal_summary'],'original_report':before,'calendar_equivalent_report':after,'source_date_view_audit':source_audit,'output_date_view_audit':view['calendar_date_review'],'changed_checks':differences,'source_files_and_model_output_unchanged':True}
def numeric_projection(score):
 fields=['case_id','page','group','row_label','period','expected','actual','status','table_id','row','column']
 return [{key:c.get(key)for key in fields}for c in score['gold_numeric_bindings']['checks']]
def compare(input_scoped,core,scope):
 before=scope.apply_core_unknowns(core.score(input_scoped),input_scoped);view=make_view(input_scoped);after=scope.apply_core_unknowns(core.score(view),view)
 if numeric_projection(before)!=numeric_projection(after):raise AssertionError('Date review changed a numeric value, row/column match, or original scope status')
 return view,{'schema_version':'calendar-source-period-review/1','core_script_sha256':core.sha(Path(core.__file__))if hasattr(core,'sha')else hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest(),'scope_script_sha256':scope.LOADED_SCRIPT_SHA256,'calendar_review_script_sha256':LOADED_SCRIPT_SHA256,'numeric_values_and_binding_selection_unchanged':True,'original_source_period_summary':before['gold_source_text_header_bindings'],'calendar_equivalent_source_period_summary':after['gold_source_text_header_bindings'],'gold_numeric_bindings_before':before['gold_numeric_bindings'],'gold_numeric_bindings_calendar_review':after['gold_numeric_bindings'],'accepted_date_cells':view['calendar_date_review']['accepted_cells'],'changed_date_cells':view['calendar_date_review']['changed_cells'],'not_a_public_output_or_main_score_rewrite':True}
