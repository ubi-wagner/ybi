-- 056: a provision is read out of a document, so the record says which one.
--
-- `scripts/load_contract_terms.py` opens with the right rule:
--
--     Every term names the clause it came from. A provision with no citation
--     is somebody's recollection of a contract, which is worth nothing in a
--     dispute and worse than nothing in a file.
--
-- A citation with no document behind it is still somebody's recollection.
-- `award_term.evidence_id` existed from the beginning and was NULL on all
-- thirty-nine rows — the fifth column in this schema that looks usable and
-- is filled by nothing, after `rate.superseded_by`, `space_partition`, the
-- three `evidence` fact columns and `award_budget_line`.
--
-- ── What it cost ────────────────────────────────────────────────────
--
-- Three of the four America Makes awards carry these, recorded as read out
-- of the executed agreements:
--
--     Payment terms        "Net 30 from receipt of a correct invoice"  §26
--     Invoicing frequency  "Monthly, by the fifth business day"        §25
--     Indirect provision   "10% of ODCs only; no indirect on labor"    Att 3
--
-- Those are **ICAM's** clauses. ICAM is the NCDMM Subrecipient Agreement
-- template — fifty-two numbered ALL-CAPS clauses, §6 CONTRACT TYPE, §25
-- INVOICING, §26 PAYMENT — and its own recorded terms are long, specific
-- and right. Hybrid Phase 2 and Last Tactical Mile are a different
-- instrument: ARTICLE-numbered, with no numbered ALL-CAPS clause anywhere
-- in either document. Neither contains a §25, a §26, or the phrase
-- "Net 30". Drive AM carries the same three and its agreement is thirty-six
-- pages of image with no text layer at all.
--
-- The value is wrong in the direction that matters too. `052` transcribed
-- the four budget schedules: Hybrid budgets **no indirect at all** against
-- $449,043 of labour, LTM budgets **$81,772.76**, and ICAM alone is 10% of
-- ODCs only. The restatement's central claim was resting, in two places, on
-- a sentence copied from the one agreement it was true of.
--
-- Nothing here corrects a term. What Hybrid's and LTM's provisions actually
-- say is a question for somebody holding the executed agreements, and Drive
-- AM's cannot be answered by anybody until its pages are read off the
-- images. This gives the record the means to *notice*, which it did not
-- have: a citation, the document it was read out of, and whether the thing
-- it names is in that document.

ALTER TABLE award ADD COLUMN agreement_evidence_id text
  REFERENCES evidence(evidence_id);

COMMENT ON COLUMN award.agreement_evidence_id IS
  'The executed agreement. One fact per award rather than per term, so a '
  'term inherits it and a term read out of something else — a modification, '
  'a proposal — says so by carrying its own.';


-- The four NCDMM agreements are on file and matched by name. Deliberately
-- not a guess: the join is on the filename the document was filed under,
-- and an award whose agreement is not on file keeps NULL, which is the
-- honest answer and the one `v_award_citation_check` reports as unevaluable.
UPDATE award a SET agreement_evidence_id = e.evidence_id
  FROM evidence e
 WHERE e.kind = 'subrecipient-agreement'
   AND a.agreement_evidence_id IS NULL
   AND ((a.award_id = 'AM-HYBRID-P2'   AND e.filename LIKE '%Hybrid-Phase-2%')
     OR (a.award_id = 'AM-DRIVE-AM'    AND e.filename LIKE '%Drive-AM%')
     OR (a.award_id = 'AM-ICAM-DIGENG' AND e.filename LIKE '%SRA-0350%')
     OR (a.award_id = 'AM-LTM-PROJ88'  AND e.filename LIKE '%Last-Tactical-Mile%'));

-- And every term with no document of its own was read out of that agreement.
UPDATE award_term t SET evidence_id = a.agreement_evidence_id
  FROM award a
 WHERE a.award_id = t.award_id
   AND t.evidence_id IS NULL
   AND a.agreement_evidence_id IS NOT NULL;


-- ── Is the clause a term cites in the document it was read from? ────
--
-- Conservative on purpose, because a false accusation against a correct
-- citation is worse than no check: this repository has been bitten by a
-- test that argued with working code. A citation is prose — "§4.3 Total
-- Obligation", "Schedule B, Budget", "Proposal cover table, Duration" — and
-- only some of it is checkable. So one token is extracted, the strongest
-- one, and a citation offering none is reported as UNTESTABLE rather than
-- as either a pass or a failure.
--
-- Five answers, and four of them are not passes:
--
--   FOUND          the document contains what the citation names
--   NOT IN DOCUMENT the document is readable end to end and does not
--   NO TEXT LAYER  pages, and nothing extractable in them. Unevaluable, in
--                  the sense `v_invoice_budget_check` uses: both sides of
--                  the comparison are empty and an empty set matches an
--                  empty set perfectly
--   NO DOCUMENT    the term names no document it was read out of
--   UNTESTABLE     the citation names no section or attachment this can look
--                  for. Not a defect — "Proposal cover table" is a perfectly
--                  good citation for a person and a poor one for a regex
CREATE VIEW v_award_citation_check AS
WITH tok AS (
  SELECT t.award_id,
         t.term_key,
         t.citation,
         t.evidence_id,
         e.filename,
         e.page_count,
         e.extracted_text,
         -- The section number in "§26 Payment", "§4.3 Total Obligation",
         -- "§11.11". Everything after it is prose.
         substring(t.citation from '§\s*([0-9]+(?:\.[0-9]+)*)')   AS section,
         -- "Attachment 3", "Schedule B", "Schedule A".
         substring(t.citation from '(?i)(Attachment|Schedule)\s+([A-Z0-9]+)')
                                                                  AS kind_word,
         substring(t.citation from '(?i)(?:Attachment|Schedule)\s+([A-Z0-9]+)')
                                                                  AS kind_id
    FROM award_term t
    LEFT JOIN evidence e ON e.evidence_id = t.evidence_id
), asked AS (
  SELECT tok.*,
         CASE WHEN section IS NOT NULL
                THEN 'section ' || section
              WHEN kind_word IS NOT NULL
                THEN initcap(kind_word) || ' ' || kind_id
         END AS looked_for,
         -- The document's own numbering style, which is what makes the
         -- check meaningful: a § reference into an ARTICLE-numbered
         -- instrument is not a near miss, it is a reference to another
         -- document.
         CASE WHEN section IS NOT NULL THEN
           extracted_text ~ ('(?m)(^|[^0-9.])' || replace(section, '.', '\.')
                             || '\.?\s+[A-Z]')
              OR extracted_text ~ ('(?i)(section|article|§)\s*'
                             || replace(section, '.', '\.') || '\M')
         WHEN kind_word IS NOT NULL THEN
           extracted_text ~* ('(^|\W)' || kind_word || '\s*' || kind_id || '\M')
         END AS present
    FROM tok
)
SELECT award_id,
       term_key,
       citation,
       evidence_id,
       filename                                        AS document,
       page_count,
       looked_for,
       CASE
         WHEN evidence_id IS NULL                      THEN 'NO DOCUMENT'
         WHEN extracted_text IS NULL                   THEN 'NOT READ'
         WHEN length(btrim(extracted_text)) < 200      THEN 'NO TEXT LAYER'
         WHEN looked_for IS NULL                       THEN 'UNTESTABLE'
         WHEN present                                  THEN 'FOUND'
         ELSE 'NOT IN DOCUMENT'
       END                                             AS state
  FROM asked;

COMMENT ON VIEW v_award_citation_check IS
  'Every recorded provision against the document it was read out of. Only '
  'FOUND is a pass: NO TEXT LAYER and NOT READ are unevaluable rather than '
  'clean, the way NO CLAUSE READ is on v_award_ceiling_check, and '
  'UNTESTABLE says the citation is prose a regex cannot check rather than '
  'that it is wrong.';


-- What an auditor asks, per award, one row.
CREATE VIEW v_award_citations AS
SELECT a.award_id,
       a.sponsor,
       e.filename                                            AS agreement,
       e.page_count,
       -- The fact that explains an award nobody has ever cited a clause of.
       (e.evidence_id IS NOT NULL
        AND e.extracted_text IS NOT NULL
        AND length(btrim(e.extracted_text)) < 200)           AS agreement_is_an_image,
       count(c.term_key)                                     AS terms,
       count(*) FILTER (WHERE c.state = 'FOUND')             AS found,
       count(*) FILTER (WHERE c.state = 'NOT IN DOCUMENT')   AS not_in_document,
       count(*) FILTER (WHERE c.state = 'UNTESTABLE')        AS untestable,
       count(*) FILTER (WHERE c.state IN ('NO DOCUMENT','NOT READ',
                                          'NO TEXT LAYER'))  AS unevaluable
  FROM award a
  LEFT JOIN evidence e ON e.evidence_id = a.agreement_evidence_id
  LEFT JOIN v_award_citation_check c ON c.award_id = a.award_id
 GROUP BY a.award_id, a.sponsor, e.filename, e.page_count, e.evidence_id,
          e.extracted_text;

COMMENT ON VIEW v_award_citations IS
  'One row per award: its agreement, whether that agreement is an image '
  'nobody can read a clause out of, and how its recorded provisions stand '
  'against it.';
