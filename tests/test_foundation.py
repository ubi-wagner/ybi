"""The deployment brings itself back, and never over the top of anybody.

A Postgres service was rebuilt and every table came back and nobody could
sign in, because the six accounts were made by a script somebody runs rather
than by anything the deployment does. `app/foundation.py` is what the boot
does about that; these are the properties it has to have, and the first one
matters more than the rest.

Every source assertion here was watched failing against a deliberately
broken copy — a test that cannot fail for the thing it names is the defect
this repository keeps finding, and one written about a bootstrap that only
runs on a recovery would otherwise never be exercised at all.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FOUNDATION = ROOT / "app" / "foundation.py"
SRC = FOUNDATION.read_text()


# ── The roster is defined once ───────────────────────────────────────

def test_the_roster_is_the_six_people_the_engagement_has():
    from app.foundation import ORG_ADMIN, ROSTER, STAFF, SYSTEM_ADMIN

    assert len(ROSTER) == 6
    assert ROSTER[0] is SYSTEM_ADMIN and ROSTER[1] is ORG_ADMIN, (
        "the ladder runs downward and the roster is read in that order — the "
        "organisation's administrator has to exist before a portfolio she "
        "grants can be written")
    assert ROSTER[2:] == STAFF
    assert len({p.email for p in ROSTER}) == 6


def test_provision_reads_the_roster_rather_than_keeping_one():
    """Two lists of the same six people is the defect the module is named
    after. `provision.py` held the original; it imports it now."""
    src = (ROOT / "scripts" / "provision.py").read_text()
    assert "from app.foundation import" in src
    assert not re.search(r"^STAFF = \[\s*$", src, re.M), (
        "provision.py has grown its own roster literal again")


def test_seed_documents_reads_the_document_list_rather_than_keeping_one():
    src = (ROOT / "scripts" / "seed_documents.py").read_text()
    assert "from app.foundation import DOCUMENTS" in src
    assert "DOCUMENTS: dict" not in src, (
        "seed_documents.py has grown its own copy of the document list again")


def test_every_portfolio_grant_carries_a_reason_the_schema_will_accept():
    """`actor_portfolio.reason` is NOT NULL with a ten-character floor. A
    person whose `why` is empty would be written with the restoration
    preamble alone, which is exactly the case the fallback covers."""
    from app.foundation import RESTORED_REASON, ROSTER

    for person in ROSTER:
        if not person.portfolios:
            continue
        reason = RESTORED_REASON + (person.why or "none recorded")
        assert len(reason.strip()) >= 10
        assert person.why, f"{person.email} holds a portfolio and says no why"


def test_the_nda_grant_is_long_enough_for_the_check_constraint():
    """`record_access_names_its_reason` refuses a grant whose reason is under
    twenty characters — a grant with no explanation is the next person's
    puzzle."""
    from app.foundation import NDA_REASON

    assert len(NDA_REASON.strip()) >= 20


# ── What it must never do ────────────────────────────────────────────

def test_it_never_writes_a_password_into_a_row():
    """The organisation's value is a setting and never anybody's stored hash.

    A bootstrap that wrote the shared password into six rows would put one
    secret at rest in six places, make withdrawing it six resets, and leave a
    copy of the database a copy of the credential.
    """
    assert "unusable_password_hash()" in SRC
    assert "hash_password(" not in SRC, (
        "app/foundation.py hashes something. The only hash it may write is "
        "the random one nobody holds.")


def test_it_never_updates_an_account_that_already_exists():
    """An account that exists is left exactly as it is.

    A deploy happens far more often than a recovery, so a boot that reset a
    password or a role would take an account away from the person using it
    on an ordinary Tuesday.
    """
    statements = re.findall(r"UPDATE\s+actor\b[\s\S]*?\"\"\"", SRC)
    for stmt in statements:
        assert "NOT record_access" in stmt, (
            f"app/foundation.py updates an existing account: {stmt[:160]}. "
            f"The only permitted update is granting the engagement lead the "
            f"record access that was never there.")
    assert "ON CONFLICT (email) DO NOTHING" in SRC


def test_it_does_nothing_without_the_organisation_password(monkeypatch):
    """Opening accounts nobody can sign into is not a recovery, it is a row.

    The gate is also what keeps this out of the way of `provision.py` on a
    development machine, which has no organisational password set.
    """
    import app.foundation as f

    monkeypatch.setattr(f, "shared_initial_password", lambda: "")
    called: list[str] = []
    for name in ("ensure_accounts", "ensure_documents", "ensure_guides"):
        monkeypatch.setattr(f, name, lambda n=name: called.append(n) or [])
    assert f.restore() == {}
    assert not called, f"the bootstrap acted with no password set: {called}"


def test_it_restores_nothing_that_is_a_judgment():
    """The ledger, the classifications, the seal and the rate are people's
    work. A boot that classified would be the machine putting its name on
    the seal, which is the guarantee the whole system rests on."""
    forbidden = ("decision", "decision_set", "rate", "ledger_line",
                 "allocation", "labor_certification", "restatement")
    tables = set(re.findall(r"(?:INSERT INTO|UPDATE)\s+(\w+)", SRC))
    assert not tables & set(forbidden), (
        f"app/foundation.py writes {sorted(tables & set(forbidden))}. "
        f"Everything in that list is a judgment with a person's name on it.")


def test_the_audit_row_names_the_boot_and_not_a_person():
    """Naming an administrator would put her signature on an act she was not
    present for, which is the one thing the audit trail is for."""
    assert "'deployment bootstrap'" in SRC
    insert = re.search(r"INSERT INTO audit_log[\s\S]*?\"\"\"", SRC).group(0)
    assert "actor_id" not in insert, (
        "the bootstrap's audit row claims an actor. It has none.")


# ── The documents and the guides ─────────────────────────────────────

def test_every_foundational_document_is_in_the_repository():
    """The image ships them now. A list naming a file that is not there is a
    register that reports a gap it caused itself."""
    from app.foundation import DOCUMENTS, SOURCE_DOCUMENTS

    missing = [n for n in DOCUMENTS if not list(SOURCE_DOCUMENTS.rglob(n))]
    assert not missing, f"named but not in docs/source-documents: {missing}"


def test_every_guide_is_in_the_repository():
    from app.foundation import GUIDE_DIR, GUIDES

    missing = [g.path for g in GUIDES if not (GUIDE_DIR / g.path).exists()]
    assert not missing, f"named but not in docs/: {missing}"


def test_the_guides_are_filed_as_generated():
    """`GENERATED` is the channel `038` added because every other value means
    the document came from outside. A manual rendered from this repository is
    exactly what it is for — and it is what keeps them out of the inbox."""
    ensure = re.search(r"def ensure_guides[\s\S]*?\n\n\ndef ", SRC).group(0)
    assert '"GENERATED"' in ensure
    assert '"UPLOAD"' not in ensure


def test_the_inbox_excludes_what_this_system_made():
    """The inbox is what nobody has filed yet. Nobody is ever going to attach
    the controller's manual to a ledger line, so eight guides at the top of
    that queue is the defect the evidence screen already learned once."""
    sql = (ROOT / "app" / "sql").glob("*.sql")
    bodies = [p.read_text() for p in sql]
    inbox = [b for b in bodies if "CREATE OR REPLACE VIEW v_evidence_inbox" in b]
    assert inbox, "nothing redefines v_evidence_inbox"
    assert any("ingest_channel <> 'GENERATED'" in b for b in inbox)


def test_the_guide_kind_has_a_folder():
    """`FOUNDATION_KINDS` is the whole mechanism: nobody chooses a path. A
    guide that fell through to the default would be filed under a year, and
    a manual is not one period's evidence."""
    from app import storage

    assert storage.FOUNDATION_KINDS.get("guide") == "guides"
    assert "guides" in storage.FOUNDATION_CATEGORIES
    path = storage.evidence_path("2025", "guide", "0" * 64, "controller.md")
    assert path.parent == storage.FOUNDATION / "guides"


# ── The boot ─────────────────────────────────────────────────────────

def test_the_boot_calls_it_after_the_migrations_and_the_volume():
    """It writes rows the migrations create tables for and bytes the
    skeleton holds, so the order is not a preference."""
    src = (ROOT / "app" / "main.py").read_text()
    lifespan = src[src.index("async def lifespan"):src.index("app = FastAPI")]
    for earlier in ("run_migrations()", "storage.ensure_skeleton()"):
        assert lifespan.index(earlier) < lifespan.index("foundation.restore()"), (
            f"foundation.restore() runs before {earlier}")


def test_a_deployment_with_no_signing_secret_refuses_to_start(monkeypatch):
    """`app/auth.py` says a deployment that refuses to start is cheaper than
    one that does not, and for the signing secret it did not refuse: the
    service booted green, passed the healthcheck and answered 500 to every
    sign-in.
    """
    import app.main as main

    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setattr(main.settings, "env", "prod")
    monkeypatch.delenv("YBI_JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="YBI_JWT_SECRET"):
        main.check_deployment()


def test_a_deployment_that_is_configured_starts(monkeypatch):
    """The other half, so the check above cannot pass by refusing
    everything."""
    import app.main as main

    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setattr(main.settings, "env", "prod")
    monkeypatch.setenv("YBI_JWT_SECRET", "x" * 40)
    main.check_deployment()


def test_off_railway_nothing_is_required(monkeypatch):
    """A laptop has neither variable and is not a deployment."""
    import app.main as main

    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("YBI_JWT_SECRET", raising=False)
    main.check_deployment()


def test_it_is_the_only_module_outside_a_router_that_files_a_document():
    """`storage.place()` is the one place a path is decided. This module is
    a fourth writer of bytes and goes through the same door, or the tree and
    the register drift apart."""
    tree = ast.parse(SRC)
    writes = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in {"write_bytes", "write_text"}]
    assert not writes, "app/foundation.py writes bytes without storage.place()"
    assert "storage.place(" in SRC
