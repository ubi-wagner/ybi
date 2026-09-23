"""The foundational documents named in the seed script are the ones on disk.

`scripts/seed_documents.py` names ten documents and the kind each one is. If
somebody renames a file in `docs/source-documents/`, the seed run fails
against a live service after signing in — which is the wrong place to find
out. This finds out in CI instead.

It also checks the claim the layout rests on: every kind in that manifest
either maps to a foundation folder or is honestly period evidence. A typo in
a kind is otherwise invisible — the document files quietly under
`evidence/<period>/<typo>/` and nobody sees it until they go looking for the
award agreement and it is not with the award agreements.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app import storage

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "source-documents"

_spec = importlib.util.spec_from_file_location(
    "seed_documents", ROOT / "scripts" / "seed_documents.py")
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


@pytest.mark.parametrize("name", sorted(seed.DOCUMENTS))
def test_every_named_document_is_on_disk(name):
    assert seed.find(name), (
        f"{name} is named in scripts/seed_documents.py but is not under "
        f"docs/source-documents/. Either restore it or take it out of the "
        f"manifest — a seed run that files nine of ten documents leaves the "
        f"register looking complete.")


def _named_by_a_loader() -> set[str]:
    """Filenames a script in `scripts/` reads by name.

    A source document reaches the record two ways, not one: filed into the
    library by `seed_documents.py`, or *read* by a loader on
    `foundation.REGISTERS` — the six invoice PDFs are the second kind, and
    nothing files them, because a rendering of the register would be filed
    beside the invoice the sponsor received and indistinguishable from it.

    Derived from the source rather than kept as a list here, because a list
    of which files are exempt is the map this repository has been wrong
    about four times in one run.
    """
    text = "\n".join(p.read_text(errors="ignore")
                     for p in (ROOT / "scripts").glob("*.py"))
    return {p.name for p in SOURCE.rglob("*")
            if p.is_file() and f'"{p.name}"' in text}


def test_nothing_on_disk_is_left_unnamed():
    """A document nobody declared is a document nobody reaches."""
    on_disk = {p.name for p in SOURCE.rglob("*") if p.is_file()}
    unreachable = on_disk - set(seed.DOCUMENTS) - _named_by_a_loader()
    assert not unreachable, (
        "these are in docs/source-documents/ and nothing names them — not "
        "the seed manifest, not a loader — so they would never reach the "
        "record: " + ", ".join(sorted(unreachable)))


def test_every_invoice_pdf_the_loader_reads_is_in_the_image():
    """The runner and what it runs on ship together.

    They did not. The six PDFs lived in `intake/`, which is gitignored, so
    the Dockerfile never copied them and every deployment's register walk
    reported `/srv/intake/Rising_Tides.pdf is not there` and loaded nothing.
    A runner in the image with nothing in the image to run.
    """
    _s = importlib.util.spec_from_file_location(
        "load_invoices_2025", ROOT / "scripts" / "load_invoices_2025.py")
    li = importlib.util.module_from_spec(_s)
    try:
        _s.loader.exec_module(li)
    except SystemExit:
        pass
    missing = [x["pdf"] for x in li.STREAMS if not (li.INVOICES / x["pdf"]).exists()]
    assert not missing, (
        "load_invoices_2025.py reads these and they are not under "
        f"{li.INVOICES.relative_to(ROOT)}: " + ", ".join(missing))


@pytest.mark.parametrize("name,kind", sorted(
    (n, v[0]) for n, v in seed.DOCUMENTS.items()))
def test_each_kind_is_spelled_the_way_the_layout_spells_it(name, kind):
    assert storage.slug(kind) == kind, (
        f"{name} is declared as {kind!r}, which slugs to "
        f"{storage.slug(kind)!r}. Write the kind in the form the tree uses "
        f"so the folder and the register read the same.")


def test_the_governing_documents_are_declared_as_foundational():
    """Agreements, statements, filings and the exports are not 2025 evidence.

    They govern the engagement or pre-date it. If one of these ever stops
    mapping to a foundation folder it will file under a single year, and the
    2023 Form 990 sitting in `evidence/2023/` is a document a reviewer will
    not find where they look for it.
    """
    for name, (kind, _, _) in seed.DOCUMENTS.items():
        assert kind in storage.FOUNDATION_KINDS, (
            f"{name} is declared {kind!r}, which app/storage.py does not "
            f"treat as foundational.")


def test_each_document_carries_the_year_it_is_of():
    """The period is the year the document is of, not the year it governs."""
    for name, (_, period, _) in seed.DOCUMENTS.items():
        assert period in name, (
            f"{name} is filed under period {period}, which does not appear "
            f"in its name. One of the two is wrong.")
