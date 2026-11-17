"""A document as numbered lines for the Files tab. The numbers match the `line N` and `rows a-b`
locators on every sourced field, so the tab can highlight exactly what a number was read from."""
from pathlib import Path

from bridge.core.parsers.documents import read_document_text
from bridge.core.parsers.tables import read_raw

TABLE_LABELS = {"rent_roll", "t12", "renovation_budget"}


def document_lines(path: Path, label: str | None) -> tuple[str, list[str]]:
    """(kind, lines). Prose: the extracted text, one entry per line (line 1 first). A table: the
    header is row 1 and each row is its cells joined with ' | ', matching `rows a-b`."""
    if label in TABLE_LABELS:
        return "table", [" | ".join(row) for row in read_raw(path)]
    return "text", read_document_text(path).splitlines()
