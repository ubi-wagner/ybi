# Project context

Everything established in analysis before the build, so it travels with the code
rather than living in a chat log. Read alongside `CLAUDE.md` (conventions) and
`ARCHITECTURE.md` (design decisions).

**Not legal or audit advice.** Several items below have potential mandatory
disclosure implications under 2 CFR 200.113 and belong with counsel.

---

## 1. The engagement

Youngstown Business Incubator, a nonprofit running federal awards as a
subrecipient. Four objectives, and they are **not one project** — different
clocks, different risk:

| | Real deadline | Blocked on |
|---|---|---|
| 2025 Form 990 functional allocation | November 2026, hard | nothing missing |
| Indirect rate proposal | 2026, negotiable | square footage, asset register |
| America Makes true-up | when the evidence is in | invoices, cost proposal |
| Chart conversion and system | 1 Jan 2026 | decisions, not data |

**The 990 does not need the rate.** Part IX wants Program / Management &
General / Fundraising. It needs the classification pass with the 990 dimension
filled in — nothing else. Decoupling it is the single biggest risk reduction
available.

Cast: Eric Wagner (engagement), Tom Metzinger (controller, 1099, prepares the
allocation), Barb Ewing (CEO, signed the awards).

---

## 2. What is verified

All recomputed from source, not taken from anyone's summary.

### Ledger controls — every one ties

| Control | Amount |
|---|---:|
| GL rows | 15,500 |
| Income | 6,662,593.00 |
| COGS | 37,261.00 |
| Expenses | 6,737,951.18 |
| Other income | 116,948.46 |
| Net income | 4,329.28 |
| Wages | 1,789,993.94 |
| Fringe pool | 401,783.60 |
| Depreciation | 850,382.89 |
| Rental revenue | 638,862.21 |

Structural integrity is clean: 4,020 cost rows + 1,076 revenue rows = 5,096 =
exactly the P&L-scoped GL row count. No duplicate source keys. Calendar year.

**This reconciliation is good work and it is the foundation everything else
assumes.**

### Labor

The controller's `GRANT_RECON_BOOK` carries employee × objective wage
distribution across 20 objectives.

- Time Breakdown totals **1,834,993.97**; GL wage control **1,789,993.94**.
  The 45,000.03 difference is a non-payroll credit in the wage account
  (payee "Vince and Phyllis Bacon"). Scale factor **0.975477**.
- **Two populations.** 8 employees with month-by-month timesheets
  (819,540 / 44.7%); 36 with a single-row percentage assertion
  (1,015,507 / 55.3%).
- **Federal labor is 100% timesheet-backed.** MBAC 2%, ESP 29%, G&A 25%.
  The strong evidence sits exactly where it will be tested first — lead with
  this in every conversation.
- **Four people carry 80% of federal labor** — Gaffney, Longo, Engel, Negro.
  All four already keep timesheets. The certification critical path is ~7
  people, not 45.
- Fringe **22.45%**, matching the controller's own Reference Sheet exactly.
- 2025 timesheet hours 31,460.5 against 29,397.0 allowable. The controller's
  proportional scaling **is total time accounting** and is the correct method —
  algebraically identical to the effective-rate approach. It also lands
  conservatively: federal is 30.5% of all hours but only 26.4% of hours in
  over-logged months.

### Management certification is the real distortion

The CEO certifies **14%** to general administration; a program director
spread across six programs certifies **0%**. Four staff certify 100% to a
single program with no time record (265,974 of wages). Fundraising is 3.0% of
hours for an organisation running Shark Tank, AMUX and EmpowerUS.

Management time is being attributed to whichever program it touched rather
than to G&A. Correcting it **raises** the rate — the mess was understating it.

---

## 3. The recommended model

Assumptions: labor properly verified and certified; facilities **40%**
allocable.

| | |
|---|---:|
| Wages recertified into G&A | 188,889 |
| Wages recertified into facilities | 18,738 |
| Wages recertified into fundraising | 19,037 |
| G&A pool | 846,743 |
| Facilities gross 1,445,047 × 40% | 578,019 |
| Direct base (MTDC) | 4,483,492 |

| Rate | |
|---|---:|
| **Fringe** on salaries and wages | **22.45%** |
| Facilities on MTDC | 12.89% |
| G&A on MTDC | 18.89% |
| **Combined indirect** on MTDC | **31.78%** |

Certification assumptions worth defending: CEO 50% G&A / 15% fundraising /
10% facilities; program director 30% G&A; timesheet staff 5% general floor;
single-assertion staff 10%.

**Propose 31.78%, expect to settle 28–30%.**

### Sensitivity — what actually moves it

| | Rate |
|---|---:|
| Baseline | 31.78% |
| Facilities at 30% instead of 40% | 28.55% |
| 25% of depreciable basis federally funded | 29.88% |
| **Portfolio consulting → direct** | **28.09%** |
| **Portfolio consulting → G&A** | **44.90%** |

`5227 Portfolio consulting` — 588,539 across 442 lines — swings the rate **17
points** and is double-acting (grows the pool, shrinks the base). It is the
largest lever in the model and, unlike the facilities and depreciation
questions, needs no external document. Sequence it first.

### The go-forward number

$100 of direct labor → **$161.36 fully burdened** (vs $134.69 at de minimis).
A **19.8% uplift on every labor dollar** in every 2026 proposal. That is the
recurring value; the 2025 recovery figure is not.

---

## 4. America Makes — unresolved, and the numbers moved

### The contract (Hybrid Phase 2, executed 8 Sep 2023)

Cost reimbursement, **no fee**. Ceiling **$500,043** federal + **$104,000**
cost share. Term ended **10 October 2025**. Prime AFRL FA8650-20-2-5700.

Schedule B budget: LABOR 449,043 · TRAVEL 4,500 · CONSULTANT 40,000 · ODC
6,500. **There is no indirect line anywhere in the approved budget.**

The two PDFs supplied as Phase 2 and Phase 3 are **byte-identical**. No Phase 3
agreement is in evidence.

### The billing method explains everything

They invoiced **budget ÷ 12**. 25,373.65 × 12 = 304,483.80, exactly the 2025
Drive AM billing; 7,493.52 × 12 = 89,922.24, exactly LTM.

One method, two opposite errors:

- **Hybrid** spent 48% of its labor budget and invoiced 105% of it → over-billed.
- **Drive AM / LTM** — a budget twelfth cannot see actual non-labor spend, so
  181,881 and 266,384 of 2025 GL direct never entered an invoice → under-billed.

The 12,466 ceiling breach is an arithmetic consequence of drawing twelfths past
the term, not a decision anyone made.

### 2025 portfolio at the recommended model

| Award | MTDC | Indirect | Claimable |
|---|---:|---:|---:|
| Drive AM | 340,215 | 108,120 | 448,335 |
| Digital Engineering | 199,763 | 63,485 | 263,248 |
| Last Tactical Mile | 323,042 | 102,663 | 425,705 |
| Hybrid II | 74,991 | 23,832 | 98,823 |
| NCDMM unsegmented | 8,516 | 2,706 | 11,223 |
| **Total** | **946,527** | **300,806** | **1,247,334** |

### Counterparty posture — updated, and it changes the strategy

**America Makes is friendly and will allow restated rates applied
retroactively to prior invoices, provided the restated total stays under the
contracted total.**

This supersedes the earlier assumption that upward amendments on expired awards
were impractical. The exercise becomes a **ceiling-constrained restatement**:
per award, restate at the defensible rate, cap at the ceiling, and the sign of
the delta decides between a collectible amended invoice and a credit. It also
makes the 200.332 pass-through rate negotiation a live path — NCDMM can
negotiate the rate directly, with no federal cognizant agency required.

Two consequences for the engine. The ceiling test moves from a pass/fail
constraint to the **binding parameter of an optimisation**. And the ceilings for
Drive AM, Last Tactical Mile and Digital Engineering are now Tier 1 intake —
only Hybrid Phase 2's $500,043 is currently known.

The "forgo the upside" decision recorded in section 6 was made under the old
assumption and should be revisited.

### The open question that stops everything

**Two different "billed" numbers, $1,578,980 apart.**

| Award | Claimable | Tab invoices | Delta | Revenue recognised | Delta |
|---|---:|---:|---:|---:|---:|
| Drive AM | 448,335 | 304,484 | +143,851 | 579,241 | −130,906 |
| Digital Engineering | 263,248 | not tracked | — | 579,074 | −315,826 |
| Last Tactical Mile | 425,705 | 89,922 | +335,783 | 368,222 | +57,482 |
| Hybrid II | 98,823 | 191,738 | −92,915 | 187,416 | −88,593 |
| NCDMM unsegmented | 11,223 | not tracked | — | 451,170 | −439,948 |
| **Total** | **1,247,334** | **586,144** | **+386,719** | **2,165,124** | **−917,790** |

The grant tabs appear to track **labor invoicing only**; other invoice lines
went out separately and never entered the reconciliation. If so the portfolio is
materially worse than the tab basis suggested, and **Digital Engineering —
never reconciled at all — becomes the largest single exposure at −315,826.**

**No amended invoice package can be built until the actual submitted invoices
are in hand.**

Hybrid survives either basis: over-billed ~90K in 2025, **178,269 life-of-award**
at 31.78%, with 12,466 above the ceiling at any rate.

---

## 5. Open items

Ordered by what they unblock.

| # | Item | Blocks | Owner |
|---|---|---|---|
| 1 | **Submitted invoices, all four awards** | the entire true-up | Controller |
| 2 | **Hybrid Phase 2 Technical/Cost Proposal** | whether loaded rates were approved | CEO |
| 3 | **Phase 3 agreement**, if it exists | ceiling and post-term billing | CEO |
| 4 | `5227 Portfolio consulting` classification | 17 points of rate | Controller |
| 5 | Square-footage schedule by tenant and function | facilities carve-out | Controller |
| 6 | Asset register with funding source per asset | 200.436(b) depreciation | Controller |
| 7 | `LTM Grant` / `Drive AM` account contents | subaward MTDC cap; 266,384 swing | Controller |
| 8 | Rising Tides federal determination | SEFA, Single Audit scope | CEO |
| 9 | $104,000 Hybrid cost share | 200.306 exposure | Controller |
| 10 | $451,170 unsegmented NCDMM revenue | award-level attribution | Controller |

### Also live

- **Single Audit territory.** Federal expenditures ≈ 1.6M excluding Rising
  Tides, ≈ 2.3M including, against a 1,000,000 threshold. Indirect rate and
  cost share are both tested compliance requirements.
- **Post-term billing** continued through June 2026 (10,992). Stop immediately
  if anything is still going out.
- **Records retention** — §4.6.1, three years past the calendar year. 2023
  records must survive through end of 2026.
- **Double-count risk.** The controller's 1099 fee is direct-charged to Hybrid
  and Rising Tides while accounting sits in the G&A pool — 200.403(d), plus an
  independence question since he prepares the allocation.
- **The systemic finding.** No time system, no cost share tracking, no rate, a
  chart that cannot support allocation, and budget-draw billing on
  cost-reimbursement instruments. An auditor writes this as **2 CFR 200.302,
  inadequate financial management system.** Self-identification and a
  remediation already underway is worth a great deal here.

---

## 6. Decisions taken

- **Postgres + Python + React, monolith on Railway.** Invariants enforced in
  the schema, not asserted in application code.
- **Sealed decision sets.** Classifications hash and freeze before any rate is
  computed; the rate carries the seal. A trigger enforces it.
- **Four orthogonal dimensions** — pool, 990 function, federal treatment,
  objective. One enum cannot serve both Part IX and Subpart E.
- **Unclassified is never defaulted into a pool.** The rate reads high while
  work is unfinished, which is the honest direction to err.
- **Forgo the upside, correct the downside.** Drive AM and LTM get a documented
  statement of unrecovered cost, not an invoice. Hybrid gets a credit. There is
  no netting across awards, and NCDMM cannot net either — expect a payment out,
  not a receipt.
- **2026 chart encodes the pool in the account number**, so classification
  becomes arithmetic. Funded asset basis segregated at 1511/1512; tenant cost to
  the 93xx pool. Crosswalk ties all 85 accounts to 6,775,212.18, variance 0.00,
  24 splits flagged as needing a driver.

---

## 7. Incoming, and what each unlocks

| Document | Unlocks |
|---|---|
| **Profit & Loss** | Control totals read from source rather than a seeded CSV. `build_control_register()` already parses this shape. |
| **Balance Sheet** | Asset basis and funding source → the 200.436(b) depreciation carve-out and the last open rate variable. Also the debt behind 49,001 of interest, which may be allowable under 200.449 rather than unallowable. |
| **Example invoices** | The 1,578,980 gap. What was actually claimed, line by line, versus what the tabs record. Determines whether the portfolio is +387K or −918K, and whether loaded rates were used. **The highest-value document in the engagement.** |

When the invoices land, check three things: whether non-labor lines were billed
separately from labor, whether any invoice carries an indirect or loaded-rate
line, and whether Digital Engineering was invoiced on the same budget-twelfth
basis as the others.

---

## 8. The 11 September document drop — seven new source documents

Seven documents arrived at once, two of them the ones that had been blocking
controls. All are filed under `docs/source-documents/` and named in
`scripts/seed_documents.py`. Two more were duplicates of what was already on
file (a second copy of Hybrid Phase 2, and the ICAM agreement twice) and were
not filed twice — the upload route is content-addressed and would have
deduplicated them anyway.

### 8.1 A third federal award nobody has been costing — ICAM Digital Engineering

`2024-02-05_NCDMM_SubRecipient_Agreement_SRA-0350_ICAM-Digital-Engineering.pdf`

| | |
|---|---|
| Prime | Grant **N00174-20-1-0031**, **CFDA 12.300**, NSWC Indian Head via Energetics Technology Center, administered by NCDMM |
| Type | Cost reimbursement, **no fee** |
| Value | **$1,000,690.00**, fully funded |
| Period | Date of award through **9 July 2025** — inside the period under review |
| Executed | 5 February 2024 (NCDMM), 2 February 2024 (YBI — Stephanie Gaffney) |
| Basis of estimate | YBI cost proposal *Digital Engineering*, 3 Nov 2023, Attachment 3 |

**The indirect provision is the finding.** Attachment 3 budgets:

| | |
|---|---|
| Labor | 655,190 |
| Travel | 35,000 |
| Materials | 8,000 |
| ODCs | 275,000 |
| **Indirects on ODCs (10%)** | **27,500** |
| **Total** | **1,000,690** |

Indirect is charged at 10% **of ODCs only**. The $655,190 of labor carries no
indirect at all. That is not the de minimis rate — 2 CFR 200.414(f) applies
10% to **MTDC**, which here would be roughly $973,190 and would recover about
**$97,319**. The award as budgeted recovers **$27,500**, a shortfall of
roughly **$70,000 on this award alone**, before any fully-burdened rate is
considered. This is a different and worse position than the Last Tactical
Mile de minimis question, because it is not a rate dispute — it is a base
that excludes the largest cost element.

Three consequences to work, in order:

1. **SEFA and Single Audit scope.** CFDA 12.300 is federal. §53 of the
   agreement flows down the $750,000 single-audit threshold. Whether this
   award is on the 2025 SEFA needs checking against the objective master —
   the same question already open on Rising Tides.
2. **Restatement scope.** §4.4-equivalent modification authority exists here
   too (§14 Changes, §12 requiring written modification signed by both
   contractual representatives). Any change of basis needs that instrument,
   exactly as `POST /api/restate` requires.
3. **§54** requires that YBI has "settled all years overheads with their
   cognizant agency" before final fee release, and certifies the accounting
   system complies with DFARS 252.242.7006. YBI has no NICRA. That sentence
   is worth a legal read before it becomes a closeout problem.

### 8.2 Hybrid Modification 001 — the $104,000 cost share is now live in 2026

`2026-01-22_NCDMM_Hybrid_20240061_Modification-001.pdf`

Effective 22 January 2026. Extends the period of performance to **30 June
2026** and raises the total obligation by **$12,366 to $512,409**. NCDMM
numbers the agreement **20240061**; the amounts it restates ($500,043 federal,
$104,000 cost share) match §4.2 of the 8 September 2023 agreement exactly, so
it is a modification of that document rather than a separate award.

**The $104,000 cost share is carried forward unchanged.** The open item
recorded as "obligated, never tracked" is therefore not a closed historical
question — it is an obligation live in a second fiscal year, on an award whose
statement of work expects the ratio of America Makes funding to cost share to
be "roughly 1:1 at all times throughout the project", with cost share reports
due monthly by the 10th. Nothing in the ledger tracks it.

### 8.3 The asset register — arrived, and it does not answer 200.436(b)

`2026_YBI_Fixed-Asset-Schedule.xls`

| | |
|---|---|
| Cost / other basis | **23,419,573.64** |
| Accumulated depreciation | **10,452,995.43** |
| Net book value | **12,966,578.21** |

Per asset it carries system number, description, date in service, method and
convention, life, cost, beginning accumulated depreciation, current-year
depreciation and remaining basis. That is enough to rebuild depreciation from
source and to close the `ASSET_REGISTER` control.

**It carries no funding source column.** The one field 200.436(b) turns on is
the one field not in the register. It has to be reconstructed by matching
asset additions to the award documents in §8.4 — real work, not a lookup.

**A second problem, and it is structural.** The register's account numbering
collides with the 2026 chart. `app/domain/chart.py` reserves **1511/1512** for
*funded* asset basis, precisely so the depreciation question is answered by
the account. The register uses 1511/1512 for **Building and Semple Building**
($8,760,612.01 of cost) and 1501/1502 for **Tech Block Building 5**
($8,935,270.34). Those are two different meanings for the same account
numbers. One of them has to give before the 2026 chart goes live, and the
carve-out that was supposed to be "answered by the account" is not answered
yet.

### 8.4 Where the building money came from — two awards, one federal

| Document | | |
|---|---|---|
| `2021-07-13_EDA_CD-450_Award_06-79-06300.pdf` | EDA, Dept of Commerce | **A scan with no text layer. Needs OCR before anything can be read out of it.** |
| `2025-11-17_EDA_Closeout-Letter_06-79-06300.pdf` | EDA closeout, signed 17 Nov 2025 | Final project cost **2,376,344**; EDA share **1,903,179**; disbursed **1,712,861**; **188,214.54 still to be drawn** |
| `2022-02-02_JobsOhio_Grant-Agreement_SFPN-2021-493762-VCG.pdf` | JobsOhio, **not federal** | **475,000** toward **2,428,974** of project investment, including **2,092,861 of building fixed assets**; ~18,000 sq ft renovated at 252 W Boardman |

Together these are the funding-source evidence the register lacks. The EDA
share is federal, so depreciation on the assets it funded is unallowable under
200.436(b); the JobsOhio share is not, so depreciation on that basis is
allowable. Splitting the building additions between them is the remaining
work.

Two things to check that do not depend on that split:

- **The 188,214.54 receivable.** Is it on the 2025 balance sheet? A closeout
  letter dated 17 November 2025 naming a balance still to be disbursed is a
  2025 receivable, and the eleven cross-reference points would not catch its
  absence.
- **Records retention runs three years from 17 November 2025**, and GPRA
  performance reports are due at three, six and nine years from **24 June
  2021**. Both are calendar items, not accounting ones.

### 8.5 The lease schedule — the tenant side of the carve-out

`2025_YBI_Lease-Schedule.xlsx` — 26 leases across four buildings (ybi, TBB5,
AM, Taft/Semple) with start, end, monthly and annual rent. Largest: Steelite
across three spaces (203,116 + 49,527 + 33,966 = **286,608/yr**), Juggerbot 3D
(62,227), and **NCDMM America Makes — 108,000/yr on the AM building through 30
September 2025, plus 18,720/yr at ybi from February 2025**.

That last one needs care. YBI is landlord to the organisation that administers
three of its federal awards. It is not a 200.465 less-than-arm's-length
problem on its face — that provision is about YBI *paying* rent to a related
party — but rental income from a funder, on space that may also carry
federally funded depreciation, is exactly the kind of arrangement a Single
Audit asks about. It should be documented deliberately rather than discovered.

**Square footage is still missing**, and it is the driver the carve-out
actually needs. The schedule gives rent, not area. The JobsOhio agreement's
"approximately 18,000 square feet" is the only area figure in the file and it
describes a renovation, not an occupancy.

### 8.6 What this drop did not change

The fringe question is untouched: 21.90% remains the defensible figure and
22.45% remains a rate computed on a wage base a $45,000 donor credit was
netted out of. Nothing here bears on the Bacon reclassification, which is
still a QuickBooks entry Tom has to make.

---

## 9. The Last Tactical Mile ceiling, and what it does to the cost share

Asked why two contracts carried no ceiling. One answer was right and one was
not.

**Last Tactical Mile was wrong.** The executed agreement has been on file
since the September drop and nobody had read §4.3 into the record:

> The total funds authorized by this agreement shall not exceed **$899,500 in
> federal funding and $513,065 cost share**.

Project total $1,412,565 over a 27-month period of performance from
24 September 2024. The award row had carried a ceiling of zero with the
citation "Ceiling not yet transcribed from the agreement" — honest about
being a placeholder, and a placeholder that had gone quiet.

**Drive AM is right.** There is no executed agreement on file for it. What
`PROJECT_CONTEXT` carries — 448,335 — is what was *invoiced* against it, and
billing tells you what was claimed, never what the contract would bear. It
stays at "not on file" until somebody produces the agreement, and that is the
correct state rather than a gap to fill with the billing figure.

### The cost share exposure is six times what was recorded

| Award | Cost share obligated | Tracked |
|---|---:|---|
| Hybrid Phase 2 | 104,000 | never |
| Last Tactical Mile | **513,065** | never |
| **Total** | **617,065** | |

Of the LTM 513,065, the proposal's cover tables put **YBI's own share at
213,037**; the balance is pledged by the University of Northern Iowa and the
industry partners named in the proposal. YBI does not incur the partner
portion but is obliged to evidence it, which is its own kind of exposure — a
cost share nobody collected evidence for is a cost share the sponsor can
disallow, and the shortfall lands on the prime.

The partner figures I could extract total roughly 279,069 against a stated
513,065 less YBI's 213,037, leaving about 21,000 unaccounted between the
cover table and the partner detail. That is a transcription question for the
controller against the signed document, not something to reconcile by
inference.

**This is now the largest untracked obligation in the engagement**, ahead of
the 5227 Portfolio consulting judgment. It has been recorded on the contract
with its clause, so the next person to ask reads it off the screen.
