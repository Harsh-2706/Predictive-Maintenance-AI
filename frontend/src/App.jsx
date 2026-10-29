import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import { useAsync } from "./hooks.js";
import Story from "./pages/Story.jsx";
import ControlRoom from "./pages/ControlRoom.jsx";
import Machine from "./pages/Machine.jsx";
import Fairness from "./pages/Fairness.jsx";
import Models from "./pages/Models.jsx";
import Method from "./pages/Method.jsx";
import { ErrorState } from "./components/ui.jsx";

const PAGES = [
  { id: "story", label: "The story" },
  { id: "control", label: "Control room" },
  { id: "machine", label: "Machine detail" },
  { id: "fairness", label: "Fairness lab" },
  { id: "models", label: "The models" },
  { id: "method", label: "How it works" },
];
const EVIDENCE_PAGES = PAGES.filter((page) => ["story", "fairness", "models", "method"].includes(page.id));

// Route lives in the URL hash: #/control, #/machine/C-08
function readHash() {
  const [, page = "story", arg] = window.location.hash.split("/");
  return { page: PAGES.some((p) => p.id === page) ? page : "story", arg };
}

export default function App() {
  const [route, setRoute] = useState(readHash);
  const fleet = useAsync(() => api.fleet(), []);
  const [strategy, setStrategy] = useState("S3_risk_priority");
  const [k, setK] = useState(8);
  const [w, setW] = useState(null);
  const [machineId, setMachineId] = useState(null);

  useEffect(() => {
    const on = () => setRoute(readHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  useEffect(() => { if (route.page === "machine" && route.arg) setMachineId(route.arg); }, [route]);
  useEffect(() => {
    if (fleet.data && w == null) {
      setW(Math.floor(fleet.data.windows.length * 0.42));
      setK(fleet.data.default_k);
    }
  }, [fleet.data, w]);
  useEffect(() => { window.scrollTo(0, 0); }, [route.page]);

  const go = (page, arg) => { window.location.hash = arg ? `/${page}/${arg}` : `/${page}`; };
  const openMachine = (id) => { setMachineId(id); go("machine", id); };
  const onEvidenceRoute = EVIDENCE_PAGES.some((page) => page.id === route.page);
  const onDecisionRoute = route.page === "control" || route.page === "machine";

  if (fleet.error) {
    return (
      <div className="boot">
        <ErrorState title="The app can't reach the plant data" error={fleet.error} onRetry={fleet.retry}>
          Start the server with <code>run_web.bat</code> (or <code>uvicorn api.main:app</code>) after
          running the pipeline once with <code>python main.py</code>.
        </ErrorState>
      </div>
    );
  }
  if (!fleet.data || w == null) return <div className="boot"><div className="spinner" />Loading the plant…</div>;

  const shared = { fleet: fleet.data, strategy, setStrategy, k, setK, w, setW, openMachine, go };
  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-main">
          <a className="brand" href="#/control" aria-label="Plant maintenance decision workspace">
            <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
              <rect width="32" height="32" rx="6" fill="#1E2422" />
            <path d="M6 22l6-8 5 5 9-11" stroke="#F2B705" strokeWidth="3" fill="none" />
            </svg>
            <span>Plant maintenance</span>
          </a>
          <nav className="primary-nav" aria-label="Primary navigation">
            <a href="#/control" className={onDecisionRoute ? "active" : ""}
               aria-current={onDecisionRoute ? "page" : undefined}>Decision</a>
            <a href="#/story" className={onEvidenceRoute ? "active" : ""}
               aria-current={onEvidenceRoute ? "page" : undefined}>Evidence</a>
          </nav>
          <span className="sim-flag" title="All data in this demo is simulated">Simulated data</span>
        </div>
        {onEvidenceRoute && (
          <nav className="evidence-nav" aria-label="Evidence sections">
            {EVIDENCE_PAGES.map((page) => (
              <a key={page.id} href={`#/${page.id}`} className={route.page === page.id ? "active" : ""}
                 aria-current={route.page === page.id ? "page" : undefined}>{page.label}</a>
            ))}
          </nav>
        )}
      </header>
      <main>
        {route.page === "story" && <Story {...shared} />}
        {route.page === "control" && <ControlRoom {...shared} />}
        {route.page === "machine" && <Machine {...shared} machineId={machineId || fleet.data.machines[0].id} />}
        {route.page === "fairness" && <Fairness {...shared} />}
        {route.page === "models" && <Models {...shared} />}
        {route.page === "method" && <Method {...shared} />}
      </main>
    </div>
  );
}
