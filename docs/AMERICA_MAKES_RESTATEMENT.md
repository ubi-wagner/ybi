# Restating the America Makes invoices

> **Superseded in its conclusion by `docs/WP_AM_2025_PL_RESTATED.md`.**
> This document was built on the three invoices in the register — one
> month, from `YBI_Invoices_1.pdf`. The 2025 P&L carries **$1,139,101.16**
> of billing on these contracts and says YBI already recovered 100.9% of
> its fully burdened cost, through a 1.77× loaded labour rate rather than
> an indirect line. The arithmetic below stands; the conclusion does not.

**What was decided, and what falls out of it.** Two of the five open questions in
`docs/RATE_RECOMMENDATION.md` are now settled by instruction:

| | |
| --- | --- |
| **5227 Portfolio consulting stays in the base** | Contractor cost under 2 CFR 200.331, counted in MTDC in full. YBI selects the consultant, scopes the engagement, administers the payment and carries the other half of it — that oversight is what the G&A pool pays for, and moving the cost out of the base because it "passes through" would forgo recovery on the very activity the administration exists for. |
| **General administration goes into the pool, across every programme** | `admin_labour = POOL`. YBI-GA's $264,444.89 of wages and the fringe on them form part of G&A rather than standing as an objective taking an allocation *of* indirect. 2 CFR 200 Appendix IV B puts the director's office, accounting and personnel administration in that pool. |

Sealed at 757 judgments, 100% of the 2025 ledger classified, computed:

| | pool | base | rate |
| --- | ---: | ---: | ---: |
| FRINGE | 401,783.60 | 1,835,047.17 | **21.90%** |
| OVERHEAD | 1,497,879.12 | 4,736,602.11 | 31.62% |
| G&A | 585,875.91 | 4,736,602.11 | 12.37% |
| **INDIRECT_COMBINED** | 2,083,755.03 | 4,736,602.11 | **43.99%** |

Every pool ties at `pool_variance` 0.00, all four `v_rate_anchor` rows tie, all
eleven cross-reference controls tie. The base falls from $5,058,960.43 to
$4,736,602.11 because YBI-GA is no longer an objective in it; the fringe rate
does not move, because administrative staff draw benefits like everybody else
and their wages stay in the fringe denominator.

**This 43.99% carries no 2 CFR 200.465 facilities carve-out**, because no
building is on the record. It is the top of the band, and §4 below prices every
figure here across the whole of it. Every number in this document was produced
by the engine — computed, sealed, and restated through `POST /api/restate`,
with each restatement checked against the rate that had just been computed.

---

## 1. What the three invoices actually say

There are three America Makes invoices in the register. All three are April 2026
service, issued 1 May 2026, Net 30, and all four awards are set to
`DE_MINIMIS_10`.

| invoice | objective | direct billed | indirect billed | total | **effective rate** |
| --- | --- | ---: | ---: | ---: | ---: |
| 10018 | Drive AM | 37,593.90 | 0.00 | 37,593.90 | **0.00%** |
| 10023 | Hybrid II | 1,374.00 | 0.00 | 1,374.00 | **0.00%** |
| 10039 | Last Tactical Mile | 15,993.52 | 3,000.00 | 18,993.52 | **18.76%** |
| | | **54,961.42** | **3,000.00** | **57,961.42** | |

**"The old rate" is three different things on three invoices under one
election.** Two carry no indirect line at all. The third carries a round
$3,000 — not 10% of anything on the page. That is the first finding, and it
sits underneath everything below:

> **Since confirmed, and it is worse than a wrong rate.** The 2025 income
> postings show LTM billed **exactly $3,000.00 of indirect in eleven of the
> twelve months** and $11,400.00 in February. So 18.76% is what a flat monthly
> figure happened to come to on *this* invoice's base; February's identical
> method came to 20.54%. There is no rate — there is a monthly amount that
> moves with nothing. `WP_AM_2025_RESTATED_INVOICES.md` §3.3.

- 10018 and 10023 **forgo recovery outright**. On a cost-reimbursement award
  there is no mechanism that gives it back later.
- 10039 is **$1,400.65 above** what the elected de minimis rate would have
  produced ($1,599.35 on a $15,993.52 base). Under the method YBI actually
  elected, that invoice over-billed.

Those two facts run in opposite directions and are **not netted**. One is money
YBI did not ask for; the other is money it asked for on a basis the election
does not support. They are separate conversations with NCDMM.

The line detail is the other half of the evidence, and it is why the categories
matter in §5: **10018 lists five categories and three of them are 0.00** —
the invoice prints what the contract allows, not what had activity. The absence
of an indirect line is therefore a statement, not an omission.

---

## 2. The three invoices restated at 43.99%

> **These three were examples, and they are off the record.** Migrations
> `088` and `089`. The arithmetic below is right about the three invoices in
> `YBI_Invoices_1.pdf`, and that file was the whole register when this was
> written — but those three are dated 1 May 2026 for April 2026 service and
> were a sample of the *shape* of an America Makes invoice, not YBI's
> billing. `089` removed them and the six restatements measured against
> them.
>
> **The 2025 register is 61 invoices**, from the six PDFs of invoices as
> issued, and those three objectives carry 12, 12 and 9 of them. §8 below
> carries the year, which is the restatement: Drive AM $(58,786.31), LTM
> $107,683.52, Hybrid $(55,250.32). Two of the three run the *other way* from
> the table below, because the indirect was recovered inside a loaded labour
> rate and no 2025 invoice carries an indirect line at all.
>
> The section is kept rather than deleted because three findings elsewhere
> rest on it — the `TERM` failure on Drive AM among them — and a reader who
> meets one of those has to be able to arrive here and see why it went.

Engine-computed, per invoice, recorded as `PROPOSED`:

| invoice | base as billed | indirect billed | indirect supported | **variance** |
| --- | ---: | ---: | ---: | ---: |
| 10018 Drive AM | 37,593.90 | 0.00 | 16,537.56 | **UNDER 16,537.56** |
| 10039 LTM | 15,993.52 | 3,000.00 | 7,035.55 | **UNDER 4,035.55** |
| 10023 Hybrid II | 1,374.00 | 0.00 | 604.42 | **UNDER 604.42** |
| | | **3,000.00** | **24,177.53** | **21,177.53** |

Nothing is over-collected at this rate on any of the three.

| invoice | as issued | restated | increase | |
| --- | ---: | ---: | ---: | ---: |
| 10018 | 37,593.90 | 54,131.46 | +16,537.56 | +44.0% |
| 10023 | 1,374.00 | 1,978.42 | +604.42 | +44.0% |
| 10039 | 18,993.52 | 23,029.07 | +4,035.55 | +21.2% |
| **total** | **57,961.42** | **79,138.95** | **+21,177.53** | **+36.5%** |

10039 rises by less in percentage terms than the other two for one reason: it is
the only invoice that already billed something, so 43.99% is being applied
against a base that has $3,000 credited back against it.

Ceiling headroom is not a constraint on any of them — Drive AM $1,066,000.10,
LTM $880,506.48, Hybrid II $511,035.00, none `capped_by_ceiling`.

---

## 3. The number that matters more

**$57,961.42 of billing sits against $999,842.96 of 2025 cost.** The three
invoices are one month of service each. The restatement above recovers
$21,177.53; the *year* is a different order of magnitude.

2025 cost classified to the America Makes objectives:

| objective | wages | fringe @ 21.90% | direct non-labour | **MTDC** |
| --- | ---: | ---: | ---: | ---: |
| Drive AM | 147,310.09 | 32,260.91 | 181,880.88 | 361,451.88 |
| Last Tactical Mile | 52,607.87 | 11,521.12 | 266,384.07 | 330,513.06 |
| Digital Engineering | 30,700.46 | 6,723.40 | 169,975.01 | 207,398.87 |
| Hybrid II | 62,992.64 | 13,795.39 | 15,000.10 | 91,788.13 |
| AM-Other | 7,129.63 | 1,561.39 | 0.00 | 8,691.02 |
| **total** | **300,740.69** | **65,862.21** | **633,240.06** | **999,842.96** |

Indirect supported on it, by rate:

| | Drive AM | LTM | Dig Eng | Hybrid II | AM-Other | **total** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| as budgeted in Schedule B | 0.00 | 81,772.76 | 27,500.00 | 0.00 | 0.00 | **109,272.76** |
| at the 10% de minimis | 36,145.19 | 33,051.31 | 20,739.89 | 9,178.81 | 869.10 | **99,984.30** |
| at 34.82% *(objective basis)* | 125,857.54 | 115,084.65 | 72,216.29 | 31,960.63 | 3,026.21 | **348,145.32** |
| **at 43.99%** | **159,002.68** | **145,392.70** | **91,234.76** | **40,377.60** | **3,823.18** | **439,830.92** |

**$439,830.92 supported against $99,984.30 the elected method would give and
$109,272.76 the four schedules actually budget — a gap of $339,846.62 on one
year of cost.** Digital Engineering has no invoice on file at all, so its
$91,234.76 is not in the restatement above and is not recoverable through it.

---

## 4. The same analysis across the carve-out band

The 200.465 facilities carve-out is the one input still missing, and the rate is
exactly linear in the tenant share. Each row below was computed and restated
through the engine, not interpolated:

| tenant share | combined rate | the three invoices | full-year indirect | vs de minimis | vs budgeted |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0% *(as the record stands)* | 43.99% | 21,177.53 | 439,830.92 | +339,846.62 | +330,558.16 |
| 10% | 40.83% | 19,440.74 | 408,235.88 | +308,251.58 | +298,963.12 |
| **20%** *(recommended provisional)* | **37.67%** | **17,703.97** | **376,640.84** | **+276,656.54** | **+267,368.08** |
| 30% | 34.51% | 15,967.18 | 345,045.81 | +245,061.51 | +235,773.05 |
| 40% | 31.34% | 14,224.91 | 313,350.78 | +213,366.48 | +204,078.02 |

**The case does not depend on where in this band the answer lands.** At the most
conservative share shown, one year of America Makes cost still supports more
than three times the indirect the elected method would give. What the square
footage changes is the size of the ask, not whether there is one.

The three invoices restated at the recommended 37.67% come to **$17,703.97**
rather than $21,177.53 — and each of the three still moves in the same
direction.

---

## 5. What the schedules budget, and the category problem

`award_budget` carries all four transcribed schedules. Read against the direct
they sit on:

| award | budgeted indirect | on budgeted direct | | |
| --- | ---: | ---: | ---: | --- |
| Drive AM | 0.00 | 1,103,594.00 | 0.00% | no INDIRECT category in the schedule at all |
| Hybrid Phase 2 | 0.00 | 500,043.00 | 0.00% | no INDIRECT category in the schedule at all |
| ICAM / Digital Engineering | 27,500.00 | 973,190.00 | 2.83% | **exactly 10% of the $275,000 ODC line** — $655,190 of labour carries nothing |
| Last Tactical Mile | 81,772.76 | 817,728.00 | **10.00%** | **exactly 10% of its whole direct** |

Two things fall out of that table, and both matter to how a restated invoice is
received:

**The de minimis election is visible in exactly one schedule.** LTM budgets
10.00% of its direct to four decimal places. That is the election, written into
an executed budget — which makes it the clearest evidence of what YBI agreed
to, and the clearest statement of what it gave up.

**Two of the three invoices cannot carry an indirect line without a schedule
change.** Drive AM's and Hybrid's schedules contain no INDIRECT category. Adding
one to 10018 or 10023 bills a category that is **not in the agreement**.

> **Correction.** This paragraph first said `v_invoice_budget_check` would
> report that as `billed_not_budgeted = {INDIRECT}`. It would not have:
> migration `040` exempted INDIRECT from the test outright, so a $16,537.56
> indirect line on invoice 10018 produced an *empty* list — measured, not
> reasoned about. Migration `074` fixes it, and
> `docs/INVOICE_GAP_TABLE.md` §3 has the whole of it.
10039 is the easier case in form — LTM's schedule does have the category — and
the harder one in size: 2025 supports $145,392.70 against a budgeted
$81,772.76, so even LTM needs a realignment of $63,619.94 on that line alone.
ICAM is the same shape at $63,734.76 over its $27,500.

So this is a **change of basis and a budget realignment**, not a corrected
invoice, on every one of them. Which is exactly what §4.4 exists for, and why
the schema will not let a restatement be accepted without naming the
modification.

---

## 6. Is there room under the ceilings

Yes, comfortably, on every award — even fully burdened at the top of the band:

| objective | 2025 MTDC | indirect @ 43.99% | fully burdened | ceiling | of ceiling |
| --- | ---: | ---: | ---: | ---: | ---: |
| Drive AM | 361,451.88 | 159,002.68 | 520,454.56 | 1,103,594.00 | 47.2% |
| Last Tactical Mile | 330,513.06 | 145,392.70 | 475,905.76 | 899,500.00 | 52.9% |
| Digital Engineering | 207,398.87 | 91,234.76 | 298,633.63 | 1,000,690.00 | 29.8% |
| Hybrid II | 91,788.13 | 40,377.60 | 132,165.73 | 512,409.00 | 25.8% |
| | | | **1,427,159.68** | **3,516,193.00** | **40.6%** |

Read it with the period of performance in mind: these are **multi-year** awards
and this is **one year** of each, so the remaining headroom also has to carry
whatever other years draw on it. Digital Engineering's period of performance
ended 9 July 2025, which makes its $91,234.76 the most time-sensitive figure
here and the only one with no invoice to restate against.

Hybrid II's ceiling is the post-modification $512,409, not the $500,043 its
Schedule B prints — Modification 001 of 22 January 2026, already on the record.

---

## 7. What this is, and what has to happen before it is a claim

All three restatements are recorded `PROPOSED`, each carrying the seal hash of
the rate it used. The trail shows both positions — the earlier ones at 34.82%
are `SUPERSEDED` rather than deleted, because a position taken and then replaced
is part of the record.

Before any of it becomes a claim:

1. **A §4.4 written modification on each agreement.** Neither Drive AM's nor
   Hybrid's agreement was billed under a provisional rate, so moving off the de
   minimis election is a change of basis. The system refuses to accept a
   restatement that does not name the modification, in the handler and again in
   the schema.
2. **A budget realignment alongside it**, per §5 — a new INDIRECT category on
   two schedules, and an increase on the other two.
3. **The 43 certifications.** 200.430(i) goes to the allowability of the entire
   direct labour charge, and $300,740.69 of these very objectives' MTDC is
   wages. Nothing is timesheet-backed today; `evidence_ratio` is 0.0000 on
   every objective. This does not change a figure — adopting the reconstruction
   reproduces its shares — but it is what makes the figure usable.
4. **The square footage**, which decides where in §4's band the answer sits.
5. **The funding source on the asset register.** $850,382.89 of depreciation
   sits in OVERHEAD at `PENDING` under 200.436(b), and it is inside the pool
   every rate above is taken from.

Items 3 to 5 are the same three that gate the rate itself. Items 1 and 2 are
specific to putting it in front of NCDMM.

**One thing to decide before the conversation, not during it.** The $1,400.65
that 10039 over-billed against its own elected rate is a real finding on YBI's
side of the ledger. Raising it first, unprompted, alongside an ask of
$21,177.53 is the posture that makes the ask credible — and the system is built
so that the two are never presented as one net figure.

---

## 8. Reproducing it

```bash
YBI_SEED_PASSWORD=... BASE=... ./scripts/seed.sh
python scripts/classification_log.py --apply          # 757 of 757
POST /api/rates/seal
POST /api/rates/compute  {"admin_labour": "POOL"}     # 43.99%
POST /api/restate        {"objective_id": "DRIVE-AM", ...}
```

`rate.admin_labour_basis` records which of the two treatments produced a rate,
so a figure taken off this document can be traced to the policy it was computed
under rather than to whichever code happened to be deployed.
