-- Tom's signature on the rate, and what it covers.
--
-- Everything up to the rate is free-order: fill in, classify, upload, seal,
-- in whatever order the work arrives in. **Nothing downstream is blocked** —
-- an invoice can be regenerated and a workbook produced at any time, because
-- testing and evaluating the system is ordinary work and a machine that
-- refused it would be one people route around. What changes is whether the
-- paper that comes out says it is certified.
--
-- So there is exactly one fact every output reads, and this is where it lives.
--
-- **It is not `rate.status`.** That column is the *sponsor* conversation —
-- PROPOSED means YBI has put the rate to NCDMM and they have not answered,
-- ACCEPTED means they have. Certification is the other axis entirely: the
-- controller asserting the rate is final and his. Overloading one word with
-- both would leave a reviewer unable to tell a position the organisation has
-- taken from a signature on its own arithmetic, which is the mistake `062`
-- records making with `PROPOSED` and refusing to repeat.
--
-- **It certifies a build-up, and names the rate rows it covers.** All four
-- rates come out of one computation, so certifying FRINGE and not OVERHEAD is
-- not a thing anybody means — but naming only the *seal* is not enough, and
-- that was found by driving it rather than by reasoning about it. Unseal,
-- re-seal the identical judgments, recompute: the seal hash is a function of
-- the judgments so it comes back the same, and the signature **revived on its
-- own**. Worse, `POST /rates/compute` takes `admin_labour`, so the same seal
-- can produce 34.82% or 43.99% — the revived signature would have been on a
-- rate Tom never saw.
--
-- So the certificate names the rate rows, and recomputing supersedes them,
-- which kills it. That is this system's own model of change used for what it
-- is for: nothing is edited, a later act supersedes an earlier one, and the
-- certificate dies with the thing it was about.
--
-- **It is reversible and the withdrawal is on the record.** The whole point of
-- a signature is that it can be withdrawn by the person who made it and that
-- the withdrawal is visible — a lock nobody can open is a lock somebody works
-- around.
--
-- **And it records what was open when it was made.** Tom may certify a rate
-- with the square footage still missing; that is his judgment to make and
-- refusing it would stop him signing for as long as a document somebody else
-- holds is outstanding. What must not happen is the caveat getting lost, so
-- the certificate carries the walk's unfinished steps as they stood at the
-- moment of signing, and every document rendered under it can say so.

CREATE TABLE rate_certification (
    cert_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    period         text NOT NULL REFERENCES fiscal_period(period),
    -- The build-up being signed: one seal, one computation, four rates.
    seal_hash      text NOT NULL,
    signature      text NOT NULL,
    certified_by   uuid NOT NULL REFERENCES actor(actor_id),
    certified_at   timestamptz NOT NULL DEFAULT now(),
    -- The walk's unfinished steps, as they stood. A snapshot on purpose: it
    -- is what the signature covers, and re-deriving it later would answer a
    -- different question from the one Tom answered.
    outstanding    jsonb NOT NULL DEFAULT '[]'::jsonb,
    note           text NOT NULL DEFAULT '',
    withdrawn_at   timestamptz,
    withdrawn_by   uuid REFERENCES actor(actor_id),
    withdrawn_reason text,

    -- A signature is a name somebody typed, not a checkbox.
    CONSTRAINT certification_is_signed
        CHECK (length(btrim(signature)) >= 2),
    -- Withdrawing says why, in enough words to act on. A lock reopened with
    -- no reason is the next person's puzzle, which is the rule
    -- `contractor_identity` and `record_access` already follow.
    CONSTRAINT withdrawal_names_its_reason
        CHECK ((withdrawn_at IS NULL) = (withdrawn_by IS NULL)
           AND (withdrawn_at IS NULL)
             = (withdrawn_reason IS NULL OR length(btrim(withdrawn_reason)) = 0)
           AND (withdrawn_at IS NULL
                OR length(btrim(withdrawn_reason)) >= 20))
);

-- Exactly which rates the signature is on. A certificate with no lines is a
-- signature on nothing, which a deferred trigger refuses below — the same
-- shape as `reconciling_item` refusing one whose lines do not add up.
CREATE TABLE rate_certification_line (
    cert_id  uuid NOT NULL REFERENCES rate_certification(cert_id)
                 ON DELETE CASCADE,
    rate_id  uuid NOT NULL REFERENCES rate(rate_id),
    PRIMARY KEY (cert_id, rate_id)
);

CREATE INDEX rate_certification_line_rate ON rate_certification_line (rate_id);

COMMENT ON TABLE rate_certification_line IS
'The rate rows one signature covers. Recomputing supersedes them, which is '
'what stops a withdrawn-and-reseal cycle silently reviving a signature.';


CREATE INDEX rate_certification_period ON rate_certification (period);

COMMENT ON TABLE rate_certification IS
'The controller''s signature on a rate build-up, naming the seal it was '
'computed from. Not rate.status, which is the sponsor conversation.';


-- The signature has to be on a rate that exists, from a set that is sealed.
--
-- `rate_requires_seal` refuses a rate whose seal does not match a sealed set.
-- This is the same guarantee one step further along: a certificate naming a
-- seal that is not the sealed set, or one with no rate under it, is a
-- signature on nothing. In the schema rather than the handler, because it has
-- to hold when application code is wrong.
CREATE FUNCTION certification_requires_a_sealed_rate() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM decision_set ds
                    WHERE ds.period = NEW.period
                      AND ds.seal_hash = NEW.seal_hash
                      AND ds.sealed_at IS NOT NULL) THEN
        RAISE EXCEPTION 'certification_requires_a_sealed_rate: no sealed '
                        'decision set for this period carries that seal';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM rate r
                    WHERE r.period = NEW.period
                      AND r.seal_hash = NEW.seal_hash
                      AND r.status <> 'SUPERSEDED') THEN
        RAISE EXCEPTION 'certification_requires_a_sealed_rate: no live rate '
                        'has been computed from that seal';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER certification_requires_a_sealed_rate
    BEFORE INSERT ON rate_certification
    FOR EACH ROW EXECUTE FUNCTION certification_requires_a_sealed_rate();


-- A signature covers something, or it is not a signature.
--
-- Deferred to the end of the transaction, because the certificate and its
-- lines are written in one turn and the parent necessarily lands first. Same
-- shape as the trigger that refuses a `reconciling_item` whose lines do not
-- add to the amount claimed — which is what separates a reconciling item from
-- a plug, and here separates a signature from a gesture.
CREATE FUNCTION certification_covers_a_rate() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM rate_certification_line cl
                    WHERE cl.cert_id = NEW.cert_id) THEN
        RAISE EXCEPTION 'certification_covers_a_rate: a certificate names the '
                        'rate rows it is a signature on, and this one names '
                        'none';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER certification_covers_a_rate
    AFTER INSERT ON rate_certification
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION certification_covers_a_rate();


-- Is the rate certified, right now, and if not then why not.
--
-- One row per period and **always a row**, because "no certificate" and "no
-- period" are different facts and a screen that got nothing back would print
-- the same thing for both. `why_not` is the sentence the footer uses, so the
-- reason lives in one place rather than being composed on four screens.
--
-- A certificate does not survive its seal. Unsealing supersedes every rate,
-- and a signature on a superseded build-up is a signature on a number nobody
-- can reproduce — so `certified` is derived from the seal still being the
-- sealed one and a live rate still standing under it, rather than from the
-- row existing. That is the `rate.superseded_by` lesson: a column that says
-- "live" and is never updated is worse than no column.
CREATE VIEW v_rate_certified AS
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
           outstanding, note, withdrawn_at
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
       END                                           AS why_not
  FROM fiscal_period p
  LEFT JOIN standing c ON c.period = p.period
  LEFT JOIN actor a ON a.actor_id = c.certified_by;

COMMENT ON VIEW v_rate_certified IS
'Whether the period''s rate carries the controller''s signature right now, and '
'the sentence to print when it does not. Always one row per period. Derived '
'from the seal still standing rather than from the certificate existing.';


-- One live signature per period. A second is not a second opinion, it is two
-- answers to "is this signed".
--
-- A partial unique index cannot express this, and the first draft tried:
-- `UNIQUE (period, seal_hash) WHERE withdrawn_at IS NULL` refused a perfectly
-- good signature on a **recomputed** build-up, because the judgments were
-- unchanged so the seal hash came back the same and the dead certificate was
-- not withdrawn — it was superseded, which is a different fact. Liveness
-- depends on whether the covered rates still stand, which lives in another
-- table, so this is a trigger reading the one definition rather than a second
-- copy of it. Defined after the view for that reason.
--
-- A `superseded_at` column on the certificate would make the index work, and
-- would be derived state stored beside the thing it is derived from — which
-- is exactly what `rate.superseded_by` turned out to be.
CREATE FUNCTION one_live_certification_per_period() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM v_rate_certified
                WHERE period = NEW.period AND certified) THEN
        RAISE EXCEPTION 'one_live_certification_per_period: this period''s '
                        'rate already carries a live signature';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER one_live_certification_per_period
    BEFORE INSERT ON rate_certification
    FOR EACH ROW EXECUTE FUNCTION one_live_certification_per_period();


-- And the walk gains the step.
--
-- `081` is applied, so it is not edited: **never edit a migration that has
-- already run in production.** The body below is *lifted* from the definition
-- in force rather than retyped — `070` records what retyping costs, which was
-- rewriting a view's scope from memory and silently changing how every line
-- was categorised.
--
-- Certifying is step 9, so the two after it move up. The nav marks follow,
-- and `test_the_nav_marks_are_the_walk_s_step_numbers` derives both sides so
-- neither can be renumbered without the other.
DROP VIEW v_audit_walk;

CREATE VIEW v_audit_walk AS
WITH
period AS (SELECT period FROM fiscal_period),
ledger AS (
    SELECT p.period,
           (SELECT count(*) FROM ledger_line l WHERE l.period = p.period) AS lines
      FROM period p
),
recon AS (
    SELECT p.period,
           count(r.*)                             AS points,
           count(r.*) FILTER (WHERE r.ties)       AS tying,
           count(r.*) FILTER (WHERE r.state = 'NO DATA') AS blind
      FROM period p
      LEFT JOIN v_statement_reconciliation r ON r.period = p.period
     GROUP BY p.period
),
cover AS (
    SELECT p.period, c.groups_total, c.groups_decided,
           c.scope_dollars, c.classified, c.unclassified, c.pct_dollars_covered
      FROM period p
      LEFT JOIN v_classification_coverage c ON c.period = p.period
),
part AS (
    SELECT p.period,
           max(pc.state) FILTER (WHERE pc.partition = 'SPACE')  AS space_state,
           max(pc.needs) FILTER (WHERE pc.partition = 'SPACE')  AS space_needs,
           max(pc.state) FILTER (WHERE pc.partition = 'ASSETS') AS asset_state,
           max(pc.needs) FILTER (WHERE pc.partition = 'ASSETS') AS asset_needs
      FROM period p
      LEFT JOIN v_partition_coverage pc ON pc.period = p.period
     GROUP BY p.period
),
cited AS (
    -- A judgment that names the paper it rests on. Attaching is not citing:
    -- `decision_verified_check` counts `decision_evidence`, and that is the
    -- difference between *this paper is about that money* and *this paper is
    -- why I judged it the way I did*.
    -- The period comes through `decision_set`, not off the decision.
    -- `decision.scope` is the **group key** — `account=…|payee=…` — and a
    -- first draft grouped by it, which produced one row per group and made
    -- this step report "nothing has been judged yet" over 757 judgments.
    -- That is the name-written-from-memory defect this file lists by name,
    -- committed by somebody who had just read the list.
    -- Scoped to the judgments the worklist's NEEDS_EVIDENCE scopes to —
    -- federally chargeable, ALLOWABLE or PENDING — because both appear on
    -- this one page and a first draft counted all 757 live judgments beside
    -- a worklist row saying 363. Two true figures about "judgments with no
    -- document", at the same moment, which a reader has to reconcile in
    -- their head. That is 13.0% and 2.2% in its presentation form.
    SELECT ds.period,
           count(DISTINCT d.decision_id)
             FILTER (WHERE d.federal IN ('ALLOWABLE', 'PENDING'))  AS live,
           count(DISTINCT de.decision_id)
             FILTER (WHERE d.federal IN ('ALLOWABLE', 'PENDING'))  AS with_citation,
           count(DISTINCT d.decision_id)                           AS all_live
      FROM decision d
      JOIN decision_set ds ON ds.set_id = d.set_id
      LEFT JOIN decision_evidence de ON de.decision_id = d.decision_id
     WHERE d.reversed_at IS NULL
     GROUP BY ds.period
),
sealed AS (
    SELECT p.period,
           bool_or(ds.sealed_at IS NOT NULL)      AS is_sealed,
           max(ds.sealed_at)                      AS at,
           max(left(ds.seal_hash, 12))            AS hash
      FROM period p
      LEFT JOIN decision_set ds ON ds.period = p.period
     GROUP BY p.period
),
rated AS (
    SELECT p.period,
           count(r.*) FILTER (WHERE r.status <> 'SUPERSEDED')  AS live,
           max(r.rate) FILTER (WHERE r.kind = 'INDIRECT_COMBINED'
                                 AND r.status <> 'SUPERSEDED') AS combined,
           max(r.admin_labour_basis) FILTER (WHERE r.status <> 'SUPERSEDED')
                                                               AS basis
      FROM period p
      LEFT JOIN rate r ON r.period = p.period
     GROUP BY p.period
),
restated AS (
    SELECT p.period,
           count(rs.*) FILTER (WHERE rs.status <> 'SUPERSEDED') AS standing
      FROM period p
      LEFT JOIN restatement rs ON rs.period = p.period
     GROUP BY p.period
)
SELECT * FROM (
    SELECT l.period, 1 AS seq, 'The books are in' AS step,
           'LEDGER' AS key,
           'The QuickBooks exports, as received' AS what,
           CASE WHEN l.lines = 0 THEN 'NO DATA' ELSE 'DONE' END AS state,
           CASE WHEN l.lines = 0
                THEN 'No ledger has been loaded for this period.'
                -- Grouped in the database because this sentence is built
                -- here: `api.js::money()` and `count()` are the one formatter
                -- for a figure the screen renders, and they cannot reach
                -- inside a string the view composed. 15500 read as a part
                -- number rather than a count.
                ELSE to_char(l.lines, 'FM999,999,999')
                     || ' general-ledger lines on file.' END AS detail,
           '/books/import' AS goes_to
      FROM ledger l

    UNION ALL
    SELECT r.period, 2, 'The books agree with themselves',
           'RECONCILE',
           'Ledger, profit and loss, balance sheet, payroll register',
           CASE WHEN r.points = 0 THEN 'NO DATA'
                WHEN r.blind > 0 THEN 'NO DATA'
                WHEN r.tying = r.points THEN 'DONE'
                ELSE 'OPEN' END,
           CASE WHEN r.points = 0
                THEN 'No control has been evaluated.'
                WHEN r.blind > 0
                THEN r.blind || ' of ' || r.points || ' points cannot be '
                     || 'evaluated, which is not the same as tying.'
                ELSE r.tying || ' of ' || r.points || ' cross-reference '
                     || 'points tie. A rate is refused while any is open.'
           END,
           '/books'
      FROM recon r

    UNION ALL
    SELECT c.period, 3, 'Every cost judged',
           'CLASSIFY',
           'The profit and loss, less income, into 2 CFR 200 pools',
           CASE WHEN c.groups_total IS NULL OR c.groups_total = 0 THEN 'NO DATA'
                WHEN c.unclassified = 0 THEN 'DONE' ELSE 'OPEN' END,
           CASE WHEN c.groups_total IS NULL OR c.groups_total = 0
                THEN 'There is no cost to classify yet.'
                ELSE to_char(c.groups_decided, 'FM999,999') || ' of '
                     || to_char(c.groups_total, 'FM999,999')
                     || ' groups, ' || c.pct_dollars_covered || '% of dollars.'
           END,
           '/classify'
      FROM cover c

    UNION ALL
    SELECT pt.period, 4, 'Every square foot accounted for',
           'SPACE',
           'Each building, into tenant, programme and vacant space',
           COALESCE(pt.space_state, 'NO DATA'),
           CASE WHEN COALESCE(pt.space_state, 'NO DATA') = 'NO DATA'
                THEN 'Needs ' || COALESCE(pt.space_needs, 'the square footage')
                     || '. Until it lands the 200.465 carve-out cannot be '
                     || 'computed at all, and every dollar of tenant and '
                     || 'vacant occupancy cost sits in the federal pool.'
                ELSE 'The space accounts for itself.' END,
           '/classify/space'
      FROM part pt

    UNION ALL
    SELECT pt.period, 5, 'Every asset''s funding source',
           'ASSETS',
           'The fixed-asset register, into funding sources',
           COALESCE(pt.asset_state, 'NO DATA'),
           CASE WHEN COALESCE(pt.asset_state, 'NO DATA') = 'NO DATA'
                THEN 'Needs ' || COALESCE(pt.asset_needs, 'the asset register')
                     || '. 200.436(b) makes depreciation on a federally '
                     || 'funded asset unallowable and the schedule has no '
                     || 'such column, which 200.313(d)(1) requires.'
                ELSE 'Every asset names where its money came from.' END,
           '/classify/assets'
      FROM part pt

    UNION ALL
    SELECT c.period, 6, 'The paper behind the judgments',
           'EVIDENCE',
           'A judgment that cites the document it rests on',
           CASE WHEN COALESCE(ct.all_live, 0) = 0 THEN 'WAITING'
                WHEN COALESCE(ct.live, 0) = 0 THEN 'DONE'
                WHEN ct.with_citation = ct.live THEN 'DONE' ELSE 'OPEN' END,
           CASE WHEN COALESCE(ct.all_live, 0) = 0
                THEN 'Nothing has been judged yet, so there is nothing to cite.'
                WHEN COALESCE(ct.live, 0) = 0
                THEN 'No judgment is federally chargeable, so none needs a '
                     || 'citation for 2 CFR 200.'
                ELSE to_char(COALESCE(ct.with_citation, 0), 'FM999,999')
                     || ' of ' || to_char(ct.live, 'FM999,999')
                     || ' federally chargeable judgments cite a document, of '
                     || to_char(ct.all_live, 'FM999,999') || ' live. '
                     || 'Attaching is not citing: a citation is why the '
                     || 'judgment was made, and it is what VERIFIED requires.'
           END,
           '/evidence'
      FROM cover c LEFT JOIN cited ct ON ct.period = c.period

    UNION ALL
    SELECT s.period, 7, 'The classifications sealed',
           'SEAL',
           'Hashed across every judgment, before any rate exists',
           CASE WHEN s.is_sealed THEN 'DONE'
                WHEN COALESCE(c.unclassified, 1) <> 0 THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN s.is_sealed
                THEN 'Sealed ' || to_char(s.at, 'DD Mon YYYY') || ' · '
                     || s.hash || '…'
                WHEN COALESCE(c.unclassified, 1) <> 0
                THEN 'Cost is still outstanding. Sealing an incomplete set '
                     || 'is allowed and makes the rate read high, which is '
                     || 'the honest direction to err.'
                ELSE 'Every group is judged. Sealing is the assertion that '
                     || 'the rate was not reverse-engineered, and it is '
                     || 'yours to make.'
           END,
           '/review/rate'
      FROM sealed s LEFT JOIN cover c ON c.period = s.period

    UNION ALL
    SELECT rt.period, 8, 'The rate computed',
           'RATE',
           'A pool over a base, carrying the seal',
           CASE WHEN COALESCE(rt.live, 0) > 0 THEN 'DONE'
                WHEN NOT COALESCE(s.is_sealed, false) THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN COALESCE(rt.live, 0) > 0
                THEN 'Indirect, combined: '
                     || round(rt.combined * 100, 2) || '% on the '
                     || rt.basis || ' basis.'
                WHEN NOT COALESCE(s.is_sealed, false)
                THEN 'No rate can exist until the set is sealed — the '
                     || 'database refuses one whose seal does not match.'
                ELSE 'The set is sealed. Computing is arithmetic from here.'
           END,
           '/review/rate'
      FROM rated rt LEFT JOIN sealed s ON s.period = rt.period

    UNION ALL
    SELECT rt.period, 9, 'The rate certified',
           'CERTIFY',
           'The controller''s signature on the build-up',
           CASE WHEN cert.certified THEN 'DONE'
                WHEN COALESCE(rt.live, 0) = 0 THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN cert.certified
                THEN 'Signed by ' || cert.certified_by || ' on '
                     || to_char(cert.certified_at, 'DD Mon YYYY') || '. '
                     || 'Anything issued from here says so.'
                ELSE COALESCE(cert.why_not, 'Nobody has signed the rate.')
                     || ' Nothing is blocked by this — an invoice or a '
                     || 'workbook produced now simply carries NOT CERTIFIED.'
           END,
           '/review/rate'
      FROM rated rt
      LEFT JOIN v_rate_certified cert ON cert.period = rt.period

    UNION ALL
    SELECT rs.period, 10, 'The position on each invoice',
           'RESTATE',
           'What was billed, against what the rate supports',
           CASE WHEN COALESCE(rs.standing, 0) > 0 THEN 'DONE'
                WHEN COALESCE(rt.live, 0) = 0 THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN COALESCE(rs.standing, 0) > 0
                THEN rs.standing || ' restatement(s) standing as a claim. '
                     || 'Everything is PROPOSED until a sponsor says '
                     || 'otherwise in writing.'
                WHEN COALESCE(rt.live, 0) = 0
                THEN 'Needs a rate to measure against.'
                ELSE 'Nothing has been put to a sponsor yet.'
           END,
           '/restate'
      FROM restated rs LEFT JOIN rated rt ON rt.period = rs.period

    UNION ALL
    SELECT p.period, 11, 'The papers that leave the building',
           'REPORT',
           'The auditor''s report, Form 990, the workbooks',
           'DONE',
           'Read from the rows they were recorded in. Each states what is '
           || 'unfinished above its figures, and the workbooks repeat it on '
           || 'the first sheet because a workbook travels.',
           '/reports'
      FROM period p
) w
ORDER BY period, seq;

COMMENT ON VIEW v_audit_walk IS
'The 2025 audit as the one ordered journey it is, eleven steps, each reading '
'the view that already owns its figure. WAITING is a step whose predecessor is '
'not done — printing it as OPEN would offer work the system would refuse.';
