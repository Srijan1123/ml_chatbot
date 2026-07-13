from fpdf import FPDF
import textwrap

infile = 'internship_defense_RAG.md'
outfile = 'internship_defense_RAG.pdf'

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()

pdf.set_font('Arial', size=12)

with open(infile, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for raw in lines:
    line = raw.rstrip('\n')
    if line.startswith('# '):
        pdf.set_font('Arial', 'B', 16)
        pdf.multi_cell(0, 8, line[2:].strip())
        pdf.ln(2)
        pdf.set_font('Arial', size=12)
    elif line.startswith('## '):
        pdf.set_font('Arial', 'B', 14)
        pdf.multi_cell(0, 7, line[3:].strip())
        pdf.set_font('Arial', size=12)
    elif line.startswith('- '):
        content = u"\u2022 " + line[2:].strip()
        pdf.multi_cell(0, 6, content)
    elif line.startswith('> '):
        pdf.set_font('Arial', 'I', 12)
        pdf.multi_cell(0,6,line[2:].strip())
        pdf.set_font('Arial', size=12)
    elif line.strip() == '---':
        pdf.ln(4)
    elif line.strip() == '':
        pdf.ln(3)
    else:
        wrapped = textwrap.fill(line, 95)
        pdf.multi_cell(0,6, wrapped)

pdf.output(outfile)
print('WROTE', outfile)
