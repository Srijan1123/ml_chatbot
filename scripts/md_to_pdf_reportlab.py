from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
import markdown

infile = 'internship_defense_RAG.md'
outfile = 'internship_defense_RAG_reportlab.pdf'

with open(infile, 'r', encoding='utf-8') as f:
    md = f.read()

html = markdown.markdown(md)

styles = getSampleStyleSheet()
styleN = styles['Normal']
styleH = styles['Heading1']

# Simple conversion: split HTML by paragraphs
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'html.parser')

doc = SimpleDocTemplate(outfile, pagesize=A4,
                        rightMargin=20*mm, leftMargin=20*mm,
                        topMargin=20*mm, bottomMargin=20*mm)

flow = []
for elem in soup.descendants:
    if elem.name == 'h1':
        flow.append(Paragraph(elem.get_text(), ParagraphStyle('h1', fontSize=18, leading=22)))
        flow.append(Spacer(1,6))
    elif elem.name == 'h2':
        flow.append(Paragraph(elem.get_text(), ParagraphStyle('h2', fontSize=14, leading=18)))
        flow.append(Spacer(1,4))
    elif elem.name == 'ul':
        for li in elem.find_all('li'):
            flow.append(Paragraph('• ' + li.get_text(), styleN))
    elif elem.name == 'p':
        flow.append(Paragraph(elem.get_text(), styleN))
        flow.append(Spacer(1,4))

if not flow:
    flow.append(Paragraph('No content', styleN))

doc.build(flow)
print('WROTE', outfile)
