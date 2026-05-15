"""
Complete format fix for the thesis document.
Fixes:
1. Add outlineLvl to ThesisHeading1/2/3 styles (critical for TOC)
2. Fix page setup (header/footer distance to 0.8cm)
3. Rebuild TOC with a clean Word field (no fallback text)
4. Verify all styles match template specifications
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from docx import Document
from docx.oxml.ns import qn, nsdecls
from docx.oxml import OxmlElement, parse_xml
from docx.shared import Pt, Emu, Cm

DOC_PATH = 'docs/academic/PROPOSAL/论文修改/毕业设计-张嘉洋_项目现状对齐修订版.docx'

doc = Document(DOC_PATH)
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# ============================================================
# STEP 1: Fix style definitions - add outlineLvl + verify fonts
# ============================================================
print('='*60)
print('STEP 1: Fixing style definitions')
print('='*60)

style_fixes = {
    'ThesisHeading1': {
        'outlineLvl': 0,
        'font_ascii': 'Times New Roman',
        'font_eastAsia': '黑体',
        'font_cs': 'Times New Roman',
        'size': 30,  # half-points (15pt)
        'bold': True,
        'alignment': 'left',
        'spacing_line': 360,  # 1.5x auto
        'spacing_before': 156,  # 7.8pt
        'spacing_after': 156,
        'page_break_before': True,
        'keep_next': True,
    },
    'ThesisHeading2': {
        'outlineLvl': 1,
        'font_ascii': 'Times New Roman',
        'font_eastAsia': '黑体',
        'font_cs': 'Times New Roman',
        'size': 28,  # 14pt
        'bold': True,
        'alignment': 'left',
        'spacing_line': 360,
        'spacing_before': 120,  # 6pt
        'spacing_after': 60,    # 3pt
        'page_break_before': False,
        'keep_next': True,
    },
    'ThesisHeading3': {
        'outlineLvl': 2,
        'font_ascii': 'Times New Roman',
        'font_eastAsia': '黑体',
        'font_cs': 'Times New Roman',
        'size': 24,  # 12pt
        'bold': False,
        'alignment': 'left',
        'spacing_line': 360,
        'spacing_before': 80,   # 4pt
        'spacing_after': 40,    # 2pt
        'page_break_before': False,
        'keep_next': True,
    },
}

for style_name, spec in style_fixes.items():
    style = doc.styles[style_name]
    el = style.element

    # --- Fix font (rPr) ---
    rPr = el.find(qn('w:rPr'))
    if rPr is None:
        rPr = OxmlElement('w:rPr')
        el.append(rPr)

    # Fonts
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    rFonts.set(qn('w:ascii'), spec['font_ascii'])
    rFonts.set(qn('w:hAnsi'), spec['font_ascii'])
    rFonts.set(qn('w:eastAsia'), spec['font_eastAsia'])
    rFonts.set(qn('w:cs'), spec['font_cs'])

    # Size
    sz = rPr.find(qn('w:sz'))
    if sz is None:
        sz = OxmlElement('w:sz')
        rPr.append(sz)
    sz.set(qn('w:val'), str(spec['size']))

    szCs = rPr.find(qn('w:szCs'))
    if szCs is None:
        szCs = OxmlElement('w:szCs')
        rPr.append(szCs)
    szCs.set(qn('w:val'), str(spec['size']))

    # Bold
    b = rPr.find(qn('w:b'))
    if spec['bold']:
        if b is None:
            b = OxmlElement('w:b')
            rPr.append(b)
    else:
        if b is not None:
            rPr.remove(b)

    # --- Fix paragraph (pPr) ---
    pPr = el.find(qn('w:pPr'))
    if pPr is None:
        pPr = OxmlElement('w:pPr')
        el.insert(0, pPr)

    # outlineLvl (critical for TOC!)
    outlineLvl = pPr.find(qn('w:outlineLvl'))
    if outlineLvl is None:
        outlineLvl = OxmlElement('w:outlineLvl')
        pPr.append(outlineLvl)
    outlineLvl.set(qn('w:val'), str(spec['outlineLvl']))

    # Alignment
    jc = pPr.find(qn('w:jc'))
    if jc is None:
        jc = OxmlElement('w:jc')
        pPr.append(jc)
    jc.set(qn('w:val'), spec['alignment'])

    # Spacing
    spacing = pPr.find(qn('w:spacing'))
    if spacing is None:
        spacing = OxmlElement('w:spacing')
        pPr.append(spacing)
    spacing.set(qn('w:before'), str(spec['spacing_before']))
    spacing.set(qn('w:after'), str(spec['spacing_after']))
    spacing.set(qn('w:line'), str(spec['spacing_line']))
    spacing.set(qn('w:lineRule'), 'auto')

    # Page break before
    pb = pPr.find(qn('w:pageBreakBefore'))
    if spec['page_break_before']:
        if pb is None:
            pb = OxmlElement('w:pageBreakBefore')
            pPr.append(pb)
    else:
        if pb is not None:
            pPr.remove(pb)

    # Keep next
    kn = pPr.find(qn('w:keepNext'))
    if spec['keep_next']:
        if kn is None:
            kn = OxmlElement('w:keepNext')
            pPr.append(kn)
    else:
        if kn is not None:
            pPr.remove(kn)

    print(f'  Fixed style: {style_name} (outlineLvl={spec["outlineLvl"]})')

# ============================================================
# STEP 2: Fix page setup - header/footer distance
# ============================================================
print()
print('='*60)
print('STEP 2: Fixing page setup')
print('='*60)

for i, section in enumerate(doc.sections):
    # Header/footer distance: 0.8cm = 457200 EMU
    section.header_distance = Cm(0.8)
    section.footer_distance = Cm(0.8)
    print(f'  Section {i}: header/footer distance set to 0.8cm')

# ============================================================
# STEP 3: Rebuild TOC - clean field, no fallback text
# ============================================================
print()
print('='*60)
print('STEP 3: Rebuilding TOC')
print('='*60)

body = doc.element.body

# Find and remove current TOC paragraph (ThesisTOC style)
toc_para = None
for i, p in enumerate(doc.paragraphs):
    if p.style.name == 'ThesisTOC':
        toc_para = p
        print(f'  Found existing TOC at paragraph [{i}]')
        break

if toc_para is not None:
    body.remove(toc_para._element)
    print('  Removed old TOC paragraph')

# Find the TOC heading
toc_heading = None
for i, p in enumerate(doc.paragraphs):
    if '目' in p.text and '次' in p.text:
        toc_heading = p
        print(f'  Found TOC heading at paragraph [{i}]: "{p.text}"')
        break

if toc_heading is None:
    print('  ERROR: TOC heading not found!')
    sys.exit(1)

# Create a clean TOC field paragraph
toc_para = OxmlElement('w:p')

# Paragraph properties with ThesisTOC style
pPr = OxmlElement('w:pPr')
pStyle = OxmlElement('w:pStyle')
pStyle.set(qn('w:val'), 'ThesisTOC')
pPr.append(pStyle)
toc_para.append(pPr)

# Field begin
r_begin = OxmlElement('w:r')
fld_begin = OxmlElement('w:fldChar')
fld_begin.set(qn('w:fldCharType'), 'begin')
r_begin.append(fld_begin)
toc_para.append(r_begin)

# Field instruction
r_instr = OxmlElement('w:r')
instrText = OxmlElement('w:instrText')
instrText.set(qn('xml:space'), 'preserve')
instrText.text = ' TOC \\o "1-3" \\h \\z \\u '
r_instr.append(instrText)
toc_para.append(r_instr)

# Field separate
r_sep = OxmlElement('w:r')
fld_sep = OxmlElement('w:fldChar')
fld_sep.set(qn('w:fldCharType'), 'separate')
r_sep.append(fld_sep)
toc_para.append(r_sep)

# Minimal placeholder text (will be replaced when user updates field in Word)
r_placeholder = OxmlElement('w:r')
rPr_ph = OxmlElement('w:rPr')
rStyle_ph = OxmlElement('w:rStyle')
rStyle_ph.set(qn('w:val'), 'Toc1')
rPr_ph.append(rStyle_ph)
r_placeholder.append(rPr_ph)
t_ph = OxmlElement('w:t')
t_ph.set(qn('xml:space'), 'preserve')
t_ph.text = '请更新目录'
r_placeholder.append(t_ph)
toc_para.append(r_placeholder)

# Field end
r_end = OxmlElement('w:r')
fld_end = OxmlElement('w:fldChar')
fld_end.set(qn('w:fldCharType'), 'end')
r_end.append(fld_end)
toc_para.append(r_end)

# Insert after heading
toc_heading._element.addnext(toc_para)
print('  Inserted clean TOC field (update in Word to generate)')

# ============================================================
# STEP 4: Save
# ============================================================
print()
print('='*60)
print('STEP 4: Saving document')
print('='*60)
doc.save(DOC_PATH)
print('  Saved successfully')

# ============================================================
# STEP 5: Verify
# ============================================================
print()
print('='*60)
print('STEP 5: Verification')
print('='*60)

# Reload to verify
doc2 = Document(DOC_PATH)

# 4a. Check outlineLvl
print()
print('--- Style outlineLvl ---')
for sn in ['ThesisHeading1', 'ThesisHeading2', 'ThesisHeading3']:
    s = doc2.styles[sn]
    ol = s.element.find(f'.//{qn("w:outlineLvl")}')
    val = ol.get(qn('w:val')) if ol is not None else 'MISSING'
    print(f'  {sn}: outlineLvl = {val}')

# 4b. Check TOC field
print()
print('--- TOC field ---')
for i, p in enumerate(doc2.paragraphs):
    if p.style.name == 'ThesisTOC':
        fld_chars = p._element.findall(f'.//{qn("w:fldChar")}')
        instrs = p._element.findall(f'.//{qn("w:instrText")}')
        runs = p._element.findall(f'{qn("w:r")}')
        print(f'  Paragraph [{i}]: style={p.style.name}')
        print(f'    fldChar count: {len(fld_chars)}')
        print(f'    instrText: {instrs[0].text if instrs else "NONE"}')
        print(f'    total runs: {len(runs)}')
        # Check for fallback text runs (should be minimal)
        text_runs = [r for r in runs if r.find(qn('w:t')) is not None and r.find(qn('w:fldChar')) is None]
        print(f'    text runs: {len(text_runs)}')
        break

# 4c. Check heading fonts (sample)
print()
print('--- Sample heading fonts ---')
samples = {'ThesisHeading1': None, 'ThesisHeading2': None, 'ThesisHeading3': None}
for p in doc2.paragraphs:
    sn = p.style.name
    if sn in samples and samples[sn] is None and p.text.strip():
        samples[sn] = p
        rPr = p.runs[0]._element.find(qn('w:rPr')) if p.runs else None
        if rPr is not None:
            rFonts = rPr.find(qn('w:rFonts'))
            sz = rPr.find(qn('w:sz'))
            b = rPr.find(qn('w:b'))
            font_ea = rFonts.get(qn('w:eastAsia')) if rFonts is not None else '?'
            font_ascii = rFonts.get(qn('w:ascii')) if rFonts is not None else '?'
            size = sz.get(qn('w:val')) if sz is not None else '?'
            bold = b is not None
            print(f'  {sn}: "{p.text[:30]}" | eastAsia={font_ea} ascii={font_ascii} size={size} bold={bold}')

# 4d. Check page setup
print()
print('--- Page setup ---')
for i, section in enumerate(doc2.sections):
    print(f'  Section {i}: header_dist={section.header_distance} footer_dist={section.footer_distance}')

# 4e. Check table count
print()
print(f'--- Tables: {len(doc2.tables)} total ---')

print()
print('='*60)
print('DONE. Please open the document in Word and:')
print('  1. Right-click the TOC area -> "Update Field" -> "Update entire table"')
print('  2. Verify headings appear in the TOC')
print('='*60)
