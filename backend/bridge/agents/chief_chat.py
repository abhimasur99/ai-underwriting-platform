"""Internal chief chat. The runner classifies a reviewer message (question, data_edit,
narrative_edit, override, action); this module answers from tool output only and proposes patches.
No patch is applied here: the reviewer's Confirm click (API) calls Chief.confirm_patch."""
from bridge.agents import patches as patching
from bridge.agents.chief import Chief
from bridge.agents.runner import AgentRunner
from bridge.core import calc
from bridge.core import format as f
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
OUTSIDE = ("That is outside this prototype. I can answer questions about this deal's metrics, "
           "reasons and sources, and propose edits you confirm.")


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

    # ---- one reviewer message
    def handle(self, deal_id: str, message: str) -> dict:
        turn = self.runner.interpret_chief(message)
        out = {"intent": turn.intent, "patch": None}
        if turn.intent == "question":
            if turn.metric:
                out["reply"] = self.get_metric(deal_id, turn.metric)
            elif turn.topic == "reasons":
                out["reply"] = self.explain_reasons(deal_id)
            elif turn.topic == "summary":
                out["reply"] = self.get_deal_summary(deal_id)
            else:
                out["reply"] = OUTSIDE
        elif turn.intent == "action":
            verb = {"approve": "Approve", "reject": "Reject", "send_back": "Send back"}[turn.action]
            out["reply"] = (f"I can't record the decision. Use the {verb} button; the AI call is "
                            "a recommendation and you decide.")
        else:
            out.update(self._propose(deal_id, turn))
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

