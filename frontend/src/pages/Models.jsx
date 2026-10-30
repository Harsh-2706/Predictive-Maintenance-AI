import React, { useState } from "react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { C, CLASS, CLASSES, MODEL_NAME, axis, chartBase, pct, sensorName } from "../theme.js";
import { Chart, ErrorState, Loading, Segmented } from "../components/ui.jsx";
import { ModelCalibrationVisual } from "../components/SectionVisuals.jsx";

const PERFORMANCE = {
  recall: { label: "Recall", detail: "failures the model alerted before" },
  precision: { label: "Precision", detail: "alerts that were real" },
  pr_auc: { label: "PR-AUC", detail: "ranking quality" },
};

export default function Models() {
  const models = useAsync(() => api.models(), []);
  const calibration = useAsync(() => api.calibration(), []);
  const [curve, setCurve] = useState("calibrated");
  const [metric, setMetric] = useState("recall");
  const [focus, setFocus] = useState("compressor");
  const error = models.error || calibration.error;

  if (error) {
    return <div className="page"><ErrorState title="Couldn't load model evidence" error={error}
                                                onRetry={() => { models.retry(); calibration.retry(); }} /></div>;
  }
  if (!models.data || !calibration.data) return <div className="page"><Loading what="Loading model evidence" /></div>;

  const cards = models.data.cards;
  const focusedModel = cards.find((card) => card.cls === focus);

  return (
    <div className="page models">
      <header className="section-intro models-intro">
        <div>
          <p className="models-kicker">Model evidence</p>
          <h1>Trust the risk, not just the score.</h1>
          <p className="lede">Three machine-specific models. Calibrated probabilities. One shared maintenance decision.</p>
        </div>
        <ModelCalibrationVisual />
      </header>

      <section className="models-lineup" aria-labelledby="lineup-title">
        <div className="models-section-head">
          <div>
            <p className="models-kicker">Model lineup</p>
            <h2 id="lineup-title">Different equipment, specialised models</h2>
          </div>
          <p>Each model estimates whether its machine will fail within the next 24 hours from its own sensor history.</p>
        </div>
        <div className="model-lineup-grid">
          {cards.map((model) => <LineupCard key={model.cls} model={model} />)}
        </div>
      </section>

      <section className="panel calibration-primary" aria-labelledby="calibration-title">
        <div className="models-section-head calibration-head">
          <div>
            <p className="models-kicker">Primary evidence</p>
            <h2 id="calibration-title">Does a stated risk match what actually happens?</h2>
            <p>Calibration compares predicted failure risk with the observed failure rate. Closer to the diagonal means a stated probability is more trustworthy.</p>
          </div>
          <Segmented label="Reliability curve" value={curve} onChange={setCurve}
                     options={[{ value: "raw", label: "Raw scores" }, { value: "calibrated", label: "Calibrated risk" }]} />
        </div>
        <Chart height={390} option={reliabilityOption(calibration.data, curve)} />
        <div className="calibration-evidence" aria-label="Calibration Brier score evidence">
          {CLASSES.map((cls) => <CalibrationRow key={cls} cls={cls} row={calibration.data.report.find((item) => item.machine_class === cls)} />)}
        </div>
        <p className="fine">
          Brier score is lower when probabilities are more accurate. Raw scores are model outputs; calibrated risk is the probability used for cross-machine comparison.
        </p>
      </section>

      <section className="panel model-performance" aria-labelledby="performance-title">
        <div className="models-section-head">
          <div>
            <p className="models-kicker">Test-set performance</p>
            <h2 id="performance-title">Compare the behaviour, not a single winner</h2>
            <p>These class-specific test metrics share a 0–1 scale, but each model sees a different failure pattern and sensor set.</p>
          </div>
          <Segmented label="Performance metric" value={metric} onChange={setMetric}
                     options={Object.entries(PERFORMANCE).map(([value, item]) => ({ value, label: item.label }))} />
        </div>
        <Chart height={300} option={performanceOption(cards, metric)} />
        <p className="fine">{PERFORMANCE[metric].label} = {PERFORMANCE[metric].detail}. Use this comparison to understand trade-offs, not to treat the machine classes as identical tasks.</p>
      </section>

      <section className="models-diagnostics" aria-labelledby="diagnostics-title">
        <div className="models-section-head">
          <div>
            <p className="models-kicker">Technical diagnostics</p>
            <h2 id="diagnostics-title">Inspect one model in detail</h2>
          </div>
          <Segmented label="Machine class diagnostic" value={focus} onChange={setFocus}
                     options={CLASSES.map((cls) => ({ value: cls, label: CLASS[cls].name }))} />
        </div>
        <div className="two-col diagnostics-grid">
          <article className="panel diagnostic-card">
            <p className="models-kicker">Alert outcomes</p>
            <h3>{CLASS[focus].name}: test-set confusion counts</h3>
            <ConfusionGrid confusion={focusedModel.confusion} />
            <p className="fine">Counts are reading-level outcomes at the configured alert threshold, not a direct comparison of fleet-level queue outcomes.</p>
          </article>
          <article className="panel diagnostic-card">
            <p className="models-kicker">Sensor dependence</p>
            <h3>What moves the {CLASS[focus].one} model?</h3>
            <ImportanceList model={focusedModel} />
            <p className="fine">Longer bars show a larger PR-AUC drop when that sensor group is shuffled.</p>
          </article>
        </div>
      </section>

      <section className="panel reporting-diagnostic">
        <div className="models-section-head">
          <div>
            <p className="models-kicker">Input-rate diagnostic</p>
            <h2>Fast-reporting machines should not dominate by volume</h2>
          </div>
          <p>Motors report more frequently than compressors. The queue therefore uses one latest-reading snapshot per machine per review shift.</p>
        </div>
        <Chart height={270} option={volumeOption(models.data.volume)} />
      </section>

      <p className="fine models-disclosure">All metrics and calibration evidence use simulated plant data and the held-out test split.</p>
    </div>
  );
}

function LineupCard({ model }) {
  const color = CLASS[model.cls].color;
  return (
    <article className="model-lineup-card" style={{ "--model-color": color }}>
      <header>
        <span className="models-kicker">{CLASS[model.cls].name}</span>
        <h3>{MODEL_NAME[model.model]}</h3>
        <p>Predicts failure within 24 h · {model.features} inputs</p>
      </header>
      <dl>
        <div><dt>Recall</dt><dd>{pct(model.recall, 1)}</dd></div>
        <div><dt>Precision</dt><dd>{pct(model.precision, 1)}</dd></div>
        <div><dt>PR-AUC</dt><dd>{model.pr_auc.toFixed(2)}</dd></div>
      </dl>
    </article>
  );
}

function CalibrationRow({ cls, row }) {
  const improvement = row?.brier_improvement_pct;
  return (
    <article className="calibration-row" style={{ "--model-color": CLASS[cls].color }}>
      <span>{CLASS[cls].name}</span>
      <div><small>Raw Brier</small><b>{row?.brier_raw?.toFixed(3) ?? "–"}</b></div>
      <div><small>Calibrated Brier</small><b>{row?.brier_calibrated?.toFixed(3) ?? "–"}</b></div>
      <div><small>Change</small><b>{improvement == null ? "–" : `−${improvement.toFixed(0)}%`}</b></div>
    </article>
  );
}

function ConfusionGrid({ confusion }) {
  return (
    <div className="confusion" aria-label="Confusion matrix">
      <div className="cm tp"><b>{confusion.tp.toLocaleString()}</b><span>caught</span></div>
      <div className="cm fn"><b>{confusion.fn.toLocaleString()}</b><span>missed</span></div>
      <div className="cm fp"><b>{confusion.fp.toLocaleString()}</b><span>false alarms</span></div>
      <div className="cm tn"><b>{confusion.tn.toLocaleString()}</b><span>correctly quiet</span></div>
    </div>
  );
}

function ImportanceList({ model }) {
  const values = model.importance.filter((item) => item.sensor !== "minutes_since_last");
  const maxDrop = Math.max(...values.map((item) => item.drop), 0.01);
  return (
    <ul className="importance">
      {values.map((item) => (
        <li key={item.sensor}>
          <span>{sensorName(item.sensor)}</span>
          <span className="imp-bar"><i style={{ width: `${(item.drop / maxDrop) * 100}%`, background: CLASS[model.cls].color }} /></span>
        </li>
      ))}
    </ul>
  );
}

function reliabilityOption(calibration, view) {
  return {
    ...chartBase,
    grid: { left: 64, right: 24, top: 38, bottom: 50 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted }, itemWidth: 14, itemGap: 18 },
    tooltip: { ...chartBase.tooltip, trigger: "item",
               formatter: (point) => `${point.seriesName}<br/>Predicted ${pct(point.value[0], 1)}<br/>Observed ${pct(point.value[1], 1)}` },
    xAxis: axis({ type: "value", min: 0, max: 1, name: view === "raw" ? "Raw model score" : "Calibrated failure risk", nameLocation: "middle", nameGap: 32,
                  axisLabel: { color: C.muted, formatter: (value) => `${value * 100}%` } }),
    yAxis: axis({ type: "value", min: 0, max: 1, name: "Observed failure rate", nameLocation: "middle", nameGap: 46,
                  axisLabel: { color: C.muted, formatter: (value) => `${value * 100}%` } }),
    series: [
      { name: "Perfect calibration", type: "line", data: [[0, 0], [1, 1]], symbol: "none", lineStyle: { color: C.ink, type: "dashed", width: 1 }, tooltip: { show: false } },
      ...CLASSES.map((cls) => ({ name: CLASS[cls].name, type: "line", smooth: true, symbolSize: 7, data: calibration.curves[cls][view],
                                  itemStyle: { color: CLASS[cls].color }, lineStyle: { width: 3 } })),
    ],
  };
}

function performanceOption(cards, metric) {
  return {
    ...chartBase,
    grid: { left: 58, right: 24, top: 26, bottom: 42 },
    tooltip: { ...chartBase.tooltip, trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value) => metric === "pr_auc" ? Number(value).toFixed(2) : pct(value, 1) },
    xAxis: axis({ type: "category", data: CLASSES.map((cls) => CLASS[cls].name) }),
    yAxis: axis({ type: "value", min: 0, max: 1, name: PERFORMANCE[metric].label, nameLocation: "middle", nameGap: 42,
                  axisLabel: { color: C.muted, formatter: (value) => metric === "pr_auc" ? value.toFixed(1) : `${value * 100}%` } }),
    series: [{
      name: PERFORMANCE[metric].label,
      type: "bar",
      barMaxWidth: 84,
      data: CLASSES.map((cls) => {
        const model = cards.find((card) => card.cls === cls);
        return { value: model?.[metric], itemStyle: { color: CLASS[cls].color, borderRadius: [4, 4, 0, 0] } };
      }),
      label: { show: true, position: "top", color: C.ink, fontWeight: 600, formatter: (point) => metric === "pr_auc" ? point.value.toFixed(2) : pct(point.value, 1) },
    }],
  };
}

function volumeOption(rows) {
  const byClass = Object.fromEntries(rows.map((row) => [row.machine_class, row]));
  return {
    ...chartBase,
    grid: { left: 155, right: 20, top: 34, bottom: 24 },
    legend: { top: 0, left: 0, textStyle: { color: C.muted }, itemWidth: 14 },
    tooltip: { ...chartBase.tooltip, trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value) => pct(value) },
    xAxis: axis({ type: "value", max: 1, axisLabel: { color: C.muted, formatter: (value) => `${value * 100}%` } }),
    yAxis: axis({ type: "category", inverse: true, data: ["Counting every reading", "One snapshot per shift"], axisLabel: { color: C.ink } }),
    series: CLASSES.map((cls) => ({
      name: CLASS[cls].name,
      type: "bar",
      stack: "volume",
      barWidth: 30,
      itemStyle: { color: CLASS[cls].color },
      label: { show: true, color: "#fff", formatter: (point) => (point.value > 0.08 ? pct(point.value) : "") },
      data: [byClass[cls].share_of_reading_alerts, byClass[cls].share_of_window_alerts],
    })),
  };
}
