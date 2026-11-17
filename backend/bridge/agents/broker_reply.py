"""The draft reply to the broker that goes with an approval or a rejection.

Code writes the draft from the deal and the decision; a model may only rephrase it (live mode,
behind the same checks as the sponsor chat, see phrasing.py). Nothing here is ever sent: the
reviewer edits the text, marks it approved, and copies it into their own mail.

The draft is written for someone outside the firm, so it states no ratio, rate, limit or other
figure from the calculations. The reasons for a rejection are given as plain-language themes (a
decision is the reviewer's, and what to share beyond that is theirs to add). It makes no promise:
an approval is "move forward to the next step", never a commitment to lend.
"""
from bridge.agents.phrasing import BLANK
from bridge.core.schema import Deal, UnderwritingResult


class ReplyError(ValueError):
    """The reviewer's text cannot be accepted (empty, too long, or still has a placeholder)."""


MAX_LENGTH = 6000

# reason-code prefix -> the theme it belongs to, in the words a broker would expect, with no figure
THEMES = [
    ("ASSET_TYPE_NOT_ALLOWED", "The property type is outside what we finance in this program."),
    ("LOAN_SIZE_OUT_OF_RANGE", "The requested loan amount is outside the range for this program."),
    ("LTC_", "The requested leverage is above what the program allows against cost and value."),
    ("LTV_AS_IS_", "The requested leverage is above what the program allows against cost and "
                   "value."),
    ("LOAN_TO_ARV_", "The requested leverage is above what the program allows against cost and "
                     "value."),
    ("EXIT_DSCR_", "The projected take-out financing does not cover the bridge loan with enough "
                   "cushion."),
    ("REFI_CUSHION_", "The projected take-out financing does not cover the bridge loan with "
                      "enough cushion."),
    ("IMPLIED_CAP_RATE_LOW", "The after-repair value looks aggressive for the projected income."),
    ("RENT_ROLL_VS_T12_", "The rent roll and the trailing twelve months operating statement "
                          "do not reconcile."),
    ("SOURCES_VS_USES_", "The sources and uses of funds do not balance."),
    ("UNIT_COUNT_MISMATCH", "The stated unit count differs from the rent roll."),
]

SIGN_OFF = "Best regards,\n[Your name]\n[Your title]"


def _theme(code: str) -> str | None:
    for prefix, text in THEMES:
        if code == prefix or (prefix.endswith("_") and code.startswith(prefix)):
            return text
    return None


def themes(result: UnderwritingResult) -> list[str]:
    """The distinct themes behind the call, in the order the rules raised them."""
    out: list[str] = []
    for reason in result.reasons:
        text = _theme(reason.code)
        if text and text not in out:
            out.append(text)
    return out


def _opening(deal: Deal) -> str:
    return (f"Thank you for sending the package for {deal.property.address.value} "
            f"on behalf of {deal.sponsor.name.value}.")


def _approve(deal: Deal, result: UnderwritingResult) -> str:
    asks = list(result.open_questions)
    parts = [f"Subject: {deal.property.address.value}: next steps", "Hello,", _opening(deal),
             "We have completed our first review and would like to move this forward."]
    if asks:
        parts.append("To keep things moving, we have the following questions:\n"
                     + "\n".join(f"- {q}" for q in asks))
    else:
        parts.append("We have no further requests at this stage.")
    parts += ["This is a preliminary view based on the information you provided. It is not a "
              "commitment to lend; any terms remain subject to full underwriting, due diligence, "
              "third-party reports and our internal credit approval.", SIGN_OFF]
    return "\n\n".join(parts) + "\n"


def _reject(deal: Deal, result: UnderwritingResult) -> str:
    parts = [f"Subject: {deal.property.address.value}: our decision", "Hello,", _opening(deal),
             "After reviewing it, we are not able to move forward with this request at this time."]
    why = themes(result)
    if why:
        parts.append("The main considerations were:\n" + "\n".join(f"- {t}" for t in why))
    parts += ["If the structure or the information changes materially, you are welcome to send "
              "it again and we will take another look.",
              "We appreciate the opportunity to review it.", SIGN_OFF]
    return "\n\n".join(parts) + "\n"


def compose(deal: Deal, result: UnderwritingResult, decision: str) -> str:
    """The code-written draft for an `approve` or a `reject` decision."""
    if decision == "approve":
        return _approve(deal, result)
    if decision == "reject":
        return _reject(deal, result)
    raise ReplyError(f"no reply is drafted for {decision!r}")


def checked(text: str) -> str:
    """The reviewer's text, trimmed, or a ReplyError saying what to fix."""
    text = text.strip()
    if not text:
        raise ReplyError("the reply is empty")
    if len(text) > MAX_LENGTH:
        raise ReplyError(f"the reply is too long (at most {MAX_LENGTH:,} characters)")
    return text + "\n"


def placeholders(text: str) -> list[str]:
    return BLANK.findall(text)
