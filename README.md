# AI Lending Platform (MVP demo): bridge loan screening

A multi-agent screening layer for bridge loans (sample data only). A chief agent routes work between an extraction agent, an underwriter agent, and an independent checker. Deterministic code does every calculation. A human reviews and approves.

Status: handoff stub. Sprint 4 replaces this with the final README (what it does, how to run, limits).

## What it will do
1. Intake chat collects deal facts and documents and says what is missing.
2. Extraction turns the documents into a typed, sourced deal object.
3. The underwriter agent calls deterministic tools for LTV, LTC, loan-to-ARV, DSCR, debt yield, and exit sizing, and produces a memo (PDF) and workbook (XLSX).
4. The checker recomputes everything independently and reconciles the documents.
5. A reviewer inspects the flow, opens the memo and workbook, edits through the chief chat, and approves.

## Limits
- Made-up sample data only. Thresholds in `config/rules.yaml` are illustrative, not any real lender's box.
- Inputs: markdown, text, PDF (text layer) or Word for the summary and contract; CSV, XLSX or PDF for the tables. No OCR, so a scanned PDF is refused. In live mode Claude helps read documents the parser cannot, but code accepts only what the document itself supports.
- No sponsor credit, appraisal, or comps. No autonomous decisions: a human approves every output.
- Localhost only, no authentication in the MVP.

## Docs
See `docs/` (start with `docs/sprints.md` and `docs/architecture.md`) and `CLAUDE.md`.
