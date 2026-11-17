"""What-ifs: the same calculator and the same rules with some assumptions changed.

Nothing here is saved and nothing is mutated: a what-if works on copies, so the deal, its versions,
the memo and the independent check are untouched. Inputs are changed with `edit.set_input`, the
same function a confirmed edit uses, and the result is the same `underwrite` a real run would give,
so a what-if shows exactly the numbers the real change would produce.

Take-out terms and stress settings are global in config/rules.yaml; here they can be tried per
deal, as a question, without becoming an exception to the box.
"""
from dataclasses import dataclass

from pydantic import BaseModel

from bridge.core.diff import VersionDiff, compare
from bridge.core.edit import set_input
from bridge.core.rules import RulesConfig
from bridge.core.schema import Deal
from bridge.core.underwrite import underwrite

REASON = "what-if (not saved)"


class ScenarioError(ValueError):
    pass


@dataclass(frozen=True)
class Param:
    label: str          # as shown
    noun: str           # inside a sentence
    kind: str           # pct, usd, mult or bps (how to show the assumption)
    low: float
    high: float
    entry: str = ""     # how the number is entered, when that differs (NOI is a % change)

    @property
    def unit(self) -> str:
        return self.entry or self.kind


PARAMS = {
    "takeout_rate": Param("Take-out rate", "take-out rate", "pct", 0.005, 0.30),
    "takeout_rate_change_bps": Param("Take-out rate change", "take-out rate change", "bps",
                                     -500, 1500),
    "noi_change_pct": Param("Stabilized NOI", "NOI change", "usd", -0.9, 1.0, "pct"),
    "cap_rate": Param("Cap rate on stabilized NOI", "cap rate", "pct", 0.01, 0.25),
    "arv": Param("After-repair value", "ARV", "usd", 100_000, 1_000_000_000),
    "loan_amount": Param("Loan amount", "loan amount", "usd", 100_000, 200_000_000),
    "min_dscr": Param("Minimum take-out DSCR", "minimum DSCR", "mult", 0.5, 5.0),
    "max_ltv": Param("Maximum take-out LTV", "maximum LTV", "pct", 0.1, 1.0),
    "min_debt_yield": Param("Minimum take-out debt yield", "minimum debt yield", "pct", 0.01, 0.5),
    "stress_noi_haircut": Param("Stress NOI haircut", "stress NOI haircut", "pct", 0.0, 0.9),
    "stress_rate_bump_bps": Param("Stress rate increase", "stress rate increase", "bps", 0, 1500),
}
EXCLUSIVE = [("takeout_rate", "takeout_rate_change_bps"), ("cap_rate", "arv")]


class Assumption(BaseModel):
    key: str
    label: str
    kind: str           # pct, usd, mult or bps
    before: float
    after: float


class Outcome(BaseModel):
    """The current case against the changed one."""
    call_before: str
    call_after: str
    assumptions: list[Assumption]
    diff: VersionDiff


def show(kind: str, value: float) -> str:
    if kind == "pct":
        return f"{value * 100:g}%"
    if kind == "usd":
        return f"${value:,.0f}"
    if kind == "mult":
        return f"{value:g}x"
    return f"{value:g} bps"


def validate(params: dict[str, float]) -> None:
    if not params:
        raise ScenarioError("no assumption was given to try")
    for key, value in params.items():
        if key not in PARAMS:
            raise ScenarioError(f"unknown assumption {key!r}")
        p = PARAMS[key]
        if not p.low <= value <= p.high:
            raise ScenarioError(f"a {p.noun} of {show(p.unit, value)} is outside the range this "
                                f"tool accepts ({show(p.unit, p.low)} to {show(p.unit, p.high)})")
    for a, b in EXCLUSIVE:
        if a in params and b in params:
            raise ScenarioError(f"give the {PARAMS[a].noun} or the {PARAMS[b].noun}, one or the "
                                "other")


def scale_loan(deal: Deal, amount: float) -> Deal:
    """The loan at a new size, the initial advance and the holdback scaling together."""
    ratio = deal.loan_request.initial_advance.value / deal.loan_request.loan_commitment.value
    out = set_input(deal, "loan_request.loan_commitment", amount, REASON)
    return set_input(out, "loan_request.initial_advance", amount * ratio, REASON)


def apply(deal: Deal, rules: RulesConfig, params: dict[str, float]
          ) -> tuple[Deal, RulesConfig, list[Assumption]]:
    """The changed copies of the deal and the rules, and what was changed."""
    validate(params)
    rules2, changed = rules.model_copy(deep=True), []
    take, stress = rules2.exit.takeout, rules2.exit.stress

    def note(key: str, before: float, after: float, label: str | None = None) -> None:
        changed.append(Assumption(key=key, label=label or PARAMS[key].label,
                                  kind=PARAMS[key].kind, before=before, after=after))

    if "takeout_rate" in params or "takeout_rate_change_bps" in params:
        was = take.rate
        take.rate = params.get("takeout_rate", was + params.get("takeout_rate_change_bps", 0)
                               / 10_000)
        note("takeout_rate", was, take.rate, "Take-out rate")
    for key, holder, name in (("min_dscr", take, "min_dscr"), ("max_ltv", take, "max_ltv"),
                              ("min_debt_yield", take, "min_debt_yield"),
                              ("stress_noi_haircut", stress, "noi_haircut"),
                              ("stress_rate_bump_bps", stress, "rate_bump_bps")):
        if key in params:
            note(key, getattr(holder, name), params[key])
            setattr(holder, name, params[key])

    out = deal
    if "loan_amount" in params:
        note("loan_amount", deal.loan_request.loan_commitment.value, params["loan_amount"])
        out = scale_loan(out, params["loan_amount"])
    if "noi_change_pct" in params:
        was = out.pro_forma.stabilized_noi.value
        out = set_input(out, "pro_forma.stabilized_noi", was * (1 + params["noi_change_pct"]),
                        REASON)
        note("noi_change_pct", was, out.pro_forma.stabilized_noi.value)
    if "cap_rate" in params:
        noi, was_arv = out.pro_forma.stabilized_noi.value, out.valuation.arv.value
        note("cap_rate", noi / was_arv, params["cap_rate"])
        out = set_input(out, "valuation.arv", noi / params["cap_rate"], REASON)
    if "arv" in params:
        note("arv", out.valuation.arv.value, params["arv"])
        out = set_input(out, "valuation.arv", params["arv"], REASON)
    return out, rules2, changed


def run_scenario(deal: Deal, rules: RulesConfig, params: dict[str, float]) -> Outcome:
    before = underwrite(deal, rules)
    changed_deal, changed_rules, assumptions = apply(deal, rules, params)
    after = underwrite(changed_deal, changed_rules)
    return Outcome(call_before=before.call, call_after=after.call, assumptions=assumptions,
                   diff=compare(before, after, []))
