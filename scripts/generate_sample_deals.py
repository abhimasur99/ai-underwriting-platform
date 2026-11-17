#!/usr/bin/env python3
"""Generate the sample deals (documents in several file formats) and their answer keys.

Sample, made-up data only. Deterministic: no randomness, so reruns give identical files.

The reference calculation in this file exists ONLY to produce expected.json. The product's own
calculators (backend/bridge/core/calc.py, Sprint 1) are built separately and must match
expected.json within tolerance (dollars exact to $1, ratios to 1e-4).

Usage: python3 scripts/generate_sample_deals.py   (needs PyYAML)
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RULES = yaml.safe_load((ROOT / "config" / "rules.yaml").read_text())
MONTHS = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04",
          "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deal_specs import BASE_TYPES, DEALS  # noqa: E402
from sample_docs import markdown_to_docx, markdown_to_pdf, write_xlsx  # noqa: E402

# File formats per kit (see deal_specs.py). The original three stay markdown and CSV.
KITS = {
    "A": {"deal_summary": "md", "purchase_contract": "md", "rent_roll": "csv", "t12": "csv",
          "renovation_budget": "csv"},
    "B": {"deal_summary": "pdf", "purchase_contract": "pdf", "rent_roll": "xlsx", "t12": "xlsx",
          "renovation_budget": "xlsx"},
    "C": {"deal_summary": "pdf", "purchase_contract": "docx", "rent_roll": "csv", "t12": "xlsx",
          "renovation_budget": "xlsx"},
}
SHEETS = {"rent_roll": "Rent roll", "t12": "T-12", "renovation_budget": "Renovation budget"}


def money(x):
    return f"${x:,.0f}"


def make_units(spec):
    units = []
    base = spec.get("base") or BASE_TYPES[spec["slug"]]
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


def write_table(folder, stem, fmt, header, rows):
    if fmt == "csv":
        write_csv(folder / f"{stem}.csv", header, rows)
    else:
        write_xlsx(folder / f"{stem}.xlsx", header,
                   [[None if v == "" else v for v in row] for row in rows], SHEETS[stem])


def write_doc(folder, stem, fmt, md, title):
    path = folder / f"{stem}.{fmt}"
    if fmt == "md":
        path.write_text(md)
    elif fmt == "pdf":
        markdown_to_pdf(md, path, title)
    else:
        markdown_to_docx(md, path, title)


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


def summary_md(d, pf, omit_arv=False):
    a = d
    arv_line = "" if omit_arv else (
        f"- After-repair value (ARV): {money(a['arv'])}, based on stabilized NOI at a "
        f"{a['stabilized_noi'] / a['arv'] * 100:.2f}% cap rate\n")
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
{arv_line}
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


def pct(x):
    return f"{x * 100:.2f}%"


def deal_readme(d, m, call, reasons, expected):
    units = d["unit_count"]
    codes = ", ".join(f"`{r['code']}`" for r in reasons) or "none"
    files = "\n".join(f"- `{f}`" for f in expected["files"])
    extra = ""
    if d.get("omit_arv"):
        extra = ("\nFirst run: **Needs input** (the summary omits the ARV). Upload "
                 "`followup/deal_summary.pdf` to continue; the deal then runs to **Screen**.\n")
    return f"""# Sample deal: {d['name']} ({d['deal_id']})

Expected call: **{call.capitalize()}**. {d['story']} All data is fictional.
{extra}
| Item | Value |
| --- | --- |
| Units | {units} ({d['occupied_units']} occupied) |
| Total cost | {money(m['total_cost'])} ({money(d['purchase_price'])} purchase + {money(d['renovation_budget'])} renovation) |
| Loan commitment | {money(d['loan_commitment'])} ({money(d['initial_advance'])} initial advance + {money(d['loan_commitment'] - d['initial_advance'])} holdback) |
| As-is value / ARV | {money(d['as_is_value'])} / {money(d['arv'])} |
| Stabilized NOI (borrower pro forma) | {money(d['stabilized_noi'])} |
| LTC / LTV (as-is) / loan-to-ARV | {pct(m['ltc'])} / {pct(m['ltv_as_is'])} / {pct(m['loan_to_arv'])} |
| Debt yield (stabilized) / implied cap rate | {pct(m['debt_yield_stabilized'])} / {pct(m['implied_cap_rate'])} |
| Exit DSCR | {m['exit_dscr']:.2f}x |
| Take-out max (binding: {m['takeout_binding'].replace('_', ' ')}) | {money(m['takeout_max'])}, cushion {money(m['refi_cushion'])} |
| Stress (NOI -10%, rate +100 bps) | take-out {money(m['stress']['takeout_max'])}, cushion {money(m['stress']['refi_cushion'])} |
| Rent roll vs T-12 gap | {pct(m['rr_vs_t12_gap'])} |

Expected reason codes: {codes}.

Files:
{files}
"""


def catalog(deals):
    rows = []
    for d in deals:
        m, kit = d["_m"], KITS[d.get("kit", "A")]
        formats = "/".join(dict.fromkeys(kit.values()))
        call = "Needs input, then " + d["_call"].capitalize() if d.get("omit_arv") else d["_call"].capitalize()
        rows.append(f"| {d['deal_id']} | {d['name']} | {call} | {d['unit_count']} | {money(d['loan_commitment'])} | "
                    f"{pct(m['ltc'])} | {pct(m['implied_cap_rate'])} | {formats} | {d['story']} |")
    counts = {c: sum(1 for d in deals if d["_call"] == c and not d.get("omit_arv"))
              for c in ("screen", "watch", "decline")}
    pending = sum(1 for d in deals if d.get("omit_arv"))
    return f"""# Sample deal catalog

Generated by `scripts/generate_sample_deals.py` (do not edit by hand). {len(deals)} fictional deals:
{counts['screen']} Screen, {counts['watch']} Watch, {counts['decline']} Decline and {pending} that first stops at Needs
input (and screens once its corrected file is uploaded). The call is computed by the rules from the
numbers, and a deal that lands on the wrong call has its inputs changed, never the rules (decision D32).
Thresholds are illustrative, not any real lender's box.

| Deal | Name | Call | Units | Loan | LTC | Implied cap | Formats | What it shows |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
""" + "\n".join(rows) + """

File formats: `md` and `csv` are the original kit; `pdf`, `docx` and `xlsx` are the realistic kits.
"""


def main():
    out, done = {}, []
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
        kit = KITS[d.get("kit", "A")]
        write_table(folder, "rent_roll", kit["rent_roll"],
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
        write_table(folder, "t12", kit["t12"], ["line_item", "category"] + MONTHS + ["total"], rows)
        d["t12_rental_income"] = rental_total
        d["t12_total_income"] = inc
        d["t12_total_expenses"] = exp
        d["in_place_noi"] = inc - exp

        assert sum(a for _, a in d["reno"]) == d["renovation_budget"], d["slug"]
        write_table(folder, "renovation_budget", kit["renovation_budget"], ["line_item", "amount"], d["reno"])

        pf = dict(d["pro_forma"])
        pf["egi"] = pf["gpr"] - pf["gpr"] * pf["vacancy_pct"] + pf["other_income"]
        pf["noi"] = pf["egi"] - pf["opex"]
        d["stabilized_noi"] = pf["noi"]
        omit = bool(d.get("omit_arv"))
        write_doc(folder, "deal_summary", kit["deal_summary"], summary_md(d, pf, omit), f"Deal summary {d['deal_id']}")
        write_doc(folder, "purchase_contract", kit["purchase_contract"], contract_md(d), f"Contract {d['deal_id']}")
        if omit:        # the corrected summary the sponsor sends after being asked for the ARV
            follow = folder / "followup"
            follow.mkdir(exist_ok=True)
            write_doc(follow, "deal_summary", kit["deal_summary"], summary_md(d, pf), f"Deal summary {d['deal_id']} (corrected)")

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
        if d["kit"] != "A":
            expected["files"] = sorted(p.name for p in folder.iterdir()
                                       if p.is_file() and p.name not in ("expected.json", "README.md"))
        if omit:
            expected["initial_state"] = "needs_input"
            expected["followup_file"] = "followup/deal_summary.pdf"
            expected["note"] += " The deal summary omits the ARV, so the first run stops at NEEDS_INPUT."
        (folder / "expected.json").write_text(json.dumps(expected, indent=2))
        if d["kit"] != "A":
            (folder / "README.md").write_text(deal_readme(d, m, call, reasons, expected))
        d["_m"], d["_call"], d["_reasons"] = m, call, reasons
        done.append(d)
        out[d["slug"]] = expected

    (ROOT / "docs" / "deals-catalog.md").write_text(catalog(done))
    print(json.dumps({k: {"call": v["expected_call"], "reasons": v["expected_reason_codes"],
                          "key": {kk: v["answer_key"][kk] for kk in ("in_place_noi", "stabilized_noi", "rent_roll_annual", "t12_rental_income")},
                          "m": {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v["metrics"].items() if kk != "stress" and kk != "takeout_caps"},
                          "caps": {a: round(b) for a, b in v["metrics"]["takeout_caps"].items()},
                          "stress": {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v["metrics"]["stress"].items() if a != "takeout_caps"},
                          "stress_caps": {a: round(b) for a, b in v["metrics"]["stress"]["takeout_caps"].items()}}
                      for k, v in out.items()}, indent=1))


if __name__ == "__main__":
    main()
