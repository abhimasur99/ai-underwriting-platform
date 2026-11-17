"""Read-only JSON view of a generated workbook for the UI grid: every non-empty cell with its
formula (when it has one) and its recalculated value, using the same safe evaluator the checker
uses. No spreadsheet library is needed in the browser."""
from pathlib import Path

from openpyxl import load_workbook

from bridge.core.independent.xl import Evaluator


def workbook_view(path: str | Path) -> dict:
    wb = load_workbook(path)
    ev = Evaluator(wb)
    sheets = []
    for ws in wb.worksheets:
        cells = []
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                formula = c.value if isinstance(c.value, str) and c.value.startswith("=") else None
                error = None
                try:
                    value = ev.value(ws.title, c.coordinate)
                except Exception as exc:  # noqa: BLE001  (show the cell, not a crash)
                    value, error = None, f"{type(exc).__name__}: {exc}"
                cells.append({"ref": c.coordinate, "row": c.row, "col": c.column,
                              "value": value if isinstance(value, int | float | str) else
                              (None if value is None else str(value)),
                              "formula": formula, "format": c.number_format, "error": error})
        sheets.append({"name": ws.title, "rows": ws.max_row, "cols": ws.max_column,
                       "cells": cells})
    return {"sheets": sheets}
