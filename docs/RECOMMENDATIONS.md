# Recommendations — 2025 cost allocation

Everything recommended during the classification and rate work, in one place,
with the figure each one turns on. Written against the live record at 100%
classification: 757 of 757 cost groups judged, $0.00 unclassified, sealed at
757 judgments.

Read `CLAUDE.md` for *why* each treatment is what it is. This is the list of
what somebody has to do about it.

---

## Where the rate stands

| | rate | pool | base |
| --- | ---: | ---: | ---: |
| FRINGE | **21.90%** | $401,783.60 | $1,835,047.17 salaries and wages |
| OVERHEAD | 29.61% | $1,497,879.12 | $5,058,960.45 MTDC |
| G&A | 5.21% | $263,517.59 | the same base |
| **INDIRECT_COMBINED** | **34.82%** | $1,761,396.71 | the same base |

Pools: DIRECT $2,425,193.27 · EXCLUDED $1,906,942.40 · OVERHEAD $1,497,879.12
· FRINGE $401,783.60 · FUNDRAISING $281,203.71 · G&A $263,517.59 ·
UNALLOWABLE $115,640.95.

Every pool ties at `pool_variance` 0.00; all four `v_rate_anchor` rows tie;
all eleven cross-reference controls tie. 21.90% is not asserted anywhere — it
falls out of the six accounts the P&L names as fringe over the payroll
register.

**34.82% is a point in a range, not an answer.** Two open questions move it
in opposite directions and neither is settled:

| carve-out applied | OVERHEAD | combined | with admin labour in the G&A pool |
| ---: | ---: | ---: | ---: |
| 0% (today) | 29.61% | **34.82%** | 43.99% |
| 20% | 23.69% | 28.90% | 37.67% |
| 40% | 17.77% | 22.97% | 31.34% |
| 55.6% | 13.15% | 18.36% | 26.41% |

### And what it is worth

The whole 2025 restatement is **$16,137.57** — Drive AM $13,090.20, Last
Tactical Mile $2,568.94, Hybrid $478.43, three invoices. The entire range of
uncertainty above is about $12,000 on that.

The same questions against a forward rate on $5.06m of direct cost are worth
**$463,907 a year** (the administrative-labour question) and **$832,705 a
year** (the carve-out). **Settle these for the 2026+ rate, not for the back
claim.** The restatement is close to a rounding error beside the forward
number, and that should decide how much argument each one gets.

---

## 1 — Certification and employment terms · *first, because it is slowest*

**No rate impact. The most serious item on this list.**

The whole $1,835,047.17 labour distribution is `RECONSTRUCTION` — **zero
timesheet entries exist for anybody**, and **zero certifications**. 43 people
carry `NEEDS_CERTIFICATION` at BLOCKING.

2 CFR 200.430(i)(1) wants records that reflect the work actually performed,
supported by internal control, with after-the-fact review; (i)(1)(viii) says
budget estimates alone do not qualify as support. This does not change a
single figure in the rate — it changes whether the rate is **usable**. In a
Single Audit it goes to the allowability of the entire direct labour charge,
not to how that charge is allocated.

It compounds: **43 `EMPLOYMENT_UNKNOWN`**. `v_employment_expected` is empty,
so there is no denominator. Nobody can certify "40% on Drive AM" when the
record cannot say whether they were full-time or half-time — and
`POST /api/timesheet/submit` already refuses for exactly that reason.

**The goal is not to invent 2025 timesheets.** A reconstruction can be
supported if the person whose effort it was adopts and certifies it after the
fact. What is not supportable is a reconstruction with no certification and
no employment terms.

**Do, in this order, because the data forces the order:**

1. **Issue the roster request** (`PEOPLE_ROSTER`) — *issued*, request 1 — and
   accept the reply. It asks for employment status, contracted weekly hours
   and the dates worked. Those give `expected_hours`, which is the
   denominator, and until it exists the draft has nothing to divide and says
   so rather than guessing.
2. **Each person adopts their own pre-populated sheet.**
   `GET /api/timesheet/draft` turns each objective's share of that person's
   wages into the same share of their contracted hours;
   `POST /api/timesheet/adopt` writes it under their own name. Nobody enters
   time for anybody else — that rule does not bend, and a sheet somebody else
   filled in is the precise thing a certification exists to rule out.
3. **Each person submits and signs.** The certification records the
   distribution and its hash, so what was signed cannot drift afterwards.

**What the draft is, and what it is not.** It is the controller's
reconstruction shown to the person whose work it was, to read, correct and
adopt. 200.430(i) does not require a contemporaneous record; it requires one
that reflects the work actually performed, supported, and reviewed after the
fact. A reconstruction the person signs meets that. A reconstruction nobody
ever saw does not, which is where 2025 has been sitting.

The hours are spread uniformly across the weekdays of the employed span,
because `timesheet_entry` is a *day's* record — a row is capped at 24 hours
and a trigger caps the person-day at 24 across rows. Uniform is the honest
shape: it is visibly the same split every day, which together with
`basis = RECALL` on every row tells a reviewer at a glance that this is a
reconstruction rather than a diary. Varying it to look contemporaneous is
what would manufacture precision.

**Submitting does not move the rate, and that was worth proving.** A
submitted timesheet switches that person's distribution in
`v_labor_effective` from reconstructed units to hours. Adopting the
reconstruction faithfully reproduces its shares, so the rate holds — if it
did not, the rate would depend on who had got round to signing.

`v_certification_chase` is the list to work, by manager. A manager cannot
sign on somebody's behalf: 200.430(i) wants the person whose effort it was.

**And fix it at source for 2026.** The reason this is a reconstruction is
that nobody kept contemporaneous records. `basis = AS_WORKED` requires entry
within seven days and the schema enforces it; that is the standard to run
2026 against.

---

## 2 — Square footage and the 200.465 carve-out · *second, also slow*

**Worth up to 16 points of combined rate — the largest single lever.**

`v_facility_occupancy` inner-joins to its space totals, so on the live record
— **no buildings, no space units** — it returns nothing, `POST /api/rates/
compute` computes **no carve-out at all**, and every dollar of tenant and
vacant occupancy cost sits in the federal pool.

**Do:** issue the `SPACE_INVENTORY` request — *issued*, request 2 — and
accept the reply. It goes out pre-filled from
YBI's own lease schedule and asks only for the column no document carries —
square footage by suite and use.

### The trap in it, which matters more than the measurement

The facilities accounts **already carry $262,885 of booked tenant credits**:

| account | gross | net | credits already booked |
| --- | ---: | ---: | ---: |
| 5027 TTC Utilities | $257,774.24 | **$0.00** | $128,887.12 — rebilled to Steelite in full |
| 5200 Real Estate Tax | $149,466.20 | $26,526.66 | $61,469.77 |
| 5043 Boardman St Electric | $154,267.70 | $78,514.36 | $37,876.67 |
| 5041 Semple Electric | $31,060.90 | $4,160.08 | $13,450.41 |
| others | | | ~$21,201 |

Carving a square-footage share on top of figures already net of recovery
**removes the same money twice.** Whoever computes the carve-out has to pick
one basis and say which:

- **gross occupancy cost**, carved by square footage; or
- **net of booked recoveries**, with the carve-out reduced accordingly.

Not both. This is the single easiest way to get the rate materially wrong in
YBI's favour, which is the direction that gets found.

### And a control that does not exist yet

Nothing says the carve-out was never evaluated. `carve_out` is empty,
`pool_carved` reads 0.00, and `v_rate_buildup` reports **TIES** — because the
pool does tie to itself. Nothing distinguishes *there is no tenant space*
from *nobody has measured any*, which is `029`'s lesson inside the largest
adjustment in the model. `SPACE_UNMEASURED` fires per building and a record
with no buildings has none to fire on, so the worklist is silent too.

**Recommended:** a schema control that refuses to call a rate complete while
the carve-out has never been evaluated. `scripts/classification_log.py`
reports it as a three-state anchor today, which is a read-side report, not a
guarantee.

---

## 3 — Administrative labour: in the base, or in the G&A pool · *a decision*

**Worth +9.17 points. The only item on this list with no external
dependency — it needs a decision, not a document.**

`YBI-GA` carries **$264,444.90** of wages ($322,358.33 with fringe) and is
modelled as a **cost objective**, so it takes a **$100,013.06 allocation of
indirect** rather than forming part of it.

Appendix IV B puts the director's office, accounting and personnel
administration *in* the G&A pool. The YBI-GA distribution is Kelly, Ruby,
Shaulis, Jaric, Politsky and Ewing — the administrator herself. Modelling
that as an objective means **allocating the indirect pool to its own
administration**, which then recovers from nobody.

The counter-argument, which is real and does not apply: `FUNDRAISING` and
`UNALLOWABLE-ACTIVITY` *are* deliberately modelled as benefiting objectives,
because 200.413 and Appendix IV B.3.d say they must bear indirect while
recovering nothing. That is the opposite case. General administration **is**
the indirect; allocating a pool to itself is a category error.

| | base | G&A pool | combined |
| --- | ---: | ---: | ---: |
| as computed (objective) | $5,058,960.45 | $263,517.59 | **34.82%** |
| administration in the pool | $4,736,602.12 | $585,875.92 | **43.99%** |

**One thing to confirm before deciding:** that `YBI-GA` in the effort
distribution is genuinely general administration, and not the bucket
unattributable time went into. Ten named people suggests the former. It is
the controller's reconstruction, so it is the controller's call.

**Set up rather than applied.** The treatment is recorded on the rate now
(`rate.admin_labour_basis`) and chosen per computation, so the decision is a
documented choice with both figures beside it rather than a property of the
code. Nothing has been changed by default.

---

## Smaller things, already done or still open

**Done in the classification work** — see `CLAUDE.md` for each:

- `propose()` refused $1,382,737 of the queue because a crosswalk mapping
  contained a slash, and separately offered DIRECT proposals with no
  objective that the database refuses. Both fixed.
- `POST /api/rates/compute` was **not idempotent**: the same sealed set
  answered 37.82% then 34.82%, because fringe entered MTDC only if a FRINGE
  rate already existed. Fixed; the model derives its own.
- Six screens reached past the request layer, so a refused import reported as
  "0 lines added to the ledger" in the tone used for success. Fixed.
- $986,592.77 of cost on non-federal objectives was marked federally
  ALLOWABLE. Now follows `cost_objective.is_federal`.
- **The payroll register was never $1,835,047.18.** `v_labor_effective`
  rounded each objective's share of a person's wages independently, so a
  person's distribution did not have to add back to what they were paid —
  six of the forty-three already drifted by a cent, and the eleventh control
  tied because the cents happened to net out. Read off the controller's
  workbook the register is **$1,835,047.17**, and `BASELINE_2025.md` carried
  $1,835,047.16 in a third place. Migration `069` allocates by largest
  remainder so it adds back by construction. **The fringe rate is unmoved** —
  401,783.60 / 1,835,047.17 is still 0.2190 — and the difference the Bacon
  credit explains is $45,053.23 rather than $45,053.24. Corrected wherever
  it was quoted.

**Still open, and each needs a person:**

| | |
| --- | --- |
| **$105,865.41** | The Staffmark **Q1 2020** Employee Retention Tax Credit, received May 2025. A credit relating to a period in which federal awards bore the wage cost is owed back under 200.406(b). Excluded from the 2025 pools; the federal treatment is PENDING until somebody establishes which 2020 awards bore those wages. **This is a liability, not income, and it is not on `FOR_TOM_TO_VERIFY.md` yet.** |
| **$850,382.89** | Depreciation is classified OVERHEAD with the federal treatment PENDING. 200.436(b) makes depreciation on a federally funded asset unallowable and the fixed-asset schedule has **no funding-source column at all**, which 200.313(d)(1) requires. That gap is a finding in its own right. |
| **$588,538.89** | `5227 Portfolio consulting`, treated as DIRECT on the judgment that a consultant pass-through is contractor cost under 200.331 — services inside YBI's own programme, so no $25,000 MTDC cap, in the base, with G&A applied for YBI's oversight. Worth confirming with counsel if NCDMM ever pushes back. |
| **$392,447.09** | A wash pair on 31 December in that same account: posted and reversed the same day, no payee, no description. EXCLUDED. Somebody should know what it was. |
| **$37,261.00** | `5001 Cost of Goods Sold` is classified DIRECT to Xjet on inference. The inventory journal entry its own description points at — *"Used Inventory (See JE for breakdown)"* — says what was consumed and for whom, and nobody has read it. Cheapest item on this list to settle. |
| **$57,596.36** | Insurance is all in OVERHEAD. The policy schedule splits property from general liability; it does not move the combined rate, but OVERHEAD is carved for tenant space and G&A is not, so the general-liability share is being carved when it should not be. |

---

## The order to work in

Sorted by lead time rather than by size, because two of these are asks of
other people and one is a decision.

1. **Roster request out, then the 43 certifications.** Weeks. Blocks whether
   the rate is usable at all. The ask is issued; the reply has to come back
   and be accepted before anybody's draft can be adopted.
2. **Space inventory out.** Weeks. Worth ±16 points, and carries the
   double-count trap. Issued.
3. **Administrative labour.** An afternoon, and it is entirely internal.
   Worth +9 points. Nothing is waiting on anybody else — the engine takes
   either basis, the rate records which was used, and
   `v_admin_labour_decision` puts both figures on one row. It needs the
   controller to say which.
