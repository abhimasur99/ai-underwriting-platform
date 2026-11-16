"""Loads config/rules.yaml and turns metrics into a call plus reason codes.

Every rule is evaluated and every reason collected (no early exit). Boundaries are strict: a
value exactly at a threshold does not trigger. The call is code-only: decline if any decline
reason, else watch if any watch reason, else screen. Thresholds are illustrative.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel

from bridge.core.calc import StressParams, TakeoutParams
from bridge.core.schema import (
    Deal,
    ExitAnalysis,
    Metrics,
    Reason,
    ReconciliationItem,
    RuleCheck,
)

EPS = 1e-9  # float noise must not push a value that is exactly at a threshold over it


def above(value: float, threshold: float) -> bool:
    return value - threshold > EPS


def below(value: float, threshold: float) -> bool:
    return threshold - value > EPS


DEFAULT_RULES_PATH = Path(__file__).resolve().parents[3] / "config" / "rules.yaml"


class _Band(BaseModel):
    watch_above: float
    decline_above: float


class _TakeoutCfg(BaseModel):
    rate: float
    min_dscr: float
    max_ltv: float
    min_debt_yield: float


class _ExitDscrCfg(BaseModel):
    watch_below: float
    decline_below: float


class _StressCfg(BaseModel):
    noi_haircut: float
    rate_bump_bps: float


class _CapRateCfg(BaseModel):
    watch_below: float


class _ExitCfg(BaseModel):
    takeout: _TakeoutCfg
    exit_fee_pct: float
    exit_dscr: _ExitDscrCfg
    stress: _StressCfg
    implied_cap_rate: _CapRateCfg


class _GapCfg(BaseModel):
    pass_within: float
    decline_above: float


class _ReconCfg(BaseModel):
    rent_roll_vs_t12: _GapCfg
    sources_vs_uses: _GapCfg
    unit_count_must_match: bool


class _LoanSize(BaseModel):
    min: float
    max: float


class _Eligibility(BaseModel):
    asset_types: list[str]
    loan_size_usd: _LoanSize


class _Confidence(BaseModel):
    flag_below: float
    key_fields: list[str]


class RulesConfig(BaseModel):
    version: str
    disclaimer: str
    eligibility: _Eligibility
    leverage: dict[str, _Band]
    exit: _ExitCfg
    reconciliation: _ReconCfg
    confidence: _Confidence

    def takeout_params(self) -> TakeoutParams:
        t = self.exit.takeout
        return TakeoutParams(rate=t.rate, min_dscr=t.min_dscr, max_ltv=t.max_ltv,
                             min_debt_yield=t.min_debt_yield, exit_fee_pct=self.exit.exit_fee_pct)

    def stress_params(self) -> StressParams:
        s = self.exit.stress
        return StressParams(noi_haircut=s.noi_haircut, rate_bump_bps=s.rate_bump_bps)


def load_rules(path: str | Path | None = None) -> RulesConfig:
    return RulesConfig.model_validate(yaml.safe_load(Path(path or DEFAULT_RULES_PATH).read_text()))


@dataclass
class RuleOutcome:
    call: str
    reasons: list[Reason]
    checks: list[RuleCheck]


LEVERAGE_FIELDS = {
    "ltc": ("LTC", "Loan to cost", ["loan_commitment", "total_cost"]),
    "ltv_as_is": ("LTV_AS_IS", "Loan to value (as-is)", ["initial_advance", "as_is_value"]),
    "loan_to_arv": ("LOAN_TO_ARV", "Loan to ARV", ["loan_commitment", "arv"]),
}
RECON_SOURCE_FIELDS = {
    "rent_roll_vs_t12": ["rent_roll", "t12"],
    "sources_vs_uses": ["sources", "uses"],
    "unit_count": ["unit_count", "rent_roll"],
}


def evaluate(deal: Deal, metrics: Metrics, exit_: ExitAnalysis, stress: ExitAnalysis,
             reconciliation: list[ReconciliationItem], rules: RulesConfig) -> RuleOutcome:
    reasons: list[Reason] = []
    checks: list[RuleCheck] = []

    def reason(code, severity, value, threshold, fields):
        reasons.append(Reason(code=code, severity=severity, value=value, threshold=threshold,
                              source_fields=fields))

    def check(metric, label, value, watch, decline, direction, status):
        checks.append(RuleCheck(metric=metric, label=label, value=value, watch_threshold=watch,
                                decline_threshold=decline, direction=direction, status=status))

    # eligibility
    asset = deal.property.asset_type.value
    if asset not in rules.eligibility.asset_types:
        reason("ASSET_TYPE_NOT_ALLOWED", "decline", None, None, ["asset_type"])
    size = rules.eligibility.loan_size_usd
    commitment = deal.loan_request.loan_commitment.value
    if below(commitment, size.min):
        reason("LOAN_SIZE_OUT_OF_RANGE", "decline", commitment, size.min, ["loan_commitment"])
    elif above(commitment, size.max):
        reason("LOAN_SIZE_OUT_OF_RANGE", "decline", commitment, size.max, ["loan_commitment"])

    # leverage (higher is worse)
    for key, (code, label, fields) in LEVERAGE_FIELDS.items():
        band, value = rules.leverage[key], getattr(metrics, key)
        if above(value, band.decline_above):
            reason(f"{code}_DECLINE", "decline", value, band.decline_above, fields)
            status = "decline"
        elif above(value, band.watch_above):
            reason(f"{code}_WATCH", "watch", value, band.watch_above, fields)
            status = "watch"
        else:
            status = "pass"
        check(key, label, value, band.watch_above, band.decline_above, "above", status)

    # exit DSCR (lower is worse)
    t = rules.exit.exit_dscr
    dscr_fields = ["stabilized_noi", "loan_commitment"]
    if below(exit_.exit_dscr, t.decline_below):
        reason("EXIT_DSCR_DECLINE", "decline", exit_.exit_dscr, t.decline_below, dscr_fields)
        status = "decline"
    elif below(exit_.exit_dscr, t.watch_below):
        reason("EXIT_DSCR_WATCH", "watch", exit_.exit_dscr, t.watch_below, dscr_fields)
        status = "watch"
    else:
        status = "pass"
    check("exit_dscr", "Exit DSCR", exit_.exit_dscr, t.watch_below, t.decline_below, "below",
          status)

    # refi cushion
    cushion_fields = ["stabilized_noi", "arv", "loan_commitment"]
    if below(exit_.refi_cushion, 0):
        reason("REFI_CUSHION_NEGATIVE_BASE", "decline", exit_.refi_cushion, 0, cushion_fields)
        check("refi_cushion", "Refi cushion (base)", exit_.refi_cushion, None, 0, "below",
              "decline")
    else:
        check("refi_cushion", "Refi cushion (base)", exit_.refi_cushion, None, 0, "below", "pass")
        if below(stress.refi_cushion, 0):
            reason("REFI_CUSHION_NEGATIVE_STRESS", "watch", stress.refi_cushion, 0, cushion_fields)
    check("refi_cushion_stress", "Refi cushion (stress)", stress.refi_cushion, 0, None, "below",
          "watch" if below(stress.refi_cushion, 0) else "pass")

    # implied cap rate
    cap = rules.exit.implied_cap_rate.watch_below
    low_cap = below(metrics.implied_cap_rate, cap)
    if low_cap:
        reason("IMPLIED_CAP_RATE_LOW", "watch", metrics.implied_cap_rate, cap,
               ["stabilized_noi", "arv"])
    check("implied_cap_rate", "Implied cap rate", metrics.implied_cap_rate, cap, None, "below",
          "watch" if low_cap else "pass")

    # reconciliation
    cfg = {"rent_roll_vs_t12": ("RENT_ROLL_VS_T12", rules.reconciliation.rent_roll_vs_t12,
                                "Rent roll vs T-12"),
           "sources_vs_uses": ("SOURCES_VS_USES", rules.reconciliation.sources_vs_uses,
                               "Sources vs uses")}
    by_name = {item.name: item for item in reconciliation}
    for name, (code, gap_cfg, label) in cfg.items():
        item = by_name[name]
        if item.status == "decline":
            reason(f"{code}_DECLINE", "decline", item.gap, gap_cfg.decline_above,
                   RECON_SOURCE_FIELDS[name])
        elif item.status == "watch":
            reason(f"{code}_WATCH", "watch", item.gap, gap_cfg.pass_within,
                   RECON_SOURCE_FIELDS[name])
        check(name, label, item.gap, gap_cfg.pass_within, gap_cfg.decline_above, "above",
              item.status)
    units = by_name["unit_count"]
    if rules.reconciliation.unit_count_must_match and units.status != "pass":
        reason("UNIT_COUNT_MISMATCH", "watch", units.a, units.b, RECON_SOURCE_FIELDS["unit_count"])

    # low-confidence key fields, one reason per field
    for field in rules.confidence.key_fields:
        conf = deal.key_field(field).confidence
        if below(conf, rules.confidence.flag_below):
            reason("LOW_CONFIDENCE_FIELD", "watch", conf, rules.confidence.flag_below, [field])

    if any(r.severity == "decline" for r in reasons):
        call = "decline"
    elif reasons:
        call = "watch"
    else:
        call = "screen"
    return RuleOutcome(call=call, reasons=reasons, checks=checks)
