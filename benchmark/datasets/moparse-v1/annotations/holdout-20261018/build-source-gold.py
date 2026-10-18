"""Build original-PDF-only, partial-coverage holdout annotations; never read candidates."""
from pathlib import Path
import collections, datetime, hashlib, json, re
import pymupdf as pdf
import jsonschema

ROOT = Path('/opt/mosaic-parse')
REL = Path('benchmark/datasets/moparse-v1')
SOURCE = ROOT / REL / 'sources/holdout-20261018'
ANNOT = ROOT / REL / 'annotations/holdout-20261018'
if (ANNOT / 'gold-seal.json').exists():
    raise SystemExit('Sealed source gold already exists; explicit source-only re-review is required before rebuilding.')
EVIDENCE = ANNOT / 'local-evidence'
EVIDENCE.mkdir(parents=True, exist_ok=True)
(EVIDENCE / '.gitignore').write_text('*\n!.gitignore\n')
provenance = json.loads((SOURCE / 'download-provenance.json').read_text())
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
records = []
docs = {}
for original in provenance['documents']:
    row = dict(original)
    path = ROOT / row['source_path']
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == row['sha256']
    doc = pdf.open(path)
    docs[row['id']] = doc
    row.update(schema='moparse-document/1', bytes=len(data), page_count=len(doc),
               media_type='application/pdf', page_count_method='PyMuPDF document.page_count',
               page_dimensions_pdf_points=[[round(p.rect.width, 3), round(p.rect.height, 3)] for p in doc])
    records.append(row)
(SOURCE / 'source-records.json').write_text(json.dumps({'schema':'moparse-source-records/1','created_at':now,'documents':records}, ensure_ascii=False, indent=2)+'\n')

IRS='holdout-irs-form1040-2025'
NIST='holdout-nist-tn2354'
CENSUS='holdout-census-samoa-1930'
checks=[]
def add(cid, did, page, kind, expected, bbox, note, selector=None):
    check={'id':cid,'document_id':did,'page':page,'kind':kind,'expected':expected,
           'source_evidence':{'physical_page':page,'bbox_pdf_points':bbox,'note':note}}
    if selector is not None: check['selector']={'text':selector}
    if kind in ('text','ordered_text'): check['normalize_whitespace']=True
    checks.append(check)

add('irs-title',IRS,1,'text','U.S. Individual Income Tax Return',[95,32,285,46],'Title visually checked on original blank form.')
for suffix, label, bbox in [
    ('single','Single',[96,204,145,216]),
    ('joint','Married filing jointly',[96,216,293,229]),
    ('separate','Married filing separately',[96,228,325,253]),
    ('head','Head of household',[349,204,458,216]),
    ('surviving','Qualifying surviving spouse',[349,216,493,229])]:
    add('irs-filing-checkbox-'+suffix,IRS,1,'text',label,bbox,'Source checkbox caption. Reading order between the two filing-status columns is not asserted; the blank state is not inferred.')
add('irs-dependent-column-order',IRS,1,'ordered_text',['Dependent 1','Dependent 2','Dependent 3','Dependent 4'],[145,297,578,309],'Four column labels read left to right.')
add('irs-dependent-field-order',IRS,1,'ordered_text',['(1) First name','(2) Last name','(3) SSN','(4) Relationship'],[92,309,145,356],'Numbered row labels read top to bottom.')
add('irs-student-checkbox-label',IRS,1,'regex',r'Full-time\s+student',[146,380,190,402],'Caption beside an empty checkbox; source line break is permitted.')
add('irs-disability-checkbox-label',IRS,1,'regex',r'Permanently\s+and\s+totally\s+disabled',[197,380,253,402],'Caption beside an empty checkbox; source line breaks are permitted.')
add('irs-dependent-claim-checkbox-order',IRS,2,'ordered_text',['You as a dependent','Your spouse as a dependent','Spouse itemizes on a separate return','You were a dual-status alien'],[111,49,425,73],'Blank checkboxes; assertions cover the labels and their local reading order.')
add('irs-standard-deduction-single-amount',IRS,2,'text','$15,750',[29,92,87,142],'Exact printed standard-deduction amount in left sidebar.')
add('irs-standard-deduction-joint-amount',IRS,2,'text','$31,500',[29,142,87,190],'Exact printed standard-deduction amount in left sidebar.')
add('irs-standard-deduction-head-amount',IRS,2,'text','$23,625',[29,187,87,213],'Exact printed standard-deduction amount in left sidebar.')
add('irs-direct-deposit-label-order',IRS,2,'ordered_text',['Routing number','Type:','Checking','Savings','Account number'],[98,503,479,529],'Direct-deposit field and empty-checkbox labels in printed reading order.')
add('irs-third-party-checkbox-order',IRS,2,'ordered_text',['Yes. Complete below.','No'],[429,575,566,589],'Two empty-checkbox labels beside the third-party designation question.')
add('irs-signature-field-order',IRS,2,'ordered_text',['Your signature','Your occupation','Spouse’s signature','Spouse’s occupation'],[90,634,405,694],'Signature rows read left to right then top to bottom; source apostrophes retained.')
add('irs-footer-instruction',IRS,2,'text','Go to www.irs.gov/Form1040 for instructions and the latest information.',[34,755,410,770],'Complete short instruction in the bottom footer.')

add('nist-publication-approval-date',NIST,3,'text','2025-09-23',[90,319,339,334],'Exact approval date from publication-history line.')
add('nist-doi',NIST,3,'text','https://doi.org/10.6028/NIST.TN.2354',[90,449,283,464],'DOI printed on the source citation page.')
add('nist-author-orcid-order',NIST,3,'ordered_text',['0000-0001-8620-5311','0000-0001-7039-5835','0000-0001-8785-2035'],[90,538,284,576],'Three source identifiers in author order; exact numeric characters retained.')
add('nist-results-section-order',NIST,11,'ordered_text',['3. Results','3.1. Fire dynamics of the fuel packages','Table 1.'],[89,148,525,552],'Section heading, subsection heading, then the table caption in original reading order.')
add('nist-combustion-properties-grid',NIST,11,'table_grid',[
    ['', 'Peak HRR (kW)', 'Total HR (MJ)', 'Initial mass (kg)', 'Mass loss (kg)', 'Effective HOC (MJ/kg)'],
    ['Vehicle 1','11312 ± 672','9327 ± 582','1877 ± 4','256.8 ± 5.7','36.32 ± 4.81'],
    ['Vehicle 2','8527 ± 507','7817 ± 489','1295 ± 4','241.3 ± 5.7','32.40 ± 4.33'],
    ['Tree 1','14511 ± 1582','324 ± 36','139.0 ± 0.1','15.4 ± 2.0','21.04 ± 7.19'],
    ['Tree 2','35474 ± 3837','517 ± 57','102.0 ± 0.1','24.6 ± 3.1','21.02 ± 7.04'],
    ['Crib 1','128.7 ± 6.7','70.9 ± 3.9','7.922 ± 0.001','2.36 ± 0.15','30.04 ± 5.05'],
    ['Crib 2','137.3 ± 7.1','68.7 ± 3.8','7.858 ± 0.001','2.29 ± 0.14','30.00 ± 4.95']
],[110,560,502,673],'Complete source table: six data rows and all uncertainty values/units. Header name and unit share one logical cell; physical line wrapping is whitespace only.','Effective HOC')
add('nist-emission-yields-grid',NIST,12,'table_grid',[
    ['', 'CO₂ yield kg/kg', 'CO yield (kg/kg)', 'PM yield (kg/kg)', 'MCE (-)'],
    ['Vehicle 1','2.66 ± 0.11','0.059 ± 0.003','0.066 ± 0.005','0.978 ± 0.029'],
    ['Vehicle 2','2.38 ± 0.10','0.044 ± 0.002','0.045 ± 0.003','0.982 ± 0.033'],
    ['Tree 1','1.90 ± 0.25','0.117 ± 0.015','0.011 ± 0.003','0.942 ± 0.110'],
    ['Tree 2','1.35 ± 0.18','0.081 ± 0.011','0.010 ± 0.003','0.943 ± 0.157'],
    ['Crib 1','2.64 ± 0.19','0.076 ± 0.006','0.015 ± 0.002','0.972 ± 0.049'],
    ['Crib 2','2.62 ± 0.19','0.082 ± 0.006','0.015 ± 0.002','0.970 ± 0.049']
],[140,280,473,393],'Complete source table. The first header unit has no parentheses in the original. Chemical subscript and all uncertainties retained.','MCE')
add('nist-pah-subsection',NIST,12,'text','3.2. PAH yields of the fuel packages',[89,425,270,440],'Subsection heading below the second technical table.')
add('nist-pah-yield-range-units',NIST,12,'regex',r'114\s+mg/kg\s+for\s+trees\s+to\s+264\s+mg/kg\s+for\s+vehicles',[89,542,504,560],'Exact short numeric comparison with its units; only source whitespace may vary.')

add('census-population-section-heading',CENSUS,3,'text','COMPOSITION AND CHARACTERISTICS OF THE POPULATION',[142,121,471,138],'Scanned heading visually verified; native OCR was not treated as gold.')
add('census-population-column-order',CENSUS,3,'ordered_text',['Introduction.','Color or race, nativity, and sex.','Age.','School attendance.','Illiteracy.'],[55,143,558,741],'Two-column page: left-column section anchors precede right-column section anchors.')
add('census-naval-governor-footnote',CENSUS,4,'text','Census taken by the naval governor.',[142,642,264,655],'Complete short source footnote. Superscript marker is excluded from this text check.')
add('census-annexation-footnote',CENSUS,4,'text','Swains Island annexed to American Samoa in 1925.',[340,642,507,655],'Complete short source footnote. Superscript marker is excluded from this text check.')
add('census-agriculture-heading',CENSUS,10,'text','NUMBER OF FARMS, ACREAGE, PRODUCTION, AND LIVESTOCK',[141,192,505,211],'Scanned section heading visually checked on the original.')
add('census-reference-dates-order',CENSUS,10,'regex',r'(?s)1930\s+relates\s+to\s+April\s+1\s+of\s+that\s+year\s+and\s+the\s+crop\s+year\s+1929.*?1920\s+relates\s+to\s+January\s+1',[57,214,323,254],'Short source date facts read in source order; no values are inferred from the later tables.')
add('census-agriculture-column-order',CENSUS,10,'ordered_text',['Census dates.','Farm.','Products.','Samoan fruits','Tables 11 and 12','Livestock.','Table 15'],[57,214,595,636],'Left column finishes before right column. Damaged text inside the coconut paragraph is not transcribed or scored.')
add('census-copra-produced-grid',CENSUS,10,'table_grid',[
    ['DISTRICT','COPRA PRODUCED (POUNDS)',''],
    ['','1929','1919'],
    ['Total','3,778,880','1,735,734'],
    ['Manua District','904,960','42,827'],
    ['Tutuila:','',''],
    ['Eastern District','808,640','521,605'],
    ['Western District','2,065,280','1,171,302']
],[155,658,497,754],'Complete scanned table visually transcribed, including both header levels and the empty group-label row. Dot leaders are decoration, not cell text. Printed digit groups are joined without typographic spacing.','COPRA PRODUCED (POUNDS)')
add('census-copra-district-header-span',CENSUS,10,'table_span',[0,0,2,1],[156,659,373,701],'Source ruling shows the district header spans both header rows. Span uses zero-based row/column indices.','COPRA PRODUCED (POUNDS)')
add('census-copra-produced-header-span',CENSUS,10,'table_span',[0,1,1,2],[372,659,497,678],'Source ruling shows the shared quantity/unit header spans both year columns. Span uses zero-based row/column indices.','COPRA PRODUCED (POUNDS)')

bundle={'schema':'moparse-source-assertions/1','id':'holdout-20261018',
 'source_documents':[{'id':r['id'],'sha256':r['sha256'],'source_path':r['source_path']} for r in records],
 'review':{'method':'original PDF visual transcription','model_outputs_seen':False,
           'reviewed_at':now,'annotator_type':'assistant_source_only_visual_review',
           'coverage':'partial','normalization_policy':'Text and ordered anchors explicitly normalize whitespace; numeric values, symbols, word order and units are source facts. Table cells normalize whitespace only.',
           'full_paragraph_coverage':'deferred; source-region fingerprints retained separately, not scored as paragraph correctness',
           'source_access_only':True,'inference_calls':0,'gpu_calls':0},
 'checks':checks}
gold_path=ANNOT/'assertions.json'
gold_path.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+'\n')

# Region fingerprints document coverage boundaries without reproducing long prose.
regions=[(NIST,3,[89,102,526,150],'publication-disclaimer'),
         (IRS,2,[92,613,570,633],'perjury-declaration'),
         (CENSUS,10,[57,252,323,341],'farm-definition')]
region_records=[]
for did,pg,box,label in regions:
    page=docs[did][pg-1]
    pix=page.get_pixmap(matrix=pdf.Matrix(2,2),clip=pdf.Rect(box))
    path=EVIDENCE/f'paragraph-region-{label}.png'
    pix.save(path)
    entry={'document_id':did,'physical_page':pg,'bbox_pdf_points':box,'label':label,
           'render_path':str(path.relative_to(ROOT)),'raster_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
           'status':'deferred','scored':False,'reason':'Long-paragraph completeness is outside the sealed short-anchor assertion scope.'}
    if did != CENSUS:
        native_text=' '.join(page.get_text(clip=pdf.Rect(box)).split())
        entry.update(native_text_sha256=hashlib.sha256(native_text.encode()).hexdigest(),
                     native_word_count=len(native_text.split()),native_text_stored=False)
    else:
        entry['native_text_fingerprint_omitted']='Scan OCR is not a reliable source transcript.'
    region_records.append(entry)

manifest=[]
for path in sorted(EVIDENCE.glob('*.png')):
    manifest.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
review={'schema':'moparse-source-review/1','id':'holdout-20261018','reviewed_at':now,
 'method':'original PDF visual transcription','model_outputs_seen':False,
 'source_documents':bundle['source_documents'],'coverage':'partial',
 'checks':len(checks),'by_kind':dict(collections.Counter(c['kind'] for c in checks)),
 'by_document':dict(collections.Counter(c['document_id'] for c in checks)),
 'complete_tables':3,'merged_span_checks':2,'paragraph_regions':region_records,
 'evidence_files':manifest,'evidence_visibility':'private ignored local renders; no public redistribution',
 'exclusions':[{'document_id':CENSUS,'physical_page':10,'bbox_pdf_points':[60,474,325,575],
                'status':'excluded_unverified','reason':'Source scan has damaged/occluded prose; unknown glyphs were not guessed.'}],
 'limitations':['These are sampled source assertions, not whole-PDF transcription accuracy.',
                'Whole-paragraph coverage is deferred and is not counted as a passed check.',
                'Empty form checkboxes are checked for labels only; no filled state is inferred.',
                'Source-image fingerprints preserve review evidence but do not score semantic text completeness.']}
(ANNOT/'source-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')

# Validate only the source records and the manually reviewed gold, never candidate outputs.
schemas=ROOT/'benchmark/schemas'
assertions_schema=json.loads((schemas/'assertions.schema.json').read_text())
document_schema=json.loads((schemas/'document.schema.json').read_text())
jsonschema.validate(bundle,assertions_schema)
for row in records: jsonschema.validate(row,document_schema)
assert len({c['id'] for c in checks})==len(checks)
for c in checks:
    page=docs[c['document_id']][c['page']-1]
    x0,y0,x1,y1=c['source_evidence']['bbox_pdf_points']
    assert 0<=x0<x1<=page.rect.width and 0<=y0<y1<=page.rect.height,c['id']
    assert c['page']==c['source_evidence']['physical_page']
    if c['kind']=='regex': re.compile(c['expected'])
    if c['kind']=='table_grid': assert len({len(row) for row in c['expected']})==1
assert len(checks)>=20
validation={'schema':'moparse-source-validation/1','validated_at':now,
            'assertion_schema':'benchmark/schemas/assertions.schema.json',
            'document_schema':'benchmark/schemas/document.schema.json',
            'status':'passed','document_count':len(records),'check_count':len(checks),
            'unique_ids':True,'page_and_bbox_bounds':True,'source_hashes_match_download_provenance':True,
            'models_or_candidates_read':False}
(ANNOT/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')

sealed_files=[gold_path,ANNOT/'source-review.json',ANNOT/'validation.json',SOURCE/'source-records.json']
seal={'schema':'moparse-source-gold-seal/1','id':'holdout-20261018','sealed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'model_outputs_seen':False,'inference_calls_before_seal':0,'coverage':'partial','check_count':len(checks),
      'files':[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sealed_files]}
(ANNOT/'gold-seal.json').write_text(json.dumps(seal,indent=2)+'\n')
print(json.dumps({'document_count':len(records),'check_count':len(checks),'complete_table_count':3,'span_count':2,
                  'source_render_count':len(manifest),'gold_sha256':hashlib.sha256(gold_path.read_bytes()).hexdigest(),
                  'sealed_at':seal['sealed_at'],'validation':'passed'}))
