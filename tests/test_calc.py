"""Unit tests per formula, plus the answer keys in data/deals/*/expected.json."""
import json

import pytest
from bridge.core import calc
from bridge.core.calc import StressParams, TakeoutParams

from tests.conftest import DEAL_NAMES, DEALS_DIR

TK = TakeoutParams(rate=0.06, min_dscr=1.25, max_ltv=0.70, min_debt_yield=0.085, exit_fee_pct=0.0)
ST = StressParams(noi_haircut=0.10, rate_bump_bps=100)


def test_total_cost_sums_uses():
    assert calc.total_cost([8_000_000, 1_200_000]) == 9_200_000


def test_ltc():
    assert calc.ltc(6_500_000, 9_200_000) == pytest.approx(0.7065217391)


def test_ltv_as_is_uses_initial_advance():
    assert calc.ltv_as_is(5_300_000, 8_000_000) == pytest.approx(0.6625)


def test_loan_to_arv():
    assert calc.loan_to_arv(6_500_000, 12_500_000) == pytest.approx(0.52)


def test_dscr_in_place():
    assert calc.dscr_in_place(369_304, 5_300_000, 0.105) == pytest.approx(0.6636190476)


def test_debt_yield_and_cap_rate():
    assert calc.debt_yield_stabilized(700_000, 6_500_000) == pytest.approx(0.1076923077)
    assert calc.implied_cap_rate(700_000, 12_500_000) == pytest.approx(0.056)


def test_exit_picks_smallest_cap_as_binding():
    out = calc.exit_analysis(700_000, 12_500_000, 6_500_000, TK)
    assert out.binding == "debt_yield"
    assert out.takeout_max == pytest.approx(8_235_294.1176)
    assert out.refi_cushion == pytest.approx(1_735_294.1176)
    assert out.exit_dscr == pytest.approx(1.7948717949)


def test_exit_fee_raises_payoff():
    fee = TakeoutParams(0.06, 1.25, 0.70, 0.085, 0.01)
    out = calc.exit_analysis(700_000, 12_500_000, 6_500_000, fee)
    assert out.payoff == pytest.approx(6_565_000)


def test_negative_cushion_when_payoff_exceeds_takeout():
    out = calc.exit_analysis(280_000, 5_000_000, 4_050_000, TK)
    assert out.refi_cushion < 0


def test_stress_haircuts_noi_and_bumps_rate():
    base = calc.exit_analysis(700_000, 12_500_000, 6_500_000, TK)
    stress = calc.stress_analysis(700_000, 12_500_000, 6_500_000, TK, ST)
    assert stress.noi == pytest.approx(630_000)
    assert stress.rate == pytest.approx(0.07)
    assert stress.binding == "dscr"
    assert stress.takeout_max == pytest.approx(7_200_000)
    assert stress.refi_cushion == pytest.approx(700_000)
    assert stress.takeout_max < base.takeout_max


@pytest.mark.parametrize("fn,args", [
    (calc.ltc, (1, 0)),
    (calc.ltv_as_is, (1, 0)),
    (calc.loan_to_arv, (1, 0)),
    (calc.debt_yield_stabilized, (1, 0)),
    (calc.implied_cap_rate, (1, 0)),
    (calc.dscr_in_place, (1, 0, 0.1)),
])
def test_zero_denominator_fails_loudly(fn, args):
    with pytest.raises(calc.CalcError):
        fn(*args)


def test_every_formula_is_documented():
    for name in ["total_cost", "ltc", "ltv_as_is", "loan_to_arv", "dscr_in_place",
                 "debt_yield_stabilized", "implied_cap_rate", "payoff", "dscr_cap",
                 "ltv_cap", "debt_yield_cap", "takeout_max", "refi_cushion", "exit_dscr"]:
        assert name in calc.FORMULAS


@pytest.mark.parametrize("name", DEAL_NAMES)
def test_matches_answer_key(name):
    """Calc, fed the answer-key inputs, reproduces expected.json (ratios 1e-4, dollars $1)."""
    e = json.loads((DEALS_DIR / name / "expected.json").read_text())
    k, m = e["answer_key"], e["metrics"]
    assert calc.ltc(k["loan_commitment"], m["total_cost"]) == pytest.approx(m["ltc"], abs=1e-4)
    assert calc.ltv_as_is(k["initial_advance"], k["as_is_value"]) == pytest.approx(
        m["ltv_as_is"], abs=1e-4)
    assert calc.loan_to_arv(k["loan_commitment"], k["arv"]) == pytest.approx(
        m["loan_to_arv"], abs=1e-4)
    assert calc.dscr_in_place(k["in_place_noi"], k["initial_advance"], k["note_rate"]) == (
        pytest.approx(m["dscr_in_place"], abs=1e-4))
    base = calc.exit_analysis(k["stabilized_noi"], k["arv"], k["loan_commitment"], TK)
    assert base.takeout_max == pytest.approx(m["takeout_max"], abs=1)
    assert base.binding == m["takeout_binding"]
    assert base.refi_cushion == pytest.approx(m["refi_cushion"], abs=1)
    assert base.exit_dscr == pytest.approx(m["exit_dscr"], abs=1e-4)
    s = calc.stress_analysis(k["stabilized_noi"], k["arv"], k["loan_commitment"], TK, ST)
    assert s.takeout_max == pytest.approx(m["stress"]["takeout_max"], abs=1)
    assert s.binding == m["stress"]["takeout_binding"]
    assert s.refi_cushion == pytest.approx(m["stress"]["refi_cushion"], abs=1)
    assert s.exit_dscr == pytest.approx(m["stress"]["exit_dscr"], abs=1e-4)


def test_reconciliation_gap_is_relative_to_second_value():
    assert calc.reconciliation_gap(730_320, 715_104) == pytest.approx(0.0212780239)
    assert calc.reconciliation_gap(715_104, 730_320) == pytest.approx(0.0208, abs=1e-4)


def test_reconciliation_gap_zero_denominator_fails_loudly():
    with pytest.raises(calc.CalcError):
        calc.reconciliation_gap(1, 0)
