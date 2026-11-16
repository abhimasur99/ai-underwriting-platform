# Sample deal: Queens mixed-use (D-0043)

Expected call: **Watch**. It passes every leverage test and the base-case exit, but the refinance cushion turns negative under stress. All data is fictional.

| Item | Value |
| --- | --- |
| Units | 20 (18 residential, 2 retail; 19 occupied) |
| Total cost | $5,800,000 ($5.0M purchase + $0.8M renovation) |
| Loan commitment | $4,300,000 ($3.5M initial advance + $0.8M holdback) |
| As-is value / ARV | $5,000,000 / $7,000,000 |
| Stabilized NOI (borrower pro forma) | $400,000 |
| LTC / LTV (as-is) / loan-to-ARV | 74.14% / 70.00% / 61.43% |
| Debt yield (stabilized) | 9.30% |
| Take-out max (binding: debt yield) | $4,705,882, cushion $405,882 |
| Stress (NOI -10%, rate +100 bps) | take-out $4,114,286, cushion -$185,714 |

Expected reason code: `REFI_CUSHION_NEGATIVE_STRESS`.

Reconciliation: rent roll vs T-12 gap is 2.00% (pass). Sources equal uses.

Files: `deal_summary.md`, `purchase_contract.md`, `rent_roll.csv`, `t12.csv`, `renovation_budget.csv`, `expected.json`.
