import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { C, CLASS, CLASSES, STRATEGY, axis, chartBase, fmtTime, pct } from "../theme.js";
import FloorMap from "../components/FloorMap.jsx";
import { Chart, ErrorState, Loading, Segmented } from "../components/ui.jsx";

export default function Story({ fleet, go }) {
  const story = useAsync(() => api.story(), []);
  const cal = useAsync(() => api.calibration(), []);
  const fair = useAsync(() => api.fairness(), []);
  const s = story.data;
  const error = story.error || cal.error || fair.error;

  return (
    <div className="page story">
      <Hero fleet={fleet} s={s} go={go} />
      {error ? <ErrorState title="Couldn't load the research results" error={error}
                           onRetry={() => { story.retry(); cal.retry(); fair.retry(); }}>
        The findings need the story, calibration, and fairness results from the plant data.
      </ErrorState> : !s || !cal.data || !fair.data ? <Loading what="Loading results" /> : (
        <>
          <StepOne cal={cal.data} />
          <StepTwo s={s} fair={fair.data} />
          <Outcome go={go} />
        </>
      )}
    </div>
  );
}

function Hero({ fleet, s, go }) {
  const [w, setW] = useState(30);
  const win = useAsync(() => api.window(w, "S3_risk_priority", fleet.default_k), [w]);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return undefined;
    const t = setInterval(() => setW((x) => (x + 1) % fleet.windows.length), 1800);
    return () => clearInterval(t);
  }, [fleet.windows.length]);

  return (
    <section className="hero">
      <div className="hero-text">
        <h1>One crew. One queue. Better decisions.</h1>
        <p>Three machine-specific models. One ranked maintenance queue. Fairness measured at every step.</p>
        <div className="hero-actions">
          <button className="btn primary" onClick={() => go("control")}>Open the control room</button>
          <a className="btn ghost" href="#step-1">Read the findings</a>
        </div>
        {s && (
          <p className="hero-facts">
            {s.machines} machines, {s.windows} six-hour shifts and {s.failures_in_test} failure events in the held-out test period.
          </p>
        )}
      </div>
      <div className="hero-map" aria-label="Live replay of the plant floor">
        {win.error ? <ErrorState title="Couldn't load the plant replay" error={win.error} onRetry={win.retry} /> : win.data && (
          <>
            <div className="hero-map-head">
              <span className="live-dot" aria-hidden="true" />
              <span>Replay, shift ending {fmtTime(win.data.end)}</span>
            </div>
            <FloorMap machines={win.data.machines} compact onSelect={(id) => go("machine", id)} />
            <p className="fine">Tile colour = failure risk. Striped frame = in today's maintenance queue.</p>
          </>
        )}
      </div>
    </section>
  );
}

function Step({ n, id, title, children, aside }) {
  return (
    <section className="step" id={id}>
      <div className="step-n" aria-hidden="true">{n}</div>
      <div className="step-body">
        <div className="step-copy">
          <h2>{title}</h2>
          {aside}
        </div>
        <div className="step-viz">{children}</div>
      </div>
    </section>
  );
}

function StepOne({ cal }) {
  const [view, setView] = useState("raw");
  const obs = cal.curves.compressor.observed_at_0_8;
  const option = {
    ...chartBase,
    grid: { left: 56, right: 20, top: 40, bottom: 48 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted } },
    tooltip: { ...chartBase.tooltip, trigger: "item",
               formatter: (p) => `${p.seriesName}<br/>Model said ${pct(p.value[0])}<br/>Actually failed ${pct(p.value[1])}` },
    xAxis: axis({ type: "value", min: 0, max: 1, name: "What the model said", nameLocation: "middle", nameGap: 30,
                  axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    yAxis: axis({ type: "value", min: 0, max: 1, name: "How often it really failed", nameLocation: "middle", nameGap: 42,
                  axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    series: [
      { name: "Honest model", type: "line", data: [[0, 0], [1, 1]], symbol: "none",
        lineStyle: { color: C.ink, type: "dashed", width: 1 }, tooltip: { show: false } },
      ...CLASSES.map((c) => ({
        name: CLASS[c].name, type: "line", smooth: true, symbolSize: 7,
        data: cal.curves[c][view], itemStyle: { color: CLASS[c].color }, lineStyle: { width: 2.5 },
      })),
    ],
  };
  return (
    <Step n="1" id="step-1" title="Raw scores are not comparable"
          aside={<>
            <p>Raw model scores share a 0–100% scale, but not the same probability meaning.</p>
            <p className="callout">
              When the compressor model said 70–90%, compressors actually failed only <b>{pct(obs)}</b> of the time.
            </p>
            <p>Calibration re-scales each model on held-out data before the models are ranked together.</p>
          </>}>
      <Segmented label="Score type" value={view} onChange={setView}
                 options={[{ value: "raw", label: "Raw model scores" }, { value: "calibrated", label: "After calibration" }]} />
      <Chart height={340} option={option} />
      <p className="fine">Points on the dashed line mean the model is honest. Test-set data, 10 bins per machine type.</p>
    </Step>
  );
}

function recallBars(fair, k, strategies) {
  const row = (st) => fair.sensitivity.find((r) => r.strategy === st && r.k === k);
  return {
    ...chartBase,
    grid: { left: 56, right: 16, top: 40, bottom: 32 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted } },
    tooltip: { ...chartBase.tooltip, trigger: "axis", valueFormatter: (v) => pct(v, 1) },
    xAxis: axis({ type: "category", data: CLASSES.map((c) => CLASS[c].name) }),
    yAxis: axis({ type: "value", min: 0, max: 1, name: "Real failures that reached the queue",
                  nameLocation: "middle", nameGap: 42, axisLabel: { color: C.muted, formatter: (v) => `${v * 100}%` } }),
    series: strategies.map((st) => ({
      name: STRATEGY[st].short, type: "bar", barGap: "12%", barMaxWidth: 46,
      itemStyle: { color: STRATEGY[st].color, borderRadius: [3, 3, 0, 0] },
      label: { show: true, position: "top", color: C.ink, fontSize: 12, formatter: (p) => pct(p.value) },
      data: CLASSES.map((c) => row(st)?.[`recall_${c}`]),
    })),
  };
}

function StepTwo({ s, fair }) {
  const [k, setK] = useState(4);
  const raw = s.compressor.S1_raw;
  const calibrated = s.compressor.S2_calibrated;
  const priority = s.compressor.S3_risk_priority;
  const atFour = (strategy) => fair.sensitivity.find((row) => row.strategy === strategy && row.k === 4);
  const priorityAtFour = atFour("S3_risk_priority");
  const safeguardAtFour = atFour("S4_class_fair");
  return (
    <Step n="2" title="A queue is a policy choice"
          aside={<>
            <p>
              At {s.k} crew slots, calibration alone lowers compressor recall from <b>{pct(raw.recall, 1)}</b> to{" "}
              <b>{pct(calibrated.recall, 1)}</b>. Its 95% bootstrap interval is a {(-calibrated.ci_high * 100).toFixed(1)}–
              {(-calibrated.ci_low * 100).toFixed(1)} point decrease.
            </p>
            <p className="callout">
              Risk × consequence × freshness returns compressor recall to <b>{pct(priority.recall, 1)}</b> while overall
              recall is <b>{pct(s.overall.S3_risk_priority.recall, 1)}</b> (raw scores: {pct(s.overall.S1_raw.recall, 1)}).
            </p>
            <p>
              With four slots, the class safeguard raises compressor recall from {pct(priorityAtFour.recall_compressor, 1)} to{" "}
              {pct(safeguardAtFour.recall_compressor, 1)}, but lowers overall recall from {pct(priorityAtFour.recall_at_k, 1)} to{" "}
              {pct(safeguardAtFour.recall_at_k, 1)}. It redistributes access; it does not guarantee a gain.
            </p>
          </>}>
      <label className="field crew">
        <span>Crew can inspect <b>{k}</b> machines per shift</span>
        <input type="range" min={2} max={16} value={k} onChange={(e) => setK(Number(e.target.value))} />
      </label>
      <Chart height={320} option={recallBars(fair, k, ["S1_raw", "S2_calibrated", "S3_risk_priority", "S4_class_fair"])} />
    </Step>
  );
}

function Outcome({ go }) {
  return (
    <section className="outcome">
      <div className="limits">
        <h2>Scope and limits</h2>
        <p>
          The data is simulated: these findings show how the queue behaves, not accuracy on real equipment.
          Consequence weights are prototype assumptions that a plant would replace with its own downtime costs.
        </p>
      </div>
      <div className="hero-actions">
        <button className="btn primary" onClick={() => go("control")}>Open the control room</button>
        <button className="btn ghost" onClick={() => go("method")}>See how it works</button>
      </div>
    </section>
  );
}
