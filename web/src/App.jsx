import React, { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ToastHost } from "./components/ui.jsx";
import { api, Unauthorized } from "./api.js";
import SignIn from "./pages/SignIn.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Worklist from "./pages/Worklist.jsx";
import ClassifyQueue from "./pages/ClassifyQueue.jsx";
import Imports from "./pages/Imports.jsx";
import Chart from "./pages/Chart.jsx";
import Lanes from "./pages/Lanes.jsx";
import Rates from "./pages/Rates.jsx";
import Awards from "./pages/Awards.jsx";

/* Navigation carries the schedule each step eventually prints as in the audit
   package. Someone who has seen the workpapers already knows where they are.
   The dashboard has no schedule letter because it prints as nothing — it is
   where the work is picked up, not part of the package. */
const TABS = [
  ["/",          "Dashboard",  "·"],
  ["/imports",   "Import",     "A"],
  ["/chart",     "Chart",      "H"],
  ["/classify",  "Classify",   "B"],
  ["/lanes",     "Lanes",      "C"],
  ["/rates",     "Rates",      "D"],
  ["/awards",    "Awards",     "F"],
];

export default function App() {
  /* undefined = still asking, null = signed out, object = signed in. The three
     states are distinct on purpose: rendering the sign-in screen while the
     session check is still in flight makes an already-authenticated user think
     they were logged out. */
  const [actor, setActor] = useState(undefined);

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
            <span className="role-chip">{actor.role}</span>
            <button className="btn quiet" onClick={signOut}>Sign out</button>
          </span>
        </header>

        <nav className="tabs">
          {TABS.map(([to, label, sched]) => (
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
          <Route path="/" element={<Dashboard />} />
          <Route path="/worklist/:kind" element={<Worklist />} />
          <Route path="/imports" element={<Imports />} />
          <Route path="/chart" element={<Chart />} />
          <Route path="/classify" element={<ClassifyQueue />} />
          <Route path="/lanes" element={<Lanes />} />
          <Route path="/rates" element={<Rates />} />
          <Route path="/awards" element={<Awards />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </ToastHost>
  );
}
