#!/usr/bin/env python3
"""Export the OpenAPI spec the frontend types come from (writes frontend/openapi.json)."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from bridge.api.app import create_app  # noqa: E402
from bridge.settings import Settings  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        app = create_app(Settings(None, "unused", runtime / "spec.db", runtime))
        out = ROOT / "frontend" / "openapi.json"
        out.write_text(json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n")
        print(f"wrote {out.relative_to(ROOT)} ({len(app.openapi()['paths'])} paths)")


if __name__ == "__main__":
    main()
