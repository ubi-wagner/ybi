-- 122 · A signature a drive made says so on the paper.
--
-- `scripts/drive_the_close.py` closes a year end to end so the mechanism can
-- be proved, and its own docstring says **run it against a clone** — because
-- it *"accepts recommendations, adopts 757 positions, certifies a rate and
-- records a sponsor's acceptance"*, and a cleanup that walked those back
-- would be withdrawing a signature and a position taken.
--
-- Nothing enforced that. It was run against the reference record, and the
-- committed publication set was generated from the result. So
-- `docs/SETTLEMENT_2025.md` — the memorandum addressed to NCDMM — opened on
--
--     The rate in this memorandum is CERTIFIED. Sealed at 757 judgments,
--     computed, and certified by Tom Metzinger, Controller, on 15 September 2026.
--
-- over a rate **nobody has signed**. The band worked perfectly: it printed
-- what the record said, and the record said it because a script typed
-- `"signature": "Tom Metzinger"` into `POST /api/rates/certify`.
--
-- This file records the near-miss once already — *"A set that says CERTIFIED
-- must not be signed by the machine"*, where a clone was rebuilt and the set
-- regenerated. `drive_the_close.py` was written afterwards and did the same
-- thing to the reference record. **Fixing one instance is not fixing the
-- rule**, for the third time, in the worst place available: a document that
-- goes to a sponsor.
--
-- **What was missing is a value for the kind of act**, which is the fifth
-- time this schema has needed one and the fifth time the answer is the same:
--
--     038  ingest_channel = 'GENERATED'   this system made the document
--     070  basis          = 'ADOPTED'     the organisation rebuilt it and
--                                         the person affirmed it
--     083  origin         = 'MACHINE_PROPOSAL'  the machine proposed it
--     120  certifier_role = 'PAPER'       they signed on paper and somebody
--                                         else filed the page
--     122  origin         = 'REHEARSAL'   a drive made this signature and no
--                                         person gave it
--
-- `certified_by` still names the account the call was made as, and the audit
-- row still names it, because that is what happened and editing it would be
-- inventing a history — `079`'s rule about 891 rows. What changes is that
-- the paper can tell the two apart, which is the whole of it.
--
-- **Nothing changes by default.** The column defaults to CONTROLLER, which is
-- what every certification before this was, and it is **write-once**: a
-- signature cannot be relabelled after the fact without withdrawing it.

ALTER TABLE rate_certification
  ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'CONTROLLER'
      CHECK (origin IN ('CONTROLLER', 'REHEARSAL'));

COMMENT ON COLUMN rate_certification.origin IS
  'CONTROLLER: a person put their name on this. REHEARSAL: a drive did, so '
  'every paper resting on it prints REHEARSAL rather than the signature. '
  'Write-once — relabelling a signature after the fact is inventing one.';

CREATE OR REPLACE FUNCTION certification_origin_is_write_once()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.origin IS DISTINCT FROM OLD.origin THEN
        RAISE EXCEPTION 'rate_certification.origin is write-once. A signature '
                        'that was a rehearsal stays one; withdraw it and '
                        'certify again rather than relabelling it.';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS certification_origin_write_once ON rate_certification;
CREATE TRIGGER certification_origin_write_once
  BEFORE UPDATE OF origin ON rate_certification
  FOR EACH ROW EXECUTE FUNCTION certification_origin_is_write_once();

-- ------------------------------------------------- the rows already here ---
--
-- Self-limiting, and it matches on what the drive actually wrote rather than
-- on a name: `089`'s rule, where removing the three example invoices matched
-- number, period *and* total and did nothing when the fingerprint was absent.
-- The note below is a verbatim string literal in `drive_the_close.py`, so a
-- row carrying it was written by that script and by nothing else. A database
-- the drive has never run against is untouched and says so.
--
-- This is an UPDATE against `origin`, which the trigger above refuses — so it
-- is done before the trigger exists. The ordering is the point: the backfill
-- is the one write of this column that is a correction rather than a claim.
DO $$
DECLARE marked int;
BEGIN
    ALTER TABLE rate_certification DISABLE TRIGGER certification_origin_write_once;

    UPDATE rate_certification
       SET origin = 'REHEARSAL'
     WHERE origin = 'CONTROLLER'
       AND note LIKE 'The build-up is mine. The square footage and the asset '
                     'funding are estimates%';
    GET DIAGNOSTICS marked = ROW_COUNT;

    ALTER TABLE rate_certification ENABLE TRIGGER certification_origin_write_once;

    IF marked > 0 THEN
        INSERT INTO audit_log (actor, actor_role, action, entity, entity_id,
                               after_state, reason)
        VALUES ('migration 122', 'SYSTEM_ADMIN', 'RATE_CERTIFY_RELABEL',
                'rate_certification', 'drive_the_close.py',
                jsonb_build_object('origin', 'REHEARSAL', 'rows', marked),
                'Written by scripts/drive_the_close.py, which types a '
                'controller''s name into the signature field. No person gave '
                'these signatures, so every paper resting on one now prints '
                'REHEARSAL instead of a name.');
        RAISE NOTICE '122: % certification(s) relabelled REHEARSAL.', marked;
    ELSE
        RAISE NOTICE '122: no drive-made certification on this database.';
    END IF;
END $$;
CREATE OR REPLACE VIEW v_rate_certified AS
-- The most recent signature on this period, whatever became of it. `why_not`
-- describes **that one**, because a chain of EXISTS clauses answers with
-- whichever branch it reaches first and that is not the same as the latest
-- fact: after Tom withdrew a signature the view said "the rate has been
-- recomputed since it was certified", which was true of an older certificate
-- and not what had just happened. A reader deciding whether to go and ask him
-- would have asked the wrong question.
WITH latest AS (
    SELECT DISTINCT ON (period)
           period, cert_id, seal_hash, signature, certified_by, certified_at,
           outstanding, note, withdrawn_at, origin
      FROM rate_certification
     ORDER BY period, certified_at DESC
),
-- Is that latest certificate still standing? Every rate it was put on is
-- still the rate on file — not "a live rate exists carrying the same seal",
-- because recomputing under a different `admin_labour_basis` produces
-- different arithmetic against an identical seal and the signature must not
-- follow it.
standing AS (
    SELECT l.*,
           (l.withdrawn_at IS NULL
            AND EXISTS (SELECT 1 FROM rate_certification_line cl
                         WHERE cl.cert_id = l.cert_id)
            AND NOT EXISTS (SELECT 1 FROM rate_certification_line cl
                              JOIN rate r ON r.rate_id = cl.rate_id
                             WHERE cl.cert_id = l.cert_id
                               AND r.status = 'SUPERSEDED')) AS live
      FROM latest l
)
SELECT p.period,
       COALESCE(c.live, false)                       AS certified,
       CASE WHEN c.live THEN c.cert_id END           AS cert_id,
       CASE WHEN c.live THEN c.signature END         AS signature,
       CASE WHEN c.live THEN c.certified_at END      AS certified_at,
       CASE WHEN c.live THEN a.display_name END      AS certified_by,
       CASE WHEN c.live THEN c.seal_hash END         AS seal_hash,
       CASE WHEN c.live THEN c.outstanding
            ELSE '[]'::jsonb END                     AS outstanding,
       CASE WHEN c.live THEN c.note END              AS note,
       CASE
         WHEN COALESCE(c.live, false) THEN NULL
         WHEN NOT EXISTS (SELECT 1 FROM decision_set ds
                           WHERE ds.period = p.period
                             AND ds.sealed_at IS NOT NULL)
           THEN 'The classifications are not sealed, so no rate exists to '
                || 'certify.'
         WHEN NOT EXISTS (SELECT 1 FROM rate r
                           WHERE r.period = p.period
                             AND r.status <> 'SUPERSEDED')
           THEN 'The set is sealed and no rate has been computed from it yet.'
         WHEN c.withdrawn_at IS NOT NULL
           THEN 'The rate was certified and the signature has been withdrawn.'
         WHEN c.cert_id IS NOT NULL
           THEN 'The rate has been recomputed since it was certified, so the '
                || 'signature is on a build-up that no longer stands. Sign '
                || 'the new one.'
         ELSE 'A rate stands and nobody has put their name to it.'
       END                                           AS why_not,
       -- Appended: a replace cannot insert a column.
       --
       -- What kind of act the signature was. NULL where nothing stands, so a
       -- reader cannot mistake "no certificate" for "a controller's" — the
       -- same three-state `certification_lines` already keeps between *not
       -- read*, *nobody signed* and *signed*.
       CASE WHEN c.live THEN c.origin END            AS origin,
       COALESCE(c.live, false) AND c.origin = 'REHEARSAL' AS rehearsal
  FROM fiscal_period p
  LEFT JOIN standing c ON c.period = p.period
  LEFT JOIN actor a ON a.actor_id = c.certified_by;
