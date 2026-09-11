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


def answer_rows(data: bytes, sheet: str, answers: dict[str, dict]) -> bytes:
    """Fill in the rows a workbook already carries, found by their reference.

    Different from `type_into`, which adds rows after the pre-filled ones.
    The verification workbook goes out with all nineteen items in it and a
    person answers the ones they can — so the reply is the same rows with
    three more columns filled, not new rows.
    """
    wb = load_workbook(BytesIO(data))
    ws = wb[sheet]
    at = {}
    for i, cell in enumerate(ws[1], start=1):
        text = str(cell.value or "").strip().rstrip(" *")
        if text:
            at.setdefault(text, i)
    ref_col = at["Ref"]
    seen = set()
    for r in range(3, ws.max_row + 1):
        ref = str(ws.cell(row=r, column=ref_col).value or "").strip()
        if ref in answers:
            seen.add(ref)
            for heading, value in answers[ref].items():
                ws.cell(row=r, column=at[heading], value=value)
    missing = set(answers) - seen
    if missing:
        raise SystemExit(f"the workbook has no row for {sorted(missing)}")
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


#: The requests this run issued.
#:
#: The chase-list check used to count ACCEPTED rows in the whole register and
#: compare against three, so it passed the first time this drive was ever run
#: and never again: a second run reported "6 of 7", a third "9 of 10". An
#: assertion over absolute state on a database the drive has already touched
#: is an assertion about how many times somebody has run it.
#:
#: The review script learned the same thing when coverage climbed 0% to 36.8%
#: across five runs and every figure was a review reading its own writing.
ISSUED: list[int] = []


def issue(client: httpx.Client, form: str, sent_to: str) -> tuple[int, bytes]:
    r = client.post(f"/api/requests/{form}/issue",
                    json={"sent_to": sent_to, "note": "Weekend drive."})
    if r.status_code != 200:
        raise SystemExit(f"issuing {form} answered {r.status_code}: {r.text[:300]}")
    rid = r.json()["request_id"]
    ISSUED.append(rid)
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
    from app.db import one
    # Whether accepting *creates* the building depends on whether a previous
    # run already did. The note is only owed in the first case, so read which
    # case this is rather than assuming the drive has never been run here.
    existing = one("""SELECT facility_id FROM facility WHERE name = 'Tech Block 5'""")
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
        created = any("Created" in n for n in got["notes"])
        if existing is None and created:
            ok("and it says it invented the building from the rows reported, "
               "so the square-foot control cannot test it yet")
        elif existing is not None and not created:
            ok(f"and it filed against the building already on record "
               f"({existing['facility_id']}) rather than inventing a second "
               f"one — two registers of one building is how the carve-out "
               f"read a table nothing wrote")
        elif existing is None:
            finding("a building was created without saying so")
        else:
            finding(f"a second building was invented alongside "
                    f"{existing['facility_id']}, which already carries that name")
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
         "Still employed?": "yes",
         "Employment type": "PART_TIME",
         "Hours a week they were employed to work": 24,
         "Employed from": "2025-01-01"},
        {"Payroll ID": "NOBODY-42", "First name": "Ray", "Surname": "Okonkwo",
         "Working email address": "rokonkwo@ybi.org", "Still employed?": "yes",
         # Terms given but no hours: not a partial row, no row — and the
         # person has to be told which, not handed a constraint violation.
         "Employment type": "FULL_TIME",
         "Employed from": "2025-03-01"},
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

    # The terms, and the denominator they give the distribution.
    span = one("""SELECT status::text AS status, weekly_hours, employed_from
                    FROM employment
                   WHERE period = '2025' AND employee_key = %s
                     AND superseded_at IS NULL""", (who["employee_key"],))
    if span and span["weekly_hours"] == 24:
        ok(f"employment terms landed — {span['status']} at "
           f"{span['weekly_hours']} hours a week from {span['employed_from']}")
    else:
        finding(f"the employment span did not land: {span}")

    expected = one("""SELECT expected_hours FROM v_employment_expected
                       WHERE period = '2025' AND employee_key = %s""",
                   (who["employee_key"],))
    if expected and expected["expected_hours"]:
        ok(f"and the distribution has a denominator at last — "
           f"{expected['expected_hours']} hours that person was employed to "
           f"work, which is what an effort percentage is measured against")
    else:
        finding("v_employment_expected still has nothing for that person")

    if any("could not be recorded" in n for n in got["notes"]):
        ok("terms given without hours were held back and named — a blank "
           "defaulted to 40 would understate every part-timer by exactly "
           "the amount that matters")
    else:
        finding("a row with no weekly hours was not reported")

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

# ── 4. The controller's own list ──────────────────────────────────────

def drive_verification(tom, heidi, outsider) -> None:
    head("The nineteen the record cannot settle — answers onto the record")
    from app.db import one, query

    before = one("""SELECT count(*) AS n FROM v_verification_status
                     WHERE period = '2025'""")["n"]
    # How much history item 1.5 already carries. This drive answers it twice,
    # and a second run over the first run's leavings would see four rows and
    # report working code as a fault — the same defect the chase-list check
    # had, measuring absolute state on a database it has already written to.
    history_before = one("""SELECT count(*) AS n FROM verification_answer
                             WHERE period = '2025' AND ref = '1.5'""")["n"]

    rid, blank = issue(tom, "VERIFICATION", "Tom Metzinger")
    wb = load_workbook(BytesIO(blank))["Verification"]
    at = {str(c.value or "").strip().rstrip(" *"): i
          for i, c in enumerate(wb[1], start=1) if c.value}
    refs = [str(wb.cell(row=r, column=at["Ref"]).value or "").strip()
            for r in range(3, wb.max_row + 1)]
    refs = [x for x in refs if x]
    if len(refs) == 19:
        ok(f"nineteen items went out, each carrying the question — {refs[0]} to "
           f"{refs[-1]}")
    else:
        finding(f"{len(refs)} items in the workbook, expected nineteen")

    # The worked example goes out already answered, because it *is* the
    # example: it shows what a settled row looks like rather than describing
    # one.
    example = wb.cell(row=3, column=at["Where it stands"]).value
    if example and "CONFIRMED" in str(example):
        ok("and the worked example goes out already settled, so the shape of "
           "an answer is shown rather than described")
    else:
        finding("the Bacon example went out blank")

    filled = answer_rows(blank, "Verification", {
        "1.3": {"Where it stands": "CONFIRMED — the record is right",
                "Your answer": "The register is the 2026 export; the "
                               "122,921.14 is 2026 additions. Asking for the "
                               "31 December cut."},
        "2.1": {"Where it stands": "CORRECTED — I have changed something",
                "Your answer": "Reclassified out of Rising Tides on 14 "
                               "January, after the GL ran and before the P&L. "
                               "Reposted so both agree.",
                "Answered by": "Heidi Ruby"},
        "1.5": {"Where it stands": "STILL CHECKING",
                "Your answer": "Asking whether the Xjet was donated."},
        # A settlement with nothing behind it. The status asserts somebody
        # went and looked; two characters is not what they found.
        "1.6": {"Where it stands": "CONFIRMED — the record is right",
                "Your answer": "ok"},
        # And a case with no words at all, which is honest for this status.
        "2.2": {"Where it stands": "SOMEBODY ELSE HAS TO ANSWER",
                "Your answer": "One for the awarding agency."},
    })

    send_back(outsider, rid, filled)
    p = tom.get(f"/api/requests/{rid}/preview").json()
    thin = [x for x in p["problems"] if "went and looked" in x["says"]]
    if thin:
        ok("a two-character confirmation is caught in the preview, not by the "
           "database on accept — “" + thin[0]["says"][:58] + "…”")
    else:
        finding("a settlement with nothing behind it was not reported")
    # Five: the four this run answered usably, plus the worked example,
    # which goes out already settled and is therefore a row with usable
    # content whoever put it there. The writer's own check is what stops it
    # being written again — see "already said" below.
    if p["usable"] == 5 and p["incomplete"] == 1:
        ok("five answers will land — four given here and the worked example "
           "that went out settled — and the thin one is held back, named. A "
           "bad cell costs one cell.")
    else:
        finding(f"{p['usable']} usable and {p['incomplete']} held back; "
                f"expected five and one")
    if p["untouched"] == 13:
        ok("and the thirteen nobody reached are untouched rather than "
           "incomplete — nobody started them, which is different from "
           "starting and stopping")
    else:
        finding(f"{p['untouched']} untouched, expected thirteen")

    refused = outsider.post(f"/api/requests/{rid}/accept", json={})
    if refused.status_code == 403:
        ok("and somebody with no portfolio may send the answers back and may "
           "not write them onto the record")
    else:
        finding(f"the verification accept admitted an outsider — "
                f"{refused.status_code}")
    refused = heidi.post(f"/api/requests/{rid}/accept", json={})
    if refused.status_code == 200:
        got = refused.json()
        ok(f"the controller accepted it — {got['written']} answer(s) written, "
           f"{got['held_back']} held back")
        if any("still open" in n for n in got["notes"]):
            ok("and it says how many of the nineteen are settled — "
               + next(n for n in got["notes"] if "still open" in n))
        else:
            finding("the accept does not say where the list stands")
    else:
        finding(f"the controller was refused — {refused.status_code}: "
                f"{refused.text[:200]}")

    rows = {r["ref"]: r for r in query(
        """SELECT * FROM v_verification_status WHERE period = '2025'""")}
    if rows.get("2.1", {}).get("answered_by") == "Heidi Ruby":
        ok("an answer names who settled it, not who sent the file — a row "
           "answered by the person who knows is worth more than one answered "
           "by whoever had the workbook")
    else:
        finding("the answered_by column did not survive the round trip")
    if rows.get("1.3", {}).get("evidence_id"):
        ok("and every answer carries the workbook it came out of, so 'who "
           "said this and on what' answers with a file")
    else:
        finding("an answer landed with no document behind it")
    if "1.6" not in rows:
        ok("the thin confirmation is nowhere on the record — held back, not "
           "half written")
    else:
        finding("a two-character confirmation reached the record")

    # ── Answered again ────────────────────────────────────────────────
    #
    # Several of these are *expected* to change answer. The sequence is what
    # an auditor is reconstructing, so a second answer supersedes rather than
    # overwrites and both stay.
    rid2, blank2 = issue(tom, "VERIFICATION", "Tom Metzinger")
    carried = load_workbook(BytesIO(blank2))["Verification"]
    answered_out = sum(1 for r in range(3, carried.max_row + 1)
                       if carried.cell(row=r, column=at["Where it stands"]).value)
    if answered_out >= 5:
        ok(f"a second issue is a chase rather than a blank page — "
           f"{answered_out} rows come back out already answered")
    else:
        finding(f"only {answered_out} answers were carried into the re-issue")

    again = answer_rows(blank2, "Verification", {
        "1.5": {"Where it stands": "CONFIRMED — the record is right",
                "Your answer": "Donated by Xjet in 2018. Nothing was paid, so "
                               "there is no basis to carry."},
    })
    send_back(outsider, rid2, again)
    r = heidi.post(f"/api/requests/{rid2}/accept", json={})
    notes = r.json().get("notes", []) if r.status_code == 200 else []
    if any("superseded" in n for n in notes):
        ok("answering again supersedes rather than overwrites, and says so")
    else:
        finding(f"a second answer did not supersede: {r.status_code} "
                f"{notes or r.text[:200]}")
    hist = query("""SELECT status, superseded_at IS NOT NULL AS gone
                      FROM verification_answer
                     WHERE period = '2025' AND ref = '1.5'
                     ORDER BY answer_id""")
    added = hist[history_before:]
    live = [h for h in hist if not h["gone"]]
    if (len(added) == 2 and added[0]["gone"] and not added[1]["gone"]
            and len(live) == 1):
        ok(f"both answers are on the record and exactly one is live — the "
           f"sequence is what an auditor is reconstructing, and 1.5 now "
           f"carries {len(hist)} of them")
    else:
        finding(f"this run added {len(added)} answer(s) to 1.5 and {len(live)} "
                f"is live: {added}")
    if any("already said" in n for n in notes):
        ok("and the rows that came back saying what they already said were "
           "left alone rather than superseded with themselves")
    else:
        finding("re-answering an unchanged row was recorded as a change")

    after = one("""SELECT count(*) AS n FROM v_verification_status
                     WHERE period = '2025'""")["n"]
    print(f"  note     {before} item(s) answered before this run, {after} after",
          flush=True)


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
    everything = r.json()["requests"]
    rows = [x for x in everything if x["request_id"] in ISSUED]
    if len(rows) != len(ISSUED):
        finding(f"{len(ISSUED)} requests were issued and {len(rows)} came "
                f"back from the register")
        return
    accepted = [x for x in rows if x["state"] == "ACCEPTED"]
    if len(accepted) == len(ISSUED):
        ok(f"{len(ISSUED)} requests issued, replied to and accepted, each on "
           f"the record — of {len(everything)} in the register")
    else:
        finding(f"{len(accepted)} of {len(ISSUED)} requests this run reached "
                f"ACCEPTED")
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
    drive_verification(tom, heidi, outsider)
    check_library(auditor)
    check_chase_list(tom)

    head("Summary")
    print(f"  {CHECKS} check(s), {len(FINDINGS)} finding(s)")
    for f in FINDINGS:
        print(f"    - {f}")
    return 1 if FINDINGS else 0


if __name__ == "__main__":
    sys.exit(main())
