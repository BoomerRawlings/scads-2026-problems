"""Build four explicitly projected SCADS research proposals.

Requires reportlab, pypdf. Run from any directory. Editable prose: proposed_papers.py.
Font fallback keeps generation portable; exact source hashes are recorded.
"""
from pathlib import Path
import hashlib
import json
import os
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable, KeepTogether
from pypdf import PdfReader
from proposed_papers import PROPOSALS as PAPERS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / 'pdf'
OUT.mkdir(parents=True, exist_ok=True)
INK = colors.HexColor('#182b49')
GREEN = colors.HexColor('#00629b')
MUTED = colors.HexColor('#657080')
RULE = colors.HexColor('#d7d0c2')
PAPER = colors.HexColor('#fffdf8')
PALE = colors.HexColor('#f5f0e6')
GOLD = colors.HexColor('#c69214')
FONTS = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
if (FONTS / 'georgia.ttf').exists():
    for name, file in [('Body','georgia.ttf'),('BodyBold','georgiab.ttf'),('BodyItalic','georgiai.ttf'),('Sans','arial.ttf'),('SansBold','arialbd.ttf'),('Mono','consola.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
    pdfmetrics.registerFontFamily('Body', normal='Body', bold='BodyBold', italic='BodyItalic', boldItalic='BodyBold')
else:
    for name, face in [('Body','Times-Roman'),('BodyBold','Times-Bold'),('BodyItalic','Times-Italic'),('Sans','Helvetica'),('SansBold','Helvetica-Bold'),('Mono','Courier')]:
        pdfmetrics.registerFont(pdfmetrics.Font(name, face, 'WinAnsiEncoding'))
    pdfmetrics.registerFontFamily('Body', normal='Body', bold='BodyBold', italic='BodyItalic', boldItalic='BodyBold')

styles = {
    'body': ParagraphStyle('body', fontName='Body', fontSize=9.6, leading=14.6, textColor=INK, spaceAfter=9),
    'small': ParagraphStyle('small', fontName='Sans', fontSize=8.1, leading=11.5, textColor=MUTED, spaceAfter=7),
    'title': ParagraphStyle('title', fontName='Body', fontSize=28, leading=32, textColor=INK, spaceAfter=12),
    'subtitle': ParagraphStyle('subtitle', fontName='Sans', fontSize=11.2, leading=16, textColor=GREEN, spaceAfter=15),
    'h1': ParagraphStyle('h1', fontName='Body', fontSize=21, leading=26, textColor=INK, spaceAfter=15),
    'h2': ParagraphStyle('h2', fontName='SansBold', fontSize=10.5, leading=14, textColor=GREEN, spaceBefore=9, spaceAfter=7),
    'cell': ParagraphStyle('cell', fontName='Sans', fontSize=8.1, leading=11.8, textColor=INK),
    'th': ParagraphStyle('th', fontName='SansBold', fontSize=8.1, leading=11.8, textColor=GREEN),
    'code': ParagraphStyle('code', fontName='Mono', fontSize=8.3, leading=12.5, textColor=INK, spaceAfter=8),
    'ref': ParagraphStyle('ref', fontName='Sans', fontSize=8.1, leading=11.7, textColor=INK, spaceAfter=8),
}

BASE = 'https://github.com/BoomerRawlings/scads-2026-problems/tree/main/projects/'
def ref_url(paper,path):
    return path if path and path.startswith('https://') else BASE+paper['slug']+'/PROPOSAL.md'
def fmt(text, paper):
    text = escape(text).replace('\n', '<br/>')
    def cite(m):
        n = int(m.group(1)); ref = paper['refs'][n-1]
        if ref[1] is None:
            return f'[{n}]'
        return '<a href="%s" color="#00629b">[%d]</a>' % (ref_url(paper,ref[1]),n)
    return re.sub(r'\[(\d+)\]', cite, text)

class Rule(Flowable):
    def __init__(self): super().__init__(); self.width=488; self.height=12
    def draw(self):
        self.canv.setStrokeColor(RULE); self.canv.setLineWidth(.6); self.canv.line(0,6,self.width,6)

def table_block(headers, rows, widths, paper):
    cells = [[Paragraph(fmt(x,paper),styles['th']) for x in headers]]
    cells += [[Paragraph(fmt(str(x),paper),styles['cell']) for x in row] for row in rows]
    table = Table(cells, colWidths=widths, hAlign='LEFT', repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),PALE),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('LINEBELOW',(0,0),(-1,0),.7,RULE),('LINEBELOW',(0,1),(-1,-1),.35,RULE)]))
    return [table,Spacer(1,10)]

def blocks(items,paper):
    result=[]
    for kind,*data in items:
        if kind=='p': result.append(Paragraph(fmt(data[0],paper),styles['body']))
        elif kind=='h': result.append(Paragraph(fmt(data[0],paper),styles['h2']))
        elif kind=='note':
            t=Table([[Paragraph(fmt(data[0],paper),styles['small'])]],colWidths=[488])
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.4,RULE),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
            result.extend([t,Spacer(1,10)])
        elif kind=='table': result.extend(table_block(*data,paper))
        elif kind=='code':
            result.append(Paragraph(fmt(data[0],paper),styles['code']))
        elif kind=='refs':
            for i,(label,path) in enumerate(paper['refs'],1):
                if path is None:
                    result.append(Paragraph(f'<b>[{i}]</b> {escape(label)}',styles['ref']))
                    continue
                url=ref_url(paper,path)
                result.append(Paragraph(f'<b>[{i}]</b> <a href="{url}" color="#00629b">{escape(label)}</a><br/><font color="#657080">{escape(path or 'User-supplied brief, paraphrased').replace("/","/&#8203;")}</font>',styles['ref']))
        else: raise ValueError(kind)
    return result

def page_chrome(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAPER);canvas.rect(0,0,612,792,fill=1,stroke=0)
    canvas.setFillColor(GREEN);canvas.setFont('SansBold',8)
    canvas.drawString(62,754,'BOOMER RAWLINGS  /  SCADS 2026')
    canvas.setFont('Sans',8);canvas.setFillColor(MUTED)
    canvas.drawRightString(550,754,doc.paper['short'])
    canvas.setStrokeColor(RULE);canvas.setLineWidth(.6);canvas.line(62,740,550,740)
    canvas.setStrokeColor(GOLD);canvas.setLineWidth(2);canvas.line(62,740,111,740)
    canvas.line(62,48,550,48);canvas.setFont('Sans',7.7)
    canvas.drawString(62,33,'OCTOBER 2026  /  RESEARCH PROPOSAL  /  NOT STARTED')
    canvas.drawRightString(550,33,f'{doc.page} / {len(doc.paper["pages"])}')
    canvas.restoreState()

manifest={'edition':'2026-10-07','scope':'Four projected solutions and research plans. No implementation or empirical results.','papers':[]}
for paper in PAPERS:
    dest=OUT/(paper['slug']+'.pdf')
    doc=SimpleDocTemplate(str(dest),pagesize=(612,792),leftMargin=62,rightMargin=62,topMargin=69,bottomMargin=63,title=paper['title'],author='Boomer Rawlings',subject=paper['subtitle'])
    doc.paper=paper
    story=[]
    for i,page in enumerate(paper['pages']):
        if i: story.append(PageBreak())
        if i==0:
            story.append(Paragraph('PROBLEM SET  /  '+paper['number'],styles['small']))
            story.append(Paragraph(paper['title'],styles['title']))
            story.append(Paragraph(paper['subtitle'],styles['subtitle']))
            story.append(Paragraph('Boomer Rawlings  |  Independent individual work',styles['small']))
            story.append(Paragraph('Proposed after the original submission and grading dates. Status: Not started.',styles['small']))
            story.append(Rule())
        else:
            story.append(Paragraph(page['title'],styles['h1']))
        story.extend(blocks(page['blocks'],paper))
    doc.build(story,onFirstPage=page_chrome,onLaterPages=page_chrome)
    reader=PdfReader(dest)
    if len(reader.pages)!=len(paper['pages']): raise RuntimeError(f'{dest.name}: expected {len(paper["pages"])} pages, got {len(reader.pages)}')
    sources=[]
    for label,path in paper['refs']:
        if path is None:
            sources.append({'title':label,'kind':'user-supplied problem brief'})
            continue
        if path.startswith('https://'):
            sources.append({'title':label,'url':path,'verified':'2026-10-07','kind':'primary external source'})
            continue
        source=ROOT/'projects'/paper['slug']/path
        if path=='IMPLEMENTATION.md' and not source.is_file():
            source=source.with_name('README.md')
        if not source.is_file(): raise FileNotFoundError(source)
        sources.append({'path':str(source.relative_to(ROOT)).replace('\\','/'),'publication_path':'projects/'+paper['slug']+'/'+path,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    manifest['papers'].append({'file':str(dest.relative_to(HERE)).replace('\\','/'),'pages':len(reader.pages),'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'sources':sources})
    print(f'{dest.name}: {len(reader.pages)} pages, {dest.stat().st_size:,} bytes')
(HERE/'proposal-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
