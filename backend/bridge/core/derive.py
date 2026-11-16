"""Recompute the code-derived totals of a Deal after an edit (rent roll annual, T-12 sums).

These are data totals the parsers also derive; recomputing them here keeps an edited deal
consistent without re-reading documents.
"""
from bridge.core.parsers.sourcing import derived
from bridge.core.schema import Deal


def recompute_derived(deal: Deal) -> Deal:
    units = deal.rent_roll.units
    annual = 12 * sum(u.monthly_rent for u in units if u.status == "occupied")
    old = deal.rent_roll.annual_occupied_rent.source
    deal.rent_roll.annual_occupied_rent = derived(
        float(annual), "12 * sum(monthly_rent where status == occupied)", old.doc, old.locator)

    lines = deal.t12.lines
    income = sum(ln.total for ln in lines if ln.category == "income")
    expense = sum(ln.total for ln in lines if ln.category == "expense")
    rental = sum(ln.total for ln in lines if "rental income" in ln.line_item.lower())
    src = deal.t12.in_place_noi.source
    deal.t12.rental_income = derived(rental, "total of the Gross rental income line",
                                     src.doc, src.locator)
    deal.t12.total_income = derived(income, "sum of income line totals", src.doc, src.locator)
    deal.t12.total_expenses = derived(expense, "sum of expense line totals", src.doc, src.locator)
    deal.t12.in_place_noi = derived(income - expense, "total income - total expenses",
                                    src.doc, src.locator)
    return deal
