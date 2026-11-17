"""Optional model wording for chat replies, with a code check that can say no.

The reply a person sees is first composed by code (intake_replies.py, chief_chat.py), so it is
correct and safe. In live mode a model may be asked to say the same thing more naturally. Its
version is used only if it passes the checks below; otherwise the code-composed reply is used. The
model is never told anything the reply does not already say, and it may not add to it:

* the sponsor chat may not contain a number the draft lacks, nor a word that belongs to credit or
  underwriting (a call, a ratio, a rate, approval) unless the draft already used it;
* the reviewer chat may not contain a number the draft lacks, so every figure it quotes is one
  that came from a calculation;
* the draft reply to a broker follows the sponsor rule and must also keep its blanks and its list.

Offline there is no model, so the code-composed reply is always used.
"""
import re
from typing import Protocol

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
SENSITIVE = re.compile(
    r"\b(screen\w*|watch|declin\w*|approv\w*|reject\w*|ltv|ltc|dscr|debt yield|cap rate|exit|"
    r"stress|cushion|refinanc\w*|underwrit\w*|interest rate|pricing|credit decisions?|odds|"
    r"likely|guarantee\w*|promise\w*)\b", re.I)
LINKS = re.compile(r"https?://|\]\(|```|<[a-z]+>", re.I)
BLANK = re.compile(r"\[[^\]\n]+\]")          # a [bracketed blank] the reviewer must fill in


def numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in NUMBER.findall(text)}


def _words(text: str) -> set[str]:
    return {m.group(0).lower() for m in SENSITIVE.finditer(text)}


def valid_external(text: str, draft: str) -> bool:
    """The sponsor chat: nothing the draft does not already say about numbers or credit."""
    if not text.strip() or len(text) > 2.5 * len(draft) + 80 or LINKS.search(text):
        return False
    if numbers(text) - numbers(draft):
        return False
    return not (_words(text) - _words(draft))


def valid_internal(text: str, draft: str) -> bool:
    """The reviewer chat: every number quoted is one the calculations produced."""
    if not text.strip() or len(text) > 2.5 * len(draft) + 80 or LINKS.search(text):
        return False
    return not (numbers(text) - numbers(draft))


def valid_broker(text: str, draft: str) -> bool:
    """A letter to someone outside the firm: no new figure, no new credit word, and the same
    placeholders and bullet list (so the reviewer's blanks and the reasons given survive)."""
    if not valid_external(text, draft):
        return False
    if sorted(BLANK.findall(text)) != sorted(BLANK.findall(draft)):
        return False
    return text.count("\n- ") == draft.count("\n- ")


class _Model(Protocol):
    mode: str

    def phrase(self, kind: str, draft: str, history: list[tuple[str, str]]) -> str | None: ...


class Phraser:
    def __init__(self, runner: _Model):
        self.runner = runner

    def _ask(self, kind: str, draft: str, history: list[tuple[str, str]], check) -> str:
        if getattr(self.runner, "mode", "cached") != "live":
            return draft
        try:
            text = self.runner.phrase(kind, draft, history[-6:])
        except Exception:  # noqa: BLE001  (wording is optional: any failure means "use the draft")
            return draft
        return text.strip() if text and check(text, draft) else draft

    def sponsor(self, draft: str, history: list[tuple[str, str]]) -> str:
        return self._ask("sponsor", draft, history, valid_external)

    def reviewer(self, draft: str, history: list[tuple[str, str]]) -> str:
        return self._ask("reviewer", draft, history, valid_internal)

    def broker(self, draft: str) -> str:
        """The draft reply to a broker: held to the strictest check, because it leaves the firm."""
        return self._ask("broker", draft, [], valid_broker)
