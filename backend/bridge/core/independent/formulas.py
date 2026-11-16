"""The checker's OWN formulas and rules, written separately from core/calc.py and core/rules.py.

Config is read straight from config/rules.yaml. Both implementations are pinned to the same
answers by data/deals/*/expected.json.
"""
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "rules.yaml"
DOLLAR_KEYS = {"total_cost", "payoff", "cap_dscr", "cap_ltv", "cap_debt_yield", "takeout_max",
               "refi_cushion", "stress_noi", "stress_cap_dscr", "stress_cap_ltv",
               "stress_cap_debt_yield", "stress_takeout_max", "stress_refi_cushion"}
EPS = 1e-9


def load_config(path: str | Path | None = None) -> dict:
    return yaml.safe_load(Path(path or CONFIG_PATH).read_text())


def independent_recompute(i: dict, cfg: dict) -> dict:
    tk, ex = cfg["exit"]["takeout"], cfg["exit"]
    cost = sum(u["amount"] for u in i["uses"])
    loan, adv, noi, arv = i["loan_commitment"], i["initial_advance"], i["stabilized_noi"], i["arv"]
    payoff = loan * (1 + ex["exit_fee_pct"])

    def size(n: float, rate: float, prefix: str) -> dict:
        caps = {"dscr": n / (tk["min_dscr"] * rate), "ltv": tk["max_ltv"] * arv,
                "debt_yield": n / tk["min_debt_yield"]}
        best = min(caps, key=lambda k: (caps[k], ["dscr", "ltv", "debt_yield"].index(k)))
        return {f"{prefix}cap_{k}": v for k, v in caps.items()} | {
            f"{prefix}binding": best, f"{prefix}takeout_max": caps[best],
            f"{prefix}refi_cushion": caps[best] - payoff,
            f"{prefix}exit_dscr": n / (payoff * rate)}

    s_noi = noi * (1 - ex["stress"]["noi_haircut"])
    s_rate = tk["rate"] + ex["stress"]["rate_bump_bps"] / 10000
    gap = lambda a, b: abs(a - b) / b  # noqa: E731
    return {
        "total_cost": cost, "ltc": loan / cost, "ltv_as_is": adv / i["as_is_value"],
        "loan_to_arv": loan / arv, "dscr_in_place": i["in_place_noi"] / (adv * i["note_rate"]),
        "debt_yield_stabilized": noi / loan, "implied_cap_rate": noi / arv, "payoff": payoff,
        **size(noi, tk["rate"], ""), "stress_noi": s_noi, "stress_rate": s_rate,
        **size(s_noi, s_rate, "stress_"),
        "rent_roll_vs_t12_gap": gap(i["rent_roll_annual"], i["t12_rental_income"]),
        "sources_vs_uses_gap": gap(sum(s["amount"] for s in i["sources"]), cost),
    }


def _over(value: float, limit: float) -> bool:
    return round(value - limit, 9) > 0


def _under(value: float, limit: float) -> bool:
    return round(limit - value, 9) > 0


def reconcile_recheck(i: dict, cfg: dict) -> dict[str, dict]:
    m = independent_recompute(i, cfg)
    rc = cfg["reconciliation"]

    def grade(gap: float, band: dict) -> str:
        return "decline" if _over(gap, band["decline_above"]) else (
            "watch" if _over(gap, band["pass_within"]) else "pass")

    return {
        "rent_roll_vs_t12": {"gap": m["rent_roll_vs_t12_gap"],
                             "status": grade(m["rent_roll_vs_t12_gap"], rc["rent_roll_vs_t12"])},
        "sources_vs_uses": {"gap": m["sources_vs_uses_gap"],
                            "status": grade(m["sources_vs_uses_gap"], rc["sources_vs_uses"])},
        "unit_count": {"status": "pass" if i["unit_count"] == i["rent_roll_rows"] else "watch"},
    }


def rules_recheck(i: dict, m: dict, cfg: dict) -> tuple[str, list[str]]:
    """(call, reason codes). LOW_CONFIDENCE_FIELD is an extraction concept and not rechecked."""
    codes: list[tuple[str, str]] = []
    el = cfg["eligibility"]
    if i["asset_type"] not in el["asset_types"]:
        codes.append(("ASSET_TYPE_NOT_ALLOWED", "decline"))
    if _under(i["loan_commitment"], el["loan_size_usd"]["min"]) or _over(
            i["loan_commitment"], el["loan_size_usd"]["max"]):
        codes.append(("LOAN_SIZE_OUT_OF_RANGE", "decline"))
    for key, stem in (("ltc", "LTC"), ("ltv_as_is", "LTV_AS_IS"), ("loan_to_arv", "LOAN_TO_ARV")):
        band = cfg["leverage"][key]
        if _over(m[key], band["decline_above"]):
            codes.append((f"{stem}_DECLINE", "decline"))
        elif _over(m[key], band["watch_above"]):
            codes.append((f"{stem}_WATCH", "watch"))
    band = cfg["exit"]["exit_dscr"]
    if _under(m["exit_dscr"], band["decline_below"]):
        codes.append(("EXIT_DSCR_DECLINE", "decline"))
    elif _under(m["exit_dscr"], band["watch_below"]):
        codes.append(("EXIT_DSCR_WATCH", "watch"))
    if _under(m["refi_cushion"], 0):
        codes.append(("REFI_CUSHION_NEGATIVE_BASE", "decline"))
    elif _under(m["stress_refi_cushion"], 0):
        codes.append(("REFI_CUSHION_NEGATIVE_STRESS", "watch"))
    if _under(m["implied_cap_rate"], cfg["exit"]["implied_cap_rate"]["watch_below"]):
        codes.append(("IMPLIED_CAP_RATE_LOW", "watch"))
    rec = reconcile_recheck(i, cfg)
    for name, stem in (("rent_roll_vs_t12", "RENT_ROLL_VS_T12"),
                       ("sources_vs_uses", "SOURCES_VS_USES")):
        if rec[name]["status"] != "pass":
            codes.append((f"{stem}_{rec[name]['status'].upper()}", rec[name]["status"]))
    if cfg["reconciliation"]["unit_count_must_match"] and rec["unit_count"]["status"] != "pass":
        codes.append(("UNIT_COUNT_MISMATCH", "watch"))
    severities = {s for _, s in codes}
    call = "decline" if "decline" in severities else ("watch" if codes else "screen")
    return call, [c for c, _ in codes]


def compare_metrics(a: dict, b: dict, tol_ratio: float = 1e-4, tol_usd: float = 1.0) -> list[dict]:
    """Mismatches between two flat metric dicts: ratios to tol_ratio, dollars to tol_usd."""
    out = []
    for key, left in a.items():
        right = b.get(key)
        if isinstance(left, str) or isinstance(right, str) or right is None:
            if left != right:
                out.append({"field": key, "a": left, "b": right, "diff": None})
            continue
        tol = tol_usd if key in DOLLAR_KEYS else tol_ratio
        if abs(left - right) > tol:
            out.append({"field": key, "a": left, "b": right, "diff": abs(left - right)})
    return out
