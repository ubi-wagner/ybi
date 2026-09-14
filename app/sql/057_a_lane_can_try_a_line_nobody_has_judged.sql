-- 057: a lane may try a reading of a line the queue has not reached.
--
-- `v_lane_buildup` started `FROM lane JOIN decision`, so a lane could only
-- ever re-read what had already been judged. That rules out the most
-- valuable question anybody can ask of a lane:
--
--     5227 Portfolio consulting, $588,539 across 442 lines, no objective
--     signal — the largest single open judgment in the ledger.
--
-- What the rate looks like if that is G&A rather than direct is exactly what
-- a lane is for, and it could not be asked, because the group has not been
-- judged yet and an unjudged line was not in the build-up at all.
--
-- This is **not** the rule that unclassified cost is never defaulted into a
-- pool. That rule is about the record: a line with no signal stays in the
-- queue, and the rate reads high while the work is unfinished, which is the
-- honest direction to err. An override is the opposite of a default — it is
-- explicit, it carries a reason the schema refuses to let be empty, it is
-- somebody's name and a grade, it lives in a sandbox that never touches the
-- sealed set, and `v_lane_disclosure` counts it. A lane asks a question. The
-- sealed set is still the answer on the record.
--
-- ── One override per line per lane ──────────────────────────────────
--
-- Two overrides covering one line in one lane would count that line twice in
-- its own build-up, which is the supersession defect in a new place: a
-- figure that reads high because something was said about it more than once.
-- Handlers could check it. The schema should, so it holds when a handler is
-- wrong — and a composite foreign key does it without a trigger.

ALTER TABLE lane_decision_override
  ADD CONSTRAINT lane_decision_override_id_lane UNIQUE (override_id, lane_id);

ALTER TABLE lane_override_line ADD COLUMN lane_id uuid;

UPDATE lane_override_line l SET lane_id = o.lane_id
  FROM lane_decision_override o WHERE o.override_id = l.override_id;

ALTER TABLE lane_override_line ALTER COLUMN lane_id SET NOT NULL;

-- The composite reference is what keeps `lane_id` honest: it cannot name a
-- lane other than the one its override belongs to, because the pair has to
-- exist in the parent.
ALTER TABLE lane_override_line
  DROP CONSTRAINT lane_override_line_override_id_fkey,
  ADD CONSTRAINT lane_override_line_override_lane_fkey
    FOREIGN KEY (override_id, lane_id)
    REFERENCES lane_decision_override (override_id, lane_id) ON DELETE CASCADE;

CREATE UNIQUE INDEX one_override_per_line_per_lane
  ON lane_override_line (lane_id, line_id);

COMMENT ON COLUMN lane_override_line.lane_id IS
  'The lane, carried here so one line cannot be overridden twice in it. Kept '
  'honest by a composite foreign key rather than a trigger: the pair '
  '(override_id, lane_id) has to exist in lane_decision_override.';


-- ── The build-up, from both sides ───────────────────────────────────
--
-- Lifted from pg_get_viewdef and restructured, not retyped from memory — a
-- draft of `045` rewrote `v_form_990_functional`'s scope from memory and
-- silently changed how every line was categorised.
--
-- Two changes. A line reaches the build-up if the lane's decision set judged
-- it **or** the lane overrode it, and the override wins where both. And the
-- join to `decision_line` says `AND dl.live` — it was safe without it,
-- because `decision_line_live_sync` keeps `live` in step with `reversed_at`
-- and the join above is to a live decision, but a rule with an exception is
-- one somebody gets wrong the day they change that join, which is exactly
-- why `045` added the filter to three views that were safe for the same
-- reason.
CREATE OR REPLACE VIEW v_lane_buildup AS
WITH judged AS (
  SELECT l.lane_id, l.name, l.kind, ll.line_id, ll.amount, d.pool
    FROM lane l
    JOIN decision d ON d.set_id = l.set_id AND d.reversed_at IS NULL
    JOIN decision_line dl ON dl.decision_id = d.decision_id AND dl.live
    JOIN ledger_line ll ON ll.line_id = dl.line_id
), tried AS (
  SELECT l.lane_id, l.name, l.kind, ll.line_id, ll.amount, o.pool,
         o.override_id
    FROM lane l
    JOIN lane_decision_override o ON o.lane_id = l.lane_id
    JOIN lane_override_line ol ON ol.override_id = o.override_id
    JOIN ledger_line ll ON ll.line_id = ol.line_id
)
SELECT COALESCE(t.lane_id, j.lane_id)                  AS lane_id,
       COALESCE(t.name, j.name)                        AS name,
       COALESCE(t.kind, j.kind)                        AS kind,
       COALESCE(t.pool, j.pool)                        AS pool,
       sum(COALESCE(t.amount, j.amount))               AS amount,
       count(DISTINCT COALESCE(t.line_id, j.line_id))  AS lines,
       count(DISTINCT t.override_id)                   AS overridden_decisions,
       -- Cost the lane has pulled in that the sealed set has not judged at
       -- all. Named rather than folded into the total, because a lane that
       -- moves $588,539 out of the queue and a lane that moves it between
       -- two pools are different claims, and only the first changes how much
       -- there is left to judge.
       sum(CASE WHEN j.line_id IS NULL THEN t.amount ELSE 0 END)
                                                       AS from_unjudged
  FROM judged j
  FULL JOIN tried t
    ON t.lane_id = j.lane_id AND t.line_id = j.line_id
 GROUP BY 1, 2, 3, 4;

COMMENT ON VIEW v_lane_buildup IS
  'What a lane''s readings do to the pools: the sealed set''s judgments, with '
  'the lane''s overrides winning where it has one, and lines the queue has '
  'not reached included when the lane has said something about them. No '
  'rate — a lane is not sealed and a rate needs a seal.';
