import React from "react";
import { CLASS, pct } from "../theme.js";
import { ClassTag } from "./ui.jsx";

/** The maintenance queue as the crew lead would read it. */
export default function Queue({ queue, strategy, onOpen, selected, onSelect, showTruth }) {
  if (!queue.length) return <p className="muted">No machines reported in this window.</p>;
  return (
    <ol className="queue">
      {queue.map((m) => (
        <li key={m.id} className={`${selected === m.id ? "selected" : ""}`}>
          <button className="q-main" onClick={() => onSelect(m.id)} aria-label={`Select ${m.id}`}>
            <span className="q-rank">{m.rank}</span>
            <span className="q-id">
              <b>{m.id}</b>
              <ClassTag cls={m.cls} />
              {m.status === "new" && <span className="pill new">New</span>}
              {m.promoted && <span className="pill promoted" title="Added by the class safeguard">Safeguard</span>}
              {showTruth && (m.fails_24h
                ? <span className="pill fail">Failed within 24 h</span>
                : <span className="pill ok">No failure</span>)}
            </span>
            <span className="q-why">
              {strategy === "S1_raw"
                ? <>Raw model score {pct(m.raw)}</>
                : <>
                    <span><b>{pct(m.risk)}</b> failure risk</span>
                    {strategy !== "S2_calibrated" && <>
                      <span>consequence ×{m.severity}</span>
                      <span>{m.freshness >= 0.99 ? "live data" : `data ${Math.round(m.age_min)} min old`}</span>
                    </>}
                  </>}
            </span>
            <span className="q-score" aria-label={`Priority ${m.priority}`}>
              <span style={{ width: `${Math.min(1, m.priority) * 100}%`, background: CLASS[m.cls].color }} />
            </span>
          </button>
          <button className="link" onClick={() => onOpen(m.id)}>Open</button>
        </li>
      ))}
    </ol>
  );
}
