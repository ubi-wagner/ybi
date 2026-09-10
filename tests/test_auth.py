"""Actor authentication and role separation.

These run without a database: the parts under test are the token, the password
hash, and the role predicates. The end-to-end path — a real login through the
API, against real rows — is `scripts/drive_actors.py`, which is where a
permission claim has to be proved.
"""

from __future__ import annotations

import os
import time

import jwt
import pytest

os.environ.setdefault(
    "YBI_JWT_SECRET",
    "test-secret-not-for-deployment-padded-to-the-minimum-length")

from app.auth import (READERS, WRITERS, Actor, AuthNotConfigured, Role,
                      hash_password, issue_token, jwt_secret, read_token,
                      verify_password)


def token_for(role: Role = Role.CONTROLLER, employee_key=None) -> str:
    return issue_token(actor_id="a-1", session_id="s-1", email="t@ybi.org",
                       role=role.value, name="Tester",
                       employee_key=employee_key)


# --------------------------------------------------------------- passwords


def test_password_round_trips():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)


def test_wrong_password_is_refused():
    h = hash_password("correct horse battery staple")
    assert not verify_password("Correct horse battery staple", h)


def test_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


@pytest.mark.parametrize("garbage", ["", "not-a-hash", "$2b$12$short"])
def test_malformed_hash_is_refused_not_raised(garbage):
    """A corrupt hash must deny, not crash into a 500 that reveals it."""
    assert verify_password("anything", garbage) is False


# ------------------------------------------------------------------ tokens


def test_token_round_trips():
    claims = read_token(token_for())
    assert claims["email"] == "t@ybi.org"
    assert claims["role"] == "CONTROLLER"
    assert claims["sid"] == "s-1"


def test_expired_token_is_refused():
    payload = {"sub": "a-1", "sid": "s-1", "role": "CONTROLLER",
               "iat": int(time.time()) - 100, "exp": int(time.time()) - 10}
    assert read_token(jwt.encode(payload, jwt_secret(), algorithm="HS256")) is None


def test_token_signed_with_another_secret_is_refused():
    forged = jwt.encode({"sub": "a-1", "sid": "s-1", "role": "ADMIN",
                         "exp": int(time.time()) + 600},
                        "a-different-secret-also-padded-to-thirty-two-bytes",
                        algorithm="HS256")
    assert read_token(forged) is None


def test_unsigned_token_is_refused():
    """alg=none is the classic JWT bypass."""
    forged = jwt.encode({"sub": "a-1", "sid": "s-1", "role": "ADMIN",
                         "exp": int(time.time()) + 600},
                        key="", algorithm="none")
    assert read_token(forged) is None


def test_garbage_is_refused():
    assert read_token("not.a.token") is None
    assert read_token("") is None


def test_missing_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("YBI_JWT_SECRET", raising=False)
    with pytest.raises(AuthNotConfigured, match="is not set"):
        jwt_secret()


def test_short_secret_fails_closed(monkeypatch):
    """A weak HMAC key is a forgeable session cookie, not a style issue."""
    monkeypatch.setenv("YBI_JWT_SECRET", "too-short")
    with pytest.raises(AuthNotConfigured, match="at least 32"):
        jwt_secret()


# ------------------------------------------------------------------- roles


def test_only_the_controller_writes():
    assert WRITERS == {Role.CONTROLLER}


def test_the_auditor_reads_but_never_writes():
    auditor = Actor("a", "e", "n", Role.AUDITOR, "s")
    assert auditor.can_read
    assert not auditor.can_write


def test_administering_people_is_not_making_cost_judgments():
    """ADMIN provisions actors and does not thereby acquire the write role."""
    admin = Actor("a", "e", "n", Role.ADMIN, "s")
    assert not admin.can_write


def test_an_employee_is_not_a_reader_of_the_whole_ledger():
    employee = Actor("a", "e", "n", Role.EMPLOYEE, "s", employee_key="EWING")
    assert not employee.can_read
    assert not employee.can_write


def test_readers_cover_exactly_the_roles_that_may_look():
    assert READERS == {Role.CONTROLLER, Role.AUDITOR, Role.ADMIN}


# ----------------------------------------------------- certification scope


def test_an_employee_certifies_only_their_own_effort():
    ewing = Actor("a", "e", "n", Role.EMPLOYEE, "s", employee_key="EWING")
    assert ewing.owns_employee("EWING")
    assert not ewing.owns_employee("GAFFNEY")


def test_the_controller_cannot_certify_on_an_employees_behalf():
    """2 CFR 200.430(i) wants the person who did the work, or a supervisor
    with firsthand knowledge. A controller signature is neither."""
    tom = Actor("a", "e", "n", Role.CONTROLLER, "s")
    assert not tom.owns_employee("EWING")
    assert not tom.owns_employee("")


def test_an_employee_key_of_none_owns_nothing():
    actor = Actor("a", "e", "n", Role.EMPLOYEE, "s", employee_key=None)
    assert not actor.owns_employee("EWING")
