import React, { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ToastHost } from "./components/ui.jsx";
import { api, Unauthorized } from "./api.js";
import SignIn from "./pages/SignIn.jsx";
import PasswordDialog from "./components/PasswordDialog.jsx";
import UndoTrail from "./components/UndoTrail.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Worklist from "./pages/Worklist.jsx";
import Certify from "./pages/Certify.jsx";
import Timesheet from "./pages/Timesheet.jsx";
import Help from "./pages/Help.jsx";
import ClassifyQueue from "./pages/ClassifyQueue.jsx";
import Imports from "./pages/Imports.jsx";
import Reconcile from "./pages/Reconcile.jsx";
import MyDocuments from "./pages/MyDocuments.jsx";
import People from "./pages/People.jsx";
import Home from "./pages/Home.jsx";
import FirstPassword from "./components/FirstPassword.jsx";
import Evidence from "./pages/Evidence.jsx";
import Facilities from "./pages/Facilities.jsx";
import Chart from "./pages/Chart.jsx";
import Lanes from "./pages/Lanes.jsx";
import Rates from "./pages/Rates.jsx";
import Review from "./pages/Review.jsx";
import Contracts from "./pages/Contracts.jsx";
import Awards from "./pages/Awards.jsx";

/* Navigation carries the schedule each step eventually prints as in the audit
   package. Someone who has seen the workpapers already knows where they are.
   The dashboard has no schedule letter because it prints as nothing — it is
   where the work is picked up, not part of the package. */
/* The nav is assembled rather than switched. Everybody in the organisation
   keeps a timesheet and has somewhere to put documents, controllers
   included — so those tabs are not an employee's consolation prize, they are
   the part of the system that belongs to the person rather than to a
   portfolio. What gets added on top is whatever they actually hold.

   Showing a tab that answers 403 is worse than not showing it: it reads as a
   system that does not know who you are. */

//: [path, label, schedule, needs]
//: needs — null for everyone, "staff" for anyone on the payroll,
//: "admin" for a provisioner, otherwise a portfolio name.
const ALL_TABS = [
  ["/",          "Home",       "·",   null],
  ["/timesheet", "My time",    "G",   "staff"],
  ["/certify",   "My effort",  "G",   "staff"],
  ["/documents", "Documents",  "E",   null],
  ["/people",    "People",     "·",   "admin"],
  ["/imports",   "Import",     "A",   "CONTROLLER"],
  ["/reconcile", "Reconcile",  "A-1", "CONTROLLER"],
  ["/chart",     "Chart",      "H",   "CONTROLLER"],
  ["/classify",  "Classify",   "B",   "CONTROLLER"],
  ["/evidence",  "Evidence",   "E",   "OFFICE"],
  ["/space",     "Space",      "I",   "FACILITIES"],
  ["/inventory", "Inventory",  "I",   "INVENTORY"],
  ["/contracts", "Contracts",  "F",   "PROJECT"],
  ["/lanes",     "Lanes",      "C",   "CONTROLLER"],
  ["/rates",     "Rates",      "D",   "CONTROLLER"],
  ["/review",    "Review",     "A-1", "reader"],
  ["/help",      "Help",       "?",   null],
];

function tabsFor(actor) {
  const held = new Set(actor.portfolios || []);
  return ALL_TABS.filter(([, , , needs]) => {
    if (!needs) return true;
    if (needs === "staff") return Boolean(actor.employee_key);
    if (needs === "admin") return Boolean(actor.is_admin);
    // The review screens belong to anybody who may read the cost record —
    // the controller, the auditor, the organisation's administrator, and
    // anyone holding a recorded grant. They write nothing.
    if (needs === "reader") return Boolean(actor.can_read);
    // An auditor reads the whole record and writes none of it, so the
    // reviewing screens are theirs even with no portfolio.
    if (actor.role === "AUDITOR") return true;
    return held.has(needs);
  });
}

export default function App() {
  /* undefined = still asking, null = signed out, object = signed in. The three
     states are distinct on purpose: rendering the sign-in screen while the
     session check is still in flight makes an already-authenticated user think
     they were logged out. */
  const [actor, setActor] = useState(undefined);
  const [changingPassword, setChangingPassword] = useState(false);
  const [showTrail, setShowTrail] = useState(false);

  const check = useCallback(() => {
    api.me().then(setActor).catch((e) => {
      if (e instanceof Unauthorized) setActor(null);
      else setActor(null);
    });
  }, []);

  useEffect(check, [check]);

  /* A session can expire while a screen is open. Any call that comes back 401
     drops the shell to sign-in rather than leaving a page of empty tables. */
  useEffect(() => {
    const onRejection = (event) => {
      if (event.reason instanceof Unauthorized) {
        setActor(null);
        event.preventDefault();
      }
    };
    window.addEventListener("unhandledrejection", onRejection);
    return () => window.removeEventListener("unhandledrejection", onRejection);
  }, []);

  if (actor === undefined) return null;
  if (actor === null) return <SignIn onSignedIn={setActor} />;

  /* Before anything else. An account still on a password somebody else
     chose cannot record anything — the API refuses it — so putting the rest
     of the application in front of that would be showing somebody a set of
     screens they cannot use. This is the first thing a new person sees, and
     it is over in one step. */
  if (actor.must_set_password) {
    return (
      <ToastHost>
        <FirstPassword actor={actor} onDone={check} onSignOut={async () => {
          try { await api.logout(); } catch { /* going either way */ }
          setActor(null);
        }} />
      </ToastHost>
    );
  }

  const tabs = tabsFor(actor);

  async function signOut() {
    try { await api.logout(); } catch { /* the cookie is going either way */ }
    setActor(null);
  }

  return (
    <ToastHost>
      <div className="shell">
        <header className="topbar">
          <span className="wordmark">Youngstown Business Incubator</span>
          <span className="period-chip">Cost allocation · 2025</span>
          <span className="topbar-actor">
            {actor.display_name}
            <span className="role-chip" title={
              (actor.portfolios || []).length
                ? `Portfolios: ${actor.portfolios.join(", ")}`
                : "No portfolio — this account judges nothing"}>
              {actor.role.replace("_", " ")}
            </span>
            <button className="btn quiet" onClick={() => setShowTrail(true)}>
              Undo
            </button>
            <button className="btn quiet" onClick={() => setChangingPassword(true)}>
              Password
            </button>
            <button className="btn quiet" onClick={signOut}>Sign out</button>
          </span>
        </header>

        {changingPassword && (
          <PasswordDialog onClose={() => setChangingPassword(false)} />
        )}
        {showTrail && (
          <UndoTrail onClose={() => setShowTrail(false)}
                     onChanged={() => window.dispatchEvent(new Event("ybi:changed"))} />
        )}

        <nav className="tabs">
          {tabs.map(([to, label, sched]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) => `tab ${isActive ? "on" : ""}`}
            >
              <span className="sched">{sched}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        <Routes>
          <Route path="/" element={<Home actor={actor} />} />
          <Route path="/documents" element={<MyDocuments actor={actor} />} />
          <Route path="/people" element={<People actor={actor} />} />
          <Route path="/inventory" element={<Facilities actor={actor} tab="equipment" />} />
          <Route path="/timesheet" element={<Timesheet actor={actor} />} />
          <Route path="/certify" element={<Certify />} />
          <Route path="/help" element={<Help />} />
          <Route path="/worklist/:kind" element={<Worklist />} />
          <Route path="/imports" element={<Imports />} />
          <Route path="/reconcile" element={<Reconcile actor={actor} />} />
          <Route path="/chart" element={<Chart />} />
          <Route path="/classify" element={<ClassifyQueue actor={actor} />} />
          <Route path="/evidence" element={<Evidence actor={actor} />} />
          <Route path="/space" element={<Facilities actor={actor} />} />
          <Route path="/lanes" element={<Lanes />} />
          <Route path="/rates" element={<Rates />} />
          <Route path="/review" element={<Review />} />
          <Route path="/review/:pane" element={<Review />} />
          <Route path="/awards" element={<Awards />} />
          <Route path="/contracts" element={<Contracts actor={actor} />} />
          <Route path="/contracts/:pane" element={<Contracts actor={actor} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </ToastHost>
  );
}
