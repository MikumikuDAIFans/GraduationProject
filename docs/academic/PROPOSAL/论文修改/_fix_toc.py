import sys
sys.stdout.reconfigure(encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document('docs/academic/PROPOSAL/论文修改/毕业设计-张嘉洋_项目现状对齐修订版.docx')

body = doc.element.body

# Step 1: Find and remove current TOC field paragraph
for i, p in enumerate(doc.paragraphs):
    if p.style.name == 'ThesisTOC' and '请在Word中' in p.text:
        body.remove(p._element)
        print(f'Removed broken TOC field at [{i}]')
        break

# Step 2: Find the TOC heading
toc_heading_elem = None
for i, p in enumerate(doc.paragraphs):
    if '目' in p.text and '次' in p.text and p.style.name == 'Normal':
        toc_heading_elem = p._element
        print(f'Found TOC heading at [{i}]')
        break

if toc_heading_elem is None:
    print('ERROR: TOC heading not found')
    sys.exit(1)

# Step 3: Create TOC field paragraph with fallback content
# The TOC field will show placeholder text, but when user right-clicks
# and selects "Update Field", it will generate the real TOC

toc_entries = [
    ('摘要', 'I', 'ThesisTOC'),
    ('Abstract', 'II', 'ThesisTOC'),
    ('1 引言', '1', 'ThesisTOC'),
    ('1.1 研究背景与意义', '1', 'ThesisTOC'),
    ('1.2 国内外研究现状', '1', 'ThesisTOC'),
    ('1.3 研究内容与目标', '3', 'ThesisTOC'),
    ('1.4 论文结构安排', '3', 'ThesisTOC'),
    ('2 相关技术基础', '4', 'ThesisTOC'),
    ('2.1 多智能体系统理论', '4', 'ThesisTOC'),
    ('2.2 大语言模型技术', '5', 'ThesisTOC'),
    ('2.3 工作流引擎技术', '6', 'ThesisTOC'),
    ('2.4 前端响应式设计技术', '7', 'ThesisTOC'),
    ('3 系统需求分析与总体设计', '9', 'ThesisTOC'),
    ('3.1 需求分析', '9', 'ThesisTOC'),
    ('3.2 系统总体架构设计', '10', 'ThesisTOC'),
    ('3.3 多Agent协同机制设计', '13', 'ThesisTOC'),
    ('3.4 数据库设计', '20', 'ThesisTOC'),
    ('4 系统详细设计与实现', '23', 'ThesisTOC'),
    ('4.1 后端架构设计与实现', '23', 'ThesisTOC'),
    ('4.2 前端界面设计与实现', '26', 'ThesisTOC'),
    ('4.3 多Agent协同流程实现', '30', 'ThesisTOC'),
    ('4.4 性能优化策略实现', '34', 'ThesisTOC'),
    ('5 系统测试与结果分析', '36', 'ThesisTOC'),
    ('5.1 测试环境与测试方法', '36', 'ThesisTOC'),
    ('5.2 功能测试结果', '36', 'ThesisTOC'),
    ('5.3 性能测试结果', '38', 'ThesisTOC'),
    ('6 结论与展望', '41', 'ThesisTOC'),
    ('6.1 研究工作总结', '41', 'ThesisTOC'),
    ('6.2 主要创新点', '41', 'ThesisTOC'),
    ('6.3 不足与改进方向', '42', 'ThesisTOC'),
    ('6.4 未来研究展望', '42', 'ThesisTOC'),
    ('参考文献', '43', 'ThesisTOC'),
    ('致谢', '44', 'ThesisTOC'),
    ('附录A 系统实现补充说明', '45', 'ThesisTOC'),
    ('附录B 数据实体补充说明', '52', 'ThesisTOC'),
    ('附录C 多智能体核心算法补充说明', '54', 'ThesisTOC'),
    ('附录D 项目实现对齐说明', '58', 'ThesisTOC'),
]

# Insert a single paragraph with TOC field
# The field instruction tells Word to generate TOC from heading levels 1-3
toc_para = OxmlElement('w:p')

# Paragraph properties
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

# Fallback content: the original TOC entries as plain text
# These will be shown until the user updates the field in Word
for entry_text, page_num, style_name in toc_entries:
    r_entry = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    rStyle = OxmlElement('w:rStyle')
    rStyle.set(qn('w:val'), 'TocHeading' if entry_text in ('摘要', 'Abstract') else 'Toc1' if not '.' in entry_text.split('\t')[0] else 'Toc2')
    rPr.append(rStyle)
    r_entry.append(rPr)

    t = OxmlElement('w:t')
    t.set(qn('xml:space'), 'preserve')
    t.text = f'{entry_text}\t{page_num}\n'
    r_entry.append(t)
    toc_para.append(r_entry)

# Field end
r_end = OxmlElement('w:r')
fld_end = OxmlElement('w:fldChar')
fld_end.set(qn('w:fldCharType'), 'end')
r_end.append(fld_end)
toc_para.append(r_end)

# Insert after heading
toc_heading_elem.addnext(toc_para)

print('TOC field with fallback content inserted')
print('When you open in Word: right-click the TOC area -> "Update Field" -> "Update entire table"')

doc.save('docs/academic/PROPOSAL/论文修改/毕业设计-张嘉洋_项目现状对齐修订版.docx')
print('Saved successfully')
