# PRD: AI Bridge Lending Platform (multi-agent)

Date: 2026-11-16 (status updated 2026-11-17). Status: design plus MVP build plan; the MVP is built through sprint 3g (see `docs/sprints.md` and `docs/decisions.md` for what changed from this plan: PDF, Word and Excel intake, 11 sample deals, what-ifs and sizing, a draft reply to the broker). All data is made up; thresholds are illustrative, not any real lender's box.

## 1. Overview
The platform takes a bridge loan request from first borrower contact to a human-approved decision package. A chief agent coordinates specialist agents, and deterministic code does all calculations. This repo builds the MVP: a thin but complete slice that runs on localhost.

**Problem.** A small-balance bridge lender wins deals on speed and certainty, but intake, re-keying documents, and first-pass math consume analyst time. Packages arrive in inconsistent formats, and borrowers wait days to learn whether a deal fits.

**Product.** An external chat collects deal facts and documents and says what is still missing. Internal agents extract the data, size the loan with deterministic tools, independently check the work, and present a memo and workbook to an underwriter, who edits and approves through a chat with the chief agent.

**Principles.** Code owns the math. Models read, classify, and draft. Every handoff passes through the chief. A human approves anything that leaves the building.

## 2. Goals, non-goals, success metrics
**Goals**
1. Give borrowers and brokers a fast, clear first response, including exactly what is missing.
2. Cut analyst time on extraction, spreading, and first-pass sizing.
3. Apply the lender's box consistently, with every number traceable to its source.
4. Keep humans in control of every decision and external message.

**Non-goals (MVP)**
- Autonomous approvals or binding commitments.
- Sponsor credit scoring, appraisal, comps, enrichment integrations.
- Servicing, draws, investor reporting, a portfolio tracker screen.
- Asset types beyond multifamily and mixed-use; authentication (localhost only).

**Success metrics (MVP targets)**

| Metric | Target |
| --- | --- |
| The three sample deals return the expected call (screen, watch, decline) | 3 of 3 |
| Calculator output vs `expected.json` | Dollars exact to $1, ratios within 1e-4 |
| Independent checker agrees with underwriter on all three deals | 100% |
| Live extraction vs answer key (key fields) | 95% or better |
| Package to analyst-ready memo, cached mode | Under 60 seconds |
| Demo recording | 3 minutes or less |

## 3. Users and scenarios
| User | Needs | Sees |
| --- | --- | --- |
| Borrower or broker (external) | Fast answer, clear list of what is missing | Chat only: checklist, pending items, status updates |
| Underwriter (internal) | Clean file, numbers that tie, ability to edit | Queue, deal page (Memo, Calculations, Files, Process), chief chat |
| Senior credit (internal) | Consistency, exceptions surfaced | Queue, flags, reasons, override history |

**Scenario 1, clean deal.** A broker chats and uploads the five required documents. The chat confirms completeness, the agents run, and the underwriter approves the memo in one pass.
**Scenario 2, gaps.** The T-12 is missing. The chat says so and the deal waits in an awaiting-documents state with no analyst time spent.
**Scenario 3, exception.** The checker finds a rent roll vs T-12 gap. The chief routes it, the underwriter edits through chat, affected numbers recalculate, and the diff is logged.

## 4. System design
A chief agent sits at the center. Specialist agents never talk to each other; every handoff goes through the chief. All state lives in one versioned deal record with an append-only event log. The chief owns every state write; the queue and any dashboards are views over the log.

| Component | Type | Job | Must not |
| --- | --- | --- | --- |
| Intake chat agent | Model, external | Collect facts and files, report what is missing | Access internal data, show ratios, or give a decision |
| Completeness check | Code | Compare received files and facts to the checklist | Rely on a model's opinion |
| Extraction agent | Parsers plus model | Classify files, extract fields with source and confidence | Talk to outsiders or compute metrics |
| Chief agent | State machine plus model | Route work, track state, handle chat edits, retry or escalate | Do the specialists' work |
| Underwriter agent | Model plus deterministic tools | Run the tools, triage missing data, draft memo narrative | Type numbers by hand |
| Underwriter tools | Code | Metrics, exit sizing, stress, rules, workbook, memo | Make judgment calls |
| Checker agent | Model plus deterministic tools | Run independent recompute and reconciliation, explain mismatches | Trust the underwriter's output or override numbers |
| Checker tools | Code | Independent parse and formulas, comparison, rules re-check, workbook audit, memo-number match, source trace | Share code with underwriter tools |
| Human reviewer | Person | Review, edit, approve, release | n/a |

**Flow**
1. Borrower chats and uploads. Code classifies files and reports gaps.
2. When complete, the chief hands files to extraction, which returns a validated deal object.
3. The chief hands the deal to the underwriter, which calls tools and produces the memo and workbook.
4. The chief hands the result to the checker. On mismatch it returns to step 3, up to two retries, then escalates to a human.
5. The human reviews, edits through chief chat, and approves.
6. The system locks a snapshot and releases outputs.

## 5. Functional requirements
| # | Area | Requirement | MVP |
| --- | --- | --- | --- |
| FR1 | Intake | External chat collects facts and files and shows a live checklist and status in the conversation | Yes |
| FR2 | Intake | Completeness decided by code against `config/checklist.yaml` | Yes |
| FR3 | Extraction | Classify files; extract fields with value, source, confidence | Yes |
| FR4 | Extraction | Parse CSV and XLSX directly first; models only classify and map columns | Yes |
| FR5 | Underwriting | LTV, LTC, loan-to-ARV, interest-only DSCR, debt yield, exit sizing, stress in tested code | Yes |
| FR6 | Underwriting | Memo (PDF) and workbook (XLSX with formulas) from one result object | Yes |
| FR7 | Checker | Independent recompute; reconciliation of rent roll vs T-12, sources vs uses, unit count | Yes |
| FR8 | Chief | Every handoff passes through the chief and is logged with inputs and outputs | Yes |
| FR9 | Chief | Chat edits become tracked patches that trigger recalculation; overrides require a reason | Yes |
| FR10 | Rules | Thresholds in versioned config | Yes |
| FR11 | Review | Memo and workbook open in-app; approve, send back, or reject | Yes |
| FR12 | Flow | Live orchestration view from the event stream | Yes |
| FR13 | Release | Approval locks a snapshot and generates outbound documents (term sheet, commitment letter) | Later |
| FR14 | Enrichment | Property records, rates, sponsor and KYC checks | Later |
| FR15 | Tracker | Portfolio view for seniors | Later |
| FR16 | Learning | Outcomes and overrides feed the eval set | Later |
| FR17 | Review | What-ifs (rate, NOI, cap rate, loan size) and the largest loan that screens, computed by the real engine, saved nowhere | Yes |
| FR18 | Release | A draft reply to the broker on approval or rejection, edited and approved by the reviewer, never sent | Yes |

## 6. Files and data formats
| Data | Format | Direction |
| --- | --- | --- |
| Deal summary and pro forma, purchase contract | MD, TXT, PDF, DOCX | In |
| Rent roll | CSV, XLSX, sometimes PDF; one row per unit | In |
| T-12 operating statement | CSV, XLSX, or PDF; line items by month | In |
| Renovation budget | CSV, XLSX, or PDF | In |
| Deal record | JSON validated by Pydantic; every field has value, source, confidence | Internal |
| Handoff, tool call, event | JSON (see `docs/data-contracts.md`) | Internal |
| Decision package | JSON | Out |
| Credit memo | PDF (DOCX later) | Out |
| Underwriting workbook | XLSX with live formulas | Out |

Uploaded files are untrusted input: type-checked, size-limited, parsed in code first, and never treated as instructions.

## 7. Screens and flows
Three screens (details in `docs/ui.md`).
1. **Chat intake (external).** A chat with a checklist strip. The chat itself reports what is received, what is missing, and status updates. No separate status page.
2. **Queue (internal).** All deals with stage, call, flags, age, owner. Analysts and seniors use it.
3. **Deal page (internal).** The chief chat on the left; on the right the tabs Memo (with a review panel), Calculations (with a link from each input to its source line), Files, and Process (the agent graph and a plain-words history).

Edit flow: the reviewer types a change, the chief proposes a diff, the reviewer confirms, affected calculations rerun, and the change is logged. Three edit types: data edit (recalculates), judgment override (requires a reason), narrative edit (memo text only).

## 8. Non-functional requirements
- **Auditability:** every number traces to a source document or tool call; every handoff, edit, and approval is an immutable event.
- **Determinism:** same deal version and rules version give the same numbers.
- **Security:** secrets only in `.env`; file parsing in code; the external agent has a separate, minimal tool set. MVP is localhost without auth; production needs SSO, roles, encryption, and retention rules.
- **Model safety:** a model never makes the final call; uploaded content cannot change agent instructions; low-confidence fields are flagged, never defaulted.
- **Reliability:** steps are idempotent and retryable; a failed step is visible in Flow and loses no state.
- **Compliance:** lending licensing, data retention, vendor risk, and fair-lending obligations need review by qualified counsel; this PRD does not settle them.

## 9. Phasing, risks, open questions
**Phases after the MVP:** shadow mode against human underwriters, limited live use with human approval on every output, enrichment integrations, release documents, servicing, portfolio tracker.

**Risks:** extraction errors compound (mitigate with validation, source quotes, independent checker); the real lender's box differs from assumptions (rules are config); messy broker packages (parsers first, confidence flags); prompt injection through uploads (sandboxing, forced output schema, narrow tools); underwriters distrust it (show sources, formulas, reasons).

**Open questions:** the real limits on LTC, LTV, DSCR, debt yield; how packages arrive today; which systems it must integrate with; approval authority by deal size.

**MVP limitation:** stabilized NOI and ARV come from the borrower's pro forma and are used as given. A real system would haircut or underwrite them independently.

## 10. MVP build plan
Stack: Python 3.12, FastAPI, Pydantic, SQLite, `anthropic` SDK, `openpyxl`, `reportlab`; React, Vite, TypeScript, Tailwind, React Flow; localhost and GitHub. Five sprints (about 5.5 hours): setup, deterministic core, agents and chief, UI, demo. Requirements and done-when per sprint are in `docs/sprints.md`. Cut line: if short, ship Sprints 1 and 2 plus the workspace screen, and seed the queue and chat with sample data.
