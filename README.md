# AI Lending Platform: bridge loan screening (MVP demo)

A multi-agent screening layer for bridge loans, built as an interview demo. A chief agent routes work between an extraction agent, an underwriter agent and an independent checker. Deterministic code does every calculation. A person reviews, edits and decides.

**Sample data only.** Every deal, name and address is made up. The thresholds in `config/rules.yaml` are illustrative, not any real lender's credit box. This is a screening-layer prototype, not any firm's product.

## What it does
1. **Intake chat (the sponsor's side).** A broker or sponsor drops PDF, Word, Excel or CSV files into a chat. The assistant files them, reads the address, units, sponsor and loan amount from the documents, and says what is still missing. It never shows a call, a ratio or a rate.
2. **Extraction.** Documents become a typed deal where every field carries its source (document and line) and a confidence. A missing field stops the deal and asks; nothing is guessed. In live mode Claude can help read unfamiliar wording, but code accepts only what the document itself supports.
3. **Underwriting.** Code computes loan to cost, loan to value, loan to ARV, DSCR, debt yield, implied cap rate, take-out sizing and a stress case, applies the rules, and renders a one-page memo (PDF) and a workbook (XLSX with live formulas).
4. **Independent check.** A second implementation with its own parser and formulas recomputes everything and audits the memo and workbook. Disagreement triggers a retry, then escalation to a person.
5. **Review (the internal side).** A queue says what needs you. The deal page has the memo, the calculations with a link from each input to the exact line in the source document, the files, and a view of the agents' process. A chat with the chief answers questions, tries what-ifs, finds the largest loan that still screens, and proposes edits that you confirm.
6. **Decision.** Approve, reject, or ask the sponsor for more. Approving or rejecting drafts a reply to the broker that you edit and approve. Nothing is ever sent from the app.

## Run it
Needs Python 3.12 and Node.

```
make setup     # virtual environment, Python and npm dependencies
make demo      # run the 10 sample deals offline and seed the queue (resets local data)
make dev       # backend on :8000 and the app on http://localhost:5173 (offline, no key needed)
make dev-live  # same, with Claude writing narrative and wording the chat (needs ANTHROPIC_API_KEY in .env)
```
Copy `.env.example` to `.env` for live mode. Never commit a real key (`.env` is gitignored). `make dev-retry` forces the checker to disagree twice, to show the retry and escalation. `make test`, `make lint`, `make fixtures` (regenerate the sample deals; must produce no diff) and `make e2e` (a local browser check of the demo path, run `make demo` first) are the other commands. A walk-through is in [docs/demo-script.md](docs/demo-script.md).

Sample packages are in `data/deals/` (see [docs/deals-catalog.md](docs/deals-catalog.md): 4 Screen, 4 Watch, 2 Decline, 1 that stops and asks, in markdown/CSV, PDF/Excel and mixed kits).

## How it is built
- **Code owns the math.** A model never outputs a computed number. Every figure in the memo, the workbook and both chats comes from `backend/bridge/core/calc.py` through the rules. The memo narrative uses placeholders that code fills, and a test fails if the narrative contains a digit outside one.
- **A checker that cannot be fooled by the same bug.** `core/independent/` has its own parser and formulas and imports nothing from the underwriter's. Both are pinned to the same answers in `data/deals/*/expected.json`.
- **Hub and spoke.** Agents never call each other; every handoff goes through the chief, a code state machine, and is logged. The queue and every view are projections of an append-only event log (SQLite).
- **Offline first.** Every agent has a cached mode, so demos and CI run with no key. Live mode makes single structured-output calls (no tools, no sampling parameters) for wording, chat interpretation and fallback reading, and code validates each answer.
- **Safe wording.** A model may rephrase a chat reply or the broker draft, but only if it adds no number, no credit word it was not given, and no link. Otherwise the code-written text stands.
- **What-ifs save nothing.** The same underwriting runs on a copy of the deal. "Largest loan that screens" is solved by re-applying the rules at different loan sizes.

Decisions and their reasons are in [docs/decisions.md](docs/decisions.md) (D1 to D43).

## Limits
- Made-up data only; thresholds are illustrative.
- Inputs: markdown, text, PDF (text layer) or Word for the summary and contract; CSV, XLSX or PDF for the tables. No OCR: a scanned PDF is refused with a reply saying what to send.
- Stabilized NOI and ARV come from the borrower's pro forma and are used as given. No sponsor credit, appraisal or comps. No autonomous decisions: a person approves every outcome.
- Nothing leaves the app: no email, no term sheet, no integrations. Localhost only, no authentication.
- Tested in Chrome. Safari and Excel are not yet verified.

## Tests
`make test` runs the backend suite (about 840 tests, including one end-to-end test per sample deal, a test that the checker imports nothing from the underwriter, and adversarial chat tests) and the frontend unit tests. CI runs lint, type checks, the tests, and fails if the generated fixtures or API types drift.

## Docs
Start with [docs/sprints.md](docs/sprints.md) and [docs/architecture.md](docs/architecture.md). Also [docs/PRD.md](docs/PRD.md), [docs/agents.md](docs/agents.md), [docs/rules.md](docs/rules.md), [docs/ui.md](docs/ui.md), [docs/data-contracts.md](docs/data-contracts.md) and [CLAUDE.md](CLAUDE.md).
