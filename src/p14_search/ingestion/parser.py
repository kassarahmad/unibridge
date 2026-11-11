"""Safe document parsing (PDF, DOCX, HTML, TXT) into text blocks with page/section information.

Safety measures:
- size limit and type check on the actual bytes (magic numbers), not only on the declared media type;
- DOCX: zip bomb limits, macro-enabled packages rejected (vbaProject.bin / macroEnabled content types),
  XML parts with DOCTYPE/ENTITY declarations rejected (defusedxml), python-docx parses with resolve_entities=False;
- HTML: parsed with Python's html.parser (no network access, no external entities); scripts and styles dropped;
- PDF: text extraction only (pdfium via pypdfium2, pypdf as fallback); JavaScript, forms and embedded
  files are never executed or opened. pdfium is native code (Chrome's PDF engine, continuously fuzzed).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

import defusedxml.ElementTree as SafeET
from bs4 import BeautifulSoup, NavigableString, Tag
from defusedxml import DefusedXmlException

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
HTML = "text/html"
TXT = "text/plain"
SUPPORTED = (PDF, DOCX, HTML, TXT)

MAX_DOCX_UNCOMPRESSED = 100 * 1024 * 1024
MAX_DOCX_RATIO = 100
ARTICLE_RE = re.compile(r"^\s*((?:Art\.|Articolo)\s*\d+[\w-]*)\b", re.IGNORECASE)
# Article heading followed by an upper-case title on the same line, e.g. "ART. 7 REQUISITI DI MERITO" (regional calls).
TITLED_ARTICLE_RE = re.compile(r"^\s*(?:ART|Art)\.\s*\d+[\w-]*\s+(.{3,})$")
_HEADINGS = {"h1", "h2", "h3", "h4"}
_BLOCKS = {"p", "div", "li", "ul", "ol", "table", "tr", "td", "th", "section", "article", "blockquote", "pre"}
GU_HEADER_RE =re.compile(r"^\s*(GAZZETTA UFFICIALE DELLA REPUBBLICA ITALIANA.*|[—–-]\s*\d+\s*[—–-])\s*$")


class ParseError(ValueError):
    """The file is invalid, unsafe or unsupported. `status` is the HTTP status the API should return."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


@dataclass
class Block:
    text: str
    page: int | None = None
    section: str | None = None


def detect_media_type(data: bytes, declared: str) -> str:
    """Trust the bytes, not the declaration: a mismatch is rejected."""
    if data.startswith(b"%PDF-"):
        actual = PDF
    elif data.startswith(b"PK\x03\x04"):
        actual = DOCX
    else:
        head = data[:2048].lstrip().lower()
        actual = HTML if head.startswith((b"<!doctype html", b"<html")) or b"<body" in head else TXT
    if declared not in SUPPORTED:
        raise ParseError(f"unsupported media type: {declared}", status=415)
    if actual != declared:
        raise ParseError(f"declared media type {declared} does not match file content ({actual})", status=415)
    return actual


def parse(data: bytes, declared_media_type: str, max_bytes: int) -> list[Block]:
    if len(data) > max_bytes:
        raise ParseError(f"file too large: {len(data)} bytes > {max_bytes}", status=413)
    if not data:
        raise ParseError("empty file")
    media_type = detect_media_type(data, declared_media_type)
    blocks = {PDF: _parse_pdf, DOCX: _parse_docx, HTML: _parse_html, TXT: _parse_txt}[media_type](data)
    blocks = [b for b in blocks if b.text.strip()]
    if not blocks:
        raise ParseError("no extractable text (scanned or empty document?)")
    return blocks


# --- TXT -------------------------------------------------------------------------------------

def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _is_heading(line: str, prev_blank: bool) -> bool:
    s = line.strip()
    return prev_blank and 0 < len(s) <= 80 and s[0].isupper() and s[-1] not in ".;:,"


def _parse_txt(data: bytes) -> list[Block]:
    """Paragraphs separated by blank lines; 'Art. N' lines and short title-like lines start a section."""
    blocks: list[Block] = []
    section: str | None = None
    para: list[str] = []
    prev_blank = True

    def flush():
        if para:
            blocks.append(Block(" ".join(para), section=section))
            para.clear()

    for line in _decode(data).splitlines():
        s = line.strip()
        if not s:
            flush()
            prev_blank = True
            continue
        art = ARTICLE_RE.match(s)
        if art and len(s) <= 40:
            flush()
            section = art.group(1)
        elif _is_heading(s, prev_blank) and not s.startswith("- "):
            flush()
            section = s
        else:
            para.append(s)
        prev_blank = False
    flush()
    return blocks


# --- HTML ------------------------------------------------------------------------------------

def _parse_html(data: bytes) -> list[Block]:
    soup = BeautifulSoup(_decode(data), "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "iframe", "object", "embed"]):
        tag.decompose()
    # Normattiva exports keep the act in this container; elsewhere use <body>.
    root = soup.select_one("div.ContentHtmlExp") or soup.body or soup
    # Document-order walk: text accumulates in a buffer that is closed at block-element boundaries, so no
    # text is lost however deeply it is nested (Normattiva nests amendment <div>s inside <span>s).
    blocks: list[Block] = []
    buf: list[str] = []
    state = {"section": None, "article": False}

    def flush():
        text = re.sub(r"\s+", " ", " ".join(buf)).strip()
        buf.clear()
        if text:
            blocks.append(Block(text, section=state["section"]))

    def walk(node):
        for child in node.children:
            if type(child) is NavigableString:
                buf.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue  # comments, doctype, CDATA
            classes = child.get("class") or []
            if child.name in _HEADINGS:
                text = child.get_text(" ", strip=True)
                if text:
                    flush()
                    state["section"], state["article"] = text, "article-num-akn" in classes
                continue
            if "article-heading-akn" in classes:
                text = child.get_text(" ", strip=True)
                if text and state["article"]:
                    state["section"] = f"{state['section']} - {text}"
                continue
            if child.name in _BLOCKS:
                flush()
                walk(child)
                flush()
            else:
                walk(child)

    walk(root)
    flush()
    return blocks


# --- DOCX ------------------------------------------------------------------------------------

def _check_docx_package(data: bytes) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ParseError(f"corrupted DOCX: {exc}") from exc
    names = zf.namelist()
    if "word/document.xml" not in names or "[Content_Types].xml" not in names:
        raise ParseError("not a Word document (word/document.xml missing)")
    total = sum(i.file_size for i in zf.infolist())
    compressed = sum(i.compress_size for i in zf.infolist()) or 1
    if total > MAX_DOCX_UNCOMPRESSED or total / compressed > MAX_DOCX_RATIO:
        raise ParseError("DOCX rejected: decompressed size or compression ratio too large (zip bomb?)", status=413)
    content_types = zf.read("[Content_Types].xml")
    if any(n.lower().endswith("vbaproject.bin") for n in names) or b"macroEnabled" in content_types:
        raise ParseError("macro-enabled documents are not accepted", status=415)
    for name in names:
        if name.endswith((".xml", ".rels")):
            try:
                SafeET.fromstring(zf.read(name))
            except DefusedXmlException as exc:
                raise ParseError(f"DOCX rejected: unsafe XML in {name} ({type(exc).__name__})") from exc
            except SafeET.ParseError as exc:
                raise ParseError(f"corrupted DOCX: invalid XML in {name}") from exc


def _parse_docx(data: bytes) -> list[Block]:
    _check_docx_package(data)
    from docx import Document  # python-docx parses with resolve_entities=False

    doc = Document(io.BytesIO(data))
    blocks: list[Block] = []
    section: str | None = None
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if para.style is not None and para.style.name.lower().startswith(("heading", "title")):
            section = text
            continue
        blocks.append(Block(text, section=section))
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                blocks.append(Block(" | ".join(cells), section=section))
    return blocks


# --- PDF -------------------------------------------------------------------------------------

_GLYPH_RE = re.compile(r"/C(\d{2,3})")


def _repair_glyph_names(text: str) -> str:
    """Some old Gazzetta Ufficiale PDFs use fonts without a ToUnicode map: pypdf then returns glyph names
    like '/C76' (= character code 76, 'L'). When such names dominate the page, map them back to characters."""
    if len(_GLYPH_RE.findall(text)) * 3 < len(text) / 3:
        return text
    return _GLYPH_RE.sub(lambda m: chr(int(m.group(1))) if int(m.group(1)) < 256 else "", text)


def _clean_pdf_page(text: str) -> list[str]:
    text = _repair_glyph_names(text)
    lines = [ln for ln in text.splitlines() if not GU_HEADER_RE.match(ln)]
    text = "\n".join(lines)
    text = re.sub(r"(\w)[-­]\n(\w)", r"\1\2", text)  # de-hyphenate words split across lines
    return text.splitlines()


_STOPWORDS_RE = re.compile(r"\b(di|il|la|che|del|della|per|non|the|of|and)\b", re.IGNORECASE)


def _text_quality(text: str) -> float:
    """Share of common function words: low when the font encoding produced garbage."""
    return len(_STOPWORDS_RE.findall(text)) / max(len(text.split()), 1)


def _control_ratio(text: str) -> float:
    return sum(1 for ch in text if ord(ch) < 32 and ch not in "\r\n\t") / max(len(text), 1)


def _extract_pdf_pages(data: bytes) -> list[str]:
    """pdfium (robust with most font encodings) per page; when a page looks garbled, pypdf with glyph-name
    repair is tried too and the more readable text is kept."""
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    try:
        doc = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        msg = str(exc).lower()
        if "password" in msg or "security" in msg:
            raise ParseError("encrypted PDFs are not accepted", status=415) from exc
        raise ParseError(f"corrupted PDF: {exc}") from exc
    pages = []
    fallback = None
    for i in range(len(doc)):
        text = doc[i].get_textpage().get_text_range().replace("\r\n", "\n")
        text = re.sub("[\x02￾]\n?", "", text)  # pdfium marks soft hyphens at line breaks
        if _control_ratio(text) > 0.05 or (text.strip() and _text_quality(text) < 0.03):
            try:
                fallback = fallback or PdfReader(io.BytesIO(data))
                alt = _repair_glyph_names(fallback.pages[i].extract_text() or "")
                if _text_quality(alt) > 1.5 * _text_quality(text):  # only a clear improvement
                    text = alt
            except Exception:  # fallback is best effort; keep pdfium's text
                pass
        pages.append(text)
    doc.close()
    return pages


def _parse_pdf(data: bytes) -> list[Block]:
    pages = list(enumerate(_extract_pdf_pages(data), start=1))

    blocks: list[Block] = []
    section: str | None = None
    for page_no, raw in pages:
        para: list[str] = []
        for line in _clean_pdf_page(raw):
            s = line.strip()
            if not s:
                continue
            art = ARTICLE_RE.match(s)
            if art and len(s) <= 40:
                if para:
                    blocks.append(Block(" ".join(para), page=page_no, section=section))
                    para = []
                section = art.group(1).rstrip(".")
                continue
            titled = TITLED_ARTICLE_RE.match(s)
            if titled and len(s) <= 160 and titled.group(1) == titled.group(1).upper() and sum(c.isalpha() for c in titled.group(1)) >= 3:
                if para:
                    blocks.append(Block(" ".join(para), page=page_no, section=section))
                    para = []
                section = s
                continue
            para.append(s)
            # A line ending a sentence closes the paragraph: keeps blocks short for chunking.
            if s.endswith((".", ";", ":")) and sum(len(p) for p in para) > 300:
                blocks.append(Block(" ".join(para), page=page_no, section=section))
                para = []
        if para:
            blocks.append(Block(" ".join(para), page=page_no, section=section))
    return blocks
