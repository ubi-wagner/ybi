-- =====================================================================
-- Materiality, and the exceptions schedule
--
-- A defensible file is not one with no exceptions. It is one where every
-- exception is stated, reasoned, and findable without reading the log.
--
-- Three things here.
--
-- 1. A COVERAGE GATE THAT BENDS. Submitting a timesheet below 90% of the
--    period was refused outright. Somebody on medical leave, somebody who
--    left in August, somebody whose calendar is genuinely gone — none of them
--    could submit honestly, so the pressure was to pad hours until the number
--    went green. A gate that cannot be passed honestly gets passed
--    dishonestly. It bends now, with a reason, and the reason is the evidence.
--
-- 2. A MATERIALITY POLICY. A $600 group and a $600,000 group were held to the
--    same standard, which means either the small ones were over-worked or the
--    large ones were under-worked and nothing said which. A written policy —
--    what standard of evidence each size of cost requires — is how effort is
--    defensibly proportioned. Stated once, applied consistently, reported
--    against.
--
-- 3. AN EXCEPTIONS SCHEDULE. The first thing a reviewer asks for. Every soft
--    limit passed, every judgment below the standard its size requires, every
--    unseal, every undo, every sub-coverage submission — in one place, with
--    who and why. Making somebody reconstruct that from a five-thousand-row
--    activity feed is how a clean file reads as evasive.
-- =====================================================================

-- ── 1. The gate that bends ───────────────────────────────────────────

ALTER TABLE timesheet_submission
  ADD COLUMN below_coverage_reason text,
  ADD COLUMN minimum_coverage numeric(6,4),
  -- Under the bar is allowed; under the bar without saying why is not.
  ADD CONSTRAINT short_coverage_needs_a_reason
    CHECK (minimum_coverage IS NULL
           OR coverage >= minimum_coverage
           OR length(btrim(COALESCE(below_coverage_reason, ''))) > 20);

COMMENT ON COLUMN timesheet_submission.below_coverage_reason IS
  'Why a sheet covering less than the period was still offered as complete. '
  'A short year, lost records, a person who left. The reason is the evidence '
  'for the gap — refusing the submission would only have produced invented '
  'hours instead.';


-- ── 2. What standard each size of cost has to meet ───────────────────

CREATE TABLE materiality_policy (
  policy_id       bigserial PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  verified_above          numeric(14,2) NOT NULL,
  corroborated_above      numeric(14,2) NOT NULL,
  federal_corroborated_above numeric(14,2) NOT NULL,
  basis           text NOT NULL,
  set_by          uuid REFERENCES actor,
  set_by_name     text NOT NULL DEFAULT '',
  set_at          timestamptz NOT NULL DEFAULT now(),
  superseded_at   timestamptz,

  CONSTRAINT materiality_ordered
    CHECK (verified_above >= corroborated_above
           AND corroborated_above >= 0
           AND federal_corroborated_above >= 0),
  CONSTRAINT materiality_needs_basis CHECK (length(btrim(basis)) > 20)
);
CREATE UNIQUE INDEX one_live_materiality_policy
  ON materiality_policy (period) WHERE superseded_at IS NULL;

CREATE TRIGGER materiality_policy_immutable
  BEFORE UPDATE OF period, verified_above, corroborated_above,
                   federal_corroborated_above, basis, set_by, set_at
  ON materiality_policy FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TRIGGER materiality_policy_no_delete
  BEFORE DELETE ON materiality_policy FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

COMMENT ON TABLE materiality_policy IS
  'The standard of evidence each size of cost has to meet, written down once '
  'so that spending less effort on small items is a policy rather than an '
  'omission. Federal exposure lowers the bar independently of size.';


-- Every live judgment against the standard its size and exposure require.
CREATE VIEW v_materiality_compliance AS
WITH policy AS (
  SELECT * FROM materiality_policy WHERE superseded_at IS NULL),
decided AS (
  SELECT d.decision_id, d.scope, d.pool::text AS pool, d.grade, d.federal,
         d.decided_by, d.decided_at, d.rationale,
         COALESCE(sum(abs(l.amount)), 0) AS amount,
         l.period
    FROM decision d
    JOIN decision_line dl ON dl.decision_id = d.decision_id AND dl.live
    JOIN ledger_line l ON l.line_id = dl.line_id
   WHERE d.reversed_at IS NULL
   GROUP BY d.decision_id, d.scope, d.pool, d.grade, d.federal, d.decided_by,
            d.decided_at, d.rationale, l.period)
SELECT x.*, p.verified_above, p.corroborated_above,
       p.federal_corroborated_above,
       CASE
         WHEN x.amount >= p.verified_above THEN 'VERIFIED'
         WHEN x.amount >= p.corroborated_above THEN 'CORROBORATED'
         WHEN x.federal IN ('ALLOWABLE', 'PENDING')
              AND x.amount >= p.federal_corroborated_above THEN 'CORROBORATED'
         ELSE 'MANAGEMENT_RECONSTRUCTION'
       END::evidence_grade                                AS required_grade,
       (x.grade >= CASE
          WHEN x.amount >= p.verified_above THEN 'VERIFIED'
          WHEN x.amount >= p.corroborated_above THEN 'CORROBORATED'
          WHEN x.federal IN ('ALLOWABLE', 'PENDING')
               AND x.amount >= p.federal_corroborated_above THEN 'CORROBORATED'
          ELSE 'MANAGEMENT_RECONSTRUCTION'
        END::evidence_grade)                              AS meets_standard
  FROM decided x CROSS JOIN policy p
 WHERE p.period = x.period;

COMMENT ON VIEW v_materiality_compliance IS
  'Each live judgment against the evidence its size and federal exposure '
  'require under the written policy. Empty when no policy is set, which is '
  'itself the finding.';


-- ── 3. The exceptions schedule ───────────────────────────────────────
--
-- One place. Everything where the standard was not met and somebody gave a
-- reason — or where it was not met and nobody did.

CREATE VIEW v_exceptions AS
-- A day or a week past the soft limit, with the reason given at the time.
SELECT o.period,
       'TIME_OVER_LIMIT'                                  AS kind,
       o.entered_at                                       AS occurred_at,
       o.entered_by_name                                  AS actor,
       o.employee_key || ' · ' || o.work_date::text       AS subject,
       array_to_string(o.overrode, ', ') || ' · '
         || o.hours::text || ' hours'                     AS detail,
       o.override_reason                                  AS reason,
       o.hours                                            AS amount
  FROM v_timesheet_overrides o

UNION ALL
-- A timesheet offered as complete for less than the period it covers.
SELECT s.period, 'SHORT_COVERAGE', s.submitted_at, s.submitted_name,
       s.employee_key,
       round(s.coverage * 100, 1)::text || '% of '
         || round(s.expected_hours)::text || ' hours',
       s.below_coverage_reason, s.entered_hours
  FROM timesheet_submission s
 WHERE s.withdrawn_at IS NULL
   AND s.minimum_coverage IS NOT NULL
   AND s.coverage < s.minimum_coverage

UNION ALL
-- A judgment carrying less evidence than its size requires.
SELECT m.period, 'BELOW_MATERIALITY', m.decided_at, m.decided_by, m.scope,
       m.grade::text || ' where ' || m.required_grade::text
         || ' is required at $' || round(m.amount)::text,
       NULLIF(m.rationale, ''), m.amount
  FROM v_materiality_compliance m
 WHERE NOT m.meets_standard

UNION ALL
-- A judgment reversed or superseded, with the reason given.
SELECT l.period, 'DECISION_REVERSED', d.reversed_at, d.decided_by, d.scope,
       'was ' || d.pool::text || ' / ' || d.grade::text,
       d.reversal_reason, sum(abs(l.amount))
  FROM decision d
  JOIN decision_line dl ON dl.decision_id = d.decision_id
  JOIN ledger_line l ON l.line_id = dl.line_id
 WHERE d.reversed_at IS NOT NULL
 GROUP BY l.period, d.reversed_at, d.decided_by, d.scope, d.pool, d.grade,
          d.reversal_reason

UNION ALL
-- A split taken back.
SELECT s.period, 'SPLIT_REVERSED', min(s.reversed_at), max(s.reversed_by),
       s.batch_key, count(*)::text || ' segments', max(s.reversal_reason),
       sum(s.amount)
  FROM ledger_segment s WHERE s.reversed_at IS NOT NULL
 GROUP BY s.period, s.batch_key

UNION ALL
-- A seal broken. The most consequential exception there is: every rate that
-- came from that set is superseded by it.
SELECT ds.period, 'UNSEALED', al.occurred_at, al.actor, ds.set_id::text,
       'decision set reopened', COALESCE(al.reason, ds.unsealed_reason), NULL
  FROM decision_set ds
  LEFT JOIN audit_log al ON al.entity = 'decision_set'
                        AND al.entity_id = ds.set_id::text
                        AND al.action IN ('UNSEAL', 'UNDO')
 WHERE ds.unsealed_reason IS NOT NULL

UNION ALL
-- An action walked back.
SELECT '2025', 'UNDONE', al.occurred_at, al.actor,
       COALESCE(al.before_state->>'label', al.entity),
       'originally by ' || COALESCE(al.before_state->>'originally_by', '—'),
       al.reason, NULL
  FROM audit_log al WHERE al.action = 'UNDO'

UNION ALL
-- Certification withdrawn: effort that was attested and now is not.
SELECT c.period, 'CERTIFICATION_SUPERSEDED', c.superseded_at, c.signed_by,
       c.employee_key, 'signed ' || to_char(c.signed_at, 'DD Mon YYYY'),
       c.superseded_reason, NULL
  FROM labor_certification c WHERE c.superseded_at IS NOT NULL

UNION ALL
-- In-kind offered as cost share. Not a failing — a claim a reviewer will want
-- to see the basis for, which is exactly what an exceptions schedule is for.
SELECT k.period, 'COST_SHARE_CLAIMED', k.recorded_at, k.recorded_name,
       k.kind::text, k.description, k.valuation_basis, k.value
  FROM in_kind_claim k
 WHERE k.superseded_at IS NULL AND k.claimed_as_cost_share;

COMMENT ON VIEW v_exceptions IS
  'Every place the standard was bent, who bent it and why. The first schedule '
  'a reviewer asks for, and the one that decides whether the rest of the file '
  'reads as candid or as managed.';
