"""Internal chief chat. The runner classifies a reviewer message (question, data_edit,
narrative_edit, override, action); this module answers from tool output only and proposes patches.
No patch is applied here: the reviewer's Confirm click (API) calls Chief.confirm_patch."""
from bridge.agents import patches as patching
from bridge.agents.chief import Chief
from bridge.agents.phrasing import Phraser
from bridge.agents.recorder import Recorder
from bridge.agents.runner import AgentRunner
from bridge.core import calc
from bridge.core import format as f
from bridge.core.diff import VersionDiff
from bridge.core.placeholders import NarrativeError
from bridge.core.schema import Deal, UnderwritingResult

FIELD_PATHS = {
    "arv": "valuation.arv", "as_is_value": "valuation.as_is_value",
    "initial_advance": "loan_request.initial_advance",
    "loan_commitment": "loan_request.loan_commitment", "note_rate": "loan_request.note_rate",
    "stabilized_noi": "pro_forma.stabilized_noi",
}
# metric -> (label, formatter, formula key in calc.FORMULAS, tool that produced it)
METRICS = {
    "ltc": ("Loan to cost", f.pct, "ltc", "calc.ltc"),
    "ltv_as_is": ("Loan to value (as-is)", f.pct, "ltv_as_is", "calc.ltv_as_is"),
    "loan_to_arv": ("Loan to ARV", f.pct, "loan_to_arv", "calc.loan_to_arv"),
    "dscr_in_place": ("In-place DSCR", f.mult, "dscr_in_place", "calc.dscr_in_place"),
    "debt_yield_stabilized": ("Stabilized debt yield", f.pct, "debt_yield_stabilized",
                              "calc.debt_yield"),
    "implied_cap_rate": ("Implied cap rate", f.pct, "implied_cap_rate", "calc.implied_cap_rate"),
    "total_cost": ("Total cost", f.usd, "total_cost", "calc.total_cost"),
    "exit_dscr": ("Exit DSCR", f.mult, "exit_dscr", "exit.analyze"),
    "takeout_max": ("Take-out maximum", f.usd, "takeout_max", "exit.analyze"),
    "refi_cushion": ("Refi cushion", f.usd, "refi_cushion", "exit.analyze"),
    "stress_refi_cushion": ("Refi cushion under stress", f.usd, "refi_cushion", "exit.stress"),
    "rent_roll_vs_t12_gap": ("Rent roll vs T-12 gap", f.pct, "reconciliation_gap", "reconcile.all"),
    "sources_vs_uses_gap": ("Sources vs uses gap", f.pct, "reconciliation_gap", "reconcile.all"),
}
INPUT_FMT = {"note_rate": f.pct}
SOURCED_INPUTS = {"loan_commitment", "initial_advance", "as_is_value", "arv", "note_rate",
                  "stabilized_noi"}
CAPABILITIES = ("I can answer questions about this deal's calculations, exceptions and sources, "
                "explain why the call is what it is, show what changed between versions, and "
                "propose edits for you to confirm.")
HELP = f"{CAPABILITIES} Nothing changes until you confirm. What would you like to know?"
GREETING = "Hello. How can I help with this deal?"
THANKS = "You're welcome. Let me know if there is anything else you would like to check."
OUTSIDE = f"That is outside what I can help with here. {CAPABILITIES}"
ACTION_BUTTON = {"approve": "the Approve button", "reject": "the Reject button",
                 "request_info": "the Request info button",
                 "send_back": "the Re-run option under More"}

# The follow-up questions offered after each kind of answer.
STARTERS = ["Summarize this deal", "What are the exceptions?", "Why is the call what it is?",
            "What changed in this version?"]
FOLLOW_UPS = {
    "summary": ["What are the exceptions?", "Why is the call what it is?",
                "What does the stress case show?"],
    "reasons": ["What are the exceptions?", "What does the stress case show?",
                "What changed in this version?"],
    "exceptions": ["Summarize this deal", "Why is the call what it is?"],
    "changes": ["Summarize this deal", "What does the stress case show?"],
    "metric": ["Why is the call what it is?", "What does the stress case show?",
               "What are the exceptions?"],
    "stress": ["Why is the call what it is?", "What are the exceptions?"],
}


def explain_exceptions(result) -> str:
    """The exceptions (flags) and the questions for the sponsor, in the words the page uses."""
    if not result.flags and not result.open_questions:
        return "There are no exceptions and no open questions for the sponsor."
    parts = []
    if result.flags:
        n = len(result.flags)
        lines = "\n".join(f"- {x.code}: {x.message}" for x in result.flags)
        parts.append(f"There {'is' if n == 1 else 'are'} {n} exception{'' if n == 1 else 's'}:\n"
                     f"{lines}")
    else:
        parts.append("There are no exceptions.")
    if result.open_questions:
        parts.append("Questions for the sponsor:\n" + "\n".join(f"- {q}" for q in
                                                                  result.open_questions))
    return "\n\n".join(parts)


def _value(path: str, text: str) -> str:
    try:
        number = float(text)
    except ValueError:
        return text
    return f.pct(number) if path.endswith("note_rate") else f.usd(number)


def explain_changes(diff: VersionDiff) -> str:
    """What the latest version changed, in plain words, from the comparison."""
    if diff.from_version == diff.to_version:
        return "This is the first version of the deal, so there is nothing to compare yet."
    parts = []
    for item in diff.inputs:
        if item.path == "documents":
            parts.append(f"Version {diff.to_version} was made by reading the documents again from "
                         "the new files.")
        else:
            why = f" (reason: {item.reason})" if item.reason else ""
            parts.append(f"Version {diff.to_version} changed {item.path}: "
                         f"{_value(item.path, item.old)} to {_value(item.path, item.new)}{why}.")
    shown = {"pct": f.pct, "usd": f.usd, "mult": f.mult}
    if diff.metrics:
        lines = "\n".join(f"- {m.label}: {shown[m.kind](m.before)} to {shown[m.kind](m.after)}"
                          for m in diff.metrics)
        parts.append(f"As a result:\n{lines}")
    else:
        parts.append("No calculation moved.")
    if diff.call_before != diff.call_after:
        text = (f"The call moved from {diff.call_before.capitalize()} to "
                f"{diff.call_after.capitalize()}.")
        if diff.reasons_added:
            text += f" New reasons: {', '.join(diff.reasons_added)}."
        if diff.reasons_removed:
            text += f" No longer applies: {', '.join(diff.reasons_removed)}."
        parts.append(text)
    else:
        parts.append(f"The call is unchanged ({diff.call_after.capitalize()}).")
    return "\n\n".join(parts)


def _metric_value(r: UnderwritingResult, name: str):
    if name == "exit_dscr":
        return r.exit.exit_dscr
    if name == "takeout_max":
        return r.exit.takeout_max
    if name == "refi_cushion":
        return r.exit.refi_cushion
    if name == "stress_refi_cushion":
        return r.stress.refi_cushion
    if name.endswith("_gap"):
        key = "rent_roll_vs_t12" if name.startswith("rent") else "sources_vs_uses"
        return next(i.gap for i in r.reconciliation if i.name == key)
    return getattr(r.metrics, name)


class ChiefChat:
    def __init__(self, chief: Chief, runner: AgentRunner):
        self.chief, self.runner = chief, runner
        self.phraser = Phraser(runner)

    # ---- tools (code; the only source of numbers in replies)
    def get_metric(self, deal_id: str, name: str) -> str:
        deal, result, _ = self.chief.latest(deal_id)
        label, fmt, formula_key, tool = METRICS[name]
        text = f"{label} is {fmt(_metric_value(result, name))}. "
        text += f"Formula: {calc.FORMULAS[formula_key]}."
        if name.endswith("_gap"):
            item = next(i for i in result.reconciliation
                        if i.name == ("rent_roll_vs_t12" if name.startswith("rent")
                                      else "sources_vs_uses"))
            text += f" Inputs: a = {f.usd(item.a)}; b = {f.usd(item.b)} ({item.detail})."
            return text
        call = self._last_call(deal_id, deal.version, tool)
        if call:
            parts = []
            for key, value in call["inputs"].items():
                if isinstance(value, list):
                    parts.append(f"{key} = {len(value)} rows totalling {f.usd(sum(value))}")
                else:
                    parts.append(f"{key} = {INPUT_FMT.get(key, f.usd)(value)}")
            text += " Inputs: " + "; ".join(parts) + "."
            sources = [self._source(deal, k) for k in call["inputs"] if k in SOURCED_INPUTS]
            if sources:
                text += " Sources: " + "; ".join(sources) + "."
        return text

    def _last_call(self, deal_id: str, version: int, tool: str) -> dict | None:
        events = [e for e in self.chief.store.events(deal_id)
                  if e.type == "tool.called" and e.payload.get("tool") == tool
                  and e.deal_version == version]
        return events[-1].payload if events else None

    @staticmethod
    def _source(deal: Deal, key: str) -> str:
        s = deal.key_field(key).source
        if s.kind == "override":
            return f"{key}: reviewer override ({s.reason})"
        return f"{key}: {s.doc} {s.locator}"

    def explain_reasons(self, deal_id: str) -> str:
        _, result, _ = self.chief.latest(deal_id)
        if not result.reasons:
            return f"The call is {result.call.upper()}. No rule was triggered."
        lines = [f"- {f.describe_reason(r)} ({r.code}; inputs: {', '.join(r.source_fields)})"
                 for r in result.reasons]
        return f"The call is {result.call.upper()} because:\n" + "\n".join(lines)

    def get_deal_summary(self, deal_id: str) -> str:
        deal, result, check = self.chief.latest(deal_id)
        commitment = f.usd(deal.loan_request.loan_commitment.value)
        ex = result.exit
        return (
            f"{deal.name} ({deal.deal_id}, version {deal.version}). Call: {result.call.upper()}. "
            f"Loan commitment {commitment} on a total cost of {f.usd(result.metrics.total_cost)}; "
            f"take-out maximum {f.usd(ex.takeout_max)}, refi cushion {f.usd(ex.refi_cushion)}, "
            f"exit DSCR {f.mult(ex.exit_dscr)}. Checker: {check.status if check else 'not run'}. "
            f"{len(result.reasons)} reason(s), {len(result.flags)} flag(s).")

    # ---- the conversation, kept in the event log
    def _log(self, deal_id: str, actor: str, type_: str, text: str) -> None:
        version = self.chief.latest(deal_id)[0].version
        Recorder(self.chief.store, deal_id, version).event(actor, type_, text[:120], {"text": text})

    def history(self, deal_id: str) -> list[tuple[str, str]]:
        roles = {"chat.reviewer": "reviewer", "chat.chief": "assistant"}
        return [(roles[e.type], e.payload.get("text", ""))
                for e in self.chief.store.events(deal_id) if e.type in roles]

    def _answer(self, deal_id: str, turn) -> tuple[str, list[str]]:
        """The code-composed reply to a question, and the follow-ups to offer."""
        if turn.metric:
            text = self.get_metric(deal_id, turn.metric)
            return text, FOLLOW_UPS["stress" if "stress" in turn.metric else "metric"]
        topic = turn.topic
        if topic == "reasons":
            return self.explain_reasons(deal_id), FOLLOW_UPS["reasons"]
        if topic == "summary":
            return self.get_deal_summary(deal_id), FOLLOW_UPS["summary"]
        if topic == "exceptions":
            return explain_exceptions(self.chief.latest(deal_id)[1]), FOLLOW_UPS["exceptions"]
        if topic == "changes":
            return explain_changes(self.chief.version_diff(deal_id)), FOLLOW_UPS["changes"]
        if topic == "greeting":
            return GREETING, STARTERS
        if topic == "thanks":
            return THANKS, []
        if topic == "help":
            return HELP, STARTERS
        return OUTSIDE, STARTERS

    # ---- one reviewer message
    def handle(self, deal_id: str, message: str) -> dict:
        self._log(deal_id, "reviewer", "chat.reviewer", message)
        past = self.history(deal_id)[:-1]
        turn = self.runner.interpret_chief(message)
        out = {"intent": turn.intent, "patch": None, "suggestions": []}
        if turn.intent == "question":
            reply, out["suggestions"] = self._answer(deal_id, turn)
            out["reply"] = self.phraser.reviewer(reply, past)
        elif turn.intent == "action":
            button = ACTION_BUTTON[turn.action]
            out["reply"] = (f"I can't record that decision for you. Please use {button}: the call "
                            "is a recommendation, and the decision is yours.")
        else:
            out.update(self._propose(deal_id, turn))      # a proposed edit is shown as it is
        self._log(deal_id, "chief", "chat.chief", out["reply"])
        return out

    def _propose(self, deal_id: str, turn) -> dict:
        req, deal = turn.patch, self.chief.store.get_deal(deal_id)
        try:
            if turn.intent == "data_edit":
                if req.field == "rent":
                    idx = next((i for i, u in enumerate(deal.rent_roll.units)
                                if u.unit.upper() == (req.unit or "").upper()), None)
                    if idx is None:
                        return {"reply": f"I couldn't find unit {req.unit} on the rent roll."}
                    path = f"rent_roll.units[{idx}].monthly_rent"
                else:
                    path = FIELD_PATHS[req.field]
                patch = self.chief.propose_patch(deal_id, "data", path, req.value, req.reason)
                fmt = f.pct if req.field == "note_rate" else f.usd
                reply = (f"I can change {path} from {fmt(patch.old)} to {fmt(patch.new)} "
                         f"(reason: {req.reason}). That creates deal version {deal.version + 1} "
                         "and re-runs underwriting and the checker. Nothing changes until you "
                         "confirm.")
            elif turn.intent in ("narrative_edit", "override") and not (req.text or "").strip():
                what = "the new text for that section" if turn.intent == "narrative_edit" \
                    else "the judgment you want recorded"
                return {"reply": f"I need {what}. For an override, say it as: "
                                 "override <judgment> because <reason>."}
            elif turn.intent == "narrative_edit":
                patch = self.chief.propose_patch(deal_id, "narrative",
                                                 f"narrative.{req.section}", req.text, "")
                reply = (f"I can replace the {req.section} text with: \"{req.text}\". Confirming "
                         "re-renders the memo only; numbers stay as computed.")
            else:  # override
                if not req.reason.strip():
                    return {"reply": "An override needs a reason. Why do you want to override? "
                                     "Say it as: override <judgment> because <reason>."}
                patch = self.chief.propose_patch(deal_id, "override", "judgment", req.text,
                                                 req.reason)
                reply = (f"I can record your judgment: \"{req.text}\" (reason: {req.reason}). It "
                         "appears on the memo; no numbers change. Confirm to record it.")
        except NarrativeError:
            return {"reply": "Narrative text can't contain digits outside placeholders such as "
                             "{{metrics.ltc}}. Please rephrase using placeholders."}
        except (patching.PatchError, RuntimeError) as exc:
            return {"reply": str(exc)}
        return {"reply": reply, "patch": patch.model_dump()}

