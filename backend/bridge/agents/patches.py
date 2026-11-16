"""Reviewer edits: data patches (new deal version), narrative patches, judgment overrides."""
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


class PatchError(ValueError):
    pass


def validate_data_path(deal: Deal, path: str) -> None:
    if path in SIMPLE_PATHS:
        return
    m = UNIT_RENT.match(path)
    if m and int(m.group(1)) < len(deal.rent_roll.units):
        return
    raise PatchError(f"{path} cannot be edited in this prototype")


def get_value(deal: Deal, path: str):
    validate_data_path(deal, path)
    if path in SIMPLE_PATHS:
        return getattr(SIMPLE_PATHS[path](deal), path.rsplit(".", 1)[1]).value
    return deal.rent_roll.units[int(UNIT_RENT.match(path).group(1))].monthly_rent


def apply_data_patch(deal: Deal, path: str, new: float, reason: str) -> Deal:
    """A new deal version with the edit applied and derived totals recomputed."""
    validate_data_path(deal, path)
    if not reason.strip():
        raise PatchError("a data edit needs a reason")
    out = deal.model_copy(deep=True)
    out.version = deal.version + 1
    if path in SIMPLE_PATHS:
        holder, name = SIMPLE_PATHS[path](out), path.rsplit(".", 1)[1]
        setattr(holder, name, Sourced[float](
            value=float(new), source=Source(kind="override", reason=reason), confidence=1.0))
    else:
        out.rent_roll.units[int(UNIT_RENT.match(path).group(1))].monthly_rent = float(new)
    return recompute_derived(out)
