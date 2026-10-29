import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { C, CLASS, CLASSES, STRATEGY, axis, chartBase, fmtTime, pct } from "../theme.js";
import FloorMap from "../components/FloorMap.jsx";
import { Chart, Loading, Segmented } from "../components/ui.jsx";

export default function Story({ fleet, go }) {
  const story = useAsync(() => api.story(), []);
  const cal = useAsync(() => api.calibration(), []);
  const fair = useAsync(() => api.fairness(), []);
  const s = story.data;

  return (
    <div className="page story">
      <Hero fleet={fleet} s={s} go={go} />
      {!s || !cal.data || !fair.data ? <Loading what="Loading results" /> : (
        <>
          <StepOne s={s} cal={cal.data} />
          <StepTwo s={s} fair={fair.data} />
          <StepThree s={s} fair={fair.data} />
          <Outcome s={s} go={go} />
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
        <h1>Three kinds of machine, three AI models, one maintenance crew. Which machine do you fix first?</h1>
        <p>
          Plants usually run a separate failure-prediction model for each machine type. Each model is fine on its
          own, but their scores mean different things, so nobody can tell which alert matters most. This platform
          turns them into one queue the crew can trust, and checks that no machine type gets ignored.
        </p>
        <div className="hero-actions">
          <button className="btn primary" onClick={() => go("control")}>Open the control room</button>
          <a className="btn ghost" href="#step-1">Read the findings</a>
        </div>
        {s && (
          <p className="hero-facts">
            {s.machines} machines, {s.windows} six-hour shifts and {s.failures_in_test} real failures in the test period.
          </p>
        )}
      </div>
      <div className="hero-map" aria-label="Live replay of the plant floor">
        {win.data && (
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
        <h2>{title}</h2>
        <div className="step-grid">
          <div className="step-copy">{aside}</div>
          <div className="step-viz">{children}</div>
        </div>
      </div>
    </section>
  );
}

function StepOne({ s, cal }) {
  const [view, setView] = useState("raw");
  const comp = s.calibration.find((c) => c.machine_class === "compressor");
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
    <Step n="1" id="step-1" title="The three models don't speak the same language"
          aside={<>
            <p>
              Each model outputs a number between 0 and 100%. You would expect 80% to mean the same thing everywhere.
              It doesn't.
            </p>
            <p className="callout">
              When the compressor model said 70–90%, compressors actually failed only <b>{pct(obs)}</b> of the time.
            </p>
            <p>
              The models over-state risk, the compressor model most of all: it averages {pct(comp.mean_raw_risk)} risk
              where the true rate is {pct(comp.actual_rate)}. We re-scale each model separately on held-back data
              (calibration), which cuts the error by {Math.round(Math.min(...s.calibration.map((c) => c.brier_improvement_pct)))}–
              {Math.round(Math.max(...s.calibration.map((c) => c.brier_improvement_pct)))}%.
            </p>
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
  const [k, setK] = useState(s.k);
  const c1 = s.compressor.S1_raw, c2 = s.compressor.S2_calibrated;
  return (
    <Step n="2" title="Fixing the language alone hides compressor failures"
          aside={<>
            <p>
              Once scores are calibrated, the compressor model is honest but unsure: even its real failures only
              reach moderate risk. Sharper motor predictions push them down the queue.
            </p>
            <p className="callout">
              With {s.k} crew slots per shift, the share of real compressor failures that reach the queue drops from{" "}
              <b>{pct(c1.recall)}</b> to <b>{pct(c2.recall)}</b>.
            </p>
            <p>
              That drop is statistically real: across 1,000 resamples of the test shifts it stays between{" "}
              {Math.round(-c2.ci_high * 100)} and {Math.round(-c2.ci_low * 100)} points. With a smaller crew it gets much worse.
              Try the slider.
            </p>
          </>}>
      <label className="field crew">
        <span>Crew can inspect <b>{k}</b> machines per shift</span>
        <input type="range" min={2} max={16} value={k} onChange={(e) => setK(Number(e.target.value))} />
      </label>
      <Chart height={320} option={recallBars(fair, k, ["S1_raw", "S2_calibrated"])} />
    </Step>
  );
}

function StepThree({ s, fair }) {
  const [k, setK] = useState(4);
  const t = s.tight_crew;
  return (
    <Step n="3" title="Weighting by consequence and data freshness puts them back"
          aside={<>
            <p>
              The queue should rank by what a failure would cost, not by probability alone. Our rule multiplies
              calibrated risk by a consequence weight per machine type and by how fresh the readings are.
            </p>
            <p className="callout">
              Compressor recall returns to <b>{pct(s.compressor.S3_risk_priority.recall)}</b>, and overall recall
              stays at {pct(s.overall.S3_risk_priority.recall)} (raw scores: {pct(s.overall.S1_raw.recall)}).
            </p>
            <p>
              This is a policy choice, not a free lunch. With 4 slots, motors give up some attention (from{" "}
              {pct(t.S1_raw.motor)} to {pct(t.S3_risk_priority.motor)}) so pumps and compressors get more. The
              optional safeguard guarantees each machine type at least one slot when it has a credible alert.
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

function Outcome({ s, go }) {
  return (
    <section className="outcome">
      <h2>What this gives a plant</h2>
      <div className="outcome-grid">
        <div>
          <h3>One queue instead of three alarm lists</h3>
          <p>Every shift, the crew gets a ranked list with a plain reason for each machine.</p>
        </div>
        <div>
          <h3>No machine type left behind</h3>
          <p>Fairness is measured per machine type, so a weaker model can't quietly lose its alerts.</p>
        </div>
        <div>
          <h3>Models that explain themselves</h3>
          <p>For any machine, see which sensor is driving the risk and test "what if" changes live.</p>
        </div>
      </div>
      <div className="limits">
        <h3>What we state up front</h3>
        <p>
          The plant data is simulated, so these results show how the method behaves, not accuracy on real equipment.
          The consequence weights are assumptions that a plant would replace with its own downtime costs. The next
          step is a pilot on one production line's historian and maintenance records.
        </p>
      </div>
      <div className="hero-actions">
        <button className="btn primary" onClick={() => go("control")}>Open the control room</button>
        <button className="btn ghost" onClick={() => go("method")}>See how it works</button>
      </div>
    </section>
  );
}
