"""Checklist status from document labels and facts. Code only; a model never decides this."""
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel

from bridge.core.schema import Deal

DEFAULT_CHECKLIST_PATH = Path(__file__).resolve().parents[3] / "config" / "checklist.yaml"


class Checklist(BaseModel):
    required_documents: list[str]
    required_facts: list[str]


class ChecklistStatus(BaseModel):
    required: list[str]
    received: list[str]
    missing: list[str]
    ready: bool
    facts_missing: list[str]


def load_checklist(path: str | Path | None = None) -> Checklist:
    raw = yaml.safe_load(Path(path or DEFAULT_CHECKLIST_PATH).read_text())
    return Checklist(required_documents=[d["type"] for d in raw["required_documents"]],
                     required_facts=list(raw["required_facts"]))


def status(labels: Iterable[str], facts: Mapping[str, object],
           checklist: Checklist | None = None) -> ChecklistStatus:
    cl = checklist or load_checklist()
    have = set(labels)
    received = [d for d in cl.required_documents if d in have]
    missing = [d for d in cl.required_documents if d not in have]
    facts_missing = [f for f in cl.required_facts if facts.get(f) in (None, "")]
    return ChecklistStatus(required=list(cl.required_documents), received=received,
                           missing=missing, ready=not missing and not facts_missing,
                           facts_missing=facts_missing)


def facts_from_deal(deal: Deal) -> dict[str, object]:
    """Facts that extraction provided, keyed like `required_facts` in the checklist."""
    return {
        "property_address": deal.property.address.value,
        "asset_type": deal.property.asset_type.value,
        "unit_count": deal.property.unit_count.value,
        "loan_amount_requested": deal.loan_request.loan_commitment.value,
        "purchase_price": deal.purchase.purchase_price.value,
        "renovation_budget": deal.renovation.renovation_budget.value,
        "sponsor_name": deal.sponsor.name.value,
    }
