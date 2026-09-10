#!/usr/bin/env python3
"""
FY2025 illustrative indirect cost rate scenarios for The Youngstown Edison
Incubator Corporation (dba Youngstown Business Incubator).

ILLUSTRATIVE ONLY. This is a sizing exercise, not an indirect cost proposal.
It is built from:
  - 2025 QuickBooks Profit and Loss (accrual, printed 2026-08-21)
  - 2025 labor distribution per the controller's Grant Reconciliation Workbook,
    sheet "Time Breakdown", row 143 ("JOB SUM")
  - Management-provided square footage split: 50% tenant / 30% program / 20% admin

Open items that will move these numbers materially are listed in
docs/analysis/indirect-cost-framework.md, section 9.

Run: python3 fy2025_indirect_rate_scenarios.py
"""
from decimal import Decimal as D, ROUND_HALF_UP

def d(x):
    return D(str(x))

def pct(n, b):
    return (n / b * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)

def money(x):
    return f"{x.quantize(D('0.01'), rounding=ROUND_HALF_UP):>14,}"

# ---------------------------------------------------------------- 2025 payroll
WAGES_PL          = d("1789993.94")   # P&L 5139 Wages (1678157.27 + 111836.67)
WAGES_TIMESHEET   = d("1834993.97")   # Grant Recon Workbook "Time Breakdown" W143
BENEFITS          = d("194353.59")    # 5130
MATCH_401K        = d("56519.42")     # 5133
PAYROLL_TAXES     = d("150910.59")    # 5141
PAYROLL_FEES      = d("5236.70")      # 5137 (treated as G&A, not fringe)

FRINGE_POOL = BENEFITS + MATCH_401K + PAYROLL_TAXES
FRINGE_RATE = (FRINGE_POOL / WAGES_PL)

# ------------------------------------- 2025 labor distribution ("Time Breakdown")
LABOR_GA          = d("264444.89")    # col V  Adj-YBI        -> M&A
LABOR_FUNDRAISING = d("40088.80")     # col K  Adj-Fundraising -> unallowable
LABOR_DIRECT      = WAGES_TIMESHEET - LABOR_GA - LABOR_FUNDRAISING

# --------------------------------------------------------- 2025 other expenses
MA_EXPENSES       = d("936268.91")    # Management & Administrative Expenses total
UNALLOW_CONTRIB   = d("1000.00")      # 5220 Contributions           (200.434)
UNALLOW_MEALS_ENT = d("28426.52")     # 5250 Meals & Entertainment   (200.438)
UNALLOW_BAD_DEBT  = d("12037.85")     # 5400 Bad Debt Expense        (200.426)
FUNDRAISING       = d("306484.11")    # 5080 Fundraising             (200.442)

GRANT_EXPENSES    = d("1427690.83")   # partner / pass-through costs
PROGRAM_EXPENSES  = d("959071.57")    # program delivery costs
COGS              = d("37261.00")

# ------------------------------------------------------------ 2025 facilities
FACILITIES        = d("545193.59")    # 5024 Facilities Expense
REAL_ESTATE_TAX   = d("26526.66")     # 5200
INSURANCE         = d("57596.36")     # 5075
INTEREST          = d("49000.78")     # 5310  (200.449 conditions apply)
DEPRECIATION      = d("850382.89")    # 5010  (200.436(c) federal-share limits)
RENTAL_INCOME     = d("638862.21")    # 4015.1 Rent/Utilities

# Management-provided square footage allocation
SQFT_TENANT, SQFT_PROGRAM, SQFT_ADMIN = d("0.50"), d("0.30"), d("0.20")
SQFT_ALLOCABLE = SQFT_PROGRAM + SQFT_ADMIN   # 50% may reach the pool

FACILITIES_BASE = FACILITIES + REAL_ESTATE_TAX + INSURANCE

SCENARIOS = {
    "A - Conservative": {
        "note": "No depreciation, no interest in the pool. Assumes the asset base "
                "is effectively fully grant-funded (2 CFR 200.436(c)) and the "
                "200.449 interest conditions are not met.",
        "depreciation_pct": d("0.00"),
        "include_interest": False,
    },
    "B - Midpoint": {
        "note": "Half of depreciation allowed (assumes ~50% of the asset base was "
                "funded with non-federal money) plus allowable interest.",
        "depreciation_pct": d("0.50"),
        "include_interest": True,
    },
    "C - Upper bound": {
        "note": "All depreciation and interest in the pool. Only supportable if the "
                "fixed asset register shows little federal or state participation.",
        "depreciation_pct": d("1.00"),
        "include_interest": True,
    },
}


def run():
    print("=" * 78)
    print("FY2025 ILLUSTRATIVE INDIRECT COST RATE SCENARIOS")
    print("The Youngstown Edison Incubator Corporation dba Youngstown Business Incubator")
    print("=" * 78)

    print("\n--- FRINGE BENEFIT RATE (separate pool) " + "-" * 38)
    print(f"  Employee benefits (5130)              {money(BENEFITS)}")
    print(f"  401(k) match & profit sharing (5133)  {money(MATCH_401K)}")
    print(f"  Payroll taxes (5141)                  {money(PAYROLL_TAXES)}")
    print(f"  Fringe pool                           {money(FRINGE_POOL)}")
    print(f"  Salaries and wages base (5139)        {money(WAGES_PL)}")
    print(f"  FRINGE RATE                                  {pct(FRINGE_POOL, WAGES_PL)}%")
    print("  (Ties to the controller's Reference Sheet fringe rate of 22.45% for 2025.)")

    print("\n--- LABOR DISTRIBUTION (Time Breakdown row 143) " + "-" * 30)
    print(f"  Direct / program labor                {money(LABOR_DIRECT)}   "
          f"{pct(LABOR_DIRECT, WAGES_TIMESHEET)}%")
    print(f"  G&A labor (Adj-YBI)                   {money(LABOR_GA)}   "
          f"{pct(LABOR_GA, WAGES_TIMESHEET)}%")
    print(f"  Fundraising labor (unallowable)       {money(LABOR_FUNDRAISING)}   "
          f"{pct(LABOR_FUNDRAISING, WAGES_TIMESHEET)}%")
    print(f"  Total per timesheet workbook          {money(WAGES_TIMESHEET)}")
    print(f"  Total per P&L account 5139            {money(WAGES_PL)}")
    print(f"  *** UNRECONCILED VARIANCE ***         {money(WAGES_TIMESHEET - WAGES_PL)}")

    # Direct cost base (MTDC-style), two treatments of partner costs
    direct_fringe = (LABOR_DIRECT * FRINGE_RATE)
    base_full = LABOR_DIRECT + direct_fringe + GRANT_EXPENSES + PROGRAM_EXPENSES + COGS
    base_ex_subawards = base_full - GRANT_EXPENSES

    print("\n--- DIRECT COST BASE " + "-" * 57)
    print(f"  Direct labor                          {money(LABOR_DIRECT)}")
    print(f"  Fringe on direct labor                {money(direct_fringe)}")
    print(f"  Grant/partner expenses                {money(GRANT_EXPENSES)}")
    print(f"  Program expenses                      {money(PROGRAM_EXPENSES)}")
    print(f"  Cost of goods sold                    {money(COGS)}")
    print(f"  BASE - partner costs treated as vendor/consultant (in MTDC)")
    print(f"                                        {money(base_full)}")
    print(f"  BASE - partner costs treated as subawards (excluded beyond $25K each)")
    print(f"                                        {money(base_ex_subawards)}")
    print("  NOTE: the true MTDC base sits between these two. It depends on the")
    print("        subrecipient-vs-contractor determination under 2 CFR 200.331.")

    # G&A pool components common to all scenarios
    ga_labor_fringe = LABOR_GA * FRINGE_RATE
    ma_allowable = MA_EXPENSES - UNALLOW_CONTRIB - UNALLOW_MEALS_ENT

    print("\n--- INDIRECT POOL - COMMON COMPONENTS " + "-" * 40)
    print(f"  G&A labor                             {money(LABOR_GA)}")
    print(f"  Fringe on G&A labor                   {money(ga_labor_fringe)}")
    print(f"  M&A expenses                          {money(MA_EXPENSES)}")
    print(f"    less contributions (200.434)        {money(-UNALLOW_CONTRIB)}")
    print(f"    less meals & entertainment (200.438){money(-UNALLOW_MEALS_ENT)}")
    print(f"  M&A allowable                         {money(ma_allowable)}")
    print("\n  Excluded from the pool entirely:")
    print(f"    Fundraising (200.442)               {money(FUNDRAISING)}")
    print(f"    Fundraising labor (200.442)         {money(LABOR_FUNDRAISING)}")
    print(f"    Bad debt (200.426)                  {money(UNALLOW_BAD_DEBT)}")

    print("\n--- FACILITIES POOL AT 50/30/20 SQUARE FOOTAGE " + "-" * 31)
    print(f"  Facilities expense (5024)             {money(FACILITIES)}")
    print(f"  Real estate tax (5200)                {money(REAL_ESTATE_TAX)}")
    print(f"  Insurance (5075)                      {money(INSURANCE)}")
    print(f"  Subtotal before depreciation/interest {money(FACILITIES_BASE)}")
    print(f"  Interest (5310), 200.449 conditional  {money(INTEREST)}")
    print(f"  Depreciation (5010), 200.436(c) limit {money(DEPRECIATION)}")
    print(f"  Rental income received (4015.1)       {money(RENTAL_INCOME)}")
    print(f"  Tenant share excluded from pool       {SQFT_TENANT * 100:.0f}%  "
          "(cost of leased space is recovered through rent, not federal awards)")

    print("\n" + "=" * 78)
    print("SCENARIO RESULTS")
    print("=" * 78)
    results = {}
    for name, s in SCENARIOS.items():
        facilities_total = FACILITIES_BASE + (DEPRECIATION * s["depreciation_pct"])
        if s["include_interest"]:
            facilities_total += INTEREST
        facilities_pool = facilities_total * SQFT_ALLOCABLE
        pool = LABOR_GA + ga_labor_fringe + ma_allowable + facilities_pool
        r_full = pct(pool, base_full)
        r_ex = pct(pool, base_ex_subawards)
        results[name] = (pool, r_full, r_ex)
        print(f"\n{name}")
        print(f"  {s['note']}")
        print(f"    Facilities cost considered          {money(facilities_total)}")
        print(f"    x {SQFT_ALLOCABLE*100:.0f}% program+admin square footage {money(facilities_pool)}")
        print(f"    TOTAL INDIRECT POOL                 {money(pool)}")
        print(f"    Rate on broad base  (vendor view)          {r_full}%")
        print(f"    Rate on narrow base (subaward view)        {r_ex}%")

    print("\n" + "=" * 78)
    print("CONTEXT")
    print("=" * 78)
    print(f"  Rate currently elected and audited (2024 SEFA Note 2)       10.00%")
    print(f"  De minimis available on awards issued on/after 2024-10-01   15.00%")
    print(f"  Naive audited proxy: 2024 M&G / Program Services            13.63%")
    print(f"  Implied by Project 88 unrecovered indirect cost share       38.56%")
    print("\n  The Project 88 Schedule B booked $233,543.12 of 'unrecovered indirects'")
    print("  as cost share on a federal direct base of $817,728, which together with")
    print("  the $81,772.76 billed at de minimis implies a total rate of 38.56%.")
    print("  No workpaper supporting that rate has been produced to date.")


if __name__ == "__main__":
    run()
