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
