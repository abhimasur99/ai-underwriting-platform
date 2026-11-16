#!/usr/bin/env python3
"""Write cached/ fixtures next to each sample deal so every agent runs offline.

Deterministic: extracted.json is the sourced Deal from the deterministic parsers and
underwriter.json is the placeholder narrative. Run via `make fixtures`. Sample data only.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from bridge.core.narrative import default_narrative  # noqa: E402
from bridge.core.parsers import parse_deal_dir  # noqa: E402
from bridge.core.underwrite import underwrite  # noqa: E402


def main() -> None:
    for deal_dir in sorted((ROOT / "data" / "deals").iterdir()):
        if not (deal_dir / "deal_summary.md").exists():
            continue
        deal = parse_deal_dir(deal_dir)
        cached = deal_dir / "cached"
        cached.mkdir(exist_ok=True)
        (cached / "extracted.json").write_text(deal.model_dump_json(indent=1) + "\n")
        narrative = default_narrative(underwrite(deal))
        (cached / "underwriter.json").write_text(
            json.dumps({"narrative": narrative}, indent=1) + "\n")
        print(f"cached fixtures: {deal_dir.name}")


if __name__ == "__main__":
    main()
