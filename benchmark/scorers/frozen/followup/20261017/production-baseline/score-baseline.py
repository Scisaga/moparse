"""Score actual public MD with frozen gold/scorers; no service/model changes.

Production has no coordinate/cell JSON endpoint. The frozen reader decodes only
visible GFM. Frozen scorers select tables by their existing nonnumeric-label
fallback, without fabricated boxes. Explicit logical-table row maps can be
projected to source pages in a separate judging view; public bytes stay intact.
"""
from pathlib import Path
from collections import Counter
import copy, hashlib, importlib.util, json, re

ROOT=Path(__file__).resolve().parent
OLD=Path('/opt/mosaic-parse/benchmark-results/clean-model-comparison-20261015')
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

reader=module('prod_frozen_reader',OLD/'http/common-export-v1.1/faithful-gfm.py')
core=module('prod_frozen_core',OLD/'scoring/score-result.py')
scope=module('prod_frozen_scope',OLD/'scoring/declared-scope-view.py')
calendar=module('prod_frozen_calendar',OLD/'scoring/calendar-date-review.py')
supplement=module('prod_frozen_supplement',OLD/'scoring/supplemental/score-supplemental.py')
source130=module('prod_frozen_130',OLD/'scoring/supplemental/score-source130.py')
source28=module('prod_frozen_28',OLD/'scoring/supplemental/score-source28.py')
continuation=module('prod_frozen_continuation',OLD/'scoring/supplemental/score-normal-continuation.py')
stock=module('prod_frozen_stock',OLD/'scoring/score-critical-keyvalue.py')
MANIFEST=json.loads((OLD/'input-manifest.json').read_text())

FRAGMENT=re.compile(r'<!-- table-fragment: ([^; ]+) -->')
LOGICAL=re.compile(r'<!-- logical-table: ([^; ]+); source-pages: ([0-9,]+) -->')
SOURCE=re.compile(r'<!-- table-source: ([^; ]+); source-page: (\d+); source-rows: ([^;]+); logical-rows: ([^;]+); repeated-header-rows: (\d+) -->')

def range_values(value):
    if value=='none':return []
    if '-' in value:
        a,b=map(int,value.split('-'));return list(range(a,b+1))
    return list(map(int,value.split(',')))

def public_metadata(page):
    metadata=[];pending={};in_table=False
    for line in page['markdown'].splitlines():
        f=FRAGMENT.fullmatch(line.strip());l=LOGICAL.fullmatch(line.strip());s=SOURCE.fullmatch(line.strip())
        if f:pending={'fragment':f[1]}
        if l:pending={'logical':l[1],'pages':list(map(int,l[2].split(','))),'sources':[]}
        if s and 'logical'in pending:
            pending['sources'].append({'fragment':s[1],'page':int(s[2]),'source_rows':range_values(s[3]),'logical_rows':range_values(s[4]),'skip':int(s[5])})
        if line.lstrip().startswith('|'):
            if not in_table:metadata.append(copy.deepcopy(pending));pending={}
            in_table=True
        else:in_table=False
    if len(metadata)!=len(page['tables']):raise ValueError('GFM table count differs from frozen reader')
    return metadata

def cells_from_rows(rows,page):
    return [{'row':ri,'column':ci,'row_span':1,'column_span':1,'text':v,
      'is_column_header':None,'is_row_header':None,'source_page':page}
      for ri,row in enumerate(rows)for ci,v in enumerate(row)if v]

def project_public_logical_tables(final):
    output=copy.deepcopy(final);by_page={p['page_number']:p for p in output['pages']};audit=[];additions=[]
    for page in output['pages']:
        kept=[]
        for table,meta in zip(page['tables'],public_metadata(page)):
            if 'fragment'in meta:table['table_id']=meta['fragment']
            if 'logical'not in meta:
                kept.append(table);continue
            rows=table['rows'];sources=meta['sources']
            try:
                if [s['page']for s in sources]!=meta['pages']:raise ValueError('Logical page list and source maps differ')
                mapped=[r for s in sources for r in s['logical_rows']]
                if mapped!=list(range(1,len(rows)+1)):raise ValueError('Row maps do not cover visible logical table exactly')
                for source in sources:
                    indices=source['logical_rows'];skip=source['skip']
                    if len(indices)!=len(source['source_rows']):raise ValueError('Source and logical row counts differ')
                    if skip<0 or skip>len(rows):raise ValueError('Invalid declared repeated-header count')
                    if source['page']not in by_page:raise ValueError('Referenced source page missing')
                for source in sources:
                    indices=source['logical_rows'];skip=source['skip']
                    selected=copy.deepcopy(rows[:skip]+[rows[i-1]for i in indices])
                    projected=copy.deepcopy(table)
                    projected.update(table_id=source['fragment'],source_pages=[source['page']],rows=selected,
                      cells=cells_from_rows(selected,source['page']),header_rows=None,
                      logical_table_id=meta['logical'],source_projection=source,
                      judging_only_projection='Explicit public source/logical row map and repeated-header count; no gold or hidden raw cells')
                    additions.append((source['page'],projected))
                    audit.append({'logical':meta['logical'],'declared_source':source,'visible_body_row_indices':indices,
                                  'visible_header_row_indices_reused':list(range(1,skip+1))})
            except ValueError as e:
                kept.append(table);audit.append({'logical':meta['logical'],'status':'unknown_invalid_public_provenance','error':str(e)})
        page['tables']=kept
    for pn,table in additions:by_page[pn]['tables'].append(table)
    output['public_logical_projection']={'audit':audit,'public_output_changed':False,'gold_text_or_values_used':False,
      'table_geometry_invented':False,'span_or_header_roles_invented':False}
    return output

def score_view(view):
    scoped=scope.make_view(view)
    raw_core=core.score(view)
    final_core=scope.apply_core_unknowns(core.score(scoped),scoped)
    calendar_view,calendar_core=calendar.compare(scoped,core,scope)
    result={'core':final_core,'core_literal':raw_core,'core_calendar':calendar_core,
            'stock':stock.score(view),'supplements':{}}
    for name,mod in [('supplement402',supplement),('source130',source130),('source28',source28),('normal33',continuation)]:
        literal=mod.score(view)
        reviewed=calendar.compare_supplement(scoped,mod,scope)
        result['supplements'][name]={'literal':literal,'scope_calendar':reviewed['calendar_equivalent_report'],
                                    'calendar_changes':reviewed['changed_checks']}
        if name=='normal33':result['normal_header_leaves']=literal['complete_repeated_header_leaves']
    return result

def main():
    summaries=[]
    for case in sorted((ROOT/'cases').iterdir()):
        if not(case/'result.md').exists():continue
        if not(case/'summary.json').exists():continue
        metadata=json.loads((case/'summary.json').read_text())
        if metadata.get('status')not in {'completed','partial'}:continue
        source=next(d for d in MANIFEST['documents']if Path(d['path']).stem==case.name)
        original_sha=sha(case/'result.md')
        warnings=json.loads((case/'warnings.json').read_text())if(case/'warnings.json').exists()else{}
        statuses={p['unit_index']:p['status']for p in warnings.get('units',[])}
        template={'run_id':'production-baseline-20261017','config_id':'live-production-complete',
          'source':{k:source[k]for k in ['path','sha256','page_count']},'status':metadata['status'],
          'pages':[{'page_number':pn,'status':'completed'if statuses.get(pn,'completed')in {'completed','warning'}else statuses.get(pn),
                    'production_page_status':statuses.get(pn,'completed'),'tables':[]}
                   for pn in range(1,source['page_count']+1)]}
        final,issues=reader.parse_final((case/'result.md').read_text(),template)
        final['actual_HTTP_MD_path']=str(case/'result.md');final['actual_HTTP_MD_SHA256']=original_sha
        projected=project_public_logical_tables(final)
        save(case/'received-MD-literal-view.json',final);save(case/'received-MD-logical-provenance-view.json',projected)
        result=score_view(projected);save(case/'frozen-scores.json',result)
        c=result['core'];sel=c['selected_source_scopes']
        row={'source':case.name,'job':metadata['job'],'status':metadata['status'],'MD_SHA256':original_sha,
          'pages_recorded':len(final['pages']),'pages_expected':source['page_count'],'parse_issues':issues,
          'core_numeric':c['gold_numeric_bindings']['counts'],
          'core_period':result['core_calendar']['calendar_equivalent_source_period_summary'],
          'financial30':sel['financial_complete_30_source_values']['counts'],
          'funding31':sel['funding_31_source_nonempty_cells']['counts'],
          'funding7_bound':sel['funding_7_year_type_amount_rows']['complete_leaf_bound_rows'],
          'stock':result['stock'],'normal_header_leaves':result['normal_header_leaves'],
          'public_logical_projection':projected['public_logical_projection'],
          'supplements':{k:{'literal':v['literal']['atomic_literal_summary'],'scope_calendar':v['scope_calendar']['atomic_literal_summary']}for k,v in result['supplements'].items()}}
        save(case/'score-summary.json',row);summaries.append(row)
        assert sha(case/'result.md')==original_sha,'Actual result changed'
    aggregate={'cases_scored':len(summaries),'pages_scored':sum(r['pages_recorded']for r in summaries),
      'core_numeric':dict(sum((Counter(r['core_numeric'])for r in summaries),Counter())),
      'core_period_pass':sum(r['core_period']['passed']for r in summaries),
      'financial30':dict(sum((Counter(r['financial30'])for r in summaries),Counter())),
      'funding31':dict(sum((Counter(r['funding31'])for r in summaries),Counter())),
      'funding7_bound':sum(r['funding7_bound']for r in summaries),
      'stock':[{'source':r['source'],'status':r['stock']['status']}for r in summaries if r['stock']],
      'supplements':{},'cases':summaries,
      'method':'Frozen gold/scorers and frozen GFM reader; public logical source-row decoding only. No hidden table text/coordinates or model invocation.',
      'scorer_files':[{'path':m.__file__,'SHA256':sha(m.__file__)}for m in [reader,core,scope,calendar,supplement,source130,source28,continuation,stock]],
      'adapter_SHA256':sha(__file__)}
    for name in ['supplement402','source130','source28','normal33']:
        aggregate['supplements'][name]={mode:{key:sum(r['supplements'][name][mode][key]for r in summaries)
          for key in ['literal_and_unique_row_pass','literal_row_and_complete_header_pass','target_count']}
          for mode in ['literal','scope_calendar']}
    save(ROOT/'score-summary.json',aggregate)
    print(json.dumps({k:v for k,v in aggregate.items()if k not in ['cases','scorer_files']},ensure_ascii=False))

if __name__=='__main__':main()
