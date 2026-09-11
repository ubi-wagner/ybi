"""The shape of the volume.

`app/storage.py` derives a path from what the database row already says. These
tests pin the derivation, because the tree is what a person browses when they
are looking for a document under time pressure and a layout that shifts
between releases is worse than no layout at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import storage

SHA = "9b9bee496040ace6" + "f" * 48


# ------------------------------------------------------------------ slugs


@pytest.mark.parametrize("raw,expect", [
    ("invoice", "invoice"),
    ("Market rate analysis (2025)", "market-rate-analysis-2025"),
    ("  Lease — tenant  ", "lease-tenant"),
    ("GENERAL_LEDGER", "general-ledger"),
    ("///", "other"),
    ("", "other"),
])
def test_slug_survives_what_people_actually_type(raw, expect):
    assert storage.slug(raw) == expect


def test_slug_truncates_rather_than_refusing():
    """`kind` is free text and the inbox lets somebody paste a sentence."""
    out = storage.slug("a" * 200)
    assert len(out) == 60 and out == "a" * 60


def test_slug_never_returns_something_that_climbs():
    for nasty in ("..", "../..", "/etc/passwd", ".", "a/../../b"):
        assert storage.slug(nasty) not in ("", ".", "..")
        assert "/" not in storage.slug(nasty)


# ------------------------------------------------------------------ names


def test_stored_name_keeps_the_hash_prefix_and_the_readable_name():
    assert storage.stored_name(SHA, "2025_Lease.pdf") \
        == "9b9bee496040ace6_2025_Lease.pdf"


def test_a_filename_cannot_escape_its_directory():
    """Filenames are attacker-supplied on every upload route."""
    name = storage.stored_name(SHA, "../../../etc/passwd")
    assert name == "9b9bee496040ace6_passwd"
    assert "/" not in name


def test_a_missing_filename_still_gets_a_name():
    assert storage.stored_name(SHA, None).endswith("_document")


# ------------------------------------------------------------------ trees


def test_the_three_trees_hang_off_the_configured_root():
    for tree in (storage.SOURCE, storage.FOUNDATION, storage.EVIDENCE):
        assert tree.parent == storage.ROOT


def test_source_is_period_then_report():
    p = storage.source_path("2025", "GENERAL_LEDGER", SHA, "GL.xlsx")
    assert p.relative_to(storage.ROOT) == Path(
        "source/2025/general-ledger/9b9bee496040ace6_GL.xlsx")


def test_evidence_is_period_then_kind():
    p = storage.evidence_path("2025", "Invoice", SHA, "inv-4471.pdf")
    assert p.relative_to(storage.ROOT) == Path(
        "evidence/2025/invoice/9b9bee496040ace6_inv-4471.pdf")


def test_foundation_is_not_period_nested():
    """An agreement signed in 2023 governs 2025 and will govern 2026.

    Filing it under a year files it under the wrong question.
    """
    p = storage.foundation_path("awards", SHA, "NCDMM.pdf")
    assert p.relative_to(storage.ROOT) == Path(
        "foundation/awards/9b9bee496040ace6_NCDMM.pdf")


def test_an_unknown_period_is_named_rather_than_dropped():
    p = storage.evidence_path("", "invoice", SHA, "x.pdf")
    assert "unknown-period" in str(p)


# ------------------------------------------------------------------ writing


def test_place_creates_the_directory_and_returns_where_it_wrote(tmp_path,
                                                               monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    dest = tmp_path / "evidence" / "2025" / "invoice" / "x.pdf"
    assert storage.place(dest, b"hello") == dest
    assert dest.read_bytes() == b"hello"


def test_skeleton_is_idempotent_and_leaves_a_readme(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(storage, "SOURCE", tmp_path / "source")
    monkeypatch.setattr(storage, "FOUNDATION", tmp_path / "foundation")
    monkeypatch.setattr(storage, "EVIDENCE", tmp_path / "evidence")

    first = storage.ensure_skeleton()
    assert first, "the first run should create the tree"
    assert (tmp_path / "README.txt").read_text() == storage.README
    for category in storage.FOUNDATION_CATEGORIES:
        assert (tmp_path / "foundation" / category).is_dir()

    assert storage.ensure_skeleton() == [], "the second run should create nothing"


# -------------------------------------------------- the kind decides the tree


@pytest.mark.parametrize("kind,category", [
    ("form-990", "tax-filings"),
    ("Form 990", "tax-filings"),
    ("award-agreement", "awards"),
    ("subrecipient-agreement", "awards"),
    ("audited-financial-statements", "financial-statements"),
    ("general-ledger", "accounting-records"),
    ("nicra", "rate-agreements"),
])
def test_a_foundational_kind_lands_in_foundation(kind, category):
    p = storage.evidence_path("2023", kind, SHA, "doc.pdf")
    assert p.parent == storage.FOUNDATION / category
    assert "2023" not in str(p.relative_to(storage.ROOT).parent)


@pytest.mark.parametrize("kind", ["invoice", "lease", "timesheet",
                                  "market-rate-analysis", "receipt",
                                  "photograph", "document"])
def test_everything_else_stays_with_its_period(kind):
    """Period evidence is the safe default and has to be the default."""
    p = storage.evidence_path("2025", kind, SHA, "doc.pdf")
    assert p.parent == storage.EVIDENCE / "2025" / storage.slug(kind)


def test_lease_is_deliberately_not_foundational():
    """The building lease is foundational; a comparable lease is evidence.

    The kind alone cannot tell them apart, so it does not try. Guessing would
    move a market-rate comparable out of the period it supports, which is the
    failure nobody notices.
    """
    assert "lease" not in storage.FOUNDATION_KINDS


def test_every_foundation_category_is_one_something_lands_in():
    """No folder exists that the application will never fill.

    An empty `policies/` is a question — there is no written cost policy on
    file — and a question is only worth showing if an answer could appear
    there.
    """
    assert set(storage.FOUNDATION_CATEGORIES) \
        == set(storage.FOUNDATION_KINDS.values())
