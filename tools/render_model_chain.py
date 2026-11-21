"""Render the concise modeling derivation as exactly two readable A4 pages.

Uses reportlab (optional report dependency), without changing the model inputs.
"""
from pathlib import Path
import argparse
import html
import re


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='results/takeover_20261120/model_chain.pdf')
    args=parser.parse_args()
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak
    font_path=Path('C:/Windows/Fonts/simsun.ttc')
    if font_path.exists():
        pdfmetrics.registerFont(TTFont('ReportChinese',str(font_path),subfontIndex=0))
    else:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        pdfmetrics.registerFontFamily('ReportChinese',normal='STSong-Light')
    font_name='ReportChinese' if font_path.exists() else 'STSong-Light'
    root=Path(__file__).resolve().parents[1];dest=root/args.out;dest.parent.mkdir(parents=True,exist_ok=True)
    source=(root/'docs/MODEL_CHAIN.md').read_text(encoding='utf-8')
    # Read explanations from the reviewed source; typeset its six registered
    # equations in plain indexed notation to avoid a second prose version.
    equations={
        'M1':'D_ith = Σ_j x_ijth + U_ith ; x, U ≥ 0   [人次/时段]',
        'M2':'K_jth = Σ_q (C_j / L_jq) × | W_jq ∩ H_th ∩ S_t ∩ [a_jt,∞) ∩ R_jt |',
        'M3':'min Σ_ith U_ith ; Σ_i x_ijth ≤ y_j K_jth ; x_ijth = 0（不可行边）',
        'M4':'V_0(B) = u_0(B) ; V_t(B) = min_A { V_(t−1)(A) + u_t(A,B) }',
        'M5':'max_j (a_j − 9) ≤ T ≤ 24 小时',
        'M6':'O_(y+1) = O_y + b_y ; 0 ≤ A_y ≤ O_(y+1) ≤ p_max\n'
             'c_b b_y + c_a A_y + c_e(e_y) + c_s s_y ≤ Budget_y',
    }
    blocks=re.split(r'(\\\[.*?\\\])',source,flags=re.S)
    style=ParagraphStyle('body',fontName=font_name,fontSize=10.3,leading=15.1,
                         wordWrap='CJK',spaceAfter=6,textColor=colors.HexColor('#223044'))
    heading=ParagraphStyle('heading',parent=style,fontSize=12,leading=17,textColor=colors.HexColor('#163e63'))
    eqstyle=ParagraphStyle('eq',parent=style,fontSize=10.1,leading=16,leftIndent=10,
                          backColor=colors.HexColor('#f0f5fa'),borderPadding=5,spaceAfter=9)
    def clean(text):
        text=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',text)
        text=text.replace('\\(','').replace('\\)','').replace('**','')
        for a,b in [('\\ge0','≥0'),('\\ge','≥'),('\\le','≤'),('\\sum_h','Σ_h'),
                    ('\\sum x','Σx'),('\\sum','Σ'),('\\alpha','α'),('\\varepsilon','ε'),
                    ('\\infty','∞'),('\\in','∈')]:text=text.replace(a,b)
        text=re.sub(r'_\{([^}]+)\}',r'_\1',text)
        text=text.replace('\\{','{').replace('\\}','}')
        return html.escape(text).replace('\n','<br/>')
    story=[]
    for block in blocks:
        if block.startswith('\\['):
            tag=re.search(r'\\tag\{(M\d)\}',block).group(1)
            story.append(Paragraph(clean(equations[tag])+f'　({tag})',eqstyle))
            continue
        for para in block.strip().split('\n\n'):
            if not para.strip():continue
            if para.startswith('**4．'):story.append(PageBreak())
            if para.startswith('# '):
                story.append(Paragraph(clean(para[2:]),ParagraphStyle('title',parent=heading,fontSize=16,leading=23)))
                story.append(Paragraph('2026-11-20 · 建模手接手交付 · 条件资源分配模型',style))
            else:story.append(Paragraph(clean(para),heading if para.startswith('**') else style))
    def footer(canvas,doc):
        canvas.setFont(font_name,8);canvas.setFillColor(colors.grey)
        canvas.drawString(38,24,'来源：docs/MODEL_CHAIN.md；公式为本题自推定义与约束；数值正确不等于现实验证。')
        canvas.drawRightString(A4[0]-38,24,str(doc.page))
    doc=SimpleDocTemplate(str(dest),pagesize=A4,rightMargin=38,leftMargin=38,
                          topMargin=32,bottomMargin=39,title='核心方程推导：Keeping Phoenix Cool',author='Codex assisted modeling')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    from pypdf import PdfReader
    n=len(PdfReader(str(dest)).pages)
    if n!=2:raise RuntimeError(f'Expected two pages; got {n}. Adjust layout and render again.')
    print(str(dest));print('pages:',n)


if __name__=='__main__':main()
