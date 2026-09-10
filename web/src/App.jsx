import React from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ToastHost } from "./components/ui.jsx";
import ClassifyQueue from "./pages/ClassifyQueue.jsx";
import Imports from "./pages/Imports.jsx";
import Chart from "./pages/Chart.jsx";
import Lanes from "./pages/Lanes.jsx";
import Rates from "./pages/Rates.jsx";
import Awards from "./pages/Awards.jsx";

/* Navigation carries the schedule each step eventually prints as in the audit
   package. Someone who has seen the workpapers already knows where they are. */
const TABS = [
  ["/imports",  "Import",     "A"],
  ["/chart",    "Chart",      "H"],
  ["/classify", "Classify",   "B"],
  ["/lanes",    "Lanes",      "C"],
  ["/rates",    "Rates",      "D"],
  ["/awards",   "Awards",     "F"],
];

export default function App() {
  return (
    <ToastHost>
      <div className="shell">
        <header className="topbar">
          <span className="wordmark">Youngstown Business Incubator</span>
          <span className="period-chip">Cost allocation · 2025</span>
        </header>

        <nav className="tabs">
          {TABS.map(([to, label, sched]) => (
            <NavLink key={to} to={to} className={({ isActive }) => `tab ${isActive ? "on" : ""}`}>
              <span className="sched">{sched}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        <Routes>
          <Route path="/" element={<Navigate to="/classify" replace />} />
          <Route path="/imports" element={<Imports />} />
        <Route path="/chart" element={<Chart />} />
          <Route path="/classify" element={<ClassifyQueue />} />
          <Route path="/lanes" element={<Lanes />} />
          <Route path="/rates" element={<Rates />} />
          <Route path="/awards" element={<Awards />} />
        </Routes>
      </div>
    </ToastHost>
  );
}
