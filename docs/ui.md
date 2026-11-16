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
Table of deals: Deal, Stage, Call, Flags, Age, Owner. Filter chips: All, Needs review, Flagged. Search box. Row click opens the workspace. Updates live from the global event stream.

Stage chips: Awaiting docs, Extraction, Underwriting, Checker, Review. Call chips: Screen (teal), Watch (amber), Decline (coral).

## 3. Deal workspace (internal)
Header: deal id and name, tabs (Flow, Review), status chip. The chief chat is docked on the right on both tabs.

**Flow tab.** React Flow diagram: Chief in the center, Extraction, Underwriter, Checker around it, Intake chat and Human reviewer at the top. Node state: idle, running (amber), done (teal), failed (coral). Edges animate when a handoff is in flight. Clicking a node opens a drawer with the handoff envelope, tool calls (tool, inputs, formula, output), and result. A retry counter shows on the Checker to Underwriter loop.

**Review tab.** Left: progress timeline (Intake, Extraction, Underwriting, Checker, Your review). Center: tabs Memo and Workbook. The memo is a PDF viewer; the workbook is a read-only grid with formulas visible on hover. Each metric in the memo summary links to its formula, inputs, and source. Buttons: Approve, Send back, Reject.

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
| `GET /api/deals` | Queue rows |
| `GET /api/deals/{id}` | Deal record, state, latest result and check report |
| `GET /api/deals/{id}/events` | Event history |
| `GET /api/deals/{id}/stream` | SSE for one deal |
| `GET /api/stream` | SSE for the queue |
| `GET /api/deals/{id}/artifacts/{memo.pdf or workbook.xlsx}` | Latest outputs |
| `POST /api/deals/{id}/chief-chat` | Internal chat; returns reply and optional patch proposal |
| `POST /api/deals/{id}/patches/{patch_id}/confirm` | Apply a proposed patch |
| `POST /api/deals/{id}/decision` | Approve, send back, or reject |

SSE event payload: `{event_id, deal_id, ts, type, actor, summary, deal_version}`. The frontend types are generated from the OpenAPI spec.

## 5. Frontend structure
`src/pages/{Chat,Queue,Workspace}.tsx`, `src/components/{FlowGraph,NodeDrawer,ChiefChat,MemoViewer,WorkbookViewer,ChecklistChips,Timeline}.tsx`, `src/api/` (client, generated types, SSE hook). Tailwind only; no component library.

## 6. Priority order if time is short
Workspace (Flow and Review) first, then Queue, then Chat intake. A seeded queue and a scripted chat are acceptable for the demo.
