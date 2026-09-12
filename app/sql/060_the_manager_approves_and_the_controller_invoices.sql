-- 060: the handoff. Somebody approves a period of work and somebody else
-- gets a job to do about it.
--
-- `059` gave the system a list a person can write. This is the thing that
-- makes the list move on its own: an act by one person that raises work for
-- another, recorded as one act rather than as two people remembering.
--
-- The loop, in the words it was asked for: the milestone uploads and the
-- time and the materials and the travel, which the project manager approves,
-- and then the controller gets a todo to invoice. And the other way — the
-- controller queries it and the manager gets the todo back.
--
-- ── Three things this does not do ───────────────────────────────────
--
-- **It does not keep its own copy of the work.** A claim names a project and
-- a span of dates. What that span contains is read from the registers that
-- already hold it — `timesheet_entry` for hours, the live decisions over
-- `ledger_line` for cost, `attachment` for the documents — through
-- `v_project_work`. A claim carrying its own hours and dollars would be the
-- second register this design keeps refusing to build, and the two would
-- eventually disagree in front of a sponsor.
--
-- **But an approval has to be of something specific**, or the record moves
-- underneath it and the approval silently comes to cover something else. So
-- a claim records **what the manager was looking at** — `saw_hours`,
-- `saw_amount`, `saw_lines`, `saw_documents` — in exactly the sense
-- `decision_set.seal_hash` records what a seal covered. Those four are not a
-- second source of truth; they are the seal, and `v_project_claim` puts them
-- beside what the record says now and reports whether it has moved.
--
-- **And it does not create an invoice.** No route in this system does, and
-- `invoice` is append-only. A claim is *linked* to the invoice that settles
-- it, which for 2025 is one of the three NCDMM invoices already on file —
-- so approving the 2025 work on Drive AM and linking invoice 10018 is what
-- ties the people, the hours, the documents and the money to each other.

-- ── A todo reaches a person, not a payroll key ──────────────────────
--
-- `todo.assignee` was an `employee_key`, and that is the wrong identity for
-- "who is going to do this". **Tom Metzinger has no employee key** — he is
-- the controller and not on the payroll register — so the first thing this
-- migration exists to do, hand him a job, could not have reached him.
--
-- An employee key says *whose effort this was*, which is the right identity
-- for a timesheet and a certification. An account says *who is doing the
-- work*, which is the right identity for a list of jobs. Every one of the
-- forty payroll people has an account, so nothing is lost in the other
-- direction.
-- Both readers of the column go first and come back at the end, rebuilt
-- against the new identity.
-- `v_project_overview` goes too: CREATE OR REPLACE can only append a column,
-- and the manager belongs beside the people it counts rather than bolted on
-- the end where nobody reading the row would look for it.
DROP VIEW v_worklist_covered;
DROP VIEW v_todo_live;
DROP VIEW v_project_overview;

ALTER TABLE todo ADD COLUMN assignee_actor uuid REFERENCES actor(actor_id);

UPDATE todo t SET assignee_actor = a.actor_id
  FROM actor a WHERE a.employee_key = t.assignee AND t.assignee IS NOT NULL;

ALTER TABLE todo DROP COLUMN assignee;

-- (dropping the column took its partial index with it)
CREATE INDEX todo_by_assignee ON todo (assignee_actor)
  WHERE assignee_actor IS NOT NULL;

COMMENT ON COLUMN todo.assignee_actor IS
  'Who is doing it — an account, not a payroll key. Tom holds CONTROLLER and '
  'is not on the payroll register, so an employee_key could never have '
  'reached him. Unassigned stays a state: on the list and nobody has it.';


-- ── The manager ────────────────────────────────────────────────────
--
-- Not a new column. `charge_authority.role_on_project` has always been the
-- field for what somebody's role on a code is, and the manager has to be
-- able to charge time to the project anyway. One live manager per code, in
-- the schema, for the same reason there is one live grant per person per
-- code: an amendment supersedes rather than sitting beside.
CREATE UNIQUE INDEX one_live_manager_per_code
  ON charge_authority (period, objective_id)
  WHERE role_on_project = 'MANAGER' AND revoked_at IS NULL;


-- ── What a span of a project contains, read from what already holds it ──
CREATE VIEW v_project_work AS
SELECT p.objective_id,
       p.name,
       -- Hours actually booked. Zero for all of 2025 and that is a fact
       -- about the year rather than a gap in this view: the effort was
       -- reconstructed as a distribution after the fact, which is what
       -- `v_labor_effective` holds and why it is named separately below.
       COALESCE(t.hours, 0)                              AS timesheet_hours,
       COALESCE(t.entries, 0)                            AS timesheet_entries,
       t.first_worked,
       t.last_worked,
       -- Direct cost judged onto this objective. Reads the live decision,
       -- like everything else that joins from the ledger side.
       COALESCE(c.amount, 0)                             AS classified_amount,
       COALESCE(c.lines, 0)                              AS classified_lines,
       -- Documents filed against the project — the milestone uploads, the
       -- receipts, the travel. `attachment` already takes OBJECTIVE as a
       -- target, so this needed no register of its own.
       COALESCE(d.documents, 0)                          AS documents,
       -- The annual distribution, named rather than folded in. It is not
       -- span-scoped and pretending otherwise would put a year's wages
       -- inside a month.
       COALESCE(l.distributed_wages, 0)                  AS distributed_wages,
       COALESCE(l.people, 0)                             AS people_distributed
  FROM project p
  LEFT JOIN LATERAL (
      SELECT sum(hours) AS hours, count(*) AS entries,
             min(work_date) AS first_worked, max(work_date) AS last_worked
        FROM timesheet_entry
       WHERE objective_id = p.objective_id AND superseded_at IS NULL) t ON true
  LEFT JOIN LATERAL (
      SELECT sum(ll.amount) AS amount, count(DISTINCT ll.line_id) AS lines
        FROM decision dn
        JOIN decision_line dl ON dl.decision_id = dn.decision_id AND dl.live
        JOIN ledger_line ll ON ll.line_id = dl.line_id
       WHERE dn.reversed_at IS NULL
         AND dn.objective_id = p.objective_id) c ON true
  LEFT JOIN LATERAL (
      SELECT count(*) AS documents FROM attachment
       WHERE target_type = 'OBJECTIVE' AND target_id = p.objective_id
         AND detached_at IS NULL) d ON true
  LEFT JOIN LATERAL (
      SELECT sum(distributed_wages) AS distributed_wages,
             count(DISTINCT employee_key) AS people
        FROM v_labor_effective
       WHERE objective_id = p.objective_id) l ON true;

COMMENT ON VIEW v_project_work IS
  'What a project has on it, read from the registers that hold it: hours '
  'from timesheets, cost from live decisions over the ledger, documents from '
  'attachment. The annual labour distribution is named separately because it '
  'is not span-scoped.';


-- ── The claim ──────────────────────────────────────────────────────
CREATE TABLE project_claim (
  claim_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  objective_id  text NOT NULL REFERENCES project(objective_id),
  period        text NOT NULL REFERENCES fiscal_period(period),

  covers_from   date NOT NULL,
  covers_to     date NOT NULL,
  CHECK (covers_to >= covers_from),

  state         text NOT NULL DEFAULT 'APPROVED'
                CHECK (state IN ('APPROVED','QUERIED','INVOICED','WITHDRAWN')),

  -- Who said it was right. A judgment gets a sentence here as everywhere.
  approved_by   uuid NOT NULL REFERENCES actor(actor_id),
  approved_at   timestamptz NOT NULL DEFAULT now(),
  note          text NOT NULL CHECK (length(btrim(note)) >= 10),

  -- What they were looking at. The seal, not a second register: read from
  -- v_project_work at the moment of approval, and compared against it after.
  saw_hours     numeric(10,2) NOT NULL,
  saw_amount    numeric(14,2) NOT NULL,
  saw_lines     integer NOT NULL,
  saw_documents integer NOT NULL,

  -- Settled by the invoice already on file. No route creates an invoice and
  -- `invoice` is append-only, so this is a link rather than a creation.
  invoice_id    uuid REFERENCES invoice(invoice_id),
  invoiced_at   timestamptz,
  invoiced_by   uuid REFERENCES actor(actor_id),
  CHECK ((state = 'INVOICED') = (invoice_id IS NOT NULL)),
  CHECK ((invoice_id IS NULL) = (invoiced_at IS NULL)),

  -- Sent back. The other direction of the loop, and it says what is wrong
  -- for the same reason a blocked todo does: a query with no reason is one
  -- nobody can answer.
  queried_reason text,
  queried_at     timestamptz,
  queried_by     uuid REFERENCES actor(actor_id),
  CHECK ((state = 'QUERIED') = (queried_reason IS NOT NULL)),

  withdrawn_reason text,
  CHECK ((state = 'WITHDRAWN') = (withdrawn_reason IS NOT NULL))
);

-- One live claim over a span. Two claims covering the same week would be
-- invoiced twice, which is the shape of every double-count in this schema.
CREATE INDEX project_claim_live ON project_claim (objective_id, covers_from)
  WHERE state <> 'WITHDRAWN';

COMMENT ON TABLE project_claim IS
  'A span of a project the manager has said is right and ready to invoice. '
  'Carries what they were looking at rather than a copy of the work, so a '
  'record that moves afterwards is visible rather than silently re-covered.';


-- The todo a claim raised, so the loop can be walked in both directions.
ALTER TABLE todo ADD COLUMN from_claim uuid REFERENCES project_claim(claim_id);
CREATE INDEX todo_by_claim ON todo (from_claim) WHERE from_claim IS NOT NULL;

COMMENT ON COLUMN todo.from_claim IS
  'The approval or query that raised this job. An act by one person that '
  'creates work for another is one act, not two people remembering.';


CREATE VIEW v_project_claim AS
SELECT c.claim_id,
       c.objective_id,
       p.name                                            AS project_name,
       c.period,
       c.covers_from,
       c.covers_to,
       c.state,
       c.note,
       a.display_name                                    AS approved_by,
       c.approved_at,
       c.saw_hours,
       c.saw_amount,
       c.saw_lines,
       c.saw_documents,
       w.timesheet_hours,
       w.classified_amount,
       w.classified_lines,
       w.documents,
       -- Has the record moved since it was approved? This is the whole
       -- reason the four `saw_` columns exist. A claim that still agrees is
       -- one a controller can invoice without re-reading the year.
       (w.timesheet_hours = c.saw_hours
        AND w.classified_amount = c.saw_amount
        AND w.classified_lines = c.saw_lines
        AND w.documents = c.saw_documents)               AS still_agrees,
       i.invoice_number,
       c.invoice_id,
       c.invoiced_at,
       inv.display_name                                  AS invoiced_by,
       c.queried_reason,
       c.queried_at,
       q.display_name                                    AS queried_by,
       c.withdrawn_reason
  FROM project_claim c
  JOIN project p ON p.objective_id = c.objective_id
  JOIN actor a ON a.actor_id = c.approved_by
  LEFT JOIN actor inv ON inv.actor_id = c.invoiced_by
  LEFT JOIN actor q ON q.actor_id = c.queried_by
  LEFT JOIN invoice i ON i.invoice_id = c.invoice_id
  LEFT JOIN v_project_work w ON w.objective_id = c.objective_id;

COMMENT ON VIEW v_project_claim IS
  'Every claim, with what was approved beside what the record says now. '
  '`still_agrees` false is not a defect — it is the record having moved, '
  'which is exactly what a controller needs to know before invoicing it.';


-- ── The project, with its manager and its claims ───────────────────
--
-- Lifted from pg_get_viewdef and extended, not retyped: a draft of `045`
-- rewrote a view's scope from memory and silently changed how every line
-- was categorised.
CREATE VIEW v_project_overview AS
SELECT p.objective_id,
       p.name,
       p.summary,
       p.status,
       p.starts_on,
       p.ends_on,
       p.award_id,
       a.sponsor,
       a.ceiling_federal,
       o.label                                           AS objective_label,
       o.is_federal,
       o.cfda,
       (SELECT count(*) FROM charge_authority c
         WHERE c.objective_id = p.objective_id
           AND c.revoked_at IS NULL)                     AS people,
       -- Who runs it. Read off the role on the grant rather than from a
       -- column of its own, because a manager is somebody on the project
       -- with a role and that register already exists.
       (SELECT c.employee_key FROM charge_authority c
         WHERE c.objective_id = p.objective_id
           AND c.role_on_project = 'MANAGER'
           AND c.revoked_at IS NULL LIMIT 1)             AS manager,
       (SELECT count(*) FROM todo t
         WHERE t.objective_id = p.objective_id
           AND t.status = 'OPEN')                        AS todos_open,
       (SELECT count(*) FROM todo t
         WHERE t.objective_id = p.objective_id
           AND t.status = 'BLOCKED')                     AS todos_blocked,
       (SELECT count(*) FROM todo t
         WHERE t.objective_id = p.objective_id
           AND t.status <> 'DONE' AND t.due_on < current_date) AS todos_overdue,
       (SELECT count(*) FROM todo t
         WHERE t.objective_id = p.objective_id
           AND t.status = 'DONE')                        AS todos_done,
       (SELECT count(*) FROM project_claim c
         WHERE c.objective_id = p.objective_id
           AND c.state = 'APPROVED')                     AS claims_to_invoice,
       (SELECT count(*) FROM project_claim c
         WHERE c.objective_id = p.objective_id
           AND c.state = 'QUERIED')                      AS claims_queried,
       (SELECT count(*) FROM project_claim c
         WHERE c.objective_id = p.objective_id
           AND c.state = 'INVOICED')                     AS claims_invoiced,
       p.opened_by,
       p.opened_at,
       p.closed_at,
       p.closeout_note
  FROM project p
  JOIN cost_objective o ON o.objective_id = p.objective_id
  LEFT JOIN award a ON a.award_id = p.award_id;


-- The live list, rebuilt because `assignee` changed identity.
CREATE VIEW v_todo_live AS
SELECT t.todo_id,
       t.period,
       t.objective_id,
       p.name                                            AS project_name,
       p.status                                          AS project_status,
       t.title,
       t.detail,
       t.assignee_actor,
       who.display_name                                  AS assignee,
       t.due_on,
       t.status,
       t.blocked_reason,
       t.worklist_kind,
       t.worklist_entity_id,
       t.verification_ref,
       t.from_claim,
       t.opened_by,
       t.opened_at,
       t.sort_index,
       (t.due_on IS NOT NULL AND t.due_on < current_date
        AND t.status <> 'DONE')                          AS overdue,
       CASE WHEN t.due_on IS NOT NULL
            THEN (t.due_on - current_date) END           AS days_to_due
  FROM todo t
  LEFT JOIN project p ON p.objective_id = t.objective_id
  LEFT JOIN actor who ON who.actor_id = t.assignee_actor
 WHERE t.status <> 'DONE';


-- And the machine's list against a person's, rebuilt for the same reason.
-- Lifted from `059` with the assignee join changed and nothing else.
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
       (t.todo_id IS NOT NULL AND t.assignee IS NULL)    AS taken_by_nobody
  FROM v_worklist_owned w
  LEFT JOIN LATERAL (
      SELECT tt.todo_id, who.display_name AS assignee, tt.due_on, tt.status
        FROM todo tt
        LEFT JOIN actor who ON who.actor_id = tt.assignee_actor
       WHERE tt.worklist_kind = w.kind
         AND tt.worklist_entity_id = w.entity_id
         AND tt.status <> 'DONE'
       ORDER BY tt.opened_at DESC
       LIMIT 1) t ON true;

COMMENT ON VIEW v_worklist_covered IS
  'The machine''s list and a person''s list, joined. An item nobody has taken '
  'is the interesting row: the system found it, routed it to a portfolio, and '
  'nobody has put their name or a date on it.';
