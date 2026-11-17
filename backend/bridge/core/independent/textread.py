"""The checker's OWN document reader. It turns a deal's summary or contract (markdown, text, PDF
or Word) into plain markdown-style text for the checker's regexes. It deliberately does not import
core/parsers/ (CLAUDE.md, checker independence; decision D30): a bug in one reader must not be
able to fool both. The two readers are written separately and pinned by the same answer keys."""
import re
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

TEXT_TYPES = ("md", "txt", "pdf", "docx")


def locate(directory: Path, stem: str) -> Path:
    for ext in TEXT_TYPES:
        if (directory / f"{stem}.{ext}").exists():
            return directory / f"{stem}.{ext}"
    raise FileNotFoundError(f"{stem} ({'/'.join(TEXT_TYPES)}) not found in {directory}")


def _pdf(path: Path) -> str:
    """Lines by vertical position; a line with several chunks is a table row; font size picks
    the headings."""
    reader = PdfReader(str(path))
    seen: list[tuple[int, float, float, float, str]] = []
    for page_no, page in enumerate(reader.pages):
        def grab(text, cm, tm, _f, size, page_no=page_no):
            if text.strip():
                seen.append((page_no, -(tm[5] * cm[3] + cm[5]), tm[4] * cm[0] + cm[4],
                             (size or 0) * abs(tm[0] or 1), text.strip()))
        page.extract_text(visitor_text=grab)
    if not seen:
        raise ValueError(f"{path.name}: no text layer")
    seen.sort()
    rows: list[list[tuple[float, float, str]]] = []
    keys: list[tuple[int, float]] = []
    for page_no, ytop, x, size, text in seen:
        if keys and keys[-1][0] == page_no and abs(keys[-1][1] - ytop) <= 1.5:
            rows[-1].append((x, size, text))
        else:
            keys.append((page_no, ytop))
            rows.append([(x, size, text)])
    body = sorted(round(r[0][1], 1) for r in rows)[len(rows) // 2]
    top = max(r[0][1] for r in rows)
    out, last_key, in_table = [], None, False
    for key, row in zip(keys, rows, strict=True):
        cells = [t for _, _, t in sorted(row)]
        size = max(sz for _, sz, _ in row)
        glyph = len(cells[0]) == 1 and not cells[0].isalnum() and cells[0] not in "$-+("
        gap_break = last_key is not None and last_key[0] == key[0] and key[1] - last_key[1] > 20
        last_key = key
        if glyph and len(cells) >= 2:
            out.append("- " + " ".join(cells[1:]))
            in_table = False
        elif len(cells) >= 2:
            if not in_table or gap_break:
                out += ["", "| " + " | ".join(cells) + " |",
                        "| " + "|".join(["---"] * len(cells)) + "|"]
            else:
                out.append("| " + " | ".join(cells) + " |")
            in_table = True
        else:
            in_table, text = False, cells[0]
            if size >= body + 1.5 and not text.endswith("."):
                out += [("# " if size == top and size >= body + 3 else "\n## ") + text, ""]
            elif text[:2] in ("• ", "· ", "- ", "– "):
                out.append("- " + text[2:])
            else:
                out.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def _docx(path: Path) -> str:
    doc = Document(str(path))
    lines: list[str] = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}tbl"):
            table = next(t for t in doc.tables if t._tbl is child)
            grid = [[c.text.strip() for c in r.cells] for r in table.rows]
            lines += ["", "| " + " | ".join(grid[0]) + " |",
                      "| " + "|".join(["---"] * len(grid[0])) + "|"]
            lines += ["| " + " | ".join(r) + " |" for r in grid[1:]] + [""]
        elif child.tag.endswith("}p"):
            para = next(p for p in doc.paragraphs if p._p is child)
            text, style = para.text.strip(), para.style.name if para.style is not None else ""
            if not text:
                continue
            if style == "Title":
                lines += [f"# {text}", ""]
            elif style.startswith("Heading"):
                lines += ["", f"## {text}", ""]
            elif style.startswith("List"):
                lines.append(f"- {text}")
            else:
                lines.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def read_text(path: str | Path) -> str:
    """Text of a document for tracing a quote back to its source. Spreadsheets give their cells."""
    path = Path(path)
    ext = path.suffix.lower().lstrip(".")
    if ext == "pdf":
        return _pdf(path)
    if ext == "docx":
        return _docx(path)
    if ext == "xlsx":
        sheet = load_workbook(path, read_only=True, data_only=True).worksheets[0]
        return "\n".join(",".join("" if c is None else str(c) for c in row)
                         for row in sheet.iter_rows(values_only=True))
    return path.read_text(encoding="utf-8-sig")


def pdf_grid(path: str | Path) -> list[list[str]]:
    """The checker's own PDF table reader (written separately from core/parsers/pdftable.py).

    Lines are text at the same height. The header is the first line with two or more cells and no
    numbers. A body cell goes to the header column whose centre is nearest, using the same rough
    text-width rule of thumb a reader would use (half an em per character)."""
    reader = PdfReader(str(path))
    placed: list[tuple[int, float, float, float, str]] = []
    for page_no, page in enumerate(reader.pages):
        def grab(text, cm, tm, _f, size, page_no=page_no):
            if text.strip():
                placed.append((page_no, tm[5] * cm[3] + cm[5], tm[4] * cm[0] + cm[4],
                               (size or 0) * abs(tm[0] or 1), text.strip()))
        page.extract_text(visitor_text=grab)
    placed.sort(key=lambda t: (t[0], -t[1], t[2]))
    rows: list[list[tuple[float, float, str]]] = []
    last: tuple[int, float] | None = None
    for page_no, y, x, size, text in placed:
        if last and last[0] == page_no and abs(last[1] - y) <= 1.5:
            rows[-1].append((x, size, text))
        else:
            rows.append([(x, size, text)])
        last = (page_no, y)
    lines = []
    for row in rows:
        row.sort()
        joined = [list(row[0])]
        for x, size, text in row[1:]:
            px, psize, ptext = joined[-1]
            if x - (px + len(ptext) * psize * 0.55) < size:       # pieces of one phrase
                joined[-1][2] = f"{ptext} {text}"
            else:
                joined.append([x, size, text])
        lines.append(joined)

    def centre(c):
        return c[0] + len(c[2]) * c[1] * 0.275

    number = re.compile(r"^\(?-?\$?[\d,]+(\.\d+)?%?\)?$")
    first = next((i for i, ln in enumerate(lines)
                  if len(ln) >= 2 and not any(number.match(c[2]) for c in ln)), None)
    if first is None:
        raise ValueError(f"{Path(path).name}: no table found")
    head = lines[first]
    names = [c[2] for c in head]
    grid = [names]
    for ln in lines[first + 1:]:
        if len(ln) < 2 or [c[2] for c in ln] == names:
            continue
        out = [""] * len(head)
        for c in ln:
            k = min(range(len(head)), key=lambda j: abs(centre(c) - centre(head[j])))
            out[k] = f"{out[k]} {c[2]}".strip()
        grid.append(out)
    return grid
