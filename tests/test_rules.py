"""One test per rule, clean and broken, with strict boundaries (a value at the threshold is OK)."""
import pytest
from bridge.core.calc import StressParams, TakeoutParams, exit_analysis, stress_analysis
from bridge.core.parsers import parse_deal_dir
from bridge.core.rules import evaluate, load_rules
from bridge.core.schema import Metrics, ReconciliationItem

from tests.conftest import DEALS_DIR


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture
def deal():
    return parse_deal_dir(DEALS_DIR / "bronx_mf")


def clean_inputs(rules):
    m = Metrics(total_cost=9_200_000, ltc=0.70, ltv_as_is=0.66, loan_to_arv=0.52,
                dscr_in_place=0.66, debt_yield_stabilized=0.107, implied_cap_rate=0.056)
    ex = exit_analysis(700_000, 12_500_000, 6_500_000, rules.takeout_params())
    st = stress_analysis(700_000, 12_500_000, 6_500_000, rules.takeout_params(),
                         rules.stress_params())
    recon = [ReconciliationItem(name="rent_roll_vs_t12", status="pass", gap=0.02),
             ReconciliationItem(name="sources_vs_uses", status="pass", gap=0.0),
             ReconciliationItem(name="unit_count", status="pass")]
    return m, ex, st, recon


def run(deal, rules, **override):
    m, ex, st, recon = clean_inputs(rules)
    m = m.model_copy(update=override.pop("metrics", {}))
    ex = ex.model_copy(update=override.pop("exit", {}))
    st = st.model_copy(update=override.pop("stress", {}))
    recon = override.pop("recon", recon)
    assert not override
    return evaluate(deal, m, ex, st, recon, rules)


def codes(outcome):
    return [r.code for r in outcome.reasons]


def test_rules_load_and_are_labeled_illustrative(rules):
    assert rules.version == "0.1-illustrative"
    assert "NOT CapMoon" in rules.disclaimer
    assert isinstance(rules.takeout_params(), TakeoutParams)
    assert isinstance(rules.stress_params(), StressParams)


def test_clean_deal_is_screen_with_no_reasons(deal, rules):
    out = run(deal, rules)
    assert out.call == "screen"
    assert out.reasons == []


@pytest.mark.parametrize("metric,code,watch,decline", [
    ("ltc", "LTC", 0.75, 0.85),
    ("ltv_as_is", "LTV_AS_IS", 0.75, 0.85),
    ("loan_to_arv", "LOAN_TO_ARV", 0.65, 0.75),
])
def test_leverage_boundaries(deal, rules, metric, code, watch, decline):
    assert codes(run(deal, rules, metrics={metric: watch})) == []
    assert codes(run(deal, rules, metrics={metric: watch + 0.0001})) == [f"{code}_WATCH"]
    assert codes(run(deal, rules, metrics={metric: decline})) == [f"{code}_WATCH"]
    out = run(deal, rules, metrics={metric: decline + 0.0001})
    assert codes(out) == [f"{code}_DECLINE"]
    assert out.call == "decline"


def test_exit_dscr_boundaries(deal, rules):
    assert codes(run(deal, rules, exit={"exit_dscr": 1.25})) == []
    assert codes(run(deal, rules, exit={"exit_dscr": 1.2499})) == ["EXIT_DSCR_WATCH"]
    assert codes(run(deal, rules, exit={"exit_dscr": 1.10})) == ["EXIT_DSCR_WATCH"]
    assert codes(run(deal, rules, exit={"exit_dscr": 1.0999})) == ["EXIT_DSCR_DECLINE"]


def test_refi_cushion_base_negative_declines(deal, rules):
    assert codes(run(deal, rules, exit={"refi_cushion": 0})) == []
    out = run(deal, rules, exit={"refi_cushion": -1})
    assert codes(out) == ["REFI_CUSHION_NEGATIVE_BASE"]
    assert out.call == "decline"


def test_refi_cushion_stress_negative_is_watch_only_if_base_ok(deal, rules):
    out = run(deal, rules, stress={"refi_cushion": -1})
    assert codes(out) == ["REFI_CUSHION_NEGATIVE_STRESS"]
    assert out.call == "watch"
    both = run(deal, rules, exit={"refi_cushion": -1}, stress={"refi_cushion": -5})
    assert codes(both) == ["REFI_CUSHION_NEGATIVE_BASE"]


def test_implied_cap_rate_boundary(deal, rules):
    assert codes(run(deal, rules, metrics={"implied_cap_rate": 0.05})) == []
    assert codes(run(deal, rules, metrics={"implied_cap_rate": 0.0499})) == ["IMPLIED_CAP_RATE_LOW"]


@pytest.mark.parametrize("name,watch_code,decline_code", [
    ("rent_roll_vs_t12", "RENT_ROLL_VS_T12_WATCH", "RENT_ROLL_VS_T12_DECLINE"),
    ("sources_vs_uses", "SOURCES_VS_USES_WATCH", "SOURCES_VS_USES_DECLINE"),
])
def test_reconciliation_statuses_become_reasons(deal, rules, name, watch_code, decline_code):
    def with_status(status):
        _, _, _, recon = clean_inputs(rules)
        return [r.model_copy(update={"status": status, "gap": 0.2}) if r.name == name else r
                for r in recon]
    assert codes(run(deal, rules, recon=with_status("watch"))) == [watch_code]
    assert codes(run(deal, rules, recon=with_status("decline"))) == [decline_code]


def test_unit_count_mismatch_is_watch(deal, rules):
    _, _, _, recon = clean_inputs(rules)
    recon[2] = recon[2].model_copy(update={"status": "watch"})
    out = run(deal, rules, recon=recon)
    assert codes(out) == ["UNIT_COUNT_MISMATCH"]
    assert out.call == "watch"


def test_asset_type_not_allowed_declines(deal, rules):
    deal.property.asset_type.value = "retail"
    out = run(deal, rules)
    assert codes(out) == ["ASSET_TYPE_NOT_ALLOWED"]
    assert out.call == "decline"


@pytest.mark.parametrize("amount,ok", [
    (1_000_000, True), (999_999, False), (15_000_000, True), (15_000_001, False)])
def test_loan_size_bounds(deal, rules, amount, ok):
    deal.loan_request.loan_commitment.value = amount
    assert (codes(run(deal, rules)) == []) is ok


def test_low_confidence_one_reason_per_field(deal, rules):
    deal.valuation.arv.confidence = 0.79
    deal.loan_request.note_rate.confidence = 0.5
    deal.purchase.purchase_price.confidence = 0.80   # exactly at the flag: fine
    out = run(deal, rules)
    assert codes(out) == ["LOW_CONFIDENCE_FIELD", "LOW_CONFIDENCE_FIELD"]
    assert {r.source_fields[0] for r in out.reasons} == {"arv", "note_rate"}
    assert out.call == "watch"


def test_collects_all_reasons_and_decline_wins(deal, rules):
    out = run(deal, rules, metrics={"ltc": 0.80, "loan_to_arv": 0.80})
    assert codes(out) == ["LTC_WATCH", "LOAN_TO_ARV_DECLINE"]
    assert out.call == "decline"


def test_reasons_carry_their_inputs(deal, rules):
    out = run(deal, rules, metrics={"ltc": 0.80})
    r = out.reasons[0]
    assert (r.code, r.severity, r.value, r.threshold) == ("LTC_WATCH", "watch", 0.80, 0.75)
    assert r.source_fields == ["loan_commitment", "total_cost"]


def test_rule_checks_table_matches_reasons(deal, rules):
    out = run(deal, rules, metrics={"ltc": 0.80})
    row = next(c for c in out.checks if c.metric == "ltc")
    assert (row.value, row.watch_threshold, row.decline_threshold, row.status) == (
        0.80, 0.75, 0.85, "watch")
    assert next(c for c in out.checks if c.metric == "ltv_as_is").status == "pass"
