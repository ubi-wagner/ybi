# CLAUDE.md

Conventions for Claude Code working in this repo.
Read `BRIEF.md` first for orientation and the intake manifest.

## What this is

A cost allocation system for Youngstown Business Incubator: take the QuickBooks
general ledger, let the controller classify it into 2 CFR 200 cost pools with
evidence, compute indirect rates, allocate to contracts, and produce an audit
package. Used for the 2025 Form 990 and audit, and for justifying cost recovery
on 2026+ proposals.

Single FastAPI process serving a React SPA. Postgres. Deployed on Railway.

## The one idea that shapes everything

**Classifications are sealed before any rate is computed.**

A reviewer will ask whether the rate was honest or reverse-engineered. The
answer has to be documentary, not a promise. So:

1. The controller classifies. No rate is computed or displayed during this phase.
2. The decision set is sealed — hashed across every judgment in it.
3. Only then can a rate be computed. The rate carries the seal hash.
4. A database trigger (`rate_requires_seal`) refuses a rate whose seal does not
   match a sealed set. Changing a classification requires unsealing with a
   written reason, which supersedes the rate.

**Do not add a rate preview to the classification screens.** It would undo the
guarantee, and it is the single easiest mistake to make in this codebase.

A related rule: **unclassified cost is never defaulted into a pool.** Anything
without a signal stays in the queue. This makes the rate read high while work is
unfinished, which is the honest direction to err.

## Layout

```
app/
  main.py            FastAPI app, migrations on startup, serves web/dist
  db.py              psycopg pool, tiny migration runner. No ORM, on purpose.
  settings.py        env config; Railway injects DATABASE_URL
  routers/
    classify.py      the queue — the screen that matters
    imports.py       QBO upload -> parse -> preview -> accept
    lanes.py         scenario lanes and build-up views
    rates.py         seal, unseal, current rates
    evidence.py      documents and notes
    awards.py        contract constraints and true-up
  domain/            pure engine, no DB, fully unit-testable
    core.py          value objects, control register, sealed DecisionSet
    qbo.py           QuickBooks report parsers + ImportProfile
    pools.py         pool build, rate computation, allocation
    awards.py        contract constraint tests
    package.py       Excel audit package
    ingest.py        CSV ledger loading
  sql/               migrations, applied in filename order at startup
web/                 Vite + React SPA
```

## Design system

`web/src/theme.css` holds the tokens; `web/src/components/ui.jsx` holds the
primitives. Pages should read as content, not as a wiring diagram.

The visual language is grounded in the craft rather than in dashboard
convention:

- **Tick marks, not status dots.** Auditors tick reconciled items. `<Tick
  state="done|open|flagged|failed" />`.
- **Schedule references in the nav.** Each tab carries the schedule it prints
  as in the audit package (A Import, B Classify, C Lanes, D Rates, F Awards),
  so someone who has seen the workpapers knows where they are.
- **Three card weights, not one.** `card`, `card raised`, `card quiet`. Radius
  and shadow carry hierarchy; do not apply the same treatment to everything.
- **Tabular numerals everywhere.** `.num` on any figure. Money right-aligned,
  negatives in the fail colour.
- **One accent.** Petrol `--accent`, carried over from the rate model so the
  whole engagement reads as one piece of work.
- **Annotation colours are warm** — pencil, not traffic light.

Two interaction rules:

- **Keyboard first.** `j`/`k` move, `Enter` accepts the proposal, `e` edits,
  `x` selects, `1`-`8` jump to a pool, `f` toggles focus mode, `/` searches.
  Hints render inline via `<Keys />` rather than hiding behind a help modal.
- **Nothing destructive without a way back.** Toasts double as the undo
  surface. The fastest way to make someone slow and cautious is to make
  mistakes expensive.

The classification queue has two modes on purpose. **Sweep** is a dense table
for the many groups with an obvious answer. **Focus** is one large card for the
few that need real thought — the amount set large, sample memos for context,
and the proposal as a single button. That card is where the visual boldness is
spent; everything around it stays quiet.

## Conventions worth keeping

- **Money is `Decimal`, never `float`.** `domain/core.py::money()` normalises and
  rounds half-up to the cent. Floats in a cost model produce variances that take
  hours to chase.
- **Invariants belong in the schema.** If a rule can be a `CHECK`, a partial
  unique index or a trigger, put it there rather than in a handler. The point is
  that it holds even when application code is wrong.
- **Domain code does not import `app.db`.** Keep `domain/` pure so it can be
  tested without Postgres, and so the engine can be run standalone.
- **Proposals are never decisions.** Anything the system infers — from
  Customer:Job, account names, prior year — is a suggestion a human confirms.
- **Every derived figure ties to a control.** If a new calculation cannot be
  reconciled to the ledger, it does not ship.

## Running it

```bash
cp .env.example .env
./scripts/dev.sh          # Postgres in docker, API on :8000, Vite on :5173
pytest -q                 # domain tests need no database
```

Migrations run automatically on startup from `app/sql/*.sql`. Add a new numbered
file; never edit one that has already been applied in production.

## Deploying

Railway, Dockerfile builder. Attach a Postgres service and `DATABASE_URL` is
injected. Healthcheck is `/api/health`. The Dockerfile builds the React app in a
node stage and copies `dist` into the Python image, so one service, one deploy.

## The 2026 chart

`app/domain/chart.py` is the structural fix, not a nice-to-have. The 2025
chart bakes program identity into account names (Drive AM, LTM Grant, Rising
Tides Expense), so a single account mixes consulting, travel and materials and
every new award means new accounts. The 2026 chart moves program identity to
Customer:Job and lets the account number carry the pool:

    Account number  ->  cost pool          (5xxx direct ... 93xx rental-direct)
    Class           ->  Form 990 function
    Customer:Job    ->  final cost objective
    Location        ->  facility

Same four dimensions the classification queue records by hand for 2025. From
2026 the books produce them directly. `pool_for()` is the whole mechanism —
classification becomes arithmetic.

Two carve-outs that cost weeks in 2025 disappear at source: funded asset basis
is segregated into 1511/1512 so the 200.436(b) depreciation question is
answered by the account, and tenant cost goes to the 93xx rental pool so the
facilities carve-out is booked rather than estimated.

`app/domain/crosswalk.py` maps all 85 of the 2025 accounts and proves the new
chart carries every dollar. Twenty-four entries are splits that need a
documented driver — those are real judgments, and they are flagged rather than
guessed.

## Where the work is

In rough order of value:

1. **Classification queue polish.** Keyboard-first: `j`/`k` to move, `Enter` to
   accept the proposal, `1-8` for pools. Tom has ~200 meaningful decisions; every
   second saved compounds.
2. **Evidence drag-and-drop and bulk match.** Drop a folder of invoices, match on
   amount, date proximity and vendor similarity, confirm in bulk.
3. ~~**Rate computation endpoint.**~~ Done. `POST /api/rates/compute` builds the
   domain model from live rows, computes, and persists `rate` and `allocation`.
   Both proofs run before anything is written: the pool reconciles to the
   ledger and every allocable dollar lands on exactly one objective, or it is
   a 409 rather than a rate. `tests/test_pools.py` covers the engine — it had
   no tests at all before, despite what this file used to say here.
4. ~~**Audit package download.**~~ Done. `domain/package.py` produces the workbook; add a
   route that streams it.
5. **Lane comparison UI.** The API exists; the side-by-side view does not.
6. ~~**Balance sheet import**~~ Done. `parse_balance_sheet` in `domain/qbo.py`,
   accepted through the same reconciling path as the P&L: the sheet must
   balance, every printed subtotal must equal what sits under it, and its net
   income must equal the P&L's — the first control in the system that spans
   two reports. `v_fixed_asset_basis` gives cost against accumulated
   depreciation by class, with land and construction in progress excluded from
   depreciable cost. The funding source still has to come from the asset
   register, and `v_depreciation_basis` states that gap rather than implying
   it.

### Done since this list was written

- **Restatement.** `POST /api/restate` measures every invoice on an objective
  against the sealed rate and records the difference in the direction it runs,
  per invoice. A restatement carries the seal of the rate it used, is PROPOSED
  until a sponsor says otherwise in writing, and cannot be accepted without
  naming the §4.4 modification that authorised the change of basis.
- **The 2026 splits.** `GET/PUT /api/chart/splits`. Each of the 24 accounts
  that divides gets its shares and the driver behind each share; the shares
  must come to one and every part must name its driver.

## Current plan

`PLAN.md` — phased tasks with numeric acceptance criteria. Phase 2, the invoice
register, is the critical path.

## Engagement findings

`PROJECT_CONTEXT.md` is the substantive handoff: control totals, labor
evidence, the recommended rate model (fringe 22.45%, indirect 31.78%), the
America Makes position, and the open items. If a change touches cost logic,
check the model there first — several figures in it are load-bearing.

## Open questions carried from the analysis

These are unresolved in the real engagement, not bugs:

- Square footage by tenant and function — drives the facilities carve-out.
- Asset register with funding source — depreciation on federally funded assets
  is unallowable under 200.436(b).
- Whether Rising Tides is federally funded. The controller's workbook says yes;
  the objective master says no. It changes the SEFA and the Single Audit scope.
- Cost share of $104,000 on the Hybrid award: obligated, never tracked.
- `5227 Portfolio consulting`, $588,539 across 442 lines, no objective signal.
  The largest single open judgment in the ledger.
