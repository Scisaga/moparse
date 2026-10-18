"""Decode explicit valid cell scope for judging, never for public output.

No source answers, domain names, digit repair or guessed header roles are used.
Original literal cells stay intact. A scoped value is copied only from its
already declared raw cell owner into empty covered positions.
"""
from __future__ import annotations
import copy,hashlib,html,json,re
from pathlib import Path
H=Path(__file__).resolve().parent
LOADED_SCRIPT_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
def compact(value):return re.sub(r'\s+','',str(value or ''))
def cells_for_scope(table):
 cells=copy.deepcopy(table.get('cells',[]))
 for r,c,rs,cs in table.get('declared_scope_final_span_metadata',[]):
  indices=[i for i,v in enumerate(cells)if v['row']==r and v['column']==c]
  if len(indices)==1:cells[indices[0]].update(row_span=rs,column_span=cs)
  elif not indices and 0<=r<len(table.get('rows',[]))and 0<=c<len(table['rows'][r]):
   cells.append({'row':r,'column':c,'row_span':rs,'column_span':cs,'text':table['rows'][r][c]})
 return cells
def make_view(result):
 out=copy.deepcopy(result);audit=[]
 for page in out['pages']:
  metadata={}
  if out.get('representation')=='independently_parsed_final_gfm':
   for match in re.finditer(r'<!-- clean-table: (.*?) -->',page.get('markdown','')):
    item=json.loads(match.group(1));metadata[item['table_id']]=item
  for table in page.get('tables',[]):
   original=table.get('rows')
   if original is None:continue
   rows=copy.deepcopy(original);height=len(rows);width=max(map(len,rows),default=0);owners={};bad=[]
   if table['table_id']in metadata:
    table['declared_scope_final_span_metadata']=copy.deepcopy(metadata[table['table_id']].get('spans',[]))
    audit.append({'kind':'final_declared_spans_read_from_public_markdown','page':page['page_number'],'table_id':table['table_id'],'span_count':len(table['declared_scope_final_span_metadata']),'model_text_copied_from_raw':False})
   cells=cells_for_scope(table)
   for index,c in enumerate(cells):
    if not compact(c.get('text')):continue
    r,c0=c['row'],c['column'];rs,cs=c.get('row_span',1),c.get('column_span',1)
    if rs<1 or cs<1 or r<0 or c0<0 or r+rs>height or c0+cs>width:
     bad.append({'kind':'unknown_out_of_bounds_span','cell_index':index,'anchor':[r,c0],'span':[rs,cs]});continue
    for ri in range(r,r+rs):
     for ci in range(c0,c0+cs):owners.setdefault((ri,ci),[]).append((index,c))
   invalid=set();unknown=set()
   for position,entries in owners.items():
    values={compact(c['text'])for _,c in entries};ri,ci=position;existing=rows[ri][ci]if ci<len(rows[ri])else ''
    if len(values)>1 or existing and compact(existing)not in values:
     invalid.update(i for i,_ in entries);unknown.add(position)
     bad.append({'kind':'unknown_conflicting_cell_owners','position':[ri,ci],'cell_indices':[i for i,_ in entries]})
   for index,c in enumerate(cells):
    rs,cs=c.get('row_span',1),c.get('column_span',1)
    if not compact(c.get('text'))or rs*cs==1:continue
    r,c0=c['row'],c['column'];positions=[(ri,ci)for ri in range(max(0,r),min(height,r+rs))for ci in range(max(0,c0),min(width,c0+cs))]
    if index in invalid:
     unknown.update(positions);bad.append({'kind':'unknown_conflicting_span','cell_index':index,'anchor':[r,c0],'span':[rs,cs]});continue
    if r<0 or c0<0 or rs<1 or cs<1 or r+rs>height or c0+cs>width:
     unknown.update(positions);continue
    inserted=[]
    for ri,ci in positions:
     while len(rows[ri])<width:rows[ri].append('')
     if not compact(rows[ri][ci]):rows[ri][ci]=c['text'];inserted.append([ri,ci])
    if inserted:audit.append({'kind':'explicit_valid_span_ownership','page':page['page_number'],'table_id':table['table_id'],'cell_index':index,'anchor':[r,c0],'span':[rs,cs],'literal':c['text'],'owned_positions':inserted})
   if rows!=original:table['rows']=rows
   if bad:audit.append({'kind':'unknown_span_scope','page':page['page_number'],'table_id':table['table_id'],'issues':bad,'unknown_positions':[list(p)for p in sorted(unknown)]})
 out['declared_scope_view']={'schema_version':'declared-cell-scope-view/1','script_sha256':LOADED_SCRIPT_SHA256,'audit':audit,'source_answers_used':False,'public_markdown_changed':False,'raw_cells_unchanged':True,'note':'Scope-aware judging view only. Literal occurrence/anchor counts and public Markdown retain original model output.'}
 assert [[t.get('cells')for t in p.get('tables',[])]for p in result['pages']]==[[t.get('cells')for t in p.get('tables',[])]for p in out['pages']]
 return out
def unknown_positions(view):return {(v['page'],v['table_id']):{tuple(p)for p in v['unknown_positions']}for v in view['declared_scope_view']['audit']if v['kind']=='unknown_span_scope'}
def evidence_key(value):
 return compact(re.sub(r'<br\s*/?>','',html.unescape(str(value or '')),flags=re.I)).translate(str.maketrans('（）／％','()/%'))
def scope_index(view):
 return unknown_positions(view),{(p['page_number'],t['table_id']):{**t,'cells':cells_for_scope(t)}for p in view['pages']for t in p.get('tables',[])}
def scope_conflicts(view,page,table_id,row,column,labels=None,header_path=None,index=None):
 if row is None:return False
 index=index or scope_index(view);positions=index[0].get((page,table_id),set())
 if not positions:return False
 table=index[1].get((page,table_id))
 if table is None:return False
 labels={evidence_key(v).replace('(','').replace(')','')for v in labels or []if evidence_key(v)};headers={evidence_key(v)for v in header_path or []if evidence_key(v)}
 for cell in table.get('cells',[]):
  text=evidence_key(cell.get('text'));r,c=cell['row'],cell['column'];rs,cs=cell.get('row_span',1),cell.get('column_span',1)
  affected={(ri,ci)for ri,ci in positions if r<=ri<r+rs and c<=ci<c+cs}
  if not affected:continue
  if labels and r<=row<r+rs and text.replace('(','').replace(')','')in labels:return True
  if headers and r<row and c<=column<c+cs and (text in headers or cell.get('is_column_header')is True):return True
 return False
def apply_core_unknowns(report,view):
 index=scope_index(view);unknown=index[0]
 for c in report['gold_numeric_bindings']['checks']:
  value_unknown=(c.get('row'),c.get('column'))in unknown.get((c['page'],c.get('table_id')),set())
  row_unknown=scope_conflicts(view,c['page'],c.get('table_id'),c.get('row'),c.get('column'),labels=[c['row_label']],index=index)
  header_unknown=scope_conflicts(view,c['page'],c.get('table_id'),c.get('row'),c.get('column'),header_path=c.get('source_period_text_path')or c.get('header_path'),index=index)
  if value_unknown or row_unknown:c['status']='unknown_conflicting_declared_cell_scope'
  if value_unknown or row_unknown or header_unknown:
   c['binding_and_source_period_pass']=False;c['binding_and_period_pass']=False
  if header_unknown:
   c['literal_source_period_header_match']=c['source_period_header_match'];c['source_period_header_match']=None
   c['literal_period_header_match']=c['period_header_match'];c['period_header_match']=None;c['header_scope_status']='unknown_conflicting_declared_cell_scope'
 from collections import Counter
 checks=report['gold_numeric_bindings']['checks'];report['gold_numeric_bindings']['counts']=dict(Counter(c['status']for c in checks))
 for name,binding,period in [('gold_source_text_header_bindings','binding_and_source_period_pass','source_period_header_match'),('gold_header_bound_numeric_bindings','binding_and_period_pass','period_header_match')]:
  report[name]={'passed':sum(c[binding]for c in checks),'period_confirmed':sum(c.get(period)is True for c in checks),'period_mismatch':sum(c.get(period)is False for c in checks),'period_unknown':sum(c.get(period)is None and not c['status'].startswith('not_evaluated')for c in checks)}
 return report
def apply_supplement_unknowns(report,view):
 index=scope_index(view);unknown=index[0]
 for table in report['tables']:
  positions=unknown.get((table['source_page'],table.get('table_id')),set())
  for v in table['values']:
   matches=v['candidate_exact_literal_cells_in_labeled_row'];valid=[]
   for c in matches:
    row_unknown=scope_conflicts(view,table['source_page'],table.get('table_id'),c['row'],c['column'],labels=v['source_row_labels'],index=index)
    if(c['row'],c['column'])in positions or row_unknown:continue
    valid.append(c)
    if scope_conflicts(view,table['source_page'],table.get('table_id'),c['row'],c['column'],header_path=c['header_evidence']['observed_literal_path'],index=index):
     c['header_evidence']['literal_complete_path_pass']=c['header_evidence']['complete_path_pass'];c['header_evidence']['complete_path_pass']=False;c['header_evidence']['scope_status']='unknown_conflicting_declared_cell_scope'
   if v['literal_row_and_complete_header_pass']and not any(c['header_evidence']['complete_path_pass']for c in valid):
    v['literal_row_and_complete_header_pass']=False;v['scope_header_status']='unknown_conflicting_declared_cell_scope'
   if matches and not valid:
    v['status']='unknown_conflicting_declared_cell_scope';v['literal_and_unique_row_pass']=False;v['literal_row_and_complete_header_pass']=False
 from collections import Counter
 vals=[v for t in report['tables']for v in t['values']if v['source_complete_atomic_literal']]
 report['atomic_literal_summary']={'counts':dict(Counter(v['status']for v in vals)),'literal_and_unique_row_pass':sum(v['literal_and_unique_row_pass']for v in vals),'literal_row_and_complete_header_pass':sum(v['literal_row_and_complete_header_pass']for v in vals),'target_count':len(vals)}
 return report
