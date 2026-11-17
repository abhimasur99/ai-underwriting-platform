# UI: screens, flows, API

Three screens for the MVP. The deals tracker (portfolio view for seniors) is deferred.

## 1. Chat intake (external)
A single chat page. The chat itself reports status; there is no separate status page.

```
+--------------------------------------------------+
| Bridge loan intake                               |
| [✓ Deal summary][✓ Contract][✓ Rent roll]        |
| [○ T-12][○ Renovation budget]                    |
|--------------------------------------------------|
|  Agent: Thanks. I have your rent roll and ...    |
|                    You: Uploading the T-12 now   |
|                    [ t12.csv uploaded ]          |
|  Agent: Got it. One item left: the budget.       |
| [ Type a message or drop files              ]    |
+--------------------------------------------------+
```
Behavior:
- Checklist chips come from the completeness check (code): done, pending.
- After each upload the chat reports what is received and what is missing, and when everything is in, says the team will review.
- Status updates ("Under review", "We need one more item") are posted into the chat from deal state. The external chat never shows ratios, reasons, or a decision.
- Handles: file type or size rejected, duplicate upload, a file that looks like the wrong type (asks to confirm).

## 2. Queue (internal)
Table of deals: Deal, Stage, Call, Flags, Age, Owner. Filter tabs with counts: All, Needs review, Flagged, Archived. Search box. Row click opens the workspace. Updates live from the global event stream.

**Housekeeping.** A deal is never deleted (the event log is append-only and ids are never reused), so "delete" is archive: a logged `deal.archived` event hides the deal from the queue; the Archived tab lists it and Restore undoes it. Each row has an Archive link; checkboxes allow bulk archive; every archive shows an Undo notice. A deal that is mid-run cannot be archived (409). A deal can be renamed by clicking its title in the workspace. Opening the intake page does not create a deal: it is created on the first message or upload, so browsing to New deal and leaving leaves nothing behind (decision D27).

Stage chips: Awaiting docs, Extraction, Underwriting, Checker, Review. Call chips: Screen (teal), Watch (amber), Decline (coral).

## 3. Deal workspace (internal)
Header: deal id and name, tabs (Flow, Review), status chip. The chief chat is docked on the right on both tabs.

**Flow tab.** React Flow diagram: Chief in the center, Extraction, Underwriter, Checker around it, Intake chat and Human reviewer at the top. Node state: idle, running (amber), done (teal), failed (coral). Edges animate when a handoff is in flight. Clicking a node opens a drawer with the handoff envelope, tool calls (tool, inputs, formula, output), and result. A retry counter shows on the Checker to Underwriter loop.

**Review tab.** Left: progress timeline (Intake, Extraction, Underwriting, Checker, Your review). Center: tabs Memo and Workbook. The memo is a PDF viewer; the workbook is a read-only grid with formulas visible on hover. Each metric in the memo summary links to its formula, inputs, and source. Buttons: Approve, Send back, Reject, each behind a one-click confirm, with a "What do these do?" panel:
- **Approve** records the approval, closes the deal and writes a `released.json` snapshot (deal, result, check, rationale) beside the memo. Nothing leaves the app.
- **Send back** re-runs underwriting and the independent check on the current version and returns the deal to review. It messages no one.
- **Reject** closes the deal as rejected. Approved and rejected deals are final; there is no reopen in the MVP.

**Chief chat (internal).** Free text. The chief classifies the message into: question (answer from the deal record), data edit, narrative edit, judgment override, or action (approve, send back).
- Data edit: the chief proposes a patch card (field, old, new, reason). The reviewer clicks Confirm or Cancel. Confirm applies the patch, bumps `deal_version`, and re-runs from underwriting; Flow shows it live.
- Narrative edit: the chief proposes revised text; Confirm re-renders the memo only.
- Judgment override: requires a reason; creates an override record; numbers do not change.

## 4. API (FastAPI)
| Method and path | Purpose |
| --- | --- |
| `POST /api/deals` | Create a deal, returns `deal_id` |
| `POST /api/deals/{id}/chat` | External chat message; returns agent reply and checklist |
| `POST /api/deals/{id}/files` | Upload a file; returns label and checklist |
| `GET /api/deals` | Queue rows (`?include_archived=true` adds archived deals, flagged `archived`) |
| `DELETE /api/deals/{id}` | Archive a deal (a logged event, not a delete); 409 while the deal is running |
| `POST /api/deals/{id}/restore` | Undo an archive |
| `PATCH /api/deals/{id}` | Rename a deal (`{name}`, 1 to 80 characters) |
| `GET /api/deals/{id}` | Deal record, state, latest result and check report |
| `GET /api/deals/{id}/events` | Event history |
| `GET /api/deals/{id}/stream` | SSE for one deal |
| `GET /api/stream` | SSE for the queue |
| `GET /api/deals/{id}/artifacts/{memo.pdf or workbook.xlsx}` | Latest outputs |
| `POST /api/deals/{id}/chief-chat` | Internal chat; returns reply and optional patch proposal |
| `POST /api/deals/{id}/patches/{patch_id}/confirm` | Apply a proposed patch |
| `POST /api/deals/{id}/patches/{patch_id}/cancel` | Cancel a proposed patch |
| `POST /api/deals/{id}/decision` | Approve, send back, or reject |
| `GET /api/deals/{id}/intake-status` | Stage, one plain sentence and the checklist, for the external chat. Never ratios, reasons or a call |
| `GET /api/deals/{id}/workbook` | The workbook's cells as JSON (formula, recalculated value, number format) for the grid viewer |

SSE frames are named by event type; the payload is `{event_id, deal_id, ts, type, actor, summary, deal_version}`. The browser's `EventSource` only delivers named frames to a listener per type, so the hook lists the types from `docs/data-contracts.md`. The frontend types are generated from the OpenAPI spec (`make openapi`); CI fails if the spec or the generated types are stale.

## 5. Frontend structure
Hash routes (no router library): `#/` Queue, `#/chat[/D-0001]` intake, `#/deals/D-0001[/flow|review]` workspace.

`src/pages/{Chat,Queue,Workspace}.tsx`, `src/components/{Shell,FlowGraph,NodeDrawer,ChiefChat,MemoViewer,WorkbookViewer,ChecklistChips,Timeline,DecisionPackage,DecisionBar,Chips}.tsx`, `src/lib/{flow,metrics,format,router,samples}.ts`, `src/api/{client,hooks}.ts` plus the generated `schema.d.ts`. Tailwind only; no component library. Look and feel: charcoal and warm off-white, Mulish (a free stand-in for Avenir) with Poppins for the wordmark, hairline rules, square corners, outlined buttons and uppercase outlined status labels. The tokens live in `src/index.css`; the default Tailwind palettes are remapped there (slate to warm neutrals, teal to forest, amber to ochre, coral to brick, sky to navy), so the status colors are muted on purpose (decision D28). The Flow state is derived from the event log by pure functions in `lib/flow.ts`; the UI keeps no workflow state of its own.

Demo conveniences (none bypass the checklist or the rules): "Bronx / Queens / Brooklyn facts" chips fill the intake box with the facts a sponsor would type; suggested prompts sit above the chief chat; `make dev` sets `BRIDGE_STEP_DELAY` so each agent visibly works (default 1 s); `make dev-retry` forces the checker to disagree twice to show the retry loop and escalation (decisions D23, D24).

The memo opens in the browser's own PDF viewer (inline). The workbook viewer is read-only; formula cells are marked and show their formula on hover.

## 6. Priority order if time is short
Workspace (Flow and Review) first, then Queue, then Chat intake. A seeded queue and a scripted chat are acceptable for the demo.
