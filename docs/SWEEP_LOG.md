# The sweep, as it happened

A running record of what each item turned up, written **as the work is done
and committed as it goes**, because the machine this is built on is
ephemeral and a finding that lives only in a terminal is a finding that did
not happen.

`docs/SWEEP.md` is the plan and says what each item *is*. This says what was
actually found doing it — including the things the plan did not know about,
which have outnumbered the things it did.

Each entry: what was wrong, how it was found, what it cost or would have
cost, and what now stops it recurring. Figures are read off the live record
at the time, never recalled.

---

## Wave 1 — screens that were saying something untrue

### S2 · The Form 990 readiness flag could never turn red

**Found by** reading the migration, not by anything failing.

`v_form_990_readiness.rate_on_file` asked
`EXISTS (SELECT 1 FROM rate WHERE period = p.period AND superseded_by IS NULL)`.
Nothing has ever written `superseded_by`. So the flag went true the moment
any rate existed and stayed true after an unseal superseded every one of
them — on the screen that says whether a tax return may be filed.

The same defect had been found in `v_rate_buildup` and fixed **thirty lines
above**, in the same migration, with a comment explaining why. The fix came
with a test scoped to the view it was found in. That is why the second
instance survived.

**Cost if unfixed.** A green light with no way of going out, on a Form 990.

**Closed by** migration `050`: filter on `status`, and drop the column. The
test is now a sweep over every view in every migration, plus a second one
that asks the database whether the column has come back. It reads the schema
as Postgres does — a later `CREATE OR REPLACE` supersedes — so `033` still
carrying the defect in its original body is not treated as a live reader.
Verified by removing `050` and watching it fail.

---

### S1 · A BLOCKING worklist item that doing the work could not clear

**Found by** the live record: `FACILITY_UNPARTITIONED` firing BLOCKING on
Tech Block 5 while `v_space_unit_control` reported 5,400 of 5,400 square
feet accounted for across three units.

It tested `NOT EXISTS (SELECT 1 FROM space_partition …)`. **Nothing in the
system has ever written that table** — not a route, not a script, not a
migration. Migration `048` had already moved the occupancy carve-out off it
for exactly this reason and left the worklist behind.

**Cost if unfixed.** A BLOCKING item that cannot be cleared by doing what it
asks teaches the reader that the list is wrong. The next one they dismiss
will be real.

**Closed by** migration `051`. `SPACE_UNATTRIBUTED` survives — it guards on a
measured building, so it reads as the second half of a pair with
`SPACE_UNMEASURED` — and reads `v_space_unit_control` rather than an
existence test, so one suite entered against a building of three is still
outstanding. That is what the constraint trigger on the dead table was for
and what `NOT EXISTS` never caught. It keeps BLOCKING: `v_facility_occupancy`
inner-joins to its space totals, so a building that does not add up drops out
of the carve-out entirely and every dollar of its occupancy cost reaches the
federal pool unchallenged.

#### Three more, found by lifting the view to edit it

**Two worklist kinds were routed by neither `CASE`.**
`STALE_CERTIFICATION` and `DONATION_RATE_MISSING` landed on the `ELSE` —
owner CONTROLLER, destination `/`. `tests/test_worklist_ownership.py` is the
test that exists to fail exactly that, and its `KINDS` was **hand-kept, and
missing the same two**.

**Two of that test's other assertions could not fail at all.** The
destination test took a fixed-width window back from `AS goes_to` that
overlapped the owner `CASE`, so it was passing on the owner routing. The
portfolio regex matched `THEN 'X'` followed by a newline, which matches
nothing against a view body lifted from `pg_get_viewdef` — the set was empty
and the test passed over it. Both now derive from the views, with a guard
that fails if the derivation returns too little to be real. Verified by
deliberately removing a routing line.

**Three hand-kept maps of the same kinds**, in `Worklist.jsx`,
`Dashboard.jsx` and `Home.jsx`, each missing different ones, all three
falling back to the raw database name. So the failure mode was never a broken
screen: it was a screen that starts speaking SQL, showing the controller
`DONATION_RATE_MISSING` and no destination. One map now, in
`web/src/worklistKinds.js`.

**And `drive_requests.py` could only ever pass once.** It counted ACCEPTED
rows in the whole register and compared against three — "6 of 7", then "9 of
10", then "12 of 13". It measures the requests its own run issued now.

---

### S3 · The manual showed screenshots nothing regenerated

**Found by** comparing what `walk_manuals.py` produces against what the pages
reference.

`Help.jsx` pointed at 24 numbered files the walk never touched, and
`tests/test_manual.py` read only `Manual.jsx` — so the Help page's images
were covered by nothing at all. `05a-reconcile.png` sat on the chapter that
tells the controller to reconcile before classifying anything, showing
**"Cross-reference points 10"** against eleven, no payroll register row, and
a nav carrying tabs that had since been renamed.

A file-exists test passes for ever on a photograph nothing retakes.

**"Ten cross-reference points" was in four places and wrong in all of them**
— the Help prose, its caption, its "four of the ten are worth knowing by
name", and the in-application manual's caption. The eleventh is the payroll
register: the control that found a $45,000 donor credit in an intern wage
account and moved the fringe rate from 22.45% to 21.90%. The chapter did not
mention it.

**Closed by** the walk taking all 35 shots and writing
`web/public/help/taken.json`, so the test can ask whether a picture is one
anything will ever retake. A shot may carry `steps` — a tab, a key, a panel,
a field filled and never submitted — which is how focus mode, the editor and
a split composed to 100.00% of $1,211,515 are photographed without the walk
writing anything. `test_the_manual_counts_the_controls_the_schema_defines`
reads the count out of the register's own evaluability `CASE`; verified by
putting the old figure back and watching it fail.

Twenty-three orphaned images deleted. Three shots that needed a recorded
state are gone (the prose already describes the outcome); the note one turned
out free, because the record already carries notes.
`role-06-first-password` is the one exception worth a write: no account on
the record is on an issued password, which is the point, so the walk
provisions one as the administrator, photographs it, and stands it down.

---

## Wave 2 — what stops being cheap once Tom starts

### S4 · Evidence matching

**Two things had to be corrected before any matching could be written.**

**`evidence.doc_amount`, `doc_date` and `vendor_name` had never been
written.** Four views read them; nothing filled them; all forty-three
documents carried NULL in each. The third instance of the dead-column shape.
There was nothing to match on.

**"A judgment cannot be graded VERIFIED without a document attached to the
cost" is wrong in a way that matters.** `decision_verified_check` counts
`decision_evidence`, not `attachment`. Attaching says *this paper is about
that money*; citing says *this paper is why I judged it the way I did*. A
bulk confirm raises nobody's grade on its own. Held in
`tests/test_verified_requires_a_citation.py` against a database, including
the case where the document **is** attached to the cost and `VERIFIED` is
still refused.

**And `Evidence.jsx` gated its upload form on `actor.role === "CONTROLLER"`**
— a *rank* — while `/api/evidence/upload` asks for the `OFFICE` portfolio.
The person whose whole job that screen is saw the register and no way to add
to it.

**Closed by** `app/domain/evidence_match.py` (pure, sixteen tests), the three
facts on the upload, `PATCH /api/documents/{id}/facts` on `OFFICE`,
`GET /api/documents/propose`, `POST /api/documents/attach/bulk`, a folder at
a time on `/evidence`, and `scripts/drive_evidence.py`.

The rules: amount is necessary and nothing else is sufficient; more than one
candidate means no candidate; a blank stays NULL.

**A screen note worth keeping.** Thirty-two request-reply workbooks nobody
had read the face of, each repeating the same sentence, buried three real
proposals. "No proposal" covers two situations and printing them as one list
is unreadable.

---

### S5 · The requests screen

**Found by** the plan. The API had been complete and proved end to end since
it was built — `drive_requests` walks the whole cycle. There was no screen,
so issuing a workbook or chasing a reply was an API call and nobody at YBI
could see what was outstanding. For three things with a lead time in weeks,
that is the part that matters.

No defects in the API. The screen is `web/src/pages/Requests.jsx`, gated
`reader` like the router, with Accept offered only to whoever holds the
portfolio that owns the data — so a person who may read it and not write it
sees all of it and is told whose judgment the last step is, rather than
meeting a 403 they could not have predicted.

---

### S6 · The fourth award, and all four budget schedules

**Digital Engineering had no award row at all**, though SRA-0350 has been on
file since the first document drop. No award means no ceiling, and a
restatement is capped against a ceiling.

Its clauses are worded differently from the other three and a citation
written to house style would have been wrong on every one: **§9** Contract
Value and Contract Funding carries the obligation ($1,000,690), **§7** the
period (through 9 July 2025), **§3** an order of precedence that resolves a
conflict by the most reasonable interpretation rather than by rank. And it
flows down from a **different prime** — Grant N00174-20-1-0031 via Energetics
Technology Center and NSWC Indian Head, not the America Makes cooperative
agreement — which decides which Single Audit programme its cost lands in.

**Three of the four schedules were missing, each for a different reason.**
Hybrid Phase 2's Schedule B is an *image* on page 17 of the PDF; Last
Tactical Mile's is plain text on page 44 nobody had been to; Digital
Engineering had no row to hang one on.

**`award_budget_line` — the fourth dead register.** Created in `001`, written
once in `004` with Hybrid's four Schedule B categories, **read by nothing**.
So the award reported `evaluable = false` for the whole engagement while its
numbers sat in the database from the first migration. `052` drops it, and the
figures were read off the page again rather than copied across — a copy of a
copy is not a transcription.

**LTM's Schedule B does not foot to its own printed total.** Federal
categories $899,500.76 against a printed $899,500; cost share $513,065.12
against $513,065. 88 cents of rounding inside the executed agreement,
transcribed as printed. The QuickBooks rule applies to an agreement too.

**Hybrid's schedule is $500,043 against a $512,409 ceiling** and both are
right — the difference is Modification 001. `award_budget_schedule` (`052`)
records what a schedule prints for itself so the two questions are asked
apart: does it foot (may not differ) and does it reach the ceiling (may, and
then has to say why).

**What the four say together**, on the face of the agreements: Drive AM
budgets **no indirect at all** against $583,594 of labour; Hybrid **none**
against $449,043; ICAM **10% of ODCs only** — $27,500 against $275,000, with
$655,190 of labour carrying nothing; and only LTM budgets a real figure,
$81,772.76, whose mirror image is **$233,543.12 of unrecovered indirect**
sitting in YBI's own cost share.

---

### Three defects only a fresh seed could show

Running `./scripts/prove.sh` against a database created empty exposed three
things the working copy had hidden, all in `drive_evidence` rather than in
the system.

**The grading step used pool `DIRECT_PROGRAM`, which is not a value of
`pool_type`.** On a sealed set that step reports "the decision set is sealed"
and never runs — so the 422 was invisible and the drive was passing sixteen
checks without exercising the one it was written for.

**Then the cleanup failed on a foreign key, and the failure was right.** A
judgment that cited a document had been walked back, and the reversal and the
citation both stay on the record. Deleting the document would leave the trail
saying somebody graded a judgment `VERIFIED` against nothing. So a cited
document stays. The same answer `audit_log` gives by refusing a `DELETE`
outright.

**That surviving document then collided with two other drives' blanket
`DELETE FROM evidence WHERE filename LIKE 'drive-%'`.** Both carry the same
guard now.

---

## Wave 3

### S10 · The controller's answers, on the record

**Found by** the plan: nineteen answers landing in a spreadsheet on a laptop.
An auditor asking "who said the Bacon credit was confirmed, and when" had a
file attachment and a memory to go on.

The `/requests` machinery already did all of it — issue a workbook, take the
reply, preview every cell, file the reply as evidence. What was missing was a
form and somewhere for the answers to land. Four things came out of building
it, and two of them were latent defects.

**The choice parser assumed every choice list is identifier-shaped.**
`_cell()` did `_text(raw).upper().replace(" ", "_")` and compared that. True
of `FULL_TIME`, `TENANT`, `OCCUPIED` — false the moment a form offers a
sentence. Every one of the verification statuses came back as *"is not one
of"* a list it was plainly in. The statuses are prose on purpose:
"CONFIRMED — the record is right" and "CORRECTED — I have changed something"
lead to different work at our end, and a dropdown reading CONFIRMED /
CORRECTED does not say so. The parser now matches what the column actually
offers, case- and whitespace-insensitively, returns the declared spelling,
and keeps the identifier reading as a fallback.

**`superseded_by` would have been the fifth dead column.** The first draft of
`053` had one, and it failed in a way that proved it pointless: the successor
could not be inserted while the predecessor was live
(`one_live_answer_per_item` is a partial unique index, checked at insert and
not at COMMIT), and the predecessor could not be marked superseded until the
successor existed to be named. A column that makes its own invariant
unsatisfiable is a column doing no work — and it was doing none anyway,
because `answer_id` is a bigserial and the sequence is `ORDER BY answer_id`
within `(period, ref)`. `rate.superseded_by` was exactly this. It is gone,
and the writer supersedes before it inserts.

**A status that claims a settlement has to carry words**, and the preview is
where that is caught. The `CHECK` refuses a two-character CONFIRMED either
way, but a database refusal on accept rolls back the *whole* batch — one
thin answer would have taken four good ones with it. `Column.substantial_when`
puts the rule in the parser, so the preview names the row and holds back one
cell rather than the file. The rule itself is the `DELIVERED`-with-no-date
rule: a status somebody picked from a dropdown is not a thing that happened.
STILL CHECKING and SOMEBODY ELSE HAS TO ANSWER are exempt — they are honest
reports of not knowing yet, and demanding prose would produce "still
checking" twice.

**And the accept note read the state it was about to change, on the wrong
connection.** It reported "0 of 19 items settled" in the same breath as
writing three settlements, because `query()` runs on a pooled connection and
the transaction had not committed. The rule CLAUDE.md already states for the
seal, in a smaller shape: *read what you are about to depend on inside the
turn.*

**And the drive's own history check could only pass once** — it asserted
that item 1.5 carries exactly two answers, which is true on a fresh database
and false on the second run. Third instance of that shape in this file. It
measures what its own run added now.

**One structural move.** The nineteen items lived in
`scripts/verification_sheet.py`, and the form needed them too. Two copies of
one list is the shape that produced 13.0% and 2.2% at the same moment; a
third would have been worse, because it would have stopped matching the day
somebody added an item. They are in `app/domain/verification_items.py` now
and the workbook, the worksheet and the form all read it.

---

### S11 · CI proved the register in the empty direction only

**Found by** the plan, and then the plan's own warning turned out to be the
interesting part: *a fixture that encodes a wrong shape is worse than no
fixture — build it from the control definitions, not from what makes them
pass.*

Building it that way found a defect in one of the eleven.

**`PL_FOOTING` computed net income as nought for any P&L with no COGS
line.** It read
`sum(Income) − sum(Expense) − sum(COGS) + sum(Other Income)` with each term a
`FILTER`ed aggregate and a **single `COALESCE` around the whole expression**.
A `FILTER` matching no rows is NULL and NULL propagates, so an absent section
erased the entire calculation and the outer COALESCE turned it into 0.00.

YBI's 2025 export carries all four sections — COGS $37,261.00 in two
accounts, Other Income $116,948.46 in two — which is why it never showed. A
small nonprofit P&L with no cost of goods sold is an ordinary thing for a
P&L to be, and 2026 is a new chart.

**The variance is not the dangerous part.** It would read as the whole of net
income, which somebody would notice. The quiet case is a period whose sheet
has no printed "Net income" leaf either — an early import, a partial export —
which compares **0 against 0 and ties**. That is exactly the defect `029` was
written to close, living inside one of the eleven points `029` was checking:
`029` made each control say whether it could be *evaluated*, and PL_FOOTING
passes that the moment a P&L and a sheet both exist. It had no way of knowing
the arithmetic in between had collapsed.

Migration `054` gives each term its own `COALESCE`. The real 2025 books are
unmoved — PL_FOOTING reads 4,329.28 against 4,329.28 before and after, and
all eleven still tie.

**Two shapes the fixture carries on purpose.** `GL_BS_COVERAGE` counts
accounts absent from the sheet *carrying a balance*; with nothing absent the
count is nought either way and the control passes over a case it never saw.
So the fixture has a clearing account that opens at nothing, moves twice and
closes flat — what QuickBooks actually produces. And the eleventh needs both
a distribution and wage accounts, equal, because that is what tying means.

**Breaking each one on purpose is the half that matters.** A fixture that
makes the register go green proves it can say yes. `test_reconciliation_
loaded.py` then disturbs each control in turn and asserts it says no —
including the payroll one, where a $45,000 credit is booked against a wage
account and the other ten are held in step deliberately, so the claim that
*only* the eleventh can see it is the thing being tested rather than an
incidental tidiness.

**And `ledger_line` is append-only**, which the first draft of those tests
discovered by being refused: "correct by superseding, never by editing". They
add correcting entries now, which is both what the schema allows and what the
books actually do.

---

### S9a · Nothing wrote the table its own comment described

**Found by** routing `DONATION_RATE_MISSING` in S1 — a worklist kind pointing
at a screen where there was nothing to do on arrival. Recorded there rather
than left to be discovered by clicking.

`donation_rate` has been in the schema since `019` with **every invariant it
needs**: immutable once set, no delete, one live rate per person per period, a
basis of at least ten characters, a positive rate. Nothing has ever written
it. The fifth instance of the dead-table shape, and the most complete one —
somebody designed this carefully and then never built the door.

**The comment above it says what the rule is, and the gate delivers half of
it.**

> The controller sets it and says what it rests on, because a volunteer
> valuing their own time is the whole problem 200.306(e) is guarding against.

`require_controller` keeps out everybody without the portfolio. It does not
keep out the one person the rule is actually about, because a controller is
on the payroll like everybody else. Tested against the live record: the
auditor 403, the administrator 403, and **Heidi — who holds `CONTROLLER` —
recorded six donated hours and valued them at $500 an hour**. 2 CFR 200.306(e)
wants a rate consistent with what YBI pays for similar work, and that is a
judgment about somebody's time that the person whose time it is cannot make.

Migration `055` is the second half, in the schema *and* the handler, which is
how this codebase already holds the three rules of the same shape: nobody
grants themselves a portfolio, nobody assigns themselves a charge code, a
manager cannot sign somebody's certification. `v_donation_rate_conflict` says
how many controllers other than each volunteer could value their hours — zero
is not a defect, it is one controller who is also the volunteer, and it is
worth knowing in October rather than in the week the return is due.

**Two more, both found by a browser rather than by a test.**

`from __future__ import annotations` turns a missing import in a Pydantic
model into a **runtime** failure. `DonationRateIn` shipped with `Decimal`
unimported: the module parsed, the router mounted, the application started,
and the first request that touched it would have answered 500 with
*"`DonationRateIn` is not fully defined"*. `tests/test_request_models_resolve.py`
builds every request model's validator — 52 of them — and catches the whole
class; verified against the real defect.

And the panel lived inside `Sheet`, which only renders for an account with an
`employee_key`. Tom is a controller with no payroll key, so the screen the
worklist points him at showed him nothing at all. The same defect as a nav
stricter than the API, one component further in.

---

### S9 · What one decision covers

**Found by** the plan, and it is a communication defect rather than a code
one: classifying a group of forty-five lines records **one** decision with a
scope, not forty-five. That is right — a scope is an account and a payee, and
the judgment covers every line in it — and from the outside it is
indistinguishable from a judgment that reached one line.

The system review's proportion check could not tell the difference. Neither
can somebody reading "Recorded" after judging $1.2m across thirteen lines,
nor an auditor reading two hundred decisions against five thousand ledger
lines, which reads as coverage and is not.

`decide()` returns the lines and the money now — **the count read back out of
`decision_line` after the insert**, not `len(with_lines)`, because that
number is already computed to prove the lines landed and using the other one
would make the response an assumption again. The queue says it in the toast,
and the audit package says it in two places: a second figure on the index
beside the decision count, and a sentence at the head of Schedule B saying a
row is a judgment rather than a line.

**One thing broke doing it**, and it is worth the line: `with_lines` selects
`line_id` and nothing else, so summing `l["amount"]` off it was a `KeyError`
and a 500. Caught by exercising the route rather than by a test — the tests
read the source, which is the right shape for "does the response say this"
and no shape at all for "does the handler run". The fix reads `amount` from
the same query the decision is attached from, rather than a separate sum that
could disagree with it.

---

## S13 — a name recalled rather than read

Not on the sweep list. It went on it because the same defect was made **six
times in one week** while working the list, and six instances of one mistake
is a system problem rather than six mistakes.

    ledger_import.loaded_by            the column is imported_by
    audit_log.actor_name               the column is actor, and occurred_at
    award_term.key                     the column is term_key
    decision.period                    the column is scope
    ledger_line.line_id                text assigned by the loader, not serial
    evidence_grade 'RECONSTRUCTED'     the value is MANAGEMENT_RECONSTRUCTION
    pool_type 'DIRECT_PROGRAM'         the value is DIRECT, which must then
                                       carry an objective
    row["amount"]                      off a query that selected line_id

Each one cost a round trip through a running service to discover, and the
last one shipped as a 500 on the route the whole engagement is worked from.
They look like eight different mistakes and they are one: **a name recalled
rather than read.** The source is syntactically perfect in every case. It is
the database that disagrees with it, and the database only says so on the
line of code that runs — which in this codebase means the line a controller
is standing on.

### The database checks the code, not the other way round

`PREPARE` parses a statement, resolves every relation and column in it, and
coerces every inline literal to the column's type, **without executing
anything**. `tests/test_sql_is_real.py` walks `app/`, `scripts/` and
`tests/` for every string handed to `execute`, `query` or `one`, converts
psycopg's `%s` to Postgres's `$1`, and prepares all 632 of them.

Every one of the eight above is caught, verified against deliberately broken
copies rather than assumed:

    column "loaded_by" does not exist
    invalid input value for enum evidence_grade: "RECONSTRUCTED"
    relation "charge_code" does not exist

There is no list in it to fall out of date, which is the point — this
repository has been bitten four times in one review by a hand-kept map of
what the code does. CI applies the migrations to a bare Postgres, so the
authority the code is checked against is the migrations and nothing else.
It passes against that bare database as well as against a seeded one, which
it has to: `PREPARE` reads the schema and never the rows.

Two limits, written down rather than left to be discovered:

- **An interpolated query cannot be reconstructed without guessing**, and a
  test that guesses at correct code is worse than no test. Seventeen sites
  build a `WHERE` clause from fragments. The relation is always in the
  literal half, so those are checked that far and no further — a view
  renamed in a migration while a router still names the old one is exactly
  what this class produces.
- **Reading a key off a row the query did not select is invisible to it.**
  The SQL is valid; the Python is wrong.

### And the half PREPARE cannot see

`app/db.py` returns a `Row` rather than a `dict`. The only difference is
what happens on a key that is not there:

    KeyError: "'amount' is not in this row. The query selected 'line_id'.
               Either the column is named something else — `python
               scripts/schema.py <table>` prints what is actually there — or
               the SELECT list does not reach far enough."

`.get()` is deliberately untouched. Subscripting is a claim that the column
is there; `.get()` is a statement that it might not be, and only the first
is worth checking. This is the rule the toast surface already follows: a
person — a developer is one — must never be left holding a true statement
that tells them nothing.

### And the half for before you write the query

`scripts/schema.py` prints what is actually there, with **enum values
inline on the column that takes them**, because that is the one thing that
cannot be inferred from anything else:

    grade   evidence_grade  NOT NULL = 'UNSUPPORTED'
              UNSUPPORTED | TEST_ASSUMPTION | MANAGEMENT_RECONSTRUCTION |
              CORROBORATED | VERIFIED

It prints the CHECK constraints and the triggers with them, so
`direct_needs_objective` is visible before it is hit rather than after, and
it suggests near matches on a name that is not there — `charge_code` answers
with `cost_objective` and `charge_authority`, which is the answer to the
question actually being asked.

### One thing found writing it

The first draft of the sweep skipped any statement containing a semicolon,
on the theory that `PREPARE` takes one statement. Three statements were
skipped that way and **all three semicolons were inside `--` comments** — so
the detector meant to catch a class of error was itself an instance of it,
guessing at SQL structure instead of letting the parser say. The sweep does
not pre-judge now: it hands everything to Postgres and reports what comes
back. A skip is allowed only for a leading keyword that `PREPARE` genuinely
refuses, and that list is asserted, so a real query can never fall out of
the sweep quietly.

---

## S8 — the milestone that was never there, and what looking for it found

S8 was scoped as *zero milestones on record, so the auditor's tenth backward
link is not walkable; the deliverables are in the agreements we hold*. Both
halves turned out to be wrong, and the second one badly.

### There are three milestones and all three are fiction

    MS-FC0802  Drive deliverable FC0802  $25,000  ACCEPTED  Stephanie Gaffney
    MS-473C37  Drive deliverable 473C37  $25,000  ACCEPTED  Stephanie Gaffney
    MS-2A5076  Drive deliverable 2A5076  $25,000  ACCEPTED  Stephanie Gaffney

`scripts/drive_contracts.py` creates one per run, named from a random tag,
and never walks it back. Three runs, three deliverables on the record that
nobody at YBI ever agreed to deliver.

Worse, it then attaches one to a **real** invoice:

    query("UPDATE invoice SET milestone_id = %s WHERE invoice_id = %s::uuid",
          (ms, inv_id))

Invoice **10018** — an invoice YBI actually issued to NCDMM for $37,593.90 —
is on the record as claiming against "Drive deliverable 2A5076". Raw SQL,
against a column no route in the application writes, so there is **no audit
row for it at all**: an auditor asking who attached that invoice to that
deliverable gets silence. Every other write in every other drive runs inside
`mutating()`, which counts audit rows before and after and checks whose name
is on the new one. This one goes round the side.

And `drive_reverse`'s step 3 — *which milestone did that invoice claim
against?* — **passes because of the forgery**. Remove the fiction and the
check it was written to prove fails. A drive reading its own writing, which
is the defect `review_system` was fixed for: *coverage climbed 0% to 36.8%
across five runs and every figure was a review reading its own writing.*

### The deliverables are not in the agreements, because there are none

All four America Makes awards are **cost reimbursement, invoiced monthly**.
ICAM says so in as many words at §6 CONTRACT TYPE — *"NCDMM is entering into
a Cost Reimbursement No Fee Agreement with the Subrecipient"* — and the three
invoices on file are cost invoices, carrying `direct_claimed`,
`indirect_claimed`, `cost_share` and a service period. Not one is a
deliverable invoice.

The statements of work carry tasks, KPPs and a nine-month work-plan Gantt.
They carry no CLIN, no deliverable value and no acceptance date, because
that is not how these awards pay. So `milestone` models a contract shape YBI
does not have, `invoice.milestone_id` has never been written by anything but
the forgery above, and the "tenth backward link" is not a hole in the data.
**It is a question the wrong way round**: the backward walk from a
cost-reimbursement invoice is to the service period and the budget
categories it claimed against, not to a deliverable.

### And then the thing that matters

Checking whether the milestone schedule was in the agreements meant reading
the agreements, which turned up something else entirely.

`award_term` carries, on three of the four awards:

    Payment terms        "Net 30 from receipt of a correct invoice"   §26 Payment
    Invoicing frequency  "Monthly, by the fifth business day"         §25 Invoicing
    Indirect provision   "10% of ODCs only; no indirect on labor"     Attachment 3

Those are **ICAM's** clauses. ICAM is the NCDMM *Subrecipient Agreement*
template: fifty-two numbered ALL-CAPS clauses, §6 CONTRACT TYPE, §25
INVOICING, §26 PAYMENT, and its recorded terms are long, specific and right.

Hybrid Phase 2 and Last Tactical Mile are a **different instrument
altogether** — ARTICLE-numbered, "ARTICLE 4. BUDGET AND PAYMENT", with no
numbered ALL-CAPS clause anywhere in either document. Searched end to end:

    §25 / §26 clause headings      not present in either
    "Net 30"                       not present in either
    "fifth business day"           not present in either

So the register cites, on two federal subawards, **clauses that are not in
the agreements** — and says "Net 30" where the document does not. Drive AM
carries the same three, and its agreement is thirty-six pages of **image with
no text layer at all**, so nothing in it has been read by anyone working from
the file.

The value is wrong too, and wrong in the direction that matters. The four
budget schedules were transcribed in `052`, and they say: **Hybrid budgets no
indirect at all** against $449,043 of labour, **LTM budgets $81,772.76**, and
**ICAM alone is 10% of ODCs only**. The register asserts ICAM's provision on
all three. That is the restatement's central claim — *no America Makes award
budgets meaningful indirect* — resting in two places on a sentence copied
from the one agreement it was true of.

This is `FOR_TOM_TO_VERIFY.md`'s own rule one level down. That document was
written because three dates had been *recalled* rather than read. Here it is
the **citation** that was recalled, which is worse: a figure read back wrong
is caught by a control, and a clause reference that does not exist is caught
by nobody until a sponsor or an auditor turns to the page.

None of it is mine to correct. What Hybrid's and LTM's payment terms actually
are is a question for somebody holding the executed agreements, and Drive
AM's cannot be answered by anyone until its pages are read off the images.

---

## S8, fixed — and two more registers with nothing real in them

### The drive writes nothing onto a real award

`drive_contracts.py` scaffolds an award, an objective and a charge code of
its own, exercises the same routes and gates against them, and takes the
scaffolding down — checked against a **census** taken before it started
rather than asserted. Seven tables counted before and after; a difference is
a finding.

Three things came out of building that:

- **`invoice` is append-only** (`invoice_no_delete`), so the drive cannot
  raise an invoice of its own to take down afterwards. The receipt therefore
  goes against a real invoice and is measured in three readings — before,
  after, and after removal — which is a check on the arithmetic rather than
  on the call having answered 201.
- **A cleanup that stops at the first refusal is worse than none.** The first
  version did exactly that: it tried to delete its scaffolding invoice, met
  `invoice_no_delete`, and left the award and objective behind. Every
  statement is attempted now and a failure is printed rather than raised.
  The orphan it left had to be removed with the trigger disabled by hand,
  which is precisely the thing the trigger exists to prevent.
- **There is still no route that attaches an invoice to a milestone**, and
  that is not an oversight to fix. `invoice.milestone_id` is for a contract
  shape YBI does not have. The drive asserts what is true — a milestone with
  nothing invoiced against it reads zero, and reads zero rather than NULL —
  rather than arranging what is convenient.

### The backward walk was standing on the forgery

`drive_reverse` opened with *money received → the invoice it settled* and
exited 2 when there was no receipt, telling the reader to run
`drive_contracts.py` first, "which records one". What that recorded was
$12,000 against invoice 10018 that NCDMM never sent.

**No payment is recorded against any invoice.** The receipt register is
empty, and `invoice.paid_on` and `invoice.paid_amount` are NULL on all three
and read by nothing anywhere — the seventh and eighth columns in this schema
that look usable and are filled by nothing. So the drive starts one hop in
now and names the missing link, because a missing first link is the finding
rather than a reason to stop.

Its third hop asked *which milestone did that invoice claim against?* and
reported a gap every run. It is not a gap. All four awards are cost
reimbursement invoiced monthly, and the hop backwards from such an invoice is
to the service period and the budget categories. A gap that doing the work
cannot clear is the `FACILITY_UNPARTITIONED` defect again: it teaches the
reader the list is wrong, and the next real one they see they will dismiss.

And its fourth hop now turns to the page. It counted provisions "with the
clause cited" and could not ask whether the clause was there. Against the
live record it reports that Drive AM's eight provisions cannot be checked at
all, because the agreement they were read out of has no text in it — which
is the honest answer and was invisible before.

### What was left on the record, and what was done with it

Removed: three fictional milestones, three receipts, four drive objectives
and their grants, the milestone link forged onto invoice 10018, and three
provisions the drive had invented on Drive AM that the loader never carried.

**Not removed: the six on Hybrid and LTM.** Those are in
`load_contract_terms.py` itself, so they would come back on the next seed,
and deleting them would be a second unsourced judgment on top of the first.
They are annotated instead — the loader now carries a note on each saying
the agreement on file contains no such clause, what the check reports, and
that the substance may still be right and sourced elsewhere. The record says
what is wrong with itself rather than either asserting a falsehood or
quietly dropping the question.

Worth stating as a hypothesis rather than a fact: the loader was written to
capture provisions that "lived in one developer's database", and this drive
had been writing exactly these three keys into exactly that database for as
long as it has existed.

---

## S8, the part that is not ours to settle

Two items on `FOR_TOM_TO_VERIFY.md`, taking it to twenty-one. Neither is
answerable from the record — which is what the list is for.

**6.1, six provisions citing a clause that is not there.** The question put
to Tom is not "is this wrong" but "what do the agreements actually say, and
if the substance came from somewhere else, which document and which clause".
The substance may well be right and sourced from a flow-down nobody wrote
down; that is a different answer from the citation being a copy, and they
lead to different work.

**6.2, nobody has read the Drive AM agreement.** Thirty-six pages, no text
layer, eight provisions that cannot be checked against it. The ask includes
whether a text-bearing copy exists, because that is the cheap fix and only
somebody at YBI can know.

### Three tests caught the drift, which is the point of having them

Adding two items failed four checks in three files, every one of them
correctly:

- `test_the_worksheet_and_the_document_carry_the_same_items` — the narrative
  had not been written yet. Two copies of one list is the shape that produced
  13.0% and 2.2% at the same moment, and this is the test that stops it.
- `test_the_count_the_document_claims_is_the_count_it_has` — and **its own
  matching was wrong**. It looked up number words in dict order, so "Twenty"
  matched inside "Twenty-one" and a document saying twenty-one read as
  claiming twenty. A test for a document miscounting itself, miscounting the
  document. Longest first now.
- `drive_requests.py` had **"expected nineteen"** and **"expected thirteen"**
  written into it by hand, so a correct workbook failed a drive. Derived from
  the list now. That is the third shape again, in the fifth place it has
  turned up: a hand-kept map of what the code does.

---

## S7 — a lane could not say anything

Scoped as *the API exists; `Lanes.jsx` has no side-by-side view.* The API did
exist. It could not answer.

`lane_decision_override`, `lane_override_line` and `lane_assumption` were
created in the first migrations and **nothing wrote any of them** — no route,
no script, no migration. So every lane's build-up was the baseline's by
construction, and `GET /lanes/compare` could only ever return zeroes.
Building the side-by-side screen first would have shipped a screen that
cannot say anything, which is the `FACILITY_UNPARTITIONED` mistake: it
teaches the reader the comparison is broken, and the next real difference
they see they will dismiss.

That is the ninth, tenth and eleventh instance of the shape. It is not rare
here; assume the next new table has it until something writes to it.

The screen's own copy had been promising the missing capability the whole
time — *"Reclassify Portfolio consulting and see what happens."*

### What was built

Routes that write the three tables, gated `CONTROLLER`, each inside
`turn(period)` and each recording what it did. And one rule the schema did
not have and should: **a BASELINE lane takes no overrides at all.** The
baseline is *the classifications and assumptions that will be submitted*, and
a lane override on it would be a way round the seal — change what will be
submitted without going through the queue, the seal and the trigger that
refuses a rate whose seal does not match. A lane is a question; the sealed
set is the answer.

### Migration 057, and the question a lane could not ask

`v_lane_buildup` started `FROM lane JOIN decision`, so a lane could only
re-read what had **already been judged** — which rules out the single most
valuable question anybody can put to it:

> 5227 Portfolio consulting, $588,539 across 442 lines, no objective signal —
> the largest single open judgment in the ledger. What does the rate look
> like if that is G&A?

The group is unjudged, so it was not in the build-up at all and an override
on it moved nothing. The view reads from both sides now.

This is **not** the rule that unclassified cost is never defaulted into a
pool. That rule is about the record, and it is why the rate reads high while
the queue is open. An override is the opposite of a default: explicit, with a
reason the schema refuses to let be empty, a grade, a name, in a sandbox that
never touches the sealed set, and counted in the disclosure. `from_unjudged`
keeps the two apart on the face of the build-up, because a lane that pulls
$588,539 out of the queue and a lane that moves it between two pools are
different claims and only the first changes how much there is left to judge.

Three things worth keeping:

- **One line carries one reading per lane**, or it is counted twice in that
  lane's own build-up — the supersession defect in a new place. Put in the
  schema rather than the handler, and `lane_id` on `lane_override_line` is
  kept honest by a **composite foreign key** rather than a trigger: the pair
  `(override_id, lane_id)` has to exist in the parent.
- **Money was `float()`** on all three columns of `compare`, which is the one
  thing `domain/core.py::money()` exists to stop. Strings now.
- **Nothing is computed on the comparison screen** beyond the difference
  between two recorded figures, and there is deliberately **no rate**: a lane
  is not sealed, so it has no rate, and inventing one would put a figure on a
  screen with nothing behind it.

And the screen says when lanes read identically, rather than leaving a column
of zeroes to be read as a broken page — which is what it would have shown
every time before any of this.

---

## Proving it from nothing, which is where the last two defects were

Everything above was built against a database that had been alive all day.
`./scripts/seed.sh` from an empty one found two things nothing else could.

**A migration cannot fill a column on rows that do not exist yet.** `056`
linked each award to its executed agreement by matching the filename it was
filed under. Migrations run at startup, before a single document has been
uploaded — so on a fresh deployment it matched nothing,
`award_term.evidence_id` stayed NULL through the entire seed, and every
citation reported `NO DOCUMENT`. Nothing would have been *wrong*: `NO
DOCUMENT` is not a pass. But the check that finds six provisions citing
clauses their agreements do not contain would have been **silent on a fresh
deployment and loud only on mine**, which is the worst possible arrangement.

The ordering is not incidental either. `seed.sh` records the contract
provisions at step five and files the documents at step six, because the
provisions hang off the awards and the awards come from the invoice load. The
terms genuinely are recorded before the paper arrives.

`058` puts the one fact nothing can derive — that `AM-ICAM-DIGENG`'s
agreement is the file with `SRA-0350` in its name — on the award row, and
`scripts/link_agreements.py` does the matching after the documents are filed.
One copy of the knowledge, one place that applies it.

**And then the same defect one level up.** `058`'s own UPDATE set
`agreement_name` on four awards and, on a fresh database, three of them do
not exist when it runs: `AM-HYBRID-P2` comes from a migration and the other
three are created by `scripts/load_invoices.py`. So the first fresh seed
linked exactly one award, and reported *3 provisions citing an absent clause,
28 that cannot be checked* against the 6 and 8 the loaded database showed.
The loader carries the fragment now, next to the rest of each award's facts,
and the migration keeps its UPDATE for databases where the rows already
exist — the same division `049` uses.

Seeded from nothing twice more, it reproduces the loaded figures exactly.

### One more thing, and it was the environment

`prove.sh` ended a clean run with **`ModuleNotFoundError: No module named
'pypdf'`** printed under *The boundaries* — which is where a reader looks for
a broken permission gate. The venv simply predated the dependency. It checks
its interpreter before running two thousand checks now, and says plainly that
this is the environment rather than the system.

The exit code was fine, incidentally: `prove.sh` exits 1 on a failure and the
0 I saw was my own `| tail` swallowing it. Worth recording only because
"a proof that reports failure and exits 0" would have been a real defect and
it was not one — a test that argues against correct code is worse than no
test, and so is a fix.

---

## Reading across from the RFP pipeline

Asked to look up the projects and todos on the RFP pipeline and bring them
over. `ubi-wagner/govwin` is that repository — a govtech proposal platform,
251 migrations, 139 tables — and it is the other half of this engagement: it
wins the work and this system accounts for it.

Its post-award module has fourteen registers. **Two were taken and twelve
were deliberately not**, and the refusals are the design.

The argument for refusing is in their own build log rather than in mine.
`docs/PROJECT_MANAGEMENT_DESIGN.md` opens with a superseded notice:

> *"the shape below — a node tree beside a milestone list, each with its own
> dates, costs and CLIN — was two structures describing one thing. It also
> produced two answers to the same question."*

Migration 228 collapsed the two and 229 dropped the table. That is
`space_partition` beside `space_unit`, and 13.0% and 2.2% at the same moment,
described by somebody who had never seen this codebase. Finding the same
lesson independently in a neighbouring system is the strongest evidence
either of us has that it is a real one.

So `project_assignments` stayed out, because `charge_authority` already holds
who may charge a code *and* the three rules a second table would have to
learn again. `project_clins` stayed out, because all four America Makes
awards are cost reimbursement invoiced monthly and carry no CLIN — a CLIN
register would be `invoice.milestone_id` all over again, a table for a
contract shape YBI does not have. Nine more stayed out for the same kind of
reason, and four (risks, reviews, meetings, comments) for a plainer one:
nothing here would write them, and eleven columns and tables in this schema
have already turned out to be filled by nothing.

### What did come across

**A project is a charge code somebody set up** — keyed on `objective_id`
rather than carrying a reference to one, so there is no second name for the
same thing.

**A todo is the list a person can actually write.** Both of
`project_milestone_tasks`'s rules came with it and both were already the house
style under other names: blocked says what is blocking it
(`reversal_needs_reason`), and done carries when and who (`milestone_check`).

**Setting up is one act.** Four calls in four places became one, inside one
turn, through every rule the separate routes already enforce. A code with
nobody on it has its authority gate off, so the answer says `gate_live` rather
than leaving somebody to work it out.

### And the thing that was actually missing

`v_worklist` has known *what* is outstanding since it was written, and
`v_worklist_owned` added *which portfolio*. **Neither could ever say who is
doing it or by when**, because nothing in the system could write that down.
So the twenty-one items on `FOR_TOM_TO_VERIFY.md`, the certification chase
list, and "obtain a text-bearing copy of the Drive AM agreement" all sat on
lists with no owner and no date.

`v_worklist_covered` joins the machine's list to a person's. Against the live
record: **1,089 outstanding and one taken.** That number is the finding — not
a defect in anything, but the first time the system has been able to state it.

### Two things caught building it

**A test that proves only the refusing direction may be refusing
everything.** A failed statement aborts its transaction, so the repository's
existing pattern is one expected failure per test, at the end — which leaves
the accepting direction untested. A `refused()` helper takes the refusal on a
savepoint, so one test can prove a constraint refuses the bad case *and*
accepts the good one. Verified by dropping five constraints on a scratch
database: exactly the five tests that name them fail.

**The coverage screen was a wall of two hundred rows.** 998 of the 1,089
items are one kind. It groups by kind now — which is the evidence screen's
lesson, where thirty-two request-reply workbooks nobody had read buried three
real proposals.

---

## The four shapes

Every item found something the plan did not know about, and they were the
same few things over and over.

**A column or table that looks usable and is filled by nothing.**
`rate.superseded_by`, `space_partition`, the three `evidence` fact columns,
`award_budget_line`. Four instances in four unrelated parts of the schema,
each read by views that quietly answered the wrong question. Assume there is
a fifth.

**A hand-kept list of what the code does.** The worklist test's kinds, three
copies of the kind map across three screens, the manual's screenshots against
the walk's. In every case the thing the list was missing *was* the defect.

**A test that cannot fail for the thing it names.** Two in
`test_worklist_ownership.py`, one in `test_review.py` scoped to the single
view its bug was found in, one in `test_document_access.py` asserting a
literal fragment of punctuation. Each was verified afterwards against a
deliberately broken copy — a test nobody has watched fail is a test nobody
has tested.

**A name recalled rather than read.** Eight instances in one week — a column,
a table, an enum value, a key off a row that never selected it. The one
shape of the four that is not a defect in the system at all: it is a defect
in how the system was being *worked on*, which is why the answer is a tool
rather than a migration. `tests/test_sql_is_real.py` and
`scripts/schema.py`.
