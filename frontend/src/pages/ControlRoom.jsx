import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { fmtTime, pct } from "../theme.js";
import FloorMap, { RiskLegend } from "../components/FloorMap.jsx";
import Queue from "../components/Queue.jsx";
import WhyPanel from "../components/WhyPanel.jsx";
import { CrewSlider, Loading, StrategyPicker } from "../components/ui.jsx";

const SPEEDS = [{ label: "1×", ms: 1600 }, { label: "2×", ms: 800 }, { label: "4×", ms: 400 }];

export default function ControlRoom({ fleet, strategy, setStrategy, k, setK, w, setW, openMachine }) {
  const nWin = fleet.windows.length;
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(0);
  const [truth, setTruth] = useState(false);
  const [selected, setSelected] = useState(null);
  const win = useAsync(() => api.window(w, strategy, k), [w, strategy, k]);
  const timer = useRef(null);

  useEffect(() => {
    if (!playing) return undefined;
    timer.current = setInterval(() => {
      setW((x) => {
        if (x + 1 >= nWin) { setPlaying(false); return x; }
        api.window(Math.min(x + 2, nWin - 1), strategy, k); // prefetch
        return x + 1;
      });
    }, SPEEDS[speed].ms);
    return () => clearInterval(timer.current);
  }, [playing, speed, strategy, k, nWin, setW]);

  const data = win.data;
  useEffect(() => {
    if (data && !selected && data.queue.length) setSelected(data.queue[0].id);
  }, [data, selected]);
  const sel = data?.machines.find((m) => m.id === selected);

  return (
    <div className="page control">
      <div className="control-head">
        <div>
          <h1>Control room</h1>
          <p className="lede">
            Every 6 hours the three models score each machine's latest readings. The queue on the right is what the
            maintenance lead acts on. Press play to watch the plant run.
          </p>
        </div>
        <div className="controls">
          <StrategyPicker strategy={strategy} setStrategy={setStrategy} />
          <CrewSlider k={k} setK={setK} />
          <label className="toggle">
            <input type="checkbox" checked={truth} onChange={(e) => setTruth(e.target.checked)} />
            <span>Reveal what actually happened</span>
          </label>
        </div>
      </div>

      <div className="replay" role="group" aria-label="Replay controls">
        <button className="play" onClick={() => { if (w >= nWin - 1) setW(0); setPlaying((p) => !p); }}
                aria-label={playing ? "Pause replay" : "Play replay"}>
          {playing
            ? <svg viewBox="0 0 20 20" width="18"><rect x="4" y="3" width="4" height="14" /><rect x="12" y="3" width="4" height="14" /></svg>
            : <svg viewBox="0 0 20 20" width="18"><path d="M5 3l12 7-12 7z" /></svg>}
        </button>
        <div className="speeds">
          {SPEEDS.map((s, i) => (
            <button key={s.label} className={speed === i ? "on" : ""} onClick={() => setSpeed(i)}
                    aria-label={`Speed ${s.label}`}>{s.label}</button>
          ))}
        </div>
        <span className="clock">{fmtTime(fleet.windows[w].end)}</span>
        <input className="scrub" type="range" min={0} max={nWin - 1} value={w}
               onChange={(e) => { setPlaying(false); setW(Number(e.target.value)); }}
               aria-label="Review window" />
        <span className="muted small">Shift {w + 1} of {nWin}</span>
      </div>

      {!data ? <Loading what="Scoring the fleet" /> : (
        <>
          <div className="kpis">
            <Kpi n={data.summary.reporting} of={fleet.machines.length} label="machines reporting" />
            <Kpi n={data.summary.high_risk} label="at 50%+ failure risk" />
            <Kpi n={data.summary.new_alerts} label="new in the queue this shift" />
            {truth
              ? <Kpi n={data.summary.caught} of={data.summary.failing_24h} label="machines that really failed within 24 h were in the queue" tone={data.summary.caught < data.summary.failing_24h ? "warn" : "good"} />
              : <Kpi n={k} label="crew slots this shift" />}
          </div>

          <div className="control-grid">
            <div className="panel map-panel">
              <FloorMap machines={data.machines} selected={selected} onSelect={setSelected} showTruth={truth} />
              <RiskLegend showTruth={truth} />
            </div>
            <div className="panel queue-panel">
              <h2>Maintenance queue</h2>
              <Queue queue={data.queue} strategy={strategy} onOpen={openMachine} selected={selected}
                     onSelect={setSelected} showTruth={truth} />
              {truth && data.summary.failing_24h > data.summary.caught && (
                <p className="missed">
                  Missed: {data.machines.filter((m) => m.fails_24h && !m.in_queue)
                    .map((m) => `${m.id} (position ${m.rank ?? "–"})`).join(", ")}
                </p>
              )}
            </div>
          </div>

          {sel && (
            <div className="panel why-panel">
              <div className="why-head">
                <h2>Why is {sel.id} at {pct(sel.risk)}?</h2>
                <button className="btn" onClick={() => openMachine(sel.id)}>Open {sel.id} in detail</button>
              </div>
              {sel.status === "offline"
                ? <p className="muted">{sel.id} has not sent readings recently, so it is not ranked.</p>
                : <WhyPanel machineId={sel.id} cls={sel.cls} w={data.window} />}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Kpi({ n, of, label, tone }) {
  return (
    <div className={`kpi ${tone || ""}`}>
      <b>{n}{of != null && <small>/{of}</small>}</b>
      <span>{label}</span>
    </div>
  );
}
