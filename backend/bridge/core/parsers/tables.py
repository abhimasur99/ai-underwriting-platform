"""Read CSV or XLSX tables into rows of normalized-header cells, and parse numbers."""
import csv
import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from bridge.core.parsers.errors import ParseError


@dataclass(frozen=True)
class Row:
    number: int                 # spreadsheet row number (header is row 1)
    cells: dict[str, str]


def normalize_header(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(raw).strip().lower()).strip("_")


def parse_number(text: str) -> float:
    """'$6,500,000' -> 6500000, '(500)' -> -500, '-$53,520' -> -53520, '10.50%' -> 10.5."""
    s = str(text).strip()
    negative = s.startswith("(") and s.endswith(")") or s.startswith("-")
    cleaned = re.sub(r"[^0-9.]", "", s)
    if not cleaned or cleaned == ".":
        raise ParseError(f"not a number: {text!r}")
    value = float(cleaned)
    return -value if negative else value


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def find_document(directory: Path, stem: str) -> Path:
    for ext in ("csv", "xlsx"):
        path = directory / f"{stem}.{ext}"
        if path.exists():
            return path
    raise FileNotFoundError(f"{stem}.csv or {stem}.xlsx not found in {directory}")


def read_rows(path: Path, synonyms: dict[str, str]) -> list[Row]:
    """Rows keyed by normalized header; `synonyms` maps alternative headers to canonical ones."""
    if path.suffix == ".xlsx":
        sheet = load_workbook(path, read_only=True, data_only=True).worksheets[0]
        raw = [[_cell_text(c) for c in r] for r in sheet.iter_rows(values_only=True)]
    else:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            raw = [list(r) for r in csv.reader(fh)]
    if not raw:
        raise ParseError(f"{path.name} is empty")
    header = [synonyms.get(normalize_header(h), normalize_header(h)) for h in raw[0]]
    rows = []
    for index, values in enumerate(raw[1:], start=2):
        if not any(v.strip() for v in values):
            continue
        rows.append(Row(index, {h: v.strip() for h, v in zip(header, values, strict=False)}))
    return rows
