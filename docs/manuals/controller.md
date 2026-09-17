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
one rate**. Today that difference is 45,053.23 — a donor credit sitting in an
intern wage account. It is named, so the control ties, but it still needs
reclassifying in QuickBooks: it is the whole gap between a fringe rate of
22.45% and one of 21.90%.

### 2. You classify

`/classify`. **757 cost groups, 10,180,642.10** — and every one of them
already carries a position. This is the screen the engagement turns on.

Two things about those figures, because the older numbers are still in
circulation. It is 757 and not 999 because migration `064` took the Income
section out of scope: 242 groups and 6,876,763.86 of it was grant revenue,
which does not go in a cost pool, and a quarter of the queue could not be
actioned at all. And the dollars are cost, not the whole ledger — the general
ledger's 15,500 lines are on `/classify/ledger`, where every line lands in
one of four buckets and the two that are out of scope say why.

**What is on this screen today is review, not judgment.** The 757 positions
were recorded by `scripts/classification_log.py` and carry
`origin = MACHINE_PROPOSAL`; `/classify/review` is where you adopt them, at
your own pace, inside the sealed set. Adopting moves no figure — that is the
guarantee, and it is why the rate never depends on who got round to
reviewing.

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
  restatement goes after — and the invoices themselves are the evidence, since
  a line set that mirrors the budget has no indirect row where the budget has
  none.
- **The zero lines on an invoice are deliberate.** They are the categories the
  contract allows with no cost that period, not errors. If somebody asks for
  them to be tidied away, the answer is that the invoice lists what the award
  funds — and that the same tidying would remove the missing indirect line
  that the restatement rests on.
- **Drive AM's cost share contradicts itself.** Schedule B proposes zero, §4.3
  names none, Schedule A expects roughly 1:1 with cancellation as a remedy.
  Recorded as a provision marked UNRESOLVED. It needs counsel, not arithmetic.
- **Square footage and the asset register.** Both exist now, and they are in
  different states. All 263 assets name where their money came from, so
  200.436(b) is answered. The estate on the record is a **derivation from the
  documents**, not a measurement — Heidi's floor plan is filed as evidence and
  **not accepted**, because accepting it supersedes the rate, and a signature
  on that rate dies with it. That is your act either way; whether a signature
  is currently on it is what the band on `/review` says.
- **Accepting a floor plan adds to the estate; it does not replace it.** The
  derived rows are still there, so the rows a reply supersedes have to come
  off first or the estate is counted twice and the 200.465 carve-out is taken
  over the result. The preview says what it will land on, building by
  building, before you press Accept — **read it**, and read it for the second
  shape too: a building named under a spelling the register does not hold is
  *created beside* the one meant, and its area becomes the sum of the rows
  just written, so it ties by construction and can check nothing.
- **`TENANT` or `PROGRAM` on a tenancy is the largest reading still open** —
  2.72 points of combined rate. It is not about whether they pay rent; a
  client company in residence pays rent too. It is whether YBI is letting the
  space commercially or housing a client company as part of what a programme
  does for them. Heidi answers it off the tenancy agreements and you accept
  it; **America Makes is the middle case** and is the one to settle together
  rather than either of you alone. A tenancy that is charged for and called
  programme space has to name the agreement that says so — that is the
  reading that moves the rate, so it does not rest on nobody's document.
