# UI: screens, flows, API

Three screens for the MVP. The deals tracker (portfolio view for seniors) is deferred.

## 1. Chat intake (external)
The sponsor's page: the conversation on the left, and what has arrived and what was read from it on the right. The chat itself reports status; there is no separate status page.

```
+--------------------------------------+-----------------------------+
| Submit a bridge loan package         | Documents        3 of 5     |
|                                      |  [x] Deal summary   Replace |
|  Assistant: Thank you, I have your   |  [x] Purchase contract      |
|  deal summary. From it I read: ...   |  [ ] Rent roll      Choose  |
|                    You: thanks       |  ...                        |
|  Assistant: You are welcome. To      | Details we read             |
|  complete the package, please send.. |  Property address  88 Sample |
| [Attach] [ Type a message...  ][Send]|  Number of units   24  ...   |
+--------------------------------------+-----------------------------+
```
Behavior:
- **Documents:** one slot per required document; drop a file on a slot to file it as that document, or drop it in the chat and the assistant works out which it is. Accepted: PDF, Word, Excel, CSV.
- **Details we read:** the address, asset type, units, sponsor, requested loan amount, purchase price and renovation budget are read from the summary and contract as they arrive, each with the document and line it came from. The sponsor confirms by saying nothing, or corrects it in the chat (what the sponsor states wins over a document; a corrected document refreshes what was read). Five documents and no typing complete the package. If a document is in wording the parser does not know, nothing is guessed and the assistant asks.
- **The assistant** understands greetings, "what can you help with", "what is missing", "what happens next", status, thanks, and decision questions, and answers each in plain business English that says where things stand and what comes next. It never gives a decision, a rate, a ratio or a timeline (decision D40).
- Status updates ("with our team for review", "The team has a question: ...") are posted into the chat from deal state. The external chat never shows ratios, reasons, or a decision.
- The conversation is kept, so a reload restores it. Handles: file type or size rejected, duplicate upload (by content), a file that looks like the wrong type (asks to confirm), a PDF with no table or no text (says what to send instead).

## 2. Queue (internal)
Table of deals: Deal, Next action, Call, Exceptions, Age, Owner, sorted so the deals that need the reviewer come first. Next action says what happens next and who must act ("Your review", "Waiting on sponsor: ...", "Running", "Done: approved"); it is a projection of the event log. Filter tabs with counts: All, Needs your review, Exceptions, Archived. Search box. Row click opens the workspace. Updates live from the global event stream.

**Housekeeping.** A deal is never deleted (the event log is append-only and ids are never reused), so "delete" is archive: a logged `deal.archived` event hides the deal from the queue; the Archived tab lists it and Restore undoes it. Each row has an Archive link; checkboxes allow bulk archive; every archive shows an Undo notice. A deal that is mid-run cannot be archived (409). A deal can be renamed by clicking its title in the workspace. Opening the intake page does not create a deal: it is created on the first message or upload, so browsing to New deal and leaving leaves nothing behind (decision D27).

Call chips: Screen (green), Watch (ochre), Decline (brick).

## 3. Deal page (internal)
Chat on the left, the deal on the right. Back and previous are on the left, next on the right (decision D33).

```
+--------------------------------------------------------------------------------------+
| <- Deal queue   <- Previous                              Next needing review (n) ->  |
| Deal name (click to rename)  D-0045 v1  [Your review]   [More] [?] [Reject] [Request |
|                                                          info] [Approve]             |
| Call [Screen]  [Checker agrees]  0 exceptions  0 questions for the sponsor  rules 0.1 · v1 |
+--------------+-----------------------------------------------------------------------+
| Chief chat   | Memo | Calculations | Files | Process                                  |
| (collapsible)|  tab content                                       | Review           |
|              |                                                    |                  |
+--------------+----------------------------------------------------+------------------+
```

**Header (every tab).** The deal name, id and version, one status chip (the queue's Next action), and the decision: **Reject** on the left, **Request info**, **Approve** on the right (the primary action rightmost). Approve and Reject ask once before they act; Request info opens a dialog for the note. **More** holds the memo and workbook downloads, re-run, and archive. A deal that is decided shows its outcome instead of the buttons. The **?** explains each action.
- **Approve** records the approval and closes the deal; a released snapshot is saved beside the memo. Nothing leaves the app.
- **Request info** asks the sponsor for something. The note appears in their intake chat and the deal waits (`NEEDS_INPUT`). A reply in words returns it to the reviewer at the same version (nothing is re-extracted, so confirmed edits are safe); a new file is read again as the next version. An upload that is refused or a duplicate keeps the deal waiting (decision D36).
- **Reject** closes the deal as rejected. Approved and rejected deals are final.

**Summary strip.** Call, checker status, exceptions, questions for the sponsor, and "Model-read fields: please confirm" when a model read any field. It replaces the status that used to be repeated in the header, a timeline and the graph.

**Memo.** The one-page PDF, with the **Review** panel on the right: questions for the sponsor (each can be sent with one click), exceptions, and the key metrics that drive the call against their thresholds.

**Calculations.** Metrics with their formulas and inputs. Each input offers **View in the document**, which opens the Files tab on the exact line it was read from. A toggle shows the workbook behind the numbers.

**Files.** The uploaded documents as the platform read them (text, or a table with the header as row 1), numbered the way every source citation numbers them. The line a number came from is highlighted.

**Process.** For audit and for the demo: the agent graph (Chief in the center, never agent to agent), a drawer per node with handoffs and tool calls, and a history in plain words ("Asked Checker to check the numbers independently", "Asked the sponsor: ...") with the raw events one click away.

**Chief chat (internal).** Free text, docked on the left and collapsible (the choice is remembered), and the conversation is kept across reloads. The chief classifies the message into: question (answered from the deal record), data edit, narrative edit, judgment override, or action (approve, request info, which it points you to the button for). A question can be about a metric, why the call is what it is, a summary, the exceptions and questions for the sponsor, **what changed in this version**, or what the chief can do. Each answer offers follow-up questions as buttons; after a confirmed edit the chat shows a before and after card (the input that moved, the metrics that moved with it, and whether the call changed). Every figure in an answer comes from a calculation.
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
| `POST /api/deals/{id}/chief-chat` | Internal chat; returns reply, suggestions and optional patch proposal, what-if outcome or sizing |
| `GET /api/deals/{id}/reply-draft` | The draft reply to the broker for an approved or rejected deal (null before a decision): `decision`, `text`, `status` (draft or approved), `wording` (template or claude), `edited` |
| `POST /api/deals/{id}/reply-draft` | Draft the reply, or start over on it (409 before a decision) |
| `PUT /api/deals/{id}/reply-draft` | The reviewer's edited text (422 if empty or too long); status returns to draft |
| `POST /api/deals/{id}/reply-draft/approve` | Record the reviewer's approval of the wording (422 while a `[blank]` is left). Nothing is ever sent |
| `POST /api/deals/{id}/what-if` | Try different assumptions (`{params: {name: value}}`); returns the current case against the changed one. Saves nothing; 422 for an unknown or out-of-range assumption |
| `GET /api/deals/{id}/max-loan?target=screen\|watch` | The largest loan that still reaches the target call, found by re-applying the rules. Saves nothing |
| `POST /api/deals/{id}/patches/{patch_id}/confirm` | Apply a proposed patch |
| `POST /api/deals/{id}/patches/{patch_id}/cancel` | Cancel a proposed patch |
| `POST /api/deals/{id}/decision` | `approve`, `reject`, `request_info` (note required) or `send_back` (re-run) |
| `GET /api/deals/{id}/intake-status` | Stage, one plain sentence, the checklist, the details read (with their sources) and the files received, for the external chat. Never ratios, reasons or a call |
| `GET /api/deals/{id}/transcript` | The sponsor's conversation only (what they said, what the assistant said, files received), so the intake page can restore it |
| `GET /api/deals/{id}/chief-transcript` | The reviewer's conversation with the chief |
| `GET /api/deals/{id}/changes` | What the latest version changed: the inputs that moved, the metrics that moved, the call before and after |
| `GET /api/deals/{id}/files/{file_id}/text` | A document as numbered lines (text, or a table with the header as row 1) for the Files tab |
| `GET /api/deals/{id}/workbook` | The workbook's cells as JSON (formula, recalculated value, number format) for the grid viewer |

SSE frames are named by event type; the payload is `{event_id, deal_id, ts, type, actor, summary, deal_version}`. The browser's `EventSource` only delivers named frames to a listener per type, so the hook lists the types from `docs/data-contracts.md`. The frontend types are generated from the OpenAPI spec (`make openapi`); CI fails if the spec or the generated types are stale.

## 5. Frontend structure
Hash routes (no router library): `#/` Queue, `#/chat[/D-0001]` intake, `#/deals/D-0001[/memo|calculations|files|process]` the deal page (old `/review`, `/flow` and `/numbers` links still work).

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
