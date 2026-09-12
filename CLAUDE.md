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
  switched on role. Never show a tab that will answer 403 — **and never hide
  one the API would allow.** Every narrow gate is
  `require_portfolio(X, Portfolio.CONTROLLER)`, so `tabsFor` admits
  `CONTROLLER` everywhere; it did not, and Tom was offered four screens fewer
  than he is entitled to. A nav stricter than the API is the same defect as
  one looser: both mean the screen and the server disagree about who you are.
  The nav is not a security boundary either way — some screens are readable
  by URL with no tab, because the nav shows what is *yours to do*.
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
a password sheet; `scripts/drive_access.py` proves all 68 boundaries against
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
    reports.py       the timesheet report, and invoices rendered off the register
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
    invoice_document.py  an invoice on the face it was issued on
    timesheet_report.py  Schedule G, as a workbook
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

`scripts/seed_documents.py` files the eighteen foundational documents through
the real upload route, signed in as a real person, so the trail shows who
filed them. It is content-addressed, so running it twice files nothing twice.

**What a document is, is read from the bytes.** `storage.sniff_type()` decides
the content type from the leading bytes at upload and the type the client sent
is discarded. A content type on the way in is a *claim the uploader makes*,
and the library decides from that column whether to show a document in the
page — so trusting the claim would mean the uploader decides whether their own
file gets rendered. It is also simply unreliable: `seed_documents.py` sends
`application/octet-stream` for everything, so every one of the eighteen
foundational documents was filed as anonymous bytes and twelve PDFs could not
be opened. A file the sniffer cannot identify is `application/octet-stream`
and downloads, which is the right answer for an unrecognised file.
`scripts/retype_documents.py` repairs rows written before this, and is the
last thing in the system permitted to read a stored path backwards.

## Matching a document to the cost it supports

Twenty-one documents on file and **none attached to a single ledger line**,
so the ceiling on every one of the controller's two hundred judgments was
`CORROBORATED`. `app/domain/evidence_match.py` proposes; `/api/documents/
propose` reads the live rows through it and **applies nothing**.

**Attaching is not citing, and the difference decides a grade.**
`decision_verified_check` counts `decision_evidence`, not `attachment`.
Attaching says *this paper is about that money*; citing says *this paper is
why I judged it the way I did*. So bulk confirmation raises nobody's grade on
its own — it makes the document findable, and `decide()` carries
`evidence_ids` from there. `tests/test_verified_requires_a_citation.py` holds
the trigger against a database, including the case where the document is
attached to the cost and `VERIFIED` is still refused.

**Amount is necessary and nothing else is sufficient.** A document proposes
only where its amount equals a candidate's to the cent; date proximity and
vendor similarity raise confidence and break ties, and neither can carry a
proposal alone. An invoice dated in March near a group that ran in March is
not evidence that it is *that* group's invoice.

**More than one candidate means no candidate** — the rule
`/api/reconcile/propose` follows and the asset schedule's variance
attribution follows, for the same reason: an attribution that could equally
have been something else is not evidence. The answer says how many tied and
shows them, so the person knows to look rather than assuming there was
nothing to find.

**The signal has to exist before it can be scored.** `evidence.doc_amount`,
`doc_date` and `vendor_name` were columns four views read and **nothing had
ever written** — all forty-three documents carried NULL in each, so there was
nothing to match on. The same shape as `rate.superseded_by` and
`space_partition`, both of which turned out to be defects rather than spare
capacity: a column that looks usable and is filled by nothing is an
invitation. The upload takes them now, because what is on the face of a
document is transcription rather than judgment and the person holding the
paper can do it; `PATCH /api/documents/{id}/facts` takes `OFFICE`, because a
wrong amount typed there produces a confident proposal for the wrong cost.
A blank stays NULL — *there is no amount on this document* and *nobody has
read it off yet* are different facts, and the second must never be written
as 0.00.

**"No proposal" covers two situations and a screen that prints them as one
list is unreadable.** Thirty-two request-reply workbooks nobody has read the
face of, each repeating the same sentence, buried three real proposals. The
screen separates *proposed*, *says what it is and nothing fits* — worth
reading one by one — and a single collapsed count of what has not been read.

## The library

`GET /api/documents/library` and `/library` in the SPA. Every document in the
record, for the people entitled to read it. `/mine` answers "what did I send
in" and the inbox answers "what has nobody filed yet"; neither answers the
question an auditor actually arrives with, which is "show me the lease".

Gated on **`require_reader`** — the same gate as the review screens, not a new
one. Reading the cost record is one permission and a document is part of the
cost record, so the controller, the people holding CONTROLLER rank alongside
them for this engagement, the auditor, the organisation's administrator and
anyone carrying a `record_access` grant all get it, and a person with a
timesheet and nothing else does not. `require_office` would be wrong in both
directions: it admits somebody who may file a receipt but may not read the
ledger, and refuses the auditor, who may read everything and holds no
portfolio.

A document opens **in the page**, because somebody checking eleven attachments
against eleven figures should not end the afternoon with eleven files in
~/Downloads. Two rules make that safe, and they are independent:

- **The inline allowlist.** PDF, PNG, JPEG, GIF, WebP, plain text and CSV, and
  nothing else — held in `INLINE_SAFE` and in `v_document_library.inline_safe`,
  which `tests/test_document_access.py` fails if they ever disagree. Anything
  else downloads however it is asked for. `text/html` and `image/svg+xml` are
  not on it and must never be: everybody signed in may upload, so an inline
  render of either is a script running as the controller.
- **The response says so.** `nosniff`, because a content type is a claim; and
  a `Content-Security-Policy` carrying `sandbox`, which puts the document in
  an opaque origin and travels with the file even when it is opened outside
  the panel.

**The preview frame carries no `sandbox` attribute, and must not grow one.**
It reads like a safety measure and is not one: Chromium refuses to run its PDF
viewer inside a sandboxed frame at *every* value of the attribute,
`allow-scripts` included, and renders "This page has been blocked by
Chromium" where the lease should be. Twelve of the eighteen foundational
documents are PDFs, so the attribute does not harden the panel, it switches it
off. This was measured in a browser against all six combinations, not reasoned
about — the CSP on the response does the same job and Chromium still renders a
PDF under it. `tests/test_document_access.py` fails a frame that re-grows one.

Reading a document and taking a copy of it are recorded as different acts —
`EVIDENCE_VIEW` and `EVIDENCE_DOWNLOAD`. An auditor who opened nine leases in
a panel and downloaded one has done one thing worth asking about, and the
register should say which.

## Two documents on paper

`app/routers/reports.py`, `/reports` in the SPA, Schedule G. Both are reads
and take `require_reader`; filing a generated invoice is not a read and takes
`CONTROLLER`.

**The timesheet report** is the labour evidence behind the fringe base. The
eleventh control compares the payroll register to the ledger's wage accounts,
and a reviewer who sees a difference then wants to know *which people* — which
is a workbook, not a table with a scrollbar. Four sheets: coverage, the
distribution, certification, and every live entry with what it was
reconstructed from. It reads `v_timesheet_coverage`, `v_labor_effective`,
`v_certification_status` and `v_payroll_reconciliation` and computes nothing;
a report that summed `timesheet_entry` itself would be a second
implementation of the distribution, and the two would eventually disagree.
The caveats go on the first sheet above the figures — who has not certified,
how much is reconstructed rather than contemporaneous, any difference nobody
has named.

**Invoice regeneration** renders the register onto the face the three America
Makes invoices already use, because a restatement has to be issued on
something NCDMM's payables recognises. `app/domain/invoice_document.py` is
pure and has no database. The masthead, the BILL TO block and the total are
fixed; **the table is the part that expands**, paginating with repeated
column headers, a "continued" marker, and a page count that needed a second
render pass to know itself. The header total is passed in rather than
re-derived from the lines, so an invoice that does not foot can print both
figures and say so instead of agreeing with itself by construction.

Three rules worth keeping:

- **A reproduction says it is one.** An invoice already issued has a document
  of record and it is the one the sponsor holds; rendering the same face
  without a band saying so would put a second artefact into circulation that
  a reader cannot tell from the first. Only `DRAFT`, `RESTATED` and `CREDIT`
  — things YBI is issuing now — render as originals.
- **`ingest_channel = 'GENERATED'`** (migration `038`). Every other channel
  means the document came from outside. A rendering of the register
  corroborates nothing the register does not already say, so filing it as
  `UPLOAD` would shelve it beside the invoice the sponsor actually received,
  indistinguishable. `v_document_library.is_generated` carries it to the
  screen — the band is on the paper, this is the same statement in the index.
- **Rendering is deterministic** (`invariant=1`). The filing route
  content-addresses what it renders, so the same invoice files once however
  often the button is pressed, and a *changed* invoice files alongside the
  first rather than over it. Without it every press files another copy
  differing only in a timestamp reportlab stamped inside.

`reportlab` and `pypdf` are the two new dependencies — both pure Python, so
the image grows no native library. `pypdf` is how the tests and the drives
read a rendered invoice back: PDF text is compressed, and searching the raw
bytes for a phrase plainly on the page finds nothing.

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
`SPACE_UNATTRIBUTED` (measured, but its space units do not account for it in
full) and `CHARGE_CODE_UNASSIGNED` (hours booked to a code nobody was
assigned to).

**What a kind means is written down once**, in `web/src/worklistKinds.js`.
There were three maps of it — `Worklist.jsx`, `Dashboard.jsx`, `Home.jsx` —
each kept by hand and each missing different kinds, and every one falls back
to the raw database name. So the failure mode was never a broken screen: it
was a screen that starts speaking SQL, showing the controller
`DONATION_RATE_MISSING` and no destination. Two kinds were in none of the
three.

**And no test of "nothing falls off the end" may keep its own list of the
ends.** `test_worklist_ownership.py` is exactly that test, its `KINDS` was
hand-kept, and it was missing the same two — so both sat on the `ELSE` with
the controller as owner and `/` as destination for as long as the list did.
Two of its other assertions could not fail at all: the destination test took
a fixed-width window back from `AS goes_to` that overlapped the owner `CASE`
and so passed on the owner routing, and the portfolio regex matched nothing
against a lifted view body. All of it derives from the views now. A
hand-kept map of what the code does was wrong four times in one run of the
system review; it is the same defect every time it appears.

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
- **Read the schema; never recall it.** `python scripts/schema.py <table>`
  prints the columns, the CHECK constraints, the triggers, and — on a column
  that takes one — **the enum's values inline**, which is the one thing that
  cannot be inferred from anything else. `--like` searches names and a name
  that is not there answers with the near misses. Eight defects in one week
  came from a name written from memory: `ledger_import.loaded_by` for
  `imported_by`, `award_term.key` for `term_key`, `decision.period` for
  `scope`, `'RECONSTRUCTED'` for `MANAGEMENT_RECONSTRUCTION`,
  `'DIRECT_PROGRAM'` for `DIRECT`. Each one is syntactically perfect source
  that only the database disagrees with, so it surfaces on the line that
  runs — which here is a line a controller is standing on.
  `tests/test_sql_is_real.py` hands all 632 literal statements in `app/`,
  `scripts/` and `tests/` to `PREPARE`, which resolves every relation,
  column and inline literal without executing anything. It is the schema
  checking the code rather than the code asserting things about the schema,
  and there is no list in it to fall out of date.
- **Subscripting a row is a claim; `.get()` is not.** `app/db.py` returns a
  `Row`, and a key that is not there answers with what the query *did*
  select rather than with a bare `KeyError: 'amount'`. `PREPARE` cannot see
  that class — the SQL is valid and the Python is wrong — and it shipped
  once as a 500 on `POST /api/classify/decide`. Use `.get()` where a column
  genuinely may be absent, and subscript where it may not.

## The foundation

`docs/FOUNDATION.md` is the baseline: every control total, where each figure
came from, and what is deliberately not loaded. The seed data is final —
there will not be more — so it is written down to the cent.

```bash
YBI_SEED_PASSWORD=... BASE=http://127.0.0.1:8000 ./scripts/seed.sh
```

Twenty-two seconds from an empty database, re-runnable, seven steps in the
order they have to happen. It exists because those seven steps were being
remembered rather than written down, and a system review found what that
costs: **the twenty-six contract provisions read out of the executed
agreements lived in one developer's database and in no script.** Seeded from
nothing, the award register carried three contracts and nothing inside them,
and an auditor walking back from an invoice reached the agreement and then a
dead end. `scripts/load_contract_terms.py` is the fix.

Set `YBI_DEV_SEED=1` to give every account the same password so the drives
can sign in; provisioning refuses that outside a development environment.

## Reviewing it

`scripts/review_system.py` drives the whole system as all six people across
six dimensions and writes `docs/SYSTEM_REVIEW.md`. `docs/REVIEW_FINDINGS.md`
is what the last pass found — six defects fixed, three matters needing a
human decision.

| | |
| --- | --- |
| CONNECTIVITY | every route answers, as everybody — 79 GETs × 6 people |
| CAPABILITY | every tab reaches its endpoint, and nothing it should not |
| FUNCTIONALITY | the screens that should carry data carry data |
| AUDITABILITY | every change names an account and a session |
| CONTINUITY | the chain walks forward, and backward by API |
| PROPORTION | a change moves what it should, and moves nothing else |

Three things about it worth knowing:

- **It runs before the drives**, like the manual walk, because the drives
  seal — and a sealed set correctly refuses the one classification the
  proportion check makes.
- **It walks its own change back** through the real undo route, so it leaves
  the record as it found it. Before that, coverage climbed 0% to 36.8% across
  five runs and every figure was a review reading its own writing.
- **It derives what each screen calls** from `App.jsx`, the page components
  and `api.js`. A hand-kept map of that was wrong four times in one run and
  reported three correct 404s and a correct 403 as faults. A test that argues
  against correct code is worse than no test.

Two faults from that review are worth carrying here because they are easy to
reintroduce:

**Unknown `/api` paths must 404, not fall through to the SPA.** The catch-all
answered every unmatched API path with `index.html` and a 200, so a typo, a
renamed endpoint or a route dropped in a deploy all looked healthy to anything
checking a status code. It had been hiding a green drive check against
`/api/rates`, which is not a route and never was.

**Coverage is defined once, in `v_classification_coverage`.** The
classification screen and the review screens used to compute it separately and
answered **13.0% and 2.2% at the same moment** over the same decision — one
scoped to the P&L, the other counted both sides of every transfer. Migration
`039` put the definition in the schema, scoped to the P&L, in absolute
dollars, with `classified + unclassified = scope_dollars` so the percentage
reproduces from the row. `classify.py` reads it.

## The invoice format is the evidence

**A line at zero is a line, and must never be filtered.** The America Makes
invoices list *the categories the contract allows*, not the categories that
had activity. Drive AM's Schedule B funds five of its seven named categories —
SUBCONTRACT and EQUIPMENT are in the schedule at zero — and invoice 10018
carries exactly those five, three of them at 0.00.

Dropping an empty row would produce a tidier document that says something
different: that a category was unavailable, when it was available and unused.
And a renderer willing to filter empty rows is one step from filtering the
absence that matters most — **10018 has no indirect line because Schedule B
has none**, against $583,594 of budgeted labour. That absence is the strongest
evidence the restatement has, because the document YBI issued is itself the
record of what it was never budgeted to claim.

`award_budget` (migration `040`) records what each award funds by category, so
this is checkable rather than remembered. A category at zero was named in the
schedule with nothing against it; a category absent was not in the schedule;
an award with no rows has not been read. `v_invoice_budget_check` reports
`evaluable = false` for the third case rather than passing — both sides of the
comparison are empty sets on an unread award, and an empty set matches an
empty set perfectly.

**All four America Makes schedules are transcribed now**, and the three that
were missing were each missing for a different reason: Hybrid Phase 2's
Schedule B is an *image* on page 17, Last Tactical Mile's is plain text on
page 44 that nobody had been to, and Digital Engineering had **no award row
at all** despite SRA-0350 being on file since the first document drop.

Two things came out of reading them that `sum(award_budget.federal)` cannot
tell apart, so `award_budget_schedule` (migration `052`) records the header
figures a schedule prints for itself and `v_award_budget_check` asks two
questions:

- **Does the schedule foot?** The QuickBooks rule — *every printed subtotal
  must equal what sits under it* — applied to an agreement. LTM's does not:
  its federal categories add to $899,500.76 against a printed $899,500, and
  its cost share to $513,065.12 against $513,065. That is a fact about the
  executed agreement, transcribed as printed. A loader that adjusted a
  category to make the page come out would be inventing a budget.
- **Does it reach the ceiling?** This one is *allowed* to differ and then has
  to say why. Hybrid's schedule is $500,043 and its ceiling $512,409, and
  both are right — the difference is Modification 001. Comparing the two
  without that would report a $12,366 failure on a document that is simply
  older than the amendment.

**And a third dead register.** `award_budget_line` was created in `001`,
written once in `004` with Hybrid's four categories, and **read by nothing** —
so the award reported `evaluable = false` for the whole engagement while its
numbers sat in the database from the first migration. `space_partition`,
`rate.superseded_by`, and now this: a table that looks usable and is filled
by nothing is an invitation to fill it again. `052` drops it, and the figures
were read off the page rather than copied across, because a copy of a copy is
not a transcription.

Read together the four schedules are the restatement's case on the face of
the agreements: **Drive AM budgets no indirect at all** against $583,594 of
labour, **Hybrid none** against $449,043, **ICAM 10% of ODCs only** — $27,500
against $275,000, with $655,190 of labour carrying nothing — and only **LTM**
budgets a real figure, $81,772.76, whose mirror image is $233,543.12 of
*unrecovered indirect* sitting in YBI's own cost share.

## Setting a piece of work up

`/projects`, migration `059`. Read across from the RFP pipeline
(`ubi-wagner/govwin`), which models the other half of the same engagement: it
wins the work and this system accounts for it.

**Two things were taken from its post-award module and a dozen were
deliberately not**, and the second half is the design. Its own build log is
the argument — `docs/PROJECT_MANAGEMENT_DESIGN.md` opens with a superseded
notice explaining that they built `project_wbs_nodes` *beside*
`project_milestones`, then collapsed and dropped it, because

> *"the shape below — a node tree beside a milestone list, each with its own
> dates, costs and CLIN — was two structures describing one thing. It also
> produced two answers to the same question."*

Which is this repository's own most expensive lesson in somebody else's
words: `space_partition` beside `space_unit`, 13.0% and 2.2% at the same
moment, and *the cost objective is the charge code; there is deliberately no
second register of codes.*

Taken:

| | |
| --- | --- |
| `projects` | `project`, **keyed on `objective_id`** — the charge code *is* the project, not a foreign key to one. A project id that could differ from an objective id is two names for one thing. |
| `project_milestone_tasks` | `todo`, with both its rules: blocked says what is blocking, and done carries when and who. Both were already the house style under other names. |

Not taken, because the register exists: `project_assignments` is
`charge_authority` (which already carries *nobody assigns themselves*, one
live grant per person per code, revoked rather than deleted);
`project_clins` is `award_budget`, and these awards carry no CLIN at all so a
CLIN table would be `invoice.milestone_id` again; `project_milestones` and
`project_deliverables` are `milestone`; `project_invoices` is `invoice` and
`receipt`; `project_time_entries` is `timesheet_entry`;
`project_modifications` is `award_term`, which cites the clause. The risks,
reviews, meetings and comments registers are not taken for a plainer reason:
nothing here would write them, and this schema has had eleven columns and
tables that looked usable and were filled by nothing.
`tests/test_projects.py` fails a migration that grows any of them.

**Setting up is one act.** Opening a charge code, saying which contract it
works under, naming who may charge it and writing down the first things to do
were four calls in four places — and a code with nobody on it has its
authority gate switched off, which is right for reconstructing a year already
worked and wrong for work starting now. `POST /api/projects` does all of it
inside one `turn(period)`, through every rule the separate routes enforce, and
the answer says `gate_live` so nobody has to infer it. A refusal partway
through leaves nothing behind, because the whole setup is one transaction.

**And the half `v_worklist` could never hold.** The worklist has always known
*what* is outstanding and `v_worklist_owned` added *which portfolio* can act
on each kind. Neither could say **who** is doing it or **by when**, because
nothing in the system could write that down — so `FOR_TOM_TO_VERIFY.md`'s
twenty-one items, `v_certification_chase`, and "obtain a text-bearing copy of
the Drive AM agreement" all sat on lists with no owner and no date.
A `todo` carries `worklist_kind` + `worklist_entity_id`, and
`v_worklist_covered` joins the machine's list to a person's: **1,089
outstanding, and the interesting column is how few anybody has taken.**

Three things about it worth keeping:

- **No foreign key on the worklist columns, and that is deliberate.** The
  worklist is a view over eleven derived sources and its entity ids are
  computed, not stored. A constraint would have to be a trigger re-deriving
  the whole view on every insert, and the failure it would prevent — a todo
  naming an item that has since been cleared — is the good outcome.
- **Unassigned is a state, not a gap.** On the list and nobody has it is a
  different fact from nobody having written it down. The intake rule, applied
  to work.
- **The coverage screen groups by kind.** 998 of the 1,089 are one kind;
  printing them flat is the defect the evidence screen had when thirty-two
  unread workbooks buried three real proposals.

The seed creates no projects. Who is on each one and what is outstanding on
it are judgments with a person's name on them, and a foundation that invented
them would be the thing this whole file argues against.

## The restatement, and the door it never had

`/restate`, migration `061`. **The point of the whole system — and for as
long as it has existed, nobody could reach it.** Five routes complete since
they were written, and no page, no route in `App.jsx`, no call in `api.js`.
Everything upstream exists so that a number put in front of NCDMM can be
traced back to a judgment somebody signed their name to, and the screen that
puts it there was missing.

The router opens by naming three things it will not do. Two were held. The
third was not:

> *It will not net an over-collection against an under-recovery. They are two
> different conversations: one is money to ask for, the other is money to
> give back, and a single net figure hides both.*

`v_restatement` carried `under_recovered - over_collected AS net_movement` —
that figure exactly, pre-computed, in a column named as though it were the
summary. **Nothing read it because nothing could**, and the first screen to
show a restatement would reasonably have reached for it. Worse than the other
dead columns here: those were empty and answered nothing, this one answers
plausibly. $120,000 to ask for and $120,000 to give back is not a quiet year.
`061` removes it and `tests/test_restate.py` fails a view **or a screen** that
subtracts one from the other — verified against both spellings, because the
first regex matched neither.

**The screen carries the router's three rules**, and they are the design:

- **Nothing is computed on it.** Every figure is read from the row the
  restatement was recorded in, like the review screens. It shows the rate the
  restatement will actually apply — the first draft took `rates[0]`, which was
  FRINGE at 0.00% while the restatement measured against INDIRECT_COMBINED at
  40.64%. A screen showing a different number from the one the server uses is
  a nav stricter than the API in another shape.
- **"Not yet, because", never an empty list.** `candidates` answers with the
  reasons and the reasons are the work.
- **A proposal is not a position.** Everything is PROPOSED until a sponsor
  says otherwise in writing.

**And the refusal that matters says what to do.**
`acceptance_names_its_modification` belongs in the schema — it has to hold
when a handler is wrong — but its refusal reached the person as *"The
database refused this write: acceptance_names_its_modification."* in the one
place the router's own docstring calls **the most likely thing in this whole
exercise to become a finding**. The handler answers first now, naming §4.4
and what to supply; the schema still stands behind it.

Against the live record, with classification at 13% and the rate reading
40.64% — high, which is the honest direction to err — **Drive AM is
$15,278.16 under-recovered on one invoice that claimed no indirect at all.**
The engine's own finding line is the case: *"No indirect line. On a
cost-reimbursement award this forgoes recovery outright."*

`scripts/drive_restate.py` walks it as the controller and the auditor. Three
things came out of writing it. **`restatement` is append-only** — *correct by
superseding, never by editing* — so the drive cannot delete what it made and
should not: a position taken and then withdrawn is part of the trail. Its
census counts restatements **standing as a claim**, and it withdraws its own
through the route a person would use. That is the `invoice_no_delete` lesson
in a second place: a cleanup that assumes it can remove what it made stops
working the day the table grows a guarantee.

**Sealing and having a rate are not the same state, and a drive that assumes
one from the other is a hand-kept map again.** The drive was written to
refuse to seal — correctly: sealing says *these judgments are final*, which
is a judgment, and a drive that makes one to give itself something to measure
is reading its own writing. But it then asserted in its own docstring that
`prove.sh` runs it after `drive_state_machine`, "which seals". It does seal —
and then unseals, which supersedes every rate — so on a proof from an empty
database there was no rate and the drive exited 2 against working code. The
distinction it was missing is the one that matters: **computing is arithmetic
and sealing is a judgment.** It computes now where the set is already sealed,
over judgments it did not make and cannot reach, and stops only where the set
is open. And it finds that out by asking `POST /api/rates/compute`, which is
the only thing that knows — a second reading of `decision_set` in the drive
would be a copy of the rule, free to drift from it, which is the defect it
was just caught in.

## Cost is not income

Migration `064`. **The controller was being asked to judge $6.9m of
revenue.**

`039` put the definition of coverage in the schema because the classification
screen and the auditor's report answered 13.0% and 2.2% at the same moment,
and it scoped the answer to the P&L. Its comment says why: *"balance sheet
movements are not cost to classify."* True, and one level too coarse —
**income is on the P&L.** Measured on the live record:

| section | dollars | groups |
| --- | --- | --- |
| Expense | $10,026,369.84 | 748 |
| Other Income | $116,948.54 | 6 |
| COGS | $37,323.72 | 3 |
| **Income** | **$6,876,763.86** | **242** |

242 of 999 groups and 40.3% of the scope was revenue, all of it open,
because there is no answer: grant income does not go in a cost pool. Four of
the six largest things on Tom's queue were `3900 Grant Income` and
`4015 Program Fees`. The screen this file calls *the one that matters* opened
on work that cannot be done, sorted worst-first because those rows are big.

Two consequences, and the second is the worse one:

- **A quarter of the queue could not be actioned** — 999 groups to look at
  where 757 is the number.
- **Coverage read 13.0% where the truth against cost is 21.8%.** That figure
  is on every workpaper, in the 990's NOT FILEABLE banner, in the rate's
  working-figure caveat, and it was quoted to the board. Wrong by a factor of
  1.7, in the pessimistic direction, because its denominator was 41% revenue.

`ledger_line.section` has carried the P&L's own section on every line since
the first import — Income, COGS, Expense, Other Income, CHECK-constrained on
`pl_account` — and **nothing had ever used it to decide what is cost**. That
is the discriminator, not a regex on account numbers.

**Other Income stays in scope on purpose.** 2 CFR 200.406 makes applicable
credits — refunds, rebates, adjustments — a reduction of cost rather than
revenue, so somebody has to look at those six groups. Only the Income section
comes out. A line whose section is blank stays too: not knowing what
something is is a reason to look at it, which is the intake rule applied to
scope.

And it is **defined once**, in `v_cost_line`. Four places expressed this
scope by hand — the coverage view, the worklist, the queue handler and the
evidence matcher — which is precisely the shape that produced 13.0% and 2.2%.
`tests/test_review.py` fails a handler that grows a fifth copy.

## Walking the whole year, and writing down why

`app/domain/classification_log.py`, `scripts/classification_log.py`,
`docs/CLASSIFICATION_LOG.md`. A reasoned treatment for every one of the 757
cost groups, walked a month at a time from January, with a citation and a
rationale on each — and a named reason where there is none.

**It proposes and does not decide, and that is not a hedge.** Run without
`--apply` it writes nothing to the cost record at all. With `--apply` it
records through the real API signed in as the controller, so every judgment
carries that person's name and an audit row. There is no path in it that
writes a decision behind the API's back. *Proposals are never decisions*: a
log that sealed 572 judgments would put the machine's name on the seal, and
the seal is the whole reason a reviewer can be told the rate was not
reverse-engineered.

**The walk is monthly and the judgment is not.** The unit is a group — an
account and a payee — and a group spans months, so a strictly monthly queue
deals the same group twelve times. Each group is reached in **the month it
first appears** and judged once. And the log covers the *whole* ledger rather
than what is open, so it reads the same after its recommendations are
accepted: a log that empties itself when acted on cannot be checked against
the books afterwards, which is the one time anybody will want to.

Four things came out of walking it that reading one screen at a time did not
show.

**A split that lands in one pool is not a split, for this question.**
`propose()` refused all twenty-four crosswalk splits, on the right principle
— *a split needs a documented driver, and proposing one side would be
inventing it*. But five of them (Rising Tides, LTM, Drive AM, Digital
Engineering, AAMEN) divide by *natural type*: labour to 5100, subawards to
5200, materials to 5300, travel to 5500 — and **every one of those numbers is
in the DIRECT range**. The split decides which 2026 account; the queue is
asking which 2025 pool. **$1,382,737 of the queue was refused on a slash.**
The test is on the pools now, and `test_the_crosswalk_refuses_to_guess_a_split`
asserts that property rather than the literal source `'"/" not in mapped[0]'`
— it was testing the punctuation rather than the rule it describes, which is
the same defect as `test_coverage_is_defined_once` asserting `l.statement =
'P&L'`.

**And the proposal it did make could not be accepted.** The crosswalk branch
returned DIRECT with `objective_id: None`, which `direct_needs_objective`
refuses outright — on **24 accounts of the live ledger**. Pressing Enter on
the queue's own suggestion answered a constraint violation. It is the
nav-stricter-than-the-API defect pointing the other way: a screen offering
what the server will not take. The objective is read off the account path
now, because 2025 buries programme identity in the account *name* — the
structural defect the 2026 chart fixes — and `customer_job_hint` is empty on
all 4,038 cost lines, so the path is not merely a signal, it is the only one.

**A pass-through is not cost, and the ledger says so on its face.**
`5027 TTC Utilities` is $257,774.24 of gross movement and **$0.00 net**: Ohio
Edison bills 255 W. Federal and Steelite International — a tenant —
reimburses the identical amount, line for line, twelve pairs. It needs no
square footage; the tenant pays all of it. `ARC Arise` is $21,000 in and
$21,000 straight back out. Coverage counts *absolute* dollars so a group
counts by what it moved, which `039` chose deliberately and which is right —
but it puts these at the top of a worst-first queue while they represent no
cost at all.

**An account can be something other than its name.** `5227 Portfolio
consulting` — $588,538.89 net, 442 lines, 72 payees, this file's "largest
single open judgment" — is not a consulting expense account. Its entries are
`50% of <vendor> Invoice #N` booked back against a portfolio company: a
fifty-fifty cost share where YBI pays a service provider and the company
repays half. $1,531,822.61 of debits against $943,283.72 of credits. And
among them **a $392,447.09 pair on 31 December, no payee, no description,
posted and reversed the same day** — one wash worth $784,894 of the account's
$2,475,106 gross and nothing of its net. It stays blocked: the pool turns on
whether supporting portfolio companies is programme delivery or YBI's own
business development, and the ledger cannot answer that.

### What it will not judge, and what each is waiting for

$3.9m of the $10.2m, every dollar of it naming the thing to go and get.
"Cannot be classified" on its own is a dead end — the shape this file keeps
finding — so a test fails a block whose reason is too short to act on.

| | |
| --- | --- |
| **$2,475,106** | what portfolio consulting serves (above) |
| **$850,383** | the asset register's funding source. Depreciation has *two* splits, not one: the occupancy share is the carve-out's to make, and 200.436(b) makes depreciation on a federally funded asset unallowable. The fixed-asset schedule has no funding-source column at all — which 200.313(d)(1) requires and is a finding of its own. The largest figure here that no amount of reading the ledger can settle. |
| **$283,761** | intern wages, carrying the $45,053.24 donor credit, not yet reposted in QuickBooks |
| **$110,183** | Other Income — and **$105,865.41 of it is a Q1 *2020* Employee Retention Tax Credit** received from Staffmark in May 2025. A credit relating to a period in which federal awards bore the wage cost is due back to those awards under 200.406(b), and which 2020 awards bore them is not on this record. New, and not on `FOR_TOM_TO_VERIFY.md` yet. |
| **$88,870** | splits that genuinely cross pools — dues between G&A and unallowable memberships, travel between direct and administrative |
| **$71,797** | cost objectives that do not exist: ARC Arise and SBA Growth Accelerator have no `cost_objective` row |
| **$57,596** | the insurance policy schedule, splitting property from general liability. **Both halves are indirect, so this moves the OVERHEAD/G&A split and not the combined rate.** |

**Occupancy is deliberately *not* on that list, and getting it right is the
difference between a usable answer and a wrong one.** The 2026 chart books
tenant cost straight to 93xx, so there it is a classification question. 2025
has no such account: occupancy goes to OVERHEAD and the tenant share comes out
at rate time as a 200.465 carve-out. The square footage is the *carve-out's*
problem, not the classification's. That exception is written down in
`tests/test_classification_log.py::DELIBERATE` with its own staleness check,
because the first version of the cross-pool test listed three accounts by hand
and every one was blocked by a named rule several branches earlier — so it
passed with the rule it was written about deleted. **A test that cannot fail
for the thing it names**, found by watching it fail.

What it carries instead is a warning that moves the rate. Facilities accounts
already hold **$262,885 of tenant credits** — Real Estate Tax is $149,466
gross and $26,527 net, Boardman Street Electric $154,268 and $78,514 — so part
of the tenant share is *booked* rather than estimated. Carving a square-footage
share on top of a figure already net of recovery removes the same money twice.

### The rate that falls out

**100% of the 2025 ledger classified — 757 of 757 groups, $0.00
unclassified** — recorded through the API as Tom, sealed at 757 judgments,
and computed:

| | | | |
| --- | --- | --- | --- |
| FRINGE | **21.90%** | $401,783.60 | over the register's $1,835,047.18 (salaries and wages) |
| OVERHEAD | 29.61% | $1,497,879.12 | over $5,058,960.45 MTDC |
| G&A | 5.21% | $263,517.59 | over the same base |
| **INDIRECT_COMBINED** | **34.82%** | $1,761,396.71 | over the same base |

Pools: DIRECT $2,425,193.27 · EXCLUDED $1,906,942.40 · OVERHEAD
$1,497,879.12 · FRINGE $401,783.60 · FUNDRAISING $281,203.71 · G&A
$263,517.59 · UNALLOWABLE $115,640.95.

**Every pool ties at `pool_variance` 0.00, all four `v_rate_anchor` rows
tie, and all eleven cross-reference controls tie.** Nothing was tuned: the
fringe pool is the six accounts the P&L names and the denominator is the
payroll register, so **0.2190 falls out**.

### The last three accounts that would not classify, and what moved them

**A consultant pass-through is contractor cost and belongs in the base.**
`5227 Portfolio consulting` — $588,538.89 net over 442 lines, this file's
"largest single open judgment" — is YBI paying a service provider for a
portfolio company and booking half back: $1,531,822.61 of debits against
$943,283.72 of credits. 200.331 decides which it is. A *subrecipient*
carries out part of a federal programme in its own right and counts in MTDC
only to the first $25,000; a *contractor* provides services inside the
recipient's own programme and counts in full. These consultants deliver into
YBI's incubation programme against YBI's scope, so they are contractors and
the whole amount is in the base — **which is the point of putting it there.
The oversight is the recovery.** YBI selects the consultant, scopes the
engagement, administers the payment and carries the other half; that
administrative effort is what the G&A pool pays for, and moving the cost out
of the base because it "passes through" would forgo recovery on the very
activity the administration exists for.

**The wage accounts must not be in a pool at all.** `compute` feeds
`v_labor_effective.distributed_wages` into `add_labor()`, which sets
`direct_labor` per objective — $1,835,047.18, the register to the cent.
`build()` separately puts every DIRECT decision into `direct_nonlabor`.
**Both feed MTDC.** So a DIRECT judgment on `5140 Employee Wages` would add
$1,678,157.27 of labour to a base that already carries it and every indirect
rate over that base would read low by the width of the payroll. EXCLUDED is
not "this is not cost" — it is the pool enum's word for cost the pools must
not carry, and the reason is on the judgment.

**`PENDING` is a federal treatment and this log had been ignoring it.**
Depreciation is $850,382.89 of occupancy cost, so OVERHEAD is not in doubt;
what is in doubt is 200.436(b), because depreciation on a federally funded
asset is unallowable and the fixed-asset schedule has no funding-source
column. Refusing to classify it left the largest single figure out of the
pool entirely; calling it ALLOWABLE would claim depreciation YBI may not be
entitled to. PENDING puts the cost where it belongs and leaves the claim
open, which is what is actually true. The same word carries the Staffmark
ERTC, which is excluded from the pools because it is **2020's** credit and
owed back under 200.406(b).

### A rate that depended on how many times you pressed the button

And the fix that came out of computing it. `_build_model` read the fringe
rate from **whatever FRINGE rate was already on file** — and on the first
computation after a seal there is none, because the FRINGE rate is produced
by that same call a few lines later. So the first compute built every
objective's base with no fringe in it and every later one built it with
fringe, and one sealed set answered **37.82%, then 34.82%, and 34.82% for
ever after** — converging silently on the right answer after one wasted
press.

**Nothing could catch it.** The pools tie to themselves either way, so
`v_rate_buildup` reports TIES on both; and *MTDC is deliberately not
anchored*, for the good reason recorded above — a second derivation of it in
SQL would be one figure computed twice. The base is the one part of a rate
with nothing standing behind it, and this lived there.

`PoolModel.apply_fringe()` derives the rate from the model's own FRINGE pool
over its own wage base, both already built, so the computation stops
depending on its own history.
`tests/test_rate_anchor.py::test_the_same_sealed_set_computes_the_same_rate_twice`
runs it twice and compares — **and asserts the first run's base carries the
fringe**, because a model that never puts fringe in the base would be
perfectly stable at the wrong answer.

### Three things to settle before this rate leaves the building

- **No 200.465 carve-out is in it.** Per the section below, a seeded record
  has no buildings, so OVERHEAD is uncarved and every dollar of tenant and
  vacant occupancy cost is in the federal pool. That pushes 29.61% *up*.
- **Administrative labour is an objective, not pool cost** — *set up for a
  decision, and deliberately not applied.* See **A decision, not a property
  of the code** below.
- **`evidence_ratio` is 0.0000 on every objective.** Nothing is
  timesheet-backed; the whole distribution is management reconstruction,
  which is exactly what `v_certification_status` has been saying.


### A decision, not a property of the code

Migration `068`. `YBI-GA` carries **$264,444.90** of wages ($322,358.32 with
fringe) and the model treats it as a **cost objective**, so it takes a
$100,013.06 allocation *of* indirect rather than forming part of it. 2 CFR
200 Appendix IV B puts the director's office, accounting and personnel
administration *in* the G&A pool, and the YBI-GA distribution is Kelly, Ruby,
Shaulis, Jaric, Politsky and Ewing — the administrator herself. Modelling
that as an objective **allocates the indirect pool to its own
administration**, which recovers from nobody.

The counter-argument is real and does not apply here: `FUNDRAISING` and
`UNALLOWABLE-ACTIVITY` *are* deliberately benefiting objectives, because
200.413 and Appendix IV B.3.d make them bear indirect while recovering
nothing. General administration is the opposite case — it **is** the
indirect.

It is **34.82% against 43.99% on the same sealed judgments**, ~$464,000 a
year on a $5.06m base. That is too large to be a property of whichever code
happened to be deployed, and it is a judgment rather than arithmetic:
whether YBI-GA is genuinely general administration or the bucket
unattributable time went into is something only the person who built the
reconstruction can say. So the treatment is a **recorded choice on the
rate** — `rate.admin_labour_basis`, the way `base_type` already records
which base a rate was taken over — chosen per computation, defaulting to
`OBJECTIVE`, which is exactly what every rate before `068` used. **Nothing
changes by default.**

`v_admin_labour_decision` puts both answers on one row, so the decision is
taken with the alternative visible rather than against a number somebody
remembers, and reports `NO DATA` where there is no allocation to move. It is
also an independent check: the view's arithmetic on the recorded OBJECTIVE
row gives 0.439926, and the engine computing under POOL gives 0.4399 — two
routes to one figure.

Two things came out of building it:

- **The wage base is the payroll register and stays the payroll register.**
  Deleting the objective took its $264,444.90 out of the *fringe* base as
  well and the fringe rate went 21.90% to 25.58%. Administrative staff draw
  benefits like everybody else, so their wages belong in the fringe
  denominator whether or not their salary sits in the G&A pool — two
  questions, and the first draft answered both at once.
  `WAGE_BASE_IS_THE_REGISTER` and `FRINGE_RATE_ON_THE_REGISTER` both reported
  OPEN the moment it ran, which is what `066` and `067` are for. And the base
  *type* cannot tell the two apart — `SALARIES_WAGES` is legitimately either
  the payroll the fringe pool is spread over or the base an indirect pool is
  allocated on — so `base_amount(..., fringe_denominator=True)` makes the
  caller say which. Inferring it from the type silently returned
  wages-without-fringe on a `SALARIES_FRINGE` denominator.
- **A control nobody can clear by doing the work.** Under POOL the G&A pool
  carries labour that came from the effort distribution rather than from a
  classification, so `v_rate_buildup` reported OPEN by exactly that amount
  the moment the choice was made — `FACILITY_UNPARTITIONED` again. It reads
  the expected pool against the basis the rate was computed on, the way
  `pool_state` already reads against the completion of the classification.
  The first fix then reported INDIRECT_COMBINED OPEN by exactly the G&A
  gross: `pool_for_kind` has **two rows** for that kind, so an add-back
  joined to it multiplied the pool. Aggregate first, add once afterwards.

Both bases tie on the live record — every pool at `pool_variance` 0.00, all
four `v_rate_anchor` rows, and FRINGE at 21.90% under either:

| | OBJECTIVE | POOL |
| --- | ---: | ---: |
| FRINGE | 21.90% | 21.90% |
| OVERHEAD | 29.61% | 31.62% |
| G&A | 5.21% | 12.37% |
| **INDIRECT_COMBINED** | **34.82%** | **43.99%** |

### The carve-out that cannot fire, and says nothing

Which is how the correction turned up something worse. `v_facility_occupancy`
inner-joins to its space totals, and on a record with **no buildings at all**
it returns nothing — so `POST /api/rates/compute` computes **no 200.465
carve-out**, `carve_out` stays empty, `pool_carved` reads 0.00, and
`v_rate_buildup` reports TIES because the pool does tie to itself.

Nothing distinguishes *there is no tenant space* from *nobody has measured
any*. `029`'s lesson — an empty set matching an empty set perfectly — in the
one adjustment this file calls **the single largest in the rate model**. And
the worklist is silent too: `SPACE_UNMEASURED` fires per building, and a
record with no buildings has none to fire on, so the gap raises nothing
anywhere.

`scripts/classification_log.py` reports it as a three-state anchor rather
than letting it pass: *not evaluable — no building is on the record, so
every dollar of tenant and vacant occupancy cost is in the federal pool.*
That is a read-side report, not a fix; the fix is a control that refuses to
call a rate complete while the carve-out has never been evaluated, and it
belongs in the schema.


### Read it backwards, and it has to say the same thing

`scripts/classification_log.py --reverse` walks December back to January.
**It must change the order and nothing else** — `judge()` is a pure function
of one group, so the same ledger has to produce the same judgments read
either way, and a log whose recommendations depended on the direction of the
read would be one where the order of the books decided the rate. Nobody
would find that by looking at either run alone. Every run now walks both
directions and compares, by group key rather than by position: comparing
elementwise would report 757 differences on a correct run, which is a test
arguing against working code.

All 757 agree. What the second pass found was not in the ordering.

**$986,592.77 was marked federally allowable on non-federal objectives.**
The first version dressed every DIRECT judgment `ALLOWABLE`, which is an
assertion about a federal award, and Rising Tides ($582,086), ESP
($284,824), the Hub, MBAC, Youth, Xjet and VGV have no award behind them.
Rising Tides is the one that stings: whether it is federally funded is an
open question in this engagement, the objective master says it is not, and
the log took a side on it in 33 places without saying so. The treatment
follows `cost_objective.is_federal` now — read from the record, not copied
into the module — and where it answers no the rationale says which objective
and why.

**And the parent of an account names the function.** Six accounts were
blocked as cross-pool splits while sitting under
`Management & Administrative Expenses` or `5080 Fundraising`, which is the
bookkeeper saying what kind of activity it is. Using the path for the
objective and refusing it for the function held one signal to two standards.
It only settles a split whose branches *differ in function*: insurance
divides 7300 from 8300 and both are indirect, so the parent cannot tell them
apart and it stays blocked.

**`5215 Dues and Subscriptions` was blocked on a misreading of 200.454.**
The crosswalk's note says civic and community memberships are unallowable.
The rule says otherwise: (a) allows business, technical and professional
organisations, (b) allows business periodicals, (c) makes civic membership
allowable **with prior approval**, and only (d) — a country, social or
dining club — is refused outright. Sixty payees, not one of them a club:
Mailchimp, LinkedIn, Zoom, Adobe, chambers of commerce, the Better Business
Bureau, one newspaper. The split does not arise on these facts.

671 of 757 groups now, up from 572, and coverage from the log alone goes
0% → **40.5%**. The 86 still open name something findable — and two of them
are new: `5001 Cost of Goods Sold` waits on an inventory journal entry its
own description points at (*"Used Inventory (See JE for breakdown)"*), which
makes it the cheapest $37,261.00 on the list; and `SBA Growth Accelerator`
waits on a `cost_objective` row that has never been opened, so the block
names the objective to open rather than reporting a gap.

**Three of the new assertions did not fail when I broke the code, and each
said something.** A break that alternated on index was neutralised by
arithmetic — reversing an odd-length list preserves every element's parity.
A genuinely stateful walk still passed, because the fixture had one group
per account and the live ledger has 757 groups over 87 accounts, so the
fixture could not express the collision. And the "more than one candidate"
guard was tested through insurance, which a named rule catches several
branches earlier — the same defect as the cross-pool test before it, found
the same way. The guard is `pick_branch()` now, tested directly, because
**no live crosswalk entry divides two indirect branches** and nothing
exercises it through `judge()` at all.


## The build-up ties to the pool

Migration `065`. `063` gave `carve_out` its writer; this is the control that
would have caught the defect on its own. **Nothing had ever compared the rate
to the pool underneath it.** `rate.pool_amount` is what the computation used;
`v_pool_balance.allocable` is what the ledger says is left after recorded
carve-outs. They sat $932,254.78 apart, in adjacent columns on the same
screen, for the life of the system.

`v_rate_buildup` carries `pool_variance` and `ties` now. Two other things it
could not say, both visible the moment carve-outs started being written:

- **INDIRECT_COMBINED had no pool at all.** The join was `pb.pool = r.kind`
  and there is no pool of that name — it is OVERHEAD plus G&A. So the rate
  that is actually applied to a restatement showed blank gross, blank carved,
  blank allocable and zero carve-outs, while OVERHEAD beside it showed all
  four. The one figure that leaves the building was the one with nothing
  behind it. It rolls up the two pools it combines now, expressed as data
  rather than as a `CASE`.
- **An empty pool read NULL, not 0.** FRINGE and G&A showed `pool_amount =
  0.00` from the computation and NULL from the LEFT JOIN, side by side,
  meaning the same thing in two spellings — and a tie cannot be evaluated
  against a NULL.

### And the tie points anchor at completion

Migration `066`. The control `065` added then reported **TIES on FRINGE and
on G&A over nothing at all** — an empty pool holds 0.00, the ledger says 0,
and `0 = 0` is green. That is `029` reproduced *inside the control written to
catch the last one*: **an empty period compares zero against zero and looks
green.** A control that cannot be evaluated has not passed.

**The way out is completion**, and it is the same idea at two scales.

`pool_state` is three states now. While anything is unjudged, an empty pool
means *nobody has judged any of this yet* — `NO DATA`. Once `unclassified`
reaches zero it means *there is none of this*, which is a figure and ties
honestly. So the state is read against the completion of the classification
rather than against the pool alone, and `tests/test_rate_anchor.py` holds
both halves: the same empty pool is NO DATA with cost outstanding and TIES
with the queue finished. `OPEN` is never softened by completion.

**And a rate is a pool over a base, so `065` had anchored only the
numerator.** `v_rate_anchor` adds the two comparisons that have genuinely
independent sources:

| | |
| --- | --- |
| `POOLS_ACCOUNT_FOR_JUDGMENTS` | the signed sum of live decision lines against the sum of every pool's gross. **Nothing had ever compared them**, so cost could go missing between the queue and the pools and each pool would still tie to itself perfectly. |
| `WAGE_BASE_IS_THE_REGISTER` | the fringe denominator against `register_wages` on the eleventh statement control — *the fringe base comes from the effort distribution, not from the ledger's wage accounts*. The anchor existed and the build-up never pointed at it. |

**Signed on both sides of the first one, deliberately.** Coverage measures in
*absolute* dollars — `039` chose that so a group counts by what it moved —
and the pools carry the signed position, so the same judgments read
$2,219,105.55 and $1,678,057.27. Both are right, and comparing those two
would be a false alarm every time a credit is judged.

**MTDC is deliberately not anchored.** It is labour plus fringe plus direct
non-labour less the 200.1 exclusions, and every part comes from the model, so
a second derivation in SQL would be one figure computed twice — the thing
that can disagree with itself. It is anchored through its parts instead: the
labour in it is the wage base, and the non-labour in it is the DIRECT pool,
which the first control covers.

These are read-side only. `POST /api/rates/compute` gates on the statement
register because a rate over books that disagree is a rate over the wrong
numbers; these are checks *on* the rate it produced, and gating a computation
on a control derived from its own output would be circular.

### The hard anchors for fringe

Migration `067`. The engagement has hard figures off the source documents,
and they reproduce on the live record to the basis point:

        the P&L's six fringe accounts        401,783.60
        the payroll register's wages       1,835,047.18
        ---------------------------------------------- = 0.2190   21.90%

        the same pool over the *ledger's*
        wage accounts, 1,789,993.94                     = 0.2245   22.45%

**21.90% and 22.45% are not two opinions. They are one pool over two
denominators, and only one of the denominators is the payroll.** The whole of
the difference is $45,053.24 — the donor credit that sat in an intern wage
account for a year, understating the ledger's wages so that any rate taken
over them reads high. The eleventh statement control already finds that
number (`gross_difference` 45,053.24, `named` −45,053.24, `unexplained`
0.00); this is the other end of the same fact.

**They are controls, not inputs, and the distinction is the whole system.**
Nothing here sets a rate — *no rate is computed or displayed during
classification, the set is sealed first, and the rate carries the seal.*
Writing 21.90% in as an input would be exactly the reverse-engineering the
seal exists to rule out. So the fringe rate is anchored the honest way, **by
anchoring both of its parts**: the numerator to the P&L's fringe accounts and
the denominator to the payroll register. 21.90% then *falls out* rather than
being asserted.

And it does. Judge the six accounts the P&L names as fringe and the pool
comes to $401,783.60 to the cent and the computed rate to **0.219000** —
arrived at from the judgments, checked against the documents.
`scripts/drive_buildup.py` does exactly that every run and states the hard
number, the alternative denominator and the credit between them before it
checks anything.

One thing to know rather than trust: the six accounts are named **by hand**
inside `v_payroll_reconciliation` — 5130 Benefits, 5133 401k, 5145 BWC, 5151
FICA, 5185 FUTA, 5195 SUI. That is the hand-kept-map shape, left alone
deliberately: it is a transcription of which accounts are fringe, which is a
judgment somebody made once, and inventing a rule to derive it would be
guessing at that judgment.

**And `PROJECT_CONTEXT.md` carried both figures.** Its recommendation tables
said 22.45% while §8.6 said *"21.90% remains the defensible figure"* — a
load-bearing document contradicting itself with the stale number in the row a
reader would quote. Corrected from the record. The combined indirect rate is
flagged rather than restated: fringe is part of total direct cost, so MTDC
moves with it, and recomputing 31.78% needs a complete classification —
*every derived figure ties to a control, and one recomputed from an
incomplete pool would tie to nothing.*

One thing worth not repeating: **the boolean assumption survived two more
places in the file that introduced it.** `drive_buildup`'s `check_ties` read
`not ties` and would have called a pool nobody has classified into a broken
control; so did its carve-out restore check, one function away. Finding one
of these in a file is the argument for reading the rest of it.

`scripts/drive_buildup.py` walks the whole chain and is the answer to *does
the rate build up completely as items are classified*:

    classify a group      ->  coverage moves by that group's own dollars,
                              and the scope does not move at all
    classify into a pool  ->  that pool's gross, allocable and rate move,
                              and no other pool's does
    classify DIRECT       ->  the MTDC base moves, so the indirect rate does
                          ->  and the wage-based fringe base does not
    compute               ->  carve-outs recorded, every objective allocated
    at every step         ->  rate.pool_amount = v_pool_balance.allocable

Its last step takes the carve-outs out from under a live rate and checks that
the build-up **reports two rates not tying, by -$932,254.78** — because a
control nobody has watched fail is a control nobody has tested.

### The register was never $1,835,047.18

Migration `069`. `v_labor_effective.distributed_wages` was
`round(payroll_wages * share, 2)` computed **per row, independently**, so a
person's distributed wages did not have to add back to what they were paid.
The residual was lost or gained a cent at a time, and **six of the
forty-three people already drifted** before any timesheet existed. The
eleventh control tied anyway, because the cents happened to net out — which
is luck, not a control, and the worst kind of green.

Read off the controller's workbook, column B, forty-three employees, the
register is **$1,835,047.17**. `FOUNDATION.md`, `BASELINE_2025.md`, `067`'s
anchors, the classification log and a memo all carried `.18`, which is this
view's rounding; `BASELINE_2025.md` carried `.16` in a third place. Three
readings of one document, which is what per-row rounding produces when
different things aggregate it. The rule was already written down — *figures
in a document for somebody else get read from the record, not recalled* —
and here the record itself was recalling an artefact.

**Nothing published moves.** 401,783.60 / 1,835,047.17 is 0.2190 to four
places, as it was; every pool ties, all four `v_rate_anchor` rows tie, and
all four rates are unchanged. What moves is the cent: the difference the
Bacon credit explains is $45,053.23, and `reconcile.py` computes the
`ROUNDING` item from the live difference rather than a constant, so it lands
at $53.23 on its own and `PAYROLL_REGISTER` ties without being told to.

**What exposed it was adopting a reconstruction as a timesheet.** Submitting
one switches that person's distribution from reconstructed units to hours,
the shares move in the sixth decimal, the cents fall the other way, and the
eleventh control went OPEN by $0.01 — refusing `POST /api/rates/compute`
outright. The certification work asks forty-three people to do exactly that,
so it would have fired on the first one and gone on firing.

Largest remainder now: floor every share to the cent and hand the spare
cents to the largest remainders, ties broken by objective so the answer is
deterministic. **`floor` rather than `round` is the load-bearing part** — a
floor can only be short, so the spare is always a non-negative number of
cents to hand out, where rounding to nearest makes it signed and a negative
spare is the shape that silently drops a line.

## The sheet somebody signs

`GET /api/timesheet/draft`, `POST /api/timesheet/adopt`. The whole
$1,835,047.17 labour distribution is `MANAGEMENT_RECONSTRUCTION`, there are
**zero timesheet entries and zero certifications**, and 43 people carry
`NEEDS_CERTIFICATION` at BLOCKING. That does not change a figure in the rate;
it changes whether the rate is *usable*, because 200.430(i) goes to the
allowability of the entire direct labour charge.

**The goal is not to invent 2025 timesheets.** 200.430(i) does not require a
contemporaneous record — it requires one that reflects the work actually
performed, supported, and reviewed after the fact. A reconstruction the
person reads, corrects and signs meets that; a reconstruction nobody ever saw
does not, which is where 2025 has been sitting. So the draft is the
controller's reconstruction shown to the person whose work it was, and
adopting it writes the entries **under their own name**. `require_own_writes`,
the calling actor's own employee key, and no parameter naming anybody else —
the router's first rule does not bend for this.

Three things came out of building it, and each is a rule this file already
has in another place:

- **The terms come from the register of terms.** The draft read
  `expected_hours` from `v_timesheet_coverage`, which is `FROM
  v_timesheet_entry` — so somebody with **no entries has no row in it at
  all**, and that is exactly who the draft is for. It told a person whose
  terms were on the record that nobody had recorded any, and no draft could
  ever become adoptable: its precondition was satisfied only by already
  having the entries it exists to create. `FACILITY_UNPARTITIONED` in a new
  place.
- **A `timesheet_entry` is a day.** The first version wrote one entry per
  objective dated the last day of the period, reasoning that spreading a
  reconstruction across the calendar manufactures a daily record nobody has.
  The concern is real and the table had already answered it:
  `timesheet_hours_sane` caps a row at 24 hours and `timesheet_day_must_fit`
  caps the person-day at 24 across rows. **978.68 hours on 31 December is not
  a coarser record, it is a refused one** — *read the schema, never recall
  it.* Uniform across the weekdays of the employed span is the honest shape:
  visibly the same split every day, which with `RECALL` on every row says at
  a glance that this is a reconstruction. Varying it to look contemporaneous
  is what would manufacture precision.
- **The hours adopted are the hours the draft showed.** The residual went on
  the last day, and where the daily rate rounded *up* the residual went
  negative and a `<= 0` guard skipped it: 25.31 hours adopted as 26.00, and
  the sheet said one figure while the record held another. Largest remainder,
  and `spread_hours()` is a pure function tested directly, because this
  arithmetic was wrong twice.

**Submitting does not move the rate, and that is the property worth having.**
A submitted timesheet switches that person's distribution in
`v_labor_effective` from reconstructed units to hours; adopting the
reconstruction faithfully reproduces its shares, so the rate holds. If it did
not, the rate would depend on who had got round to signing.

## Five registers with no writer, found by sweeping rather than by reading

Migration `063`, `tests/test_no_register_is_dead.py`. **This is the answer to
the shape, not the twelfth instance of it.**

Every previous one — `space_partition`, `rate.superseded_by`, the three
`evidence` fact columns, `award_budget_line`, `donation_rate`, the three
`lane_*` override tables — was found by somebody reading one area closely,
and this file has said *"assume there is a fifth"* for months. A note to self
is the hand-kept map applied to defects: it cannot be wrong, so it is never
checked, and it never finds anything.

The sweep derives every table and column from the database, asks what could
write each, and fails on one that something reads and nothing writes. No list
of tables in it — the database is the list, the same way
`tests/test_sql_is_real.py` hands the schema the code. It found five tables
and they split three ways.

**`carve_out` was the worst instance in the system, because of where the
wrong answer landed.** `POST /api/rates/compute` builds the 2 CFR 200.465
facilities carve-out from `v_facility_occupancy` and applies it correctly —
the rate it persists is right. It never wrote the carve-out down, and three
things read that table: `v_pool_balance`, `v_rate_buildup` and `/review/rate`.

Measured against the live record: the computation carved **$932,254.78** out
of a $1,678,057.27 overhead pool — 3,000 of 5,400 usable square feet at Tech
Block 5, tenant and vacant — while `v_pool_balance` reported `carved = 0` and
the review screen showed no carve-out at all. **The single largest adjustment
in the rate model, 55.6% of the pool it applies to, absent from the workpaper
an auditor reads, with a control-shaped view asserting the opposite.** It
also broke the rule the review screens exist on: *every figure is read from
the row it was recorded in* — the row was never written, so the screen read
zero. The handler writes it now, in the turn that writes the rate, against
the same seal, rewritten each run rather than appended to.

**`constraint_result` told the controller an invoice was safe to issue
because nobody had checked.** `GET /api/awards/{id}/trueup` counted blocking
failures and answered `INVOICE_ISSUABLE` when it found none; it found none on
all four awards because `app/domain/awards.py::test_constraints` — a complete
engine, written with the schema — **had no caller anywhere**. An empty set
matching an empty set perfectly, which is what `029` fixed for the eleven
controls and what `v_invoice_budget_check` already reports as
`evaluable = false`.

It runs from the rate computation now, inside that turn and against that
rate's id, because every one of these tests is a statement about a claim and
a claim is direct cost plus a rate applied to it. `Constraint.evaluable`
carries the three-state, and `unevaluable_never_passes` holds it in the
schema. Six tests × four awards, and the first run is not decoration:

- **COST_SHARE fails on Last Tactical Mile ($513,065) and Hybrid
  ($104,000).** The $617,065 this file calls *the largest untracked
  obligation in the file* is now a failing test rather than a paragraph.
- **RATE_METHOD fails on all four** — awards set to `DE_MINIMIS_10`, model
  applying `NEGOTIATED`. The restatement's whole thesis, stated as a
  constraint against each agreement.
- **EVIDENCE is unevaluable on all four**, because nothing is classified to
  those objectives yet. Unevaluable, not passed.

**`ledger_revision` is dropped, because the shape it records cannot occur.**
It held a source line amended after somebody judged it, and `v_worklist`
raised `STALE_DECISION` off it. The importer inserts lines `ON CONFLICT
(line_id) DO NOTHING` and nothing updates one, so a ledger line cannot change
after it is written: this system models change by supersession. The
classification queue carried an **"Amended" filter that always returned
nothing and a tick that never lit** — a control on the screen the whole
engagement is worked from that doing the work could not clear, which is the
`FACILITY_UNPARTITIONED` defect in the worst place to have it.

**`control_total` and `evidence_match_proposal` are dropped because nothing
reads them either.** The first predates `v_statement_reconciliation`, which
computes rather than stores; the second predates
`domain/evidence_match.py`, which deliberately persists nothing — *proposals
are never decisions*, so a proposal register is a second place a judgment can
appear to have been made.

**The allowlist is the part that has to stay honest.** Twenty-three columns
are written by nothing on purpose, each carrying its reason, and **an entry
that is no longer needed fails the test** — so the list can only shrink by
somebody noticing, which is the opposite of how the twelve got there. An
entry with a reason under twenty-five characters fails too: an allowlist
entry with no reason is the defect wearing a permission slip.

Two things worth carrying from writing it:

- **The detector was itself an instance of the class, twice.** Its first
  draft matched `SET col =` and `"col":` anywhere in the source, so it
  reported `milestone.delivered_on` dead (written through a dict of state to
  column name) and `invoice.milestone_id` written (an unrelated `UPDATE` had
  `WHERE milestone_id` in its span). A column belongs to a table, and a check
  that forgets which is the hand-kept map in a new costume. Then it read
  `load_labor.py` — the loader for the entire payroll distribution — as
  writing nothing, because a three-line `--` comment sits between its column
  list and its `SELECT`. That is *exactly* the mistake recorded further up
  this file about semicolons hiding in comments.
- **Two more citations with no document behind them.**
  `chart_split_driver.evidence_id` and `in_kind_claim.evidence_id` are the
  `award_term.evidence_id` shape — a citation in text with nothing to check
  it against. Both are recorded in the allowlist rather than fixed blind,
  because what each should point at is a judgment.

## A helper recommends; the controller verifies and seals

Migration `062`. `060` made an act by one person raise work for another
inside one project. This is the same move over the whole outstanding list:
anybody holding any portfolio can say *this one is worth your attention, and
here is what I noticed* — and nothing else happens.

**A recommendation is a `todo` and never a row in the register it points
at.** The obvious build was to let a helper write a `PROPOSED` restatement
for the controller to confirm, and it is the wrong one twice over. `PROPOSED`
already means *YBI has put this to NCDMM and they have not answered*, so a
second meaning in one word leaves an auditor unable to tell a position the
organisation has taken from a colleague's suggestion — and the register would
stop being a record of what YBI has said to a sponsor. So there is no new
table and no new column: `todo` already carries `worklist_kind` +
`worklist_entity_id` to point at the item without copying it, `opened_by` for
who noticed, `assignee_actor` for who is being asked, and `detail` for why.

**The fact the record could not hold is who *noticed*.** `audit_log` has
always said who decided. Nothing said who spotted it, so "why was this
invoice restated and not that one" had a one-name answer. `v_worklist_covered`
carries `opened_by` beside `assignee` now — and deliberately not a derived
`handed_on` boolean, which a first draft added and which was wrong on the
state that matters: a recommendation nobody could be named for is
*unassigned*, and `opened_by <> assignee` reads false when the assignee is
NULL. Three states do not fit in a boolean.

Four rules, each one this system already follows somewhere:

- **One live job per outstanding item** (`one_live_job_per_worklist_item`).
  Two is two people each told to clear it and each assuming the other has —
  `one_live_manager_per_code` in a new place. Partial on `status <> 'DONE'`,
  because an item that comes back is a new job.
- **The item is read inside the turn**, so a recommendation cannot name
  something that has since been cleared.
- **You can only recommend what is on your own list**, and **nobody
  recommends to themselves** — handing yourself a job is *taking* one, which
  reads differently on the record.
- **The reason is required.** A recommendation with no reason is the
  machine's own list with a person's name on it, which is worth less than the
  machine's list: the reader now has to work out whether a human added
  anything.

Two defects came out of building it, both masked by data rather than by luck:

**`/worklist/mine` was gated on reading the cost record.** The router carried
`require_reader` and a router-level dependency cannot be relaxed by a route,
so the endpoint whose own docstring is written about Heidi — *"Heidi should
open the application and see that the buildings have no square footage"* —
would have answered Heidi 403 the day she held `FACILITIES` and nothing else.
It never showed because every portfolio holder in the seeded record also
holds `CONTROLLER` **rank**, and a portfolio is not a rank. `require_own_work`
admits somebody who holds a portfolio *or* reads the record; the handler still
filters to `owner_portfolio = ANY(held)`, so a narrow portfolio reaches its
own area and no ledger.

**The two worklist endpoints read different halves of the list.**
`/worklist` read `v_worklist` and `/worklist/mine` read `v_worklist_owned`,
which unions in `v_worklist_extra` — so four kinds answered `total = 0` on
one endpoint while appearing on the other to the same person at the same
moment, and `/worklist/SPACE_UNATTRIBUTED` reached by URL said there was
nothing open in a class somebody had just been told about. 13.0% and 2.2% in
a smaller place.

The screen offers **Recommend** only to somebody who holds a portfolio — the
auditor reads every one of these rows and holds none, and a button that
answers 403 is the lesson the Requests screen already learned. It asks for
*any* portfolio rather than the item's, because which list an item is on is
the handler's judgment and a second copy of that rule in the screen is one
free to drift from it.

`tests/test_recommend.py` holds all of it, and every source assertion in it
was watched failing against a deliberately broken copy. `drive_projects.py`
walks the act against live rows — recommend, refuse the second, refuse the
one that is not outstanding, refuse handing it to yourself, refuse the
auditor — and checks that `restatement`, `decision` and `rate` all stood
still, because *a recommendation raises work, never a number*.

## The handoff

Migration `060`. `059` gave the system a list a person can write; this is what
makes the list move on its own — **an act by one person that raises work for
another, recorded as one act rather than as two people remembering.**

    the manager approves a span   ->  the controller gets a job to invoice
    the controller sends it back  ->  the manager gets a job to answer
    the controller settles it     ->  the manager gets one to chase the money

Stephanie manages the three America Makes projects and Tom invoices them,
which for 2025 was a helper arrangement rather than two departments.
`scripts/load_projects.py` sets the three up from facts already on the
record — the charge code, the award it works under, the team read off the
2025 payroll distribution — and **is signed in as Tom, not as Stephanie**.
Its first draft ran as her and was refused three times: *nobody puts
themselves on a charge code.* An assignment is a statement by one person
about another, so setting Stephanie as manager is something somebody else
does.

**A todo reaches a person, not a payroll key.** `todo.assignee` was an
`employee_key` and **Tom holds CONTROLLER and is not on the payroll
register** — so the one thing the handoff exists to do could never have
reached him. An employee key says *whose effort this was*, which is right for
a timesheet and a certification; an account says *who is doing the work*,
which is what a list of jobs wants. All forty payroll people have accounts,
so nothing is lost the other way.

**A claim keeps no copy of the work.** It names a project and a span; what
that span contains is read from the registers that already hold it —
`timesheet_entry`, the live decisions over `ledger_line`, `attachment` —
through `v_project_work`. **But an approval has to be of something specific**,
or the record moves underneath it and the approval silently comes to cover
something else. So a claim records `saw_hours`, `saw_amount`, `saw_lines` and
`saw_documents`: **the seal, in exactly the sense `decision_set.seal_hash`
is one**, and `v_project_claim.still_agrees` puts them beside what the record
says now. False there is not a defect — it is the thing a controller needs to
know before invoicing.

**And nothing here creates an invoice.** No route in this system does and the
table is append-only, so a claim is *linked* to one already on file. For 2025
that is exactly right: invoice 10018 exists, and what has been missing is the
thread from it back to the work, the people and the documents underneath.
Settling against another objective's invoice is a 409 — that is how cost ends
up charged to the wrong award.

Two smaller rules worth keeping:

- **The manager is a role on the grant**, not a column of its own.
  `charge_authority.role_on_project` has always been the field for what
  somebody's role on a code is, and a manager has to be able to charge time
  to the project anyway. One live manager per code, in the schema, because an
  amendment supersedes rather than sitting beside — two live managers is two
  people each believing the other is watching it.
- **More than one candidate means no candidate, but a person may name one.**
  Approving hands the job to the sole holder of `CONTROLLER`, or to nobody
  with the reason on the todo when two hold it. `hand_to` exists because the
  manager knows who does the invoicing and the system does not, and a person
  naming a person beats a rule guessing between two.

`scripts/drive_projects.py` walks the whole loop as Stephanie and Tom and
leaves the record as it found it, against a census of four tables. Its first
run reported a fault against working code because it checked `audit_log.actor`
for an **email** and the column holds a **display name** — a value recalled
rather than read, which does not stop being that defect because it is in a
drive.

## A lane is a question; the sealed set is the answer

`lane_decision_override`, `lane_override_line` and `lane_assumption` were
created in the first migrations and **nothing wrote any of them** — no route,
no script, no migration. So every lane's build-up was the baseline's by
construction and `GET /lanes/compare` could only ever return zeroes. Building
the side-by-side screen over that API would have shipped a page that cannot
say anything, which is the `FACILITY_UNPARTITIONED` mistake: it teaches the
reader the comparison is broken, and the next real difference they see they
will dismiss. The Lanes screen had been promising the missing capability the
whole time — *"Reclassify Portfolio consulting and see what happens."*

**A BASELINE lane takes no overrides.** The baseline is the classifications
that will be submitted; changing those goes through the queue and the seal,
in front of the trigger that refuses a rate whose seal does not match. A lane
override on it would be the one way round the guarantee the whole system is
built on. Everything else about a lane follows from that: an override lives
in `lane_decision_override`, covers specific ledger lines, and
`v_lane_buildup` reads `COALESCE(override.pool, decision.pool)` — the sealed
decision is never edited, superseded or unsealed by trying something.

**A lane may try a line the queue has not reached** (migration `057`). The
view started `FROM lane JOIN decision`, so a lane could only re-read what had
already been judged — which rules out the most valuable question there is:
*5227 Portfolio consulting, $588,539 across 442 lines, unjudged. What does
the rate look like if that is G&A?* This is not the rule that unclassified
cost is never defaulted into a pool: that rule is about the record, and an
override is the opposite of a default — explicit, with a reason the schema
refuses to let be empty, a grade, a name, in a sandbox, and counted in the
disclosure. `from_unjudged` keeps the two apart on the face of the build-up,
because a lane that pulls cost out of the queue and a lane that moves it
between pools are different claims and only the first changes how much there
is left to judge.

**One line carries one reading per lane**, or it is counted twice in that
lane's own build-up — the supersession defect in a new place. In the schema,
and `lane_id` on `lane_override_line` is kept honest by a **composite foreign
key** rather than a trigger: `(override_id, lane_id)` has to exist in the
parent.

**No rate on the comparison screen, ever.** A lane is not sealed, so it has
no rate; dividing one out on the way past would put a figure in front of a
reviewer with nothing behind it. The only arithmetic is the difference
between two recorded amounts, and the difference is taken in the database.
`compare` returned `float()` on all three columns — the one thing
`domain/core.py::money()` exists to stop.

## A citation names a document

`scripts/load_contract_terms.py` has always opened with the right rule —
*a provision with no citation is somebody's recollection of a contract,
which is worth nothing in a dispute and worse than nothing in a file.* A
citation with **no document behind it** is still somebody's recollection,
and `award_term.evidence_id` was NULL on all thirty-nine rows.

Worse, `evidence.extracted_text` and `page_count` were NULL on all
forty-three documents, so nothing could ask a document whether it contains
what was cited. It is the same shape as `rate.superseded_by`,
`space_partition`, `award_budget_line` and the three `evidence` fact columns
— and the most expensive instance of it, because of what it was hiding:

**Hybrid Phase 2 and Last Tactical Mile each carry three provisions cited to
§25 Invoicing, §26 Payment and Attachment 3. Neither agreement contains any
of them.** Both are ARTICLE-numbered instruments with no numbered clause
heading anywhere, and neither contains the phrase "Net 30" or "fifth business
day". Those are ICAM's clauses; ICAM is the numbered NCDMM Subrecipient
Agreement template and its own ten provisions all check out against it. The
indirect one is the one that moves: Schedule B says Hybrid budgets **no
indirect at all** against $449,043 of labour and LTM budgets **$81,772.76**,
while the register asserts ICAM's "10% of ODCs only" on both — the
restatement's central claim resting, in two places, on a sentence copied from
the one agreement it was true of.

`storage.read_text()` reads a document as it arrives and all four writers of
`evidence` go through it. **Three answers, kept apart:** NULL is nobody has
read it, `''` is read and there is nothing extractable in it, text is read.
Drive AM's agreement is thirty-six pages and seventy characters, and that is
a *fact about the document* — the one that explains why no clause of it has
ever been checked. Collapsing those two would turn "this cannot be checked"
into "this checks out". `scripts/read_documents.py` backfills what was filed
before, the way `retype_documents.py` did for content types.

`v_award_citation_check` (migration `056`) then asks each document whether
the cited clause is in it. **Only `FOUND` is a pass.** `NO TEXT LAYER` and
`NOT READ` are unevaluable the way `NO CLAUSE READ` is on
`v_award_ceiling_check`, and `UNTESTABLE` says the citation is prose a regex
cannot check — "Proposal cover table, Duration" is a perfectly good citation
for a person and a poor one for a pattern. Reporting that as a failure would
teach the reader the list is wrong, and the next real one they see they will
dismiss.

None of it is corrected here. What Hybrid's and LTM's provisions actually
say is `FOR_TOM_TO_VERIFY.md` 6.1, and whether a readable Drive AM agreement
exists is 6.2. The loader carries a note on each contradicted term rather
than dropping it, because the substance may be right and sourced elsewhere,
and that is a different answer from the citation being a copy.

## A drive that writes fiction is worse than no drive

`drive_contracts.py` recorded three provisions onto whichever real award it
picked — upserting on `(award, key)`, so it **replaced** what had been read
out of the executed agreement — opened a milestone named from a random tag
and left it, attached that milestone to **invoice 10018** (a real $37,593.90
invoice YBI issued to NCDMM) with a raw `UPDATE` against a column no route
writes so there was no audit row at all, and booked $12,000 of receipts
against it every run. `drive_reverse`'s third step passed *because of* that
forgery. This is the defect `review_system` was fixed for: a review reading
its own writing.

Three rules came out of it:

- **A drive scaffolds its own award and takes it down**, checked against a
  census of seven tables taken before it started. "Leaves the record as it
  found it" is a claim, and a claim in a drive is something to check.
- **A cleanup that stops at the first refusal is worse than none.** The first
  version met `invoice_no_delete` — `invoice` is append-only — and left its
  award and objective behind. Every statement is attempted now and a failure
  is printed rather than raised.
- **`invoice.milestone_id` has no writer and must not grow one casually.**
  All four America Makes awards are cost reimbursement invoiced monthly
  (ICAM §6 CONTRACT TYPE), and no statement of work carries a CLIN, a
  deliverable value or an acceptance date. The column is for a contract shape
  YBI does not have, so the backward hop from an invoice is the service
  period and the budget categories — not a deliverable. A gap that doing the
  work cannot clear is the `FACILITY_UNPARTITIONED` defect again.

And a related emptiness: **no payment is recorded against any invoice.** The
`receipt` register is empty and `invoice.paid_on` and `paid_amount` are NULL
on all three and read by nothing. `drive_reverse` starts one hop in and names
the missing link rather than exiting 2 and telling the reader to run the
drive that used to invent one.

## When something does not work

The rule: **a person must never be left believing something happened when it
did not.** Four ways that was possible, all found by reading rather than by
anything failing.

**The error handler threw.** `useToast()` returned a bare function; seventeen
call sites across five screens called `toast.show(...)`. Most were inside
`catch` blocks, so a failed write made the error handler fail and the person
was told nothing at all — Barb could have an account creation refused and see
an unchanged screen. The toast surface is callable *and* carries `.show`,
`.ok`, `.warn`, `.fail`, because one of those spellings was always going to be
written by somebody.

**An error looked like a confirmation.** `ToastHost` rendered only
`tone === "bad"` and nine sites passed `tone: "fail"`. Tones are normalised
now, an unrecognised one renders as a *failure* rather than as plain, and a
failure is **sticky** — one that fades in six seconds while somebody is
looking elsewhere is the same as no notification.

**A failed read showed an empty screen.** Thirty-two places load with
`.catch(() => {})`, so "nothing yet" and "the request failed" were
indistinguishable. Fixing thirty-two call sites works until the thirty-third
is written, so the record is taken underneath them in `req()` itself, and
`FailureBell` in the shell surfaces what the screens swallowed. It is absent
entirely when there is nothing to say — a status light that is green all day
is one nobody looks at on the day it turns red.

**A refusal was on no record at all.** `audit_log` means "this changed", so by
construction it says nothing when a change does not happen. `refusal`
(migration `041`) is the other half, written by middleware rather than by each
handler remembering — a route added next year records its refusals without
knowing the file exists. It records faults too: an unhandled exception
propagates out before any status is sent, so the note has to be taken on the
way past and re-raised.

Three rules for it: only mutating methods, because a refused GET is usually
somebody opening a screen they do not hold and would bury the writes that
matter; `anonymous` is honest for a 401 *and* for a body FastAPI rejects
before any dependency runs; and recording a refusal must never turn a refusal
into a crash.

### And the door underneath it had six holes in it

The section above ends on the right rule — *the record is taken underneath
them in `req()` itself, where a caller cannot forget it* — and
`tests/test_failure_contract.py` held it. What nothing held was whether the
screens **go through `req()`**, and six calls did not.

`Imports.jsx` ran the entire import cycle on bare
`fetch(...).then(x => x.json())`, and that is the worst place in the system
for it. A refusal comes back as `{detail: "..."}` with a 4xx, which parses
perfectly: `lines_promoted` is undefined, the `?? 0` fills in, and the screen
said **"0 lines added to the ledger"** in the tone it uses for success. A
refused import of the general ledger, reported as nothing having happened, on
the screen the whole engagement starts at. `Awards.jsx` opened its drawer the
same way and failed in both directions at once — a 403 parsed to an object
and was handed to `.map`, which took the page down, and a network error
rejected a promise nobody awaited, so the row simply did not open and no
trace of it reached anything.

The rule is the one `tests/test_storage_paths.py` already holds for the
volume: **there is one door.** `test_no_screen_reaches_past_the_request_layer`
fails a `fetch(` anywhere in `web/src` outside `api.js`.

And the three multipart helpers — which genuinely cannot use `req()`, because
setting `Content-Type` by hand drops the boundary the browser generates and
the server sees no file — were hand-rolled, checked `res.ok`, and stopped
there. So an upload that failed left nothing on the list `FailureBell` exists
to surface. `sendForm()` is `req()` with different headers and *nothing else
different*: same statuses, same sentence, same record taken underneath.

### A count is honest and a tone is not

The other half of the question. Sweeping the sixty-seven success toasts, most
read a figure back from the response, and **five could report a write that
landed on nothing in the tone used for success** — which is worse than a
wrong number, because nobody re-reads a green toast.

The shape this file already records shipping once: *the handler said
`decisions_created: 1` ... and the controller was told it had worked.* Each
of these is reachable and each is now a sticky `warn` naming what happened:

| | |
| --- | --- |
| the import | a batch already promoted is `ON CONFLICT DO UPDATE`, so it is a no-op — the ledger got nothing |
| a reply accepted | every row unusable writes none, and the request closes: a second acceptance is a 409, so it is the end rather than a step |
| a document attached | attachment is per line and `attached_to` is how many the group key matched; zero means the file is in the library and on nothing |
| the classification queue | `decide()` skipped a group whose key matches no line — *silently*, with `continue`. One stale group judged alone answered **200 with zeroes**, and the screen's detail suffix vanished, leaving "Recorded 5227 → G&A" over nothing |
| the bulk evidence confirm | printed `rows.length`, its own selection, rather than the `attached` the server answered with |

The queue is the one worth keeping. The insert-level version of this defect
was found and fixed before — *`ON CONFLICT DO NOTHING` swallowed the
conflict* — and the **group-level** version was one loop out from it the
whole time. Nothing at all is a refusal now (409 naming the group and saying
to reload), a partial batch names what it skipped in `skipped`, and the
screen says both halves. Two smaller things fell out of reading that loop:
its line lookup was the one of five spellings using bare `payee = %s` where
`advice`, `segment` and the evidence attach all say `coalesce(payee,'')`, and
the bulk attach wrote its audit rows *after* its transaction committed —
`decide()`'s rule pointing the other way, attachments with nobody's name on
them rather than a name on a change that rolled back.

### A name in the request is only ever a label

Eight of the nine mutating routes carrying a `*_by` parameter reassign it
from the session, most with a comment saying why. `POST /api/imports/
{batch_id}/accept` did not — and the screen sent the literal string `tom` in
the query string, which reached `staging_batch.accepted_by` and
`ledger_import.imported_by`, **the permanent provenance record every ledger
line points back to**. Who promoted the general ledger was whatever the URL
said.

`test_mutating_route_takes_its_actor_from_the_session` could not see it:
resolving an `Actor` through a dependency and *using* it are different facts,
and that route did the first. `test_a_name_in_the_request_is_only_ever_a_label`
is the second, over the same parametrised list of routes, and it fails on
exactly the one route that was wrong.

## Supersession, and the one rule it needs

Reclassifying leaves the old `decision_line` in place with `live = false` —
that is how the record stays append-only. So:

> **Every join to `decision_line` by `line_id` says `AND dl.live`.**
> No exceptions, including where an inner join to a live decision already
> makes it redundant.

Without it a line joins once per judgment it has ever carried and every sum
multiplies. This was latent for as long as nothing could supersede, which is
why **three** places had it and none was wrong when written:

| | |
| --- | --- |
| `v_classification_coverage` | `classified` doubled on one reclassification — and the *scope* grew, which is the tell: no judgment changes how much there is to judge |
| the classification queue | a group judged four times printed **four times its amount**, on the screen the engagement is worked from |
| `v_form_990_functional` | a reclassified line landed in its function *and* in `NOT_YET_CLASSIFIED`, so a **tax return** carried the same cost twice — and the extra would have looked like work remaining |

Migrations `042`, `044` and `045` close them; `045` adds the filter to three
more that are safe only because their next join is inner, because a rule with
an exception is one somebody gets wrong the day they change that join.
`tests/test_supersession.py` sweeps both the SQL and the handlers, so a fourth
is caught by a test rather than by somebody noticing a number that looks high.

Two things learned writing those migrations, both worth not repeating: a view
body must be **lifted, not retyped** — one draft rewrote
`v_form_990_functional`'s scope from memory and silently changed how every
line is categorised — and a `CREATE VIEW` extracted by regex runs into the
next one unless you find its terminating semicolon.

## The undo trail cannot jam

Undo walks newest first, which is right: undoing out of order puts a value
back that a later action had already moved on from. But there was no way
*past* an entry that can never be undone, and one sits in the ordinary
lifecycle — seal, compute, unseal, and the `SEAL` entry is offered for ever
while answering "that set is not sealed". Everything older became
unreachable; a drive walked back forty times and moved one thing.

`v_undoable.already_undone` (migration `043`) now covers two cases, not one:
somebody pressed undo on it, **or** its effect is already gone by another
route — a seal whose set has since been unsealed, a classification a later
judgment superseded. The distinction that matters is between *must not be*
undone (something later depends on it — the chain is supposed to stop) and
*need not be* (there is nothing left to walk back).

And **an undo that walked nothing back answers 409**, not 200 with an empty
list. The reasons were in the body the whole time and every caller checks the
status.

## What one change moves

**Reclassifying one expense changes the whole system**, and
`scripts/drive_propagation.py` makes "the whole system" a list rather than a
feeling. Twenty-one observations are taken before and after each of four
changes — classify, reclassify, seal, then be refused by the seal — and every
one is asserted to move or to hold. **A figure that moves when it should not
is as much a defect as one that does not move when it should, and only the
second kind ever gets noticed.**

It found two defects that no screen would have shown.

**A reclassification answered 200 and did nothing.**
`one_live_decision_per_unit` stops a line carrying two live decisions, and the
line insert swallowed the conflict with `ON CONFLICT DO NOTHING`. So a second
judgment on a decided group produced a live decision with *no lines*: the
handler said `decisions_created: 1`, the pools still read the old pool, two
live decisions disagreed with each other, and the controller was told it had
worked. Reclassifying supersedes now — the prior judgment is reversed, which a
trigger uses to free its lines — and **the handler checks that its lines
landed** rather than assuming. The response carries `superseded` so a screen
can say the change replaced something.

**Coverage then counted every reclassified line twice.** Superseding leaves
the old `decision_line` in place with `live = false`, and
`v_classification_coverage` joined on `line_id` alone. One reclassification
took `classified` to exactly double and the *scope* grew — which is the tell,
because no judgment anybody makes can change how much there is to judge.
Migration `042` joins `AND dl.live`, which every other view joining from the
ledger side already had. It was latent for as long as nothing superseded.

The drive runs **before every drive that seals**, because its third step is to
seal and its fourth is to prove a sealed set refuses a reclassification. Run
after one, it can do neither and reports the guarantee as a fault.

## Asking for what is missing

Three things are missing from the record and none can be inferred: which
assets federal money paid for, who uses which square foot, and the email
address of thirty-seven people who have to sign their own effort. All three
live in somebody else's filing cabinet and each has a lead time in weeks.

`/requests` is the mechanism. A form definition becomes a workbook, somebody
fills it in offline in the tool they already use, it comes back, the preview
says exactly what it will do, and only then is it written.

    POST /requests/{form}/issue    a workbook to send, and a row saying we asked
    POST /requests/{id}/reply      the filled one comes back
    GET  /requests/{id}/preview    what it says, and what is wrong with it
    POST /requests/{id}/accept     write it

`/requests` in the SPA is that cycle in the order somebody holds it in their
head: what we asked for, what has come back, what it says, and only then what
it will do. It is gated `reader`, which is what the router asks for — and the
**Accept** button is offered only to whoever holds the portfolio that owns
the data, so a person who may read the page and not write it sees all of it
and is told whose judgment the last step is, rather than meeting a 403 they
could not have predicted.

**The form is defined once and both directions read it.**
`domain/request_forms.py` holds the columns; `request_workbook.py` writes and
`request_intake.py` reads, through the same definition. A workbook cannot ask
for a column the parser will not accept — the shape that produced two coverage
figures six-fold apart and a nav stricter than the API.

**Ask only for what only they know.** `2026_YBI_Fixed-Asset-Schedule.xls` and
`2025_YBI_Lease-Schedule.xlsx` had been on file since the foundation was
loaded and **nothing had ever read them**. The first is a complete
asset-level register — 263 assets with description, in-service date, life,
cost and depreciation. The second is 26 tenancies with the building and the
rent. So the workbooks go out pre-filled from YBI's own documents and the ask
collapses to the column neither carries: *funding source* on the register
(2 CFR 200.313(d)(1) requires it and the register has no such column, which
is a finding on its own) and *square footage* on the space book.

**Every printed subtotal must equal what sits under it** — the QuickBooks
rule, applied to the asset schedule, and it earned its keep twice. The first
parser dropped every asset with no system number, because the report prints
the number only when it changes: $2.5m gone, including $2,388,438.81 of Tech
Block phase 2. And two sheets open with an aggregate the detail below
replaced, which their own totals exclude — attributed the way a reconciling
item is, by finding the **one** combination of rows that explains the
difference and refusing to guess when more than one would.

Three rules in the intake:

- **A blank is unanswered, and unanswered is a value.** The intake form of
  *unclassified cost is never defaulted into a pool*. "There is no federal
  money in this asset" and "nobody has looked" stay different facts all the
  way to `asset_funding`, where the first is a row at 0.00 and the second is
  no row.
- **Columns are found by their heading.** Somebody will insert a column or
  fill in last quarter's copy. Reading by position turns either into silently
  wrong data in every column to the right.
- **Nothing is coerced into validity, and a bad cell costs one cell.**
  "2019ish" is reported as `Assets, row 214, "Placed in service": is not a
  date` and the asset still lands with that field empty. A bad cell in a
  *required* column holds the row back instead — an asset at a guessed cost
  is worse than an asset nobody recorded.

**The door is wide and the judgment is not.** Anybody signed in may send a
reply back, exactly as anybody may send a document in. Accepting takes the
portfolio that owns the data — `INVENTORY`, `FACILITIES`, the administrator
for the roster — because writing somebody's answer into the cost record is
the same judgment as typing it in by hand.

**A reply is evidence.** The workbook is filed through `storage.place()`, so
"where did this funding source come from" answers with the spreadsheet
somebody sent, under their name.

**The roster asks for two things because they come from one filing cabinet**
(v2). An address, so a person can sign their own 200.430(i) certification —
and the terms they worked under, because `v_employment_expected` is *the
denominator every effort percentage is measured against* and it is empty for
all forty-three. Twenty hours a week is the whole of a half-time job and half
of a full-time one, and nothing on the record can tell which. Status, weekly
hours and a start date are each `NOT NULL` on `employment`, so a partial
answer is no row rather than a partial one, and the reply says whose and
why — a blank defaulted to 40 would understate every part-timer by exactly
the amount that matters. A live span is never superseded from a spreadsheet,
for the same reason a confirmed address is not.

**Send the reply to `/intake/` or through the upload route, never to
`docs/source-documents/`.** The eighteen foundational documents are committed;
a roster is forty-three people's names and addresses and `/intake/` is
gitignored for exactly this.

Two defects came out of building it, both found by the drive rather than by
anything failing:

**A spreadsheet renamed the organisation's administrator and locked her out.**
The roster reply matched on `employee_key`, and Barb Ewing's account is keyed
`EWING` because she is on the payroll like everybody else. A row naming
`EWING` rewrote her address and her display name; she could not sign in
afterwards, and the account that provisions every other account had been
taken over by a file from outside the organisation. A reply may now only fill
in an address **nobody has confirmed**, and may never touch `display_name` at
all — a name is what every audit entry is recorded under, and changing it
rewrites how the whole trail reads. This is the rule provisioning already
follows for passwords, for the same reason.

**The facilities carve-out could never have fired.** There were two registers
of one fact: `space_partition` (009) and `space_unit` (020).
`v_facility_occupancy` is the only thing the rate model reads for the 200.465
carve-out, it read `space_partition`, and **nothing in the system has ever
written `space_partition`** — not a route, not a script, not a migration. So
`PUT /api/facilities/space` wrote a row, the screen showed it,
`v_space_unit_control` tied, and the rate carried tenant and vacant space
into the federal pool regardless. Migration `048` points the view at
`space_unit`; `051` takes the two live worklist views off the same table and
drops it — which is how
`FACILITY_UNPARTITIONED` came to fire BLOCKING on a building with 5,400 of
5,400 square feet accounted for. **A BLOCKING item that doing the work
cannot clear is worse than no item**: it teaches the reader that the list is
wrong, and the next one they dismiss will be real.

`SPACE_UNATTRIBUTED` is the survivor of the two and reads
`v_space_unit_control` rather than an existence test, so one suite entered
against a building of three is still outstanding — which is what the
constraint trigger on the dead table was for, and what an existence test
never caught. It keeps the BLOCKING severity: `v_facility_occupancy` inner-
joins to its space totals, so a building that does not add up drops out of
the carve-out entirely and every dollar of its occupancy cost reaches the
federal pool unchallenged.

## Donated time

Hours given rather than paid. They **never enter the paid labour
distribution** — that would move every other share — so they are valued
separately, or not at all.

`donation_rate` (migration `019`) carried every invariant it needed from the
day it was written and **nothing ever wrote it**: the fifth instance of the
dead-table shape after `space_partition`, `rate.superseded_by`, the
`evidence` fact columns and `award_budget_line`. `PUT /api/timesheet/
donation-rate` is the door it was designed for.

**Nobody values their own donated time.** The comment above the table has
always said so — *a volunteer valuing their own time is the whole problem
200.306(e) is guarding against* — and `require_controller` delivers only half
of it, because a controller is on the payroll like everybody else. Tested
against the live record the auditor got 403, the administrator got 403, and
a controller valued her own six donated hours at whatever she liked.
Migration `055` closes it in the schema *and* the handler, which is how the
three rules of this shape are already held: nobody grants themselves a
portfolio, nobody assigns themselves a charge code, a manager cannot sign
somebody's certification.

`v_donation_rate_conflict` says how many controllers other than each
volunteer could value their hours. Zero is not a defect — it is one
controller who is also the volunteer — but it is the kind of thing to find
out about in October rather than in the week the return is due.

## Two people at once

Everything above describes one person acting. Tom and Heidi both hold
`CONTROLLER` and both work the queue, and the system is fast enough that they
will almost never collide — which is exactly what makes the collision worth
guarding. A defect that appears once a month and cannot be reproduced is one
people learn to explain away.

`app/statelock.py` is the whole mechanism. **Every action that changes the
cost record takes `turn(period)` and holds it until its transaction ends.**
`pg_advisory_xact_lock` is the queue: Postgres orders the waiters, there is
no second queue to keep alive, nothing to drain on restart, and it works
across processes — which an in-memory queue would not on a deployment that
runs more than one. It releases at COMMIT or ROLLBACK, so there is no unlock
to forget and nothing left held by a process that died. Uncontended it is a
hash table insert.

The key is `crc32(period)`, not `hash(period)`: Python's hash is salted per
process, so two workers would take different locks for the same period and
serialise nothing at all.

**The seal did not cover what it sealed.** `seal()` ran four statements on
four pooled connections — find the open set, hash every live judgment in it,
count them, write the hash — and `decide()` read *which set is open* on a
fifth, before doing anything. So seven requests all read "set X is open", the
seal froze X against two judgments, and the four still in flight inserted into
X afterwards. The stored hash covered two; the set held six. Nothing would
ever have shown it: the hash is only recomputed when somebody unseals, which
may be months away or never. `scripts/drive_concurrency.py` reproduces it
exactly, and reported it the first time it ran.

Three rules came out of it:

- **Read what you are about to depend on inside the turn.** The open-set
  lookup was correct, on its own connection, and outside the lock — which is
  the same defect in a shape that does not look like one.
- **A sealed set is frozen in the schema too** (migration `046`).
  `decision_respects_the_seal` refuses an insert into a sealed set and refuses
  an update that moves anything the seal hashed, `reversed_at` included —
  because `POST /api/undo` reverses a judgment that way and had nothing
  stopping it doing so under a seal. `v_undoable.blocked_by_seal` is the
  other kind of stop from `already_undone`: there *is* something left to walk
  back, and the way past it is to unseal.
- **A long read before a short write re-checks under the lock.**
  `/api/rates/compute` builds the model from live rows on other connections
  and then re-reads the seal; `/api/restate` re-reads the rate's status.
  Either is a 409 that says what moved, rather than a raw constraint
  violation that says nothing.

**A race that goes all one way leaves a guarantee untested, and the drive has
to say so.** `drive_concurrency` reported 16 checks on one run and 15 on the
next with nothing explaining the difference, and the chase found **two**
silent branches, not one. Where every judgment beat the seal, the branch that
reads *whether a refusal names the seal* had no refusal to read. And where
the seal-against-unseal race ended with the unseal — one of its two
legitimate outcomes — `walk_back` had no seal to release and printed nothing
at all. Both are the register's `NO DATA` state in a drive: not a pass, not a
finding. They print a note now and the summary counts them, because a check
count that moves without saying why is how somebody learns to ignore the run
that actually lost one.

And **two more checks that could not fail**, both in the same file. The
summary called `coverage_is_arithmetic()`, bound the answer to `good, how`
and read neither — `walk_back` checks it properly a few lines up, so this one
was a query run for nothing. And `walk_back`'s own unseal was
`ok(f"unsealed ({r.status_code})")`, which prints a 409 as a pass: an
assertion whose entire content is the thing it is printing. The fourth and
fifth instances of the shape, in the drive whose whole job is to catch what
nobody would notice — which is the argument for going back through a file
once you have found one in it.

**Serialising makes the order deterministic; it does not make it
comprehensible.** Tom judges 5227 at 10:31, Barb's queue was drawn at 10:29,
and her Enter at 10:32 silently replaces a judgment she never saw. So the
queue carries `live_decision` — a decision id, `"none"`, or `"several"` — and
the screen sends it straight back as `based_on`. Where it disagrees with what
is actually live, the judgment is refused and the sentence names who
classified it as what and when, and the queue redraws itself. `based_on` is
optional and absent means *not participating*: a script doing a bulk
reclassification has no screen to be stale, and refusing it would make the
crosswalk unloadable.

One more thing fell out: **`decide()` is one turn for the whole request**, not
one per group. A refusal partway through a batch used to leave the groups
before it recorded while the response said nothing was.

## What the controller still has to settle

`docs/FOR_TOM_TO_VERIFY.md` — eighteen discrepancies the record cannot resolve
on its own, ordered by how much each moves the rate, each one found by a
control rather than by somebody reading. Everything on it is answerable from
what the controller already knows or can reach today; anything needing
counsel, a sponsor or an outside document is listed at the end as explicitly
*not* on it.

The Bacon $45,000 is confirmed and stays on the list as the worked example,
because it shows the shape of the rest: ten of the eleven controls were blind
to it, the eleventh caught it, it moved the fringe rate 22.45% to 21.90%, and
it is closed by *naming* it rather than by adjusting anything. It also carries
the one thing still outstanding — it has not been reposted in QuickBooks, and
when it is, the reconciling item has to come off with it or the correction
counts twice.

Keep the figures in it read from the live record rather than recalled. Three
dates in the first draft were written from memory and were wrong by weeks.

`scripts/verification_sheet.py` turns the same nineteen into the two shapes
somebody settles them in: a workbook with a status dropdown and a box to type
in, and a printable worksheet with a tick box and ruled lines. The narrative
has to be prose and the worksheet has to be structured, so neither can be
derived from the other — which leaves `tests/test_verification_sheet.py`
checking that the references in the two agree, and that the document's opening
count is the count it actually has. Two copies of one list is the shape that
produced 13.0% and 2.2% at the same moment.

The status column is a dropdown and deliberately not a yes/no: *I have checked
and the record is right* and *I have corrected it* lead to different work at
our end, and *somebody else has to answer this* is a real outcome that
otherwise looks like silence.

### The ceiling the register enforces

Hybrid Phase 2 was seeded from the executed agreement at $500,043 with
performance to 10 October 2025. Modification 001 of 22 January 2026 raised it
to **$512,409** and extended performance to 30 June 2026; the modification is
on file as a document and the controller read it into `award_term`. The award
row was never brought into line, so two records of one fact disagreed by
$12,366 and eight months — and the one `POST /api/restate` reads to cap a
claim was the stale one. It would have reported headroom YBI does not have,
against a sponsor, in writing.

None of the eleven cross-reference controls touched it, because a ceiling is
not a derived figure — it is read off a clause. Migration `049` brings the row
into line and adds `v_award_ceiling_check`, which is simply that the register
says what the clause says. `NO CLAUSE READ` is not a pass, for the same reason
`NO DATA` is not: an award whose agreement nobody has been through cannot be
said to tie. **Four awards tie now rather than three.** Digital Engineering
had no award row at all despite SRA-0350 being on file since the first drop,
and its obligation is not in a §4.3 like the other three — §9 Contract Value
and Contract Funding carries it, at $1,000,690, through a different prime
(Grant N00174-20-1-0031 via Energetics Technology Center and NSWC Indian
Head, not the America Makes cooperative agreement). Which prime it flows down
from decides which Single Audit programme its cost lands in, so the citation
has to say which clause in which agreement rather than assume a house
style.

**Figures in a document for somebody else get read from the record, not
recalled.** Three dates in the first draft of the verification list were
written from memory and were wrong by weeks; a status memo stated that only
one of three ceilings was known when all three were on file; and the "top 200
groups carry 94.7%" in `classify.py` was measured against a 4,020-line extract
that predates the full ledger — it is 93.3% of 999 groups, and it had been
quoted into a memo for the board.

### CI runs against an empty database

`.github/workflows/ci.yml` applies the migrations to a bare Postgres and runs
`pytest`. It loads no foundation — deliberately, because the schema is the
thing being tested and a suite that needs a seeded ledger is one nobody can
run on a fresh clone.

So **a test that reads whatever happens to be in the database passes for a
developer and fails in CI**, and `tests/test_reconcile_db.py` did exactly
that: `some_lines()` selected real ledger rows to hang a reconciling item
off, found none, and three tests failed on `assert 0 == 2`. They make their
own rows now, inside the transaction that is rolled back.

Two things worth carrying from it:

- **The failures were not the worst part.** `test_a_plug_is_refused` summed
  nought lines to nought, claimed a dollar, and was refused for having no
  lines at all — which is the *next* test's guarantee. It proved the wrong
  thing and reported success. A test that cannot find its data usually fails
  loudly; the dangerous one is the test whose assertion is still satisfied by
  the empty case.
- **A test whose premise the environment cannot meet states the premise.**
  `test_a_loaded_period_still_evaluates` asserts that the 029 guard does not
  make every control unevaluable. On an empty database nought of eleven are
  evaluable and that is the guard working, so the test skips on an explicit
  check for a loaded ledger and names `scripts/reconcile.py` as what covers
  the other direction.

**CI was red on `main` as well, for many commits.** Nothing merged was
checked by it, which is the same shape as a status light that is green all
day: nobody looks at it until the day it matters. Keep it green.

## Manuals for the team

`docs/manuals/` — one per job, not one per role, because two people here hold
the same rank and do different work. [everybody](docs/manuals/everybody.md),
[the controller](docs/manuals/controller.md),
[the administrator](docs/manuals/administrator.md),
[the auditor](docs/manuals/auditor.md).

The manual *inside* the application is assembled from what the reader holds,
so it never describes a screen they cannot open. These are the longer version,
for reading away from the screen.

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
| `scripts/drive_access.py` | rank, portfolios, the seal, the password gate, the library, the reports |
| `scripts/drive_actors.py` | anonymous, auditor, employee, controller boundaries |
| `scripts/review_system.py` | six dimensions, as all six people, forward and backward |
| `scripts/drive_state_machine.py` | the lifecycle one action at a time, every invariant re-checked each turn, then walked back |
| `scripts/drive_propagation.py` | what one reclassification moves, and what it must not |
| `scripts/drive_requests.py` | the ask, the imperfect answer, and what it writes |
| `scripts/drive_evidence.py` | a folder of documents, what it proposes, and what it refuses to |
| `scripts/drive_concurrency.py` | two controllers acting at the same instant, four races |
| `scripts/drive_buildup.py` | the rate build-up, and everything that moves it |
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
5. ~~**Lane comparison UI.**~~ Done, and the API did *not* exist in any
   useful sense — see **A lane is a question** above. Three tables with
   no writer meant every lane read as the baseline, so the comparison
   could only ever answer with zeroes.
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

- **The timesheet report and invoice regeneration.** Migration `038`. See
  **Two documents on paper** above. Three things came out of building them:
  Excel refuses a timezone-aware datetime outright, so every timestamp is
  converted to UTC and the column says so — a lag computed against a
  local-time column would be wrong by the offset, silently, and lag is what
  separates a record made as the work was done from one made eleven months
  later. `ingest_channel` had no value meaning "this system made it". And a
  drive that searched a PDF's raw bytes for a phrase plainly on its page
  reported a failure against working code, because PDF text is compressed.
- **The document library.** Migration `037`. Every document in the record,
  readable in the page by anybody who may read the record — see **The
  library** above. Two real defects came out of building it, both invisible
  until there was a screen listing every document: no upload route recorded
  the *name* the file arrived under, so the only copy of it was inside the
  stored path and a screen wanting to print it would have had to read a path
  backwards; and both routes kept the content type the client sent, which for
  `seed_documents.py` is `application/octet-stream` for everything, so all
  eighteen foundational documents were filed as anonymous bytes and twelve
  PDFs could not be opened. The type is now read from the bytes.
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
- **Drive AM's cost share contradicts itself.** Schedule B proposes zero and
  §4.3 names none, while Schedule A expects a roughly 1:1 ratio at all times
  with cancellation as a stated remedy. §11.11 gives the Agreement precedence
  over a Schedule, but §4.3 is silent rather than contradictory and silence
  may not be a conflict. If the 1:1 reading binds it is another ~$1.1m.
  Recorded as a term marked UNRESOLVED; needs counsel, not arithmetic.
- **No America Makes award budgets meaningful indirect.** Drive AM has no
  indirect line at all on $583,594 of labour; ICAM budgets 10% of ODCs only.
  That is the recovery the restatement exists to go after.
- `5227 Portfolio consulting`, $588,539 across 442 lines, no objective signal.
  The largest single open judgment in the ledger.
