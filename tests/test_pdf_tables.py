"""Tables inside PDFs (rent roll, T-12, renovation budget): rows rebuilt from text positions."""
import csv
import re
import shutil

import pytest
from bridge.core.parsers import parse_deal_dir
from bridge.core.parsers.errors import ParseError
from bridge.core.parsers.pdftable import pdf_grid
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from scripts.sample_docs import table_to_pdf
from tests.conftest import DEALS_DIR, ORIGINAL_DEALS

STEMS = ["rent_roll", "t12", "renovation_budget"]


def csv_grid(path):
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [row for row in csv.reader(fh)]


def plain(grid):
    """Numbers print with thousands separators; compare without them (text cells untouched)."""
    return [[c.replace(",", "") if re.fullmatch(r"-?[\d,]+(\.\d+)?", c) else c for c in row]
            for row in grid]


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("deal", ORIGINAL_DEALS)
def test_a_printed_table_reads_back_cell_for_cell(tmp_path, deal, stem):
    expected = csv_grid(DEALS_DIR / deal / f"{stem}.csv")
    pdf = tmp_path / f"{stem}.pdf"
    table_to_pdf(expected[0], expected[1:], pdf, title=f"{stem} sample")
    assert plain(pdf_grid(pdf)) == expected          # blank cells stay in their column


def test_a_table_over_many_pages_has_one_header_and_no_footers(tmp_path):
    rows = [[f"{100 + i}", "1br", "620", "occupied" if i % 3 else "vacant",
             f"Tenant {i}" if i % 3 else "", "1,500"] for i in range(150)]
    header = ["unit", "unit_type", "sqft", "status", "tenant", "monthly_rent"]
    pdf = tmp_path / "long.pdf"
    table_to_pdf(header, rows, pdf, title="Rent roll long")
    grid = pdf_grid(pdf)
    assert grid[0] == header and len(grid) == 151        # header once, every row, no "Page n"
    assert plain(grid[1:]) == plain(rows)


def test_right_aligned_numbers_and_split_header_words_are_read_correctly(tmp_path):
    """A report in another style: header words drawn separately, numbers right-aligned."""
    pdf = tmp_path / "other.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter, invariant=1)
    c.setFont("Helvetica-Bold", 9)
    for x, word in ((50, "Unit"), (73, "#"), (110, "Unit"), (135, "Type"), (230, "Sq"),
                    (243, "Ft"), (300, "Status"), (380, "Monthly"), (420, "Rent")):
        c.drawString(x, 700, word)
    c.setFont("Helvetica", 9)
    for i, (unit, kind, sqft, status, rent) in enumerate([
            ("101", "studio", "450", "occupied", "1,320"),
            ("102", "1br", "620", "vacant", "0"),
            ("103", "2br", "1,010", "occupied", "1,980")]):
        y = 685 - i * 14
        c.drawString(50, y, unit)
        c.drawString(110, y, kind)
        c.drawRightString(260, y, sqft)
        c.drawString(300, y, status)
        c.drawRightString(470, y, rent)
    c.save()
    grid = pdf_grid(pdf)
    assert grid[0] == ["Unit #", "Unit Type", "Sq Ft", "Status", "Monthly Rent"]
    assert grid[1:] == [["101", "studio", "450", "occupied", "1,320"],
                        ["102", "1br", "620", "vacant", "0"],
                        ["103", "2br", "1,010", "occupied", "1,980"]]


def test_a_pdf_with_no_table_is_refused_loudly(tmp_path):
    pdf = tmp_path / "prose.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 700, "Just a paragraph of text with no columns at all.")
    c.save()
    with pytest.raises(ParseError, match="no table"):
        pdf_grid(pdf)


def test_a_deal_whose_tables_are_all_pdfs_parses_like_the_csv_version(tmp_path):
    src = DEALS_DIR / "queens_mixed_use"
    folder = tmp_path / "deal"
    shutil.copytree(src, folder, ignore=shutil.ignore_patterns("cached", "expected.json"))
    for stem in STEMS:
        grid = csv_grid(folder / f"{stem}.csv")
        (folder / f"{stem}.csv").unlink()
        table_to_pdf(grid[0], grid[1:], folder / f"{stem}.pdf", title=f"{stem} sample")
    from_pdf, from_csv = parse_deal_dir(folder), parse_deal_dir(src)
    assert from_pdf.rent_roll.units == from_csv.rent_roll.units
    assert from_pdf.t12.lines == from_csv.t12.lines
    assert from_pdf.renovation.line_items == from_csv.renovation.line_items
    assert from_pdf.rent_roll.annual_occupied_rent.source.doc == "rent_roll.pdf"
