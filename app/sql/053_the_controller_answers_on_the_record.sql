-- 053: the nineteen answers go on the record, not into a spreadsheet on a
-- laptop.
--
-- `docs/FOR_TOM_TO_VERIFY.md` is nineteen things the record cannot settle on
-- its own, each found by a control rather than by somebody reading, and each
-- needing something the controller knows or can reach.
-- `scripts/verification_sheet.py` turns them into a workbook and a printed
-- worksheet. Until now the answers came back in the workbook and stopped
-- there: an auditor asking "who said the Bacon credit was confirmed, and
-- when" had a file attachment and a memory to go on.
--
-- So the `VERIFICATION` request form takes them back through the machinery
-- that already exists for the other three — preview every cell, accept, file
-- the workbook as evidence under the sender's name — and this is where they
-- land.
--
-- ── Superseded, never edited ─────────────────────────────────────────
--
-- An answer is a judgment with a person's name on it, and judgments here are
-- append-only: reclassifying leaves the old `decision_line` in place, an
-- audit row cannot be deleted, and a certification that goes stale is
-- *marked* stale rather than removed. So a second answer to the same item
-- supersedes the first and both stay.
--
-- That matters more here than it looks. Several of these items are expected
-- to change answer: 1.3 and 1.4 are almost certainly a 2026 export and will
-- be confirmed as timing once the 31 December register arrives, and item 0
-- is confirmed *except* that the QuickBooks entry has not been reposted —
-- when it is, the reconciling item has to come off with it. A record that
-- kept only the latest answer would lose the sequence, and the sequence is
-- the thing an auditor is reconstructing.
--
-- ── A status that claims a settlement carries words ──────────────────
--
-- The same rule as `DELIVERED` with no delivery date, and for the same
-- reason: a status somebody picked from a dropdown is not a thing that
-- happened. CONFIRMED and CORRECTED both assert that somebody went and
-- looked, so both have to say what they found. STILL CHECKING and SOMEBODY
-- ELSE HAS TO ANSWER are honest with nothing attached — they are reports of
-- not knowing yet, and demanding prose for one would just produce "still
-- checking" twice.

CREATE TABLE verification_answer (
  answer_id     bigserial PRIMARY KEY,
  period        text NOT NULL REFERENCES fiscal_period,
  -- The reference on the item, e.g. '1.3'. Not a foreign key: the list of
  -- items lives in domain/verification_items.py, because it is prose about
  -- documents rather than rows anything joins to, and a table of them would
  -- be a second copy of a list that already has three readers.
  ref           text NOT NULL,
  status        text NOT NULL,
  answer        text NOT NULL DEFAULT '',
  -- Who settled it. Usually whoever sent the workbook back, but a row may
  -- name somebody else — an answer from the person who actually knows is
  -- worth more than one from whoever had the file.
  answered_by   text NOT NULL,
  -- The account that accepted it into the record, which is a different act
  -- from answering and may be a different person.
  accepted_by   text NOT NULL,
  accepted_at   timestamptz NOT NULL DEFAULT now(),
  -- The workbook it came out of, so "where did this answer come from"
  -- answers with a file under somebody's name.
  evidence_id   text REFERENCES evidence,
  -- Superseded, and *when*. There is deliberately no `superseded_by`.
  --
  -- The first draft had one, and it produced the failure that proved it
  -- pointless: the insert of the successor collided with
  -- `one_live_answer_per_item` because the predecessor could not be marked
  -- superseded until the successor existed to be named, and the successor
  -- could not be inserted while the predecessor was live. A column that
  -- makes its own invariant unsatisfiable is a column doing no work.
  --
  -- It was doing no work anyway. `answer_id` is a bigserial, so the sequence
  -- for an item is `ORDER BY answer_id` within (period, ref) and the
  -- successor of any row is the next one along. `rate.superseded_by` was
  -- exactly this — a second register of a fact the row order already
  -- carries — and it sat dead for the whole engagement until `050` dropped
  -- it. Four instances of that shape have been found in this schema. This
  -- would have been the fifth.
  superseded_at timestamptz,

  CONSTRAINT verification_status_known
    CHECK (status IN ('CONFIRMED — the record is right',
                      'CORRECTED — I have changed something',
                      'STILL CHECKING',
                      'SOMEBODY ELSE HAS TO ANSWER',
                      'NOT APPLICABLE')),
  CONSTRAINT verification_needs_an_answerer
    CHECK (length(trim(answered_by)) > 1),
  -- A settlement says what was found. A report of not knowing yet need not.
  CONSTRAINT settled_says_what_was_found
    CHECK (status NOT IN ('CONFIRMED — the record is right',
                          'CORRECTED — I have changed something')
           OR length(trim(answer)) >= 10)
);

-- One live answer per item per period. The partial index is the invariant:
-- it holds when a handler is wrong, which is the whole reason it is here
-- rather than in Python.
CREATE UNIQUE INDEX one_live_answer_per_item
    ON verification_answer (period, ref) WHERE superseded_at IS NULL;

CREATE INDEX ON verification_answer (period, ref);

COMMENT ON TABLE verification_answer IS
  'What the controller said about each of the items the record cannot settle '
  'on its own, under the name of whoever answered and with the workbook it '
  'came out of. Append-only: a second answer supersedes the first and both '
  'stay, because several of these are expected to change answer and the '
  'sequence is what an auditor is reconstructing.';


CREATE VIEW v_verification_status AS
SELECT a.period,
       a.ref,
       a.status,
       a.answer,
       a.answered_by,
       a.accepted_by,
       a.accepted_at,
       a.evidence_id,
       e.filename                                       AS evidence_filename,
       -- How many times this item has been answered, including this one. A
       -- ref answered three times is one somebody has been round twice, and
       -- that is worth seeing without opening the history.
       (SELECT count(*) FROM verification_answer x
         WHERE x.period = a.period AND x.ref = a.ref)    AS answers,
       a.status IN ('CONFIRMED — the record is right',
                    'CORRECTED — I have changed something')
                                                         AS settled
  FROM verification_answer a
  LEFT JOIN evidence e ON e.evidence_id = a.evidence_id
 WHERE a.superseded_at IS NULL;

COMMENT ON VIEW v_verification_status IS
  'The live answer for each item. An item with no row here is unanswered, '
  'which is a different fact from STILL CHECKING and has to stay different: '
  'one means nobody has looked and the other means somebody has and cannot '
  'say yet.';
