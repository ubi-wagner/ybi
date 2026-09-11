import React, { useCallback, useEffect, useState } from "react";
import { api, money } from "../api.js";
import { Card, Drawer, Empty, PageHead, Pill, Stat, Table, Tick, useToast } from "../components/ui.jsx";

/* The roster, and the two things an administrator actually does with it.
 *
 * Set somebody up, and give or take away authority. Both are recorded
 * against the administrator who did them, with a reason, because a grant of
 * authority over the cost record is itself part of the record: a judgment
 * made in March by somebody whose portfolio ended in June was authorised
 * when it was made, and the file has to be able to show that.
 *
 * Two rules this screen makes visible rather than hiding:
 *
 *   Provisioning only runs downward. The role list offers what this
 *   administrator may actually create, which for an organisation
 *   administrator is not another organisation administrator.
 *
 *   Nobody grants themselves a portfolio. Your own row has no grant control
 *   on it, and the API refuses it too. */

const PORTFOLIOS = [
  ["CONTROLLER", "Controller", "Classify, import, reconcile — and seal. The only one that can fix the judgments and then produce a rate from them."],
  ["INVENTORY", "Inventory", "The asset register, equipment, what its use is worth by the hour."],
  ["PROJECT", "Project", "Awards and cost objectives, and what work belongs to them."],
  ["FACILITIES", "Facilities", "Buildings, space, occupancy, market rent."],
  ["OFFICE", "Office", "The document library: matching evidence to what it supports."],
];

const ROLE_NOTE = {
  SYSTEM_ADMIN: "Sets up the organisation's administrator. Not staff.",
  ORG_ADMIN: "Sets up controllers and employees. Holds no portfolio.",
  CONTROLLER: "Does the work of the system, according to the portfolios held.",
  EMPLOYEE: "Their own time, their own certification, their own documents.",
  AUDITOR: "Reads everything, writes nothing.",
};

export default function People({ actor }) {
  const [roster, setRoster] = useState([]);
  const [gaps, setGaps] = useState(null);
  const [view, setView] = useState("roster");
  const [creating, setCreating] = useState(null);
  const [granting, setGranting] = useState(null);
  const [amending, setAmending] = useState(null);
  const toast = useToast();

  const load = useCallback(() => {
    api.actors().then(setRoster).catch(() => setRoster([]));
    api.rosterGaps().then(setGaps).catch(() => setGaps(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  const mayCreate = actor.may_provision || [];
  const unset = roster.filter((r) => r.must_set_password && r.is_active);
  const unconfirmed = roster.filter((r) => !r.email_confirmed && r.is_active);

  return (
    <div className="page">
      <PageHead title="People">
        Who can sign in, what they may judge, and who let them in. An account
          is set up by somebody above it and never by a peer — and nobody,
          including you, grants themselves authority over the cost record.
      </PageHead>

      <div className="grid four">
        <Stat label="Accounts" value={roster.length} size="lg"
              note={`${roster.filter((r) => r.is_active).length} active`} />
        <Stat label="On payroll, no account"
              value={gaps?.without_account ?? "—"} size="lg"
              tone={gaps?.without_account ? "warn" : ""}
              note={gaps?.without_account ? "reconstructed on their behalf" : "everybody can sign in"} />
        <Stat label="Have not set a password yet" value={unset.length}
              tone={unset.length ? "warn" : ""}
              note={unset.length ? "can sign in; cannot record anything until they do"
                                 : "every password is its owner's"} />
        <Stat label="Address needs checking" value={unconfirmed.length}
              tone={unconfirmed.length ? "warn" : ""}
              note={unconfirmed.length
                ? "derived from the naming convention — they cannot sign in until it is right"
                : "every address is confirmed"} />
      </div>

      <div className="seg" role="tablist">
        {[["roster", `Roster (${roster.length})`],
          ["addresses", `Addresses to check (${unconfirmed.length})`],
          ["gaps", `Payroll without accounts (${gaps?.without_account ?? 0})`]]
          .map(([v, l]) => (
            <button key={v} role="tab" aria-selected={view === v}
                    className={view === v ? "on" : ""} onClick={() => setView(v)}>
              {l}
            </button>
          ))}
      </div>

      {view === "roster" && (
        <Card variant="raised" title="Accounts"
              aside={mayCreate.length
                ? <button className="btn primary"
                          onClick={() => setCreating({ role: mayCreate[0] })}>
                    Set somebody up
                  </button>
                : null}>
          <Table columns={[
            { label: "", align: "left", width: "34px" },
            { label: "Person", align: "left" },
            { label: "Rank", align: "left" },
            { label: "May judge", align: "left" },
            { label: "May read", align: "left" },
            { label: "Account", align: "left", width: "320px" },
            { label: "", align: "left", width: "92px" },
          ]}>
            {roster.map((r) => {
              const mine = r.actor_id === actor.actor_id;
              const canTouch = (actor.may_provision || []).includes(r.role);
              return (
                <tr key={r.actor_id}>
                  <td className="l">
                    <Tick state={!r.is_active ? "failed"
                                 : r.holds_bootstrap_password ? "flagged" : "done"}
                          title={!r.is_active ? "deactivated"
                                 : r.holds_bootstrap_password ? "password was issued to them"
                                 : "in good standing"} />
                  </td>
                  <td className="l">
                    <strong>{r.display_name}</strong>
                    <div className="rowsub">{r.email}</div>
                  </td>
                  <td className="l">
                    <Pill tone={r.role.endsWith("ADMIN") ? "warn" : ""}>
                      {r.role.replace("_", " ")}
                    </Pill>
                  </td>
                  <td className="l">
                    {(r.portfolios || []).length === 0
                      ? <span className="rowsub">nothing</span>
                      : (r.portfolios || []).map((p) => (
                          <Pill key={p} tone={p === "CONTROLLER" ? "accent" : ""}>{p}</Pill>
                        ))}
                  </td>
                  <td className="l">
                    {r.may_read_record
                      ? (r.record_access
                          ? <Pill tone="warn" >granted</Pill>
                          : <span className="rowsub">by rank</span>)
                      : <span className="rowsub">nothing</span>}
                    {r.record_access && (
                      <div className="rowsub">
                        by {r.record_access_granted_by_name}
                      </div>
                    )}
                  </td>
                  <td className="l rowsub wrap">
                    {!r.email_confirmed && (
                      <div><strong>address unchecked</strong></div>
                    )}
                    {r.must_set_password && (
                      <div>password not yet theirs</div>
                    )}
                    {r.employee_key
                      ? <>timesheet {r.employee_key}</>
                      : <>no timesheet</>}
                    <div>
                      by {r.provisioned_by_name || "seeding"} ·{" "}
                      {r.last_login_at
                        ? String(r.last_login_at).slice(0, 10)
                        : "never signed in"}
                    </div>
                  </td>
                  <td className="l">
                    {mine ? (
                      <span className="rowsub" title="Nobody grants themselves authority">
                        you
                      </span>
                    ) : canTouch ? (
                      <button className="btn sm" onClick={() => setGranting(r)}>
                        Access
                      </button>
                    ) : (
                      <span className="rowsub">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </Table>
        </Card>
      )}

      {view === "addresses" && (
        <Card title="Addresses derived from the naming convention">
          <p className="rowsub">
            Seeding the payroll produced an account for everybody who was paid
            in 2025, but the register carries surnames only — so these
            addresses were built from the pattern the known accounts use
            rather than looked up. Any that are wrong belong to somebody who
            cannot sign in, and because the payroll key is unique, the wrong
            account is sitting in the right one's place. Correcting the
            address in place is the fix; deleting an account never is.
          </p>
          {!unconfirmed.length ? (
            <Empty mark="✓" title="Every address has been checked" />
          ) : (
            <Table columns={[
              { label: "Person", align: "left" },
              { label: "Payroll", align: "left" },
              { label: "Address as derived", align: "left" },
              { label: "", align: "left", width: "92px" },
            ]}>
              {unconfirmed.map((r) => (
                <tr key={r.actor_id}>
                  <td className="l">{r.display_name}</td>
                  <td className="l rowsub">{r.employee_key}</td>
                  <td className="l rowsub">{r.email}</td>
                  <td className="l">
                    <button className="btn sm" onClick={() => setAmending(r)}>
                      Correct
                    </button>
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      )}

      {view === "gaps" && (
        <Card title="On the 2025 payroll, with no way to sign in">
          <p className="rowsub">
            {gaps?.note || ""} Until somebody has an account, their effort is
            reconstructed on their behalf from the controller's workbook, which
            is the weakest evidence in the file. An account turns that into a
            timesheet they keep and a certification they sign.
          </p>
          {!gaps?.people?.length ? (
            <Empty mark="✓" title="Everybody on the payroll can sign in" />
          ) : (
            <Table columns={[
              { label: "Employee", align: "left" },
              { label: "2025 wages" },
              { label: "Suggested email", align: "left" },
              { label: "", align: "left" },
            ]}>
              {gaps.people.map((p) => (
                <tr key={p.employee_key}>
                  <td className="l">{p.employee_name || p.employee_key}</td>
                  <td className="amt">{money(p.payroll_wages)}</td>
                  <td className="l rowsub">{p.suggested_email}</td>
                  <td className="l">
                    {mayCreate.includes("EMPLOYEE") && (
                      <button className="btn sm" onClick={() => setCreating({
                        role: "EMPLOYEE",
                        employee_key: p.employee_key,
                        display_name: p.employee_name || p.employee_key,
                        email: p.suggested_email,
                      })}>
                        Set up
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      )}

      {creating && (
        <CreateDrawer actor={actor} seed={creating} onClose={() => setCreating(null)}
                      onDone={(msg) => { toast.show(msg); setCreating(null); load(); }}
                      onError={(m) => toast.show(m, { tone: "fail" })} />
      )}
      {amending && (
        <AmendDrawer person={amending} onClose={() => setAmending(null)}
                     onDone={(msg) => { toast.show(msg); setAmending(null); load(); }}
                     onError={(m) => toast.show(m, { tone: "fail" })} />
      )}
      {granting && (
        <AccessDrawer actor={actor} person={granting} onClose={() => setGranting(null)}
                      onDone={(msg) => { toast.show(msg); setGranting(null); load(); }}
                      onError={(m) => toast.show(m, { tone: "fail" })} />
      )}
    </div>
  );
}

/* ── Setting somebody up ────────────────────────────────────────── */

function newPassword() {
  const words = ["ledger", "rampart", "quarry", "meridian", "tallow", "cobalt",
                 "lantern", "sable", "kestrel", "mortar", "juniper", "thistle",
                 "gantry", "vellum", "prairie", "copper", "wharf", "tempest"];
  const pick = () => words[Math.floor(Math.random() * words.length)];
  const digits = Array.from({ length: 5 },
    () => "23456789"[Math.floor(Math.random() * 8)]).join("");
  return [pick(), pick(), pick(), pick(), digits].join("-");
}

function CreateDrawer({ actor, seed, onClose, onDone, onError }) {
  const [email, setEmail] = useState(seed.email || "");
  const [name, setName] = useState(seed.display_name || "");
  const [role, setRole] = useState(seed.role);
  const [employeeKey, setEmployeeKey] = useState(seed.employee_key || "");
  const [portfolios, setPortfolios] = useState([]);
  const [reason, setReason] = useState("");
  const [password] = useState(newPassword);
  const [busy, setBusy] = useState(false);
  const [issued, setIssued] = useState(null);

  const mayCreate = actor.may_provision || [];
  const needsReason = portfolios.length > 0;
  const ready = email.includes("@") && name.trim() && !busy
    && (role !== "EMPLOYEE" || employeeKey.trim())
    && (!needsReason || reason.trim().length >= 10);

  async function submit() {
    setBusy(true);
    try {
      await api.createActor({
        email: email.trim().toLowerCase(), display_name: name.trim(), role,
        password, employee_key: employeeKey.trim() || null,
        portfolios, grant_reason: reason.trim(),
      });
      setIssued({ name: name.trim(), email: email.trim().toLowerCase(), password });
    } catch (err) {
      onError(String(err.message || err).replace(/^\d+:\s*/, ""));
      setBusy(false);
    }
  }

  if (issued) {
    return (
      <Drawer open title="Hand this over" subtitle={issued.name} onClose={() => onDone(`${issued.name} can sign in`)}>
        <p className="rowsub">
          This password will not be shown again. It works for signing in once;
          they will be asked to choose their own before they can record
          anything, which is what makes their name on a record mean something.
        </p>
        <div className="card quiet" style={{ padding: 16, marginTop: 12 }}>
          <div className="rowsub">Email</div>
          <div style={{ fontWeight: 600, marginBottom: 10 }}>{issued.email}</div>
          <div className="rowsub">Password</div>
          <div className="num" style={{ fontSize: 20, fontWeight: 600 }}>
            {issued.password}
          </div>
        </div>
        <button className="btn primary" style={{ marginTop: 14 }}
                onClick={() => onDone(`${issued.name} can sign in`)}>
          I have handed it over
        </button>
      </Drawer>
    );
  }

  return (
    <Drawer open title="Set somebody up" onClose={onClose}
            subtitle="They will choose their own password on first sign-in">
      <label className="field">
        <span className="field-label">Full name</span>
        <input value={name} onChange={(e) => setName(e.target.value)}
               placeholder="Heidi Ruby" autoFocus />
      </label>
      <label className="field">
        <span className="field-label">Email</span>
        <input value={email} onChange={(e) => setEmail(e.target.value)}
               placeholder="hruby@ybi.org" />
      </label>
      <label className="field">
        <span className="field-label">Rank</span>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {mayCreate.map((r) => (
            <option key={r} value={r}>{r.replace("_", " ")}</option>
          ))}
        </select>
        <span className="rowsub">{ROLE_NOTE[role]}</span>
      </label>
      <label className="field">
        <span className="field-label">
          Payroll key {role === "EMPLOYEE" ? "(required)" : "(if they are on the payroll)"}
        </span>
        <input value={employeeKey}
               onChange={(e) => setEmployeeKey(e.target.value.toUpperCase())}
               placeholder="RUBY" />
        <span className="rowsub">
          This is what links the account to a timesheet. A controller who is
          also on the payroll should have one — they keep time like everybody
          else.
        </span>
      </label>

      <div className="field">
        <span className="field-label">What may they judge</span>
        {PORTFOLIOS.map(([v, label, what]) => (
          <label key={v} style={{ display: "flex", gap: 8, marginTop: 8,
                                  alignItems: "flex-start" }}>
            <input type="checkbox" checked={portfolios.includes(v)}
                   onChange={(e) => setPortfolios(
                     e.target.checked ? [...portfolios, v]
                                      : portfolios.filter((p) => p !== v))} />
            <span>
              <strong>{label}</strong>
              <div className="rowsub">{what}</div>
            </span>
          </label>
        ))}
      </div>

      {needsReason && (
        <label className="field">
          <span className="field-label">Why they hold these</span>
          <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)}
                    placeholder="Facilities and inventory manager. Holding every portfolio for the 2025 push; the intent is FACILITIES and INVENTORY once the year is closed." />
          <span className="rowsub">
            A grant of authority over the cost record is part of the record.
            At least ten characters.
          </span>
        </label>
      )}

      <button className="btn primary" onClick={submit} disabled={!ready}>
        {busy ? "Creating…" : "Create the account"}
      </button>
    </Drawer>
  );
}

/* ── Giving and taking away ─────────────────────────────────────── */

function AccessDrawer({ actor, person, onClose, onDone, onError }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const held = new Set(person.portfolios || []);
  const ready = reason.trim().length >= 10 && !busy;

  async function toggle(p) {
    setBusy(true);
    try {
      if (held.has(p)) {
        await api.revokePortfolio(person.actor_id, p, reason.trim());
        onDone(`${p} taken back from ${person.display_name}`);
      } else {
        await api.grantPortfolio(person.actor_id, p, reason.trim());
        onDone(`${p} granted to ${person.display_name}`);
      }
    } catch (err) {
      onError(String(err.message || err).replace(/^\d+:\s*/, ""));
      setBusy(false);
    }
  }

  async function setActive(next) {
    setBusy(true);
    try {
      await api.setActorActive(person.actor_id, next, reason.trim());
      onDone(next ? `${person.display_name} reactivated`
                  : `${person.display_name} deactivated`);
    } catch (err) {
      onError(String(err.message || err).replace(/^\d+:\s*/, ""));
      setBusy(false);
    }
  }

  return (
    <Drawer open title={person.display_name} subtitle={person.email} onClose={onClose}>
      <p className="rowsub">
        Every change here is recorded against you, with the reason you give.
        Taking a portfolio back also closes whatever sessions the account has
        open — authority that ends should end straight away.
      </p>

      <label className="field">
        <span className="field-label">Why</span>
        <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)}
                  placeholder="Taking on the facilities schedule for the 2025 audit." />
      </label>

      <div className="field">
        <span className="field-label">Portfolios</span>
        <Table columns={[
          { label: "", align: "left" },
          { label: "", align: "left" },
          { label: "", align: "left", width: "110px" },
        ]}>
          {PORTFOLIOS.map(([v, label, what]) => (
            <tr key={v}>
              <td className="l">
                <strong>{label}</strong>
                <div className="rowsub">{what}</div>
              </td>
              <td className="l">
                {held.has(v) ? <Pill tone={v === "CONTROLLER" ? "accent" : ""}>held</Pill>
                             : <span className="rowsub">—</span>}
              </td>
              <td className="l">
                <button className="btn sm" disabled={!ready}
                        onClick={() => toggle(v)}>
                  {held.has(v) ? "Take back" : "Grant"}
                </button>
              </td>
            </tr>
          ))}
        </Table>
      </div>

      <div className="field">
        <span className="field-label">The account itself</span>
        <p className="rowsub">
          Accounts are never deleted — every judgment, certification and upload
          points at one, and removing it would orphan the record it authorised.
          Deactivating closes their sessions and stops them signing in.
        </p>
        <button className="btn" disabled={!ready}
                onClick={() => setActive(!person.is_active)}>
          {person.is_active ? "Deactivate this account" : "Reactivate this account"}
        </button>
      </div>
    </Drawer>
  );
}


/* ── Correcting an address ──────────────────────────────────────── */

function AmendDrawer({ person, onClose, onDone, onError }) {
  const [email, setEmail] = useState(person.email);
  const [name, setName] = useState(person.display_name);
  const [busy, setBusy] = useState(false);
  const changed = email !== person.email || name !== person.display_name;

  async function save() {
    setBusy(true);
    try {
      await api.amendActor(person.actor_id, {
        email: email.trim().toLowerCase(),
        display_name: name.trim(),
        reason: "Corrected from the payroll register, where only the surname "
                + "was carried.",
      });
      onDone(`${name.trim()} can sign in at ${email.trim().toLowerCase()}`);
    } catch (err) {
      onError(String(err.message || err).replace(/^\d+:\s*/, ""));
      setBusy(false);
    }
  }

  return (
    <Drawer open title="Correct the address" subtitle={person.employee_key}
            onClose={onClose}>
      <p className="rowsub">
        The payroll register gave a surname and nothing else, so this address
        and name were built from a pattern. Put in what is actually right.
        Correcting the address is what takes this account off the list.
      </p>
      <label className="field">
        <span className="field-label">Name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </label>
      <label className="field">
        <span className="field-label">Email</span>
        <input value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <button className="btn primary" onClick={save} disabled={!changed || busy}>
        {busy ? "Saving…" : "Save"}
      </button>
    </Drawer>
  );
}
