import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { Card, Empty, Field, PageHead, Pill, Segmented, Stat, Table, useToast } from "../components/ui.jsx";
import TimeRoster from "./TimeRoster.jsx";

/*
  The employee's own record of their own time.

  Two ways in, because reconstructing a year and keeping this week are
  different jobs. The month calendar is for finding your way around 2025 and
  seeing what is still blank. The week grid is for filling it in: objectives
  down, days across, one basis for the week, because that is how a person
  actually works from a calendar — a week at a time.

  What the screen never does is let someone say a record is contemporaneous
  when it is not. That follows from the date, and the date is not an opinion.
*/

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"];

const iso = (d) => d.toISOString().slice(0, 10);
const parse = (s) => new Date(s + "T00:00:00");
const money = (v) => Number(v ?? 0).toLocaleString(undefined,
  { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const hours = (v) => Number(v ?? 0).toLocaleString(undefined, {
  minimumFractionDigits: Number(v ?? 0) % 1 === 0 ? 0 : 2,
  maximumFractionDigits: 2 });

/* The grades are enum names in the database and sentences to a person. */
const GRADE = {
  VERIFIED: "verified",
  CORROBORATED: "contemporaneous",
  MANAGEMENT_RECONSTRUCTION: "reconstruction",
  TEST_ASSUMPTION: "test assumption",
  UNSUPPORTED: "unsupported",
};

/* Monday-based week containing d. */
function weekStart(d) {
  const c = new Date(d);
  const shift = (c.getDay() + 6) % 7;
  c.setDate(c.getDate() - shift);
  return c;
}
function addDays(d, n) {
  const c = new Date(d);
  c.setDate(c.getDate() + n);
  return c;
}

/* The grid of a month, padded to whole Monday weeks. */
function monthGrid(year, month) {
  const first = new Date(year, month, 1);
  const start = weekStart(first);
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const d = addDays(start, i);
    cells.push({ date: d, inMonth: d.getMonth() === month });
    if (i >= 34 && addDays(start, i + 1).getMonth() !== month) break;
  }
  return cells;
}

export default function Timesheet({ actor }) {
  /* An account with no employee behind it — the controller, the auditor — has
     no timesheet of its own. It gets the roster instead, and can open anyone's
     sheet from there to read. */
  const [viewing, setViewing] = useState(null);

  /* Donated time sits above both, because it is the organisation's record
     rather than this sheet's — and because the person who has to value it is
     very often the one with no timesheet of their own.
     `Donated` lived inside `Sheet` for about ten minutes, which meant Tom —
     a controller with no payroll key — could not see it at all, and the
     worklist item pointing him here would have sent him to a screen with
     nothing on it. The same defect as a nav stricter than the API, one
     component further in. */
  const [given, setGiven] = useState(null);
  const loadGiven = useCallback(
    () => api.donations().then(setGiven).catch(() => setGiven(null)), []);
  useEffect(() => { loadGiven(); }, [loadGiven]);

  const donated = given && given.people.length > 0 && (
    <Donated given={given} actor={actor} onDone={loadGiven} />
  );

  if (!actor?.employee_key && !viewing) {
    return <>{donated}<TimeRoster onOpen={setViewing} /></>;
  }
  return <>{donated}
    <Sheet actor={actor} viewing={viewing} onBack={() => setViewing(null)} />
  </>;
}

function Sheet({ actor, viewing, onBack }) {
  const toast = useToast();
  const [mode, setMode] = useState("week");
  const [vocab, setVocab] = useState(null);
  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [cursor, setCursor] = useState(() => new Date(2025, 2, 3));
  const [basis, setBasis] = useState("CALENDAR");
  const [openDay, setOpenDay] = useState(null);
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState("");

  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const wkStart = weekStart(cursor);

  const range = mode === "week"
    ? { start: iso(wkStart), end: iso(addDays(wkStart, 6)) }
    : { start: iso(new Date(year, month, 1)), end: iso(new Date(year, month + 1, 0)) };

  const who = viewing ? { employee_key: viewing } : {};

  const load = useCallback(async () => {
    try {
      const [d, s] = await Promise.all([
        api.timesheetEntries({ ...range, ...who }),
        api.timesheetSummary(who),
      ]);
      setData(d); setSummary(s); setError("");
    } catch (e) {
      setError(String(e.message || e));
    }
    /* The draft is only ever the caller's own — `adopt` writes under the
       calling actor and takes no employee key, so offering it while reading
       somebody else's sheet would be a button that cannot mean what it says.
       It is loaded separately from the pair above because a person with no
       reconstruction is a normal state and must not blank the screen. */
    if (viewing) { setDraft(null); return; }
    try {
      setDraft(await api.timesheetDraft());
    } catch {
      setDraft(null);
    }
  }, [range.start, range.end, viewing]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { api.timesheetObjectives().then(setVocab).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);


  /* Entries indexed by day and objective, so a cell is a lookup. */
  const byCell = useMemo(() => {
    const m = new Map();
    (data?.entries || []).forEach((e) => m.set(`${e.work_date}|${e.objective_id}`, e));
    return m;
  }, [data]);

  const dayTotals = useMemo(() => {
    const m = new Map();
    (data?.days || []).forEach((d) => m.set(d.work_date, Number(d.hours)));
    return m;
  }, [data]);

  /* Rows in the week grid: everything used this period, plus anything already
     on this week, so a line never disappears out from under you mid-entry. */
  const rows = useMemo(() => {
    const used = new Set((summary?.distribution || []).map((d) => d.objective_id));
    (data?.entries || []).forEach((e) => used.add(e.objective_id));
    const all = vocab?.objectives || [];
    const chosen = all.filter((o) => used.has(o.objective_id));
    return chosen.length ? chosen : all.filter((o) => o.is_final).slice(0, 5);
  }, [vocab, summary, data]);

  async function save(workDate, objectiveId, value) {
    const n = Number(value);
    try {
      if (!value || n === 0) {
        await api.removeTime({ work_date: workDate, objective_id: objectiveId });
      } else {
        await api.putTime({ work_date: workDate, objective_id: objectiveId,
                            hours: n, basis });
      }
      await load();
    } catch (e) {
      const msg = String(e.message || e).replace(/^\d+:\s*/, "");
      let detail = msg;
      try {
        const parsed = JSON.parse(msg);
        detail = parsed.detail?.message || parsed.detail || msg;
      } catch { /* not JSON, use it as it stands */ }
      toast(detail, { tone: "bad", sticky: true });
      await load();
    }
  }

  if (error) return <Empty mark="!" title="Could not load">{error}</Empty>;
  if (!data || !vocab) return <Empty mark="…" title="Loading" />;

  const editable = data.editable;
  const chargeable = summary?.chargeable_hours || 0;
  const leave = summary?.leave_hours || 0;
  const status = summary?.status || {};

  return (
    <div className="dash">
      <PageHead
        title={viewing ? `${viewing}'s timesheet` : "Timesheet"}
        aside={
          <>
            {status.certified && !status.stale && <Pill tone="good">Certified</Pill>}
            {status.certified && status.stale && <Pill tone="fail">Signature stale</Pill>}
            {!status.certified && <Pill>Not yet certified</Pill>}
          </>
        }>
        {data.employee_key} · {data.period} ·{" "}
        {editable
          ? "your own record of your own time"
          : "read only — a timesheet is only ever kept by the person whose time it is"}
        {viewing && (
          <>{" · "}<button className="linkish" onClick={onBack}>back to the roster</button></>
        )}
      </PageHead>

      <Card variant="raised">
        <div className="stat-row">
          <Stat label="Chargeable hours" size="xl" value={hours(chargeable)} />
          <Stat label="Paid leave" value={hours(leave)}
                note="recorded, not in the base" />
          <Stat label="Objectives" value={(summary?.distribution || []).length} />
          <Stat label="This view"
                value={hours((data.days || []).reduce((a, d) => a + Number(d.hours), 0))}
                note={`${range.start} to ${range.end}`} />
        </div>
      </Card>

      {(summary?.months || []).some((m) => Number(m.expected_hours) > 0) && (
        <Card title="Month by month"
              aside="Where the gap is, rather than one number at the bottom">
          <div className="month-strip">
            {summary.months.map((m) => {
              const cov = m.coverage === null ? null : Number(m.coverage);
              return (
                <button key={m.month_label} className="month-cell"
                        onClick={() => { setMode("month");
                                         setCursor(new Date(m.month_label.replace(" ", " 1, "))); }}>
                  <span className="month-name">{m.month_label.slice(0, 3)}</span>
                  <span className="month-hours num">{hours(m.entered_hours)}</span>
                  <span className="month-bar-track">
                    <span className={`month-bar ${cov !== null && cov < 0.9 ? "short" : ""}`}
                          style={{ width: `${Math.min(100, (cov || 0) * 100)}%` }} />
                  </span>
                  <span className="quiet small">
                    {cov === null ? "—" : `${(cov * 100).toFixed(0)}%`}
                  </span>
                </button>
              );
            })}
          </div>
        </Card>
      )}

      <div className="ts-bar">
        <Segmented value={mode} onChange={setMode}
                   options={[["week", "Week"], ["month", "Month"]]} />
        <div className="ts-nav">
          <button className="sm" onClick={() => setCursor(addDays(cursor, mode === "week" ? -7 : -31))}>←</button>
          <span className="ts-when">
            {mode === "week"
              ? `${wkStart.toLocaleDateString(undefined, { day: "numeric", month: "short" })} – ${addDays(wkStart, 6).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}`
              : `${MONTHS[month]} ${year}`}
          </span>
          <button className="sm" onClick={() => setCursor(addDays(cursor, mode === "week" ? 7 : 31))}>→</button>
        </div>
        {editable && (
          <label className="ts-basis">
            <span className="quiet small">What are you working from?</span>
            <select value={basis} onChange={(e) => setBasis(e.target.value)}>
              {vocab.bases.map((b) => (
                <option key={b.basis} value={b.basis}>{b.label}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      {editable && (
        <p className="quiet small ts-note">
          {vocab.bases.find((b) => b.basis === basis)?.detail}{" "}
          Anything entered more than {vocab.contemporaneous_days} days after the
          day worked is recorded as a reconstruction — that follows from the
          dates, not from what anyone says about it.
        </p>
      )}

      {mode === "week" ? (
        <Card title="Hours" aside={editable ? "Tab across, Enter to save" : ""}>
          <div className="table-wrap">
            <table className="ts-grid">
              <thead>
                <tr>
                  <th className="l">Objective</th>
                  {DAY_NAMES.map((n, i) => {
                    const d = addDays(wkStart, i);
                    return (
                      <th key={n} className={i > 4 ? "ts-weekend" : ""}>
                        {n}<span className="ts-dnum">{d.getDate()}</span>
                      </th>
                    );
                  })}
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((o) => {
                  const week = DAY_NAMES.map((_, i) =>
                    byCell.get(`${iso(addDays(wkStart, i))}|${o.objective_id}`));
                  const total = week.reduce((a, e) => a + Number(e?.hours || 0), 0);
                  return (
                    <tr key={o.objective_id}>
                      <td className="l">
                        <span className="strong">{o.objective_id}</span>
                        <div className="quiet small">{o.label}</div>
                      </td>
                      {week.map((e, i) => {
                        const d = iso(addDays(wkStart, i));
                        return (
                          <td key={d} className={i > 4 ? "ts-weekend" : ""}>
                            <input
                              className="ts-cell num"
                              defaultValue={e ? String(Number(e.hours)) : ""}
                              key={`${d}|${o.objective_id}|${e?.entry_id || 0}`}
                              disabled={!editable}
                              inputMode="decimal"
                              aria-label={`${o.objective_id} on ${d}`}
                              title={e?.note || ""}
                              onKeyDown={(ev) => { if (ev.key === "Enter") ev.target.blur(); }}
                              onBlur={(ev) => {
                                const was = e ? String(Number(e.hours)) : "";
                                if (ev.target.value.trim() !== was) {
                                  save(d, o.objective_id, ev.target.value.trim());
                                }
                              }} />
                          </td>
                        );
                      })}
                      <td className="num strong">{total ? hours(total) : ""}</td>
                    </tr>
                  );
                })}
                <tr className="ts-foot">
                  <td className="l quiet">Day total</td>
                  {DAY_NAMES.map((_, i) => {
                    const d = iso(addDays(wkStart, i));
                    const t = dayTotals.get(d) || 0;
                    return (
                      <td key={d} className={`num ${i > 4 ? "ts-weekend" : ""}`}>
                        {t ? hours(t) : ""}
                      </td>
                    );
                  })}
                  <td className="num strong">
                    {hours((data.days || []).reduce((a, d) => a + Number(d.hours), 0))}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          {editable && (
            <ObjectivePicker vocab={vocab} rows={rows}
                             onPick={(id) => save(iso(wkStart), id, "")} />
          )}
        </Card>
      ) : (
        <Card title={`${MONTHS[month]} ${year}`}
              aside="Click a day to see what is on it">
          <div className="cal">
            {DAY_NAMES.map((n) => <div key={n} className="cal-head">{n}</div>)}
            {monthGrid(year, month).map(({ date, inMonth }) => {
              const d = iso(date);
              const t = dayTotals.get(d) || 0;
              const weekend = date.getDay() === 0 || date.getDay() === 6;
              return (
                <button key={d}
                        className={`cal-day ${inMonth ? "" : "out"} ${weekend ? "wknd" : ""} ${t ? "has" : ""} ${openDay === d ? "on" : ""}`}
                        onClick={() => setOpenDay(openDay === d ? null : d)}>
                  <span className="cal-num">{date.getDate()}</span>
                  {t > 0 && <span className="cal-hours num">{hours(t)}</span>}
                  {t > 0 && (
                    <span className="cal-bar"
                          style={{ width: `${Math.min(100, (t / 8) * 100)}%` }} />
                  )}
                </button>
              );
            })}
          </div>

          {openDay && (
            <DayPanel day={openDay}
                      entries={(data.entries || []).filter((e) => e.work_date === openDay)}
                      onClose={() => setOpenDay(null)} />
          )}
        </Card>
      )}

      {editable && !viewing && (
        <DraftCard draft={draft} onDone={load} />
      )}

      {editable && <SubmitCard summary={summary} onDone={load} />}

      <Card title="What this adds up to"
            aside="Leave is recorded but left out of the base — it is not a final cost objective">
        {(summary?.distribution || []).length === 0 ? (
          <Empty mark="—" title="Nothing entered yet">
            Enter a week and it will appear here as a distribution you can certify.
          </Empty>
        ) : (
          <Table columns={[
            { label: "Objective", align: "left" }, { label: "Hours" },
            { label: "Share" }, { label: "Days" },
            { label: "Grade", align: "left" }, { label: "Mean lag" },
          ]}>
            {summary.distribution.map((d) => (
              <tr key={d.objective_id}>
                <td className="l">
                  <span className="strong">{d.objective_id}</span>
                  <div className="quiet small">{d.objective_label}</div>
                </td>
                <td className="num">{hours(d.hours)}</td>
                <td className="num">
                  {chargeable ? `${((d.hours / chargeable) * 100).toFixed(1)}%` : "—"}
                </td>
                <td className="num">{d.days}</td>
                <td className="l quiet small">
                  {GRADE[d.weakest_grade] || d.weakest_grade}
                </td>
                <td className="num quiet small">{d.mean_lag_days} d</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {(summary?.variance || []).length > 0 && (
        <Card title="Where your record differs from the reconstruction"
              variant="raised"
              aside="For the controller to look at, not for either side to overwrite">
          <p className="quiet small">
            The 2025 distribution was rebuilt from payroll and hours logs before
            you filled this in. Where your own record disagrees with it, both
            stay on the file and the difference is shown.
          </p>
          <Table columns={[
            { label: "Objective", align: "left" }, { label: "Your hours" },
            { label: "Your share" }, { label: "Reconstructed" },
            { label: "Difference" }, { label: "In wages" },
          ]}>
            {summary.variance.map((v) => (
              <tr key={v.objective_id}>
                <td className="l strong">{v.objective_id}</td>
                <td className="num">{v.timesheet_hours ? hours(v.timesheet_hours) : "—"}</td>
                <td className="num">{(v.timesheet_share * 100).toFixed(1)}%</td>
                <td className="num">{(v.reconstructed_share * 100).toFixed(1)}%</td>
                <td className={`num ${v.share_variance < 0 ? "amt neg" : ""}`}>
                  {(v.share_variance * 100).toFixed(1)}%
                </td>
                <td className={`num ${v.wage_variance < 0 ? "amt neg" : ""}`}>
                  {money(v.wage_variance)}
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

/* Calling the sheet finished is a separate act from filling it in, and it is
   the act that makes the timesheet speak for the year instead of the
   controller's reconstruction. So it says what it is claiming, in hours. */
/*
  The controller's reconstruction, shown to the person whose work it was.

  2 CFR 200.430(i) does not require a contemporaneous record — it requires one
  that reflects the work actually performed, supported, and reviewed after the
  fact. A reconstruction the person reads, corrects and signs meets that; a
  reconstruction nobody ever saw does not, which is where 2025 has been
  sitting: 43 people, zero entries, zero certifications.

  So this is a **proposal**, in the same sense every other proposal in this
  system is one. Nothing here is on the sheet. Adopting writes it under the
  person's own name, and the router takes no employee key, because nobody
  enters time for anybody else.

  Two rules the restatement screen already follows, and this one keeps:

  - **"Not yet, because", never an empty list.** Where the draft cannot be
    adopted the server says why, and the reason is the work — usually that
    nobody has recorded the employment terms the hours are divided by.
  - **Nothing is computed here.** Every figure is read from the answer,
    including the hours, the working days and the share. A screen that
    divided the shares itself would be a second implementation of the
    distribution, free to disagree with the one that gets written.
*/
function DraftCard({ draft, onDone }) {
  const toast = useToast();
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  if (!draft) return null;

  const lines = draft.lines || [];
  const alreadyEntered = Number(draft.already_entered || 0);
  /* Adopted is read from the sheet rather than remembered in this component:
     a flag set on success would be wrong the moment somebody reloads, and
     the answer is already on the record. Every proposed hour is on the sheet
     when the entered total has reached what the draft proposes. */
  const proposed = lines.reduce((a, l) => a + Number(l.hours || 0), 0);
  const adopted = proposed > 0 && alreadyEntered >= proposed - 0.005;

  async function adopt() {
    setBusy(true);
    try {
      const r = await api.adoptDraft({ acknowledged: true });
      toast(`Adopted — ${hours(r.hours)} hours across ${r.working_days} working days`,
            { tone: "ok" });
      setAck(false);
      await onDone();
    } catch (e) {
      const msg = String(e.message || e).replace(/^\d+:\s*/, "");
      let detail = msg;
      try { detail = JSON.parse(msg).detail || msg; } catch { /* plain text */ }
      toast(typeof detail === "string" ? detail : JSON.stringify(detail),
            { tone: "fail", sticky: true });
    }
    setBusy(false);
  }

  /* Not adoptable is the ordinary state until the roster reply comes back,
     and it is worth as much screen as the adoptable one: the sentence names
     the thing somebody has to go and get. */
  if (!draft.adoptable) {
    return (
      <Card title="The reconstruction of your year"
            aside="Not yet — and here is why">
        <p className="quiet small">{draft.because}</p>
      </Card>
    );
  }

  return (
    <Card title="The reconstruction of your year" variant="raised"
          aside={`${hours(draft.expected_hours)} contracted hours · ${draft.working_days} working days`}>
      <p className="quiet small">{draft.because}</p>

      {adopted && (
        <p className="quiet small">
          You have adopted this. It is on your sheet above as your own record —
          correct any day that is wrong, then submit. Adopting again would be
          refused, because the hours are already there.
        </p>
      )}
      {!adopted && alreadyEntered > 0 && (
        <p className="quiet small">
          You already have {hours(alreadyEntered)} hours on this sheet.
          Adopting adds the reconstruction alongside them and will be refused
          where the two land on the same day and objective — so correct or
          remove those first if you want the reconstruction to stand instead.
        </p>
      )}

      <Table columns={[
        { label: "Objective", align: "left" }, { label: "Share" },
        { label: "Hours" }, { label: "Grade", align: "left" },
      ]}>
        {lines.map((l) => (
          <tr key={l.objective_id}>
            <td className="l"><strong>{l.objective_id}</strong></td>
            <td className="num">{(Number(l.share) * 100).toFixed(1)}%</td>
            <td className="num">{hours(l.hours)}</td>
            <td className="l quiet small">{GRADE[l.grade] || l.grade}</td>
          </tr>
        ))}
      </Table>

      <p className="quiet small">
        {draft.from_hours_log
          ? <>Adopting records these as <strong>recalled</strong>, each
              month&apos;s hours placed in that month and spread across its
              working days — about {hours(draft.hours_per_day)} a day. It is
              not a diary, but the months are yours: they come from the hours
              log, not from a figure smeared over the year.</>
          : <>Adopting records these as <strong>recalled</strong>, spread
              evenly across the {draft.working_days} working days — about{" "}
              {hours(draft.hours_per_day)} a day. There is no month-by-month
              record of your hours, so this is the year&apos;s distribution
              and it says so rather than pretending to a shape it has not
              got.</>}
      </p>

      {(draft.months || []).length > 0 && (
        <Table columns={[
          { label: "Month", align: "left" }, { label: "Work days" },
          { label: "Available" }, { label: "On the log" },
          { label: "Objectives" },
        ]}>
          {draft.months.map((m) => (
            <tr key={m.month_start}>
              <td className="l">{m.month}</td>
              <td className="num">{m.days}</td>
              <td className="num">{hours(m.available)}</td>
              <td className="num">{hours(m.hours)}</td>
              <td className="num">{m.lines.length}</td>
            </tr>
          ))}
        </Table>
      )}

      {/* **Contracted hours are not project hours**, and a sheet that spends
          all of them on cost objectives says nobody took a day off all year.
          The public holidays are the part the record can defend; the rest is
          the person's to correct, and saying so is the whole point of
          showing them a draft. */}
      <div className="stat-row">
        <Stat label="Available" size="lg" value={hours(draft.available_hours)}
              note={`${draft.working_days} work days, YBI's calendar`} />
        <Stat label="On the log" value={hours(draft.work_hours)}
              note={draft.from_hours_log
                    ? `${(draft.months || []).length} months on file`
                    : "no monthly record"} />
        <Stat label="Contracted" value={hours(draft.expected_hours)}
              note="from your terms" />
      </div>
      {/* Not a failure — a caveat the reader must not miss. Warm, per the
          annotation rule: pencil, not traffic light. */}
      {draft.not_known && <p className="caveat">{draft.not_known}</p>}

      <button className="linkish" onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Where these figures come from"}
      </button>
      {open && (
        <div className="ts-draft-why">
          {lines.map((l) => (
            <p key={l.objective_id} className="quiet small">
              <strong>{l.objective_id}</strong> — {l.rationale}
              {l.source ? ` (${l.source})` : ""}
            </p>
          ))}
        </div>
      )}

      {/* **A button that would answer 409 is the lesson the nav already
          learned.** Once the reconstruction is on the sheet, adopting again
          is refused by the day-and-objective collision, so the card stops
          offering it and says what the state is instead. */}
      {!adopted && (
        <>
          <label className="cert-ack">
            <input type="checkbox" checked={ack}
                   onChange={(e) => setAck(e.target.checked)} />
            <span>
              I have read this and it is a fair record of my own work. I
              understand I can correct any day before I submit the sheet.
            </span>
          </label>
          <button className="btn primary" disabled={!ack || busy} onClick={adopt}>
            {busy ? "Adopting…" : "Adopt this as my sheet"}
          </button>
        </>
      )}
    </Card>
  );
}


function SubmitCard({ summary, onDone }) {
  const toast = useToast();
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [withdrawing, setWithdrawing] = useState(false);

  const cov = summary?.coverage;
  const submitted = summary?.submitted;
  const entered = Number(cov?.entered_hours || 0);
  /* The denominator comes from employment terms, which are payroll's fact and
     not the employee's to set. Without them there is nothing to measure a
     complete period against, and the sheet cannot be submitted. */
  const termsKnown = Boolean(cov?.terms_known);
  const expected = Number(cov?.expected_hours || 0);
  const share = expected ? entered / expected : 0;
  const min = summary?.min_coverage ?? 0.9;

  async function submit() {
    setBusy(true);
    try {
      const r = await api.submitTimesheet({ acknowledged: true });
      toast(`Submitted — ${(r.coverage * 100).toFixed(0)}% of the period`);
      await onDone();
    } catch (e) {
      const msg = String(e.message || e).replace(/^\d+:\s*/, "");
      let detail = msg;
      try { detail = JSON.parse(msg).detail || msg; } catch { /* plain text */ }
      toast(detail, { tone: "bad", sticky: true });
    }
    setBusy(false);
  }

  async function withdraw() {
    setBusy(true);
    try {
      await api.withdrawTimesheet({ reason });
      toast("Submission withdrawn. The reconstruction speaks again until you resubmit.");
      setWithdrawing(false); setReason("");
      await onDone();
    } catch (e) {
      toast(String(e.message || e), { tone: "bad" });
    }
    setBusy(false);
  }

  if (submitted) {
    return (
      <Card title="Submitted" variant="raised"
            aside={`${hours(cov.entered_hours)} hours · ${(Number(cov.submitted_coverage) * 100).toFixed(0)}% of the period`}>
        <p className="quiet small">
          This sheet now speaks for your 2025 in place of the reconstruction
          that was built for you. Editing it from here leaves it submitted and
          makes any certification you have signed stale, because the numbers
          behind the signature will have moved.
        </p>
        {withdrawing ? (
          <div className="ts-withdraw">
            <input value={reason} placeholder="Why you are taking it back"
                   onChange={(e) => setReason(e.target.value)} />
            <button className="btn" disabled={!reason.trim() || busy}
                    onClick={withdraw}>Withdraw</button>
            <button className="btn quiet" onClick={() => setWithdrawing(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button className="btn quiet" onClick={() => setWithdrawing(true)}>
            Withdraw the submission
          </button>
        )}
      </Card>
    );
  }

  return (
    <Card title="Is this sheet finished?" variant="raised">
      <p className="quiet small">
        Until you submit it, this is a work in progress and the controller's
        reconstruction still stands for your year. A part-filled sheet is not
        allowed to speak for the whole period — it would say the objectives you
        have reached so far were all of it.
      </p>
      {!termsKnown ? (
        <p className="amt neg">
          Nobody has recorded your employment terms for 2025, so there is
          nothing to measure a complete period against. Ask the controller to
          record your status, your contracted hours and the dates you worked.
        </p>
      ) : (
        <div className="stat-row">
          <Stat label="On the sheet" size="lg" value={hours(entered)} note="hours" />
          <Stat label="Your terms"
                value={`${Number(cov.weekly_hours)}h`}
                note={`${String(cov.statuses).toLowerCase().replace(/_/g, " ")}, ${cov.employed_from} → ${cov.employed_to}`} />
          <Stat label="Expected" value={hours(expected)} note="hours" />
          <Stat label="You have" value={`${(share * 100).toFixed(0)}%`}
                tone={share < min ? "fail" : undefined}
                note={share < min ? `${(min * 100).toFixed(0)}% needed` : "enough to submit"} />
        </div>
      )}
      <label className="cert-ack">
        <input type="checkbox" checked={ack}
               onChange={(e) => setAck(e.target.checked)} />
        <span>
          This is a complete record of the time I was compensated for in 2025,
          including the time I was not working on any project.
        </span>
      </label>
      <button className="btn primary"
              disabled={!ack || busy || !termsKnown || share < min}
              onClick={submit}>
        {busy ? "Submitting…" : "Submit the sheet"}
      </button>
    </Card>
  );
}

function ObjectivePicker({ vocab, rows, onPick }) {
  const [open, setOpen] = useState(false);
  const shown = new Set(rows.map((r) => r.objective_id));
  const rest = (vocab.objectives || []).filter((o) => !shown.has(o.objective_id));
  if (!rest.length) return null;
  return (
    <div className="ts-add">
      <button className="linkish" onClick={() => setOpen(!open)}>
        {open ? "−" : "+"} Add another objective
      </button>
      {open && (
        <div className="ts-add-list">
          {rest.map((o) => (
            <button key={o.objective_id} className="sm"
                    onClick={() => { onPick(o.objective_id); setOpen(false); }}>
              {o.objective_id}
              <span className="quiet small"> {o.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function DayPanel({ day, entries, onClose }) {
  const total = entries.reduce((a, e) => a + Number(e.hours), 0);
  return (
    <div className="day-panel">
      <div className="day-panel-head">
        <span className="strong">
          {parse(day).toLocaleDateString(undefined,
            { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
        </span>
        <span className="quiet">{hours(total)} hours</span>
        <div style={{ flex: 1 }} />
        <button className="sm" onClick={onClose}>Close</button>
      </div>
      {entries.length === 0 ? (
        <p className="quiet small">
          Nothing recorded. Switch to the week view to enter time.
        </p>
      ) : (
        <ul className="day-entries">
          {entries.map((e) => (
            <li key={e.entry_id}>
              <span className="strong">{e.objective_id}</span>
              <span className="num">{hours(e.hours)} h</span>
              <span className="quiet small">
                {e.timing.toLowerCase().replace("_", " ")} · {e.basis.toLowerCase().replace(/_/g, " ")}
                {e.lag_days > 0 && ` · recorded ${e.lag_days} days later`}
              </span>
              {e.note && <div className="quiet small">{e.note}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}


/* Hours given rather than paid, and what they are worth.
 *
 * They never enter the paid labour distribution — that would move every
 * other share — so they are valued separately or not at all.
 *
 * The rate is the controller's judgment and **never for their own hours**:
 * 2 CFR 200.306(e) wants a rate consistent with what YBI pays for similar
 * work, and that is a judgment about somebody's time rather than theirs to
 * make. The schema refuses it and so does the handler; this just does not
 * offer the box, so nobody meets a refusal they could not have predicted.
 */
function Donated({ given, actor, onDone }) {
  const [open, setOpen] = useState(null);
  const [rate, setRate] = useState("");
  const [basis, setBasis] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const isController = (actor?.portfolios || []).includes("CONTROLLER");
  const mine = (actor?.employee_key || "").toUpperCase();

  async function save(key) {
    setBusy(true);
    try {
      const r = await api.putDonationRate({
        employee_key: key, hourly_rate: rate, basis,
      });
      toast.ok(`${r.hours} donated hours valued at $${r.valued_at}`
               + (r.superseded ? " — the earlier rate is superseded" : ""));
      setOpen(null); setRate(""); setBasis("");
      await onDone();
    } catch (e) { toast.fail(String(e.message || e)); }
    setBusy(false);
  }

  return (
    <Card title="Donated time"
          aside={given.unvalued
            ? `${given.unvalued} person${given.unvalued === 1 ? "" : "s"} not yet valued`
            : `valued at $${Number(given.valued_total).toLocaleString()}`}>
      <p className="quiet small" style={{ marginTop: -4, marginBottom: 12 }}>
        Hours given rather than paid. They never enter the paid labour
        distribution — that would move every other share — so they are valued
        separately, at a rate consistent with what YBI pays for similar work
        (2 CFR 200.306(e)). Nobody values their own.
      </p>
      <Table columns={[
        { label: "Who", align: "left" },
        { label: "Hours" },
        { label: "Rate" },
        { label: "Worth" },
        { label: "On what basis", align: "left" },
      ]}>
        {given.people.map((p) => (
          <React.Fragment key={p.employee_key}>
            <tr>
              <td className="l strong">{p.employee_key}
                <div className="quiet small">
                  {p.objectives.map((o) => o.objective_id).join(", ")}
                </div>
              </td>
              <td className="num">{Number(p.hours).toFixed(2)}</td>
              <td className="num">{p.hourly_rate ? `$${p.hourly_rate}` : "—"}</td>
              <td className="num">
                {p.valued_at ? `$${Number(p.valued_at).toLocaleString()}`
                             : <span className="quiet">not valued</span>}
              </td>
              <td className="l wrap quiet small">
                {p.rate_basis || (
                  isController && p.employee_key !== mine ? (
                    <button className="btn sm"
                            onClick={() => { setOpen(p.employee_key); setRate(""); setBasis(""); }}>
                      Set the rate
                    </button>
                  ) : isController && p.employee_key === mine
                    ? "Yours to give, somebody else's to value."
                    : "Not yet valued."
                )}
              </td>
            </tr>
            {open === p.employee_key && (
              <tr className="subrow">
                <td className="l" colSpan={5}>
                  <div className="upload-form">
                    {/* The narrow column of `.upload-form` is 220px, so
                        the short label belongs to the short field. The
                        200.306(e) guidance is on the card above rather than
                        crammed into a hint that wraps to four lines. */}
                    <Field label="An hour is worth" hint="In dollars.">
                      <input value={rate} inputMode="decimal"
                             onChange={(e) => setRate(e.target.value)}
                             placeholder="72.50" />
                    </Field>
                    <Field label="On what basis"
                           hint="What YBI pays for similar work, or the labour market where it has no such work. This is what an auditor reads — 'market' is not a statement of anything, and the schema will not take it.">
                      <input value={basis} onChange={(e) => setBasis(e.target.value)}
                             placeholder="Comparable is programme delivery; Ohio market, 2025 survey." />
                    </Field>
                    <div className="upload-actions">
                      <button className="btn primary" disabled={busy || !rate || basis.length < 11}
                              onClick={() => save(p.employee_key)}>
                        {busy ? "Recording…" : "Record the rate"}
                      </button>
                      <button className="btn quiet" onClick={() => setOpen(null)}>Cancel</button>
                    </div>
                  </div>
                </td>
              </tr>
            )}
          </React.Fragment>
        ))}
      </Table>
    </Card>
  );
}
