"""Read text from the memo PDF (reportlab output) and check every number against the checker's
own figures."""
import re
import zlib
from base64 import a85decode
from pathlib import Path

TOKEN = re.compile(r"-?\$[\d,]+|\d+\.\d+%|\d+\.\d+x")


def extract_pdf_text(path: str | Path) -> str:
    data = Path(path).read_bytes()
    chunks = []
    for stream in re.findall(rb"stream\r?\n(.*?)endstream", data, re.S):
        body = stream.strip()
        if body.endswith(b"~>"):
            body = a85decode(body, adobe=body.startswith(b"<~"))
        try:
            body = zlib.decompress(body)
        except zlib.error:
            pass
        chunks.append(body.decode("latin-1"))
    text = "\n".join(chunks)
    pieces = re.findall(r"\((.*?)(?<!\\)\)\s*Tj", text)
    return " ".join(pieces).replace("\\(", "(").replace("\\)", ")")


def _flatten(node, out: list[float]) -> None:
    if isinstance(node, bool):
        return
    if isinstance(node, int | float):
        out.append(float(node))
    elif isinstance(node, dict):
        for v in node.values():
            _flatten(v, out)
    elif isinstance(node, list):
        for v in node:
            _flatten(v, out)


def build_pool(inputs: dict, metrics: dict, cfg: dict) -> dict[str, list[float]]:
    nums: list[float] = [0.0]
    _flatten(inputs, nums)
    _flatten({k: v for k, v in metrics.items() if not isinstance(v, str)}, nums)
    _flatten(cfg, nums)
    holdback = inputs["loan_commitment"] - inputs["initial_advance"]
    nums += [holdback, sum(s["amount"] for s in inputs["sources"]),
             sum(u["amount"] for u in inputs["uses"])]
    return {"usd": nums, "pct": nums, "mult": nums}


def find_unmatched(text: str, pool: dict[str, list[float]]) -> list[str]:
    def near(value: float, candidates: list[float], tol: float) -> bool:
        return any(abs(value - c) <= tol for c in candidates)

    bad = []
    for token in TOKEN.findall(text):
        if token.endswith("%"):
            ok = near(float(token[:-1]) / 100, pool["pct"], 0.00006)
        elif token.endswith("x"):
            ok = near(float(token[:-1]), pool["mult"], 0.0051)
        else:
            ok = near(float(token.replace("$", "").replace(",", "")), pool["usd"], 1.0)
        if not ok:
            bad.append(token)
    return bad


def memo_number_match(path: str | Path, inputs: dict, metrics: dict, cfg: dict,
                      call: str) -> dict:
    text = extract_pdf_text(path)
    return {"unmatched": find_unmatched(text, build_pool(inputs, metrics, cfg)),
            "call_ok": f"CALL: {call.upper()}" in text}
