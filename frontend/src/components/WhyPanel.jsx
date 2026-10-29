import React from "react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { CLASS, pct, sensorName, sensorUnit } from "../theme.js";
import { Loading } from "./ui.jsx";

/**
 * Live explanation from the real model: for each sensor, the risk the model
 * gives if that sensor alone were back at its normal level.
 */
export default function WhyPanel({ machineId, cls, w }) {
  const ex = useAsync(() => api.explain(machineId, w), [machineId, w]);
  if (ex.error) return <p className="muted">{machineId} did not report in this window, so there is nothing to explain.</p>;
  if (!ex.data) return <Loading what="Asking the model" />;
  const d = ex.data;
  const top = d.drivers[0];
  return (
    <div className="why">
      <p className="why-lead">
        The {CLASS[cls].one} model puts {machineId} at <b>{pct(d.risk)}</b> risk of failing in the next 24 hours.
        {top && top.contribution > 0.05 && (
          <> The biggest driver is <b>{sensorName(top.sensor).toLowerCase()}</b>: if it were normal, risk would
            drop to {pct(top.risk_if_normal)}.</>
        )}
      </p>
      <ul className="drivers">
        {d.drivers.map((dr) => (
          <li key={dr.sensor}>
            <span className="dr-name">{sensorName(dr.sensor)}</span>
            <span className="dr-val">
              {dr.value} {sensorUnit(dr.sensor)} <small>normal {dr.normal}</small>
            </span>
            <span className="dr-bar" title={`Risk if ${dr.sensor} were normal: ${pct(dr.risk_if_normal)}`}>
              <i style={{ width: `${Math.max(0, dr.contribution) / Math.max(d.risk, 0.01) * 100}%` }} />
            </span>
            <span className="dr-num">{dr.contribution > 0 ? "+" : ""}{(dr.contribution * 100).toFixed(0)} pts</span>
          </li>
        ))}
      </ul>
      <p className="fine">
        Points = how much lower the risk would be if only that sensor were at its normal level. Computed live by
        re-running the model.
      </p>
    </div>
  );
}
