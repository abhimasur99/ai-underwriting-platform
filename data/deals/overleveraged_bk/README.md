# Sample deal: Brooklyn multifamily, should fail (D-0044)

Expected call: **Decline**. It is built to trip several rules at once so the memo has to list every reason. All data is fictional.

| Item | Value |
| --- | --- |
| Units | 22 (20 occupied) |
| Total cost (uses) | $4,600,000 ($4.0M purchase + $0.6M renovation) |
| Loan commitment | $4,050,000 ($3.45M initial advance + $0.6M holdback) |
| As-is value / ARV | $4,000,000 / $5,000,000 |
| Stabilized NOI (borrower pro forma) | $280,000 |
| LTC / LTV (as-is) / loan-to-ARV | 88.04% / 86.25% / 81.00% |
| Exit DSCR (NOI / payoff x take-out rate) | 1.15x |
| Take-out max (binding: debt yield) | $3,294,118, cushion -$755,882 |
| Rent roll vs T-12 gap | 12.99% |
| Sources vs uses gap | 3.26% (sources $4,450,000, uses $4,600,000) |

Expected reason codes: `LTC_DECLINE`, `LTV_AS_IS_DECLINE`, `LOAN_TO_ARV_DECLINE`, `EXIT_DSCR_WATCH`, `REFI_CUSHION_NEGATIVE_BASE`, `RENT_ROLL_VS_T12_DECLINE`, `SOURCES_VS_USES_DECLINE`.

Extra red flag, not coded in the MVP: the pro forma operating expenses ($120,000) are below in-place expenses ($150,000).

Files: `deal_summary.md`, `purchase_contract.md`, `rent_roll.csv`, `t12.csv`, `renovation_budget.csv`, `expected.json`.
