"""Common faithful GFM output. No model/domain corrections or app imports.

Public functions: render_page(page)->(str,list[dict]);
render_result(result)->(str,list[dict]). Original cells remain authoritative;
GFM contains unique anchors and blank span coverage, plus source/span comments.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import html
import importlib.util
import json
import re
import subprocess
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=next(parent for parent in HERE.parents if(parent/'pyproject.toml').is_file()and(parent/'app').is_dir())
META=re.compile(r'<!-- clean-table: (.*?) -->')
PAGE=re.compile(r'<!-- page: (\d+) -->')
EXPORT_VERSION='1.1.0'
_NATIVE_CACHE={}
_NATIVE_INPUT_CACHE={}
_COMPONENT_RESULT_CACHE={}
_COMMON_PYTHON=REPO/'benchmark-results/model-upgrade-20261015/docling-2.139.0-eval/.venv/bin/python'


def _text(value):return str(value if value is not None else '')
def _escape(value):
    value=_text(value).replace('\r\n','\n').replace('\r','\n')
    return html.escape(value,quote=False).replace('|','&#124;').replace('\n','<br>')
def _visible(value):
    value=re.sub(r'<br\s*/?>','\n',_text(value),flags=re.I)
    return re.sub(r'\s+','',html.unescape(value))
def _rows(table):
    if 'rows'in table:return [[_text(v)for v in row]for row in table['rows']]
    cells=table.get('cells',[])
    if not cells:return []
    height=max(c['row']+c.get('row_span',1)for c in cells);width=max(c['column']+c.get('column_span',1)for c in cells)
    rows=[['']*width for _ in range(height)]
    for c in cells:rows[c['row']][c['column']]=c['text']
    return rows

def _meta(table,encoding):
    return {'table_id':table['table_id'],'source_pages':table.get('source_pages',[]),'span_encoding':encoding,
            'spans':[[c['row'],c['column'],c.get('row_span',1),c.get('column_span',1)]for c in table.get('cells',[])if c.get('row_span',1)>1 or c.get('column_span',1)>1],
            'header_rows':table.get('header_rows'),'unit_text':table.get('unit_text')}

def _marker(table,encoding):return '<!-- clean-table: '+json.dumps(_meta(table,encoding),ensure_ascii=False,separators=(',',':'))+' -->'

def _gfm(table):
    rows=_rows(table)
    if not rows or not any(rows):raise ValueError('empty or unknown matrix')
    width=max(map(len,rows));matrix=[r+['']*(width-len(r))for r in rows]
    rendered=['| '+' | '.join(_escape(v)for v in matrix[0])+' |','| '+' | '.join(['---']*width)+' |']
    rendered+=['| '+' | '.join(_escape(v)for v in row)+' |'for row in matrix[1:]]
    return '\n'.join(rendered)

def _gfm_groups(markdown):
    lines=markdown.splitlines(keepends=True);groups=[];start=None
    for i,line in enumerate(lines+['']):
        if line.lstrip().startswith('|'):
            if start is None:start=i
        elif start is not None:groups.append((start,i));start=None
    return lines,groups

def docling_table_reading_order(document,page_map=None):
    """Return official body-reference table order per page, without text matching."""
    output={};containers=set()
    def resolve(ref):
        parts=ref.removeprefix('#/').split('/')
        node=document
        for part in parts:node=node[int(part)]if isinstance(node,list)else node[part]
        return node
    def walk(node):
        if isinstance(node,dict)and '$ref'in node:
            ref=node['$ref'];node=resolve(ref)
            if ref.startswith('#/tables/'):
                for prov in node.get('prov',[]):
                    local=prov['page_no'];pn=(page_map or{}).get(str(local),(page_map or{}).get(local,local))
                    output.setdefault(pn,[]).append(ref)
            elif ref in containers:return
            containers.add(ref)
        if isinstance(node,dict):
            for child in node.get('children',[]):walk(child)
    walk(document.get('body',{}))
    return output


def _official_native_page(page):
    rawpath=page.get('raw_docling_path')
    document=page.get('raw_docling_document')
    if rawpath:
        p=Path(rawpath);p=p if p.is_absolute()else REPO/p
        stat=p.stat();inputkey=(str(p.resolve()),stat.st_size,stat.st_mtime_ns,page.get('raw_docling_sha256'))
        digest=_NATIVE_INPUT_CACHE.get(inputkey);payload=None
        if digest is None:
            payload=p.read_bytes();digest=hashlib.sha256(payload).hexdigest();_NATIVE_INPUT_CACHE[inputkey]=digest
        if page.get('raw_docling_sha256')and page['raw_docling_sha256']!=digest:raise ValueError('raw Docling document SHA mismatch')
    elif document is not None:
        payload=json.dumps(document,ensure_ascii=False).encode();digest=hashlib.sha256(payload).hexdigest()
    else:return None,[]
    worker=HERE/'official-native-export.py'
    key=(digest,hashlib.sha256(worker.read_bytes()).hexdigest(),hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    cachepath=HERE/'native-export-cache'/digest/('-'.join(key[1:])+'.json')
    if key not in _NATIVE_CACHE:
        if cachepath.exists():value=json.loads(cachepath.read_text())
        else:
            document=json.loads(payload if payload is not None else p.read_bytes())
            proc=subprocess.run([str(_COMMON_PYTHON),str(worker)],input=json.dumps({'document':document},ensure_ascii=False),text=True,capture_output=True,timeout=600)
            if proc.returncode:raise RuntimeError('Official common native serializer failed: '+proc.stderr[-3000:])
            value=json.loads(proc.stdout);cachepath.parent.mkdir(parents=True,exist_ok=True)
            tmp=cachepath.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(cachepath)
        _NATIVE_CACHE[key]=value
        if len(_NATIVE_CACHE)>4:_NATIVE_CACHE.pop(next(iter(_NATIVE_CACHE)))
    value=_NATIVE_CACHE[key];pn=page.get('local_page_number',page['page_number'])
    if str(pn)not in value['pages']:raise ValueError('Source page absent in official native serializer output')
    audit=[{'kind':'common_official_native_serializer','page':page['page_number'],'raw_document_sha256':digest,'cache_path':str(cachepath),**value['metadata']}]
    audit.extend(value['audit'])
    return value['pages'][str(pn)],audit


def _native_markdown(page):
    official,official_audit=_official_native_page(page)
    if official is not None:return official,official_audit
    md=page.get('markdown','');tables=page.get('tables',[]);lines,groups=_gfm_groups(md);audit=[]
    if not tables:return md,audit
    order=page.get('table_reading_order')
    byid={t['table_id']:t for t in tables}
    unique=order is not None and len(order)==len(set(order)) and set(order)==set(byid)and len(byid)==len(tables)
    if not unique or len(groups)!=len(tables):
        audit.append({'kind':'native_markdown_table_mapping_unknown','page':page['page_number'],'raw_tables':len(tables),'gfm_groups':len(groups),'official_ref_order':order,'raw_markdown_preserved':True})
        return md,audit
    replacements={}
    for(start,end),tid in zip(groups,order):
        table=byid[tid]
        try:
            if len(table.get('source_pages',[]))!=1:raise ValueError('multi_source_table_page_cells_unknown')
            # Multiple distinct texts with the same raw anchor cannot be
            # collapsed into one cell by a faithful common renderer.
            anchors={}
            for c in table.get('cells',[]):
                key=(c['row'],c['column'])
                if key in anchors and anchors[key]!=c['text']:raise ValueError('conflicting_raw_anchor_texts')
                anchors[key]=c['text']
            replacements[start]=(_marker(table,'anchor_and_blanks')+'\n'+_gfm(table)+'\n',end)
        except (ValueError,IndexError,KeyError)as exc:
            replacements[start]=(_marker(table,'raw_unknown')+'\n'+''.join(lines[start:end]),end)
            audit.append({'kind':'unconvertible_native_table_official_markdown_retained','page':page['page_number'],'table_id':tid,'reason':str(exc)})
    output=[];i=0
    while i<len(lines):
        if i in replacements:
            text,end=replacements[i];output.append(text);i=end
        else:output.append(lines[i]);i+=1
    return ''.join(output),audit


def _native_order_for_page(page,result):
    if page.get('raw_docling_path')or page.get('raw_docling_document')is not None:return page
    source=result
    component=page.get('selected_component',{}).get('result_path')
    if component:
        path=Path(component);path=path if path.is_absolute()else REPO/path
        stat=path.stat();ckey=(str(path.resolve()),stat.st_size,stat.st_mtime_ns)
        if ckey not in _COMPONENT_RESULT_CACHE:_COMPONENT_RESULT_CACHE[ckey]=json.loads(path.read_text())
        source=_COMPONENT_RESULT_CACHE[ckey]
    out=dict(page)
    if source.get('raw_docling_document')is not None:
        out['raw_docling_document']=source['raw_docling_document'];return out
    if source.get('raw_result_path'):
        out['raw_docling_path']=source['raw_result_path']
        if source.get('raw_result_sha256'):out['raw_docling_sha256']=source['raw_result_sha256']
    return out


def _blocks(page):
    if isinstance(page.get('blocks'),list):return page['blocks']
    path=page.get('raw_path')
    if path:
        p=Path(path);p=p if p.is_absolute()else REPO/p
        raw=json.loads(p.read_text());data=raw.get('res',raw)
        if isinstance(data.get('parsing_res_list'),list):return data['parsing_res_list']
    return None

def render_page(page):
    """Return faithful page Markdown and diagnostics; never mutate page/raw."""
    pn=page['page_number'];audit=[]
    native=page.get('export_kind')=='official_native_markdown'or bool(page.get('native_scope'))or page.get('selected_route')=='native'
    if native:
        body,issues=_native_markdown(page);audit.extend(issues)
    else:
        blocks=_blocks(page)
        if blocks is None:
            body,issues=_native_markdown(page);audit.extend(issues)
            audit.append({'kind':'layout_blocks_unknown_retained_original_markdown','page':pn})
        else:
            rendered=[];used=set();tables=page.get('tables',[])
            images=re.findall(r'<img\b[^>]*>|!\[[^\]]*\]\([^\n)]*\)',page.get('markdown',''),flags=re.I)
            used_images=set()
            for index,block in enumerate(blocks):
                label=block.get('block_label',block.get('label',''))
                content=_text(block.get('block_content',block.get('content','')))
                is_table=label=='table'or block.get('native_label')=='table'
                # Official image filenames encode the model-owned layout box.
                # Preserve those references at their original block; this only
                # links existing outputs and never recognizes or invents text.
                bbox=block.get('block_bbox',block.get('bbox_2d'))
                if bbox and len(bbox)==4:
                    exactbox=tuple(round(v)for v in bbox)
                    for image_index,tag in enumerate(images):
                        box=re.search(r'_box_(\d+)_(\d+)_(\d+)_(\d+)',tag)
                        if image_index not in used_images and box and tuple(map(int,box.groups()))==exactbox:
                            rendered.append(tag);used_images.add(image_index)
                if not is_table:
                    rendered.append(content)
                    if not content:audit.append({'kind':'empty_raw_layout_block_preserved','page':pn,'block_index':index,'label':label})
                    continue
                bid=block.get('block_id',block.get('index',index));tid=f'p{pn}_b{bid}'
                matches=[t for t in tables if t['table_id']not in used and t['table_id']==tid]
                if not matches:matches=[t for t in tables if t['table_id']not in used and t.get('raw_content')==content]
                if len(matches)!=1:
                    rendered.append('<!-- unknown-table-structure: original raw block retained -->\n'+content)
                    audit.append({'kind':'unmatched_raw_table_retained','page':pn,'block_index':index});continue
                t=matches[0];used.add(t['table_id'])
                try:
                    if t.get('structure_status')in {'invalid','unknown'}:raise ValueError(t['structure_status'])
                    gfm=_gfm(t);rendered.append(_marker(t,'anchor_and_blanks')+'\n'+gfm)
                except (ValueError,IndexError,KeyError)as exc:
                    rendered.append(_marker(t,'raw_unknown')+'\n<!-- unknown-table-structure: raw evidence retained -->\n'+content)
                    audit.append({'kind':'unconvertible_table_raw_retained','page':pn,'table_id':t['table_id'],'reason':str(exc)})
            for t in tables:
                if t['table_id']in used:continue
                # A declared table not linked to a layout block is never dropped.
                content=t.get('raw_content','')
                rendered.append(_marker(t,'raw_unknown')+'\n<!-- unlinked-original-table: raw evidence retained -->\n'+content)
                audit.append({'kind':'unlinked_table_raw_retained','page':pn,'table_id':t['table_id']})
            for image_index,tag in enumerate(images):
                if image_index not in used_images and tag not in '\n'.join(rendered):
                    rendered.append(tag)
                    audit.append({'kind':'upstream_image_preserved_source_page_block_scope_unknown','page':pn,'image_index':image_index})
            body='\n\n'.join(rendered)
    # Validation is text retention only. Business binding is scored separately
    # from parsed final cells; this is never a semantic accuracy claim.
    visible=_visible(re.sub(r'<!--.*?-->','',body,flags=re.S))
    for t in page.get('tables',[]):
        for c in t.get('cells',[]):
            text=_visible(c.get('text',''))
            if text and text not in visible:
                audit.append({'kind':'raw_cell_text_not_visible_in_export','page':pn,'table_id':t['table_id'],'row':c['row'],'column':c['column'],'text':c['text']})
    return body,audit

def render_result(result):
    """Return all recorded source pages, without merging/deduplicating tables."""
    pages=[];audit=[]
    for page in result['pages']:
        page=_native_order_for_page(page,result)if page.get('export_kind')=='official_native_markdown'or bool(page.get('native_scope'))or page.get('selected_route')=='native'else page
        body,issues=render_page(page)
        pages.append(f'<!-- page: {page["page_number"]} -->\n\n'+body);audit.extend(issues)
    return '\n\n'.join(pages),audit


def parse_final(markdown,source_result):
    """Read final GFM independently; no raw cell text is copied into output."""
    markers=list(PAGE.finditer(markdown));pages=[];issues=[]
    sourcepages={p['page_number']:p for p in source_result['pages']}
    for index,mark in enumerate(markers):
        pn=int(mark.group(1));end=markers[index+1].start()if index+1<len(markers)else len(markdown);body=markdown[mark.end():end]
        tables=[];current=[];metadata=None
        def flush():
            nonlocal current,metadata
            if not current:return
            tid=metadata['table_id']if metadata else f'p{pn}_gfm{len(tables)+1}'
            spanmap={};covered=set()
            for r,c,rs,cs in(metadata or{}).get('spans',[]):
                positions={(rr,cc)for rr in range(r,r+rs)for cc in range(c,c+cs)}
                anchor=current[r][c]if r<len(current)and c<len(current[r])else None
                valid=anchor is not None and all(rr<len(current)and cc<len(current[rr])and(not current[rr][cc]or _visible(current[rr][cc])==_visible(anchor))for rr,cc in positions)
                if valid and not(positions&covered):
                    spanmap[(r,c)]=(rs,cs);covered.update(positions-{(r,c)})
                else:issues.append({'kind':'declared_span_conflicts_with_final_visible_cells','page':pn,'table_id':tid,'row':r,'column':c})
            hdr=(metadata or{}).get('header_rows');cells=[]
            for r,row in enumerate(current):
                for c,text in enumerate(row):
                    if(r,c)in covered:continue
                    rs,cs=spanmap.get((r,c),(1,1))
                    if text or (r,c)in spanmap:cells.append({'row':r,'column':c,'row_span':rs,'column_span':cs,'text':text,'is_column_header':r in hdr if hdr is not None else None,'is_row_header':None,'source_page':pn})
            decoded={'table_id':tid,'source_pages':(metadata or{}).get('source_pages',[pn]),'rows':current,'cells':cells,
                     'header_rows':hdr,'unit_text':(metadata or{}).get('unit_text'),'structure_status':'decoded','span_representation':(metadata or{}).get('span_encoding','gfm_no_span_metadata')}
            # Preserve provenance via the explicit output table ID, never copy
            # raw cell text into readback. Public Markdown has no coordinates.
            rawtable=next((t for t in sourcepages.get(pn,{}).get('tables',[])if t['table_id']==tid),None)
            if rawtable is not None:
                for key in('bbox','bbox_coordinate_space'):
                    if key in rawtable:decoded[key]=copy.deepcopy(rawtable[key])
                decoded['source_provenance_sidecar']='original table ID, coordinates only; no text copied'
            tables.append(decoded)
            current=[];metadata=None
        for line in body.splitlines():
            mm=META.fullmatch(line.strip())
            if mm:
                flush();metadata=json.loads(mm.group(1));continue
            if line.lstrip().startswith('|'):
                vals=[html.unescape(re.sub(r'<br\s*/?>','\n',v.strip(),flags=re.I))for v in re.split(r'(?<!\\)\|',line.strip())[1:-1]]
                if vals and all(re.fullmatch(r':?-{3,}:?',v)for v in vals):continue
                current.append(vals)
            else:
                flush()
                if '<table'in line.lower():issues.append({'kind':'raw_html_structure_unknown_in_final_gfm_reader','page':pn})
        flush()
        old=sourcepages.get(pn,{})
        page={'page_number':pn,'status':old.get('status','partial'),'markdown':body,'tables':tables}
        for key in('native_scope','selected_route','export_kind','layout_width','layout_height'):
            if key in old:page[key]=old[key]
        pages.append(page)
    result={k:copy.deepcopy(v)for k,v in source_result.items()if k not in {'pages','raw_result_path','raw_result_sha256'}}
    result['pages']=pages;result['representation']='independently_parsed_final_gfm';result['source_raw_result_retained']=True
    return result,issues


def main():
    p=argparse.ArgumentParser();p.add_argument('--result',required=True,type=Path);p.add_argument('--output-dir',type=Path);args=p.parse_args()
    src=json.loads(args.result.read_text());md,audit=render_result(src);final,readissues=parse_final(md,src)
    out=args.output_dir or args.result.parent;out.mkdir(parents=True,exist_ok=True)
    (out/'final-result.md').write_text(md);(out/'final-result.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n')
    report={'schema_version':'faithful-gfm-export-audit/1','input_result':str(args.result),'input_result_sha256':hashlib.sha256(args.result.read_bytes()).hexdigest(),
            'renderer_version':EXPORT_VERSION,'renderer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'final_markdown_sha256':hashlib.sha256(md.encode()).hexdigest(),
            'audit':audit,'final_readback_issues':readissues,'raw_cells_not_visible':sum(v['kind']=='raw_cell_text_not_visible_in_export'for v in audit),
            'no_model_or_domain_repair':True,'no_header_deletion_or_crosspage_merge':True}
    (out/'final-export-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'result':str(out/'final-result.md'),'raw_cells_not_visible':report['raw_cells_not_visible'],'issues':len(audit)+len(readissues)},ensure_ascii=False))

if __name__=='__main__':main()
