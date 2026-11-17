"""The checker's own parser and formulas (core/independent/), pinned to expected.json."""
import ast
import shutil
from datetime import date
from pathlib import Path

import pytest
from bridge.core.builders.memo import render_memo
from bridge.core.builders.workbook import build_workbook
from bridge.core.independent import formulas, parse, pdftext, trace, xl
from bridge.core.parsers import parse_deal_dir
from bridge.core.rules import load_rules
from bridge.core.underwrite import underwrite
from openpyxl import load_workbook

from tests.conftest import DEALS_DIR, ROOT


@pytest.fixture(scope="module")
def cfg():
    return formulas.load_config()


def test_independence_no_imports_of_calc_parsers_or_the_shared_rules_module():
    forbidden = {"bridge.core.calc", "bridge.core.parsers", "bridge.core.rules"}
    forbidden_names = {"calc", "parsers", "rules"}
    for path in (ROOT / "backend" / "bridge" / "core" / "independent").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert not any(a.name.startswith(f) for f in forbidden), f"{path}: {a.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(f) for f in forbidden), \
                    f"{path}: {node.module}"
                if node.module in ("bridge.core", "bridge"):
                    assert not {a.name for a in node.names} & forbidden_names, f"{path}"


def test_parse_matches_answer_key(deal_dir, expected):
    k, got = expected["answer_key"], parse.independent_parse(deal_dir)
    for key in ("purchase_price", "renovation_budget", "loan_commitment", "initial_advance",
                "as_is_value", "arv", "stabilized_noi", "in_place_noi", "unit_count",
                "occupied_units"):
        assert got[key] == pytest.approx(k[key]), key
    assert got["note_rate"] == pytest.approx(k["note_rate"])
    assert got["asset_type"] == k["asset_type"]
    assert got["rent_roll_annual"] == k["rent_roll_annual"]
    assert got["t12_rental_income"] == k["t12_rental_income"]
    assert got["sources_stated_total"] == k["sources_stated_total"]
    assert got["uses_stated_total"] == k["uses_stated_total"]
    assert got["rent_roll_rows"] == k["unit_count"]


def test_recompute_matches_answer_key(deal_dir, expected, cfg):
    m = formulas.independent_recompute(parse.independent_parse(deal_dir), cfg)
    e = expected["metrics"]
    for key in ("total_cost", "ltc", "ltv_as_is", "loan_to_arv", "dscr_in_place",
                "debt_yield_stabilized", "implied_cap_rate", "payoff", "takeout_max",
                "refi_cushion", "exit_dscr"):
        assert m[key] == pytest.approx(e[key], abs=1e-4 if e[key] < 100 else 1), key
    assert m["binding"] == e["takeout_binding"]
    assert m["stress_takeout_max"] == pytest.approx(e["stress"]["takeout_max"], abs=1)
    assert m["stress_binding"] == e["stress"]["takeout_binding"]
    assert m["rent_roll_vs_t12_gap"] == pytest.approx(e["rr_vs_t12_gap"], abs=1e-4)
    assert m["sources_vs_uses_gap"] == pytest.approx(e["sources_vs_uses_gap"], abs=1e-4)


def test_rules_recheck_matches_answer_key(deal_dir, expected, cfg):
    inputs = parse.independent_parse(deal_dir)
    call, codes = formulas.rules_recheck(inputs, formulas.independent_recompute(inputs, cfg), cfg)
    assert call == expected["expected_call"]
    assert codes == expected["expected_reason_codes"]


def test_compare_metrics_tolerances():
    a = {"ltc": 0.7065, "takeout_max": 8_235_294.4, "binding": "debt_yield"}
    assert formulas.compare_metrics(a, {"ltc": 0.70655, "takeout_max": 8_235_295.0,
                                        "binding": "debt_yield"}) == []
    bad = formulas.compare_metrics(a, {"ltc": 0.7143, "takeout_max": 8_235_400.0,
                                       "binding": "dscr"})
    assert {m["field"] for m in bad} == {"ltc", "takeout_max", "binding"}
    assert next(m for m in bad if m["field"] == "ltc")["diff"] == pytest.approx(0.0078)


def test_reconcile_recheck_status(cfg):
    out = formulas.reconcile_recheck(parse.independent_parse(DEALS_DIR / "overleveraged_bk"), cfg)
    assert out["rent_roll_vs_t12"]["status"] == "decline"
    assert out["sources_vs_uses"]["status"] == "decline"
    assert out["unit_count"]["status"] == "pass"


# ---- workbook audit and the safe evaluator
@pytest.fixture
def built(tmp_path):
    deal = parse_deal_dir(DEALS_DIR / "bronx_mf")
    result = underwrite(deal)
    path = tmp_path / "wb.xlsx"
    build_workbook(deal, result, load_rules(), path)
    cfg = formulas.load_config()
    inputs = parse.independent_parse(DEALS_DIR / "bronx_mf")
    return path, formulas.independent_recompute(inputs, cfg)


def test_workbook_audit_passes_on_a_real_workbook(built):
    path, metrics = built
    out = xl.workbook_audit(path, metrics)
    assert out["hardcoded"] == [] and out["mismatches"] == [] and out["missing"] == []
    assert out["audited"] >= 20


def test_workbook_audit_catches_a_pasted_number(built):
    path, metrics = built
    wb = load_workbook(path)
    wb["Metrics"]["B3"] = 0.7065   # ltc pasted as a number
    wb.save(path)
    assert "ltc" in xl.workbook_audit(path, metrics)["hardcoded"]


def test_workbook_audit_catches_a_wrong_input(built):
    path, metrics = built
    wb = load_workbook(path)
    for row in wb["Inputs"].iter_rows(min_row=2):
        if row[0].value == "loan_commitment":
            row[1].value = 7_000_000
    wb.save(path)
    assert "ltc" in {m["field"] for m in xl.workbook_audit(path, metrics)["mismatches"]}


@pytest.mark.parametrize("formula", [
    '=__import__("os").system("echo hi")', "=().__class__", '=open("/etc/passwd")',
    "=[1,2][0]", "=lambda: 1"])
def test_evaluator_refuses_anything_but_spreadsheet_math(formula):
    from openpyxl import Workbook
    wb = Workbook()
    wb.active["A1"] = formula
    with pytest.raises(xl.FormulaError):
        xl.Evaluator(wb).value(wb.active.title, "A1")


# ---- memo numbers
def test_memo_number_match_passes_on_a_real_memo(tmp_path):
    deal = parse_deal_dir(DEALS_DIR / "overleveraged_bk")
    path = tmp_path / "m.pdf"
    render_memo(deal, underwrite(deal), path, as_of=date(2026, 11, 16))
    cfg = formulas.load_config()
    inputs = parse.independent_parse(DEALS_DIR / "overleveraged_bk")
    metrics = formulas.independent_recompute(inputs, cfg)
    out = pdftext.memo_number_match(path, inputs, metrics, cfg, call="decline")
    assert out["unmatched"] == [] and out["call_ok"] is True
    assert "CALL: DECLINE" in pdftext.extract_pdf_text(path)


def test_unmatched_numbers_are_found():
    pool = {"usd": [8_235_294.0], "pct": [0.7065], "mult": [1.79]}
    text = "take-out $8,235,294 and $9,999,999 at 70.65% or 71.00% with 1.79x and 3.50x"
    assert pdftext.find_unmatched(text, pool) == ["$9,999,999", "71.00%", "3.50x"]


# ---- source trace
def test_source_trace_clean_for_every_sample(deal_dir):
    assert trace.source_trace(parse_deal_dir(deal_dir), deal_dir) == []


def test_source_trace_flags_a_bad_quote_and_a_wrong_value(tmp_path):
    d = tmp_path / "deal"
    shutil.copytree(DEALS_DIR / "bronx_mf", d)
    deal = parse_deal_dir(d)
    deal.valuation.arv.source.quote = "After-repair value (ARV): $99,999,999"
    deal.loan_request.note_rate.value = 0.2
    problems = trace.source_trace(deal, d)
    assert any("valuation.arv" in p for p in problems)
    assert any("loan_request.note_rate" in p for p in problems)


def test_source_trace_flags_a_missing_document(tmp_path):
    d = tmp_path / "deal"
    shutil.copytree(DEALS_DIR / "bronx_mf", d)
    deal = parse_deal_dir(d)
    Path(d / "purchase_contract.md").unlink()
    assert any("purchase_price" in p for p in trace.source_trace(deal, d))


def test_the_checkers_own_pdf_table_reader_agrees_on_a_deal_whose_tables_are_pdfs(tmp_path):
    import csv
    import shutil

    from bridge.core.independent.parse import independent_parse

    from scripts.sample_docs import table_to_pdf
    src = DEALS_DIR / "queens_mixed_use"
    folder = tmp_path / "deal"
    shutil.copytree(src, folder, ignore=shutil.ignore_patterns("cached", "expected.json"))
    for stem in ("rent_roll", "t12", "renovation_budget"):
        with (folder / f"{stem}.csv").open(newline="") as fh:
            grid = list(csv.reader(fh))
        (folder / f"{stem}.csv").unlink()
        table_to_pdf(grid[0], grid[1:], folder / f"{stem}.pdf", title=f"{stem} sample")
    assert independent_parse(folder) == independent_parse(src)
