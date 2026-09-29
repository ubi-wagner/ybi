-- 129 · What a document is shaped like, apart from what it says
--
-- Every parser here was written against **one** instance of the document it
-- parses, and three have already been caught by the second one: the asset
-- schedule printing a system number only when it changes ($2.5m dropped);
-- two of the five executed agreements being ARTICLE-numbered, so three
-- provisions on each cited `§25` and `§26`, which appear in neither; and one
-- agreement being thirty-six pages and seventy characters, which is why no
-- clause of it had ever been checked.
--
-- Each of those is a difference in **form** rather than in content, and each
-- was found by a person reading. `app/domain/document_shape.py` reads the
-- form off the bytes at the door, the way `storage.read_text()` already
-- reads the text, so the differences can be compared instead of discovered.
--
-- **Form and content are kept apart.** Next year's general ledger will have
-- wholly different content and had better have the same form; an export
-- somebody saved differently has the same content and a form that breaks the
-- parser. One column for both would hide exactly the case worth catching.
--
-- `reader` is the version of the module that produced the row. A shape read
-- by an older reader is not wrong, it is *older*, and a mixed population is
-- a thing the register has to be able to say rather than average over.

CREATE TABLE IF NOT EXISTS document_shape (
    evidence_id  text PRIMARY KEY REFERENCES evidence(evidence_id)
                   ON DELETE CASCADE,
    form         jsonb NOT NULL,
    content      jsonb NOT NULL DEFAULT '{}'::jsonb,
    reader       text  NOT NULL,
    read_at      timestamptz NOT NULL DEFAULT now(),
    -- A document the reader could not open is a finding, not an absence: it
    -- is the one somebody has to go and look at. The row says so rather than
    -- being missing, because a missing row and an unreadable document are
    -- different facts and only one of them is about the document.
    CONSTRAINT shape_names_its_container
        CHECK (form ? 'container')
);

COMMENT ON TABLE document_shape IS
  'The form and content signature of one document, read from its bytes by '
  'app/domain/document_shape.py. Written at the upload door and by '
  'scripts/read_shapes.py for rows filed before it existed.';


-- Every top-level form attribute of every document, one row each, so the
-- comparison below is a GROUP BY rather than a second derivation in Python.
-- `per_sheet` is left out: it is the form of each sheet *within* a document
-- and belongs to the document, not to the comparison across documents.
CREATE OR REPLACE VIEW v_document_form_attribute AS
SELECT e.kind               AS family,
       s.evidence_id,
       e.filename,
       f.key                AS attribute,
       f.value              AS value
  FROM document_shape s
  JOIN evidence e ON e.evidence_id = s.evidence_id
 CROSS JOIN LATERAL jsonb_each(s.form - 'per_sheet') f;


-- How much the documents in one family differ in form, named rather than
-- scored.
--
-- **A family of one cannot be evaluated**, and says so. That is `029` in a
-- new place: one document agrees with itself perfectly, and reporting
-- UNIFORM over it would be the empty set matching the empty set — it would
-- read as *this parser has been proved against variation* when what is true
-- is *nothing has ever varied here because there has only ever been one*.
--
-- And there is deliberately no variability index. A single number over a
-- handful of documents is a figure nobody can reproduce and nobody can act
-- on; `varies_on` names the attributes and `values` carries what they were,
-- which is the reconciling item's rule applied to a form.
CREATE OR REPLACE VIEW v_document_variability AS
WITH per_attribute AS (
    SELECT family, attribute,
           count(DISTINCT value)                     AS distinct_values,
           jsonb_agg(DISTINCT value)                 AS values
      FROM v_document_form_attribute
     GROUP BY family, attribute
), per_family AS (
    SELECT e.kind                                    AS family,
           count(*)                                  AS instances,
           count(*) FILTER (
             WHERE s.form ->> 'container' = 'unreadable')
                                                     AS unreadable,
           count(*) FILTER (
             WHERE s.form ->> 'text_layer' IN ('none', 'sparse'))
                                                     AS without_usable_text
      FROM evidence e
      JOIN document_shape s ON s.evidence_id = e.evidence_id
     GROUP BY e.kind
)
SELECT f.family,
       f.instances,
       f.unreadable,
       f.without_usable_text,
       COALESCE(array_agg(a.attribute ORDER BY a.attribute)
                FILTER (WHERE a.distinct_values > 1), '{}') AS varies_on,
       COALESCE(jsonb_object_agg(a.attribute, a.values)
                FILTER (WHERE a.distinct_values > 1), '{}'::jsonb) AS values,
       CASE
         WHEN f.instances < 2 THEN 'NO DATA'
         WHEN count(a.attribute) FILTER (WHERE a.distinct_values > 1) > 0
           THEN 'VARIES'
         ELSE 'UNIFORM'
       END AS state,
       CASE
         WHEN f.instances < 2
           THEN 'One document on file, so nothing here has been read twice. '
                'The parser for this family has never met a second instance '
                'and no variation has been ruled out.'
         WHEN count(a.attribute) FILTER (WHERE a.distinct_values > 1) > 0
           THEN 'The documents in this family differ in form. Every '
                'attribute named is one a positional or single-shape parser '
                'can be wrong about.'
         ELSE 'Every document in this family has the same form. The parser '
              'has been met by the same shape each time.'
       END AS note
  FROM per_family f
  LEFT JOIN per_attribute a ON a.family = f.family
 GROUP BY f.family, f.instances, f.unreadable, f.without_usable_text
 ORDER BY f.instances DESC, f.family;


-- The one-line answer, for the panel and the report: how much of the record
-- has been read at all, and how much of what has been read is a family
-- nobody could have proved a parser against.
CREATE OR REPLACE VIEW v_document_shape_coverage AS
SELECT (SELECT count(*) FROM evidence)                        AS documents,
       (SELECT count(*) FROM document_shape)                  AS shaped,
       (SELECT count(*) FROM v_document_variability
         WHERE state = 'VARIES')                              AS families_varying,
       (SELECT count(*) FROM v_document_variability
         WHERE state = 'UNIFORM')                             AS families_uniform,
       (SELECT count(*) FROM v_document_variability
         WHERE state = 'NO DATA')                             AS families_of_one,
       (SELECT COALESCE(sum(unreadable), 0)
          FROM v_document_variability)                        AS unreadable,
       (SELECT COALESCE(sum(without_usable_text), 0)
          FROM v_document_variability)                        AS without_usable_text;
