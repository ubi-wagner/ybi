"""A guide printed as a PDF says what its manual says.

`docs/manuals/*.md` is the source and `scripts/guide_pdf.py` renders it, so
the two cannot drift by construction — until somebody edits the markdown and
does not reprint, which is the ordinary way it happens and which nothing
would otherwise report. The shelf serves the PDF, so a reader would get the
old document with no sign that a newer one exists.

Both sides are derived: the pairs come from `foundation.GUIDES` and the
headings from the markdown. There is no list here to fall out of date, which
is the defect this repository has been wrong about more often than any
other.

It reads the printed text back with `pypdf` rather than searching the bytes,
for the reason recorded in `requirements.txt`: PDF text is compressed, and
looking for a phrase plainly on the page finds nothing.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.foundation import GUIDE_DIR, GUIDES

def _text(pdf: Path) -> str:
    from pypdf import PdfReader

    return "\n".join(p.extract_text() for p in PdfReader(str(pdf)).pages)


def _pairs() -> list[tuple[Path, Path]]:
    """Every PDF guide that names the manual it was printed from.

    **The pairing is read off the document and never off its filename.** A
    first draft paired a `.pdf` with any `.md` of the same name, and
    `BARB_ONE_PAGE_AM.pdf` has one — written by its own script from the
    record, nothing to do with this renderer — so the sweep reported a
    correct document as stale. *A test that argues with correct code is
    worse than no test.* `guide_pdf.py` puts the source on the face of what
    it prints, so the artefact answers rather than a convention.
    """
    out = []
    for g in GUIDES:
        if not g.path.endswith(".pdf"):
            continue
        pdf = GUIDE_DIR / g.path
        m = re.search(r"Printed from\s+(\S+?\.md)",
                      " ".join(_text(pdf).split()))
        if not m:
            continue              # not printed by this renderer
        md = (GUIDE_DIR / ".." / m.group(1)).resolve()
        assert md.exists(), f"{pdf.name} names {m.group(1)}, which is not there"
        out.append((pdf, md))
    return out


PAIRS = _pairs()


def headings(md: str) -> list[str]:
    """Every `#` heading, with its inline markers taken off.

    The heading is what a reader navigates by and the coarsest thing that
    cannot be absent from a faithful rendering. Asserting whole paragraphs
    would fail on a line break the renderer is entitled to move.
    """
    out = []
    for line in md.splitlines():
        if line.startswith("#") and " " in line:
            out.append(re.sub(r"[*`]", "", line.lstrip("#").strip()))
    return out


def test_there_is_a_pdf_guide_to_check():
    """A sweep over an empty list passes for the wrong reason.

    Four sweeps in this repository iterate a register and every one of them
    is satisfied by nothing being there.
    """
    assert PAIRS, "no guide on the shelf names the manual it was printed from"


@pytest.mark.parametrize("pdf,md", PAIRS, ids=lambda p: Path(p).name)
def test_the_pdf_carries_every_heading_of_the_manual(pdf, md):
    text = " ".join(_text(pdf).split())
    missing = [h for h in headings(md.read_text())
               if " ".join(h.split()) not in text]
    assert not missing, (
        f"{pdf.name} is behind {md.name} — reprint it with "
        f"`python3 scripts/guide_pdf.py manuals/{md.name}`. Missing: {missing}")


@pytest.mark.parametrize("pdf,md", PAIRS, ids=lambda p: Path(p).name)
def test_the_pdf_prints_no_markdown_at_a_reader(pdf, md):
    """`**bold**` reaching the page is the renderer failing quietly.

    It did: emphasis spanning a code span had its two markers in different
    pieces and neither matched, so three paragraphs printed literal
    asterisks. Found by reading the rendered PDF back, which is the only
    way any of these are found.
    """
    text = _text(pdf)
    stray = {m: text.count(m) for m in ("**", "`", "| ---") if m in text}
    assert not stray, f"{pdf.name} prints markdown at a reader: {stray}"
