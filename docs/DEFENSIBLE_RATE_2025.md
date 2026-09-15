# The 2025 rate, built to survive a line-by-line reading

**Regenerate with `scripts/defensible_rate.py`.** Nothing here is written to
the record. The certified rate is still 24.71%; this is what a defensible one
looks like and why it differs.

---

## 1. Why 24.71% is arithmetically right and hard to defend

It is a **31.62% overhead rate with 61% carved back out**. On Heidi's measured
estate the carve-out reaches **102.4%** and the overhead rate goes negative —
`rate_rate_check` refuses to record it.

**A carve-out that approaches its own pool is the model saying the pool was
never the right size.** A reviewer who sees one will test every carve-out line
by line rather than accept the rate, and three things will not survive that:

| | | citation |
| --- | --- | --- |
| **The pool was never segregated by activity** | YBI runs an incubator and a landlord business. The occupancy cost of let and vacant space belongs to the second and should not enter a federal pool and then be carved out of it. | App IV B.2.a |
| **A floor-area driver was applied to cost floor area does not drive** | $181,276.15 of the pool is T1 access, telephone, equipment and insurance. | 200.405 |
| **The tenants have already paid some of it back** | $133,998.11 of credits sit inside these accounts. Carving a space share off a figure already net of tenant recovery removes the same money twice. | 200.406 |

The third errs **against** YBI. The first two err for it.

---

## 2. How the pool is built instead

```
     occupancy cost, GROSS of tenant reimbursement       1,450,601.08
       of which the tenants have already repaid            133,998.11
  ×  the share of the estate that is YBI's own
  +  overhead that floor area does not drive                181,276.15
  −  200.436(b), scaled to the share that is YBI's own
  =  the federal overhead pool
                                            MTDC base    4,736,602.11
```

Grossing up before carving is what removes the double count: the tenants'
$133,998.11 is *their* share paid directly, so it belongs on the rental side
of the split rather than being deducted before the split and again by it.

---

## 3. The band, and the one question that sets its width

Common area — corridors, restrooms, conference rooms — serves tenants and the
incubator both. Heidi's floor plan separates two kinds of it, and they are not
the same question.

| reading | let share | YBI's own occupancy | less 436(b) in it | + non-space | federal pool | overhead |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all common follows the tenants | 94.01% of 103,909 sq ft | 86,895.36 | (9,358.96) | 181,276.15 | 258,812.55 | **5.46%** |
| **shared facilities ours, circulation pro rata** | **86.27% of 113,235 sq ft** | **199,215.40** | **(21,456.26)** | **181,276.15** | **359,035.29** | **7.58%** |
| all common is the incubator's own | 63.92% of 152,814 sq ft | 523,326.10 | (56,364.22) | 181,276.15 | 648,238.03 | **13.69%** |

**Take the middle, and not because it is the middle.** Splitting the difference
between two arguments is an average, not an argument. The middle row is the one
with a reason on it: a conference room an incubator books for its programme is
the incubator's, and a corridor serves whoever is in the building and follows
them. The plan names them separately — 9,326.5 sq ft of conference and meeting
space against 39,579 sq ft of circulation — so this is read off the document
rather than assumed.

---

## 4. The defensible structure

| | | |
| --- | ---: | --- |
| **Fringe** | **21.90%** | of salaries and wages |
| **Overhead** | **7.58%** | of MTDC · band 5.46% – 13.69% |
| **G&A** | **12.37%** | of MTDC |
| **Indirect, combined** | **19.95%** | of MTDC · band 17.83% – 26.05% |
| Fully loaded on labour | **1.4622×** | |

**Fringe and G&A are not in the band and cannot be.** Fringe is anchored at
both ends to source documents — the P&L's six accounts over the payroll
register, 401,783.60 / 1,835,047.17 = 0.2190 — so no floor plan touches it.
G&A carries no occupancy, so the carve cannot reach it. **Only overhead moves
on a measurement**, which is the check that the construction is sound.


---

## 4a. The 436(b) correction, and why it matters for reading the rest

The first version of this workpaper said **4.73%**. It subtracted the whole
$156,235.27 of 200.436(b) depreciation from a pool the space split had already
reduced to 13.73% — **the same money out twice**, costing YBI **2.85 points of
overhead**.

Depreciation on federally funded assets sits *inside* occupancy. The let share
of it left with the let share of everything else; only the part riding on YBI's
own floor was still there to remove. The asset register names no building on
any of the eighteen, so they are spread like the estate — if they sit
disproportionately on YBI's own floor the adjustment is larger, and
`b436_ours` is the line to argue about.

---

## 4b. Which way each judgment runs

The fair question about a rate that has moved from 43.99% to 19.95% in one week
is whether the assumptions have quietly stacked in one direction. They have
not, and this is the check rather than the assurance:

| judgment | taken | alternative | points | runs |
| --- | --- | --- | ---: | --- |
| Administrative labour | POOL | OBJECTIVE | 6.81 | **for YBI** |
| Tenant reimbursements | grossed up before the split | carve the net | 2.44 | **for YBI** |
| Overhead floor area does not drive | left uncarved | carve it | 3.30 | **for YBI** |
| 200.436(b) | scaled to YBI's share | subtract whole | 2.85 | **for YBI** |
| Insurance | left in the federal pool | carve as occupancy | 1.05 | **for YBI** |
| Common space | shared ours, circulation pro rata | all common ours | 6.11 | against |
| Common space | shared ours, circulation pro rata | all common to tenants | 2.12 | **for YBI** |

**18.57 points already sit in YBI's favour**, at five of the six forks. The one
place the construction gives ground is common space, and it gives it to a
reason rather than to caution.

**What moved the rate was the measurement, not the assumptions.** 43.99% was a
rate with no facilities carve-out at all, because no building was on the
record. Take every remaining fork against YBI and the overhead pool goes
negative — which is the same thing the engine said when it refused to record a
rate on Heidi's literal reading, and it is why the pool needs resizing rather
than the rate defending.

---

## 4c. $313,605.35 turns on a determination nobody has made

Migration `115`, `party_determination`, `v_subaward_exposure`,
`scripts/load_party_determinations.py`.

2 CFR 200.1 takes **the first $25,000 of each subaward** into MTDC and a
contract for services whole. So the same payment sits in the base or mostly
outside it depending on a 200.331 determination — and this system had never
recorded one. `burdened_buildup.py` shipped a `SUBAWARD_CAP` that **never
fired**, because these invoices categorise every one of them as `CONSULTANT`.

| objective | payee | amount | at stake |
| --- | --- | ---: | ---: |
| LTM | Defense & Energy Systems LLC | 102,000.00 | 77,000.00 |
| Drive AM | Elevate Systems | 101,075.89 | 76,075.89 |
| Digital Engineering | *(no payee on the ledger line)* | 100,000.00 | 75,000.00 |
| AAMEN | *(no payee on the ledger line)* | 77,710.46 | 52,710.46 |
| AAMEN | NezTech Corp. | 51,319.00 | 26,319.00 |
| LTM | *(no payee on the ledger line)* | 31,500.00 | 6,500.00 |
| | | | **313,605.35** |

Every one is `UNDETERMINED`, which the register reports as **NO DATA and never
a pass**. The schema refuses a half-made determination: one that is made
carries who made it, when, and forty characters of substance, because 200.331
turns on the substance of the relationship and not on what an invoice called
it.

Three of the six name **no payee at all** on the ledger line, which is a
separate question and a worse one.

---

## 5. Applied to each contract

**There is one rate structure and four bases.** An indirect cost rate is the
organisation's, not the contract's — Appendix IV gives YBI one. What differs
per award is the MTDC it carries, the ceiling it sits under, and what its own
schedule budgets.

| award | MTDC | indirect @ 19.95% | ceiling | headroom |
| --- | ---: | ---: | ---: | ---: |
| Drive AM | 361,451.88 | 72,106.40 | 1,103,594.00 | 670,035.72 |
| Last Tactical Mile | 330,513.06 | 65,934.38 | 899,500.00 | 503,052.56 |
| Hybrid Phase 2 | 91,788.13 | 18,310.91 | 512,409.00 | 402,309.96 |
| Digital Engineering | 207,398.87 | 41,374.21 | 1,000,690.00 | 751,916.92 |

**Every award has headroom**, which is the useful fact: the rate is not
constrained by any ceiling. What constrains it is what each schedule budgets —
Drive AM and Hybrid carry **no INDIRECT category at all**, so an indirect line
on either is a budget realignment beside the §4.4 change of basis, not just a
change of rate.

Digital Engineering's prime is **N00174-20-1-0031** through Energetics
Technology Center and NSWC Indian Head, not the AFRL America Makes cooperative
agreement. Same rate, different federal money.

---

## 6. What still has to be settled

| | worth |
| --- | --- |
| **Three rows of the floor plan cannot be read.** The Taft/Semple cell reading `"3630 and 25,809"`; Semple's rows accounting for $49,527.00 of $109,932.32 of rent; 5,459.8 sq ft of YBI Incubator vacant entered twice. | the whole band |
| **The insurance policy schedule.** $57,596.36 sits in the federal pool because property cannot be told from general liability. Property insurance is floor-area driven and would carve; this leaves it in, which favours YBI and a reviewer will ask. | up to 1.05 points of overhead |
| **$33,066.60 of the credits carry no payee** and two are a reclassification and a parking-lot insurance recovery, not tenant recovery. | ~0.6 points |
| **Is the invoiced labour cost or a loaded rate?** Unchanged by any of this and still the largest single question in the file. | $462,047.66 |

**None of this is on the record.** Moving the classification to segregate the
rental activity costs an unseal and a re-certification, which is two deliberate
acts with Tom's name on them.
