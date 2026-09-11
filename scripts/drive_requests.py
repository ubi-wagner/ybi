#!/usr/bin/env python3
"""The ask, the reply, and what it does to the record.

Three things are missing and none of them can be inferred. This drives the
whole cycle for each of them, as the people who would actually do it:

    Tom issues a request      → a workbook, and a row saying we asked
    somebody fills it in      → here, a script pretending to be a person
    anybody sends it back     → an employee, because the door is that wide
    the portfolio accepts it  → Heidi for space, Tom for the register

What it is looking for is not "did it work". It is whether the imperfect
answer — and every answer will be imperfect — leaves the record honest:

  * the good rows land and the bad rows do not
  * a bad cell costs one cell, not the file
  * a blank stays unanswered rather than becoming a zero
  * the boundary holds: an employee may send a reply and may not accept one
  * the reply is in the library as a document, so the register's source is a
    file with a name and a sender

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/drive_requests.py \\
        [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from io import BytesIO

import httpx
from openpyxl import load_workbook

FINDINGS: list[str] = []
CHECKS = 0
XLSX = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}", file=sys.stderr, flush=True)


def ok(msg: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  ok       {msg}", flush=True)


def head(msg: str) -> None:
    print(f"\n\033[1m{msg}\033[0m", flush=True)


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email} ({r.status_code}).")
    return c


def type_into(data: bytes, sheet: str, rows: list[dict],
              start_after_known: int = 0) -> bytes:
    """Fill a workbook in the way a person would: by heading, on the rows
    after whatever we sent pre-filled."""
    wb = load_workbook(BytesIO(data))
    ws = wb[sheet]
    at = {}
    for i, cell in enumerate(ws[1], start=1):
        text = str(cell.value or "").strip().rstrip(" *")
        if text:
            at.setdefault(text, i)
    r = 3 + start_after_known
    for row in rows:
        for heading, value in row.items():
            if heading not in at:
                raise SystemExit(f"the workbook has no column {heading!r}")
            ws.cell(row=r, column=at[heading], value=value)
        r += 1
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def known_row_count(data: bytes, sheet: str) -> int:
    wb = load_workbook(BytesIO(data))
    ws = wb[sheet]
    n = 0
    for r in range(3, ws.max_row + 1):
        if any(c.value not in (None, "") for c in ws[r]):
            n += 1
        else:
            break
    return n


def issue(client: httpx.Client, form: str, sent_to: str) -> tuple[int, bytes]:
    r = client.post(f"/api/requests/{form}/issue",
                    json={"sent_to": sent_to, "note": "Weekend drive."})
    if r.status_code != 200:
        raise SystemExit(f"issuing {form} answered {r.status_code}: {r.text[:300]}")
    rid = r.json()["request_id"]
    wb = client.get(f"/api/requests/{rid}/workbook")
    if wb.status_code != 200:
        raise SystemExit(f"workbook for {rid} answered {wb.status_code}")
    if wb.headers.get("content-type") != XLSX:
        finding(f"the workbook came back as {wb.headers.get('content-type')}")
    return rid, wb.content


def send_back(client: httpx.Client, rid: int, data: bytes,
              filename="reply.xlsx") -> httpx.Response:
    return client.post(f"/api/requests/{rid}/reply",
                       files={"file": (filename, data, XLSX)},
                       data={"received_from": "Facilities"})


# ── 1. The asset register ─────────────────────────────────────────────

def drive_assets(tom, outsider) -> None:
    head("The asset register — the column that decides $327,000")
    rid, blank = issue(tom, "ASSET_REGISTER", "Whoever keeps the register")
    known = known_row_count(blank, "Assets")
    if known:
        ok(f"the workbook went out with {known} balance-sheet row(s) already "
           f"filled in, to be broken down rather than typed from nothing")
    else:
        finding("the asset workbook went out completely blank")

    # A reply as one really arrives: mostly fine, one vague date, one
    # sentence where a number belongs, one row with no identifier, and two
    # assets where nobody looked at the funding question.
    filled = type_into(blank, "Assets", [
        {"Asset ID or tag": "TB5", "Description": "Tech Block Building 5",
         "Original cost, before any reimbursement": "8,922,679.69",
         "Federal money in it": "3,434,230.00",
         "Federal award number / FAIN": "ED17ATL3020023",
         "Placed in service": "2017-06-30", "2025 depreciation": 327000,
         "Who holds title": "YBI"},
        {"Asset ID or tag": "LOTS", "Description": "Buildings — Lots 13, 14 & 28",
         "Original cost, before any reimbursement": "8,760,612.01",
         "Federal money in it": 0,
         "Placed in service": "2012ish"},
        {"Asset ID or tag": "CAPIMP", "Description": "Capital improvements",
         "Original cost, before any reimbursement": "about 4 million"},
        {"Description": "A row nobody identified",
         "Original cost, before any reimbursement": 1000},
        {"Asset ID or tag": "COMP", "Description": "Computer equipment",
         "Original cost, before any reimbursement": "973,054.57"},
    ], start_after_known=known)

    r = send_back(outsider, rid, filled)
    if r.status_code == 200:
        ok(f"somebody holding no portfolio sent the reply back — the door "
           f"is that wide ({r.json()['rows']} rows read)")
    else:
        finding(f"a reply could not be sent back: {r.status_code} "
                f"{r.text[:200]}")
        return

    p = tom.get(f"/api/requests/{rid}/preview").json()
    # Two rows cannot be recorded: one has no identifier, and one has a cost
    # that will not read — and a cost is not optional on an asset register.
    # The row with the unreadable *date* is a different case and must not be
    # among them: a date is not required, so that row lands with one field
    # empty and the problem named.
    if p["incomplete"] == 2:
        ok(f"{p['usable']} rows usable, two held back — one with no "
           f"identifier, one whose cost will not read — and "
           f"{p['untouched']} pre-filled rows nobody has reached")
    else:
        finding(f"expected 2 rows held back, got {p['incomplete']}")

    said = {x["column"]: x for x in p["problems"]}
    if "Placed in service" in said and "2012ish" in said["Placed in service"]["value"]:
        ok(f"and it names the cell: “{said['Placed in service']['text'][:78]}…”")
    else:
        finding("the vague date was not reported with its cell")
    if any("is not a number" in x["says"] for x in p["problems"]):
        ok("“about 4 million” was refused rather than mined for digits")
    else:
        finding("a sentence where a number belongs was not refused")

    # A bad cell costs one cell wherever the column is optional.
    landed = {r["values"].get("asset_id") for r in p["sample"]}
    if "LOTS" in landed:
        ok("the asset whose date reads “2012ish” is still on the register "
           "with that one field empty — an optional cell costs one cell")
    else:
        finding("an unreadable optional cell lost the whole asset")
    if not any(r["values"].get("asset_id") == "CAPIMP" for r in p["sample"]):
        ok("and the one whose *cost* will not read is held back instead — "
           "a required figure is not optional, and an asset at a guessed "
           "cost is worse than an asset nobody has recorded")
    else:
        finding("an asset with an unreadable cost was recorded anyway")

    ctl = next((c for c in p["controls"] if "Original cost" in c["label"]), None)
    if ctl:
        ok(f"the control says what came back against what was expected — "
           f"{ctl['got']} against {ctl['expect']}")
    else:
        finding("no control was reported on the asset workbook")

    # The boundary: accepting is a judgment, not a contribution.
    refused = outsider.post(f"/api/requests/{rid}/accept", json={})
    if refused.status_code == 403:
        ok("and may not accept one — sending a reply is a contribution, "
           "writing it into the record is a judgment. 403")
    else:
        finding(f"somebody with no portfolio accepting answered "
                f"{refused.status_code}")

    a = tom.post(f"/api/requests/{rid}/accept",
                 json={"note": "Register from the facilities team."})
    if a.status_code != 200:
        finding(f"accepting answered {a.status_code}: {a.text[:300]}")
        return
    got = a.json()
    if got["written"] >= 3:
        ok(f"{got['written']} assets written, {got['held_back']} held back, "
           f"{got['untouched']} pre-filled rows nobody reached")
    else:
        finding(f"{got['written']} assets written, expected at least 3")
    if any("say nothing about federal money" in n for n in got["notes"]):
        ok("and it says how many say nothing about federal money — the "
           "overstating direction, worth a second ask")
    else:
        finding("nothing was said about the assets with no funding answer")

    check_assets_landed()

    again = tom.post(f"/api/requests/{rid}/accept", json={})
    if again.status_code == 409:
        ok("accepting the same reply twice is refused")
    else:
        finding(f"a second accept answered {again.status_code}")


def check_assets_landed() -> None:
    from app.db import one, query
    n = one("SELECT count(*) AS n FROM asset WHERE period = '2025'")["n"]
    if n >= 3:
        ok(f"the register reads {n} assets")
    else:
        finding(f"the register reads {n} assets")

    # A blank is not a zero: LOTS said 0 and CAPIMP said nothing, and the
    # difference has to survive all the way to the table.
    funding = {r["asset_id"]: r["amount"] for r in
               query("""SELECT asset_id, amount FROM asset_funding
                         WHERE kind = 'FEDERAL'""")}
    if funding.get("LOTS") == Decimal("0") and "CAPIMP" not in funding:
        ok("a checked zero is a funding row of 0.00; an unanswered column is "
           "no row at all — the two stayed different")
    else:
        finding(f"blank and zero did not stay apart: {funding}")

    unreadable = one("""SELECT gross_cost FROM asset WHERE asset_id = 'CAPIMP'""")
    if unreadable is None:
        ok("and the asset whose cost would not read is nowhere on the "
           "register — not there at zero, which would understate the basis "
           "while looking complete")
    else:
        finding(f"CAPIMP reached the register at {unreadable['gross_cost']}")

    src = one("""SELECT source_document, evidence_grade::text AS grade
                   FROM asset WHERE asset_id = 'TB5'""")
    if src and "Request reply" in src["source_document"]:
        ok(f"every asset names where it came from — {src['source_document']!r}, "
           f"graded {src['grade']}")
    else:
        finding("assets do not name the reply they came from")


# ── 2. Space ──────────────────────────────────────────────────────────

def drive_space(tom, heidi, outsider) -> None:
    head("Floor space — the carve-out that cannot be computed at all today")
    rid, blank = issue(tom, "SPACE_INVENTORY", "Facilities")
    known = known_row_count(blank, "Space")

    filled = type_into(blank, "Space", [
        {"Building": "Tech Block 5", "Suite or area": "Suite 210",
         "Usable square feet": 2400, "What it is used for": "tenant",
         "Occupied or empty": "OCCUPIED", "Who is in it": "Acme Robotics",
         "Months occupied in 2025": 12, "Charged for it in 2025": 28800},
        {"Building": "Tech Block 5", "Suite or area": "Lab 1",
         "Usable square feet": 1800, "What it is used for": "SHARED_LAB",
         "Occupied or empty": "INTERNAL"},
        {"Building": "Tech Block 5", "Suite or area": "Suite 310",
         "Usable square feet": 1200, "What it is used for": "VACANT",
         "Occupied or empty": "VACANT", "Months occupied in 2025": 6},
        {"Building": "Tech Block 5", "Suite or area": "Corridors",
         "Usable square feet": 900, "What it is used for": "rented out",
         "Occupied or empty": "COMMON"},
    ], start_after_known=known)

    send_back(outsider, rid, filled)
    p = tom.get(f"/api/requests/{rid}/preview").json()
    bad = next((x for x in p["problems"]
                if x["column"] == "What it is used for"), None)
    if bad and "TENANT" in bad["says"]:
        ok("a use outside the list is refused with the list — "
           f"“{bad['says'][:60]}…”")
    else:
        finding("an invalid space use was not reported against its choices")

    refused = heidi.post(f"/api/requests/{rid}/accept", json={})
    # Heidi holds FACILITIES, so this should be allowed.
    if refused.status_code == 200:
        got = refused.json()
        ok(f"the facilities portfolio accepted it — {got['written']} unit(s)")
        if any("Created" in n for n in got["notes"]):
            ok("and it says it invented the building from the rows reported, "
               "so the square-foot control cannot test it yet")
        else:
            finding("a building was created without saying so")
    else:
        finding(f"facilities accepting answered {refused.status_code}: "
                f"{refused.text[:200]}")
        return

    from app.db import one
    ctl = one("""SELECT name, usable_sqft, unit_sqft, ties
                   FROM v_space_unit_control WHERE period = '2025'""")
    if ctl:
        ok(f"{ctl['name']}: {ctl['unit_sqft']} of {ctl['usable_sqft']} square "
           f"feet accounted for")
    else:
        finding("no space control row after accepting")

    occ = one("""SELECT tenant_sqft, vacant_sqft, usable_sqft
                   FROM v_facility_occupancy WHERE period = '2025'""")
    if occ and occ["tenant_sqft"] and occ["tenant_sqft"] > 0:
        ok(f"and the carve-out has something to work with at last — "
           f"{occ['tenant_sqft']} tenant square feet of {occ['usable_sqft']}")
    else:
        finding(f"the occupancy view still sees no tenant space: {occ}")


# ── 3. The roster ─────────────────────────────────────────────────────

def drive_people(tom, barb, outsider) -> None:
    head("The roster — thirty-seven people who cannot sign")
    rid, blank = issue(barb, "PEOPLE_ROSTER", "Payroll")
    known = known_row_count(blank, "People")
    if known:
        ok(f"{known} people came pre-filled from the payroll register")
    else:
        finding("the roster went out with nobody on it")

    from app.db import execute, one
    who = one("""SELECT employee_key, email, display_name FROM actor
                  WHERE employee_key IS NOT NULL ORDER BY employee_key LIMIT 1""")
    if not who:
        finding("no account carries an employee key, so nothing to confirm")
        return
    # An unconfirmed address is the state the thirty-seven are in, and it is
    # the only state a roster reply may write into. Put this account in it so
    # the drive is testing the real case rather than the one that is refused.
    execute("UPDATE actor SET email_confirmed = false WHERE employee_key = %s",
            (who["employee_key"],))

    settled = one("""SELECT employee_key, email, display_name FROM actor
                      WHERE employee_key IS NOT NULL AND email_confirmed
                      ORDER BY employee_key LIMIT 1""")

    filled = type_into(blank, "People", [
        {"Payroll ID": who["employee_key"], "First name": "Dolores",
         "Surname": "Wallace",
         "Working email address": f"  {who['email'].upper()}  ",
         "Still employed?": "yes"},
        {"Payroll ID": "NOBODY-42", "First name": "Ray", "Surname": "Okonkwo",
         "Working email address": "rokonkwo@ybi.org", "Still employed?": "yes"},
    ] + ([{"Payroll ID": settled["employee_key"], "First name": "Somebody",
           "Surname": "Else",
           "Working email address": "takeover@example.com",
           "Still employed?": "yes"}] if settled else []),
        start_after_known=known)

    send_back(outsider, rid, filled)
    refused = tom.post(f"/api/requests/{rid}/accept", json={})
    if refused.status_code == 403:
        ok("the controller may not accept the roster — accounts are the "
           "administrator's, and the portfolio is not the ladder")
    else:
        finding(f"the controller accepting the roster answered "
                f"{refused.status_code}")

    a = barb.post(f"/api/requests/{rid}/accept", json={})
    if a.status_code != 200:
        finding(f"the administrator accepting answered {a.status_code}: "
                f"{a.text[:200]}")
        return
    got = a.json()
    if got["written"] == 1:
        ok("one address confirmed onto an account that exists")
    else:
        finding(f"{got['written']} addresses written, expected 1")
    if any("no account yet" in n for n in got["notes"]):
        ok("and the person with no account is named rather than conjured — "
           "an account is handed over by a person")
    else:
        finding("a person with no account was not reported")

    confirmed = one("""SELECT email, email_confirmed, display_name FROM actor
                        WHERE employee_key = %s""", (who["employee_key"],))
    if confirmed and confirmed["email_confirmed"]:
        ok(f"the address is confirmed and normalised — {confirmed['email']}")
    else:
        finding(f"the address did not land confirmed: {confirmed}")
    if confirmed and confirmed["display_name"] == who["display_name"]:
        ok(f"and the account is still {confirmed['display_name']} — a reply "
           f"may fill in an address and may never rename somebody")
    else:
        finding(f"a spreadsheet renamed an account: {who['display_name']!r} "
                f"became {confirmed['display_name']!r}")

    # The takeover: an account somebody has already confirmed must be
    # untouchable from a spreadsheet. Without this a payroll key collision
    # renamed the organisation's administrator and locked her out.
    if settled:
        after = one("""SELECT email, display_name FROM actor
                        WHERE employee_key = %s""", (settled["employee_key"],))
        if after["email"] == settled["email"]:
            ok(f"an address somebody had already confirmed was left alone — "
               f"{after['display_name']} still signs in as {after['email']}")
        else:
            finding(f"a reply took over a confirmed account: "
                    f"{settled['email']} became {after['email']}")
        if any("already confirmed" in n for n in got["notes"]):
            ok("and it says so, rather than passing over it in silence")
        else:
            finding("a confirmed address was skipped with nothing said")


# ── The reply is a document ───────────────────────────────────────────

def check_library(auditor) -> None:
    head("Where the answers came from")
    from app.db import query
    rows = query("""SELECT filename, received_from, kind FROM evidence
                     WHERE kind = 'information-request' ORDER BY received_at""")
    if len(rows) >= 3:
        ok(f"{len(rows)} replies filed as documents, each with a name and a "
           f"sender — {rows[0]['filename']} from {rows[0]['received_from']}")
    else:
        finding(f"only {len(rows)} replies reached the library")

    r = auditor.get("/api/documents/library")
    if r.status_code != 200:
        finding(f"the auditor cannot read the library: {r.status_code}")
        return
    lib = r.json()
    items = lib if isinstance(lib, list) else lib.get("documents", lib.get("items", []))
    names = [d.get("kind") for d in items]
    if "information-request" in names:
        ok("and the auditor can see them, so 'where did this funding source "
           "come from' has an answer with a file behind it")
    else:
        finding("the replies are not visible in the library to an auditor")


def check_chase_list(tom) -> None:
    head("The chase list")
    r = tom.get("/api/requests")
    if r.status_code != 200:
        finding(f"the request register answered {r.status_code}")
        return
    rows = r.json()["requests"]
    accepted = [x for x in rows if x["state"] == "ACCEPTED"]
    if len(accepted) == 3:
        ok("three requests issued, replied to and accepted, each on the record")
    else:
        finding(f"{len(accepted)} of {len(rows)} requests reached ACCEPTED")
    if all(x["days"] is not None for x in rows):
        ok("every one carries how long it took")
    else:
        finding("a request has no age")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--password", default=os.environ.get("YBI_SEED_PASSWORD", ""))
    args = ap.parse_args()
    if not args.password:
        raise SystemExit("YBI_SEED_PASSWORD (or --password) is required.")

    tom = sign_in(args.base, "tom@ybi.org", args.password)
    heidi = sign_in(args.base, "hruby@ybi.org", args.password)
    barb = sign_in(args.base, "bewing@ybi.org", args.password)
    auditor = sign_in(args.base, "auditor@ybi.org", args.password)
    # The wide door, tested with somebody who holds no portfolio at all.
    # The auditor may read the whole cost record and may write none of it,
    # which is exactly the boundary the reply route has to sit on: sending a
    # filled workbook back is a contribution, and accepting it is a judgment.
    from app.db import one
    emp = one("""SELECT email FROM actor WHERE role = 'EMPLOYEE'
                   AND is_active ORDER BY email LIMIT 1""")
    outsider = (sign_in(args.base, emp["email"], args.password) if emp
                else auditor)

    drive_assets(tom, outsider)
    drive_space(tom, heidi, outsider)
    drive_people(tom, barb, outsider)
    check_library(auditor)
    check_chase_list(tom)

    head("Summary")
    print(f"  {CHECKS} check(s), {len(FINDINGS)} finding(s)")
    for f in FINDINGS:
        print(f"    - {f}")
    return 1 if FINDINGS else 0


if __name__ == "__main__":
    sys.exit(main())
