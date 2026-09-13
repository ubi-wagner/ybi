# Monday — the run sheet

Everything in the system is staged and waiting. **Nothing below has been done
for anybody**, and that is deliberate: every step here is a judgment with a
person's name on it, and a machine that performed them would destroy the thing
those signatures are worth.

Pre-flight, the night before or first thing:

```bash
DATABASE_URL=... ./scripts/monday.sh          # read-only checks
YBI_SEED_PASSWORD=... ./scripts/monday.sh --full   # and the sandbox test
```

`readiness.py` writes nothing. `monday.sh --full` builds a **throwaway
database** and proves the whole path there, so if the machinery is going to
fail it fails on Sunday rather than in front of the controller. The live
record is read and never written by either.

---

## Order of operations

The order is not a preference. Each step is refused until the one before it is
done, by the schema rather than by anybody remembering.

### 1 · Reconcile the books — Tom

**Gate: `POST /api/rates/compute` returns 409 while any of the eleven control
points is open.** A rate over books that do not agree with themselves is a rate
over the wrong numbers.

```bash
python3 scripts/reconcile.py --base http://… --record
```

Eleven points where the general ledger, the P&L, the balance sheet and the
payroll register have to agree. A difference is closed by **naming** it — a
reconciling item carrying the specific ledger lines it consists of — never by
netting it. `/api/reconcile/propose` will find the lines when exactly one
combination adds up, and proposes nothing at all when more than one would.

*Today all eleven tie. If a QuickBooks reposting has landed since, they may
not, and this is where that shows.*

### 2 · Review the recommendations — the controller team

`/classify`, and `docs/CLASSIFICATION_LOG.md` beside it — a reasoned treatment
for every one of the 757 cost groups, with a citation and a rationale on each,
and a named reason where there is none.

**The log proposes and does not decide.** Run without `--apply` it writes
nothing to the cost record at all. Nothing is pre-accepted; the queue carries
each group's proposal and a person presses Enter on it or does not.

Work the queue in Sweep for the obvious ones and Focus for the ones that need
thought. `j`/`k` move, `Enter` accepts, `1`–`8` jump to a pool, `e` edits.

### 3 · Seal — Tom, and only Tom

**This is the judgment the whole system rests on.** Sealing says *these
classifications are final*, and the hash it writes is what lets a reviewer be
told the rate was not reverse-engineered. Only `CONTROLLER` may do it, and
nothing automated may do it at all.

No rate is computed or displayed before this point. That is the guarantee.

### 4 · Compute the rate — Tom

```
POST /api/rates/compute   { }
```

Defaults are what every rate before migration 068 used. The two settled
decisions are `admin_labour = POOL` (administrative salaries into the G&A pool)
and 5227 consultants in the base as contractor cost under 200.331.

The rate carries the seal hash. A database trigger refuses one whose seal does
not match a sealed set.

### 5 · Check the stack — Tom

`/review/rate`. Every pool at `pool_variance` 0.00, all four `v_rate_anchor`
rows tying. **A control that cannot be evaluated has not passed** — read
`state`, never `variance = 0` alone.

---

## Running in parallel, at their own pace

These do not block steps 1–5 and must not be chased into them.

### The forty-three — their own timesheets

`/timesheet` offers each person the controller's reconstruction of their year,
pre-filled. **It is a convenience they may decline**, and the screen says so
before it says anything else. Three answers are all complete:

- type your own days and ignore the draft — a sheet somebody types is the
  stronger record, not the weaker one;
- adopt it and then correct any day that is wrong;
- leave it. Nothing expires.

**Adopting is not certifying.** Adopting puts hours on a sheet; signing says
the sheet is true, and that happens separately under `/certify`. Nobody can
sign for anybody else — 2 CFR 200.430(i) wants the record of the person whose
effort it was, and a manager cannot sign on their behalf. `v_certification_chase`
is a list to go and ask, never an action.

**Blocked today:** no employment terms are on the record for any of the 43, so
no draft can be built for anyone. That is the roster reply coming back, not a
fault in the system — it is the thing to go and get.

**Submitting does not move the rate.** Adopting the reconstruction faithfully
reproduces its shares, so the figures hold. If it did not, the rate would
depend on who had got round to signing.

### Kelly — the square footage

The single largest open item. No facility on the record carries measured space,
so **no 200.465 carve-out has ever been evaluated** and every dollar of tenant
and vacant occupancy cost sits in the federal pool. The rate reads high, which
is the honest direction to err.

At a realistic tenant share the combined rate is **37.67%** rather than 43.99%.
Nothing should go to NCDMM before this lands.

### Barb — the four decisions

`docs/BARB_ONE_PAGE_AM.pdf`. Whether YBI raises its own two credits first and
unprompted; who opens with NCDMM and when; pushing the 43 certifications; and
whether anybody looks at 2024.

---

## What must not be automated, and why

| | |
| --- | --- |
| **The seal** | It is the assertion that the rate was not reverse-engineered. A script that sealed would put the machine's name on it and the assertion would be worth nothing. |
| **A certification** | 200.430(i) wants the person whose effort it was. A signature nobody gave is the one lie that matters here. |
| **Adopting a draft** | Theirs to accept or decline. A pre-filled sheet that reads as an instruction produces forty-three signatures on somebody else's account of the year. |
| **A reconciling item** | A difference is closed by naming the lines behind it. A tolerance that quietly swallows a residual is how a system starts lying. |
| **Sending anything to NCDMM** | A position YBI takes with a sponsor, in writing. |

---

## If something is wrong

- **A control is OPEN.** Name the difference; do not net it. `ROUNDING` takes
  no lines only if it says in sixty characters or more why it cannot be
  attributed, and never above a thousand dollars.
- **A judgment was wrong after sealing.** Unseal with a written reason. That
  supersedes the rate, and recomputing is step 4 again. The record stays
  append-only: correct by superseding, never by editing.
- **Something was recorded by mistake.** `/api/undo` walks newest first. An
  undo that walked nothing back answers 409 with the reason.
- **A screen reported success and nothing happened.** Check `FailureBell` in
  the shell and the `refusal` register — a refused write is recorded even
  though `audit_log` by construction says nothing when nothing changed.
