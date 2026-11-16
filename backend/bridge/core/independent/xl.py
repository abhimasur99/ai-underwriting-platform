"""Workbook audit: metric cells must be formulas, and their recalculated values must match the
checker's own numbers. Includes a small, SAFE formula evaluator (no eval of arbitrary code)."""
import ast
import re
from pathlib import Path

from openpyxl import load_workbook

from bridge.core.independent.formulas import DOLLAR_KEYS

REF = r"(?:(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))!)?"
CELL = r"\$?([A-Z]{1,3})\$?(\d+)"
RANGE_RE = re.compile(REF + CELL + ":" + CELL)
CELL_RE = re.compile(REF + CELL)
ALLOWED_CALLS = {"SUM", "SUMIF", "MIN", "MAX", "ABS", "IF", "COUNTA", "ROUND"}
ALLOWED_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd, ast.Eq, ast.NotEq,
               ast.Lt, ast.LtE, ast.Gt, ast.GtE)


class FormulaError(ValueError):
    """The formula uses something other than spreadsheet arithmetic and a few functions."""


def _col(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _letters(n: int) -> str:
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _check(tree: ast.AST, names: set[str]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Load)):
            continue
        if isinstance(node, ast.operator | ast.unaryop | ast.cmpop):
            if not isinstance(node, ALLOWED_OPS):
                raise FormulaError(f"operator not allowed: {type(node).__name__}")
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, int | float | str):
                raise FormulaError("constant not allowed")
        elif isinstance(node, ast.Name):
            if node.id not in names and node.id not in ALLOWED_CALLS:
                raise FormulaError(f"name not allowed: {node.id}")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_CALLS \
                    or node.keywords:
                raise FormulaError("call not allowed")
        else:
            raise FormulaError(f"syntax not allowed: {type(node).__name__}")


class Evaluator:
    def __init__(self, workbook):
        self.wb = workbook
        self.cache: dict[tuple[str, str], object] = {}

    def value(self, sheet: str, coord: str):
        key = (sheet, coord)
        if key not in self.cache:
            raw = self.wb[sheet][coord].value
            if isinstance(raw, str) and raw.startswith("="):
                raw = self.evaluate(raw, sheet)
            self.cache[key] = raw
        return self.cache[key]

    def _range(self, sheet, c1, r1, c2, r2):
        return [self.value(sheet, f"{_letters(col)}{row}")
                for row in range(int(r1), int(r2) + 1) for col in range(_col(c1), _col(c2) + 1)]

    def evaluate(self, formula: str, sheet: str):
        strings: list[str] = []
        expr = re.sub(r'"([^"]*)"', lambda m: strings.append(m.group(1)) or f"_s_{len(strings)-1}_",
                      formula[1:])
        stash: list = []

        def rng(m):
            stash.append(self._range(m.group(1) or m.group(2) or sheet, m.group(3), m.group(4),
                                     m.group(5), m.group(6)))
            return f"_v_{len(stash)-1}_"

        def cell(m):
            v = self.value(m.group(1) or m.group(2) or sheet, f"{m.group(3)}{m.group(4)}")
            stash.append(0 if v is None else v)
            return f"_v_{len(stash)-1}_"

        expr = CELL_RE.sub(cell, RANGE_RE.sub(rng, expr))
        expr = re.sub(r"_s_(\d+)_", lambda m: repr(strings[int(m.group(1))]), expr)
        expr = re.sub(r"(?<![<>!=])=(?!=)", "==", expr.replace("<>", "!="))
        env = {f"_v_{i}_": v for i, v in enumerate(stash)}
        try:
            tree = ast.parse(expr.strip(), mode="eval")
        except SyntaxError as exc:
            raise FormulaError(f"cannot parse {formula!r}") from exc
        _check(tree, set(env))
        env.update(
            SUM=lambda *a: sum(x for v in a for x in (v if isinstance(v, list) else [v])
                               if isinstance(x, int | float)),
            MIN=lambda *a: min(a), MAX=lambda *a: max(a), ABS=abs, ROUND=round,
            IF=lambda c, a, b: a if c else b,
            COUNTA=lambda r: sum(1 for x in r if x not in (None, "")),
            SUMIF=lambda crit_range, crit, sum_range: sum(
                s for c, s in zip(crit_range, sum_range, strict=True)
                if c == crit and isinstance(s, int | float)),
        )
        return eval(compile(tree, "<formula>", "eval"), {"__builtins__": {}}, env)  # noqa: S307


METRICS_SHEET = {"total_cost", "ltc", "ltv_as_is", "loan_to_arv", "dscr_in_place",
                 "debt_yield_stabilized", "implied_cap_rate", "rent_roll_vs_t12_gap",
                 "sources_vs_uses_gap"}
EXIT_LABELS = {"payoff": "payoff", "DSCR cap": "cap_dscr", "LTV cap": "cap_ltv",
               "debt yield cap": "cap_debt_yield", "take-out max": "takeout_max",
               "binding cap": "binding", "refi cushion": "refi_cushion", "exit DSCR": "exit_dscr"}
EXIT_STRESS_ONLY = {"stabilized NOI": "noi", "take-out rate": "rate"}


def workbook_audit(path: str | Path, metrics: dict, tol_ratio: float = 1e-4,
                   tol_usd: float = 1.0) -> dict:
    """Locate metric cells by their labels, require formulas, recalc, and compare."""
    wb = load_workbook(path)
    ev = Evaluator(wb)
    targets: dict[str, tuple[str, str]] = {}
    for row in wb["Metrics"].iter_rows(min_row=2):
        if row[0].value in METRICS_SHEET:
            targets[row[0].value] = ("Metrics", f"B{row[0].row}")
    ex = wb["Exit & Stress"]
    start = next((r[0].row for r in ex.iter_rows() if r[0].value == "Take-out sizing"), None)
    for row in ex.iter_rows(min_row=(start or 10) + 1):
        label, r = row[0].value, row[0].row
        if label in EXIT_LABELS:
            targets[EXIT_LABELS[label]] = ("Exit & Stress", f"B{r}")
            targets["stress_" + EXIT_LABELS[label]] = ("Exit & Stress", f"C{r}")
        elif label in EXIT_STRESS_ONLY:
            targets["stress_" + EXIT_STRESS_ONLY[label]] = ("Exit & Stress", f"C{r}")
    hardcoded, mismatches, missing = [], [], []
    for key in sorted(set(metrics) & (METRICS_SHEET | {f"stress_{k}" for k in
                                                      (*EXIT_LABELS.values(), "noi", "rate")}
                                      | set(EXIT_LABELS.values()))):
        if key not in targets:
            missing.append(key)
            continue
        sheet, coord = targets[key]
        raw = wb[sheet][coord].value
        if not (isinstance(raw, str) and raw.startswith("=")):
            hardcoded.append(key)
            continue
        got, want = ev.value(sheet, coord), metrics[key]
        if isinstance(want, str) or isinstance(got, str):
            ok = got == want
        else:
            ok = abs(got - want) <= (tol_usd if key in DOLLAR_KEYS else tol_ratio)
        if not ok:
            mismatches.append({"field": key, "workbook": got, "independent": want})
    return {"hardcoded": hardcoded, "mismatches": mismatches, "missing": missing,
            "audited": len(targets)}
