"""The lease book YBI already keeps.

`2025_YBI_Lease-Schedule.xlsx` has been on file since the foundation was
loaded and nothing had read it either. Twenty-six tenants: who, which
building, the term, and what they pay monthly and annually.

That is most of the tenant half of the space question. What it does not carry
is **square footage**, which is the driver the 200.465 carve-out is sized by —
so the ask stops being "tell us about your space" and becomes "here are your
twenty-six tenants with their rent already filled in; how many square feet is
each one in?"

It also does not carry YBI's own space — the labs, the offices, the
corridors, the empty suites. Those still have to come from a floor plan, and
the workbook says so rather than implying that twenty-six tenants are the
whole building.

Two things the file does that a parser has to survive:

**"monthly" appears where a start date belongs**, for the tenants on a
rolling arrangement, and the columns after it shift left by one. A date that
cannot be read is left empty rather than approximated.

**Buildings are named four ways** — "ybi", "YBI", "TBB5", "Tbb5". They are
folded, because "ybi" and "YBI" being two buildings would make every square
foot control fail in a way nobody could see.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

__all__ = ["parse_lease_book", "Tenancy"]

#: What the book calls a building, against what it is. Folded on the way in,
#: because a building that exists twice makes every square-foot control fail
#: silently — the sum still foots, against the wrong denominator.
BUILDINGS = {
    "ybi": "YBI Incubator Building",
    "tbb5": "Tech Block Building 5",
    "tb5": "Tech Block Building 5",
}


@dataclass(frozen=True)
class Tenancy:
    lessee: str
    building: str
    building_as_written: str
    starts_on: dt.date | None
    ends_on: dt.date | None
    monthly_rent: Decimal
    annual_rent: Decimal
    #: What was in the start-date column when it was not a date — "monthly"
    #: for a rolling tenancy. Kept rather than discarded: it is the term.
    term_note: str = ""

    @property
    def rolling(self) -> bool:
        return self.starts_on is None and bool(self.term_note)


def _money(value) -> Decimal:
    if value in (None, ""):
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
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


def parse_lease_book(path_or_bytes) -> list[Tenancy]:
    from io import BytesIO

    from openpyxl import load_workbook

    source = (BytesIO(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray))
              else str(path_or_bytes))
    wb = load_workbook(source, data_only=True)
    out: list[Tenancy] = []

    for ws in wb.worksheets:
        at: dict[str, int] = {}
        for row in ws.iter_rows(min_row=1, max_row=min(8, ws.max_row)):
            found = {}
            for cell in row:
                label = str(cell.value or "").strip().lower()
                if label.startswith("lessee"):
                    found["lessee"] = cell.column
                elif label.startswith("building"):
                    found["building"] = cell.column
                elif "start" in label:
                    found["starts_on"] = cell.column
                elif "end" in label:
                    found["ends_on"] = cell.column
                elif "monthly" in label:
                    found["monthly_rent"] = cell.column
                elif "annual" in label:
                    found["annual_rent"] = cell.column
            if "lessee" in found and "annual_rent" in found:
                at = found
                heading = row[0].row
                break
        if not at:
            continue

        for r in range(heading + 1, ws.max_row + 1):
            def cell(key):
                c = at.get(key)
                return ws.cell(row=r, column=c).value if c else None

            lessee = str(cell("lessee") or "").strip()
            if not lessee or lessee.lower().startswith("total"):
                continue
            raw_start = cell("starts_on")
            written = str(cell("building") or "").strip()
            out.append(Tenancy(
                lessee=lessee,
                building=BUILDINGS.get(written.lower().replace(" ", ""),
                                       written or "Unnamed building"),
                building_as_written=written,
                starts_on=_date(raw_start),
                ends_on=_date(cell("ends_on")),
                monthly_rent=_money(cell("monthly_rent")),
                annual_rent=_money(cell("annual_rent")),
                term_note=("" if _date(raw_start)
                           else str(raw_start or "").strip())))
    return out
