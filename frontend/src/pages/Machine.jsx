import React, { useEffect, useMemo, useState } from "react";
import * as echarts from "echarts";
import { api } from "../api.js";
import { useAsync, useDebounced } from "../hooks.js";
import { C, CLASS, MODEL_NAME, axis, chartBase, fmtTime, pct, sensorName, sensorUnit } from "../theme.js";
import WhyPanel from "../components/WhyPanel.jsx";
import { Chart, ClassTag, CrewSlider, Loading, StrategyPicker } from "../components/ui.jsx";

export default function Machine({ fleet, machineId, strategy, setStrategy, k, setK, w, setW, go }) {
  const md = useAsync(() => api.machine(machineId, strategy, k), [machineId, strategy, k]);
  const m = md.data;

  useEffect(() => { echarts.connect("sensors"); }, []);

  // If the machine did not report in the chosen window, jump to its nearest reported one.
  useEffect(() => {
    if (!m) return;
    if (!m.timeline.some((t) => t.window === w)) {
      const nearest = m.timeline.reduce((a, b) => (Math.abs(b.window - w) < Math.abs(a.window - w) ? b : a));
      setW(nearest.window);
    }
  }, [m, w, setW]);

  const point = m?.timeline.find((t) => t.window === w);

  return (
    <div className="page machine">
      <div className="machine-head">
        <div>
          <label className="field machine-pick">
            <span>Machine</span>
            <select value={machineId} onChange={(e) => go("machine", e.target.value)}>
              {["motor", "pump", "compressor"].map((c) => (
                <optgroup key={c} label={CLASS[c].name}>
                  {fleet.machines.filter((x) => x.cls === c).map((x) => <option key={x.id}>{x.id}</option>)}
                </optgroup>
              ))}
            </select>
          </label>
          {m && (
            <p className="machine-meta">
              <ClassTag cls={m.cls} /> Watched by a {MODEL_NAME[m.model]} model, reporting every{" "}
              {m.sample_every_min} minutes, consequence weight {m.severity}.
            </p>
          )}
        </div>
        <div className="controls">
          <StrategyPicker strategy={strategy} setStrategy={setStrategy} compact />
          <CrewSlider k={k} setK={setK} />
        </div>
      </div>

      {!m ? <Loading what={`Loading ${machineId}`} /> : (
        <>
          <section className="panel">
            <div className="panel-head">
              <h2>Failure risk over the test period</h2>
              <p className="muted small">Click any point to inspect that shift. Drag the bar below to zoom.</p>
            </div>
            <Chart height={300} option={riskOption(m, w)}
                   onEvents={{ click: (p) => { const t = m.timeline[p.dataIndex]; if (t) setW(t.window); } }} />
          </section>

          <div className="two-col">
            <section className="panel">
              <h2>Why the model says {point ? pct(point.risk) : "–"} on {point ? fmtTime(point.end) : "–"}</h2>
              {point
                ? <WhyPanel machineId={m.id} cls={m.cls} w={w} />
                : <p className="muted">No reading in this shift.</p>}
            </section>
            <section className="panel">
              <h2>What if the readings were different?</h2>
              {point ? <WhatIf m={m} w={w} strategy={strategy} k={k} point={point} />
                     : <p className="muted">Pick a shift where the machine reported.</p>}
            </section>
          </div>

          <section className="panel">
            <div className="panel-head">
              <h2>Sensor history</h2>
              <p className="muted small">Hourly averages. Dashed line is this machine type's normal level; red lines are failures.</p>
            </div>
            <div className="sensor-grid">
              {m.sensors.map((s) => (
                <Chart key={s.name} group="sensors" height={190} option={sensorOption(m, s, point)} />
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function riskOption(m, w) {
  const x = m.timeline.map((t) => t.end);
  const color = CLASS[m.cls].color;
  const sel = m.timeline.findIndex((t) => t.window === w);
  return {
    ...chartBase,
    grid: { left: 52, right: 24, top: 36, bottom: 70 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted }, itemWidth: 18 },
    tooltip: {
      ...chartBase.tooltip, trigger: "axis",
      formatter: (ps) => {
        const t = m.timeline[ps[0].dataIndex];
        return `<b>${fmtTime(t.end)}</b><br/>Calibrated risk ${pct(t.risk)}<br/>Raw model score ${pct(t.raw)}<br/>`
          + (t.in_queue ? `<b style="color:#8a6a00">In queue, position ${t.rank}</b>` : `Position ${t.rank} (not in queue)`);
      },
    },
    xAxis: axis({ type: "category", data: x, axisLabel: { color: C.muted, formatter: (v) => fmtTime(v).split(",")[0] } }),
    yAxis: axis({ type: "value", min: 0, max: 1, axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    dataZoom: [{ type: "slider", bottom: 10, height: 22, borderColor: C.rule, fillerColor: "rgba(31,35,40,0.08)" },
               { type: "inside" }],
    series: [
      { name: "Raw model score", type: "line", data: m.timeline.map((t) => t.raw), symbol: "none",
        itemStyle: { color: "#9AA0A6" }, lineStyle: { color: "#9AA0A6", type: "dashed", width: 1.5 } },
      { name: "Calibrated risk", type: "line", data: m.timeline.map((t) => t.risk), symbolSize: 6,
        itemStyle: { color }, lineStyle: { color, width: 2.5 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: color + "40" }, { offset: 1, color: color + "00" }]) },
        markArea: {
          silent: true, itemStyle: { color: "rgba(242,183,5,0.22)" },
          data: queueRuns(m.timeline).map(([a, b]) => [{ xAxis: x[a] }, { xAxis: x[b] }]),
        },
        markLine: {
          silent: true, symbol: "none",
          data: [
            ...m.failures.map((f) => ({ xAxis: nearestIndex(x, f), lineStyle: { color: C.signal, width: 2 },
                                        label: { formatter: "Failure", color: C.signal, position: "insideEndTop" } })),
            ...(sel >= 0 ? [{ xAxis: sel, lineStyle: { color: C.ink, type: "solid", width: 1 }, label: { show: false } }] : []),
          ],
        } },
      { name: "In maintenance queue", type: "line", data: [], itemStyle: { color: "rgba(242,183,5,0.6)" } },
    ],
  };
}

function queueRuns(tl) {
  const runs = []; let start = null;
  tl.forEach((t, i) => {
    if (t.in_queue && start === null) start = i;
    if ((!t.in_queue || i === tl.length - 1) && start !== null) { runs.push([start, t.in_queue ? i : i - 1]); start = null; }
  });
  return runs;
}

function nearestIndex(xs, iso) {
  const t = new Date(iso).getTime();
  let best = 0;
  xs.forEach((x, i) => { if (Math.abs(new Date(x).getTime() - t) < Math.abs(new Date(xs[best]).getTime() - t)) best = i; });
  return best;
}

function sensorOption(m, s, point) {
  const color = CLASS[m.cls].color;
  return {
    ...chartBase,
    grid: { left: 52, right: 16, top: 30, bottom: 24 },
    title: { text: `${sensorName(s.name)} (${sensorUnit(s.name)})`, left: 0, top: 0,
             textStyle: { fontSize: 14, fontWeight: 600, color: C.ink, fontFamily: "Barlow" } },
    tooltip: { ...chartBase.tooltip, trigger: "axis",
               valueFormatter: (v) => `${v} ${sensorUnit(s.name)}` },
    xAxis: axis({ type: "time", axisLabel: { color: C.muted, fontSize: 11, hideOverlap: true } }),
    yAxis: axis({ type: "value", scale: true, axisLabel: { color: C.muted, fontSize: 11 } }),
    dataZoom: [{ type: "inside" }],
    series: [{
      type: "line", data: s.points, symbol: "none", lineStyle: { color, width: 1.4 },
      markLine: {
        silent: true, symbol: "none",
        data: [
          { yAxis: s.normal, lineStyle: { color: C.muted, type: "dashed" }, label: { formatter: "normal", color: C.muted, fontSize: 11, position: "insideEndTop" } },
          ...m.failures.map((f) => ({ xAxis: f, lineStyle: { color: C.signal, width: 1.5 }, label: { show: false } })),
          ...(point ? [{ xAxis: point.end, lineStyle: { color: C.ink, width: 1 }, label: { show: false } }] : []),
        ],
      },
    }],
  };
}

function WhatIf({ m, w, strategy, k, point }) {
  const sl = useAsync(() => api.sliders(m.id), [m.id]);
  const [deltas, setDeltas] = useState({});
  useEffect(() => { setDeltas({}); }, [m.id, w]);
  const debounced = useDebounced(deltas, 200);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    api.whatIf(m.id, { window: w, deltas: debounced, strategy, k })
      .then((r) => { if (alive) { setRes(r); setErr(null); } })
      .catch((e) => alive && setErr(e.message));
    return () => { alive = false; };
  }, [m.id, w, debounced, strategy, k]);

  const gauge = useMemo(() => res && gaugeOption(res.risk, point.risk, CLASS[m.cls].color), [res, point, m.cls]);
  if (!sl.data) return <Loading what="Loading sensors" />;
  const changed = Object.values(deltas).some((v) => v !== 0);

  return (
    <div className="whatif">
      <p className="muted small">
        Shift a sensor as if the change built up over the last two hours. The real {MODEL_NAME[m.model]} model
        re-scores the machine and the queue is re-ranked.
      </p>
      <div className="whatif-body">
        <div className="sliders">
          {sl.data.map((s) => (
            <label key={s.sensor} className="slider">
              <span>{sensorName(s.sensor)}
                <b>{(deltas[s.sensor] || 0) > 0 ? "+" : ""}{(deltas[s.sensor] || 0).toFixed(2)} {sensorUnit(s.sensor)}</b>
              </span>
              <input type="range" min={s.min} max={s.max} step={s.step} value={deltas[s.sensor] || 0}
                     onChange={(e) => setDeltas((d) => ({ ...d, [s.sensor]: Number(e.target.value) }))} />
            </label>
          ))}
          <button className="btn ghost" disabled={!changed} onClick={() => setDeltas({})}>Reset to actual readings</button>
        </div>
        <div className="whatif-result" aria-live="polite">
          {gauge && <Chart height={170} option={gauge} />}
          {err && <p className="error">{err}</p>}
          {res && (
            <p className="whatif-rank">
              {res.in_queue
                ? <>Queue position <b>{res.rank}</b> of {res.k}</>
                : <>Position <b>{res.rank}</b>, outside the {res.k} crew slots</>}
              {changed && res.rank !== res.rank_before && <small> (was {res.rank_before})</small>}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function gaugeOption(risk, actual, color) {
  return {
    series: [{
      type: "gauge", startAngle: 200, endAngle: -20, min: 0, max: 1, radius: "100%", center: ["50%", "62%"],
      progress: { show: true, width: 14, itemStyle: { color } },
      axisLine: { lineStyle: { width: 14, color: [[1, "#D5D8D1"]] } },
      axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { show: false }, pointer: { show: false },
      anchor: { show: false },
      title: { offsetCenter: [0, "55%"], fontSize: 12, color: C.muted, fontFamily: "Barlow" },
      detail: { offsetCenter: [0, "5%"], fontSize: 34, fontWeight: 700, fontFamily: "Barlow Condensed",
                color: C.ink, formatter: (v) => `${Math.round(v * 100)}%` },
      data: [{ value: risk, name: `actual reading: ${Math.round(actual * 100)}%` }],
    }],
  };
}
