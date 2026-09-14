# WP — The thirty-six 2025 America Makes invoices, rebuilt

**Bookmarked 13 September 2026, against the sealed 2025 classification.**
Regenerate with `scripts/restate_2025_invoices.py`; the rendering is
deterministic, so `docs/restated-2025/MANIFEST.md` reproduces digest for
digest from the same record. A digest that moves means a figure moved.

> **Nothing here has been issued.** These are proposed restatements. Every one
> needs a §4.4 modification changing the basis from the 10% de minimis to the
> negotiated rate before it could go anywhere.

Rendered: `docs/restated-2025/R-<objective>-<YYYYMM>.pdf`, thirty-six of them,
on the face NCDMM's payables already recognises.
Workbook: `docs/restated-2025/YBI-2025-AM-restated-invoices.xlsx`, with the
QuickBooks columns left **empty** — a blank is unanswered, and unanswered is a
value.

---

## 1. What to lay beside what, on Monday

The workbook's `By month` sheet has eleven columns on the right that this side
of the record cannot fill: the QB invoice number, its date, and its category
split. Those are the comparison. What each one tests:

| | |
| --- | --- |
| **QB invoice no / date** | whether thirty-six invoices is the right count. This workpaper assumes one per contract per month because the ledger carries exactly thirty-six monthly income postings. If QB holds thirty-eight, two of them are not in the ledger. |
| **QB total vs `as billed total`** | whether the ledger's income postings *are* the invoicing. They should agree month for month. This is the control that was missing when four published figures were computed against a three-invoice sample. |
| **QB category columns vs `restated non-labour`** | the one thing the cost record cannot supply. The ledger carries an account and a payee, not an invoice category, so the restated non-labour is a single line. The split plugs in; **the totals do not move when it does.** |

---

## 2. The year, and then the months

| | ceiling | as billed 2025 | restated | movement |
| --- | ---: | ---: | ---: | ---: |
| Drive AM | 1,103,594 | 579,240.87 | 520,454.56 | **(58,786.31)** |
| Last Tactical Mile | 899,500 | 368,222.24 | 475,905.76 | **107,683.52** |
| Hybrid Phase 2 | 512,409 | 191,638.05 | 132,165.73 | **(59,472.32)** |
| **all three** | **2,515,503** | **1,139,101.16** | **1,128,526.05** | **(10,575.11)** |

Unchanged from `WP_AM_RESTATEMENT_IF_ACCEPTED.md`, and that is the point: the
thirty-six months add back to the recorded allocation to the cent, on all
three contracts. The script refuses to write anything if they do not.

**But the monthly view says something the annual view hides.** The largest
single-month movements are an order of magnitude larger than the year's:

| | | movement |
| --- | --- | ---: |
| Drive AM | October | **+118,382.12** |
| Drive AM | May | **(110,758.82)** |
| Drive AM | September | (75,026.45) |
| Last Tactical Mile | March | +44,610.20 |
| Last Tactical Mile | December | +35,392.60 |

Drive AM billed $150,719.52 in May against $39,960.70 of cost, and $62,615.64
in October against $180,997.76. **Billing and cost do not fall in the same
month**, by five and six figures — which is a fact about when invoices were
raised, not about the rate.

**So restate the year, not the months.** Month-by-month credits and claims
swinging six figures in both directions, netting to $10,575.11, is the same
economics presented in the way most likely to trigger a desk audit. The
thirty-six documents exist so the year's figure can be *traced*, not so
thirty-six transactions can be issued.

---

## 3. What the monthly split shows that the annual one could not

### 3.1 Two of the three billed labour at a flat monthly figure, all year

| | monthly labour billed | months |
| --- | ---: | --- |
| Drive AM | **25,373.65** | all twelve, identical |
| Last Tactical Mile | **7,493.52** | all twelve, identical |
| Hybrid Phase 2 | **19,168.47** | eight identical, then 19,068.19 in September |

Actual monthly wages on Drive AM run from $10,733.22 to $14,345.27 — a 34%
spread. A flat monthly labour figure is a **rate times assumed hours**, not
cost reimbursement, and all four awards are cost reimbursement invoiced
monthly (ICAM §6 CONTRACT TYPE). This is the loaded-rate finding, visible on
the face of the billing rather than inferred from an annual ratio.

### 3.2 The loading is not the same on the three contracts

| | billed labour | restated wages + fringe | loading |
| --- | ---: | ---: | ---: |
| Drive AM | 304,483.80 | 179,571.00 | **1.70×** |
| Last Tactical Mile | 89,922.24 | 64,128.99 | **1.40×** |
| Hybrid Phase 2 | 172,415.95 | 76,788.03 | **2.25×** |
| **all three** | **566,821.99** | **320,488.02** | **1.77×** |

The fully burdened multiplier the sealed classification computes is **1.44×**
(fringe 21.90%, then indirect 43.99% on the MTDC). So LTM's labour was billed
*below* full burden, Drive AM's above it, and **Hybrid's at more than half as
much again as full burden**. Three different embedded rates under one de
minimis election, and none of them is 10%.

### 3.3 LTM's indirect line is a flat $3,000 a month, not a rate

Eleven months at exactly $3,000.00 and February at $11,400.00. It is not 10%
of anything, it does not move with the base, and it is the only indirect line
on any of the three contracts all year — $44,400.00 against $145,392.70 of
restated indirect.

`AMERICA_MAKES_RESTATEMENT.md` read invoice 10039's $3,000 as **18.76%** of
that invoice's base. That reading is correct for that invoice and **wrong as a
description of the method**: 18.76% is what a flat $3,000 happens to come to
on a month whose base was $15,993.52. February's identical method came to
20.54%. There is no rate; there is a monthly figure.

### 3.4 Hybrid was worked for a quarter after the billing stopped

The last real Hybrid invoice is September. October, November and December
carry $1,474.00, $1,374.00 and $1,374.00 of `Hybrid 2` with **no labour line
and no category breakdown** — the only three postings in the year whose
description names no invoice category, and the script reports them rather than
bucketing them.

The hours log puts $2,353.43, $3,109.75 and $4,870.13 of wages on the project
in those months. **$18,137.41 of restated cost against $4,222.00 billed** in
the final quarter. The award's original period of performance ended 10 October
2025 and Modification 001 extended it to 30 June 2026, so the work is within
term; it simply was not invoiced.

---

## 4. The thirty-six, month by month

Labour is the month's wages from the hours log — **all fourteen
person-objective pairs on these three contracts have a full twelve-month log**,
so this is read rather than smeared. Fringe at 21.90% and the indirect
allocation are spread across the months by largest remainder against the
recorded annual figure, not rounded month by month: per-month rounding drifted
one and two cents against the engine on all three contracts the first time this
ran, which is migration `069`'s defect in a new place.

### Drive AM

| month | labour | fringe | non-labour | MTDC | indirect @ 43.99% | **restated** | as billed | movement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 | 14,345.27 | 3,141.61 | 0.00 | 17,486.88 | 7,692.48 | **25,179.36** | 25,373.65 | (194.29) |
| 02 | 12,752.95 | 2,792.90 | 13,113.85 | 28,659.70 | 12,607.40 | **41,267.10** | 27,798.15 | 13,468.95 |
| 03 | 11,877.11 | 2,601.09 | 2,142.86 | 16,621.06 | 7,311.61 | **23,932.67** | 26,032.42 | (2,099.75) |
| 04 | 11,793.19 | 2,582.71 | 4,960.86 | 19,336.76 | 8,506.24 | **27,843.00** | 33,785.53 | (5,942.53) |
| 05 | 12,640.24 | 2,768.21 | 12,343.96 | 27,752.41 | 12,208.29 | **39,960.70** | 150,719.52 | (110,758.82) |
| 06 | 10,987.94 | 2,406.36 | 3,662.31 | 17,056.61 | 7,503.20 | **24,559.81** | 29,086.96 | (4,527.15) |
| 07 | 10,733.22 | 2,350.57 | 3,700.00 | 16,783.79 | 7,383.19 | **24,166.98** | 29,073.65 | (4,906.67) |
| 08 | 10,896.72 | 2,386.38 | 381.83 | 13,664.93 | 6,011.20 | **19,676.13** | 25,940.16 | (6,264.03) |
| 09 | 11,457.83 | 2,509.26 | 26,017.29 | 39,984.38 | 17,589.13 | **57,573.51** | 132,599.96 | (75,026.45) |
| 10 | 13,629.86 | 2,984.94 | 109,086.82 | 125,701.62 | 55,296.14 | **180,997.76** | 62,615.64 | 118,382.12 |
| 11 | 12,253.27 | 2,683.47 | 102.50 | 15,039.24 | 6,615.76 | **21,655.00** | 10,841.58 | 10,813.42 |
| 12 | 13,942.49 | 3,053.41 | 6,368.60 | 23,364.50 | 10,278.04 | **33,642.54** | 25,373.65 | 8,268.89 |
| **year** | **147,310.09** | **32,260.91** | **181,880.88** | **361,451.88** | **159,002.68** | **520,454.56** | **579,240.87** | **(58,786.31)** |

### Last Tactical Mile

| month | labour | fringe | non-labour | MTDC | indirect @ 43.99% | **restated** | as billed | movement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 | 3,586.34 | 785.41 | 8,500.00 | 12,871.75 | 5,662.28 | **18,534.03** | 18,993.52 | (459.49) |
| 02 | 4,407.25 | 965.19 | 29,603.25 | 34,975.69 | 15,385.81 | **50,361.50** | 66,893.52 | (16,532.02) |
| 03 | 4,764.06 | 1,043.33 | 38,364.93 | 44,172.32 | 19,431.40 | **63,603.72** | 18,993.52 | 44,610.20 |
| 04 | 4,369.54 | 956.93 | 15,190.41 | 20,516.88 | 9,025.38 | **29,542.26** | 18,993.52 | 10,548.74 |
| 05 | 3,617.26 | 792.18 | 8,387.50 | 12,796.94 | 5,629.37 | **18,426.31** | 18,993.52 | (567.21) |
| 06 | 4,470.20 | 978.97 | 13,575.61 | 19,024.78 | 8,369.00 | **27,393.78** | 18,993.52 | 8,400.26 |
| 07 | 4,978.90 | 1,090.38 | 33,898.04 | 39,967.32 | 17,581.63 | **57,548.95** | 63,493.52 | (5,944.57) |
| 08 | 4,861.80 | 1,064.73 | 14,000.00 | 19,926.53 | 8,765.68 | **28,692.21** | 18,993.52 | 9,698.69 |
| 09 | 5,183.26 | 1,135.13 | 13,500.00 | 19,818.39 | 8,718.11 | **28,536.50** | 18,993.52 | 9,542.98 |
| 10 | 4,792.19 | 1,049.49 | 48,284.33 | 54,126.01 | 23,810.03 | **77,936.04** | 66,893.52 | 11,042.52 |
| 11 | 3,663.40 | 802.29 | 10,080.00 | 14,545.69 | 6,398.65 | **20,944.34** | 18,993.52 | 1,950.82 |
| 12 | 3,913.67 | 857.09 | 33,000.00 | 37,770.76 | 16,615.36 | **54,386.12** | 18,993.52 | 35,392.60 |
| **year** | **52,607.87** | **11,521.12** | **266,384.07** | **330,513.06** | **145,392.70** | **475,905.76** | **368,222.24** | **107,683.52** |

### Hybrid Phase 2

| month | labour | fringe | non-labour | MTDC | indirect @ 43.99% | **restated** | as billed | movement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 | 7,328.34 | 1,604.91 | 1,666.66 | 10,599.91 | 4,662.90 | **15,262.81** | 20,835.13 | (5,572.32) |
| 02 | 5,792.83 | 1,268.63 | 1,666.66 | 8,728.12 | 3,839.50 | **12,567.62** | 20,835.13 | (8,267.51) |
| 03 | 5,091.88 | 1,115.12 | 1,666.66 | 7,873.66 | 3,463.62 | **11,337.28** | 20,835.13 | (9,497.85) |
| 04 | 4,095.94 | 897.01 | 1,666.66 | 6,659.61 | 2,929.56 | **9,589.17** | 20,835.13 | (11,245.96) |
| 05 | 5,178.53 | 1,134.10 | 1,666.66 | 7,979.29 | 3,510.09 | **11,489.38** | 20,835.13 | (9,345.75) |
| 06 | 5,084.55 | 1,113.52 | 1,666.66 | 7,864.73 | 3,459.70 | **11,324.43** | 20,835.13 | (9,510.70) |
| 07 | 6,235.96 | 1,365.67 | 1,666.66 | 9,268.29 | 4,077.12 | **13,345.41** | 20,835.13 | (7,489.72) |
| 08 | 6,455.42 | 1,413.74 | 1,666.66 | 9,535.82 | 4,194.81 | **13,730.63** | 20,835.13 | (7,104.50) |
| 09 | 7,395.88 | 1,619.70 | 1,666.82 | 10,682.40 | 4,699.19 | **15,381.59** | 20,735.01 | (5,353.42) |
| 10 | 2,353.43 | 515.40 | 0.00 | 2,868.83 | 1,262.00 | **4,130.83** | 1,474.00 | 2,656.83 |
| 11 | 3,109.75 | 681.03 | 0.00 | 3,790.78 | 1,667.56 | **5,458.34** | 1,374.00 | 4,084.34 |
| 12 | 4,870.13 | 1,066.56 | 0.00 | 5,936.69 | 2,611.55 | **8,548.24** | 1,374.00 | 7,174.24 |
| **year** | **62,992.64** | **13,795.39** | **15,000.10** | **91,788.13** | **40,377.60** | **132,165.73** | **191,638.05** | **(59,472.32)** |

---

## 5. What each restated invoice carries, and why

Four lines, and every one of them is read from a row rather than computed
here — the review-screen rule, for the same reason: a figure derived twice is
one that can disagree with itself.

| line | source |
| --- | --- |
| **Labor** | the month's wages for the objective, `labor_month` over `v_labor_effective`, at cost |
| **Fringe** | 21.90%, the rate on the record, spread by largest remainder |
| **ODC's** | the direct non-labour classified to the objective, by transaction date, **one line** |
| **Indirects** | the engine's own `allocation.allocated`, distributed across the months by MTDC |

**The indirect is the allocation the rate computation persisted, distributed —
not a rate re-applied to a base rebuilt in this script.** A second derivation
would be free to disagree with the first, and the twelve months would no
longer add back to the workpaper.

**Labour is at cost, and that is the whole restatement.** The original billed
labour at a loaded rate, so the indirect recovery is already inside it. Adding
an indirect line to the labour *as billed* would claim indirect twice — the
mistake the first three documents in this sequence were heading towards.

**The non-labour is one line because the split is not on the cost record.**
The ledger carries `Grant Expenses:LTM Grant` and `Humtown Products`, not
MATERIALS or CONSULTANT. Guessing the category from a payee name would be
inventing a judgment. It is on the invoice face, in the caveats, and in the
workbook, because "we could not tell" is more use to a reviewer than a
plausible guess — and it is precisely the column Monday's export supplies.

**The rate is in the description, not in the RATE column.** That column formats
to the cent, so 21.90% printed as `0.22` and 43.99% as `0.44` — a figure that
reads as twenty-two cents on a document a payables clerk checks. Found by
reading a rendered PDF back with `pypdf`, not by reasoning about it.

---

## 6. What these figures rest on, stated above them

- **No 200.465 facilities carve-out has been evaluated.** No building on the
  record carries square footage, so every dollar of tenant and vacant
  occupancy cost is in the federal pool and 43.99% reads high. At a
  provisional 20% tenant share the combined rate is 37.67%, and every restated
  total here falls. **Do not issue anything before the square footage
  arrives** — restating at 43.99% and then discovering 37.67% means
  over-claiming on a rate YBI proposed itself.
- **0 of 43 people have certified their 2025 effort** under 2 CFR 200.430(i).
  Every restated labour line is the management reconstruction at 100%, and
  restating *raises* the reliance on it, because labour becomes the audited
  cost rather than a rate.
- **$92,876.19 of Drive AM non-labour is unreconciled.** Drive AM billed that
  much more in ODCs than the ledger classifies as Drive AM cost. Either the
  classification under-attributes or the billing over-claimed, and it sits
  underneath the largest credit in the set.
- **Administrative labour is in the G&A pool** (`admin_labour = POOL`) and
  **5227 portfolio consulting is in the base as contractor cost** under
  200.331. Both were settled by instruction; see
  `WP_AM_RESTATEMENT_IF_ACCEPTED.md` and the rejected two-tier alternative in
  its appendix.
- **Hybrid's `bill_to_name` in the register is `236 W Boardman Street`** — an
  address in the name field, a transcription artefact from the original load.
  The rendered restatements bill NCDMM, like the other two. The register
  should be corrected at source.

---

## 7. One sentence

*The year's restatement is a net give-back of $10,575.11 and stands; the
thirty-six monthly documents exist so that figure can be traced back to the
month and the person it came from, not so thirty-six transactions can be
issued — and what Monday's export has to settle is the category split of the
non-labour and whether thirty-six is the right count.*
