"""Offline interpretation of chat messages: plain regex rules. This is the 'cached' counterpart of
the model's job (read a message, return structure). It never produces numbers of its own beyond
parsing the ones the person typed."""
import re

from bridge.agents.runner_types import ChiefTurn, IntakeTurn, PatchRequest

FACT_KEYS = ["property_address", "asset_type", "unit_count", "loan_amount_requested",
             "purchase_price", "renovation_budget", "sponsor_name"]
DECISION_WORDS = re.compile(
    r"\b(approv\w*|odds|chances?|pricing|what rate|interest rate|quote|term sheet|ltv|ltc|"
    r"dscr|cap rate|decision|will you (?:fund|lend)|how much (?:can|will) you)\b", re.I)


def _money(number: str, scale: str | None) -> float:
    value = float(number.replace(",", ""))
    if scale and scale.lower().startswith("m"):
        value *= 1_000_000
    elif scale and scale.lower() in ("k", "thousand"):
        value *= 1_000
    return value


_AMOUNT = r"\$?\s*([\d][\d,]*(?:\.\d+)?)\s*(million|m|thousand|k)?\b"


def interpret_intake(message: str) -> IntakeTurn:
    facts: dict[str, str] = {}
    text = message.strip()
    if m := re.search(r"(?:sponsor(?: name)?|borrower)\s*(?:is|:)\s*(.+?)(?:[.;\n]|$)", text, re.I):
        facts["sponsor_name"] = m.group(1).strip()
    if m := re.search(r"(?:address|property)\s*(?:is|:)\s*(.+?)(?:[.;\n]|$)", text, re.I):
        facts["property_address"] = m.group(1).strip()
    if re.search(r"mixed[\s_-]?use", text, re.I):
        facts["asset_type"] = "mixed_use"
    elif re.search(r"multi[\s-]?family", text, re.I):
        facts["asset_type"] = "multifamily"
    if m := re.search(r"(\d+)\s*(?:units?|apartments)\b", text, re.I):
        facts["unit_count"] = m.group(1)
    for key, pattern in (
            ("purchase_price", r"purchase price(?:\s*(?:is|of|:))?\s*"),
            ("renovation_budget", r"(?:renovation|reno)(?: budget)?(?:\s*(?:is|of|:))?\s*"),
            ("loan_amount_requested",
             r"loan(?: amount)?(?: request(?:ed)?)?(?:\s*(?:is|of|:))?\s*")):
        if m := re.search(pattern + _AMOUNT, text, re.I):
            facts[key] = str(int(_money(m.group(1), m.group(2))))
    return IntakeTurn(facts={k: v for k, v in facts.items() if k in FACT_KEYS},
                      asks_for_decision=bool(DECISION_WORDS.search(text)))


METRIC_WORDS = [
    (r"loan[\s-]to[\s-]cost|\bltc\b", "ltc"),
    (r"loan[\s-]to[\s-]arv|\bl\.?t\.?a\.?r?\b", "loan_to_arv"),
    (r"loan[\s-]to[\s-]value|\bltv\b|as[\s-]is", "ltv_as_is"),
    (r"in[\s-]place dscr", "dscr_in_place"),
    (r"exit dscr|\bdscr\b", "exit_dscr"),
    (r"debt yield", "debt_yield_stabilized"),
    (r"cap(?:italization)? rate", "implied_cap_rate"),
    (r"stress", "stress_refi_cushion"),
    (r"cushion", "refi_cushion"),
    (r"take[\s-]?out|refinanc", "takeout_max"),
    (r"total cost", "total_cost"),
    (r"rent roll", "rent_roll_vs_t12_gap"),
    (r"sources", "sources_vs_uses_gap"),
]
EDIT_FIELDS = [
    (r"\barv\b|after[\s-]repair", "arv"),
    (r"as[\s-]is value", "as_is_value"),
    (r"initial advance", "initial_advance"),
    (r"loan (?:amount|commitment)|commitment", "loan_commitment"),
    (r"note rate|interest rate|\brate\b", "note_rate"),
    (r"stabilized noi|\bnoi\b", "stabilized_noi"),
    (r"\brent\b", "rent"),
]


def _reason(text: str) -> str:
    m = re.search(r"(?:because|reason\s*:|since)\s*(.+)$", text, re.I)
    return m.group(1).strip().rstrip(".") if m else ""


def interpret_chief(message: str) -> ChiefTurn:
    text = message.strip()
    low = text.lower()
    if re.search(r"\b(other deals?|lender polic\w+|real lender|legal advice)\b", low):
        return ChiefTurn("question", topic="outside")
    if re.match(r"\s*(?:please\s+)?(approve|reject|send (?:it )?back)\b", low):
        verb = re.match(r"\s*(?:please\s+)?(approve|reject|send (?:it )?back)", low).group(1)
        return ChiefTurn("action", action="send_back" if "back" in verb else verb)
    if m := re.match(r"\s*override\b[:,]?\s*(.+)", text, re.I | re.S):
        body = m.group(1)
        reason = _reason(body)
        judgment = re.split(r"\s*(?:because|reason\s*:|since)\s*", body, maxsplit=1, flags=re.I)[0]
        return ChiefTurn("override", patch=PatchRequest("override", text=judgment.strip(" ."),
                                                        reason=reason))
    if m := re.search(r"(?:reword|rewrite|change|update)\s+the\s+(summary|exit|risks)"
                      r"(?:\s+(?:section|narrative|text))?\s*(?:to say|to|:)\s*(.+)$",
                      text, re.I | re.S):
        return ChiefTurn("narrative_edit", patch=PatchRequest(
            "narrative", section=m.group(1).lower(), text=m.group(2).strip().strip('"')))
    if re.search(r"\b(change|set|update|make|correct|revise)\b", low):
        for pattern, field_name in EDIT_FIELDS:
            if re.search(pattern, low):
                m = re.search(r"(?:to|at|=)\s*\$?\s*([\d][\d,]*(?:\.\d+)?)\s*"
                              r"(%|percent|million|m|k)?", low)
                if m:
                    value = float(m.group(1).replace(",", ""))
                    scale = m.group(2)
                    if scale in ("%", "percent"):
                        value /= 100
                    elif scale in ("million", "m"):
                        value *= 1_000_000
                    elif scale == "k":
                        value *= 1_000
                    unit = None
                    if field_name == "rent":
                        um = re.search(r"unit\s+([\w-]+)", low)
                        unit = um.group(1).upper() if um else None
                    return ChiefTurn("data_edit", patch=PatchRequest(
                        "data", field=field_name, value=value, unit=unit,
                        reason=_reason(text) or text))
    if re.search(r"\bwhy\b.*\b(decline|watch|screen|call|flag\w*|reason\w*)\b|\breasons?\b", low):
        return ChiefTurn("question", topic="reasons")
    for pattern, metric in METRIC_WORDS:
        if re.search(pattern, low):
            return ChiefTurn("question", metric=metric)
    if re.search(r"\b(summary|summari[sz]e|overview|tell me about)\b", low):
        return ChiefTurn("question", topic="summary")
    return ChiefTurn("question", topic="outside")
