"""A citation names a document, and the document is asked whether it is true.

`award_term` carried, on two federal subawards, `§25 Invoicing` and `§26
Payment` — clauses that are not in either agreement. They are ICAM's, and
ICAM is a different instrument: fifty-two numbered ALL-CAPS clauses against
two ARTICLE-numbered ones. Nothing in the system was in a position to notice,
because `award_term.evidence_id` was NULL on all thirty-nine rows and
`evidence.extracted_text` was NULL on all forty-three documents.

These make their own award, their own document and their own terms, so they
run on the bare database CI builds from the migrations. The foundation is not
needed and must not be: a test that reads whatever happens to be in the
database passes for a developer and fails in CI, which is what
`test_reconcile_db.py` did.

Every test writes inside a transaction that is rolled back.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

#: A document shaped like the NCDMM Subrecipient Agreement: numbered
#: ALL-CAPS clause headings, and an Attachment.
NUMBERED = """
Subrecipient Agreement
6. CONTRACT TYPE.
NCDMM is entering into a Cost Reimbursement No Fee Agreement with the
Subrecipient.
25. INVOICING.
Invoices shall be submitted monthly.
26. PAYMENT.
Payment terms are stated herein.
Attachment 3
Basis of Estimate
""" + "filler. " * 60

#: And one shaped like Hybrid and LTM: ARTICLE-numbered, no numbered clause
#: headings anywhere, no §25, no §26, no Attachment 3.
ARTICLED = """
ARTICLE 4. BUDGET AND PAYMENT
4.2 Reimbursement only for costs allowable under 2 CFR 200 Subpart E.
4.3 Total Obligation. The total obligation is stated in Schedule B.
SCHEDULE B
BUDGET
""" + "filler. " * 60


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                yield cursor


def make_award(cur, award_id: str, text: str | None, pages: int | None = 27):
    """An award, an objective for it, and an agreement carrying `text`."""
    cur.execute("""INSERT INTO fiscal_period (period, start_date, end_date)
                   VALUES ('2097','2097-01-01','2097-12-31')
                   ON CONFLICT DO NOTHING""")
    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal)
                   VALUES (%s,'2097',%s,'CONTRACT',true)
                   ON CONFLICT DO NOTHING""",
                (award_id, f"objective for {award_id}"))
    eid = f"EV-{award_id[:12]}"
    cur.execute("""INSERT INTO evidence (evidence_id, period, kind, uri,
                                         sha256, filename, mime_type,
                                         extracted_text, page_count)
                   VALUES (%s,'2097','subrecipient-agreement',%s,%s,%s,
                           'application/pdf',%s,%s)""",
                (eid, f"/tmp/{award_id}.pdf", award_id.lower() * 4,
                 f"{award_id}.pdf", text, pages))
    cur.execute("""INSERT INTO award (award_id, objective_id, sponsor,
                                      instrument, ceiling_federal,
                                      period_start, period_end, rate_method,
                                      agreement_evidence_id)
                   VALUES (%s,%s,'NCDMM','SUBAWARD',100000,
                           '2097-01-01','2097-12-31','DE_MINIMIS_10',%s)""",
                (award_id, award_id, eid))
    return eid


def term(cur, award_id, key, citation):
    cur.execute("""INSERT INTO award_term (award_id, term_key, term_value,
                                           citation, recorded_by, evidence_id)
                   SELECT %s, %s, 'a value', %s, 'test',
                          a.agreement_evidence_id
                     FROM award a WHERE a.award_id = %s""",
                (award_id, key, citation, award_id))


def state(cur, award_id, key) -> str:
    cur.execute("""SELECT state FROM v_award_citation_check
                    WHERE award_id = %s AND term_key = %s""", (award_id, key))
    return cur.fetchone()["state"]


# ── The direction it is meant to pass ─────────────────────────────────

def test_a_clause_that_is_in_the_document_is_found(cur):
    make_award(cur, "T-NUMBERED", NUMBERED)
    term(cur, "T-NUMBERED", "Invoicing frequency", "§25 Invoicing")
    term(cur, "T-NUMBERED", "Payment terms", "§26 Payment")
    term(cur, "T-NUMBERED", "Indirect provision", "Attachment 3, Basis")
    for key in ("Invoicing frequency", "Payment terms", "Indirect provision"):
        assert state(cur, "T-NUMBERED", key) == "FOUND", (
            f"{key} cites something that is plainly in the document and the "
            f"check could not find it — a check that accuses correct work is "
            f"worse than no check")


# ── And the direction that matters ────────────────────────────────────

def test_a_clause_that_is_not_in_the_document_is_named(cur):
    """The six that were actually on the record: ICAM's clauses recorded
    against two agreements that do not contain them."""
    make_award(cur, "T-ARTICLED", ARTICLED)
    term(cur, "T-ARTICLED", "Invoicing frequency", "§25 Invoicing")
    term(cur, "T-ARTICLED", "Payment terms", "§26 Payment")
    term(cur, "T-ARTICLED", "Indirect provision", "Attachment 3, Basis")
    for key in ("Invoicing frequency", "Payment terms", "Indirect provision"):
        assert state(cur, "T-ARTICLED", key) == "NOT IN DOCUMENT", (
            f"{key} cites a clause this document does not contain and the "
            f"check passed it")


def test_a_clause_the_same_document_does_contain_is_still_found(cur):
    """So the previous test is about the clause, not about the document.

    Without this, a check that answered NOT IN DOCUMENT for everything in an
    ARTICLE-numbered agreement would pass the test above while proving
    nothing.
    """
    make_award(cur, "T-BOTH", ARTICLED)
    term(cur, "T-BOTH", "Allowability", "§4.2, closing sentence")
    term(cur, "T-BOTH", "Total obligation", "§4.3 Total Obligation")
    term(cur, "T-BOTH", "Budget as proposed", "Schedule B, Budget")
    term(cur, "T-BOTH", "Payment terms", "§26 Payment")
    assert state(cur, "T-BOTH", "Allowability") == "FOUND"
    assert state(cur, "T-BOTH", "Total obligation") == "FOUND"
    assert state(cur, "T-BOTH", "Budget as proposed") == "FOUND"
    assert state(cur, "T-BOTH", "Payment terms") == "NOT IN DOCUMENT"


# ── The four answers that are not passes ──────────────────────────────

def test_an_agreement_that_is_an_image_is_unevaluable_not_clean(cur):
    """Drive AM: thirty-six pages, seventy characters, nothing extractable.

    Both sides of the comparison are empty and an empty set matches an empty
    set perfectly — the same trap `v_invoice_budget_check` reports
    `evaluable = false` for, and the same one `029` was written for.
    """
    make_award(cur, "T-IMAGE", "\n" * 40, pages=36)
    term(cur, "T-IMAGE", "Payment terms", "§26 Payment")
    assert state(cur, "T-IMAGE", "Payment terms") == "NO TEXT LAYER"
    cur.execute("""SELECT agreement_is_an_image, unevaluable, found
                     FROM v_award_citations WHERE award_id = 'T-IMAGE'""")
    row = cur.fetchone()
    assert row["agreement_is_an_image"]
    assert row["unevaluable"] == 1 and row["found"] == 0


def test_a_document_nobody_has_read_is_not_a_document_that_agrees(cur):
    make_award(cur, "T-UNREAD", None, pages=None)
    term(cur, "T-UNREAD", "Payment terms", "§26 Payment")
    assert state(cur, "T-UNREAD", "Payment terms") == "NOT READ"


def test_a_term_with_no_document_says_so(cur):
    make_award(cur, "T-NODOC", NUMBERED)
    cur.execute("""INSERT INTO award_term (award_id, term_key, term_value,
                                           citation, recorded_by)
                   VALUES ('T-NODOC','Payment terms','a value',
                           '§26 Payment','test')""")
    assert state(cur, "T-NODOC", "Payment terms") == "NO DOCUMENT"


def test_a_prose_citation_is_untestable_rather_than_wrong(cur):
    """"Proposal cover table, Duration" is a perfectly good citation for a
    person and a poor one for a regex. Reporting it as a failure would teach
    the reader that the list is wrong, and the next real one they see they
    will dismiss."""
    make_award(cur, "T-PROSE", NUMBERED)
    term(cur, "T-PROSE", "Period of performance", "Proposal cover table")
    term(cur, "T-PROSE", "Prime agreement", "Recitals")
    assert state(cur, "T-PROSE", "Period of performance") == "UNTESTABLE"
    assert state(cur, "T-PROSE", "Prime agreement") == "UNTESTABLE"
