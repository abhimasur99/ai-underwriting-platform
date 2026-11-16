"""Workbook: live formulas for every metric, recalculated values match the answer key."""
import pytest
from bridge.core.builders.workbook import METRIC_CELLS, build_workbook
from bridge.core.independent.xl import Evaluator
from bridge.core.parsers import parse_deal_dir
from bridge.core.rules import load_rules
from bridge.core.underwrite import underwrite
from openpyxl import load_workbook

SHEETS = ["Summary", "Inputs", "Rent Roll", "T-12", "Sources & Uses", "Metrics",
          "Exit & Stress", "Flags"]


@pytest.fixture
def built(deal_dir, tmp_path):
    deal = parse_deal_dir(deal_dir)
    result = underwrite(deal)
    path = tmp_path / "workbook.xlsx"
    build_workbook(deal, result, load_rules(), path)
    return load_workbook(path), result


def test_has_all_sheets(built):
    wb, _ = built
    assert wb.sheetnames == SHEETS


def test_every_metric_cell_is_a_formula(built):
    wb, _ = built
    for name, ref in METRIC_CELLS.items():
        sheet, coord = ref.split("!")
        value = wb[sheet][coord].value
        assert isinstance(value, str) and value.startswith("="), f"{name} is not a formula"


def test_recalculated_values_match_answer_key(built, expected):
    wb, _ = built
    ev, m = Evaluator(wb), expected["metrics"]

    def get(name):
        sheet, coord = METRIC_CELLS[name].split("!")
        return ev.value(sheet, coord)

    for name in ("total_cost", "ltc", "ltv_as_is", "loan_to_arv", "dscr_in_place",
                 "debt_yield_stabilized", "implied_cap_rate", "payoff", "takeout_max",
                 "refi_cushion", "exit_dscr"):
        key = {"payoff": "payoff"}.get(name, name)
        assert get(name) == pytest.approx(m[key], abs=1e-4 if m[key] < 100 else 1), name
    assert get("dscr_cap") == pytest.approx(m["takeout_caps"]["dscr"], abs=1)
    assert get("ltv_cap") == pytest.approx(m["takeout_caps"]["ltv"], abs=1)
    assert get("debt_yield_cap") == pytest.approx(m["takeout_caps"]["debt_yield"], abs=1)
    assert get("binding") == m["takeout_binding"]
    s = m["stress"]
    assert get("stress_takeout_max") == pytest.approx(s["takeout_max"], abs=1)
    assert get("stress_refi_cushion") == pytest.approx(s["refi_cushion"], abs=1)
    assert get("stress_exit_dscr") == pytest.approx(s["exit_dscr"], abs=1e-4)
    assert get("stress_binding") == s["takeout_binding"]
    assert get("rent_roll_vs_t12_gap") == pytest.approx(m["rr_vs_t12_gap"], abs=1e-4)
    assert get("sources_vs_uses_gap") == pytest.approx(m["sources_vs_uses_gap"], abs=1e-4)


def test_inputs_sheet_lists_value_and_source(built):
    wb, _ = built
    rows = {r[0].value: r for r in wb["Inputs"].iter_rows(min_row=2) if r[0].value}
    assert rows["loan_commitment"][1].value in (6_500_000, 4_300_000, 4_050_000)
    assert "deal_summary.md" in rows["loan_commitment"][2].value


def test_summary_and_flags_carry_the_call_and_reasons(built):
    wb, result = built
    summary = " ".join(str(c.value) for r in wb["Summary"].iter_rows() for c in r if c.value)
    assert result.call.upper() in summary
    for reason in result.reasons:
        assert reason.code in summary
    assert "illustrative" in summary.lower()
