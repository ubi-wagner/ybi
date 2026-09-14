-- 047: what we have asked YBI for, and whether it came back.
--
-- Three things are missing from the record and none can be inferred: which
-- assets federal money paid for, who uses which square foot, and the email
-- address of thirty-seven people who have to sign their own effort. Each is
-- somebody else's filing cabinet and each has a lead time in weeks.
--
-- Until now the asking was an email and the chasing was a memory. This is the
-- register: what was asked, of whom, when, what came back, and what was done
-- with it. It exists for the same reason the audit log does — a request that
-- nobody can show was made is a request that was not made.
--
-- The reply itself is not staged into a table. The workbook is filed as
-- evidence like any other document and the preview re-reads it from the
-- bytes, so there is one copy of the answer and it is the file the person
-- actually sent. A staging table would be a second copy that can disagree
-- with the first, which is the thing this system keeps refusing to build.

CREATE TYPE request_state AS ENUM ('ISSUED', 'RECEIVED', 'ACCEPTED', 'WITHDRAWN');

CREATE TABLE information_request (
  request_id      bigserial PRIMARY KEY,
  form            text NOT NULL,              -- ASSET_REGISTER, SPACE_INVENTORY, ...
  form_version    integer NOT NULL,
  period          text NOT NULL REFERENCES fiscal_period,
  state           request_state NOT NULL DEFAULT 'ISSUED',

  issued_at       timestamptz NOT NULL DEFAULT now(),
  issued_by       text NOT NULL DEFAULT '',
  issued_by_id    uuid REFERENCES actor,
  -- Who it went to. Free text because it is usually a person outside the
  -- system — the facilities manager, whoever keeps the asset register — and
  -- inventing accounts for them to answer a spreadsheet would be worse.
  sent_to         text NOT NULL DEFAULT '',
  note            text NOT NULL DEFAULT '',

  -- The reply.
  reply_evidence_id text REFERENCES evidence,
  received_at     timestamptz,
  received_from   text NOT NULL DEFAULT '',
  accepted_at     timestamptz,
  accepted_by     text NOT NULL DEFAULT '',
  rows_accepted   integer,
  rows_held_back  integer,

  -- Why it was dropped, where it was.
  withdrawn_reason text NOT NULL DEFAULT '',

  -- A state that claims an event carries its evidence, exactly as a
  -- DELIVERED milestone carries a delivery date. A request marked RECEIVED
  -- with no file attached is a status somebody set, not a thing that
  -- happened.
  CONSTRAINT received_carries_a_reply
    CHECK (state NOT IN ('RECEIVED', 'ACCEPTED')
           OR (reply_evidence_id IS NOT NULL AND received_at IS NOT NULL)),
  CONSTRAINT accepted_says_what_it_took
    CHECK (state <> 'ACCEPTED'
           OR (accepted_at IS NOT NULL AND rows_accepted IS NOT NULL)),
  CONSTRAINT withdrawn_says_why
    CHECK (state <> 'WITHDRAWN' OR length(btrim(withdrawn_reason)) > 0)
);
CREATE INDEX ON information_request (period, state);
CREATE INDEX ON information_request (form, state);

COMMENT ON TABLE information_request IS
  'What has been asked of somebody outside the system, and whether it came '
  'back. The reply is filed as evidence rather than staged into a table: one '
  'copy of the answer, and it is the file the person sent.';


-- ── What is outstanding, and how long it has been ─────────────────────

CREATE VIEW v_information_request AS
SELECT r.request_id, r.form, r.form_version, r.period, r.state::text AS state,
       r.issued_at, r.issued_by, r.sent_to, r.note,
       r.reply_evidence_id, r.received_at, r.received_from,
       r.accepted_at, r.accepted_by, r.rows_accepted, r.rows_held_back,
       r.withdrawn_reason,
       e.filename       AS reply_filename,
       -- Days outstanding, which is the number that gets somebody to pick up
       -- the phone. Frozen at the reply for anything that came back, so a
       -- request answered in three days does not keep ageing on the screen.
       CASE WHEN r.received_at IS NOT NULL
            THEN EXTRACT(day FROM r.received_at - r.issued_at)::int
            WHEN r.state = 'WITHDRAWN' THEN NULL
            ELSE EXTRACT(day FROM now() - r.issued_at)::int
       END                                               AS days,
       (r.state = 'ISSUED'
        AND now() - r.issued_at > interval '14 days')     AS overdue
  FROM information_request r
  LEFT JOIN evidence e ON e.evidence_id = r.reply_evidence_id;

COMMENT ON VIEW v_information_request IS
  'The chase list. days stops counting when the reply lands, so a request '
  'answered quickly does not keep ageing beside one that was never answered.';
