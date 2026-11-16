"""Build `Sourced` values and enforce the quote rule: a quote that is not in the source text
caps confidence at 0.5 (docs/data-contracts.md)."""
from bridge.core.schema import Source, Sourced

DOC_CONFIDENCE = 0.98       # deterministic read of a labeled line or table row
DERIVED_CONFIDENCE = 1.0    # computed by code from other sourced values
UNVERIFIED_CAP = 0.5


def sourced_from_quote[T](value: T, doc: str, text: str, locator: str, quote: str,
                          confidence: float = DOC_CONFIDENCE) -> Sourced[T]:
    if quote not in text:
        confidence = min(confidence, UNVERIFIED_CAP)
    return Sourced[type(value)](
        value=value,
        source=Source(kind="document", doc=doc, locator=locator, quote=quote),
        confidence=confidence,
    )


def derived[T](value: T, formula: str, doc: str | None = None,
               locator: str | None = None) -> Sourced[T]:
    return Sourced[type(value)](
        value=value,
        source=Source(kind="derived", formula=formula, doc=doc, locator=locator),
        confidence=DERIVED_CONFIDENCE,
    )
