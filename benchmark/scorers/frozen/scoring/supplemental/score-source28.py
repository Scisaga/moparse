"""Deterministic original scan pages7/21, independent24 source fields."""
from __future__ import annotations
import argparse,copy,hashlib,importlib.util,json,re
from pathlib import Path
H=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('supplement11_source28',H/'score-supplemental.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
SOURCE=H.parent/'source28-original-only.json';ORIGINAL=json.loads(SOURCE.read_text());m.TARGETS=ORIGINAL
def canonical(text):return re.sub(r'(?<=\d)[,，](?=\d{3}(?:[,，]\d{3})*(?:\D|$))','',str(text))
def normalize(value):
 if isinstance(value,str):return canonical(value)
 if isinstance(value,list):return [normalize(v)for v in value]
 if isinstance(value,dict):return {k:normalize(v)if k in {'rows','text'}else normalize(v)if isinstance(v,(list,dict))else v for k,v in value.items()}
 return value
def score(result):
 strict=m.score(result)
 try:m.TARGETS=normalize(copy.deepcopy(ORIGINAL));out=m.score(normalize(copy.deepcopy(result)))
 finally:m.TARGETS=ORIGINAL
 out['schema_version']='source28-independent-score/1';out['source_only_rules_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest();out['source28_scorer_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 out['strict_original_cell_literal_summary']=strict['atomic_literal_summary'];out['strict_original_cell_literal_tables']=strict['tables'];out['format_only_comparison']='Ignore valid thousands separators between digits only; preserve every digit, precision, negative sign, date, unit, row and full header path. This changes comparison strings only, never saved model output.'
 out['scope']='Deterministic source quartiles of complete28-page scanned PDF: original pages7/21,24 account/status/unit/benefit fields. Separate from209/402/73; no overall accuracy.'
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--result',required=True,type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args();out=score(json.loads(a.result.read_text()));p=a.output or a.result.with_name('source28-score.json');p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(p),'atomic':out['atomic_literal_summary']},ensure_ascii=False))
if __name__=='__main__':main()
