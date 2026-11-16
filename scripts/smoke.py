#!/usr/bin/env python3
"""One tiny live Claude call to verify the API key. Needs ANTHROPIC_API_KEY in .env or the env."""
import os
import sys
from pathlib import Path

import anthropic


def load_env() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return 1
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    client = anthropic.Anthropic()
    reply = client.messages.create(
        model=model,
        max_tokens=16,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
    )
    print(f"model={model} reply={reply.content[0].text.strip()!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
