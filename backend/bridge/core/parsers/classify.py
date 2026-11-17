"""Cheap deterministic file classification: filename hints first, then header hints (from
config/checklist.yaml). A model only picks a label from the fixed enum if both fail (live mode)."""
import csv
import io
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from openpyxl import load_workbook

from bridge.core.parsers.documents import UnreadableDocument, read_document_text

CHECKLIST = Path(__file__).resolve().parents[4] / "config" / "checklist.yaml"


@dataclass
class Classification:
    label: str | None
    status: str                       # "ok", "ambiguous" or "unknown"
    candidates: list[str] = field(default_factory=list)
    note: str = ""


def _header(filename: str, content: bytes) -> set[str]:
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".csv":
            first = next(csv.reader(io.StringIO(content.decode("utf-8-sig"))), [])
        elif ext == ".xlsx":
            sheet = load_workbook(io.BytesIO(content), read_only=True).worksheets[0]
            first = [str(c) for c in next(sheet.iter_rows(values_only=True), []) if c is not None]
        else:
            return set()
    except Exception:  # noqa: BLE001  (an unreadable file simply has no header hints)
        return set()
    return {re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_") for h in first}


def _head(filename: str, content: bytes) -> str:
    """The first lines of a text, PDF or Word document, lower-cased ('' if it cannot be read)."""
    ext = Path(filename).suffix.lower()
    if ext not in (".md", ".txt", ".pdf", ".docx"):
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"doc{ext}"
        path.write_bytes(content)
        try:
            return read_document_text(path)[:800].lower()
        except UnreadableDocument:
            return ""


def classify(filename: str, content: bytes, checklist_path: Path | None = None) -> Classification:
    cfg = yaml.safe_load((checklist_path or CHECKLIST).read_text())["classification"]
    stem = Path(filename).stem.lower()
    by_name = [label for label, hints in cfg["filename_hints"].items()
               if any(h in stem for h in hints)]
    header = _header(filename, content)
    head = _head(filename, content)
    by_content = [label for label, hints in cfg.get("content_hints", {}).items()
                  if any(h in head for h in hints)]
    by_header: list[str] = []
    best = 0.0
    for label, hints in cfg["header_hints"].items():
        hits = sum(1 for h in hints if h in header)
        fraction = hits / len(hints)
        if hits >= 2 and fraction >= 0.75:
            if fraction > best:
                best, by_header = fraction, [label]
            elif fraction == best:
                by_header.append(label)

    if len(by_content) == 1 and (not by_name or by_content[0] in by_name) and not by_header:
        return Classification(by_content[0], "ok")
    if by_name and by_header:
        agree = [label for label in by_name if label in by_header]
        if len(agree) == 1:
            return Classification(agree[0], "ok")
        return Classification(None, "ambiguous", sorted(set(by_name + by_header)),
                              "the filename and the columns point to different document types")
    if len(by_name) == 1 and not header:
        return Classification(by_name[0], "ok")
    if len(by_name) == 1:
        return Classification(by_name[0], "ok")
    if len(by_header) == 1:
        return Classification(by_header[0], "ok")
    if by_name or by_header:
        return Classification(None, "ambiguous", sorted(set(by_name + by_header)),
                              "more than one document type fits")
    return Classification(None, "unknown", [], "could not tell what this file is")
