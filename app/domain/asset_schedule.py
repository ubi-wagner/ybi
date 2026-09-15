"""The fixed asset schedule YBI already keeps.

`2026_YBI_Fixed-Asset-Schedule.xls` has been on file since the foundation was
loaded and nothing had read it. It is a Crystal Reports export from the
depreciation system: a summary sheet of account balances, then one sheet per
asset class holding **every asset individually** — system number, description,
date in service, method, life, cost basis, accumulated and current
depreciation.

That changes the shape of the ask completely. The question we need answered is
not "please build us an asset register", which is an afternoon of somebody's
week and comes back in six. It is:

    here are your three hundred assets, every column filled in except one —
    which of these did federal money pay for?

The column the schedule does not have is the only column that decides
allowability. 2 CFR 200.313(d)(1) requires source of funding in the property
records and this register does not carry it, which is a finding in its own
right, independently of the rate.

Two things about the file worth knowing:

**It is a real .xls**, an OLE2 compound document, not a renamed xlsx. openpyxl
cannot open it at all, which is why `xlrd` is a dependency — pure Python, so
the image grows no native library.

**Dates are Excel serial numbers**, days since 1899-12-30, and the summary
sheet's account column is a float. Both are artefacts of the export rather
than facts about the assets, and both are normalised here rather than being
carried into a column somebody reads.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal

__all__ = ["parse_asset_schedule", "ScheduleAsset", "AccountBalance"]

EPOCH = dt.date(1899, 12, 30)

#: The sheet name carries the accounts it covers: cost account and its
#: accumulated depreciation contra. "BLDG5-1501-1502" is cost in 1501 and
#: accumulated depreciation in 1502.
#: The label may itself carry a digit — "BLDG5-1501-1502" is building 5, not
#: building followed by account 5 — so it is matched non-greedily up to the
#: first four-digit account rather than by character class.
_SHEET = re.compile(r"^(?P<label>.+?)-(?P<cost>\d{4})(?:-(?P<contra>\d{4}))?$")

_HEADINGS = {
    "system no.": "system_no",
    "description": "description",
    "date in service": "in_service_on",
    "method / conv.": "method",
    "life": "useful_life_years",
    "cost / other basis": "gross_cost",
    "salvage/ basis adj.": "salvage_value",
    "beg. accum. depreciation": "accum_depr_open",
    "current depreciation": "depreciation",
    "total depreciation": "accum_depr_close",
}


@dataclass(frozen=True)
class ScheduleAsset:
    system_no: str
    description: str
    gl_account: str
    asset_class: str
    in_service_on: dt.date | None
    method: str
    useful_life_years: Decimal | None
    gross_cost: Decimal
    salvage_value: Decimal
    accum_depr_open: Decimal
    depreciation: Decimal
    accum_depr_close: Decimal

    @property
    def asset_id(self) -> str:
        """Stable, and derived from what the depreciation system calls it.

        The system number is the identifier YBI's own records use, so a
        register reloaded next year lands on the same rows rather than
        doubling. Prefixed because a bare number in an id column is a
        provocation.

        **And the account, because the number alone is not unique.** The
        depreciation software numbers assets *within* a GL account, so
        system 165 is `Juggerbot Buildout` at $35,414.95 under 1501 and
        `Old Turning Office Furniture` at $5,000.00 under 1527. Keyed on the
        number alone they are one asset, and the register loads 262 rows from
        263 — the second silently overwriting the first, $35,414.95 of cost
        and $1,770.75 of depreciation gone, with every printed subtotal still
        tying because the parser saw both rows and only the database collapsed
        them.

        That is `071`'s lesson in a new register: *71 lines worth $24,082.67
        were being dropped on promote by natural keys that collided on
        genuinely-duplicate lines.* A natural key has to be the whole natural
        key.
        """
        return f"FA-{self.gl_account}-{self.system_no}"


@dataclass(frozen=True)
class Adjustment:
    """A row inside the asset block that is not an asset.

    The schedule carries depreciation true-ups — "True Up Entry (One Time)"
    with accumulated depreciation and no cost. They are real entries and they
    are not property, so they are neither loaded as assets nor dropped: they
    are listed, because a register that quietly loses fourteen rows is how
    somebody spends a morning proving a total that was never going to foot.
    """
    sheet: str
    row: int
    description: str
    why: str


@dataclass(frozen=True)
class Superseded:
    """A row the sheet carries and its own total excludes.

    Two sheets open with an aggregate — "BUILDINGS" at 180,000.00,
    "CAPITAL IMPROVEMENTS" at 1,336,695.00 — that the detail below replaced.
    They are still printed, they are not in the printed total, and loading
    them would overstate the depreciable basis by $1.5m.

    Which rows those are is *attributed*, never assumed: the difference has
    to be explained by exactly one combination of rows, or nothing is
    excluded and the control stays open for a person. That is the same rule
    `/api/reconcile/propose` follows — it proposes nothing at all when more
    than one combination would add up, because a difference that two
    explanations fit is a difference nobody has explained.
    """
    sheet: str
    row: int
    description: str
    gross_cost: Decimal


@dataclass(frozen=True)
class SheetControl:
    """What the sheet prints as its own total, against what is under it.

    The same rule the QuickBooks parsers follow: every printed subtotal must
    equal what sits under it, or the parse is wrong and saying so is the
    whole job. This one caught a parser that dropped every asset without a
    system number — $2,388,438.81 of Tech Block phase 2 among them, because
    the report only prints a system number when it changes.
    """
    sheet: str
    gl_account: str
    printed: Decimal
    parsed: Decimal
    #: Named rather than netted, and only where exactly one combination of
    #: rows explains the whole difference.
    explained_by: tuple[Superseded, ...] = ()

    @property
    def variance(self) -> Decimal:
        return self.parsed - self.printed

    @property
    def ties(self) -> bool:
        return abs(self.variance) <= Decimal("0.01")


@dataclass(frozen=True)
class AccountBalance:
    account: str
    cost: Decimal
    accumulated_depreciation: Decimal


@dataclass(frozen=True)
class Schedule:
    assets: tuple[ScheduleAsset, ...]
    balances: tuple[AccountBalance, ...]
    #: Sheets that did not look like an asset sheet, named rather than
    #: skipped silently — an export that grew a tab is a thing to notice.
    skipped: tuple[str, ...]
    adjustments: tuple[Adjustment, ...] = ()
    controls: tuple[SheetControl, ...] = ()
    #: Rows the sheets carry that their own totals exclude.
    superseded: tuple[Superseded, ...] = ()

    @property
    def ties(self) -> bool:
        return all(c.ties for c in self.controls)

    @property
    def open_controls(self) -> tuple[SheetControl, ...]:
        return tuple(c for c in self.controls if not c.ties)

    @property
    def total_cost(self) -> Decimal:
        return sum((a.gross_cost for a in self.assets), Decimal("0"))

    @property
    def total_depreciation(self) -> Decimal:
        return sum((a.depreciation for a in self.assets), Decimal("0"))


def _money(value) -> Decimal:
    if value in (None, "", " "):
        return Decimal("0")
    if isinstance(value, str):
        value = value.replace(",", "").replace("$", "").strip()
        if not value:
            return Decimal("0")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:                                        # noqa: BLE001
        return Decimal("0")


def _date(value) -> dt.date | None:
    """An Excel serial, or nothing.

    A few rows carry text in this column — "Jan-Aug" appears where a partial
    year was taken — and a date that cannot be read is left empty rather than
    approximated. An in-service date drives when depreciation starts, and a
    guessed one is worse than an absent one.
    """
    if isinstance(value, (int, float)) and value > 1000:
        try:
            return EPOCH + dt.timedelta(days=int(value))
        except (OverflowError, ValueError):
            return None
    return None


def parse_asset_schedule(path_or_bytes) -> Schedule:
    """Read the whole schedule: the summary balances and every asset."""
    import xlrd

    if isinstance(path_or_bytes, (bytes, bytearray)):
        wb = xlrd.open_workbook(file_contents=bytes(path_or_bytes))
    else:
        wb = xlrd.open_workbook(str(path_or_bytes))

    assets: list[ScheduleAsset] = []
    balances: list[AccountBalance] = []
    skipped: list[str] = []
    adjustments: list[Adjustment] = []
    controls: list[SheetControl] = []
    superseded: list[Superseded] = []

    for name in wb.sheet_names():
        sheet = wb.sheet_by_name(name)
        if name.strip().lower().startswith("summary"):
            balances.extend(_summary(sheet))
            continue
        match = _SHEET.match(name.strip())
        if not match:
            skipped.append(name)
            continue
        found, odd, control = _assets(sheet, match.group("cost"),
                                      match.group("label").strip())
        if control and not control.ties:
            control, found = _attribute(control, found)
        superseded.extend(control.explained_by if control else ())
        assets.extend(found)
        adjustments.extend(odd)
        if control:
            controls.append(control)

    return Schedule(tuple(assets), tuple(balances), tuple(skipped),
                    tuple(adjustments), tuple(controls), tuple(superseded))


def _attribute(control: "SheetControl", found: list["ScheduleAsset"]):
    """Explain a sheet's difference by the rows behind it, or leave it open.

    Only where **exactly one** combination of at most three rows accounts for
    the whole difference. Two explanations mean nobody has explained it, and
    an excluded asset that should have been included is a hole in the basis
    that no later control would find.
    """
    from itertools import combinations

    variance = control.variance
    if variance <= 0 or len(found) > 200:
        return control, found            # only over-parsing is attributable

    hits = [combo for size in (1, 2, 3)
            for combo in combinations(found, size)
            if sum((a.gross_cost for a in combo), Decimal("0")) == variance]
    if len(hits) != 1:
        return control, found            # ambiguous, or unexplained: say so

    excluded = set(hits[0])
    kept = [a for a in found if a not in excluded]
    explained = tuple(Superseded(control.sheet, 0, a.description, a.gross_cost)
                      for a in hits[0])
    return (SheetControl(control.sheet, control.gl_account, control.printed,
                         sum((a.gross_cost for a in kept), Decimal("0")),
                         explained),
            kept)


def _summary(sheet) -> list[AccountBalance]:
    out: list[AccountBalance] = []
    for r in range(sheet.nrows):
        first = sheet.cell_value(r, 0)
        # The account column is a float in the export. Anything that is not a
        # four-digit account number is a heading or the grand total row.
        if not isinstance(first, (int, float)) or not (1000 <= first < 10000):
            continue
        out.append(AccountBalance(
            account=str(int(first)),
            cost=_money(sheet.cell_value(r, 1) if sheet.ncols > 1 else 0),
            accumulated_depreciation=_money(
                sheet.cell_value(r, 2) if sheet.ncols > 2 else 0)))
    return out


def _assets(sheet, gl_account: str, asset_class: str):
    """One sheet of assets, found by its heading row rather than by position.

    A Crystal export puts its heading wherever the report design put it, and
    a class with a page break has the heading twice. Reading columns by name
    survives both; counting rows from the top does not.

    Two things this has to get right, both learned from the file:

    **A blank system number is still an asset.** The report prints the number
    only when it changes, so fourteen rows on the Tech Block sheet carry a
    description and a cost and nothing in the first column — including "YBI
    Portion TBB5 Phase-2" at $2,388,438.81. Requiring the number dropped
    $2.5m and left the sheet's own printed total unreachable.

    **The asset block ends at "Total Cost/Basis:".** Below it the report
    continues with breakout sections, a month-by-month depreciation roll and
    the adjusting entries — rows that have a description and a number and are
    not assets at all. Reading to the end of the sheet loads "Fitz
    Reimbursement" as property.
    """
    heading_row = None
    at: dict[str, int] = {}
    for r in range(min(20, sheet.nrows)):
        found = {}
        for c in range(sheet.ncols):
            label = str(sheet.cell_value(r, c)).strip().lower()
            if label in _HEADINGS:
                found[_HEADINGS[label]] = c
        if "description" in found and "gross_cost" in found:
            heading_row, at = r, found
            break
    if heading_row is None:
        return [], [], None

    def cell(r, key):
        c = at.get(key)
        return sheet.cell_value(r, c) if c is not None else None

    def row_text(r):
        return " ".join(str(sheet.cell_value(r, c)).strip()
                        for c in range(sheet.ncols)
                        if str(sheet.cell_value(r, c)).strip())

    out: list[ScheduleAsset] = []
    odd: list[Adjustment] = []
    printed: Decimal | None = None

    for r in range(heading_row + 1, sheet.nrows):
        text = row_text(r)
        if not text:
            continue
        if re.match(r"^\s*Total\b", text) or "Total Cost/Basis" in text:
            for c in range(sheet.ncols):
                if "total cost/basis" in str(sheet.cell_value(r, c)).lower():
                    printed = _money(cell(r, "gross_cost"))
            break                          # the asset block ends here

        description = str(cell(r, "description") or "").strip()
        if not description or description.lower() == "description":
            continue                       # blank, or a repeated page heading

        cost = _money(cell(r, "gross_cost"))
        if cost == 0:
            # A description with no cost in the cost column is not property.
            # Named rather than dropped: the depreciation true-ups live here.
            odd.append(Adjustment(sheet.name, r + 1, description,
                                  "no cost in the Cost / Other Basis column, "
                                  "so it is an entry against the class rather "
                                  "than an asset"))
            continue

        system = cell(r, "system_no")
        if isinstance(system, (int, float)):
            system = str(int(system))
        system = str(system or "").strip()
        if not system:
            # The report prints the number only when it changes. Fall back to
            # where the row is, which is stable for as long as the export is.
            system = f"{sheet.name}-r{r + 1}"

        life = cell(r, "useful_life_years")
        out.append(ScheduleAsset(
            system_no=system,
            description=description,
            gl_account=gl_account,
            asset_class=asset_class,
            in_service_on=_date(cell(r, "in_service_on")),
            method=str(cell(r, "method") or "").strip(),
            useful_life_years=(_money(life) if isinstance(life, (int, float))
                               else None),
            gross_cost=cost,
            salvage_value=_money(cell(r, "salvage_value")),
            accum_depr_open=_money(cell(r, "accum_depr_open")),
            depreciation=_money(cell(r, "depreciation")),
            accum_depr_close=_money(cell(r, "accum_depr_close"))))

    control = None
    if printed is not None:
        control = SheetControl(
            sheet=sheet.name, gl_account=gl_account, printed=printed,
            parsed=sum((a.gross_cost for a in out), Decimal("0")))
    return out, odd, control
