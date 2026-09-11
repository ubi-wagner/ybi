"""Who may open a document, and what a browser is allowed to do with it.

Three rules live here. Two are access rules that a handler could drift away
from silently, and one is the reason the inline view is safe to offer at all.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "app" / "sql"
DOCUMENTS = ROOT / "app" / "routers" / "documents.py"
PAGES = ROOT / "web" / "src" / "pages"


def _view(name: str) -> str:
    for path in sorted(SQL.glob("*.sql"), reverse=True):
        src = path.read_text()
        m = re.search(
            rf"CREATE (?:OR REPLACE )?VIEW {name} AS(.*?);\s*(?:COMMENT|CREATE|--|$)",
            src, re.S)
        if m:
            return re.sub(r"--[^\n]*", "", m.group(1))
    raise AssertionError(f"{name} is not defined in any migration")


def test_the_library_is_gated_on_reading_the_record():
    """Not on a portfolio, and not on rank.

    The library is the cost record in document form, so it takes the same
    gate the review screens take. `require_office` would be wrong in both
    directions: it would admit somebody who may file a receipt but may not
    read the ledger, and refuse the auditor, who may read everything and
    holds no portfolio at all.
    """
    src = DOCUMENTS.read_text()
    m = re.search(r'@router\.get\("/library"\)(.*?)(?=\n@router\.|\Z)', src, re.S)
    assert m, "the library route is gone"
    body = m.group(1)
    assert "require_reader" in body, (
        "the document library is not gated on require_reader. Every document "
        "in the organisation is behind this route.")
    for wrong in ("require_office", "require_controller", "current_actor"):
        assert f"Depends({wrong})" not in body, (
            f"the library is gated on {wrong}; reading the cost record is "
            f"one permission and require_reader is it")


def test_a_document_belongs_to_its_uploader_or_to_a_reader():
    """An employee's receipt is not public to the organisation just because
    it was sent to the finance system."""
    src = DOCUMENTS.read_text()
    m = re.search(r'@router\.get\("/\{evidence_id\}/file"\)(.*?)(?=\n@router\.|\ndef _header_safe|\Z)',
                  src, re.S)
    assert m, "the file route is gone"
    body = m.group(1)
    assert "actor.can_read" in body and "uploaded_by" in body, (
        "the file route no longer checks that the document is yours or that "
        "you may read the record")


def test_inline_rendering_is_an_allowlist_and_the_two_copies_agree():
    """The handler decides the disposition and the view reports it to the
    screen. They are the same set or the screen offers a preview the handler
    will refuse — or worse, the reverse.

    The set itself is the point. Everybody signed in may upload, so an inline
    render on this origin is a door held open by whoever sends a file in.
    `text/html` or `image/svg+xml` inline is a script running as the
    controller.
    """
    src = DOCUMENTS.read_text()
    m = re.search(r"INLINE_SAFE = frozenset\(\{(.*?)\}\)", src, re.S)
    assert m, "INLINE_SAFE is gone from the handler"
    handler = set(re.findall(r'"([^"]+)"', m.group(1)))

    body = _view("v_document_library")
    m = re.search(r"inline_safe|IN \((.*?)\)\s*AS\s*inline_safe", body, re.S)
    view_block = re.search(
        r"lower\(coalesce\(e\.mime_type, ''\)\) IN \((.*?)\)", body, re.S)
    assert view_block, "v_document_library no longer publishes an allowlist"
    view = set(re.findall(r"'([^']+)'", view_block.group(1)))

    assert handler == view, (
        f"the handler and v_document_library disagree about what may be "
        f"shown inline: handler only {sorted(handler - view)}, view only "
        f"{sorted(view - handler)}")

    for dangerous in ("text/html", "image/svg+xml", "application/xhtml+xml",
                      "text/xml", "application/xml"):
        assert dangerous not in handler, (
            f"{dangerous} is on the inline allowlist. Anybody signed in may "
            f"upload; that is a script running as whoever opens it.")


def test_an_inline_response_refuses_to_be_sniffed():
    """A content type is a claim the uploader made, not a fact about the
    bytes. Without nosniff a browser may decide for itself and land outside
    the allowlist."""
    src = DOCUMENTS.read_text()
    assert "X-Content-Type-Options" in src and "nosniff" in src, (
        "the file route no longer sends nosniff")
    assert "Content-Security-Policy" in src and "sandbox" in src, (
        "the file route no longer sandboxes what it hands back")


def test_the_library_never_hands_out_a_path():
    """The database is the index and the tree is a convenience. A path that
    reaches a screen is a path somebody will parse back into a row."""
    body = _view("v_document_library")
    assert re.search(r"\be\.uri\b(?!\s+IS\s+NOT\s+NULL)", body) is None, (
        "v_document_library selects the stored path. Nothing outside "
        "storage.py needs to know where a file sits on disk.")


def test_the_filename_is_a_column_and_not_a_parsed_path():
    """It survived only inside the stored name, and a screen that printed it
    would have had to read a path backwards to get it."""
    joined = "\n".join(p.read_text() for p in sorted(SQL.glob("*.sql")))
    assert "ALTER TABLE evidence ADD COLUMN filename" in joined, (
        "evidence.filename is gone; the library has no name to print")
    src = DOCUMENTS.read_text()
    # The column, in the INSERT's column list — not a literal fragment of
    # punctuation. This asserted `"suggested_for, filename)"`, which broke
    # the day the upload learned to record the amount, date and vendor as
    # well, and argued against a correct change. A test that can only pass on
    # one spelling of working code is a test about the spelling.
    insert = src[src.index("INSERT INTO evidence"):]
    columns = insert[:insert.index("VALUES")]
    assert "filename" in columns, (
        "the upload route no longer records the name the document arrived "
        "under, so every new document joins the library nameless")


def test_the_preview_frame_carries_no_sandbox_attribute():
    """It reads like a safety measure and it is not one.

    Chromium refuses to run its PDF viewer inside a frame carrying
    `sandbox`, at every value of the attribute — `allow-scripts` included —
    and renders "This page has been blocked by Chromium" in place of the
    document. Twelve of the eighteen foundational documents are PDFs, so the
    attribute does not harden the preview panel, it switches it off.

    Nothing is given up. The sandbox that matters is on the response, in the
    Content-Security-Policy the file route sets: Chromium honours it *and*
    still renders a PDF under it, it puts the document in an opaque origin
    the same way, and being on the response it travels with the file even
    when it is opened outside this frame. The type is read from the bytes at
    upload besides, so nothing that could carry script is ever served under
    a type a parser would execute.

    This was measured in a browser, against all six combinations, not
    reasoned about. Re-add the attribute and the panel goes dark.
    """
    for page in ("Library.jsx", "MyDocuments.jsx"):
        src = (PAGES / page).read_text()
        for m in re.finditer(r"<iframe\b[^>]*>", src, re.S):
            assert "sandbox" not in m.group(0), (
                f"{page} has a sandbox attribute on its preview frame. "
                f"Chromium will not render a PDF inside one, and twelve of "
                f"the documents on file are PDFs. The Content-Security-Policy "
                f"on the response is what sandboxes this.")
