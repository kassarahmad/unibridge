"""Build the UniBridge technical report as Word and PDF from docs/REPORT_UNIBRIDGE.md.

The Markdown file stays the single source (its numbers are checked by eval/check_doc_numbers.py); this script only
lays it out: title page, table of contents, headings, tables, figures, page numbers. The PDF is exported by the
locally installed Microsoft Word (COM), which also fills the table of contents.

Usage:
    python scripts/build_report_docx.py
Outputs: deliverables/UniBridge_Technical_Report_Ahmad_Kassar.docx and .pdf
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "REPORT_UNIBRIDGE.md"
OUT = ROOT / "deliverables" / "UniBridge_Technical_Report_Ahmad_Kassar.docx"
LOGO = ROOT / "docs" / "images" / "unicam_logo.png"
NAVY = RGBColor(0x14, 0x20, 0x3D)
GREY = RGBColor(0x5B, 0x64, 0x72)
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*\s][^*]*\*)")


def field(paragraph, code: str, size: float | None = None) -> None:
    """Insert a Word field (PAGE, TOC ...); Word computes it when the document is opened or exported."""
    run = paragraph.add_run()
    if size:
        run.font.size = Pt(size)
    for kind, text in (("begin", None), (None, code), ("separate", None), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def orient(section, landscape: bool) -> None:
    w, h = sorted((section.page_width, section.page_height))
    section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = (h, w) if landscape else (w, h)


def add_inline(paragraph, text: str, size: float | None = None) -> None:
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            continue
        elif part.startswith("["):
            run = paragraph.add_run(re.match(r"\[([^\]]+)\]", part).group(1))
        elif part.startswith("*") and part.endswith("*"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(part)
        if size:
            run.font.size = Pt(size)


def setup_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12
    for name, size, before in (("Heading 1", 16, 18), ("Heading 2", 13, 12), ("Heading 3", 11.5, 10)):
        st = doc.styles[name]
        st.font.name = "Cambria"
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = NAVY
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(4)
        st.paragraph_format.keep_with_next = True
        rpr = st.element.get_or_add_rPr()
        fonts = rpr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            rpr.append(fonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs"):
            fonts.set(qn(attr), "Cambria")


def title_page(doc: Document, title: str, subtitle: str) -> None:
    if LOGO.exists():
        p = doc.add_paragraph()
        p.add_run().add_picture(str(LOGO), width=Cm(3))
    p = doc.add_paragraph()
    r = p.add_run("University of Camerino")
    r.bold = True
    p.add_run("\nMSc Computer Science (Artificial Intelligence) · Complex Systems Design").font.color.rgb = GREY
    for _ in range(5):
        doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run(title)
    r.font.name = "Cambria"
    r.font.size = Pt(26)
    r.bold = True
    r.font.color.rgb = NAVY
    p = doc.add_paragraph()
    r = p.add_run(subtitle)
    r.font.size = Pt(14)
    r.font.color.rgb = GREY
    for _ in range(8):
        doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run("Ahmad Kassar")
    r.bold = True
    r.font.size = Pt(12)
    p.add_run("\nProfessor: Flavio Corradini\nNovember 2026").font.size = Pt(11)
    p.runs[-1].add_break(WD_BREAK.PAGE)
    h = doc.add_paragraph()
    r = h.add_run("Contents")
    r.font.name = "Cambria"
    r.font.size = Pt(16)
    r.bold = True
    r.font.color.rgb = NAVY
    field(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
    doc.add_section(WD_SECTION.NEW_PAGE)


def table(doc: Document, rows: list[list[str]]) -> None:
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Light Grid Accent 1" if "Light Grid Accent 1" in [s.name for s in doc.styles] else "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            c = t.cell(i, j)
            c.text = ""
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            add_inline(p, cell, size=9.5)
            if i == 0:
                for r in p.runs:
                    r.bold = True
    doc.add_paragraph()


def build() -> Path:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.3)
        s.top_margin = s.bottom_margin = Cm(2.2)
    setup_styles(doc)
    title = lines[0].lstrip("# ").strip()
    subtitle = lines[1].lstrip("# ").strip()
    name, _, rest = title.partition(" - ")
    title_page(doc, name, (rest[:1].upper() + rest[1:]) if rest else subtitle)
    footer = doc.sections[-1].footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = fp.add_run("Ahmad Kassar · UniBridge · page ")
    run.font.size = Pt(8.5)
    run.font.color.rgb = GREY
    field(fp, "PAGE", size=8.5)

    i, para = 2, []

    def flush():
        if para:
            add_inline(doc.add_paragraph(), " ".join(para))
            para.clear()

    while i < len(lines):
        line = lines[i]
        if line.startswith("<!--") or not line.strip():
            flush()
        elif line.startswith("## "):
            flush()
            doc.add_paragraph(line[3:].strip(), style="Heading 1")
        elif line.startswith("### "):
            flush()
            doc.add_paragraph(line[4:].strip(), style="Heading 2")
        elif line.startswith("!["):
            flush()
            alt, path = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line).groups()
            img = (SRC.parent / path).resolve()
            w, h = Image.open(img).size
            wide = w / h > 2.5  # very wide figures (the BPMN model) get a landscape page of their own
            if wide:
                orient(doc.add_section(WD_SECTION.NEW_PAGE), landscape=True)
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # tall figures are limited by height (17 cm), wide ones by the text width
            p.add_run().add_picture(str(img), width=Cm(24.5 if wide else min(15.5, 17 * w / h)))
            cap = doc.add_paragraph()
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = cap.add_run(alt)
            r.italic = True
            r.font.size = Pt(9)
            r.font.color.rgb = GREY
            if wide:
                orient(doc.add_section(WD_SECTION.NEW_PAGE), landscape=False)
        elif line.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            table(doc, rows)
            continue
        elif re.match(r"^(- |\d+\. )", line):
            flush()
            numbered = not line.startswith("- ")
            text = re.sub(r"^(- |\d+\. )", "", line)
            while i + 1 < len(lines) and lines[i + 1].startswith("  ") and lines[i + 1].strip():
                i += 1
                text += " " + lines[i].strip()
            p = doc.add_paragraph(style="List Number" if numbered else "List Bullet")
            p.paragraph_format.space_after = Pt(3)
            add_inline(p, text)
        else:
            para.append(line.strip())
        i += 1
    flush()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    return OUT


def export_pdf(docx: Path) -> Path:
    """Open in Word, update the fields (table of contents, page numbers), save, export PDF."""
    pdf = docx.with_suffix(".pdf")
    script = (
        "$w = New-Object -ComObject Word.Application; $w.Visible = $false; "
        f"$d = $w.Documents.Open('{docx}'); $d.Fields.Update() | Out-Null; "
        "foreach ($t in $d.TablesOfContents) { $t.Update() }; $d.Save(); "
        f"$d.ExportAsFixedFormat('{pdf}', 17); $d.Close(); $w.Quit()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=300)
    return pdf


def main() -> int:
    docx = build()
    print(f"wrote {docx.relative_to(ROOT).as_posix()}")
    print(f"wrote {export_pdf(docx).relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
