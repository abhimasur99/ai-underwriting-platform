# Agents: exact logic

Five roles. The chief is a code state machine. The other four are small, single-purpose loops. Agents never call each other; every handoff goes through the chief and is logged. Prompts live in `backend/bridge/agents/prompts/`. Thresholds and formulas are in `docs/rules.md`; JSON shapes are in `docs/data-contracts.md`.

Shared loop for tool-using agents (`agents/base.py`): send messages and tool schemas to the model; if it returns tool calls, run them in code, append results, loop; stop when it returns the final structured output or hits `max_steps`. Every tool call is written to the event log. Output is validated against a Pydantic model; on a validation error, retry once with the error text, then fail the step.

## 1. Intake chat (external, chat only)
- **Job:** collect the documents and facts the checklist needs, in a friendly chat. Never gives a decision or any numbers about the deal.
- **Model use:** wording and understanding free-text replies. The checklist logic is code.
- **Tools:** `record_fact(key, value)`, `get_checklist_status()`, `classify_file(file_id)` (filename and header hints first, model label only if ambiguous), `submit_deal()` (allowed only when `ready` is true).
- **Flow per message:** apply tool calls, recompute checklist, reply with what was received and what is missing, one ask at a time.
- **Guardrails:** refuses to discuss underwriting results, rates or approval odds ("the team will follow up"); file type and size limits from `config/checklist.yaml`; uploaded file content is data, never instructions.
- **Done:** the deal is created as `CREATED` when the chat starts. `submit_deal` is allowed only in `READY`; it hands the deal to the chief, which dispatches extraction (`EXTRACTING`).

## 2. Extraction agent
- **Job:** turn the labeled documents into the deal record, every field a `Sourced` value.
- **Order of work:** (1) deterministic parsers for `rent_roll.csv`, `t12.csv`, `renovation_budget.csv` (no model); (2) for the markdown summary and contract, the sample parser extracts `Label: value` lines and tables; in live mode the model reads the text and returns fields with a quote and locator for each; (3) code verifies each quote appears in the source (else confidence capped at 0.5) and each number parses; (4) code derives totals and checks stated vs computed (units, renovation sum, T-12 row sums).
- **Tools:** `read_document(doc_id)`, `parse_rent_roll`, `parse_t12`, `parse_budget`, `find_in_document(doc_id, text)`.
- **Output:** deal record v1 plus `extraction_notes` (conflicts, ambiguous fields).
- **Guardrails:** never guesses a missing required field (returns `needs_input` naming it); if two documents disagree, keeps both values, flags it, and lowers confidence; fields below 0.80 become `LOW_CONFIDENCE_FIELD` flags downstream.
- **Retry policy:** one retry on schema-validation failure; otherwise the chief sets `NEEDS_INPUT` (missing or invalid fields) or `FAILED` (unrecoverable error) and posts the reason to the queue. There is no separate `EXTRACTION_FAILED` state.

## 3. Underwriter agent
- **Job:** size and evaluate the deal and draft the narrative. It does not do arithmetic.
- **Order of work:** (1) call `calc.*` tools for every metric (each call logged with inputs, formula, output); (2) call `rules.evaluate(metrics, reconciliation)` which returns the call and reason list; (3) call `exit.analyze` and `exit.stress`; (4) draft narrative sections using only placeholders for numbers (`{{metrics.ltc}}`); (5) code renders the workbook and memo.
- **Tools:** `calc.total_cost`, `calc.ltc`, `calc.ltv_as_is`, `calc.loan_to_arv`, `calc.dscr_in_place`, `calc.debt_yield`, `calc.implied_cap_rate`, `exit.analyze`, `exit.stress`, `reconcile.all`, `rules.evaluate`, `render.workbook`, `render.memo`.
- **Guardrails:** the call comes from `rules.evaluate` only; the model may not change it. A narrative containing a digit outside a placeholder fails validation and is regenerated once. The memo always carries the sample-data footer.
- **Output:** the underwriting result (see data contracts).

## 4. Checker agent
- **Job:** independently verify the underwriting and the artifacts. Cannot see the underwriter's reasoning, only its outputs.
- **Independence:** uses `core/independent/` only (own parser, own formulas), checked against `expected.json` vectors. No imports from `core/calc.py` or `core/parsers/`.
- **Deterministic tools:** `independent_parse(doc_id)`, `independent_recompute(deal_inputs)`, `compare_metrics(a, b, tol)`, `rules_recheck(metrics)`, `reconcile_recheck()`, `workbook_audit(path)` (metric cells must be formulas; recalculated values must match), `memo_number_match(memo, result)`, `source_trace(deal_record)`.
- **Model use:** only to write the summary and to word `likely_cause` for a mismatch, from the tool output.
- **Status rule (code):** any numeric mismatch beyond tolerance (0.0001 ratios, $1 amounts), an untraceable field, a hardcoded metric cell, or an unmatched memo number is `fail`; non-numeric concerns are `warn`; else `pass`.
- **Handling in the chief:** `pass` goes to review; `fail` sends the underwriter back with the mismatch list (up to 2 retries); if the check still fails after the second retry, the deal goes to `NEEDS_REVIEW` with `escalation=true` and the report attached (the UI may show a "check failed" badge, but it is a flag, not a state). `warn` goes to review with the warnings visible.

## 5. Chief agent
- **Job:** run the workflow and talk to reviewers.
- **State machine (code):** the states and the transition table live only in `docs/architecture.md` section 3; do not duplicate them here. The chief writes the state change and the handoff to the event log, then calls the next agent. All queue views are projections of these events.
- **Model use:** classifying reviewer chat intent (`question | data_edit | narrative_edit | override | action`) and wording replies. It never decides workflow state.
- **Chat tools:** `get_deal_summary`, `get_metric(name)` (returns value plus formula and inputs), `explain_reason(code)`, `propose_patch(path, new_value, reason)`, `confirm_patch(patch_id)` (reviewer button, never the model), `rerun_underwriting()`, `record_decision(decision, rationale)` (reviewer only).
- **Edit handling:**
  - Data edit: chief proposes a patch with old and new value and shows impact in words; on confirm, writes deal v+1, reruns underwriter then checker; the old version stays readable.
  - Narrative edit: re-renders the memo text, then reruns the memo-number-match check.
  - Override: records the reviewer's judgment with a required reason; numbers do not change; shown on the memo.
- **Guardrails:** answers numeric questions only from tool output; no patch applies without a confirm click; the decision button records the human decision, the AI call is a recommendation.
- **Failure policy:** each step has a timeout; any exception writes an `error` event and sets a visible state, never a silent stall.

## 6. Cost and mode
Defaults to cached fixtures per sample deal so the demo runs offline and free; `--live` calls the model. Model name comes from `ANTHROPIC_MODEL`. Keep `max_steps` low (8) and temperature at 0 for extraction and checking.
