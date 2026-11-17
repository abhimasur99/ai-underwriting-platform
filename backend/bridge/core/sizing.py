"""The largest loan that still gets a given call, found by re-applying the rules.

The loan is resized as `scenario.scale_loan` does (the initial advance and the holdback scale
together; value, NOI, cost and the documents are held), the full underwriting and rules run at
each size, and the largest size whose call is good enough is found by bisection to the dollar. No
formula is guessed: whatever the rules say at that size is the answer, including every limit the
rules apply at once.

A loan below the program's minimum size is declined by the rules, so the search runs between the
minimum and the maximum the program allows. If even the smallest loan does not reach the call,
resizing cannot fix the deal, and the reasons that remain are returned.
"""
from pydantic import BaseModel

from bridge.core import format as f
from bridge.core.rules import RulesConfig
from bridge.core.scenario import scale_loan
from bridge.core.schema import Deal, UnderwritingResult
from bridge.core.underwrite import underwrite

RANK = {"screen": 0, "watch": 1, "decline": 2}
GRID = 60


class Sizing(BaseModel):
    target: str                     # the call the loan must still get: screen, or watch
    current_loan: float
    current_call: str
    max_loan: float | None          # None: no loan size reaches the target
    call_at_max: str | None
    binding: list[str] = []         # what changes the call just above the maximum
    persistent: list[str] = []      # reasons that remain at any size, when none works
    capped: bool = False            # the maximum is the program's own limit, not a rule


def _result(deal: Deal, rules: RulesConfig, amount: float) -> UnderwritingResult:
    return underwrite(scale_loan(deal, amount), rules)


def _limit(reason) -> str:
    """'Loan to cost (limit 75.00%)': the rule that applies, in words."""
    for prefix, text, fmt in f._REASONS:
        if reason.code == prefix or (prefix.endswith("_") and reason.code.startswith(prefix)):
            if reason.threshold is None:
                return text
            return f"{text} (limit {fmt(reason.threshold)})"
    return reason.code


def reason_label(code: str) -> str:
    """A reason code in words: RENT_ROLL_VS_T12_DECLINE is 'Rent roll and T-12 income disagree'."""
    for prefix, text, _ in f._REASONS:
        if code == prefix or (prefix.endswith("_") and code.startswith(prefix)):
            return text
    return code


def max_loan(deal: Deal, rules: RulesConfig, target: str = "screen") -> Sizing:
    size = rules.eligibility.loan_size_usd
    current = deal.loan_request.loan_commitment.value
    now = underwrite(deal, rules)

    def good(amount: float) -> bool:
        return RANK[_result(deal, rules, amount).call] <= RANK[target]

    base = dict(target=target, current_loan=current, current_call=now.call)
    low, high = float(size.min), float(size.max)
    if not good(low):
        remaining = _result(deal, rules, low)
        return Sizing(**base, max_loan=None, call_at_max=None,
                      persistent=[r.code for r in remaining.reasons
                                  if RANK[r.severity] > RANK[target]])
    if good(high):
        top = _result(deal, rules, high)
        return Sizing(**base, max_loan=high, call_at_max=top.call, capped=True)

    # Find the largest size on a coarse grid that is good, then refine to the dollar. The grid
    # guards against the rare case where "good" is not a single stretch from the minimum.
    step = (high - low) / GRID
    last = max(i for i in range(GRID + 1) if good(low + i * step))
    low, high = low + last * step, min(low + (last + 1) * step, high)
    while high - low > 1:
        mid = (low + high) / 2
        low, high = (mid, high) if good(mid) else (low, mid)
    # `high` is the first size that is not good, to within a dollar: the whole dollar at or below it
    # is the answer if it is good, else the one just under `low`.
    amount = float(int(high)) if good(float(int(high))) else float(int(low))
    at, above = _result(deal, rules, amount), _result(deal, rules, amount + 1_000)
    had = {r.code for r in at.reasons}
    return Sizing(**base, max_loan=amount, call_at_max=at.call,
                  binding=[_limit(r) for r in above.reasons if r.code not in had])
