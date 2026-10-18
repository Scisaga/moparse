"""Independent raw-cell scoring. No app imports, model calls or output repairs."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
GOLD = REPO / 'pdf_sample/gold/table_fact_gold_v1.json'
NUM = re.compile(r'\(?[+−-]?\d[\d,]*(?:\.\d+)?[%％]?\)?')


def compact(value):
    return re.sub(r'\s+', '', html.unescape(str(value or '')).replace('<br>', '').replace('<br/>', ''))


def label_key(value):
    # Pure punctuation typography, not missing words or business-name inference.
    return compact(value).translate(str.maketrans('（）／％', '()/%'))


def row_key(value):
    # A missing label bracket is a text-fidelity issue, not a missing amount.
    # The complete name and unit tokens must still match. Values never use this.
    return label_key(value).replace('(', '').replace(')', '')


def numeric(value):
    return bool(NUM.fullmatch(compact(value)))


def equivalent_number(left, right):
    # Ignore thousands separator typography only. Signs, precision, percent and
    # parentheses are retained: do not round, infer negatives or repair digits.
    return compact(left).replace(',', '') == compact(right).replace(',', '')


def rows_for(table):
    if 'rows' in table:
        return [[str(v or '') for v in row] for row in table['rows']]
    cells = table.get('cells', [])
    if not cells:
        return []
    height = max(c['row'] + c.get('row_span', 1) for c in cells)
    width = max(c['column'] + c.get('column_span', 1) for c in cells)
    rows = [[''] * width for _ in range(height)]
    for c in cells:
        if rows[c['row']][c['column']]:
            raise ValueError('Conflicting anchors; preserve raw invalid topology, do not choose one')
        rows[c['row']][c['column']] = c['text']
    return rows


def header_path(table, row, column):
    cells = table.get('cells', [])
    selected = [c for c in cells if c.get('is_column_header') is True and c['row'] < row
                and c['column'] <= column < c['column'] + c.get('column_span', 1)]
    declared = table.get('header_rows')
    if not selected and declared is not None:
        rows = rows_for(table)
        selected = [{'row': r, 'column': column, 'text': rows[r][column]}
                    for r in declared if r < row and r < len(rows) and column < len(rows[r])]
    values = [compact(c['text']) for c in sorted(selected, key=lambda c: (c['row'], c['column'])) if compact(c['text'])]
    return values or None


def period_matches(path, period):
    if path is None:
        return None
    if period == 'current_period':
        return path == ['本报告期']
    if period == 'prior_period':
        return path == ['上年同期']
    if period == 'change':
        return path == ['本报告期比上年同期增减(%)'] or path == ['本报告期比上年同期增减（%）']
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', period):
        y, m, d = period.split('-')
        valid = {period, f'{y}年{int(m)}月{int(d)}日', f'{y}/{int(m)}/{int(d)}'}
        # Do not accept a merged cell containing two opposing dates.
        return len(path) == 1 and path[0] in valid
    return None


def recognized_period_literal(text):
    value=compact(text)
    named={'本报告期':'current_period','上年同期':'prior_period','本报告期末':'current_period_end','上年度末':'prior_year_end',
           '本报告期比上年同期增减(%)':'change','本报告期比上年同期增减（%）':'change',
           '本报告期末比上年度末增减(%)':'end_change','本报告期末比上年度末增减（%）':'end_change'}
    if value in named:
        return named[value]
    match=re.fullmatch(r'(\d{4})(?:年|-|/)(\d{1,2})(?:月|-|/)(\d{1,2})日?',value)
    if match:
        y,month,day=map(int,match.groups())
        return f'{y:04d}-{month:02d}-{day:02d}'
    # A recognized unit/currency prefix does not erase the one complete date
    # physically anchored in this column. Retain the combined-cell issue as raw.
    dates=re.findall(r'(\d{4})(?:年|-|/)(\d{1,2})(?:月|-|/)(\d{1,2})日?',value)
    if len(dates)>1:
        return 'compound_periods'
    if len(dates)==1 and ('单位'in value or '币种'in value):
        y,month,day=map(int,dates[0])
        return f'{y:04d}-{month:02d}-{day:02d}'
    if '本报告期'in value and '上年同期'in value and '增减'not in value:
        return 'compound_periods'
    return None


def source_period_evidence(table,row,column,expected):
    """Score literal source-period ownership without guessing model header flags.

    This changes no output. A nearest complete period literal in the same raw
    physical column must precede the data row; a cell spanning opposing periods
    is a conflict. No indicator label, amount or business rule supplies a date.
    """
    cells=table.get('cells')
    if not cells:
        cells=[{'row':ri,'column':ci,'text':v}for ri,r in enumerate(rows_for(table))for ci,v in enumerate(r)]
    observed=[]
    for c in cells:
        if c['row'] >= row or not c['column'] <= column < c['column']+c.get('column_span',1):
            continue
        literal=recognized_period_literal(c['text'])
        if literal is not None:
            observed.append((c['row'],literal,compact(c['text'])))
    if not observed:
        return None,None
    latest=max(v[0]for v in observed)
    nearest=[v for v in observed if v[0]==latest]
    return [v[2]for v in nearest],len(nearest)==1 and nearest[0][1]==expected


def counts(checks, key='status'):
    return dict(Counter(c[key] for c in checks))


def same_matrix(left, right):
    return [[compact(v) for v in r] for r in left] == [[compact(v) for v in r] for r in right]


def select_source_table(expected,page,source_path):
    """Select original table by source geometry, then nonnumeric labels.

    Monetary answers never select a candidate. Geometry is scoring provenance,
    not a model correction; no raw table is changed.
    """
    if page is None:
        return None,[],'page_unavailable'
    size=expected.get('source_page_size')
    try:
        import pymupdf
        with pymupdf.open(source_path)as pdf:
            rect=pdf[expected['source_page']-1].rect
            size=(rect.width,rect.height)
    except (ImportError,OSError):
        pass
    bbox=expected.get('source_bbox')
    geometric=[]
    if size and bbox:
        width,height=size
        exp=[bbox[0]/width,bbox[1]/height,bbox[2]/width,bbox[3]/height]
        for table in page['tables']:
            raw=table.get('bbox')
            if not raw or len(raw)!=4:
                continue
            if table.get('bbox_coordinate_space')=='sdk_0_to_1000':
                obs=[v/1000 for v in raw]
            elif page.get('layout_width')and page.get('layout_height'):
                w,h=page['layout_width'],page['layout_height'];obs=[raw[0]/w,raw[1]/h,raw[2]/w,raw[3]/h]
            else:
                obs=[raw[0]/width,raw[1]/height,raw[2]/width,raw[3]/height]
            inter=max(0,min(exp[2],obs[2])-max(exp[0],obs[0]))*max(0,min(exp[3],obs[3])-max(exp[1],obs[1]))
            union=max(0,exp[2]-exp[0])*max(0,exp[3]-exp[1])+max(0,obs[2]-obs[0])*max(0,obs[3]-obs[1])-inter
            iou=inter/union if union else 0
            geometric.append((iou,table,rows_for(table)))
        geometric.sort(key=lambda x:x[0],reverse=True)
        if geometric and geometric[0][0]>=0.5 and(len(geometric)==1 or geometric[0][0]-geometric[1][0]>=0.1):
            return geometric[0],geometric,'source_bbox_iou'
    labels={label_key(c['text'])for c in expected['cells']if compact(c['text'])and not numeric(c['text'])}
    candidates=[]
    for table in page['tables']:
        rows=rows_for(table)
        overlap=len(labels&{label_key(v)for row in rows for v in row if compact(v)and not numeric(v)})
        if overlap:
            candidates.append((overlap,table,rows))
    candidates.sort(key=lambda x:x[0],reverse=True)
    if candidates and(len(candidates)==1 or candidates[0][0]>candidates[1][0]):
        return candidates[0],candidates,'source_nonnumeric_label_overlap'
    return None,candidates,'ambiguous_or_missing'


def source_table_checks(result, completed):
    source = json.loads((HERE / 'full-source-tables.json').read_text())['tables']
    checks = []
    for expected in source:
        if Path(expected['document']).name != Path(result['source']['path']).name:
            continue
        page_number = expected['source_page']
        if page_number not in completed:
            checks.append({'page': page_number, 'source_ordinal': expected['source_ordinal'], 'status': 'not_evaluated_page_unavailable'})
            continue
        page = completed[page_number]
        matched,candidates,method=select_source_table(expected,page,REPO/Path(result['source']['path']))
        record = {'page': page_number, 'source_ordinal': expected['source_ordinal'], 'source_bbox': expected['source_bbox'],
                  'status': 'matched' if matched else 'ambiguous_or_missing', 'matching_method':method,'candidate_source_match_scores':[c[0]for c in candidates]}
        if matched:
            _, table, actual = matched
            expcells = {(c['row'], c['column'], c.get('row_span', 1), c.get('column_span', 1), compact(c['text'])) for c in expected['cells']}
            actualcells = {(c['row'], c['column'], c.get('row_span', 1), c.get('column_span', 1), compact(c['text'])) for c in table.get('cells', [])}
            headers = [compact(v) for v in expected['rows'][0]]
            # Complete original first header row, not generic cell-count similarity.
            header_ok = bool(actual) and [compact(v) for v in actual[0]] == headers
            record.update(table_id=table['table_id'], strict_matrix_exact=same_matrix(expected['rows'], actual),
                          strict_cell_text_spans_exact=expcells == actualcells if actualcells else None,
                          complete_source_first_header_row_exact=header_ok,
                          source_page_association=page_number in table.get('source_pages', []),
                          expected_shape=[len(expected['rows']), max(map(len, expected['rows']))],
                          actual_shape=[len(actual), max(map(len, actual), default=0)])
        checks.append(record)
    return checks


def selected_scope_checks(result, completed):
    """Separate fixed original-table semantics; never added to the 209 gold."""
    source_tables = json.loads((HERE / 'full-source-tables.json').read_text())['tables']
    stem = Path(result['source']['path']).stem
    financial, funding, funding_bindings, units = [], [], [], []
    for source in source_tables:
        if Path(source['document']).stem != stem:
            continue
        pn = source['source_page']
        page = completed.get(pn)
        wanted_financial = stem == '1225474693' and (pn, source['source_ordinal']) in {(2, 3), (3, 1)}
        wanted_funding = stem == '1225473526' and (pn, source['source_ordinal']) == (7, 2)
        if not (wanted_financial or wanted_funding):
            continue
        matched,candidates,method=select_source_table(source,page,REPO/Path(result['source']['path']))
        if wanted_financial:
            for ri, source_row in enumerate(source['rows'][1:], 1):
                rowlabel = source_row[0]
                rows_matched = [(ar, ci, row) for ar, row in enumerate(matched[2]) for ci, v in enumerate(row)
                                if row_key(v) == row_key(rowlabel)] if matched else []
                raw = rows_matched[0] if len(rows_matched) == 1 else None
                for ci, expected in enumerate(source_row[1:], 1):
                    actual = raw[2][raw[1] + ci] if raw and raw[1] + ci < len(raw[2]) else None
                    path = header_path(matched[1], raw[0], raw[1] + ci) if raw else None
                    expected_header = compact(source['rows'][0][ci])
                    expected_period=recognized_period_literal(expected_header)
                    sourcepath,sourceperiod=source_period_evidence(matched[1],raw[0],raw[1]+ci,expected_period)if raw and expected_period else (None,None)
                    financial.append({'page':pn,'row_label':rowlabel,'expected_header':expected_header,
                        'expected':expected,'actual':actual,'status':'not_evaluated_page_unavailable' if page is None else 'pass' if actual is not None and equivalent_number(expected,actual) else 'mismatch',
                        'header_path':path,'complete_period_header_match':path == [expected_header] if path is not None else None,
                        'source_period_text_path':sourcepath,'source_complete_period_header_match':sourceperiod})
        if wanted_funding:
            # Evaluate original year/type/amount relationships independently
            # of empty-column compression or the omitted merged label.
            for sr in source['rows'][2:9]:
                year,typ,amount=sr[1:4]
                yearrows=[(ar,ci,row)for ar,row in enumerate(matched[2])for ci,v in enumerate(row)if label_key(v)==label_key(year)]if matched else []
                yr=yearrows[0]if len(yearrows)==1 else None
                actual_type=yr[2][yr[1]+1]if yr and yr[1]+1<len(yr[2])else None
                actual_amount=yr[2][yr[1]+2]if yr and yr[1]+2<len(yr[2])else None
                body_type_ok=actual_type is not None and label_key(actual_type)==label_key(typ)
                body_amount_ok=actual_amount is not None and equivalent_number(actual_amount,amount)
                expected_heads=['时间','发行类型','筹资净额']
                headchecks=[]
                if yr:
                    for off,head in enumerate(expected_heads):
                        matching_headers=[c for c in matched[1].get('cells',[])if c['row']<yr[0]and c['column']<=yr[1]+off<c['column']+c.get('column_span',1)and label_key(c['text'])==label_key(head)]
                        headchecks.append(bool(matching_headers))
                funding_bindings.append({'page':pn,'source_year':year,'source_issue_type':typ,'source_net_amount':amount,
                    'actual_issue_type':actual_type,'actual_net_amount':actual_amount,'unique_year_row':bool(yr),
                    'issue_type_match':body_type_ok,'amount_match':body_amount_ok,'complete_leaf_headers_match':headchecks,
                    'full_business_binding_pass':bool(yr)and body_type_ok and body_amount_ok and all(headchecks),
                    'status':'not_evaluated_page_unavailable'if page is None else 'pass'if body_type_ok and body_amount_ok else 'row_type_or_amount_mismatch'})
            # A whole source cell must remain a whole observed anchor cell.
            # Position/span matches are diagnostics; values are not borrowed from other tables.
            sourcecells = [c for c in source['cells'] if compact(c['text'])]
            observed = matched[1].get('cells',[]) if matched else []
            observed_exact=Counter(compact(c['text'])for c in observed if compact(c['text']))
            observed_text = Counter(label_key(c['text']) for c in observed if compact(c['text']))
            if matched and not observed:
                observed_exact=Counter(compact(v)for row in matched[2]for v in row if compact(v))
                observed_text = Counter(label_key(v) for row in matched[2] for v in row if compact(v))
            for c in sourcecells:
                text = label_key(c['text'])
                exact = observed_exact[compact(c['text'])]>0
                present = observed_text[text] > 0
                if present:
                    observed_text[text] -= 1
                funding.append({'page':pn,'source_row':c['row'],'source_column':c['column'],'expected':c['text'],
                                'status':'not_evaluated_page_unavailable' if page is None else 'pass' if present else 'missing_or_split_cell',
                                'source_table_detected':bool(matched),'table_id':matched[1]['table_id']if matched else None,'matching_method':method,
                                'exact_cell_text':exact,'whole_cell_typography_equivalent':present and not exact,
                                'same_anchor_position':any(o['row']==c['row'] and o['column']==c['column'] and label_key(o['text'])==text for o in observed),
                                'same_anchor_span':any(o['row']==c['row'] and o['column']==c['column'] and o.get('row_span',1)==c.get('row_span',1) and o.get('column_span',1)==c.get('column_span',1) and label_key(o['text'])==text for o in observed)})
            page_md = page.get('markdown','') if page else ''
            ownunit = matched[1].get('unit_text') if matched else None
            units.append({'page':pn,'table':'funding','expected':'万元','table_associated':ownunit is not None and '万元' in compact(ownunit),
                          'present_on_same_page': '单位：万元' in compact(page_md) or '单位:万元' in compact(page_md),
                          'association_status':'not_evaluated_page_unavailable' if page is None else 'confirmed' if ownunit and '万元' in compact(ownunit) else 'unknown'})
    if stem == '1225474693':
        page = completed.get(3)
        for name in ('基本每股收益','稀释每股收益'):
            matches = [(t,v) for t in page['tables'] for row in rows_for(t) for v in row if compact(v).startswith(name)] if page else []
            units.append({'page':3,'table':'financial','row_label':name,'expected':'元／股',
                          'actual_labels':[v for _,v in matches],
                          'row_associated':len(matches)==1 and ('元／股' in compact(matches[0][1]) or '元/股' in compact(matches[0][1])),
                          'unit_text_exact':len(matches)==1 and '元／股' in compact(matches[0][1]),
                          'association_status':'not_evaluated_page_unavailable' if page is None else 'confirmed' if len(matches)==1 and ('元／股' in compact(matches[0][1]) or '元/股' in compact(matches[0][1])) else 'missing_or_ambiguous'})
    return {'financial_complete_30_source_values':{'counts':counts(financial),'checks':financial},
            'funding_31_source_nonempty_cells':{'counts':counts(funding),'checks':funding},
            'funding_7_year_type_amount_rows':{'counts':counts(funding_bindings),'complete_leaf_bound_rows':sum(c['full_business_binding_pass']for c in funding_bindings),'checks':funding_bindings},'units':units}


def score(result, allow_diagnostic=False):
    manifest = json.loads((HERE / 'source-manifest.json').read_text())
    src = result['source']
    target = [d for d in manifest['documents'] if Path(d['path']).name == Path(src['path']).name]
    if len(target) != 1 or target[0]['sha256'] != src['sha256']:
        raise ValueError('Unknown source or SHA mismatch: refusing to score a different PDF')
    diagnostic = src.get('scope') == 'fixed_diagnostic_excerpt' or result.get('selection',{}).get('diagnostic_only',False)
    if (diagnostic or src['page_count'] != target[0]['page_count']) and not allow_diagnostic:
        raise ValueError('Diagnostic excerpt is excluded from full-PDF comparison; use --allow-diagnostic for a separate report')
    if result.get('raw_result_path') and result.get('raw_result_sha256'):
        raw = Path(result['raw_result_path'])
        raw = raw if raw.is_absolute() else REPO / raw
        if hashlib.sha256(raw.read_bytes()).hexdigest() != result['raw_result_sha256']:
            raise ValueError('Raw result SHA mismatch')
    page_numbers = [p['page_number'] for p in result['pages']]
    if len(set(page_numbers)) != len(page_numbers):
        raise ValueError('Duplicate pages: do not silently choose last result')
    parsed_completed = {p['page_number']: p for p in result['pages'] if p['status'] == 'completed'}
    completed = dict(parsed_completed)
    not_applicable = []
    route_path = HERE.parent / 'page-routing.json'
    native_only = not result.get('composition') and (any(str(p.get('native_scope','')).startswith('native_model_only') for p in result['pages']) or result.get('evaluation_scope') == 'native_only')
    if native_only and route_path.exists():
        routing = json.loads(route_path.read_text())
        route_doc = next(d for d in routing['documents'] if d['sha256'] == src['sha256'])
        not_applicable = [p['page_number'] for p in route_doc['pages'] if p['route'] != 'native']
        completed = {pn:p for pn,p in completed.items() if pn not in not_applicable}
    gold = json.loads(GOLD.read_text())
    binding_checks, row_checks, note_checks = [], [], []
    for case in gold['cases']:
        if Path(case['document']).name != Path(src['path']).name:
            continue
        if case['source_sha256'] != src['sha256']:
            raise ValueError('Gold source SHA mismatch')
        page = completed.get(case['page'])
        for group, label, note, *expected_values in case['facts']:
            matches = []
            if page:
                for t in page['tables']:
                    for ri, row in enumerate(rows_for(t)):
                        for ci, text in enumerate(row):
                            if row_key(text) == row_key(label):
                                matches.append((t, ri, ci, row))
            matched = matches[0] if len(matches) == 1 else None
            offset = 1 if group == 'performance' else 2
            rid = {'case_id': case['id'], 'page': case['page'], 'group': group, 'row_label': label}
            for index, value in enumerate(expected_values):
                if not numeric(value):
                    continue
                actual, path, period_ok, sourcepath, sourceperiod = None, None, None, None, None
                if matched:
                    t, ri, ci, row = matched
                    col = ci + offset + index
                    actual = row[col] if col < len(row) else None
                    path = header_path(t, ri, col)
                    period_ok = period_matches(path, case['columns'][3 + index])
                    sourcepath, sourceperiod = source_period_evidence(t,ri,col,case['columns'][3 + index])
                if page is None:
                    state = 'not_evaluated_not_applicable' if case['page'] in not_applicable else 'not_evaluated_page_unavailable'
                elif not page['tables']:
                    state = 'not_evaluated_structure_unknown' if page.get('structure_status') == 'unknown' else 'missing_table'
                elif len(matches) > 1:
                    state = 'ambiguous_row'
                elif actual is None:
                    state = 'missing_row_or_column'
                else:
                    state = 'pass' if equivalent_number(value, actual) else 'value_mismatch'
                binding_checks.append({**rid, 'period': case['columns'][3 + index], 'expected': value, 'actual': actual,
                                       'status': state, 'exact_text': compact(value) == compact(actual) if actual is not None else False,
                                       'header_path': path, 'period_header_match': period_ok,
                                       'binding_and_period_pass': state == 'pass' and period_ok is True,
                                       'source_period_text_path':sourcepath,'source_period_header_match':sourceperiod,
                                       'binding_and_source_period_pass':state == 'pass' and sourceperiod is True,
                                       'table_id': matched[0]['table_id'] if matched else None,
                                       'row': matched[1] if matched else None, 'column': matched[2] + offset + index if matched else None})
            row_checks.append({**rid, 'unique_row_match': bool(matched), 'candidates': len(matches),
                               'row_label_typography_equivalent':bool(matched)and compact(matched[3][matched[2]])!=compact(label),
                               'all_value_cells_exact': bool(matched) and all(ci + offset + i < len(row) and compact(row[ci + offset + i]) == compact(v)
                                                                         for i, v in enumerate(expected_values)) if matched else False})
            if note:
                actualnote = matched[3][matched[2] + 1] if matched and matched[2] + 1 < len(matched[3]) else None
                note_checks.append({**rid, 'expected': note, 'actual': actualnote, 'status': ('not_evaluated_not_applicable' if case['page'] in not_applicable else 'not_evaluated_page_unavailable') if page is None else 'pass' if compact(actualnote) == compact(note) else 'mismatch'})
    full = source_table_checks(result, completed)
    output = {'schema_version': 'clean-model-score/1', 'scorer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'run_id': result['run_id'], 'config_id': result['config_id'], 'source': src,
              'run_status': result['status'], 'diagnostic_only': diagnostic, 'coverage': {'expected_pages': src['page_count'], 'recorded_pages': len(page_numbers),
                                                        'completed_pages': len(completed), 'parsed_completed_pages':len(parsed_completed),
                                                        'not_applicable_pages':not_applicable, 'native_only':native_only,
                                                        'routing_manifest_sha256':hashlib.sha256(route_path.read_bytes()).hexdigest()if route_path.exists()else None,
                                                        'page_status_counts': counts(result['pages'])},
              'timing': result.get('timing', {}), 'resources': result.get('resources', {}),
              'gold_labeling_method': gold['labeling_method'], 'gold_numeric_bindings': {'counts': counts(binding_checks), 'checks': binding_checks},
              'gold_source_text_header_bindings':{'passed':sum(c['binding_and_source_period_pass']for c in binding_checks),
                                                'period_confirmed':sum(c['source_period_header_match']is True for c in binding_checks),
                                                'period_mismatch':sum(c['source_period_header_match']is False for c in binding_checks),
                                                'period_unknown':sum(c['source_period_header_match']is None and not c['status'].startswith('not_evaluated')for c in binding_checks)},
              'gold_header_bound_numeric_bindings': {'passed': sum(c['binding_and_period_pass'] for c in binding_checks),
                                                     'period_confirmed': sum(c['period_header_match'] is True for c in binding_checks),
                                                     'period_mismatch': sum(c['period_header_match'] is False for c in binding_checks),
                                                     'period_unknown': sum(c['period_header_match'] is None and not c['status'].startswith('not_evaluated') for c in binding_checks)},
              'gold_rows': row_checks, 'gold_notes': {'counts': counts(note_checks), 'checks': note_checks},
              'full_source_tables': full, 'selected_source_scopes': selected_scope_checks(result, completed),
              'quality_scope': 'Only fixed source gold and 11 complete source tables. Whole502-page accuracy is not estimated. No model answer supplied; no app repair/oracle imported.',
              'strict_grid_is_diagnostic_not_value_score': True}
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--result', required=True, type=Path)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--allow-diagnostic',action='store_true')
    args = ap.parse_args()
    result = json.loads(args.result.read_text())
    output = score(result,allow_diagnostic=args.allow_diagnostic)
    output['input_result'] = str(args.result.resolve())
    output['input_result_sha256'] = hashlib.sha256(args.result.read_bytes()).hexdigest()
    path = args.output or args.result.with_name('score.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'score': str(path), 'config_id': output['config_id'], 'source': output['source']['path'],
                      'coverage': output['coverage'], 'numeric': output['gold_numeric_bindings']['counts'],
                      'periods': output['gold_header_bound_numeric_bindings']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
