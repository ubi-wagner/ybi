# Indirect Cost Rate Framework for YBI

**2 CFR 200 and DCAA/FAR rules on indirect cost buildup, and the allowability of
restating prior-period rates away from the de minimis election**

| | |
|---|---|
| Entity | The Youngstown Edison Incubator Corporation, dba Youngstown Business Incubator ("YBI") |
| UEI / CAGE | E38PN6F4AVU3 / 5EAR9 |
| Fiscal year | Calendar year |
| Prepared | September 2026 |
| Status | Working analysis. Not an indirect cost proposal. Not legal or accounting advice. |

This document establishes the regulatory framework for the FY2025 indirect cost
rate build. It is written to be read alongside the source documents committed in
`docs/source-documents/`. Where a conclusion depends on a document YBI has not yet
produced, that is stated explicitly rather than assumed.

---

## 1. Which rules actually govern

This matters more than it might appear, because the two bodies of rules give
different answers to the retroactive question.

**2 CFR Part 200 (Uniform Guidance) governs.** Both America Makes agreements are
sub-recipient agreements under a Department of the Air Force **cooperative
agreement** — FA8650-20-2-5700, Assistance Listing 12.800 — administered by the
National Center for Defense Manufacturing and Machining ("NCDMM"). A cooperative
agreement is federal financial assistance, not a procurement contract. Schedule C
§1.04 of each agreement flows the cost principles down explicitly:

> "Sub-recipient(s) shall comply with the cost principles as contained in 2 CFR
> 200, Subpart E, Cost Principles."

Schedule C §1.00 further incorporates the DoD interim implementation at **2 CFR
Part 1103** and Chapter I, Subchapter C of Title 32 CFR.

**FAR Part 31 and the Cost Accounting Standards do not directly apply.** YBI is
not a contractor here and holds no CAS-covered contract. DCAA has no independent
audit right over YBI under these agreements; §4.6.2 gives audit access to "a
Government auditor, or a certified public accountant," which is broader than DCAA
but is exercised through NCDMM or the Government, not by DCAA on its own motion.

**Why DCAA/FAR still matters in practice.** Three reasons, and they are not
academic:

1. DoD is the ultimate funding source. NCDMM is itself subject to federal audit,
   and the concepts its program and finance staff apply are FAR-flavored.
2. FAR Part 42's provisional-rate/final-rate machinery is the most developed body
   of practice on exactly the question YBI is asking, and it is the vocabulary a
   DoD reviewer will use.
3. If YBI ever takes a DoD **contract** rather than a subaward — and organizations
   on this trajectory usually do — FAR 31.2, CAS and the DFARS accounting system
   criteria become binding. Building the FY2025 system to that standard costs
   little more now and avoids a rebuild later.

The correct posture: **comply with 2 CFR 200; design to DCAA standards.**

---

## 2. Entity and award facts

### 2.1 The America Makes agreements

| | Hybrid Phase 2 | Project 88 / "Last Tactical Mile" |
|---|---|---|
| Agreement date | 2023-09-08 | 2024-09-24 |
| Term ends | **2025-10-10** | 2026-12-23 |
| Instrument | Cost Reimbursement, No Fee | Cost Reimbursement, No Fee |
| Federal ceiling | $500,043 | $899,500 |
| Cost share | $104,000 | $513,065 |
| Prime | AFRL FA8650-20-2-5700 (ALN 12.800) | same |
| Schedule B | Incorporated by reference — **not yet produced** | Detailed budget in the agreement |

A third NCDMM agreement is evidenced by the FY2024 SEFA (grant N00174-20-1-0031,
ALN 12.300, $421,616 expended) but has not yet been produced.

### 2.2 Project 88 budget as executed

```
FEDERAL
  Labor                          212,326.00
  Consultant                     605,402.00
  Direct cost base               817,728.00
  Indirects                       81,772.76   = exactly 10.000% of base
  Total federal                  899,500.76

COST SHARE
  Consultant                     279,522.00
  Unrecovered indirects          233,543.12
  Total cost share               513,065.12
```

Two derived figures drive much of what follows:

- Total indirect contemplated = $81,772.76 + $233,543.12 = **$315,315.88**
- Implied total indirect rate = $315,315.88 / $817,728 = **38.56%**

The cover-page partner table does not tie to Schedule B. Partner cost share sums
to $279,069 against a $279,522 consultant cost-share line (−$453), and the lead
organization line of $213,037 does not tie to the $233,543.12 unrecovered
indirect line (−$20,506). Total variance $20,959. This should be reconciled
before the figures are used in any submission.

### 2.3 Federal award volume and audit history

| | FY2023 | FY2024 |
|---|---|---|
| Total federal expenditures (SEFA) | $1,012,543 | $4,114,007 |
| DoD via NCDMM | $238,004 | $1,068,732 |
| Largest **direct** federal award | ARC $463,516 | **Commerce/EDA $1,872,050** |

YBI has been a Single Audit filer since FY2023. FY2024 results:

- **Finding 2024-001 — material weakness.** Federal and state reimbursements on
  capital expenditures were netted against the asset cost, understating grant
  revenue and property and equipment.
- **Finding 2024-002.** The FY2023 Single Audit reporting package was submitted
  late, contrary to 2 CFR 200.512(a)(1).
- **Not a low-risk auditee** (2 CFR 200.520). Consequence: 40% major-program
  coverage rather than 20% under 200.518(f).
- SEFA Note 2 states plainly: *"The Organization has elected to use the 10% de
  minimis indirect cost rate allowed under the Uniform Guidance."*

Finding 2024-001 is directly on the critical path. A netted capital reimbursement
corrupts the gross asset basis, which corrupts depreciation, which is the largest
single swing factor in YBI's indirect pool (§7).

---

## 3. Indirect cost buildup under 2 CFR 200

### 3.1 The governing sections

| Section | Subject | Why it matters here |
|---|---|---|
| 200.402 | Composition of costs | Total cost = direct + allocable indirect, less applicable credits |
| 200.403 | Factors affecting allowability | Necessary, reasonable, **consistently treated**, adequately documented, incurred in the budget period |
| 200.404 | Reasonable costs | Prudent-person standard |
| 200.405 | Allocable costs | Relative-benefit rule; **200.405(c)** bars shifting costs to overcome fund deficiencies |
| 200.406 | Applicable credits | Rental income, rebates, refunds must reduce the pool |
| 200.412 | Classification of costs | No universal rule; treatment must be consistent |
| 200.413 | Direct costs | **200.413(c)** limits direct-charging administrative/clerical salaries |
| 200.414 | Indirect (F&A) costs | Negotiated rates; **200.414(f)** de minimis |
| 200.415 | Required certifications | CFO-signed certification of the proposal |
| 200.430(i) | Personnel expense documentation | The binding constraint on YBI today |
| Appendix IV | Nonprofit indirect cost identification | The methods YBI must choose among |

### 3.2 Allocation methods available to a nonprofit (Appendix IV, § B)

**B.2 Simplified allocation method.** A single indirect pool over a single base.
Appropriate only where the organization's major functions benefit from indirect
costs to approximately the same degree. **YBI does not qualify.** Tenant real
estate operations, state ESP programming, federal R&D subawards, and fundraising
plainly do not benefit equally from occupancy and administration.

**B.3 Multiple allocation base method.** The pool is subdivided into groupings —
typically depreciation, operation and maintenance of plant, and general
administration — each allocated on the base that best measures the benefit
received. Technically the most accurate fit for YBI. Also the most expensive to
build and defend.

**B.4 Direct allocation method.** All costs are treated as direct except general
administration and general expenses. Joint costs — occupancy, telephone,
depreciation — are prorated to benefiting activities on measurable bases such as
square footage, headcount, or usage. **This is the recommended structure for
YBI**, because management has already given the occupancy driver: 50% tenant /
30% program / 20% administrative square footage.

**B.5 Special indirect cost rates.** Where a particular segment of work involves
materially different indirect cost incidence, a separate rate is permitted. Worth
holding in reserve if the America Makes work turns out to carry a very different
facilities profile than ESP.

**Recommendation:** a two-tier structure — a **fringe pool** on a salaries and
wages base, and a **single indirect pool** built by direct allocation on an MTDC
base. Two tiers are defensible by a small finance team. A three-tier
fringe/overhead/G&A structure is more precise and, in an organization that until
now has posted payroll in two lump journal entries per period, will not survive
contact with an auditor.

### 3.3 The base: Modified Total Direct Cost

MTDC is defined at 2 CFR 200.1. It comprises all direct salaries and wages,
applicable fringe benefits, materials and supplies, services, travel, and **up to
the first $25,000 of each subaward** — raised to **$50,000** by the 2024
revisions for awards issued on or after 1 October 2024.

MTDC **excludes** equipment, capital expenditures, charges for patient care,
rental costs, tuition remission, scholarships and fellowships, participant
support costs, and the portion of each subaward exceeding the threshold.

**This is the largest open question in the FY2025 build.** Project 88 applied 10%
to a base of $817,728 that includes $605,402 of "Consultant" cost. If those
partners — which include Ohio State, the University of Northern Iowa, and the
University of Tennessee Knoxville — are **subrecipients** rather than vendors,
MTDC excludes all but the first $25,000 of each, the base collapses, and the
$81,772.76 already billed was **overstated**, not understated.

The FY2024 SEFA reports **$0 passed through to subrecipients** for both DoD
programs, so YBI's audited position is that all partners are contractors. That
position needs to survive a 200.331 determination on each agreement, applying the
substance tests: does the partner determine eligibility, have performance
measured against program objectives, have responsibility for programmatic
decision-making, and carry compliance obligations? Or does it provide goods and
services within its normal business operations to many purchasers in a
competitive environment? Universities performing collaborative research typically
land on the subrecipient side.

**Do this determination first.** It is the one thread in this project that can run
against YBI, and it is better found internally than by an auditor.

### 3.4 Unallowable costs — remove from the pool, keep in the base

The classic error is symmetrical removal. Unallowable costs come **out of the
indirect pool** but generally **stay in the MTDC base**, because they still
consumed administrative effort. Removing them from both inflates the rate and is
a standard audit test.

From the FY2025 P&L:

| Account | Amount | Authority | Treatment |
|---|---:|---|---|
| 5080 Fundraising | $306,484.11 | 200.442 | Unallowable; excluded from pool |
| — of which 5120 Government Relations | $25,000.00 | 200.450 | Lobbying; unallowable, verify nature |
| — of which 5085 Advertising | $125,017.19 | 200.421 | Largely unallowable; narrow exceptions |
| 5400 Bad Debt Expense | $12,037.85 | 200.426 | Unallowable |
| 5250 Meals & Entertainment | $28,426.52 | 200.438 / 200.475 | Split required; entertainment unallowable |
| 5220 Contributions | $1,000.00 | 200.434 | Unallowable |
| 5215 Dues and Subscriptions | $50,134.97 | 200.454 | Review: lobbying-organization memberships unallowable |
| 5310 Interest Expense | $49,000.78 | 200.449 | Conditionally allowable; see §3.5 |
| 5010 Depreciation | $850,382.89 | 200.436 | Federal-share portion unallowable; see §3.5 |

Note also **200.441 fines and penalties** and **200.470 taxes** on review, and
that under FAR 31.201-6 — the discipline worth borrowing — **directly associated
costs** of an unallowable activity are themselves unallowable. The salary of
staff supporting the fundraising function follows the fundraising cost out of the
pool. The controller's Time Breakdown already isolates $40,088.80 of fundraising
labor, which is exactly right.

### 3.5 The two facilities constraints that cap YBI's rate

YBI is, financially, a real estate operation with programs attached. Gross
property and equipment was $22,393,574 at 31 December 2024 against $5,058,740 of
total expenses. Two rules therefore dominate the rate.

**200.436 — depreciation.** Depreciation is allowable, but **not on the portion of
asset cost borne by or donated by the Federal Government**. YBI's asset base is
substantially grant-funded:

- Commerce/EDA Economic Adjustment Assistance — $1,872,050 expended in FY2024
- Appalachian Regional Commission — ~$750,000 direct in FY2024
- A **$3,000,000** Vindicator Building renovation grant, repayable if the building
  is not used for its intended purpose for twenty years after placement in
  service (2017)
- **$1,500,000** from the Ohio Board of Regents via Youngstown State University
  under a twenty-year joint use agreement, with prorated repayment if YSU's right
  of use terminates early

Producing an allowable depreciation figure requires a **fixed asset register
tagged with funding source per asset** — which YBI has not yet produced, and which
Finding 2024-001 tells us is currently misstated. Until that exists, any
depreciation in the pool is an estimate.

**200.465 — rental costs of real property.** Space owned by the entity is charged
at **cost of ownership** — depreciation, maintenance, taxes, insurance — never at
market rent. More importantly here: space whose cost is recovered through tenant
rent **cannot also be loaded into an indirect pool charged to federal awards**.
That would be double recovery, and 200.406 requires the rental receipts to be
treated as an applicable credit against the associated costs.

FY2025 rental income was **$638,862.21**, including a line captioned **"4026 NAMII
Rent Boardman St. — $108,000."** America Makes is simultaneously YBI's pass-through
grantor and its tenant. Separately, YBI expenses roughly $84,320 of Boardman
Street electric and gas. Any occupancy reaching the indirect pool must be net of
tenant-recovered space, which is precisely what the 50% tenant square-footage
exclusion accomplishes.

**200.449 — interest.** Interest on debt incurred to acquire or improve buildings
is allowable for nonprofits under conditions, including that the financing is the
least expensive alternative and the asset is used for the award's purposes. The
$804,134 mortgage is collateralized by "buildings and rent assignments," which
points at the tenant operation and needs review before the associated interest
enters the pool.

### 3.6 Certification

**2 CFR 200.415(a)** requires the indirect cost proposal to carry a certification
signed by the CFO or an individual at an equivalent level, stating that the
proposal was prepared in accordance with the applicable cost principles and that
the costs are allowable.

That signature carries **False Claims Act exposure** (31 U.S.C. 3729). It is the
reason §5 of this document is written the way it is.

---

## 4. The DCAA / FAR framework, and what to borrow from it

Not binding on these agreements. Worth building to anyway.

### 4.1 Cost principles and rate mechanics

| Reference | Subject | 2 CFR 200 analogue |
|---|---|---|
| FAR 31.201-4 | Allocability | 200.405 |
| FAR 31.201-6 | Accounting for unallowable costs; **directly associated costs** | 200.412, no direct equivalent for directly-associated |
| FAR 31.203 | Indirect costs — logical cost groupings, base best linking pool to cost objectives | Appendix IV § B |
| FAR 42.704 | **Billing rates** — provisional, revisable prospectively **or retroactively** by mutual agreement | Appendix IV § C.1 provisional rates |
| FAR 42.705 | **Final indirect cost rates** — proposal due within 6 months of fiscal year end | Appendix IV § C |
| FAR 52.242-4 | Certificate of Final Indirect Costs | 200.415(a) |

### 4.2 Cost Accounting Standards worth internalizing

- **CAS 401 — Consistency in estimating, accumulating and reporting costs.** The
  rate you propose must be the rate you book and the rate you bill.
- **CAS 402 — Consistency in allocating costs incurred for the same purpose.** A
  cost incurred for the same purpose in like circumstances is either always direct
  or always indirect. It cannot be both.

CAS 402 has a live application at YBI. The controller is a 1099 contractor whose
$72,375 in account 5202 Accounting is allocated 64.5% to G&A but also **15.4% each
directly to Hybrid and Rising Tides** and 4.7% to ESP. Accounting and controller
services are classically indirect. Direct-charging them to some awards while
running a G&A pool that contains the same function is a CAS 402 problem in
substance and a **200.403(d)** problem in law:

> "A cost may not be assigned to a Federal award as a direct cost if any other
> cost incurred for the same purpose in like circumstances has been allocated to
> the Federal award as an indirect cost."

Either the controller's grant-specific work is genuinely a distinguishable direct
activity — award-specific invoicing and reporting, documented as such — or it
belongs entirely in G&A. Pick one, document the basis, and apply it uniformly.
The same test applies to every support staff member the tool will let YBI classify
as direct, G&A, or overhead.

### 4.3 DFARS accounting system criteria

**DFARS 252.242-7006** sets out what an acceptable accounting system must do.
Assessed against YBI's FY2025 general ledger as produced, the system currently
fails at least five criteria on its face:

| Criterion | YBI status |
|---|---|
| Proper segregation of direct from indirect costs | **Fail.** No dimension in the GL distinguishes them |
| Identification and accumulation of direct costs by contract | **Partial.** Vendor invoices are coded to sub-accounts (`Grant Expenses:LTM Grant`); labor is not coded at all |
| Logical and consistent method for allocating indirect costs | **Fail.** De minimis election in lieu of a method |
| Accumulation of costs under general ledger control | Pass |
| Timekeeping system identifying employees' labor by cost objective | **Fail.** No timekeeping system of record |
| Labor distribution system charging labor to the appropriate cost objectives | **Fail.** Payroll posts as two lump journal entries per pay period |
| Interim determination of costs charged to a contract | **Fail.** Invoicing is straight-line, not cost-based (§6) |
| Exclusion of unallowable costs from billings | **Fail.** No unallowable cost identification in the chart of accounts |

This table is the specification for the tool.

---

## 5. Can YBI restate prior periods away from the de minimis rate?

This is the question the whole project turns on. The answer is a qualified yes,
with the qualifications doing most of the work.

### 5.1 What the de minimis election is

**2 CFR 200.414(f)** permits any non-federal entity that does not have a current
federally negotiated indirect cost rate to elect a de minimis rate. Under the
pre-2024 text this was **10% of MTDC** and "may be used indefinitely." The 2024
revisions (89 FR 30046, 22 April 2024, effective for awards issued on or after
1 October 2024) raised it to **15% of MTDC** and raised the MTDC subaward
exclusion from $25,000 to $50,000.

Three consequences for YBI:

1. **The election is not irrevocable.** Nothing in 200.414 locks an entity into de
   minimis. An entity may apply for a negotiated rate at any time.
2. **The 15% rate does not reach the two America Makes agreements in hand.** Both
   predate 1 October 2024 (September 2023 and September 2024). It applies to new
   awards and, potentially, to modifications — worth asking NCDMM.
3. **The election is on the audited record.** FY2024 SEFA Note 2 states it
   expressly. Any restatement has to reckon with that.

### 5.2 YBI can pursue a negotiated rate — and has a cognizant agency

An earlier working assumption in this project was that YBI, receiving America
Makes money two levels down from AFRL, might have no cognizant agency and
therefore no path to a negotiated rate. **That is wrong.** The FY2024 SEFA shows
**$1,872,050 direct** from the U.S. Department of Commerce (EDA, ALN 11.307) and
approximately $750,000 direct from the Appalachian Regional Commission.

Under **Appendix IV § C.2(a)**, the cognizant agency for indirect costs is the
federal agency with the largest dollar value of **direct** federal awards. For
FY2024 that is **Commerce**. YBI can submit an indirect cost rate proposal and
negotiate a NICRA. Under **200.414(c)**, a negotiated rate must then be accepted
by all federal awarding agencies unless a statute or regulation provides
otherwise, or the agency head grants an exception.

**The faster route for the America Makes work is 200.332(a)(4).** A pass-through
entity must provide a subrecipient with an indirect cost rate, and the options
are: the subrecipient's federally negotiated rate; **a rate negotiated between the
pass-through entity and the subrecipient**; or the de minimis rate. NCDMM can
therefore agree a rate with YBI without waiting on Commerce. Given that America
Makes is described as friendly and willing to work with YBI, this is the practical
path — pursue both in parallel, with the NICRA as the durable answer.

### 5.3 The rate types that make retroactive adjustment possible

**Appendix IV § C.1** defines four rate types. Two matter here:

- **Provisional rate** — "a temporary indirect cost rate applicable to a specified
  period which is used for funding, interim reimbursement and reporting... pending
  the establishment of a final rate for that period."
- **Final rate** — established after the actual costs of the period are known; not
  subject to later adjustment.

**This is the mechanism.** A period billed under a provisional rate is trued up —
upward or downward — when the final rate for that same period is established.
FAR 42.704(c) is the direct analogue and is more explicit still: billing rates may
be revised **retroactively** by mutual agreement to prevent substantial over- or
underpayment.

Supporting authority on the assistance side: **2 CFR 200.345** provides that the
awarding agency or pass-through entity **"must make upward or downward adjustments
to the Federal share of costs after closeout,"** and preserves the Government's
right to disallow and recover based on later audit. Upward post-closeout
adjustment is expressly contemplated.

### 5.4 Where the argument breaks down

Four obstacles, in ascending order of difficulty.

**(a) YBI did not bill under a provisional rate.** It billed under a de minimis
election. Those are different instruments. A provisional rate is provisional
*because the parties agreed it was pending a final determination*. A de minimis
election is a complete answer to the indirect question at the time it is made.
There is no automatic true-up attached to it.

**(b) Project 88 fixes indirect as a budget line under a ceiling.** Schedule B
states `INDIRECTS 81,772.76`. §4.3 provides that "the total funds authorized by
this agreement shall not exceed $899,500 in federal funding." That is not a rate
awaiting resolution; it is a budgeted dollar amount inside a hard ceiling.
Changing it requires a **written amendment under §4.4**, which contemplates
exactly this: the parties evaluate revised expenses in good faith and "shall amend
the SOW and Budget by written agreement," with arbitration if they cannot agree.

**A higher rate does not raise the ceiling.** It reallocates within it. On
Project 88, more indirect recovery means less room for direct cost unless NCDMM
modifies the award.

**(c) Consistency binds across all funding sources.** Under **200.403(d)** and
**200.412**, a restated allocation method must be applied uniformly — to state ESP
work, to MBAC, to the Hub, to non-federal activity, not only to the federal awards
where recovery improves. The FY2025 labor distribution shows ESP at 30.6% of
wages and MBAC at 15.2%. If YBI's indirect rate rises, those programs must absorb
their share, and the Ohio Department of Development may impose a cap that leaves
the difference unrecovered rather than shiftable.

**(d) 200.405(c) is the provision that will be cited against a reverse-engineered
rate.**

> "Any cost allocable to a particular Federal award... may not be charged to other
> Federal awards to overcome fund deficiencies, to avoid restrictions imposed by
> Federal statutes, regulations, or terms and conditions of the Federal awards, or
> for other reasons."

If the FY2025 rate is derived from the size of the billing gap rather than from
the books, this is the finding. The distinction is not cosmetic and it is not
about intent as YBI understands it internally — it is about the order in which the
work was done and whether the workpapers show it.

### 5.5 Prior years — FY2023 and FY2024

Materially harder than FY2025, for reasons that compound:

- Both years are audited, with SEFAs filed and an explicit de minimis election in
  the notes.
- Reopening them implies an amended SEFA and potentially a reissued Single Audit.
- FY2023 already carries a late-submission finding; FY2024 carries a material
  weakness. Amending those years invites scrutiny of everything else in them.
- The labor records for those years are weaker than FY2025's, which are themselves
  reconstructed.

**Recommendation: do not attempt to restate FY2023 or FY2024.** Build FY2025
forward. Address the two open agreements through modification under §4.4. If a
negotiated rate is later established with a retroactive effective date, prior
years can be revisited from a position of strength rather than as the opening
move.

### 5.6 The sequence that survives audit

Order matters more than any individual step.

1. **Fix labor distribution prospectively.** Timekeeping of record, coded to cost
   objectives, certified by employees and supervisors. This is the material
   control defect and everything else depends on it.
2. **Write the methodology before running the numbers.** Document the allocation
   method, the pools, the bases, the unallowable-cost treatment, and the occupancy
   drivers. Date it. The workpaper trail must show the method was chosen on its
   merits before its effect on the reconciliation was known.
3. **Build the FY2025 proposal from the general ledger.** Reconcile it to the
   audited financial statements — a proposal that does not tie to the F/S is dead
   on arrival.
4. **Resolve the subrecipient/contractor determination** under 200.331 for every
   partner on every agreement, and correct the MTDC base accordingly.
5. **Certify under 200.415(a).**
6. **Negotiate in parallel:** a rate with NCDMM under 200.332(a)(4) for the America
   Makes awards; a NICRA with Commerce as cognizant agency for the durable answer.
7. **Request written budget modifications under §4.4** of each agreement. Nothing
   is re-billed until those are executed.
8. **Disclose proactively** to both the auditor and NCDMM — the billing
   methodology defect in §6 as much as the rate work.
9. **Plan to return what the rate does not absorb.** See §6.

---

## 6. The billing defect is a separate and larger problem

The rate question has absorbed most of the attention. The reconciliation workbook
reveals something more serious.

### 6.1 What the invoices actually did

Sheet `LTM`, row 11, "Billed Labor," reads **$7,493.52 in every month** from
October 2024 through July 2026 without variation, against actual monthly labor
ranging from $3,626 to $9,195.

YBI invoiced a **straight-line monthly budget draw** on a **cost-reimbursement**
agreement.

That is a compliance failure independent of any indirect rate, and it is squarely
contrary to both the agreement and the regulation:

- §4.1: NCDMM "shall... pay to Sub-Recipient the amounts for the invoiced
  **incurred** expenses."
- §4.2: "NCDMM shall reimburse Sub-Recipient for **actual expenses incurred**."
- §4.5.1: each monthly invoice "shall include expenses and cost share for expenses
  **incurred**."
- **2 CFR 200.305(b)** requires payments to be limited to the minimum amounts
  needed and timed to actual immediate cash requirements.

### 6.2 The magnitude

Per the controller's Summary Sheet:

| Grant | Billed | Actual | Difference |
|---|---:|---:|---:|
| Drive AM | $668,909.02 | $506,630.94 | **−$162,278.08** |
| Hybrid | $512,509.12 | $253,639.06 | **−$258,870.06** |
| LTM | $164,857.44 | $142,280.20 | **−$22,577.24** |
| **Total** | | | **−$443,725.38** |

### 6.3 Whether a higher rate closes the gap

Taking each grant's overdraw as a percentage of actual cost — the additional
indirect recovery a restated rate would have to generate on top of the 10% already
billed:

| Grant | Gap as % of actual cost | Closable by a rate restatement? |
|---|---:|---|
| LTM | 15.9% | **Plausibly.** A total rate around 26% closes it |
| Drive AM | 32.0% | **Arguably.** Requires roughly 42%, at the top of the modeled range |
| Hybrid | **102.1%** | **No.** Billed more than double actual cost |

The working expectation that proper rates will convert overbilling into
underbilling is defensible for LTM, arguable for Drive AM, and **wrong for
Hybrid**. No indirect rate recovers a 102% overdraw. Hybrid's term ended
**10 October 2025** and it is in closeout now, which is when **200.344** requires
the final financial report and when **200.345** and **200.346** govern the
recovery of amounts due.

Hybrid also appears to have been billed **above its federal ceiling** — $512,509.12
against $500,043 authorized by §4.3 — though this depends on whether the workbook
figure is cumulative federal or includes cost share. Resolve it before anything
else.

**Plan for repayment on Hybrid.** Treating that as the expected outcome, disclosed
early and voluntarily, is a far better posture than discovering it in fieldwork.

### 6.4 Why this ordering protects the rate work

A legitimate rate proposal that arrives *after* a self-disclosed billing defect and
a voluntary repayment reads as remediation. The same proposal arriving *as the
explanation* for the overdraw reads as 200.405(c). The facts are identical; the
sequence determines the finding.

---

## 7. FY2025 illustrative rate scenarios

Reproducible workpaper: `docs/analysis/workpapers/fy2025_indirect_rate_scenarios.py`

**Illustrative only.** Sizing exercise, not a proposal.

### 7.1 Fringe rate — the one solid number

| | |
|---|---:|
| Employee benefits (5130) | $194,353.59 |
| 401(k) match and profit sharing (5133) | $56,519.42 |
| Payroll taxes (5141) | $150,910.59 |
| **Fringe pool** | **$401,783.60** |
| Salaries and wages base (5139) | $1,789,993.94 |
| **Fringe rate** | **22.45%** |

This ties exactly to the controller's Reference Sheet. It is defensible today.

### 7.2 Labor distribution (Time Breakdown, row 143)

| | Amount | % |
|---|---:|---:|
| Direct / program labor | $1,530,460.28 | 83.40% |
| G&A labor (Adj-YBI) | $264,444.89 | 14.41% |
| Fundraising labor (unallowable) | $40,088.80 | 2.18% |
| **Total per workbook** | **$1,834,993.97** | |
| Total per P&L account 5139 | $1,789,993.94 | |
| **Unreconciled variance** | **$45,000.03** | |

That variance must be resolved before the distribution supports anything.

### 7.3 Scenarios

All apply the management-provided square footage split — 50% tenant (excluded as
recovered through rent), 30% program, 20% administrative — so 50% of facilities
cost is available to the pool. They differ only in the treatment of depreciation
and interest, which is the dominant unknown pending the fixed asset register.

| Scenario | Depreciation in pool | Indirect pool | Rate on broad base | Rate on narrow base |
|---|---|---:|---:|---:|
| **A — Conservative** | None; no interest | $1,545,303 | **35.95%** | 53.84% |
| **B — Midpoint** | 50%; plus interest | $1,782,399 | **41.47%** | 62.10% |
| **C — Upper bound** | 100%; plus interest | $1,994,995 | **46.42%** | 69.50% |

*Broad base* ($4,298,012) treats partner costs as vendor/consultant, fully in
MTDC. *Narrow base* ($2,870,321) treats them as subawards excluded beyond the
per-subaward threshold. The true base lies between, per §3.3.

### 7.4 Reading the result

| Reference point | Rate |
|---|---:|
| Currently elected and audited | 10.00% |
| De minimis available on post-2024-10-01 awards | 15.00% |
| Naive audited proxy — FY2024 M&G / Program Services | 13.63% |
| **Implied by the Project 88 unrecovered indirect cost share** | **38.56%** |
| Modeled range, broad base | **36% – 46%** |

The 38.56% embedded in Project 88's cost share **falls inside the modeled range**.
Whoever computed that figure was working from something real. Finding that
workpaper is a priority — it is either the foundation of the proposal or the thing
that gets questioned.

Two cautions against reading the range too warmly. On the narrow base the rate
exceeds 50%, which is high enough that a reviewer will scrutinize the pool
composition rather than accept it. And every scenario is hostage to the fixed
asset register: if the asset base is overwhelmingly grant-funded, Scenario A is
the ceiling, not the floor.

---

## 8. Personnel expense documentation — the binding constraint

### 8.1 What 200.430(i) requires

Charges to federal awards for salaries and wages must be based on records that
accurately reflect the work performed, and those records must:

- be supported by a system of internal control providing reasonable assurance that
  charges are accurate, allowable and properly allocated;
- be incorporated into the official records of the entity;
- reasonably reflect the **total activity** for which the employee is compensated,
  **not exceeding 100%**;
- encompass both federally assisted and all other activities on an integrated
  basis;
- comply with the entity's established accounting policies and practices; and
- support the distribution of salary among specific activities or cost objectives.

**Budget estimates alone do not qualify as support.** They may be used for interim
accounting only where the system produces reasonable approximations, significant
changes are identified and entered timely, and internal controls include
after-the-fact review. Substitute systems using sampling or statistical methods
require federal approval under 200.430(i)(8).

### 8.2 Where YBI stands

**The general ledger contains no labor distribution at all.** Payroll enters as two
lump journal entries per pay period:

```
5140 Employee Wages | 01/15/2025 | Journal Entry | 202500018 | GROSS - Employee | 59,791.40
5140 Employee Wages | 01/29/2025 | Journal Entry | 202500037 | GROSS - Employee | 61,836.76
```

No employee. No project. No class. No function. $1,789,993.94 of wages with zero
distribution in the accounting system of record.

The controller's workbook is a substantial and competent reconstruction — a full
distribution of every employee's FY2025 wages across twenty cost objectives,
footing to total compensation. It is far better than nothing. It is not yet
sufficient, for four reasons:

1. **It is not contemporaneous.** Prepared September 2026 for calendar 2025. This
   is the central vulnerability and no amount of internal rigor cures it.
2. **It is not in the official records.** 200.430(i)(1)(ii) requires
   incorporation into the entity's records. A spreadsheet on the controller's
   drive is not the general ledger.
3. **Roughly twenty-eight employees are recorded at 100% to a single cost
   objective** — entered as the value `100` in the source pivot. For an employee
   working solely on a single federal award this is acceptable *if supported by a
   periodic certification signed by the employee or a supervisor with firsthand
   knowledge*. Those certifications do not yet exist. Without them these are
   allocations by assertion.
4. **Hours were normalized to fit compensation.** The controller notes that "many
   employees who have excess time over and above what would be allowed for in a
   given month... is factored into calculations in columns AD:AW to ensure the
   hours align with 100% of compensation." Pro-rata normalization is a defensible
   method and satisfies the not-exceeding-100% rule. It also means the underlying
   hour records were internally inconsistent with payroll, which an auditor will
   pull on. The method needs to be written up and disclosed rather than left
   implicit in hidden columns.

### 8.3 What to do

- **Prospective (from the next pay period):** timekeeping of record capturing all
  hours by cost objective for every employee, reviewed and approved by a
  supervisor, feeding a labor distribution journal entry that posts to the GL by
  project. This closes the DFARS 252.242-7006 gaps and is what the audit needs to
  see going forward.
- **FY2025 (retrospective):** obtain **signed employee or supervisor certifications**
  for the reconstructed distribution — annual certifications for single-objective
  employees, and confirmation of the allocation for split employees. Document the
  normalization methodology as a written memorandum. Disclose the reconstruction to
  the auditor as a reconstruction. Do not present it as a contemporaneous record.
- **Do not re-derive the distribution to improve the reconciliation.** The
  controller's allocation was prepared before the rate work and that independence
  is an asset. Reclassification should correct identifiable errors — a
  misclassified cost objective, a support role that belongs in G&A rather than
  direct — each with a documented reason and a named approver. It should never be
  a global re-run tuned to an outcome.

---

## 9. Open items

Blocking the FY2025 proposal:

1. **Third NCDMM agreement** — believed to be N00174-20-1-0031, ALN 12.300,
   $421,616 expended in FY2024. Plus all modifications to all three agreements.
2. **Hybrid Phase 2 Schedule B** — the cost proposal incorporated by reference,
   containing that award's indirect treatment.
3. **The workpaper behind the $233,543.12** of unrecovered indirect on Project 88,
   and any **written AFRL approval** of unrecovered indirect as cost share.
   200.306(c) permits unrecovered indirect as match **only with prior approval of
   the federal awarding agency**. §4.1 references "the approval of AFRL found in
   Schedule B" — that approval document needs to be located and read.
4. **Fixed asset register with funding source per asset.** The single largest
   swing factor in the rate. Must be corrected for Finding 2024-001 first.
5. **Subrecipient vs. contractor determinations** under 200.331 for every partner
   on every agreement.
6. **Resolution of the $45,000.03 variance** between the timesheet workbook and
   P&L account 5139.
7. **Whether Hybrid was billed above its $500,043 federal ceiling.**
8. **Ohio Department of Development ESP indirect cost cap**, if any.

Received:

- Square footage: **50% tenant / 30% program / 20% administrative** (management
  estimate — a floor plan or lease schedule supporting it will be needed for the
  proposal).

Not yet available:

- FY2025 draft audit and SEFA. Same audit firm as FY2023 and FY2024. No draft
  exists yet, which is the opportunity: the remediation and disclosure described
  in §5.6 and §6.4 can be in place before fieldwork rather than after.

---

## 10. What this means for the tool

The regulatory analysis above translates fairly directly into requirements.

**Ingestion must be immutable.** Every QuickBooks export stored verbatim with a
content hash, period, source and uploader. Parsed into a normalized ledger.
Nothing edited in place. When an auditor asks where a number came from, the answer
has to run to the source transaction.

**Classification is data, not code.** An effective-dated mapping from account ×
cost objective × employee to treatment — direct, fringe, overhead, G&A,
unallowable, base-excluded — with a **rationale and a named approver on every
entry**, and full version history. Reclassification is a first-class operation,
never an overwrite. This is the heart of the product and the thing that makes the
proposal defensible.

**Support staff allocation must be per-person and per-period,** classifiable as
direct, overhead or G&A according to their actual time, with the CAS 402 /
200.403(d) consistency check enforced: the tool should flag when the same role is
being treated as direct on one award and indirect on another, because that is the
controller-allocation problem in §4.2 and it will recur.

**Timesheet certifications are records, not attachments.** Employee and supervisor
certifications tied to the specific period and cost objectives they attest to,
with signature, date and scope, retrievable as evidence supporting a specific
labor charge. 200.430(i)(1)(ii) requires the distribution to live in the official
records; the tool is where that happens.

**Restated invoices need full lineage.** Original invoice, restated invoice, the
delta, the rate applied, the authority for the restatement — the executed §4.4
modification — and the approval chain. America Makes is willing to work with YBI;
what will make that easy is handing NCDMM a package that shows its own arithmetic.

**Scenario modeling, versioned and reproducible.** Multiple allocation methods and
pool/base structures run side by side, each a reproducible artifact that can be
diffed against another, with a locked methodology date proving the method preceded
the result — the §5.6 discipline enforced by the system rather than by memory.

**Reconciliation to the audited financial statements is blocking, not advisory.**
A rate proposal that does not tie to the F/S cannot be submitted.

**Monthly cost-share tracking against the ~1:1 ratio** both agreements require,
with the corrective-action trigger visible before it is breached rather than after.

**Every number carries its authority.** Unallowable exclusions cite their section.
Base exclusions cite theirs. The proposal should be able to print itself as a
workpaper with citations intact.

---

## Appendix A — Authorities cited

**2 CFR Part 200**

200.1 (definitions: MTDC, unrecovered indirect cost) · 200.305 (payment) ·
200.306 (cost sharing or matching) · 200.331 (subrecipient and contractor
determinations) · 200.332 (requirements for pass-through entities) · 200.344
(closeout) · 200.345 (post-closeout adjustments) · 200.346 (collection of amounts
due) · 200.402 (composition of costs) · 200.403 (factors affecting allowability) ·
200.404 (reasonable costs) · 200.405 (allocable costs) · 200.406 (applicable
credits) · 200.412 (classification of costs) · 200.413 (direct costs) · 200.414
(indirect costs) · 200.415 (required certifications) · 200.421 (advertising and
public relations) · 200.426 (bad debts) · 200.430(i) (standards for documentation
of personnel expenses) · 200.434 (contributions and donations) · 200.436
(depreciation) · 200.438 (entertainment) · 200.441 (fines and penalties) · 200.442
(fund raising and investment management) · 200.449 (interest) · 200.450
(lobbying) · 200.454 (memberships, subscriptions and professional activity) ·
200.465 (rental costs of real property and equipment) · 200.470 (taxes) · 200.475
(travel costs) · 200.501 (audit requirements) · 200.512 (report submission) ·
200.516 (audit findings) · 200.518 (major program determination) · 200.519
(criteria for federal program risk) · 200.520 (criteria for a low-risk auditee) ·
Appendix IV (indirect cost identification and assignment for nonprofit
organizations)

**Other federal**

2 CFR Part 1103 (DoD interim implementation) · 32 CFR Subchapter C (DoD grant and
agreement regulations) · 31 U.S.C. 3729 (False Claims Act) · 89 FR 30046
(22 April 2024, OMB Uniform Guidance revisions)

**FAR / DFARS / CAS — persuasive, not binding on these agreements**

FAR 31.201-4 · FAR 31.201-6 · FAR 31.203 · FAR 42.704 · FAR 42.705 ·
FAR 52.242-4 · DFARS 252.242-7006 · CAS 401 · CAS 402

**Agreement provisions**

Sub-Recipient Agreements, NCDMM–YBI: §4.1 (compensation) · §4.2 (reimbursement of
actual expenses) · §4.3 (total obligation ceiling) · §4.4 (expense changes and
written amendment) · §4.5 (invoicing and progress reports) · §4.6 (records
retention and audit) · §10.1 (term) · Schedule B (budget) · Schedule C (federal
flow-down) · Schedule D (programmatic and financial reporting)
