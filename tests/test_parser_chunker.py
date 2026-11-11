import pytest

from fixtures import make_docx, make_html, make_pdf, make_txt, rewrite_docx
from p14_search.ingestion.chunker import TARGET_CHARS, chunk, document_id, document_version
from p14_search.ingestion.parser import DOCX, HTML, PDF, TXT, Block, ParseError, parse

MAX = 5 * 1024 * 1024
LONG = "Il lavoratore ha diritto alla disconnessione dalle 19:00 alle 8:00. " * 40


def test_txt_sections_from_article_lines():
    data = make_txt("LEGGE TEST\n\nArt. 1\n\nPrimo comma del primo articolo.\n\nArt. 2\n\nSecondo articolo, testo.\n")
    blocks = parse(data, TXT, MAX)
    assert [(b.section, b.text) for b in blocks][-2:] == [("Art. 1", "Primo comma del primo articolo."), ("Art. 2", "Secondo articolo, testo.")]


def test_html_drops_scripts_and_keeps_headings():
    data = make_html("<h2>Art. 18</h2><div>Lavoro agile: modalità di esecuzione.</div><p>Altro testo.</p>")
    blocks = parse(data, HTML, MAX)
    assert all("alert" not in b.text for b in blocks)
    assert blocks[0].section == "Art. 18" and "Lavoro agile" in blocks[0].text


def test_html_keeps_text_nested_in_inline_elements():
    # Normattiva markup: amendment <div> inside the comma <span>, article heading as a sibling div.
    data = make_html(
        '<div class="ContentHtmlExp"><h2 class="article-num-akn">Art. 4</h2>'
        '<div class="article-heading-akn">(Impianti audiovisivi)</div>'
        '<span class="art-just-text-akn">Testo originale del comma. <div class="ins-akn">((Testo aggiunto.))</div></span></div>'
    )
    blocks = parse(data, HTML, MAX)
    joined = " ".join(b.text for b in blocks)
    assert "Testo originale del comma." in joined and "((Testo aggiunto.))" in joined
    assert {b.section for b in blocks} == {"Art. 4 - (Impianti audiovisivi)"}


def test_pdf_glyph_name_repair():
    from p14_search.ingestion.parser import _repair_glyph_names

    assert _repair_glyph_names("/C76/C69/C71/C71/C69 /C52") == "LEGGE 4"
    assert _repair_glyph_names("testo normale /C76 raro") == "testo normale /C76 raro"


def test_docx_headings_become_sections():
    data = make_docx([("h", "Articolo 3 - Giornate"), ("p", "Massimo 10 giornate al mese.")])
    blocks = parse(data, DOCX, MAX)
    assert blocks == [Block("Massimo 10 giornate al mese.", section="Articolo 3 - Giornate")]


def test_pdf_keeps_page_numbers():
    data = make_pdf(["Art. 1\nPrima pagina, testo.", "Seconda pagina, altro testo."])
    blocks = parse(data, PDF, MAX)
    assert {b.page for b in blocks} == {1, 2}
    assert blocks[0].section == "Art. 1"


def test_pdf_long_upper_case_article_titles_start_sections():
    # Regional calls (ERDIS bando): "ART. 7 REQUISITI DI MERITO" on one line, longer than a bare "Art. 7".
    data = make_pdf(["ART. 7 REQUISITI DI MERITO E ALTRE CONDIZIONI PER IL CONCORSO\nTesto del settimo articolo.\n"
                     "Art. 10 TERMINI E MODALITA PER LA PRESENTAZIONE DELLA DOMANDA\nTesto del decimo articolo.\n"
                     "Art. 11 prevede che lo studente presenti i documenti entro il termine indicato nel bando."])
    blocks = parse(data, PDF, MAX)
    assert [b.section for b in blocks] == [
        "ART. 7 REQUISITI DI MERITO E ALTRE CONDIZIONI PER IL CONCORSO",
        "Art. 10 TERMINI E MODALITA PER LA PRESENTAZIONE DELLA DOMANDA",
    ]
    assert "Art. 11 prevede" in blocks[-1].text  # a sentence that starts with "Art." is not a heading


@pytest.mark.parametrize(
    "data, media_type, status",
    [
        (b"%PDF-1.7\nthis is not really a pdf", PDF, 422),  # malformed PDF
        (b"PK\x03\x04garbage-not-a-zip", DOCX, 422),  # corrupted DOCX
        (make_txt("ciao"), PDF, 415),  # declared type does not match content
        (make_txt("ciao"), "application/x-msdownload", 415),  # unsupported type
        (b"x" * (MAX + 1), TXT, 413),  # too large
        (b"", TXT, 422),  # empty
    ],
)
def test_invalid_files_are_rejected(data, media_type, status):
    with pytest.raises(ParseError) as err:
        parse(data, media_type, MAX)
    assert err.value.status == status


def test_docx_with_macros_is_rejected():
    data = rewrite_docx(make_docx([("p", "testo")]), add={"word/vbaProject.bin": b"\x00macro"})
    with pytest.raises(ParseError) as err:
        parse(data, DOCX, MAX)
    assert err.value.status == 415


def test_docx_with_external_entity_is_rejected():
    xxe = (
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///c:/windows/win.ini">]>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p></w:body></w:document>"
    )
    data = rewrite_docx(make_docx([("p", "testo")]), replace={"word/document.xml": xxe})
    with pytest.raises(ParseError, match="unsafe XML"):
        parse(data, DOCX, MAX)


def _chunks(data: bytes):
    blocks = parse(data, TXT, MAX)
    return chunk(blocks, document_id("d1b", "x"), document_version(data))


def test_same_content_gives_same_ids():
    data = make_txt("Art. 1\n\n" + LONG + "\n\nArt. 2\n\nBreve.\n")
    _, a = _chunks(data)
    _, b = _chunks(data)
    assert [c.passage_id for c in a] == [c.passage_id for c in b]
    assert len({c.passage_id for c in a}) == len(a)


def test_changed_content_changes_version_and_ids():
    v1 = make_txt("Art. 1\n\nTesto originale.\n")
    v2 = make_txt("Art. 1\n\nTesto modificato.\n")
    assert document_version(v1) != document_version(v2)
    assert _chunks(v1)[1][0].passage_id != _chunks(v2)[1][0].passage_id


def test_chunks_respect_sections_size_and_offsets():
    data = make_txt("Art. 1\n\n" + LONG + "\n\nArt. 2\n\nBreve.\n")
    text, chunks = _chunks(data)
    assert {c.section for c in chunks} == {"Art. 1", "Art. 2"}
    assert all(len(c.text) <= TARGET_CHARS + 1 for c in chunks)
    for c in chunks:  # offsets point into the parsed text (citation precision)
        assert c.text == text[c.char_start : c.char_end].strip()
    assert chunks[-1].section == "Art. 2" and chunks[-1].text == "Breve."


def test_encrypted_pdf_is_rejected():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_encryption(owner_password="owner", user_password="secret")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.cell(text="riservato")
    with pytest.raises(ParseError) as err:
        parse(bytes(pdf.output()), PDF, MAX)
    assert err.value.status == 415
