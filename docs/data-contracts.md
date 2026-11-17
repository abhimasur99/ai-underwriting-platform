# Data contracts

All JSON, validated by Pydantic models in `backend/bridge/core/schema.py`. Examples use the Bronx deal. `S` below means a `Sourced` field.

## Sourced field
```json
{"value": 8000000,
 "source": {"kind": "document", "doc": "purchase_contract.md", "locator": "line 6", "quote": "Purchase price: $8,000,000"},
 "confidence": 0.98}
```
Source kinds: `document` (file plus locator and quote), `derived` (computed by code, with `formula`), `chat` (recorded fact), `override` (reviewer change, with reason). A quoted string must appear in the source text or confidence is capped at 0.5. For PDF and Word sources the locator's line number counts lines of the text the reader extracts (the Files tab shows that text), not printed lines on a page. Tables may be CSV, XLSX or a PDF with a text layer. A field a model read in live mode has confidence 0.75, its quote is the extracted line, and the deal carries a `MODEL_ASSISTED_EXTRACTION` flag naming the fields.

## Deal record (abridged)
```json
{"deal_id": "D-0042", "version": 1, "state": "EXTRACTED",
 "property": {"address": "S", "asset_type": "S", "unit_count": "S", "occupied_units": "S", "year_built": "S"},
 "loan_request": {"loan_commitment": "S", "initial_advance": "S", "term_months": "S", "note_rate": "S", "points": "S"},
 "valuation": {"as_is_value": "S", "arv": "S"},
 "purchase": {"purchase_price": "S", "deposit": "S", "closing_date": "S"},
 "renovation": {"renovation_budget": "S", "line_items": [{"item": "Roof and facade", "amount": 150000}]},
 "sources_uses": {"sources": [{"name": "Senior bridge loan", "amount": 6500000}], "uses": [{"name": "Purchase price", "amount": 8000000}],
                  "stated_total_sources": "S", "stated_total_uses": "S"},
 "pro_forma": {"gpr": "S", "vacancy_pct": "S", "other_income": "S", "opex": "S", "stabilized_noi": "S"},
 "rent_roll": {"units": [{"unit": "101", "unit_type": "studio", "status": "occupied", "monthly_rent": 1300}], "annual_occupied_rent": "S"},
 "t12": {"lines": [{"line_item": "Gross rental income", "category": "income", "months": [], "total": 715104}], "rental_income": "S", "total_income": "S", "total_expenses": "S", "in_place_noi": "S"},
 "sponsor": {"name": "S"}}
```

## Handoff envelope (chief to agent)
```json
{"handoff_id": "h-0007", "from": "chief", "to": "underwriter", "deal_id": "D-0042", "deal_version": 1,
 "task": "size_and_compute", "attempt": 1, "inputs_ref": "deal_record@v1", "ts": "2026-11-16T15:04:05Z"}
```
Return envelope: same ids plus `"status": "ok|needs_input|error"`, `"outputs_ref"`, `"summary"`, `"duration_ms"`.

## Tool call record
```json
{"call_id": "t-0031", "agent": "underwriter", "tool": "calc.ltc",
 "inputs": {"loan_commitment": 6500000, "total_cost": 9200000},
 "formula": "loan_commitment / total_cost", "output": 0.706522, "ts": "2026-11-16T15:04:07Z"}
```

## Underwriting result (also the decision package)
```json
{"deal_id": "D-0042", "deal_version": 1, "rules_version": "0.1-illustrative",
 "call": "screen",
 "reasons": [],
 "metrics": {"total_cost": 9200000, "ltc": 0.706522, "ltv_as_is": 0.6625, "loan_to_arv": 0.52,
             "dscr_in_place": 0.6636, "debt_yield_stabilized": 0.107692, "implied_cap_rate": 0.056},
 "exit": {"payoff": 6500000, "caps": {"dscr": 9333333, "ltv": 8750000, "debt_yield": 8235294},
          "binding": "debt_yield", "takeout_max": 8235294, "refi_cushion": 1735294, "exit_dscr": 1.7949},
 "stress": {"noi": 630000, "rate": 0.07, "takeout_max": 7200000, "binding": "dscr", "refi_cushion": 700000, "exit_dscr": 1.3846},
 "reconciliation": [{"name": "rent_roll_vs_t12", "gap": 0.0213, "status": "pass"},
                    {"name": "sources_vs_uses", "gap": 0.0, "status": "pass"},
                    {"name": "unit_count", "status": "pass"}],
 "flags": [], "open_questions": [],
 "narrative": {"summary": "...with {{metrics.ltc}} placeholders...", "exit": "...", "risks": "..."},
 "artifacts": {"memo_pdf": "data/runtime/outputs/D-0042/v1/memo.pdf", "workbook": "data/runtime/outputs/D-0042/v1/workbook.xlsx"}}
```
Reason object: `{"code": "LTC_WATCH", "severity": "watch", "value": 0.7414, "threshold": 0.75, "source_fields": ["loan_commitment", "total_cost"]}`.

## Check report
```json
{"deal_id": "D-0042", "deal_version": 1, "status": "pass",
 "checks": [{"name": "recompute_metrics", "status": "pass", "max_abs_diff": 0.0},
            {"name": "rules_recheck", "status": "pass"},
            {"name": "source_trace", "status": "pass", "untraceable_fields": []},
            {"name": "workbook_audit", "status": "pass", "hardcoded_metric_cells": []},
            {"name": "memo_number_match", "status": "pass", "unmatched_numbers": []}],
 "mismatches": [], "flags": [], "summary": "Independent recompute matches on all metrics."}
```
Status values: `pass`, `warn` (non-numeric issue, human should look), `fail` (numeric mismatch or untraceable field).
Mismatch: `{"field": "ltc", "underwriter": 0.7065, "independent": 0.7143, "diff": 0.0078, "likely_cause": "..."}`.

## Event (append-only log and SSE payload)
```json
{"event_id": 112, "deal_id": "D-0042", "ts": "2026-11-16T15:04:07Z", "actor": "underwriter",
 "type": "tool.called", "summary": "calc.ltc = 70.65%", "deal_version": 1, "payload": {"call_id": "t-0031"}}
```
Types: `deal.created`, `deal.submitted`, `version.created`, `fact.recorded`, `file.uploaded`, `file.classified`, `checklist.updated`, `state.changed`, `handoff.sent`, `handoff.returned`, `tool.called`, `extraction.completed`, `underwriting.completed`, `check.completed`, `check.retry`, `review.requested`, `patch.proposed`, `patch.confirmed`, `patch.cancelled`, `override.recorded`, `decision.recorded`, `memo.rendered`, `deal.archived`, `deal.restored`, `deal.renamed`, `info.requested`, `info.replied`, `error`.

## Checklist status (external chat)
```json
{"required": ["deal_summary", "purchase_contract", "rent_roll", "t12", "renovation_budget"],
 "received": ["rent_roll", "t12"], "missing": ["deal_summary", "purchase_contract", "renovation_budget"], "ready": false,
 "facts_missing": ["sponsor_name"]}
```

## Patch and override
```json
{"patch_id": "p-0004", "deal_id": "D-0042", "kind": "data", "path": "rent_roll.units[3].monthly_rent",
 "old": 1640, "new": 2100, "reason": "Reviewer: signed lease shows 2,100", "status": "proposed"}
```
Kinds: `data` (recalculates from underwriting), `narrative` (re-renders memo), `override` (records a reviewer judgment with a required reason; numbers unchanged). A confirmed patch writes a new deal version; the old version stays readable.

## Chat messages
External chat request: `{"message": "...", "files": []}`. Response: `{"reply": "...", "checklist": <Checklist status>}`. Internal chief chat response: `{"reply": "...", "intent": "question|data_edit|narrative_edit|override|action", "patch": <Patch or null>}`.
