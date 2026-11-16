"""Number and reason formatting shared by placeholders, the memo and the workbook."""
from bridge.core.schema import Reason

BINDING_LABEL = {"dscr": "DSCR", "ltv": "LTV", "debt_yield": "debt yield"}


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def usd(value: float) -> str:
    rounded = round(value)
    return f"-${abs(rounded):,}" if rounded < 0 else f"${rounded:,}"


def mult(value: float) -> str:
    return f"{value:.2f}x"


# reason-code prefix -> (plain-language text, value formatter)
_REASONS = [
    ("ASSET_TYPE_NOT_ALLOWED", "Asset type is not eligible", str),
    ("LOAN_SIZE_OUT_OF_RANGE", "Loan size outside the allowed range", usd),
    ("LTC_", "Loan to cost", pct),
    ("LTV_AS_IS_", "Loan to value (as-is)", pct),
    ("LOAN_TO_ARV_", "Loan to ARV", pct),
    ("EXIT_DSCR_", "Exit DSCR", mult),
    ("REFI_CUSHION_NEGATIVE_BASE", "Take-out does not cover the bridge payoff", usd),
    ("REFI_CUSHION_NEGATIVE_STRESS", "Take-out does not cover the payoff under stress", usd),
    ("IMPLIED_CAP_RATE_LOW", "Implied cap rate is low (aggressive ARV)", pct),
    ("RENT_ROLL_VS_T12_", "Rent roll and T-12 income disagree", pct),
    ("SOURCES_VS_USES_", "Sources and uses do not balance", pct),
    ("UNIT_COUNT_MISMATCH", "Stated unit count differs from the rent roll", lambda v: f"{v:g}"),
    ("LOW_CONFIDENCE_FIELD", "Low-confidence extracted field", lambda v: f"{v:.2f}"),
]


def describe_reason(reason: Reason) -> str:
    """One readable line: what tripped, the value, and the threshold."""
    for prefix, text, fmt in _REASONS:
        if reason.code == prefix or (prefix.endswith("_") and reason.code.startswith(prefix)):
            if reason.code == "LOW_CONFIDENCE_FIELD":
                return f"{text}: {reason.source_fields[0]} ({fmt(reason.value)} vs " \
                       f"{fmt(reason.threshold)} minimum)"
            if reason.value is None or reason.threshold is None:
                return text
            return f"{text}: {fmt(reason.value)} vs {fmt(reason.threshold)} limit"
    return reason.code
