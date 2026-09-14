-- A helper recommends; the controller verifies and seals.
--
-- The rule the system already runs on in three places — proposals are never
-- decisions, the classification queue is a suggestion a human confirms, and
-- `060`'s handoff is an act by one person that raises work for another —
-- applied to the outstanding list itself.
--
-- **A recommendation is a `todo`, never a row in the register it points at.**
-- The obvious alternative was to let a helper write a PROPOSED `restatement`
-- for the controller to confirm. That would put two meanings in one word:
-- PROPOSED already means *YBI has put this to NCDMM and they have not
-- answered*, and an auditor reading `restatement` could not tell a position
-- the organisation has taken from a colleague's suggestion. The register
-- stays a record of what YBI has said to a sponsor; the recommendation lives
-- where every other piece of assigned work already lives.
--
-- So there is no new table and no new column here. `todo` already carries
-- everything a recommendation is: `worklist_kind` + `worklist_entity_id` to
-- point at the item without copying it, `opened_by` for who noticed it,
-- `assignee_actor` for who is being asked, and `detail` for why. A
-- recommendation is simply a todo whose opener is not its assignee — which
-- is a fact about the two columns rather than a third column to keep in
-- step with them.

-- One live job per outstanding item.
--
-- The rule `charge_authority` and `actor_portfolio` already follow: an
-- amendment supersedes rather than sitting beside. Two open todos on one
-- worklist item is two people each told to clear it and each assuming the
-- other has — the `one_live_manager_per_code` failure in a new place.
--
-- Partial on `status <> 'DONE'`, because a cleared job must not block the
-- item being raised again: an item that comes back is a new job, and the
-- finished one is part of the trail.
CREATE UNIQUE INDEX one_live_job_per_worklist_item
    ON todo (period, worklist_kind, worklist_entity_id)
 WHERE worklist_kind IS NOT NULL AND status <> 'DONE';

COMMENT ON INDEX one_live_job_per_worklist_item IS
  'One live todo per outstanding worklist item per period. Two is two people '
  'each told to do it and each assuming the other has.';


-- The join that says whether an item has been picked up now matches the
-- period as well.
--
-- `060` joined on kind and entity id alone, so a 2026 todo naming a 2025
-- entity would have reported the 2025 item as taken — and reported it taken
-- by somebody who is not working on it. Never join on part of what
-- identifies a thing; the period is part of it here, and the new index says
-- so too.
--
-- Dropped and recreated rather than replaced: this adds columns and the
-- body is lifted from `060` rather than retyped.
DROP VIEW v_worklist_covered;
CREATE VIEW v_worklist_covered AS
SELECT w.kind,
       w.severity,
       w.period,
       w.label,
       w.entity,
       w.entity_id,
       w.amount,
       w.detail,
       w.owner_portfolio,
       w.goes_to,
       t.todo_id,
       t.assignee,
       t.due_on,
       t.status                                          AS todo_status,
       (t.todo_id IS NOT NULL)                           AS taken,
       (t.todo_id IS NOT NULL AND t.assignee IS NULL)    AS taken_by_nobody,
       -- Who noticed it, beside who is doing it. A first draft derived a
       -- `handed_on` boolean from the two, and it was wrong on the state
       -- that matters most: a recommendation nobody could be named for is
       -- unassigned, and `opened_by <> assignee` reads false when assignee
       -- is NULL. Three states — taken by its opener, handed to somebody,
       -- handed to nobody — do not fit in a boolean, and a derived flag
       -- that quietly collapses one of them is the kind of figure this
       -- record exists to not produce. Both names, and the reader decides.
       t.opened_by
  FROM v_worklist_owned w
  LEFT JOIN LATERAL (
      SELECT tt.todo_id, who.display_name AS assignee, tt.due_on, tt.status,
             tt.opened_by
        FROM todo tt
        LEFT JOIN actor who ON who.actor_id = tt.assignee_actor
       WHERE tt.worklist_kind = w.kind
         AND tt.worklist_entity_id = w.entity_id
         AND tt.period = w.period
         AND tt.status <> 'DONE'
       ORDER BY tt.opened_at DESC
       LIMIT 1) t ON true;

COMMENT ON VIEW v_worklist_covered IS
  'The machine''s list and a person''s list, joined. An item nobody has taken '
  'is the interesting row: the system found it, routed it to a portfolio, and '
  'nobody has put their name or a date on it. opened_by sits beside assignee '
  'because who noticed and who is doing it are different facts and an '
  'auditor asks about both.';
