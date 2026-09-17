import React, { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
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
import PositionReview from "./components/PositionReview.jsx";
import Books from "./pages/Books.jsx";
import Imports from "./pages/Imports.jsx";
import Reconcile from "./pages/Reconcile.jsx";
import MyDocuments from "./pages/MyDocuments.jsx";
import People from "./pages/People.jsx";
import Home from "./pages/Home.jsx";
import Requests from "./pages/Requests.jsx";
import FirstPassword from "./components/FirstPassword.jsx";
import Evidence from "./pages/Evidence.jsx";
import Facilities from "./pages/Facilities.jsx";
import Parties from "./pages/Parties.jsx";
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

/* The nav mark is the step of the walk, not the schedule letter.
 *
 * It used to carry the schedule each tab prints as in the audit package, so
 * that somebody holding the workpapers knew where they were. That was right
 * when the nav was twenty unordered tabs. It is wrong now the eight ARE the
 * order of operations: they read `· A B E D F G E` — E before D, and E twice
 * — which looks like a sequence, is not one, and is worse than no mark at all.
 *
 * So the mark is the step number, and it is **the walk's** number rather than
 * a fresh 1–8. Books is steps 1 and 2, Classify is 3 to 5, Rate is 7 and 8: a
 * plain 1–8 would put "Rate = 5" in the nav beside a landing page saying the
 * rate is step 8, which is two numberings of one order — the defect this file
 * is mostly about. One order, one set of numbers, and the nav and the walk are
 * the same map.
 *
 * Two tabs carry no number, and that is a statement rather than a gap: Audit
 * *is* the walk, and Requests is not a step in it — asking for what is missing
 * runs alongside the sequence, not inside it.
 *
 * The schedule letters are not lost. Every page carries its own in `PageHead`,
 * which is where a workpaper reference belongs: on the page, where there is
 * exactly one of them and it cannot read as an ordering. */
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
/* The 2025 audit is eight tabs and the ongoing system is the rest.
 *
 * Sixteen tabs were reaching the audit door and the controller's screen was
 * two rows of them — Import beside Reconcile beside Chart beside Classify
 * beside Space beside Inventory beside Rates beside Review, which is one job
 * dealt out as eight errands. The eight below are the year being closed, in
 * the order it is closed in, and nothing else is offered behind that door.
 *
 * **Folding a tab never removes a route.** `/space`, `/inventory`, `/library`,
 * `/imports`, `/reconcile` and `/review` all still answer and are all still
 * linked to from inside the tab that owns them — this file's own rule is that
 * the nav shows what is *yours to do*, not what you may open, and some screens
 * are reached by URL with no tab at all. A fold that deleted the routes would
 * be the nav-stricter-than-the-API defect with the evidence removed.
 *
 * Schedule letters are kept because somebody who has seen the workpapers
 * navigates by them, and two tabs now carry a span: Books is A and A-1
 * together, Reports is D and G.
 */
const ALL_TABS = [
  // ── the 2025 audit, in the order the file is closed ──────────────────
  ["/",          "Audit",      "·",     null,         "both"],
  /* Import and Reconcile were two tabs and are one job: get the books in and
     make them agree with themselves before anything is judged. Nothing
     downstream can start until both are done, so splitting them put a tab in
     the nav that is finished five minutes into the engagement and sits there
     for the rest of it. */
  ["/books",     "Books",      "1–2",     "CONTROLLER", "audit"],
  /* And Space and Inventory fold in here as partitions rather than tabs.
     They are the same question as the queue asked of a different sheet —
     account for the year — and they were two tabs a controller had no reason
     to open until the cost side was finished. `/classify/space` and
     `/classify/assets` are where they live now. */
  ["/classify",  "Classify",   "3–5",     "CONTROLLER", "audit"],
  ["/evidence",  "Evidence",   "6",     "OFFICE",     "audit"],
  /* The rate is read-only and is reached through the steps above rather than
     opened first. Nothing on it is computed — every figure is read from the
     row the computation recorded — which is the whole reason a reviewer can
     be told the rate was not reverse-engineered. */
  ["/review/rate", "Rate",     "7–9",     "reader",     "audit"],
  ["/restate",   "Restate",    "10",     "CONTROLLER", "audit"],
  ["/reports",   "Reports",    "11",     "reader",     "audit"],
  /* Reading what has been asked for takes the same gate the router asks for,
     `require_reader`. Accepting a reply takes the portfolio that owns the
     data, which the screen itself decides — so somebody who may read this
     and not write it sees everything and is told whose judgment the last
     step is, rather than meeting a 403 they could not have predicted. */
  ["/requests",  "Requests",   "·",     "reader",     "audit"],

  // ── the ongoing financial control system ─────────────────────────────
  ["/timesheet", "My time",    "G",     "staff",      "fcs"],
  ["/certify",   "My effort",  "G",     "staff",      "fcs"],
  ["/documents", "My documents", "E",   null,         "fcs"],
  ["/library",   "Library",    "E",     "reader",     "fcs"],
  ["/people",    "People",     "·",     "admin",      "fcs"],
  ["/imports",   "Import",     "A",     "CONTROLLER", "fcs"],
  ["/reconcile", "Reconcile",  "A-1",   "CONTROLLER", "fcs"],
  ["/chart",     "Chart",      "H",     "CONTROLLER", "fcs"],
  ["/space",     "Space",      "I",     "FACILITIES", "fcs"],
  ["/inventory", "Inventory",  "I",     "INVENTORY",  "fcs"],
  ["/contracts", "Contracts",  "F",     "PROJECT",    "fcs"],
  /* Setting a piece of work up, and the list of who is doing what by when.
     Same gate as Contracts, because it is the same job: a project IS a
     charge code somebody set up, and the people on it are the people the
     charge-code routes authorise. */
  ["/projects",  "Projects",   "F",     "PROJECT",    "fcs"],
  ["/lanes",     "Lanes",      "C",     "CONTROLLER", "fcs"],
  ["/rates",     "Rates",      "D",     "CONTROLLER", "fcs"],
  ["/review",    "Review",     "A-1",   "reader",     "fcs"],
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
            {/* Guidebook and Help were tabs and are not work, so they left
                the nav with the fold. They must not leave the *building*
                with it: the everybody manual is written for somebody with a
                timesheet and no portfolio, and a shelf they cannot see is
                the capability-with-no-door shape one step along. The
                masthead is where a reader looks for them, and it is on
                every screen rather than only on the two they were tabs
                beside. */}
            <Link className="btn quiet" to="/guidebook" title="The manuals and the printed walk-throughs">
              Guide
            </Link>
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
          {/* The fold keeps every route and adds the two the partitions
              point at. `/space` and `/inventory` still answer — a link, a
              bookmark and the worklist's own `goes_to` all still land — and
              these are the addresses the Classify screen sends people to. */}
          <Route path="/classify" element={<ClassifyQueue actor={actor} />} />
          <Route path="/classify/review" element={<PositionReview actor={actor} />} />
          <Route path="/classify/space" element={<Facilities actor={actor} />} />
          <Route path="/classify/assets" element={<Facilities actor={actor} tab="equipment" />} />
          {/* 200.331, the third partition of the same question: which of the
              cost already judged DIRECT reaches MTDC whole. The register has
              been on file since migration 115 and had no door at all. */}
          <Route path="/classify/parties" element={<Parties actor={actor} />} />
          <Route path="/books" element={<Books actor={actor} />} />
          <Route path="/books/:pane" element={<Books actor={actor} />} />
          <Route path="/evidence" element={<Evidence actor={actor} />} />
          <Route path="/requests" element={<Requests actor={actor} />} />
          <Route path="/space" element={<Facilities actor={actor} />} />
          <Route path="/projects" element={<Projects actor={actor} />} />
          <Route path="/projects/:objectiveId" element={<Projects actor={actor} />} />
          <Route path="/lanes" element={<Lanes />} />
          <Route path="/rates" element={<Rates />} />
          <Route path="/restate" element={<Restate actor={actor} />} />
          <Route path="/restate/:restatementId" element={<Restate actor={actor} />} />
          <Route path="/review" element={<Review actor={actor} />} />
          <Route path="/review/:pane" element={<Review actor={actor} />} />
          <Route path="/awards" element={<Awards />} />
          <Route path="/contracts" element={<Contracts actor={actor} />} />
          <Route path="/contracts/:pane" element={<Contracts actor={actor} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </ToastHost>
  );
}
