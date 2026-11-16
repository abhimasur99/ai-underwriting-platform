"""Deterministic underwriting pipeline: Deal in, UnderwritingResult out. No model involved.

The Sprint 2 underwriter agent calls the same functions as tools and adds the model-written
narrative; this pipeline is what runs offline and what the tests pin to expected.json.
"""
from bridge.core import calc
from bridge.core.narrative import default_narrative
from bridge.core.reconcile import reconcile_all
from bridge.core.rules import RulesConfig, evaluate, load_rules
from bridge.core.schema import Deal, Reason, UnderwritingResult

_QUESTIONS = [
    ("RENT_ROLL_VS_T12_", "Explain the gap between the rent roll and the T-12 rental income."),
    ("SOURCES_VS_USES_", "Reconcile total sources to total uses."),
    ("UNIT_COUNT_MISMATCH", "Confirm the unit count against the rent roll."),
    ("REFI_CUSHION_", "What take-out sizing does the sponsor expect? Does it cover the payoff?"),
    ("EXIT_DSCR_", "Confirm the stabilized NOI that supports the exit DSCR."),
    ("IMPLIED_CAP_RATE_LOW", "Support the ARV: the implied cap rate looks aggressive."),
    ("LTC_", "Is the sponsor willing to add equity or reduce the loan?"),
    ("LTV_AS_IS_", "Is the sponsor willing to add equity or reduce the loan?"),
    ("LOAN_TO_ARV_", "Is the sponsor willing to add equity or reduce the loan?"),
    ("ASSET_TYPE_NOT_ALLOWED", "Confirm the asset type; it is outside the eligible set."),
    ("LOAN_SIZE_OUT_OF_RANGE", "Confirm the requested amount; it is outside the allowed range."),
]


def open_questions(reasons: list[Reason], flags) -> list[str]:
    out: list[str] = []

    def add(q: str) -> None:
        if q not in out:
            out.append(q)

    for reason in reasons:
        if reason.code == "LOW_CONFIDENCE_FIELD":
            add(f"Confirm {reason.source_fields[0]}: extraction confidence is below the "
                "flag level.")
            continue
        for prefix, question in _QUESTIONS:
            if reason.code == prefix or (prefix.endswith("_") and reason.code.startswith(prefix)):
                add(question)
                break
    for flag in flags:
        add(f"Resolve: {flag.message}")
    return out


def underwrite(deal: Deal, rules: RulesConfig | None = None) -> UnderwritingResult:
    rules = rules or load_rules()
    metrics = calc.compute_metrics(deal)
    commitment = deal.loan_request.loan_commitment.value
    noi, arv = deal.pro_forma.stabilized_noi.value, deal.valuation.arv.value
    exit_ = calc.exit_analysis(noi, arv, commitment, rules.takeout_params())
    stress = calc.stress_analysis(noi, arv, commitment, rules.takeout_params(),
                                  rules.stress_params())
    recon, recon_flags = reconcile_all(deal, rules)
    outcome = evaluate(deal, metrics, exit_, stress, recon, rules)
    flags = [*deal.flags, *recon_flags]
    result = UnderwritingResult(
        deal_id=deal.deal_id, deal_version=deal.version, rules_version=rules.version,
        call=outcome.call, reasons=outcome.reasons, metrics=metrics, exit=exit_, stress=stress,
        reconciliation=recon, rule_checks=outcome.checks, flags=flags,
        open_questions=open_questions(outcome.reasons, flags),
    )
    result.narrative = default_narrative(result)
    return result
