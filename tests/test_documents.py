"""Reading PDF and Word documents into the structure the markdown parser understands, and the
deterministic sample-document writers."""
import time

import pytest
from bridge.core.parsers.documents import (
    UnreadableDocument,
    find_text_document,
    read_document_text,
)
from bridge.core.parsers.markdown import parse_markdown
from reportlab.pdfgen import canvas

from scripts.sample_docs import markdown_to_docx, markdown_to_pdf, write_xlsx
from tests.conftest import DEALS_DIR

SOURCES = ["deal_summary.md", "purchase_contract.md"]


def shape(text: str) -> dict:
    """What the deal parser depends on, with line numbers left out."""
    doc = parse_markdown(text)
    return {
        "title": doc.title,
        "plain": {k: v[0] for k, v in doc.plain.items()},
        "bullets": [(b.section, b.label, b.value) for b in doc.bullets],
        "tables": [(t.section, t.header, [r.cells for r in t.rows]) for t in doc.tables],
    }


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("deal", ["bronx_mf", "queens_mixed_use", "overleveraged_bk"])
@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_a_pdf_or_word_copy_reads_back_to_the_same_structure(tmp_path, deal, source, fmt):
    md = (DEALS_DIR / deal / source).read_text()
    path = tmp_path / f"doc.{fmt}"
    (markdown_to_pdf if fmt == "pdf" else markdown_to_docx)(md, path)
    assert shape(read_document_text(path)) == shape(md)


def test_markdown_and_text_files_pass_through(tmp_path):
    (tmp_path / "a.txt").write_text("# T\n- Label: 1\n")
    assert read_document_text(tmp_path / "a.txt") == "# T\n- Label: 1\n"


@pytest.mark.parametrize("fmt", ["pdf", "docx", "xlsx"])
def test_writers_are_deterministic(tmp_path, fmt):
    md = (DEALS_DIR / "bronx_mf" / "deal_summary.md").read_text()
    a, b = tmp_path / f"a.{fmt}", tmp_path / f"b.{fmt}"
    for path in (a, b):
        time.sleep(1.1)            # metadata has one-second resolution; cross the boundary
        if fmt == "pdf":
            markdown_to_pdf(md, path)
        elif fmt == "docx":
            markdown_to_docx(md, path)
        else:
            write_xlsx(path, ["unit", "rent"], [[101, 1320], [102, 1280]])
    assert a.read_bytes() == b.read_bytes()


def test_a_pdf_without_a_text_layer_is_refused_loudly(tmp_path):
    path = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(path))
    c.rect(50, 50, 100, 100)            # drawing only, like a scanned page
    c.save()
    with pytest.raises(UnreadableDocument, match="text layer"):
        read_document_text(path)


def test_a_corrupt_file_is_refused_loudly(tmp_path):
    for name in ("x.pdf", "x.docx"):
        (tmp_path / name).write_bytes(b"not a real document")
        with pytest.raises(UnreadableDocument):
            read_document_text(tmp_path / name)


def test_an_unsupported_type_is_refused(tmp_path):
    (tmp_path / "x.rtf").write_text("hello")
    with pytest.raises(UnreadableDocument, match="unsupported"):
        read_document_text(tmp_path / "x.rtf")


def test_find_text_document_prefers_listed_order_and_reports_what_it_tried(tmp_path):
    (tmp_path / "deal_summary.pdf").write_bytes(b"x")
    assert find_text_document(tmp_path, "deal_summary").name == "deal_summary.pdf"
    with pytest.raises(FileNotFoundError, match="purchase_contract"):
        find_text_document(tmp_path, "purchase_contract")
