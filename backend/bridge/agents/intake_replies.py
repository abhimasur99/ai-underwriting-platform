"""What the sponsor chat says. Pure functions: the words come from the checklist and the deal's
state, never from underwriting, so the chat cannot reveal a call, a ratio or a number of ours.

The tone is a courteous business correspondent: plain words, no slang, no emoji, and every reply
says where things stand and what happens next. Wording varies a little by turn so a repeated
question is not answered with identical text, but a given turn always gives the same answer, so
conversations are testable. In live mode a model may rephrase these replies, and code checks the
result before it is used (agents/phrasing.py).
"""
from dataclasses import dataclass

DOCS = {"deal_summary": "deal summary", "purchase_contract": "purchase contract",
        "rent_roll": "rent roll", "t12": "T-12", "renovation_budget": "renovation budget"}
FACT_ASK = {
    "property_address": "the property address", "asset_type": "the asset type (multifamily or "
    "mixed use)", "unit_count": "the number of units", "loan_amount_requested":
    "the loan amount you are requesting", "purchase_price": "the purchase price",
    "renovation_budget": "the renovation budget", "sponsor_name": "the sponsor's name",
}
FACT_NAME = {"property_address": "property address", "asset_type": "asset type",
             "unit_count": "number of units", "loan_amount_requested": "requested loan amount",
             "purchase_price": "purchase price", "renovation_budget": "renovation budget",
             "sponsor_name": "sponsor name"}
FORMATS = "PDF, Word, Excel or CSV"
REFUSAL = ("I can't discuss pricing, terms or credit decisions in this chat. The team will follow "
           "up after review.")

IN_REVIEW = {"EXTRACTING", "EXTRACTED", "UNDERWRITING", "UNDERWRITTEN", "CHECKING", "CHECKED",
             "NEEDS_REVIEW", "SENT_BACK", "READY"}
DONE = {"APPROVED", "RELEASED", "REJECTED"}


@dataclass
class Ctx:
    received: list[str]                 # document types we have
    missing: list[str]                  # document types still needed
    facts_missing: list[str]            # details still needed
    ready: bool                         # nothing else is needed
    state: str = "AWAITING_DOCS"
    turn: int = 0                       # how many messages the sponsor has already sent
    note: str = ""                      # the reviewer's question, when one is open
    awaiting: bool = False              # the team is waiting on the sponsor


def joined(items: list[str]) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def docs(keys: list[str]) -> str:
    return joined([DOCS[k] for k in keys])


def pick(options: list[str], turn: int) -> str:
    return options[turn % len(options)]


def ask_next(c: Ctx, after_receipt: bool = False) -> str:
    """Where we are and what to do next. After a receipt the list of what we hold is left out,
    because the receipt has just said it."""
    if c.state in DONE:
        return "The team has finished its review and will follow up with you."
    if c.state == "FAILED":
        return "Something went wrong on our side, and the team will follow up with you."
    if c.awaiting and c.note:
        return (f"The team has a question: {c.note} You can reply here, or upload the file they "
                "need.")
    if c.state == "NEEDS_INPUT":
        return "We need one more item from you, and the team will be in touch."
    if c.ready and c.state in IN_REVIEW:
        return ("Your package is with our team for review. If they need anything else, I'll "
                "post it here.")
    if c.ready:
        return "Your package is complete. Our team will review it and follow up with you."
    parts = []
    if c.received and not after_receipt:
        parts.append(f"I have your {docs(c.received)}.")
    if c.missing:
        parts.append(f"To complete the package, please send your {docs(c.missing)}.")
    elif c.facts_missing:
        names = [FACT_ASK[k] for k in c.facts_missing[:3]]
        parts.append(f"I still need a few details: {joined(names)}."
                     if len(names) > 1 else f"One last detail: could you tell me {names[0]}?")
    return " ".join(parts)


def greeting(c: Ctx) -> str:
    if c.turn == 0 and not c.received:
        return ("Hello. Whenever you are ready, drop your documents here or onto the checklist "
                f"and I will take it from there. {ask_next(c)}")
    return f"Hello again. {ask_next(c)}"


def help_(c: Ctx) -> str:
    return ("I collect the documents and basic details our team needs to review a bridge loan "
            "request, and I'll let you know if anything is missing. I can't discuss pricing, terms "
            f"or credit decisions; the team follows up after review. {ask_next(c)}")


def missing(c: Ctx) -> str:
    if c.ready:
        return f"Nothing is missing. {ask_next(c)}"
    got = (f"I have your {docs(c.received)}. " if c.received
           else "I haven't received any documents yet. ")
    need = []
    if c.missing:
        need.append(f"Still needed: {docs(c.missing)}.")
    if c.facts_missing:
        need.append(f"I also need {joined([FACT_ASK[k] for k in c.facts_missing[:3]])}.")
    return got + " ".join(need)


def next_(c: Ctx) -> str:
    base = ("Once your package is complete, our team reviews it and follows up with you directly. "
            "I can't give a timeline or say what the outcome will be.")
    return f"{base} {ask_next(c)}"


def status(c: Ctx) -> str:
    return ask_next(c)


def thanks(c: Ctx) -> str:
    return f"{pick(['You are welcome.', 'Happy to help.'], c.turn)} {ask_next(c)}"


def unclear(c: Ctx) -> str:
    lead = pick(["I'm not sure I understood that.", "I didn't catch that."], c.turn)
    return (f"{lead} I can help you submit your package and tell you what is still needed. "
            f"{ask_next(c)}")


def refusal(c: Ctx) -> str:
    return f"{REFUSAL} {ask_next(c)}"


def facts_noted(keys: list[str]) -> str:
    return f"Thank you, I've noted the {joined([FACT_NAME[k] for k in keys])}."


def received(label: str, replaced: bool) -> str:
    name = DOCS[label]
    return f"I've updated your {name}." if replaced else f"Thank you, I have your {name}."


TOPICS = {"greeting": greeting, "help": help_, "missing": missing, "next": next_,
          "status": status, "thanks": thanks}
