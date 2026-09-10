"""
Ingestion. Reads the GL, P&L control and (when supplied) the balance sheet and
labor distribution, and proves each against a control total before anything
downstream is allowed to use it.

The GL is loaded read-only and never mutated. Classification writes to a
separate overlay keyed by line id.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .core import ControlRegister, ControlTotal, TieOut, money


@dataclass(frozen=True)
class LedgerLine:
    line_id: str
    period: str
    date: str
    account: str
    payee: str
    description: str
    amount: Decimal
    pl_scope: str
    pl_section: str
    source_key: str

    @property
    def is_pl(self) -> bool:
        return self.pl_scope == "P&L"

    @property
    def group_key(self) -> tuple[str, str]:
        """Classification works at this grain, not per row."""
        return (self.account, self.payee)


class Ledger:
    def __init__(self, period: str, lines: list[LedgerLine]):
        self.period = period
        self.lines = lines
        self._by_id = {l.line_id: l for l in lines}

    def __len__(self) -> int:
        return len(self.lines)

    def get(self, line_id: str) -> LedgerLine:
        return self._by_id[line_id]

    @property
    def line_ids(self) -> set[str]:
        return set(self._by_id)

    def pl_lines(self) -> list[LedgerLine]:
        return [l for l in self.lines if l.is_pl]

    def section_totals(self) -> dict[str, Decimal]:
        t: dict[str, Decimal] = defaultdict(Decimal)
        for l in self.pl_lines():
            t[l.pl_section] += l.amount
        return dict(t)

    def groups(self) -> list["LineGroup"]:
        buckets: dict[tuple[str, str], list[LedgerLine]] = defaultdict(list)
        for l in self.lines:
            buckets[l.group_key].append(l)
        gs = [LineGroup(account=k[0], payee=k[1], lines=v) for k, v in buckets.items()]
        gs.sort(key=lambda g: abs(g.amount), reverse=True)
        return gs


@dataclass
class LineGroup:
    """The unit Tom actually reviews. 4,020 rows collapse to ~751 groups, and
    the top 200 groups carry 80% of the dollars."""
    account: str
    payee: str
    lines: list[LedgerLine]

    @property
    def amount(self) -> Decimal:
        return money(sum(l.amount for l in self.lines))

    @property
    def count(self) -> int:
        return len(self.lines)

    @property
    def line_ids(self) -> tuple[str, ...]:
        return tuple(l.line_id for l in self.lines)

    @property
    def scope(self) -> str:
        return f"account={self.account}" + (f" | payee={self.payee}" if self.payee else "")


def _rows(path: Path) -> list[dict]:
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_cost_ledger(path: Path, period: str = "2025") -> Ledger:
    lines = []
    for r in _rows(path):
        lines.append(LedgerLine(
            line_id=r["Cost ID"],
            period=r.get("Period", period),
            date=r.get("Date", ""),
            account=r.get("Source Account", ""),
            payee=(r.get("Vendor / Employee") or "").strip(),
            description=(r.get("Description") or "").strip(),
            amount=money(r.get("Booked Amount")),
            pl_scope="P&L",
            pl_section="Expense",
            source_key=r.get("Source Key", ""),
        ))
    return Ledger(period, lines)


def load_gl(path: Path, period: str = "2025") -> Ledger:
    lines = []
    for r in _rows(path):
        lines.append(LedgerLine(
            line_id=r["Transaction ID"],
            period=r.get("Period", period),
            date=r.get("Date", ""),
            account=r.get("Distribution Account", ""),
            payee=(r.get("Name / Vendor / Employee") or "").strip(),
            description=(r.get("Description") or "").strip(),
            amount=money(r.get("Raw Amount")),
            pl_scope=r.get("P&L Scope", ""),
            pl_section=r.get("P&L Section", ""),
            source_key=r.get("Transaction ID", ""),
        ))
    return Ledger(period, lines)


def load_revenue(path: Path) -> list[dict]:
    out = []
    for r in _rows(path):
        out.append({
            "revenue_id": r["Revenue ID"],
            "funder": (r.get("Customer / Funder / Tenant") or "").strip(),
            "amount": money(r.get("Booked Revenue")),
            "revenue_type": r.get("Revenue Type", ""),
            # QuickBooks customer:job encoding already carries the objective
            "objective_hint": (r.get("Customer / Funder / Tenant") or "").split(":")[-1].strip()
            if ":" in (r.get("Customer / Funder / Tenant") or "") else "",
        })
    return out


def load_labor_distribution(path: Path) -> dict[str, dict]:
    """Employee x objective wage distribution from the controller's workbook.

    Returns {objective: {wages, timesheet_backed}}. Employees with a single
    row in the Hours Log are a management assertion, not a time record; that
    distinction is carried through so it can be graded and tested.
    """
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)

    hours = list(wb["Hours Log"].iter_rows(values_only=True))
    counts: dict[str, int] = defaultdict(int)
    for r in hours[1:]:
        if r[0]:
            counts[str(r[0]).strip()] += 1
    contemporaneous = {k for k, v in counts.items() if v > 1}

    tb = list(wb["Time Breakdown"].iter_rows(values_only=True))
    header = tb[96]
    cols = {i: str(header[i]).replace("Adj-", "").strip()
            for i in range(2, 22) if header[i]}

    dist: dict[str, dict] = defaultdict(lambda: {"wages": Decimal(0), "backed": Decimal(0)})
    for r in tb[97:143]:
        if not r[0] or str(r[0]).strip() == "JOB SUM:":
            continue
        name = str(r[0]).strip()
        for i, obj in cols.items():
            v = money(r[i]) if r[i] not in (None, "") else Decimal(0)
            if not v:
                continue
            dist[obj]["wages"] += v
            if name in contemporaneous:
                dist[obj]["backed"] += v
    return {k: dict(v) for k, v in dist.items()}


def build_control_register(pl_path: Path) -> ControlRegister:
    """Controls come from the reconciled P&L, not from constants in code."""
    reg = ControlRegister()
    sections: dict[str, Decimal] = defaultdict(Decimal)
    for r in _rows(pl_path):
        sections[r["P&L Section"]] += money(r.get("Baseline Amount"))

    for section, amount in sections.items():
        reg.add(ControlTotal(
            control_id=f"PL-{section.upper().replace(' ', '-')}",
            description=f"P&L {section} ties to the reconciled control",
            expected=amount,
            source="PL_2025_CONTROL.csv",
        ))
    return reg


def gl_tieouts(gl: Ledger, reg: ControlRegister) -> list[TieOut]:
    actual = gl.section_totals()
    mapped = {f"PL-{k.upper().replace(' ', '-')}": v for k, v in actual.items()}
    return [reg.test(cid, mapped.get(cid, Decimal(0))) for cid in reg.ids if cid in mapped]
