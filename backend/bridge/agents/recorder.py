"""Writes workflow events and tool-call records for one deal through the store."""
from bridge.core.schema import ToolCall
from bridge.store.db import Store, now


def _plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _short(value) -> str:
    value = _plain(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    text = str(value)
    return text if len(text) <= 80 else text[:77] + "..."


class Recorder:
    def __init__(self, store: Store, deal_id: str, version: int = 1):
        self.store, self.deal_id, self.version = store, deal_id, version

    def event(self, actor: str, type_: str, summary: str, payload: dict | None = None):
        return self.store.append_event(self.deal_id, actor, type_, summary, self.version,
                                       payload or {})

    def tool_call(self, agent: str, tool: str, inputs: dict, formula: str | None, output):
        n = sum(1 for e in self.store.events(self.deal_id) if e.type == "tool.called") + 1
        record = ToolCall(call_id=f"t-{n:04d}", agent=agent, tool=tool, inputs=_plain(inputs),
                          formula=formula, output=_plain(output), ts=now())
        self.event(agent, "tool.called", f"{tool} = {_short(output)}", record.model_dump())
        return record
