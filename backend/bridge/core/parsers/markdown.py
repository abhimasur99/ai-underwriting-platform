"""Deterministic reader for the sample markdown documents: `Label: value` bullets and tables."""
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Bullet:
    section: str
    label: str | None        # lower-cased, parentheticals removed; None for unlabeled bullets
    value: str
    line: int
    text: str                # the raw line, used as the quote


@dataclass
class TableRow:
    line: int
    cells: list[str]
    text: str


@dataclass
class Table:
    section: str
    header: list[str]
    rows: list[TableRow] = field(default_factory=list)


@dataclass
class MarkdownDoc:
    title: str
    # "Deal ID: X" lines that are not bullets: label -> (value, line, text)
    plain: dict[str, tuple[str, int, str]]
    bullets: list[Bullet]
    tables: list[Table]

    def bullet(self, label: str, section: str | None = None) -> Bullet | None:
        for b in self.bullets:
            if b.label == label and (section is None or b.section == section):
                return b
        return None

    def first_bullet(self, section: str) -> Bullet | None:
        return next((b for b in self.bullets if b.section == section), None)

    def table(self, section: str, first_header: str | None = None) -> Table | None:
        for t in self.tables:
            if t.section == section and (
                    first_header is None or t.header[0].lower() == first_header.lower()):
                return t
        return None


def clean_label(raw: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", raw).strip().lower()


def strip_parenthetical(text: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_markdown(text: str) -> MarkdownDoc:
    title, section = "", ""
    plain: dict[str, tuple[str, int, str]] = {}
    bullets: list[Bullet] = []
    tables: list[Table] = []
    current: Table | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = _split_row(stripped)
            if current is None:
                current = Table(section=section, header=cells)
                tables.append(current)
            elif not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                current.rows.append(TableRow(number, cells, stripped))
            continue
        current = None
        if stripped.startswith("# "):
            title = stripped[2:].strip()
        elif stripped.startswith("## "):
            section = stripped[3:].strip()
        elif stripped.startswith("- "):
            body = stripped[2:].strip()
            label, sep, value = body.partition(":")
            if sep:
                bullets.append(Bullet(section, clean_label(label), value.strip(), number, stripped))
            else:
                bullets.append(Bullet(section, None, body, number, stripped))
        elif ":" in stripped:
            label, _, value = stripped.partition(":")
            plain[clean_label(label)] = (value.strip(), number, stripped)
    return MarkdownDoc(title, plain, bullets, tables)
