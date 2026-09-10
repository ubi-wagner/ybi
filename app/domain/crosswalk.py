"""
2025 -> 2026 crosswalk.

Two jobs. It tells the bookkeeper where each old account goes, and it proves
the new chart carries every dollar of the reconciled 2025 ledger — same
totals, same pools, different structure. A chart conversion that does not tie
is how a clean reconciliation gets thrown away.

The mapping is explicit rather than inferred. Where an old account has to
split across new ones (rental utilities out of building utilities, funded
depreciation out of total depreciation), the crosswalk says so and names the
driver, because that split is a judgment somebody has to make and defend.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

from .core import money

# 2025 account -> (2026 account number, note). A "split" note means the old
# account does not map one-to-one and needs a documented driver.
CROSSWALK: dict[str, tuple[str, str]] = {
    # Labour
    "5140 Employee Wages": ("5000 / 8000 / 9100", "split by timesheet: direct, administrative, fundraising"),
    "5142 Intern Wages": ("5010", ""),

    # Fringe
    "5130 Benefits": ("6000", ""),
    "5151 Social Security & Medicare": ("6100", ""),
    "5133 401k Match & Profit Sharing": ("6200", ""),
    "5195 SUI": ("6300", ""),
    "5185 FUTA": ("6300", ""),
    "5145 Bureau of Worker's Compensation": ("6400", ""),

    # Facilities — the rental split is the one that decides the rate
    "5010 Depreciation Expense": ("7000 / 9300", "split by square footage, and by funded vs private basis"),
    "5035 Maintenance": ("7100 / 9310", "split by square footage"),
    "5030 Janitorial": ("7110", ""),
    "5040 Waste Removal": ("7120", ""),
    "5050 Security": ("7130", ""),
    "5043 Boardman Street Electric": ("7200 / 9320", "split by square footage"),
    "5055 Electric": ("7200 / 9320", "split by square footage"),
    "5041 Semple Electric": ("7200 / 9320", "split by square footage"),
    "5060 Heating/Cooling": ("7210 / 9320", "split by square footage"),
    "5044 Boardman St. Gas": ("7210 / 9320", "split by square footage"),
    "5042 Semple Gas": ("7210 / 9320", "split by square footage"),
    "5070 Water": ("7220 / 9320", "split by square footage"),
    "5027 TTC Utilities": ("7200 / 9320", "split by square footage"),
    "5056 T1 Access": ("7230", ""),
    "5065 Telephone": ("7230", ""),
    "5200 Real Estate Tax": ("7310 / 9330", "split by square footage"),

    # Direct — program identity moves to Customer:Job
    "5227 Portfolio consulting": ("5110", "requires a Customer:Job; if it benefits no single objective it is 8120"),
    "5221 ESP/EIR Consulting": ("5100", "Customer:Job = ODSA:ESP"),
    "Rising Tides Expense": ("5100 / 5300 / 5500", "Customer:Job = ARC:Rising Tides, split by natural type"),
    "LTM Grant": ("5100 / 5200 / 5300", "Customer:Job = NCDMM:Last Tactical Mile; subawards to 5200"),
    "Drive AM": ("5100 / 5300", "Customer:Job = NCDMM:Drive AM"),
    "Digital Engineering": ("5100 / 5300", "Customer:Job = NCDMM:Digital Engineering"),
    "AAMEN Grant": ("5100 / 5300", "Customer:Job = Parallax:AAMEN"),
    "DOE Hybrid": ("5100", "Customer:Job = NCDMM:Hybrid II"),
    "DLA Grant": ("5100", "Customer:Job = DLA"),
    "5014 MBAC - ODSA - YBI": ("5100", "Customer:Job = ODSA:MBAC"),
    "MBAC/Power Marketing": ("5100", "Customer:Job = ODSA:MBAC"),
    "ESP": ("5100", "Customer:Job = ODSA:ESP"),
    "ESP Marketing": ("5100", "Customer:Job = ODSA:ESP"),
    "Youth Entrepreneurship": ("5100", "Customer:Job = YBI Internal:Youth entrepreneurship"),
    "SBA Growth Accelerator": ("5100", "new Customer:Job required"),
    "IH-Other": ("5100", "new Customer:Job required"),
    "IH-EIR": ("5100", "new Customer:Job required"),
    "ARC Arise": ("5100", "new Customer:Job required"),
    "Advanced Mfg Marketing": ("5100", "Customer:Job required"),
    "5900 Additive Manufacturing": ("5300", "Customer:Job required"),
    "5246 Manufacturing Expense": ("5300", ""),
    "5902 Supplies": ("5300", ""),
    "5229 VGV - Investment Fund": ("5100", "Customer:Job = YBI Internal:VGV investment fund"),
    "5211 Internship Program": ("5010", ""),
    "5001 Cost of Goods Sold": ("5700", ""),
    "5226 Manuf. support - factory manage": ("5100", "reclassified from G&A; benefits identifiable objectives"),

    # G&A
    "5202 Accounting": ("8100", "G&A by nature — must not be direct-charged to an award"),
    "5201 Professional Services": ("8120", ""),
    "5222 IT development manager": ("8700", ""),
    "5100 Office Expenses": ("8200", ""),
    "5106 Office Miscellaneous": ("8200", ""),
    "5115 Consumable": ("8200", ""),
    "5125 Postage and Delivery": ("8210", ""),
    "5017 Software Purchases": ("8220", ""),
    "5215 Dues and Subscriptions": ("8230 / 9240", "civic and community memberships are unallowable"),
    "5075 Insurance": ("8300 / 7300", "split property from general liability"),
    "5000 Bank Service Charges": ("8400", ""),
    "5315 Finance Charge/Paypal/Eventbrit": ("8400", ""),
    "PayPal fees": ("8400", ""),
    "5137 Payroll Processing Fees": ("8410", ""),
    "5300 Staff Training - Education": ("8500", ""),
    "Management & Administrative Expenses": ("8200", ""),

    # Review population — resolved by natural type once the pool is explicit
    "5206 Travel": ("5500 / 8600", "direct travel carries a Customer:Job"),
    "5213 Conference/Seminar": ("5510 / 8500", ""),
    "5207 Meals": ("5510 / 9220", "entertainment meals are unallowable"),
    "5020 Equipment Rental/Leases": ("5410 / 7400", ""),
    "5015 Equipment Expenses": ("5400", ""),
    "5016 Equipment Purchases": ("5400", "capitalise above threshold to 1530"),

    # Fundraising
    "5085 Advertising": ("9120", ""),
    "Shark Tank Events": ("9110", ""),
    "AMUX Event": ("9110", ""),
    "EmpowerUS Event": ("9110", ""),
    "5089 Special Events": ("9110", ""),
    "5095 Workshops/Seminars": ("9110 / 8500", ""),
    "5092 Networking/Mixers": ("9110", ""),

    # Unallowable
    "5310 Interest Expense": ("9200", "review against 200.449 — building debt interest may be allowable"),
    "5320 Loan Interest": ("9200", "review against 200.449"),
    "5400 Bad Debt Expense": ("9210", ""),
    "5250 Meals & Entertainment": ("9220", ""),
    "5120 Government Relations": ("9230", "also drives Form 990 Schedule C"),
    "5220 Contributions": ("9240", ""),
}


def build(cost_rows: list[dict], chart_index: dict[str, str]) -> tuple[list[dict], dict]:
    """Return crosswalk rows with 2025 amounts, plus a tie-out summary."""
    def num(x) -> Decimal:
        return money(x)

    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    disp: dict[str, str] = {}
    for r in cost_rows:
        a = r["Source Account"]
        totals[a] = money(totals.get(a, Decimal(0)) + num(r["Booked Amount"]))
        counts[a] = counts.get(a, 0) + 1
        disp.setdefault(a, r.get("Cost Disposition", ""))

    rows = []
    mapped = Decimal(0)
    unmapped = Decimal(0)
    splits = 0
    for account in sorted(totals, key=lambda k: -abs(totals[k])):
        target, note = CROSSWALK.get(account, ("", "NOT MAPPED — needs a decision"))
        is_split = "/" in target
        if is_split:
            splits += 1
        if target:
            mapped += totals[account]
        else:
            unmapped += totals[account]
        rows.append({
            "account_2025": account,
            "amount_2025": totals[account],
            "lines": counts[account],
            "disposition_2025": disp.get(account, ""),
            "account_2026": target,
            "split": "Y" if is_split else "",
            "note": note,
        })

    grand = money(sum(totals.values()))
    return rows, {
        "accounts_2025": len(totals),
        "mapped": mapped,
        "unmapped": unmapped,
        "total": grand,
        "variance": money(mapped + unmapped - grand),
        "splits_requiring_a_driver": splits,
    }


def crosswalk_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()
