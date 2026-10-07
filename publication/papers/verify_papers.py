"""Check five final research PDFs and their exact cited frozen source files.

Requires pdfplumber and pypdf. Visual review remains a separate human/agent step.
"""
from pathlib import Path
import argparse,hashlib,json
import pdfplumber

here=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root',type=Path,default=here.parent.parent)
args=parser.parse_args()
manifest=json.loads((here/'evidence-manifest.json').read_text(encoding='utf-8'))
records=[]; errors=[]
for item in manifest['papers']:
    path=here/item['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        errors.append(f'PDF fingerprint mismatch: {path.name}')
    for source in item['sources']:
        if 'sha256' not in source: continue
        source_path=args.source_root/source['path']
        if not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest()!=source['sha256']:
            errors.append(f'Source mismatch: {source["path"]}')
    pages=[]
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages)!=10: errors.append(f'{path.name}: unexpected page count')
        for i,page in enumerate(pdf.pages,1):
            words=page.extract_words()
            out_of_bounds=[w['text'] for w in words if w['x0']<60 or w['x1']>552 or w['top']<24 or w['bottom']>765]
            text=page.extract_text() or ''
            bad_glyphs=[c for c in ['\u25a0','\u25a1','\ufffd','(cid:0)'] if c in text]
            if out_of_bounds or bad_glyphs: errors.append(f'{path.name} page{i}: geometry/glyph issue')
            if f'{i} / 10' not in text: errors.append(f'{path.name} page{i}: footer mismatch')
            pages.append({'page':i,'words':len(words),'links':len(page.hyperlinks),'geometry_issues':out_of_bounds,'glyph_issues':bad_glyphs})
    records.append({'file':item['file'],'sha256':item['sha256'],'pages':pages,'words':sum(p['words'] for p in pages)})
report={'edition':'2026-10-07','scope':'Five implementation research papers; automated text/geometry/hash checks complement Poppler visual review.','papers':records,'errors':errors,'status':'passed' if not errors else 'failed'}
(here/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'papers':len(records),'pages':sum(len(x['pages']) for x in records),'words':sum(x['words'] for x in records),'errors':errors}))
if errors: raise SystemExit(1)
