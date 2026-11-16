"""Tool registry: each tool has a JSON schema, a formula (where it computes), and a function.
Every call is logged as a `tool.called` event with inputs, formula and output."""
from collections.abc import Callable
from dataclasses import dataclass, field

from bridge.agents.recorder import Recorder


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable
    input_schema: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    formula: str | None = None


class ToolRegistry:
    def __init__(self, agent: str, recorder: Recorder):
        self.agent, self.recorder, self.tools = agent, recorder, {}

    def add(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def call(self, name: str, **inputs):
        if name not in self.tools:
            raise KeyError(f"unknown tool: {name}")
        tool = self.tools[name]
        output = tool.fn(**inputs)
        self.recorder.tool_call(self.agent, name, inputs, tool.formula, output)
        return output

    def schemas(self) -> list[dict]:
        """Anthropic-style tool definitions."""
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in self.tools.values()]


def number_schema(*names: str) -> dict:
    return {"type": "object", "properties": {n: {"type": "number"} for n in names},
            "required": list(names)}
