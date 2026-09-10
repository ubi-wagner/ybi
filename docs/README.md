# YBI Indirect Cost Rate Project — Documentation

Supporting documentation for a financial tool that builds and maintains a
defensible fully burdened indirect cost rate for **The Youngstown Edison Incubator
Corporation dba Youngstown Business Incubator ("YBI")**, for application to its
federal subawards under the America Makes / NCDMM program and to its other federal
and state funding.

> **Confidentiality.** This directory contains YBI's audited financial statements,
> general ledger, payroll-derived labor distribution, and executed federal
> sub-recipient agreements. The NCDMM agreements carry a restrictive legend
> limiting disclosure and use. Treat everything here as confidential.

## Contents

### `analysis/`

| Document | Description |
|---|---|
| [`indirect-cost-framework.md`](analysis/indirect-cost-framework.md) | Full analysis of 2 CFR 200 and DCAA/FAR rules on indirect cost buildup, and the allowability of restating prior-period rates away from the de minimis election |
| [`workpapers/fy2025_indirect_rate_scenarios.py`](analysis/workpapers/fy2025_indirect_rate_scenarios.py) | Reproducible FY2025 rate scenario model. Run with `python3` — no dependencies |

### `source-documents/`

**`awards/`** — executed NCDMM sub-recipient agreements

- `2023-09-08_NCDMM_SubRecipient_Agreement_Hybrid-Phase-2.pdf` — $500,043 federal
  + $104,000 cost share; term ended 2025-10-10
- `2024-09-24_NCDMM_SubRecipient_Agreement_Proj88_Last-Tactical-Mile.pdf` —
  $899,500 federal + $513,065 cost share; term ends 2026-12-23

**`financial-statements/`** — audited financial statements with Single Audit

- `2023_YBI_Audited_Financial_Statements_and_Single_Audit.pdf` — $1,012,543 total
  federal expenditures
- `2024_YBI_Audited_Financial_Statements_and_Single_Audit.pdf` — $4,114,007 total
  federal expenditures; Finding 2024-001 (material weakness), Finding 2024-002
  (late Single Audit submission)

**`tax-filings/`** — Forms 990 for 2023 and 2024 (ProPublica full filings)

**`accounting-records/`** — QuickBooks exports and the controller's workbook

- `2025_Profit-and-Loss_QuickBooks.xlsx`
- `2025_Balance-Sheet_QuickBooks.xlsx`
- `2025_General-Ledger_QuickBooks.xlsx`
- `2025_Grant-Reconciliation-Workbook_controller.xlsx` — labor distribution and
  billed-vs-actual reconciliation prepared by the controller

## Key figures

| | |
|---|---:|
| FY2025 fringe rate | **22.45%** |
| Indirect rate currently elected and audited | 10.00% |
| Rate implied by Project 88 unrecovered indirect cost share | 38.56% |
| Modeled FY2025 range (broad base) | **36% – 46%** |
| Billed-vs-actual overdraw across three grants | **$443,725.38** |

## Open items

Tracked in [`analysis/indirect-cost-framework.md` §9](analysis/indirect-cost-framework.md).
The blocking items are the third NCDMM agreement, the Hybrid Phase 2 Schedule B,
the workpaper behind the $233,543.12 unrecovered indirect figure, and a fixed
asset register tagged with funding source per asset.
