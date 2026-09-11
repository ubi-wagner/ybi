# For the controller

You hold `CONTROLLER`, which reaches everything. You are also the only person
who can seal a decision set, compute a rate, unseal, or restate — the narrow
portfolios reach their own area and never add up to yours.

You keep a timesheet and certify your own effort like everybody else. Read
[the manual for everybody](everybody.md) first; this is what is yours on top
of it.

## The order, and why it cannot be changed

    the books agree  →  you classify  →  you seal  →  a rate exists

Each step is refused until the one before it is done, by the database rather
than by a screen. That is deliberate and it is the answer to the only
question a reviewer really has about a rate.

### 1. The books have to agree with themselves

Schedule A-1, `/reconcile`. Eleven points where the ledger, the profit and
loss, the balance sheet and the payroll register have to say the same thing.

`POST /api/rates/compute` returns 409 while any of them is open. A rate over a
ledger that does not match its own statements is a rate over the wrong
numbers, however carefully the pools were built.

**A difference is closed by naming it, not by netting it.** Ask the system to
find the lines behind a difference: where exactly one set of lines adds up it
shows them, and where more than one would it proposes nothing, because a guess
is not evidence. A reconciling item carries the specific ledger lines it
consists of and a trigger refuses one whose lines do not add to the amount
claimed — which is what separates a reconciling item from a plug.

There is one relaxation. A `ROUNDING` item may carry no lines if it says in
sixty characters or more *why* it cannot be attributed and is under a thousand
dollars. Past that, "rounding" is not a description of anything.

**Read `state`, never `variance = 0`.** A control reads `TIES`, `OPEN` or `NO
DATA`. Both sides of most controls are `COALESCE(..., 0)`, so an empty period
compares zero against zero and looks green — the system reported all eleven
points tying over no books at all until that was fixed. A control that cannot
be evaluated has not passed.

The eleventh point is the payroll register, and it is the one that pays for
itself. The fringe base comes from the effort distribution, not from the
ledger's wage accounts, so a difference between them is **two denominators for
one rate**. Today that difference is 45,053.24 — a donor credit sitting in an
intern wage account. It is named, so the control ties, but it still needs
reclassifying in QuickBooks: it is the whole gap between a fringe rate of
22.45% and one of 21.90%.

### 2. You classify

`/classify`. 999 groups, 17,057,405.96. This is the screen the engagement
turns on.

**No rate is computed or shown anywhere during this phase.** Not a preview,
not an indication, not a running total. If you find yourself wanting one, that
want is precisely what the sequence exists to defeat.

**Four independent judgments per group.** Cost pool, Form 990 function,
federal treatment, and how well supported it is. The last is not optional
politeness — the materiality policy reads it.

**The queue is ordered by money, largest first.** Press `f` for focus mode on
anything needing real thought: one large card, the amount set large, sample
memos for context. `j`/`k` move, `Enter` accepts the proposal, `1`–`8` jump to
a pool, `/` searches. There are around two hundred meaningful decisions and
every second saved compounds.

**Advice is never a decision.** The system will tell you what an account name
suggests, what the 2026 crosswalk maps it to, and what the same account was
treated as elsewhere — each with the rule it rests on. You decide; it records
that you did.

**Nothing is defaulted into a pool.** Anything without a signal stays in the
queue. That makes the rate read high while the work is unfinished, which is
the honest direction to be wrong in.

### 3. You seal

`/rates`. The decision set is hashed across every judgment in it. After this,
changing a classification requires unsealing with a written reason, and that
supersedes the rate that was computed from it.

### 4. Then, and only then, a rate

Two proofs run before anything is written: the pool reconciles to the ledger,
and every allocable dollar lands on exactly one objective. If either fails it
is a 409 rather than a rate.

The rate carries the seal hash. A database trigger refuses one whose seal does
not match a sealed set, so the guarantee holds even when application code is
wrong.

## Restatement

`/api/restate`. Every invoice on an objective measured against the sealed rate,
with the difference recorded in the direction it runs — per invoice, including
the ones where YBI collected too much. Hybrid Phase 2 was billed at more than
twice its actual cost; reporting only the favourable half would be advocacy.

A restatement carries the seal of the rate it used, stays `PROPOSED` until a
sponsor says otherwise in writing, and cannot be accepted without naming the
§4.4 modification that authorised the change of basis.

## Reports

`/reports`, Schedule G. The timesheet report is the labour evidence behind the
fringe base — coverage, the distribution, who has certified, every entry with
what it was reconstructed from, and the eleventh control on the first sheet.

Invoices render onto the face they were issued on. An invoice already issued
renders as a **reproduction from the register** and says so; only a draft or a
restatement renders as something YBI is issuing. Filing one puts it in the
document library with a hash.

## Things that will bite

- **`5227 Portfolio consulting`** — 588,539 across 442 lines with no objective
  signal. The largest single open judgment in the ledger.
- **No award budgets meaningful indirect.** Drive AM budgets none at all on
  583,594 of labour; ICAM budgets 10% of ODCs only. That is the recovery the
  restatement goes after.
- **Drive AM's cost share contradicts itself.** Schedule B proposes zero, §4.3
  names none, Schedule A expects roughly 1:1 with cancellation as a remedy.
  Recorded as a provision marked UNRESOLVED. It needs counsel, not arithmetic.
- **Square footage and the asset register.** Neither exists yet. The
  facilities carve-out cannot be sized without the first, and 200.436(b)
  cannot be answered without the second.
