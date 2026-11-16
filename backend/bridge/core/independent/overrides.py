"""Apply confirmed reviewer data patches to the checker's OWN parsed inputs, so the check still
means something after an edit. Written separately from the chief's patch application."""
import re

SIMPLE = {
    "valuation.arv": "arv", "valuation.as_is_value": "as_is_value",
    "loan_request.loan_commitment": "loan_commitment",
    "loan_request.initial_advance": "initial_advance", "loan_request.note_rate": "note_rate",
    "pro_forma.stabilized_noi": "stabilized_noi",
}
UNIT_RENT = re.compile(r"rent_roll\.units\[(\d+)\]\.monthly_rent$")


def apply_overrides(inputs: dict, patches: list[dict]) -> dict:
    out = {**inputs, "rent_roll_units": [dict(u) for u in inputs["rent_roll_units"]]}
    for patch in patches:
        path, new = patch["path"], patch["new"]
        if path in SIMPLE:
            out[SIMPLE[path]] = float(new)
        elif (m := UNIT_RENT.match(path)):
            out["rent_roll_units"][int(m.group(1))]["rent"] = float(new)
        else:
            raise ValueError(f"checker cannot apply override at {path}")
    out["rent_roll_annual"] = 12 * sum(u["rent"] for u in out["rent_roll_units"]
                                       if u["status"] == "occupied")
    return out
