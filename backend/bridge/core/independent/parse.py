"""The checker's OWN parser. It reads the raw files directly with its own regexes and csv/openpyxl
code. It must not import core/parsers/ or core/calc.py (see CLAUDE.md, checker independence)."""
import csv
import re
from pathlib import Path

from openpyxl import load_workbook


def _money(text: str) -> float:
    return float(re.sub(r"[^\d.]", "", text))


def _cell(c) -> str:
    if c is None:
        return ""
    return str(int(c)) if isinstance(c, float) and c.is_integer() else str(c)


def _grid(path: Path) -> list[dict[str, str]]:
    """Rows of a CSV or XLSX as dicts keyed by lower-cased header."""
    if path.suffix == ".xlsx":
        sheet = load_workbook(path, read_only=True, data_only=True).worksheets[0]
        raw = [[_cell(c) for c in r] for r in sheet.iter_rows(values_only=True)]
    else:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            raw = list(csv.reader(fh))
    header = [h.strip().lower().replace(" ", "_") for h in raw[0]]
    return [dict(zip(header, row, strict=False)) for row in raw[1:] if any(c.strip() for c in row)]


def _find(directory: Path, stem: str) -> Path:
    for ext in ("csv", "xlsx"):
        if (directory / f"{stem}.{ext}").exists():
            return directory / f"{stem}.{ext}"
    raise FileNotFoundError(f"{stem} not found in {directory}")


def _first(pattern: str, text: str, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None


def _table_amounts(text: str, section: str) -> dict[str, list[tuple[str, float]]]:
    """Under `## section`: rows of each markdown table, keyed by that table's first header."""
    body = text.split(f"## {section}", 1)[1].split("\n## ", 1)[0]
    tables: dict[str, list[tuple[str, float]]] = {}
    current = None
    for line in body.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if "$" not in cells[-1] and not cells[-1].replace(",", "").isdigit():
            if set(cells[0]) <= set("- :"):
                continue
            current = cells[0].lower()
            tables[current] = []
        elif current:
            tables[current].append((cells[0], _money(cells[-1])))
    return tables


def independent_parse(deal_dir: str | Path) -> dict:
    d = Path(deal_dir)
    summary = (d / "deal_summary.md").read_text()
    contract = (d / "purchase_contract.md").read_text()

    def need(value, name):
        if value is None:
            raise ValueError(f"independent parse: {name} not found")
        return value

    tables = _table_amounts(summary, "Sources and uses")
    sources = [(n, a) for n, a in tables["sources"] if not n.lower().startswith("total")]
    uses = [(n, a) for n, a in tables["uses"] if not n.lower().startswith("total")]
    stated = {n.lower(): a for rows in tables.values() for n, a in rows
              if n.lower().startswith("total")}
    reno = next((a for n, a in uses if n.lower().startswith("renovation")), None)

    rent_rows = _grid(_find(d, "rent_roll"))
    rent_col = next(c for c in ("monthly_rent", "rent", "monthly") if c in rent_rows[0])
    annual_rent = 12 * sum(_money(r[rent_col] or "0") for r in rent_rows
                           if r["status"].strip().lower() == "occupied")

    t12_rows = _grid(_find(d, "t12"))
    month_cols = [c for c in t12_rows[0] if re.fullmatch(r"\d{4}-\d{2}", c)]
    totals = {"income": 0.0, "expense": 0.0}
    rental_income = 0.0
    for r in t12_rows:
        amount = sum(_money(r[c] or "0") for c in month_cols)   # sum the months, not the Total col
        totals[r["category"].strip().lower()] += amount
        if "rental income" in r["line_item"].lower():
            rental_income += amount

    occupancy = need(_first(r"In-place occupancy:\s*(\d+)\s+of", summary), "occupied units")
    return {
        "deal_id": need(_first(r"Deal ID:\s*(\S+)", summary), "deal id"),
        "asset_type": need(_first(r"Asset type:\s*(\w+)", summary), "asset type"),
        "unit_count": int(need(_first(r"^- Units:\s*(\d+)", summary, re.M), "units")),
        "occupied_units": int(occupancy),
        "purchase_price": _money(need(_first(r"Purchase price:\s*(\$[\d,]+)", contract),
                                      "purchase price")),
        "renovation_budget": need(reno, "renovation budget"),
        "loan_commitment": _money(need(_first(r"Loan commitment requested:\s*(\$[\d,]+)",
                                              summary), "loan commitment")),
        "initial_advance": _money(need(_first(r"Initial advance at closing:\s*(\$[\d,]+)",
                                              summary), "initial advance")),
        "note_rate": float(need(_first(r"Note rate:\s*([\d.]+)%", summary), "note rate")) / 100,
        "as_is_value": _money(need(_first(r"As-is value[^:]*:\s*(\$[\d,]+)", summary), "as-is")),
        "arv": _money(need(_first(r"After-repair value[^:]*:\s*(\$[\d,]+)", summary), "arv")),
        "stabilized_noi": _money(need(_first(r"\|\s*Stabilized NOI\s*\|\s*(\$[\d,]+)", summary),
                                      "stabilized noi")),
        "sources": [{"name": n, "amount": a} for n, a in sources],
        "uses": [{"name": n, "amount": a} for n, a in uses],
        "sources_stated_total": need(stated.get("total sources"), "total sources"),
        "uses_stated_total": need(stated.get("total uses"), "total uses"),
        "rent_roll_rows": len(rent_rows),
        "rent_roll_annual": annual_rent,
        "t12_rental_income": rental_income,
        "t12_total_income": totals["income"],
        "t12_total_expenses": totals["expense"],
        "in_place_noi": totals["income"] - totals["expense"],
    }
