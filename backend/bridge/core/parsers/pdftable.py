"""Rebuild a table (rent roll, T-12, renovation budget) from a PDF's text layer.

A PDF has no table, only text placed at coordinates. This reads chunks of text with their
positions, groups them into lines by vertical position, finds the header row (the first line of
two or more non-numeric cells), and assigns every later line's cells to the header column whose
centre is nearest. That handles blank cells, left- or right-aligned columns, header words drawn
as separate pieces, and tables that continue over several pages with the header repeated.

It does not handle wrapped (multi-line) cells, merged cells or scans. Anything it cannot read as a
table raises ParseError and the deal stops at "needs input" (decision D29).
"""
import re
from pathlib import Path

from bridge.core.parsers.documents import pdf_chunks
from bridge.core.parsers.errors import ParseError

NUMERIC = re.compile(r"^\(?-?\$?[\d,]+(\.\d+)?%?\)?$")
JOIN_GAP = 1.0          # chunks closer than this many font sizes are one cell ("Monthly" "Rent")


class _Cell:
    __slots__ = ("x", "size", "text")

    def __init__(self, x: float, size: float, text: str):
        self.x, self.size, self.text = x, size, text

    @property
    def width(self) -> float:
        return len(self.text) * self.size * 0.55

    @property
    def centre(self) -> float:
        return self.x + self.width / 2


def _lines(path: Path) -> list[list[_Cell]]:
    chunks = sorted(pdf_chunks(path), key=lambda c: (c[0], -c[2], c[1]))
    lines: list[tuple[int, float, list[_Cell]]] = []
    for page, x, y, size, text in chunks:
        cell = _Cell(x, size, text.strip())
        if lines and lines[-1][0] == page and abs(lines[-1][1] - y) <= 1.5:
            lines[-1][2].append(cell)
        else:
            lines.append((page, y, [cell]))
    merged = []
    for _, _, cells in lines:
        cells.sort(key=lambda c: c.x)
        out = [cells[0]]
        for cell in cells[1:]:
            last = out[-1]
            if cell.x - (last.x + last.width) < JOIN_GAP * cell.size:
                last.text = f"{last.text} {cell.text}"
            else:
                out.append(cell)
        merged.append(out)
    return merged


def _is_header(cells: list[_Cell]) -> bool:
    return len(cells) >= 2 and not any(NUMERIC.match(c.text) for c in cells)


def pdf_grid(path: str | Path) -> list[list[str]]:
    """Header row first, then one list per table row (empty string for a blank cell)."""
    path = Path(path)
    lines = _lines(path)
    start = next((i for i, cells in enumerate(lines) if _is_header(cells)), None)
    if start is None:
        raise ParseError(f"{path.name}: no table found (no row of column headings)")
    header = lines[start]
    names = [c.text for c in header]
    grid = [names]
    for cells in lines[start + 1:]:
        if len(cells) < 2:                              # a page footer or a stray line
            continue
        if [c.text for c in cells] == names:             # the header repeated on a new page
            continue
        row = [""] * len(header)
        for cell in cells:
            nearest = min(range(len(header)), key=lambda i: abs(cell.centre - header[i].centre))
            row[nearest] = f"{row[nearest]} {cell.text}".strip()
        grid.append(row)
    return grid
