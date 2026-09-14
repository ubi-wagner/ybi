-- 059: setting a piece of work up, and writing down who is doing what by when.
--
-- Read across from the RFP pipeline (`ubi-wagner/govwin`), which models the
-- other half of the same engagement: it wins the work and this system
-- accounts for it. Its post-award module has `projects`, `project_clins`,
-- `project_milestones`, `project_milestone_tasks`, `project_deliverables`,
-- `project_assignments`, `project_invoices`, `project_invoice_lines`,
-- `project_time_entries`, `project_modifications`, `project_risks`,
-- `project_reviews`, `project_meetings` and `project_comments`.
--
-- **Two of those are taken and the rest are already here under other names.**
-- That is the whole design decision, and their own build log is the argument
-- for it. `docs/PROJECT_MANAGEMENT_DESIGN.md` carries a superseded notice at
-- the top: they built `project_wbs_nodes` *beside* `project_milestones`,
-- migration 228 collapsed them and 229 dropped the table, because
--
--     "the shape below — a node tree beside a milestone list, each with its
--      own dates, costs and CLIN — was two structures describing one thing.
--      It also produced two answers to the same question."
--
-- Which is this system's own most expensive lesson in somebody else's words:
-- `space_partition` beside `space_unit`, 13.0% and 2.2% at the same moment,
-- and the rule written at the top of the contracts section — *the cost
-- objective is the charge code; there is deliberately no second register of
-- codes.*
--
-- So, taken across:
--
--   projects                 -> `project`, below, keyed on the charge code
--   project_milestone_tasks  -> `todo`, below
--
-- and deliberately not taken, because the register already exists:
--
--   project_assignments   `charge_authority` — and it already carries the
--                         rules a second table would have to learn again:
--                         nobody assigns themselves, one live grant per
--                         person per code, revoked rather than deleted
--   project_clins         `award_budget` by category. All four America Makes
--                         awards are cost reimbursement invoiced monthly and
--                         carry no CLIN at all; a CLIN table would be
--                         `invoice.milestone_id` again — a register for a
--                         contract shape YBI does not have
--   project_milestones    `milestone`
--   project_deliverables  `milestone`, and these agreements schedule none
--   project_invoices      `invoice`, and `receipt` for the money in
--   project_time_entries  `timesheet_entry` and `labor_allocation`
--   project_modifications `award_term`, which cites the clause
--
-- The risks, reviews, meetings and comments registers are not taken either,
-- for a plainer reason: nothing here would write them. This schema has
-- eleven columns and tables that looked usable and were filled by nothing,
-- and every one of them cost something to find.

CREATE TABLE project (
  -- **The charge code is the project.** Not a foreign key to one — the
  -- identity. A project id that could differ from an objective id is two
  -- names for one thing, and somebody would eventually ask which is right.
  objective_id  text PRIMARY KEY REFERENCES cost_objective(objective_id),

  -- The contract, where there is one. Nullable because not everything YBI
  -- runs is a federal award, and a project with no award is a real project
  -- rather than a half-entered one.
  award_id      text REFERENCES award(award_id),

  name          text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
  summary       text NOT NULL DEFAULT '',

  status        text NOT NULL DEFAULT 'PLANNING'
                CHECK (status IN ('PLANNING','ACTIVE','CLOSING','CLOSED')),

  starts_on     date,
  ends_on       date,
  CHECK (ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on),

  opened_by     text NOT NULL,
  opened_at     timestamptz NOT NULL DEFAULT now(),

  closed_at     timestamptz,
  closed_by     text,
  closeout_note text,
  -- Their `projects_closed_has_time`, which is this system's
  -- `milestone_check` in another accent: a state that claims a date carries
  -- one. CLOSED with no closing date is a status somebody set, not a thing
  -- that happened.
  CHECK ((status = 'CLOSED') = (closed_at IS NOT NULL)),
  CHECK ((closed_at IS NULL) = (closed_by IS NULL)),
  -- And closing is a judgment worth a sentence, like every other one here.
  CHECK (status <> 'CLOSED' OR length(btrim(coalesce(closeout_note,''))) >= 10)
);

COMMENT ON TABLE project IS
  'A charge code somebody has set up: the contract it works under, the dates '
  'it runs between, and a status. Keyed on the objective because the cost '
  'objective is the charge code and there is no second register of codes.';


CREATE TABLE todo (
  todo_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period        text NOT NULL REFERENCES fiscal_period(period),

  -- A todo about a project, or about the engagement. Both are real: "chase
  -- NCDMM for a readable Drive AM agreement" belongs to no charge code.
  objective_id  text REFERENCES project(objective_id) ON DELETE RESTRICT,

  title         text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 200),
  detail        text NOT NULL DEFAULT '',

  -- Unassigned is a state worth keeping, not a gap to fill: it says the work
  -- is on the list and nobody has it, which is different from nobody having
  -- written it down. Same rule as a blank on an intake form.
  assignee      text,
  due_on        date,

  status        text NOT NULL DEFAULT 'OPEN'
                CHECK (status IN ('OPEN','DONE','BLOCKED')),

  -- Both from `project_milestone_tasks`, and both already the house style:
  -- `blocked_has_reason` is `reversal_needs_reason`, and `done_has_time` is
  -- the milestone rule again.
  blocked_reason text,
  CHECK ((status = 'BLOCKED') = (blocked_reason IS NOT NULL)),
  done_at       timestamptz,
  done_by       text,
  CHECK ((status = 'DONE') = (done_at IS NOT NULL)),
  CHECK ((done_at IS NULL) = (done_by IS NULL)),

  -- What outstanding thing this is somebody's answer to.
  --
  -- `v_worklist` has always known *what* is outstanding, and `049`'s
  -- `v_worklist_owned` added *which portfolio* can act on it. Neither can
  -- say **who** is doing it or **by when**, because nothing in the system
  -- could write that down. These two columns are how a person takes an item.
  --
  -- No foreign key, and that is not laziness: the worklist is a view over
  -- eleven derived sources and its entity ids are computed, not stored. A
  -- constraint would have to be a trigger re-deriving the whole view on every
  -- insert, and the failure it would prevent — a todo naming an item that has
  -- since been cleared — is not a failure. It is the good outcome.
  worklist_kind      text,
  worklist_entity_id text,
  CHECK ((worklist_kind IS NULL) = (worklist_entity_id IS NULL)),

  -- Or one of the things only the controller can settle. Free text rather
  -- than a key, because `verification_items.py` is Python and a database
  -- constraint against it would be a hand-kept copy of a list — the shape
  -- that has been wrong five times in this repository.
  verification_ref text,

  opened_by     text NOT NULL,
  opened_at     timestamptz NOT NULL DEFAULT now(),
  sort_index    integer NOT NULL DEFAULT 0
);

CREATE INDEX todo_live ON todo (period, status) WHERE status <> 'DONE';
CREATE INDEX todo_by_assignee ON todo (assignee) WHERE assignee IS NOT NULL;
CREATE INDEX todo_by_project ON todo (objective_id) WHERE objective_id IS NOT NULL;
CREATE INDEX todo_by_worklist ON todo (worklist_kind, worklist_entity_id)
  WHERE worklist_kind IS NOT NULL;

COMMENT ON TABLE todo IS
  'Work somebody has written down, assigned and dated. The half v_worklist '
  'could never hold: the worklist derives what is outstanding and knows the '
  'portfolio that can act on it, and nothing could say who actually has it '
  'or by when.';


-- ── The three questions ─────────────────────────────────────────────

CREATE VIEW v_todo_live AS
SELECT t.todo_id,
       t.period,
       t.objective_id,
       p.name                                            AS project_name,
       p.status                                          AS project_status,
       t.title,
       t.detail,
       t.assignee,
       t.due_on,
       t.status,
       t.blocked_reason,
       t.worklist_kind,
       t.worklist_entity_id,
       t.verification_ref,
       t.opened_by,
       t.opened_at,
       t.sort_index,
       (t.due_on IS NOT NULL AND t.due_on < current_date
        AND t.status <> 'DONE')                          AS overdue,
       CASE WHEN t.due_on IS NOT NULL
            THEN (t.due_on - current_date) END           AS days_to_due
  FROM todo t
  LEFT JOIN project p ON p.objective_id = t.objective_id
 WHERE t.status <> 'DONE';

COMMENT ON VIEW v_todo_live IS
  'Everything still to do. DONE drops out — a todo is not superseded, it is '
  'finished, and the row stays for the trail.';


-- Of everything outstanding, how much has anybody actually taken.
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
  -- The most recent live todo naming this item. More than one person working
  -- the same item is not an error worth refusing — it is worth showing.
  LEFT JOIN LATERAL (
      SELECT todo_id, assignee, due_on, status
        FROM todo
       WHERE worklist_kind = w.kind
         AND worklist_entity_id = w.entity_id
         AND status <> 'DONE'
       ORDER BY opened_at DESC
       LIMIT 1) t ON true;

COMMENT ON VIEW v_worklist_covered IS
  'The machine''s list and a person''s list, joined. An item nobody has taken '
  'is the interesting row: the system found it, routed it to a portfolio, and '
  'nobody has put their name or a date on it.';


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
       -- The people who may charge it. Read from the register that already
       -- holds them rather than from a second one.
       (SELECT count(*) FROM charge_authority c
         WHERE c.objective_id = p.objective_id
           AND c.revoked_at IS NULL)                     AS people,
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
       p.opened_by,
       p.opened_at,
       p.closed_at,
       p.closeout_note
  FROM project p
  JOIN cost_objective o ON o.objective_id = p.objective_id
  LEFT JOIN award a ON a.award_id = p.award_id;

COMMENT ON VIEW v_project_overview IS
  'One row per project: the contract it works under, how many people may '
  'charge it, and what is outstanding on it. Every figure read from the '
  'register that already holds it.';
