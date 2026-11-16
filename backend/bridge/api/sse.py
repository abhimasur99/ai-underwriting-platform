"""Server-sent events over the event log. The stream reads the store (the log is the source of
truth); it never polls a model."""
import asyncio
import json
from collections.abc import AsyncIterator

from bridge.store.db import Store


def format_event(event) -> str:
    data = {k: getattr(event, k) for k in ("event_id", "deal_id", "ts", "type", "actor",
                                           "summary", "deal_version")}
    return f"id: {event.event_id}\nevent: {event.type}\ndata: {json.dumps(data)}\n\n"


async def event_stream(store: Store, deal_id: str | None, after: int = 0, poll: float = 0.25,
                       once: bool = False, is_disconnected=None) -> AsyncIterator[str]:
    """Yield SSE frames for new events. `once` flushes what exists and ends (for tests, curl)."""
    last = after
    idle = 0.0
    while True:
        events = await asyncio.to_thread(store.events, deal_id, last)
        for e in events:
            last = e.event_id
            yield format_event(e)
        if once:
            return
        if is_disconnected is not None and await is_disconnected():
            return
        idle += poll
        if not events and idle >= 15:
            idle = 0.0
            yield ": keep-alive\n\n"
        await asyncio.sleep(poll)
