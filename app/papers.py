"""How a generated paper reaches the person who asked for it.

One place decides whether a PDF opens in the page or saves to disk, because
there was no such place and the four routes that render a paper all sent
`Content-Disposition: inline` — including the ones behind a button reading
**Download**.

That worked by accident. `Reports.jsx` builds an `<a download>` and clicks
it, and whether the browser honours that attribute over an explicit `inline`
from the server is a thing browsers disagree about. The controller's own
session is the record of what that costs: three invoices fetched in sixteen
seconds, every one answered 200 with an audit row written, and nothing
landing on his machine.

The library settled this shape already — `?inline=1` views and the bare URL
downloads — so the **default here is the save**, which is what a button
reading Download has to do on every browser rather than on most of them. A
preview frame asks for `inline` explicitly, because that is the caller who
actually wants it.
"""

from __future__ import annotations

from fastapi import Response


def as_pdf(body: bytes, name: str, inline: bool = False) -> Response:
    """A rendered PDF, saved by default and shown only when asked.

    `nosniff` for the same reason the library sends it: a content type is a
    claim, and this one is ours, so there is nothing for a browser to
    improve by guessing.

    And the sandboxing `Content-Security-Policy` the library already sends,
    which `Reports.jsx` **says** is on this response — *"the
    Content-Security-Policy on the response does the same job"*, in the
    comment explaining why the preview frame carries no `sandbox`
    attribute. It was not on this response. A comment asserting a safety
    measure that is not there is worse than no comment, because the next
    person reads it and stops looking. The header travels with the file even
    when it is opened outside the panel, which is the half that matters.
    """
    disposition = "inline" if inline else "attachment"
    return Response(
        body, media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{name}"',
                 "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy":
                     "default-src 'none'; object-src 'self'; "
                     "plugin-types application/pdf; sandbox"})
