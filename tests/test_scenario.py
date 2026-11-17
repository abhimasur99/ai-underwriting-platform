"""What-ifs: the same calculator with some assumptions changed. Nothing is saved or mutated, and
a what-if gives the same answer as actually making the change."""
import pytest
from bridge.core.edit import set_input
from bridge.core.parsers import parse_deal_dir
from bridge.core.rules import load_rules
from bridge.core.scenario import PARAMS, ScenarioError, run_scenario
from bridge.core.underwrite import underwrite

from tests.conftest import DEALS_DIR


@pytest.fixture
def bronx():
    return parse_deal_dir(DEALS_DIR / "bronx_mf"), load_rules()


def moved(outcome):
    return {m.key: m for m in outcome.diff.metrics}


# Bronx: loan 6.5M, NOI 700,000, ARV 12.5M; take-out 6%, min DSCR 1.25, max LTV 70%, min DY 8.5%.
def test_a_higher_takeout_rate_lowers_the_dscr_cap_and_the_exit_dscr(bronx):
    out = run_scenario(*bronx, {"takeout_rate": 0.07})
    m = moved(out)
    assert m["exit_dscr"].before == pytest.approx(700_000 / (6_500_000 * 0.06))
    assert m["exit_dscr"].after == pytest.approx(700_000 / (6_500_000 * 0.07))
    assert m["takeout_max"].before == pytest.approx(8_235_294.12, abs=1)        # debt yield binds
    assert m["takeout_max"].after == pytest.approx(8_000_000)                   # now the DSCR cap
    assert m["refi_cushion"].after == pytest.approx(1_500_000)
    assert [a.key for a in out.assumptions] == ["takeout_rate"]
    assert (out.assumptions[0].before, out.assumptions[0].after) == (0.06, 0.07)


def test_a_rate_change_in_basis_points_is_relative_to_the_current_rate(bronx):
    by_bps = run_scenario(*bronx, {"takeout_rate_change_bps": 100})
    absolute = run_scenario(*bronx, {"takeout_rate": 0.07})
    assert [m.after for m in by_bps.diff.metrics] == pytest.approx(
        [m.after for m in absolute.diff.metrics])
    assert by_bps.assumptions[0].after == pytest.approx(0.07)


def test_lower_noi_moves_the_debt_yield_cap_and_the_cushion(bronx):
    out = run_scenario(*bronx, {"noi_change_pct": -0.10})
    m = moved(out)
    assert m["takeout_max"].after == pytest.approx(630_000 / 0.085)
    assert m["refi_cushion"].after == pytest.approx(630_000 / 0.085 - 6_500_000)
    assert m["exit_dscr"].after == pytest.approx(630_000 / (6_500_000 * 0.06))
    assert "ltc" not in m and "loan_to_arv" not in m               # NOI does not touch these
    assert out.assumptions[0].before == 700_000
    assert out.assumptions[0].after == pytest.approx(630_000)


def test_a_cap_rate_derives_the_arv_from_the_noi(bronx):
    out = run_scenario(*bronx, {"cap_rate": 0.065})
    m = moved(out)
    assert m["loan_to_arv"].after == pytest.approx(6_500_000 / (700_000 / 0.065))
    assert m["implied_cap_rate"].after == pytest.approx(0.065)
    a = out.assumptions[0]
    assert (a.key, a.before, a.after) == ("cap_rate", pytest.approx(0.056), 0.065)


def test_noi_and_cap_rate_together_use_the_changed_noi(bronx):
    out = run_scenario(*bronx, {"noi_change_pct": -0.10, "cap_rate": 0.06})
    assert moved(out)["loan_to_arv"].after == pytest.approx(6_500_000 / (630_000 / 0.06))


def test_a_smaller_loan_scales_the_advance_and_the_holdback_together(bronx):
    out = run_scenario(*bronx, {"loan_amount": 5_500_000})
    m = moved(out)
    assert m["ltc"].after == pytest.approx(5_500_000 / 9_200_000)
    assert m["ltv_as_is"].after == pytest.approx(5_500_000 * (5_300_000 / 6_500_000) / 8_000_000)
    assert out.assumptions[0].after == 5_500_000


def test_takeout_terms_can_be_changed_per_deal(bronx):
    out = run_scenario(*bronx, {"min_dscr": 1.5, "max_ltv": 0.60, "min_debt_yield": 0.09})
    m = moved(out)
    caps = {"dscr": 700_000 / (1.5 * 0.06), "ltv": 0.60 * 12_500_000, "dy": 700_000 / 0.09}
    assert m["takeout_max"].after == pytest.approx(min(caps.values()))


def test_the_stress_assumptions_change_only_the_stress_case(bronx):
    out = run_scenario(*bronx, {"stress_noi_haircut": 0.20, "stress_rate_bump_bps": 200})
    m = moved(out)
    assert set(m) == {"stress_refi_cushion"}
    stressed_noi, rate = 700_000 * 0.8, 0.08
    caps = [stressed_noi / (1.25 * rate), 0.70 * 12_500_000, stressed_noi / 0.085]
    assert m["stress_refi_cushion"].after == pytest.approx(min(caps) - 6_500_000)


def test_a_what_if_can_change_the_call_and_names_the_reasons(bronx):
    out = run_scenario(*bronx, {"noi_change_pct": -0.35})
    assert out.call_before == "screen" and out.call_after != "screen"
    assert out.diff.reasons_added


def test_nothing_is_mutated_and_repeating_gives_the_same_answer(bronx):
    deal, rules = bronx
    before = (deal.model_dump_json(), rules.model_dump_json())
    first = run_scenario(deal, rules, {"takeout_rate": 0.08, "loan_amount": 6_000_000})
    again = run_scenario(deal, rules, {"takeout_rate": 0.08, "loan_amount": 6_000_000})
    assert first == again
    assert (deal.model_dump_json(), rules.model_dump_json()) == before
    assert underwrite(deal, rules).call == "screen"


def test_a_what_if_equals_actually_making_the_change(bronx):
    """The explore and commit paths must not drift: same inputs, same numbers."""
    deal, rules = bronx
    out = run_scenario(deal, rules, {"loan_amount": 5_800_000, "noi_change_pct": -0.05})
    ratio = 5_300_000 / 6_500_000
    changed = set_input(deal, "loan_request.loan_commitment", 5_800_000, "x")
    changed = set_input(changed, "loan_request.initial_advance", 5_800_000 * ratio, "x")
    changed = set_input(changed, "pro_forma.stabilized_noi", 700_000 * 0.95, "x")
    real = underwrite(changed, rules)
    shown = {m.key: m.after for m in out.diff.metrics}
    for key in ("ltc", "ltv_as_is", "debt_yield_stabilized", "exit_dscr", "takeout_max",
                "refi_cushion"):
        assert shown[key] == pytest.approx(getattr(real.metrics, key, None) if hasattr(
            real.metrics, key) else {"exit_dscr": real.exit.exit_dscr,
                                     "takeout_max": real.exit.takeout_max,
                                     "refi_cushion": real.exit.refi_cushion}[key])
    assert out.call_after == real.call


@pytest.mark.parametrize("params,message", [
    ({}, "no assumption"),
    ({"takeout_rate": 0.9}, "take-out rate"),
    ({"takeout_rate": 0.07, "takeout_rate_change_bps": 100}, "one or the other"),
    ({"cap_rate": 0.0}, "cap rate"),
    ({"loan_amount": 5}, "loan amount"),
    ({"noi_change_pct": -2}, "NOI"),
    ({"mystery": 1}, "unknown"),
])
def test_unreasonable_or_unknown_assumptions_are_refused_with_a_reason(bronx, params, message):
    with pytest.raises(ScenarioError, match=message):
        run_scenario(*bronx, params)


def test_every_parameter_has_a_label_and_a_range():
    assert {"takeout_rate", "takeout_rate_change_bps", "noi_change_pct", "cap_rate", "arv",
            "loan_amount", "min_dscr", "max_ltv", "min_debt_yield", "stress_noi_haircut",
            "stress_rate_bump_bps"} == set(PARAMS)
    assert all(p.label and p.low < p.high for p in PARAMS.values())


def test_an_arv_what_if_changes_the_value_ratios(bronx):
    out = run_scenario(*bronx, {"arv": 10_000_000})
    m = moved(out)
    assert m["loan_to_arv"].after == pytest.approx(0.65) and "ltc" not in m
