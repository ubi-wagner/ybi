# System review — what was found, what was fixed, what needs a decision

A full pass over the system and the seed data as all six people who use it,
across six dimensions, forward and backward. `docs/SYSTEM_REVIEW.md` is the
machine's output; this is what it means.

`scripts/review_system.py` produces the former. It probes 78 GET routes as
six actors (468 calls), checks every nav tab against the endpoint its screen
calls, walks the chain forward and backward, and makes exactly one
classification to measure what a change moves — then walks it back through
the real undo route, so it leaves the record as it found it.

**Final state: 0 faults, 1 gap, 26 notes.** The gap is the work not yet done,
which is not a defect. Six faults were found and fixed; three system-level
matters need your judgment rather than a patch.

---

## The six defects, fixed

### 1. Every unknown `/api/...` path answered 200 with the SPA's HTML

**Severity: high.** The catch-all that serves the React app swallowed every
API path that matched no route and returned `index.html` with a 200.

A typo, a renamed endpoint, or a route dropped in a deploy all looked
**healthy** to anything checking a status code. A caller got `res.ok` true and
HTML where a figure should be, and only found out when a JSON parser threw
somewhere far from the cause. A monitor pointed at an endpoint that no longer
existed would have reported green indefinitely.

Found by the review's own probe choking on a 200 that was not JSON.

*Fixed:* `app/main.py` — anything under `/api` that matches no route raises a
404 that says so, naming the path and noting it may exist under another
method. The SPA and its assets are unaffected.

### 2. Coverage had two answers, six-fold apart

**Severity: high — this is the number the engagement is tracked by.**

At the same moment, over the same single classification:

| | scope | classified | coverage |
| --- | --- | --- | --- |
| Classification screen | 5,096 lines · 17,057,405.96 | 2,219,105.55 | **13.0%** |
| Auditor's report | 15,500 lines · 99,281,655.58 | 1,678,057.27 | **2.2%** |

The handler scoped to the P&L — correctly, with the reason in a comment — and
`v_classification_coverage` counted every ledger line including both sides of
every transfer. The *classified* figure differed too, because one measured a
group by what it moved and the other by its net position.

Worse, the view disagreed with itself: it printed `classified` and
`unclassified` as net sums beside a percentage taken over absolute sums, so
1,678,057.27 against 12,693,242.03 sat next to a figure of 2.2%. A reader
checking the arithmetic on one row could not make it come out.

Both figures still fired the "working figure" and NOT FILEABLE caveats, so no
wrong conclusion was drawn — but the number quoted to a reviewer was wrong and
irreproducible, which is exactly the failure the review screens exist to
prevent.

*Fixed:* migration `039`. One definition, in the schema, scoped to the P&L, in
absolute dollars, with `classified + unclassified = scope_dollars` so the
percentage reproduces from the row. `classify.py` reads it instead of
computing its own. Two tests hold it.

### 3. The twenty-six contract provisions existed in no script

**Severity: high, and invisible from any screen.**

The provisions read out of four signed agreements — §4.3 ceilings, §10.1
terms, Schedule B indirect, §11.11 conflicts, the Drive AM cost-share
contradiction — were recorded through the API by hand and captured nowhere. A
database seeded from nothing carried three contracts and **zero** provisions.

An auditor walking back from an invoice reached the agreement and then
nothing. Everything above the agreement was reproducible; the reading of the
agreement was not.

*Fixed:* `scripts/load_contract_terms.py` records all 26 through the real
endpoint signed in as the controller, so the trail shows a person recording a
reading of a document rather than a migration asserting one. Every provision
names its clause; the loader refuses to record one against an award that does
not exist rather than skipping it quietly.

### 4. Two of three invoices named no award

An invoice can arrive before its award is registered — the schema allows it
deliberately. Drive AM and Last Tactical Mile were loaded before their
agreements were read in, and stayed unlinked afterwards. An auditor could walk
an invoice to its objective and no further, one link short of the agreement
that authorised the money.

*Fixed:* `load_invoices.py` resolves the link from the objective after the
awards are in — but only where **exactly one** award covers that objective.
Two is ambiguous, and guessing which agreement authorised an invoice is the
inference this system refuses elsewhere. An invoice that stays unlinked is
printed as `UNLINKED` rather than passed over.

### 5. The nav was stricter than the API for a controller

`CONTROLLER` reaches everything — CLAUDE.md says so and `auth.py` means it:
every narrow gate is `require_portfolio(X, Portfolio.CONTROLLER)`. `tabsFor`
tested `held.has(needs)` alone, so Tom was offered four screens fewer than he
is entitled to and would have had to know the URLs for Evidence, Space,
Inventory and Contracts.

A nav stricter than the API is the same class of defect as one looser than it:
both mean the screen and the server disagree about who you are. One shows a
tab that answers 403; the other hides work somebody is supposed to do.

*Fixed:* `tabsFor` and the manual's `visible()` both admit `CONTROLLER`
everywhere. A test reads the gates out of `auth.py` and fails if they drift.

### 6. The seed procedure was seven remembered steps

There was no one command. The order matters — nobody can record anything
before there are accounts; the fringe base needs the effort distribution;
provisions need their awards — and it was documented only as a list in a QA
note.

*Fixed:* `scripts/seed.sh`. An empty database to a complete foundation in 23
seconds, re-runnable, printing what each step loaded. It also exposed that
re-running provisioning needs the root password back, which is now handled.

---

## Three that need your judgment

### A. The review instrument found its own errors more often than the system's

Of eleven findings in the first run, **seven were the review's own wrong
assumptions** — it probed `/api/timesheet/2025`, `/api/facilities/assets` and
`/api/documents/inbox`, none of which any screen calls, and reported three
correct 404s and a correct 403 as faults.

The cause was a hand-kept map of "what each screen calls", which is a second
copy of something the source already knows. It derives that map from
`App.jsx`, the page components and `api.js` now, and the false findings went
away.

**Worth knowing generally:** a test that argues against correct code is worse
than no test, because somebody eventually "fixes" the code to satisfy it. Two
existing tests had the same shape and were corrected in passing — `test_manual`
rejected a chapter gated on `"reader"` because its sentinel list was
hardcoded and stale, and a check I wrote for the reports router fired on
`Path / name` because a path join is a division operator.

### B. Forty of forty-three people cannot sign anything

The payroll register carries surnames only. Six people have accounts; the
other thirty-seven have no address that anyone has confirmed, so they have no
account, so they cannot certify — and 2 CFR 200.430(i) wants a statement from
the person who did the work, which nobody can give on their behalf.

This is not fixable in software. Somebody has to collect thirty-seven real
email addresses. Until then the labour evidence stays a reconstruction that
names its sources, which is defensible but is not a certification.

**It is the single largest blocker to a defensible fringe rate**, and it has a
lead time measured in weeks rather than minutes.

### C. What "one decision" means is not obvious from the screens

Classifying a group of 45 ledger lines records **one** decision with a scope,
not 45. That is the right design — but the proportion check could not tell
from the outside whether it was correct or a bug, and neither can a reviewer.

Nothing to fix; worth a sentence on the classification screen saying that a
decision covers a group and the evidence gate reads it per line.

---

## What held

Worth stating, because a review that only lists problems reads as a system in
trouble:

- **Every one of 468 route calls answered.** No 500s, as any of six people.
- **Every audit entry names an account and a session.** No orphans.
- **The chain has no broken links.** No decision without a set, no allocation
  without a rate, no invoice line without an invoice, no attachment without a
  document, and every indexed document present on the volume.
- **9 of 10 backward links walkable by an auditor holding no portfolio** — the
  tenth is milestones, of which there are none yet.
- **A classification moved exactly what it should.** One decision, one audit
  entry, coverage up — and the ledger, the payroll register and all eleven
  control points unmoved. Classifying cost must not change the cost.
- **A rate over an unsealed set was refused with a 409.** The guarantee the
  engagement rests on, tested rather than asserted.
- **The review walked its own change back** through the real undo route.

## Reproducing this

```bash
YBI_SEED_PASSWORD=... BASE=http://127.0.0.1:8000 ./scripts/seed.sh
YBI_SEED_PASSWORD=... python3 scripts/review_system.py --base $BASE
```
