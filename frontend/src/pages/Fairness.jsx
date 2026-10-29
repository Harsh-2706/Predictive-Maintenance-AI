import React, { useState } from "react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { C, CLASS, CLASSES, STRATEGY, STRATEGIES, axis, chartBase, pct } from "../theme.js";
import { Chart, Loading, Segmented } from "../components/ui.jsx";

export default function Fairness({ k, setK }) {
  const fair = useAsync(() => api.fairness(), []);
  const [focus, setFocus] = useState("compressor");
  const [picked, setPicked] = useState(["S1_raw", "S2_calibrated", "S3_risk_priority", "S4_class_fair"]);
  if (!fair.data) return <div className="page"><Loading what="Loading fairness results" /></div>;
  const f = fair.data;
  const toggle = (s) => setPicked((p) => (p.includes(s) ? (p.length > 1 ? p.filter((x) => x !== s) : p) : [...p, s]));

  return (
    <div className="page fairness">
      <h1>Fairness lab</h1>
      <p className="lede">
        A fair queue gives every machine type a comparable chance that its real failures get inspected. Change the
        crew size and the ranking rules to see where each rule helps and where it costs.
      </p>

      <div className="panel">
        <div className="panel-head row">
          <h2>How many real {CLASS[focus].one} failures reach the queue, as the crew grows</h2>
          <Segmented label="Machine type" value={focus} onChange={setFocus}
                     options={CLASSES.map((c) => ({ value: c, label: CLASS[c].name }))} />
        </div>
        <div className="chips" role="group" aria-label="Ranking rules shown">
          {STRATEGIES.map((s) => (
            <button key={s} className={`chip ${picked.includes(s) ? "on" : ""}`} style={{ "--c": STRATEGY[s].color }}
                    aria-pressed={picked.includes(s)} onClick={() => toggle(s)}>
              <i />{STRATEGY[s].short}
            </button>
          ))}
        </div>
        <Chart height={340} option={capacityOption(f, focus, picked, k)}
               onEvents={{ click: (p) => p.value && setK(p.value[0]) }} />
        <p className="fine">Click a point to set the crew size used below. Dotted line = current crew size ({k}).</p>
      </div>

      <div className="two-col">
        <div className="panel">
          <h2>All machine types with a crew of {k}</h2>
          <label className="field crew">
            <span>Crew size <b>{k}</b></span>
            <input type="range" min={2} max={16} value={k} onChange={(e) => setK(Number(e.target.value))} />
          </label>
          <Chart height={300} option={byClassOption(f, k, picked)} />
        </div>
        <div className="panel">
          <h2>Who gets the crew's time?</h2>
          <p className="muted small">Share of queue slots compared with share of real failures, crew of {f.k_default}.</p>
          <Chart height={330} option={shareOption(f)} />
        </div>
      </div>

      <div className="panel">
        <h2>Is the difference real, or noise?</h2>
        <p className="muted small">
          Change in the share of real failures reaching the queue, compared with raw scores, crew of {f.k_default}.
          Bars are 95% ranges from 1,000 resamples of the test shifts. Dark bars do not cross zero, so those effects are
          real; grey bars are within noise.
        </p>
        <Chart height={300} option={ciOption(f)} />
      </div>
    </div>
  );
}

function capacityOption(f, cls, picked, k) {
  return {
    ...chartBase,
    grid: { left: 56, right: 20, top: 20, bottom: 48 },
    tooltip: { ...chartBase.tooltip, trigger: "axis", valueFormatter: (v) => pct(v, 1),
               axisPointer: { type: "line" } },
    xAxis: axis({ type: "value", min: 2, max: 16, name: "Machines the crew can inspect per shift", nameLocation: "middle", nameGap: 30 }),
    yAxis: axis({ type: "value", min: 0, max: 1, axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    series: picked.map((s, i) => ({
      name: STRATEGY[s].short, type: "line", symbolSize: 7,
      itemStyle: { color: STRATEGY[s].color }, lineStyle: { width: s === "S3_risk_priority" ? 3.5 : 2 },
      data: f.sensitivity.filter((r) => r.strategy === s).map((r) => [r.k, r[`recall_${cls}`]]),
      markLine: i === 0 ? { silent: true, symbol: "none", data: [{ xAxis: k }],
                            lineStyle: { color: C.ink, type: "dotted" }, label: { show: false } } : undefined,
    })),
  };
}

function byClassOption(f, k, picked) {
  const row = (s) => f.sensitivity.find((r) => r.strategy === s && r.k === k);
  return {
    ...chartBase,
    grid: { left: 56, right: 12, top: 36, bottom: 30 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted }, itemWidth: 14 },
    tooltip: { ...chartBase.tooltip, trigger: "axis", valueFormatter: (v) => pct(v, 1) },
    xAxis: axis({ type: "category", data: CLASSES.map((c) => CLASS[c].name) }),
    yAxis: axis({ type: "value", min: 0, max: 1, axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    series: picked.map((s) => ({
      name: STRATEGY[s].short, type: "bar", barMaxWidth: 34, itemStyle: { color: STRATEGY[s].color, borderRadius: [3, 3, 0, 0] },
      data: CLASSES.map((c) => row(s)?.[`recall_${c}`]),
    })),
  };
}

function shareOption(f) {
  const cats = ["Real failures", ...STRATEGIES.map((s) => STRATEGY[s].short)];
  const get = (s, c, col) => f.per_class.find((r) => r.strategy === s && r.machine_class === c)?.[col];
  return {
    ...chartBase,
    grid: { left: 120, right: 20, top: 36, bottom: 24 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted } },
    tooltip: { ...chartBase.tooltip, trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => pct(v) },
    xAxis: axis({ type: "value", max: 1, axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    yAxis: axis({ type: "category", data: cats, inverse: true, axisLabel: { color: C.ink, fontSize: 12 } }),
    series: CLASSES.map((c) => ({
      name: CLASS[c].name, type: "bar", stack: "s", barWidth: 22, itemStyle: { color: CLASS[c].color },
      label: { show: true, color: "#fff", fontSize: 11, formatter: (p) => (p.value > 0.08 ? pct(p.value) : "") },
      data: [get("S1_raw", c, "failure_share"), ...STRATEGIES.map((s) => get(s, c, "queue_share"))],
    })),
  };
}

function ciOption(f) {
  const strategies = STRATEGIES.filter((s) => s !== "S1_raw");
  const cats = [];
  const points = [];
  const ranges = [];
  CLASSES.forEach((c) => strategies.forEach((s) => {
    const r = f.per_class.find((x) => x.strategy === s && x.machine_class === c);
    const label = `${CLASS[c].name}: ${STRATEGY[s].short}`;
    cats.push(label);
    const sig = r.recall_vs_S1_ci_high < 0 || r.recall_vs_S1_ci_low > 0;
    points.push({ value: [r.recall_vs_S1, label], itemStyle: { color: STRATEGY[s].color, borderColor: C.ink, borderWidth: sig ? 2 : 0 } });
    ranges.push([r.recall_vs_S1_ci_low, r.recall_vs_S1_ci_high, label, sig]);
  }));
  return {
    ...chartBase,
    grid: { left: 230, right: 30, top: 10, bottom: 36 },
    tooltip: { ...chartBase.tooltip, trigger: "item",
               formatter: (p) => {
                 const r = ranges[p.dataIndex];
                 return `${r[2]}<br/>Change ${(p.value[0] * 100).toFixed(1)} pts<br/>95% range ${(r[0] * 100).toFixed(1)} to ${(r[1] * 100).toFixed(1)}`
                   + (r[3] ? "<br/><b>Real effect</b>" : "<br/>Within noise");
               } },
    xAxis: axis({ type: "value", axisLabel: { color: C.muted, formatter: (v) => `${(v * 100).toFixed(0)} pts` } }),
    yAxis: axis({ type: "category", data: cats, inverse: true, axisLabel: { color: C.ink, fontSize: 12 } }),
    series: [
      { type: "custom", renderItem: (params, api) => {
          const lo = api.coord([api.value(0), api.value(2)]);
          const hi = api.coord([api.value(1), api.value(2)]);
          return { type: "line", shape: { x1: lo[0], y1: lo[1], x2: hi[0], y2: hi[1] },
                   style: { stroke: api.value(3) ? C.ink : "#A7ADB2", lineWidth: api.value(3) ? 4 : 2.5 } };
        },
        encode: { x: [0, 1], y: 2 }, data: ranges, silent: true, z: 1 },
      { type: "scatter", symbolSize: 11, data: points, z: 2,
        markLine: { silent: true, symbol: "none", data: [{ xAxis: 0 }], lineStyle: { color: C.ink }, label: { show: false } } },
    ],
  };
}
