"""Cross-document reconciliation: rent roll vs T-12, sources vs uses, unit count."""
from bridge.core import calc
from bridge.core.rules import RulesConfig, _GapCfg, above
from bridge.core.schema import Deal, Flag, ReconciliationItem

TOLERANCE_USD = 1.0


def _status(gap: float, cfg: _GapCfg) -> str:
    if above(gap, cfg.decline_above):
        return "decline"
    if above(gap, cfg.pass_within):
        return "watch"
    return "pass"


def reconcile_all(deal: Deal, rules: RulesConfig) -> tuple[list[ReconciliationItem], list[Flag]]:
    rr = deal.rent_roll.annual_occupied_rent.value
    t12 = deal.t12.rental_income.value
    rr_gap = calc.reconciliation_gap(rr, t12)

    su = deal.sources_uses
    total_sources = sum(r.amount for r in su.sources)
    total_uses = sum(r.amount for r in su.uses)
    su_gap = calc.reconciliation_gap(total_sources, total_uses)

    stated_units = deal.property.unit_count.value
    rows = len(deal.rent_roll.units)

    items = [
        ReconciliationItem(
            name="rent_roll_vs_t12", a=rr, b=t12, gap=rr_gap,
            status=_status(rr_gap, rules.reconciliation.rent_roll_vs_t12),
            detail="12 x occupied monthly rent vs T-12 gross rental income"),
        ReconciliationItem(
            name="sources_vs_uses", a=total_sources, b=total_uses, gap=su_gap,
            status=_status(su_gap, rules.reconciliation.sources_vs_uses),
            detail="sum of source rows vs sum of use rows"),
        ReconciliationItem(
            name="unit_count", a=stated_units, b=rows,
            status="pass" if stated_units == rows else "watch",
            detail="stated unit count vs rent roll rows"),
    ]

    flags = []
    for label, code, stated, computed in (
            ("sources", "SOURCES_TOTAL_MISMATCH", su.stated_total_sources.value, total_sources),
            ("uses", "USES_TOTAL_MISMATCH", su.stated_total_uses.value, total_uses)):
        if abs(stated - computed) > TOLERANCE_USD:
            flags.append(Flag(
                code=code, field=f"sources_uses.{label}",
                message=f"Stated total {label} {stated:,.0f} differs from the sum of its "
                        f"rows {computed:,.0f}"))
    return items, flags
