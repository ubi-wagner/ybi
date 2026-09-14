#!/usr/bin/env python3
"""Issue the two requests the rate is actually waiting on.

    python3 scripts/ask_for_what_is_missing.py --base http://127.0.0.1:8000

Two things block the 2025 rate and neither is in this building:

  **Employment terms**, for the 43 people whose effort was reconstructed.
  `v_employment_expected` is empty, so there is no denominator: nobody can
  certify "40% on Drive AM" when the record cannot say whether they were
  full-time or half-time, and `POST /api/timesheet/submit` already refuses
  for that reason. It is also what turns the reconstruction into a draft
  timesheet — the draft divides *contracted hours*, so with no terms there
  is nothing to divide.

  **Square footage**, by suite and use. `v_facility_occupancy` inner-joins
  to its space totals, so with no buildings on the record no 2 CFR 200.465
  carve-out is computed at all and every dollar of tenant and vacant
  occupancy cost sits in the federal pool. Worth up to sixteen points of
  combined rate — the largest single lever left.

Both go out as workbooks pre-filled from YBI's own documents, so the ask
collapses to the column no document carries. Both come back through
`POST /api/requests/{id}/reply`, are previewed before anything is written,
and are accepted by whoever holds the portfolio that owns the data.

**It issues and does not accept.** Writing somebody's answer into the cost
record is the same judgment as typing it in by hand, and it belongs to the
person who holds that portfolio. This gets the ask out of the door.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BOLD, DIM, OK, WARN, FAIL, END = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m")

#: What each ask is for, in the words the recipient needs rather than the
#: words the schema uses. The note travels with the request row, so the
#: person who opens it months later can tell what it was for.
ASKS = [
    ("PEOPLE_ROSTER",
     "Employment terms and a working address for everyone on the 2025 "
     "payroll. The terms are the denominator every effort percentage is "
     "measured against — twenty hours a week is the whole of a half-time "
     "job and half of a full-time one, and nothing on the record can "
     "currently tell which. Status, contracted weekly hours and the dates "
     "worked; a blank is left blank rather than defaulted to full-time, "
     "because a default would understate every part-timer by exactly the "
     "amount that matters.",
     "blocks all 43 certifications, and the draft timesheets"),
    ("SPACE_INVENTORY",
     "Square footage by suite and by use, for every building. This sizes "
     "the 2 CFR 200.465 facilities carve-out, which on the current record "
     "is not computed at all — so tenant and vacant occupancy cost is "
     "sitting in the federal pool. Pre-filled from the 2025 lease schedule; "
     "the column nobody has is the footage.",
     "worth up to 16 points of combined indirect rate"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BASE",
                                                     "http://127.0.0.1:8000"))
    ap.add_argument("--email", default="tom@ybi.org")
    ap.add_argument("--password", default=os.environ.get("YBI_SEED_PASSWORD", ""))
    ap.add_argument("--period", default="2025")
    ap.add_argument("--due", default="", help="YYYY-MM-DD, optional")
    a = ap.parse_args()

    c = httpx.Client(base_url=a.base, timeout=180)
    r = c.post("/api/auth/login",
               json={"email": a.email, "password": a.password})
    if r.status_code != 200:
        print(f"{FAIL}could not sign in as {a.email}: {r.status_code}{END}")
        return 2

    print(f"\n{BOLD}Asking for what the rate is waiting on{END}")
    faults = 0
    for form, why, worth in ASKS:
        body = {"period": a.period, "note": why}
        if a.due:
            body["due_on"] = a.due
        r = c.post(f"/api/requests/{form}/issue", json=body)
        if r.status_code not in (200, 201):
            faults += 1
            detail = (r.json().get("detail")
                      if r.headers.get("content-type", "").startswith(
                          "application/json") else r.text)
            print(f"  {FAIL}{form}: {r.status_code}{END} {str(detail)[:200]}")
            continue
        d = r.json()
        print(f"\n  {OK}issued{END} {BOLD}{form}{END}  "
              f"request {d.get('request_id')}")
        print(f"    {DIM}{worth}{END}")
        for k in ("rows", "prefilled", "workbook", "filename", "uri"):
            if d.get(k) is not None:
                print(f"    {k}: {d[k]}")

    print(f"\n{BOLD}What happens next{END}")
    print(f"  1. Send each workbook to the person who has the answer.")
    print(f"  2. It comes back through {DIM}POST /api/requests/"
          f"{{id}}/reply{END} — anybody signed in may return one.")
    print(f"  3. {DIM}GET /api/requests/{{id}}/preview{END} says exactly what "
          f"it will write, and what it will not.")
    print(f"  4. {DIM}POST /api/requests/{{id}}/accept{END} writes it, and "
          f"takes the portfolio that owns the data.")
    print(f"\n  {DIM}Accepting is not automated here on purpose: writing "
          f"somebody's answer into the cost record is the same judgment as "
          f"typing it in by hand.{END}")

    if faults:
        print(f"\n{FAIL}{faults} request(s) did not issue.{END}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
