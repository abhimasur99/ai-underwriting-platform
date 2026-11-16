"""Typed results of interpreting a chat message. The model (or cached rules) only INTERPRETS a
message; replies are composed by code from tool output, so the external chat can never leak a
number and the chief never states a figure it did not get from a tool."""
from dataclasses import dataclass, field


@dataclass
class IntakeTurn:
    facts: dict[str, str] = field(default_factory=dict)   # allowlisted keys only (code filters)
    asks_for_decision: bool = False                         # rates, approval odds, pricing...


@dataclass
class PatchRequest:
    kind: str                       # "data" | "narrative" | "override"
    field: str | None = None        # arv, as_is_value, loan_commitment, ..., rent
    value: float | None = None
    unit: str | None = None         # for rent edits
    section: str | None = None      # narrative section
    text: str | None = None         # narrative text or override judgment
    reason: str = ""


@dataclass
class ChiefTurn:
    intent: str                     # question | data_edit | narrative_edit | override | action
    metric: str | None = None       # for questions
    topic: str | None = None        # "reasons" | "summary" | "outside" | None
    patch: PatchRequest | None = None
    action: str | None = None       # approve | send_back | reject
