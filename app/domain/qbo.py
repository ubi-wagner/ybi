"""
QuickBooks Online ingestion.

The thing that trips up QBO imports is that its exports are *reports*, not
tables. The General Ledger export is hierarchical: account section headers,
indented transaction rows, "Total for ..." subtotals, blank spacer rows, and
a running Balance column that is meaningless once the rows are extracted.
Column names also drift between QBO versions and between the "export to
Excel" and "export to CSV" paths.

So parsing is driven by a named ImportProfile rather than hardcoded column
positions. A new export shape is configuration, not a code change — and the
profile is stored with the import so a reviewer can see exactly how the file
was read two years later.

Every parse is a dry run until its control totals tie. Nothing reaches the
ledger tables on the strength of "it looked right".
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .core import money

# QBO writes negatives three ways depending on report and locale.
_PARENS = re.compile(r"^\((.*)\)$")
_TOTAL_ROW = re.compile(r"^\s*total\s+(for\s+)?", re.I)
_BEGIN_BAL = re.compile(r"beginning\s+balance", re.I)

# QuickBooks closes a parent account with "Total for <parent> with sub-accounts".
# That row is a subtree rollup, not a leaf total, and reconciling it against
# lines coded directly to the parent will always fail — most parents carry no
# direct lines at all.
_ROLLUP_SUFFIX = re.compile(r"\s+with\s+sub-?accounts\s*$", re.I)


def qbo_amount(raw) -> Decimal:
    """QBO emits 1,234.56 / (1,234.56) / -1,234.56 / $1,234.56 / blank."""
    if raw is None:
        return Decimal(0)
    s = str(raw).strip().replace("$", "").replace(",", "").replace("\u00a0", "")
    if not s or s in {"-", "—"}:
        return Decimal(0)
    m = _PARENS.match(s)
    if m:
        s = "-" + m.group(1)
    try:
        return money(s)
    except Exception:
        return Decimal(0)


@dataclass
class ImportProfile:
    """A named, versioned recipe for reading one export shape.

    Column keys are matched case-insensitively against the detected header
    row, and several aliases are allowed per field because QBO renames things
    between versions ("Memo/Description" vs "Description" vs "Memo").
    """
    profile_id: str
    report: str                      # GENERAL_LEDGER | PROFIT_LOSS | BALANCE_SHEET | TIME_ACTIVITY
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    debit_credit_columns: bool = False
    account_in_section_header: bool = True
    strip_totals: bool = True
    date_formats: tuple[str, ...] = ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y")

    def resolve(self, header: list[str]) -> dict[str, int]:
        norm = [(h or "").strip().lower() for h in header]
        out: dict[str, int] = {}
        for field_name, options in self.aliases.items():
            for opt in options:
                o = opt.strip().lower()
                if o in norm:
                    out[field_name] = norm.index(o)
                    break
        return out


QBO_GENERAL_LEDGER = ImportProfile(
    profile_id="qbo-gl-v1",
    report="GENERAL_LEDGER",
    aliases={
        "date": ("date", "txn date", "transaction date"),
        "txn_type": ("transaction type", "type"),
        "num": ("num", "no.", "number", "doc num"),
        "name": ("name", "vendor", "customer", "name/vendor/employee",
                 "payee", "customer/project"),
        "memo": ("memo/description", "description", "memo"),
        "split": ("split", "account"),
        "amount": ("amount",),
        "debit": ("debit",),
        "credit": ("credit",),
        "balance": ("balance", "running balance"),
        "class_": ("class",),
        "location": ("location",),
    },
)

QBO_PROFIT_LOSS = ImportProfile(
    profile_id="qbo-pl-v1",
    report="PROFIT_LOSS",
    aliases={"account": ("", "account", "distribution account"),
             "amount": ("total", "amount")},
    account_in_section_header=False,
)

QBO_TIME_ACTIVITY = ImportProfile(
    profile_id="qbo-time-v1",
    report="TIME_ACTIVITY",
    aliases={
        "date": ("date", "activity date"),
        "employee": ("employee", "name", "vendor/employee"),
        "customer": ("customer", "customer/project", "customer:job"),
        "service": ("service", "service item"),
        "hours": ("duration", "hours", "time"),
        "billable": ("billable", "billable?"),
        "memo": ("description", "memo", "notes"),
        "class_": ("class",),
    },
    account_in_section_header=False,
)


@dataclass
class StagedLine:
    row_number: int
    account: str
    date: str
    txn_type: str
    num: str
    name: str
    memo: str
    split: str
    amount: Decimal
    class_: str = ""
    location: str = ""
    customer_job: str = ""          # raw "Customer:Job" string if present
    objective_hint: str = ""        # the segment after the colon

    @property
    def natural_key(self) -> str:
        """Stable identity for a QBO line across re-exports. QBO does not
        expose transaction ids in report exports, so identity is composed
        from the fields that do not drift."""
        import hashlib
        parts = "|".join([self.date, self.txn_type, self.num, self.name,
                          self.account, f"{self.amount:.2f}", self.memo[:80]])
        return hashlib.sha256(parts.encode()).hexdigest()[:24]


@dataclass
class StagedImport:
    profile_id: str
    source_name: str
    sha256: str
    lines: list[StagedLine] = field(default_factory=list)
    #: "Total for <account>" — leaf totals, keyed by qualified account path.
    subtotals: dict[str, Decimal] = field(default_factory=dict)
    #: "Total for <account> with sub-accounts" — subtree rollups, which
    #: reconcile against the account and everything beneath it.
    rollups: dict[str, Decimal] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    skipped: int = 0

    @property
    def total(self) -> Decimal:
        return money(sum(l.amount for l in self.lines))

    def account_totals(self) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for l in self.lines:
            out[l.account] = money(out.get(l.account, Decimal(0)) + l.amount)
        return out

    def subtotal_check(self) -> list[tuple[str, Decimal, Decimal, Decimal]]:
        """QBO prints its own 'Total for <account>' rows. Reconciling parsed
        rows against them proves the parser did not drop or duplicate lines —
        an internal control that costs nothing and catches almost every
        parsing mistake."""
        parsed = self.account_totals()
        out = []
        for account, printed in self.subtotals.items():
            got = parsed.get(account, Decimal(0))
            out.append((account, printed, got, money(got - printed)))
        return sorted(out, key=lambda r: abs(r[3]), reverse=True)

    def subtree_total(self, account: str) -> Decimal:
        """Sum of an account and every sub-account beneath it."""
        prefix = account + ":"
        return money(sum(
            (l.amount for l in self.lines
             if l.account == account or l.account.startswith(prefix)),
            Decimal(0)))

    def rollup_check(self) -> list[tuple[str, Decimal, Decimal, Decimal]]:
        """Reconcile the "with sub-accounts" rollups against their subtrees.

        This is the control that proves the account hierarchy was reconstructed
        correctly, not merely that individual leaves add up."""
        out = []
        for account, printed in self.rollups.items():
            got = self.subtree_total(account)
            out.append((account, printed, got, money(got - printed)))
        return sorted(out, key=lambda r: abs(r[3]), reverse=True)


def _read_rows(path: Path) -> list[list[str]]:
    if path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        return [["" if c is None else str(c) for c in row]
                for row in ws.iter_rows(values_only=True)]
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.reader(f)]


def _find_header(rows: list[list[str]], profile: ImportProfile) -> tuple[int, dict[str, int]]:
    """QBO puts a company name, report title and date range above the header,
    and sometimes a blank spacer column at position 0. Scan for the first row
    that resolves enough known columns."""
    need = {"date", "amount"} if not profile.debit_credit_columns else {"date", "debit"}
    for i, row in enumerate(rows[:40]):
        cols = profile.resolve(row)
        if need.issubset(cols.keys()):
            return i, cols
        if "date" in cols and ("amount" in cols or "debit" in cols):
            return i, cols
    raise ValueError(
        "Could not locate a header row. QBO exports vary; add the column "
        "names from this file to an ImportProfile rather than editing code."
    )


def parse_general_ledger(path: Path, profile: ImportProfile = QBO_GENERAL_LEDGER,
                         sha256: str = "") -> StagedImport:
    rows = _read_rows(path)
    hdr_idx, cols = _find_header(rows, profile)
    staged = StagedImport(profile_id=profile.profile_id, source_name=path.name, sha256=sha256)

    def cell(row: list[str], key: str) -> str:
        i = cols.get(key)
        return (row[i].strip() if i is not None and i < len(row) and row[i] else "")

    # QuickBooks prints the account tree as header / total pairs in column 0
    # rather than by indentation, so the qualified path has to be tracked as a
    # stack. Without it, sub-accounts sharing a leaf name under different
    # parents collide — YBI's 2025 chart has "Drive AM" under both
    # "3900 Grant Income" and "Grant Expenses", and merging them silently
    # overstates the account by the whole of the other one.
    #
    # One further wrinkle: QuickBooks prints a parent's own direct lines and
    # its "Total for <parent>" *before* the sub-account sections, then closes
    # with "Total for <parent> with sub-accounts". So a header following a
    # leaf total may be either that account's child or its sibling, and column
    # 0 does not say which. The rollup rows do: an account is a parent exactly
    # when it has a "with sub-accounts" total. Collect those first, then use
    # them to decide whether a leaf total closes its frame.
    parents = {
        _ROLLUP_SUFFIX.sub("", _TOTAL_ROW.sub("", (r[0] or "").strip())).strip()
        for r in rows[hdr_idx + 1:]
        if r and (r[0] or "").strip()
        and _TOTAL_ROW.match((r[0] or "").strip())
        and _ROLLUP_SUFFIX.search((r[0] or "").strip())
    }

    stack: list[str] = []
    for n, row in enumerate(rows[hdr_idx + 1:], start=hdr_idx + 2):
        if not any((c or "").strip() for c in row):
            continue

        first = (row[0] or "").strip() if row else ""

        # "Total for 5010 Depreciation Expense" — capture as a control, skip row
        if first and _TOTAL_ROW.match(first):
            label = _TOTAL_ROW.sub("", first).strip()
            is_rollup = bool(_ROLLUP_SUFFIX.search(label))
            account = _ROLLUP_SUFFIX.sub("", label).strip()
            amt = qbo_amount(cell(row, "amount"))
            if not amt:
                for c in reversed(row):
                    if (c or "").strip():
                        amt = qbo_amount(c)
                        if amt:
                            break
            if account:
                if account in stack:
                    depth = len(stack) - 1 - stack[::-1].index(account)
                    path = ":".join(stack[:depth + 1])
                    # A leaf total closes the frame only when the account has
                    # no sub-accounts; otherwise its children are still to
                    # come and the frame stays open until the rollup.
                    if is_rollup or account not in parents:
                        del stack[depth:]
                else:
                    path = ":".join(stack + [account])
                if is_rollup:
                    staged.rollups[path] = amt
                else:
                    staged.subtotals[path] = amt
            continue

        # Section header: something in column 0 and no date on the row
        if profile.account_in_section_header and first and not cell(row, "date"):
            stack.append(first)
            continue

        date = cell(row, "date")
        if not date:
            staged.skipped += 1
            continue
        if _BEGIN_BAL.search(cell(row, "memo") or "") or _BEGIN_BAL.search(cell(row, "txn_type") or ""):
            continue  # opening balance rows are not transactions

        if profile.debit_credit_columns:
            amount = money(qbo_amount(cell(row, "debit")) - qbo_amount(cell(row, "credit")))
        else:
            amount = qbo_amount(cell(row, "amount"))

        account = ":".join(stack) if stack else cell(row, "split")
        if not account:
            staged.warnings.append(f"row {n}: no account context, line held for review")

        name = cell(row, "name")
        customer_job = name if ":" in name else ""
        hint = name.split(":")[-1].strip() if ":" in name else ""

        staged.lines.append(StagedLine(
            row_number=n, account=account, date=date,
            txn_type=cell(row, "txn_type"), num=cell(row, "num"),
            name=name, memo=cell(row, "memo"), split=cell(row, "split"),
            amount=amount, class_=cell(row, "class_"),
            location=cell(row, "location"),
            customer_job=customer_job, objective_hint=hint,
        ))

    dupes = len(staged.lines) - len({l.natural_key for l in staged.lines})
    if dupes:
        staged.warnings.append(
            f"{dupes} line(s) share a natural key — identical date, type, num, "
            f"name, account, amount and memo. Usually genuine split lines; "
            f"confirm before accepting.")
    return staged


def parse_time_activity(path: Path, profile: ImportProfile = QBO_TIME_ACTIVITY) -> list[dict]:
    """QBO Time Activity detail. This is the feed that makes labour
    distribution contemporaneous rather than reconstructed — the single
    highest-value import in the system."""
    rows = _read_rows(path)
    hdr_idx = 0
    cols: dict[str, int] = {}
    for i, row in enumerate(rows[:40]):
        c = profile.resolve(row)
        if "employee" in c and "hours" in c:
            hdr_idx, cols = i, c
            break
    if not cols:
        raise ValueError("Time activity header not found; extend QBO_TIME_ACTIVITY aliases.")

    out = []
    for row in rows[hdr_idx + 1:]:
        def g(k):
            i = cols.get(k)
            return (row[i].strip() if i is not None and i < len(row) and row[i] else "")
        if not g("employee") or not g("date"):
            continue
        cust = g("customer")
        out.append({
            "date": g("date"),
            "employee": g("employee"),
            "customer_job": cust,
            "objective_hint": cust.split(":")[-1].strip() if ":" in cust else cust,
            "service": g("service"),
            "hours": qbo_amount(g("hours")),
            "billable": g("billable").lower() in {"yes", "true", "y", "1"},
            "memo": g("memo"),
            "class_": g("class_"),
        })
    return out


def objective_hints(staged: StagedImport) -> dict[str, Decimal]:
    """Customer:Job already encodes the cost objective in YBI's file — 188
    revenue rows worth $2.03M carry it. Surface it as a classification
    proposal rather than making anyone retype it."""
    out: dict[str, Decimal] = {}
    for l in staged.lines:
        if l.objective_hint:
            out[l.objective_hint] = money(out.get(l.objective_hint, Decimal(0)) + l.amount)
    return dict(sorted(out.items(), key=lambda kv: abs(kv[1]), reverse=True))


# ---------------------------------------------------------------------
# Profit and loss
# ---------------------------------------------------------------------

#: The four sections a QBO P&L prints, in the order it prints them. The
#: section is what decides whether an account is a cost, a revenue or neither
#: — never the account number. YBI's 2025 chart has revenue sitting in the
#: 5xxx expense range (5107 Interest Income, 5108 Other Income) and income in
#: the net-assets range (3991 MBAC), so number-based inference is wrong here.
PL_SECTIONS = ("Income", "COGS", "Expense", "Other Income")

_PL_SECTION_HEADERS = {
    "income": "Income",
    "cost of goods sold": "COGS",
    "expenses": "Expense",
    "other income": "Other Income",
}


@dataclass
class ProfitLoss:
    """A parsed QuickBooks Profit and Loss.

    ``accounts`` maps the qualified account path to its section and amount.
    ``leaf_section`` maps the bare leaf name to its section, which is what the
    general ledger needs in order to tell a cost account from a balance sheet
    account.
    """

    source_name: str
    sha256: str = ""
    accounts: dict[str, tuple[str, Decimal]] = field(default_factory=dict)
    rollups: dict[str, tuple[str, Decimal]] = field(default_factory=dict)
    section_totals: dict[str, Decimal] = field(default_factory=dict)
    net_income: Decimal = Decimal(0)
    warnings: list[str] = field(default_factory=list)

    @property
    def income_total(self) -> Decimal:
        return self.section_totals.get("Income", Decimal(0))

    @property
    def cogs_total(self) -> Decimal:
        return self.section_totals.get("COGS", Decimal(0))

    @property
    def expense_total(self) -> Decimal:
        return self.section_totals.get("Expense", Decimal(0))

    @property
    def other_income_total(self) -> Decimal:
        return self.section_totals.get("Other Income", Decimal(0))

    @property
    def leaf_section(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for path, (section, _) in self.accounts.items():
            out[path.split(":")[-1]] = section
        for path, (section, _) in self.rollups.items():
            out.setdefault(path.split(":")[-1], section)
        return out

    def check_net_income(self) -> Decimal:
        """Variance between the printed net income and the sections."""
        derived = (self.income_total - self.cogs_total - self.expense_total
                   + self.other_income_total)
        return money(derived - self.net_income)


def parse_profit_loss(path: Path, sha256: str = "") -> ProfitLoss:
    """Parse a QBO Profit and Loss export.

    Same header/total hierarchy as the general ledger, but with section
    headers (Income, Cost of Goods Sold, Expenses, Other Income) framing the
    account tree and a single amount column.
    """
    rows = _read_rows(path)
    pl = ProfitLoss(source_name=path.name, sha256=sha256)

    parents = {
        _ROLLUP_SUFFIX.sub("", _TOTAL_ROW.sub("", (r[0] or "").strip())).strip()
        for r in rows
        if r and (r[0] or "").strip()
        and _TOTAL_ROW.match((r[0] or "").strip())
        and _ROLLUP_SUFFIX.search((r[0] or "").strip())
    }

    def amount_of(row: list[str]) -> Decimal:
        for c in reversed(row[1:]):
            if (c or "").strip():
                return qbo_amount(c)
        return Decimal(0)

    section = ""
    stack: list[str] = []
    for row in rows:
        if not row or not any((c or "").strip() for c in row):
            continue
        label = (row[0] or "").strip()
        if not label:
            continue

        low = label.lower()
        if low in _PL_SECTION_HEADERS:
            section = _PL_SECTION_HEADERS[low]
            stack = []
            continue

        if _TOTAL_ROW.match(label):
            name = _TOTAL_ROW.sub("", label).strip()
            is_rollup = bool(_ROLLUP_SUFFIX.search(name))
            name = _ROLLUP_SUFFIX.sub("", name).strip()
            amt = amount_of(row)

            low_name = name.lower()
            if low_name in _PL_SECTION_HEADERS:
                pl.section_totals[_PL_SECTION_HEADERS[low_name]] = amt
                stack = []
                continue

            if name in stack:
                depth = len(stack) - 1 - stack[::-1].index(name)
                qualified = ":".join(stack[:depth + 1])
                if is_rollup or name not in parents:
                    del stack[depth:]
            else:
                qualified = ":".join(stack + [name])
            if is_rollup:
                pl.rollups[qualified] = (section, amt)
            else:
                pl.accounts[qualified] = (section, amt)
            continue

        if low.startswith("net income") or low.startswith("net operating income"):
            if low.startswith("net income"):
                pl.net_income = amount_of(row)
            continue

        # An account line: a label plus an amount is a leaf with activity; a
        # label alone opens a parent whose children follow.
        amt = amount_of(row)
        has_amount = any((c or "").strip() for c in row[1:])
        if has_amount and section:
            pl.accounts[":".join(stack + [label])] = (section, amt)
        elif section:
            stack.append(label)

    return pl
