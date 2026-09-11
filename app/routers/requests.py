"""Asking for what is missing, and taking the answer back in.

Three things are missing from the record and none of them can be inferred:
which assets federal money paid for, who uses which square foot, and the
email address of thirty-seven people who have to sign their own effort. All
three live in somebody else's filing cabinet, and each has a lead time
measured in weeks rather than minutes.

So the shape is: issue a workbook with the answer half written already, let
somebody fill it in offline in the tool they already use, take it back, show
exactly what it will do, and only then write it.

    POST /requests/{form}/issue        a workbook to send, and a row saying we sent it
    POST /requests/{id}/reply          the filled one comes back
    GET  /requests/{id}/preview        what it says, and what is wrong with it
    POST /requests/{id}/accept         write it

**Preview before accept**, exactly as the QuickBooks import does. Nothing
reaches the record without somebody having seen what it will do, and the
preview re-reads the stored file rather than a staging table — one copy of the
answer, and it is the file the person actually sent.

**The door is wide and the judgment is not.** Anybody signed in may send a
reply back, for the same reason anybody may send a document in: the person
holding the answer is the person who was asked, and routing every reply
through the controller is how a workbook sits in an inbox for a fortnight.
Accepting it into the record takes the portfolio that owns that data —
`INVENTORY` for the asset register, `FACILITIES` for space, the administrator
for the roster — because writing somebody's answer into the cost record is a
judgment and not a contribution.

**A reply is evidence.** The workbook is filed through `storage.place()` like
any other document, so the source behind every asset row is a file in the
library with a name and a sender, and an auditor asking "where did this
funding source come from" gets the spreadsheet somebody signed off.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app import storage
from app.audit import record
from app.auth import (Actor, current_actor, require_admin, require_facilities,
                      require_inventory, require_own_writes, require_reader)
from app.db import execute, one, query, transaction
from app.domain.request_forms import FORMS, Form as FormDef
from app.domain.request_intake import (Filled, WorkbookNotRecognised,
                                       read_request_workbook)
from app.domain.request_workbook import build_request_workbook
from app.settings import settings
from app.statelock import turn

router = APIRouter(prefix="/requests", tags=["requests"],
                   dependencies=[Depends(require_reader)])

XLSX = ("application/vnd.openxmlformats-officedocument"
        ".spreadsheetml.sheet")
MAX_BYTES = 40 * 1024 * 1024


def _form(name: str) -> FormDef:
    form = FORMS.get(name.upper())
    if not form:
        raise HTTPException(404, f"No form called {name!r}. There are "
                                 f"{', '.join(sorted(FORMS))}.")
    return form


# ── What each form knows already ──────────────────────────────────────
#
# The rows that go out pre-filled. A form that makes somebody retype what we
# already hold comes back late and wrong, and the person filling it cannot
# tell which parts we could have filled in ourselves — so they reasonably
# check everything.

def _known_rows(form: FormDef, period: str) -> list[dict]:
    if form.name == "ASSET_REGISTER":
        # YBI's own register, which has been on file since the foundation was
        # loaded and which nothing had read. Two hundred and sixty-three
        # assets with description, in-service date, life, cost and
        # depreciation already in them, every sheet tying to its own printed
        # total. So the ask is not "build us a register" — an afternoon of
        # somebody's week that comes back in six — it is "here are your
        # assets; which of these did federal money pay for?"
        assets = _asset_schedule(period)
        if assets:
            return [{"asset_id": a.asset_id,
                     "description": a.description,
                     "gl_account": a.gl_account,
                     "in_service_on": a.in_service_on,
                     "gross_cost": a.gross_cost,
                     "book_cost": a.gross_cost,
                     "useful_life_years": a.useful_life_years,
                     "accum_depr_close": a.accum_depr_close,
                     "depreciation": a.depreciation,
                     "note": ""}
                    for a in assets]
        # No register on file: fall back to the balance sheet's own asset
        # accounts, which are totals rather than assets, and say so.
        rows = query("""SELECT asset_class, gross_cost FROM v_fixed_asset_basis
                         WHERE period = %s AND COALESCE(gross_cost, 0) <> 0
                         ORDER BY asset_class""", (period,))
        return [{"gl_account": r["asset_class"],
                 "description": "",
                 "book_cost": r["gross_cost"],
                 "note": "Balance sheet total — please replace this row with "
                         "the assets that make it up."}
                for r in rows]

    if form.name == "SPACE_INVENTORY":
        # The lease book, same story: twenty-six tenants with the building
        # and the rent already filled in. What it has never carried is square
        # footage, which is the one thing the carve-out is sized by and the
        # one thing only a floor plan knows.
        rows = [{"facility_name": t.building,
                 "label": "",
                 "occupant": t.lessee,
                 "use": "TENANT",
                 "status": "OCCUPIED",
                 "actual_annual_charge": t.annual_rent,
                 "note": ("Rolling tenancy — the lease book says "
                          f"{t.term_note!r} rather than a start date."
                          if t.rolling else "")}
                for t in _lease_book(period)]
        for r in query("""SELECT name FROM facility WHERE period = %s
                           ORDER BY name""", (period,)):
            if not any(x["facility_name"] == r["name"] for x in rows):
                rows.append({"facility_name": r["name"]})
        return rows

    if form.name == "PEOPLE_ROSTER":
        # Everybody the payroll register knows about, with an address only
        # where somebody has confirmed one. A derived address is worse than a
        # blank: it looks answered.
        rows = query("""SELECT l.employee_key,
                               COALESCE(a.display_name, '')  AS known_name,
                               COALESCE(a.email, '')         AS known_email,
                               COALESCE(a.email_confirmed, false) AS confirmed
                          FROM (SELECT DISTINCT employee_key
                                  FROM v_labor_effective WHERE period = %s) l
                          LEFT JOIN actor a ON a.employee_key = l.employee_key
                         ORDER BY l.employee_key""", (period,))
        return [{"employee_key": r["employee_key"],
                 "surname": r["known_name"] or r["employee_key"],
                 "email": r["known_email"] if r["confirmed"] else None,
                 "note": "" if r["confirmed"]
                         else ("An address was guessed from the naming "
                               "convention and has never been confirmed — "
                               "please overwrite it."
                               if r["known_email"] else "")}
                for r in rows]
    return []


def _source_bytes(period: str, kind: str) -> bytes | None:
    """A document already on file, read back from the volume.

    Deliberately by `kind` rather than by filename: the library indexes what
    a document *is*, and a path is derived from the row and never parsed
    back into one. If it is missing from the volume the workbook still goes
    out — pre-filling is a courtesy and its absence must not stop the ask.
    """
    row = one("""SELECT uri FROM evidence
                  WHERE kind = %s ORDER BY received_at DESC LIMIT 1""", (kind,))
    if not row:
        return None
    try:
        return Path(row["uri"]).read_bytes()
    except OSError:
        return None


def _asset_schedule(period: str):
    from app.domain.asset_schedule import parse_asset_schedule
    raw = _source_bytes(period, "asset-register")
    if not raw:
        return []
    try:
        return list(parse_asset_schedule(raw).assets)
    except Exception:                                        # noqa: BLE001
        # A register that will not parse is a thing to fix, not a reason to
        # stop asking. The workbook goes out blank and the first sheet still
        # says what is wanted.
        return []


def _lease_book(period: str):
    from app.domain.lease_book import parse_lease_book
    raw = _source_bytes(period, "lease-schedule")
    if not raw:
        return []
    try:
        return parse_lease_book(raw)
    except Exception:                                        # noqa: BLE001
        return []


def _controls(form: FormDef, period: str) -> dict[str, Decimal]:
    """Live figures for the controls the form prints, so a workbook issued
    next year does not carry this year's totals in its instructions."""
    out: dict[str, Decimal] = {}
    if form.name == "ASSET_REGISTER":
        r = one("""SELECT COALESCE(sum(depreciable_cost), 0) AS basis
                     FROM v_fixed_asset_basis WHERE period = %s""", (period,))
        if r and r["basis"]:
            out["gross_cost"] = Decimal(str(r["basis"]))
        d = one("""SELECT COALESCE(sum(amount), 0) AS depr FROM ledger_line
                    WHERE period = %s AND account ILIKE '5010%%'""", (period,))
        if d and d["depr"]:
            out["depreciation"] = Decimal(str(d["depr"]))
    return out


# ── Issuing ───────────────────────────────────────────────────────────

class IssueIn(BaseModel):
    sent_to: str = ""
    note: str = ""
    blank_rows: int = 60


@router.get("/forms")
def forms() -> list[dict]:
    """What can be asked for. Read off the definitions, so a form added next
    year appears on the screen without anybody editing a list."""
    return [{"name": f.name, "version": f.version, "title": f.title,
             "for_whom": f.for_whom, "purpose": f.purpose,
             "consequence": f.consequence,
             "columns": len(f.columns),
             "required": [c.heading for c in f.required]}
            for f in FORMS.values()]


@router.post("/{form_name}/issue")
def issue(form_name: str, body: IssueIn, period: str = None,
          actor: Actor = Depends(require_own_writes)) -> dict:
    """Record that we asked, and hand back the workbook to send.

    The row is written before the file is handed over, because a request
    nobody can show was made is a request that was not made — and the point
    of the register is to be able to say "we asked on the 4th, twice".
    """
    period = period or settings.period
    form = _form(form_name)
    rid = one("""INSERT INTO information_request
                   (form, form_version, period, issued_by, issued_by_id,
                    sent_to, note)
                 VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING request_id""",
              (form.name, form.version, period, actor.display_name,
               actor.actor_id, body.sent_to.strip(), body.note.strip()))
    record(actor, "REQUEST_ISSUE", "information_request", str(rid["request_id"]),
           after={"form": form.name, "version": form.version,
                  "sent_to": body.sent_to},
           reason=body.note.strip() or f"{form.title} requested")
    return {"request_id": rid["request_id"], "form": form.name,
            "period": period,
            "download": f"/api/requests/{rid['request_id']}/workbook"}


@router.get("/{request_id}/workbook")
def workbook(request_id: int) -> Response:
    """The workbook for a request, built fresh from what is on file now.

    Rebuilt rather than stored: somebody who classified two hundred assets
    between issuing and sending should not post a form that ignores them.
    The form version is pinned to the request, so a request issued against v1
    stays v1 even after a v2 exists — a person filling in a form is entitled
    to the form they were sent.
    """
    r = _request(request_id)
    form = _form(r["form"])
    if form.version != r["form_version"]:
        raise HTTPException(409, {
            "error": "FORM_HAS_MOVED",
            "message": (f"This request was issued against {form.name} "
                        f"v{r['form_version']} and the current form is "
                        f"v{form.version}. Issue a new request rather than "
                        f"sending a workbook whose columns have changed "
                        f"underneath it.")})
    data = build_request_workbook(
        form, r["period"],
        known_rows=_known_rows(form, r["period"]),
        controls=_controls(form, r["period"]))
    name = f"YBI_{form.name}_{r['period']}_request-{request_id}.xlsx"
    return Response(content=data, media_type=XLSX, headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "X-Content-Type-Options": "nosniff"})


def _request(request_id: int) -> dict:
    r = one("SELECT * FROM information_request WHERE request_id = %s",
            (request_id,))
    if not r:
        raise HTTPException(404, "No such request.")
    return r


@router.get("")
def outstanding(period: str = None, state: str = "") -> dict:
    """The chase list."""
    period = period or settings.period
    rows = query("""SELECT * FROM v_information_request
                     WHERE period = %s AND (%s = '' OR state = %s)
                     ORDER BY (state = 'ISSUED') DESC, issued_at DESC""",
                 (period, state, state))
    return {"period": period, "requests": rows,
            "forms": [{"name": f.name, "title": f.title} for f in FORMS.values()]}


# ── The reply ─────────────────────────────────────────────────────────

@router.post("/{request_id}/reply")
async def reply(request_id: int, file: UploadFile = File(...),
                received_from: str = Form(""),
                actor: Actor = Depends(require_own_writes)) -> dict:
    """A filled workbook comes back. Anybody signed in.

    It is read far enough to say whether it is a reply to this request at
    all, and filed as evidence either way it parses — a workbook that will
    not parse is still the document somebody sent, and deleting it because
    the parser disliked a column would lose the only copy.
    """
    r = _request(request_id)
    form = _form(r["form"])
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "That file is empty.")
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, f"That file is {len(raw) / 1e6:.0f} MB; the "
                                 f"limit is {MAX_BYTES // 1024 // 1024} MB.")
    try:
        filled = read_request_workbook(raw, form)
    except WorkbookNotRecognised as exc:
        raise HTTPException(422, {"error": "NOT_THIS_REQUEST",
                                  "message": str(exc)})
    except Exception as exc:                                    # noqa: BLE001
        raise HTTPException(422, {
            "error": "NOT_A_WORKBOOK",
            "message": (f"That file could not be opened as a spreadsheet "
                        f"({type(exc).__name__}). If it was saved as .xls or "
                        f".csv, save it again as .xlsx and send that.")})

    safe = Path(file.filename or "reply.xlsx").name
    sha = hashlib.sha256(raw).hexdigest()
    eid = f"EV-{sha[:12]}"
    existing = one("SELECT evidence_id FROM evidence WHERE sha256 = %s", (sha,))
    if not existing:
        dest = storage.place(
            storage.evidence_path(r["period"], "information-request", sha, safe),
            raw)
        execute("""INSERT INTO evidence (evidence_id, period, kind, uri, sha256,
                                         received_from, byte_size, mime_type,
                                         ingest_channel, uploaded_by, note,
                                         filename)
                   VALUES (%s,%s,'information-request',%s,%s,%s,%s,%s,'UPLOAD',
                           %s,%s,%s)""",
                (eid, r["period"], str(dest), sha,
                 received_from.strip() or actor.display_name, len(raw), XLSX,
                 actor.actor_id,
                 f"Reply to request {request_id} — {form.title}", safe))
    else:
        eid = existing["evidence_id"]

    execute("""UPDATE information_request
                  SET state = 'RECEIVED', reply_evidence_id = %s,
                      received_at = now(), received_from = %s
                WHERE request_id = %s""",
            (eid, received_from.strip() or actor.display_name, request_id))
    record(actor, "REQUEST_REPLY", "information_request", str(request_id),
           after={"form": form.name, "evidence_id": eid, "filename": safe,
                  "rows": len(filled.rows), "problems": len(filled.problems)},
           reason=f"reply received to {form.title}")
    return {"request_id": request_id, "evidence_id": eid,
            "rows": len(filled.rows), "usable": len(filled.usable),
            "problems": len(filled.problems),
            "preview": f"/api/requests/{request_id}/preview"}


def _reread(r: dict) -> tuple[FormDef, Filled]:
    form = _form(r["form"])
    if not r["reply_evidence_id"]:
        raise HTTPException(409, "Nothing has come back for this request yet.")
    ev = one("SELECT uri FROM evidence WHERE evidence_id = %s",
             (r["reply_evidence_id"],))
    if not ev:
        raise HTTPException(404, "The reply is indexed but not on the volume.")
    try:
        raw = Path(ev["uri"]).read_bytes()
    except OSError as exc:
        raise HTTPException(404, f"The reply could not be read back: {exc}")
    return form, read_request_workbook(raw, form)


@router.get("/{request_id}/preview")
def preview(request_id: int) -> dict:
    """What the reply says, what is wrong with it, and what it will do.

    Everything at once. A person correcting a workbook should make one pass,
    not discover the next problem each time they upload.
    """
    r = _request(request_id)
    form, filled = _reread(r)
    controls = []
    for ctl in form.controls:
        expect = _controls(form, r["period"]).get(ctl.column, ctl.expect)
        got = filled.total(ctl.column)
        controls.append({
            "label": ctl.label, "note": ctl.note,
            "expect": str(expect) if expect is not None else None,
            "got": str(got),
            "variance": str(got - expect) if expect is not None else None,
            "ties": bool(expect is not None and abs(got - expect) <= 1),
            "answered": filled.answered(ctl.column),
        })
    return {
        "request_id": request_id, "form": form.name, "title": form.title,
        "period": r["period"], "state": r["state"],
        "rows": len(filled.rows),
        "usable": len(filled.usable),
        "incomplete": len(filled.incomplete),
        "untouched": len(filled.untouched),
        "missing_columns": list(filled.missing_columns),
        "problems": [{"sheet": p.sheet, "row": p.row, "column": p.heading,
                      "value": p.value, "says": p.says, "text": str(p)}
                     for p in filled.problems[:400]],
        "problem_count": len(filled.problems),
        "controls": controls,
        "sample": [{"row": row.number,
                    "values": {k: str(v) for k, v in row.values.items()
                               if v is not None}}
                   for row in filled.usable[:10]],
        "caveat": ("Nothing here is on the record yet. Accepting writes the "
                   "usable rows and leaves the rest to be chased."),
    }


# ── Accepting ─────────────────────────────────────────────────────────
#
# The gate is the portfolio that owns the data, not a new one. Writing
# somebody's answer into the cost record is the same judgment as typing it in
# by hand would be, and it should take the same authority.

_GATES = {"ASSET_REGISTER": require_inventory,
          "SPACE_INVENTORY": require_facilities,
          "PEOPLE_ROSTER": require_admin}


class AcceptIn(BaseModel):
    note: str = ""


@router.post("/{request_id}/accept")
def accept(request_id: int, body: AcceptIn,
           actor: Actor = Depends(current_actor)) -> dict:
    """Write the usable rows, and say what was left behind.

    Rows that are not usable are not written and not silently dropped: the
    count comes back and the preview still names every one of them. A reply
    is rarely complete, and a system that either takes all of it or none of
    it is one that takes none of it.
    """
    r = _request(request_id)
    form = _form(r["form"])
    gate = _GATES.get(form.name)
    if gate is None:
        raise HTTPException(500, f"No gate defined for {form.name}.")
    actor = gate(actor)           # raises 403 with the same sentence as always
    if r["state"] == "ACCEPTED":
        raise HTTPException(409, "This reply has already been accepted. "
                                 "Issue a new request if a corrected "
                                 "workbook has arrived.")
    form, filled = _reread(r)

    writer = {"ASSET_REGISTER": _write_assets,
              "SPACE_INVENTORY": _write_space,
              "PEOPLE_ROSTER": _write_people}[form.name]

    with turn(r["period"]) as cur:
        written, notes = writer(cur, r["period"], filled, actor)
        cur.execute("""UPDATE information_request
                          SET state = 'ACCEPTED', accepted_at = now(),
                              accepted_by = %s, rows_accepted = %s,
                              rows_held_back = %s
                        WHERE request_id = %s""",
                    (actor.display_name, written,
                     len(filled.incomplete) + len(filled.untouched),
                     request_id))
        record(actor, "REQUEST_ACCEPT", "information_request", str(request_id),
               after={"form": form.name, "written": written,
                      "held_back": len(filled.incomplete),
                      "untouched": len(filled.untouched),
                      "problems": len(filled.problems),
                      "evidence_id": r["reply_evidence_id"]},
               reason=body.note.strip() or f"{form.title} accepted",
               cursor=cur)

    return {"request_id": request_id, "written": written,
            "held_back": len(filled.incomplete),
            "untouched": len(filled.untouched),
            "problems": len(filled.problems),
            "notes": notes}


def _write_assets(cur, period: str, filled: Filled, actor: Actor):
    """The register, and the funding behind each asset.

    Funding is written as `asset_funding` rows rather than as columns on the
    asset, because one asset can carry federal, state and debt money at once
    and a column per source is a schema that runs out. A deferred trigger
    refuses funding that exceeds what the asset cost, so an arithmetic
    mistake in the workbook surfaces here rather than in the rate.
    """
    written = 0
    notes: list[str] = []
    evidence = filled
    for row in filled.usable:
        v = row.values
        cur.execute("""
            INSERT INTO asset (asset_id, period, description, serial_number,
                               gl_account, title_holder, acquired_on,
                               in_service_on, disposed_on, gross_cost,
                               book_cost, useful_life_years, accum_depr_close,
                               depreciation, last_inventory_on, note,
                               source_document, evidence_grade, loaded_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    'CORROBORATED',%s)
            ON CONFLICT (asset_id) DO UPDATE SET
              description = EXCLUDED.description,
              serial_number = EXCLUDED.serial_number,
              gl_account = EXCLUDED.gl_account,
              title_holder = EXCLUDED.title_holder,
              acquired_on = EXCLUDED.acquired_on,
              in_service_on = EXCLUDED.in_service_on,
              disposed_on = EXCLUDED.disposed_on,
              gross_cost = EXCLUDED.gross_cost,
              book_cost = EXCLUDED.book_cost,
              useful_life_years = EXCLUDED.useful_life_years,
              accum_depr_close = EXCLUDED.accum_depr_close,
              depreciation = EXCLUDED.depreciation,
              last_inventory_on = EXCLUDED.last_inventory_on,
              note = EXCLUDED.note,
              source_document = EXCLUDED.source_document,
              loaded_by = EXCLUDED.loaded_by""",
            (v["asset_id"], period, v["description"], v.get("serial_number") or "",
             v.get("gl_account") or "", v.get("title_holder") or "",
             v.get("acquired_on"), v.get("in_service_on"), v.get("disposed_on"),
             v["gross_cost"], v.get("book_cost"), v.get("useful_life_years"),
             v.get("accum_depr_close") or 0, v.get("depreciation") or 0,
             v.get("last_inventory_on"), v.get("note") or "",
             f"Request reply — {filled.form.title}", actor.display_name))

        # Replace this asset's funding rather than adding to it: a corrected
        # workbook says what the funding is, not what to add to it.
        cur.execute("DELETE FROM asset_funding WHERE asset_id = %s",
                    (v["asset_id"],))
        for kind, amount_key, ref_key, funder in (
                ("FEDERAL", "federal_amount", "federal_award_reference", ""),
                ("STATE", "state_amount", "state_award_reference", "")):
            amount = v.get(amount_key)
            if amount is None:
                continue        # unanswered is not zero, and not a row
            cur.execute("""INSERT INTO asset_funding
                             (asset_id, kind, amount, award_reference, funder,
                              counted_as_cost_share, note)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (asset_id, kind, award_reference)
                             DO UPDATE SET amount = EXCLUDED.amount""",
                        (v["asset_id"], kind, amount,
                         v.get(ref_key) or "", funder,
                         bool(v.get("counted_as_cost_share")),
                         "From the asset register reply"))
        written += 1

    unanswered = sum(1 for r in filled.usable
                     if r.values.get("federal_amount") is None)
    if unanswered:
        notes.append(f"{unanswered} asset(s) say nothing about federal money. "
                     f"They are on the register and their depreciation is "
                     f"still treated as fully allowable, which is the "
                     f"overstating direction — worth a second ask.")
    return written, notes


def _write_space(cur, period: str, filled: Filled, actor: Actor):
    """Buildings first, then the units inside them.

    A unit needs its facility to exist, and the workbook names buildings by
    name rather than by id — the person filling it in has no idea what a
    facility_id is. So a building named on a row that does not exist yet is
    created from the square feet on its units, and flagged: a building whose
    usable area is the sum of the rows somebody typed cannot then be used to
    check those rows, and the control has to say so rather than tie by
    construction.
    """
    written = 0
    notes: list[str] = []
    known = {r["name"]: r["facility_id"] for r in
             query("SELECT facility_id, name FROM facility WHERE period = %s",
                   (period,))}
    invented: list[str] = []

    by_building: dict[str, list] = {}
    for row in filled.usable:
        by_building.setdefault(row.values["facility_name"].strip(), []).append(row)

    for name, rows in by_building.items():
        fid = known.get(name)
        if not fid:
            fid = "F-" + "".join(ch for ch in name.upper() if ch.isalnum())[:16]
            total = sum((r.values["usable_sqft"] for r in rows), Decimal("0"))
            cur.execute("""INSERT INTO facility (facility_id, period, name,
                                                 usable_sqft, source_document,
                                                 evidence_grade, note)
                           VALUES (%s,%s,%s,%s,%s,'UNSUPPORTED',%s)
                           ON CONFLICT (facility_id) DO NOTHING""",
                        (fid, period, name, total,
                         f"Request reply — {filled.form.title}",
                         "Usable area is the sum of the units reported, so "
                         "the unit control cannot test it. Confirm the "
                         "building's area from the floor plan."))
            known[name] = fid
            invented.append(name)

        for row in rows:
            v = row.values
            unit_id = f"{fid}-" + "".join(
                ch for ch in str(v["label"]).upper() if ch.isalnum())[:20]
            cur.execute("""
                INSERT INTO space_unit (unit_id, facility_id, period, label,
                                        floor, usable_sqft, use, status,
                                        objective_id, occupant, months_occupied,
                                        actual_annual_charge, market_rate_psf,
                                        market_basis, market_source, note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (unit_id) DO UPDATE SET
                  label = EXCLUDED.label, floor = EXCLUDED.floor,
                  usable_sqft = EXCLUDED.usable_sqft, use = EXCLUDED.use,
                  status = EXCLUDED.status,
                  objective_id = EXCLUDED.objective_id,
                  occupant = EXCLUDED.occupant,
                  months_occupied = EXCLUDED.months_occupied,
                  actual_annual_charge = EXCLUDED.actual_annual_charge,
                  market_rate_psf = EXCLUDED.market_rate_psf,
                  market_basis = EXCLUDED.market_basis,
                  market_source = EXCLUDED.market_source,
                  note = EXCLUDED.note""",
                (unit_id, fid, period, v["label"], v.get("floor") or "",
                 v["usable_sqft"], v["use"], v["status"],
                 _objective(cur, v.get("objective_id")),
                 v.get("occupant") or "", v.get("months_occupied") or 12,
                 v.get("actual_annual_charge"), v.get("market_rate_psf"),
                 v.get("market_basis") or "",
                 f"Request reply — {filled.form.title}",
                 v.get("note") or ""))
            written += 1

    if invented:
        notes.append("Created " + ", ".join(invented) + " from the rows "
                     "reported. Their usable area is the sum of those rows, "
                     "so the square-foot control cannot test them until "
                     "somebody confirms the area from the floor plan.")
    return written, notes


def _objective(cur, name: str | None) -> str | None:
    """Match a programme the way somebody would say it, or leave it unset.

    Never guesses: an exact id, then an exact label, then nothing. A
    programme matched loosely puts space on the wrong award, which is the
    kind of error nobody finds because every total still foots.
    """
    if not name:
        return None
    cur.execute("""SELECT objective_id FROM cost_objective
                    WHERE objective_id = %s
                       OR lower(btrim(label)) = lower(btrim(%s))
                    LIMIT 1""", (name, name))
    got = cur.fetchone()
    return got["objective_id"] if got else None


def _write_people(cur, period: str, filled: Filled, actor: Actor):
    """Addresses onto the accounts that exist, and a list of the rest.

    This deliberately does not create accounts. Provisioning runs down a
    ladder with a password sheet and a person handing it over; conjuring
    thirty-seven accounts out of a spreadsheet would put people into the
    system who have never been told they are in it. What it does is fill in
    the address and mark it confirmed, which is what the roster was blocking.
    """
    written = 0
    notes: list[str] = []
    no_account: list[str] = []
    already: list[str] = []
    spans = 0
    span_held: list[str] = []
    for row in filled.usable:
        v = row.values
        spans += _employment_span(cur, period, v, actor, span_held)
        # Only where nobody has confirmed an address yet.
        #
        # This is the rule provisioning already follows for passwords, and it
        # is here for the same reason: an account on an address somebody else
        # chose stops belonging to the person. Without the filter a roster
        # reply renamed the organisation's administrator — Barb Ewing's
        # account became "Dolores Wallace" at a different address because the
        # payroll register happens to key her as EWING, and she could not
        # sign in afterwards. A spreadsheet from outside the organisation had
        # taken over the account that provisions every other account.
        #
        # `display_name` is never touched at all. A name is what the audit
        # trail records every change under, and changing it rewrites how
        # every past entry reads.
        cur.execute("""UPDATE actor SET email = %s, email_confirmed = true
                        WHERE employee_key = %s
                          AND NOT email_confirmed
                        RETURNING actor_id""",
                    (v["email"].strip().lower(), v["employee_key"]))
        if cur.fetchone():
            written += 1
            continue
        cur.execute("""SELECT display_name, email FROM actor
                        WHERE employee_key = %s""", (v["employee_key"],))
        held = cur.fetchone()
        if held:
            already.append(f"{held['display_name']} ({held['email']})")
        else:
            no_account.append(f"{v.get('first_name','')} {v.get('surname','')} "
                              f"({v['employee_key']})".strip())
    if spans:
        notes.append(f"{spans} employment span(s) recorded — the effort "
                     f"distribution has a denominator for those people now.")
    if span_held:
        notes.append(f"{len(span_held)} row(s) gave terms that could not be "
                     f"recorded: {', '.join(span_held[:6])}"
                     f"{'…' if len(span_held) > 6 else ''}.")
    if already:
        notes.append(f"{len(already)} address(es) were left alone because "
                     f"somebody has already confirmed them: "
                     f"{', '.join(already[:6])}"
                     f"{'…' if len(already) > 6 else ''}. Changing an address "
                     f"somebody signs in with is an account change, not a "
                     f"correction — do it from the People screen, where it is "
                     f"one person deciding about one account.")
    if no_account:
        notes.append(f"{len(no_account)} of these people have no account yet, "
                     f"so their address is recorded nowhere: "
                     f"{', '.join(no_account[:8])}"
                     f"{'…' if len(no_account) > 8 else ''}. Provision them "
                     f"from the People screen — an account is handed over by "
                     f"a person, not conjured from a spreadsheet.")
    return written, notes


def _employment_span(cur, period: str, v: dict, actor: Actor,
                     held: list[str]) -> int:
    """The terms somebody worked under, where the row says all three.

    Status, weekly hours and a start date are each NOT NULL on `employment`,
    so a partial answer is not a partial row — it is no row, and saying which
    is more use than a constraint violation. Hours especially: defaulting a
    blank to 40 would understate every part-timer's effort by exactly the
    amount that matters, and this is the one figure that may never come from
    the person being measured.

    An existing live span is never superseded from a spreadsheet. Correcting
    somebody's terms is the same kind of act as changing their address —
    `employment` is immutable and append-only by trigger, a correction closes
    one span and opens another, and that belongs to a person on the
    Employment screen rather than to a file arriving by email.
    """
    key = v.get("employee_key")
    status = v.get("status")
    hours = v.get("weekly_hours")
    start = v.get("employed_from")
    if not key or not any((status, hours, start)):
        return 0                    # the row said nothing about terms
    who = f"{v.get('first_name','')} {v.get('surname','')}".strip() or key
    missing = [name for name, got in (("employment type", status),
                                      ("hours a week", hours),
                                      ("employed from", start)) if not got]
    if missing:
        held.append(f"{who} (no {', no '.join(missing)})")
        return 0
    if not (0 < hours <= 80):
        held.append(f"{who} ({hours} hours a week is outside 0 to 80)")
        return 0

    cur.execute("""SELECT 1 FROM employment
                    WHERE period = %s AND employee_key = %s
                      AND superseded_at IS NULL LIMIT 1""", (period, key))
    if cur.fetchone():
        held.append(f"{who} (terms already on file — correct them on the "
                    f"Employment screen, which closes the old span)")
        return 0

    cur.execute("""INSERT INTO employment
                     (period, employee_key, status, weekly_hours,
                      employed_from, employed_to, source_document, note,
                      recorded_by, recorded_name)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (period, key, status, hours, start, v.get("employed_to"),
                 "Roster reply", v.get("job_title") or "",
                 actor.actor_id, actor.display_name))
    return 1
