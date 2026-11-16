#!/usr/bin/env python3
"""Run sample deals through the chief, offline by default. See bridge/cli.py for options."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from bridge.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
