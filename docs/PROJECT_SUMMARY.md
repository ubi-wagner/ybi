# YBI Cost Allocation System — Project Summary

**As of 10 September 2026.** Written after standing the application up against
the real 2025 QuickBooks exports and working it as the controller would.

---

## 1. What this is for

Two jobs, one system.

**The 2025 job — finite, and time-critical.** Build a defensible indirect cost
rate structure from the 2025 books, produce an evidence-linked workpaper package
the auditor can examine without being handed a spreadsheet, and support a
restatement of the 2025 America Makes invoices for NCDMM's approval, including
the closeout of Hybrid Phase 2. The auditor has not started fieldwork, which is
the whole opportunity: remediation and disclosure can be in place before they
arrive rather than discovered by them.

**The 2026+ job — continuing.** The same machinery run as an operating discipline:
contemporaneous timekeeping and certification, monthly close and tie-out,
cost-share tracking against the ~1:1 ratio both agreements require, and rate
proposals for future awards. `app/domain/chart.py` is the structural fix that
makes 2026 classification arithmetic rather than judgment — account number
carries the pool, Class carries the Form 990 function, Customer:Job carries the
cost objective, Location carries the facility.

The organising constraint, from NCDMM: **retroactive restatement is acceptable
provided the restated total stays under the contracted total.** That is a
ceiling-capped recovery problem, and it is what the award engine implements.

---

## 2. Architecture

One FastAPI process serving a React SPA, backed by Postgres, deployed on Railway
as a single service. No ORM: the schema is the design document and the invariants
live in constraints and triggers, so they hold even when application code is
wrong.

```
app/
  main.py          FastAPI app; migrations on startup; serves web/dist
  db.py            psycopg pool, migration runner, transaction helper
  routers/         classify · imports · lanes · rates · evidence · awards · chart
  domain/          pure engine, no database imports, unit-testable
  sql/             numbered migrations, applied in filename order
web/               Vite + React SPA
scripts/           repeatable acceptance runs
docs/              source documents, regulatory analysis, screenshots
```

### The guarantee that shapes everything

**Classifications are sealed before any rate is computed.** The controller
classifies with no rate displayed; the decision set is hashed across every
judgment; only then can a rate be computed, and it carries the seal. A database
trigger refuses a rate whose seal does not match a sealed set.

This exists to answer one question an auditor will ask — *was the rate honest or
reverse-engineered?* — documentarily rather than by assurance. It is the
technical expression of **2 CFR 200.405(c)**, which prohibits shifting cost to
overcome fund deficiencies. Given that the 2025 books carry a known
$443,725.38 billed-versus-actual difference, a rate that cannot be shown to
predate knowledge of that gap is worth very little.

Corollary rule: **unclassified cost is never defaulted into a pool.** Anything
without a signal stays in the queue, which makes the rate read *high* while work
is unfinished. That is the honest direction to err.

---

## 3. Component analysis

### `app/domain/` — the engine

| Module | Responsibility | State |
|---|---|---|
| `core.py` | Money (Decimal, half-up to the cent), pool/function/grade vocabularies, control register, sealed `DecisionSet` | Working, tested |
| `qbo.py` | QuickBooks report parsers driven by named `ImportProfile`s | **Rebuilt this session**; ties on real data |
| `pools.py` | Pool build, carve-outs, rate computation, allocation | Arithmetic tested; not yet wired to persistence |
| `awards.py` | Contract terms, constraint tests, ceiling-capped true-up | Working; needs real award rows |
| `package.py` | Excel audit package | Built; no download route yet |
| `chart.py` | The 2026 chart of accounts; `pool_for()` | Complete, 85 accounts |
| `crosswalk.py` | 2025 → 2026 account mapping | Complete; 24 splits flagged as real judgments |
| `ingest.py` | CSV ledger loading | Working |

The engine imports no database code, so it runs and tests standalone.

### `app/sql/` — invariants in the schema

Six migrations. What they enforce, rather than what they contain:

- **Source is evidence.** `ledger_line` refuses UPDATE and DELETE, loudly.
- **Decisions are append-only.** Amend by superseding; a decision can be reversed
  but never removed, and a line carries at most one live decision.
- **Direct cost names an objective; pooled cost must not.**
- **A supported grade requires written reasoning.**
- **A VERIFIED grade requires evidence cited on the judgment** — not merely a
  document existing somewhere nearby.
- **Fundraising and unallowable activity can never be federally allowable.**
- **An import cannot be accepted while a subtotal fails to tie.**
- **A rate cannot exist without a matching seal.**

### `app/routers/` — the API

29 endpoints. `classify` is the one that matters: a grouped queue with proposals,
decisions, deferrals and coverage. `imports` is a two-phase commit — nothing
reaches the ledger until QuickBooks' own printed subtotals reconcile against what
was parsed.

### `web/` — the human surface

Six screens, keyboard-first, with a pool colour language carried identically
across the queue, the buildup and the crosswalk. Tabs carry the schedule letter
they print as in the audit package (A Import, B Classify, C Lanes, D Rates,
F Awards), so a reviewer who has seen the workpapers knows where they are.

---

## 4. What actually works, verified against real data

Everything below was run against the 2025 QuickBooks exports through the running
API, not asserted from fixtures. `scripts/load_2025.py` re-runs it.

### Import and reconciliation

| Control | Expected | Result |
|---|---:|---|
| P&L income | 6,662,593.00 | PASS |
| P&L COGS | 37,261.00 | PASS |
| P&L expenses | 6,737,951.18 | PASS |
| P&L other income | 116,948.46 | PASS |
| P&L net income | 4,329.28 | PASS |
| Section-to-net-income variance | 0.00 | PASS |
| GL dated rows | 15,500 | PASS |
| GL leaf subtotals tying | 206 of 206 | PASS |
| GL subtree rollups tying | 40 of 40 | PASS |
| GL subtotal variance | 0.00 | PASS |

15,429 lines promoted to the ledger. The 71-line difference is duplicate natural
keys — identical date, type, num, name, account, amount and memo — surfaced as a
warning to confirm rather than silently deduplicated.

### Classification scope

999 groups and $17,051,093.71 in P&L scope, out of 15,429 ledger lines. The
remaining 10,367 lines are balance sheet and are excluded from the queue.

### A controller working session

`scripts/tom_session.py` — nine judgments, each with a pool, a Form 990 function,
a federal treatment, an evidence grade, written reasoning and a regulatory
citation; three supporting documents attached across 85 lines and cited on the
decisions that required them; four workpaper notes. Dollar coverage 19.4%.

---

## 5. The build-test-build-test record

Running the real files through the real API found eight defects. All are fixed
and covered by tests. They are listed because the pattern matters more than the
individual bugs: **every one of them sat on the path between the source files and
a number, and none would have been found by reading the code.**

**1. The schema could not be created.** `001_core.sql` used a subquery in a
partial index predicate, which Postgres rejects. Every migration after it was
unreachable, so no deploy could ever have started. The one-live-decision-per-line
rule is now a denormalised flag maintained by trigger.

**2. Append-only rules silently swallowed writes.** `INSTEAD NOTHING` leaves a
caller believing it edited evidence and a reviewer with no trace of the attempt.
Now triggers that RAISE. They also blocked `ON CONFLICT`, which the import path
needs.

**3. Accept referenced a row nothing created.** `ledger_line.import_id` pointed at
a `ledger_import` that was never inserted, so acceptance failed on a foreign key
every time.

**4. Sub-accounts sharing a leaf name collided.** "Drive AM" exists under both
`3900 Grant Income` (579,240.87) and `Grant Expenses` (181,880.88). The parser
keyed on leaf name, merging them into one account overstated by 761,121.75. Forty
subtotals failed to tie.

**5. Children were reparented to their grandparent.** QuickBooks prints a
parent's own lines and total *before* its sub-accounts, so a header after a total
may be a child or a sibling. Fifteen rollups failed. The "with sub-accounts" rows
are what disambiguate.

**6. The queue asked the controller to classify cash.** Balance sheet accounts
made it 2,479 groups and $99M against $6.7M of actual cost — dollar coverage, the
measure that gates sealing, was meaningless.

**7. A VERIFIED classification could never be created.** The gate is a deferred
constraint trigger firing at COMMIT, but each database helper took its own
connection and committed, so the decision committed before the evidence it cited
existed. Every VERIFIED judgment was refused as unevidenced.

**8. Schema gates rendered as bare 500s.** The controller needs to read *"a
VERIFIED classification requires at least one attached document"*. The message is
the entire point of putting the rule in the schema.

30 tests pass, including the real 2025 ledger reconciling at every depth.

---

## 6. Screenshots

In `docs/screenshots/`, captured from the running application with the 2025 data
loaded and nine classifications recorded.

| File | Screen |
|---|---|
| `01-imports.png` | Import — both files accepted, subtotals tied |
| `02-classify.png` | Classification queue — 999 groups, real accounts and vendors |
| `03-chart.png` | The 2026 chart and its crosswalk |
| `04-lanes.png` | Scenario lanes |
| `05-rates.png` | Rates — 19.4% coverage, seal gate holding, "no rate yet" |
| `06-awards.png` | Awards and constraint tests |

---

## 7. What is not built yet

In the order it is worth doing.

1. **The invoice register.** The critical path. Invoices carry six line
   categories — Labor, Travel, Materials, Consultant, ODCs, Indirects — and the
   controller's tabs track only Labor. That is the $1.16M reconciliation gap, and
   nothing in the America Makes restatement resolves without it. LTM invoice
   10039 already carries an Indirects line of $3,000, so restatement is a change
   of basis, not a new concept.
2. **Award rows with real ceilings.** Only Hybrid Phase 2's $500,043 is known.
3. **Rate persistence.** `pools.py` does the arithmetic and is tested; it needs
   wiring to persist `rate` and `allocation` rows with the seal hash.
4. **Balance sheet import and the asset register.** This resolves the
   depreciation carve-out, which is the largest single swing in the rate. Tech
   Block Building 5 alone is 38.5% of the depreciable basis.
5. **Time certification.** Migration `007_time_certification.sql` — employee and
   supervisor attestation covering *total* activity, not the federal slice
   (2 CFR 200.430(i)(1)(iii)). This is what turns the controller's reconstruction
   into support for a direct charge, including executive oversight time that was
   never direct billed.
6. **Audit package download.** `package.py` produces the workbook; it needs a
   route that streams it.
7. **Authentication and multi-actor testing.** Not present. The system currently
   takes an actor name as a parameter, which is right for a single trusted
   operator and wrong the moment employees sign certifications or the auditor
   gets read access.

---

## 8. Open questions carried from the engagement

Unresolved facts, not bugs:

- Square footage by tenant and function. Management estimate is 50% tenant /
  30% program / 20% administrative; a floor plan or rent roll is needed to
  support it.
- Asset register with funding source per asset. Depreciation on federally funded
  assets is unallowable under 200.436, and Finding 2024-001 records that capital
  reimbursements were netted against asset cost.
- Whether Rising Tides is federally funded. The controller's workbook says yes;
  the objective master says no. It changes the SEFA and the Single Audit scope.
- The $104,000 Hybrid cost share: obligated, never tracked.
- `5227 Portfolio consulting` — $588,539 across 442 lines with no objective
  signal. The largest single open judgment in the ledger, and it swings the rate
  between roughly 28% and 45%.
- The workpaper behind the $233,543.12 of unrecovered indirect claimed as cost
  share on Project 88, and any written AFRL approval of it under 200.306(c).

See [`docs/analysis/indirect-cost-framework.md`](analysis/indirect-cost-framework.md)
for the regulatory analysis these rest on.
