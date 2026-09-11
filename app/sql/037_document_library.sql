-- 037 — the document library
--
-- Three readers need to open a document rather than know it exists: the
-- controller, the people helping them, and the auditor. Until now the only
-- way to a file was the download route, and the only way to find one was to
-- have uploaded it yourself or to be holding OFFICE and looking at the
-- unattached queue. A reader could see that EV-9f2c1a4b0e77 supported the
-- lease test and had no way to read it.
--
-- Two things were missing to build that screen honestly.

-- 1. The filename.
--
-- A document has a name — the one it arrived under — and the record did not
-- keep it. It survived only inside the stored path as `<sha16>_<name>`, and
-- a screen that wanted to print it would have had to parse the path back
-- into a row, which is the one thing the storage layout says never to do:
-- the database is the index and the tree is a convenience. So the name
-- becomes a column and the index owns it.
--
-- The backfill below reads the stored name once. That is not the rule being
-- broken, it is the moment the rule takes effect: this is the last read of a
-- path for anything other than opening the bytes behind it.

ALTER TABLE evidence ADD COLUMN filename text NOT NULL DEFAULT '';

COMMENT ON COLUMN evidence.filename IS
  'The name the document arrived under. Display and download only — it is '
  'never part of a path decision, which storage.place() owns, and two '
  'documents may share a name without being the same document (sha256 '
  'decides that).';

UPDATE evidence
   SET filename = regexp_replace(split_part(uri, '/', -1), '^[0-9a-f]{16}_', '')
 WHERE filename = '';

-- 2. Whether it is safe to show inline.
--
-- A reader wants a PDF in a panel, not in a downloads folder. But an upload
-- is attacker-supplied bytes under an attacker-supplied content type, and
-- rendering `text/html` inline on this origin hands the uploader a script
-- running as the controller — on a system whose whole claim is that the
-- controller's judgments are theirs. Everybody in the organisation may
-- upload, which is exactly the door that makes this reachable.
--
-- So the allowlist is a view, not a handler's opinion: the set of types that
-- a browser renders without executing anything the uploader wrote. Anything
-- not on it downloads, including anything unrecognised — an uploader who
-- mislabels a file gets a download rather than a decision made in their
-- favour. The handler sets the disposition from this column and sends
-- nosniff besides, because a content type is a claim and not a fact.

CREATE VIEW v_document_library AS
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
       -- target_type is an enum, and string_agg wants text. The cast is
       -- not cosmetic: without it the view will not create at all.
       (SELECT string_agg(DISTINCT t.target_type::text, ', ')
          FROM attachment t
         WHERE t.evidence_id = e.evidence_id AND t.detached_at IS NULL)
                                                        AS supports
  FROM evidence e
  LEFT JOIN actor a ON a.actor_id = e.uploaded_by;

COMMENT ON VIEW v_document_library IS
  'Every document in the record, for the people entitled to read it: the '
  'controller, whoever is helping them, and the auditor. inline_safe is the '
  'allowlist of types a browser renders without running anything the '
  'uploader wrote; everything else, recognised or not, downloads.';
