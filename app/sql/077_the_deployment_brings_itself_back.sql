-- 077  The inbox is what nobody has filed yet, and a manual is not waiting
--
-- `app/foundation.py` files the manuals and the generated PDFs so they are
-- readable in the library rather than only on somebody's laptop. They go in
-- as `GENERATED` — the channel `038` added because every other value means
-- the document came from outside and there was no way to say *this system
-- made it*.
--
-- Which is exactly why they must not appear here. `v_evidence_inbox` is the
-- queue of documents somebody sent in that nobody has yet said anything
-- about, and the screen reading it shows what is unattached. A rendering of
-- this system's own register is not waiting for a judgment: nobody is ever
-- going to attach the controller's manual to a ledger line, so it would sit
-- at the top of that list for ever.
--
-- This is the defect the evidence screen already learned once — *thirty-two
-- request-reply workbooks nobody has read the face of, each repeating the
-- same sentence, buried three real proposals*. Eight guides and however many
-- restated invoices have been filed would do the same thing, and a queue
-- that is mostly things nobody can act on teaches the reader to skim it.
--
-- The restated invoices are the same case and were already in it, which is
-- why the filter is on the channel rather than on the kind: `038` files a
-- regenerated invoice as `GENERATED` and it corroborates nothing the
-- register does not already say.
--
-- The body below is **lifted from the definition in force** rather than
-- retyped. Only the WHERE is new.

CREATE OR REPLACE VIEW v_evidence_inbox AS
 SELECT e.evidence_id,
    e.period,
    e.kind,
    e.received_at,
    e.received_from,
    e.byte_size,
    e.mime_type,
    e.doc_date,
    e.doc_amount,
    e.vendor_name,
    e.note,
    e.suggested_for,
    e.uploaded_by,
    a.display_name AS uploaded_by_name,
    a.employee_key AS uploaded_by_employee,
    ( SELECT count(*) AS count
           FROM attachment t
          WHERE t.evidence_id = e.evidence_id AND t.detached_at IS NULL) AS attachments,
    (EXISTS ( SELECT 1
           FROM attachment t
          WHERE t.evidence_id = e.evidence_id AND t.detached_at IS NULL)) AS is_attached
   FROM evidence e
     LEFT JOIN actor a ON a.actor_id = e.uploaded_by
 WHERE e.ingest_channel <> 'GENERATED';

COMMENT ON VIEW v_evidence_inbox IS
  'Documents sent in that nobody has yet said what they support. Excludes '
  'GENERATED: a rendering this system made is not waiting for a judgment.';
