"""Parsers: sample CSV, XLSX and markdown into a sourced Deal."""
import csv
import shutil

import pytest
from bridge.core.parsers import parse_deal_dir
from bridge.core.parsers.errors import MissingRequiredFieldError, ParseError
from bridge.core.parsers.sourcing import sourced_from_quote
from bridge.core.parsers.tables import parse_number
from openpyxl import Workbook

from tests.conftest import DEALS_DIR


def test_matches_answer_key(deal_dir, expected):
    k = expected["answer_key"]
    d = parse_deal_dir(deal_dir)
    assert d.deal_id == expected["deal_id"]
    assert d.purchase.purchase_price.value == k["purchase_price"]
    assert d.renovation.renovation_budget.value == k["renovation_budget"]
    assert d.loan_request.loan_commitment.value == k["loan_commitment"]
    assert d.loan_request.initial_advance.value == k["initial_advance"]
    assert d.loan_request.note_rate.value == pytest.approx(k["note_rate"])
    assert d.loan_request.term_months.value == k["term_months"]
    assert d.valuation.as_is_value.value == k["as_is_value"]
    assert d.valuation.arv.value == k["arv"]
    assert d.property.unit_count.value == k["unit_count"]
    assert d.property.occupied_units.value == k["occupied_units"]
    assert d.property.asset_type.value == k["asset_type"]
    assert d.pro_forma.stabilized_noi.value == k["stabilized_noi"]
    assert d.t12.in_place_noi.value == k["in_place_noi"]
    assert d.t12.rental_income.value == k["t12_rental_income"]
    assert d.t12.total_income.value == k["t12_total_income"]
    assert d.t12.total_expenses.value == k["t12_total_expenses"]
    assert d.rent_roll.annual_occupied_rent.value == k["rent_roll_annual"]
    assert d.sources_uses.stated_total_sources.value == k["sources_stated_total"]
    assert d.sources_uses.stated_total_uses.value == k["uses_stated_total"]
    assert len(d.rent_roll.units) == k["unit_count"]


def test_every_key_field_is_traceable(deal_dir):
    d = parse_deal_dir(deal_dir)
    for name in ["purchase_price", "renovation_budget", "loan_commitment", "initial_advance",
                 "as_is_value", "arv", "stabilized_noi", "unit_count", "note_rate"]:
        f = d.key_field(name)
        assert f.source.kind == "document", name
        assert f.source.doc and f.source.locator and f.source.quote, name
        assert f.confidence >= 0.8, name


def test_clean_deal_has_no_parse_flags():
    assert parse_deal_dir(DEALS_DIR / "bronx_mf").flags == []


def test_retail_units_count_in_rent_roll():
    d = parse_deal_dir(DEALS_DIR / "queens_mixed_use")
    assert any(u.unit_type == "retail" for u in d.rent_roll.units)
    assert d.rent_roll.annual_occupied_rent.value == 547_800


def test_xlsx_parses_same_as_csv(tmp_path):
    src = DEALS_DIR / "bronx_mf"
    dst = tmp_path / "deal"
    shutil.copytree(src, dst)
    for stem in ("rent_roll", "t12", "renovation_budget"):
        wb = Workbook()
        ws = wb.active
        for line in (dst / f"{stem}.csv").read_text().splitlines():
            ws.append(next(csv.reader([line])))
        # store numbers as real numbers, like a real spreadsheet
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                try:
                    cell.value = float(cell.value) if cell.value not in ("", None) else None
                except ValueError:
                    pass
        wb.save(dst / f"{stem}.xlsx")
        (dst / f"{stem}.csv").unlink()
    a, b = parse_deal_dir(src), parse_deal_dir(dst)
    assert b.rent_roll.annual_occupied_rent.value == a.rent_roll.annual_occupied_rent.value
    assert b.t12.in_place_noi.value == a.t12.in_place_noi.value
    assert b.renovation.line_items == a.renovation.line_items
    assert b.rent_roll.units[0].tenant == a.rent_roll.units[0].tenant


def test_rent_roll_header_synonyms(tmp_path):
    dst = tmp_path / "deal"
    shutil.copytree(DEALS_DIR / "bronx_mf", dst)
    p = dst / "rent_roll.csv"
    p.write_text(p.read_text().replace("unit,", "Apt,", 1).replace("monthly_rent", "Monthly Rent"))
    d = parse_deal_dir(dst)
    assert d.rent_roll.annual_occupied_rent.value == 730_320


def _broken(tmp_path, filename, old, new=""):
    dst = tmp_path / "deal"
    shutil.copytree(DEALS_DIR / "bronx_mf", dst)
    p = dst / filename
    text = p.read_text()
    assert old in text
    p.write_text(text.replace(old, new))
    return dst


@pytest.mark.parametrize("filename,line,field", [
    ("deal_summary.md", "- Loan commitment requested: $6,500,000\n", "loan_commitment"),
    ("deal_summary.md", "- Note rate: 10.50% interest-only\n", "note_rate"),
    ("deal_summary.md", "- Asset type: multifamily\n", "asset_type"),
    ("purchase_contract.md", "- Purchase price: $8,000,000\n", "purchase_price"),
])
def test_missing_required_field_fails_loudly(tmp_path, filename, line, field):
    dst = _broken(tmp_path, filename, line)
    with pytest.raises(MissingRequiredFieldError) as exc:
        parse_deal_dir(dst)
    assert field in exc.value.missing


def test_all_missing_fields_reported_together(tmp_path):
    dst = _broken(tmp_path, "deal_summary.md", "- Loan commitment requested: $6,500,000\n")
    p = dst / "deal_summary.md"
    p.write_text(p.read_text().replace("- Note rate: 10.50% interest-only\n", ""))
    with pytest.raises(MissingRequiredFieldError) as exc:
        parse_deal_dir(dst)
    assert {"loan_commitment", "note_rate"} <= set(exc.value.missing)


def test_missing_document_raises(tmp_path):
    dst = tmp_path / "deal"
    shutil.copytree(DEALS_DIR / "bronx_mf", dst)
    (dst / "t12.csv").unlink()
    with pytest.raises(FileNotFoundError):
        parse_deal_dir(dst)


def test_t12_row_total_mismatch_is_flagged(tmp_path):
    dst = _broken(tmp_path, "t12.csv", ",715104", ",700000")
    codes = [f.code for f in parse_deal_dir(dst).flags]
    assert "T12_ROW_TOTAL_MISMATCH" in codes


def test_budget_sum_mismatch_is_flagged(tmp_path):
    dst = _broken(tmp_path, "renovation_budget.csv", "Contingency,30000", "Contingency,10000")
    codes = [f.code for f in parse_deal_dir(dst).flags]
    assert "RENOVATION_BUDGET_MISMATCH" in codes


def test_bad_rent_roll_status_raises(tmp_path):
    dst = _broken(tmp_path, "rent_roll.csv", ",occupied,Tenant 101,", ",maybe,Tenant 101,")
    with pytest.raises(ParseError):
        parse_deal_dir(dst)


@pytest.mark.parametrize("text,value", [
    ("$6,500,000", 6_500_000), ("-$53,520", -53_520), ("(500)", -500), ("1,320", 1320),
    ("10.50%", 10.5), ("12", 12), ("1320.0", 1320),
])
def test_parse_number(text, value):
    assert parse_number(text) == pytest.approx(value)


def test_unverifiable_quote_caps_confidence():
    text = "- Purchase price: $8,000,000\n"
    ok = sourced_from_quote(8_000_000, "c.md", text, "line 1", "Purchase price: $8,000,000")
    assert ok.confidence == 0.98
    bad = sourced_from_quote(9_000_000, "c.md", text, "line 1", "Purchase price: $9,000,000")
    assert bad.confidence == 0.5
