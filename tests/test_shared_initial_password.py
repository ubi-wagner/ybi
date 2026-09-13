"""The organisation's shared first-login password.

A round where a set of accounts is opened at once and each person claims their
own. The shared value is a **setting**, never a stored hash, and these hold the
four properties that follow from that:

- it lets somebody in who has not set their own password,
- it stops letting them in the moment they do,
- clearing or shortening the setting closes the door for everybody at once,
- and it is never a way to find out whether an address has an account.

The write side is not tested here because it is not new: an account whose
`password_set_by` is not `SELF` is already refused every write by
`refuse_issued_password`, and `tests/test_auth.py` holds that. What is new is
only which credentials authenticate, and that is `check_credential`.

These run without a database. The end-to-end — a real login through the API
against real rows — is `scripts/drive_shared_password.py`.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault(
    "YBI_JWT_SECRET",
    "test-secret-not-for-deployment-padded-to-the-minimum-length")

from app.auth import (MIN_PASSWORD, check_credential, hash_password,
                      shared_initial_password, unusable_password_hash)
from app.settings import settings

OWN = "a password only this person knows"
SHARED = "ybi-first-login-2026"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "initial_password", SHARED)
    return SHARED


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "initial_password", "")


# ------------------------------------------------------- what it lets through

def test_the_shared_password_signs_in_an_account_that_has_not_set_one(configured):
    assert check_credential(SHARED, unusable_password_hash(), "SEED") == "SHARED"


def test_an_account_issued_a_password_may_also_use_the_shared_one(configured):
    """ADMIN is an administrator's reset, and it has not been claimed either.

    The rule is about whether the person has chosen the password, not about
    how the row came to exist.
    """
    assert check_credential(SHARED, hash_password("issued by an admin"),
                            "ADMIN") == "SHARED"


def test_an_account_keeps_its_own_password_too(configured):
    assert check_credential(OWN, hash_password(OWN), "SEED") == "OWN"


def test_the_two_are_reported_as_different_facts(configured):
    """Not a boolean. A sign-in on a password the organisation holds does not
    identify one person, and the trail records it as its own action."""
    own = check_credential(OWN, hash_password(OWN), "SELF")
    shared = check_credential(SHARED, unusable_password_hash(), "SEED")
    assert (own, shared) == ("OWN", "SHARED")


# ------------------------------------------------------------ when it stops

def test_claiming_your_own_password_closes_the_shared_door(configured):
    """The property the whole round rests on: person by person, as they go."""
    assert check_credential(SHARED, hash_password(OWN), "SELF") is None
    assert check_credential(OWN, hash_password(OWN), "SELF") == "OWN"


def test_clearing_the_setting_closes_it_for_everybody_at_once(unconfigured):
    """A shared password written into forty rows would take forty resets to
    withdraw. Held as a setting, it is one variable."""
    assert check_credential(SHARED, unusable_password_hash(), "SEED") is None


def test_rotating_the_setting_retires_the_old_value(monkeypatch):
    monkeypatch.setattr(settings, "initial_password", SHARED)
    assert check_credential(SHARED, unusable_password_hash(), "SEED") == "SHARED"
    monkeypatch.setattr(settings, "initial_password", "a-different-one-2026")
    assert check_credential(SHARED, unusable_password_hash(), "SEED") is None
    assert check_credential("a-different-one-2026", unusable_password_hash(),
                            "SEED") == "SHARED"


def test_a_short_default_is_ignored_rather_than_honoured(monkeypatch):
    """A six-character organisational default reads as a control and is not
    one. The door is shut, not left ajar at a weaker setting."""
    monkeypatch.setattr(settings, "initial_password", "ybi2026")
    assert shared_initial_password() == ""
    assert check_credential("ybi2026", unusable_password_hash(), "SEED") is None


@pytest.mark.parametrize("value", ["", "   ", "x" * (MIN_PASSWORD - 1)])
def test_nothing_below_the_minimum_configures_anything(monkeypatch, value):
    monkeypatch.setattr(settings, "initial_password", value)
    assert shared_initial_password() == ""


def test_whitespace_around_the_setting_is_not_part_of_it(monkeypatch):
    """A value pasted into a Railway variable arrives with whatever was
    selected around it, and a password nobody can type is an outage."""
    monkeypatch.setattr(settings, "initial_password", f"  {SHARED}\n")
    assert shared_initial_password() == SHARED
    assert check_credential(SHARED, unusable_password_hash(), "SEED") == "SHARED"


# ------------------------------------------------------ what it must not leak

def test_it_is_not_an_oracle_for_whether_an_address_has_an_account(configured):
    """login passes SELF for an account that does not exist, so a guess at an
    unknown address is refused on the same path as a wrong password at a known
    one. Without this the shared credential would answer, for every address
    anybody cared to try, whether there is a row behind it — and this system
    knows the names of everyone at the organisation."""
    absent = "$2b$12$" + "x" * 53          # what login verifies against
    assert check_credential(SHARED, absent, "SELF") is None


def test_a_wrong_password_is_still_wrong(configured):
    assert check_credential("not it at all", unusable_password_hash(),
                            "SEED") is None


def test_the_shared_value_is_never_the_stored_hash():
    """Two accounts opened on the same shared password share no secret at
    rest, so a copy of the record is not a copy of the credential."""
    from app.auth import verify_password
    a, b = unusable_password_hash(), unusable_password_hash()
    assert a != b
    assert not verify_password(SHARED, a)
    assert not verify_password(SHARED, b)


def test_an_unusable_hash_is_a_real_hash_shape():
    """It goes into a NOT NULL column that `verify_password` will be handed.
    A placeholder that is not hash-shaped took login out with a 500 once."""
    from app.auth import verify_password
    assert not verify_password("", unusable_password_hash())
    assert not verify_password("anything", unusable_password_hash())
