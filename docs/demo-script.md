# Demo script (about 3 minutes)

Audience: Justin Wolk, CapMoon. Frame it as a sample-data prototype with illustrative thresholds, built on my own time and devices. It is not CapMoon's real credit box and uses no employer data.

**Setup before the call:** `make demo` running, browser on the intake chat, deal queue empty, a terminal ready with `make test` output visible. Use cached mode unless the network is solid.

1. **The problem (20 s).** Bridge deals arrive as messy packages and the first pass is slow. The goal is to screen faster without letting a model do the math or make the call.
2. **Intake chat (30 s).** Open the external chat. Upload the Bronx package. The chat confirms the checklist as files land and asks for the one missing fact. No numbers or decisions are shown to the borrower side.
3. **Flow view (40 s).** Switch to the internal deal workspace, Flow tab. Show the hub-and-spoke: chief hands to extraction, underwriter, checker, with each handoff and tool call appearing live. Point out that agents never talk to each other directly.
4. **Review tab (50 s).** Show the one-page memo, metrics with formulas and sources, and the check report. Click a metric to show its inputs and the source row. Bronx is a Screen: LTC 70.65%, take-out max $8.24M, exit DSCR 1.79x.
5. **Chat edit (30 s).** In the chief chat: "Change unit 4 rent to 2,100." The chief proposes a patch; confirm; underwriting and check rerun; the memo updates. Mention versioning and that a human records the final decision.
6. **Range (20 s).** Run Queens (Watch: passes base case, fails the rate and NOI stress) and Brooklyn (Decline: leverage, rent roll gap, sources and uses). Show that each reason code maps to a rule.
7. **Close (10 s).** Code owns the math, the checker recomputes independently, models read and draft, humans decide. Next steps: real borrower package formats, more asset types, a deals tracker.

**If something breaks:** fall back to the pre-rendered memos in `data/runtime/outputs/` and walk the architecture doc instead. Do not debug live.

**Likely questions:** How do you handle scanned PDFs? (Next step: OCR then the same extraction path.) What stops hallucinated numbers? (Numbers only come from code or traced source fields; narrative uses placeholders; checker recomputes.) Why not one big prompt? (Auditability, testing, and independent checking.)
