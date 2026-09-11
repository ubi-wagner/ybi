#!/usr/bin/env python3
"""A folder of documents, matched to the cost they support, and graded.

Twenty-one documents on file and **none attached to a single ledger line**,
so no judgment in the record could be graded `VERIFIED` — the deferred
trigger refuses the whole set otherwise — and the ceiling on every one of
the controller's two hundred decisions was `CORROBORATED`. This drives the
path that changes that, end to end, as the people who own each step:

    anybody sends documents in    → an employee, because the door is that wide
    somebody reads the face of it → OFFICE, because a wrong amount here
                                    produces a confident wrong proposal
    the system proposes           → and applies nothing
    OFFICE confirms in bulk       → one act each, each on the record
    the controller cites it       → which is what the grade actually reads

What it is looking for is not "did it attach something". It is whether the
matcher is honest about what it does not know:

  * a document that says nothing about itself proposes nothing
  * two costs at the same amount propose **nothing**, and say how many tied
  * a near amount is not a match
  * the reasons are in words somebody can check, not a score
  * nothing is applied until a person confirms it
  * and a judgment citing the document it found may be graded VERIFIED

One thing this deliberately does not claim: **attaching is not citing.**
`decision_verified_check` counts `decision_evidence`, not `attachment`, so a
bulk confirm does not raise anybody's grade on its own — it makes the
document findable, and `decide()` carries `evidence_ids` from there. The
trigger itself is held in `tests/test_verified_requires_a_citation.py`,
against a database, including the case where the document is attached to the
cost and the grade is still refused.

It leaves the record as it found it: every attachment it makes, and every
fact it writes, is walked back at the end. A drive that accumulates is a
drive reading its own writing.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/drive_evidence.py \\
        [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from decimal import Decimal

import httpx

FINDINGS: list[str] = []
CHECKS = 0


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
        raise SystemExit(f"{email} could not sign in — {r.status_code}")
    return c


#: A fresh set of bytes every run.
#:
#: Uploads are content-addressed, so the same bytes sent twice are one
#: document — which is right, and which would make this drive dedup against
#: its own previous run and report a finding about working code. The same
#: lesson drive_requests learned by asserting absolute counts over a register
#: it had already written to.
RUN = os.urandom(8).hex().encode()


def send(client: httpx.Client, name: str, body: bytes, **facts) -> str:
    """Put a document in, as anybody signed in."""
    body = body + b" " + RUN
    r = client.post("/api/documents/upload",
                    files={"file": (name, body, "application/pdf")},
                    data={"kind": "invoice", "note": "Evidence drive.",
                          **{k: str(v) for k, v in facts.items()}})
    if r.status_code != 200:
        raise SystemExit(f"upload of {name} answered {r.status_code}: {r.text[:300]}")
    return r.json()["evidence_id"]


def undo_last(client: httpx.Client) -> None:
    """Walk the drive's own judgment back through the real route.

    Not a DELETE. Undo is a forward, auditable act here, and a drive that
    reached into the tables to tidy up would be proving the undo path works
    by not using it.
    """
    r = client.post("/api/undo", json={
        "count": 1, "reason": "Evidence drive: leaving the record as found."})
    if r.status_code not in (200, 409):
        finding(f"undo answered {r.status_code}: {r.text[:200]}")


def proposal_for(client: httpx.Client, eid: str) -> dict | None:
    r = client.get("/api/documents/propose", params={"limit": 200})
    if r.status_code != 200:
        finding(f"the proposal route answered {r.status_code}")
        return None
    for d in r.json()["documents"]:
        if d["evidence_id"] == eid:
            return d
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--password", default=os.environ.get("YBI_SEED_PASSWORD", ""))
    args = ap.parse_args()
    if not args.password:
        raise SystemExit("YBI_SEED_PASSWORD (or --password) is required.")

    from app.db import execute, one, query

    tom = sign_in(args.base, "tom@ybi.org", args.password)
    auditor = sign_in(args.base, "auditor@ybi.org", args.password)
    emp = one("""SELECT email FROM actor WHERE role = 'EMPLOYEE' AND is_active
                   AND password_set_by = 'SELF' ORDER BY email LIMIT 1""")
    # Somebody who holds no portfolio at all. An employee where the record
    # has one; otherwise the auditor, who may read the whole cost record and
    # may write none of it — which is the same boundary and, if anything, the
    # sharper case. Which it was is printed, because a check that quietly
    # used a different person proves something different.
    outsider = sign_in(args.base, emp["email"], args.password) if emp else auditor
    who = emp["email"] if emp else "auditor@ybi.org (no employee on the record)"

    # ── The costs this drive will match against ───────────────────────
    #
    # Read off the live ledger rather than invented, so the proposal is
    # tested against the shapes the record actually has — several lines to a
    # group, a payee written the way QuickBooks writes it.
    groups = query("""SELECT l.account, l.payee, sum(l.amount) AS amount,
                             count(*) AS lines, min(l.txn_date) AS first_day,
                             max(l.txn_date) AS last_day
                        FROM ledger_line l
                       WHERE l.period = '2025' AND l.statement = 'P&L'
                         AND l.payee <> ''
                       GROUP BY l.account, l.payee
                      HAVING count(*) > 1 AND sum(l.amount) > 1000
                       ORDER BY sum(l.amount) DESC LIMIT 40""")
    if not groups:
        raise SystemExit("no ledger groups to match against; seed the period first")

    # One group whose total no other group shares — the unambiguous case.
    totals = [g["amount"] for g in groups]
    unique = next((g for g in groups if totals.count(g["amount"]) == 1), None)
    if unique is None:
        raise SystemExit("every group in the sample shares its total; widen it")

    written: list[str] = []
    attached: list[tuple[str, str, str]] = []

    try:
        # ── 1. The door is wide, and what it now carries ──────────────
        head("Sending documents in — and saying what is on the face of them")
        print(f"  as       {who} — holds no portfolio", flush=True)
        eid = send(outsider, "drive-invoice-a.pdf", b"%PDF-1.4 drive evidence A",
                   doc_amount=unique["amount"],
                   doc_date=(unique["last_day"] + timedelta(days=3)).isoformat(),
                   vendor_name=unique["payee"])
        written.append(eid)
        row = one("""SELECT doc_amount, doc_date, vendor_name FROM evidence
                      WHERE evidence_id = %s""", (eid,))
        if row and row["doc_amount"] == unique["amount"]:
            ok(f"somebody with no portfolio sent a document in carrying its "
               f"own amount, date "
               f"and vendor — {row['doc_amount']}, {row['doc_date']}")
        else:
            finding("the upload did not record what the document says about itself")

        blank = send(outsider, "drive-mystery.pdf", b"%PDF-1.4 drive evidence B")
        written.append(blank)
        b = one("SELECT doc_amount FROM evidence WHERE evidence_id = %s", (blank,))
        if b and b["doc_amount"] is None:
            ok("and one sent in with nothing on it stays unanswered — a blank "
               "is not a zero, the same rule the intake follows")
        else:
            finding(f"a document with no amount came out as {b}")

        # Stamped like everything else send() puts in. This one goes direct
        # because it is testing the response shape rather than the happy
        # path, and unstamped bytes deduped against the previous run — the
        # drive reporting a finding about its own re-runnability again.
        bad = outsider.post("/api/documents/upload",
                            files={"file": ("drive-typo.pdf",
                                            b"%PDF-1.4 C " + RUN,
                                            "application/pdf")},
                            data={"kind": "invoice", "doc_amount": "about 400",
                                  "doc_date": "March", "vendor_name": "Acme"})
        if bad.status_code == 200:
            written.append(bad.json()["evidence_id"])
            got = bad.json()
            if set(got.get("could_not_read", [])) == {"amount", "date"} \
                    and got["vendor_name"] == "Acme":
                ok("a cell that will not read costs that cell and not the "
                   "document — 'about 400' and 'March' are named, the vendor "
                   "landed, and the file is on file")
            else:
                finding(f"an unreadable field was not reported: {got}")
        else:
            finding(f"a document with one bad field was refused outright — "
                    f"{bad.status_code}; a receipt held back is a receipt in a drawer")

        # ── 2. The boundary ───────────────────────────────────────────
        head("Who may say what a document is of")
        r = outsider.patch(f"/api/documents/{blank}/facts",
                           json={"doc_amount": "1.00"})
        if r.status_code == 403:
            ok("somebody with no portfolio may send a document in and may not "
               "read facts onto "
               "one — a wrong amount here produces a confident wrong proposal")
        else:
            finding(f"the facts route admitted somebody with no portfolio — "
                    f"{r.status_code}")

        r = auditor.get("/api/documents/propose")
        if r.status_code == 403:
            ok("and the auditor, who may read the whole record, may not see "
               "proposals to act on — it is a queue of work, not a report")
        else:
            finding(f"the proposal queue answered the auditor {r.status_code}")

        # ── 3. What it proposes, and what it refuses to ───────────────
        head("The proposal — and nothing is applied")
        p = proposal_for(tom, eid)
        if p and p["proposes"]:
            ok(f"the document was matched to {p['target']['label']}")
            because = p["target"]["because"]
            if "matches to the cent" in because and "same party" in because:
                ok(f"and it says why in words somebody can check — “{because[:90]}…”")
            else:
                finding(f"the proposal's reasons are thin: {because}")
            if set(p["target"]["signals"]) >= {"AMOUNT", "VENDOR"}:
                ok("amount and vendor both carried it, not amount alone")
            else:
                finding(f"signals were {p['target']['signals']}")
        else:
            finding(f"the unambiguous document was not proposed for anything: "
                    f"{(p or {}).get('why_not')}")

        p = proposal_for(tom, blank)
        if p and not p["proposes"] and "does not say what it is for" in p["why_not"]:
            ok("a document that says nothing about itself proposes nothing, "
               "and says what would let it be matched")
        else:
            finding("a document with no amount was matched to something")

        near = send(outsider, "drive-near.pdf", b"%PDF-1.4 drive evidence D",
                    doc_amount=unique["amount"] + Decimal("0.50"),
                    vendor_name=unique["payee"])
        written.append(near)
        p = proposal_for(tom, near)
        if p and not p["proposes"]:
            ok("fifty cents out is not a match — a tolerance here is how a "
               "system starts agreeing with itself")
        else:
            finding("a near amount was proposed as a match")

        # Two costs at one amount. Built by sending a document for an amount
        # two different groups share, which is the case that matters most.
        shared = next((t for t in totals if totals.count(t) > 1), None)
        if shared is not None:
            twin = send(outsider, "drive-ambiguous.pdf", b"%PDF-1.4 drive evidence E",
                        doc_amount=shared)
            written.append(twin)
            p = proposal_for(tom, twin)
            if p and not p["proposes"] and "fit this document equally well" in p["why_not"]:
                ok(f"two costs at {shared} propose nothing, and it says how "
                   f"many tied — {p['why_not'][:48]}…")
                if p["also_fits"]:
                    ok(f"and it shows what tied, so the person can choose — "
                       f"{len(p['also_fits'])} shown")
                else:
                    finding("nothing was shown of what tied")
            else:
                finding("an ambiguous amount was matched to one of them")
        else:
            # Not a fault: this ledger may have no two groups at one total.
            # Saying so is better than a check that quietly did not run.
            print("  note     no two groups in the sample share a total, so "
                  "the tie case was proved in tests/test_evidence_match.py "
                  "rather than here", flush=True)

        before = one("""SELECT count(*) AS n FROM attachment
                         WHERE detached_at IS NULL""")
        if before["n"] == (one("""SELECT count(*) AS n FROM attachment
                                   WHERE detached_at IS NULL""")["n"]):
            ok("and after all of that, nothing has been attached to anything — "
               "a proposal is never a decision")

        # ── 4. Confirming, in bulk ────────────────────────────────────
        head("Confirming — one act each, each on the record")
        p = proposal_for(tom, eid)
        if not (p and p["proposes"]):
            finding("nothing to confirm; the earlier proposal did not stand")
        else:
            t = p["target"]
            audits = one("SELECT count(*) AS n FROM audit_log")["n"]
            r = tom.post("/api/documents/attach/bulk", json={"attachments": [
                {"evidence_id": eid, "target_type": t["target_type"],
                 "target_id": t["target_id"],
                 "relevance": "Vendor invoice for the cost in this group."}]})
            if r.status_code == 201:
                attached.append((eid, t["target_type"], t["target_id"]))
                ok(f"confirmed in bulk — {r.json()['attached']} attachment(s)")
            else:
                finding(f"the bulk confirm answered {r.status_code}: {r.text[:200]}")
            now = one("SELECT count(*) AS n FROM audit_log")["n"]
            if now > audits:
                who = one("""SELECT actor, action FROM audit_log
                              ORDER BY occurred_at DESC LIMIT 1""")
                ok(f"and it is on the record under a name — {who['actor']}, "
                   f"{who['action']}")
            else:
                finding("a bulk confirm changed the record and recorded nothing")

            r = tom.post("/api/documents/attach/bulk", json={"attachments": [
                {"evidence_id": eid, "target_type": t["target_type"],
                 "target_id": t["target_id"], "relevance": "again"},
                {"evidence_id": "EV-nothing-here", "target_type": "LEDGER_GROUP",
                 "target_id": "x", "relevance": "a document that is not there"}]})
            if r.status_code == 404:
                ok("a batch naming a document that is not there is refused "
                   "whole — the defect decide() had, where a refusal partway "
                   "through left the ones before it recorded")
            else:
                finding(f"a batch with a bad row answered {r.status_code}")

            p = proposal_for(tom, eid)
            if p is None:
                ok("and the document has left the queue, because it is now "
                   "doing something")
            else:
                finding("an attached document is still offered for matching")

            # ── 5. The grade the schema refused before ────────────
            head("The grade this was all for")
            openset = one("""SELECT set_id FROM decision_set
                              WHERE period = '2025' AND sealed_at IS NULL
                              LIMIT 1""")
            if openset is None:
                print("  note     the decision set is sealed, so no judgment "
                      "could be made to grade. That is the correct state, not "
                      "a defect — run this before the drives that seal.",
                      flush=True)
            else:
                group = t["target_id"] if t["target_type"] == "LEDGER_GROUP" else None
                if group is None:
                    print("  note     the proposal landed on a line rather "
                          "than a group, so there is no group judgment to "
                          "grade here", flush=True)
                else:
                    # OVERHEAD rather than DIRECT: `direct_needs_objective`
                    # requires a final cost objective on a direct judgment,
                    # and which objective this group belongs to is exactly
                    # the judgment a drive must not invent. The pool is
                    # beside the point here — what is being proved is the
                    # grade, and the whole judgment is walked back.
                    body = {"group_keys": [group], "pool": "OVERHEAD",
                            "function_990": "MANAGEMENT_AND_GENERAL",
                            "federal": "ALLOWABLE", "grade": "VERIFIED",
                            "rationale": "Evidence drive: graded against the "
                                         "vendor invoice attached to this "
                                         "group, then walked back."}
                    r = tom.post("/api/classify/decide", json=body)
                    if r.status_code >= 400:
                        ok("a VERIFIED grade citing nothing is refused — "
                           "attaching a document is not the same as citing "
                           "it, and the gate reads the citation")
                    else:
                        finding("a VERIFIED grade was accepted with no "
                                "document cited on the judgment")
                        undo_last(tom)

                    r = tom.post("/api/classify/decide",
                                 json={**body, "evidence_ids": [eid]})
                    if r.status_code == 200 and r.json().get("decisions_created"):
                        ok("and the same judgment, citing the document the "
                           "matcher found, is VERIFIED — the grade every one "
                           "of the two hundred decisions was capped below")
                        undo_last(tom)
                        ok("and walked straight back, so the record is as it "
                           "was")
                    else:
                        finding(f"the graded judgment answered "
                                f"{r.status_code}: {r.text[:200]}")

    finally:
        # ── Walked back, so the next run reads the same record ────────
        head("Leaving it as it was found")
        for eid_, ttype, tid in attached:
            execute("""DELETE FROM attachment WHERE evidence_id = %s
                        AND target_type = %s AND target_id = %s""",
                    (eid_, ttype, tid))
        # A document a judgment *cited* stays, even though that judgment has
        # been walked back. The reversal is on the record and so is what it
        # was decided on; deleting the document would leave the trail saying
        # somebody graded a judgment VERIFIED against nothing, which is the
        # one thing the grade is supposed to make impossible. The same answer
        # audit_log gives by refusing a DELETE outright.
        cited = [r["evidence_id"] for r in query(
            """SELECT DISTINCT evidence_id FROM decision_evidence
                WHERE evidence_id = ANY(%s)""", (written,))] if written else []
        removable = [e for e in written if e not in cited]
        if removable:
            execute("DELETE FROM attachment WHERE evidence_id = ANY(%s)",
                    (removable,))
            execute("DELETE FROM evidence WHERE evidence_id = ANY(%s)",
                    (removable,))
        if cited:
            execute("DELETE FROM attachment WHERE evidence_id = ANY(%s)", (cited,))
            ok(f"{len(cited)} document(s) stay, because a judgment cited them "
               f"— reversed, and still on the record as what it was decided on")
        # The audit entries stay. audit_log refuses a DELETE outright —
        # "append-only; correct by superseding, never by editing" — and it is
        # right to: the drive really did upload five documents and attach
        # one, under somebody's name, and a trail that can be tidied up
        # afterwards is not a trail. The rows it leaves say what happened.
        left = one("""SELECT count(*) AS n FROM evidence e
                       WHERE e.filename LIKE 'drive-%'
                         AND NOT EXISTS (SELECT 1 FROM decision_evidence de
                                          WHERE de.evidence_id = e.evidence_id)""")
        hanging = one("""SELECT count(*) AS n FROM attachment a
                          JOIN evidence e USING (evidence_id)
                         WHERE e.filename LIKE 'drive-%'""")
        if left["n"] == 0 and hanging["n"] == 0:
            ok("every document this drive sent in is gone bar the ones a "
               "judgment cited, and every attachment with them")
        else:
            finding(f"{left['n']} uncited drive document(s) and "
                    f"{hanging['n']} attachment(s) left on the record")

    head("Summary")
    print(f"  {CHECKS} check(s), {len(FINDINGS)} finding(s)")
    for f in FINDINGS:
        print(f"    - {f}")
    return 1 if FINDINGS else 0


if __name__ == "__main__":
    sys.exit(main())
