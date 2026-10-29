import React from "react";
import { CLASS, CLASSES, riskColor, pct } from "../theme.js";

/**
 * The plant floor: every machine is a tile in its bay, filled by calibrated
 * failure risk. Machines in the maintenance queue get a hazard-stripe frame.
 */
export default function FloorMap({ machines, selected, onSelect, showTruth, compact }) {
  const byClass = Object.fromEntries(CLASSES.map((c) => [c, []]));
  machines.forEach((m) => byClass[m.cls].push(m));
  CLASSES.forEach((c) => byClass[c].sort((a, b) => a.id.localeCompare(b.id)));

  return (
    <div className={`floor ${compact ? "compact" : ""}`}>
      {CLASSES.map((cls) => (
        <section key={cls} className={`bay bay-${cls}`} style={{ "--c": CLASS[cls].color }}
                 aria-label={`${CLASS[cls].bay}, ${byClass[cls].length} machines`}>
          <header>
            <span>{CLASS[cls].bay}</span>
            <small>{byClass[cls].filter((m) => m.in_queue).length} in queue</small>
          </header>
          <div className="tiles">
            {byClass[cls].map((m) => {
              const offline = m.status === "offline";
              const cls2 = ["tile", m.in_queue && "queued", offline && "offline",
                            selected === m.id && "selected", showTruth && m.fails_24h && "truth"]
                .filter(Boolean).join(" ");
              const label = offline
                ? `${m.id}: not reporting`
                : `${m.id}: failure risk ${pct(m.risk)}${m.in_queue ? `, queue position ${m.rank}` : ""}`
                  + (showTruth && m.fails_24h ? ", fails within 24 h" : "");
              return (
                <button key={m.id} className={cls2} style={{ "--fill": riskColor(m.risk) }}
                        title={label} aria-label={label} onClick={() => onSelect && onSelect(m.id)}>
                  <span className="id">{m.id.split("-")[1]}</span>
                  {m.in_queue && <span className="rank">{m.rank}</span>}
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

export function RiskLegend({ showTruth }) {
  const stops = [0, 0.1, 0.25, 0.5, 0.75, 1];
  return (
    <div className="legend">
      <span>Failure risk in next 24 h</span>
      <span className="ramp">
        {stops.map((s) => <i key={s} style={{ background: riskColor(s) }} title={pct(s)} />)}
      </span>
      <span className="ramp-labels"><small>0%</small><small>100%</small></span>
      <span className="legend-item"><i className="sw queued" />In maintenance queue</span>
      <span className="legend-item"><i className="sw offline" />Not reporting</span>
      {showTruth && <span className="legend-item"><i className="sw truth" />Actually failed within 24 h</span>}
    </div>
  );
}
