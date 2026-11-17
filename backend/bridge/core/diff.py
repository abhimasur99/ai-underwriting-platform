"""What changed between two versions of a deal. Pure: two results in, a comparison out.

The reviewer chat and the deal page use it to say, after an edit, which input moved, which metrics
moved with it, and whether the call changed. Only metrics that actually changed are listed.
"""
from pydantic import BaseModel

from bridge.core.schema import UnderwritingResult

# (key, label, kind). The kind says how to show it: pct, usd or mult.
METRICS = [
    ("ltc", "Loan to cost", "pct"),
    ("ltv_as_is", "Loan to value (as-is)", "pct"),
    ("loan_to_arv", "Loan to ARV", "pct"),
    ("dscr_in_place", "In-place DSCR", "mult"),
    ("debt_yield_stabilized", "Stabilized debt yield", "pct"),
    ("implied_cap_rate", "Implied cap rate", "pct"),
    ("exit_dscr", "Exit DSCR", "mult"),
    ("takeout_max", "Take-out maximum", "usd"),
    ("refi_cushion", "Refi cushion", "usd"),
    ("stress_refi_cushion", "Refi cushion under stress", "usd"),
]
EPSILON = 1e-9


class MetricChange(BaseModel):
    key: str
    label: str
    kind: str
    before: float
    after: float


class InputChange(BaseModel):
    path: str
    old: str
    new: str
    reason: str


class VersionDiff(BaseModel):
    from_version: int
    to_version: int
    call_before: str
    call_after: str
    metrics: list[MetricChange] = []
    inputs: list[InputChange] = []
    reasons_added: list[str] = []
    reasons_removed: list[str] = []


def value_of(result: UnderwritingResult, key: str) -> float:
    if key == "exit_dscr":
        return result.exit.exit_dscr
    if key == "takeout_max":
        return result.exit.takeout_max
    if key == "refi_cushion":
        return result.exit.refi_cushion
    if key == "stress_refi_cushion":
        return result.stress.refi_cushion
    return getattr(result.metrics, key)


def compare(before: UnderwritingResult, after: UnderwritingResult,
            inputs: list[InputChange]) -> VersionDiff:
    moved = [MetricChange(key=k, label=label, kind=kind, before=value_of(before, k),
                          after=value_of(after, k))
             for k, label, kind in METRICS
             if abs(value_of(before, k) - value_of(after, k)) > EPSILON]
    was, now = {r.code for r in before.reasons}, {r.code for r in after.reasons}
    return VersionDiff(
        from_version=before.deal_version, to_version=after.deal_version,
        call_before=before.call, call_after=after.call, metrics=moved, inputs=inputs,
        reasons_added=sorted(now - was), reasons_removed=sorted(was - now))
