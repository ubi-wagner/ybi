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
