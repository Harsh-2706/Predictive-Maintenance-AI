import React, { useState } from "react";
import { api } from "../api.js";
import { CLASS, fmtTime, pct, rulText } from "../theme.js";
import { ClassTag, CrewSlider, ErrorState, Loading, Notice } from "../components/ui.jsx";

const FORMAT = [
  ["motor", "temperature, vibration, rpm"],
  ["pump", "pressure, flow_rate, temperature"],
  ["compressor", "temperature, pressure, vibration"],
];

export default function Upload() {
  const [file, setFile] = useState(null);
  const [k, setK] = useState(8);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [showAll, setShowAll] = useState(false);

  const run = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    try { setRes(await api.scoreCsv(file, k)); } catch (e) { setErr(e); setRes(null); }
    setBusy(false);
  };

  return (
    <div className="page upload">
      <header className="section-intro">
        <div>
          <p className="models-kicker">Score your own data</p>
          <h1>Run the trained models on a sensor file</h1>
          <p className="lede">
            Upload recent readings from your machines. The same pipeline as the live system runs on them:
            features → trained model → calibrated risk → remaining life → crew queue.
          </p>
        </div>
        <div className="notice">
          <strong>No file to hand?</strong>
          Download a sample with 12 hours of readings from all 60 machines, then upload it here.
          <p style={{ marginTop: ".6rem" }}><a className="btn ghost" href="/api/sample-csv" download>Download sample CSV</a></p>
        </div>
      </header>

      <div className="two-col">
        <section className="panel">
          <h2>1 · Choose a file</h2>
          <label className="file-drop">
            <input type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files[0] || null); setRes(null); setErr(null); }} />
            <span>{file ? <><b>{file.name}</b> · {(file.size / 1024).toFixed(0)} KB</> : "Click to choose a .csv file (up to 10 MB)"}</span>
          </label>
          <CrewSlider k={k} setK={setK} />
          <p><button type="button" className="btn primary" disabled={!file || busy} onClick={run}>
            {busy ? "Scoring…" : "Score with the AI"}</button></p>
        </section>
        <section className="panel">
          <h2>File format</h2>
          <p className="small">One row per reading. Columns: <code>timestamp</code>, <code>machine_id</code>,
            <code>machine_class</code>, then the sensors for that class:</p>
          <ul className="plain small">
            {FORMAT.map(([c, s]) => <li key={c}><ClassTag cls={c} /> {s}</li>)}
          </ul>
          <p className="fine">Include at least the last 6 hours per machine (the models read 2 h and 6 h trends).
            Units as in the sample: °C, mm/s, rpm, bar, m³/h. Data freshness is measured against the newest reading in the file.</p>
        </section>
      </div>

      {busy && <Loading what="Scoring" />}
      {err && <ErrorState title="That file couldn't be scored" error={err} />}
      {res && (
        <section className="panel">
          <div className="panel-head row">
            <div>
              <h2>Crew queue as of {fmtTime(res.as_of)}</h2>
              <p className="muted small">{res.machines.length} machines scored from {res.rows_used.toLocaleString("en-IN")} readings ·
                top {res.k} go to the crew.</p>
            </div>
            <button type="button" className="btn ghost" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Show crew queue only" : `Show all ${res.machines.length} machines`}</button>
          </div>
          {res.warnings.map((w) => <Notice key={w} tone="info">{w}</Notice>)}
          <table className="data-table">
            <thead><tr><th className="num">#</th><th>Machine</th><th className="num">Failure risk (24 h)</th>
              <th>Estimated time left</th><th className="num">Consequence</th><th className="num">Data age</th><th className="num">Priority</th></tr></thead>
            <tbody>
              {(showAll ? res.machines : res.queue).map((m) => (
                <tr key={m.machine_id} className={m.in_queue ? "hl" : ""}>
                  <td className="num">{m.rank}</td>
                  <td><b>{m.machine_id}</b> <ClassTag cls={m.machine_class} /></td>
                  <td className="num"><span className="risk-chip" style={{ "--c": CLASS[m.machine_class].color }}>{pct(m.risk)}</span></td>
                  <td>{rulText(m)}</td>
                  <td className="num">×{m.severity}</td>
                  <td className="num">{m.age_min < 1 ? "live" : `${Math.round(m.age_min)} min`}</td>
                  <td className="num">{m.priority.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
