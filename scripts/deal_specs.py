"""Specifications of the sample deals (fictional). One dict per deal; the generator turns each into
documents, an answer key and cached fixtures. The call is computed by the rules from the numbers;
a spec that lands on a different call than `expected_call` stops the generator, and the fix is to
change the spec's inputs, never the rules (decision D32)."""

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
        "kit": "A",
        "story": "The clean case and the demo's original deal: moderate leverage, a comfortable exit, documents that tie.",
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
        "kit": "A",
        "story": "Passes every leverage test and the base-case exit, but the refinance cushion turns negative under stress.",
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
        "kit": "A",
        "story": "Built to trip several rules at once so the memo has to list every reason.",
    },
]


# ---------------------------------------------------------------------------------------------
# Eight more deals (decisions D32). `mk` fills what is the same for every deal: the renovation
# budget breakdown, the expense lines, the T-12 monthly pattern, and sources equal to uses.
# `kit` says which file formats the package comes in:
#   A  markdown summary and contract, CSV tables (the original three)
#   B  PDF summary and contract, XLSX tables
#   C  PDF summary, Word contract, CSV rent roll, XLSX T-12 and budget
#   D  everything as PDF, tables included (printed reports)
# ---------------------------------------------------------------------------------------------
RENO_SHARES = [("Unit interior renovations", 0.42), ("Kitchens and baths", 0.16),
               ("Roof and facade", 0.13), ("Boiler and heating", 0.08),
               ("Electrical and plumbing", 0.08), ("Common areas", 0.05),
               ("Soft costs (architect, permits)", 0.05)]
EXPENSE_SHARES = [("Real estate taxes", 0.36), ("Insurance", 0.13), ("Utilities", 0.16),
                  ("Repairs and maintenance", 0.12), ("Payroll", 0.09), ("Management fee", 0.07),
                  ("Contract services", 0.04)]
T12_OFFSETS = [-0.006, 0.0, 0.005, 0.003, -0.003, 0.004, -0.001, 0.005, -0.004, 0.002, 0.003,
               -0.005]


def _split(total, shares, last_name, unit):
    items, used = [], 0
    for name, share in shares:
        amount = round(total * share / unit) * unit
        items.append((name, amount))
        used += amount
    items.append((last_name, total - used))
    return items


def mk(**s):
    s.setdefault("retail", [])
    s.setdefault("points", 0.02)
    s.setdefault("term_months", 18)
    s["reno"] = _split(s["renovation_budget"], RENO_SHARES, "Contingency", 1000)
    s["expenses"] = dict(_split(s.pop("opex_in_place"), EXPENSE_SHARES,
                                "Administrative and other", 100))
    avg = s.pop("t12_avg")
    s["t12_factors"] = [round(avg + o, 3) for o in T12_OFFSETS]
    s["equity"] = s["purchase_price"] + s["renovation_budget"] - s["loan_commitment"]
    s["sources_stated_total"] = s["uses_stated_total"] = s["purchase_price"] + s["renovation_budget"]
    s["pro_forma"] = {"gpr": s.pop("pf_gpr"), "vacancy_pct": 0.05,
                      "other_income": s.pop("pf_other"), "opex": s.pop("pf_opex")}
    s["base"] = s.pop("base")
    return s


NEW_DEALS = [
    mk(slug="statenisland_mf", deal_id="D-0045", name="Staten Island multifamily, 24 units",
       address="88 Sample Court, Staten Island, NY 10301 (fictional)", asset_type="multifamily",
       year_built=1951, floors=[(1, 6), (2, 6), (3, 6), (4, 6)],
       types=["studio", "1br", "1br", "2br", "1br", "2br"], vacant={"104", "305"}, step=15,
       t12_avg=0.98, other_income_annual=9000, opex_in_place=150000,
       pf_gpr=504000, pf_other=9000, pf_opex=160000,
       purchase_price=3900000, renovation_budget=550000, loan_commitment=3000000,
       initial_advance=2450000, as_is_value=3900000, arv=5650000, note_rate=0.1025,
       sponsor="Narrows Residential Partners LLC (fictional)",
       sponsor_bio="Sample sponsor with 4 prior light renovations in Staten Island (fictional).",
       plan="Light renovation of 14 units and common areas, re-lease at market, refinance into "
            "a bank take-out.",
       closing_date="2027-01-12", deposit=390000, seller="Sample Family Trust (fictional)",
       expected_call="screen", kit="B",
       base={"studio": (480, 1150), "1br": (640, 1450), "2br": (860, 1750)},
       story="Small and clean: moderate leverage, a comfortable exit, and reconciliation that ties."),
    mk(slug="harlem_mixed_use", deal_id="D-0046", name="Harlem mixed-use, 12 residential + 3 retail",
       address="512 Sample Avenue, New York, NY 10027 (fictional)", asset_type="mixed_use",
       year_built=1925, floors=[(2, 4), (3, 4), (4, 4)], types=["1br", "2br", "1br", "2br"],
       vacant={"303"}, step=25,
       retail=[("R1", 1500, 7500), ("R2", 1200, 5600), ("R3", 900, 4400)],
       t12_avg=0.98, other_income_annual=6000, opex_in_place=175000,
       pf_gpr=627600, pf_other=8000, pf_opex=185000,
       purchase_price=4600000, renovation_budget=700000, loan_commitment=3700000,
       initial_advance=3100000, as_is_value=4600000, arv=7000000, note_rate=0.105,
       sponsor="Morningside Property Group LLC (fictional)",
       sponsor_bio="Sample sponsor with 5 prior mixed-use projects in Upper Manhattan (fictional).",
       plan="Renovate residential units and refresh storefronts, re-lease, refinance into a "
            "bank take-out.",
       closing_date="2027-01-20", deposit=460000, seller="Sample Holdings Inc (fictional)",
       expected_call="screen", kit="C",
       base={"1br": (650, 2100), "2br": (880, 2650)},
       story="Mixed-use with three retail rows in the rent roll; passes every test."),
    mk(slug="bronx_mf_64", deal_id="D-0047", name="Bronx multifamily, 64 units, light renovation",
       address="2300 Sample Boulevard, Bronx, NY 10461 (fictional)", asset_type="multifamily",
       year_built=1964, floors=[(1, 16), (2, 16), (3, 16), (4, 16)],
       types=["studio", "1br", "1br", "1br", "2br", "2br", "1br", "2br"],
       vacant={"105", "212", "309", "414"}, step=20,
       t12_avg=0.98, other_income_annual=22000, opex_in_place=365000,
       pf_gpr=1382400, pf_other=30000, pf_opex=383000,
       purchase_price=11200000, renovation_budget=1000000, loan_commitment=8000000,
       initial_advance=7100000, as_is_value=11200000, arv=16700000, note_rate=0.0975, points=0.015,
       sponsor="Parkchester Capital Partners LLC (fictional)",
       sponsor_bio="Sample sponsor with 11 stabilized assets and 3 prior value-add projects "
                   "(fictional).",
       plan="Light renovation of 20 units and building systems, re-lease, refinance into an "
            "agency take-out.",
       closing_date="2027-02-03", deposit=1120000, seller="Sample Realty Fund LP (fictional)",
       expected_call="screen", kit="B",
       base={"studio": (430, 1240), "1br": (600, 1560), "2br": (820, 1880)},
       story="The largest loan in the set, with a strong exit: the take-out covers the payoff "
             "with a wide cushion."),
    mk(slug="yonkers_leaseup", deal_id="D-0048", name="Yonkers multifamily, 30 units (lease-up)",
       address="76 Sample Lane, Yonkers, NY 10701 (fictional)", asset_type="multifamily",
       year_built=1958, floors=[(1, 8), (2, 8), (3, 7), (4, 7)],
       types=["studio", "1br", "1br", "2br", "1br", "2br"],
       vacant={"103", "104", "106", "108", "203", "205", "206", "208", "304", "305", "307",
               "402", "404"}, step=15,
       t12_avg=0.98, other_income_annual=6000, opex_in_place=128000,
       pf_gpr=642000, pf_other=10000, pf_opex=150000,
       purchase_price=4600000, renovation_budget=900000, loan_commitment=4200000,
       initial_advance=3500000, as_is_value=4600000, arv=7600000, note_rate=0.11,
       sponsor="Hudson Ridge Residential LLC (fictional)",
       sponsor_bio="Sample sponsor, second lease-up project (fictional).",
       plan="Complete unit renovations, lease up the vacant units at market, refinance into a "
            "bank take-out.",
       closing_date="2027-01-28", deposit=460000, seller="Sample Bank REO Trust (fictional)",
       expected_call="watch", kit="D",
       base={"studio": (450, 1250), "1br": (600, 1500), "2br": (820, 1800)},
       story="Only 17 of 30 units are occupied. The call is Watch because leverage is high "
             "(LTC and LTV just above 75%); there is no occupancy rule, so the weak in-place "
             "DSCR is shown but does not drive the call."),
    mk(slug="astoria_richarv", deal_id="D-0049", name="Astoria multifamily, 18 units (ARV looks rich)",
       address="31-20 Sample Street, Queens, NY 11102 (fictional)", asset_type="multifamily",
       year_built=1960, floors=[(1, 5), (2, 5), (3, 4), (4, 4)],
       types=["1br", "2br", "1br", "2br", "1br"], vacant={"203"}, step=20,
       t12_avg=0.98, other_income_annual=4000, opex_in_place=128000,
       pf_gpr=586000, pf_other=8000, pf_opex=135000,
       purchase_price=5600000, renovation_budget=800000, loan_commitment=4300000,
       initial_advance=3500000, as_is_value=5600000, arv=9000000, note_rate=0.105,
       sponsor="Ditmars Holdings LLC (fictional)",
       sponsor_bio="Sample sponsor with 2 prior projects in Astoria (fictional).",
       plan="Renovate all units and common areas, re-lease at market, refinance into a bank "
            "take-out.",
       closing_date="2027-02-10", deposit=560000, seller="Sample Estate LLC (fictional)",
       expected_call="watch", kit="C",
       base={"1br": (640, 2250), "2br": (870, 2800)},
       story="Everything passes except the sanity check on the after-repair value: stabilized "
             "NOI implies a cap rate below 5%, so the ARV may be too rich."),
    mk(slug="washheights_gap", deal_id="D-0050", name="Washington Heights multifamily, 36 units",
       address="615 Sample Place, New York, NY 10033 (fictional)", asset_type="multifamily",
       year_built=1930, floors=[(1, 9), (2, 9), (3, 9), (4, 9)],
       types=["studio", "1br", "1br", "2br", "1br", "1br", "2br", "studio", "1br"],
       vacant={"104", "207", "305"}, step=20,
       t12_avg=0.935, other_income_annual=8000, opex_in_place=175000,
       pf_gpr=822000, pf_other=9000, pf_opex=190000,
       purchase_price=7400000, renovation_budget=1000000, loan_commitment=5600000,
       initial_advance=4600000, as_is_value=7400000, arv=10800000, note_rate=0.105,
       sponsor="Fort George Residential LLC (fictional)",
       sponsor_bio="Sample sponsor with 7 prior renovations in Upper Manhattan (fictional).",
       plan="Renovate 20 units and common systems, re-lease at market, refinance into a bank "
            "take-out.",
       closing_date="2027-02-17", deposit=740000, seller="Sample Seller Partners LP (fictional)",
       expected_call="watch", kit="B",
       base={"studio": (440, 1300), "1br": (610, 1700), "2br": (830, 2050)},
       story="Strong numbers, but the rent roll claims about 7% more income than the T-12 "
             "shows: a reconciliation Watch."),
    mk(slug="mountvernon_exit", deal_id="D-0051", name="Mount Vernon multifamily, 20 units",
       address="140 Sample Road, Mount Vernon, NY 10550 (fictional)", asset_type="multifamily",
       year_built=1955, floors=[(1, 5), (2, 5), (3, 5), (4, 5)],
       types=["studio", "1br", "1br", "2br", "1br"], vacant={"203", "402"}, step=15,
       t12_avg=0.98, other_income_annual=3000, opex_in_place=98000,
       pf_gpr=329500, pf_other=3000, pf_opex=105000,
       purchase_price=3800000, renovation_budget=600000, loan_commitment=3400000,
       initial_advance=2900000, as_is_value=3800000, arv=5200000, note_rate=0.1125,
       term_months=12,
       sponsor="Westchester Value Partners LLC (fictional)",
       sponsor_bio="Sample sponsor, first renovation project of this size (fictional).",
       plan="Light renovation and re-lease, refinance in 12 months.",
       closing_date="2027-01-06", deposit=190000, seller="Sample Owner LLC (fictional)",
       expected_call="decline", kit="B",
       base={"studio": (420, 1150), "1br": (580, 1400), "2br": (780, 1700)},
       story="Leverage is only in the watch band and the documents tie, but the property cannot "
             "refinance the bridge out: exit DSCR is about 1.03x and the base-case cushion is "
             "negative."),
    mk(slug="ridgewood_missing_arv", deal_id="D-0052", name="Ridgewood multifamily, 16 units",
       address="60-14 Sample Avenue, Queens, NY 11385 (fictional)", asset_type="multifamily",
       year_built=1948, floors=[(1, 4), (2, 4), (3, 4), (4, 4)],
       types=["1br", "2br", "1br", "studio"], vacant={"303"}, step=15,
       t12_avg=0.98, other_income_annual=3000, opex_in_place=90000,
       pf_gpr=400000, pf_other=4000, pf_opex=100000,
       purchase_price=3300000, renovation_budget=500000, loan_commitment=2600000,
       initial_advance=2100000, as_is_value=3300000, arv=5000000, note_rate=0.105,
       sponsor="Cypress Hills Capital LLC (fictional)",
       sponsor_bio="Sample sponsor with 3 prior projects in Queens (fictional).",
       plan="Renovate units and building systems, re-lease at market, refinance into a bank "
            "take-out.",
       closing_date="2027-02-24", deposit=330000, seller="Sample Seller Trust (fictional)",
       expected_call="screen", kit="B", omit_arv=True,
       base={"studio": (420, 1300), "1br": (600, 1650), "2br": (820, 1950)},
       story="The deal summary leaves out the after-repair value. Extraction stops and asks "
             "for it instead of guessing; `followup/deal_summary.pdf` is the corrected file, "
             "after which the deal screens."),
]
DEALS = DEALS + NEW_DEALS
