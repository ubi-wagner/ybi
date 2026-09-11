# Plan

Execution plan for Claude Code. Revised after the P&L, balance sheet and sample
invoices landed. Read `BRIEF.md` for orientation and `PROJECT_CONTEXT.md` for
the numbers.

Every phase has an **acceptance criterion that is a number or a test**, not a
judgement. If it does not tie, the phase is not done.

---

## What changed with the last upload

Four findings that reshape the plan:

1. **Invoices carry separate lines** — Labor, Travel, Materials, Consultant,
   ODCs, Indirects. The controller's grant tabs track **only the labor line**.
   Invoice 10018 (Drive AM) bills Labor 18,448.11 **plus ODCs 19,145.79**. That
   is the $1.16M reconciliation gap.
2. **Hybrid ties to $100.** P&L revenue 191,638.05 against tab billings
   191,738.17. Hybrid genuinely is labor-only, so its over-billing conclusion
   stands and can proceed independently of everything else.
3. **$451,170 is not America Makes.** The P&L shows it as `4801 IH Grant
   Income` under Innovation Hub. The revenue ledger mis-attributes it to NCDMM.
4. **LTM already bills an `Indirects` line** — 3,000.00 on invoice 10039. There
   is precedent for indirect billing to NCDMM. The restatement is a change of
   basis, not the introduction of a new concept.

Plus: the balance sheet finally answers the depreciation question, and
`2004 5th Bldg Loan — 772,315` puts most of the 49,001 interest expense in play
as allowable facilities cost under 200.449 rather than unallowable.

---

## Phase 0 — Intake (human, blocking)

Drop into `/intake/` (gitignored). Contracts are too long for chat; Claude Code
reads them from disk.

| Path | Contents | Blocks |
|---|---|---|
| `/intake/contracts/` | Drive AM (**PO 20240119**), Last Tactical Mile (**PO 20250018**), Digital Engineering, Hybrid Phase 3, AM Workforce — agreements, incorporated cost proposals, all modifications | Phases 3, 6 |
| `/intake/invoices/` | Every invoice to NCDMM, all awards, 2024–2025, same format as the samples. PDF is fine. | Phase 2 |
| `/intake/2025/qbo/` | GL, P&L, BS, Trial Balance, Chart of Accounts, Transaction List by Vendor, Customer list with sub-customers, A/R Aging Detail | Phase 1 |
| `/intake/2024/qbo/` | Same set. Most of Hybrid Phase 2 sits in 2024. | Phase 5 decision |
| `/intake/assets/` | Fixed asset register with **funding source per asset**, grant award docs for any funded asset, debt schedule | Phase 5 |
| `/intake/facilities/` | Floor plan with SF by suite, rent roll, lease schedule | Phase 5 |
| `/intake/payroll/` | Payroll register by employee by pay period 2024–2025, employer tax and benefit cost by employee, employee roster | Phase 4 |

**Never commit `/intake/`.** Payroll and certifications route to the bucket via
the upload endpoint.

---

## Phase 1 — Ingest and reconcile

**Goal.** GL, P&L and balance sheet in Postgres, controls derived from source
rather than a seeded CSV.

### Tasks

- Extend `app/domain/qbo.py` with `parse_profit_loss()` and
  `parse_balance_sheet()`. Both are indented hierarchies with `Total for X`
  rollup rows — same shape as the GL parser, no account section headers.
  Two-column layout: label, amount.
- Handle the account-number defects in the source: `5107 Interest Income` and
  `5108 Other Income` are revenue sitting in the 5xxx expense range;
  `3991 MBAC` is income in the net-assets range. Map by statement section, not
  by number.
- New table `asset` (migration `005_assets.sql`): account, description, gross
  cost, accumulated depreciation, in-service date, life, method, **funding
  source**, funding award reference, `federally_funded boolean`.
- Seed from the balance sheet, leaving `funding_source` null — it is the human
  input from `/intake/assets/`.
- Add `POST /api/imports/{batch_id}/parse` support for `PROFIT_LOSS` and
  `BALANCE_SHEET` report types.

### Acceptance

- P&L income total = **6,662,593.00**, expenses = **6,737,951.18**, net =
  **4,329.28**
- Balance sheet: assets = liabilities + equity = **16,713,219.80**
- Gross depreciable basis from the asset table = **23,189,122.50**
- Control register built from the imported P&L, not from `PL_2025_CONTROL.csv`
- Existing 21 tests still pass

### Cross-reference reconciliation — done

Ten points where the three source documents have to agree, in
`v_statement_reconciliation`, read at `/reconcile` and printed as Schedule
A-1. `scripts/reconcile.py` runs them and exits non-zero when one is open, so
it can gate a deploy. `POST /api/rates/compute` refuses while any point is
open: a rate over a ledger that does not agree with its own statements is a
rate over the wrong numbers.

Measured on the 2025 export, in the order it was found:

| Point | Result |
| --- | --- |
| P&L foots to the net income the sheet carries | 4,329.28 both ways |
| Balance sheet balances | 16,713,219.80 both ways |
| Every staged line reached the ledger | 15,500 = 15,500 |
| Printed account totals vs parsed lines | 14,371,299.30, no mismatches |
| Ledger vs P&L by section | 13,554,753.64 both ways |
| Ledger vs P&L by account | 5 accounts, 7,469.87 gross, all named |
| Every P&L account exists on both sides | no orphans either way |
| Opening + movement vs the balance sheet | 71 accounts, none off |
| Accounts the sheet omits | 4, each closing at 0.00 |
| Segmentation | 14,371,299.30 both ways |

Two defects surfaced and were fixed on the way:

- **71 lines, $24,082.67, lost on promote.** A line's natural key hashed date,
  type, num, name, account, amount and memo — so two genuinely identical
  lines (two $100 ticket sales, two equal splits of one entry) collided, and
  `ON CONFLICT DO NOTHING` kept one. 58 keys collided. `StagedLine.occurrence`
  numbers the repeats, and the accept path now refuses to promote at all if
  the ledger ends up short.
- **The balance sheet could not be tied to anything.** The parser discarded
  the GL's "Beginning Balance" rows as non-transactions, which they are — and
  which left no way to compare a position to a year of movement. They are kept
  in `gl_opening`, and every one of the 71 printed balance-sheet accounts is
  now proved off the ledger rather than trusted.

The five accounts that differ are *not* netted away. Each is a
`reconciling_item` naming the ledger lines behind it, and a deferred trigger
refuses one whose lines do not add to the amount claimed. Ten lines in all —
two conference tickets and an accelerator fee to ESP, Detroit mileage and a
hotel to travel, a print job to advertising, two subscriptions to staff
training — reclassified out of Rising Tides Expense between the two exports.

---

## Phase 2 — Invoice register (the critical path)

**Goal.** Every invoice line, by award, by month, by budget category. This is
what closes the reconciliation and it gates Phase 6.

### Tasks

- Migration `006_invoices.sql`: extend `invoice` with `po_number`,
  `bill_to_name`, `bill_to_address`, `terms`, `paid_at`; add `invoice_line`
  (invoice_id, activity, description, category, qty, rate, amount, sequence).
- Category enum matching the invoice format: `LABOR`, `TRAVEL`, `MATERIALS`,
  `CONSULTANT`, `ODC`, `INDIRECT`, `SUBAWARD`, `OTHER`.
- `app/domain/invoice_parse.py` — extract line items from the PDF invoices.
  They are QuickBooks-generated and structurally consistent: header block, then
  an ACTIVITY / DESCRIPTION / QTY / RATE / AMOUNT table, then PAYMENT and
  BALANCE DUE. Parse the `PAID` stamp where present.
- Reconciliation view `v_award_reconciliation`: per award per period —
  invoiced by category, revenue recognised from the ledger, variance.
- Flag every invoice with a bill-to other than NCDMM Johnstown. Invoice 10023
  bills Hybrid to 236 W Boardman Street with no PO and Net 30 instead of Net 60;
  the P&L shows `4026 NAMII Rent Boardman St. 108,000`, so America Makes leases
  that building. Confirm which entity pays before treating it as award billing.

### Acceptance

- Total invoiced per award reconciles to P&L grant income **within $500**:
  Drive AM 579,240.87 · Digital Engineering 579,074.25 · Last Tactical Mile
  368,222.24 · Hybrid Energy 191,638.05 · AM Workforce 28,063.50
- The 1,160,095 currently unexplained is attributed to specific invoice lines
- Every invoice carries a category breakdown; no invoice is labor-only unless
  the source is labor-only

---

## Phase 3 — Contract terms and ceilings

**Goal.** Ceilings are the binding parameter of the restatement. Only Hybrid
Phase 2's 500,043 is currently known.

### Tasks

- Read each agreement from `/intake/contracts/`. Extract into `award` and
  `award_budget_line`: ceiling, cost share, period of performance, instrument
  type, rate method, budget by line, PO number, citation.
- Record the **incorporated cost proposal** for each award as evidence, and
  extract whether labor rates are loaded. This decides whether Hybrid is an
  over-billing at all.
- Extend the constraint tests in `app/domain/awards.py` with
  `BUDGET_CATEGORY` — claims by category against the approved budget line, per
  4.2 of the agreements.

### Acceptance

- Every award with 2025 revenue has a row in `award` with a non-null ceiling
- Each `award_budget_line` sums to the award's federal ceiling
- Constraint results exist for all five awards, not just Hybrid

---

## Phase 2b — GL explorer and evidence desk

**Goal.** The analysis surface. Before classifying anything you need to be able
to look at 15,500 rows and see shape — by account, vendor, objective, pool,
month — and drill from a pool balance to the lines behind it.

### Tasks

- `GET /api/ledger/explore` — server-side pivot. Group by any of
  account · vendor · objective · pool · month · 990 function, filter on any
  combination, drill to lines. Cursor pagination; 15,500 rows will not go over
  the wire at once.
- **GL explorer page.** Dense table (`.dense`), pool colour stripe per row,
  group/ungroup, running subtotals, saved views. Click a subtotal to drill.
- **Evidence desk page.** The API is built (`/api/evidence/*`) and has no UI.
  Drag-drop onto any target, thumbnails, extracted-text search, and the
  documented-dollars coverage bar per pool from `v_evidence_coverage`.
- Bulk evidence matching — drop a folder of invoices, propose matches on
  amount, date proximity and vendor similarity, confirm in bulk.
- General document intake for contracts, floor plans, asset schedules — the
  things that are evidence but not ledger.

### Acceptance

- Any pool balance drills to the ledger lines composing it, and they sum
- Explorer renders 15,500 rows without a full fetch
- Evidence coverage reports documented **dollars** by pool, not row counts
- A contract PDF can be attached to an award and read back

---

## Phase 4 — Classification and certification

**Goal.** Four dimensions on every ledger line, and defensible labor.

### Tasks

- Run the classification queue against the imported GL. Priority order: the top
  200 account-vendor groups, then `5227 Portfolio consulting` (588,539 across
  442 lines, swings the rate between 28.09% and 44.90% — largest single lever
  and needs no external document).
- Reclassify interest: `2004 5th Bldg Loan — 772,315` is building debt.
  Under 200.449 the associated interest is allowable facilities cost, not
  unallowable. Split the 49,001 by debt purpose and cite it.
- Migration `007_time_certification.sql`: `time_entry` (employee, period,
  objective, hours, employer_directed boolean) and `certification` (employee,
  period, total_hours, attestation_text, signed_at, signed_by,
  supervisor_signed_at).
- **The attestation must cover total activity**, not the federal slice — 2 CFR
  200.430(i)(1)(iii). A certification that only covers federal hours proves
  nothing about the denominator.
- Effective rate per employee-period = compensation ÷ **total hours worked**.
  Keep actual hours in the record; derive dollars from the rate. Do not scale
  hours down to a standard month — that produces the right dollars and destroys
  the evidence.
- Certification targets: CEO 50% G&A / 15% fundraising / 10% facilities;
  program director 30% G&A; timesheet staff 5% general floor; single-assertion
  staff 10%.

### Colour and speed — not cosmetics

- **One pool colour language everywhere.** `web/src/components/pool.jsx` and
  the `--pool-*` tokens in `theme.css`. Row stripe in tables, chip on values,
  identical in the GL explorer, the queue, the allocation schedule and the
  crosswalk. The abbreviation always travels with the colour, so greyscale
  printing and colour vision deficiency both still read.
- **Keyboard-first queue.** `j`/`k` move, `Enter` accepts the proposal, `e`
  edits, `x` selects, `1`–`8` jump to a pool, `f` toggles focus, `/` searches.
  Roughly 200 meaningful decisions — the difference between two keystrokes and
  six clicks is an afternoon versus a week.
- **Capture the 2026 account on the decision.** Add `target_account_2026` to
  `decision`, defaulted from `domain/chart.py` by pool. The crosswalk then
  builds itself from real judgments rather than the static map in
  `domain/crosswalk.py` — and Phase 8 becomes an export instead of a project.
- Bulk apply across selected groups; undo on every action.

### Acceptance

- Dollar coverage ≥ 80% before sealing
- Zero ledger lines defaulted into a pool without a decision
- Certifications on file for the seven people carrying ~100% of federal labor —
  Gaffney, Longo, Engel, Negro, Jaric, Kale, Sprowl
- Distributed labor ties to the wage control **1,789,993.94**, with the
  45,000.03 non-payroll credit disclosed as a reconciling item

---

## Phase 5 — Rate build

**Goal.** One sealed rate with documented carve-outs.

### Tasks

- Wire `POST /api/rates/compute` to `domain/pools.py`, persisting `rate` and
  `allocation` rows with the seal hash.
- Carve-outs from evidence rather than estimate: facilities by square footage
  from `/intake/facilities/`, depreciation by funding source from the asset
  table.
- **Tech Block Building 5 is 8,922,680 — 38.5% of the depreciable basis.** If
  publicly funded, 327,209 of depreciation is unallowable and the rate falls
  about 2.9 points. The balance sheet carries `1120 A/R EDA Grant — Federal`,
  so a federal EDA relationship exists. Resolve this asset first.
- Decide and record: 2024 pools, or leave 2024 at de minimis. Most of Hybrid
  Phase 2 sits in 2024, and building 2024 pools reopens the 2024 990.

### Acceptance

- Reconciliation variance **0.00**; allocation variance **0.00**
- Rate carries a seal hash matching a sealed decision set
- Every carve-out has a citation, an amount, a driver and an evidence grade
- Current model reproduces: fringe 22.45%, indirect 31.78% at 40% facilities
  and 0% funded depreciation

---

## Phase 5b — Cross-contract scenario testing

**Goal.** Test allocations across the whole portfolio before committing. The
lane machinery exists in the schema, the API and the UI; no phase used it.

### Tasks

- **Portfolio impact view.** For a lane: rate, pool balances, and the delta on
  **every award simultaneously** — claimable, billed, variance, ceiling
  headroom. One screen answering "if we classify it this way, what happens
  across all five contracts."
- Side-by-side lane comparison — `v_lane_buildup` joined to itself. Rate delta,
  pool delta, per-objective delta, per-award delta.
- Assumption sliders on a lane: facilities allocable %, funded depreciation %,
  base type, rate method. Free to vary and not disclosure-bearing.
- Classification overrides on a lane: reason required, counted, and printed in
  the audit package via `v_lane_disclosure`. This is the line that keeps
  exploration honest — assumption sensitivity is free, classification shopping
  is visible.
- Seed the three lanes worth running: baseline at 40% facilities; depreciation
  sensitivity at 25/50/75%; `5227 Portfolio consulting` as direct versus G&A.

### Acceptance

- A lane shows the effect on all five awards at once, with ceiling headroom
- Comparing two lanes reports rate, pool and per-award deltas
- Sandbox lanes cannot produce a submitted rate — the trigger holds
- Audit package prints every lane, its purpose, and its override count

---

## Phase 6 — Ceiling-constrained restatement

**Goal.** America Makes will accept restated rates retroactively provided the
restated total stays under the contracted total. Solve it per award.

### Tasks

- `domain/restate.py`: for each award, compute allowable cost by category ×
  period, apply fringe and indirect at the applicable rate, cap cumulative
  claims at the ceiling, and emit either an amended invoice or a credit.
- Generate amended invoices in the same line format as the originals —
  Labor, Travel, Materials, Consultant, ODCs, **Indirects** — so NCDMM sees a
  familiar document. LTM already carries an Indirects line; follow that pattern.
- Cost share: Hybrid's 104,000 is untracked, but `IH Cost Share Deferral —
  412,500` on the balance sheet shows the mechanism exists. Apply it.
- The invoice issue gate already blocks on failing blocking constraints; keep
  the acknowledged-deficiency path for anything that cannot clear.

### Acceptance

- Cumulative restated claims ≤ ceiling for every award
- Hybrid: credit computed and issuable. At 31.78%, claimable 334,240 against
  512,509 billed — **178,269 credit**, of which **12,466 exceeds the ceiling at
  any rate**
- No invoice issues while a blocking constraint fails
- Every amended invoice traces to ledger lines and to a sealed rate

---

## Phase 7 — Outputs

- Stream the audit package from `domain/package.py` via
  `GET /api/export/workpapers`
- Form 990 Part IX functional schedule — Program / M&G / Fundraising by natural
  expense line, derived from the `function_990` dimension
- SEFA schedule, which needs the Rising Tides federal determination resolved
- Board memo: forgone recovery, the systemic 200.302 finding, and remediation
  status

**Acceptance.** Part IX total = 6,737,951.18 + 37,261.00. SEFA reconciles to
federal expenditures. Workbook recalculates with zero formula errors.

---

## Phase 8 — 2026 cutover

- Import `YBI_2026_Chart_of_Accounts_QBO.csv`, classes and customer:jobs. **Turn
  on account numbers in QBO first** (Settings → Advanced), or the pool encoding
  is discarded.
- Apply the crosswalk, resolving the 24 flagged splits with documented drivers
- Opening balances from the 2025 balance sheet
- Monthly close cadence — run tie-outs, freeze the period, post interim costs.
  This is the second SF1408 gap after timekeeping.

---

## Sequencing

```
Phase 0 ─┬─► 1 ─► 2b ─► 4 ─► 5 ─► 5b ─┐
         ├─► 2 ──────────────────────┼─► 6 ─► 7
         └─► 3 ──────────────────────┘
                                        8 (parallel from November)
```

Phases 1, 2 and 3 run in parallel once intake lands. **Phase 2 is the critical
path** — nothing in America Makes resolves without the invoice register. Phase
2b gates Phase 4: nobody should classify what they cannot first look at.

Two things can start immediately and need nothing from anyone: `5227 Portfolio
consulting` classification, and the interest reclassification under 200.449.

The Hybrid credit can proceed independently of every other phase, because
Hybrid ties to $100 and its conclusion does not depend on the reconciliation.

---

## Standing rules

- Money is `Decimal`. Never float.
- Invariants belong in the schema — `CHECK`, partial unique index, trigger.
- **No rate preview on the classification screens.** The seal is the guarantee.
- Unclassified cost is never defaulted into a pool.
- Proposals are never decisions.
- Every derived figure ties to a control, or it does not ship.
