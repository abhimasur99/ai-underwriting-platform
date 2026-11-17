"""Setting one input of a deal to a new value, as an override with its reason.

One implementation for everything that changes an input: a reviewer's confirmed edit (a new deal
version, agents/patches.py) and a what-if (core/scenario.py, nothing saved). Sharing it is what
guarantees a what-if gives exactly the numbers the real change would.
"""
import re

from bridge.core.derive import recompute_derived
from bridge.core.schema import Deal, Source, Sourced

SIMPLE_PATHS = {
    "valuation.arv": lambda d: d.valuation,
    "valuation.as_is_value": lambda d: d.valuation,
    "loan_request.loan_commitment": lambda d: d.loan_request,
    "loan_request.initial_advance": lambda d: d.loan_request,
    "loan_request.note_rate": lambda d: d.loan_request,
    "pro_forma.stabilized_noi": lambda d: d.pro_forma,
}
UNIT_RENT = re.compile(r"rent_roll\.units\[(\d+)\]\.monthly_rent$")


class EditError(ValueError):
    pass


def validate_path(deal: Deal, path: str) -> None:
    if path in SIMPLE_PATHS:
        return
    m = UNIT_RENT.match(path)
    if m and int(m.group(1)) < len(deal.rent_roll.units):
        return
    raise EditError(f"{path} cannot be edited in this prototype")


def get_value(deal: Deal, path: str):
    validate_path(deal, path)
    if path in SIMPLE_PATHS:
        return getattr(SIMPLE_PATHS[path](deal), path.rsplit(".", 1)[1]).value
    return deal.rent_roll.units[int(UNIT_RENT.match(path).group(1))].monthly_rent


def set_input(deal: Deal, path: str, new: float, reason: str) -> Deal:
    """A copy of the deal with `path` set to `new` and the derived totals recomputed. The version
    is left alone: the caller decides whether this becomes a new version."""
    validate_path(deal, path)
    if not reason.strip():
        raise EditError("a change to an input needs a reason")
    out = deal.model_copy(deep=True)
    if path in SIMPLE_PATHS:
        holder, name = SIMPLE_PATHS[path](out), path.rsplit(".", 1)[1]
        setattr(holder, name, Sourced[float](
            value=float(new), source=Source(kind="override", reason=reason), confidence=1.0))
    else:
        out.rent_roll.units[int(UNIT_RENT.match(path).group(1))].monthly_rent = float(new)
    return recompute_derived(out)
