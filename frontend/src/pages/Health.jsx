import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAsync, useDebounced } from "../hooks.js";
import { C, CLASS, CLASSES, axis, chartBase, fmtTime, pct, sensorName } from "../theme.js";
import { Chart, ClassTag, ErrorState, Loading } from "../components/ui.jsx";

const STATUS = { stable: "Stable", watch: "Watch", drift: "Drift" };
const OUTCOME = { fault_found: "Fault found", no_fault: "No fault", not_checked: "Not checked" };

export default function Health({ fleet }) {
  const [inject, setInject] = useState({ cls: "motor", sensor: "temperature", pct: 0, from_week: 2 });
  const live = useDebounced(inject, 250);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const fb = useAsync(() => api.feedback(), []);

  useEffect(() => {
    let alive = true;
    api.health(live.pct ? live : null).then((d) => { if (alive) { setData(d); setErr(null); } })
      .catch((e) => alive && setErr(e));
    return () => { alive = false; };
  }, [live]);

  const sensors = fleet.classes.find((c) => c.id === inject.cls).sensors;
  return (
    <div className="page health">
      <header className="section-intro">
        <div>
          <p className="models-kicker">Model health</p>
          <h1>Is the AI still seeing the data it was trained on?</h1>
          <p className="lede">After deployment, sensors get replaced or recalibrated and machines take new loads. A model can
            quietly get worse. These checks raise a flag before it does.</p>
        </div>
        <div className="notice">
          <strong>How drift is measured</strong>
          Population Stability Index (PSI): each week of new readings against the training period.
          Below {data?.thresholds.watch ?? 0.1} stable, up to {data?.thresholds.drift ?? 0.25} watch, above that: investigate or retrain.
        </div>
      </header>

      <section className="panel">
        <div className="panel-head row">
          <div><h2>Sensor drift by week</h2>
            <p className="muted small">Each cell compares one week of test-period readings with the training data.</p></div>
        </div>
        <div className="inject">
          <b>Try it: simulate a faulty sensor</b>
          <label className="field"><span>Machine type</span>
            <select value={inject.cls} onChange={(e) => {
              const cls = e.target.value;
              setInject((s) => ({ ...s, cls, sensor: fleet.classes.find((c) => c.id === cls).sensors[0] }));
            }}>
              {CLASSES.map((c) => <option key={c} value={c}>{CLASS[c].name}</option>)}
            </select></label>
          <label className="field"><span>Sensor</span>
            <select value={inject.sensor} onChange={(e) => setInject((s) => ({ ...s, sensor: e.target.value }))}>
              {sensors.map((s) => <option key={s} value={s}>{sensorName(s)}</option>)}
            </select></label>
          <label className="field crew"><span>Reads <b>{inject.pct > 0 ? "+" : ""}{inject.pct}%</b> off from week {inject.from_week + 1}</span>
            <input type="range" min={-15} max={15} step={1} value={inject.pct}
                   onChange={(e) => setInject((s) => ({ ...s, pct: Number(e.target.value) }))} /></label>
          <button type="button" className="btn ghost" disabled={!inject.pct} onClick={() => setInject((s) => ({ ...s, pct: 0 }))}>Reset</button>
        </div>
        {err && <ErrorState title="Couldn't compute drift" error={err} />}
        {!data ? <Loading what="Checking drift" /> : <DriftGrid data={data} />}
      </section>

      {data && (
        <section className="panel">
          <div className="panel-head"><h2>Weekly performance once outcomes are known</h2>
            <p className="muted small">Share of pre-failure readings the model flagged (recall), week by week. A falling line is the signal to retrain.</p></div>
          <Chart height={260} option={perfOption(data.performance)} />
        </section>
      )}

      <section className="panel">
        <div className="panel-head"><p className="models-kicker">Technician feedback</p>
          <h2>What the crew found when they checked</h2>
          <p className="muted small">Recorded from each machine’s page. Confirmed faults and confirmed false alarms become new
            training labels for the next retraining run.</p></div>
        {fb.error ? <ErrorState title="Couldn't load feedback" error={fb.error} onRetry={fb.retry} /> : !fb.data ? <Loading what="Loading feedback" /> : (
          fb.data.total === 0 ? <p className="muted">No inspections recorded yet. Open a machine from the queue and record what the crew found.</p> : <>
            <div className="kpis with-outcomes">
              <div className="kpi"><b>{fb.data.total}</b><span>inspections recorded</span></div>
              <div className="kpi good"><b>{fb.data.counts.fault_found}</b><span>faults confirmed</span></div>
              <div className="kpi"><b>{fb.data.counts.no_fault}</b><span>no fault found</span></div>
              <div className="kpi"><b>{fb.data.confirmed_precision == null ? "–" : pct(fb.data.confirmed_precision)}</b><span>of checked alerts were real</span></div>
            </div>
            <table className="data-table">
              <thead><tr><th>Recorded</th><th>Machine</th><th>Shift</th><th className="num">Risk then</th><th>Outcome</th><th>Note</th></tr></thead>
              <tbody>{fb.data.recent.map((r, i) => (
                <tr key={i}><td>{fmtTime(r.recorded_at)}</td><td><b>{r.machine_id}</b> <ClassTag cls={r.machine_class} /></td>
                  <td>{fmtTime(r.window_end)}</td><td className="num">{pct(r.risk)}</td>
                  <td><span className={`pill ${r.outcome === "fault_found" ? "fail" : "ok"}`}>{OUTCOME[r.outcome]}</span></td>
                  <td className="muted">{r.note}</td></tr>))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </div>
  );
}

function DriftGrid({ data }) {
  const weeks = [...new Set(data.weekly.map((r) => r.week))].sort((a, b) => a - b);
  const keys = [];
  CLASSES.forEach((c) => [...new Set(data.weekly.filter((r) => r.machine_class === c).map((r) => r.sensor))]
    .forEach((s) => keys.push([c, s])));
  const cell = (c, s, w) => data.weekly.find((r) => r.machine_class === c && r.sensor === s && r.week === w);
  const flagged = data.worst.filter((r) => r.status !== "stable");
  return (
    <>
      <p className={`drift-verdict ${flagged.length ? "bad" : "good"}`}>
        {flagged.length
          ? <>Drift detected: {flagged.map((r) => `${CLASS[r.machine_class].one} ${sensorName(r.sensor).toLowerCase()} (PSI ${r.psi.toFixed(2)})`).join(", ")}. Check the sensor before trusting these alerts.</>
          : <>All sensors stable: the test period looks like the training data, so the models’ results can be trusted.</>}
      </p>
      <div className="drift-scroll">
        <table className="drift-grid">
          <thead><tr><th>Sensor</th>{weeks.map((w) => <th key={w}>Week of {fmtTime(cell(keys[0][0], keys[0][1], w)?.week_start || "").split(",")[0]}</th>)}</tr></thead>
          <tbody>{keys.map(([c, s]) => (
            <tr key={c + s}><td><ClassTag cls={c} /> {sensorName(s)}</td>
              {weeks.map((w) => { const r = cell(c, s, w); return (
                <td key={w} className={`psi ${r?.status}`} title={r ? `${r.readings} readings` : ""}>
                  {r ? <><b>{r.psi.toFixed(3)}</b><span>{STATUS[r.status]}</span></> : "–"}</td>); })}
            </tr>))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function perfOption(perf) {
  const weeks = [...new Set(perf.map((r) => r.week))].sort((a, b) => a - b);
  return {
    ...chartBase,
    grid: { left: 52, right: 24, top: 36, bottom: 30 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted } },
    tooltip: { ...chartBase.tooltip, trigger: "axis", valueFormatter: (v) => pct(v, 1) },
    xAxis: axis({ type: "category", data: weeks.map((w) => `Test week ${w + 1}`) }),
    yAxis: axis({ type: "value", min: (v) => Math.max(0, Math.floor(v.min * 10) / 10), max: 1, axisLabel: { color: C.muted, formatter: (v) => `${Math.round(v * 100)}%` } }),
    series: CLASSES.map((c) => ({
      name: CLASS[c].name, type: "line", symbolSize: 8, itemStyle: { color: CLASS[c].color }, lineStyle: { width: 2.5 },
      data: weeks.map((w) => perf.find((r) => r.machine_class === c && r.week === w)?.recall ?? null),
    })),
  };
}
