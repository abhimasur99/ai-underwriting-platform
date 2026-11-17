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
Table of deals: Deal, Next action, Call, Flags, Age, Owner, sorted so the deals that need the reviewer come first. Next action says what happens next and who must act ("Your review", "Waiting on sponsor: ...", "Running", "Done: approved"); it is a projection of the event log. Filter tabs with counts: All, Needs your review, Flagged, Archived. Search box. Row click opens the workspace. Updates live from the global event stream.

**Housekeeping.** A deal is never deleted (the event log is append-only and ids are never reused), so "delete" is archive: a logged `deal.archived` event hides the deal from the queue; the Archived tab lists it and Restore undoes it. Each row has an Archive link; checkboxes allow bulk archive; every archive shows an Undo notice. A deal that is mid-run cannot be archived (409). A deal can be renamed by clicking its title in the workspace. Opening the intake page does not create a deal: it is created on the first message or upload, so browsing to New deal and leaving leaves nothing behind (decision D27).

Call chips: Screen (green), Watch (ochre), Decline (brick).

## 3. Deal page (internal)
Chat on the left, the deal on the right. Back and previous are on the left, next on the right (decision D33).

```
+--------------------------------------------------------------------------------------+
| <- Deal queue   <- Previous                              Next needing review (n) ->  |
| Deal name (click to rename)  D-0045 v1  [Your review]   [More] [?] [Reject] [Request |
|                                                          info] [Approve]             |
| Call [Screen]  [Checker agrees]  0 flags  0 open questions      rules 0.1 · version 1 |
+--------------+-----------------------------------------------------------------------+
| Chief chat   | Memo | Numbers | Files | Process                                       |
| (collapsible)|  tab content                                       | Needs your       |
|              |                                                    | attention        |
+--------------+----------------------------------------------------+------------------+
```

**Header (every tab).** The deal name, id and version, one status chip (the queue's Next action), and the decision: **Reject** on the left, **Request info**, **Approve** on the right (the primary action rightmost). Approve and Reject ask once before they act; Request info opens a dialog for the note. **More** holds the memo and workbook downloads, re-run, and archive. A deal that is decided shows its outcome instead of the buttons. The **?** explains each action.
- **Approve** records the approval and closes the deal; a released snapshot is saved beside the memo. Nothing leaves the app.
- **Request info** asks the sponsor for something. The note appears in their intake chat and the deal waits (`NEEDS_INPUT`). A reply in words returns it to the reviewer at the same version (nothing is re-extracted, so confirmed edits are safe); a new file is read again as the next version. An upload that is refused or a duplicate keeps the deal waiting (decision D36).
- **Reject** closes the deal as rejected. Approved and rejected deals are final.

**Summary strip.** Call, checker status, flags, open questions, and "Model-read fields: please confirm" when a model read any field. It replaces the status that used to be repeated in the header, a timeline and the graph.

**Memo.** The one-page PDF, with the attention panel on the right: open questions (each can be put to the sponsor with one click), flags, and the numbers that drive the call against their thresholds.

**Numbers.** Metrics with their formulas and inputs. Each input offers **View in the document**, which opens the Files tab on the exact line it was read from. A toggle shows the workbook behind the numbers.

**Files.** The uploaded documents as the platform read them (text, or a table with the header as row 1), numbered the way every source citation numbers them. The line a number came from is highlighted.

**Process.** For audit and for the demo: the agent graph (Chief in the center, never agent to agent), a drawer per node with handoffs and tool calls, and a history in plain words ("Asked Checker to check the numbers independently", "Asked the sponsor: ...") with the raw events one click away.

**Chief chat (internal).** Free text, docked on the left and collapsible (the choice is remembered). The chief classifies the message into: question (answered from the deal record), data edit, narrative edit, judgment override, or action (approve, request info).
- Data edit: the chief proposes a patch card (field, old, new, reason). The reviewer clicks Confirm or Cancel. Confirm applies the patch, bumps `deal_version`, and re-runs from underwriting.
- Narrative edit: the chief proposes revised text; Confirm re-renders the memo only.
- Judgment override: requires a reason; creates an override record; numbers do not change.

**Accessibility.** The tabs follow the WAI-ARIA tab pattern (arrow keys, Home and End); the Request info dialog is the browser's own modal dialog (focus trap, Escape); new chat messages are announced; text colors meet WCAG AA contrast (checked, not assumed); the system's reduced-motion setting is honored. Checked at 1280x800 and 1440x900 (decision D37).

## 4. API (FastAPI)
| Method and path | Purpose |
| --- | --- |
| `POST /api/deals` | Create a deal, returns `deal_id` |
| `POST /api/deals/{id}/chat` | External chat message; returns agent reply and checklist |
| `POST /api/deals/{id}/files` | Upload a file; returns label and checklist |
| `GET /api/deals` | Queue rows with `next_action` and `needs_you`, those needing the reviewer first (`?include_archived=true` adds archived deals) |
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
| `POST /api/deals/{id}/decision` | `approve`, `reject`, `request_info` (note required) or `send_back` (re-run) |
| `GET /api/deals/{id}/intake-status` | Stage, one plain sentence and the checklist, for the external chat. Never ratios, reasons or a call |
| `GET /api/deals/{id}/files/{file_id}/text` | A document as numbered lines (text, or a table with the header as row 1) for the Files tab |
| `GET /api/deals/{id}/workbook` | The workbook's cells as JSON (formula, recalculated value, number format) for the grid viewer |

SSE frames are named by event type; the payload is `{event_id, deal_id, ts, type, actor, summary, deal_version}`. The browser's `EventSource` only delivers named frames to a listener per type, so the hook lists the types from `docs/data-contracts.md`. The frontend types are generated from the OpenAPI spec (`make openapi`); CI fails if the spec or the generated types are stale.

## 5. Frontend structure
Hash routes (no router library): `#/` Queue, `#/chat[/D-0001]` intake, `#/deals/D-0001[/memo|numbers|files|process]` the deal page (old `/review` and `/flow` links still work).

```
src/ui/          shared kit: Button, Chip, Tabs (ARIA), Dialog, Shell (top bar and page frame)
src/features/    queue/, intake/ (chat, checklist), deal/ (page, header, tabs, chat pane, dialogs)
src/lib/         pure logic with unit tests: flow, log, nav, dealTabs, tabs, locator, format
src/api/         typed client, hooks (SSE), generated schema.d.ts
```
Tailwind only; no component library. Look and feel: charcoal and warm off-white, Mulish (a free stand-in for Avenir) with Poppins for the wordmark, hairline rules, square corners, outlined buttons and uppercase outlined status labels. The tokens live in `src/index.css`; the default Tailwind palettes are remapped there, so the status colors are muted on purpose (decision D28). The Flow state and the readable history are derived from the event log by pure functions; the UI keeps no workflow state of its own.

Tests: `npm test` runs the unit tests of the pure logic (vitest); `make e2e` runs a browser smoke test of the demo path locally (Playwright, not in CI; run `make demo` first).

Demo conveniences (none bypass the checklist or the rules): "Bronx / Queens / Brooklyn facts" chips fill the intake box with the facts a sponsor would type; suggested prompts sit above the chief chat; `make dev` sets `BRIDGE_STEP_DELAY` so each agent visibly works (default 1 s); `make dev-retry` forces the checker to disagree twice to show the retry loop and escalation (decisions D23, D24).

The memo opens in the browser's own PDF viewer (inline). The workbook viewer is read-only; formula cells are marked and show their formula on hover.

## 6. Priority order if time is short
Workspace (Flow and Review) first, then Queue, then Chat intake. A seeded queue and a scripted chat are acceptable for the demo.
