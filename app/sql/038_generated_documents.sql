-- 038 — a document the system made
--
-- `ingest_channel` has said how a document reached the record since 002:
-- UPLOAD, EMAIL, DRIVE_SYNC, SCAN, API. Every one of them means the same
-- thing underneath — it came from outside, and somebody or something handed
-- it over.
--
-- A regenerated invoice did not. It is rendered from `invoice` and
-- `invoice_line`, which are rows this system already holds, and that makes it
-- a different kind of object however similar the PDF looks: it is a
-- *rendering of the record*, not evidence about the world. It cannot
-- corroborate anything the register does not already say, because it is the
-- register. Filing it as UPLOAD would put it on the same shelf as the
-- invoice NCDMM actually received, indistinguishable, which is precisely the
-- confusion the "not the document of record" band on its face exists to
-- prevent. The band is on the paper; this is the same statement in the index.
--
-- So the channel says so, and `v_document_library` can tell a reader which
-- documents in front of them came from somewhere and which came from here.

ALTER TABLE evidence DROP CONSTRAINT evidence_ingest_channel_check;
ALTER TABLE evidence ADD CONSTRAINT evidence_ingest_channel_check
  CHECK (ingest_channel IN ('UPLOAD','EMAIL','DRIVE_SYNC','SCAN','API',
                            'GENERATED'));

COMMENT ON COLUMN evidence.ingest_channel IS
  'How the document reached the record. Everything but GENERATED came from '
  'outside; GENERATED means this system rendered it from its own rows, so it '
  'is a presentation of the record rather than evidence about the world and '
  'corroborates nothing the record does not already say.';

-- The library already reports the channel. This makes the distinction the
-- one a reader actually cares about — is this paper somebody sent us, or is
-- it our own arithmetic in a nice font — without every screen having to know
-- the list of channels.
CREATE OR REPLACE VIEW v_document_library AS
SELECT e.evidence_id,
       e.period,
       e.kind,
       e.filename,
       e.uri IS NOT NULL                                AS has_file,
       e.received_at,
       e.received_from,
       e.byte_size,
       e.mime_type,
       e.doc_date,
       e.doc_amount,
       e.vendor_name,
       e.note,
       e.suggested_for,
       e.ingest_channel,
       e.uploaded_by,
       a.display_name                                   AS uploaded_by_name,
       lower(coalesce(e.mime_type, '')) IN (
         'application/pdf',
         'image/png', 'image/jpeg', 'image/gif', 'image/webp',
         'text/plain', 'text/csv'
       )                                                AS inline_safe,
       (SELECT count(*) FROM attachment t
         WHERE t.evidence_id = e.evidence_id AND t.detached_at IS NULL)
                                                        AS attachments,
       EXISTS (SELECT 1 FROM attachment t
                WHERE t.evidence_id = e.evidence_id AND t.detached_at IS NULL)
                                                        AS is_attached,
       (SELECT string_agg(DISTINCT t.target_type::text, ', ')
          FROM attachment t
         WHERE t.evidence_id = e.evidence_id AND t.detached_at IS NULL)
                                                        AS supports,
       -- Appended rather than slotted in beside ingest_channel where it
       -- belongs: CREATE OR REPLACE VIEW can only add columns at the end,
       -- and dropping the view to reorder it would be a schema change with
       -- real risk for a cosmetic gain.
       e.ingest_channel = 'GENERATED'                   AS is_generated
  FROM evidence e
  LEFT JOIN actor a ON a.actor_id = e.uploaded_by;

COMMENT ON VIEW v_document_library IS
  'Every document in the record, for the people entitled to read it: the '
  'controller, whoever is helping them, and the auditor. inline_safe is the '
  'allowlist of types a browser renders without running anything the '
  'uploader wrote; everything else, recognised or not, downloads. '
  'is_generated marks a document this system rendered from its own rows '
  'rather than one that came from outside.';
