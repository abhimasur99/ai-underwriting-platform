"""Assemble a `Deal` from a directory of sample documents. No model involved.

Required fields that cannot be found are collected and raised together as
`MissingRequiredFieldError`; nothing is defaulted.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from bridge.core.parsers.assist import (
    ASSISTED_CONFIDENCE,
    SPEC_BY_KEY,
    TABLE_KEYS,
    Assist,
    Augmentation,
    checked_mapping,
    verify,
)
from bridge.core.parsers.documents import find_text_document, read_document_text
from bridge.core.parsers.errors import MissingRequiredFieldError, ParseError
from bridge.core.parsers.markdown import (
    Bullet,
    TableRow,
    clean_label,
    parse_markdown,
    strip_parenthetical,
)
from bridge.core.parsers.sourcing import derived, sourced_from_quote
from bridge.core.parsers.tables import (
    find_document,
    parse_number,
    read_raw,
    read_rows,
)
from bridge.core.schema import (
    T12,
    AmountRow,
    Deal,
    Flag,
    LineItem,
    LoanRequest,
    ProForma,
    Property,
    Purchase,
    Renovation,
    RentRoll,
    RentRollUnit,
    SourcesUses,
    Sponsor,
    T12Line,
    Valuation,
)

RENT_ROLL_SYNONYMS = {
    "rent": "monthly_rent", "monthly": "monthly_rent", "apt": "unit", "unit_no": "unit",
    "unit_number": "unit", "type": "unit_type", "sf": "sqft", "square_feet": "sqft",
}
T12_SYNONYMS = {"line": "line_item", "item": "line_item", "annual": "total", "type": "category"}
BUDGET_SYNONYMS = {"item": "line_item", "cost": "amount", "budget": "amount"}
MONTH = re.compile(
    r"^(?:\d{4}_\d{1,2}|\d{1,2}_\d{4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*_?(?:\d{2}|\d{4}))$")
REQUIRED_COLUMNS = {"rent_roll": ["unit", "unit_type", "status", "monthly_rent"],
                    "t12": ["line_item", "category", "total"],
                    "renovation_budget": ["line_item", "amount"]}
SYNONYMS = {"rent_roll": RENT_ROLL_SYNONYMS, "t12": T12_SYNONYMS,
            "renovation_budget": BUDGET_SYNONYMS}
TOLERANCE_USD = 1.0


class _Collector:
    """Collects required values; remembers which ones were not found."""

    def __init__(self) -> None:
        self.missing: list[str] = []

    def need[V](self, name: str, value: V | None) -> V | None:
        if value is None:
            self.missing.append(name)
        return value

    def raise_if_missing(self) -> None:
        if self.missing:
            raise MissingRequiredFieldError(self.missing)


def _src(doc: str, text: str, bullet: Bullet | TableRow, value, *, conf: float | None = None):
    if conf is None and getattr(bullet, "assisted", False):
        conf = ASSISTED_CONFIDENCE
    kwargs = {} if conf is None else {"confidence": conf}
    return sourced_from_quote(value, doc, text, f"line {bullet.line}", bullet.text, **kwargs)


def _bullet_value(b: Bullet | None, kind: str):
    """Parse a bullet's value as money/number ('money'), whole number ('int'), or text."""
    if b is None:
        return None
    try:
        if kind == "money":
            return parse_number(_first_amount(b.value))
        if kind == "int":
            return int(parse_number(re.search(r"[\d,]+", b.value).group()))
        if kind == "percent":
            return parse_number(re.search(r"[\d.]+%", b.value).group()) / 100
        return strip_parenthetical(b.value) if kind == "text" else b.value
    except (AttributeError, ValueError) as exc:
        raise ParseError(f"cannot read {b.label!r} from line {b.line}: {b.value!r}") from exc


def _canonical_asset_type(text: str | None) -> str | None:
    """'Multi-family' and 'mixed use' are the platform's `multifamily` and `mixed_use`; anything
    else is left as written so the eligibility rule can refuse it."""
    if text is None:
        return None
    key = re.sub(r"[^a-z]", "", text.lower())
    if key.startswith("multifamily"):
        return "multifamily"
    if key.startswith("mixeduse"):
        return "mixed_use"
    return text


def _first_amount(text: str) -> str:
    m = re.search(r"-?\$[\d,]+(?:\.\d+)?|-?[\d,]+(?:\.\d+)?", text)
    if not m:
        raise ParseError(f"no amount in {text!r}")
    return m.group()


def _amount(row: TableRow, column: int = 1) -> float:
    return parse_number(_first_amount(row.cells[column]))


def _table_row(table, label: str) -> TableRow | None:
    if table is None:
        return None
    for row in table.rows:
        if clean_label(row.cells[0]) == label:
            return row
    return None


@dataclass
class _Context:
    """What one parse needs beyond the files: an optional model assist (asked only when the
    deterministic read fails), notes on what it did, and prose fields already verified."""
    assist: Assist | None = None
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Augmentation] = field(default_factory=dict)


class _Memo:
    """Ask the assist once per question, even though a parse may run twice."""

    def __init__(self, assist: Assist):
        self.assist, self.cache = assist, {}

    def map_columns(self, kind, headers, sample):
        key = (kind, tuple(headers))
        if key not in self.cache:
            self.cache[key] = self.assist.map_columns(kind, headers, sample)
        return self.cache[key]

    def read_document(self, name, text, wanted, want_tables):
        key = (name, tuple(s.key for s in wanted), want_tables)
        if key not in self.cache:
            self.cache[key] = self.assist.read_document(name, text, wanted, want_tables)
        return self.cache[key]


def _missing_columns(stem: str, rows) -> list[str]:
    return [c for c in REQUIRED_COLUMNS[stem] if rows and c not in rows[0].cells]


def _table(directory: Path, stem: str, ctx: _Context):
    """The table's rows. If required columns are not found by name, a model (when allowed) may
    say which heading is which; the numbers are still read from the table by code."""
    path = find_document(directory, stem)
    rows = read_rows(path, SYNONYMS[stem])
    if not rows:
        raise ParseError(f"{path.name} has no data rows")
    missing = _missing_columns(stem, rows)
    if missing and ctx.assist is not None:
        raw = read_raw(path)
        mapping = checked_mapping(stem, raw[0], ctx.assist.map_columns(stem, raw[0], raw[1:4]))
        if mapping:
            rows = read_rows(path, {**SYNONYMS[stem], **mapping})
            missing = _missing_columns(stem, rows)
            if not missing:
                ctx.notes.append(f"{path.name}: columns matched by the model ("
                                 + ", ".join(f"{h} as {c}" for h, c in mapping.items()) + ")")
    if missing:
        raise MissingRequiredFieldError([f"{stem}.{c}" for c in missing])
    return path, rows


def _read_rent_roll(directory: Path, flags: list[Flag], ctx: _Context
                    ) -> tuple[list[RentRollUnit], str, int, int]:
    path, rows = _table(directory, "rent_roll", ctx)
    units = []
    for r in rows:
        status = r.cells["status"].lower()
        if status not in ("occupied", "vacant"):
            raise ParseError(f"{path.name} row {r.number}: unknown status {status!r}")
        units.append(RentRollUnit(
            unit=r.cells["unit"], unit_type=r.cells["unit_type"].lower(), status=status,
            monthly_rent=parse_number(r.cells["monthly_rent"] or "0"),
            sqft=parse_number(r.cells["sqft"]) if r.cells.get("sqft") else None,
            tenant=r.cells.get("tenant") or None,
            lease_start=r.cells.get("lease_start") or None,
            lease_end=r.cells.get("lease_end") or None,
        ))
    return units, path.name, rows[0].number, rows[-1].number


def _read_t12(directory: Path, flags: list[Flag], ctx: _Context
              ) -> tuple[list[T12Line], str, int, int]:
    path, rows = _table(directory, "t12", ctx)
    lines = []
    for r in rows:
        category = r.cells.get("category", "").lower()
        if category not in ("income", "expense"):
            raise ParseError(f"{path.name} row {r.number}: category must be income or expense")
        months = [parse_number(v or "0") for k, v in r.cells.items() if MONTH.match(k)]
        total = parse_number(r.cells["total"])
        if abs(sum(months) - total) > TOLERANCE_USD:
            flags.append(Flag(
                code="T12_ROW_TOTAL_MISMATCH", field=f"t12.{r.cells['line_item']}",
                message=f"{path.name} row {r.number}: months sum to {sum(months):,.0f} "
                        f"but total says {total:,.0f}"))
        lines.append(T12Line(line_item=r.cells["line_item"], category=category,
                             months=months, total=total))
    return lines, path.name, rows[0].number, rows[-1].number


def _read_budget(directory: Path, ctx: _Context) -> list[LineItem]:
    _, rows = _table(directory, "renovation_budget", ctx)
    return [LineItem(item=r.cells["line_item"], amount=parse_number(r.cells["amount"]))
            for r in rows]


def _assisted_prose(d: Path, assist: Assist, missing: list[str]) -> dict[str, Augmentation]:
    """Ask the model for the prose fields the parser did not find; keep only what verifies."""
    wanted_keys = [k for k in missing if k in SPEC_BY_KEY]
    want_tables = any(k in TABLE_KEYS for k in missing)
    out: dict[str, Augmentation] = {}
    for doc, stem in (("summary", "deal_summary"), ("contract", "purchase_contract")):
        wanted = [SPEC_BY_KEY[k] for k in wanted_keys if SPEC_BY_KEY[k].doc == doc]
        tables = want_tables and doc == "summary"
        if not wanted and not tables:
            continue
        path = find_text_document(d, stem)
        text = read_document_text(path)
        reading = assist.read_document(path.name, text, wanted, tables)
        out[doc] = verify(reading, text, wanted, tables)
    return out


def parse_deal_dir(directory: str | Path, assist: Assist | None = None) -> Deal:
    """Read a deal folder into a sourced Deal. The deterministic parser always runs first. With an
    `assist` (live mode), a field or column it cannot find may be read by the model instead, and
    only if the document itself supports the answer (core/parsers/assist.py). Without one, a
    missing field raises MissingRequiredFieldError and the deal stops and asks."""
    d = Path(directory)
    ctx = _Context(assist=_Memo(assist) if assist is not None else None)
    try:
        return _parse(d, ctx)
    except MissingRequiredFieldError as exc:
        if ctx.assist is None:
            raise
        try:
            ctx.extra = _assisted_prose(d, ctx.assist, exc.missing)
        except FileNotFoundError:
            raise exc from None
        refused = {k: why for aug in ctx.extra.values() for k, why in aug.rejected.items()}
        if not any(aug.accepted for aug in ctx.extra.values()):
            raise MissingRequiredFieldError(exc.missing, refused) from None
        try:
            return _parse(d, ctx)
        except MissingRequiredFieldError as again:
            raise MissingRequiredFieldError(again.missing, refused) from None


def _parse(d: Path, ctx: _Context) -> Deal:
    summary_path = find_text_document(d, "deal_summary")
    contract_path = find_text_document(d, "purchase_contract")
    summary_text = read_document_text(summary_path)
    contract_text = read_document_text(contract_path)
    summary, contract = parse_markdown(summary_text), parse_markdown(contract_text)
    for doc, parsed in (("summary", summary), ("contract", contract)):
        if doc in ctx.extra:                                  # fields the model read, verified
            parsed.bullets.extend(ctx.extra[doc].bullets)
            parsed.tables.extend(ctx.extra[doc].tables)
    flags: list[Flag] = []
    c = _Collector()

    # --- tabular documents (these raise on their own if a file or column is missing)
    units, rr_name, rr_first, rr_last = _read_rent_roll(d, flags, ctx)
    t12_lines, t12_name, t12_first, t12_last = _read_t12(d, flags, ctx)
    budget_items = _read_budget(d, ctx)

    S, K = summary_path.name, contract_path.name

    def sb(label, section=None):   # summary bullet
        return summary.bullet(label, section)

    def money(b):
        return _bullet_value(b, "money")

    # --- identity
    deal_id_line = summary.plain.get("deal id")
    if deal_id_line is None and ctx.extra:        # the platform assigns its own id (decision D22)
        deal_id_line = (d.name, 0, "")
    deal_id = c.need("deal_id", deal_id_line[0].split()[0] if deal_id_line else None)

    # --- property
    b_addr, b_type = sb("address"), sb("asset type")
    b_units, b_occ = sb("units"), sb("in-place occupancy")
    address = _bullet_value(b_addr, "text")
    asset_type = _canonical_asset_type(_bullet_value(b_type, "text"))
    unit_count = _bullet_value(b_units, "int")
    occupied = None
    if b_occ is not None:
        m = re.search(r"(\d+)\s+of\s+(\d+)", b_occ.value)
        occupied = int(m.group(1)) if m else None
    title = summary.title
    if not title and ctx.extra and address:       # a name for the queue when the document has none
        title = f"Deal summary: {address.split(',')[0]}"
    name = c.need("name", strip_parenthetical(title.split(":", 1)[-1].strip()) if title else None)
    c.need("address", address), c.need("asset_type", asset_type)
    c.need("unit_count", unit_count), c.need("occupied_units", occupied)
    b_year = sb("year built")
    year_built = _bullet_value(b_year, "int")

    # --- sponsor
    b_sponsor = summary.first_bullet("Sponsor")
    sponsor = strip_parenthetical(b_sponsor.value) if b_sponsor else None
    c.need("sponsor_name", sponsor)

    # --- loan request
    b_commit, b_adv = sb("loan commitment requested"), sb("initial advance at closing")
    b_rate, b_term, b_pts = sb("note rate"), sb("term"), sb("origination")
    commitment, advance = money(b_commit), money(b_adv)
    rate = _bullet_value(b_rate, "percent")
    c.need("loan_commitment", commitment), c.need("initial_advance", advance)
    c.need("note_rate", rate)
    term = _bullet_value(b_term, "int")
    points = None
    if b_pts is not None:
        m = re.search(r"[\d.]+(?=\s*points?)", b_pts.value)
        points = float(m.group()) if m else None

    # --- valuation
    b_asis, b_arv = sb("as-is value"), sb("after-repair value")
    as_is, arv = money(b_asis), money(b_arv)
    c.need("as_is_value", as_is), c.need("arv", arv)

    # --- purchase contract
    k_price, k_dep = contract.bullet("purchase price"), contract.bullet("deposit")
    k_close = contract.bullet("scheduled closing date")
    price = money(k_price)
    c.need("purchase_price", price)

    # --- sources and uses
    sec = "Sources and uses"
    src_t, use_t = summary.table(sec, "Sources"), summary.table(sec, "Uses")
    c.need("sources_table", src_t), c.need("uses_table", use_t)
    sources = uses = []
    stated_src = stated_use = reno_row = None
    if src_t and use_t:
        sources = [AmountRow(name=r.cells[0], amount=_amount(r)) for r in src_t.rows
                   if not r.cells[0].lower().startswith("total")]
        uses = [AmountRow(name=r.cells[0], amount=_amount(r)) for r in use_t.rows
                if not r.cells[0].lower().startswith("total")]
        stated_src = _table_row(src_t, "total sources")
        stated_use = _table_row(use_t, "total uses")
        reno_row = _table_row(use_t, "renovation budget")
    c.need("stated_total_sources", stated_src), c.need("stated_total_uses", stated_use)
    c.need("renovation_budget", reno_row)

    # --- pro forma
    pf_t = summary.table("Stabilized pro forma (borrower provided)")
    noi_row = _table_row(pf_t, "stabilized noi")
    c.need("stabilized_noi", noi_row)

    # --- rent roll / T-12 derived values
    rr_annual = 12 * sum(u.monthly_rent for u in units if u.status == "occupied")
    income = [ln for ln in t12_lines if ln.category == "income"]
    expense = [ln for ln in t12_lines if ln.category == "expense"]
    rental = next((ln for ln in income if "rental income" in ln.line_item.lower()), None)
    c.need("t12_rental_income", rental)

    c.raise_if_missing()

    read_by_model = sorted({k for aug in ctx.extra.values() for k in aug.accepted})
    if read_by_model or ctx.notes:
        detail = ([f"fields read by the model, each checked against a quote in the document: "
                   f"{', '.join(read_by_model)}"] if read_by_model else []) + ctx.notes
        flags.append(Flag(code="MODEL_ASSISTED_EXTRACTION", field=", ".join(read_by_model) or None,
                          message="; ".join(detail) + ". Please check them against the documents."))

    # --- consistency flags (do not change the call; shown to the reviewer)
    reno_value = _amount(reno_row)
    budget_sum = sum(i.amount for i in budget_items)
    if abs(budget_sum - reno_value) > TOLERANCE_USD:
        flags.append(Flag(
            code="RENOVATION_BUDGET_MISMATCH", field="renovation_budget",
            message=f"Budget lines sum to {budget_sum:,.0f} but the summary states "
                    f"{reno_value:,.0f}"))
    actual_occ = sum(1 for u in units if u.status == "occupied")
    if actual_occ != occupied:
        flags.append(Flag(
            code="OCCUPANCY_MISMATCH", field="occupied_units",
            message=f"Summary says {occupied} occupied units; rent roll shows {actual_occ}"))

    total_income = sum(ln.total for ln in income)
    total_expenses = sum(ln.total for ln in expense)
    t12_loc = f"rows {t12_first}-{t12_last}"

    def pf_get(label):
        return _table_row(pf_t, label)

    pro_forma = ProForma(stabilized_noi=_src(S, summary_text, noi_row, _amount(noi_row)))
    gpr, vac = pf_get("gross potential rent"), pf_get("vacancy and credit loss")
    other, opex = pf_get("other income"), pf_get("operating expenses")
    if gpr:
        pro_forma.gpr = _src(S, summary_text, gpr, _amount(gpr))
    if vac:
        m = re.search(r"\(([\d.]+)%\)", vac.cells[0])
        if m:
            pro_forma.vacancy_pct = _src(S, summary_text, vac, float(m.group(1)) / 100)
    if other:
        pro_forma.other_income = _src(S, summary_text, other, _amount(other))
    if opex:
        pro_forma.opex = _src(S, summary_text, opex, abs(_amount(opex)))

    def opt(bullet, kind, doc, text):
        value = _bullet_value(bullet, kind)
        return None if value is None else _src(doc, text, bullet, value)

    return Deal(
        deal_id=deal_id, name=name,
        property=Property(
            address=_src(S, summary_text, b_addr, address),
            asset_type=_src(S, summary_text, b_type, asset_type),
            unit_count=_src(S, summary_text, b_units, unit_count),
            occupied_units=_src(S, summary_text, b_occ, occupied),
            year_built=opt(b_year, "int", S, summary_text) if year_built else None),
        loan_request=LoanRequest(
            loan_commitment=_src(S, summary_text, b_commit, commitment),
            initial_advance=_src(S, summary_text, b_adv, advance),
            note_rate=_src(S, summary_text, b_rate, rate),
            term_months=_src(S, summary_text, b_term, term) if term else None,
            points=_src(S, summary_text, b_pts, points) if points is not None else None),
        valuation=Valuation(as_is_value=_src(S, summary_text, b_asis, as_is),
                            arv=_src(S, summary_text, b_arv, arv)),
        purchase=Purchase(
            purchase_price=_src(K, contract_text, k_price, price),
            deposit=opt(k_dep, "money", K, contract_text),
            closing_date=_src(K, contract_text, k_close, k_close.value) if k_close else None),
        renovation=Renovation(
            renovation_budget=_src(S, summary_text, reno_row, reno_value),
            line_items=budget_items),
        sources_uses=SourcesUses(
            sources=sources, uses=uses,
            stated_total_sources=_src(S, summary_text, stated_src, _amount(stated_src)),
            stated_total_uses=_src(S, summary_text, stated_use, _amount(stated_use))),
        pro_forma=pro_forma,
        rent_roll=RentRoll(
            units=units,
            annual_occupied_rent=derived(
                float(rr_annual), "12 * sum(monthly_rent where status == occupied)",
                rr_name, f"rows {rr_first}-{rr_last}")),
        t12=T12(
            lines=t12_lines,
            rental_income=derived(rental.total, "total of the Gross rental income line",
                                  t12_name, t12_loc),
            total_income=derived(total_income, "sum of income line totals", t12_name, t12_loc),
            total_expenses=derived(total_expenses, "sum of expense line totals",
                                   t12_name, t12_loc),
            in_place_noi=derived(total_income - total_expenses,
                                 "total income - total expenses", t12_name, t12_loc)),
        sponsor=Sponsor(name=_src(S, summary_text, b_sponsor, sponsor)),
        flags=flags,
    )
