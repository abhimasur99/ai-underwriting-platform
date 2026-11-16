# Decisions

| # | Decision | Why | Revisit when |
| --- | --- | --- | --- |
| D1 | Use the plain `anthropic` SDK with tool use, not Google ADK | Claude is the only model; one API key; we own the control loop and the event log. ADK would need LiteLLM or a Google Cloud setup for Claude and its own session and event model. | The team is on Google Cloud or Gemini, or we want ADK's built-in evals and dev UI |
| D2 | Do not use the Claude Agent SDK | It is built around coding-style agents with file and shell tools, which we do not need | Agents need open-ended tool use |
| D3 | React and Vite frontend with a FastAPI backend, not Streamlit | Better demo: React Flow can animate handoffs, docked chat and viewers are easier. Costs about 30 to 45 minutes more. | Time runs short; fall back per the cut line in `docs/sprints.md` |
| D4 | Hub-and-spoke: all handoffs go through the chief | One place for state, permissions, and audit; no agent-to-agent drift | Never for the MVP |
| D5 | The chief is a code state machine with a model only for chat intent and wording | Predictable, testable, cheap, explainable | Routing becomes genuinely ambiguous |
| D6 | The checker has its own deterministic tools and an independent parse and formula path | A checker that shares code with the underwriter repeats its bugs | Never |
| D7 | External UI is the chat only; chat reports checklist and status | Simpler; fewer screens to secure | Borrowers need document history |
| D8 | Deals tracker screen deferred | Not needed for the MVP demo | After the MVP |
| D9 | SQLite plus an append-only event log; queue is a view | Simple, auditable, enough for localhost | Multiple users or hosted deployment |
| D10 | Cached fixtures for every agent; `--live` calls Claude | Demo and CI work offline and are repeatable | Never |
| D11 | Thresholds live in `config/rules.yaml` and are labeled illustrative | The real lender's box is unknown | After discovery with the lender |
| D12 | Memo narrative uses number placeholders; code fills numbers; a test rejects stray digits | Models must not type numbers | Never |
| D13 | MVP uses the borrower's pro forma NOI and ARV as given | Keeps scope small | A real underwriting haircut is added |
| D14 | LTV is initial advance divided by as-is value; LTC and loan-to-ARV use the full commitment | Bridge convention with a renovation holdback | The lender defines it differently |
| D15 | Exit DSCR is stabilized NOI divided by (payoff times take-out rate); take-out max is the smallest of DSCR, LTV, and debt-yield caps | Tests whether the property can refinance out the bridge balance | The lender uses a different exit test |
| D16 | Rent roll vs T-12 gap above 10% is a decline reason; 5 to 10% is a watch reason | Data integrity failures should stop a deal | Lender tolerances are known |
