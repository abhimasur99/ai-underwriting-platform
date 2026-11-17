"""Memo narrative contract: text carries `{{placeholders}}`, code fills the numbers.

A digit outside a placeholder fails validation, so a model can never type a number into a memo.
"""
import re

from bridge.core import format as f
from bridge.core.schema import UnderwritingResult

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")


class NarrativeError(ValueError):
    pass


def placeholder_values(r: UnderwritingResult) -> dict[str, str]:
    m, ex, st = r.metrics, r.exit, r.stress
    values = {
        "call": r.call.upper(),
        "reasons.count": str(len(r.reasons)),
        "metrics.total_cost": f.usd(m.total_cost),
        "metrics.ltc": f.pct(m.ltc),
        "metrics.ltv_as_is": f.pct(m.ltv_as_is),
        "metrics.loan_to_arv": f.pct(m.loan_to_arv),
        "metrics.dscr_in_place": f.mult(m.dscr_in_place),
        "metrics.debt_yield_stabilized": f.pct(m.debt_yield_stabilized),
        "metrics.implied_cap_rate": f.pct(m.implied_cap_rate),
    }
    for prefix, a in (("exit", ex), ("stress", st)):
        values.update({
            f"{prefix}.payoff": f.usd(a.payoff),
            f"{prefix}.noi": f.usd(a.noi),
            f"{prefix}.rate": f.pct(a.rate),
            f"{prefix}.takeout_max": f.usd(a.takeout_max),
            f"{prefix}.refi_cushion": f.usd(a.refi_cushion),
            f"{prefix}.exit_dscr": f.mult(a.exit_dscr),
            f"{prefix}.binding": f.BINDING_LABEL[a.binding],
            f"{prefix}.cap_dscr": f.usd(a.caps.dscr),
            f"{prefix}.cap_ltv": f.usd(a.caps.ltv),
            f"{prefix}.cap_debt_yield": f.usd(a.caps.debt_yield),
        })
    for item in r.reconciliation:
        if item.gap is not None:
            values[f"recon.{item.name}"] = f.pct(item.gap)
    return values


def fill(text: str, result: UnderwritingResult) -> str:
    values = placeholder_values(result)

    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise NarrativeError(f"unknown placeholder: {{{{{key}}}}}")
        return values[key]

    return PLACEHOLDER.sub(replace, text)


def find_stray_digits(text: str) -> list[str]:
    return re.findall(r"\d+", PLACEHOLDER.sub("", text))


def validate_narrative(narrative: dict[str, str]) -> None:
    for section, text in narrative.items():
        stray = find_stray_digits(text)
        if stray:
            # quote the words around the first offender so a model (or a person) can fix it
            bare = PLACEHOLDER.sub("", text)
            at = re.search(r"\d", bare)
            near = bare[max(0, at.start() - 25):at.start() + 25].strip() if at else ""
            raise NarrativeError(f"narrative section {section!r} has digits outside "
                                 f"placeholders: {stray} (near: \"{near}\")")
