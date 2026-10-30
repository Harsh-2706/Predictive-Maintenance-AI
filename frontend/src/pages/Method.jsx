import React from "react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { CLASS, CLASSES, MODEL_NAME, STRATEGY, pct } from "../theme.js";
import { ErrorState, Loading } from "../components/ui.jsx";

const ARCHITECTURE = [
  { n: "01", title: "Sensor simulation", text: "Class-specific sensor streams arrive at 15, 30, or 60-minute cadences." },
  { n: "02", title: "Feature engineering", text: "Time-based 2-hour and 6-hour summaries retain comparable physical windows." },
  { n: "03", title: "Machine-specific models", text: "Each class is scored by its own trained failure model." },
  { n: "04", title: "Risk calibration", text: "Validation-fitted isotonic curves turn model scores into calibrated risk." },
  { n: "05", title: "Alert fusion", text: "A transparent policy ranks raw score, risk, consequence, freshness, or coverage." },
  { n: "06", title: "Maintenance queue", text: "One latest-reading snapshot per reporting machine competes for crew slots every six hours." },
];

const STRATEGY_NOTES = {
  S1_raw: "Ranks the original model score. It is the baseline, but scores from different models need not mean the same failure probability.",
  S2_calibrated: "Ranks calibrated failure risk, making probabilities comparable across the machine-specific models.",
  S3_risk_priority: "Ranks calibrated risk × the assumed severity weight × data freshness. The result is a priority score, not a probability.",
  S4_class_fair: "Uses the S3 score, then may promote an eligible class leader when a class has no queue slot. It improves visibility, not model accuracy by itself.",
};

export default function Method({ fleet }) {
  const models = useAsync(() => api.models(), []);

  if (models.error) {
    return <div className="page method"><ErrorState title="Couldn't load methodology evidence" error={models.error} onRetry={models.retry}>
      The sampling-rate diagnostic is calculated from the same plant data used by the maintenance queue.
    </ErrorState></div>;
  }
  if (!models.data) return <div className="page method"><Loading what="Loading methodology evidence" /></div>;

  const byClass = Object.fromEntries(models.data.volume.map((row) => [row.machine_class, row]));
  const machineTotal = fleet.classes.reduce((sum, item) => sum + item.count, 0);
  const info = (cls) => fleet.classes.find((item) => item.id === cls);

  return (
    <div className="page method">
      <p className="method-kicker">Methodology &amp; research transparency</p>
      <h1>From sensor stream to maintenance decision.</h1>
      <p className="lede">A transparent pipeline turns machine-specific failure risk into one capacity-constrained queue—while keeping probabilities, assumptions, and policy choices separate.</p>

      <section className="method-architecture" aria-labelledby="architecture-title">
        <div className="method-section-head">
          <div>
            <p className="method-kicker">System architecture</p>
            <h2 id="architecture-title">A traceable path from reading to action</h2>
          </div>
          <p>Every queue entry can be traced through the same six stages. The ranking policy is deliberately separate from the prediction models.</p>
        </div>
        <ol className="architecture-flow">
          {ARCHITECTURE.map((step) => (
            <li key={step.n}>
              <span>{step.n}</span>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="method-models" aria-labelledby="modelling-title">
        <div className="method-section-head">
          <div>
            <p className="method-kicker">Multi-machine modelling</p>
            <h2 id="modelling-title">One prediction task, three specialised models</h2>
          </div>
          <p>Each model predicts whether its own machine will fail within the next {fleet.horizon_hours} hours. Different sensors and sampling cadences are not forced into one generic model.</p>
        </div>
        <div className="method-machine-grid">
          {CLASSES.map((cls) => {
            const machine = info(cls);
            return <article key={cls} className="method-machine" style={{ "--machine-color": CLASS[cls].color }}>
              <span>{CLASS[cls].name}</span>
              <h3>{MODEL_NAME[machine.model]}</h3>
              <dl>
                <div><dt>Sampling</dt><dd>Every {machine.sample_every_min} min</dd></div>
                <div><dt>Target</dt><dd>Failure within {fleet.horizon_hours} h</dd></div>
                <div><dt>Sensors</dt><dd>{machine.sensors.join(", ")}</dd></div>
              </dl>
            </article>;
          })}
        </div>
        <p className="method-note">Feature windows are measured in time—not row count—so a motor and compressor describe the same 2-hour and 6-hour operating periods despite reporting at different rates.</p>
      </section>

      <section className="panel method-fusion" aria-labelledby="fusion-title">
        <div className="method-section-head">
          <div>
            <p className="method-kicker">Alert fusion strategies</p>
            <h2 id="fusion-title">The model estimates risk; policy decides what reaches the crew</h2>
          </div>
          <p>All four strategies are evaluated on the same held-out six-hour review windows. They add one policy choice at a time.</p>
        </div>
        <div className="strategy-method-list">
          {Object.keys(STRATEGY).map((id) => (
            <article key={id} style={{ "--strategy-color": STRATEGY[id].color }}>
              <div><span>{id.slice(0, 2)}</span><h3>{STRATEGY[id].short}</h3></div>
              <p>{STRATEGY_NOTES[id]}</p>
            </article>
          ))}
        </div>
        <p className="formula">S3 priority = calibrated risk × severity weight × 0.5<sup>(data age ÷ 2 h)</sup></p>
        <p className="fine">S4 only considers a class leader eligible when its calibrated risk is at least 20%; it does not reserve a slot for low-risk equipment.</p>
      </section>

      <section className="method-sampling" aria-labelledby="sampling-title">
        <div className="method-section-head">
          <div>
            <p className="method-kicker">Fairness &amp; sampling-rate mitigation</p>
            <h2 id="sampling-title">A fast reporter gets more readings, not more votes</h2>
          </div>
          <p>At each six-hour review point, the system keeps only each reporting machine’s latest reading. A reading more than 12 hours old is treated as not reporting.</p>
        </div>
        <div className="sampling-evidence" aria-label="Alert shares before and after six-hour snapshots">
          {CLASSES.map((cls) => {
            const row = byClass[cls];
            return <article key={cls} style={{ "--machine-color": CLASS[cls].color }}>
              <h3>{CLASS[cls].name}</h3>
              <div><span>Share when every alerting reading is counted</span><b>{pct(row?.share_of_reading_alerts, 1)}</b></div>
              <div><span>Share after one snapshot per review shift</span><b>{pct(row?.share_of_window_alerts, 1)}</b></div>
            </article>;
          })}
        </div>
        <p className="method-note">These are observed alert-volume shares from the generated test data, not failure shares or recall. Queue allocation and captured failures remain policy outcomes, reported separately in the Fairness Lab.</p>
      </section>

      <section className="method-transparency" aria-labelledby="transparency-title">
        <div className="method-section-head">
          <div>
            <p className="method-kicker">Assumptions &amp; limitations</p>
            <h2 id="transparency-title">What the evidence does—and does not—support</h2>
          </div>
        </div>
        <div className="transparency-grid">
          <article>
            <h3>Research protocol</h3>
            <ul className="plain">
              <li>{machineTotal} machines over 120 days of simulated operation.</li>
              <li>Chronological split: 60% training, 20% calibration, 20% held-out testing, with a 24-hour gap at each boundary.</li>
              <li>Calibration is fitted only on validation predictions; queue policies are compared on identical untouched test shifts.</li>
              <li>Uncertainty intervals use 1,000 paired bootstrap resamples of review windows.</li>
            </ul>
          </article>
          <article>
            <h3>Deployment limits</h3>
            <ul className="plain">
              <li>Sensor streams and failure outcomes are simulated; they demonstrate method behaviour, not field accuracy.</li>
              <li>Severity weights are prototype assumptions: motor {info("motor").severity}, pump {info("pump").severity}, compressor {info("compressor").severity}.</li>
              <li>The {fleet.horizon_hours}-hour prediction target, cadence, and queue capacity must be validated against plant operations before use.</li>
              <li>A production deployment would require historian data, maintenance records, drift monitoring, and locally agreed consequence weights.</li>
            </ul>
          </article>
        </div>
        <p className="fine method-disclosure">This prototype keeps model estimation, probability calibration, and maintenance policy inspectable rather than treating the final queue as an unexplained AI output. API details are available at <a href="/docs">/docs</a>.</p>
      </section>
    </div>
  );
}
