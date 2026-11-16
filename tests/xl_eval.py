"""Tiny evaluator for the restricted Excel formulas the workbook uses (test helper).

Supports: + - * /, comparisons, cell and range refs (with optional sheet), string literals, and
SUM, SUMIF, MIN, MAX, ABS, IF, COUNTA, ROUND. Lets tests recalculate the workbook without Excel.
"""
import re

REF = r"(?:(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))!)?"
CELL = r"\$?([A-Z]{1,3})\$?(\d+)"
RANGE_RE = re.compile(REF + CELL + ":" + CELL)
CELL_RE = re.compile(REF + CELL)


def _col(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


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
        out = []
        for row in range(int(r1), int(r2) + 1):
            for col in range(_col(c1), _col(c2) + 1):
                letters = ""
                n = col
                while n:
                    n, rem = divmod(n - 1, 26)
                    letters = chr(65 + rem) + letters
                out.append(self.value(sheet, f"{letters}{row}"))
        return out

    def evaluate(self, formula: str, sheet: str):
        expr = formula[1:]
        strings: list[str] = []
        expr = re.sub(r'"([^"]*)"', lambda m: strings.append(m.group(1)) or f"_s_{len(strings)-1}_",
                      expr)
        stash: list = []

        def rng(m):
            s = m.group(1) or m.group(2) or sheet
            stash.append(self._range(s, m.group(3), m.group(4), m.group(5), m.group(6)))
            return f"_v_{len(stash)-1}_"

        def cell(m):
            s = m.group(1) or m.group(2) or sheet
            v = self.value(s, f"{m.group(3)}{m.group(4)}")
            stash.append(0 if v is None else v)
            return f"_v_{len(stash)-1}_"

        expr = RANGE_RE.sub(rng, expr)
        expr = CELL_RE.sub(cell, expr)
        expr = re.sub(r"_s_(\d+)_", lambda m: repr(strings[int(m.group(1))]), expr)
        expr = expr.replace("<>", "!=")
        expr = re.sub(r"(?<![<>!=])=(?!=)", "==", expr)
        env = {f"_v_{i}_": v for i, v in enumerate(stash)}
        env.update(
            SUM=lambda *a: sum(x for v in a for x in (v if isinstance(v, list) else [v])
                               if isinstance(x, (int, float))),
            MIN=lambda *a: min(a), MAX=lambda *a: max(a), ABS=abs, ROUND=round,
            IF=lambda c, a, b: a if c else b,
            COUNTA=lambda r: sum(1 for x in r if x not in (None, "")),
            SUMIF=lambda crit_range, crit, sum_range: sum(
                s for c, s in zip(crit_range, sum_range, strict=True)
                if c == crit and isinstance(s, (int, float))),
        )
        return eval(expr, {"__builtins__": {}}, env)  # noqa: S307 (test helper, own formulas)
