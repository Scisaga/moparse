"""Independent complex source-table review; core209 scorer is unchanged."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
CORE=HERE.parent
REPO=CORE.parents[2]
spec=importlib.util.spec_from_file_location('fixed_core',CORE/'score-result.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
TARGETS=json.loads((HERE/'source-only-tables.json').read_text())


def path_evidence(table,row,column,expected,universe):
    cells=table.get('cells',[])
    if not cells:cells=[{'row':ri,'column':ci,'text':v}for ri,r in enumerate(m.rows_for(table))for ci,v in enumerate(r)]
    wanted=[m.label_key(v)for v in expected if m.compact(v)]
    known={m.label_key(v)for v in universe if m.compact(v)}
    known.update(''.join(wanted[start:end])for start in range(len(wanted))for end in range(start+2,len(wanted)+1))
    observed=[];declared=[]
    for c in sorted(cells,key=lambda c:(c['row'],c['column'])):
        if c['row']>=row or not c['column']<=column<c['column']+c.get('column_span',1):continue
        text=m.label_key(c['text'])
        if c.get('is_column_header') is True and text:declared.append(text)
        if text in known:observed.append(text)
    flat=''.join(observed)
    return {'source_path':expected,'observed_literal_path':observed,'declared_model_header_path':declared,
            'complete_path_pass':bool(wanted)and flat==''.join(wanted),
            'status':'pass'if wanted and flat==''.join(wanted)else 'unknown_no_complete_source_header_literal'if not observed else 'incomplete_or_conflicting_source_header_path'}


def row_scope_keys(table,rows,ri):
    # Literal rowspan ownership is necessary decoding, not text recovery.
    keys={m.row_key(v)for v in rows[ri]}
    keys.update(m.row_key(c['text'])for c in table.get('cells',[])if c['row']<=ri<c['row']+c.get('row_span',1)and m.compact(c['text']))
    return keys

def non_answer_selection_source(source):
    # Units, dates, status text and compound descriptions can contain answers
    # even when the core numeric regex returns False. Fallback selection may
    # use only source row identities and column-header paths, never values.
    labels={text for rule in source['values']for text in rule['source_row_labels']}
    labels.update(text for path in source['source_header_paths'].values()for text in path)
    labels.update(scope[key]for rule in source['values']if(scope:=rule.get('source_row_scope'))for key in ('parent_before','until_next_parent')if key in scope)
    return {'source_page':source['source_page'],'source_bbox':source.get('source_bbox'),
            'source_page_size':source.get('source_page_size'),'cells':[{'text':text}for text in sorted(labels)]}


def score(result):
    primary=m.score(result)
    notapp=primary['coverage']['not_applicable_pages']
    pages={p['page_number']:p for p in result['pages']if p['status']=='completed'and p['page_number']not in notapp}
    tables=[]
    for source in TARGETS['tables']:
        if source['source_sha256']!=result['source']['sha256']:continue
        page=pages.get(source['source_page']);table,candidates,method=m.select_source_table(non_answer_selection_source(source),page,REPO/Path(source['document']))
        record={'source_document':source['document'],'source_page':source['source_page'],'source_ordinal':source['source_ordinal'],
                'table_detected':bool(table),'table_id':table[1]['table_id']if table else None,'selection_method':method,'selection_fallback_uses_only_source_row_labels_and_header_paths':True,'values':[]}
        if table:
            rawtable,rows=table[1:];record['raw_shape']=[len(rows),max(map(len,rows),default=0)]
            record['strict_matrix_diagnostic_only']=m.same_matrix(source['rows'],rows)
        universe=[v for path in source['source_header_paths'].values()for v in path]
        for rule in source['values']:
            expected=rule['source_cell']['text'];labels=[v for v in rule['source_row_labels']if m.compact(v)not in {'','-','--','—'}]
            matchedrows=[]
            if table:
                for ri,row in enumerate(rows):
                    keys=row_scope_keys(rawtable,rows,ri)
                    if labels and all(m.row_key(label)in keys for label in labels):matchedrows.append((ri,row))
            scope=rule.get('source_row_scope');scope_evidence=None
            if scope and table:
                parents=[ri for ri in range(len(rows))if m.row_key(scope['parent_before'])in row_scope_keys(rawtable,rows,ri)]
                until=[ri for ri in range(len(rows))if m.row_key(scope['until_next_parent'])in row_scope_keys(rawtable,rows,ri)]
                valid=len(parents)==1 and len(until)==1 and parents[0]<until[0]
                scope_evidence={'parent_rows':parents,'until_rows':until,'source_parent_scope_confirmed':valid}
                matchedrows=[(ri,row)for ri,row in matchedrows if valid and parents[0]<ri<until[0]]
            matches=[]
            for ri,row in matchedrows:
                for ci,text in enumerate(row):
                    equal=m.equivalent_number(expected,text)if m.numeric(expected)else m.label_key(expected)==m.label_key(text)
                    if equal:
                        matches.append({'row':ri,'column':ci,'text':text,'header_evidence':path_evidence(rawtable,ri,ci,rule['source_header_path'],universe)})
            good=[c for c in matches if c['header_evidence']['complete_path_pass']]
            atomic=rule['source_numeric_is_complete_atomic_value']
            unavailable='not_evaluated_not_applicable'if source['source_page']in notapp else 'not_evaluated_page_unavailable'
            # Matching a value in one of several identical row-label contexts
            # does not resolve row meaning. Keep the ambiguity explicit.
            value_ok=len(matchedrows)==1 and bool(matches)
            header_ok=len(matchedrows)==1 and len(good)==1
            status=unavailable if page is None else 'missing_table'if table is None else 'ambiguous_or_missing_labeled_row'if len(matchedrows)!=1 else 'pass'if matches else 'value_mismatch_or_missing'
            record['values'].append({'source_cell':rule['source_cell'],'source_row_labels':labels,'source_header_path':rule['source_header_path'],'source_row_scope':scope,'observed_parent_scope':scope_evidence,
                 'source_complete_atomic_literal':atomic,'source_broken_fragment_evidence':rule['source_broken_crosspage_fragment_evidence'],
                 'external_original_header':rule['external_original_header'],'matched_row_indices':[r for r,_ in matchedrows],
                 'candidate_exact_literal_cells_in_labeled_row':matches,'status':status,'literal_and_unique_row_pass':value_ok,
                 'literal_row_and_complete_header_pass':header_ok,'is_crosspage_reconstructed_full_amount':False if not atomic else None})
        tables.append(record)
    atomic=[v for t in tables for v in t['values']if v['source_complete_atomic_literal']]
    fragments=[v for t in tables for v in t['values']if not v['source_complete_atomic_literal']]
    return {'schema_version':'clean-supplemental-score/1.2','run_id':result['run_id'],'config_id':result['config_id'],'source':result['source'],
            'core_scorer_sha256':hashlib.sha256((CORE/'score-result.py').read_bytes()).hexdigest(),
            'supplement_scorer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_only_rules_sha256':hashlib.sha256((HERE/'source-only-tables.json').read_bytes()).hexdigest(),
            'atomic_literal_summary':{'counts':dict(Counter(v['status']for v in atomic)),'literal_and_unique_row_pass':sum(v['literal_and_unique_row_pass']for v in atomic),
              'literal_row_and_complete_header_pass':sum(v['literal_row_and_complete_header_pass']for v in atomic),'target_count':len(atomic)},
            'source_fragment_summary':{'counts':dict(Counter(v['status']for v in fragments)),'target_count':len(fragments),
                'not_a_complete_amount_accuracy_denominator':True,'reconstruction_not_inferred':True},
            'tables':tables,'scope':'35 original-confirmed complex tables plus original bank continuation; source-only fixed annotations; no old actual outputs used as oracle; not combined with209gold.'}


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--result',required=True,type=Path);ap.add_argument('--output',type=Path);args=ap.parse_args()
 result=json.loads(args.result.read_text());report=score(result);report['input_result']=str(args.result);report['input_result_sha256']=hashlib.sha256(args.result.read_bytes()).hexdigest()
 out=args.output or args.result.with_name('supplemental-score.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'score':str(out),'config_id':report['config_id'],'atomic':report['atomic_literal_summary'],'fragments':report['source_fragment_summary']},ensure_ascii=False))

if __name__=='__main__':main()
