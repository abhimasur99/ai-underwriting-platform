# Agents: exact logic

Five roles. The chief is a code state machine. The other four are small, single-purpose loops. Agents never call each other; every handoff goes through the chief and is logged. Prompts live in `backend/bridge/agents/prompts/`. Thresholds and formulas are in `docs/rules.md`; JSON shapes are in `docs/data-contracts.md`.

Shared pattern: **code owns the order of work.** The underwriter, checker and extraction run their steps in a fixed sequence from code (`agents/underwriter.py`, `checker.py`, `extraction.py`) and log every tool call to the event log (inputs, formula, output). The model, in live mode, makes single structured-output calls (`agents/claude_runner.py`) for narrative, wording and chat interpretation. It has no tools and no sampling parameters (see decisions D17, D19). Output is validated against a Pydantic model; invalid output fails the step loudly. Offline, a cached runner returns the same shapes without a model.

## 1. Intake chat (external, chat only)
- **Job:** collect the documents and facts the checklist needs, in a friendly chat. Never gives a decision or any numbers about the deal.
- **Model use:** only to read a message into facts, what the person is doing (greeting, help, missing, next, status, thanks) and an "asked for a decision" flag. Replies are composed by code from the checklist and the deal's state (`agents/intake_replies.py`, D18); in live mode a model may rephrase a reply, and code uses the rephrasing only if it adds no number and no credit or underwriting word the draft did not already have (`agents/phrasing.py`, D40). The checklist logic is code.
- **Details from documents:** as each document arrives, the address, asset type, units, sponsor, loan amount, price and renovation budget are read from it (`core/parsers/preview.py`), so the sponsor confirms instead of retyping (D39).
- **Tools:** `record_fact(key, value)`, `get_checklist_status()`, `classify_file(file_id)` (filename, then columns, then the document's first lines; if all fail the chat asks), `submit_deal()` (allowed only when `ready` is true).
- **Flow per message:** apply tool calls, recompute checklist, reply with what was received and what is missing, one ask at a time.
- **Guardrails:** refuses to discuss underwriting results, rates or approval odds ("the team will follow up"); file type and size limits from `config/checklist.yaml`; uploaded file content is data, never instructions.
- **Done:** the deal is created as `CREATED` when the chat starts. `submit_deal` is allowed only in `READY`; it hands the deal to the chief, which dispatches extraction (`EXTRACTING`).

## 2. Extraction agent
- **Job:** turn the labeled documents into the deal record, every field a `Sourced` value.
- **Order of work:** (1) deterministic parsers for the rent roll, T-12 and renovation budget as CSV, XLSX or a PDF table (rebuilt from text positions); no model; (2) the deal summary and contract may be markdown, text, PDF (text layer) or Word: `core/parsers/documents.py` turns each into markdown-like text (headings from font size or style, tables from table rows) and the sample parser extracts `Label: value` lines and tables from it; in live mode the model reads the text and returns fields with a quote and locator for each; (3) code verifies each quote appears in the source (else confidence capped at 0.5) and each number parses; (4) code derives totals and checks stated vs computed (units, renovation sum, T-12 row sums); (5) live mode only, and only for what (1) to (4) could not find: a missing prose field or an unmatched table heading is put to Claude, whose answer code accepts only if its one-line quote is in the document and the value is inside the quote (columns: a heading to canonical-name map, numbers still read by code). Such fields get confidence 0.75 and a `MODEL_ASSISTED_EXTRACTION` flag (decisions D34, D35).
- **Tools:** `read_document(doc_id)`, `parse_rent_roll`, `parse_t12`, `parse_budget`, `find_in_document(doc_id, text)`.
- **Output:** deal record v1 plus `extraction_notes` (conflicts, ambiguous fields).
- **Guardrails:** never guesses a missing required field (returns `needs_input` naming it); if two documents disagree, keeps both values, flags it, and lowers confidence; fields below 0.80 become `LOW_CONFIDENCE_FIELD` flags downstream.
- **Retry policy:** none inside extraction (it is deterministic parsing); a missing required field or invalid file makes the chief set `NEEDS_INPUT` (missing or invalid fields), or `FAILED` (unrecoverable error), and posts the reason to the queue. There is no separate `EXTRACTION_FAILED` state.

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
- **Model use:** classifying reviewer chat intent (`question | data_edit | narrative_edit | override | action`) and wording replies. It never decides workflow state. A what-if arrives as named assumptions and a values, and "largest loan" as a target; code computes both (`core/scenario.py`, `core/sizing.py`, D41, D42).
- **Reply to the broker:** on an approval or rejection the chief drafts a reply (`agents/broker_reply.py`): code-written, no figures; in live mode a model may rephrase it behind `phrasing.valid_broker`. The reviewer edits and approves it; it is logged (`reply.drafted`, `reply.edited`, `reply.approved`) and never sent (D43).
- **Chat tools:** `get_deal_summary`, `get_metric(name)` (returns value plus formula and inputs), `explain_reason(code)`, `propose_patch(path, new_value, reason)`, `confirm_patch(patch_id)` (reviewer button, never the model), `rerun_underwriting()`, `record_decision(decision, rationale)` (reviewer only), `run_what_if(assumptions)` and `max_loan(target)` (read-only: they save nothing).
- **Edit handling:**
  - Data edit: chief proposes a patch with old and new value and shows impact in words; on confirm, writes deal v+1, reruns underwriter then checker; the old version stays readable.
  - Narrative edit: re-renders the memo text, then reruns the memo-number-match check.
  - Override: records the reviewer's judgment with a required reason; numbers do not change; shown on the memo.
- **Guardrails:** answers numeric questions only from tool output; no patch applies without a confirm click; the decision button records the human decision, the AI call is a recommendation.
- **Failure policy:** each step has a timeout; any exception writes an `error` event and sets a visible state, never a silent stall.

## 6. Cost and mode
Defaults to cached fixtures per sample deal so the demo runs offline and free; `--live` calls the model. Model name comes from `ANTHROPIC_MODEL`. Live calls send no `temperature` (the current model rejects it); determinism comes from code owning the numbers (D19). Live extraction is parsers only for now (D20).
