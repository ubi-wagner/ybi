# For the auditor

You can read everything and change nothing. That is not a limitation of the
account; it is the point of it.

## What you can get to, and how

**Everything is a file.** A system that only answers questions on screen makes
you work at somebody else's desk on their schedule.

| | |
| --- | --- |
| `/review` | The auditor's report, the indirect rate build-up, and Form 990 Part IX — each its own URL, each downloadable as a workbook. |
| `/reports` | Schedule G, the timesheet and effort report. And any invoice, rendered off the register. |
| `/library` | Every document anybody has sent in, readable in the page. |
| `/reconcile` | The eleven cross-reference points, and what each rests on. |
| `/export/audit-package` | The whole record as one workbook with live formulas. |

Every document you open and every copy you take is recorded against your
name — which is what makes it safe for the library to show you the whole
shelf rather than only what somebody selected for you.

## What the screens will not do

**Nothing on a review screen is computed.** Every figure is read from the row
it was recorded in. A figure derived twice can disagree with itself, and the
workpaper would carry the version nobody can reproduce.

That rule was not free. The classification screen and the review screens used
to compute coverage separately and answered 13.0% and 2.2% at the same moment,
over the same single decision. There is one definition now, in the schema, and
both read it.

**Each deliverable states what is unfinished, above the figures.** The rate
says it is a working figure while classification is open; the return says NOT
FILEABLE while any expense is unjudged; the report says the record is
incomplete. The workbooks repeat it on the first sheet, because a workbook
travels and the caveat has to travel with it.

**`NOT_YET_CLASSIFIED` is a column of the 990, not a rounding.** Cost nobody
has judged is never spread across the three functions the return prints. The
totals are short by that amount on purpose until the queue is empty.

## Walking a figure back

From an invoice you can reach the objective it was billed against, the award
behind it, every provision of that award with the clause it came from, the
milestones, the money received, and the people who charged time to it — then
each person's effort distribution and the certification behind it.

The document behind any figure opens from the library. The database is the
index; where a document sits on disk is a convenience for browsing and
enforces nothing.

## What is deliberately incomplete

**Read it off the record, not off this page.** This section used to list the
state of the work — *999 groups unclassified, coverage 0.0%, no seal, no
rate, no square footage, no funding source* — and every one of those had
stopped being true by the time anybody read it. A manual is not generated, so
a snapshot in it is a figure that can only go stale, and the one it misleads
is the reader who has no other source. Two screens answer it live, and both
are built for exactly this question:

- **`/` — the walk.** Eleven steps in the order the year is closed, each
  reading the view that owns its figure, each `DONE`, `OPEN`, `NO DATA` or
  `WAITING`. `NO DATA` is the one to look at: it means the step *cannot be
  evaluated*, which is never a pass. Nothing on it is computed.
- **`/review` — the tie register.** One row per report and anchor, twenty-one
  of them, each reading the control that already owns its figure. A
  difference is named to the cent rather than netted, and an anchor with
  nothing behind it reads `NO DATA` rather than green.

`GET /api/review/ties` and `GET /api/dashboard/walk` are the same two as
JSON, and `docs/REPORT_TIES_2025.md` is the register as a document for
reading away from a screen.

What belongs here instead is what does **not** change when somebody does the
work — facts about the year and about the agreements, not about the queue:

- **45,053.23** between the payroll register and the ledger's wage accounts.
  A donor credit sat in an intern wage account for a year; it is named down
  to zero unexplained, and whether it has been reposted in QuickBooks is on
  the eleventh control rather than on this page. It is the whole difference
  between a fringe rate of 22.45% and one of 21.90%, and only the eleventh
  control could ever have found it — the other ten do not touch the register.
- **Drive AM's cost share contradicts itself** across §4.3, Schedule A and
  Schedule B. Recorded as a provision marked UNRESOLVED rather than resolved
  by inference. It needs counsel, not arithmetic.
- **No America Makes award budgets meaningful indirect.** Drive AM carries no
  indirect line at all against $583,594 of labour; ICAM budgets 10% of ODCs
  only. That absence is the strongest evidence the restatement has, because
  the document YBI issued is itself the record of what it was never budgeted
  to claim.
- **The effort distribution is a reconstruction**, from calendars and project
  logs, and each row names what it rests on. Whether a given person has since
  signed for theirs is `v_certification_status`, live — a count here would be
  wrong within a week.

## The sequence, which is the thing to test

Classifications are sealed before any rate is computed, and the rate carries
the seal hash. A database trigger refuses a rate whose seal does not match a
sealed set; changing a classification requires unsealing with a written
reason, which supersedes the rate.

So the question "was this rate reverse-engineered" has a documentary answer.
The exceptions schedule (`/export/exceptions`) lists every place the standard
was bent, who bent it and why — it is the first schedule worth asking for.
