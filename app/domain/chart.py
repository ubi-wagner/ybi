"""
The 2026 chart of accounts.

The structural problem with the 2025 chart is that program identity is baked
into account names: "Drive AM", "LTM Grant", "Rising Tides Expense",
"AAMEN Grant", "Digital Engineering". Eighty-five expense accounts, and every
new award means new accounts. Worse, a single account mixes natural expense
types — "Drive AM" contains consulting, travel and materials — so the account
tells you which program but not what was bought, and the pool has to be
reconstructed by hand every year.

The fix is to move program identity off the account and into the fields
QuickBooks already has for it, then let the account number carry the cost
pool. After that, four dimensions come off every transaction with no
classification work at all:

    Account number  ->  cost pool          (first digit)
    Class           ->  Form 990 function
    Customer:Job    ->  final cost objective
    Location        ->  facility, for the space allocation

That is the same four-dimension model the classification queue records by
hand for 2025. For 2026 the books produce it directly, which is the whole
point: 2025 is remediation, 2026 onward is bookkeeping.

Numbering:

    1000-1999  Assets                  4400-4499  Rental income
    2000-2999  Liabilities             4500-4599  Contributions
    3000-3999  Net assets              4900-4999  Other income
    4100-4199  Federal award revenue   5000-5999  DIRECT program cost
    4200-4299  State and local         6000-6999  FRINGE
    4300-4399  Program service         7000-7999  FACILITIES / overhead
                                       8000-8999  G&A
                                       9100-9199  FUNDRAISING and B&P
                                       9200-9299  UNALLOWABLE (2 CFR 200.420-475)
                                       9300-9399  RENTAL-DIRECT (tenant space)
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .core import PoolType, Function990, FederalTreatment, money

# Cost pool is a function of the account number's leading digits. This is the
# load-bearing idea: classification for 2026 is arithmetic, not judgment.
POOL_RANGES: list[tuple[int, int, PoolType]] = [
    (5000, 5999, PoolType.DIRECT),
    (6000, 6999, PoolType.FRINGE),
    (7000, 7999, PoolType.OVERHEAD),
    (8000, 8999, PoolType.GA),
    (9100, 9199, PoolType.FUNDRAISING),
    (9200, 9299, PoolType.UNALLOWABLE),
    (9300, 9399, PoolType.RENTAL_DIRECT),
]


def pool_for(account_number: str) -> PoolType | None:
    try:
        n = int(str(account_number).strip()[:4])
    except (ValueError, TypeError):
        return None
    for lo, hi, pool in POOL_RANGES:
        if lo <= n <= hi:
            return pool
    return None


@dataclass(frozen=True)
class Account:
    number: str
    name: str
    qbo_type: str
    detail_type: str
    description: str = ""
    parent: str = ""
    function_990: Function990 = Function990.NOT_APPLICABLE
    federal: FederalTreatment = FederalTreatment.PENDING
    mtdc: bool = True          # in the MTDC base under 2 CFR 200.1
    citation: str = ""

    @property
    def pool(self) -> PoolType | None:
        return pool_for(self.number)

    @property
    def full_name(self) -> str:
        return f"{self.parent}:{self.name}" if self.parent else self.name


P, MG, FR, NA = (Function990.PROGRAM, Function990.MGMT_GENERAL,
                 Function990.FUNDRAISING, Function990.NOT_APPLICABLE)
ALLOW, UNALLOW, NAPP = (FederalTreatment.ALLOWABLE, FederalTreatment.UNALLOWABLE,
                        FederalTreatment.NOT_APPLICABLE)


def _a(number, name, qbo_type, detail, desc="", parent="", fn=NA, fed=NAPP,
       mtdc=True, cite=""):
    return Account(number, name, qbo_type, detail, desc, parent, fn, fed, mtdc, cite)


# --------------------------------------------------------------------------
# Balance sheet — carried over structurally, renumbered into clean ranges.
# The asset accounts matter more than they look: the depreciation carve-out
# under 200.436(b) depends on knowing the funding source of each asset, so
# funded-asset cost is segregated at the account level rather than tracked in
# a side spreadsheet.
# --------------------------------------------------------------------------

BALANCE_SHEET = [
    _a("1010", "Operating account", "Bank", "Checking"),
    _a("1011", "Savings", "Bank", "Savings"),
    _a("1100", "Accounts receivable", "Accounts receivable", "Accounts Receivable (A/R)"),
    _a("1150", "Pledges receivable", "Other Current Assets", "Other Current Assets"),
    _a("1160", "Grants receivable", "Other Current Assets", "Other Current Assets",
       "Federal and state award receivables"),
    _a("1200", "Prepaid expenses", "Other Current Assets", "Prepaid Expenses"),
    _a("1250", "Inventory", "Other Current Assets", "Inventory"),

    _a("1500", "Land", "Fixed Assets", "Land"),
    _a("1510", "Buildings", "Fixed Assets", "Buildings"),
    _a("1511", "Buildings — privately funded", "Fixed Assets", "Buildings",
       "Depreciation on this basis is allowable", parent="1510 Buildings",
       fed=ALLOW, cite="2 CFR 200.436"),
    _a("1512", "Buildings — federally or state funded", "Fixed Assets", "Buildings",
       "Depreciation on this basis is UNALLOWABLE — segregated at source",
       parent="1510 Buildings", fed=UNALLOW, cite="2 CFR 200.436(b)"),
    _a("1520", "Capital improvements", "Fixed Assets", "Leasehold Improvements"),
    _a("1521", "Capital improvements — privately funded", "Fixed Assets",
       "Leasehold Improvements", parent="1520 Capital improvements", fed=ALLOW),
    _a("1522", "Capital improvements — federally or state funded", "Fixed Assets",
       "Leasehold Improvements", "Depreciation UNALLOWABLE",
       parent="1520 Capital improvements", fed=UNALLOW, cite="2 CFR 200.436(b)"),
    _a("1530", "Equipment", "Fixed Assets", "Machinery & Equipment"),
    _a("1531", "Equipment — privately funded", "Fixed Assets", "Machinery & Equipment",
       parent="1530 Equipment", fed=ALLOW),
    _a("1532", "Equipment — federally or state funded", "Fixed Assets",
       "Machinery & Equipment", "Depreciation UNALLOWABLE",
       parent="1530 Equipment", fed=UNALLOW, cite="2 CFR 200.436(b)"),
    _a("1540", "Construction in progress", "Fixed Assets", "Buildings"),
    _a("1590", "Accumulated depreciation", "Fixed Assets", "Accumulated Depreciation"),

    _a("2000", "Accounts payable", "Accounts payable", "Accounts Payable (A/P)"),
    _a("2100", "Accrued liabilities", "Other Current Liabilities", "Other Current Liabilities"),
    _a("2110", "Accrued payroll", "Other Current Liabilities", "Payroll Clearing"),
    _a("2200", "Deferred revenue", "Other Current Liabilities", "Deferred Revenue",
       "Award advances and cost-share deferrals"),
    _a("2500", "Lines of credit", "Other Current Liabilities", "Line of Credit"),
    _a("2600", "Notes payable", "Long Term Liabilities", "Notes Payable"),

    _a("3000", "Net assets without donor restrictions", "Equity", "Retained Earnings"),
    _a("3100", "Net assets with donor restrictions", "Equity", "Retained Earnings"),
]

# --------------------------------------------------------------------------
# Revenue. Program identity moves to Customer:Job, so one federal-award
# revenue account serves every award instead of one per award.
# --------------------------------------------------------------------------

REVENUE = [
    _a("4100", "Federal award revenue", "Income", "Sales of Product Income",
       "Use Customer:Job for the award. Do not create per-award accounts.", fn=P, fed=ALLOW),
    _a("4110", "Federal award revenue — pass-through", "Income", "Sales of Product Income",
       "Subrecipient awards received through a pass-through entity",
       parent="4100 Federal award revenue", fn=P, fed=ALLOW),
    _a("4200", "State and local program revenue", "Income", "Sales of Product Income",
       "ODSA, MBAC and similar", fn=P),
    _a("4300", "Program service revenue", "Income", "Service/Fee Income", fn=P),
    _a("4310", "Manufacturing and technical services", "Income", "Service/Fee Income",
       parent="4300 Program service revenue", fn=P),
    _a("4400", "Rental income", "Income", "Other Primary Income",
       "Tenant leases. Pairs with the 9300 rental-direct pool.", fn=P, fed=NAPP),
    _a("4410", "Rental income — incubator tenants", "Income", "Other Primary Income",
       parent="4400 Rental income", fn=P),
    _a("4420", "Rental income — commercial tenants", "Income", "Other Primary Income",
       parent="4400 Rental income", fn=P),
    _a("4500", "Contributions — unrestricted", "Income", "Non-Profit Income", fn=P),
    _a("4510", "Contributions — restricted", "Income", "Non-Profit Income", fn=P),
    _a("4520", "Sponsorships", "Income", "Non-Profit Income",
       "Event sponsorship. Pairs with the 9100 fundraising pool.", fn=FR),
    _a("4900", "Other income", "Other Income", "Other Miscellaneous Income"),
    _a("4910", "Interest income", "Other Income", "Interest Earned"),
]

# --------------------------------------------------------------------------
# 5000 DIRECT — natural expense types, not programs. The Customer:Job field
# says which program; the account says what was bought.
# --------------------------------------------------------------------------

DIRECT = [
    _a("5000", "Direct salaries and wages", "Expense", "Payroll Expenses",
       "Charged to a Customer:Job by timesheet", fn=P, fed=ALLOW, cite="2 CFR 200.430"),
    _a("5010", "Direct wages — interns and students", "Expense", "Payroll Expenses",
       parent="5000 Direct salaries and wages", fn=P, fed=ALLOW),
    _a("5100", "Consultants and professional services — direct", "Expense",
       "Legal & Professional Fees", fn=P, fed=ALLOW, cite="2 CFR 200.459"),
    _a("5110", "Portfolio and advisory services", "Expense", "Legal & Professional Fees",
       "Requires a Customer:Job. If it benefits no single objective it is not direct.",
       parent="5100 Consultants and professional services — direct", fn=P, fed=ALLOW),
    _a("5200", "Subawards and subcontracts", "Expense", "Other Business Expenses",
       "MTDC includes only the first $25,000 of each subaward",
       fn=P, fed=ALLOW, mtdc=False, cite="2 CFR 200.1 (MTDC)"),
    _a("5300", "Materials and supplies — direct", "Expense", "Supplies & Materials", fn=P, fed=ALLOW),
    _a("5400", "Equipment — direct, under capitalisation threshold", "Expense",
       "Office Expenses", fn=P, fed=ALLOW),
    _a("5410", "Equipment rental — direct", "Expense", "Equipment Rental", fn=P, fed=ALLOW),
    _a("5500", "Travel — direct", "Expense", "Travel",
       "Joint Travel Regulations apply on federal awards", fn=P, fed=ALLOW,
       cite="2 CFR 200.475"),
    _a("5510", "Conferences and training — direct", "Expense", "Travel Meals",
       fn=P, fed=ALLOW, cite="2 CFR 200.432"),
    _a("5600", "Participant and client support", "Expense", "Other Business Expenses",
       "Excluded from MTDC", fn=P, fed=ALLOW, mtdc=False, cite="2 CFR 200.456"),
    _a("5700", "Cost of goods sold", "Cost of Goods Sold", "Supplies & Materials", fn=P),
    _a("5900", "Cost share — direct", "Expense", "Other Business Expenses",
       "Committed cost share. Track here so 200.306 can be evidenced.",
       fn=P, fed=ALLOW, cite="2 CFR 200.306"),
]

FRINGE = [
    _a("6000", "Health and welfare benefits", "Expense", "Payroll Expenses",
       fn=NA, fed=ALLOW, cite="2 CFR 200.431"),
    _a("6100", "FICA and Medicare", "Expense", "Taxes Paid", fn=NA, fed=ALLOW),
    _a("6200", "Retirement and 401(k) match", "Expense", "Payroll Expenses", fn=NA, fed=ALLOW),
    _a("6300", "Unemployment insurance", "Expense", "Taxes Paid", fn=NA, fed=ALLOW),
    _a("6400", "Workers compensation", "Expense", "Insurance", fn=NA, fed=ALLOW),
    _a("6500", "Paid leave accrual", "Expense", "Payroll Expenses", fn=NA, fed=ALLOW),
]

OVERHEAD = [
    _a("7000", "Depreciation — buildings", "Expense", "Depreciation",
       "Post by funding source: 1511 basis is allowable, 1512 is not",
       fn=P, fed=ALLOW, cite="2 CFR 200.436"),
    _a("7010", "Depreciation — capital improvements", "Expense", "Depreciation", fn=P, fed=ALLOW),
    _a("7020", "Depreciation — equipment", "Expense", "Depreciation", fn=P, fed=ALLOW),
    _a("7100", "Building maintenance and repair", "Expense", "Repair & Maintenance", fn=P, fed=ALLOW),
    _a("7110", "Janitorial", "Expense", "Repair & Maintenance", fn=P, fed=ALLOW),
    _a("7120", "Grounds and waste removal", "Expense", "Repair & Maintenance", fn=P, fed=ALLOW),
    _a("7130", "Security", "Expense", "Repair & Maintenance", fn=P, fed=ALLOW),
    _a("7200", "Electricity", "Expense", "Utilities", fn=P, fed=ALLOW),
    _a("7210", "Gas and heating", "Expense", "Utilities", fn=P, fed=ALLOW),
    _a("7220", "Water and sewer", "Expense", "Utilities", fn=P, fed=ALLOW),
    _a("7230", "Telecommunications and internet", "Expense", "Utilities", fn=P, fed=ALLOW),
    _a("7300", "Property insurance", "Expense", "Insurance", fn=P, fed=ALLOW),
    _a("7310", "Real estate and property tax", "Expense", "Taxes Paid", fn=P, fed=ALLOW,
       cite="2 CFR 200.470"),
    _a("7400", "Rent and lease — occupied by YBI", "Expense", "Rent or Lease of Buildings",
       fn=P, fed=ALLOW),
]

GA = [
    _a("8000", "Administrative salaries and wages", "Expense", "Payroll Expenses",
       "Executive, finance and administration", fn=MG, fed=ALLOW),
    _a("8100", "Accounting, audit and tax", "Expense", "Legal & Professional Fees",
       "G&A by nature. Do not direct-charge to an award — 200.403(d).",
       fn=MG, fed=ALLOW, cite="2 CFR 200.403(d), 200.435"),
    _a("8110", "Legal", "Expense", "Legal & Professional Fees", fn=MG, fed=ALLOW),
    _a("8120", "Other professional services", "Expense", "Legal & Professional Fees",
       fn=MG, fed=ALLOW),
    _a("8200", "Office expenses and supplies", "Expense", "Office Expenses", fn=MG, fed=ALLOW),
    _a("8210", "Postage and delivery", "Expense", "Office Expenses", fn=MG, fed=ALLOW),
    _a("8220", "Software and subscriptions", "Expense", "Office Expenses", fn=MG, fed=ALLOW),
    _a("8230", "Dues and memberships", "Expense", "Dues & Subscriptions",
       "Memberships in civic or community organisations are unallowable — use 9230",
       fn=MG, fed=ALLOW, cite="2 CFR 200.454"),
    _a("8300", "General liability and D&O insurance", "Expense", "Insurance", fn=MG, fed=ALLOW),
    _a("8400", "Bank and merchant fees", "Expense", "Bank Charges", fn=MG, fed=ALLOW),
    _a("8410", "Payroll processing", "Expense", "Payroll Expenses", fn=MG, fed=ALLOW),
    _a("8500", "Staff training and development", "Expense", "Other Business Expenses",
       fn=MG, fed=ALLOW, cite="2 CFR 200.432"),
    _a("8600", "Administrative travel", "Expense", "Travel", fn=MG, fed=ALLOW),
    _a("8700", "IT infrastructure and support", "Expense", "Office Expenses", fn=MG, fed=ALLOW),
]

FUNDRAISING = [
    _a("9100", "Fundraising salaries and wages", "Expense", "Payroll Expenses",
       fn=FR, fed=UNALLOW, cite="2 CFR 200.442"),
    _a("9110", "Event costs", "Expense", "Advertising/Promotional",
       "Shark Tank, AMUX, EmpowerUS and similar", fn=FR, fed=UNALLOW),
    _a("9120", "Donor development and advertising", "Expense", "Advertising/Promotional",
       fn=FR, fed=UNALLOW, cite="2 CFR 200.421"),
    _a("9130", "Bid and proposal costs", "Expense", "Other Business Expenses",
       "B&P is unallowable as a direct charge but bears its share of indirect",
       fn=MG, fed=UNALLOW),
]

UNALLOWABLE = [
    _a("9200", "Interest expense", "Other Expense", "Interest Paid",
       "Interest on debt to acquire or improve a building may be allowable — "
       "review against 200.449 before defaulting here",
       fn=MG, fed=UNALLOW, cite="2 CFR 200.449"),
    _a("9210", "Bad debt", "Expense", "Bad Debts", fn=MG, fed=UNALLOW, cite="2 CFR 200.426"),
    _a("9220", "Meals and entertainment", "Expense", "Entertainment Meals",
       fn=MG, fed=UNALLOW, cite="2 CFR 200.438"),
    _a("9230", "Lobbying and government relations", "Expense", "Other Business Expenses",
       "Unallowable federally AND triggers Schedule C on the Form 990",
       fn=MG, fed=UNALLOW, cite="2 CFR 200.450"),
    _a("9240", "Contributions and donations made", "Expense", "Charitable Contributions",
       fn=MG, fed=UNALLOW, cite="2 CFR 200.434"),
    _a("9250", "Fines and penalties", "Expense", "Other Business Expenses",
       fn=MG, fed=UNALLOW, cite="2 CFR 200.441"),
    _a("9260", "Alcohol", "Expense", "Entertainment Meals",
       fn=MG, fed=UNALLOW, cite="2 CFR 200.423"),
]

RENTAL_DIRECT = [
    _a("9300", "Rental operations — depreciation", "Expense", "Depreciation",
       "Tenant space is not allocable to federal awards. Segregating it here "
       "removes the carve-out judgment from the rate build entirely.",
       fn=P, fed=NAPP, cite="2 CFR 200.405"),
    _a("9310", "Rental operations — maintenance", "Expense", "Repair & Maintenance",
       fn=P, fed=NAPP),
    _a("9320", "Rental operations — utilities", "Expense", "Utilities", fn=P, fed=NAPP),
    _a("9330", "Rental operations — insurance and tax", "Expense", "Insurance", fn=P, fed=NAPP),
    _a("9340", "Rental operations — management", "Expense", "Other Business Expenses",
       fn=P, fed=NAPP),
]

CHART: list[Account] = (BALANCE_SHEET + REVENUE + DIRECT + FRINGE + OVERHEAD
                        + GA + FUNDRAISING + UNALLOWABLE + RENTAL_DIRECT)

# --------------------------------------------------------------------------
# Classes carry the Form 990 functional dimension. Kept deliberately short —
# a long class list is how class tracking dies.
# --------------------------------------------------------------------------

CLASSES = [
    ("Program", "Program services — Form 990 Part IX column B"),
    ("Program:Federal awards", "Work performed under federal awards and subawards"),
    ("Program:State and local", "ODSA, MBAC and other state or local programs"),
    ("Program:Incubation and rental", "Tenant and incubation operations"),
    ("Program:Manufacturing services", "Fee-for-service technical work"),
    ("Management & General", "Form 990 Part IX column C"),
    ("Fundraising", "Form 990 Part IX column D"),
]

# --------------------------------------------------------------------------
# Customers and jobs carry the cost objective. Federal awards are jobs under a
# funder so the QBO Customer:Job export already reads as "funder:award" — the
# format the importer parses today.
# --------------------------------------------------------------------------

CUSTOMER_JOBS = [
    ("NCDMM - America Makes", None, "Pass-through, AFRL FA8650-20-2-5700"),
    ("NCDMM - America Makes", "Drive AM", "Federal award"),
    ("NCDMM - America Makes", "Hybrid II", "Federal award"),
    ("NCDMM - America Makes", "Last Tactical Mile", "Federal award"),
    ("NCDMM - America Makes", "Digital Engineering", "Federal award"),
    ("Parallax Advanced Research", None, "Pass-through"),
    ("Parallax Advanced Research", "AAMEN", "Federal award"),
    ("Appalachian Regional Commission", None, "Federal agency"),
    ("Appalachian Regional Commission", "Rising Tides", "Federal determination pending"),
    ("Defense Logistics Agency", "DLA", "Federal award"),
    ("Ohio Development Services Agency", None, "State agency"),
    ("Ohio Development Services Agency", "ESP", "State program"),
    ("Ohio Development Services Agency", "MBAC", "State program"),
    ("JumpStart Inc", None, "Program funder"),
    ("YBI Internal", "General administration", "G&A carrier"),
    ("YBI Internal", "Fundraising", "Fundraising carrier"),
    ("YBI Internal", "Rental operations", "Landlord operations"),
    ("YBI Internal", "Youth entrepreneurship", "Program"),
    ("YBI Internal", "IIOT", "Program"),
    ("YBI Internal", "VGV investment fund", "Program"),
]


# --------------------------------------------------------------------------
# Exporters — QuickBooks Online import format
# --------------------------------------------------------------------------

def _csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\r\n").writerows(rows)
    return buf.getvalue()


def chart_csv() -> str:
    """QBO: Settings -> Chart of accounts -> Import. Turn on account numbers
    first (Settings -> Advanced -> Chart of accounts -> Enable account numbers),
    or the numbers that carry the pool assignment are discarded on import."""
    rows = [["Account Number", "Account Name", "Account Type", "Detail Type", "Description"]]
    for a in CHART:
        note = a.description
        if a.citation:
            note = f"{note} [{a.citation}]".strip()
        rows.append([a.number, a.full_name, a.qbo_type, a.detail_type, note])
    return _csv(rows)


def classes_csv() -> str:
    rows = [["Class Name", "Description"]]
    rows.extend([[n, d] for n, d in CLASSES])
    return _csv(rows)


def customers_csv() -> str:
    """QBO customer import. Sub-customers become the ':job' segment that the
    ledger importer already reads as the cost objective."""
    rows = [["Customer", "Sub-customer of", "Notes", "Bill with parent"]]
    for parent, job, note in CUSTOMER_JOBS:
        if job is None:
            rows.append([parent, "", note, ""])
        else:
            rows.append([job, parent, note, "N"])
    return _csv(rows)


def mapping_rows() -> list[dict]:
    """Machine-readable pool assignment. This is what makes 2026 classification
    automatic: the importer reads the account number and the pool follows."""
    out = []
    for a in CHART:
        pool = a.pool
        out.append({
            "account_number": a.number,
            "account_name": a.full_name,
            "qbo_type": a.qbo_type,
            "pool": pool.value if pool else "",
            "function_990": a.function_990.value,
            "federal": a.federal.value,
            "in_mtdc_base": "Y" if (pool is PoolType.DIRECT and a.mtdc) else
                            ("N" if pool is PoolType.DIRECT else ""),
            "citation": a.citation,
            "description": a.description,
        })
    return out


def write_all(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "chart": out_dir / "YBI_2026_Chart_of_Accounts_QBO.csv",
        "classes": out_dir / "YBI_2026_Classes_QBO.csv",
        "customers": out_dir / "YBI_2026_Customers_Jobs_QBO.csv",
    }
    files["chart"].write_text(chart_csv(), encoding="utf-8")
    files["classes"].write_text(classes_csv(), encoding="utf-8")
    files["customers"].write_text(customers_csv(), encoding="utf-8")
    return files


def summary() -> dict:
    by_pool: dict[str, int] = {}
    for a in CHART:
        key = a.pool.value if a.pool else a.qbo_type
        by_pool[key] = by_pool.get(key, 0) + 1
    return {"accounts": len(CHART), "classes": len(CLASSES),
            "customer_jobs": len(CUSTOMER_JOBS), "by_pool": by_pool}
