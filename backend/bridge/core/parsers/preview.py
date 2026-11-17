"""The deal's basic details, read from the documents as they arrive.

The intake chat uses this so a sponsor who has uploaded a deal summary and a purchase contract is
not asked to type the address, the unit count or the loan amount again. It is best effort and
deterministic: a document it cannot read simply yields no details, and the chat asks the sponsor
instead. Extraction later does the authoritative read; these are only what the chat confirms.
"""
from dataclasses import dataclass
from pathlib import Path

from bridge.core.parsers.deal import (
    _amount,
    _bullet_value,
    _canonical_asset_type,
    _table_row,
)
from bridge.core.parsers.documents import find_text_document, read_document_text
from bridge.core.parsers.errors import ParseError
from bridge.core.parsers.markdown import MarkdownDoc, parse_markdown, strip_parenthetical


@dataclass(frozen=True)
class FactRead:
    key: str            # a key of `required_facts` in config/checklist.yaml
    value: str
    doc: str            # the document it was read from
    locator: str        # "line 8"
    quote: str


def _doc(directory: Path, stem: str) -> tuple[str, MarkdownDoc] | None:
    try:
        path = find_text_document(directory, stem)
        return path.name, parse_markdown(read_document_text(path))
    except (FileNotFoundError, ParseError):
        return None


def read_facts(directory: str | Path) -> list[FactRead]:
    d = Path(directory)
    found: list[FactRead] = []

    def add(key: str, value, name: str, line: int, quote: str) -> None:
        if value in (None, ""):
            return
        text = str(int(round(value))) if isinstance(value, float) else str(value)
        found.append(FactRead(key, text, name, f"line {line}", quote))

    def attempt(fn) -> None:
        try:
            fn()
        except (ParseError, ValueError, AttributeError, IndexError, TypeError):
            pass                                # a detail that cannot be read is simply not read

    if summary := _doc(d, "deal_summary"):
        name, doc = summary

        def bullet(label: str, key: str, kind: str, fix=lambda v: v) -> None:
            b = doc.bullet(label)
            if b is not None:
                add(key, fix(_bullet_value(b, kind)), name, b.line, b.text)

        attempt(lambda: bullet("address", "property_address", "text"))
        attempt(lambda: bullet("asset type", "asset_type", "text", _canonical_asset_type))
        attempt(lambda: bullet("units", "unit_count", "int"))
        attempt(lambda: bullet("loan commitment requested", "loan_amount_requested", "money"))

        def sponsor() -> None:
            b = doc.first_bullet("Sponsor")
            if b is not None:
                add("sponsor_name", strip_parenthetical(b.value), name, b.line, b.text)

        def renovation() -> None:
            row = _table_row(doc.table("Sources and uses", "Uses"), "renovation budget")
            if row is not None:
                add("renovation_budget", _amount(row), name, row.line, row.text)

        attempt(sponsor)
        attempt(renovation)

    if contract := _doc(d, "purchase_contract"):
        name, doc = contract

        def price() -> None:
            b = doc.bullet("purchase price")
            if b is not None:
                add("purchase_price", _bullet_value(b, "money"), name, b.line, b.text)

        attempt(price)
    return found
