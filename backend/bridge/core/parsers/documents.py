"""Read a deal's prose documents (summary, contract) from markdown, text, PDF or Word, and return
the markdown-like text the deterministic parser already understands.

PDF: only the text layer is read (no OCR). pypdf reports the font size of every text chunk, so a
larger font marks a heading, a line made of several chunks is a table row, and a bullet glyph
marks a bullet. This works for documents laid out the usual way (and for the ones this project
generates); a scanned or unusual PDF is a limitation recorded in docs/decisions.md D29.
Word: paragraph styles and tables map to the same markdown structure.
"""
import re
import statistics
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from docx import Document as _open_docx
from docx.table import Table as _DocxTable
from docx.text.paragraph import Paragraph as _DocxParagraph
from pypdf import PdfReader

from bridge.core.parsers.errors import ParseError

TEXT_EXTENSIONS = (".md", ".txt", ".pdf", ".docx")
BULLETS = ("•", "·", "▪", "–", "-")
# pypdf returns a drawn bullet glyph as a lone chunk; some encodings give a control character.
BULLET_CHUNKS = {"•", "·", "▪", "◦", "■", "*"}


def _is_bullet_chunk(cell: str) -> bool:
    return len(cell) == 1 and (cell in BULLET_CHUNKS or not cell.isprintable())


class UnreadableDocument(ParseError):
    """The file could not be read as text (corrupt, encrypted, or only scanned images)."""


def find_text_document(directory: Path, stem: str) -> Path:
    for ext in TEXT_EXTENSIONS:
        path = directory / f"{stem}{ext}"
        if path.exists():
            return path
    raise FileNotFoundError(
        f"{stem} not found in {directory} (looked for {', '.join(TEXT_EXTENSIONS)})")


def read_document_text(path: str | Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    try:
        if ext in (".md", ".txt"):
            return path.read_text(encoding="utf-8-sig")
        if ext == ".pdf":
            return _pdf_to_markdown(path)
        if ext == ".docx":
            return _docx_to_markdown(path)
    except UnreadableDocument:
        raise
    except Exception as exc:  # noqa: BLE001  (any library failure means "cannot read this file")
        raise UnreadableDocument(f"{path.name} could not be read: {exc}") from exc
    raise UnreadableDocument(f"{path.name}: unsupported document type {ext or 'unknown'}")


# ---------------------------------------------------------------- PDF
def _chunks(path: Path) -> Iterator[tuple[int, float, float, float, str]]:
    """(page, x, y, font_size, text) for every text chunk, in page coordinates."""
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise UnreadableDocument(f"{path.name} is encrypted")
    for number, page in enumerate(reader.pages):
        found: list[tuple[float, float, float, str]] = []

        def visit(text, cm, tm, _font, size, found=found):
            if text and text.strip():
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                found.append((x, y, float(size or 0) * abs(tm[0] or 1) * abs(cm[0] or 1), text))

        page.extract_text(visitor_text=visit)
        for x, y, size, text in found:
            yield number, x, y, size, text


def _pdf_to_markdown(path: Path) -> str:
    chunks = list(_chunks(path))
    if not chunks:
        raise UnreadableDocument(f"{path.name} has no text layer (a scan? OCR is not supported)")
    # group chunks into lines: same page, y within 1.5 points
    chunks.sort(key=lambda c: (c[0], -c[2], c[1]))
    lines: list[dict] = []
    for page, _x, y, size, text in chunks:
        last = lines[-1] if lines else None
        if last and last["page"] == page and abs(last["y"] - y) <= 1.5:
            last["cells"].append(text.strip())
            last["size"] = max(last["size"], size)
        else:
            lines.append({"page": page, "y": y, "size": size, "cells": [text.strip()]})
    sizes = Counter()
    for ln in lines:
        sizes[round(ln["size"], 1)] += sum(len(c) for c in ln["cells"])
    body = sizes.most_common(1)[0][0]
    biggest = max(round(ln["size"], 1) for ln in lines)
    gaps = [a["y"] - b["y"] for a, b in zip(lines, lines[1:], strict=False)
            if a["page"] == b["page"] and 0 < a["y"] - b["y"]]
    normal_gap = statistics.median(gaps) if gaps else 12.0

    out: list[str] = []
    in_table, previous = False, None
    for ln in lines:
        size = round(ln["size"], 1)
        row_break = previous is not None and previous["page"] == ln["page"] and \
            previous["y"] - ln["y"] > 1.6 * normal_gap
        if len(ln["cells"]) > 1 and _is_bullet_chunk(ln["cells"][0]):    # bullet glyph + text
            in_table = False
            out.append("- " + " ".join(ln["cells"][1:]).strip())
        elif len(ln["cells"]) > 1:                                # a table row
            if not in_table or row_break:
                if out and out[-1] != "":
                    out.append("")
                out.append("| " + " | ".join(ln["cells"]) + " |")
                out.append("| " + " | ".join("---" for _ in ln["cells"]) + " |")
            else:
                out.append("| " + " | ".join(ln["cells"]) + " |")
            in_table = True
        else:
            in_table = False
            text = ln["cells"][0]
            if size >= body + 1.5 and len(text) <= 90 and not text.endswith("."):
                marker = "# " if size == biggest and size >= body + 3 and not any(
                    o.startswith("# ") for o in out) else "## "
                out += ["", marker + text, ""] if marker == "## " else [marker + text, ""]
            elif text[0] in BULLETS and len(text) > 1 and text[1] == " ":
                out.append("- " + text[2:].strip())
            else:
                out.append(text)
        previous = ln
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


# ---------------------------------------------------------------- Word
def _docx_blocks(doc) -> Iterator[_DocxParagraph | _DocxTable]:
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield _DocxParagraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield _DocxTable(child, doc)


def _docx_to_markdown(path: Path) -> str:
    doc = _open_docx(str(path))
    out: list[str] = []
    for block in _docx_blocks(doc):
        if isinstance(block, _DocxTable):
            rows = [[c.text.strip() for c in row.cells] for row in block.rows]
            if not rows:
                continue
            if out and out[-1] != "":
                out.append("")
            out.append("| " + " | ".join(rows[0]) + " |")
            out.append("| " + " | ".join("---" for _ in rows[0]) + " |")
            out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
            out.append("")
            continue
        text, style = block.text.strip(), (block.style.name if block.style is not None else "")
        if not text:
            continue
        if style == "Title":
            out.append(f"# {text}")
            out.append("")
        elif style.startswith("Heading"):
            out += ["", f"## {text}", ""]
        elif style.startswith("List"):
            out.append(f"- {text}")
        else:
            out.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
