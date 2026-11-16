"""Pure metric and exit-sizing functions. The ONLY place metrics are computed.

Formulas are in docs/rules.md. Interest-only, no amortization. No web or LLM imports.
`FORMULAS` gives the human-readable formula for each metric (logged with every tool call).
"""
from collections.abc import Iterable
from dataclasses import dataclass

from bridge.core.schema import Deal, ExitAnalysis, Metrics, TakeoutCaps


class CalcError(ValueError):
    """Raised on impossible inputs (e.g. a zero denominator). Never return a silent default."""


@dataclass(frozen=True)
class TakeoutParams:
    rate: float
    min_dscr: float
    max_ltv: float
    min_debt_yield: float
    exit_fee_pct: float


@dataclass(frozen=True)
class StressParams:
    noi_haircut: float
    rate_bump_bps: float


FORMULAS = {
    "total_cost": "sum(uses)",
    "ltc": "loan_commitment / total_cost",
    "ltv_as_is": "initial_advance / as_is_value",
    "loan_to_arv": "loan_commitment / arv",
    "dscr_in_place": "in_place_noi / (initial_advance * note_rate)",
    "debt_yield_stabilized": "stabilized_noi / loan_commitment",
    "implied_cap_rate": "stabilized_noi / arv",
    "payoff": "loan_commitment * (1 + exit_fee_pct)",
    "dscr_cap": "noi / (min_dscr * takeout_rate)",
    "ltv_cap": "max_ltv * arv",
    "debt_yield_cap": "noi / min_debt_yield",
    "takeout_max": "min(dscr_cap, ltv_cap, debt_yield_cap)",
    "refi_cushion": "takeout_max - payoff",
    "exit_dscr": "noi / (payoff * takeout_rate)",
    "stress_noi": "noi * (1 - noi_haircut)",
    "stress_rate": "takeout_rate + rate_bump_bps / 10000",
    "reconciliation_gap": "abs(a - b) / b",
}


def _div(numerator: float, denominator: float, what: str) -> float:
    if denominator == 0:
        raise CalcError(f"{what}: denominator is zero")
    return numerator / denominator


def total_cost(uses: Iterable[float]) -> float:
    return float(sum(uses))


def ltc(loan_commitment: float, total_cost: float) -> float:
    return _div(loan_commitment, total_cost, "ltc")


def ltv_as_is(initial_advance: float, as_is_value: float) -> float:
    return _div(initial_advance, as_is_value, "ltv_as_is")


def loan_to_arv(loan_commitment: float, arv: float) -> float:
    return _div(loan_commitment, arv, "loan_to_arv")


def dscr_in_place(in_place_noi: float, initial_advance: float, note_rate: float) -> float:
    return _div(in_place_noi, initial_advance * note_rate, "dscr_in_place")


def debt_yield_stabilized(stabilized_noi: float, loan_commitment: float) -> float:
    return _div(stabilized_noi, loan_commitment, "debt_yield_stabilized")


def implied_cap_rate(stabilized_noi: float, arv: float) -> float:
    return _div(stabilized_noi, arv, "implied_cap_rate")


def reconciliation_gap(a: float, b: float) -> float:
    """Relative gap of `a` against the reference value `b`."""
    return _div(abs(a - b), b, "reconciliation_gap")


def payoff(loan_commitment: float, exit_fee_pct: float) -> float:
    return loan_commitment * (1 + exit_fee_pct)


def _size(noi: float, arv: float, loan_commitment: float, p: TakeoutParams,
          rate: float) -> ExitAnalysis:
    pay = payoff(loan_commitment, p.exit_fee_pct)
    caps = TakeoutCaps(
        dscr=_div(noi, p.min_dscr * rate, "dscr_cap"),
        ltv=p.max_ltv * arv,
        debt_yield=_div(noi, p.min_debt_yield, "debt_yield_cap"),
    )
    values = caps.model_dump()
    binding = min(values, key=values.get)  # ties resolve in the order dscr, ltv, debt_yield
    takeout_max = values[binding]
    return ExitAnalysis(
        payoff=pay, noi=noi, rate=rate, caps=caps, binding=binding, takeout_max=takeout_max,
        refi_cushion=takeout_max - pay,
        exit_dscr=_div(noi, pay * rate, "exit_dscr"),
    )


def exit_analysis(noi: float, arv: float, loan_commitment: float,
                  p: TakeoutParams) -> ExitAnalysis:
    return _size(noi, arv, loan_commitment, p, p.rate)


def stress_analysis(noi: float, arv: float, loan_commitment: float, p: TakeoutParams,
                    s: StressParams) -> ExitAnalysis:
    return _size(noi * (1 - s.noi_haircut), arv, loan_commitment, p,
                 p.rate + s.rate_bump_bps / 10000)


def compute_metrics(deal: Deal) -> Metrics:
    """All headline metrics for a deal. Inputs come only from the deal's Sourced values."""
    lr, val = deal.loan_request, deal.valuation
    cost = total_cost(row.amount for row in deal.sources_uses.uses)
    noi = deal.pro_forma.stabilized_noi.value
    commitment = lr.loan_commitment.value
    return Metrics(
        total_cost=cost,
        ltc=ltc(commitment, cost),
        ltv_as_is=ltv_as_is(lr.initial_advance.value, val.as_is_value.value),
        loan_to_arv=loan_to_arv(commitment, val.arv.value),
        dscr_in_place=dscr_in_place(
            deal.t12.in_place_noi.value, lr.initial_advance.value, lr.note_rate.value),
        debt_yield_stabilized=debt_yield_stabilized(noi, commitment),
        implied_cap_rate=implied_cap_rate(noi, val.arv.value),
    )
