# Manuals

One per job, not one per role. Two people here hold the same rank and do
different work, and one holds the highest rank and the least authority over
cost — so the split follows what somebody actually does.

| | |
| --- | --- |
| [Everybody](everybody.md) | Signing in, your timesheet, certifying your effort, sending a document in. Read this one first; it is the only one most people need. |
| [The controller](controller.md) | Classifying cost, the seal, the rate, restatement. Tom, Stephanie and Heidi. |
| [The administrator](administrator.md) | Accounts, access, and who let whom in. Barb. |
| [Facilities and inventory](facilities-and-inventory.md) | The two measurements the rate turns on: the square footage of each building and what federal money paid for each asset. Heidi. |
| [The classification team](classification-team.md) | Reviewing the 757 working positions, citing the paper behind each, and the timesheet path. |
| [The auditor](auditor.md) | Reading the record, and what each figure rests on. |

**Six, and this table has been four.** A list of the manuals kept by hand
beside the manuals is the shape the rest of this repository spends its time
removing; `app/foundation.py::GUIDES` is the one the shelf reads, and it is
what `/guidebook` serves.

There is also a manual **inside the application**, on your landing page,
assembled from what you hold — so it never describes a screen you cannot
open. These are the longer version, for reading away from the screen.

## A figure in here is a fact about the books, never the state of the work

A manual is not generated, so nothing keeps it honest but somebody reading it
against the record when the record moves — and that is exactly the kind of
thing nobody does. The auditor's manual carried *999 groups unclassified,
coverage 0.0%, no seal, no rate, no square footage, no funding source* for a
week after every one of those stopped being true, and it is the manual read
by the person with no other source.

So the line is:

- **A fact about the 2025 books may be stated.** 757 cost groups, 15,500
  ledger lines, 43 people on the payroll register, $45,053.23 in an intern
  wage account. The year is closed and the seed is final; these do not move.
- **The state of the work may not.** Coverage, how many have certified, which
  rate stands, whether a register has been answered. Those have a screen that
  reads them from the record — the walk at `/`, the tie register at
  `/review`, the readiness report — and a manual points at it instead.

The test is whether doing the work would make the sentence false. If it
would, it belongs on a screen.

## The one idea worth knowing before any of it

**Classifications are sealed before any rate is computed.**

A reviewer will ask whether the rate was honest or reverse-engineered, and
the answer has to be documentary rather than a promise. So the controller
classifies with no rate visible anywhere; the decision set is then sealed,
hashed across every judgment in it; and only then can a rate be computed,
carrying that seal. A database trigger refuses a rate whose seal does not
match a sealed set.

Changing a classification afterwards means unsealing with a written reason,
and that supersedes the rate. Nothing about this is a formality — it is the
whole of why the number is worth anything.
