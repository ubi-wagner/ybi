# Discrepancies for the controller to settle

Eighteen things the record cannot resolve on its own. Every one was found by a
control rather than by somebody reading — which is the point of the controls —
and every one is a question Tom can answer from what he already knows or can
reach today. Nothing here needs counsel, an outside document, or a decision
from a sponsor; those are listed separately at the end.

Ordered by how much each moves the rate.

Figures are as at 11 September 2026, read from the live record.

---

## 0. The worked example — confirmed

**The Bacon $45,000.** A pledge from Vince and Phyllis Bacon to fund interns,
booked as a **credit against intern wage expense** rather than as
contributions income:

```
2025-12-01  5142 Intern Wages         Vince and Phyllis Bacon  -45,000.00
2025-12-01  1100 Accounts Receivable  Vince and Phyllis Bacon  +45,000.00
```

**Confirmed by Tom, 11 September 2026.**

It is on this list as the example of what the rest of it looks like, because it
shows the whole shape:

- **Nothing else would have found it.** Ten of the eleven cross-reference
  controls compare the ledger to the P&L and the balance sheet, and this line
  is consistent with all three. Only the eleventh — the payroll register
  against the ledger's wage accounts — sees it, because the register records
  what was *paid to people* and the ledger recorded a donation in the same
  account.
- **It is two denominators for one rate.** The fringe base comes from the
  effort distribution, so a $45,000 credit sitting in a wage account made the
  fringe rate read **22.45%** when it is **21.90%**.
- **It is named, not netted.** It sits on the record as a `SOURCE_DEFECT`
  reconciling item carrying the two specific ledger lines it consists of, so
  the control closes without anybody adjusting anything.

**Still open on it:** it has not been reposted in QuickBooks. When it is, the
reconciling item has to come off with it — the two must not both be there.

---

## 1. Depreciation — the largest lever in the file

$23.4m of gross basis against $6.74m of annual expense. These six questions
decide roughly three points of the indirect rate between them.

### 1.1 Three reimbursements netted against Tech Block Building 5 — $157,739

The 2026 fixed asset schedule carries these on the Building 5 sheet:

| Date | Description | Amount |
|---|---|---:|
| 2019-06-30 | Fitz Reimbursement | −117,739.00 |
| 2019-09-26 | NCDMM Reimbursement | −25,000.00 |
| 2019-12-31 | YSU Reimbursement | −15,000.00 |

**This is Finding 2024-001 in the flesh** — capital reimbursements netted
against asset cost. If the cost on the books is net of these, the gross basis
is understated by $157,739 and the federal participation percentage cannot be
derived from what is recorded.

**Tom:** is the recorded cost of Building 5 gross or net of these three? And
is NCDMM's $25,000 federal money?

### 1.2 Two aggregates the register's own totals exclude — $1,516,695

| Sheet | Row | Amount |
|---|---|---:|
| BLDG-1511-1512 | `BUILDINGS` | 180,000.00 |
| BIMP-1521-1522 | `CAPITAL IMPROVEMENTS` | 1,336,695.00 |

Both are printed on their sheets and both are left out of the "Total
Cost/Basis" those sheets carry. Reading them as assets overstates the basis by
$1.5m; dropping them silently would be a $1.5m hole nobody could see. They
look like opening aggregates the itemised rows below them replaced.

**Tom:** confirm these were superseded by the detail rather than dropped by
accident.

### 1.3 The register is $122,921.14 above the balance sheet

| | |
|---|---:|
| Register, every asset on all seven sheets | 23,419,573.64 |
| Construction in progress — on the balance sheet, absent from the register | 438,355.19 |
| **Register plus construction in progress** | **23,857,928.83** |
| Balance sheet, gross fixed assets at 31 Dec 2025 | 23,735,007.69 |
| **Over** | **122,921.14** |

The register is a 2026 export, so additions after 31 December would account
for it — but that is an assumption and the rate should not rest on one.

**Tom:** can we have the register as at 31 December 2025? Failing that,
confirm the $122,921.14 is 2026 additions.

### 1.4 Depreciation differs by $22,429.02

| | |
|---|---:|
| 2025 P&L, account 5010 | 850,382.89 |
| Register, "Current Depreciation" | 872,811.91 |

Same likely cause as 1.3 — the register is a 2026 export — and the same
answer needed.

### 1.5 Xjet Ceramic Printer, carried at $0.00

System no. 174, in service 25 January 2018, seven-year life, **cost 0.00**,
no accumulated depreciation, no current depreciation. An asset with a real
number and a real date and no money against it.

There is also an `XJET` cost objective on the record.

**Tom:** donated? Fully reimbursed and netted, like 1.1? Or written off?

### 1.6 Two "True Up Entry (One Time)" rows — $16,931.13

On the Building 5 sheet, dated 30 and 31 December 2019, carrying
accumulated depreciation of $7,173.29 and $9,757.84 and no cost at all.

**Tom:** what were these correcting?

---

## 2. The books against each other

### 2.1 Every ledger-to-P&L difference is Rising Tides — $7,469.87

Five accounts differ and all five are one account bleeding into four others:

| Account | Ledger | P&L | Difference |
|---|---:|---:|---:|
| Grant Expenses:Rising Tides Expense | 582,085.53 | 574,615.66 | **+7,469.87** |
| Program Expenses:ESP | 17,511.84 | 23,811.84 | −6,300.00 |
| M&A:5205 Travel:5206 Travel | 17,784.01 | 18,406.27 | −622.26 |
| 5080 Fundraising:5085 Advertising | 124,736.79 | 125,017.19 | −280.40 |
| M&A:5300 Staff Training | 7,961.44 | 8,228.65 | −267.21 |

Ten specific lines, recorded as `RECLASS_AFTER_EXPORT` items carrying the
lines behind each. Nothing is unexplained.

**Tom:** were these reclassified out of Rising Tides after the general ledger
was exported and before the P&L was? If so the record is right as it stands;
if not, one of the two exports is wrong.

### 2.2 Is Rising Tides federally funded? — $1,386,355.56

The objective master says **not federal**. The controller's workbook says it
is. 137 ledger lines.

This is the single biggest open question outside depreciation, because it
changes the **SEFA and the scope of the Single Audit**, not just a rate.

**Tom:** which is right, and what is the award?

### 2.3 $451,170.39 in `4801 IH Grant Income`

The P&L reports it under Innovation Hub. The revenue ledger attributes it to
NCDMM.

**Tom:** which? If it is not America Makes money, the America Makes
reconciliation changes by nearly half a million dollars.

### 2.4 Hybrid is out by $100.02

| | |
|---|---:|
| P&L revenue, `3900 Grant Income:Hybrid Energy` | 191,638.05 |
| Grant tabs, billings | 191,738.17 |

Small, and Hybrid is the one award that is genuinely labour-only, so its
over-billing conclusion stands either way.

**Tom:** worth five minutes to close it rather than leaving it in a workpaper.

---

## 3. Space

From the 2025 lease book — 26 tenancies, $601,269.48 of annual rent.

### 3.1 Four buildings named once each

`AM`, `Taft`, `Semple`, and `Taft/semple`. The other twenty-two tenants are in
`YBI` or `TBB5`.

**Tom:** are these YBI buildings, and are `Taft`, `Semple` and `Taft/semple`
two buildings or three?

### 3.2 One tenant across two buildings

`Taft/semple` is a single row. Square footage is the driver the facilities
carve-out is sized by, so it has to land in one building or be split between
two.

**Tom:** which, and in what proportion?

### 3.3 Eight tenancies say "monthly" where a start date belongs — $18,592.56

Azanna Elise, Equipment Appraisal Services, Greg Babinack, JSO Technologies,
M. Jones, Made by Morgan, Parallax, Ralph Zerbonia.

**Tom:** month-to-month arrangements, or start dates that were never
recorded? It matters because a suite occupied for part of the year is a part
of a suite of cost.

### 3.4 MVMC starts 1 April 2026

In the 2025 lease book, contributing no 2025 rent.

**Tom:** should it be in the 2025 book at all?

---

## 4. People

### 4.1 The payroll register keys people by surname

`EWING`, `RUBY`, `GAFFNEY`. If two people shared a surname in 2025 their hours
are already joined together and every effort figure for both is wrong.

**Tom:** any duplicate surnames on the 2025 register? If yes we need real
payroll IDs, and that is a change to the ingest rather than to a form.

---

## 5. The invoices

### 5.1 The invoice dates on file are ours, not YBI's

All three invoices carry `2026-05-01` with a service period of April 2026,
sitting in period **2025**. Those dates are a placeholder in
`scripts/load_invoices.py` — the line items and totals are real, the dates
were never supplied.

| Invoice | Objective | Total |
|---|---|---:|
| 10018 | DRIVE-AM | 37,593.90 |
| 10023 | HYBRID-II | 1,374.00 |
| 10039 | LTM | 18,993.52 |

**Tom:** the real invoice dates and service periods for these three. A
restatement is measured per invoice within a period, so a wrong date puts a
claim in the wrong year.

### 5.2 No cash has been recorded against any of them

$57,961.42 issued, **zero** receipts on the record.

**Tom:** have these been paid? Collections are currently unknowable from the
system, and a receipt may be negative, so a clawback would show here too.

---

## Not on this list, and why

These are open and they are not Tom's to settle today:

- **Drive AM's cost share contradiction.** Schedule A expects roughly 1:1 at
  all times; Schedule B proposes zero and §4.3 names none. §11.11 gives the
  Agreement precedence over a Schedule, but §4.3 is silent rather than
  contradictory, and silence may not be a conflict. ~$1.1m if the 1:1 reading
  binds. **Needs counsel, not arithmetic.** Recorded as a term marked
  UNRESOLVED.
- **$617,065 of obligated cost share never tracked** — $513,065 on Last
  Tactical Mile (§4.3), of which YBI's own share is $213,037, and $104,000 on
  Hybrid. Needs the partner evidence, not a judgment.
- **Funding source per asset** and **square footage per suite** — these are
  the two request workbooks, not questions.
- **Award budgets for ICAM, LTM and Hybrid** — our transcription job, not
  YBI's. Only Drive AM's Schedule B is read in, so
  `v_invoice_budget_check` correctly reports the other three as
  `evaluable = false` rather than passing.
