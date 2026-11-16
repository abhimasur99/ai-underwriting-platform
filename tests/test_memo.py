"""Memo: a one-page PDF with numbers filled from the result and the sample-data footer."""
import re
import zlib
from base64 import a85decode
from datetime import date

import pytest
from bridge.core.builders.memo import FOOTER, render_memo
from bridge.core.parsers import parse_deal_dir
from bridge.core.underwrite import underwrite


def pdf_text(path) -> str:
    """Pull the text out of an uncompressed reportlab PDF (helper; no PDF library needed)."""
    data = path.read_bytes()
    chunks = []
    for stream in re.findall(rb"stream\r?\n(.*?)endstream", data, re.S):
        body = stream.strip()
        if body.endswith(b"~>"):
            body = a85decode(body, adobe=False) if not body.startswith(b"<~") else a85decode(
                body, adobe=True)
        try:
            body = zlib.decompress(body)
        except zlib.error:
            pass
        chunks.append(body.decode("latin-1"))
    text = "\n".join(chunks)
    return " ".join(re.findall(r"\((.*?)(?<!\\)\)\s*Tj", text)).replace("\\(", "(").replace(
        "\\)", ")")


@pytest.fixture
def memo(deal_dir, tmp_path):
    deal = parse_deal_dir(deal_dir)
    result = underwrite(deal)
    path = tmp_path / "memo.pdf"
    render_memo(deal, result, path, as_of=date(2026, 11, 16))
    return path, deal, result


def test_one_page_pdf(memo):
    path, _, _ = memo
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page(?![s\w])", data)) == 1


def test_header_call_and_footer(memo):
    path, deal, result = memo
    text = pdf_text(path)
    assert deal.deal_id in text
    assert result.call.upper() in text
    assert "2026-11-16" in text
    assert FOOTER in text
    assert "Illustrative thresholds, not a real lender's box" in FOOTER


def test_numbers_come_from_the_result(memo):
    path, _, result = memo
    text = pdf_text(path)
    assert f"{result.metrics.ltc * 100:.2f}%" in text
    assert f"${result.exit.takeout_max:,.0f}" in text
    assert f"{result.exit.exit_dscr:.2f}x" in text
    assert f"${result.stress.takeout_max:,.0f}" in text


def test_reasons_are_listed(memo):
    path, _, result = memo
    text = pdf_text(path)
    for reason in result.reasons:
        assert reason.code in text


def test_every_dollar_percent_and_multiple_in_the_memo_traces_to_the_result_or_deal(memo):
    """No stray numbers: each $ amount, % and x in the memo is a rounded value from the data."""
    path, deal, result = memo
    text = pdf_text(path)
    pool = {float(n) for blob in (result.model_dump_json(), deal.model_dump_json())
            for n in re.findall(r"-?\d+(?:\.\d+)?", blob)}

    def near(value: float, tolerance: float) -> bool:
        return any(abs(value - p) <= tolerance for p in pool)

    for token in re.findall(r"-?\$[\d,]+", text):
        assert near(float(token.replace("$", "").replace(",", "")), 1.0), token
    for token in re.findall(r"\d+\.\d+%", text):
        assert near(float(token[:-1]) / 100, 0.00006), token
    for token in re.findall(r"\d+\.\d+x", text):
        assert near(float(token[:-1]), 0.0051), token
