# Sprints (MVP, about 5.5 hours total)

Work one sprint at a time. Stop at done-when and show the result before starting the next. Branch per sprint, tag at the end. Cut line is at the bottom.

## Sprint 0: Setup (20 min)
- [ ] Python project with `pyproject.toml`, `.venv`, `ruff`, `pytest`; `frontend/` created with Vite, React, TypeScript, Tailwind
- [ ] Folder layout from `docs/architecture.md` created with empty modules
- [ ] `Makefile` with `setup`, `test`, `lint`, `dev`, `demo`, `smoke`, `fixtures`
- [ ] GitHub repo created or connected, first push, CI workflow running `ruff`, `pytest`, and the frontend typecheck
- [ ] `make fixtures` regenerates the three sample deals with no diff
**Done when:** `make test` runs (even with one placeholder test), CI is green, and the repo is pushed.

## Sprint 1: Deterministic core (75 min)
- [ ] `schema.py`: `Sourced[T]`, `Deal` (property, rent roll, T-12, loan request, sources and uses, pro forma), `Metrics`, `UnderwritingResult`
- [ ] `calc.py`: LTC, LTV as-is, loan-to-ARV, in-place DSCR, stabilized debt yield, implied cap rate, take-out caps and binding constraint, refi cushion, exit DSCR, stress (formulas in `docs/rules.md`)
- [ ] `rules.py`: loads `config/rules.yaml`; returns call and reason codes
- [ ] Reconciliation: rent roll vs T-12, sources vs uses, unit count
- [ ] `completeness.py` against `config/checklist.yaml`
- [ ] Parsers for the sample CSV, XLSX, and markdown into a `Deal`
- [ ] `builders/workbook.py` (XLSX with formulas) and `builders/memo.py` (one-page PDF with numbers filled from the result)
- [ ] Tests: unit tests per formula, one test per rule and reconciliation check (clean and broken input), three end-to-end tests against each `expected.json`
**Done when:** the three deals return screen, watch, and decline from files alone with no model, metrics match `expected.json`, and the memo PDF and workbook open correctly.

## Sprint 2: Agents, chief, store, API (90 min)
- [ ] `store/`: SQLite deal record, versions, append-only event log, patches
- [ ] `agents/runner.py`: `AgentRunner` interface with Claude and cached implementations
- [ ] Extraction agent (cached `extracted.json` per deal; live parse plus Claude behind `--live`)
- [ ] Underwriter agent with tool registry; memo narrative with placeholders and the digits-only-in-placeholders test
- [ ] `core/independent/` and the checker agent with its tools and `CheckReport`
- [ ] Chief state machine with retry limit and escalation; handoff envelopes logged
- [ ] CLI: `python scripts/run_deal.py data/deals/bronx_mf` prints events and writes outputs
- [ ] Intake chat agent (cached replies in offline mode) and the chief-chat intent classifier with patch proposals
- [ ] FastAPI routes and SSE streams from `docs/ui.md`; OpenAPI spec exported for frontend types
**Done when:** the CLI runs all three deals end to end offline, the checker agrees on each, a forced mismatch triggers the retry loop and then escalation, and `make smoke` passes once the API key is set.

## Sprint 3: UI (120 min)
- [ ] Workspace page: header, Flow tab (React Flow, node states, drawer), Review tab (timeline, memo viewer, workbook viewer, decision buttons)
- [ ] Docked chief chat with patch confirm card
- [ ] Queue page with live updates
- [ ] Chat intake page with checklist chips and upload
- [ ] Generated API types and SSE hook
**Done when:** you can click through the full demo on localhost in Safari: create a deal in the chat, watch the Flow tab run, review the memo and workbook, make one chat edit, and approve.

## Sprint 4: Demo and docs (30 min)
- [ ] Final `README.md` (what it does, how to run, limits), `docs/demo-script.md` checked against the real UI
- [ ] 3-minute screen recording (Cmd+Shift+5)
- [ ] One-page PDF summary and the email to the interviewer
**Done when:** a fresh clone runs `make setup` and `make demo` successfully, and the recording exists.

## Cut line (in this order)
1. Drop live extraction (`--live`); ship on cached `extracted.json`.
2. Seed the Queue and script the Chat intake instead of building them live.
3. Drop the workbook viewer (offer a download link).
4. Last resort: ship Sprints 1 and 2 plus the workspace Review tab on one deal. Do not half-build everything.

## Demo script (3 minutes)
1. (20s) Problem: speed decides bridge deals; the first pass is mostly mechanical.
2. (30s) Chat intake: upload documents, the chat reports what is missing, then complete.
3. (60s) Flow tab: the chief hands off to extraction, underwriter, checker; open one tool call to show the formula and inputs.
4. (40s) Review tab: memo leads with the exit; make one chat edit and watch recalculation.
5. (20s) Show the decline deal listing every failed rule; approve the clean one.
6. (10s) Limits: made-up data, illustrative thresholds, human approves.
