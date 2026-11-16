"""Typed contracts for the deterministic core. See docs/data-contracts.md.

Every extracted fact is a `Sourced[T]` (value, source, confidence). Fields that are required for
underwriting have no default, so a missing field fails loudly instead of being filled in.
Fields typed `... | None` are informational only and never feed a metric or a rule.
"""
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Source(BaseModel):
    kind: Literal["document", "derived", "chat", "override"]
    doc: str | None = None
    locator: str | None = None
    quote: str | None = None
    formula: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _kind_requirements(self) -> "Source":
        if self.kind == "document" and not (self.doc and self.locator):
            raise ValueError("document source needs doc and locator")
        if self.kind == "derived" and not self.formula:
            raise ValueError("derived source needs formula")
        if self.kind == "override" and not self.reason:
            raise ValueError("override source needs reason")
        return self


class Sourced[T](BaseModel):
    value: T
    source: Source
    confidence: float = Field(ge=0.0, le=1.0)


class Flag(BaseModel):
    code: str
    message: str
    field: str | None = None


class AmountRow(BaseModel):
    name: str
    amount: float


class LineItem(BaseModel):
    item: str
    amount: float


class Property(BaseModel):
    address: Sourced[str]
    asset_type: Sourced[str]
    unit_count: Sourced[int]
    occupied_units: Sourced[int]
    year_built: Sourced[int] | None = None


class LoanRequest(BaseModel):
    loan_commitment: Sourced[float]
    initial_advance: Sourced[float]
    note_rate: Sourced[float]
    term_months: Sourced[int] | None = None
    points: Sourced[float] | None = None


class Valuation(BaseModel):
    as_is_value: Sourced[float]
    arv: Sourced[float]


class Purchase(BaseModel):
    purchase_price: Sourced[float]
    deposit: Sourced[float] | None = None
    closing_date: Sourced[str] | None = None


class Renovation(BaseModel):
    renovation_budget: Sourced[float]
    line_items: list[LineItem]


class SourcesUses(BaseModel):
    sources: list[AmountRow]
    uses: list[AmountRow]
    stated_total_sources: Sourced[float]
    stated_total_uses: Sourced[float]


class ProForma(BaseModel):
    stabilized_noi: Sourced[float]
    gpr: Sourced[float] | None = None
    vacancy_pct: Sourced[float] | None = None
    other_income: Sourced[float] | None = None
    opex: Sourced[float] | None = None


class RentRollUnit(BaseModel):
    unit: str
    unit_type: str
    status: Literal["occupied", "vacant"]
    monthly_rent: float
    sqft: float | None = None
    tenant: str | None = None
    lease_start: str | None = None
    lease_end: str | None = None


class RentRoll(BaseModel):
    units: list[RentRollUnit]
    annual_occupied_rent: Sourced[float]


class T12Line(BaseModel):
    line_item: str
    category: Literal["income", "expense"]
    months: list[float]
    total: float


class T12(BaseModel):
    lines: list[T12Line]
    rental_income: Sourced[float]
    total_income: Sourced[float]
    total_expenses: Sourced[float]
    in_place_noi: Sourced[float]


class Sponsor(BaseModel):
    name: Sourced[str]


class Deal(BaseModel):
    deal_id: str
    name: str
    version: int = 1
    property: Property
    loan_request: LoanRequest
    valuation: Valuation
    purchase: Purchase
    renovation: Renovation
    sources_uses: SourcesUses
    pro_forma: ProForma
    rent_roll: RentRoll
    t12: T12
    sponsor: Sponsor
    flags: list[Flag] = []

    def key_field(self, name: str) -> Sourced:
        """Look up one of the rules.yaml `confidence.key_fields` by name."""
        paths = {
            "purchase_price": self.purchase.purchase_price,
            "renovation_budget": self.renovation.renovation_budget,
            "loan_commitment": self.loan_request.loan_commitment,
            "initial_advance": self.loan_request.initial_advance,
            "as_is_value": self.valuation.as_is_value,
            "arv": self.valuation.arv,
            "stabilized_noi": self.pro_forma.stabilized_noi,
            "unit_count": self.property.unit_count,
            "note_rate": self.loan_request.note_rate,
        }
        if name not in paths:
            raise KeyError(f"unknown key field: {name}")
        return paths[name]


class Metrics(BaseModel):
    total_cost: float
    ltc: float
    ltv_as_is: float
    loan_to_arv: float
    dscr_in_place: float
    debt_yield_stabilized: float
    implied_cap_rate: float


class TakeoutCaps(BaseModel):
    dscr: float
    ltv: float
    debt_yield: float


class ExitAnalysis(BaseModel):
    payoff: float
    noi: float
    rate: float
    caps: TakeoutCaps
    binding: Literal["dscr", "ltv", "debt_yield"]
    takeout_max: float
    refi_cushion: float
    exit_dscr: float


class ReconciliationItem(BaseModel):
    name: str
    status: Literal["pass", "watch", "decline"]
    a: float | None = None
    b: float | None = None
    gap: float | None = None
    detail: str | None = None


class Reason(BaseModel):
    code: str
    severity: Literal["watch", "decline"]
    value: float | None = None
    threshold: float | None = None
    source_fields: list[str] = []


class RuleCheck(BaseModel):
    """One row of the memo metrics table: value, thresholds, and status."""
    metric: str
    label: str
    value: float
    watch_threshold: float | None = None
    decline_threshold: float | None = None
    direction: Literal["above", "below"]
    status: Literal["pass", "watch", "decline"]


class UnderwritingResult(BaseModel):
    deal_id: str
    deal_version: int
    rules_version: str
    call: Literal["screen", "watch", "decline"]
    reasons: list[Reason]
    metrics: Metrics
    exit: ExitAnalysis
    stress: ExitAnalysis
    reconciliation: list[ReconciliationItem]
    rule_checks: list[RuleCheck] = []
    flags: list[Flag] = []
    open_questions: list[str] = []
    narrative: dict[str, str] = {}
    artifacts: dict[str, str] = {}
