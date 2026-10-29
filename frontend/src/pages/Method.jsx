import React from "react";
import { CLASS, CLASSES } from "../theme.js";

const FLOW = [
  { title: "Sensor readings", text: "Motors every 15 min, pumps every 30 min, compressors every hour." },
  { title: "Trend features", text: "Each reading is summarised with its 2-hour and 6-hour averages, spread and trend." },
  { title: "One model per machine type", text: "Each model predicts the chance of failure in the next 24 hours." },
  { title: "One snapshot per shift", text: "Every 6 hours, each machine's latest reading is scored, so fast reporters don't flood the list." },
  { title: "Calibration", text: "Each model's scores are re-scaled on held-back data so that 30% means 30%." },
  { title: "Priority", text: "Calibrated risk × consequence of failure × freshness of the data." },
  { title: "Maintenance queue", text: "The top machines, up to the crew's capacity, with a plain reason for each." },
];

export default function Method({ fleet }) {
  return (
    <div className="page method">
      <h1>How it works</h1>
      <p className="lede">From raw sensor readings to a ranked list a maintenance lead can act on.</p>

      <ol className="flow">
        {FLOW.map((f) => (
          <li key={f.title}><h3>{f.title}</h3><p>{f.text}</p></li>
        ))}
      </ol>

      <div className="two-col">
        <section className="panel">
          <h2>The priority rule</h2>
          <p className="formula">
            priority = calibrated risk × consequence × 0.5<sup>(data age ÷ 2 h)</sup>
          </p>
          <ul className="plain">
            {CLASSES.map((c) => {
              const info = fleet.classes.find((x) => x.id === c);
              return <li key={c}><b style={{ color: CLASS[c].color }}>{CLASS[c].name}</b>: consequence weight {info.severity}</li>;
            })}
          </ul>
          <p className="muted small">
            Consequence weights are assumptions for this prototype. A plant would set them from its downtime cost
            per hour for each machine type. Data that is 2 hours old counts half; a machine silent for 12 hours
            drops out of the queue.
          </p>
        </section>
        <section className="panel">
          <h2>How the results were tested</h2>
          <ul className="plain">
            <li>120 days of simulated operation: 60 machines and 763 failures.</li>
            <li>Split by time: the first 60% to train the models, the next 20% to calibrate, the last 20% to test. A 24-hour gap at each cut stops future information leaking into training.</li>
            <li>Every ranking rule is scored on the same untouched test shifts.</li>
            <li>Differences are checked with 1,000 resamples of those shifts, so we can tell real effects from noise.</li>
          </ul>
        </section>
      </div>

      <div className="two-col">
        <section className="panel">
          <h2>What is AI here, and what is a rule</h2>
          <ul className="plain">
            <li><b>Machine learning:</b> the three failure-prediction models (Random Forest, Gradient Boosting, Logistic Regression) and the calibration models.</li>
            <li><b>Rules:</b> the priority formula and the class safeguard. They are kept as transparent rules on purpose, so a maintenance lead can see and challenge them.</li>
            <li><b>Live in this app:</b> the explanations and the what-if simulator call the real trained models each time you use them.</li>
          </ul>
        </section>
        <section className="panel">
          <h2>Limits and next steps</h2>
          <ul className="plain">
            <li>The data is simulated. Results show how the method behaves, not accuracy on real equipment.</li>
            <li>Next: a pilot on one production line using its historian data and maintenance records, run alongside current practice for 4–8 weeks.</li>
            <li>Then: consequence weights from real downtime costs, monitoring for model drift, and export of the queue to the maintenance system.</li>
          </ul>
          <p className="muted small">Developers: the API is documented at <a href="/docs">/docs</a>.</p>
        </section>
      </div>
    </div>
  );
}
