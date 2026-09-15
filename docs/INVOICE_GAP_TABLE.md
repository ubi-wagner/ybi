# Where the invoicing and the record disagree, and what restating does to each

> **Superseded in its conclusion by `docs/WP_AM_2025_PL_RESTATED.md`.**
> This document was built on the three invoices in the register — one
> month, from `YBI_Invoices_1.pdf`. The 2025 P&L carries **$1,139,101.16**
> of billing on these contracts and says YBI already recovered 100.9% of
> its fully burdened cost, through a 1.77× loaded labour rate rather than
> an indirect line. The arithmetic below stands; the conclusion does not.

Every figure read off the live 2025 record at the sealed rate — **21.90%
fringe, 43.99% combined indirect** (general administration in the G&A pool,
5227 in the base, no facilities carve-out). The "flagged" column is what the
system's own controls report, not a view of what an auditor might say.

---

## 1. The gaps, and what restating does to each

| # | gap | as the record stands | flagged by | what restating does |
| --- | --- | ---: | --- | --- |
| 1 | ~~**Drive AM invoice 10018 is entirely outside the period of performance.**~~ **Withdrawn — it was example data.** 10018 is dated 1 May 2026 for April 2026 service and came from `YBI_Invoices_1.pdf`, a sample of the invoice format loaded before the year's own register existed. Migration `089` removed it; the `TERM` failure went with it, and nothing on the 2025 register bills outside its award's term. | ~~37,593.90~~ **0.00** | `constraint_result` **TERM** now passes on Drive AM, over the 12 invoices YBI actually issued in 2025 | **Nothing to fix.** The row is kept rather than deleted because this was quoted as a finding and a reader who met it has to be able to find out why it went. |
| 2 | **LTM 10039 billed indirect above its own elected method.** A round 3,000.00 on a 15,993.52 base is 18.76%; the elected de minimis supports 1,599.35. | **1,400.65 over** | nothing — the register had no control comparing billed indirect to the elected rate | **Resolves it.** 43.99% supports 7,035.55, so the 3,000.00 stops being an over-claim and becomes 4,035.55 short. |
| 3 | **Nothing in the record supports any invoice's service period.** The ledger is 2025 only; all three invoices bill April 2026. | **57,961.42 billed against 0.00 of recorded cost in period** | nothing — no control compares an invoice to cost in its own service window | **Nothing.** The 2026 ledger has to be imported. Every figure below is 2025 cost, measured against 2026 invoices. |
| 4 | **27,315.63 of billed labour rests on an uncertified reconstruction.** 43 people, **0 certifications, 0 timesheet entries**. | **27,315.63** on these invoices; **300,740.69** of 2025 wages behind the awards | `constraint_result` EVIDENCE passes at `MANAGEMENT_RECONSTRUCTION` — the weakest grade that passes | **Nothing, and it is the precondition.** 200.430(i) goes to the allowability of the *entire* direct labour charge, and the restated invoices claim more of it, not less. |
| 5 | **Cost share obligated and never tracked.** | **LTM 513,065.00** · **Hybrid 104,000.00** | `constraint_result` **COST_SHARE fails** on both, 2 CFR 200.306 — *"tracked 0.00 of 513,065.00 required"* | **Nothing.** Independent of the rate, and 617,065.00 is the largest untracked obligation on the file. |
| 6 | **Every award is set to `DE_MINIMIS_10` while the model applies a negotiated rate.** | all four awards | `constraint_result` **RATE_METHOD fails** ×4, 2 CFR 200.414(f) | **This is what restating is for** — and it is only resolved by the §4.4 modification, not by the arithmetic. |
| 7 | **No payment recorded against any invoice.** `receipt` is empty; `paid_on` and `paid_amount` NULL on all three. | **57,961.42 issued, 0.00 evidenced as received** | nothing — the register has no unpaid-invoice control | **Nothing.** Whether NCDMM paid these decides whether a restatement is an additional claim or a correction to a settled one. |
| 8 | **An indirect line on Drive AM or Hybrid is a category their Schedule B does not contain.** | **17,141.98** of restated indirect (16,537.56 + 604.42) | `v_invoice_budget_check` — **only since migration `074`**; it was blind to this (§3) | **Restating creates this flag.** It is a budget realignment, not just a change of basis. LTM is the easy case: INDIRECT is budgeted at 81,772.76 and the restated 7,035.55 sits inside it. |

---

## 2. The gap that dwarfs the rest

The three monthly invoices are not a small version of the cost — they are a
rounding error against it.

| award | ceiling | budgeted indirect | direct claimed | indirect claimed | 2025 MTDC | indirect at 43.99% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Drive AM | 1,103,594.00 | 0.00 | 37,593.90 | 0.00 | 361,451.88 | 159,002.68 |
| ICAM / Digital Engineering | 1,000,690.00 | 27,500.00 | **0.00** | **0.00** | 207,398.87 | 91,234.76 |
| Last Tactical Mile | 899,500.00 | 81,772.76 | 15,993.52 | 3,000.00 | 330,513.06 | 145,392.70 |
| Hybrid Phase 2 | 512,409.00 | 0.00 | 1,374.00 | 0.00 | 91,788.13 | 40,377.60 |
| **total** | **3,516,193.00** | **109,272.76** | **54,961.42** | **3,000.00** | **991,151.94** | **436,007.74** |

- **1.6% of the ceilings has ever been invoiced.**
- **936,190.52 of 2025 MTDC was incurred on these awards and never invoiced at
  all** — before any indirect is added to it.
- **Digital Engineering has no invoice on the record and its period of
  performance ended 9 July 2025**, so its 207,398.87 of cost and 91,234.76 of
  indirect have nothing to be claimed through.

That is the shape of the finding. It is not that the invoices claim too much
— on every budget line they are comfortably within, and cumulatively nothing
is over. It is that **the invoicing bears almost no relationship to the cost
on the books**, in both directions: outside the term on one award, absent on
another, and an order of magnitude short on all four.

### Cumulative claimed against each budget line

`v_award_claim_check`, migration `074`. Nothing is `OVER` and nothing is
`OUTSIDE SCHEDULE` as issued:

| award | category | budgeted | claimed | headroom | state |
| --- | --- | ---: | ---: | ---: | --- |
| Drive AM | LABOR | 583,594.00 | 18,448.11 | 565,145.89 | WITHIN |
| Drive AM | ODC | 415,000.00 | 19,145.79 | 395,854.21 | WITHIN |
| Drive AM | TRAVEL · MATERIALS · CONSULTANT | 105,000.00 | 0.00 | 105,000.00 | UNBILLED |
| Hybrid II | LABOR | 449,043.00 | 1,374.00 | 447,669.00 | WITHIN |
| Hybrid II | TRAVEL · CONSULTANT · ODC | 51,000.00 | 0.00 | 51,000.00 | UNBILLED |
| LTM | LABOR | 212,326.00 | 7,493.52 | 204,832.48 | WITHIN |
| LTM | CONSULTANT | 605,402.00 | 8,500.00 | 596,902.00 | WITHIN |
| LTM | INDIRECT | 81,772.76 | 3,000.00 | 78,772.76 | WITHIN |
| ICAM | every category | 1,000,690.00 | 0.00 | 1,000,690.00 | UNBILLED |

Restating moves LTM's INDIRECT from 3,000.00 to 7,035.55 — still `WITHIN`,
74,737.21 of headroom left. Drive AM's and Hybrid's restated indirect has no
line to sit in.

---

## 3. The check that could not see it

**A correction to `docs/AMERICA_MAKES_RESTATEMENT.md` §5.** That document said
adding an indirect line to invoice 10018 would read as
`billed_not_budgeted = {INDIRECT}`. It would not have. Migration `040` wrote:

> *INDIRECT and OTHER are exempt from the first test. An indirect line is
> claimed under a rate or a de minimis provision rather than a budget line —
> that is the whole subject of the restatement.*

True of the record it was written against. `052` then transcribed all four
schedules and **two of them budget INDIRECT** — ICAM 27,500.00 and LTM
81,772.76 — while Drive AM's and Hybrid's contain no such category. So an
indirect line is *inside* the schedule on two of these awards and *outside*
it on the other two, and the exemption meant the check could not say which.

Measured rather than argued: a **16,537.56** indirect line inserted on invoice
10018 — the largest single figure the restatement puts anywhere, on the award
with the largest variance — produced an **empty** `billed_not_budgeted`.

**And a second defect in the same view, pointing the other way.** `funded`
read `federal + cost_share > 0`, so a category the schedule *names at zero*
was indistinguishable from one it never names. That is the exception to a rule
this repository states plainly — *a category at zero was named in the schedule
with nothing against it; a category absent was not in the schedule* — and it
is why invoice 10039 reported `{MATERIALS, TRAVEL}`: two categories LTM's
Schedule B **does** name, at zero, with 0.00 billed against them. A flag with
no money behind it, on the one invoice that has a real exposure, while `OTHER`
— genuinely absent from that schedule — went unreported because it was exempt.

Migration `074` keeps three facts apart:

| | |
| --- | --- |
| `billed_outside_the_schedule` | the schedule never names this category. INDIRECT is no longer exempt. |
| `billed_against_a_zero_line` | the schedule names it, at zero, and the invoice carries money against it. Available and unfunded — a different finding from absent. |
| `budgeted_not_billed` | a *funded* category missing from the invoice. Unchanged, and still the weak one. |

A category named at zero and billed at zero is now none of the three, which is
the point: 10018 carries three such lines because Drive AM's Schedule B does.

And `v_award_claim_check` is the comparison nothing in the system made —
**cumulative** claimed against budgeted, by category. Per-invoice was the wrong
unit: a monthly invoice is meant to be a fraction of a budget, so a
per-invoice over-budget test would never fire and would mean nothing if it
did. `NOT READ` is unevaluable rather than a pass.

`tests/test_invoice_budget_check.py` holds all of it, and every assertion was
watched failing against a deliberately broken view — re-exempting INDIRECT
fails two, restoring `funded > 0` fails two others, and making `NOT READ` pass
fails the third.

One thing found by the test rather than by reading: the first draft of
`v_award_claim_check` joined the budget and the claims and filtered on the
award, which dropped **exactly the row that matters** — a category claimed
with no budget line behind it had no award on its side of the join, so
`OUTSIDE SCHEDULE` could never be reported at all. The category universe is a
union of both registers now, because the question is asked of both at once.

---

## 4. The three invoices, side by side

| | direct | indirect billed | *10% would be* | supported at 43.99% | as issued | restated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **10018** Drive AM | 37,593.90 | 0.00 | *3,759.39* | 16,537.56 | 37,593.90 | **54,131.46** |
| **10023** Hybrid II | 1,374.00 | 0.00 | *137.40* | 604.42 | 1,374.00 | **1,978.42** |
| **10039** LTM | 15,993.52 | 3,000.00 | *1,599.35* | 7,035.55 | 18,993.52 | **23,029.07** |
| **total** | **54,961.42** | **3,000.00** | *5,496.14* | **24,177.53** | **57,961.42** | **79,138.95** |

Three invoices, one election, **three different effective rates: 0.00%, 0.00%
and 18.76%**. Two forgo recovery outright; the third is 1,400.65 above what its
own elected method supports.

**Raise the 1,400.65 first.** It is money YBI claimed on a basis the election
does not support, and it is on YBI's side of the ledger. Putting it on the
table unprompted, alongside an ask of 21,177.53, is what makes the ask
credible — and the system is built so the two are never presented as one net
figure.

---

## 5. What has to be true before any of it is a claim

In the order that blocks the others:

1. **Import the 2026 ledger.** Every invoice on file bills April 2026 service
   and the record holds 2025 only. Until that changes, no invoice can be tied
   to the cost underneath it — gap 3, and it silently limits gaps 1, 2 and 8.
2. **Certify the 43.** Zero of 43, and the restated invoices claim *more*
   labour-driven cost, not less.
3. **Settle Drive AM's term.** 54,131.46 restated against an award that ended
   4 January 2026 is the one item on this page that restating makes worse.
4. **§4.4 modifications, with budget realignment**, on all four — a new
   INDIRECT category on two schedules and an increase on the other two.
5. **Square footage and the asset register's funding source**, which decide
   where in the 27.06%–43.01% band the rate actually lands.

Gaps 5 and 7 — the 617,065.00 of untracked cost share and the absent payment
record — are independent of every step above and of the rate.
