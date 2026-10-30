import React, { useState } from "react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { C, CLASS, CLASSES, STRATEGY, STRATEGIES, axis, chartBase, pct } from "../theme.js";
import { Chart, ErrorState, Loading, Segmented } from "../components/ui.jsx";
import { FairnessAllocationVisual } from "../components/SectionVisuals.jsx";

export default function Fairness({ k, setK, strategy, setStrategy }) {
  const fair = useAsync(() => api.fairness(), []);
  const [focus, setFocus] = useState("compressor");

  if (fair.error) {
    return <div className="page"><ErrorState title="Couldn't load fairness results" error={fair.error} onRetry={fair.retry} /></div>;
  }
  if (!fair.data) return <div className="page"><Loading what="Loading fairness results" /></div>;

  const f = fair.data;
  const selected = f.sensitivity.find((row) => row.strategy === strategy && row.k === k);
  const selectedClassRecall = selected?.[`recall_${focus}`];

  return (
    <div className="page fairness">
      <header className="section-intro fairness-intro">
        <div>
          <p className="fairness-kicker">Maintenance-policy experiment</p>
          <h1>Which failures reach the crew?</h1>
          <p className="lede">
            Compare how crew capacity and ranking strategy change captured and missed failures across motors, pumps, and compressors.
          </p>
        </div>
        <FairnessAllocationVisual capacity={k} focus={focus} />
      </header>

      <section className="panel fairness-primary">
        <div className="fairness-primary-head">
          <div>
            <h2>Strategy versus capacity</h2>
            <p className="muted small">
              Each line is the share of real {CLASS[focus].one} failures captured by the maintenance queue. The remainder is missed.
            </p>
          </div>
          <Segmented label="Machine class" value={focus} onChange={setFocus}
                     options={CLASSES.map((cls) => ({ value: cls, label: CLASS[cls].name }))} />
        </div>

        <div className="fairness-controls">
          <label className="field fairness-policy">
            <span>Selected ranking strategy</span>
            <select value={strategy} onChange={(event) => setStrategy(event.target.value)}>
              {STRATEGIES.map((id) => <option key={id} value={id}>{STRATEGY[id].short}</option>)}
            </select>
          </label>
          <label className="field crew fairness-crew">
            <span>Crew capacity <b>{k}</b> machines per 6-hour shift</span>
            <input type="range" min={2} max={16} value={k} onChange={(event) => setK(Number(event.target.value))} />
          </label>
        </div>

        <Chart height={410} option={capacityOption(f, focus, strategy, k)}
               onEvents={{ click: (event) => event.value && setK(event.value[0]) }} />
        <p className="fine">All four strategies remain visible. Click a point to set the shared crew capacity; the selected policy is drawn strongest.</p>

        <div className="policy-readout" aria-label="Selected policy results">
          <div>
            <span>Selected policy</span>
            <b style={{ color: STRATEGY[strategy].color }}>{STRATEGY[strategy].short}</b>
          </div>
          <div>
            <span>Overall recall</span>
            <b>{pct(selected?.recall_at_k, 1)}</b>
            <small>all real failures captured</small>
          </div>
          <div>
            <span>{CLASS[focus].name} captured</span>
            <b>{pct(selectedClassRecall, 1)}</b>
            <small>per-class recall</small>
          </div>
          <div>
            <span>{CLASS[focus].name} missed</span>
            <b>{pct(selectedClassRecall == null ? null : 1 - selectedClassRecall, 1)}</b>
            <small>not in the queue</small>
          </div>
        </div>
      </section>

      <section className="fairness-results" aria-labelledby="class-results-title">
        <div className="fairness-section-head">
          <div>
            <p className="fairness-kicker">Selected policy at {k} crew slots</p>
            <h2 id="class-results-title">What does the crew capture by machine class?</h2>
          </div>
          <span className="fairness-definition">Overall recall combines all classes. These results keep the classes separate.</span>
        </div>
        <div className="class-results">
          {CLASSES.map((cls) => {
            const recall = selected?.[`recall_${cls}`];
            return (
              <button key={cls} type="button" className={`class-result ${focus === cls ? "selected" : ""}`}
                      style={{ "--class-color": CLASS[cls].color }} onClick={() => setFocus(cls)}>
                <span>{CLASS[cls].name}</span>
                <b>{pct(recall, 1)}</b>
                <small>{pct(recall == null ? null : 1 - recall, 1)} missed</small>
              </button>
            );
          })}
        </div>
      </section>

      <div className="two-col fairness-support">
        <section className="panel">
          <div className="panel-head">
            <p className="fairness-kicker">Allocation diagnostic</p>
            <h2>Queue share is not failure share</h2>
          </div>
          <p className="muted small">For {STRATEGY[strategy].short}, compare where failures occurred with where queue slots went.</p>
          <Chart height={260} option={shareOption(f, strategy)} />
          <p className="fine">Allocation is reported at the default analysis capacity of {f.k_default} slots; the capacity curve above is the interactive comparison.</p>
        </section>

        <section className="panel fairness-uncertainty">
          <div className="panel-head">
            <p className="fairness-kicker">Uncertainty diagnostic</p>
            <h2>Does the change hold up?</h2>
          </div>
          <p className="muted small">
            {CLASS[focus].name} recall changes versus raw scores at {f.k_default} slots. Ranges are 95% bootstrap intervals from 1,000 resamples.
          </p>
          <Chart height={260} option={ciOption(f, focus, strategy)} />
        </section>
      </div>

      <aside className="fairness-note">
        <strong>Choose deliberately</strong>
        <span>
          A higher overall recall can still leave one class with more missed failures. The S4 safeguard can redistribute queue access, but it does not automatically maximise overall or every class’s recall.
        </span>
      </aside>

      <p className="fine fairness-disclosure">All findings use simulated plant data and the same held-out test windows for every strategy.</p>
    </div>
  );
}

function capacityOption(f, cls, selectedStrategy, k) {
  return {
    ...chartBase,
    grid: { left: 60, right: 24, top: 38, bottom: 50 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted }, itemWidth: 14, itemGap: 16 },
    tooltip: { ...chartBase.tooltip, trigger: "axis", valueFormatter: (value) => pct(value, 1), axisPointer: { type: "line" } },
    xAxis: axis({ type: "value", min: 2, max: 16, name: "Machines the crew can inspect per 6-hour shift", nameLocation: "middle", nameGap: 32 }),
    yAxis: axis({ type: "value", min: 0, max: 1, name: "Failures captured (per-class recall)", nameLocation: "middle", nameGap: 46,
                  axisLabel: { color: C.muted, formatter: (value) => `${value * 100}%` } }),
    series: STRATEGIES.map((id, index) => ({
      name: STRATEGY[id].short,
      type: "line",
      symbolSize: id === selectedStrategy ? 8 : 6,
      itemStyle: { color: STRATEGY[id].color, opacity: id === selectedStrategy ? 1 : 0.68 },
      lineStyle: { width: id === selectedStrategy ? 4 : 2, opacity: id === selectedStrategy ? 1 : 0.72 },
      data: f.sensitivity.filter((row) => row.strategy === id).map((row) => [row.k, row[`recall_${cls}`]]),
      markLine: index === 0 ? { silent: true, symbol: "none", data: [{ xAxis: k }],
                                lineStyle: { color: C.ink, type: "dotted" }, label: { show: false } } : undefined,
    })),
  };
}

function shareOption(f, strategy) {
  const get = (cls, column) => f.per_class.find((row) => row.strategy === strategy && row.machine_class === cls)?.[column];
  return {
    ...chartBase,
    grid: { left: 112, right: 18, top: 30, bottom: 24 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted }, itemWidth: 14 },
    tooltip: { ...chartBase.tooltip, trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value) => pct(value) },
    xAxis: axis({ type: "value", max: 1, axisLabel: { color: C.muted, formatter: (value) => `${value * 100}%` } }),
    yAxis: axis({ type: "category", data: ["Failure share", "Queue share"], inverse: true, axisLabel: { color: C.ink, fontSize: 12 } }),
    series: CLASSES.map((cls) => ({
      name: CLASS[cls].name,
      type: "bar",
      stack: "share",
      barWidth: 28,
      itemStyle: { color: CLASS[cls].color },
      label: { show: true, color: "#fff", fontSize: 11, formatter: (point) => (point.value > 0.08 ? pct(point.value) : "") },
      data: [get(cls, "failure_share"), get(cls, "queue_share")],
    })),
  };
}

function ciOption(f, cls, selectedStrategy) {
  const strategies = STRATEGIES.filter((id) => id !== "S1_raw");
  const ranges = strategies.map((id) => {
    const row = f.per_class.find((item) => item.strategy === id && item.machine_class === cls);
    const significant = row.recall_vs_S1_ci_high < 0 || row.recall_vs_S1_ci_low > 0;
    return [row.recall_vs_S1_ci_low, row.recall_vs_S1_ci_high, STRATEGY[id].short, significant, id, row.recall_vs_S1];
  });
  return {
    ...chartBase,
    grid: { left: 148, right: 24, top: 12, bottom: 38 },
    tooltip: { ...chartBase.tooltip, trigger: "item", formatter: (point) => {
      const row = ranges[point.dataIndex];
      return `${row[2]}<br/>Change ${(row[5] * 100).toFixed(1)} pts<br/>95% interval ${(row[0] * 100).toFixed(1)} to ${(row[1] * 100).toFixed(1)} pts`
        + (row[3] ? "<br/><b>Interval excludes zero</b>" : "<br/>Interval includes zero");
    } },
    xAxis: axis({ type: "value", axisLabel: { color: C.muted, formatter: (value) => `${(value * 100).toFixed(0)} pts` } }),
    yAxis: axis({ type: "category", data: ranges.map((row) => row[2]), inverse: true, axisLabel: { color: C.ink, fontSize: 12 } }),
    series: [
      { type: "custom", renderItem: (params, api) => {
          const low = api.coord([api.value(0), api.value(2)]);
          const high = api.coord([api.value(1), api.value(2)]);
          const selected = api.value(4) === selectedStrategy;
          return { type: "line", shape: { x1: low[0], y1: low[1], x2: high[0], y2: high[1] },
                   style: { stroke: selected ? C.ink : "#A7ADB2", lineWidth: selected ? 4 : 2.5 } };
        }, encode: { x: [0, 1], y: 2 }, data: ranges, silent: true, z: 1 },
      { type: "scatter", symbolSize: 11, data: ranges.map((row) => ({
          value: [row[5], row[2]], itemStyle: { color: STRATEGY[row[4]].color, borderColor: C.ink, borderWidth: row[4] === selectedStrategy ? 2 : 0 },
        })), z: 2, markLine: { silent: true, symbol: "none", data: [{ xAxis: 0 }], lineStyle: { color: C.ink }, label: { show: false } } },
    ],
  };
}
