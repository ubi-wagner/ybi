import React, { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, money } from "../api.js";
/* What a kind means is written down once — three screens each kept
   their own map of it and every one was missing different kinds. */
import { KINDS } from "../worklistKinds.js";
import {
  Card, Drawer, Empty, Field, PageHead, Pill, Segmented, Stat, Table, Tick,
  useToast,
} from "../components/ui.jsx";

/* Setting a piece of work up, and writing down who is doing what by when.

   Read across from the RFP pipeline, which models the other half of the same
   engagement — it wins the work and this system accounts for it. What was
   taken is a project and a todo; what was not is a dozen registers that
   already exist here under other names, which migration 059 lists one by one.

   Nothing on this screen keeps its own copy of anything. The people are
   `charge_authority`, the contract is `award`, the provisions are
   `award_term` with the citation check beside them. A project screen holding
   its own list of who may charge a code would be the second register this
   whole design exists to avoid. */

const STATUS = {
  PLANNING: { tone: "", says: "Planning" },
  ACTIVE:   { tone: "accent", says: "Active" },
  CLOSING:  { tone: "warn", says: "Closing" },
  CLOSED:   { tone: "solid", says: "Closed" },
};

export default function Projects({ actor }) {
  const { objectiveId } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [view, setView] = useState("projects");
  const [rows, setRows] = useState([]);
  const [detail, setDetail] = useState(null);
  const [opening, setOpening] = useState(null);

  const canWrite = (actor?.portfolios || []).some(
    (p) => p === "PROJECT" || p === "CONTROLLER");

  const load = useCallback(async () => {
    const got = await api.projects();
    setRows(got.projects || []);
  }, []);
  useEffect(() => { load(); }, [load]);

  const openDetail = useCallback(async (id) => {
    setDetail(await api.project(id));
  }, []);
  useEffect(() => { if (objectiveId) openDetail(objectiveId); }, [objectiveId, openDetail]);

  return (
    <div className="page">
      <PageHead title="Projects" schedule="F">
        A project is a charge code somebody has set up: the contract it works
        under, the people who may charge it, and the things still to do on it.
        There is deliberately no second register of any of those — the people
        are the same grants the charge-code screen shows, and the contract is
        the same award the auditor walks back to.
      </PageHead>

      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", margin: "14px 0 10px" }}>
        <Segmented value={view} onChange={setView} options={[
          ["projects", "Projects"],
          ["todos", "To do"],
          ["covering", "What nobody has taken"],
        ]} />
        {view === "projects" && canWrite && (
          <button className="primary" onClick={() => setOpening({
            objective_id: "", name: "", summary: "", award_id: "",
            starts_on: "", ends_on: "", reason: "",
          })}>Set up a project</button>
        )}
      </div>

      {view === "projects" && (
        rows.length === 0 ? (
          <Card><Empty mark="▣" title="Nothing set up yet">
            Opening a charge code, saying which contract it works under,
            naming who may charge it and writing down the first things to do
            were four separate acts in four places. This is all of them at
            once — and a code with nobody on it has its authority gate
            switched off, which is right for reconstructing a year already
            worked and wrong for work starting now.
          </Empty></Card>
        ) : (
          <Table columns={[
            { label: "Project", align: "left" },
            { label: "Contract", align: "left" },
            { label: "Ceiling" },
            { label: "People" },
            { label: "To do" },
            { label: "Overdue" },
            { label: "Status", align: "left" },
          ]}>
            {rows.map((p) => (
              <tr key={p.objective_id} className="hoverable"
                  style={{ cursor: "pointer" }}
                  onClick={() => nav(`/projects/${p.objective_id}`)}>
                <td className="l">
                  <strong>{p.name}</strong>
                  <div className="rowsub">{p.objective_id}</div>
                </td>
                <td className="l rowsub">
                  {p.award_id || <span className="rowsub">none</span>}
                  {p.sponsor && <div>{p.sponsor}</div>}
                </td>
                <td className="amt">
                  {p.ceiling_federal ? money(p.ceiling_federal)
                                     : <span className="rowsub">—</span>}
                </td>
                <td style={{ color: p.people === 0 ? "var(--warn)" : undefined }}>
                  {p.people}
                </td>
                <td>{p.todos_open}{p.todos_blocked > 0 &&
                  <span className="warnish"> · {p.todos_blocked} blocked</span>}</td>
                <td className={p.todos_overdue > 0 ? "amt neg" : "amt"}>
                  {p.todos_overdue || ""}
                </td>
                <td className="l">
                  <Pill tone={STATUS[p.status]?.tone}>
                    {STATUS[p.status]?.says || p.status}
                  </Pill>
                </td>
              </tr>
            ))}
          </Table>
        )
      )}

      {view === "todos" && <Todos actor={actor} canWrite={canWrite} toast={toast} />}
      {view === "covering" && <Covering canWrite={canWrite} toast={toast} />}

      <Drawer open={!!detail} onClose={() => { setDetail(null); nav("/projects"); }}
              title={detail?.project.name}
              subtitle={detail ? `${detail.project.objective_id}${
                detail.project.award_id ? ` · ${detail.project.award_id}` : ""}` : ""}>
        {detail && (
          <ProjectDetail d={detail} canWrite={canWrite} toast={toast}
                         onChange={async () => {
                           await openDetail(detail.project.objective_id);
                           load();
                         }} />
        )}
      </Drawer>

      <Drawer open={!!opening} onClose={() => setOpening(null)}
              title="Set up a project"
              subtitle="One act — the code, the contract, the people, and the first things to do">
        {opening && (
          <Setup f={opening} setF={setOpening} toast={toast}
                 onDone={() => { setOpening(null); load(); }} />
        )}
      </Drawer>
    </div>
  );
}


/* ── One project ───────────────────────────────────────────────────── */
function ProjectDetail({ d, canWrite, toast, onChange }) {
  const p = d.project;
  const [closing, setClosing] = useState("");
  const bad = d.terms.filter((t) => t.citation_state === "NOT IN DOCUMENT").length;
  const blind = d.terms.filter(
    (t) => t.citation_state === "NO TEXT LAYER" || t.citation_state === "NOT READ").length;

  return (
    <>
      <div className="grid three" style={{ marginBottom: 14 }}>
        <Stat label="May charge it" value={p.people}
              note={p.people === 0 ? "the gate is off" : "authorised"} />
        <Stat label="To do" value={p.todos_open}
              note={p.todos_overdue > 0 ? `${p.todos_overdue} overdue` : "none overdue"} />
        <Stat label="Ceiling"
              value={p.ceiling_federal ? money(p.ceiling_federal) : "—"}
              note={p.sponsor || "no contract"} />
      </div>
      {p.summary && <div className="rowsub wrap" style={{ marginBottom: 14 }}>{p.summary}</div>}

      {/* The contract's provisions, with whether the agreement on file
          actually contains what each cites. It is the same check the
          contracts screen shows, read here because somebody setting a
          project up is the person who would go and ask. */}
      {d.terms.length > 0 && (
        <Card variant="quiet" title="The contract says"
              aside={`${d.terms.length} provision(s)`} style={{ marginBottom: 14 }}>
          {bad > 0 && (
            <div className="rowsub failish" style={{ marginBottom: 8 }}>
              {bad} cite a clause the agreement on file does not contain.
            </div>
          )}
          {blind > 0 && (
            <div className="rowsub warnish" style={{ marginBottom: 8 }}>
              {blind} cannot be checked — there is no text in the agreement on
              file to check them against.
            </div>
          )}
          {/* Two columns, not three. A drawer is narrow and a provision's
              text is the part worth reading; squeezed into a third of the
              width it becomes a column of single words. The clause goes
              under the text it belongs to. */}
          {d.terms.map((t) => (
            <div key={t.term_key} className="rowsub"
                 style={{ padding: "8px 0", borderTop: "1px solid var(--rule)" }}>
              <strong style={{ color: "var(--ink)" }}>{t.term_key}</strong>
              <div className="wrap" style={{ color: "var(--ink)", margin: "3px 0" }}>
                {t.term_value}
              </div>
              <div>
                {t.citation}
                {t.citation_state === "NOT IN DOCUMENT" && (
                  <span className="failish"> · not in the agreement on file</span>
                )}
                {t.citation_state === "FOUND" && <span> · checked</span>}
              </div>
            </div>
          ))}
        </Card>
      )}

      <Card variant="quiet" title="Who may charge it"
            aside="The same grants the charge-code screen shows"
            style={{ marginBottom: 14 }}>
        {d.people.length === 0 ? (
          <div className="rowsub warnish">
            Nobody is assigned, so the authority gate is off on this code and
            anybody may book time to it. That is right for a year already
            worked and wrong for work starting now — assign one person and the
            gate turns on.
          </div>
        ) : (
          <Table columns={[{ label: "Person", align: "left" },
                           { label: "Role", align: "left" },
                           { label: "Since", align: "left" },
                           { label: "Why", align: "left" }]}>
            {d.people.map((x) => (
              <tr key={x.employee_key}>
                <td className="l"><strong>{x.employee_key}</strong></td>
                <td className="l rowsub">{x.role_on_project || "—"}</td>
                <td className="l rowsub">{x.opens_on || "—"}</td>
                <td className="l wrap rowsub">{x.reason}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <TodoList rows={d.todos} canWrite={canWrite} toast={toast}
                onChange={onChange} objectiveId={p.objective_id}
                title="To do on this project" />

      {canWrite && p.status !== "CLOSED" && (
        <Card variant="quiet" title="Close it out" style={{ marginTop: 14 }}>
          <div className="rowsub" style={{ marginBottom: 8 }}>
            Say what it delivered and what is left. A project closed over an
            open list is a list nobody will look at again, so anything still
            outstanding has to be finished first.
          </div>
          <textarea rows={3} value={closing}
                    placeholder="What it delivered, and what is left."
                    onChange={(e) => setClosing(e.target.value)} />
          <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
            {["PLANNING", "ACTIVE", "CLOSING"].filter((s) => s !== p.status).map((s) => (
              <button key={s} className="sm" onClick={async () => {
                try {
                  await api.setProjectStatus(p.objective_id, { status: s, note: closing });
                  toast.ok(`Moved to ${STATUS[s].says.toLowerCase()}`);
                  onChange();
                } catch (e) { toast.fail(String(e.message || e)); }
              }}>{STATUS[s].says}</button>
            ))}
            <button className="primary" disabled={closing.trim().length < 10}
                    onClick={async () => {
                      try {
                        await api.setProjectStatus(p.objective_id,
                          { status: "CLOSED", note: closing });
                        toast.ok("Closed out");
                        onChange();
                      } catch (e) { toast.fail(String(e.message || e)); }
                    }}>Close the project</button>
          </div>
        </Card>
      )}
      {p.status === "CLOSED" && (
        <Card variant="quiet" title="Closed" style={{ marginTop: 14 }}>
          <div className="rowsub wrap">{p.closeout_note}</div>
          <div className="rowsub" style={{ marginTop: 6 }}>
            {new Date(p.closed_at).toLocaleDateString()}
          </div>
        </Card>
      )}
    </>
  );
}


/* ── The list a person can actually write ──────────────────────────── */
function Todos({ actor, canWrite, toast }) {
  const [rows, setRows] = useState([]);
  const [mine, setMine] = useState(false);
  const load = useCallback(async () => {
    const got = await api.todos(mine ? { mine: "true" } : {});
    setRows(got.todos || []);
  }, [mine]);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      {actor?.employee_key && (
        <div style={{ marginBottom: 10 }}>
          <Segmented value={mine ? "mine" : "all"}
                     onChange={(v) => setMine(v === "mine")}
                     options={[["all", "Everything"], ["mine", "Mine"]]} />
        </div>
      )}
      <TodoList rows={rows} canWrite={canWrite} toast={toast} onChange={load}
                objectiveId={null} title="To do"
                aside="Assigned, dated, and not derived from anything" />
    </>
  );
}


function TodoList({ rows, canWrite, toast, onChange, objectiveId, title, aside }) {
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ title: "", detail: "", assignee: "", due_on: "" });
  const [blocking, setBlocking] = useState(null);

  const add = async () => {
    try {
      await api.openTodo({
        title: f.title, detail: f.detail,
        objective_id: objectiveId || null,
        assignee: f.assignee.trim() || null,
        due_on: f.due_on || null,
      });
      toast.ok("On the list");
      setAdding(false);
      setF({ title: "", detail: "", assignee: "", due_on: "" });
      onChange();
    } catch (e) { toast.fail(String(e.message || e)); }
  };

  const change = async (id, body, said) => {
    try {
      await api.changeTodo(id, body);
      toast.ok(said);
      onChange();
    } catch (e) { toast.fail(String(e.message || e)); }
  };

  return (
    <Card variant="quiet" title={title}
          aside={aside || `${rows.length} outstanding`} style={{ marginTop: 14 }}>
      {rows.length === 0 ? (
        <div className="rowsub">Nothing outstanding.</div>
      ) : (
        <Table columns={[
          { label: "", width: 30, align: "left" },
          { label: "What", align: "left" },
          { label: "Who", align: "left" },
          { label: "By", align: "left" },
          { label: "", width: 150, align: "left" },
        ]}>
          {rows.map((t) => (
            <tr key={t.todo_id}>
              <td className="l">
                <Tick state={t.status === "BLOCKED" ? "flagged"
                             : t.overdue ? "failed" : "open"} />
              </td>
              <td className="l wrap">
                <strong>{t.title}</strong>
                {t.detail && <div className="rowsub wrap">{t.detail}</div>}
                {t.status === "BLOCKED" && (
                  <div className="rowsub warnish wrap">
                    Blocked: {t.blocked_reason}
                  </div>
                )}
                {t.worklist_kind && (
                  <div className="rowsub">covers {t.worklist_kind}</div>
                )}
                {t.project_name && !objectiveId && (
                  <div className="rowsub">{t.project_name}</div>
                )}
              </td>
              <td className="l rowsub">
                {t.assignee || <span className="warnish">nobody</span>}
              </td>
              <td className={"l rowsub" + (t.overdue ? " failish" : "")}>
                {t.due_on || "—"}
                {t.overdue && <div>{-t.days_to_due}d late</div>}
              </td>
              <td className="l">
                {canWrite && (
                  <>
                    <button className="sm"
                            onClick={() => change(t.todo_id, { status: "DONE" },
                                                  "Done")}>Done</button>{" "}
                    {t.status !== "BLOCKED" && (
                      <button className="sm"
                              onClick={() => setBlocking(t)}>Blocked</button>
                    )}
                    {t.status === "BLOCKED" && (
                      <button className="sm"
                              onClick={() => change(t.todo_id, { status: "OPEN" },
                                                    "Unblocked")}>Unblock</button>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </Table>
      )}

      {canWrite && !adding && (
        <button className="sm" style={{ marginTop: 10 }}
                onClick={() => setAdding(true)}>Add something</button>
      )}
      {canWrite && adding && (
        <div style={{ marginTop: 12 }}>
          <Field label="What" required>
            <input value={f.title} placeholder="Obtain a text-bearing copy of the agreement"
                   onChange={(e) => setF({ ...f, title: e.target.value })} />
          </Field>
          <div style={{ marginTop: 10 }}>
            <Field label="Why it matters">
              <textarea rows={2} value={f.detail}
                        onChange={(e) => setF({ ...f, detail: e.target.value })} />
            </Field>
          </div>
          <div className="grid two" style={{ marginTop: 10 }}>
            <Field label="Who">
              <input value={f.assignee} placeholder="METZINGER — or leave it for now"
                     onChange={(e) => setF({ ...f, assignee: e.target.value })} />
            </Field>
            <Field label="By when">
              <input type="date" value={f.due_on}
                     onChange={(e) => setF({ ...f, due_on: e.target.value })} />
            </Field>
          </div>
          {/* Unassigned is a state, not a gap: on the list and nobody has it
              is a different fact from nobody having written it down. */}
          <div className="rowsub" style={{ marginTop: 4 }}>
            Leaving it unassigned is fine — it says the work is on the list and
            nobody has it, which is worth knowing.
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
            <button className="primary" disabled={!f.title.trim()} onClick={add}>
              Add it
            </button>
            <button onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}

      <Drawer open={!!blocking} onClose={() => setBlocking(null)}
              title="What is blocking it?"
              subtitle="A blocked item with no reason is one nobody can unblock">
        {blocking && (
          <BlockForm t={blocking} onDone={(reason) => {
            change(blocking.todo_id,
                   { status: "BLOCKED", blocked_reason: reason }, "Blocked");
            setBlocking(null);
          }} />
        )}
      </Drawer>
    </Card>
  );
}


function BlockForm({ t, onDone }) {
  const [reason, setReason] = useState("");
  return (
    <>
      <div className="rowsub wrap" style={{ marginBottom: 10 }}>{t.title}</div>
      <Field label="Blocked on" required>
        <textarea rows={3} value={reason}
                  placeholder="NCDMM has not answered the request for a text-bearing copy."
                  onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div style={{ marginTop: 10 }}>
        <button className="primary" disabled={!reason.trim()}
                onClick={() => onDone(reason.trim())}>Record it</button>
      </div>
    </>
  );
}


/* ── Of everything outstanding, what nobody has taken ────────────────

   By kind, not as one list. There are 1,089 outstanding items on the live
   record and 263 of them are one kind; printing them flat produces a page
   nobody reads, which is the same defect the evidence screen had when
   thirty-two unread workbooks buried three real proposals. The counts are
   the answer most of the time, and the rows are there when somebody wants
   to work one kind down. */
function Covering({ canWrite, toast }) {
  const [d, setD] = useState(null);
  const [open, setOpen] = useState(null);
  const [taking, setTaking] = useState(null);
  const load = useCallback(async () => setD(await api.todoCovering()), []);
  useEffect(() => { load(); }, [load]);
  if (!d) return null;

  const byKind = {};
  for (const i of d.items) {
    const k = (byKind[i.kind] ||= {
      kind: i.kind, severity: i.severity, portfolio: i.owner_portfolio,
      goes_to: i.goes_to, n: 0, taken: 0, items: [],
    });
    k.n += 1;
    if (i.taken) k.taken += 1;
    k.items.push(i);
  }
  const kinds = Object.values(byKind).sort((a, b) => b.n - a.n);

  return (
    <>
      <Card variant="quiet" style={{ marginBottom: 12 }}>
        <div className="grid three">
          <Stat label="Outstanding" value={d.outstanding} note="the system found these" />
          <Stat label="Somebody has it" value={d.taken} note="with a name and a date" />
          <Stat label="Nobody has it" value={d.nobody_has_it}
                note="routed to a portfolio, and no further" />
        </div>
        <div className="rowsub" style={{ marginTop: 10 }}>
          The worklist has always known <em>what</em> is outstanding, and which
          portfolio can act on each kind. Neither could say <em>who</em> is
          doing it or <em>by when</em>, because nothing in the system could
          write that down. Taking an item puts a name and a date on it.
        </div>
      </Card>

      <Table columns={[
        { label: "", width: 30, align: "left" },
        { label: "Kind", align: "left" },
        { label: "Outstanding" },
        { label: "Taken" },
        { label: "Whose", align: "left" },
        { label: "Dealt with on", align: "left" },
      ]}>
        {kinds.map((k) => (
          <tr key={k.kind} className="hoverable" style={{ cursor: "pointer" }}
              onClick={() => setOpen(open === k.kind ? null : k.kind)}>
            <td className="l">
              <Tick state={k.taken === k.n ? "done"
                           : k.severity === "BLOCKING" ? "failed" : "open"} />
            </td>
            <td className="l"><strong>{KINDS[k.kind]?.title || k.kind}</strong>
              <div className="rowsub">{k.kind}</div></td>
            <td className="amt">{k.n}</td>
            <td className={k.taken ? "amt" : "amt rowsub"}>{k.taken || "—"}</td>
            <td className="l rowsub">{k.portfolio}</td>
            <td className="l rowsub">{k.goes_to}</td>
          </tr>
        ))}
      </Table>

      {open && (
        <Card variant="quiet" title={KINDS[open]?.title || open}
              aside={`${byKind[open].n} outstanding`} style={{ marginTop: 12 }}>
          {KINDS[open]?.why && (
            <div className="rowsub wrap" style={{ marginBottom: 10 }}>
              {KINDS[open].why} {KINDS[open].where}
            </div>
          )}
          <Table columns={[
            { label: "", width: 30, align: "left" },
            { label: "What", align: "left" },
            { label: "Who has it", align: "left" },
            { label: "", width: 90, align: "left" },
          ]}>
            {byKind[open].items.slice(0, 40).map((i) => (
              <tr key={`${i.kind}:${i.entity_id}`}>
                <td className="l"><Tick state={i.taken ? "done" : "open"} /></td>
                <td className="l wrap">{i.label}
                  {i.detail && <div className="rowsub wrap">{i.detail}</div>}</td>
                <td className="l rowsub">
                  {i.assignee || (i.taken ? <span className="warnish">nobody named</span>
                                          : <span className="rowsub">—</span>)}
                  {i.due_on && <div>by {i.due_on}</div>}
                </td>
                <td className="l">
                  {canWrite && !i.taken && (
                    <button className="sm" onClick={() => setTaking(i)}>Take it</button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
          {byKind[open].n > 40 && (
            <div className="rowsub" style={{ marginTop: 8 }}>
              {byKind[open].n - 40} more of this kind. Working down from the top
              is the point; a page that prints all {byKind[open].n} is one
              nobody reads.
            </div>
          )}
        </Card>
      )}

      <Drawer open={!!taking} onClose={() => setTaking(null)} title="Take it on"
              subtitle="A name and a date, against the item the system found">
        {taking && (
          <TakeForm item={taking} onDone={async (body) => {
            try {
              await api.openTodo({
                ...body,
                worklist_kind: taking.kind,
                worklist_entity_id: taking.entity_id,
              });
              toast.ok("Taken");
              setTaking(null);
              load();
            } catch (e) { toast.fail(String(e.message || e)); }
          }} />
        )}
      </Drawer>
    </>
  );
}


function TakeForm({ item, onDone }) {
  const [f, setF] = useState({
    title: item.label || item.kind, assignee: "", due_on: "",
  });
  return (
    <>
      <div className="rowsub wrap" style={{ marginBottom: 10 }}>
        <Pill>{item.kind}</Pill> {item.detail}
      </div>
      <Field label="What somebody is going to do" required>
        <input value={f.title}
               onChange={(e) => setF({ ...f, title: e.target.value })} />
      </Field>
      <div className="grid two" style={{ marginTop: 10 }}>
        <Field label="Who">
          <input value={f.assignee} placeholder="employee key"
                 onChange={(e) => setF({ ...f, assignee: e.target.value })} />
        </Field>
        <Field label="By when">
          <input type="date" value={f.due_on}
                 onChange={(e) => setF({ ...f, due_on: e.target.value })} />
        </Field>
      </div>
      <div style={{ marginTop: 12 }}>
        <button className="primary" disabled={!f.title.trim()}
                onClick={() => onDone({
                  title: f.title.trim(),
                  assignee: f.assignee.trim() || null,
                  due_on: f.due_on || null,
                })}>Take it on</button>
      </div>
    </>
  );
}


/* ── Setting one up, in one act ────────────────────────────────────── */
function Setup({ f, setF, toast, onDone }) {
  const [people, setPeople] = useState([{ employee_key: "", reason: "" }]);
  const [todos, setTodos] = useState([{ title: "", due_on: "" }]);
  const [awards, setAwards] = useState([]);
  useEffect(() => {
    api.contracts?.().then((d) => setAwards(d.contracts || [])).catch(() => {});
  }, []);

  const go = async () => {
    try {
      const got = await api.openProject({
        objective_id: f.objective_id.trim(),
        name: f.name.trim(),
        summary: f.summary,
        award_id: f.award_id || null,
        starts_on: f.starts_on || null,
        ends_on: f.ends_on || null,
        label: f.name.trim(),
        is_federal: Boolean(f.award_id),
        cfda: f.cfda || null,
        people: people.filter((p) => p.employee_key.trim() && p.reason.trim()),
        todos: todos.filter((t) => t.title.trim())
                    .map((t) => ({ title: t.title.trim(), due_on: t.due_on || null })),
        reason: f.reason.trim(),
      });
      toast.ok(`${got.objective_id} set up — ${got.people.length} person(s), `
               + `${got.todos} thing(s) to do`
               + (got.gate_live ? "" : " · nobody assigned, so the authority gate is off"));
      onDone();
    } catch (e) { toast.fail(String(e.message || e)); }
  };

  return (
    <>
      <div className="grid two">
        <Field label="Charge code" required>
          <input value={f.objective_id} placeholder="DRIVE-AM"
                 onChange={(e) => setF({ ...f, objective_id: e.target.value })} />
        </Field>
        <Field label="Contract">
          <select value={f.award_id}
                  onChange={(e) => setF({ ...f, award_id: e.target.value })}>
            <option value="">none</option>
            {awards.map((a) => (
              <option key={a.award_id} value={a.award_id}>
                {a.award_id} — {a.sponsor}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {/* The code IS the project — not a foreign key to one. A project id
          that could differ from an objective id is two names for one thing,
          and somebody would eventually ask which is right. */}
      <div className="rowsub" style={{ marginTop: 4 }}>
        The charge code is the project. An hour and a dollar spent on this
        work land in the same place because there is only one place.
      </div>

      <div style={{ marginTop: 12 }}>
        <Field label="Name" required>
          <input value={f.name} placeholder="Drive AM — additive manufacturing transition"
                 onChange={(e) => setF({ ...f, name: e.target.value })} />
        </Field>
      </div>
      <div style={{ marginTop: 10 }}>
        <Field label="What it is">
          <textarea rows={2} value={f.summary}
                    onChange={(e) => setF({ ...f, summary: e.target.value })} />
        </Field>
      </div>
      <div className="grid two" style={{ marginTop: 10 }}>
        <Field label="Starts"><input type="date" value={f.starts_on}
          onChange={(e) => setF({ ...f, starts_on: e.target.value })} /></Field>
        <Field label="Ends"><input type="date" value={f.ends_on}
          onChange={(e) => setF({ ...f, ends_on: e.target.value })} /></Field>
      </div>

      <Card variant="quiet" title="Who may charge it" style={{ marginTop: 14 }}>
        <div className="rowsub" style={{ marginBottom: 8 }}>
          Assign one person and the authority gate turns on for this code.
          Nobody puts themselves on it — an assignment is a statement by one
          person about another, and one made by its own beneficiary says
          nothing.
        </div>
        {people.map((p, i) => (
          <div className="grid two" key={i} style={{ marginBottom: 8 }}>
            <input value={p.employee_key} placeholder="employee key"
                   onChange={(e) => setPeople(people.map((x, j) =>
                     j === i ? { ...x, employee_key: e.target.value } : x))} />
            <input value={p.reason} placeholder="why they are on it"
                   onChange={(e) => setPeople(people.map((x, j) =>
                     j === i ? { ...x, reason: e.target.value } : x))} />
          </div>
        ))}
        <button className="sm"
                onClick={() => setPeople([...people, { employee_key: "", reason: "" }])}>
          Another
        </button>
      </Card>

      <Card variant="quiet" title="First things to do" style={{ marginTop: 14 }}>
        {todos.map((t, i) => (
          <div className="grid two" key={i} style={{ marginBottom: 8 }}>
            <input value={t.title} placeholder="what needs doing"
                   onChange={(e) => setTodos(todos.map((x, j) =>
                     j === i ? { ...x, title: e.target.value } : x))} />
            <input type="date" value={t.due_on}
                   onChange={(e) => setTodos(todos.map((x, j) =>
                     j === i ? { ...x, due_on: e.target.value } : x))} />
          </div>
        ))}
        <button className="sm"
                onClick={() => setTodos([...todos, { title: "", due_on: "" }])}>
          Another
        </button>
      </Card>

      <div style={{ marginTop: 14 }}>
        <Field label="Why this is being set up" required>
          <textarea rows={2} value={f.reason}
                    placeholder="A reviewer reads this next to the code it opened."
                    onChange={(e) => setF({ ...f, reason: e.target.value })} />
        </Field>
      </div>
      <div style={{ marginTop: 12 }}>
        <button className="primary"
                disabled={!f.objective_id.trim() || !f.name.trim() || !f.reason.trim()}
                onClick={go}>Set it up</button>
      </div>
    </>
  );
}
