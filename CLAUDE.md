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

And one before either: **the books have to agree with themselves before a rate
is computed.** `v_statement_reconciliation` holds eleven points where the
general ledger, the profit and loss, the balance sheet and the payroll
register are required to agree, and
`POST /api/rates/compute` returns 409 while any of them is open. A rate over a
ledger that does not match its own statements is a rate over the wrong numbers.

The eleventh is the payroll register, and it is the one that pays for
itself. The fringe base comes from the effort distribution, not from the
ledger's wage accounts, so a difference between them is *two denominators for
one rate* — not a presentation question. Nothing among the other ten touches
the register, which is how a $45,000 donor credit sat in an intern wage
account for a year and made the fringe rate read 22.45% when it was 21.90%.

A difference is closed by *naming* it, not by netting it. A `reconciling_item`
carries the specific ledger lines it consists of, and a deferred trigger
refuses one whose lines do not add to the amount claimed — which is what
separates a reconciling item from a plug. `/api/reconcile/propose` will find
the lines for you when exactly one combination adds up, and proposes nothing
at all when more than one would.

There is exactly one relaxation, and it exists because sometimes attribution
is genuinely impossible: a `ROUNDING` item may carry no lines, provided it
says in sixty characters or more *why* it cannot be attributed and does not
exceed a thousand dollars — past which "rounding" is not a description of
anything. Both fences are in the trigger. Do not widen them; the alternative
to writing down an unattributable residual is a tolerance that quietly
swallows it, and that is how a system starts lying.

## Who may do what

Two axes, and keeping them apart is the point.

**Rank** (`actor.role`) is the provisioning ladder and only runs downward:
`SYSTEM_ADMIN` sets up the organisation's administrator, `ORG_ADMIN` sets up
controllers and employees, and nobody provisions a peer or a superior. A
database trigger enforces the same rule, so it holds when a handler is wrong.
Rank says who creates accounts and nothing else — `SYSTEM_ADMIN` is
deliberately *not* in `READERS`, because standing the software up is not a
reason to read every employee's timesheet.

**Portfolio** (`actor_portfolio`) is authority over part of the cost record,
held as a set: `CONTROLLER`, `INVENTORY`, `PROJECT`, `FACILITIES`, `OFFICE`.
A person holds the union of what they are granted. `CONTROLLER` is the main
one and reaches everything; the narrow ones reach only their own area and
**never add up to `CONTROLLER`** — only `CONTROLLER` may seal, unseal,
compute a rate or restate. Nobody grants themselves a portfolio; the table
refuses it and so does the handler.

Two rules that fall out of this and are easy to break:

- **Everybody on the payroll keeps a timesheet, controllers included.** The
  nav is assembled from what an actor holds (`tabsFor` in `App.jsx`), not
  switched on role. Never show a tab that will answer 403.
- **Reading the cost record is a grant, not a side effect of rank.**
  `CONTROLLER`, `AUDITOR` and `ORG_ADMIN` read it by rank. `SYSTEM_ADMIN`
  does not — that account may belong to somebody outside the organisation.
  Where such a person genuinely needs it (an engagement lead under an
  agreement), `actor.record_access` carries it, granted by *YBI's own*
  administrator to the account above them in rank. That direction is
  deliberate: the data is theirs, so they are who lets somebody read it.
- **An account on a password somebody else chose cannot write anything** —
  not a classification, not a timesheet, not a certification, not a document.
  `refuse_issued_password` covers the portfolio gates, the admin gate and
  `require_own_writes`. The one exit is changing your own password. Adding a
  write endpoint on bare `current_actor` reopens the hole.

Everybody signed in can send a document in (`/api/documents`). Saying what a
document *supports* is a judgment and needs `OFFICE`. That split is why the
upload door can be open this wide.

`scripts/provision.py` walks the whole ladder through the real API and prints
a password sheet; `scripts/drive_access.py` proves all 39 boundaries against
live rows.

## Layout

```
app/
  main.py            FastAPI app, migrations on startup, serves web/dist
  db.py              psycopg pool, tiny migration runner. No ORM, on purpose.
  settings.py        env config; Railway injects DATABASE_URL
  storage.py         where a file goes on the volume — the only place a path
                     is decided. The kind decides the tree.
  routers/
    classify.py      the queue — the screen that matters
    contracts.py     charge codes, who may charge them, milestones, money in
    review.py        the three deliverables: rate, auditor's report, 990
    imports.py       QBO upload -> parse -> preview -> accept
    documents.py     the document inbox everybody in the org gets
    reconcile.py     the three source documents against each other
    lanes.py         scenario lanes and build-up views
    rates.py         seal, unseal, current rates
    evidence.py      documents and notes
    awards.py        contract constraints and true-up
  domain/            pure engine, no DB, fully unit-testable
    core.py          value objects, control register, sealed DecisionSet
    qbo.py           QuickBooks report parsers + ImportProfile
    reconcile.py     attributing a difference to the lines behind it
    pools.py         pool build, rate computation, allocation
    awards.py        contract constraint tests
    package.py       Excel audit package
    ingest.py        CSV ledger loading
  sql/               migrations, applied in filename order at startup
web/                 Vite + React SPA
```

## The volume

`app/storage.py` owns the layout. Three routes write documents — the importer,
the evidence route and the inbox everybody has — and all three go through
`storage.place()`. Nothing else writes bytes; `tests/test_storage_paths.py`
fails the build if a router starts to.

```
<YBI_STORAGE_DIR>/            the mounted volume; /srv/storage on Railway
  README.txt                  written at boot
  source/<period>/<report>/   the QuickBooks and payroll exports as received
  foundation/<category>/      what governs the engagement across periods
  evidence/<period>/<kind>/   everything supporting a figure in the record
```

**The database is the index; the tree is for people.** A path is derived from
the row and never parsed back into one. Nothing reads a directory to decide
what a document is, which is what keeps the tree a convenience rather than a
second source of truth that can disagree with the first.

**The kind decides the tree.** `FOUNDATION_KINDS` maps a kind to its folder,
so no uploader chooses a path — they say what a document *is*, which they
know. A kind that is not in that map is period evidence, which is the safe
default: mis-filing an agreement costs a few seconds of browsing, while
mis-filing an invoice out of its period hides it from the year it belongs to.
`lease` is deliberately not foundational — the building lease is, a
comparable lease supporting a market-rate analysis is not, and the kind alone
cannot tell them apart.

There is no inbox directory. An unattached document is a queue, and that queue
is `v_evidence_inbox`. Giving it a folder would mean moving a file whenever
somebody made a judgment, which is a second index and a way for the two to
drift.

**The tree is not an access boundary.** It is easier to browse and it keeps
periods apart on disk, which helps a backup and a retention rule. It enforces
nothing: `require_reader`, the portfolio gates and `require_own_writes` are
what decide who sees a document, and they are unchanged by where it sits.

`scripts/seed_documents.py` files the ten foundational documents through the
real upload route, signed in as a real person, so the trail shows who filed
them. It is content-addressed, so running it twice files nothing twice.

## Whose job is it

`v_worklist` has always known what is outstanding and never whose job it is,
so every screen showed everybody the same list. `v_worklist_owned` adds the
portfolio that can act on each kind and the screen it is dealt with on, and
`GET /api/dashboard/worklist/mine` filters it by what the caller holds.

A `CONTROLLER` sees everything — that is what the portfolio means, not a
special case — and an item whose portfolio nobody in the organisation holds
still reaches the controller rather than falling off the end. Every kind is
routed and every kind has a destination; `tests/test_worklist_ownership.py`
fails a new kind that lands on the `ELSE` by accident.

`v_certification_chase` is the project manager's version of the certification
question. **A manager cannot sign on somebody's behalf** — 200.430(i) wants
the person whose effort it was — so it is a list to go and ask, never an
action. "Their projects" is read from the assignments they made, which is a
fact already on the record rather than a new field to maintain.

Three worklist kinds were added with it: `SPACE_UNMEASURED` (no building has
square footage, which is what the facilities carve-out is sized by),
`SPACE_UNATTRIBUTED` (measured, but no partition saying who uses it) and
`CHARGE_CODE_UNASSIGNED` (hours booked to a code nobody was assigned to).

## Suggesting a classification

`propose()` is ordered by strength of signal and the 2026 crosswalk is now
part of it. Sixty-one of the eighty-five 2025 accounts map one-to-one to a
2026 account number and `pool_for()` reads the pool off that number — a
mapping somebody already built and reviewed. It took proposal coverage from
36.2% of dollars to **65.5%**.

The other twenty-four accounts are splits — depreciation by square footage,
wages by timesheet — and propose nothing. A split needs a documented driver,
which is a judgment with a person's name on it, and proposing one side would
be inventing the driver.

A crosswalk proposal leaves the 990 function and the federal treatment open
(`PENDING`), because an account number knows neither. Proposing a function
would put cost in a column of the return nobody chose.

## The income side

Everything else here reads a year already spent: the ledger arrives, the
controller judges it, a rate falls out. `/contracts` is the half that has to
exist *before* the year is worked — a code opened, somebody assigned to it, a
deliverable worth something, an invoice against the deliverable, and the money
that arrives against the invoice.

**The cost objective is the charge code.** There is deliberately no second
register of codes. An hour and a dollar spent on the same work have to land in
the same place, and two lists of "the thing you charge to" is how they stop
doing that. `charge_authority` hangs off `cost_objective`; a test fails a
migration that creates a `charge_code` table.

**Charging is gated, but only on a code somebody has been assigned to.** A
code with an empty assignment list predates the mechanism — which for all of
2025 is every code, because the year was worked before any of this existed —
and refusing those would make reconstructing it impossible. Assign one person
and the gate turns on for that code. `POST /api/timesheet/entry` and the
screen both ask `v_charge_authorised`, so neither can hold its own opinion
about who may charge what.

**Nobody assigns themselves**, the table keeps a revoked grant rather than
deleting it, and one live grant per person per code means an amendment
supersedes instead of stacking. All three are the rules the portfolios
already follow.

**A milestone state that claims a date carries one.** `DELIVERED` with no
delivery date is a status somebody set, not a thing that happened, and the
schema refuses it.

**A receipt may be negative.** A refund and a clawback are money moving the
other way; constraining it positive would overstate collections for ever.

The auditor's path runs `/contracts/people` → a person → every code they
charged, with `authorised` on each → the contract → its terms with the clause
each came from → a milestone → the invoice against it, the money in, and the
cost classified underneath. `scripts/drive_contracts.py` walks the whole chain
as the people who own it.

**No margin is shown anywhere.** Cost against a contract is what has been
*classified* to its objective, and classification is unfinished — a margin
over an incomplete cost side flatters in exactly the direction nobody should
be flattered.

## Final review

Three deliverables, one tab. `/review` holds the auditor's report, the
indirect rate build-up and Form 990 Part IX, each its own URL
(`/review/report`, `/review/rate`, `/review/form-990`) so a link still lands
where it says. They are read together — rate, then the allocation it feeds,
then the report carrying both — and three nav entries made one journey look
like three errands.

**Nothing on a review screen is computed.** Every figure is read from the row
it was recorded in, because a figure derived twice is one that can disagree
with itself and the workpaper would carry the version nobody can reproduce.
`tests/test_review.py` fails a screen that starts dividing a pool by a base.

**Each one states what is unfinished, above the figures.** A reviewer handed a
total has formed a view before they reach a footnote — so the rate says it is
a working figure while classification is open, the return says NOT FILEABLE
while any expense is unjudged, and the report says the record is incomplete.
The workbooks repeat it on their first sheet, because a workbook travels and
the caveat has to travel with it.

**`NOT_YET_CLASSIFIED` is a column of the 990, not a rounding.** Cost nobody
has judged is never spread across the three functions the return prints; the
totals are short by that amount on purpose until the queue is empty.

One trap worth knowing: **`rate.superseded_by` is dead.** The column exists and
no code path writes it — recomputing and unsealing both express supersession
through `status`, and every reader filters on that. `v_rate_buildup` first
filtered on the column, which is a no-op, and presented four SUPERSEDED rates
as the rate on file.

## Design system

`web/src/theme.css` holds the tokens; `web/src/components/ui.jsx` holds the
primitives. Pages should read as content, not as a wiring diagram.

The visual language is grounded in the craft rather than in dashboard
convention:

- **Tick marks, not status dots.** Auditors tick reconciled items. `<Tick
  state="done|open|flagged|failed" />`.
- **Schedule references in the nav.** Each tab carries the schedule it prints
  as in the audit package (A Import, A-1 Reconcile, B Classify, C Lanes,
  D Rates, F Awards), so someone who has seen the workpapers knows where they
  are.
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
- **A control that cannot be evaluated has not passed.** Read `state` on the
  register — `TIES`, `OPEN` or `NO DATA` — never `variance = 0` alone. Both
  sides of most controls are `COALESCE(..., 0)`, so an empty period compares
  zero against zero and looks green; it reported all eleven points tying over
  no books at all until `029` fixed it. The general ledger's printed
  subtotals had the same shape: an export that saved formulas without their
  cached values read as zero and reconciled against zero. When you add a
  control, say what it needs in order to mean anything.
- **Never join on a name where a key exists, and never on a name that can
  repeat.** Joining the ledger to the P&L on the leaf account name
  mislabelled 138 lines worth $1,570,174.17, because four leaves live under
  both an income and an expense parent. `v_gl_bs_account` still joins the
  balance sheet on leaf, because the sheet's path and the chart's path never
  match — it is guarded rather than safe by luck.
- **A composite key never goes in a URL path.** A group key is an account and
  a payee joined by 0x1f; a non-printable character in a path is not
  something every client will encode, and httpx refuses outright. Query
  parameter.

## Proving it

```bash
YBI_SEED_PASSWORD=... ./scripts/prove.sh
```

Everything, in the order a reviewer would want it. Unit tests need no
database; everything after drives the running service as real people against
real rows, because a permission claim and an audit claim are worth what they
are tested at.

| | |
| --- | --- |
| `pytest` | the engine, and two structural checks: every mutating route records what it did and takes its actor from the session, and every screenshot the manual shows exists |
| `scripts/reconcile.py` | the three source documents and the payroll register against each other, eleven points |
| `scripts/drive_everyone.py` | every person, every process they own, and an audit row under their own name for every change |
| `scripts/drive_contracts.py` | charge codes, assignment, milestones, money in, and the auditor's path |
| `scripts/drive_reverse.py` | the same chain walked backwards, from a receipt to the ledger lines under it |
| `scripts/drive_access.py` | rank, portfolios, the seal, the password gate |
| `scripts/drive_actors.py` | anonymous, auditor, employee, controller boundaries |
| `scripts/walk_manuals.py` | re-photographs the manual's screens |

`drive_everyone` is the one that answers "does each kind of person have a
complete, working job". Every write in it runs inside `mutating`, which
counts audit rows before and after and checks who the new one names — a
handler that changes the database and records nothing fails there even when
the change itself was correct.

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
- **Cross-reference reconciliation.** Schedule A-1. Eleven points where the
  ledger, the P&L, the balance sheet and the payroll register have to agree, in
  `v_statement_reconciliation`; `scripts/reconcile.py` runs them and exits
  non-zero on an open one. Two real defects came out of building it: 71 lines
  worth $24,082.67 were being dropped on promote by natural keys that
  collided on genuinely-duplicate lines, and the balance sheet could not be
  tied to anything at all because the parser discarded the ledger's opening
  balances. Both fixed; all 71 printed balance-sheet accounts now prove off
  the ledger. The five accounts where the ledger and the P&L still differ are
  named, not netted — ten specific lines reclassified between the two
  exports. See PLAN.md, Phase 1.

### Accounts and landing pages — done

Migration `026`. `SYSTEM_ADMIN`/`ORG_ADMIN` rank, the five portfolios,
`v_actor_access`, and `evidence.uploaded_by` with `v_evidence_inbox`. The SPA
gained `Home.jsx` (one landing assembled from what you hold), `People.jsx`
(the roster, provisioning, and the 40 payroll people with no account yet),
`MyDocuments.jsx`, and `FirstPassword.jsx` in front of everything.

Migration `027` adds `record_access` (above), and `email_confirmed` for the
forty payroll accounts whose addresses were derived from the naming
convention rather than looked up — they are listed on the People screen and
corrected in place, because deleting an account is never right here.

Two real bugs came out of building the drives. The password gate covered
portfolio and admin writes and left the three screens everybody actually uses
wide open, so a newcomer could sign a 2 CFR 200.430(i) certification on the
password an administrator had handed them an hour earlier;
`require_own_writes` closes it. And the login response did not carry
`must_set_password`, so a newcomer landed on the application and only met the
password screen on the next page load, with every write in between refused by
an API that knew something the screen did not — login now returns the same
shape as `/me`, and the access drive asserts they agree.

### The manual

`web/src/components/Manual.jsx`, on the landing page, assembled from what the
person holds — the same rule the nav follows, so it never describes a screen
the reader cannot open. It opens itself once on a first visit and stays shut
after; a panel that reopens every morning is one people learn to click past.
Screenshots come from `scripts/walk_manuals.py`, signed in as somebody with
that job against the real ledger, and `tests/test_manual.py` fails if one is
missing or a chapter is gated on something that does not exist.

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
- Cost share obligated and never tracked: $104,000 on Hybrid and
  **$513,065 on Last Tactical Mile** (§4.3), of which YBI's own share is
  $213,037 and the balance is partner cost share it must evidence.
  $617,065 in total — the largest untracked obligation in the file.
- `5227 Portfolio consulting`, $588,539 across 442 lines, no objective signal.
  The largest single open judgment in the ledger.
