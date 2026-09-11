# 2025 baseline — ground truth

Produced by running the real exports through the system end to end against a
clean database: 32 migrations, the ladder provisioned through the API, the
three QuickBooks exports and the controller's effort distribution loaded
through the real endpoints, and every control point evaluated.

Nothing here is asserted. Every figure below is reproduced from source and
cross-tied to at least one other document.

---

## 1. Statement integrity — eleven of eleven tie

| Control | Left | Right | State |
|---|---:|---:|---|
| PL_FOOTING | 4,329.28 | 4,329.28 | TIES |
| BS_FOOTING | 16,713,219.80 | 16,713,219.80 | TIES |
| GL_PROMOTE_COMPLETE | 15,500 | 15,500 | TIES |
| GL_SUBTOTALS | 14,371,299.30 | 14,371,299.30 | TIES |
| GL_PL_SECTION | 13,554,753.64 | 13,554,753.64 | TIES |
| GL_PL_ACCOUNT | gross 14,939.74 | unexplained 0.00 | TIES |
| GL_PL_COVERAGE | 0 | 0 | TIES |
| GL_BS_ACCOUNT | 71 tied | 0 off | TIES |
| GL_BS_COVERAGE | 4 absent at zero | 0 carrying a balance | TIES |
| SEGMENTATION | 14,371,299.30 | 14,371,299.30 | TIES |
| PAYROLL_REGISTER | 1,835,047.18 | 1,789,993.94 | TIES |

They tie on six named reconciling items and one alias — no plugs:

| Kind | Items | Lines | Amount |
|---|---:|---:|---:|
| `RECLASS_AFTER_EXPORT` | 4 | 10 | 7,469.87 gross, nets to 0.00 |
| `SOURCE_DEFECT` | 1 | 1 | −45,000.00 |
| `ROUNDING` | 1 | 0 | −53.24 |

The four reclassifications all run out of `Grant Expenses:Rising Tides
Expense` into four other accounts, and net to exactly zero — which is why
GL_PL_SECTION tied before GL_PL_ACCOUNT did. The alias records that the ledger
prints the accumulated surplus as `Retained Earnings` and the balance sheet
prints it as `3000 Fund Balance`.

## 2. Cost structure

Expense by family, footing to the P&L to the cent:

| Family | Lines | Amount |
|---|---:|---:|
| 5129 Payroll Expenses | 364 | 2,197,014.24 |
| Grant Expenses | 288 | 1,435,160.70 |
| Program Expenses | 704 | 952,771.57 |
| Management & Administrative | 2,229 | 935,379.44 |
| 5010 Depreciation Expense | 12 | 850,382.89 |
| 5080 Fundraising | 345 | 306,203.71 |
| 5310 Interest Expense | 43 | 49,000.78 |
| 5001 Cost of Goods Sold | 2 | 37,261.00 |
| 5400 Bad Debt Expense | 4 | 12,037.85 |
| Channel selling fees | 29 | 0.00 |
| **Total** | **3,720** | **6,775,212.18** |

= P&L Expense 6,737,951.18 + COGS 37,261.00. Ties exactly.

## 3. Fringe — both published rates reproduced, and the difference explained

**Fringe pool** — six accounts, 401,783.60:

| | |
|---|---:|
| 5130 Benefits | 194,353.59 |
| 5133 401k Match & Profit Sharing | 56,519.42 |
| 5145 Bureau of Worker's Compensation | 2,707.00 |
| 5151 Social Security & Medicare | 139,303.78 |
| 5185 FUTA | 1,653.51 |
| 5195 SUI | 7,246.30 |
| **fringe pool** | **401,783.60** |
| *5137 Payroll Processing Fees (excluded)* | *5,236.70* |

**Wage base:**

| | |
|---|---:|
| 5140 Employee Wages | 1,678,157.27 |
| 5142 Intern Wages | 111,836.67 |
| wages as booked | **1,789,993.94** |
| Bacon donor credit added back | 45,000.00 |
| wages corrected | **1,834,993.94** |
| controller's register | 1,835,047.18 |
| unattributable residual | 53.24 |

**The rate:**

| Basis | Rate | |
|---|---:|---|
| on wages as booked | **22.45%** | 401,783.60 / 1,789,993.94 |
| on wages corrected | **21.90%** | 401,783.60 / 1,834,993.94 |
| on the register | 21.90% | 401,783.60 / 1,835,047.18 |

Both figures in circulation are now derived rather than asserted. 22.45% is
the rate over a wage base a $45,000 donor credit has been netted out of;
21.90% is the rate over the wage base that credit belongs in. The difference
is entirely the Bacon misposting and nothing else.

One judgment is embedded and should be stated: `5137 Payroll Processing Fees`
(5,236.70) is outside the fringe pool. It is an administrative cost of running
payroll rather than a benefit accruing to employees, but the choice is worth
0.28 points — with it in the pool the corrected rate is 22.18%.

## 4. Depreciation — cross-tied by asset class

The six accumulated-depreciation accounts' 2025 movement:

| | |
|---|---:|
| 1502 TBB5 | 438,873.05 |
| 1512 Buildings | 224,524.44 |
| 1522 Capital Improvements | 102,820.79 |
| 1523 Capital Leases | 0.00 |
| 1526 Computer Equipment | 77,597.49 |
| 1528 Equipment-Other | 6,567.12 |
| **Total** | **850,382.89** |

Exactly `5010 Depreciation Expense`. Depreciation is proved off the balance
sheet by class, both sides, with no residual.

## 5. Fixed asset basis — the register ties the sheet within ten cents

The 2026 fixed asset schedule's **beginning** accumulated depreciation column
is the 31 December 2025 position:

| Account | Balance sheet 2025 | Register beginning | Diff |
|---|---:|---:|---:|
| 1512 Buildings | 3,650,762.57 | 3,650,762.43 | (0.14) |
| 1522 Capital Improvements | 2,095,262.68 | 2,095,262.02 | (0.66) |
| 1523 Capital Leases | 211,518.00 | 211,518.00 | — |
| 1526 Computer Equipment | 655,438.60 | 655,438.51 | (0.09) |
| 1528 Equipment-Other | 163,558.21 | 163,559.43 | 1.22 |
| 1502 TBB5 | 2,803,893.23 | 2,803,893.00 | (0.23) |
| **Total** | **9,580,433.29** | **9,580,433.39** | **0.10** |

Ten cents on $9.58 million across six independently-kept accounts is not a
coincidence — it establishes that the register and the ledger are the same
assets.

Cost ties exactly on Land (107,530.00) and Buildings (8,760,612.01). The
122,921.14 of cost differences elsewhere are 2026 additions: the register's
newest assets are dated July 2026, so its **current-year column is 2026, not
2025**. 2025 depreciation therefore cannot be proved from this document —
that needs the 2025 run of the same schedule — but the 2025 **basis** can, and
the basis is what 200.436(b) turns on.

Balance sheet fixed assets: gross 23,735,007.69 less A/D 9,580,433.29 =
**14,154,574.40**, as printed.

`1505 Construction in Progress` (438,355.19) is on the sheet and absent from
the register. Correct — it is not depreciated — but it means the register is
not a complete statement of what the organisation owns.

## 6. Effort distribution — 43 people, 16 objectives, 1,835,047.16

| Objective | People | Wage dollars | % | Treatment |
|---|---:|---:|---:|---|
| ESP | 32 | 561,144.73 | 30.6% | non-federal direct |
| MBAC | 10 | 278,465.52 | 15.2% | non-federal direct |
| YBI-GA | 10 | 264,444.89 | 14.4% | G&A pool |
| HUB | 5 | 172,214.46 | 9.4% | non-federal direct |
| DRIVE-AM | 6 | 147,310.09 | 8.0% | federal direct |
| RISING-TIDES | 7 | 106,398.41 | 5.8% | **disputed** |
| YOUTH | 4 | 90,591.31 | 4.9% | non-federal direct |
| HYBRID-II | 4 | 62,992.64 | 3.4% | federal direct |
| LTM | 4 | 52,607.87 | 2.9% | federal direct |
| FUNDRAISING | 5 | 40,088.79 | 2.2% | excluded, 990 function |
| DIG-ENG | 2 | 30,700.46 | 1.7% | federal direct |
| XJET | 1 | 16,937.31 | 0.9% | federal direct |
| AM-OTHER | 3 | 7,129.63 | 0.4% | federal direct |
| IIOT | 1 | 2,777.39 | 0.2% | federal direct |
| VGV | 2 | 842.68 | 0.0% | federal direct |
| DLA | 1 | 400.98 | 0.0% | federal direct |

Grouped: non-federal direct 1,102,416.02 (60.1%), federal direct 321,699.05
(17.5%), G&A 264,444.89 (14.4%), disputed 106,398.41 (5.8%), fundraising
40,088.79 (2.2%).

Two things this says out loud:

- **G&A carries 14.4% of labor.** That is the distortion BRIEF.md names —
  management time attributed to whichever programme it touched rather than to
  general administration. A defensible G&A pool will be larger, and every
  dollar that moves into it comes out of a direct objective, so this number
  moves the indirect rate in both the numerator and the denominator.
- **DIG-ENG carries 30,700.46 of 2025 labor** against an ICAM budget of
  655,190 over a 24-month period of performance ending 9 July 2025. Either
  the effort distribution understates what was worked, or the award was
  substantially underperformed. It is the newest of the three federal awards
  and the one nobody has been costing.

## 7. What the indirect rate still needs

The rate is not computable and the system will not pretend otherwise —
`POST /api/rates/compute` refuses an unsealed decision set, and the seal
refuses an unfinished classification.

| Blocker | Size | Nature |
|---|---:|---|
| Classification | 999 groups, 17,057,405.96, **0 decided** | Tom's judgment. 485 groups (36.2% of dollars) carry a system proposal to accept or reject; 514 have no signal. |
| Labor certification | 43 employees, **0 signed** | Each person's own 2 CFR 200.430(i) attestation. Weakest grade across all 43 is MANAGEMENT RECONSTRUCTION. |
| Square footage by tenant and function | — | Drives the facilities carve-out. The 2025 lease schedule gives rent by tenant and building; it gives no area. |
| Funding source per asset | 23.4M of cost | 200.436(b). The EDA award (1,903,179 federal) and JobsOhio (475,000 non-federal) are now on file; splitting the building additions between them is the work. |

The largest single open judgment remains `5227 Portfolio consulting` —
810,847.93 in the ESP programme with no objective signal, plus a further
~400,000 across named payees.

## 8. Two defects this run found

**`v_depreciation_basis.depreciation_expensed` overstated by 51.6%.** It read
depreciation as `sum(abs(amount)) WHERE account ILIKE '%depreciation%'` with
no scope, which caught `1570 TBB5:1502 TBB5 Accumulated Depreciation` — a
contra-asset — and `abs()` turned its credit into an addition. It reported
1,289,255.94 against a ledger that expensed 850,382.89. It matched exactly one
of the six A/D accounts because that one spells the word out where the others
say "Accum. Depr." or "A/D"; a pattern that catches one sixth of a class is
worse than one that catches none, because the total looks plausible. Fixed in
migration 032 by scoping to `pl_account` and dropping `abs()`.

**`ASSET_REGISTER` reported a variance where it had no data.** With no
register loaded it showed register 0.00 against ledger 850,382.89 and called
the difference a variance — "the register disagrees by 850,382.89" when the
truth is "there is no register". Migration 029 established the rule for the
other eleven controls; this one lives in the audit package and never got it.
Now reports `NO DATA` and names what it needs.
