import React, { useState } from "react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { C, CLASS, CLASSES, MODEL_NAME, axis, chartBase, pct, sensorName } from "../theme.js";
import { Chart, Loading, Segmented } from "../components/ui.jsx";

export default function Models() {
  const models = useAsync(() => api.models(), []);
  const cal = useAsync(() => api.calibration(), []);
  const [view, setView] = useState("raw");
  if (!models.data || !cal.data) return <div className="page"><Loading what="Loading models" /></div>;

  return (
    <div className="page models">
      <h1>The models</h1>
      <p className="lede">
        Each machine type has its own failure-prediction model, trained on that type's sensor history. Every model
        answers one question for every reading: how likely is this machine to fail in the next 24 hours?
      </p>

      <div className="model-cards">
        {models.data.cards.map((m) => <ModelCard key={m.cls} m={m} />)}
      </div>

      <div className="two-col">
        <div className="panel">
          <div className="panel-head row">
            <h2>Can the scores be taken at face value?</h2>
            <Segmented label="Score type" value={view} onChange={setView}
                       options={[{ value: "raw", label: "Raw" }, { value: "calibrated", label: "Calibrated" }]} />
          </div>
          <Chart height={320} option={reliability(cal.data, view)} />
          <p className="fine">On the dashed line, a model's 70% really means 70%.</p>
        </div>
        <div className="panel">
          <h2>Why we count machines, not readings</h2>
          <p className="muted small">
            Motors report every 15 minutes, compressors every hour. Counting raw readings, motors would flood the
            alert list just by talking more. The queue uses one snapshot per machine per shift.
          </p>
          <Chart height={300} option={volume(models.data.volume)} />
        </div>
      </div>
    </div>
  );
}

function ModelCard({ m }) {
  const color = CLASS[m.cls].color;
  const imp = m.importance.filter((d) => d.sensor !== "minutes_since_last");
  const maxDrop = Math.max(...imp.map((d) => d.drop), 0.01);
  const total = m.confusion.tp + m.confusion.fn;
  return (
    <article className="model-card" style={{ "--c": color }}>
      <header>
        <h2>{CLASS[m.cls].name}</h2>
        <span>{MODEL_NAME[m.model]}, {m.features} inputs</span>
      </header>
      <div className="model-stats">
        <div><b>{pct(m.recall)}</b><span>of readings before a failure raised an alert</span></div>
        <div><b>{pct(m.precision)}</b><span>of alerts were real</span></div>
        <div><b>{m.pr_auc.toFixed(2)}</b><span>ranking quality (PR-AUC, 1 = perfect)</span></div>
      </div>
      <div className="confusion" aria-label="Confusion matrix">
        <div className="cm tp"><b>{m.confusion.tp.toLocaleString()}</b><span>caught</span></div>
        <div className="cm fn"><b>{m.confusion.fn.toLocaleString()}</b><span>missed</span></div>
        <div className="cm fp"><b>{m.confusion.fp.toLocaleString()}</b><span>false alarms</span></div>
        <div className="cm tn"><b>{m.confusion.tn.toLocaleString()}</b><span>correctly quiet</span></div>
      </div>
      <p className="fine">{total.toLocaleString()} test readings came within 24 h of a failure.</p>
      <h3>What the model listens to</h3>
      <ul className="importance">
        {imp.map((d) => (
          <li key={d.sensor}>
            <span>{sensorName(d.sensor)}</span>
            <span className="imp-bar"><i style={{ width: `${(d.drop / maxDrop) * 100}%`, background: color }} /></span>
          </li>
        ))}
      </ul>
      <p className="fine">Longer bar = the model gets worse if this sensor is scrambled.</p>
    </article>
  );
}

function reliability(cal, view) {
  return {
    ...chartBase,
    grid: { left: 52, right: 16, top: 36, bottom: 40 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted } },
    tooltip: { ...chartBase.tooltip, trigger: "item",
               formatter: (p) => `${p.seriesName}<br/>Said ${pct(p.value[0])}, failed ${pct(p.value[1])}` },
    xAxis: axis({ type: "value", min: 0, max: 1, axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    yAxis: axis({ type: "value", min: 0, max: 1, axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    series: [
      { type: "line", data: [[0, 0], [1, 1]], symbol: "none", lineStyle: { color: C.ink, type: "dashed", width: 1 },
        tooltip: { show: false } },
      ...CLASSES.map((c) => ({ name: CLASS[c].name, type: "line", smooth: true, data: cal.curves[c][view],
                               itemStyle: { color: CLASS[c].color }, lineStyle: { width: 2.5 } })),
    ],
  };
}

function volume(rows) {
  const by = Object.fromEntries(rows.map((r) => [r.machine_class, r]));
  return {
    ...chartBase,
    grid: { left: 150, right: 20, top: 36, bottom: 24 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted } },
    tooltip: { ...chartBase.tooltip, trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => pct(v) },
    xAxis: axis({ type: "value", max: 1, axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    yAxis: axis({ type: "category", inverse: true, data: ["Counting every reading", "One snapshot per shift"],
                  axisLabel: { color: C.ink } }),
    series: CLASSES.map((c) => ({
      name: CLASS[c].name, type: "bar", stack: "v", barWidth: 30, itemStyle: { color: CLASS[c].color },
      label: { show: true, color: "#fff", formatter: (p) => pct(p.value) },
      data: [by[c].share_of_reading_alerts, by[c].share_of_window_alerts],
    })),
  };
}
