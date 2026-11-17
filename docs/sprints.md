# Sprints (MVP, about 5.5 hours total)

Work one sprint at a time. Stop at done-when and show the result before starting the next. Branch per sprint, tag at the end. Cut line is at the bottom.

## Status and the rebuild plan (updated 2026-11-16)

| Sprint | State |
| --- | --- |
| 0 Setup, 1 Core, 2 Agents, 3 UI, 3b Restyle and queue housekeeping | Done, tagged (`sprint-0` to `sprint-3b`) |
| 3c Files and deals | Done, tagged `sprint-3c` |
| 3d Deal page rebuild | Done, tagged `sprint-3d` |
| 3e Intake and chat | Done, tagged `sprint-3e` |
| 3f What-ifs and sizing | Planned |
| 3g Draft broker reply | Planned |
| 3h Underwriter case (assumptions) | Optional: decide after 3g |
| 4 Demo and docs | Planned (last) |

Why 3c to 3h exist: a design review (see `docs/decisions.md` D29 to D33) found that the demo should use real PDF, Word and Excel files, that the deal page repeats itself and shows system internals instead of the reviewer's job, and that the chats are too canned. Each sprint below is its own branch and tag, test-first where it touches core code.

## Sprint 3c: Files and deals
- [x] Add `pypdf` and `python-docx`. Read PDF (text layer) and DOCX into the same structure the markdown parser uses; summary and contract may be `.md`, `.txt`, `.pdf` or `.docx`; tables may be `.csv` or `.xlsx`. The checker gets its own small reader (independence)
- [x] Intake accepts only formats that really parse; classification also uses a document's first lines (content hints)
- [x] Sample-document writers (markdown to PDF, DOCX, XLSX), deterministic so CI can diff them
- [x] Eight new sample deals (`docs/deals-catalog.md`): 4 Screen, 4 Watch, 2 Decline, 1 Needs input across the 11, in three file kits (markdown and CSV; PDF and XLSX; mixed)
- [x] Answer keys and cached fixtures for all 11; one parametrized end-to-end test over every deal
- [x] PDF tables read from text positions (own reader in the checker); one deal is an all-PDF package
- [x] Claude-assisted extraction as a verified fallback in live mode (D34), with the checker's honest fallback (D35)
**Done when:** all 11 deals reach their expected call (the Needs input deal stops and asks, then proceeds after a corrected file), the checker agrees on each, uploading the PDF and XLSX files through the API works, and CI regenerates the files with no diff.

## Sprint 3d: Deal page rebuild
- [x] Layout: chat on the left (collapsible), workspace on the right; back on the left, forward on the right
- [x] Header actions on every tab: Reject, Request info, Approve; Next deal needing review
- [x] One summary strip (call, checker, exceptions, questions for the sponsor) replacing the repeated status chips
- [x] Tabs: Memo, Calculations (metrics and sources; "click to edit inputs" is deferred, edits still go through the chat), Files (document text with the source line highlighted), Process (flow graph and a readable log)
- [x] Queue: a Next action column (Your review, Waiting on sponsor, Running); sorted by what needs you
- [x] Request info replaces Send back: the note appears in the sponsor's chat and the deal waits for new files
- [x] Shared UI kit and feature folders; `vitest` unit tests for flow derivation and next-action rules; accessibility pass (contrast AA, tab roles, keyboard, live regions); checked at 1280x800 and 1440x900
**Done when:** a reviewer can go from the queue to a decision without opening the Process tab, and every number opens to its source line.

## Sprint 3e: Intake and chat
- [x] Facts are read from the uploaded documents; the sponsor only confirms or fills gaps
- [x] Interactive checklist beside the chat (drop a file onto its slot); chat on the left, as everywhere
- [x] Richer replies from code-composed templates (greeting, help, what is missing, what next, status, thanks); live mode may phrase them from an allowed-facts packet, guarded by a test that rejects numbers and decision language
- [x] Chief chat: capabilities help, deal summary, exceptions, what changed in the latest version (with a before and after card), follow-up chips
**Done when:** a sponsor who drops five files and types nothing else is told what was read and what is missing.

## Sprint 3f: What-ifs and sizing
- [ ] A pure scenario engine (the same calculator, with parameters changed) behind both the chat and an API route: what if the take-out rate, an NOI haircut, a cap rate, take-out terms or the loan amount changed; nothing is saved and the deal is not touched, so the independent check is not involved
- [ ] The chief chat understands what-ifs ("what if rates are 7%?") and answers with the current case against the changed one, the call change highlighted, every figure from the engine
- [ ] "What is the largest loan that still screens?": code solves it exactly by re-applying the rules (the advance and the holdback scale together; ARV and NOI are held)
- [ ] The before and after view for every committed change (the chat card from 3e) also on the deal page
**Done when:** a reviewer can ask a what-if or the maximum loan in the chat and get an exact answer in seconds, and no what-if changes the deal.

## Sprint 3g: Draft broker reply
- [ ] Approving or rejecting a deal produces a draft reply to the broker (template offline, wording from Claude in live mode behind the same validator as the chats); it is shown for the reviewer to edit and approve, and is never sent
**Done when:** every approved or rejected deal has a logged, reviewer-approved draft.

## Sprint 3h: Underwriter case (optional)
An assumptions panel for the reviewer's own haircuts, cap rate and take-out terms beside the borrower's figures, with explore, then commit with a reason (the chat proposes the same card). It needs the independent checker's own implementation of each assumption, the workbook, the memo and the rules on the committed case, so it is decided after 3g, and kept to a few assumptions if it is built.

`make e2e` (a Playwright script in the repo) runs the demo path locally; it is not a CI step.

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
