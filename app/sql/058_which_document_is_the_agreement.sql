-- 058: the award says which document its agreement is, in one place.
--
-- `056` linked each award to its executed agreement by matching the filename
-- it was filed under. That works against a loaded database and does nothing
-- on a fresh one: migrations run at startup, before a single document has
-- been uploaded, so the UPDATE matched nothing and `award_term.evidence_id`
-- stayed NULL through the whole seed. Every citation would then report
-- `NO DOCUMENT` — which is not a pass, so nothing would have been *wrong*,
-- but the check that found six provisions citing clauses that are not in
-- their agreements would have been silent on a fresh deployment.
--
-- The ordering is not incidental either: `scripts/seed.sh` loads the
-- contract provisions at step five and the documents at step six, because
-- the provisions hang off the awards and the awards come from the invoice
-- load. The terms genuinely are recorded before the paper arrives.
--
-- So the knowledge lives on the award row and the matching happens whenever
-- a document turns up. Which fragment of a filename identifies an
-- agreement is a fact somebody knows and nothing can derive — AM-LTM-PROJ88
-- is "Last-Tactical-Mile" and AM-ICAM-DIGENG is "SRA-0350" — and a fact
-- like that belongs in one place. Putting it in a script as well as here is
-- the shape that produced two coverage figures six-fold apart.

ALTER TABLE award ADD COLUMN agreement_name text;

COMMENT ON COLUMN award.agreement_name IS
  'The fragment of a filename that identifies this award''s executed '
  'agreement. The one fact nothing can derive — AM-ICAM-DIGENG is SRA-0350 '
  '— so it is recorded once here and scripts/link_agreements.py does the '
  'matching, rather than a second copy of it living in a script.';

UPDATE award SET agreement_name = v.fragment
  FROM (VALUES ('AM-HYBRID-P2',   'Hybrid-Phase-2'),
               ('AM-DRIVE-AM',    'Drive-AM'),
               ('AM-ICAM-DIGENG', 'SRA-0350'),
               ('AM-LTM-PROJ88',  'Last-Tactical-Mile'))
       AS v(award_id, fragment)
 WHERE award.award_id = v.award_id;

-- Idempotent, and harmless on an empty database: on a loaded one it links
-- what `056` linked, and on a fresh one it links nothing and the script does
-- it after the documents are filed.
UPDATE award a SET agreement_evidence_id = e.evidence_id
  FROM evidence e
 WHERE a.agreement_evidence_id IS NULL
   AND a.agreement_name IS NOT NULL
   AND e.kind = 'subrecipient-agreement'
   AND e.filename LIKE '%' || a.agreement_name || '%';
