"""XLSX workbook with live formulas (openpyxl). Metric cells are formulas, never pasted numbers.

Sheets: Summary, Inputs, Rent Roll, T-12, Sources & Uses, Metrics, Exit & Stress, Flags.
`METRIC_CELLS` maps each metric to its cell so the checker can audit that they are formulas.
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from bridge.core import format as fmt
from bridge.core.rules import RulesConfig
from bridge.core.schema import Deal, UnderwritingResult

BOLD = Font(bold=True)
HEAD_FILL = PatternFill("solid", fgColor="DDE6F0")
FOOTNOTE = ("Sample data. Illustrative thresholds, not a real lender's box. "
            "A human approves every decision.")

# Fixed layout: Metrics rows and Exit & Stress rows (column B = base, column C = stress).
_METRICS_ROWS = {
    "total_cost": 2, "ltc": 3, "ltv_as_is": 4, "loan_to_arv": 5, "dscr_in_place": 6,
    "debt_yield_stabilized": 7, "implied_cap_rate": 8,
    "rent_roll_annual": 10, "t12_rental_income": 11, "rent_roll_vs_t12_gap": 12,
    "total_sources": 13, "total_uses": 14, "sources_vs_uses_gap": 15,
    "unit_count_stated": 16, "rent_roll_rows": 17, "unit_count_check": 18,
}
_EXIT_ROWS = {
    "noi": 11, "rate": 12, "payoff": 13, "dscr_cap": 14, "ltv_cap": 15, "debt_yield_cap": 16,
    "takeout_max": 17, "binding": 18, "refi_cushion": 19, "exit_dscr": 20,
}
_EXIT = "Exit & Stress"

METRIC_CELLS: dict[str, str] = {
    **{name: f"Metrics!B{row}" for name, row in _METRICS_ROWS.items()},
    **{name: f"{_EXIT}!B{_EXIT_ROWS[name]}" for name in (
        "payoff", "dscr_cap", "ltv_cap", "debt_yield_cap", "takeout_max", "binding",
        "refi_cushion", "exit_dscr")},
    **{f"stress_{name}": f"{_EXIT}!C{_EXIT_ROWS[name]}" for name in (
        "noi", "rate", "takeout_max", "binding", "refi_cushion", "exit_dscr")},
}


def _header(ws, labels: list[str]) -> None:
    ws.append(labels)
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = BOLD, HEAD_FILL


def _widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build_workbook(deal: Deal, result: UnderwritingResult, rules: RulesConfig,
                   path: str | Path) -> Path:
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    inputs = wb.create_sheet("Inputs")
    rr = wb.create_sheet("Rent Roll")
    t12 = wb.create_sheet("T-12")
    su = wb.create_sheet("Sources & Uses")
    metrics = wb.create_sheet("Metrics")
    exit_ws = wb.create_sheet(_EXIT)
    flags_ws = wb.create_sheet("Flags")

    # ---- Rent Roll
    _header(rr, ["unit", "unit_type", "sqft", "status", "tenant", "lease_start", "lease_end",
                 "monthly_rent"])
    for u in deal.rent_roll.units:
        rr.append([u.unit, u.unit_type, u.sqft, u.status, u.tenant, u.lease_start, u.lease_end,
                   u.monthly_rent])
    rr_last = rr.max_row
    rr_annual_row = rr_last + 2
    rr["A" + str(rr_annual_row)] = "Annual occupied rent"
    rr["B" + str(rr_annual_row)] = f'=12*SUMIF(D2:D{rr_last},"occupied",H2:H{rr_last})'
    rr["A" + str(rr_annual_row + 1)] = "Unit rows"
    rr["B" + str(rr_annual_row + 1)] = f"=COUNTA(A2:A{rr_last})"
    _widths(rr, [10, 12, 8, 10, 14, 12, 12, 14])

    # ---- T-12 (months in C.., stated total after them)
    n_months = max(len(ln.months) for ln in deal.t12.lines)
    total_col = get_column_letter(3 + n_months)
    _header(t12, ["line_item", "category", *[f"m{i + 1}" for i in range(n_months)], "total"])
    for ln in deal.t12.lines:
        t12.append([ln.line_item, ln.category, *ln.months, ln.total])
    t_last = t12.max_row
    rows = {"total_income": t_last + 2, "total_expenses": t_last + 3,
            "in_place_noi": t_last + 4, "rental_income": t_last + 5}
    rng_cat, rng_tot = f"$B$2:$B${t_last}", f"{total_col}2:{total_col}{t_last}"
    t12[f"A{rows['total_income']}"] = "Total income"
    t12[f"{total_col}{rows['total_income']}"] = f'=SUMIF({rng_cat},"income",{rng_tot})'
    t12[f"A{rows['total_expenses']}"] = "Total expenses"
    t12[f"{total_col}{rows['total_expenses']}"] = f'=SUMIF({rng_cat},"expense",{rng_tot})'
    t12[f"A{rows['in_place_noi']}"] = "In-place NOI"
    t12[f"{total_col}{rows['in_place_noi']}"] = (
        f"={total_col}{rows['total_income']}-{total_col}{rows['total_expenses']}")
    t12[f"A{rows['rental_income']}"] = "Gross rental income"
    t12[f"{total_col}{rows['rental_income']}"] = (
        f'=SUMIF($A$2:$A${t_last},"Gross rental income",{rng_tot})')
    _widths(t12, [30, 10, *([9] * n_months), 12])

    # ---- Sources & Uses
    _header(su, ["Sources", "Amount"])
    for row in deal.sources_uses.sources:
        su.append([row.name, row.amount])
    s_first, s_last = 2, su.max_row
    su.append(["Total sources (sum of rows)", f"=SUM(B{s_first}:B{s_last})"])
    s_total = su.max_row
    su.append(["Stated total sources", deal.sources_uses.stated_total_sources.value])
    su.append([])
    _header(su, ["Uses", "Amount"])
    u_first = su.max_row + 1
    for row in deal.sources_uses.uses:
        su.append([row.name, row.amount])
    u_last = su.max_row
    su.append(["Total uses (sum of rows)", f"=SUM(B{u_first}:B{u_last})"])
    u_total = su.max_row
    su.append(["Stated total uses", deal.sources_uses.stated_total_uses.value])
    _widths(su, [34, 16])

    # ---- Inputs: every field with value and source; derived fields are formulas
    _header(inputs, ["field", "value", "source", "confidence"])
    cell: dict[str, str] = {}

    def add_input(name: str, sourced=None, formula: str | None = None, source: str = ""):
        row = inputs.max_row + 1
        if sourced is not None:
            s = sourced.source
            source = f"{s.doc} {s.locator}" if s.kind == "document" else (s.formula or "")
            inputs.append([name, sourced.value, source, sourced.confidence])
        else:
            inputs.append([name, formula, source, 1.0])
        cell[name] = f"Inputs!$B${row}"

    add_input("purchase_price", deal.purchase.purchase_price)
    add_input("renovation_budget", deal.renovation.renovation_budget)
    add_input("loan_commitment", deal.loan_request.loan_commitment)
    add_input("initial_advance", deal.loan_request.initial_advance)
    add_input("as_is_value", deal.valuation.as_is_value)
    add_input("arv", deal.valuation.arv)
    add_input("note_rate", deal.loan_request.note_rate)
    add_input("stabilized_noi", deal.pro_forma.stabilized_noi)
    add_input("unit_count", deal.property.unit_count)
    add_input("occupied_units", deal.property.occupied_units)
    add_input("in_place_noi", formula=f"='T-12'!{total_col}{rows['in_place_noi']}",
              source="T-12 total income - total expenses")
    add_input("t12_rental_income", formula=f"='T-12'!{total_col}{rows['rental_income']}",
              source="T-12 Gross rental income line")
    add_input("rent_roll_annual", formula=f"='Rent Roll'!B{rr_annual_row}",
              source="12 x occupied monthly rent")
    for name, sourced in (("term_months", deal.loan_request.term_months),
                          ("points", deal.loan_request.points),
                          ("deposit", deal.purchase.deposit),
                          ("year_built", deal.property.year_built)):
        if sourced is not None:
            add_input(name, sourced)
    for row in inputs.iter_rows(min_row=2, min_col=2, max_col=2):
        row[0].number_format = "#,##0.00" if isinstance(row[0].value, float) else "General"
    _widths(inputs, [22, 16, 52, 11])

    def ref(name: str) -> str:
        return cell[name]

    # ---- Metrics (all formulas)
    _header(metrics, ["metric", "value", "formula"])
    r = _METRICS_ROWS
    su_ref = "'Sources & Uses'"
    formulas = {
        "total_cost": (f"={su_ref}!B{u_total}", "sum of uses"),
        "ltc": (f"={ref('loan_commitment')}/B{r['total_cost']}", "loan_commitment / total_cost"),
        "ltv_as_is": (f"={ref('initial_advance')}/{ref('as_is_value')}",
                      "initial_advance / as_is_value"),
        "loan_to_arv": (f"={ref('loan_commitment')}/{ref('arv')}", "loan_commitment / arv"),
        "dscr_in_place": (f"={ref('in_place_noi')}/({ref('initial_advance')}*{ref('note_rate')})",
                          "in_place_noi / (initial_advance * note_rate)"),
        "debt_yield_stabilized": (f"={ref('stabilized_noi')}/{ref('loan_commitment')}",
                                  "stabilized_noi / loan_commitment"),
        "implied_cap_rate": (f"={ref('stabilized_noi')}/{ref('arv')}", "stabilized_noi / arv"),
        "rent_roll_annual": (f"={ref('rent_roll_annual')}", "12 x occupied monthly rent"),
        "t12_rental_income": (f"={ref('t12_rental_income')}", "T-12 gross rental income"),
        "rent_roll_vs_t12_gap": (f"=ABS(B{r['rent_roll_annual']}-B{r['t12_rental_income']})"
                                 f"/B{r['t12_rental_income']}", "abs(a - b) / b"),
        "total_sources": (f"={su_ref}!B{s_total}", "sum of source rows"),
        "total_uses": (f"={su_ref}!B{u_total}", "sum of use rows"),
        "sources_vs_uses_gap": (f"=ABS(B{r['total_sources']}-B{r['total_uses']})"
                                f"/B{r['total_uses']}", "abs(sources - uses) / uses"),
        "unit_count_stated": (f"={ref('unit_count')}", "stated unit count"),
        "rent_roll_rows": (f"='Rent Roll'!B{rr_annual_row + 1}", "rent roll rows"),
        "unit_count_check": (f'=IF(B{r["unit_count_stated"]}=B{r["rent_roll_rows"]},'
                             '"pass","watch")', "stated units = rent roll rows"),
    }
    for name, row in r.items():
        formula, text = formulas[name]
        metrics[f"A{row}"], metrics[f"B{row}"], metrics[f"C{row}"] = name, formula, text
        if name in ("ltc", "ltv_as_is", "loan_to_arv", "debt_yield_stabilized",
                    "implied_cap_rate", "rent_roll_vs_t12_gap", "sources_vs_uses_gap"):
            metrics[f"B{row}"].number_format = "0.00%"
        elif name == "dscr_in_place":
            metrics[f"B{row}"].number_format = '0.00"x"'
        elif name != "unit_count_check":
            metrics[f"B{row}"].number_format = "#,##0"
    for c in metrics[1]:
        c.font, c.fill = BOLD, HEAD_FILL
    _widths(metrics, [26, 16, 46])

    # ---- Exit & Stress
    tk, st = rules.exit.takeout, rules.exit.stress
    exit_ws["A1"], exit_ws["B1"] = "Assumptions (illustrative, from config/rules.yaml)", "value"
    for i, (label, value) in enumerate([
            ("take-out rate", tk.rate), ("min DSCR", tk.min_dscr), ("max LTV (on ARV)", tk.max_ltv),
            ("min debt yield", tk.min_debt_yield), ("exit fee %", rules.exit.exit_fee_pct),
            ("stress NOI haircut", st.noi_haircut), ("stress rate bump (bps)", st.rate_bump_bps)],
            start=2):
        exit_ws[f"A{i}"], exit_ws[f"B{i}"] = label, value
    for c in exit_ws[1]:
        c.font, c.fill = BOLD, HEAD_FILL
    exit_ws["A10"], exit_ws["B10"], exit_ws["C10"] = "Take-out sizing", "Base", "Stress"
    for c in exit_ws[10]:
        c.font, c.fill = BOLD, HEAD_FILL
    e = _EXIT_ROWS
    labels = {"noi": "stabilized NOI", "rate": "take-out rate", "payoff": "payoff",
              "dscr_cap": "DSCR cap", "ltv_cap": "LTV cap", "debt_yield_cap": "debt yield cap",
              "takeout_max": "take-out max", "binding": "binding cap",
              "refi_cushion": "refi cushion", "exit_dscr": "exit DSCR"}
    for name, row in e.items():
        exit_ws[f"A{row}"] = labels[name]
    for col in "BC":
        stress = col == "C"
        exit_ws[f"{col}{e['noi']}"] = (f"=B{e['noi']}*(1-$B$7)" if stress
                                      else f"={ref('stabilized_noi')}")
        exit_ws[f"{col}{e['rate']}"] = "=$B$2+$B$8/10000" if stress else "=$B$2"
        exit_ws[f"{col}{e['payoff']}"] = (f"=B{e['payoff']}" if stress
                                         else f"={ref('loan_commitment')}*(1+$B$6)")
        exit_ws[f"{col}{e['dscr_cap']}"] = f"={col}{e['noi']}/($B$3*{col}{e['rate']})"
        exit_ws[f"{col}{e['ltv_cap']}"] = f"=$B$4*{ref('arv')}"
        exit_ws[f"{col}{e['debt_yield_cap']}"] = f"={col}{e['noi']}/$B$5"
        exit_ws[f"{col}{e['takeout_max']}"] = (
            f"=MIN({col}{e['dscr_cap']},{col}{e['ltv_cap']},{col}{e['debt_yield_cap']})")
        exit_ws[f"{col}{e['binding']}"] = (
            f'=IF({col}{e["dscr_cap"]}={col}{e["takeout_max"]},"dscr",'
            f'IF({col}{e["ltv_cap"]}={col}{e["takeout_max"]},"ltv","debt_yield"))')
        exit_ws[f"{col}{e['refi_cushion']}"] = f"={col}{e['takeout_max']}-{col}{e['payoff']}"
        exit_ws[f"{col}{e['exit_dscr']}"] = (
            f"={col}{e['noi']}/({col}{e['payoff']}*{col}{e['rate']})")
        for name in ("noi", "payoff", "dscr_cap", "ltv_cap", "debt_yield_cap", "takeout_max",
                     "refi_cushion"):
            exit_ws[f"{col}{e[name]}"].number_format = "#,##0"
        exit_ws[f"{col}{e['rate']}"].number_format = "0.00%"
        exit_ws[f"{col}{e['exit_dscr']}"].number_format = '0.00"x"'
    _widths(exit_ws, [46, 16, 16])

    # ---- Flags
    _header(flags_ws, ["code", "field", "message"])
    for flag in result.flags:
        flags_ws.append([flag.code, flag.field, flag.message])
    flags_ws.append([])
    _header(flags_ws, ["open questions"])
    for question in result.open_questions:
        flags_ws.append([question])
    _widths(flags_ws, [34, 26, 90])

    # ---- Summary (call and reasons are results of the rules; key metrics link to Metrics)
    summary["A1"] = f"{deal.deal_id}: {deal.name}"
    summary["A1"].font = Font(bold=True, size=14)
    summary["A2"], summary["B2"] = "Call (recommendation)", result.call.upper()
    summary["A2"].font = summary["B2"].font = BOLD
    summary["A3"], summary["B3"] = "Rules version", result.rules_version
    _header(summary, [])
    summary.append([])
    _header(summary, ["reason code", "severity", "detail"])
    for reason in result.reasons:
        summary.append([reason.code, reason.severity, fmt.describe_reason(reason)])
    if not result.reasons:
        summary.append(["(none)", "", "No rule was triggered."])
    summary.append([])
    _header(summary, ["key metric", "value"])
    for label, name, number_format in (
            ("Loan to cost", "ltc", "0.00%"), ("Loan to value (as-is)", "ltv_as_is", "0.00%"),
            ("Loan to ARV", "loan_to_arv", "0.00%"), ("Take-out max", "takeout_max", "#,##0"),
            ("Refi cushion", "refi_cushion", "#,##0"), ("Exit DSCR", "exit_dscr", '0.00"x"')):
        summary.append([label, f"={METRIC_CELLS[name]}"])
        summary.cell(row=summary.max_row, column=2).number_format = number_format
    summary.append([])
    summary.append([rules.disclaimer])
    summary.append([FOOTNOTE])
    _widths(summary, [34, 16, 80])
    summary["B2"].alignment = Alignment(horizontal="left")

    wb.calculation.fullCalcOnLoad = True   # Excel/Numbers recompute every formula on open
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
