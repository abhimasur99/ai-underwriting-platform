"""Write sample deal documents as PDF, Word or Excel from the same source the markdown uses.

Everything here is deterministic (fixed PDF and zip metadata) so `make fixtures` followed by
`git diff` still proves nothing drifted. Sample data only.
"""
import re
import zipfile
from datetime import datetime
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

FIXED_TIME = datetime(2026, 1, 1, 9, 0, 0)
ZIP_TIME = (2026, 1, 1, 9, 0, 0)
LEFT, RIGHT_COL, TOP, BOTTOM, WIDTH = 54, 380, 740, 60, 500
BODY, SECTION, TITLE, LINE = 10, 12.5, 16, 14


def freeze_zip(path: Path) -> None:
    """Rewrite an OOXML file (docx, xlsx) uncompressed, with fixed entry timestamps and fixed
    created/modified properties (openpyxl stamps the current time into them on every save)."""
    stamp = FIXED_TIME.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    with zipfile.ZipFile(path) as src:
        entries = [(info.filename, src.read(info.filename)) for info in src.infolist()]
    pattern = rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*"
    entries = [(name, re.sub(pattern, rb"\g<1>" + stamp, data)
                if name == "docProps/core.xml" else data) for name, data in entries]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as dst:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            dst.writestr(info, data)


def _blocks(md: str):
    """('title'|'section'|'bullet'|'plain'|'table', payload) in order. Tables arrive whole."""
    table: list[list[str]] = []
    for raw in md.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                table.append(cells)
            continue
        if table:
            yield "table", table
            table = []
        if not line:
            continue
        if line.startswith("# "):
            yield "title", line[2:]
        elif line.startswith("## "):
            yield "section", line[3:]
        elif line.startswith("- "):
            yield "bullet", line[2:]
        else:
            yield "plain", line
    if table:
        yield "table", table


# ---------------------------------------------------------------- PDF
def markdown_to_pdf(md: str, path: Path, title: str = "Sample document") -> None:
    # No compression: the bytes must not depend on the platform's zlib build (CI diffs them).
    c = canvas.Canvas(str(path), pagesize=letter, invariant=1, pageCompression=0)
    c.setTitle(title)
    c.setAuthor("Sample data (fictional)")
    c.setCreator("Bridge Loan Platform sample generator")
    y = TOP

    def need(height: float) -> None:
        nonlocal y
        if y - height < BOTTOM:
            c.showPage()
            y = TOP

    def text(x: float, string: str, font: str = "Helvetica", size: float = BODY) -> None:
        c.setFont(font, size)
        c.drawString(x, y, string)

    for kind, payload in _blocks(md):
        if kind == "title":
            need(30)
            text(LEFT, payload, "Helvetica-Bold", TITLE)
            y -= 26
        elif kind == "section":
            need(34)
            y -= 8
            text(LEFT, payload, "Helvetica-Bold", SECTION)
            y -= 20
        elif kind in ("bullet", "plain"):
            indent = LEFT + 14 if kind == "bullet" else LEFT
            room = WIDTH - (indent - LEFT)
            for i, part in enumerate(simpleSplit(payload, "Helvetica", BODY, room)):
                need(LINE)
                if kind == "bullet" and i == 0:
                    text(LEFT, "•")
                text(indent, part)
                y -= LINE
        else:                                              # table
            y -= 6
            columns = len(payload[0])
            xs = [LEFT, RIGHT_COL] if columns == 2 else [
                LEFT + i * (WIDTH / columns) for i in range(columns)]
            for r, row in enumerate(payload):
                need(LINE + 4)
                for x, cell in zip(xs, row, strict=False):
                    text(x, cell, "Helvetica-Bold" if r == 0 else "Helvetica")
                if r == 0:
                    c.setLineWidth(0.5)
                    c.line(LEFT, y - 3, LEFT + WIDTH, y - 3)
                y -= LINE + 2
            y -= 12
    c.save()


# ---------------------------------------------------------------- Word
def markdown_to_docx(md: str, path: Path, title: str = "Sample document") -> None:
    doc = Document()
    props = doc.core_properties
    props.author = props.last_modified_by = "Sample data (fictional)"
    props.title, props.comments = title, ""
    props.created = props.modified = props.last_printed = FIXED_TIME
    props.revision = 1
    for kind, payload in _blocks(md):
        if kind == "title":
            doc.add_heading(payload, 0)
        elif kind == "section":
            doc.add_heading(payload, 1)
        elif kind == "bullet":
            doc.add_paragraph(payload, style="List Bullet")
        elif kind == "plain":
            doc.add_paragraph(payload)
        else:
            table = doc.add_table(rows=len(payload), cols=len(payload[0]))
            table.style = "Table Grid"
            for r, row in enumerate(payload):
                for k, cell in enumerate(row):
                    table.cell(r, k).text = cell
            doc.add_paragraph("")
    doc.save(str(path))
    freeze_zip(path)


# ---------------------------------------------------------------- Excel
def write_xlsx(path: Path, header: list, rows: list, sheet: str = "Sheet1") -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(header)
    for row in rows:
        ws.append(list(row))
    wb.properties.creator = wb.properties.lastModifiedBy = "Sample data (fictional)"
    wb.properties.created = wb.properties.modified = FIXED_TIME
    wb.save(str(path))
    freeze_zip(path)
