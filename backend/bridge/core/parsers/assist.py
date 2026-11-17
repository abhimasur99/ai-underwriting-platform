"""Model-assisted reading for documents the deterministic parser cannot read.

The deterministic parser always runs first. Only when it cannot find a required field or a table
column does the caller ask an `Assist` (a model, in live mode). The model is never trusted:

* for prose fields it must return the value as written plus a one-line quote; code rejects a field
  whose quote is not in the document or whose value is not inside its quote, and the field is then
  treated as missing (the deal stops and asks, it never guesses);
* for table columns it only maps a column heading to a canonical name; the numbers still come from
  the table, read by code;
* every field it supplies is marked `assisted`, carries lower confidence, and the deal gets a flag
  so the reviewer sees what the model read.

This module has no model or web imports (core must stay free of them): the model sits behind the
`Assist` protocol, implemented in agents/claude_runner.py.
"""
import re
from dataclasses import dataclass, field
from typing import Protocol

from bridge.core.parsers.markdown import Bullet, Table, TableRow
from bridge.core.parsers.tables import normalize_header, parse_number

ASSISTED_CONFIDENCE = 0.75      # below the 0.80 review threshold on purpose: a human should look


@dataclass(frozen=True)
class FieldSpec:
    key: str            # the name the deal parser reports when it is missing
    doc: str            # "summary" or "contract"
    group: str          # "property", "sponsor", "loan", "valuation", "pro_forma", "purchase"
    label: str          # the label the deal parser looks up
    section: str        # the section it looks in
    ask: str            # what to tell the model


PRO_FORMA_SECTION = "Stabilized pro forma (borrower provided)"
SPECS = [
    FieldSpec("address", "summary", "property", "address", "Property",
              "the property's street address"),
    FieldSpec("asset_type", "summary", "property", "asset type", "Property",
              "the asset type as written, for example multifamily or mixed use"),
    FieldSpec("unit_count", "summary", "property", "units", "Property",
              "the total number of units"),
    FieldSpec("occupied_units", "summary", "property", "in-place occupancy", "Property",
              "the number of units currently occupied (a count, not a percentage)"),
    FieldSpec("sponsor_name", "summary", "sponsor", "", "Sponsor",
              "the sponsor (borrower) name"),
    FieldSpec("loan_commitment", "summary", "loan", "loan commitment requested", "Loan request",
              "the total loan amount requested (the full commitment, including any holdback)"),
    FieldSpec("initial_advance", "summary", "loan", "initial advance at closing", "Loan request",
              "the amount advanced at closing (before the renovation holdback)"),
    FieldSpec("note_rate", "summary", "loan", "note rate", "Loan request",
              "the interest rate, written with its percent sign"),
    FieldSpec("as_is_value", "summary", "valuation", "as-is value", "Valuation",
              "the as-is (current) property value"),
    FieldSpec("arv", "summary", "valuation", "after-repair value", "Valuation",
              "the after-repair value (ARV, as-stabilized value)"),
    FieldSpec("stabilized_noi", "summary", "pro_forma", "stabilized noi", PRO_FORMA_SECTION,
              "the stabilized net operating income from the pro forma"),
    FieldSpec("purchase_price", "contract", "purchase", "purchase price", "",
              "the purchase price in the contract"),
]
TABLE_KEYS = {"sources_table", "uses_table", "stated_total_sources", "stated_total_uses",
              "renovation_budget"}
SPEC_BY_KEY = {s.key: s for s in SPECS}
NUMBER_KINDS = {"unit_count", "occupied_units", "loan_commitment", "initial_advance",
                "as_is_value", "arv", "stabilized_noi", "purchase_price"}

COLUMNS = {
    "rent_roll": ["unit", "unit_type", "sqft", "status", "tenant", "lease_start", "lease_end",
                  "monthly_rent"],
    "t12": ["line_item", "category", "total"],
    "renovation_budget": ["line_item", "amount"],
}


@dataclass(frozen=True)
class RawField:
    key: str
    value_text: str
    quote: str


@dataclass(frozen=True)
class RawRow:
    name: str
    amount_text: str
    quote: str
    is_renovation_budget: bool = False


@dataclass
class RawReading:
    fields: list[RawField] = field(default_factory=list)
    sources: list[RawRow] = field(default_factory=list)
    uses: list[RawRow] = field(default_factory=list)
    total_sources: RawRow | None = None
    total_uses: RawRow | None = None


class Assist(Protocol):
    def map_columns(self, kind: str, headers: list[str], sample: list[list[str]]
                    ) -> dict[str, str]:
        """Map each heading to a canonical column name (or leave it out). `kind` is one of
        COLUMNS."""

    def read_document(self, name: str, text: str, wanted: list[FieldSpec], want_tables: bool
                      ) -> RawReading:
        """Return the wanted fields as written, each with a one-line quote from `text`."""


@dataclass
class Augmentation:
    bullets: list[Bullet] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    accepted: list[str] = field(default_factory=list)       # supplied by the model, verified
    rejected: dict[str, str] = field(default_factory=dict)  # key -> why it was refused


def _line_of(text: str, quote: str) -> int | None:
    if len(quote.strip()) < 3:
        return None
    for number, line in enumerate(text.splitlines(), start=1):
        if quote in line:
            return number
    return None


def _check(text: str, quote: str, value_text: str) -> tuple[int | None, str]:
    """(line, '') when the quote is in the document and holds the value, else (None, reason)."""
    line = _line_of(text, quote)
    if line is None:
        return None, "its quote is not a single line of the document"
    if not value_text.strip() or value_text not in quote:
        return None, "its value is not inside its quote"
    return line, ""


def _number_ok(value_text: str) -> bool:
    match = re.search(r"-?\$?[\d,]+(?:\.\d+)?", value_text)
    try:
        parse_number(match.group()) if match else None
    except ValueError:
        return False
    return match is not None


def verify(reading: RawReading, text: str, wanted: list[FieldSpec], want_tables: bool
           ) -> Augmentation:
    """Keep only what the document itself supports; everything else is treated as not found."""
    out = Augmentation()
    allowed = {s.key: s for s in wanted}
    pro_forma_rows: list[TableRow] = []
    occupancy: tuple[FieldSpec, str, int, str] | None = None

    for raw in reading.fields:
        spec = allowed.get(raw.key)
        if spec is None:
            continue
        line, why = _check(text, raw.quote, raw.value_text)
        if line is None:
            out.rejected[raw.key] = why
            continue
        if raw.key in NUMBER_KINDS and not _number_ok(raw.value_text):
            out.rejected[raw.key] = "its value is not a number"
            continue
        if raw.key == "occupied_units":      # the parser reads "N of M"; finished below
            occupancy = (spec, raw.value_text, line, raw.quote)
        elif spec.group == "pro_forma":
            pro_forma_rows.append(TableRow(line, ["Stabilized NOI", raw.value_text], raw.quote,
                                           assisted=True))
        else:
            out.bullets.append(Bullet(spec.section, spec.label or None, raw.value_text, line,
                                      raw.quote, assisted=True))
        out.accepted.append(raw.key)

    if occupancy:
        spec, value_text, line, quote = occupancy
        occupied = int(parse_number(re.search(r"[\d,]+", value_text).group()))
        units = next((int(parse_number(re.search(r"[\d,]+", b.value).group()))
                      for b in out.bullets if b.label == "units"), occupied)
        out.bullets.append(Bullet(spec.section, spec.label, f"{occupied} of {units}", line, quote,
                                  assisted=True))

    if pro_forma_rows:
        out.tables.append(Table(PRO_FORMA_SECTION, ["Line", "Annual"], pro_forma_rows))

    if want_tables:
        out.tables += _verify_tables(reading, text, out)
    return out


def _verify_tables(reading: RawReading, text: str, out: Augmentation) -> list[Table]:
    def rows(items: list[RawRow], label: str) -> list[TableRow]:
        kept = []
        for item in items:
            line, why = _check(text, item.quote, item.amount_text)
            if line is None or not _number_ok(item.amount_text):
                out.rejected[f"{label}:{item.name}"] = why or "its value is not a number"
                continue
            name = "Renovation budget" if item.is_renovation_budget else item.name
            kept.append(TableRow(line, [name, item.amount_text], item.quote, assisted=True))
        return kept

    sources, uses = rows(reading.sources, "source"), rows(reading.uses, "use")
    totals = []
    for label, raw in (("Total sources", reading.total_sources),
                       ("Total uses", reading.total_uses)):
        kept = rows([raw], label) if raw else []
        totals.append(kept[0] if kept else None)
    tables = []
    if sources and totals[0] and uses and totals[1]:
        sources.append(TableRow(totals[0].line, ["Total sources", totals[0].cells[1]],
                                totals[0].text, assisted=True))
        uses.append(TableRow(totals[1].line, ["Total uses", totals[1].cells[1]],
                             totals[1].text, assisted=True))
        tables = [Table("Sources and uses", ["Sources", "Amount"], sources),
                  Table("Sources and uses", ["Uses", "Amount"], uses)]
        for key in ("sources_table", "uses_table", "stated_total_sources", "stated_total_uses"):
            out.accepted.append(key)
        if any(r.cells[0] == "Renovation budget" for r in uses):
            out.accepted.append("renovation_budget")
    return tables


def checked_mapping(kind: str, headers: list[str], mapping: dict[str, str]
                    ) -> dict[str, str]:
    """The model's column mapping, reduced to what is safe: real headings, known canonical names,
    and no two headings claiming the same column. Keys are normalized headings."""
    allowed, seen, out = set(COLUMNS[kind]), set(), {}
    real = {normalize_header(h): h for h in headers}
    for heading, canonical in mapping.items():
        key = normalize_header(heading)
        if key in real and canonical in allowed and canonical not in seen:
            out[key] = canonical
            seen.add(canonical)
    return out
