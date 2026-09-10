# Brief

Start here. `PROJECT_CONTEXT.md` has the numbers, `ARCHITECTURE.md` has the
design decisions, `CLAUDE.md` has the conventions. This is the orientation and
the intake list.

---

## 1. What this is, in one page

Youngstown Business Incubator is a nonprofit incubator. Its historic operating
model was **rental income plus state-funded entrepreneurial services** — a
landlord with an ODSA-funded programme attached. A few years ago it began
taking **federal work** as a subrecipient, principally America Makes awards
flowing through NCDMM under AFRL cooperative agreement FA8650-20-2-5700.

The accounting never caught up with the change. The chart of accounts was built
for a landlord running state programmes, and federal awards were bolted onto it.
Concretely, that produced:

- **No real timekeeping.** 36 of 45 employees have a single asserted percentage
  rather than a time record. Management time is attributed to whichever
  programme it touched instead of to G&A — the CEO certifies 14% to general
  administration.
- **No indirect structure.** They elected the 10% de minimis and never built
  pools, so facilities and operational overhead have never burdened direct
  labour at all.
- **Budget-draw billing.** Invoices went out at budget ÷ 12 on
  cost-reimbursement instruments, which over-bills an award that underspends
  and under-bills one that overspends.

The net effect is **systematic under-recovery**. They have been absorbing
facilities, overhead and administrative cost that a proper rate would have
recovered — while simultaneously over-billing one award through the twelfths
method.

They are now in a **Single Audit** for the 2 CFR 200 flow-through work, and they
need to restate off de minimis onto a real rate.

### The counterparty position — this is favourable and it drives strategy

**America Makes is friendly and will allow restated rates applied
retroactively to prior invoices, provided the restated total stays under the
contracted total.**

That converts the whole exercise from a negotiation into a **ceiling-constrained
optimisation**. Per award: restate at the defensible rate, cap at the ceiling,
and the direction of the delta determines whether it is a collectible invoice or
a credit. It also makes the 200.332 pass-through rate negotiation a real path
rather than a theoretical one — no federal cognizant agency required.

### The target end state

1. A defensible 2025 indirect rate, restated retroactively across the America
   Makes portfolio within each contract ceiling.
2. A 2025 Form 990 with an honest functional allocation.
3. A Single Audit that finds a financial management system **already
   remediated and self-identified**, not one discovered to be missing.
4. A QuickBooks chart and a system that make 2026 onward bookkeeping rather
   than remediation — and that meet **DCAA accounting system criteria**, so YBI
   can bid cost-reimbursement work directly rather than only as a subrecipient.

---

## 2. The recommended model, as it stands

Assumptions: labour properly certified, facilities 40% allocable.

| Rate | |
|---|---:|
| Fringe on salaries and wages | **22.45%** |
| Facilities on MTDC | 12.89% |
| G&A on MTDC | 18.89% |
| **Combined indirect on MTDC** | **31.78%** |

$100 of direct labour becomes **$161.36** fully burdened, against $134.69 under
de minimis — a **19.8% uplift on every labour dollar**, which is the recurring
value of the work.

Largest open lever: `5227 Portfolio consulting`, 588,539 across 442 lines,
swinging the rate between 28.09% and 44.90% depending on classification.

The unresolved blocker is a **$1,578,980 discrepancy** between invoices tracked
in the controller's grant tabs (586,144) and America Makes revenue recognised in
the ledger (2,165,124). Until actual submitted invoices are in hand, no award
delta is final and Digital Engineering — never reconciled at all — may be a
larger exposure than Hybrid.

---

## 3. Deployment shape

Railway project, four services:

| Service | Notes |
|---|---|
| **api** | FastAPI. Migrations on boot from `app/sql/*.sql`. Healthcheck `/api/health`. |
| **web** | Vite/React. Can deploy as its own service against `VITE_API_URL`, or be served from the API's `web/dist` — the Dockerfile already builds it that way. Start unified; split only if build times justify it. |
| **postgres** | Small instance. `DATABASE_URL` injected. The schema is the design document — invariants live in constraints and triggers. |
| **bucket** | Evidence store, content-addressed by SHA-256. Set `S3_BUCKET` / `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY`; falls back to a local volume at `/srv/storage` when unset. |

**Nothing with PII goes in git.** Payroll registers, employee rosters and
certifications go to the bucket through the upload endpoint, never into the
repo. Add `/intake/` to `.gitignore` before dropping anything in it.

---

## 4. DCAA alignment

2 CFR 200 is the floor. If YBI wants to prime cost-reimbursement work rather
than only subcontract, the standard is the SF1408 preaward accounting system
survey. The build already targets most of it:

| SF1408 criterion | Where it lives | Status |
|---|---|---|
| Consistent with GAAP | QuickBooks, accrual | exists |
| Segregation of direct from indirect | account number encodes the pool | built |
| Direct costs accumulated by contract | Customer:Job → cost objective | built |
| Logical, consistent indirect allocation | multiple allocation base, Appendix IV B.3 | built |
| Costs under general ledger control | immutable `ledger_line`, control tie-outs | built |
| Timekeeping identifying labour by objective | **the gap** | needs a time system |
| Labour distribution to cost objectives | labour module, certification | partial |
| Interim cost determination, at least monthly | monthly close and posting | **needs a cadence** |
| Exclusion of unallowables | 92xx accounts, `UNALLOWABLE` pool | built |
| Costs by contract line item | award budget lines, invoice reconstruction | partial |
| Limitation of cost / funds reporting | ceiling constraint, cumulative test | built |

The two real gaps are **contemporaneous timekeeping** and a **monthly close
cadence**. Both are 2026 process problems rather than software problems, but the
system should make them cheap: employee-facing time entry with digital
certification, and a monthly close that runs the tie-outs and freezes the period.

---

## 5. Raw intake

Drop into `/intake/<year>/<category>/`. CSV wherever QuickBooks offers it — the
Excel export path merges cells and inserts formatting rows the parser has to
work around.

### Tier 1 — blocks the America Makes restatement

| # | Item | Unblocks |
|---|---|---|
| 1 | **Every invoice submitted to NCDMM**, all four awards, with the required expense summaries and progress reports | the 1,578,980 gap; whether non-labour was billed separately; whether any invoice carried a loaded or indirect line |
| 2 | **Cost proposals incorporated by reference** — starting with `Hybrid Phase 2 Technical_Cost Proposal_YBI_Final_V2.pdf` | whether loaded labour rates were ever approved. Decides if Hybrid is an over-billing at all |
| 3 | **All America Makes sub-recipient agreements** — Drive AM, Hybrid Phase 2 **and 3**, Last Tactical Mile, Digital Engineering, plus every modification | the ceilings, which are now the binding constraint on restatement |
| 4 | **Cost share reports** submitted under Schedule D, if any | the 104,000 obligation, untracked |
| 5 | Payment remittances / cash receipts against each award | reconciles invoiced to collected |

### Tier 2 — completes the rate

| # | Item | Unblocks |
|---|---|---|
| 6 | **Fixed asset register** — acquisition date, cost, funding source, method, life | 200.436(b). 850,383 of depreciation, the last open rate variable |
| 7 | **Grant award documents for any funded asset or building** | proves which basis is federally or state funded |
| 8 | **Floor plan with square footage by suite**, plus rent roll and lease schedule | the facilities carve-out; replaces the 40% estimate with evidence |
| 9 | **Debt schedule** — mortgages and notes | whether the 49,001 of interest is allowable under 200.449 rather than unallowable |
| 10 | **Payroll register**, employee × pay period, gross wages, 2024–2025 | validates the wage control bottom-up and the 45,000 reconciling credit |
| 11 | **Employer tax and benefit cost by employee** | validates the fringe pool bottom-up |
| 12 | **Employee roster** — title, exempt status, department, hire/term dates | certification targeting; who should be G&A |
| 13 | Any existing timesheets, calendars, effort records, board minutes | turns MANAGEMENT RECONSTRUCTION into CORROBORATED |

### Tier 3 — QuickBooks, per year 2023–2025

| # | Report | Path in QBO |
|---|---|---|
| 14 | General Ledger, accrual, all accounts | Reports → For my accountant |
| 15 | Profit & Loss, no subaccount collapsing | Reports → Business overview |
| 16 | Balance Sheet | Reports → Business overview |
| 17 | Trial Balance | Reports → For my accountant |
| 18 | Chart of Accounts | Settings → Chart of accounts → Export |
| 19 | Transaction List by Vendor | Reports → Expenses and vendors |
| 20 | Transaction List by Customer | Reports → Sales and customers |
| 21 | Customer list **with sub-customers** | Reports → Customers |
| 22 | Vendor list | Reports → Vendors |
| 23 | A/R Aging Detail | Reports → Who owes you |
| 24 | Journal report | Reports → For my accountant |
| 25 | Time Activities by Employee Detail | Reports → Employees |
| 26 | Class and Location lists, if tracking is on | Settings → All lists |
| 27 | Fixed Asset listing | Reports → For my accountant |

2024 matters more than it looks. Most of the Hybrid Phase 2 period sits there,
and a retroactive restatement across the award will need a 2024 basis or an
explicit, disclosed decision to leave 2024 at de minimis.

### Tier 4 — governance and other awards

| # | Item |
|---|---|
| 28 | Form 990, 2023 and 2024 |
| 29 | Audited financial statements, 2023 and 2024 |
| 30 | Prior Single Audit reports and management letters, if any |
| 31 | ARC / Rising Tides award document — settles the federal determination and the SEFA |
| 32 | ODSA ESP and MBAC agreements |
| 33 | DLA award |
| 34 | Written policies: timekeeping, travel, procurement, allowability, cost allocation |
| 35 | Organisation chart |

---

## 6. What to build next

Superseded by `PLAN.md`. Summary of the order below.


1. **Invoice ingestion and reconstruction.** Parse submitted invoices, tie them
   to awards and budget lines, and reconcile invoiced against revenue recognised
   against claimable. This is the gate on everything in America Makes.
2. **Ceiling-constrained restatement.** Given the friendly retroactive posture,
   the engine should solve per award: restate at rate, cap at ceiling, output an
   amended invoice or a credit. `awards.py` has the constraint tests; it needs
   the optimisation and the invoice generator.
3. **Employee time entry with digital certification.** Employee × period × cost
   objective, signed attestation covering **total activity**, supervisor
   countersignature. Closes the largest SF1408 gap and makes 2026 real.
4. **Balance sheet ingestion** for asset basis and funding source.
5. **Monthly close.** Run the tie-outs, freeze the period, post interim costs.
   The other SF1408 gap.
6. **Audit package download** — `domain/package.py` already generates it, needs
   a streaming route.

---

## 7. Framing worth keeping

The story here is not that YBI over-billed. It is that an organisation built to
be a landlord running state programmes took on federal work without the
financial infrastructure federal work requires, and **under-recovered
substantially as a result** — absorbing facilities and overhead that never
burdened a single direct labour hour.

The restatement recovers some of that. The system stops it recurring. An auditor
who sees the gaps self-identified, quantified and already being remediated
writes a very different finding than one who discovers them.
