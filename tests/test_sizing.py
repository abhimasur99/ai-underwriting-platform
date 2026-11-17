"""The largest loan that still gets a call: found by re-applying the rules, not estimated."""
import pytest
from bridge.core.parsers import parse_deal_dir
from bridge.core.rules import load_rules
from bridge.core.scenario import scale_loan
from bridge.core.sizing import max_loan
from bridge.core.underwrite import underwrite

from tests.conftest import DEAL_NAMES, DEALS_DIR


def load(name):
    return parse_deal_dir(DEALS_DIR / name), load_rules()


def call_at(deal, rules, amount):
    return underwrite(scale_loan(deal, amount), rules).call


def test_a_deal_that_screens_can_carry_more_and_the_limit_is_exact():
    deal, rules = load("bronx_mf")
    s = max_loan(deal, rules)
    assert s.current_call == "screen" and s.max_loan > s.current_loan
    assert call_at(deal, rules, s.max_loan) == "screen"
    assert call_at(deal, rules, s.max_loan + 1_000) != "screen"      # maximal to the nearest dollar


def test_a_watch_caused_by_leverage_is_limited_by_loan_to_cost():
    deal, rules = load("yonkers_leaseup")        # cost 5.5M, so 75% is 4,125,000
    s = max_loan(deal, rules)
    assert s.current_call == "watch" and s.max_loan == pytest.approx(4_125_000, abs=2)
    assert any("Loan to cost" in b for b in s.binding)


def test_a_stress_only_failure_names_the_stress_cushion_as_the_limit():
    deal, rules = load("queens_mixed_use")
    s = max_loan(deal, rules)
    assert s.max_loan < s.current_loan and call_at(deal, rules, s.max_loan) == "screen"
    assert any("payoff under stress" in b for b in s.binding)


def test_no_loan_size_fixes_a_deal_whose_documents_do_not_agree():
    deal, rules = load("overleveraged_bk")
    s = max_loan(deal, rules)
    assert s.max_loan is None and s.call_at_max is None
    assert {"RENT_ROLL_VS_T12_DECLINE", "SOURCES_VS_USES_DECLINE"} <= set(s.persistent)


def test_avoiding_a_decline_is_a_looser_target_than_screening():
    deal, rules = load("mountvernon_exit")       # declines on the exit: DY cap 2,482,647
    s = max_loan(deal, rules, target="watch")
    assert s.current_call == "decline" and s.max_loan == pytest.approx(2_482_647, abs=5)
    assert call_at(deal, rules, s.max_loan) != "decline"
    assert call_at(deal, rules, s.max_loan + 1_000) == "decline"


def test_the_solver_does_not_change_the_deal_or_the_rules():
    deal, rules = load("bronx_mf")
    before = (deal.model_dump_json(), rules.model_dump_json())
    assert max_loan(deal, rules) == max_loan(deal, rules)
    assert (deal.model_dump_json(), rules.model_dump_json()) == before


@pytest.mark.parametrize("name", DEAL_NAMES)
def test_for_every_sample_deal_the_answer_is_consistent_with_the_rules(name):
    deal, rules = load(name)
    s = max_loan(deal, rules)
    if s.max_loan is None:
        assert s.persistent
        return
    assert call_at(deal, rules, s.max_loan) == "screen"
    assert s.capped or call_at(deal, rules, s.max_loan + 1_000) != "screen"
    assert rules.eligibility.loan_size_usd.min <= s.max_loan <= rules.eligibility.loan_size_usd.max
