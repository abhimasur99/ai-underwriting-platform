"""Reviewer edits: data patches (new deal version), narrative patches, judgment overrides."""
from bridge.core import edit
from bridge.core.schema import Deal


class PatchError(ValueError):
    pass


def validate_data_path(deal: Deal, path: str) -> None:
    try:
        edit.validate_path(deal, path)
    except edit.EditError as exc:
        raise PatchError(str(exc)) from exc


def get_value(deal: Deal, path: str):
    validate_data_path(deal, path)
    return edit.get_value(deal, path)


def apply_data_patch(deal: Deal, path: str, new: float, reason: str) -> Deal:
    """A new deal version with the edit applied and derived totals recomputed."""
    validate_data_path(deal, path)
    if not reason.strip():
        raise PatchError("a data edit needs a reason")
    out = edit.set_input(deal, path, new, reason)
    out.version = deal.version + 1
    return out
