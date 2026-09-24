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

import functools

import hashlib
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app import storage
from app.audit import record
from app.auth import (Actor, current_actor, require_admin, require_controller, require_facilities,
                      require_inventory, require_own_writes, require_reader)
from app.db import execute, one, query, transaction
from app import shapes
from app.domain.core import money
from app.domain.request_forms import FORMS, Form as FormDef
from app.domain.request_intake import (Filled, WorkbookNotRecognised,
                                       read_request_workbook)
from app.domain.request_forms import verification_rows
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
        # **The register first, and the schedule only where there is none.**
        # `_asset_schedule` re-parses the source xls, so a workbook issued
        # today describes the document rather than the record — and the two
        # part company the moment anybody corrects an asset. *Read the
        # record, never recall it*, applied to what a form asks about.
        #
        # It also happens to be the only version of this that is safe over
        # time. The parser's key changed once: `085` made it
        # `FA-<gl account>-<system>` because system number 165 is two assets
        # in two accounts and keying on the system number alone had already
        # lost one of them. A workbook issued before that carries `FA-162`
        # against a register holding `FA-1501-162`, so **not one of its 262
        # ids matches** — which is a real reply now on file, and `_asset_keys`
        # is what reads it. Pre-filling from the register cannot drift from
        # the register; pre-filling from a parser can, and did.
        held = query("""SELECT asset_id, description, gl_account,
                               in_service_on, gross_cost, book_cost,
                               useful_life_years, accum_depr_close,
                               depreciation
                          FROM asset WHERE period = %s
                         ORDER BY gl_account, asset_id""", (period,))
        if held:
            return [{"asset_id": a["asset_id"],
                     "description": a["description"],
                     "gl_account": a["gl_account"],
                     "in_service_on": a["in_service_on"],
                     "gross_cost": a["gross_cost"],
                     "book_cost": a["book_cost"] or a["gross_cost"],
                     "useful_life_years": a["useful_life_years"],
                     "accum_depr_close": a["accum_depr_close"],
                     "depreciation": a["depreciation"],
                     "note": ""}
                    for a in held]
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
        # Three sources, and the order is the point.
        #
        # **A reply somebody has already sent and nobody has accepted beats
        # the register**, because it is the most recent thing that person
        # said and the register may still hold an estimate we derived while
        # waiting for them. Showing them our estimate in place of their own
        # floor plan is the worst possible second pass: they cannot tell what
        # they answered from what we guessed, so they check all of it.
        #
        # Once the reply is accepted the register *is* the record and comes
        # first. The lease book is the fallback it always was — twenty-six
        # tenants with the building and the rent, and no square footage,
        # which is the one thing only a floor plan knows.
        rows = _space_from_reply(period, form) or _space_from_register(period)
        if not rows:
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
            if not any(x.get("facility_name") == r["name"] for x in rows):
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

    if form.name == "VERIFICATION":
        # The nineteen items, read out of domain/verification_items.py — the
        # same list the printed worksheet and docs/FOR_TOM_TO_VERIFY.md are
        # checked against. Any answer already on the record goes out in the
        # row, so a second issue of this workbook is a chase rather than a
        # blank page: somebody who settled six items last week should see
        # their six answers and the thirteen still open.
        answered = {r["ref"]: r for r in query(
            """SELECT ref, status, answer, answered_by
                 FROM verification_answer
                WHERE period = %s AND superseded_at IS NULL""", (period,))}
        out = []
        for row in verification_rows():
            prior = answered.get(row["ref"])
            if prior:
                row = {**row, "status": prior["status"],
                       "answer": prior["answer"],
                       "answered_by": prior["answered_by"]}
            out.append(row)
        return out

    return []


#: Columns of the space form that a second pass carries across from whatever
#: was said last. `use` is deliberately among them — the question v2 asks is
#: whether the answer given is still the right one now the column explains
#: itself, and blanking it would make somebody re-read thirty-eight rows from
#: scratch. `occupancy_basis` is the one column v1 never had, so it comes back
#: empty on every row, which is what makes the new ask visible.
_SPACE_CARRY = ("facility_name", "label", "floor", "usable_sqft", "use",
                "status", "occupant", "objective_id", "months_occupied",
                "actual_annual_charge", "market_rate_psf", "market_basis",
                "occupancy_basis", "note")


def _space_from_reply(period: str, form: FormDef) -> list[dict]:
    """The last reply on file that nobody has accepted, read back as rows.

    A row the intake held back comes back with **what was wrong with it in
    the note**, because those rows are still outstanding and a second
    workbook that showed them as ordinary rows would ask somebody to notice
    on their own that three of thirty-eight never landed.
    """
    row = one("""SELECT r.reply_evidence_id, e.uri
                   FROM information_request r
                   JOIN evidence e ON e.evidence_id = r.reply_evidence_id
                  WHERE r.form = %s AND r.period = %s AND r.state = 'RECEIVED'
                  ORDER BY r.received_at DESC LIMIT 1""",
             (form.name, period))
    if not row:
        return []
    try:
        raw = Path(row["uri"]).read_bytes()
    except OSError:
        return []
    try:
        filled = read_request_workbook(raw, form)
    except Exception:                                        # noqa: BLE001
        # A reply that will not parse is a thing to fix, not a reason to stop
        # asking — the same rule the asset schedule and the lease book follow.
        return []

    held = {}
    for pr in filled.problems:
        if pr.row:
            held.setdefault(pr.row, []).append(f"{pr.heading}: {pr.says}")

    out: list[dict] = []
    for r in filled.rows:
        # **Every row comes back, touched or not.** `touched` asks whether a
        # person changed a row *relative to what we sent them*, which is the
        # right question for "did anybody get to this" and the wrong one here:
        # twenty-seven of Heidi's thirty-eight rows matched the lease book we
        # pre-filled, so a `touched` filter dropped two thirds of her estate
        # and re-asked her to type it. Found by counting the rows in the
        # workbook against the rows in the reply.
        d = {k: r.values.get(k) for k in _SPACE_CARRY
             if r.values.get(k) not in (None, "")}
        if not d.get("facility_name"):
            continue
        says = held.get(r.number, [])
        for k in r.missing_required:
            says.append(f"{k}: was required and was blank")
        if says:
            d["note"] = ("HELD BACK LAST TIME — " + "; ".join(says)
                         + (f" (you wrote: {d['note']})" if d.get("note") else ""))
        out.append(d)
    return out


def _space_from_register(period: str) -> list[dict]:
    """What the register holds, for a second pass after a reply was accepted."""
    rows = query("""SELECT f.name AS facility_name, u.label, u.floor,
                           u.usable_sqft, u.use::text AS use,
                           u.status::text AS status, u.occupant,
                           u.objective_id, u.months_occupied,
                           u.actual_annual_charge, u.market_rate_psf,
                           u.market_basis, u.occupancy_basis, u.note
                      FROM space_unit u
                      JOIN facility f ON f.facility_id = u.facility_id
                     WHERE u.period = %s
                     ORDER BY f.name, u.usable_sqft DESC""", (period,))
    return [{k: v for k, v in dict(r).items() if v not in (None, "")}
            for r in rows]


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


def _notes_from_the_record(form: FormDef, period: str) -> tuple[str, ...]:
    """Instructions the register supplies, read at the moment of issue.

    The space book's rows are filed against a **building name**, and a name
    the register does not hold creates a building beside the one meant — five
    became nine on a driven copy of the record, one of them carrying twice its
    own floor area. The names cannot be written on the `Form`, because the
    form is a definition and this is a reading of the database.
    """
    if form.name != "SPACE_INVENTORY":
        return ()
    names = [r["name"] for r in query(
        "SELECT name FROM facility WHERE period = %s ORDER BY name",
        (period,))]
    if not names:
        return ()
    return ("The buildings on the record are: " + "; ".join(names) + ". "
            "Use these names exactly in the Building column. A name that is "
            "not one of these creates a second building beside the first and "
            "the estate is counted twice — if one of your buildings is one of "
            "these under a different name, use the name on this list and say "
            "so in the note.",)


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
        controls=_controls(form, r["period"]),
        notes=_notes_from_the_record(form, r["period"]))
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

@router.get("/verification")
def verification(period: str = None) -> dict:
    """Where the nineteen stand, and what each one moves.

    Reading, so it takes the router's own `require_reader` and nothing
    narrower — the auditor's first question about any of these is going to be
    "who said that, and on what", and the answer is on this screen with the
    workbook behind it.

    An item with no answer is **unanswered**, which is a different fact from
    STILL CHECKING and stays different all the way to the screen: one means
    nobody has looked and the other means somebody has and cannot say yet.
    """
    period = period or settings.period
    live = {r["ref"]: r for r in query(
        """SELECT * FROM v_verification_status WHERE period = %s""", (period,))}
    items = []
    for row in verification_rows():
        got = live.get(row["ref"])
        items.append({
            "ref": row["ref"], "area": row["area"], "title": row["title"],
            "figure": row["figure"], "asks": row["asks"], "moves": row["moves"],
            "status": got["status"] if got else None,
            "answer": got["answer"] if got else "",
            "answered_by": got["answered_by"] if got else "",
            "accepted_by": got["accepted_by"] if got else "",
            "accepted_at": got["accepted_at"].isoformat() if got else None,
            "evidence_id": got["evidence_id"] if got else None,
            "evidence_filename": got["evidence_filename"] if got else None,
            "answers": got["answers"] if got else 0,
            "settled": bool(got and got["settled"]),
        })
    return {"period": period, "items": items,
            "settled": sum(1 for i in items if i["settled"]),
            "answered": sum(1 for i in items if i["status"]),
            "total": len(items)}


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
        text, pages = storage.read_text(raw, XLSX)
        execute("""INSERT INTO evidence (evidence_id, period, kind, uri, sha256,
                                         received_from, byte_size, mime_type,
                                         ingest_channel, uploaded_by, note,
                                         filename, extracted_text, page_count)
                   VALUES (%s,%s,'information-request',%s,%s,%s,%s,%s,'UPLOAD',
                           %s,%s,%s,%s,%s)""",
                (eid, r["period"], str(dest), sha,
                 received_from.strip() or actor.display_name, len(raw), XLSX,
                 actor.actor_id,
                 f"Reply to request {request_id} — {form.title}", safe,
                 text, pages))
        # The form as well as the text — one reading, at every door, so a
        # family's shapes can be compared rather than discovered.
        shapes.record_shape(eid, raw, XLSX)
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
        "lands_on": (_space_lands_on(r["period"], filled)
                     if form.name == "SPACE_INVENTORY" else
                     _asset_lands_on(r["period"], filled)
                     if form.name == "ASSET_REGISTER" else []),
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
          "PEOPLE_ROSTER": require_admin,
          # The narrow portfolios do not add up to CONTROLLER and this list
          # does not divide along them: item 1.3 is the asset register
          # against the balance sheet, 2.2 is whether Rising Tides is
          # federally funded, 5.1 is an invoice date. Settling any of them
          # changes what the rate rests on, which is the controller's
          # judgment by the same rule that only a controller may seal.
          "VERIFICATION": require_controller}


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
              "PEOPLE_ROSTER": _write_people,
              # The only writer that records where its rows came from. The
              # other three write facts — an asset's funding source, a
              # suite's square footage — whose provenance is the request row
              # itself. An answer is somebody's judgment, so it carries the
              # workbook it was given in, and "who said this and on what"
              # answers with a file rather than with a join.
              "VERIFICATION": functools.partial(
                  _write_verification,
                  evidence_id=r["reply_evidence_id"])}[form.name]

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


def _write_verification(cur, period: str, filled: Filled, actor: Actor,
                        evidence_id: str | None = None):
    """The controller's answers, each against the item it settles.

    Superseding rather than editing. A second answer to the same item marks
    the first superseded and both stay — several of these are *expected* to
    change answer, and the sequence is what an auditor is reconstructing.
    Item 1.3 will become "confirmed, timing" when the 31 December register
    arrives; item 0 is confirmed except that the QuickBooks entry has not
    been reposted, and when it is the reconciling item has to come off with
    it.
    """
    known = {i["ref"] for i in verification_rows()}
    written = 0
    notes: list[str] = []
    unknown: list[str] = []
    unchanged: list[str] = []
    replaced = 0

    for row in filled.usable:
        v = row.values
        ref = str(v["ref"]).strip()
        if ref not in known:
            # A ref we did not send is a row somebody added, and there is
            # nothing for it to be an answer *to*. Named rather than written,
            # because the alternative is an answer floating free of any item.
            unknown.append(f"row {row.number} ({ref!r})")
            continue

        status = str(v["status"]).strip()
        answer = str(v.get("answer") or "").strip()
        by = str(v.get("answered_by") or "").strip() or actor.display_name

        cur.execute("""SELECT answer_id, status, answer FROM verification_answer
                        WHERE period = %s AND ref = %s AND superseded_at IS NULL""",
                    (period, ref))
        prior = cur.fetchone()
        if prior and prior["status"] == status and prior["answer"] == answer:
            # The workbook goes out carrying the answers already on the
            # record, so a second issue is a chase rather than a blank page —
            # which means most rows in a returned one say what they already
            # said. Superseding an answer with itself would fill the history
            # with movement that did not happen.
            unchanged.append(ref)
            continue

        # Supersede first, then insert. `one_live_answer_per_item` is a
        # partial unique index and an index is checked at the moment of the
        # insert, not at COMMIT — so writing the successor while the
        # predecessor is still live is refused outright. It was, the first
        # time this ran.
        if prior:
            cur.execute("""UPDATE verification_answer SET superseded_at = now()
                            WHERE answer_id = %s""", (prior["answer_id"],))
            replaced += 1
        cur.execute("""INSERT INTO verification_answer
                         (period, ref, status, answer, answered_by,
                          accepted_by, evidence_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (period, ref, status, answer, by, actor.display_name,
                     evidence_id))
        written += 1

    if replaced:
        notes.append(f"{replaced} item(s) answered again — the earlier answer "
                     f"is superseded and still on the record")
    if unchanged:
        notes.append(f"{len(unchanged)} item(s) came back saying what they "
                     f"already said, and were left alone: "
                     + ", ".join(sorted(unchanged)[:8])
                     + ("…" if len(unchanged) > 8 else ""))
    if unknown:
        notes.append("no such item on the list, so nothing was written for "
                     + ", ".join(unknown)
                     + " — an answer with no question is not an answer")

    # On `cur`, not on a pooled connection. `query()` here read the state
    # before this transaction and reported "0 of 19 items settled" in the
    # same breath as writing three settlements — the rule CLAUDE.md already
    # states for the seal, in a smaller shape: read what you are about to
    # depend on inside the turn.
    cur.execute("""SELECT count(*) AS n FROM v_verification_status
                    WHERE period = %s AND settled""", (period,))
    settled = cur.fetchone()["n"]
    notes.append(f"{settled} of {len(known)} items settled, "
                 f"{len(known) - settled} still open")
    return written, notes


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
    keys = _asset_keys(period, filled)
    landed = {"on": 0, "by account": 0, "new": 0}
    for row in filled.usable:
        v = dict(row.values)
        # Read through the same resolver the preview printed, so the panel
        # and the write cannot disagree about which asset this is.
        key, how = keys.get(row.number, (v.get("asset_id"), "new"))
        v["asset_id"] = key
        landed[how] += 1
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

    if landed["by account"]:
        notes.append(
            f"{landed['by account']} row(s) named the schedule's own asset "
            f"id and were resolved to the register through the account each "
            f"names. The workbook went out carrying the wrong key; the rows "
            f"landed on the assets already on file rather than beside them.")
    if landed["new"]:
        notes.append(
            f"{landed['new']} row(s) are not on the register and were "
            f"created. If that is more than you expected, the reply is "
            f"keyed differently from the register and the rest of it has "
            f"landed beside your assets rather than on them.")
    unanswered = sum(1 for r in filled.usable
                     if r.values.get("federal_amount") is None)
    if unanswered:
        notes.append(f"{unanswered} asset(s) say nothing about federal money. "
                     f"They are on the register and their depreciation is "
                     f"still treated as fully allowable, which is the "
                     f"overstating direction — worth a second ask.")
    return written, notes


def _asset_keys(period: str, filled) -> dict[int, tuple[str, str]]:
    """Which asset each reply row lands on, by row number.

    Returns `{row.number: (asset_id, how)}` where *how* is `on` for a row
    that lands on an asset already on the register, `by account` for one
    resolved through the account it names, and `new` for one that would
    create an asset.

    **One definition, read by the preview and by the writer**, the way
    `subject_merged()` is for a recommendation: a panel that says what will
    happen and a writer that does something else is worse than no panel.

    Two ways to land, and the second exists because **a key changed under a
    workbook that was already out.** `085` made the register's key
    `FA-<gl account>-<system>` — system number 165 is two assets in two
    accounts, and keying on the system number alone had already lost one of
    them. A workbook issued before that carries `FA-162` against a register
    holding `FA-1501-162`, so **not one of its 262 ids matches**: that is a
    real reply, 263 rows, every one of them answered.

    Nothing was wrong with the form when it went out, which is the point.
    A register may be re-keyed for a good reason while an ask is in
    somebody's inbox, and the answer that comes back is still the answer.

    It is a rule and not a guess: the account is a column the reply carries,
    the reconstruction is exactly the key `load_assets.py` builds, and it was
    checked against `gross_cost` — an independent figure neither side derived
    from the other — on all 263 rows. **More than one candidate means no
    candidate**, which is the rule `/api/reconcile/propose` follows, so an id
    that resolves ambiguously is treated as new rather than guessed at.
    """
    held = {r["asset_id"]: r["gl_account"] for r in
            query("SELECT asset_id, gl_account FROM asset WHERE period = %s",
                  (period,))}
    out: dict[int, tuple[str, str]] = {}
    for row in filled.usable:
        rid = str(row.values.get("asset_id") or "").strip()
        if not rid:
            continue
        if rid in held:
            out[row.number] = (rid, "on")
            continue
        gl = str(row.values.get("gl_account") or "").strip()
        candidates = [k for k in held
                      if gl and k == f"FA-{gl}-{rid.removeprefix('FA-')}"]
        if len(candidates) == 1:
            out[row.number] = (candidates[0], "by account")
        else:
            out[row.number] = (rid, "new")
    return out


def _asset_lands_on(period: str, filled) -> list[dict]:
    """What accepting an asset reply would land on, and what it would create.

    `_space_lands_on` exists because a reply naming a building the register
    does not hold **invents** one whose area is the sum of the rows just
    written, so it ties by construction and says nothing at all. The asset
    form has the identical shape — `_write_assets` upserts on `asset_id`, so
    a key that never collides inserts — and it had no panel.

    That is not hypothetical. A reply written against the pre-`085` key would
    have put 263 new assets beside the 263 already on file and doubled a
    $23,419,573.64 basis, and the only thing that could have said so in
    advance was this panel. It was the empty `lands_on` on that preview that
    made anybody look. A rule fixed in one arm is one somebody gets wrong in
    the other two.
    """
    keys = _asset_keys(period, filled)
    by_how: dict[str, list[str]] = {"on": [], "by account": [], "new": []}
    for row in filled.usable:
        hit = keys.get(row.number)
        if hit:
            by_how[hit[1]].append(str(row.values.get("asset_id")))
    said = {
        "on": "lands on an asset already on the register",
        "by account": "resolved to the register through the account it names "
                      "— the workbook carries the schedule's own id and the "
                      "register is keyed by account and id",
        "new": "is not on the register; accepting would create it",
    }
    return [{"how": how, "rows": len(ids), "what_it_means": said[how],
             "examples": ids[:6]}
            for how, ids in by_how.items() if ids]


def _space_lands_on(period: str, filled) -> list[dict]:
    """What accepting a space reply would land on, building by building.

    The router's own promise is that *the preview says exactly what it will
    do*, and on this form it did not say the one thing that matters most.
    Driven on a clone of the reference record: accepting Heidi's measured
    plan produced **nine buildings where there are five** and left Tech Block
    Building 5 carrying fourteen rows summing to 109,179 square feet against
    a usable area of 54,308 — her rooms **plus** the derived lump row the
    close had put there, double counted, with the 200.465 carve-out taken
    over the result.

    Two shapes, and only one of them is visible afterwards:

      * a name the register already holds **adds** to it, because a unit id
        is derived from the label and the lump row's id is not one of them —
        `v_space_unit_control` reports `ties False` and somebody has to look;
      * a name it does not hold **invents a building**, whose usable area is
        the sum of the rows just written, so it ties perfectly by
        construction and says nothing at all. Four of the nine were this.

    So the preview says both, before anybody presses Accept.
    """
    named: dict[str, dict] = {}
    for row in filled.usable:
        name = str(row.values.get("facility_name") or "").strip()
        if not name:
            continue
        d = named.setdefault(name, {"building": name, "rows": 0,
                                    "sqft": Decimal("0")})
        d["rows"] += 1
        d["sqft"] += row.values.get("usable_sqft") or Decimal("0")

    have = {r["name"]: r for r in query(
        """SELECT f.name, f.facility_id, f.usable_sqft,
                  COALESCE((SELECT count(*) FROM space_unit u
                             WHERE u.facility_id = f.facility_id
                               AND u.period = f.period), 0) AS units,
                  COALESCE((SELECT sum(u.usable_sqft) FROM space_unit u
                             WHERE u.facility_id = f.facility_id
                               AND u.period = f.period), 0) AS unit_sqft
             FROM facility f WHERE f.period = %s""", (period,))}

    out = []
    for name, d in sorted(named.items()):
        cur = have.get(name)
        if not cur:
            out.append({**d, "sqft": str(money(d["sqft"])),
                        "on_the_record": False,
                        "says": "No building of this name is on the record, so "
                                "accepting creates one whose usable area is "
                                "the sum of these rows — which then ties by "
                                "construction and can check nothing. If this "
                                "is one of the buildings already on the "
                                "record under another name, correct the name "
                                "in the workbook first."})
        else:
            out.append({**d, "sqft": str(money(d["sqft"])),
                        "on_the_record": True,
                        "already": int(cur["units"]),
                        "already_sqft": str(money(cur["unit_sqft"])),
                        "usable_sqft": str(money(cur["usable_sqft"])),
                        # Plain prose and the house spelling for a figure.
                        # The screen renders this as text: markdown reaches
                        # the reader as literal asterisks, and `money()`
                        # returns a Decimal, so `15448.00` printed beside
                        # `15,448.00` in the column next to it. Both are in
                        # CLAUDE.md already, one of them twice.
                        "says": (f"{cur['units']} row(s) of "
                                 f"{money(cur['unit_sqft']):,.2f} sq ft are "
                                 f"already on this building. These are added "
                                 f"to them, not put in their place — remove "
                                 f"the rows this replaces first, or the estate "
                                 f"is counted twice and the 200.465 carve-out "
                                 f"is taken over the result.")
                        if cur["units"] else
                        "Nothing is recorded against this building yet."})
    return out


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
                                        market_basis, market_source,
                                        occupancy_basis, note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                  occupancy_basis = EXCLUDED.occupancy_basis,
                  note = EXCLUDED.note""",
                (unit_id, fid, period, v["label"], v.get("floor") or "",
                 v["usable_sqft"], v["use"], v["status"],
                 _objective(cur, v.get("objective_id")),
                 v.get("occupant") or "", v.get("months_occupied") or 12,
                 v.get("actual_annual_charge"), v.get("market_rate_psf"),
                 v.get("market_basis") or "",
                 f"Request reply — {filled.form.title}",
                 v.get("occupancy_basis") or "",
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
