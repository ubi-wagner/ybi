# The sweep

Work that can be done while YBI's three workbooks are out. Nothing here waits
on anybody outside the engagement.

Every item states what is wrong, the evidence for it read off the live record,
what changes, and how it is proved. Ordered into waves: the first is things
that are currently telling somebody something untrue, the second is what
stops being cheap once Tom starts classifying, the third is completeness, the
fourth is infrastructure.

Figures read on 11 September 2026.

---

## Wave 1 — screens that mislead

Three small defects. Two of them are visible on screens people read, and one
cannot be cleared by doing the work it demands.

### S1 · A BLOCKING worklist item that doing the work cannot clear

**The evidence.** `FACILITY_UNPARTITIONED` fires BLOCKING on the only building
on file, while `v_space_unit_control` reports 5,400 of 5,400 square feet
accounted for across three units. The test is
`NOT EXISTS (SELECT 1 FROM space_partition …)`, and **nothing in the system
has ever written `space_partition`** — migration `048` already moved the
occupancy view onto `space_unit` for exactly this reason and left the worklist
behind. Two live views still read it: `v_worklist` and `v_worklist_extra`.

**The change.** Migration `050`:

- Redefine both views over `space_unit`, **lifted from their current
  definitions rather than retyped** — the rule from `044`, where a view body
  rewritten from memory silently changed how every line of the 990 was
  categorised. Read them out of `pg_views`, change the one table reference,
  put them back.
- `DROP TABLE space_partition`. It has never held a row.
- While there: `v_worklist` carries `FACILITY_UNPARTITIONED` and
  `v_worklist_extra` carries `SPACE_UNATTRIBUTED`, which are the same
  question asked twice. Decide on one and say why in the migration.

**Proved by.** A test that fails any view definition mentioning
`space_partition`, and a database assertion that with space units recorded
against a facility, no space item is raised for it. The existing
`tests/test_worklist_ownership.py` already fails a kind that lands on the
`ELSE`, so a removed kind has to leave the routing consistent.

**Effort.** Half a day. **Depends on** nothing.

### S2 · The Form 990 readiness flag can never turn red

**The evidence.** `v_form_990_readiness.rate_on_file` reads
`EXISTS (SELECT 1 FROM rate WHERE period = p.period AND superseded_by IS NULL)`
— thirty lines below the comment in the same migration explaining that
`superseded_by` is dead and every reader must filter on `status`. Nothing has
ever written the column, so the flag goes true the moment any rate exists and
stays true after an unseal supersedes every one of them.

**The change.** Filter on `status <> 'SUPERSEDED'`, as `v_rate_buildup` was
already corrected to do. Then decide the column's fate: either drop it, or
give it the one job it could have. Dropping is cleaner — two ways to express
supersession is what caused this twice.

**Proved by.** A sweep test over every view definition and handler for a
reference to `rate.superseded_by`, the same shape as
`tests/test_supersession.py`. That is the guard that was missing: the first
instance was fixed without one, so the second survived in the same file.

**Effort.** An hour. **Depends on** nothing.

### S3 · The in-app manual shows screenshots nothing regenerates

**The evidence.** `scripts/walk_manuals.py` photographs 21 screens as
`m-*.png`. `web/src/pages/Help.jsx` points at a different set of 24 numbered
files that the walk does not touch — including `05a-reconcile.png`, which
shows "Cross-reference points 10" when there are eleven. `tests/test_manual.py`
checks that every referenced screenshot **exists**, which a stale one does.

**The change.** Add the Help chapters' screens to `SHOTS` so they are
re-photographed with everything else, and delete the numbered set. The walk
already refuses a blank photograph after the last fix; extend it to refuse a
screenshot older than the commit that last touched the screen it shows.

**Proved by.** `tests/test_manual.py` gains an assertion that every screenshot
the manual references is one the walk produces — the same derive-don't-keep
rule that fixed the review script's hand-kept endpoint map.

**Effort.** An hour. **Depends on** nothing.

---

## Wave 2 — what stops being cheap once Tom starts

### S4 · Evidence attach and bulk match

**The highest-value item on this list.**

**The evidence.** 21 documents on file; **zero attached to any ledger line**.
A judgment cannot be graded `VERIFIED` without a document attached to the
cost it judges — the deferred trigger refuses the whole set otherwise — so
the ceiling on all ~200 of Tom's decisions today is `CORROBORATED`.

**Why the order matters.** Building this after Tom classifies means reopening
200 judgments to re-grade them, each of which supersedes and leaves a trail.
Building it first means he grades as he goes.

**The change.**

1. Drop a folder of documents onto `/evidence`. The inbox route already
   accepts them and files them by kind; what is missing is the matching.
2. Propose attachments on three signals, scored and never applied: amount
   equal to a line or a group, date within a window of the transaction, and
   vendor similarity against `payee`. **A proposal is never a decision** —
   the same rule `propose()` follows in the queue.
3. Confirm in bulk, one keystroke per proposal, with the same undo surface.
4. The classification queue shows the attachment count it already counts, so
   a group with a document on it is visibly gradeable.

**Watch for.** Matching on amount alone will pair a $1,200 invoice with the
wrong $1,200 line; the codebase's own rule is to propose nothing when more
than one candidate fits, which is what `/api/reconcile/propose` does and what
the asset-schedule attribution does. Follow it.

**Proved by.** A drive that files a folder, accepts the unambiguous matches,
proves the ambiguous ones were not proposed, and then grades a judgment
`VERIFIED` that could not have been graded so before.

**Effort.** Two to three days. **Depends on** nothing. **Do first.**

### S5 · The `/requests` screen

**The evidence.** The API is complete and proved end to end by
`scripts/drive_requests.py` — 36 checks, 0 findings. There is no page. Issuing
a workbook or chasing a reply is an API call today, so nobody at YBI can see
what is outstanding.

**The change.** One screen: what has been asked, of whom, how many days ago,
what came back. Issue a workbook, upload a reply, read the preview — every
problem cell with its row — and accept. `v_information_request` already
carries the chase list with `days` and `overdue`.

**Gating.** `require_reader` to see it, the portfolio that owns the data to
accept — `tabsFor` admits `CONTROLLER` everywhere, and the nav must not be
stricter than the API.

**Proved by.** The screen reaching its endpoints in `review_system.py`, which
derives what each screen calls from `App.jsx` and `api.js` rather than from a
hand-kept list.

**Effort.** A day. **Depends on** nothing.

### S6 · Transcribe what we already hold

**The evidence.** Digital Engineering has **no award row at all**, though its
executed agreement (`SRA-0350 ICAM Digital Engineering`) has been on file
since the first document drop. No award means no ceiling, and a restatement is
capped against a ceiling — so nothing can be measured for it. And only Drive
AM's budget schedule is transcribed: `v_invoice_budget_check` correctly
reports ICAM, LTM and Hybrid as `evaluable = false`, which is honest and is
not an answer.

**The change.** Read the agreements, extend `load_contract_terms.py` and
`load_award_budgets.py`. Pure transcription from documents in hand, recorded
through the real API as the controller so the trail shows a person reading a
document.

**Proved by.** `v_award_ceiling_check` — added in `049` — reporting TIES for
four awards rather than three, and `v_invoice_budget_check` becoming
evaluable for all of them.

**Effort.** Half a day. **Depends on** nothing. **Unblocks the restatement.**

---

## Wave 3 — completeness

### S7 · Lane comparison

The API exists; `Lanes.jsx` has no side-by-side view. This is how a reviewer
is shown the rate under three defensible readings instead of being asserted
one — directly useful when 31.78% goes to NCDMM, and the sensitivity in
Barb's memo (28.09% to 44.90% on one account) is exactly what it would
display. **A day.**

### S8 · Milestones

Zero on record, so the auditor's tenth backward link is not walkable and
`drive_reverse` names it as a gap every run. The deliverables are in the
agreements we hold. **Half a day**, and it closes the last hole in the
backward chain.

### S9 · What one decision covers

Classifying a group of 45 lines records **one** decision with a scope, not 45.
That is right, and the review's proportion check could not tell it from a bug
from the outside — neither can a reviewer. One sentence on the screen, and
the same sentence in the audit package. **An hour.**

### S10 · Take Tom's verification sheet back in

Nineteen answers currently land in a spreadsheet on his laptop. The
`/requests` machinery already parses a returned workbook, reports bad cells by
row and files the reply as evidence; a `VERIFICATION` form would put his
answers on the record under his name, each against the item it settles.
**Half a day.** **Depends on** S5 for the screen.

---

## Wave 4 — the things underneath

### S11 · CI proves the empty direction only

**The evidence.** CI applies the migrations to a bare database, which is right
— but it means `test_a_loaded_period_still_evaluates` now skips there, and the
loaded direction of the reconciliation register is covered only by
`scripts/reconcile.py` against a seeded foundation. That is a real test run
locally and not in CI.

**The change.** A fixture period that builds itself: enough ledger, P&L,
balance sheet and payroll rows, inside a rolled-back transaction, to make all
eleven controls evaluable and tie. Then CI proves the register end to end on
data it made, and the skip goes away.

**Watch for.** A fixture that encodes a wrong shape is worse than no fixture —
it would make the controls agree with a misunderstanding. Build it from the
control definitions, not from what makes them pass.

**Effort.** A day. **Depends on** nothing, but do it after Wave 1 so it is not
competing with defects.

### S12 · Railway — yours, not mine

"GitHub repo not found", and the default branch. Nothing deploys until it is
fixed, and it sits upstream of every other deployment item.

---

## Suggested order

| | | |
|---|---|---|
| 1 | S2, S1, S3 | half a day — two of them are lying on screens today |
| 2 | **S4** | two to three days — its value decays the moment Tom starts |
| 3 | S6 | half a day — unblocks the restatement |
| 4 | S5, then S10 | a day and a half |
| 5 | S11 | a day |
| 6 | S7, S8, S9 | two days |

S12 whenever you get to it; everything deployable waits behind it.
