#!/usr/bin/env python3
"""Generate the three sample deals and their answer keys (expected.json).

Sample, made-up data only. Deterministic: no randomness, so reruns give identical files.

The reference calculation in this file exists ONLY to produce expected.json. The product's own
calculators (backend/bridge/core/calc.py, Sprint 1) are built separately and must match
expected.json within tolerance (dollars exact to $1, ratios to 1e-4).

Usage: python3 scripts/generate_sample_deals.py   (needs PyYAML)
"""
import csv
import json
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RULES = yaml.safe_load((ROOT / "config" / "rules.yaml").read_text())
MONTHS = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04",
          "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]

BASE_TYPES = {
    "bronx_mf": {"studio": (450, 1320), "1br": (620, 1640), "2br": (840, 1980)},
    "queens_mixed_use": {"1br": (650, 1950), "2br": (880, 2450)},
    "overleveraged_bk": {"studio": (400, 1150), "1br": (560, 1400), "2br": (760, 1750)},
}

DEALS = [
    {
        "slug": "bronx_mf", "deal_id": "D-0042", "name": "Bronx multifamily, 40 units",
        "address": "1200 Sample Avenue, Bronx, NY 10456 (fictional)", "asset_type": "multifamily",
        "year_built": 1928, "floors": [(1, 10), (2, 10), (3, 10), (4, 10)],
        "types": ["studio", "studio", "1br", "1br", "1br", "1br", "2br", "2br", "2br", "2br"],
        "vacant": {"104", "207", "310", "408"}, "step": 20, "retail": [],
        "t12_factors": [0.970, 0.975, 0.980, 0.985, 0.980, 0.975, 0.980, 0.985, 0.980, 0.975, 0.980, 0.985],
        "other_income_annual": 12000,
        "expenses": {"Real estate taxes": 118000, "Insurance": 42000, "Utilities": 61000,
                     "Repairs and maintenance": 38000, "Payroll": 44000, "Management fee": 28800,
                     "Contract services": 12000, "Administrative and other": 14000},
        "purchase_price": 8000000, "renovation_budget": 1200000, "equity": 2700000,
        "loan_commitment": 6500000, "initial_advance": 5300000, "as_is_value": 8000000, "arv": 12500000,
        "note_rate": 0.105, "term_months": 18, "points": 0.02,
        "sources_stated_total": 9200000, "uses_stated_total": 9200000,
        "pro_forma": {"gpr": 1070400, "vacancy_pct": 0.05, "other_income": 20000, "opex": 336880},
        "reno": [("Unit interior renovations", 540000), ("Kitchens and baths", 220000),
                 ("Roof and facade", 150000), ("Boiler and heating", 90000),
                 ("Electrical and plumbing risers", 80000), ("Common areas and lobby", 50000),
                 ("Soft costs (architect, permits)", 40000), ("Contingency", 30000)],
        "sponsor": "Harborline Residential LLC (fictional)",
        "sponsor_bio": "Sample sponsor with 6 prior renovations in the Bronx and Upper Manhattan (fictional).",
        "plan": "Renovate 24 units and all common systems, re-lease at market, refinance into a bank take-out.",
        "closing_date": "2026-12-15", "deposit": 800000, "seller": "Sample Seller Holdings LP (fictional)",
        "expected_call": "screen",
    },
    {
        "slug": "queens_mixed_use", "deal_id": "D-0043", "name": "Queens mixed-use, 18 residential + 2 retail",
        "address": "47-10 Sample Boulevard, Queens, NY 11101 (fictional)", "asset_type": "mixed_use",
        "year_built": 1931, "floors": [(2, 6), (3, 6), (4, 6)],
        "types": ["1br", "1br", "2br", "2br", "2br", "1br"], "vacant": {"304"}, "step": 25,
        "retail": [("R1", 1400, 4800), ("R2", 1100, 3600)],
        "t12_factors": [0.980, 0.980, 0.985, 0.980, 0.975, 0.985, 0.980, 0.980, 0.985, 0.980, 0.980, 0.975],
        "other_income_annual": 5000,
        "expenses": {"Real estate taxes": 62000, "Insurance": 21000, "Utilities": 28000,
                     "Repairs and maintenance": 22000, "Payroll": 18000, "Management fee": 14000,
                     "Contract services": 6000, "Administrative and other": 7000},
        "purchase_price": 5000000, "renovation_budget": 800000, "equity": 1500000,
        "loan_commitment": 4300000, "initial_advance": 3500000, "as_is_value": 5000000, "arv": 7000000,
        "note_rate": 0.105, "term_months": 18, "points": 0.02,
        "sources_stated_total": 5800000, "uses_stated_total": 5800000,
        "pro_forma": {"gpr": 668000, "vacancy_pct": 0.05, "other_income": 5400, "opex": 240000},
        "reno": [("Unit interior renovations", 300000), ("Storefront and retail fit-out", 120000),
                 ("Roof and facade", 120000), ("Boiler and heating", 70000),
                 ("Electrical and plumbing", 60000), ("Common areas", 40000),
                 ("Soft costs (architect, permits)", 50000), ("Contingency", 40000)],
        "sponsor": "Larchmont Partners LLC (fictional)",
        "sponsor_bio": "Sample sponsor with 3 prior mixed-use projects in Queens (fictional).",
        "plan": "Renovate residential units and storefronts, re-lease, refinance into a bank take-out.",
        "closing_date": "2026-12-22", "deposit": 500000, "seller": "Sample Estate Trust (fictional)",
        "expected_call": "watch",
    },
    {
        "slug": "overleveraged_bk", "deal_id": "D-0044", "name": "Brooklyn multifamily, 22 units (should fail)",
        "address": "310 Sample Street, Brooklyn, NY 11216 (fictional)", "asset_type": "multifamily",
        "year_built": 1925, "floors": [(1, 6), (2, 6), (3, 5), (4, 5)],
        "types": ["studio", "1br", "1br", "2br", "1br", "studio"], "vacant": {"202", "403"}, "step": 15,
        "retail": [],
        "t12_factors": [0.880, 0.885, 0.890, 0.880, 0.885, 0.890, 0.885, 0.880, 0.890, 0.885, 0.880, 0.890],
        "other_income_annual": 8000,
        "expenses": {"Real estate taxes": 48000, "Insurance": 17000, "Utilities": 24000,
                     "Repairs and maintenance": 18000, "Payroll": 12000, "Management fee": 12000,
                     "Contract services": 5000, "Administrative and other": 14000},
        "purchase_price": 4000000, "renovation_budget": 600000, "equity": 400000,
        "loan_commitment": 4050000, "initial_advance": 3450000, "as_is_value": 4000000, "arv": 5000000,
        "note_rate": 0.115, "term_months": 12, "points": 0.02,
        "sources_stated_total": 4450000, "uses_stated_total": 4600000,
        "pro_forma": {"gpr": 420000, "vacancy_pct": 0.05, "other_income": 1000, "opex": 120000},
        "reno": [("Unit interior renovations", 260000), ("Roof and facade", 90000),
                 ("Boiler and heating", 60000), ("Electrical and plumbing", 50000),
                 ("Common areas", 40000), ("Soft costs (architect, permits)", 60000),
                 ("Contingency", 40000)],
        "sponsor": "Northgate Capital Group LLC (fictional)",
        "sponsor_bio": "Sample sponsor, first project of this size (fictional).",
        "plan": "Light renovation and re-lease, refinance in 12 months.",
        "closing_date": "2026-12-10", "deposit": 200000, "seller": "Sample Owner Corp (fictional)",
        "expected_call": "decline",
    },
]


def money(x):
    return f"${x:,.0f}"


def make_units(spec):
    units = []
    base = BASE_TYPES[spec["slug"]]
    for floor, count in spec["floors"]:
        for i in range(count):
            unit = f"{floor}{i + 1:02d}"
            utype = spec["types"][i % len(spec["types"])]
            sqft, rent = base[utype]
            rent += ((floor * 7 + i * 3) % 5 - 2) * spec["step"]
            start = date(2024, 1, 1) + timedelta(days=(floor * 31 + i * 17) % 600)
            if unit in spec["vacant"]:
                units.append([unit, utype, sqft, "vacant", "", "", "", 0])
            else:
                units.append([unit, utype, sqft, "occupied", f"Tenant {unit}",
                              start.isoformat(), (start + timedelta(days=365)).isoformat(), rent])
    for unit, sqft, rent in spec["retail"]:
        start = date(2023, 9, 1)
        units.append([unit, "retail", sqft, "occupied", f"Tenant {unit}",
                      start.isoformat(), (start + timedelta(days=365 * 5)).isoformat(), rent])
    return units


def split_even(annual):
    m = round(annual / 12)
    parts = [m] * 11
    parts.append(annual - sum(parts))
    return parts


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def build_t12(spec, rr_monthly):
    rental = [round(rr_monthly * f) for f in spec["t12_factors"]]
    lines = [("Gross rental income", "income", rental),
             ("Other income", "income", split_even(spec["other_income_annual"]))]
    for name, annual in spec["expenses"].items():
        lines.append((name, "expense", split_even(annual)))
    return lines


def reference_metrics(d, rules):
    r = rules
    uses_total = d["purchase_price"] + d["renovation_budget"]
    loan = d["loan_commitment"]
    payoff = loan * (1 + r["exit"]["exit_fee_pct"])
    noi = d["stabilized_noi"]
    tk = r["exit"]["takeout"]

    def takeout(noi_v, rate):
        caps = {"dscr": noi_v / (tk["min_dscr"] * rate),
                "ltv": tk["max_ltv"] * d["arv"],
                "debt_yield": noi_v / tk["min_debt_yield"]}
        binding = min(caps, key=caps.get)
        return caps, binding, caps[binding]

    caps, binding, tmax = takeout(noi, tk["rate"])
    st = r["exit"]["stress"]
    s_noi = noi * (1 - st["noi_haircut"])
    s_rate = tk["rate"] + st["rate_bump_bps"] / 10000
    s_caps, s_binding, s_tmax = takeout(s_noi, s_rate)

    m = {
        "total_cost": uses_total,
        "ltc": loan / uses_total,
        "ltv_as_is": d["initial_advance"] / d["as_is_value"],
        "loan_to_arv": loan / d["arv"],
        "dscr_in_place": d["in_place_noi"] / (d["initial_advance"] * d["note_rate"]),
        "debt_yield_stabilized": noi / loan,
        "implied_cap_rate": noi / d["arv"],
        "payoff": payoff,
        "takeout_caps": caps, "takeout_binding": binding, "takeout_max": tmax,
        "refi_cushion": tmax - payoff,
        "exit_dscr": noi / (payoff * tk["rate"]),
        "stress": {"noi": s_noi, "rate": s_rate, "takeout_caps": s_caps,
                   "takeout_binding": s_binding, "takeout_max": s_tmax,
                   "refi_cushion": s_tmax - payoff,
                   "exit_dscr": s_noi / (payoff * s_rate)},
        "rr_vs_t12_gap": abs(d["rent_roll_annual"] - d["t12_rental_income"]) / d["t12_rental_income"],
        "sources_vs_uses_gap": abs(d["sources_stated_total"] - d["uses_stated_total"]) / d["uses_stated_total"],
        "unit_count_match": d["unit_count"] == d["rent_roll_rows"],
    }
    return m


def evaluate(d, m, rules):
    """Return (call, reasons). Reasons are dicts with code and severity."""
    r = rules
    reasons = []

    def add(code, sev):
        reasons.append({"code": code, "severity": sev})

    if d["asset_type"] not in r["eligibility"]["asset_types"]:
        add("ASSET_TYPE_NOT_ALLOWED", "decline")
    lo, hi = r["eligibility"]["loan_size_usd"]["min"], r["eligibility"]["loan_size_usd"]["max"]
    if not (lo <= d["loan_commitment"] <= hi):
        add("LOAN_SIZE_OUT_OF_RANGE", "decline")
    for key, code in (("ltc", "LTC"), ("ltv_as_is", "LTV_AS_IS"), ("loan_to_arv", "LOAN_TO_ARV")):
        t = r["leverage"][key]
        if m[key] > t["decline_above"]:
            add(f"{code}_DECLINE", "decline")
        elif m[key] > t["watch_above"]:
            add(f"{code}_WATCH", "watch")
    t = r["exit"]["exit_dscr"]
    if m["exit_dscr"] < t["decline_below"]:
        add("EXIT_DSCR_DECLINE", "decline")
    elif m["exit_dscr"] < t["watch_below"]:
        add("EXIT_DSCR_WATCH", "watch")
    if m["refi_cushion"] < 0:
        add("REFI_CUSHION_NEGATIVE_BASE", "decline")
    elif m["stress"]["refi_cushion"] < 0:
        add("REFI_CUSHION_NEGATIVE_STRESS", "watch")
    if m["implied_cap_rate"] < r["exit"]["implied_cap_rate"]["watch_below"]:
        add("IMPLIED_CAP_RATE_LOW", "watch")
    t = r["reconciliation"]["rent_roll_vs_t12"]
    if m["rr_vs_t12_gap"] > t["decline_above"]:
        add("RENT_ROLL_VS_T12_DECLINE", "decline")
    elif m["rr_vs_t12_gap"] > t["pass_within"]:
        add("RENT_ROLL_VS_T12_WATCH", "watch")
    t = r["reconciliation"]["sources_vs_uses"]
    if m["sources_vs_uses_gap"] > t["decline_above"]:
        add("SOURCES_VS_USES_DECLINE", "decline")
    elif m["sources_vs_uses_gap"] > t["pass_within"]:
        add("SOURCES_VS_USES_WATCH", "watch")
    if r["reconciliation"]["unit_count_must_match"] and not m["unit_count_match"]:
        add("UNIT_COUNT_MISMATCH", "watch")
    if any(x["severity"] == "decline" for x in reasons):
        return "decline", reasons
    if reasons:
        return "watch", reasons
    return "screen", reasons


def summary_md(d, pf):
    a = d
    return f"""# Deal summary: {a['name']}

Deal ID: {a['deal_id']} (sample, fictional data)
Submitted by: Sample Broker LLC (fictional)

## Property
- Address: {a['address']}
- Asset type: {a['asset_type']}
- Units: {a['unit_count']}
- Year built: {a['year_built']}
- In-place occupancy: {a['occupied_units']} of {a['unit_count']} units

## Sponsor
- {a['sponsor']}
- {a['sponsor_bio']}

## Loan request
- Loan commitment requested: {money(a['loan_commitment'])}
- Initial advance at closing: {money(a['initial_advance'])}
- Renovation holdback: {money(a['loan_commitment'] - a['initial_advance'])}
- Term: {a['term_months']} months
- Note rate: {a['note_rate'] * 100:.2f}% interest-only
- Origination: {a['points'] * 100:.2f} points
- Exit: refinance into a bank or agency take-out loan

## Sources and uses
| Sources | Amount |
| --- | --- |
| Senior bridge loan | {money(a['loan_commitment'])} |
| Sponsor equity | {money(a['equity'])} |
| Total sources | {money(a['sources_stated_total'])} |

| Uses | Amount |
| --- | --- |
| Purchase price | {money(a['purchase_price'])} |
| Renovation budget | {money(a['renovation_budget'])} |
| Total uses | {money(a['uses_stated_total'])} |

## Valuation
- As-is value (broker opinion): {money(a['as_is_value'])}
- After-repair value (ARV): {money(a['arv'])}, based on stabilized NOI at a {a['stabilized_noi'] / a['arv'] * 100:.2f}% cap rate

## Business plan
{a['plan']}

## Stabilized pro forma (borrower provided)
| Line | Annual |
| --- | --- |
| Gross potential rent | {money(pf['gpr'])} |
| Vacancy and credit loss ({pf['vacancy_pct'] * 100:.0f}%) | -{money(pf['gpr'] * pf['vacancy_pct'])} |
| Other income | {money(pf['other_income'])} |
| Effective gross income | {money(pf['egi'])} |
| Operating expenses | -{money(pf['opex'])} |
| Stabilized NOI | {money(pf['noi'])} |
"""


def contract_md(a):
    return f"""# Contract of sale: key terms ({a['deal_id']}, sample, fictional)

- Property: {a['address']}
- Seller: {a['seller']}
- Buyer: {a['sponsor']}
- Purchase price: {money(a['purchase_price'])}
- Deposit: {money(a['deposit'])}
- Scheduled closing date: {a['closing_date']}
- Condition: sold as-is, subject to financing
"""


def main():
    out = {}
    for spec in DEALS:
        d = dict(spec)
        folder = ROOT / "data" / "deals" / d["slug"]
        folder.mkdir(parents=True, exist_ok=True)

        units = make_units(d)
        occupied = [u for u in units if u[3] == "occupied"]
        rr_monthly = sum(u[7] for u in occupied)
        d["unit_count"] = len(units)
        d["occupied_units"] = len(occupied)
        d["rent_roll_rows"] = len(units)
        d["rent_roll_annual"] = rr_monthly * 12
        write_csv(folder / "rent_roll.csv",
                  ["unit", "unit_type", "sqft", "status", "tenant", "lease_start", "lease_end", "monthly_rent"], units)

        lines = build_t12(d, rr_monthly)
        rows, inc, exp = [], 0, 0
        rental_total = 0
        for name, cat, vals in lines:
            tot = sum(vals)
            rows.append([name, cat] + vals + [tot])
            if cat == "income":
                inc += tot
                if name == "Gross rental income":
                    rental_total = tot
            else:
                exp += tot
        write_csv(folder / "t12.csv", ["line_item", "category"] + MONTHS + ["total"], rows)
        d["t12_rental_income"] = rental_total
        d["t12_total_income"] = inc
        d["t12_total_expenses"] = exp
        d["in_place_noi"] = inc - exp

        assert sum(a for _, a in d["reno"]) == d["renovation_budget"], d["slug"]
        write_csv(folder / "renovation_budget.csv", ["line_item", "amount"], d["reno"])

        pf = dict(d["pro_forma"])
        pf["egi"] = pf["gpr"] - pf["gpr"] * pf["vacancy_pct"] + pf["other_income"]
        pf["noi"] = pf["egi"] - pf["opex"]
        d["stabilized_noi"] = pf["noi"]
        (folder / "deal_summary.md").write_text(summary_md(d, pf))
        (folder / "purchase_contract.md").write_text(contract_md(d))

        m = reference_metrics(d, RULES)
        call, reasons = evaluate(d, m, RULES)
        assert call == d["expected_call"], (d["slug"], call, reasons)

        key_fields = {k: d[k] for k in (
            "purchase_price", "renovation_budget", "loan_commitment", "initial_advance", "equity",
            "as_is_value", "arv", "note_rate", "term_months", "unit_count", "occupied_units",
            "asset_type", "stabilized_noi", "in_place_noi", "rent_roll_annual", "t12_rental_income",
            "t12_total_income", "t12_total_expenses", "sources_stated_total", "uses_stated_total")}
        expected = {
            "deal_id": d["deal_id"], "name": d["name"], "expected_call": call,
            "expected_reason_codes": [r["code"] for r in reasons],
            "answer_key": key_fields, "metrics": m,
            "note": "Reference values computed by scripts/generate_sample_deals.py from config/rules.yaml.",
        }
        (folder / "expected.json").write_text(json.dumps(expected, indent=2))
        out[d["slug"]] = expected

    print(json.dumps({k: {"call": v["expected_call"], "reasons": v["expected_reason_codes"],
                          "key": {kk: v["answer_key"][kk] for kk in ("in_place_noi", "stabilized_noi", "rent_roll_annual", "t12_rental_income")},
                          "m": {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v["metrics"].items() if kk != "stress" and kk != "takeout_caps"},
                          "caps": {a: round(b) for a, b in v["metrics"]["takeout_caps"].items()},
                          "stress": {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v["metrics"]["stress"].items() if a != "takeout_caps"},
                          "stress_caps": {a: round(b) for a, b in v["metrics"]["stress"]["takeout_caps"].items()}}
                      for k, v in out.items()}, indent=1))


if __name__ == "__main__":
    main()
