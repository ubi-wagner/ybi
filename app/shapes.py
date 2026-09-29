"""Record what a document is shaped like, at the door it comes in by.

`app/domain/document_shape.py` is the reading and is pure. This is the one
place that writes it down, for the reason `storage.place()` is the one place
a path is decided: there are five doors a document can arrive by — the
importer, the evidence route, the inbox everybody has, a request reply and
the boot — and a fact recorded at four of them is a fact that is missing
exactly where somebody will later assume it is present.

`tests/test_every_evidence_writer_records_a_shape.py` fails a sixth door
that files a document and does not call this.

**It never raises.** A document whose form cannot be read is a finding and
the row says so; a reader that took the upload down with it would trade a
document nobody can analyse for a document nobody could file.
"""

from __future__ import annotations

import logging

from app.db import execute
from app.domain import document_shape

log = logging.getLogger("ybi.shapes")

#: Bumped when the reading changes. A shape read by an older reader is not
#: wrong, it is older, and a register that could not say which is which would
#: average two different questions together.
READER = "document_shape/1"


def record_shape(evidence_id: str, raw: bytes, mime: str) -> None:
    """Read the form and content of one document and write it down."""
    try:
        form, content = document_shape.shape_of(raw, mime)
    except Exception as exc:                            # noqa: BLE001
        # shape_of is written not to raise; this is the belt on top, because
        # the alternative is an upload that fails for a reason that has
        # nothing to do with the document being uploaded.
        log.warning("could not read the shape of %s: %s", evidence_id, exc)
        form, content = {"container": "unreadable",
                         "why": f"{type(exc).__name__}: {exc}"[:200]}, {}
    try:
        execute("""INSERT INTO document_shape (evidence_id, form, content,
                                               reader)
                   VALUES (%s, %s::jsonb, %s::jsonb, %s)
                   ON CONFLICT (evidence_id) DO UPDATE
                     SET form = EXCLUDED.form,
                         content = EXCLUDED.content,
                         reader = EXCLUDED.reader,
                         read_at = now()""",
                (evidence_id, _json(form), _json(content), READER))
    except Exception as exc:                            # noqa: BLE001
        log.warning("could not record the shape of %s: %s", evidence_id, exc)


def _json(value: dict) -> str:
    import json
    return json.dumps(value, default=str)


def record_missing_shape(evidence_id: str, raw: bytes, mime: str) -> None:
    """Record a shape only where the row does not already carry one.

    The upload door is content-addressed, so a document sent twice returns
    early and files nothing — correctly. But the row it returns may predate
    the form being read at all, and this is the one moment the bytes and the
    row are in the same place. It never *replaces* a shape: re-reading on a
    new reader is `scripts/read_shapes.py`'s job and is a decision somebody
    makes, not something a duplicate upload does on the way past.
    """
    from app.db import one
    if one("SELECT 1 FROM document_shape WHERE evidence_id = %s",
           (evidence_id,)):
        return
    record_shape(evidence_id, raw, mime)
