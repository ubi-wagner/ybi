import React, { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ToastHost } from "./components/ui.jsx";
import { api, Unauthorized } from "./api.js";
import SignIn from "./pages/SignIn.jsx";
import PasswordDialog from "./components/PasswordDialog.jsx";
import UndoTrail from "./components/UndoTrail.jsx";
import FailureBell from "./components/FailureBell.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Worklist from "./pages/Worklist.jsx";
import Certify from "./pages/Certify.jsx";
import Timesheet from "./pages/Timesheet.jsx";
import Choose from "./pages/Choose.jsx";
import Guidebook from "./pages/Guidebook.jsx";
import Help from "./pages/Help.jsx";
import ClassifyQueue from "./pages/ClassifyQueue.jsx";
import Imports from "./pages/Imports.jsx";
import Reconcile from "./pages/Reconcile.jsx";
import MyDocuments from "./pages/MyDocuments.jsx";
import People from "./pages/People.jsx";
import Home from "./pages/Home.jsx";
import Requests from "./pages/Requests.jsx";
import FirstPassword from "./components/FirstPassword.jsx";
import Evidence from "./pages/Evidence.jsx";
import Facilities from "./pages/Facilities.jsx";
import Chart from "./pages/Chart.jsx";
import Projects from "./pages/Projects.jsx";
import Lanes from "./pages/Lanes.jsx";
import Restate from "./pages/Restate.jsx";
import Rates from "./pages/Rates.jsx";
import Review from "./pages/Review.jsx";
import Contracts from "./pages/Contracts.jsx";
import Awards from "./pages/Awards.jsx";
import Library from "./pages/Library.jsx";
import Reports from "./pages/Reports.jsx";

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
  ["/",          "Home",       "·",   null, "both"],
  ["/timesheet", "My time",    "G",   "staff", "fcs"],
  ["/certify",   "My effort",  "G",   "staff", "fcs"],
  /* Three tabs live on Schedule E and they are easy to confuse, so each one
     is named for what you do there rather than for what it holds. "My
     documents" is where you send yours in; the "Library" is the whole shelf,
     to read; "Evidence" is where somebody says what a document proves. The
     first of those was called "Documents", which is the generic word for all
     three and matched neither its own heading nor its job. */
  ["/documents", "My documents", "E", null, "both"],
  ["/library",   "Library",    "E",   "reader", "both"],
  ["/people",    "People",     "·",   "admin", "fcs"],
  ["/imports",   "Import",     "A",   "CONTROLLER", "audit"],
  ["/reconcile", "Reconcile",  "A-1", "CONTROLLER", "audit"],
  ["/chart",     "Chart",      "H",   "CONTROLLER", "fcs"],
  ["/classify",  "Classify",   "B",   "CONTROLLER", "audit"],
  ["/evidence",  "Evidence",   "E",   "OFFICE", "audit"],
  /* Reading what has been asked for takes the same gate the router asks for,
     `require_reader`. Accepting a reply takes the portfolio that owns the
     data, which the screen itself decides — so somebody who may read this
     and not write it sees everything and is told whose judgment the last
     step is, rather than meeting a 403 they could not have predicted. */
  ["/requests",  "Requests",   "E",   "reader", "audit"],
  ["/space",     "Space",      "I",   "FACILITIES", "both"],
  ["/inventory", "Inventory",  "I",   "INVENTORY", "both"],
  ["/contracts", "Contracts",  "F",   "PROJECT", "fcs"],
  /* Setting a piece of work up, and the list of who is doing what by when.
     Same gate as Contracts, because it is the same job: a project IS a
     charge code somebody set up, and the people on it are the people the
     charge-code routes authorise. */
  ["/projects",  "Projects",   "F",   "PROJECT", "fcs"],
  ["/lanes",     "Lanes",      "C",   "CONTROLLER", "fcs"],
  ["/rates",     "Rates",      "D",   "CONTROLLER", "audit"],
  /* The point of the whole system, and it had no tab for as long as it has
     existed: five routes, complete, and no page, no route and no call in
     api.js. Everything upstream — the classification, the seal, the rate,
     the allocation — exists so that a number put in front of NCDMM can be
     traced back to a judgment somebody signed their name to, and nobody
     could reach the screen that puts it there. */
  ["/restate",   "Restate",    "F",   "CONTROLLER", "audit"],
  ["/reports",   "Reports",    "G",   "reader", "audit"],
  ["/review",    "Review",     "A-1", "reader", "audit"],
  /* The manuals and the generated PDFs, on a shelf. `null` because the
     everybody manual is written for somebody with a timesheet and no
     portfolio, and nothing on any of these pages is part of the cost
     record — which is what `reader` is a grant over. The API asks for the
     same thing, so the nav and the server agree. */
  ["/guidebook", "Guidebook",  "?",   null, "both"],
  ["/help",      "Help",       "?",   null, "both"],
];

/* Two products, one login.
 *
 * The tabs were cramming the controller's job together with the employee's,
 * and a year being closed together with the company being run. Twenty tabs
 * over two rows, and no two of them the same kind of work. So each tab now
 * says which product it belongs to and the shell shows one product at a
 * time — the 2025 audit, which is a year being closed and then never
 * touched again, or the ongoing financial control system.
 *
 * `both` is not a hedge. The document library, the space register and the
 * inventory register are genuinely read by each: the 2025 rate is built on
 * the square footage and the asset schedule, and the same registers carry on
 * being maintained afterwards. A tab that belonged to one and was reached
 * from the other would be the nav disagreeing with the work.
 *
 * The permission gate is unchanged and is applied as well as this, never
 * instead: a product never widens what somebody may open. */
function tabsFor(actor, product) {
  const held = new Set(actor.portfolios || []);
  return ALL_TABS.filter(([, , , needs, belongs]) => {
    if (product && belongs !== "both" && belongs !== product) return false;
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
    // CONTROLLER reaches everything. Every narrow gate in auth.py is
    // `require_portfolio(X, Portfolio.CONTROLLER)`, so the API already lets
    // a controller into Evidence, Space, Inventory and Contracts — and this
    // function did not, which left Tom holding the portfolio that reaches
    // everything and offered four screens fewer than he is entitled to. A
    // nav stricter than the API is the same defect as one looser than it:
    // both mean the screen and the server disagree about who you are. The
    // looser direction shows a tab that answers 403; this direction hides
    // work somebody has to know a URL to reach.
    return held.has(needs) || held.has("CONTROLLER");
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
  /* Which product the shell is drawing. Remembered per browser so somebody
     closing the audit for the evening lands back in it in the morning, and
     deliberately *not* on the server: it is a preference about a screen, not
     a fact about the cost record, and the one place this system keeps
     per-viewer conveniences is the browser. Reading it can throw in a
     private window, so it is guarded. */
  const [product, setProduct] = useState(() => {
    try { return localStorage.getItem("ybi.product") || null; } catch { return null; }
  });

  function pick(next) {
    try { localStorage.setItem("ybi.product", next); } catch { /* fine */ }
    setProduct(next);
  }

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

  /* Somebody with a timesheet and nothing else has one job here, and being
     asked to choose between two products before they can record a day would
     be a question with one answer. They go straight in. */
  async function signOut() {
    try { await api.logout(); } catch { /* the cookie is going either way */ }
    setActor(null);
  }

  const chooses = actor.can_read || (actor.portfolios || []).length > 0;
  const effective = chooses ? product : "fcs";

  if (chooses && !product) {
    return (
      <ToastHost>
        <div className="shell">
          <header className="topbar">
            <span className="wordmark">Youngstown Business Incubator</span>
            <FailureBell />
            <span className="topbar-actor">
              {actor.display_name}
              <button className="btn quiet" onClick={signOut}>Sign out</button>
            </span>
          </header>
          <Choose actor={actor} onPick={pick} />
        </div>
      </ToastHost>
    );
  }

  const tabs = tabsFor(actor, effective);

  return (
    <ToastHost>
      <div className="shell">
        <header className="topbar">
          <span className="wordmark">Youngstown Business Incubator</span>
          {chooses ? (
            /* Which product you are in, and the way back out. A person who
               cannot tell which of two products they are looking at is one
               tab away from doing the right thing on the wrong year. */
            <button className={`product-chip ${effective}`}
                    onClick={() => pick(effective === "audit" ? "fcs" : "audit")}
                    title="Switch to the other product">
              {effective === "audit"
                ? "2025 Audit" : "Financial Control Solution"}
              <span className="product-swap">switch</span>
            </button>
          ) : (
            <span className="period-chip">Cost allocation · 2025</span>
          )}
          <FailureBell />
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
          <Route path="/" element={<Home actor={actor} product={effective} />} />
          <Route path="/documents" element={<MyDocuments actor={actor} />} />
          <Route path="/library" element={<Library />} />
          <Route path="/reports" element={<Reports actor={actor} />} />
          <Route path="/people" element={<People actor={actor} />} />
          <Route path="/inventory" element={<Facilities actor={actor} tab="equipment" />} />
          <Route path="/timesheet" element={<Timesheet actor={actor} />} />
          <Route path="/certify" element={<Certify />} />
          <Route path="/guidebook" element={<Guidebook />} />
          <Route path="/help" element={<Help />} />
          <Route path="/worklist/:kind" element={<Worklist actor={actor} />} />
          <Route path="/imports" element={<Imports />} />
          <Route path="/reconcile" element={<Reconcile actor={actor} />} />
          <Route path="/chart" element={<Chart />} />
          <Route path="/classify" element={<ClassifyQueue actor={actor} />} />
          <Route path="/evidence" element={<Evidence actor={actor} />} />
          <Route path="/requests" element={<Requests actor={actor} />} />
          <Route path="/space" element={<Facilities actor={actor} />} />
          <Route path="/projects" element={<Projects actor={actor} />} />
          <Route path="/projects/:objectiveId" element={<Projects actor={actor} />} />
          <Route path="/lanes" element={<Lanes />} />
          <Route path="/rates" element={<Rates />} />
          <Route path="/restate" element={<Restate actor={actor} />} />
          <Route path="/restate/:restatementId" element={<Restate actor={actor} />} />
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
