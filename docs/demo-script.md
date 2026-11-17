# Demo script (about 3 to 4 minutes)

Frame it as a sample-data prototype with illustrative thresholds, built on my own time and devices. It is not any firm's real credit box and uses no employer data.

**Before the call**
- `make demo`, then `make dev` (offline: free and reliable). Use `make dev-live` only if the network is solid; the numbers are the same either way.
- Browser on the deal queue, a Finder window open on `data/deals/ridgewood_missing_arv/` (and its `followup/` folder). Rehearse once; `make demo` resets everything.
- If something breaks, do not debug live: open a seeded deal and walk the memo and `docs/architecture.md` instead.

## The flow
1. **The problem and the queue (20 s).** Bridge deals are won on speed, and the first pass is mostly mechanical. The queue has 10 deals with a realistic mix of Screen, Watch and Decline. The Next action column says who must act; deals that need me come first.
2. **A sponsor sends a package (50 s).** New deal. Drop the five Ridgewood files (PDF and Excel). The assistant files each one, reads the address, units, sponsor and loan from the documents, and answers politely. Point out what it does not do: no call, no ratio, no rate. The deal stops: the summary leaves out the after-repair value, and the system asks instead of guessing. In the queue the deal reads "Waiting on sponsor". Drop `followup/deal_summary.pdf` and it runs.
3. **The result, and why to trust it (45 s).** Open the deal: a Screen with the checker agreeing. Memo first: leads with the exit. On Calculations, click **View in the document** on an input and land on the exact source line. Process tab (10 s): the chief in the center, extraction, underwriter and checker around it, never agent to agent; open one tool call to show the formula and inputs.
4. **Ask the chief (60 s).** In the chat on the left:
   - "What if the take-out rate is 7%?" The card shows the exit and cushion moving and the call going from Screen to Watch, marked **not saved**. This is the moment that shows the engine: same underwriting, exact numbers, nothing changed.
   - "What is the largest loan that still screens?" The answer is $2,850,000 against the $2,600,000 request, and names the limit that binds (loan to cost).
   - "Change the ARV to 4,200,000 because the appraisal came in lower." The chat proposes the change; Confirm. A new version, the checker re-runs, and the before and after card shows what moved (the call stays Screen).
5. **Decide, and the reply (30 s).** Approve. The draft reply to the broker opens: next steps, my open questions, no figures, "not a commitment to lend". Fill in the name and title, **Approve wording**, and point at "Nothing is sent from this app."
6. **Range and close (15 s).** Open Brooklyn (Decline, built to trip several rules: the memo lists every reason) or Mount Vernon (leverage is fine, but the exit fails). Close: code owns the math, a second implementation checks it, models read and word, people decide. Next: real package formats, more asset types, a portfolio tracker.

## Likely questions
- **Scanned PDFs?** Refused with a reply saying what to send; the next step is OCR into the same extraction path.
- **What stops invented numbers?** Numbers come only from code or from a source field with its line; narrative uses placeholders; the checker recomputes; every model answer is validated.
- **Why not one big prompt?** Auditability, testing, and independent checking.
- **Are these CapMoon's rules?** No. The thresholds are illustrative and the data is made up.
- **Does it send anything?** No. The broker reply is a draft for a person.

## Optional extras if there is time
- Request info on a Watch deal (the note appears in the sponsor's chat; a reply returns it to review).
- Show the Files tab: the documents as the platform read them, with the cited line highlighted.
- `make dev-retry` to show the checker disagreeing, the retry, and the escalation badge.
