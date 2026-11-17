import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { useAsync, useDebounced } from "../hooks.js";
import { APPROACH, C, CLASS, CLASSES, axis, chartBase, inr, pct } from "../theme.js";
import { Chart, ErrorState, Loading } from "../components/ui.jsx";

const ORDER = ["reactive", "schedule", "threshold", "ai"];
const COST_FIELDS = [
  { id: "downtime_cost_per_hour", label: "Lost production per hour a machine is down", unit: "₹", step: 1000 },
  { id: "breakdown_downtime_hours", label: "Downtime of an unplanned breakdown", unit: "hours", step: 1 },
  { id: "planned_downtime_hours", label: "Downtime of a planned repair", unit: "hours", step: 0.5 },
  { id: "breakdown_repair_cost", label: "Emergency repair cost", unit: "₹", step: 5000 },
  { id: "planned_repair_cost", label: "Planned repair cost", unit: "₹", step: 1000 },
  { id: "inspection_cost", label: "Cost of one crew inspection", unit: "₹", step: 100 },
];

export default function Compare() {
  const b = useAsync(() => api.baselines(), []);
  if (b.error) return <div className="page"><ErrorState title="Couldn't load the comparison" error={b.error} onRetry={b.retry} /></div>;
  if (!b.data) return <div className="page"><Loading what="Loading the comparison" /></div>;
  const rows = Object.fromEntries(b.data.comparison.map((r) => [r.approach, r]));
  const ai = rows.ai, thr = rows.threshold, sch = rows.schedule;
  const perClass = (a, c) => b.data.per_class.find((r) => r.approach === a && r.machine_class === c);

  return (
    <div className="page compare">
      <header className="section-intro">
        <div>
          <p className="models-kicker">AI vs today’s practice</p>
          <h1>Is the AI better than what plants already do?</h1>
          <p className="lede">
            Four ways to decide what the crew inspects, each with the <b>same crew of {b.data.k} machines per 6-hour shift</b>,
            scored on the same {Math.round(ai.days)} test days the models never saw.
          </p>
        </div>
        <div className="notice">
          <strong>How a failure counts as caught</strong>
          The machine was inspected in a shift ending in the 24 hours before it failed. We assume any inspection in that
          window finds the fault, which is generous to the non-AI approaches.
        </div>
      </header>

      <div className="kpis with-outcomes">
        <div className="kpi good"><b>{ai.events_caught}<small>/{ai.failure_events}</small></b><span>failures caught by the AI before breakdown</span></div>
        <div className="kpi"><b>{thr.events_caught}<small>/{thr.failure_events}</small></b><span>caught by sensor alarm limits</span></div>
        <div className="kpi"><b>{sch.events_caught}<small>/{sch.failure_events}</small></b><span>caught by a fixed inspection schedule</span></div>
        <div className="kpi good"><b>+{(thr.ai_recall_gain * 100).toFixed(0)}<small> pts</small></b>
          <span>more at-risk machines reached vs alarm limits (95% CI {(thr.ai_recall_gain_ci_low * 100).toFixed(1)}–{(thr.ai_recall_gain_ci_high * 100).toFixed(1)})</span></div>
      </div>

      <section className="panel">
        <div className="panel-head"><h2>Same crew, four decision rules</h2>
          <p className="muted small">Bars: share of failures caught in time, and share of crew visits that went to a machine about to fail.</p></div>
        <Chart height={300} option={barsOption(rows)} />
        <table className="data-table">
          <thead><tr><th>Approach</th><th>How the crew is sent</th><th className="num">Crew visits</th><th className="num">Failures caught</th>
            <th className="num">Typical warning</th><th className="num">Useful visits</th><th className="num">Wasted visits</th></tr></thead>
          <tbody>
            {ORDER.map((a) => {
              const r = rows[a];
              return (
                <tr key={a} className={a === "ai" ? "hl" : ""}>
                  <td><span className="sw" style={{ background: APPROACH[a].color }} /> <b>{APPROACH[a].short}</b></td>
                  <td className="muted">{describe(a, b.data)}</td>
                  <td className="num">{r.inspections}</td>
                  <td className="num">{r.events_caught} / {r.failure_events}</td>
                  <td className="num">{r.median_warning_h == null ? "–" : `${r.median_warning_h.toFixed(0)} h`}</td>
                  <td className="num">{a === "reactive" ? "–" : pct(r.precision_at_k)}</td>
                  <td className="num">{r.wasted_visits}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <div className="panel-head"><h2>Where simple alarm limits break down</h2>
          <p className="muted small">Failures caught in time, by machine type. Compressor sensors are the noisiest, so a fixed limit either fires constantly or misses the slow drift.</p></div>
        <div className="class-compare">
          {CLASSES.map((c) => {
            const t = perClass("threshold", c), a = perClass("ai", c);
            return (
              <div key={c} className="class-compare-card" style={{ "--c": CLASS[c].color }}>
                <h3>{CLASS[c].name}</h3>
                <p><span>Alarm limits</span><b>{t.events_caught}/{t.failure_events}</b></p>
                <p><span>Our AI</span><b>{a.events_caught}/{a.failure_events}</b></p>
              </div>
            );
          })}
        </div>
      </section>

      <Savings defaults={b.data.default_costs} />
    </div>
  );
}

function describe(a, d) {
  return {
    reactive: "No predictive work; fix machines after they break",
    schedule: `Rotate through the fleet, ${d.k} machines a shift (each one every ${d.schedule_cycle_shifts} shifts)`,
    threshold: `Visit machines whose latest reading is beyond ±${d.threshold_sigma}σ of normal, largest first`,
    ai: "Trained model → calibrated risk × consequence × data freshness",
  }[a];
}

function barsOption(rows) {
  const metrics = [
    { key: "event_catch_rate", name: "Failures caught in time" },
    { key: "precision_at_k", name: "Crew visits that were useful" },
  ];
  return {
    ...chartBase,
    grid: { left: 190, right: 40, top: 30, bottom: 30 },
    legend: { top: 0, left: 190, textStyle: { color: C.muted } },
    tooltip: { ...chartBase.tooltip, trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => pct(v) },
    xAxis: axis({ type: "value", max: 1, axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    yAxis: axis({ type: "category", data: ORDER.map((a) => APPROACH[a].short), inverse: true,
                  axisLabel: { color: C.ink, fontSize: 13, fontWeight: 600 } }),
    series: metrics.map((m, i) => ({
      name: m.name, type: "bar", barGap: "15%", barMaxWidth: 18,
      data: ORDER.map((a) => ({ value: rows[a][m.key] || 0,
                                itemStyle: { color: i === 0 ? APPROACH[a].color : C.ink, opacity: i === 0 ? 1 : 0.55 } })),
      label: { show: true, position: "right", formatter: (p) => pct(p.value), color: C.ink, fontSize: 12 },
      itemStyle: { color: i === 0 ? C.safety : C.ink },
    })),
  };
}

function Savings({ defaults }) {
  const [costs, setCosts] = useState(defaults);
  const [days, setDays] = useState(30);
  const debounced = useDebounced(useMemo(() => ({ ...costs, period_days: days }), [costs, days]), 250);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    api.savings(debounced).then((r) => { if (alive) { setRes(r); setErr(null); } })
      .catch((e) => alive && setErr(e));
    return () => { alive = false; };
  }, [debounced]);

  const rows = res && Object.fromEntries(res.rows.map((r) => [r.approach, r]));
  return (
    <section className="panel savings">
      <div className="panel-head row">
        <div>
          <p className="models-kicker">Savings calculator</p>
          <h2>What would this be worth on your plant?</h2>
          <p className="muted small">Enter your own figures. The outcomes (failures caught, missed, crew visits) are the measured test results above, scaled to the period you choose.</p>
        </div>
        <label className="field"><span>Period</span>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={30}>Per month (30 days)</option><option value={91}>Per quarter</option><option value={365}>Per year</option>
          </select>
        </label>
      </div>
      <div className="savings-body">
        <div className="cost-inputs">
          {COST_FIELDS.map((f) => (
            <label key={f.id} className="cost-field">
              <span>{f.label}</span>
              <span className="cost-input">
                {f.unit === "₹" && <i>₹</i>}
                <input type="number" min={0} step={f.step} value={costs[f.id]}
                       onChange={(e) => setCosts((c) => ({ ...c, [f.id]: e.target.value === "" ? 0 : Math.max(0, Number(e.target.value)) }))} />
                {f.unit !== "₹" && <i>{f.unit}</i>}
              </span>
            </label>
          ))}
          <button type="button" className="btn ghost" onClick={() => setCosts(defaults)}>Reset to example values</button>
        </div>
        <div className="savings-result" aria-live="polite">
          {err && <ErrorState title="Couldn't calculate" error={err} />}
          {rows && <>
            <div className="saving-headline">
              <span>With the AI, maintenance costs {res.period_days === 30 ? "per month" : res.period_days === 91 ? "per quarter" : "per year"} fall by</span>
              <b>{inr(rows.ai.saving_vs_reactive)}</b>
              <span>vs running machines to failure ({rows.ai.saving_pct.toFixed(0)}% less), and by <b>{inr(rows.threshold.total - rows.ai.total)}</b> vs alarm limits.</span>
            </div>
            <Chart height={260} option={costOption(rows)} />
            <p className="fine">
              One breakdown = {inr(res.cost_per_breakdown)} · one planned repair = {inr(res.cost_per_planned_repair)}.
              Example values are placeholders, not plant data. The simulated plant fails far more often than a real one,
              so use the percentage saving, not the absolute amount, as the indicator.
            </p>
          </>}
        </div>
      </div>
    </section>
  );
}

function costOption(rows) {
  const parts = [
    { key: "cost_breakdowns", name: "Breakdowns", color: C.signal },
    { key: "cost_planned_repairs", name: "Planned repairs", color: "#6682B7" },
    { key: "cost_inspections", name: "Inspections", color: "#9AA0A6" },
  ];
  return {
    ...chartBase,
    grid: { left: 120, right: 90, top: 30, bottom: 24 },
    legend: { top: 0, left: 120, textStyle: { color: C.muted } },
    tooltip: { ...chartBase.tooltip, trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => inr(v) },
    xAxis: axis({ type: "value", axisLabel: { color: C.muted, formatter: (v) => inr(v).replace(" crore", " cr") } }),
    yAxis: axis({ type: "category", inverse: true, data: ORDER.map((a) => APPROACH[a].short),
                  axisLabel: { color: C.ink, fontWeight: 600 } }),
    series: parts.map((p, i) => ({
      name: p.name, type: "bar", stack: "c", barMaxWidth: 26, itemStyle: { color: p.color },
      data: ORDER.map((a) => rows[a][p.key]),
      label: i === parts.length - 1 ? { show: true, position: "right", color: C.ink, fontSize: 12,
                                        formatter: (q) => inr(rows[ORDER[q.dataIndex]].total) } : undefined,
    })),
  };
}
