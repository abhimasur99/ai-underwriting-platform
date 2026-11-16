#!/usr/bin/env python3
"""One tiny live Claude call to verify the API key and the request shape the runner uses
(structured output via output_config.format). Needs ANTHROPIC_API_KEY in .env or the environment."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import anthropic  # noqa: E402
from bridge.settings import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    if not settings.api_key:
        print("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return 1
    client = anthropic.Anthropic(api_key=settings.api_key)
    try:
        reply = client.messages.create(
            model=settings.model, max_tokens=2048,
            messages=[{"role": "user", "content": "Reply with JSON saying ok is true."}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": {
                "type": "object", "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"], "additionalProperties": False}}},
        )
    except anthropic.APIError as exc:
        print(f"Claude call failed: {type(exc).__name__}: {exc}")
        return 1
    text = next((b.text for b in reply.content if b.type == "text"), "")
    ok = bool(text) and json.loads(text).get("ok") is True
    print(f"model={settings.model} stop={reply.stop_reason} ok={ok} "
          f"tokens in/out={reply.usage.input_tokens}/{reply.usage.output_tokens}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
