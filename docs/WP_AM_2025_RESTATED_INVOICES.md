# WP — The forty-three 2025 NCDMM invoices, rebuilt on the certified rate

**Bookmarked 15 September 2026, against the sealed and certified 2025
classification.** Regenerate with `scripts/restate_2025_invoices.py`; the
rendering is deterministic, so `docs/restated-2025/MANIFEST.md` reproduces
digest for digest from the same record. A digest that moves means a figure
moved.

> **Nothing here has been issued.** These are proposed restatements. Every one
> needs a §4.4 modification changing the basis from the 10% de minimis to the
> negotiated rate before it could go anywhere.

Rendered: `docs/restated-2025/R-<objective>-<YYYYMM>.pdf`, forty-three of them,
on the face NCDMM's payables already recognises.
Workbook: `docs/restated-2025/YBI-2025-AM-restated-invoices.xlsx`, with the
QuickBooks columns left **empty** — a blank is unanswered, and unanswered is a
value.

The settlement this supports is `docs/SETTLEMENT_2025.md`.

---

## 1. What changed since the thirty-six

Three things, and the second is the one that moves the money.

**A fourth award.** Digital Engineering was never in this workpaper and is the
largest single offset in the file — $320,427.12. It has seven invoices, a
complete monthly hours log for two people, and $169,975.01 of direct
non-labour, so it restates exactly as the other three do. It was absent
because the script carried a hand-written list of three contracts while the
restatement register carried four.

**The rate is certified, and it is 24.71%, not 43.99%.** The thirty-six were
built before the estate and the asset register existed, so no 200.465
facilities carve-out and no 200.436(b) depreciation carve-out were in the
pool. Both are now, at **$913,104.60** against an overhead pool of
$1,497,879.12 — 61% of it. The combined rate fell from 43.99% to 24.71% and
the whole of that fall is the two carve-outs.

**Each contract's months are read from the record, not assumed to be twelve.**
Digital Engineering ran to 9 July 2025 and has seven. A constant twelve would
have rendered five empty invoices for a closed award, which says the months
were worked and nothing was billed — a different statement from the award
having ended.

---

## 2. The year

| | ceiling | billed 2025 | restated | movement |
| --- | ---: | ---: | ---: | ---: |
| Drive AM | 1,103,594 | 579,240.87 | 450,766.64 | **(128,474.23)** |
| Last Tactical Mile | 899,500 | 368,222.24 | 412,182.84 | **43,960.60** |
| Hybrid Phase 2 | 512,409 | 191,638.05 | 114,468.98 | **(77,169.07)** |
| Digital Engineering | 1,000,690 | 579,074.25 | 258,647.13 | **(320,427.12)** |
| **all four** | **3,516,193** | **1,718,175.41** | **1,236,065.59** | **(482,109.82)** |

**These are two directions and they are never added together.** $43,960.60 is
money to ask for; $521,848.42 is money to give back. A single net figure hides
both, which is why `v_restatement` has no net column and why the settlement
memo shows each award in full before it states an aggregate.

### The one place this workpaper and the engine disagree, by $4,222.00

The script checks itself against `v_restatement` on every run and prints both:

| | this workpaper | the restatement | difference |
| --- | ---: | ---: | ---: |
| Drive AM | (128,474.23) | (128,474.23) | 0.00 |
| Last Tactical Mile | 43,960.60 | 43,960.60 | 0.00 |
| Hybrid Phase 2 | (77,169.07) | (72,947.07) | **(4,222.00)** |
| Digital Engineering | (320,427.12) | (320,427.12) | 0.00 |

Both are right and they measure different registers. `POST /api/restate`
measures the **invoice register**, which holds nine Hybrid invoices totalling
$187,416.05. This workpaper measures the **Income section of the ledger**,
which holds $191,638.05 — three further postings in October, November and
December described only as "Hybrid 2". So Hybrid was billed after the invoice
register stops, and the register does not have those three.

That is `v_invoice_income_tie`, which reports the difference by name rather
than netting it. **The settlement uses the invoice register figure**, because a
settlement has to be against invoices the sponsor holds.

---

## 3. What the monthly view says that the annual view hides

The largest single-month movements are an order of magnitude larger than the
year's, in both directions:

| | | movement |
| --- | --- | ---: |
| Drive AM | May | **(116,109.49)** |
| Drive AM | October | **+94,146.85** |
| Drive AM | September | (82,735.44) |
| Digital Engineering | July | (79,728.13) |
| Digital Engineering | March | +47,462.71 |
| Last Tactical Mile | March | +36,093.78 |

Drive AM billed $150,719.52 in May against $34,610.03 of restated cost, and
$62,615.64 in October against $156,762.49. **Billing and cost do not fall in
the same month**, by six figures.

So: **restate the year, not the months.** Forty-three transactions swinging six
figures in both directions to settle $482,109.82 is the same economics
presented in the way most likely to trigger a desk audit. These documents exist
so the year's figure can be *traced* to a month, not so the months can be
issued.

---

## 4. Four contracts, four different billing methods, one election

Every one of these awards elects `DE_MINIMIS_10`. None of them was billed that
way, and no two were billed alike.

| | how labour was billed | billed labour ÷ wages + fringe |
| --- | --- | ---: |
| Drive AM | loaded labour rate, no indirect line | **1.70×** |
| Hybrid Phase 2 | loaded labour rate, no indirect line | **2.25×** |
| Last Tactical Mile | labour plus a flat $3,000/month indirect | **1.40×** |
| Digital Engineering | **a flat $82,724.89 a month, no categories at all** | — |

Full burden on the certified rate is 1.2190 × 1.2471 = **1.52×**. So Drive AM
and Hybrid billed labour *above* full burden — which is why restating them
gives money back — and Last Tactical Mile billed *below* it, which is why
restating it claims money.

**Digital Engineering is the one that is not an invoice at all in substance.**
Seven identical monthly postings of $82,724.89, the last marked "(Final)", with
no labour, materials, travel or indirect line anywhere in the description.
Against $258,647.13 of restated cost for the same seven months. That is a fixed
monthly draw on a cost-reimbursement instrument, and it is the reason its
offset is the largest.

Three further things the categories show:

- **Last Tactical Mile is the only award that ever billed an indirect line** —
  $44,400.00, eleven months at $3,000 and one at $11,400. It is also the only
  one whose Schedule B budgets indirect. The other three billed **$0.00** of
  indirect across thirty-one invoices.
- **Last Tactical Mile is 63.5% consultant cost** — $233,900.00 of $368,222.24.
  That is what makes its MTDC large relative to its labour and why it
  under-recovers on a rate applied to MTDC.
- **Drive AM's non-labour billing is $274,757.07** — $272,493.96 of ODCs,
  $1,880.90 of materials, $382.21 of travel, 48% of its billing — against
  $181,880.88 the ledger classifies as Drive AM direct non-labour. The gap is
  **$92,876.19** and it is unresolved: either the classification under-attributes
  Drive AM cost, or the billing over-claimed. **Restating to cost only works if
  the cost record is complete**, and this is the one contract where that is in
  question.

---

## 5. The rate these are built on

| | pool | base | rate |
| --- | ---: | ---: | ---: |
| FRINGE | 401,783.60 | 1,835,047.17 salaries and wages | **21.90%** |
| OVERHEAD | 584,774.52 | 4,736,602.11 MTDC | 12.35% |
| G&A | 585,875.91 | 4,736,602.11 MTDC | 12.37% |
| **INDIRECT_COMBINED** | **1,170,650.43** | **4,736,602.11 MTDC** | **24.71%** |

Administrative labour on the `POOL` basis. Sealed at 757 judgments, 100% of
the 2025 cost classified, $0.00 unclassified. Certified by Tom Metzinger on
15 September 2026. Every pool ties at `pool_variance` 0.00 and all four
`v_rate_anchor` rows tie.

The overhead pool is stated **after** $913,104.60 of carve-outs:

| | citation | amount |
| --- | --- | ---: |
| Taft Technology Center — let and vacant | 200.465 | 281,002.12 |
| Depreciation on federally funded assets | 200.436(b) | 156,235.27 |
| Tech Block Building 5 — let and vacant | 200.465 | 149,498.82 |
| Semple Building — let and vacant | 200.465 | 130,300.50 |
| America Makes Building — let and vacant | 200.465 | 128,010.25 |
| YBI Main (Vindicator) — let and vacant | 200.465 | 68,057.64 |
| | | **913,104.60** |

---

## 6. The measurement that arrived the same day, and which way it points

The five 200.465 rows above are computed against an estate **derived from
documents, not measured from floor plans** — building areas from the JobsOhio
grant's $116.27/sq ft against the 2024 audited statements, let area from the
rent roll at $7.00/sq ft. Every choice in that derivation took the low side, so
the carve-out is if anything too small and the rate too high.

**A measured floor plan came back from Heidi Ruby on 15 September 2026** and is
on file as evidence `EV-224fc92fe21b`. It has **not** been accepted into the
record and no figure in this workpaper moves until it is. Where it can be
compared, it points one way:

| building | derived let/vacant share | measured | |
| --- | ---: | ---: | --- |
| Taft Technology Center | 99.1% | ~100% | confirms |
| America Makes Building | 99.9% | 100% | confirms |
| Semple Building | 55.9% | ~100% | **higher** |
| Tech Block Building 5 | 33.2% | ~92% of assignable | **much higher** |
| YBI Main (Vindicator) | 16.9% | ~83% of assignable | **much higher** |

A higher let-and-vacant share means a **larger** carve-out, a **smaller**
federal overhead pool and a **lower** combined rate than 24.71%. A lower rate
supports less indirect, so **every offset in section 2 grows in the direction
it already runs**: the three give-backs get larger and Last Tactical Mile's
claim gets smaller.

Three rows of the reply cannot be read yet and are with Heidi:

1. `Taft/semple · suites 2A,2B & building` gives its area as the text
   **"3630 and 25,809"**, which is not a number, so the row is held back. The
   rent settles which building it is — $203,115.96 on that row plus $33,965.52
   on the vacant Taft suite is **$237,081.48, exactly `4021 TTC Rent`** — but
   whether the two figures are one building or two is hers to say.
2. **Semple** reports 16,999 sq ft against $109,932.32 of Semple rent, of which
   her rows account for $49,527.00. Rows appear to be missing.
3. YBI Incubator carries **5,459.8 sq ft of vacant space twice**, once as
   "floors 2-5" and once as "unoccupied offices F3-5". If that is one area
   entered twice, the building's vacant space halves.

Until those are answered, the measured estate is not a figure — it is a
direction. The direction is down.

---

## 7. What is still not on the record

- **No payment is recorded against any invoice.** The `receipt` register is
  empty. Whether a restatement is an additional claim or a correction to a
  settled one turns on that, and nothing here can say.
- **No one of the forty-three people has certified their 2025 effort** under
  2 CFR 200.430(i). Every restated labour line is the management
  reconstruction. It does not move a figure; it moves whether the figure is
  usable.
- **The category split of the restated non-labour is not on the cost record.**
  The ledger carries an account and a payee, not an invoice category. It is one
  line on every restated invoice and the QuickBooks columns in the workbook are
  where it plugs in. **The totals do not move when it does.**
- **Digital Engineering's invoices are billed to "NCDMM - America Makes" on
  their face**, and its prime is N00174-20-1-0031 through Energetics Technology
  Center and NSWC Indian Head — not the AFRL America Makes cooperative
  agreement FA8650-20-2-5700 the other three sit under. The restated face
  reproduces what YBI issued, because that is the document NCDMM's payables
  holds. Whose federal money the offset settles against is a different question
  and `docs/SETTLEMENT_2025.md` keeps it separate.
