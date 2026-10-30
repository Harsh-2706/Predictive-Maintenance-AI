import React from "react";
import { CLASS, CLASSES, MODEL_NAME } from "../theme.js";

const MACHINE_SYMBOL = {
  motor: "M",
  pump: "P",
  compressor: "C",
};

export function StoryFleetVisual() {
  return (
    <figure className="section-visual story-fleet-visual">
      <svg viewBox="0 0 460 160" role="img" aria-labelledby="story-visual-title story-visual-desc">
        <title id="story-visual-title">Three machine classes feeding one maintenance queue</title>
        <desc id="story-visual-desc">Motor, pump, and compressor sensor readings flow through their models into a shared maintenance queue.</desc>
        <path className="visual-wire" d="M112 38H196M112 80H196M112 122H196M270 80H338" />
        <path className="visual-wire visual-wire-dash" d="M196 38L270 80M196 80H270M196 122L270 80" />
        {CLASSES.map((cls, index) => {
          const y = [38, 80, 122][index];
          return <g key={cls} style={{ "--visual-color": CLASS[cls].color }}>
            <rect className="visual-machine" x="24" y={y - 18} width="88" height="36" rx="4" />
            <text className="visual-symbol" x="40" y={y + 6}>{MACHINE_SYMBOL[cls]}</text>
            <text className="visual-label" x="60" y={y + 5}>{CLASS[cls].name.slice(0, -1)}</text>
            <circle className="visual-pulse" cx="144" cy={y} r="5" />
            <circle className="visual-pulse" cx="161" cy={y} r="3" />
            <rect className="visual-model" x="196" y={y - 13} width="74" height="26" rx="3" />
            <text className="visual-model-text" x="233" y={y + 4}>{index === 0 ? "risk" : index === 1 ? "risk" : "risk"}</text>
          </g>;
        })}
        <g className="visual-queue">
          <rect x="338" y="44" width="98" height="72" rx="4" />
          <text x="387" y="66">one crew</text>
          <path d="M357 79h59M357 91h47M357 103h33" />
          <circle cx="350" cy="79" r="3" /><circle cx="350" cy="91" r="3" /><circle cx="350" cy="103" r="3" />
        </g>
      </svg>
      <figcaption>Three specialised signals, one review queue.</figcaption>
    </figure>
  );
}

export function FairnessAllocationVisual({ capacity, focus }) {
  const slots = Array.from({ length: Math.min(capacity, 12) });
  return (
    <figure className="section-visual fairness-allocation-visual">
      <svg viewBox="0 0 460 160" role="img" aria-labelledby="fairness-visual-title fairness-visual-desc">
        <title id="fairness-visual-title">Capacity-constrained maintenance allocation</title>
        <desc id="fairness-visual-desc">Motor, pump, and compressor candidates are considered for a shared maintenance queue with {capacity} crew slots. The selected class is {CLASS[focus].name}.</desc>
        <text className="visual-caption" x="20" y="26">Candidates</text>
        {CLASSES.map((cls, index) => {
          const y = 50 + index * 35;
          return <g key={cls} style={{ "--visual-color": CLASS[cls].color }}>
            <circle className="visual-class-dot" cx="30" cy={y} r="9" />
            <text className="visual-symbol visual-symbol-light" x="26" y={y + 5}>{MACHINE_SYMBOL[cls]}</text>
            <path className="visual-wire" d={`M44 ${y}H160`} />
            <circle className="visual-pulse" cx="75" cy={y} r="4" />
            <circle className="visual-pulse" cx="101" cy={y} r="4" />
            <circle className="visual-pulse" cx="127" cy={y} r="4" />
          </g>;
        })}
        <path className="visual-wire visual-wire-dash" d="M160 50L214 80M160 85H214M160 120L214 80" />
        <rect className="visual-gate" x="214" y="46" width="54" height="68" rx="4" />
        <text className="visual-model-text" x="241" y="76">rank</text>
        <text className="visual-model-text" x="241" y="91">policy</text>
        <path className="visual-wire" d="M268 80H300" />
        <text className="visual-caption" x="304" y="26">Crew slots</text>
        {slots.map((_, index) => <rect key={index} className="visual-slot" x={304 + (index % 4) * 33} y={46 + Math.floor(index / 4) * 31} width="24" height="21" rx="3" />)}
        <text className="visual-queue-label" x="304" y="144">{capacity} inspections / six-hour shift</text>
      </svg>
      <figcaption>Capacity constrains allocation; it does not change failure share.</figcaption>
    </figure>
  );
}

export function ModelCalibrationVisual() {
  return (
    <figure className="section-visual model-calibration-visual">
      <svg viewBox="0 0 460 160" role="img" aria-labelledby="models-visual-title models-visual-desc">
        <title id="models-visual-title">Machine-specific models and calibration</title>
        <desc id="models-visual-desc">Random Forest, Gradient Boosting, and Logistic Regression models feed class-specific calibration into comparable failure probabilities.</desc>
        {CLASSES.map((cls, index) => {
          const x = 20 + index * 106;
          return <g key={cls} style={{ "--visual-color": CLASS[cls].color }}>
            <rect className="visual-model-card" x={x} y="20" width="88" height="60" rx="4" />
            <text className="visual-model-acronym" x={x + 44} y="47">{index === 0 ? "RF" : index === 1 ? "GB" : "LR"}</text>
            <text className="visual-model-small" x={x + 44} y="65">{CLASS[cls].one}</text>
            <path className="visual-wire" d={`M${x + 44} 80V104`} />
          </g>;
        })}
        <path className="visual-wire visual-wire-dash" d="M64 104L190 122M170 104L190 122M276 104L190 122" />
        <circle className="visual-calibration-node" cx="190" cy="122" r="20" />
        <text className="visual-symbol" x="178" y="128">cal</text>
        <path className="visual-wire" d="M210 122H252" />
        <g className="visual-probability">
          <rect x="252" y="99" width="174" height="46" rx="4" />
          <path d="M271 130c20-31 42 10 63-13 17-18 35-15 71-27" />
          <path className="visual-diagonal" d="M271 136l136-31" />
          <text x="339" y="154">calibrated failure probability</text>
        </g>
      </svg>
      <figcaption>{MODEL_NAME.random_forest}, {MODEL_NAME.gradient_boosting}, and {MODEL_NAME.logistic_regression} become comparable only after calibration.</figcaption>
    </figure>
  );
}

export function MethodPipelineVisual() {
  const stages = ["Sensors", "Features", "Models", "Calibration", "Fusion", "Queue"];
  return (
    <figure className="section-visual method-pipeline-visual">
      <svg viewBox="0 0 520 138" role="img" aria-labelledby="method-visual-title method-visual-desc">
        <title id="method-visual-title">Six-stage predictive maintenance pipeline</title>
        <desc id="method-visual-desc">Sensor simulation, feature engineering, machine-specific models, risk calibration, alert fusion, and the maintenance queue in sequence.</desc>
        {stages.map((stage, index) => {
          const x = 16 + index * 84;
          return <g key={stage} className="visual-stage" style={{ "--stage-index": index }}>
            {index > 0 && <path className="visual-wire" d={`M${x - 16} 66H${x - 4}`} />}
            <rect x={x} y="43" width="64" height="46" rx="4" />
            <text x={x + 32} y="64">{String(index + 1).padStart(2, "0")}</text>
            <text x={x + 32} y="107">{stage}</text>
          </g>;
        })}
      </svg>
      <ol className="method-pipeline-stack" aria-label="Six-stage pipeline">
        {stages.map((stage, index) => <li key={stage}><span>{String(index + 1).padStart(2, "0")}</span>{stage}</li>)}
      </ol>
      <figcaption>Six inspectable stages keep prediction, calibration, and policy distinct.</figcaption>
    </figure>
  );
}
