import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import { useAsync } from "./hooks.js";
import Story from "./pages/Story.jsx";
import ControlRoom from "./pages/ControlRoom.jsx";
import Machine from "./pages/Machine.jsx";
import Fairness from "./pages/Fairness.jsx";
import Models from "./pages/Models.jsx";
import Method from "./pages/Method.jsx";
import { Notice } from "./components/ui.jsx";

const PAGES = [
  { id: "story", label: "The story" },
  { id: "control", label: "Control room" },
  { id: "machine", label: "Machine detail" },
  { id: "fairness", label: "Fairness lab" },
  { id: "models", label: "The models" },
  { id: "method", label: "How it works" },
];

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

  if (fleet.error) {
    return (
      <div className="boot">
        <Notice title="The app can't reach the plant data">
          Start the server with <code>run_web.bat</code> (or <code>uvicorn api.main:app</code>) after
          running the pipeline once with <code>python main.py</code>. Details: {String(fleet.error.message)}
        </Notice>
      </div>
    );
  }
  if (!fleet.data || w == null) return <div className="boot"><div className="spinner" />Loading the plant…</div>;

  const shared = { fleet: fleet.data, strategy, setStrategy, k, setK, w, setW, openMachine, go };
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/story" aria-label="Home">
          <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
            <rect width="32" height="32" rx="6" fill="#1F2328" />
            <path d="M6 22l6-8 5 5 9-11" stroke="#F2B705" strokeWidth="3" fill="none" />
          </svg>
          <span>Plant maintenance</span>
        </a>
        <nav>
          {PAGES.map((p) => (
            <a key={p.id} href={`#/${p.id}${p.id === "machine" && machineId ? "/" + machineId : ""}`}
               className={route.page === p.id ? "active" : ""} aria-current={route.page === p.id ? "page" : undefined}>
              {p.label}
            </a>
          ))}
        </nav>
        <span className="sim-flag" title="All data in this demo is simulated">Simulated plant data</span>
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
