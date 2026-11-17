"""Source trace: every document-sourced field must point at a real file, a quote that is in that
file, and a quote that contains the value."""
import re
from pathlib import Path

from bridge.core.independent.textread import read_text
from bridge.core.schema import Deal


def _walk(node, path=""):
    if isinstance(node, dict):
        if {"value", "source", "confidence"} <= set(node):
            yield path, node
            return
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        return   # table rows carry no per-cell source


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def _value_in_quote(value, quote: str) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, int | float):
        candidates = _numbers(quote)
        wanted = abs(float(value))
        return any(abs(c - wanted) <= 0.5 or abs(c / 100 - wanted) <= 0.00006 for c in candidates)
    def letters(text: str) -> str:      # "multifamily" is in "Multi-family walk-up"
        return re.sub(r"[^a-z0-9]", "", text.lower())

    return letters(str(value)) in letters(quote)


def source_trace(deal: Deal, deal_dir: str | Path) -> list[str]:
    """Problems found, as 'field: reason' strings. Empty means every field traces."""
    directory, problems = Path(deal_dir), []
    texts: dict[str, str | None] = {}
    for path, field in _walk(deal.model_dump()):
        src = field["source"]
        if src["kind"] != "document":
            continue
        doc = src["doc"]
        if doc not in texts:
            file = directory / doc
            texts[doc] = read_text(file) if file.exists() else None
        if texts[doc] is None:
            problems.append(f"{path}: document {doc} not found")
        elif not src.get("quote"):
            problems.append(f"{path}: no quote")
        elif src["quote"] not in texts[doc]:
            problems.append(f"{path}: quote not found in {doc}")
        elif not _value_in_quote(field["value"], src["quote"]):
            problems.append(f"{path}: value {field['value']!r} is not in its quote")
    return problems
