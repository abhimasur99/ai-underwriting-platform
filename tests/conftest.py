"""Shared helpers: sample deal paths and their answer keys."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEALS_DIR = ROOT / "data" / "deals"
DEAL_NAMES = ["bronx_mf", "queens_mixed_use", "overleveraged_bk"]


@pytest.fixture(params=DEAL_NAMES)
def deal_name(request) -> str:
    return request.param


@pytest.fixture
def deal_dir(deal_name) -> Path:
    return DEALS_DIR / deal_name


@pytest.fixture
def expected(deal_dir) -> dict:
    return json.loads((deal_dir / "expected.json").read_text())
