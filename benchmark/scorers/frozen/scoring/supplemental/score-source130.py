"""Seven source-reviewed130-report tables; independent73-field denominator."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json
from pathlib import Path
H=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('supplement11_frozen',H/'score-supplemental.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
SOURCE=H/'130-merged-source-only.json';m.TARGETS=json.loads(SOURCE.read_text())
def score(result):
 out=m.score(result);out['schema_version']='clean-source130-four-page-score/1'
 out['source_only_rules_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
 out['scope']='Seven original-confirmed130-report tables,73 deduplicated fields; separate from209 and402. Header scope, inline currency units, dates and negative signs retained. Period captions outside tables remain separately unknown.'
 out['source130_wrapper_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);ap.add_argument('--output',type=Path);a=ap.parse_args();r=score(json.loads(a.result.read_text()));out=a.output or a.result.with_name('source130-score.json');out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(out),'atomic':r['atomic_literal_summary']},ensure_ascii=False))
if __name__=='__main__':main()
