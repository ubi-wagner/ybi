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
  −  200.436(b) depreciation on federally funded assets     156,235.27
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

| reading | let share | federal pool | overhead |
| --- | ---: | ---: | ---: |
| all common follows the tenants | 94.01% of 103,909 sq ft | 111,936.24 | **2.36%** |
| **shared facilities ours, circulation pro rata** | **86.27% of 113,235 sq ft** | **224,256.28** | **4.73%** |
| all common is the incubator's own | 63.92% of 152,814 sq ft | 548,366.98 | **11.58%** |

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
| **Overhead** | **4.73%** | of MTDC · band 2.36% – 11.58% |
| **G&A** | **12.37%** | of MTDC |
| **Indirect, combined** | **17.10%** | of MTDC · band 14.73% – 23.95% |
| Fully loaded on labour | **1.4275×** | |

**Fringe and G&A are not in the band and cannot be.** Fringe is anchored at
both ends to source documents — the P&L's six accounts over the payroll
register, 401,783.60 / 1,835,047.17 = 0.2190 — so no floor plan touches it.
G&A carries no occupancy, so the carve cannot reach it. **Only overhead moves
on a measurement**, which is the check that the construction is sound.

---

## 5. Applied to each contract

**There is one rate structure and four bases.** An indirect cost rate is the
organisation's, not the contract's — Appendix IV gives YBI one. What differs
per award is the MTDC it carries, the ceiling it sits under, and what its own
schedule budgets.

| award | MTDC | indirect @ 17.10% | ceiling | headroom |
| --- | ---: | ---: | ---: | ---: |
| Drive AM | 361,451.88 | 61,821.28 | 1,103,594.00 | 680,320.84 |
| Last Tactical Mile | 330,513.06 | 56,529.63 | 899,500.00 | 512,457.31 |
| Hybrid Phase 2 | 91,788.13 | 15,699.07 | 512,409.00 | 404,921.80 |
| Digital Engineering | 207,398.87 | 35,472.67 | 1,000,690.00 | 757,818.46 |

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
