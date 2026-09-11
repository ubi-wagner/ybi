#!/usr/bin/env python3
"""Every boundary in the access model, proved against a live ledger.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/drive_access.py

Two axes, and the drive walks both. Rank decides who may create accounts and
only runs downward. Portfolios decide who may judge what, do not add up to
each other, and never add up to the seal.

A permission claim is worth what it is tested at. These are signed-in HTTP
calls against real rows, not assertions about a table.
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

PASS, FAIL = [], []


def ok(msg: str) -> None:
    PASS.append(msg)
    print(f"  ok       {msg}", flush=True)


def bad(msg: str) -> None:
    FAIL.append(msg)
    print(f"  FAIL     {msg}", file=sys.stderr, flush=True)


def check(c: httpx.Client, method: str, path: str, expect: int, what: str,
          **kw) -> httpx.Response:
    r = c.request(method, path, **kw)
    (ok if r.status_code == expect else bad)(
        f"{what} — {r.status_code}" +
        ("" if r.status_code == expect else f" (wanted {expect})"))
    return r


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=60)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email}: {r.status_code}")
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    pw = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw:
        raise SystemExit("YBI_SEED_PASSWORD is required.")

    # ── Rank runs downward ───────────────────────────────────────────
    print("\nRank — who may create an account")
    eric = sign_in(args.base, "eric.c.wagner@gmail.com", pw)
    barb = sign_in(args.base, "bewing@ybi.org", pw)
    tom = sign_in(args.base, "tom@ybi.org", pw)
    heidi = sign_in(args.base, "hruby@ybi.org", pw)
    auditor = sign_in(args.base, "auditor@ybi.org", pw)
    try:
        me = eric.get("/api/auth/me").json()
        # The ladder is "strictly below", not "exactly one rung below": if
        # the organisation's administrator is away, the system administrator
        # can still set somebody up. What neither can do is create a peer.
        (ok if "ORG_ADMIN" in me["may_provision"]
               and "SYSTEM_ADMIN" not in me["may_provision"] else bad)(
            f"a system administrator creates below themselves and never a "
            f"peer — {sorted(me['may_provision'])}")
        me = barb.get("/api/auth/me").json()
        (ok if set(me["may_provision"]) == {"CONTROLLER", "EMPLOYEE", "AUDITOR"}
         else bad)(f"an organisation administrator may create the finance "
                   f"roles — {sorted(me['may_provision'])}")

        body = {"email": "peer-test@ybi.org", "display_name": "Peer",
                "password": "a-long-enough-password-1"}
        check(eric, "POST", "/api/auth/actors", 403,
              "a system administrator cannot create another one",
              json={**body, "role": "SYSTEM_ADMIN"})
        check(barb, "POST", "/api/auth/actors", 403,
              "an organisation administrator cannot create another one",
              json={**body, "role": "ORG_ADMIN"})
        check(barb, "POST", "/api/auth/actors", 403,
              "nor a system administrator above them",
              json={**body, "role": "SYSTEM_ADMIN"})
        check(tom, "POST", "/api/auth/actors", 403,
              "a controller cannot create accounts at all",
              json={**body, "role": "EMPLOYEE", "employee_key": "X"})
        check(eric, "GET", "/api/auth/actors", 200,
              "a system administrator reads the roster")
        check(tom, "GET", "/api/auth/actors", 403,
              "a controller does not")

        # ── Portfolios do not add up to the seal ─────────────────────
        print("\nPortfolios — the seal is not a sum of other authority")
        roster = {r["email"]: r for r in barb.get("/api/auth/actors").json()}
        heidi_id = roster["hruby@ybi.org"]["actor_id"]

        check(barb, "POST", f"/api/auth/actors/{heidi_id}/portfolios/revoke", 200,
              "the organisation administrator takes CONTROLLER back from Heidi",
              json={"portfolio": "CONTROLLER",
                    "reason": "Access drive: proving the seal stands alone."})
        heidi2 = sign_in(args.base, "hruby@ybi.org", pw)
        me = heidi2.get("/api/auth/me").json()
        (ok if not me["may_seal"] else bad)(
            "she keeps four portfolios and may no longer seal — "
            f"{','.join(me['portfolios'])}")
        check(heidi2, "POST", "/api/rates/seal", 403,
              "four portfolios do not add up to sealing", json={"note": "drive"})
        check(heidi2, "POST", "/api/rates/compute", 403,
              "nor to computing a rate", json={})
        check(heidi2, "GET", "/api/facilities", 200,
              "her facilities work is untouched")
        check(heidi2, "GET", "/api/facilities/equipment", 200,
              "so is her inventory work")
        check(barb, "POST", f"/api/auth/actors/{heidi_id}/portfolios", 201,
              "and the administrator can give it back",
              json={"portfolio": "CONTROLLER",
                    "reason": "Access drive: restoring after the proof."})
        heidi2.close()

        # ── Nobody grants themselves ─────────────────────────────────
        print("\nNobody grants themselves authority")
        barb_id = roster["bewing@ybi.org"]["actor_id"]
        check(barb, "POST", f"/api/auth/actors/{barb_id}/portfolios", 403,
              "an administrator cannot grant themselves a portfolio",
              json={"portfolio": "CONTROLLER",
                    "reason": "Access drive: this must be refused."})
        me = barb.get("/api/auth/me").json()
        (ok if not me["portfolios"] else bad)(
            "the organisation administrator still judges nothing")

        # ── The narrow portfolios open their own door ────────────────
        #
        # CONTROLLER is the main one and does open every door — it is the
        # role the whole system was built around, and fencing the controller
        # out of the buildings would be an obstacle rather than a control.
        # What matters is the other direction: holding the narrow ones does
        # not accumulate into it, which is proved above.
        #
        # Revoking closed Heidi's sessions, correctly, so she signs in again.
        print("\nThe narrow portfolios open their own door")
        heidi.close()
        heidi = sign_in(args.base, "hruby@ybi.org", pw)
        check(tom, "GET", "/api/classify/queue?limit=1", 200,
              "Tom classifies")
        check(tom, "PUT", "/api/facilities", 200,
              "and CONTROLLER, the main portfolio, reaches the buildings too",
              json={"facility_id": "DRIVE-TEST", "name": "Drive test building",
                    "usable_sqft": 100, "owned": True,
                    "source_document": "Access drive."})
        check(heidi, "PUT", "/api/facilities", 200,
              "so does Heidi, who holds FACILITIES in her own right",
              json={"facility_id": "DRIVE-TEST", "name": "Drive test building",
                    "usable_sqft": 100, "owned": True,
                    "source_document": "Access drive."})

        # ── Reading, writing, and the auditor ────────────────────────
        print("\nThe auditor reads everything and writes nothing")
        check(auditor, "GET", "/api/reconcile", 200, "reads the register")
        check(auditor, "GET", "/api/export/audit-package", 200,
              "takes the whole package away")
        check(auditor, "POST", "/api/rates/seal", 403, "cannot seal",
              json={"note": "drive"})
        check(auditor, "PUT", "/api/facilities", 403, "cannot touch a building",
              json={"facility_id": "X", "name": "X", "usable_sqft": 1})
        check(auditor, "GET", "/api/auth/actors", 403, "cannot read the roster")

        # ── The document door is open to everyone ────────────────────
        print("\nEverybody can send a document in; almost nobody files it")
        import io
        for who, client in (("the auditor", auditor), ("Tom", tom),
                            ("the organisation administrator", barb)):
            files = {"file": (f"drive-{who.replace(' ', '-')}.txt",
                              io.BytesIO(f"drive upload from {who}".encode()),
                              "text/plain")}
            check(client, "POST", "/api/documents/upload", 200,
                  f"{who} sends a document in",
                  files=files, data={"kind": "receipt",
                                     "suggested_for": "Access drive"})
        check(barb, "GET", "/api/documents/mine", 200,
              "and can see what became of it")
        check(barb, "GET", "/api/documents/inbox", 403,
              "but the organisation administrator does not work the inbox")
        check(heidi, "GET", "/api/documents/inbox", 200,
              "Heidi does — she holds OFFICE")

        # ── The library, and what a browser may do with a document ──
        print("\nThe shelf is open to whoever may read the record")
        # The library is the cost record in document form, so it takes the
        # same gate the review screens take — not a portfolio, and not rank.
        for who, client in (("the auditor", auditor), ("Tom", tom),
                            ("Heidi", heidi),
                            ("the organisation administrator", barb),
                            ("the system administrator, on his grant", eric)):
            check(client, "GET", "/api/documents/library", 200,
                  f"{who} opens the library")

        anon = httpx.Client(base_url=args.base, timeout=60)
        try:
            check(anon, "GET", "/api/documents/library", 401,
                  "nobody signed in gets nothing")
        finally:
            anon.close()

        # Somebody uploads, then reads their own back. The uploader is not a
        # reader of the record and must not become one by having sent a file
        # in — nor be locked out of the thing they sent.
        r = tom.get("/api/documents/library?q=Drive-AM")
        rows = r.json().get("documents", []) if r.status_code == 200 else []
        pdf = next((d for d in rows if d["inline_safe"]), None)
        if not pdf:
            bad("no previewable document on file — the library cannot be "
                "proved against real rows")
        else:
            eid = pdf["evidence_id"]
            head = auditor.get(f"/api/documents/{eid}/file?inline=1")
            disp = head.headers.get("content-disposition", "")
            (ok if disp.startswith("inline") else bad)(
                f"a PDF is offered to read in the page — {disp[:40]}")
            (ok if head.headers.get("x-content-type-options") == "nosniff"
             else bad)("and the browser is told not to sniff past the type")
            (ok if "sandbox" in head.headers.get("content-security-policy", "")
             else bad)("and to treat it as its own origin")

            plain = auditor.get(f"/api/documents/{eid}/file")
            (ok if plain.headers.get("content-disposition", "").startswith(
                "attachment") else bad)(
                "and asked for plainly, it comes back as a copy to keep")

        # A type not on the allowlist downloads however it is asked for.
        sheet = next((d for d in tom.get("/api/documents/library?limit=500")
                      .json()["documents"] if not d["inline_safe"]), None)
        if sheet:
            r = auditor.get(f"/api/documents/{sheet['evidence_id']}/file?inline=1")
            (ok if r.headers.get("content-disposition", "").startswith(
                "attachment") else bad)(
                f"a {sheet['mime_type'].rsplit('.', 1)[-1][:24]} is refused "
                f"the page even when the page asks for it")

        # ── Two documents, and who may make one ─────────────────────
        print("\nA report is a read; filing one is not")
        for who, client in (("the auditor", auditor), ("Tom", tom),
                            ("the organisation administrator", barb)):
            check(client, "GET", "/api/reports/timesheet", 200,
                  f"{who} takes the timesheet report")

        r = tom.get("/api/reports/invoices")
        rows = r.json().get("invoices", []) if r.status_code == 200 else []
        if not rows:
            bad("no invoices on the register — regeneration cannot be proved "
                "against real rows")
        else:
            number = rows[0]["invoice_number"]
            pdf = check(auditor, "GET", f"/api/reports/invoice/{number}", 200,
                        f"the auditor renders invoice {number}")
            (ok if pdf.content[:5] == b"%PDF-" else bad)(
                "and what comes back is a PDF")
            # The whole point of the provenance band: an invoice already
            # issued must not come back as something that could pass for the
            # document the sponsor holds.
            #
            # Read through pypdf rather than searched for in the raw bytes.
            # PDF text is compressed, so a byte search for a phrase that is
            # plainly on the page finds nothing and the drive reports a
            # failure against working code — which is what the first version
            # of this check did.
            from io import BytesIO
            from pypdf import PdfReader
            issued = (rows[0].get("status") or "").upper() == "ISSUED"
            face = "".join(pg.extract_text()
                           for pg in PdfReader(BytesIO(pdf.content)).pages)
            marked = "NOT THE DOCUMENT OF RECORD" in face
            if issued:
                (ok if marked else bad)(
                    "an issued invoice renders as a reproduction and says so")

            # Filing is a write into the evidence volume. Reading the record
            # is not enough; this is the controller's to do.
            check(auditor, "POST", f"/api/reports/invoice/{number}/file", 403,
                  "the auditor may read it and may not file it")
            filed = check(tom, "POST", f"/api/reports/invoice/{number}/file",
                          201, "Tom files the rendering")
            if filed.status_code == 201:
                eid = filed.json().get("evidence_id")
                again = tom.post(f"/api/reports/invoice/{number}/file")
                (ok if again.json().get("deduplicated") else bad)(
                    "filing the same rendering twice files one document")
                lib = tom.get(f"/api/documents/library?q={eid}")
                row = next((d for d in lib.json().get("documents", [])
                            if d["evidence_id"] == eid), None)
                (ok if row else bad)("and it reaches the library")
                if row:
                    (ok if row.get("is_generated") else bad)(
                        "marked as made from the record rather than sent in")

        # ── Reading the books is granted, not assumed ────────────────
        print("\nReading the books is granted by whoever owns them")
        eric_id = roster["eric.c.wagner@gmail.com"]["actor_id"]
        me = eric.get("/api/auth/me").json()
        (ok if me["record_access"] and me["can_read"] else bad)(
            "the system administrator reads the record on a grant, not on rank")
        (ok if not me["may_seal"] else bad)(
            "and still cannot seal anything")
        row = roster["eric.c.wagner@gmail.com"]
        (ok if row["record_access_granted_by_name"] else bad)(
            f"the grant names who made it — "
            f"{row['record_access_granted_by_name']}")

        check(barb, "POST", f"/api/auth/actors/{barb_id}/record-access", 403,
              "nobody lets themselves into the books",
              json={"granted": True,
                    "reason": "Access drive: this must be refused."})
        tom_id = roster["tom@ybi.org"]["actor_id"]
        check(barb, "POST", f"/api/auth/actors/{tom_id}/record-access", 422,
              "and there is nothing to grant somebody who reads by rank",
              json={"granted": True,
                    "reason": "Access drive: this must be refused."})

        # ── A derived address is correctable, not deletable ──────────
        print("\nAn address that was guessed can be put right")
        derived = [a for a in barb.get("/api/auth/actors").json()
                   if not a["email_confirmed"] and a["is_active"]]
        if derived:
            who = derived[0]
            ok(f"{len(derived)} seeded account(s) carry a derived address")
            r = barb.patch(f"/api/auth/actors/{who['actor_id']}", json={
                "email": f"drive.{who['employee_key'].lower()}@ybi.org",
                "reason": "Access drive: correcting a derived address."})
            (ok if r.status_code == 200 else bad)(
                f"the administrator corrects it — {r.status_code}")
            after = [a for a in barb.get("/api/auth/actors").json()
                     if a["actor_id"] == who["actor_id"]][0]
            (ok if after["email_confirmed"] else bad)(
                "and correcting it is what marks it checked")
            check(barb, "PATCH", f"/api/auth/actors/{who['actor_id']}", 409,
                  "an address already in use is refused",
                  json={"email": "tom@ybi.org",
                        "reason": "Access drive: must be refused."})
        else:
            ok("no derived addresses outstanding")
        check(barb, "PATCH", f"/api/auth/actors/{eric_id}", 403,
              "and rank still runs downward for amendments",
              json={"display_name": "Nope",
                    "reason": "Access drive: must be refused."})

        # ── An issued password cannot sign anything ──────────────────
        print("\nAn issued password cannot sign anything")
        # A fresh identity every run. This is the section that proves the
        # gate covering the personal writes, and a run that skips it because
        # yesterday's newcomer is still there proves nothing.
        import time
        stamp = int(time.time())
        email = f"drive-newcomer-{stamp}@ybi.org"
        r = barb.post("/api/auth/actors", json={
            "email": email, "display_name": "Drive Newcomer",
            "role": "EMPLOYEE", "employee_key": f"DRIVE{stamp}",
            "password": "issued-by-somebody-else-1"})
        if r.status_code == 201:
            ok("a newcomer is provisioned — 201")
            new = sign_in(args.base, email, "issued-by-somebody-else-1")
            me = new.get("/api/auth/me").json()
            (ok if me["must_set_password"] else bad)(
                "their first screen is choosing their own password")
            check(new, "POST", "/api/timesheet/entry", 403,
                  "and they cannot record time until they do",
                  json={"work_date": "2025-06-02", "objective_id": "YBI-GA",
                        "hours": 8, "basis": "PROJECT_RECORD",
                        "note": "Access drive."})
            # The one that matters most: 2 CFR 200.430(i) wants a statement
            # by a named person, and a password two people know does not
            # name one.
            check(new, "POST", "/api/certify/sign", 403,
                  "nor sign a certification",
                  json={"employee_key": f"DRIVE{stamp}", "acknowledged": True})
            import io
            check(new, "POST", "/api/documents/upload", 403,
                  "nor send a document in under their name",
                  files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
                  data={"kind": "receipt"})
            check(new, "GET", "/api/documents/mine", 200,
                  "though they can still look around")
            r2 = new.post("/api/auth/password", json={
                "current_password": "issued-by-somebody-else-1",
                "new_password": "a-password-only-they-know-1"})
            (ok if r2.status_code == 200 else bad)(
                f"they choose their own — {r2.status_code}")
            check(new, "POST", "/api/timesheet/entry", 200,
                  "and now their time is theirs to record",
                  json={"work_date": "2025-06-02", "objective_id": "YBI-GA",
                        "hours": 8, "basis": "PROJECT_RECORD",
                        "note": "Access drive: first entry after setting a "
                                "password only they know."})
            new.close()
        else:
            bad(f"could not provision a newcomer — {r.status_code}")
    finally:
        # The buildings this drive invents are litter, and the Space screen is
        # one the user manual photographs.
        from app.db import execute
        # Same reason as the buildings: an account holding a password only
        # this drive knows is one nobody can sign into, and it is the account
        # another drive will pick as its plain employee.
        execute("""UPDATE actor SET is_active = false
                    WHERE email LIKE 'drive-newcomer-%@ybi.org'
                       OR email LIKE 'peer%@ybi.org'""")
        # The documents this drive sends in are litter too, and since the
        # library shows every document to every reader they are litter on a
        # screen the manual photographs. They were invisible until there was
        # a screen that listed the whole shelf.
        execute("""DELETE FROM attachment
                    WHERE evidence_id IN (SELECT evidence_id FROM evidence
                                           WHERE filename LIKE 'drive-%')""")
        # Never one a judgment cited. The decision may have been walked back and
        # it is still on the record as what it was decided on; deleting the
        # document behind it would leave the trail saying somebody graded a
        # judgment against nothing, which is the one thing the grade exists to
        # make impossible. `drive_evidence` leaves exactly one such document.
        execute("""DELETE FROM evidence e
                    WHERE e.filename LIKE 'drive-%'
                      AND NOT EXISTS (SELECT 1 FROM decision_evidence de
                                       WHERE de.evidence_id = e.evidence_id)""")
        execute("""DELETE FROM space_unit
                    WHERE facility_id LIKE 'DRIVE%'""")
        execute("DELETE FROM facility WHERE facility_id LIKE 'DRIVE%'")
        for c in (eric, barb, tom, heidi, auditor):
            c.close()

    print(f"\n{'PASS' if not FAIL else 'FAIL'} — {len(PASS)} checks"
          + (f", {len(FAIL)} failed" if FAIL else ", every boundary held"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
